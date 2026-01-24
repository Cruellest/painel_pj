# -*- coding: utf-8 -*-
"""
Schemas Pydantic para validação de dados da API BERT Training.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator
from enum import Enum


# ==================== Enums ====================

class TaskTypeEnum(str, Enum):
    """Tipo de tarefa de classificação."""
    TEXT_CLASSIFICATION = "text_classification"
    TOKEN_CLASSIFICATION = "token_classification"


class JobStatusEnum(str, Enum):
    """Status do job de treinamento."""
    PENDING = "pending"
    CLAIMED = "claimed"
    DOWNLOADING = "downloading"
    TRAINING = "training"
    EVALUATING = "evaluating"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class LogLevel(str, Enum):
    """Nível de log."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


# ==================== Preset Schemas ====================

class PresetConfig(BaseModel):
    """Configuracao de hiperparametros de um preset."""
    learning_rate: float = Field(5e-5, gt=0, le=1)
    batch_size: int = Field(16, ge=1, le=128)
    epochs: int = Field(10, ge=1, le=100)
    max_length: int = Field(512, ge=32, le=1024)
    train_split: float = Field(0.8, gt=0.1, lt=1.0)
    warmup_steps: int = Field(0, ge=0)
    weight_decay: float = Field(0.01, ge=0, le=1)
    gradient_accumulation_steps: int = Field(1, ge=1, le=32)
    early_stopping_patience: Optional[int] = Field(3, ge=1, le=20)
    use_class_weights: bool = True
    seed: int = Field(42, ge=0)
    truncation_side: str = Field("right", pattern="^(left|right)$")


# ==================== Dataset Schemas ====================

class DatasetUploadResponse(BaseModel):
    """Resposta após upload de dataset."""
    id: int
    filename: str
    sha256_hash: str
    file_size_bytes: int
    task_type: TaskTypeEnum
    text_column: str
    label_column: str
    total_rows: int
    total_labels: Optional[int] = None
    label_distribution: Optional[Dict[str, int]] = None
    sample_preview: Optional[List[Dict[str, Any]]] = None
    uploaded_at: datetime
    is_duplicate: bool = False  # True se hash já existia

    model_config = {"from_attributes": True}


class DatasetListItem(BaseModel):
    """Item na listagem de datasets."""
    id: int
    filename: str
    sha256_hash: str
    task_type: TaskTypeEnum
    total_rows: int
    total_labels: Optional[int]
    uploaded_at: datetime

    model_config = {"from_attributes": True}


class DatasetDetail(DatasetUploadResponse):
    """Detalhes completos do dataset."""
    runs_count: int = 0


class ExcelValidationResult(BaseModel):
    """Resultado da validação de Excel."""
    is_valid: bool
    errors: List[str] = []
    warnings: List[str] = []
    columns: List[str] = []
    total_rows: int = 0
    sample_data: Optional[List[Dict[str, Any]]] = None


# ==================== Run Schemas ====================

class HyperparametersConfig(BaseModel):
    """Configuração de hiperparâmetros."""
    learning_rate: float = Field(5e-5, gt=0, le=1)
    batch_size: int = Field(16, ge=1, le=128)
    epochs: int = Field(10, ge=1, le=100)
    max_length: int = Field(512, ge=32, le=1024)
    train_split: float = Field(0.7, gt=0.1, lt=1.0)
    warmup_steps: int = Field(0, ge=0)
    weight_decay: float = Field(0.01, ge=0, le=1)
    gradient_accumulation_steps: int = Field(1, ge=1, le=32)
    early_stopping_patience: int = Field(3, ge=1, le=20)
    use_class_weights: bool = True
    seed: int = Field(42, ge=0)
    truncation_side: str = Field("right", pattern="^(left|right)$")


