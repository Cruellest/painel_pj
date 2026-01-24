# -*- coding: utf-8 -*-
"""
Serviços de lógica de negócio para BERT Training.
"""

import hashlib
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
import pandas as pd
import logging

from sqlalchemy.orm import Session
from sqlalchemy import select

from sistemas.bert_training.models import (
    BertDataset, BertRun, BertJob, BertMetric, BertLog, BertWorker,
    TaskType, JobStatus
)
from sistemas.bert_training.schemas import (
    ExcelValidationResult, HyperparametersConfig, TaskTypeEnum
)
from sistemas.bert_training.presets import (
    get_preset_by_name, get_default_preset, merge_preset_with_overrides, get_preset_config
)
from sistemas.bert_training.error_translator import (
    translate_error, get_friendly_error_message, get_quality_alert
)

logger = logging.getLogger(__name__)

# Diretório para armazenar datasets
DATASETS_DIR = Path("data/bert_datasets")
DATASETS_DIR.mkdir(parents=True, exist_ok=True)


def calculate_sha256(file_path: Path) -> str:
    """Calcula o hash SHA256 de um arquivo."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def validate_excel_file(
    file_path: Path,
    task_type: TaskTypeEnum,
    text_column: str,
    label_column: str
) -> ExcelValidationResult:
    """
    Valida um arquivo Excel para treinamento.

    Args:
        file_path: Caminho do arquivo Excel
        task_type: Tipo de tarefa (text_classification ou token_classification)
        text_column: Nome da coluna de texto
        label_column: Nome da coluna de labels

    Returns:
        ExcelValidationResult com status de validação
    """
    errors = []
    warnings = []
    columns = []
    total_rows = 0
    sample_data = None

    try:
        # Tenta ler o Excel
        df = pd.read_excel(file_path, engine="openpyxl")
        columns = list(df.columns)
        total_rows = len(df)

        # Valida colunas existem
        if text_column not in columns:
            errors.append(f"Coluna de texto '{text_column}' não encontrada. Colunas disponíveis: {columns}")

        if label_column not in columns:
            errors.append(f"Coluna de labels '{label_column}' não encontrada. Colunas disponíveis: {columns}")

        if errors:
            return ExcelValidationResult(
                is_valid=False,
                errors=errors,
                columns=columns,
                total_rows=total_rows
            )

        # Valida dados não vazios
        text_nulls = df[text_column].isnull().sum()
        label_nulls = df[label_column].isnull().sum()

        if text_nulls > 0:
            warnings.append(f"Coluna de texto tem {text_nulls} valores nulos ({text_nulls/total_rows*100:.1f}%)")

        if label_nulls > 0:
            warnings.append(f"Coluna de labels tem {label_nulls} valores nulos ({label_nulls/total_rows*100:.1f}%)")

        # Validações específicas por tipo de tarefa
        if task_type == TaskTypeEnum.TEXT_CLASSIFICATION:
            # Text classification: texto é string, label é string/int
            non_string_text = df[text_column].apply(lambda x: not isinstance(x, str) if pd.notna(x) else False).sum()
            if non_string_text > 0:
                warnings.append(f"{non_string_text} valores na coluna de texto não são strings")

            # Conta labels únicas
            unique_labels = df[label_column].dropna().nunique()
            if unique_labels < 2:
                errors.append(f"Classificação requer pelo menos 2 labels distintas. Encontradas: {unique_labels}")
            elif unique_labels > 100:
                warnings.append(f"Muitas labels distintas ({unique_labels}). Considere reduzir para melhor performance.")

        elif task_type == TaskTypeEnum.TOKEN_CLASSIFICATION:
            # Token classification: tokens e tags são JSON strings ou listas
            def validate_json_column(col_name):
                invalid_count = 0
                for idx, val in df[col_name].items():
                    if pd.isna(val):
                        continue
                    try:
                        if isinstance(val, str):
                            parsed = json.loads(val)
                            if not isinstance(parsed, list):
                                invalid_count += 1
                        elif not isinstance(val, list):
                            invalid_count += 1
                    except json.JSONDecodeError:
                        invalid_count += 1
                return invalid_count

            invalid_tokens = validate_json_column(text_column)
            invalid_labels = validate_json_column(label_column)

            if invalid_tokens > 0:
                errors.append(f"{invalid_tokens} valores na coluna de tokens não são JSON válidos de lista")

            if invalid_labels > 0:
                errors.append(f"{invalid_labels} valores na coluna de tags não são JSON válidos de lista")

        # Mínimo de amostras
        if total_rows < 10:
            errors.append(f"Dataset muito pequeno ({total_rows} linhas). Mínimo recomendado: 100 amostras")
        elif total_rows < 100:
            warnings.append(f"Dataset pequeno ({total_rows} linhas). Recomendado: pelo menos 100 amostras")

        # Amostra dos dados
        sample_df = df.head(5)[[text_column, label_column]]
        sample_data = sample_df.to_dict(orient="records")

        return ExcelValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            columns=columns,
            total_rows=total_rows,
            sample_data=sample_data
        )

    except Exception as e:
        logger.error(f"Erro ao validar Excel: {e}")
        return ExcelValidationResult(
            is_valid=False,
            errors=[f"Erro ao ler arquivo Excel: {str(e)}"],
            columns=columns,
            total_rows=total_rows
        )


def extract_dataset_metadata(
    file_path: Path,
    task_type: TaskTypeEnum,
    text_column: str,
    label_column: str
) -> Dict[str, Any]:
    """
    Extrai metadados do dataset.

    Returns:
        Dicionário com total_rows, total_labels, label_distribution, sample_preview
    """
    df = pd.read_excel(file_path, engine="openpyxl")

    # Remove linhas com valores nulos nas colunas principais
    df_clean = df.dropna(subset=[text_column, label_column])

    # Distribuição de labels
    if task_type == TaskTypeEnum.TEXT_CLASSIFICATION:
        label_counts = df_clean[label_column].value_counts().to_dict()
        # Converte keys para string para JSON
        label_distribution = {str(k): int(v) for k, v in label_counts.items()}
        total_labels = len(label_distribution)
    else:
        # Para token classification, extrai labels únicas das tags
        all_labels = set()
        for tags in df_clean[label_column]:
            try:
                if isinstance(tags, str):
                    tags = json.loads(tags)
                if isinstance(tags, list):
                    all_labels.update(tags)
            except Exception:
                pass
        total_labels = len(all_labels)
        label_distribution = {label: 1 for label in list(all_labels)[:50]}  # Limita preview

    # Sample preview (primeiras 10 linhas)
    sample_df = df_clean.head(10)[[text_column, label_column]]
    sample_preview = sample_df.to_dict(orient="records")

    return {
        "total_rows": len(df_clean),
        "total_labels": total_labels,
        "label_distribution": label_distribution,
        "sample_preview": sample_preview
    }


def save_dataset_file(
    content: bytes,
    original_filename: str,
    sha256_hash: str
) -> Path:
    """
    Salva o arquivo do dataset no storage.

    Args:
        content: Conteúdo do arquivo em bytes
        original_filename: Nome original do arquivo
        sha256_hash: Hash SHA256 do conteúdo

    Returns:
        Caminho onde o arquivo foi salvo
    """
    # Usa o hash como nome do arquivo para evitar duplicatas
    ext = Path(original_filename).suffix
    file_path = DATASETS_DIR / f"{sha256_hash}{ext}"

    if not file_path.exists():
        file_path.write_bytes(content)
        logger.info(f"Dataset salvo em: {file_path}")
    else:
        logger.info(f"Dataset já existe: {file_path}")

    return file_path


def get_git_commit_hash() -> Optional[str]:
    """Obtém o hash do commit atual do Git."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent  # Raiz do projeto
        )
        if result.returncode == 0:
            return result.stdout.strip()[:40]
    except Exception as e:
        logger.warning(f"Não foi possível obter commit hash: {e}")
    return None


