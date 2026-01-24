# -*- coding: utf-8 -*-
"""
Router FastAPI para o sistema BERT Training.

Endpoints para:
- Upload e gestão de datasets
- Criação e monitoramento de runs
- Fila de jobs e comunicação com workers
- Métricas e logs em tempo real
"""

import hashlib
import json
import logging
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc

from auth.dependencies import get_current_active_user
from auth.models import User
from database.connection import get_db

from sistemas.bert_training.models import (
    BertDataset, BertRun, BertJob, BertMetric, BertLog, BertWorker, BertTestHistory,
    TaskType, JobStatus
)
from sistemas.bert_training.schemas import (
    TaskTypeEnum, JobStatusEnum, LogLevel,
    DatasetUploadResponse, DatasetListItem, DatasetDetail, ExcelValidationResult,
    RunCreate, RunCreateSimple, RunResponse, RunListItem, RunDetailResponse,
    JobResponse, JobListItem, JobClaimRequest, JobClaimResponse, JobProgressUpdate,
    MetricCreate, MetricResponse, MetricDetailResponse,
    LogCreate, LogResponse, LogBatchCreate,
    WorkerRegister, WorkerRegisterResponse, WorkerResponse, WorkerHeartbeat,
    ReproduceRequest, HyperparametersConfig
)
from sistemas.bert_training import services
from sistemas.bert_training.presets import (
    get_all_presets, get_preset_by_name, get_all_presets_as_dicts, preset_to_dict
)
from sistemas.bert_training.error_translator import (
    get_friendly_error_message, translate_error, get_quality_alert
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bert-training", tags=["BERT Training"])


# ==================== Preset Endpoints ====================

@router.get("/api/presets")
async def list_presets(
    current_user: User = Depends(get_current_active_user)
):
    """
    Lista os presets de treinamento disponiveis.

    Presets sao configuracoes pre-definidas que simplificam a criacao de runs:
    - rapido: Teste rapido para validar dataset
    - equilibrado: Recomendado para maioria dos casos
    - preciso: Maximo de qualidade, mais demorado
    """
    presets = get_all_presets_as_dicts()
    return {"presets": presets}


@router.get("/api/presets/{preset_name}")
async def get_preset(
    preset_name: str,
    current_user: User = Depends(get_current_active_user)
):
    """Obtem detalhes de um preset especifico."""
    preset = get_preset_by_name(preset_name)
    if not preset:
        raise HTTPException(status_code=404, detail=f"Preset '{preset_name}' nao encontrado")

    return preset_to_dict(preset)


# ==================== Dataset Endpoints ====================

@router.post("/api/datasets/preview")
async def preview_dataset(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user)
):
    """
    Faz preview de um arquivo Excel e retorna as colunas disponíveis.
    Use antes do upload para selecionar as colunas corretas.
    """
    import pandas as pd

    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(
            status_code=400,
            detail="Apenas arquivos Excel (.xlsx, .xls) são aceitos"
        )

    # Salva arquivo temporário
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        df = pd.read_excel(tmp_path)

        # Detecta colunas que parecem texto (strings longas)
        text_candidates = []
        label_candidates = []

        for col in df.columns:
            col_str = str(col)
            # Verifica se é coluna de texto (strings longas)
            sample = df[col].dropna().head(10)
            if len(sample) > 0:
                avg_len = sample.astype(str).str.len().mean()
                unique_ratio = df[col].nunique() / len(df) if len(df) > 0 else 0

                if avg_len > 50:  # Textos longos
                    text_candidates.append(col_str)
                elif unique_ratio < 0.3:  # Poucas categorias únicas = label
                    label_candidates.append(col_str)

        # Preview dos dados (primeiras 5 linhas)
        preview_rows = df.head(5).to_dict(orient='records')

        # Estatísticas por coluna
        column_stats = []
        for col in df.columns:
            col_str = str(col)
            unique_count = df[col].nunique()
            null_count = df[col].isnull().sum()
            sample_values = df[col].dropna().head(3).tolist()

            column_stats.append({
                "name": col_str,
                "unique_values": int(unique_count),
                "null_count": int(null_count),
                "sample_values": [str(v)[:100] for v in sample_values],
                "is_text_candidate": col_str in text_candidates,
                "is_label_candidate": col_str in label_candidates
            })

        return {
            "filename": file.filename,
            "total_rows": len(df),
            "total_columns": len(df.columns),
            "columns": [str(c) for c in df.columns],
            "column_stats": column_stats,
            "text_candidates": text_candidates,
            "label_candidates": label_candidates,
            "preview_rows": preview_rows
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao ler Excel: {str(e)}")
    finally:
        tmp_path.unlink(missing_ok=True)


@router.post("/api/datasets/validate", response_model=ExcelValidationResult)
async def validate_dataset(
    file: UploadFile = File(...),
    task_type: TaskTypeEnum = Form(...),
    text_column: str = Form(...),
    label_column: str = Form(...),
    current_user: User = Depends(get_current_active_user)
):
    """
    Valida um arquivo Excel antes do upload.
    Retorna erros de validação e preview dos dados.
    """
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(
            status_code=400,
            detail="Apenas arquivos Excel (.xlsx, .xls) são aceitos"
        )

    # Salva arquivo temporário para validação
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        result = services.validate_excel_file(
            tmp_path, task_type, text_column, label_column
        )
        return result
    finally:
        tmp_path.unlink(missing_ok=True)


@router.post("/api/datasets/upload", response_model=DatasetUploadResponse)
async def upload_dataset(
    file: UploadFile = File(...),
    task_type: TaskTypeEnum = Form(...),
    text_column: str = Form(...),
    label_column: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Faz upload de um dataset Excel para treinamento.

    O arquivo é validado, salvo com hash SHA256 (idempotência),
    e os metadados são extraídos.
    """
    if not current_user.pode_acessar_sistema("bert_training"):
        raise HTTPException(status_code=403, detail="Acesso negado ao BERT Training")

    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(
            status_code=400,
            detail="Apenas arquivos Excel (.xlsx, .xls) são aceitos"
        )

    # Lê conteúdo e calcula hash
    content = await file.read()
    sha256_hash = hashlib.sha256(content).hexdigest()

    # Verifica se já existe
    existing = db.query(BertDataset).filter(
        BertDataset.sha256_hash == sha256_hash
    ).first()

    if existing:
        # Retorna o existente
        return DatasetUploadResponse(
            id=existing.id,
            filename=existing.filename,
            sha256_hash=existing.sha256_hash,
            file_size_bytes=existing.file_size_bytes,
            task_type=TaskTypeEnum(existing.task_type.value),
            text_column=existing.text_column,
            label_column=existing.label_column,
            total_rows=existing.total_rows,
            total_labels=existing.total_labels,
            label_distribution=existing.label_distribution,
            sample_preview=existing.sample_preview,
            uploaded_at=existing.uploaded_at,
            is_duplicate=True
        )

    # Salva arquivo temporário para validação
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        # Valida
        validation = services.validate_excel_file(
            tmp_path, task_type, text_column, label_column
        )

        if not validation.is_valid:
            raise HTTPException(
                status_code=400,
                detail=f"Validação falhou: {'; '.join(validation.errors)}"
            )

        # Extrai metadados
        metadata = services.extract_dataset_metadata(
            tmp_path, task_type, text_column, label_column
        )

        # Salva arquivo no storage
        file_path = services.save_dataset_file(content, file.filename, sha256_hash)

        # Cria registro no banco
        dataset = BertDataset(
            filename=file.filename,
            file_path=str(file_path),
            sha256_hash=sha256_hash,
            file_size_bytes=len(content),
            task_type=TaskType(task_type.value),
            text_column=text_column,
            label_column=label_column,
            total_rows=metadata["total_rows"],
            total_labels=metadata["total_labels"],
            label_distribution=metadata["label_distribution"],
            sample_preview=metadata["sample_preview"],
            uploaded_by=current_user.id
        )

        db.add(dataset)
        db.commit()
        db.refresh(dataset)

        logger.info(f"Dataset uploaded: id={dataset.id}, hash={sha256_hash[:8]}")

        return DatasetUploadResponse(
            id=dataset.id,
            filename=dataset.filename,
            sha256_hash=dataset.sha256_hash,
            file_size_bytes=dataset.file_size_bytes,
            task_type=TaskTypeEnum(dataset.task_type.value),
            text_column=dataset.text_column,
            label_column=dataset.label_column,
            total_rows=dataset.total_rows,
            total_labels=dataset.total_labels,
            label_distribution=dataset.label_distribution,
            sample_preview=dataset.sample_preview,
            uploaded_at=dataset.uploaded_at,
            is_duplicate=False
        )

    finally:
        tmp_path.unlink(missing_ok=True)


@router.get("/api/datasets", response_model=List[DatasetListItem])
async def list_datasets(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Lista datasets do usuário."""
    if not current_user.pode_acessar_sistema("bert_training"):
        raise HTTPException(status_code=403, detail="Acesso negado")

    query = db.query(BertDataset).order_by(desc(BertDataset.uploaded_at))

    # Se não for admin, filtra por usuário
    if current_user.role != "admin":
        query = query.filter(BertDataset.uploaded_by == current_user.id)

    datasets = query.offset(skip).limit(limit).all()

    return [
        DatasetListItem(
            id=d.id,
            filename=d.filename,
            sha256_hash=d.sha256_hash,
            task_type=TaskTypeEnum(d.task_type.value),
            total_rows=d.total_rows,
            total_labels=d.total_labels,
            uploaded_at=d.uploaded_at
        )
        for d in datasets
    ]


@router.get("/api/datasets/{dataset_id}", response_model=DatasetDetail)
async def get_dataset(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Obtém detalhes de um dataset."""
    dataset = db.query(BertDataset).filter(BertDataset.id == dataset_id).first()

    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset não encontrado")

    if current_user.role != "admin" and dataset.uploaded_by != current_user.id:
        raise HTTPException(status_code=403, detail="Acesso negado")

    runs_count = db.query(BertRun).filter(BertRun.dataset_id == dataset_id).count()

    return DatasetDetail(
        id=dataset.id,
        filename=dataset.filename,
        sha256_hash=dataset.sha256_hash,
        file_size_bytes=dataset.file_size_bytes,
        task_type=TaskTypeEnum(dataset.task_type.value),
        text_column=dataset.text_column,
        label_column=dataset.label_column,
        total_rows=dataset.total_rows,
        total_labels=dataset.total_labels,
        label_distribution=dataset.label_distribution,
        sample_preview=dataset.sample_preview,
        uploaded_at=dataset.uploaded_at,
        runs_count=runs_count
    )


@router.post("/api/datasets/analyze-quality")
async def analyze_dataset_quality(
    file: UploadFile = File(...),
    text_column: str = Form(...),
    label_column: str = Form(...),
    current_user: User = Depends(get_current_active_user)
):
    """
    Analisa a qualidade de um dataset antes do upload.

    Retorna:
    - quality_score: Pontuacao de qualidade (0-100)
    - warnings: Alertas sobre problemas encontrados
    - errors: Erros que impedem o treinamento
    - suggestions: Sugestoes de melhoria
    - label_distribution: Distribuicao das classes

    Use este endpoint para validar seu dataset ANTES de fazer upload.
    """
    import pandas as pd

    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(
            status_code=400,
            detail="Apenas arquivos Excel (.xlsx, .xls) sao aceitos"
        )

    # Salva arquivo temporario
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        df = pd.read_excel(tmp_path)

        # Verifica colunas
        if text_column not in df.columns:
            raise HTTPException(
                status_code=400,
                detail=f"Coluna de texto '{text_column}' nao encontrada"
            )
        if label_column not in df.columns:
            raise HTTPException(
                status_code=400,
                detail=f"Coluna de labels '{label_column}' nao encontrada"
            )

        # Analisa qualidade
        analysis = services.analyze_dataset_quality(df, text_column, label_column)

        return analysis

    finally:
        tmp_path.unlink(missing_ok=True)


@router.get("/api/datasets/{dataset_id}/quality")
async def get_dataset_quality(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Analisa a qualidade de um dataset ja salvo.
    """
    import pandas as pd

    dataset = db.query(BertDataset).filter(BertDataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset nao encontrado")

    if current_user.role != "admin" and dataset.uploaded_by != current_user.id:
        raise HTTPException(status_code=403, detail="Acesso negado")

    file_path = Path(dataset.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Arquivo nao encontrado")

    df = pd.read_excel(file_path)
    analysis = services.analyze_dataset_quality(df, dataset.text_column, dataset.label_column)

    return analysis


@router.get("/api/datasets/{dataset_id}/download")
async def download_dataset(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Download do arquivo Excel do dataset."""
    dataset = db.query(BertDataset).filter(BertDataset.id == dataset_id).first()

    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset não encontrado")

    file_path = Path(dataset.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")

    return FileResponse(
        path=file_path,
        filename=dataset.filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


# ==================== Run Endpoints ====================

@router.post("/api/runs", response_model=RunResponse, status_code=status.HTTP_201_CREATED)
async def create_run(
    run_data: RunCreate,
    request: "Request" = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Cria um novo run de treinamento e coloca na fila de jobs.

    Modos de uso:
    1. Modo Simples: Use preset_name ou preset_id (sem hyperparameters)
    2. Modo Avancado: Forneca hyperparameters customizados
    3. Modo Hibrido: Use preset + override de alguns hyperparameters

    Se nenhum preset/hyperparameters for fornecido, usa preset "equilibrado".
    """
    from fastapi import Request

    if not current_user.pode_acessar_sistema("bert_training"):
        raise HTTPException(status_code=403, detail="Acesso negado")

    # Busca dataset
    dataset = db.query(BertDataset).filter(BertDataset.id == run_data.dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset nao encontrado")

    # Verifica acesso ao dataset
    if current_user.role != "admin" and dataset.uploaded_by != current_user.id:
        raise HTTPException(status_code=403, detail="Acesso negado ao dataset")

    # Obtem IP do cliente para auditoria
    ip_address = None
    if request:
        ip_address = request.client.host if request.client else None

    # Cria run
    run = services.create_run(
        db=db,
        name=run_data.name,
        description=run_data.description,
        dataset=dataset,
        base_model=run_data.base_model,
        user_id=current_user.id,
        preset_name=run_data.preset_name,
        hyperparameters=run_data.hyperparameters,
        ip_address=ip_address
    )

    # Cria job na fila
    services.create_job_for_run(db, run)

    # Traduz mensagem de erro se houver
    error_friendly = None
    if run.error_message:
        error_friendly = get_friendly_error_message(run.error_message)

    return RunResponse(
        id=run.id,
        name=run.name,
        description=run.description,
        dataset_id=run.dataset_id,
        dataset_sha256=run.dataset_sha256,
        task_type=TaskTypeEnum(run.task_type.value),
        base_model=run.base_model,
        config_json=run.config_json,
        status=run.status,
        error_message=run.error_message,
        error_message_friendly=error_friendly,
        final_accuracy=run.final_accuracy,
        final_macro_f1=run.final_macro_f1,
        final_weighted_f1=run.final_weighted_f1,
        git_commit_hash=run.git_commit_hash,
        environment_fingerprint=run.environment_fingerprint,
        model_fingerprint=run.model_fingerprint,
        created_at=run.created_at,
        started_at=run.started_at,
        completed_at=run.completed_at
    )


@router.post("/api/runs/simple", response_model=RunResponse, status_code=status.HTTP_201_CREATED)
async def create_run_simple(
    run_data: RunCreateSimple,
    request: "Request" = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Cria um novo run no modo SIMPLES (recomendado para usuarios amadores).

    Apenas forneca:
    - name: Nome do seu treino
    - dataset_id: ID do dataset
    - preset_name: rapido, equilibrado ou preciso

    O sistema cuida do resto!
    """
    from fastapi import Request

    if not current_user.pode_acessar_sistema("bert_training"):
        raise HTTPException(status_code=403, detail="Acesso negado")

    # Busca dataset
    dataset = db.query(BertDataset).filter(BertDataset.id == run_data.dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset nao encontrado")

    # Verifica acesso ao dataset
    if current_user.role != "admin" and dataset.uploaded_by != current_user.id:
        raise HTTPException(status_code=403, detail="Acesso negado ao dataset")

    # Obtem IP do cliente
    ip_address = None
    if request:
        ip_address = request.client.host if request.client else None

    # Cria run com preset
    run = services.create_run(
        db=db,
        name=run_data.name,
        description=run_data.description,
        dataset=dataset,
        base_model=run_data.base_model,
        user_id=current_user.id,
        preset_name=run_data.preset_name,
        ip_address=ip_address
    )

    # Cria job na fila
    services.create_job_for_run(db, run)

    return RunResponse(
        id=run.id,
        name=run.name,
        description=run.description,
        dataset_id=run.dataset_id,
        dataset_sha256=run.dataset_sha256,
        task_type=TaskTypeEnum(run.task_type.value),
        base_model=run.base_model,
        config_json=run.config_json,
        status=run.status,
        error_message=run.error_message,
        error_message_friendly=None,
        final_accuracy=run.final_accuracy,
        final_macro_f1=run.final_macro_f1,
        final_weighted_f1=run.final_weighted_f1,
        git_commit_hash=run.git_commit_hash,
        environment_fingerprint=run.environment_fingerprint,
        model_fingerprint=run.model_fingerprint,
        created_at=run.created_at,
        started_at=run.started_at,
        completed_at=run.completed_at
    )


@router.get("/api/runs", response_model=List[RunListItem])
async def list_runs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Lista runs de treinamento."""
    if not current_user.pode_acessar_sistema("bert_training"):
        raise HTTPException(status_code=403, detail="Acesso negado")

    query = db.query(BertRun).order_by(desc(BertRun.created_at))

    if current_user.role != "admin":
        query = query.filter(BertRun.created_by == current_user.id)

    if status:
        query = query.filter(BertRun.status == status)

    runs = query.offset(skip).limit(limit).all()

    return [
        RunListItem(
            id=r.id,
            name=r.name,
            task_type=TaskTypeEnum(r.task_type.value),
            base_model=r.base_model,
            status=r.status,
            final_accuracy=r.final_accuracy,
            final_macro_f1=r.final_macro_f1,
            created_at=r.created_at,
            completed_at=r.completed_at
        )
        for r in runs
    ]


@router.get("/api/runs/{run_id}", response_model=RunDetailResponse)
async def get_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Obtém detalhes de um run."""
    run = db.query(BertRun).filter(BertRun.id == run_id).first()

    if not run:
        raise HTTPException(status_code=404, detail="Run não encontrado")

    if current_user.role != "admin" and run.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Acesso negado")

    # Busca dataset filename
    dataset = db.query(BertDataset).filter(BertDataset.id == run.dataset_id).first()

    # Busca jobs
    jobs = db.query(BertJob).filter(BertJob.run_id == run_id).order_by(desc(BertJob.created_at)).all()

    # Busca últimas métricas
    metrics = db.query(BertMetric).filter(
        BertMetric.run_id == run_id
    ).order_by(BertMetric.epoch.asc()).limit(100).all()

    # Traduz erro se houver
    error_friendly = None
    if run.error_message:
        error_friendly = get_friendly_error_message(run.error_message)

    return RunDetailResponse(
        id=run.id,
        name=run.name,
        description=run.description,
        dataset_id=run.dataset_id,
        dataset_sha256=run.dataset_sha256,
        task_type=TaskTypeEnum(run.task_type.value),
        base_model=run.base_model,
        config_json=run.config_json,
        status=run.status,
        error_message=run.error_message,
        error_message_friendly=error_friendly,
        final_accuracy=run.final_accuracy,
        final_macro_f1=run.final_macro_f1,
        final_weighted_f1=run.final_weighted_f1,
        git_commit_hash=run.git_commit_hash,
        environment_fingerprint=run.environment_fingerprint,
        model_fingerprint=run.model_fingerprint,
        created_at=run.created_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
        dataset_filename=dataset.filename if dataset else "Unknown",
        jobs=[
            JobListItem(
                id=j.id,
                run_id=j.run_id,
                status=JobStatusEnum(j.status.value),
                progress_percent=j.progress_percent,
                created_at=j.created_at
            )
            for j in jobs
        ],
        recent_metrics=[
            MetricResponse(
                id=m.id,
                run_id=m.run_id,
                epoch=m.epoch,
                train_loss=m.train_loss,
                val_loss=m.val_loss,
                val_accuracy=m.val_accuracy,
                val_macro_f1=m.val_macro_f1,
                val_weighted_f1=m.val_weighted_f1,
                recorded_at=m.recorded_at
            )
            for m in metrics
        ]
    )


@router.get("/api/runs/{run_id}/progress")
async def get_run_progress(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Obtem progresso do run com estimativa de tempo.

    Retorna:
    - progress_percent: Porcentagem de progresso
    - current_epoch: Rodada atual
    - total_epochs: Total de rodadas
    - current_epoch_label: "Rodada X de Y"
    - estimated_remaining_minutes: Tempo estimado restante
    - estimated_remaining_label: "~X minutos restantes"
    - status: Status atual do run
    - quality_alert: Alerta de qualidade (se aplicavel)
    """
    run = db.query(BertRun).filter(BertRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run nao encontrado")

    if current_user.role != "admin" and run.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Acesso negado")

    # Busca job ativo
    job = db.query(BertJob).filter(
        BertJob.run_id == run_id
    ).order_by(desc(BertJob.created_at)).first()

    result = {
        "run_id": run_id,
        "status": run.status,
        "status_label": _translate_status(run.status)
    }

    if job:
        current_epoch = job.current_epoch or 0
        total_epochs = run.epochs or 10

        progress = services.calculate_progress_with_estimate(job, run, current_epoch)
        result.update(progress)

        result["job_status"] = job.status.value

    # Se completado, adiciona metricas finais
    if run.status == "completed":
        result["final_accuracy"] = run.final_accuracy
        result["final_accuracy_label"] = f"{int(run.final_accuracy * 100)}% de acertos" if run.final_accuracy else None

        # Alerta de qualidade
        alert = get_quality_alert({
            "accuracy": run.final_accuracy,
            "macro_f1": run.final_macro_f1
        })
        if alert:
            result["quality_alert"] = alert

    # Se falhou, adiciona erro amigavel
    if run.status == "failed" and run.error_message:
        error = translate_error(run.error_message)
        result["error"] = {
            "title": error.title,
            "message": error.message,
            "suggestion": error.suggestion,
            "can_auto_retry": error.can_auto_retry
        }

    return result


def _translate_status(status: str) -> str:
    """Traduz status para portugues amigavel."""
    translations = {
        "pending": "Na fila",
        "claimed": "Preparando",
        "downloading": "Baixando dados",
        "training": "Treinando",
        "evaluating": "Avaliando",
        "completed": "Concluido",
        "failed": "Falhou",
        "cancelled": "Cancelado"
    }
    return translations.get(status, status)


@router.get("/api/runs/{run_id}/metrics", response_model=List[MetricResponse])
async def get_run_metrics(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Obtém todas as métricas de um run."""
    run = db.query(BertRun).filter(BertRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run não encontrado")

    if current_user.role != "admin" and run.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Acesso negado")

    metrics = db.query(BertMetric).filter(
        BertMetric.run_id == run_id
    ).order_by(BertMetric.epoch.asc()).all()

    return [
        MetricResponse(
            id=m.id,
            run_id=m.run_id,
            epoch=m.epoch,
            train_loss=m.train_loss,
            val_loss=m.val_loss,
            val_accuracy=m.val_accuracy,
            val_macro_f1=m.val_macro_f1,
            val_weighted_f1=m.val_weighted_f1,
            recorded_at=m.recorded_at
        )
        for m in metrics
    ]


@router.get("/api/runs/{run_id}/logs")
async def get_run_logs_sse(
    run_id: int,
    last_id: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Server-Sent Events para logs em tempo real.
    """
    import asyncio

    run = db.query(BertRun).filter(BertRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run não encontrado")

    async def event_generator():
        current_last_id = last_id
        consecutive_empty = 0

        while True:
            # Busca novos logs
            logs = db.query(BertLog).filter(
                BertLog.run_id == run_id,
                BertLog.id > current_last_id
            ).order_by(BertLog.id.asc()).limit(50).all()

            for log in logs:
                data = {
                    "id": log.id,
                    "level": log.level,
                    "message": log.message,
                    "timestamp": log.timestamp.isoformat(),
                    "epoch": log.epoch,
                    "batch": log.batch
                }
                yield f"data: {json.dumps(data)}\n\n"
                current_last_id = log.id
                consecutive_empty = 0

            if not logs:
                consecutive_empty += 1

            # Verifica se run terminou
            db.refresh(run)
            if run.status in ["completed", "failed", "cancelled"]:
                yield f"data: {json.dumps({'status': run.status, 'done': True})}\n\n"
                break

            # Para se muito tempo sem novos logs
            if consecutive_empty > 60:  # ~2 minutos
                yield f"data: {json.dumps({'timeout': True})}\n\n"
                break

            await asyncio.sleep(2)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )


@router.post("/api/runs/{run_id}/reproduce", response_model=RunResponse)
async def reproduce_run(
    run_id: int,
    new_name: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Reproduz um run existente com a mesma configuração.
    """
    can_reproduce, message = services.validate_reproduce_run(db, run_id)
    if not can_reproduce:
        raise HTTPException(status_code=400, detail=message)

    original_run = db.query(BertRun).filter(BertRun.id == run_id).first()
    dataset = db.query(BertDataset).filter(BertDataset.id == original_run.dataset_id).first()

    from sistemas.bert_training.schemas import HyperparametersConfig
    hyperparams = HyperparametersConfig(**original_run.config_json)

    run = services.create_run(
        db=db,
        name=new_name or f"{original_run.name} (reprodução)",
        description=f"Reprodução do run #{run_id}",
        dataset=dataset,
        base_model=original_run.base_model,
        hyperparameters=hyperparams,
        user_id=current_user.id
    )

    services.create_job_for_run(db, run)

    return RunResponse(
        id=run.id,
        name=run.name,
        description=run.description,
        dataset_id=run.dataset_id,
        dataset_sha256=run.dataset_sha256,
        task_type=TaskTypeEnum(run.task_type.value),
        base_model=run.base_model,
        config_json=run.config_json,
        status=run.status,
        error_message=run.error_message,
        final_accuracy=run.final_accuracy,
        final_macro_f1=run.final_macro_f1,
        final_weighted_f1=run.final_weighted_f1,
        git_commit_hash=run.git_commit_hash,
        environment_fingerprint=run.environment_fingerprint,
        model_fingerprint=run.model_fingerprint,
        created_at=run.created_at,
        started_at=run.started_at,
        completed_at=run.completed_at
    )


# ==================== Job Endpoints (Worker API) ====================

@router.post("/api/jobs/claim", response_model=JobClaimResponse)
async def claim_job(
    request: JobClaimRequest,
    db: Session = Depends(get_db)
):
    """
    Worker tenta pegar um job da fila.
    """
    worker = services.get_worker_by_token(db, request.worker_token)
    if not worker:
        raise HTTPException(status_code=401, detail="Token inválido")

    # Atualiza info do worker se fornecido
    if request.gpu_name:
        worker.gpu_name = request.gpu_name
    if request.gpu_vram_gb:
        worker.gpu_vram_gb = request.gpu_vram_gb
    if request.cuda_version:
        worker.cuda_version = request.cuda_version
    db.commit()

    # Busca job pendente
    job = services.get_pending_job(db)
    if not job:
        raise HTTPException(status_code=404, detail="Nenhum job pendente")

    # Tenta pegar o job
    if not services.claim_job(db, worker, job):
        raise HTTPException(status_code=409, detail="Job já foi pego por outro worker")

    # Busca dados do run
    run = db.query(BertRun).filter(BertRun.id == job.run_id).first()
    dataset = db.query(BertDataset).filter(BertDataset.id == run.dataset_id).first()

    # Gera URL de download (relativa)
    download_url = f"/bert-training/api/datasets/{dataset.id}/download"

    return JobClaimResponse(
        job_id=job.id,
        run_id=run.id,
        dataset_download_url=download_url,
        dataset_sha256=dataset.sha256_hash,
        config=run.config_json,
        base_model=run.base_model,
        task_type=TaskTypeEnum(run.task_type.value),
        text_column=dataset.text_column,
        label_column=dataset.label_column
    )


@router.post("/api/jobs/{job_id}/progress")
async def update_job_progress(
    job_id: int,
    update: JobProgressUpdate,
    db: Session = Depends(get_db)
):
    """
    Worker atualiza progresso do job.
    """
    worker = services.get_worker_by_token(db, update.worker_token)
    if not worker:
        raise HTTPException(status_code=401, detail="Token inválido")

    job = db.query(BertJob).filter(BertJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado")

    if job.worker_id != worker.id:
        raise HTTPException(status_code=403, detail="Job pertence a outro worker")

    services.update_job_progress(
        db=db,
        job=job,
        status=JobStatus(update.status.value) if update.status else None,
        current_epoch=update.current_epoch,
        progress_percent=update.progress_percent,
        error_message=update.error_message
    )

    # Atualiza heartbeat
    services.update_worker_heartbeat(db, worker, job_id)

    return {"status": "ok"}


@router.post("/api/jobs/{job_id}/complete")
async def complete_job(
    job_id: int,
    worker_token: str,
    final_accuracy: float,
    final_macro_f1: float,
    final_weighted_f1: float,
    model_fingerprint: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Worker marca job como completo.
    """
    worker = services.get_worker_by_token(db, worker_token)
    if not worker:
        raise HTTPException(status_code=401, detail="Token inválido")

    job = db.query(BertJob).filter(BertJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado")

    if job.worker_id != worker.id:
        raise HTTPException(status_code=403, detail="Job pertence a outro worker")

    # Atualiza job
    services.update_job_progress(db, job, status=JobStatus.COMPLETED, progress_percent=100.0)

    # Finaliza run
    run = db.query(BertRun).filter(BertRun.id == job.run_id).first()
    services.finalize_run(
        db=db,
        run=run,
        success=True,
        final_accuracy=final_accuracy,
        final_macro_f1=final_macro_f1,
        final_weighted_f1=final_weighted_f1,
        model_fingerprint=model_fingerprint
    )

    # Atualiza stats do worker
    worker.total_jobs_completed += 1
    if job.started_at and job.completed_at:
        hours = (job.completed_at - job.started_at).total_seconds() / 3600
        worker.total_training_hours += hours
    worker.current_job_id = None
    db.commit()

    return {"status": "ok"}


# ==================== Metric Endpoints (Worker API) ====================

@router.post("/api/metrics")
async def record_metric(
    metric: MetricCreate,
    db: Session = Depends(get_db)
):
    """
    Worker registra métricas de uma época.
    """
    worker = services.get_worker_by_token(db, metric.worker_token)
    if not worker:
        raise HTTPException(status_code=401, detail="Token inválido")

    services.record_metric(
        db=db,
        run_id=metric.run_id,
        epoch=metric.epoch,
        train_loss=metric.train_loss,
        val_loss=metric.val_loss,
        val_accuracy=metric.val_accuracy,
        val_macro_f1=metric.val_macro_f1,
        val_weighted_f1=metric.val_weighted_f1,
        val_macro_precision=metric.val_macro_precision,
        val_macro_recall=metric.val_macro_recall,
        seqeval_f1=metric.seqeval_f1,
        seqeval_precision=metric.seqeval_precision,
        seqeval_recall=metric.seqeval_recall,
        classification_report=metric.classification_report,
        confusion_matrix=metric.confusion_matrix
    )

    return {"status": "ok"}


# ==================== Log Endpoints (Worker API) ====================

@router.post("/api/logs")
async def record_log(
    log: LogCreate,
    db: Session = Depends(get_db)
):
    """
    Worker registra um log.
    """
    worker = services.get_worker_by_token(db, log.worker_token)
    if not worker:
        raise HTTPException(status_code=401, detail="Token inválido")

    services.record_log(
        db=db,
        run_id=log.run_id,
        level=log.level.value,
        message=log.message,
        extra_data=log.extra_data,
        source=log.source,
        epoch=log.epoch,
        batch=log.batch
    )

    return {"status": "ok"}


@router.post("/api/logs/batch")
async def record_logs_batch(
    batch: LogBatchCreate,
    db: Session = Depends(get_db)
):
    """
    Worker registra múltiplos logs de uma vez.
    """
    worker = services.get_worker_by_token(db, batch.worker_token)
    if not worker:
        raise HTTPException(status_code=401, detail="Token inválido")

    for log in batch.logs:
        services.record_log(
            db=db,
            run_id=log.run_id,
            level=log.level.value,
            message=log.message,
            extra_data=log.extra_data,
            source=log.source,
            epoch=log.epoch,
            batch=log.batch
        )

    return {"status": "ok", "count": len(batch.logs)}


# ==================== Worker Management ====================

@router.post("/api/workers/register", response_model=WorkerRegisterResponse)
async def register_worker(
    worker: WorkerRegister,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Registra um novo worker (apenas admin).
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Apenas admin pode registrar workers")

    # Verifica se nome já existe
    existing = db.query(BertWorker).filter(BertWorker.name == worker.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Nome de worker já existe")

    new_worker, token = services.create_worker(
        db=db,
        name=worker.name,
        description=worker.description,
        gpu_name=worker.gpu_name,
        gpu_vram_gb=worker.gpu_vram_gb,
        cuda_version=worker.cuda_version
    )

    return WorkerRegisterResponse(
        id=new_worker.id,
        name=new_worker.name,
        token=token,  # Mostrado apenas uma vez!
        created_at=new_worker.created_at
    )


@router.get("/api/workers", response_model=List[WorkerResponse])
async def list_workers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Lista workers registrados (apenas admin)."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Acesso negado")

    workers = db.query(BertWorker).order_by(desc(BertWorker.created_at)).all()

    return [
        WorkerResponse(
            id=w.id,
            name=w.name,
            description=w.description,
            gpu_name=w.gpu_name,
            gpu_vram_gb=w.gpu_vram_gb,
            cuda_version=w.cuda_version,
            is_active=w.is_active,
            last_heartbeat=w.last_heartbeat,
            current_job_id=w.current_job_id,
            total_jobs_completed=w.total_jobs_completed,
            total_training_hours=w.total_training_hours,
            created_at=w.created_at
        )
        for w in workers
    ]


@router.post("/api/workers/heartbeat")
async def worker_heartbeat(
    heartbeat: WorkerHeartbeat,
    db: Session = Depends(get_db)
):
    """Worker envia heartbeat."""
    worker = services.get_worker_by_token(db, heartbeat.worker_token)
    if not worker:
        raise HTTPException(status_code=401, detail="Token inválido")

    services.update_worker_heartbeat(db, worker, heartbeat.current_job_id)

    return {"status": "ok"}


# ==================== Queue Status ====================

@router.get("/api/queue/status")
async def get_queue_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Obtém status da fila de jobs."""
    pending = db.query(BertJob).filter(BertJob.status == JobStatus.PENDING).count()
    training = db.query(BertJob).filter(BertJob.status == JobStatus.TRAINING).count()
    completed = db.query(BertJob).filter(BertJob.status == JobStatus.COMPLETED).count()
    failed = db.query(BertJob).filter(BertJob.status == JobStatus.FAILED).count()

    active_workers = db.query(BertWorker).filter(
        BertWorker.is_active == True,
        BertWorker.current_job_id != None
    ).count()

    return {
        "pending": pending,
        "training": training,
        "completed": completed,
        "failed": failed,
        "active_workers": active_workers
    }


# ==================== Watchdog & Health ====================

@router.get("/api/system/health")
async def get_system_health(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Retorna status de saude do sistema.

    Util para dashboards e monitoramento.
    """
    from sistemas.bert_training.watchdog import get_system_health as watchdog_health
    return watchdog_health(db)


@router.post("/api/system/watchdog/run")
async def run_watchdog(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Executa verificacao do watchdog manualmente (apenas admin).

    Normalmente o watchdog roda automaticamente via cron/scheduler.
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Apenas admin pode executar watchdog")

    from sistemas.bert_training.watchdog import run_watchdog_check
    results = run_watchdog_check(db)

    return results


@router.get("/api/system/calculate-batch")
async def calculate_optimal_batch(
    vram_gb: float = Query(..., description="VRAM disponivel em GB"),
    max_length: int = Query(512, description="Tamanho maximo de sequencia"),
    model: str = Query("neuralmind/bert-base-portuguese-cased", description="Nome do modelo"),
    current_user: User = Depends(get_current_active_user)
):
    """
    Calcula batch size otimo baseado na VRAM disponivel.

    Use este endpoint para descobrir qual batch size usar
    baseado na GPU do seu computador.
    """
    model_size = services.detect_model_size(model)
    optimal_batch = services.calculate_optimal_batch_size(vram_gb, max_length, model_size)

    return {
        "vram_gb": vram_gb,
        "max_length": max_length,
        "model": model,
        "model_size": model_size,
        "optimal_batch_size": optimal_batch,
        "explanation": f"Para {vram_gb}GB de VRAM com max_length={max_length} e modelo {model_size}, "
                      f"recomendamos batch_size={optimal_batch}"
    }


# ==================== Modelos para Teste ====================

@router.get("/api/models/completed")
async def get_completed_models(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Lista modelos treinados com sucesso disponiveis para teste.

    Retorna apenas runs com status 'completed'.
    """
    runs = db.query(BertRun).filter(
        BertRun.status == "completed"
    ).order_by(desc(BertRun.completed_at)).all()

    return [
        {
            "id": run.id,
            "name": run.name,
            "description": run.description,
            "base_model": run.base_model,
            "accuracy": run.final_accuracy,
            "f1_score": run.final_macro_f1,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "dataset_name": run.dataset.filename if run.dataset else None,
            "total_labels": run.dataset.total_labels if run.dataset else None,
            "labels": list(run.dataset.label_distribution.keys()) if run.dataset and run.dataset.label_distribution else []
        }
        for run in runs
    ]


# ==================== Historico de Testes ====================

@router.get("/api/tests")
async def get_test_history(
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Lista historico de testes do usuario."""
    tests = db.query(BertTestHistory).filter(
        BertTestHistory.user_id == current_user.id
    ).order_by(desc(BertTestHistory.created_at)).limit(limit).all()

    return [
        {
            "id": test.id,
            "run_id": test.run_id,
            "run_name": test.run.name if test.run else None,
            "input_type": test.input_type,
            "input_text": test.input_text[:200] + "..." if len(test.input_text) > 200 else test.input_text,
            "input_filename": test.input_filename,
            "predicted_label": test.predicted_label,
            "confidence": test.confidence,
            "created_at": test.created_at.isoformat()
        }
        for test in tests
    ]


@router.post("/api/tests")
async def create_test_record(
    run_id: int = Form(...),
    input_type: str = Form(...),
    input_text: str = Form(...),
    predicted_label: str = Form(...),
    confidence: float = Form(...),
    input_filename: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Salva registro de teste no historico."""
    # Verifica se o run existe
    run = db.query(BertRun).filter(BertRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run nao encontrado")

    test = BertTestHistory(
        run_id=run_id,
        input_type=input_type,
        input_text=input_text,
        input_filename=input_filename,
        predicted_label=predicted_label,
        confidence=confidence,
        user_id=current_user.id
    )

    db.add(test)
    db.commit()
    db.refresh(test)

    return {
        "id": test.id,
        "message": "Teste salvo com sucesso"
    }


@router.delete("/api/tests/{test_id}")
async def delete_test_record(
    test_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Deleta um registro de teste."""
    test = db.query(BertTestHistory).filter(
        BertTestHistory.id == test_id,
        BertTestHistory.user_id == current_user.id
    ).first()

    if not test:
        raise HTTPException(status_code=404, detail="Teste nao encontrado")

    db.delete(test)
    db.commit()

    return {"message": "Teste deletado com sucesso"}


@router.delete("/api/tests")
async def clear_test_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Limpa todo historico de testes do usuario."""
    deleted = db.query(BertTestHistory).filter(
        BertTestHistory.user_id == current_user.id
    ).delete()

    db.commit()

    return {"message": f"{deleted} teste(s) deletado(s)"}