class RunCreate(BaseModel):
    """Dados para criar um novo run.

    O usuario pode:
    1. Usar um preset (preset_name) - modo simples
    2. Ou fornecer hyperparameters customizados - modo avancado

    Se ambos forem fornecidos, hyperparameters tem prioridade (override).
    Se nenhum for fornecido, usa preset "equilibrado" como padrao.
    """
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    dataset_id: int
    base_model: str = Field("neuralmind/bert-base-portuguese-cased", min_length=1)

    # Modo simples: usar preset (rapido, equilibrado, preciso)
    preset_name: Optional[str] = None

    # Modo avancado: configuracao customizada (sobrescreve preset se fornecido)
    hyperparameters: Optional[HyperparametersConfig] = None

    @field_validator("base_model")
    @classmethod
    def validate_base_model(cls, v):
        # Modelos conhecidos/recomendados
        known_models = [
            "neuralmind/bert-base-portuguese-cased",
            "neuralmind/bert-large-portuguese-cased",
            "bert-base-multilingual-cased",
            "xlm-roberta-base",
            "xlm-roberta-large",
        ]
        if v not in known_models:
            # Permite modelos customizados, mas valida formato básico
            if "/" not in v and not v.startswith("bert-"):
                pass  # Aceita mesmo assim, pode ser path local
        return v


class RunCreateSimple(BaseModel):
    """Dados para criar run no modo simples (apenas preset).

    Este e o schema recomendado para usuarios amadores.
    """
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    dataset_id: int
    preset_name: str = Field("equilibrado", description="Nome do preset: rapido, equilibrado, preciso")
    base_model: str = Field("neuralmind/bert-base-portuguese-cased")


class RunResponse(BaseModel):
    """Resposta com dados do run."""
    id: int
    name: str
    description: Optional[str]
    dataset_id: int
    dataset_sha256: str
    task_type: TaskTypeEnum
    base_model: str
    config_json: Dict[str, Any]

    status: str
    error_message: Optional[str]

    # Mensagem de erro amigavel (traduzida)
    error_message_friendly: Optional[str] = None

    final_accuracy: Optional[float]
    final_macro_f1: Optional[float]
    final_weighted_f1: Optional[float]
    git_commit_hash: Optional[str]
    environment_fingerprint: Optional[str]
    model_fingerprint: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    model_config = {"from_attributes": True}


class RunListItem(BaseModel):
    """Item na listagem de runs."""
    id: int
    name: str
    task_type: TaskTypeEnum
    base_model: str
    status: str
    final_accuracy: Optional[float]
    final_macro_f1: Optional[float]
    created_at: datetime
    completed_at: Optional[datetime]

    model_config = {"from_attributes": True}


class RunDetailResponse(RunResponse):
    """Detalhes completos do run incluindo jobs e métricas recentes."""
    dataset_filename: str
    jobs: List["JobListItem"] = []
    recent_metrics: List["MetricResponse"] = []


# ==================== Job Schemas ====================

class JobResponse(BaseModel):
    """Resposta com dados do job."""
    id: int
    run_id: int
    status: JobStatusEnum
    worker_id: Optional[int]
    current_epoch: Optional[int]
    total_epochs: Optional[int]
    progress_percent: float
    retry_count: int
    max_retries: int
    error_message: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    model_config = {"from_attributes": True}


class JobListItem(BaseModel):
    """Item na listagem de jobs."""
    id: int
    run_id: int
    status: JobStatusEnum
    progress_percent: float
    created_at: datetime

    model_config = {"from_attributes": True}


class JobClaimRequest(BaseModel):
    """Requisição do worker para pegar um job."""
    worker_token: str
    gpu_name: Optional[str] = None
    gpu_vram_gb: Optional[float] = None
    cuda_version: Optional[str] = None


class JobClaimResponse(BaseModel):
    """Resposta ao worker com dados do job."""
    job_id: int
    run_id: int
    dataset_download_url: str
    dataset_sha256: str
    config: Dict[str, Any]
    base_model: str
    task_type: TaskTypeEnum
    text_column: str
    label_column: str