def get_environment_fingerprint() -> Optional[str]:
    """
    Gera um fingerprint do ambiente (requirements.txt hash ou similar).
    """
    try:
        requirements_path = Path(__file__).parent.parent.parent / "requirements.txt"
        if requirements_path.exists():
            return calculate_sha256(requirements_path)[:16]
    except Exception as e:
        logger.warning(f"Não foi possível gerar fingerprint do ambiente: {e}")
    return None


def create_run(
    db: Session,
    name: str,
    description: Optional[str],
    dataset: BertDataset,
    base_model: str,
    user_id: int,
    preset_name: Optional[str] = None,
    hyperparameters: Optional[HyperparametersConfig] = None,
    ip_address: Optional[str] = None
) -> BertRun:
    """
    Cria um novo run de treinamento.

    O usuario pode:
    1. Usar um preset (preset_name) - modo simples
    2. Fornecer hyperparameters customizados - modo avancado
    3. Combinar ambos (hyperparameters sobrescreve o preset)

    Se nenhum for fornecido, usa preset "equilibrado" como padrao.
    """
    # Determina a configuracao base
    if preset_name:
        config_json = get_preset_config(preset_name)
        used_preset_name = preset_name
    else:
        # Usa preset padrao
        config_json = get_preset_config("equilibrado")
        used_preset_name = "equilibrado"

    # Aplica overrides dos hyperparameters se fornecidos
    if hyperparameters:
        hp_dict = hyperparameters.model_dump()
        for key, value in hp_dict.items():
            if value is not None:
                config_json[key] = value
        # Se tem overrides customizados, marca como custom
        used_preset_name = f"{used_preset_name}_customizado"

    # Extrai campos principais para filtros
    learning_rate = config_json.get("learning_rate", 5e-5)
    batch_size = config_json.get("batch_size", 16)
    epochs = config_json.get("epochs", 10)
    max_length = config_json.get("max_length", 512)
    train_split = config_json.get("train_split", 0.8)
    seed = config_json.get("seed", 42)

    run = BertRun(
        name=name,
        description=description,
        dataset_id=dataset.id,
        dataset_sha256=dataset.sha256_hash,
        task_type=dataset.task_type,
        base_model=base_model,
        config_json=config_json,
        learning_rate=learning_rate,
        batch_size=batch_size,
        epochs=epochs,
        max_length=max_length,
        train_split=train_split,
        seed=seed,
        git_commit_hash=get_git_commit_hash(),
        environment_fingerprint=get_environment_fingerprint(),
        status="pending",
        created_by=user_id
    )

    db.add(run)
    db.commit()
    db.refresh(run)

    logger.info(f"Run criado: id={run.id}, name={run.name}, preset={used_preset_name}")
    return run