class JobProgressUpdate(BaseModel):
    """Atualização de progresso do worker."""
    worker_token: str
    status: Optional[JobStatusEnum] = None
    current_epoch: Optional[int] = None
    progress_percent: Optional[float] = None
    error_message: Optional[str] = None


# ==================== Metric Schemas ====================

class MetricCreate(BaseModel):
    """Dados para criar uma métrica."""
    worker_token: str
    run_id: int
    epoch: int
    train_loss: Optional[float] = None
    val_loss: Optional[float] = None
    val_accuracy: Optional[float] = None
    val_macro_f1: Optional[float] = None
    val_weighted_f1: Optional[float] = None
    val_macro_precision: Optional[float] = None
    val_macro_recall: Optional[float] = None
    seqeval_f1: Optional[float] = None
    seqeval_precision: Optional[float] = None
    seqeval_recall: Optional[float] = None
    classification_report: Optional[Dict[str, Any]] = None
    confusion_matrix: Optional[List[List[int]]] = None


class MetricResponse(BaseModel):
    """Resposta com dados da métrica."""
    id: int
    run_id: int
    epoch: int
    train_loss: Optional[float]
    val_loss: Optional[float]
    val_accuracy: Optional[float]
    val_macro_f1: Optional[float]
    val_weighted_f1: Optional[float]
    recorded_at: datetime

    model_config = {"from_attributes": True}


class MetricDetailResponse(MetricResponse):
    """Métricas detalhadas incluindo reports."""
    val_macro_precision: Optional[float]
    val_macro_recall: Optional[float]
    seqeval_f1: Optional[float]
    seqeval_precision: Optional[float]
    seqeval_recall: Optional[float]
    classification_report: Optional[Dict[str, Any]]
    confusion_matrix: Optional[List[List[int]]]


# ==================== Log Schemas ====================

class LogCreate(BaseModel):
    """Dados para criar um log."""
    worker_token: str
    run_id: int
    level: LogLevel
    message: str
    extra_data: Optional[Dict[str, Any]] = None
    source: Optional[str] = None
    epoch: Optional[int] = None
    batch: Optional[int] = None


class LogResponse(BaseModel):
    """Resposta com dados do log."""
    id: int
    run_id: int
    level: str
    message: str
    extra_data: Optional[Dict[str, Any]]
    source: Optional[str]
    epoch: Optional[int]
    batch: Optional[int]
    timestamp: datetime

    model_config = {"from_attributes": True}


class LogBatchCreate(BaseModel):
    """Batch de logs para envio em lote."""
    worker_token: str
    logs: List[LogCreate]


# ==================== Worker Schemas ====================

class WorkerRegister(BaseModel):
    """Dados para registrar um worker."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    gpu_name: Optional[str] = None
    gpu_vram_gb: Optional[float] = None
    cuda_version: Optional[str] = None


class WorkerRegisterResponse(BaseModel):
    """Resposta ao registrar worker com token."""
    id: int
    name: str
    token: str  # Token gerado (mostrado apenas uma vez)
    created_at: datetime


class WorkerResponse(BaseModel):
    """Dados do worker."""
    id: int
    name: str
    description: Optional[str]
    gpu_name: Optional[str]
    gpu_vram_gb: Optional[float]
    cuda_version: Optional[str]
    is_active: bool
    last_heartbeat: Optional[datetime]
    current_job_id: Optional[int]
    total_jobs_completed: int
    total_training_hours: float
    created_at: datetime

    model_config = {"from_attributes": True}


class WorkerHeartbeat(BaseModel):
    """Heartbeat do worker."""
    worker_token: str
    gpu_utilization: Optional[float] = None  # 0-100%
    gpu_memory_used_gb: Optional[float] = None
    current_job_id: Optional[int] = None


# ==================== Reproduce Schemas ====================

class ReproduceRequest(BaseModel):
    """Requisição para reproduzir um run."""
    run_id: int
    new_name: Optional[str] = None


# Forward references para evitar circular imports
RunDetailResponse.model_rebuild()