def create_job_for_run(db: Session, run: BertRun) -> BertJob:
    """
    Cria um job de treinamento para um run.
    """
    job = BertJob(
        run_id=run.id,
        status=JobStatus.PENDING,
        total_epochs=run.epochs
    )

    db.add(job)
    db.commit()
    db.refresh(job)

    logger.info(f"Job criado: id={job.id}, run_id={run.id}")
    return job


def claim_job(
    db: Session,
    worker: BertWorker,
    job: BertJob
) -> bool:
    """
    Worker tenta pegar um job para executar.

    Returns:
        True se conseguiu pegar o job, False caso contrário
    """
    if job.status != JobStatus.PENDING:
        return False

    job.status = JobStatus.CLAIMED
    job.worker_id = worker.id
    job.claimed_at = datetime.utcnow()

    worker.current_job_id = job.id
    worker.last_heartbeat = datetime.utcnow()

    db.commit()

    logger.info(f"Job {job.id} claimed by worker {worker.name}")
    return True


def update_job_progress(
    db: Session,
    job: BertJob,
    status: Optional[JobStatus] = None,
    current_epoch: Optional[int] = None,
    progress_percent: Optional[float] = None,
    error_message: Optional[str] = None
) -> None:
    """
    Atualiza o progresso de um job.
    """
    if status:
        job.status = status
        if status == JobStatus.TRAINING and not job.started_at:
            job.started_at = datetime.utcnow()
        elif status in [JobStatus.COMPLETED, JobStatus.FAILED]:
            job.completed_at = datetime.utcnow()

    if current_epoch is not None:
        job.current_epoch = current_epoch

    if progress_percent is not None:
        job.progress_percent = progress_percent

    if error_message:
        job.error_message = error_message

    db.commit()


def record_metric(
    db: Session,
    run_id: int,
    epoch: int,
    train_loss: Optional[float] = None,
    val_loss: Optional[float] = None,
    val_accuracy: Optional[float] = None,
    val_macro_f1: Optional[float] = None,
    val_weighted_f1: Optional[float] = None,
    val_macro_precision: Optional[float] = None,
    val_macro_recall: Optional[float] = None,
    seqeval_f1: Optional[float] = None,
    seqeval_precision: Optional[float] = None,
    seqeval_recall: Optional[float] = None,
    classification_report: Optional[Dict] = None,
    confusion_matrix: Optional[List[List[int]]] = None
) -> BertMetric:
    """
    Registra métricas de uma época de treinamento.
    """
    metric = BertMetric(
        run_id=run_id,
        epoch=epoch,
        train_loss=train_loss,
        val_loss=val_loss,
        val_accuracy=val_accuracy,
        val_macro_f1=val_macro_f1,
        val_weighted_f1=val_weighted_f1,
        val_macro_precision=val_macro_precision,
        val_macro_recall=val_macro_recall,
        seqeval_f1=seqeval_f1,
        seqeval_precision=seqeval_precision,
        seqeval_recall=seqeval_recall,
        classification_report=classification_report,
        confusion_matrix=confusion_matrix
    )

    db.add(metric)
    db.commit()
    db.refresh(metric)

    return metric


def record_log(
    db: Session,
    run_id: int,
    level: str,
    message: str,
    extra_data: Optional[Dict] = None,
    source: Optional[str] = None,
    epoch: Optional[int] = None,
    batch: Optional[int] = None
) -> BertLog:
    """
    Registra um log de treinamento.
    """
    log = BertLog(
        run_id=run_id,
        level=level,
        message=message,
        extra_data=extra_data,
        source=source,
        epoch=epoch,
        batch=batch
    )

    db.add(log)
    db.commit()
    db.refresh(log)

    return log


def finalize_run(
    db: Session,
    run: BertRun,
    success: bool,
    final_accuracy: Optional[float] = None,
    final_macro_f1: Optional[float] = None,
    final_weighted_f1: Optional[float] = None,
    model_fingerprint: Optional[str] = None,
    error_message: Optional[str] = None
) -> None:
    """
    Finaliza um run de treinamento.
    """
    if success:
        run.status = "completed"
        run.final_accuracy = final_accuracy
        run.final_macro_f1 = final_macro_f1
        run.final_weighted_f1 = final_weighted_f1
        run.model_fingerprint = model_fingerprint
    else:
        run.status = "failed"
        run.error_message = error_message

    run.completed_at = datetime.utcnow()
    db.commit()

    logger.info(f"Run {run.id} finalizado: status={run.status}")


def get_worker_by_token(db: Session, token: str) -> Optional[BertWorker]:
    """
    Busca worker pelo token de autenticação.
    """
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    return db.query(BertWorker).filter(
        BertWorker.token_hash == token_hash,
        BertWorker.is_active == True
    ).first()


def create_worker(
    db: Session,
    name: str,
    description: Optional[str] = None,
    gpu_name: Optional[str] = None,
    gpu_vram_gb: Optional[float] = None,
    cuda_version: Optional[str] = None
) -> Tuple[BertWorker, str]:
    """
    Cria um novo worker e retorna o token gerado.

    Returns:
        Tuple de (worker, token)
    """
    import secrets
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    worker = BertWorker(
        name=name,
        description=description,
        token_hash=token_hash,
        gpu_name=gpu_name,
        gpu_vram_gb=gpu_vram_gb,
        cuda_version=cuda_version,
        is_active=True
    )

    db.add(worker)
    db.commit()
    db.refresh(worker)

    logger.info(f"Worker criado: id={worker.id}, name={worker.name}")
    return worker, token


def update_worker_heartbeat(
    db: Session,
    worker: BertWorker,
    current_job_id: Optional[int] = None
) -> None:
    """
    Atualiza heartbeat do worker.
    """
    worker.last_heartbeat = datetime.utcnow()
    if current_job_id is not None:
        worker.current_job_id = current_job_id
    db.commit()


def get_pending_job(db: Session) -> Optional[BertJob]:
    """
    Busca o próximo job pendente na fila.
    """
    return db.query(BertJob).filter(
        BertJob.status == JobStatus.PENDING
    ).order_by(BertJob.created_at.asc()).first()


def get_dataset_file_path(dataset: BertDataset) -> Path:
    """
    Retorna o caminho do arquivo do dataset.
    """
    return Path(dataset.file_path)


def validate_reproduce_run(db: Session, run_id: int) -> Tuple[bool, str]:
    """
    Valida se um run pode ser reproduzido.

    Returns:
        Tuple de (pode_reproduzir, mensagem)
    """
    run = db.query(BertRun).filter(BertRun.id == run_id).first()
    if not run:
        return False, "Run não encontrado"

    dataset = db.query(BertDataset).filter(BertDataset.id == run.dataset_id).first()
    if not dataset:
        return False, "Dataset do run não encontrado"

    # Verifica se o arquivo do dataset existe
    if not Path(dataset.file_path).exists():
        return False, "Arquivo do dataset não encontrado no storage"

    # Verifica integridade do dataset
    current_hash = calculate_sha256(Path(dataset.file_path))
    if current_hash != dataset.sha256_hash:
        return False, "Integridade do dataset comprometida (hash diferente)"

    return True, "Run pode ser reproduzido"


# ==================== Estimativa de Tempo ====================

def estimate_training_time(
    db: Session,
    dataset_rows: int,
    epochs: int,
    batch_size: int,
    base_model: str
) -> Optional[Dict[str, int]]:
    """
    Estima o tempo de treinamento baseado em historico.

    Retorna:
        Dicionario com min_minutes e max_minutes, ou None se nao houver historico
    """
    # Busca runs completados similares
    similar_runs = db.query(BertRun).filter(
        BertRun.status == "completed",
        BertRun.base_model == base_model,
        BertRun.started_at.isnot(None),
        BertRun.completed_at.isnot(None)
    ).limit(10).all()

    if not similar_runs:
        # Estimativa baseada em heuristica
        # ~1 minuto por 100 amostras por epoca (rough estimate)
        samples_per_minute = 100
        base_time = (dataset_rows * epochs) / samples_per_minute

        return {
            "min_minutes": max(5, int(base_time * 0.5)),
            "max_minutes": max(15, int(base_time * 1.5))
        }

    # Calcula tempo medio por amostra por epoca
    times = []
    for run in similar_runs:
        if run.started_at and run.completed_at:
            duration = (run.completed_at - run.started_at).total_seconds() / 60
            dataset = db.query(BertDataset).filter(BertDataset.id == run.dataset_id).first()
            if dataset and run.epochs:
                time_per_sample_epoch = duration / (dataset.total_rows * run.epochs)
                times.append(time_per_sample_epoch)

    if times:
        avg_time = sum(times) / len(times)
        estimated = avg_time * dataset_rows * epochs

        return {
            "min_minutes": max(5, int(estimated * 0.7)),
            "max_minutes": max(15, int(estimated * 1.3))
        }

    return None


# ==================== Auto-Batch VRAM ====================

def calculate_optimal_batch_size(
    vram_gb: float,
    max_length: int = 512,
    model_size: str = "base"
) -> int:
    """
    Calcula batch size seguro baseado em VRAM disponivel.

    Args:
        vram_gb: VRAM disponivel em GB
        max_length: Tamanho maximo de sequencia
        model_size: "base" ou "large"

    Returns:
        Batch size otimo (potencia de 2)
    """
    # Estimativa de VRAM por amostra (em GB)
    # Baseado em testes empiricos com BERT
    VRAM_PER_SAMPLE = {
        "base": {
            512: 0.5,
            256: 0.25,
            128: 0.15
        },
        "large": {
            512: 1.2,
            256: 0.6,
            128: 0.35
        }
    }

    # Usa valores mais proximos
    size_key = model_size if model_size in VRAM_PER_SAMPLE else "base"

    if max_length >= 512:
        length_key = 512
    elif max_length >= 256:
        length_key = 256
    else:
        length_key = 128

    vram_per_sample = VRAM_PER_SAMPLE[size_key][length_key]

    # Deixa 20% de margem de seguranca
    safe_vram = vram_gb * 0.8

    # Calcula batch size
    optimal = int(safe_vram / vram_per_sample)

    # Arredonda para potencia de 2 mais proxima (para eficiencia)
    if optimal <= 0:
        return 1

    import math
    power = int(math.log2(optimal))
    batch_size = 2 ** power

    # Limita entre 1 e 64
    return max(1, min(64, batch_size))


def detect_model_size(model_name: str) -> str:
    """
    Detecta se o modelo e base ou large pelo nome.
    """
    model_lower = model_name.lower()

    if "large" in model_lower:
        return "large"
    elif "xlarge" in model_lower or "xl" in model_lower:
        return "large"
    else:
        return "base"


def calculate_progress_with_estimate(
    job: BertJob,
    run: BertRun,
    current_epoch: int,
    epoch_start_time: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Calcula progresso com estimativa de tempo restante.

    Returns:
        Dicionario com progress_percent, current_epoch, total_epochs,
        estimated_remaining_minutes
    """
    total_epochs = run.epochs or 10
    progress_percent = (current_epoch / total_epochs) * 100

    result = {
        "progress_percent": round(progress_percent, 1),
        "current_epoch": current_epoch,
        "total_epochs": total_epochs,
        "current_epoch_label": f"Rodada {current_epoch} de {total_epochs}"
    }

    # Estima tempo restante baseado em tempo por epoca
    if job.started_at and current_epoch > 0:
        elapsed = (datetime.utcnow() - job.started_at).total_seconds() / 60
        time_per_epoch = elapsed / current_epoch
        remaining_epochs = total_epochs - current_epoch
        estimated_remaining = time_per_epoch * remaining_epochs

        result["estimated_remaining_minutes"] = max(1, int(estimated_remaining))
        result["estimated_remaining_label"] = f"~{result['estimated_remaining_minutes']} minutos restantes"

    return result


# ==================== Validacoes Proativas ====================

def analyze_dataset_quality(
    df: pd.DataFrame,
    text_column: str,
    label_column: str
) -> Dict[str, Any]:
    """
    Analisa qualidade do dataset e retorna alertas.

    Returns:
        Dicionario com quality_score, warnings, errors, suggestions
    """
    warnings = []
    errors = []
    suggestions = []
    quality_score = 100  # Comeca em 100 e vai reduzindo

    total_rows = len(df)
    df_clean = df.dropna(subset=[text_column, label_column])
    valid_rows = len(df_clean)

    # Verifica valores nulos
    null_count = total_rows - valid_rows
    if null_count > 0:
        null_percent = (null_count / total_rows) * 100
        warnings.append({
            "type": "null_values",
            "message": f"{null_count} linhas ({null_percent:.1f}%) tem campos vazios e serao ignoradas.",
            "count": null_count
        })
        quality_score -= min(20, null_percent)

    # Verifica poucas amostras
    if valid_rows < 50:
        errors.append({
            "type": "too_few_samples",
            "message": f"Seu dataset tem apenas {valid_rows} amostras. Recomendamos pelo menos 100.",
            "count": valid_rows
        })
        quality_score -= 30
        suggestions.append("Adicione mais exemplos ao dataset.")
    elif valid_rows < 100:
        warnings.append({
            "type": "few_samples",
            "message": f"Seu dataset tem {valid_rows} amostras. Para melhores resultados, recomendamos pelo menos 100.",
            "count": valid_rows
        })
        quality_score -= 10
        suggestions.append("Considere adicionar mais exemplos.")

    # Verifica distribuicao de classes
    label_counts = df_clean[label_column].value_counts()
    num_classes = len(label_counts)

    if num_classes < 2:
        errors.append({
            "type": "single_class",
            "message": "Todas as amostras tem a mesma categoria. Voce precisa de pelo menos 2 categorias diferentes.",
            "count": 1
        })
        quality_score = 0

    # Verifica desbalanceamento
    if num_classes >= 2:
        max_count = label_counts.max()
        min_count = label_counts.min()
        imbalance_ratio = max_count / min_count if min_count > 0 else float('inf')

        if imbalance_ratio > 10:
            minority_classes = label_counts[label_counts < max_count / 10].index.tolist()
            warnings.append({
                "type": "severe_imbalance",
                "message": f"Algumas categorias tem muito menos exemplos ({', '.join(str(c) for c in minority_classes[:3])}). O modelo pode ignorar essas categorias.",
                "ratio": round(imbalance_ratio, 1),
                "minority_classes": minority_classes[:5]
            })
            quality_score -= 15
            suggestions.append("Adicione mais exemplos das categorias menores ou considere remover categorias com poucos exemplos.")
        elif imbalance_ratio > 5:
            warnings.append({
                "type": "moderate_imbalance",
                "message": f"O dataset esta um pouco desbalanceado (proporcao {imbalance_ratio:.1f}:1).",
                "ratio": round(imbalance_ratio, 1)
            })
            quality_score -= 5

    # Verifica textos muito curtos
    text_lengths = df_clean[text_column].astype(str).str.len()
    short_texts = (text_lengths < 20).sum()
    if short_texts > 0:
        short_percent = (short_texts / valid_rows) * 100
        if short_percent > 10:
            warnings.append({
                "type": "short_texts",
                "message": f"{short_texts} textos ({short_percent:.1f}%) sao muito curtos (menos de 20 caracteres).",
                "count": short_texts
            })
            quality_score -= 5

    # Verifica textos muito longos
    long_texts = (text_lengths > 5000).sum()
    if long_texts > 0:
        long_percent = (long_texts / valid_rows) * 100
        warnings.append({
            "type": "long_texts",
            "message": f"{long_texts} textos ({long_percent:.1f}%) sao muito longos e serao cortados.",
            "count": long_texts
        })

    # Verifica labels duplicadas (case insensitive)
    labels_lower = df_clean[label_column].astype(str).str.lower().str.strip()
    label_mapping = {}
    for label in df_clean[label_column].unique():
        label_lower = str(label).lower().strip()
        if label_lower not in label_mapping:
            label_mapping[label_lower] = []
        label_mapping[label_lower].append(label)

    duplicate_labels = {k: v for k, v in label_mapping.items() if len(v) > 1}
    if duplicate_labels:
        for lower, originals in duplicate_labels.items():
            warnings.append({
                "type": "duplicate_labels",
                "message": f"Categorias parecidas encontradas: {', '.join(str(o) for o in originals)}. Sao a mesma coisa?",
                "labels": originals
            })
            quality_score -= 5
            suggestions.append(f"Considere unificar as categorias: {', '.join(str(o) for o in originals)}")

    quality_score = max(0, min(100, quality_score))

    # Determina nivel de qualidade
    if quality_score >= 80:
        quality_level = "bom"
    elif quality_score >= 60:
        quality_level = "aceitavel"
    elif quality_score >= 40:
        quality_level = "regular"
    else:
        quality_level = "ruim"

    return {
        "quality_score": quality_score,
        "quality_level": quality_level,
        "total_rows": total_rows,
        "valid_rows": valid_rows,
        "num_classes": num_classes,
        "label_distribution": label_counts.to_dict(),
        "warnings": warnings,
        "errors": errors,
        "suggestions": suggestions
    }
