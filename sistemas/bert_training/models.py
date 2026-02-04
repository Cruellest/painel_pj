# -*- coding: utf-8 -*-
"""
Modelos SQLAlchemy para o sistema BERT Training.

Tabelas:
- bert_datasets: Datasets Excel enviados para treinamento
- bert_runs: Experimentos de treinamento (configuração + metadata)
- bert_jobs: Fila de jobs de treinamento
- bert_metrics: Métricas por época de treinamento
- bert_logs: Logs estruturados de treinamento
- bert_workers: Registro de workers GPU
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Text, DateTime,
    ForeignKey, JSON, Index, Enum as SQLEnum
)
from sqlalchemy.orm import relationship
from database.connection import Base
import enum


class TaskType(str, enum.Enum):
    """Tipo de tarefa de classificação."""
    TEXT_CLASSIFICATION = "text_classification"  # tokens (string) + label
    TOKEN_CLASSIFICATION = "token_classification"  # NER/BIO: tokens/tags como JSON


class JobStatus(str, enum.Enum):
    """Status do job de treinamento."""
    PENDING = "pending"
    CLAIMED = "claimed"  # Worker pegou o job
    DOWNLOADING = "downloading"  # Baixando dataset
    TRAINING = "training"
    EVALUATING = "evaluating"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Helper para garantir que SQLEnum use o value (lowercase) ao inves do name (uppercase)
def _enum_values_callable(enum_class):
    """Retorna os valores do enum para uso com SQLEnum."""
    return [e.value for e in enum_class]


class BertDataset(Base):
    """Dataset Excel enviado para treinamento."""

    __tablename__ = "bert_datasets"

    id = Column(Integer, primary_key=True, index=True)

    # Metadata do arquivo
    filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)  # Caminho no storage
    sha256_hash = Column(String(64), nullable=False, unique=True, index=True)
    file_size_bytes = Column(Integer, nullable=False)

    # Estrutura do dataset
    task_type = Column(SQLEnum(TaskType, values_callable=_enum_values_callable), nullable=False)
    text_column = Column(String(100), nullable=False)  # Coluna com tokens/texto
    label_column = Column(String(100), nullable=False)  # Coluna com labels/tags

    # Metadados extraídos
    total_rows = Column(Integer, nullable=False)
    total_labels = Column(Integer, nullable=True)  # Número de classes distintas
    label_distribution = Column(JSON, nullable=True)  # {label: count}
    sample_preview = Column(JSON, nullable=True)  # Primeiras N linhas para preview

    # Auditoria
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relacionamentos
    user = relationship("User", backref="bert_datasets")
    runs = relationship("BertRun", back_populates="dataset", cascade="all, delete-orphan")

    # Índices
    __table_args__ = (
        Index("ix_bert_datasets_uploaded_at", "uploaded_at"),
        Index("ix_bert_datasets_task_type", "task_type"),
    )


class BertRun(Base):
    """Experimento/Run de treinamento BERT."""

    __tablename__ = "bert_runs"

    id = Column(Integer, primary_key=True, index=True)

    # Nome/descrição
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Dataset
    dataset_id = Column(Integer, ForeignKey("bert_datasets.id"), nullable=False)
    dataset_sha256 = Column(String(64), nullable=False)  # Snapshot do hash para reprodutibilidade

    # Tipo de tarefa
    task_type = Column(SQLEnum(TaskType, values_callable=_enum_values_callable), nullable=False)

    # Modelo base
    base_model = Column(String(255), nullable=False)  # Ex: neuralmind/bert-base-portuguese-cased

    # Hiperparâmetros
    config_json = Column(JSON, nullable=False)  # Todos os hiperparâmetros
    # Campos principais extraídos para filtros
    learning_rate = Column(Float, nullable=True)
    batch_size = Column(Integer, nullable=True)
    epochs = Column(Integer, nullable=True)
    max_length = Column(Integer, nullable=True)
    train_split = Column(Float, nullable=True)
    seed = Column(Integer, nullable=True, default=42)

    # Reprodutibilidade
    git_commit_hash = Column(String(40), nullable=True)  # Commit do código
    environment_fingerprint = Column(String(64), nullable=True)  # Hash do lockfile/docker

    # Status
    status = Column(String(50), default="pending", nullable=False)
    error_message = Column(Text, nullable=True)

    # Métricas finais (preenchidas após conclusão)
    final_accuracy = Column(Float, nullable=True)
    final_macro_f1 = Column(Float, nullable=True)
    final_weighted_f1 = Column(Float, nullable=True)

    # Fingerprint do modelo treinado (sem pesos, apenas hash)
    model_fingerprint = Column(String(64), nullable=True)

    # Timestamps
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Relacionamentos
    dataset = relationship("BertDataset", back_populates="runs")
    user = relationship("User", backref="bert_runs")
    jobs = relationship("BertJob", back_populates="run", cascade="all, delete-orphan")
    metrics = relationship("BertMetric", back_populates="run", cascade="all, delete-orphan")
    logs = relationship("BertLog", back_populates="run", cascade="all, delete-orphan")

    # Índices
    __table_args__ = (
        Index("ix_bert_runs_status", "status"),
        Index("ix_bert_runs_created_at", "created_at"),
        Index("ix_bert_runs_dataset_id", "dataset_id"),
    )


class BertJob(Base):
    """Job de treinamento na fila."""

    __tablename__ = "bert_jobs"

    id = Column(Integer, primary_key=True, index=True)

    # Run associado
    run_id = Column(Integer, ForeignKey("bert_runs.id"), nullable=False)

    # Status
    status = Column(SQLEnum(JobStatus, values_callable=_enum_values_callable), default=JobStatus.PENDING, nullable=False)

    # Worker que pegou o job
    worker_id = Column(Integer, ForeignKey("bert_workers.id"), nullable=True)
    claimed_at = Column(DateTime, nullable=True)

    # Progresso
    current_epoch = Column(Integer, nullable=True)
    total_epochs = Column(Integer, nullable=True)
    progress_percent = Column(Float, default=0.0)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Retry
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    error_message = Column(Text, nullable=True)

    # Timeout
    timeout_seconds = Column(Integer, default=3600 * 6)  # 6 horas padrão

    # Relacionamentos
    run = relationship("BertRun", back_populates="jobs")
    worker = relationship("BertWorker", back_populates="jobs")

    # Índices
    __table_args__ = (
        Index("ix_bert_jobs_status", "status"),
        Index("ix_bert_jobs_created_at", "created_at"),
        Index("ix_bert_jobs_run_id", "run_id"),
    )


class BertMetric(Base):
    """Métricas por época de treinamento."""

    __tablename__ = "bert_metrics"

    id = Column(Integer, primary_key=True, index=True)

    # Run associado
    run_id = Column(Integer, ForeignKey("bert_runs.id"), nullable=False)

    # Época
    epoch = Column(Integer, nullable=False)

    # Métricas de loss
    train_loss = Column(Float, nullable=True)
    val_loss = Column(Float, nullable=True)

    # Métricas de classificação
    val_accuracy = Column(Float, nullable=True)
    val_macro_f1 = Column(Float, nullable=True)
    val_weighted_f1 = Column(Float, nullable=True)
    val_macro_precision = Column(Float, nullable=True)
    val_macro_recall = Column(Float, nullable=True)

    # Métricas NER (seqeval) - para token classification
    seqeval_f1 = Column(Float, nullable=True)
    seqeval_precision = Column(Float, nullable=True)
    seqeval_recall = Column(Float, nullable=True)

    # Dados detalhados
    classification_report = Column(JSON, nullable=True)
    confusion_matrix = Column(JSON, nullable=True)

    # Timestamp
    recorded_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relacionamentos
    run = relationship("BertRun", back_populates="metrics")

    # Índices
    __table_args__ = (
        Index("ix_bert_metrics_run_id", "run_id"),
        Index("ix_bert_metrics_epoch", "epoch"),
    )


class BertLog(Base):
    """Logs estruturados de treinamento."""

    __tablename__ = "bert_logs"

    id = Column(Integer, primary_key=True, index=True)

    # Run associado
    run_id = Column(Integer, ForeignKey("bert_runs.id"), nullable=False)

    # Log info
    level = Column(String(20), nullable=False)  # DEBUG, INFO, WARNING, ERROR
    message = Column(Text, nullable=False)
    extra_data = Column(JSON, nullable=True)  # Dados adicionais estruturados

    # Contexto
    source = Column(String(100), nullable=True)  # worker, api, etc
    epoch = Column(Integer, nullable=True)
    batch = Column(Integer, nullable=True)

    # Timestamp
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relacionamentos
    run = relationship("BertRun", back_populates="logs")

    # Índices
    __table_args__ = (
        Index("ix_bert_logs_run_id", "run_id"),
        Index("ix_bert_logs_level", "level"),
        Index("ix_bert_logs_timestamp", "timestamp"),
    )


class BertTestHistory(Base):
    """Historico de testes de inferencia."""

    __tablename__ = "bert_test_history"

    id = Column(Integer, primary_key=True, index=True)

    # Run/modelo usado
    run_id = Column(Integer, ForeignKey("bert_runs.id"), nullable=False)

    # Input
    input_type = Column(String(20), nullable=False)  # "text" ou "pdf"
    input_text = Column(Text, nullable=False)  # Texto classificado (ou extraido do PDF)
    input_filename = Column(String(255), nullable=True)  # Nome do PDF (se aplicavel)

    # Resultado
    predicted_label = Column(String(255), nullable=False)
    confidence = Column(Float, nullable=False)

    # Usuario
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relacionamentos
    run = relationship("BertRun", backref="test_history")
    user = relationship("User", backref="bert_test_history")

    # Indices
    __table_args__ = (
        Index("ix_bert_test_history_run_id", "run_id"),
        Index("ix_bert_test_history_user_id", "user_id"),
        Index("ix_bert_test_history_created_at", "created_at"),
    )


class BertWorker(Base):
    """Registro de workers GPU."""

    __tablename__ = "bert_workers"

    id = Column(Integer, primary_key=True, index=True)

    # Identificação
    name = Column(String(255), nullable=False, unique=True)
    description = Column(Text, nullable=True)

    # Token de autenticação (hash)
    token_hash = Column(String(64), nullable=False)

    # Info da máquina
    gpu_name = Column(String(255), nullable=True)
    gpu_vram_gb = Column(Float, nullable=True)
    cuda_version = Column(String(20), nullable=True)

    # Status
    is_active = Column(Boolean, default=True)
    last_heartbeat = Column(DateTime, nullable=True)
    current_job_id = Column(Integer, nullable=True)

    # Stats
    total_jobs_completed = Column(Integer, default=0)
    total_training_hours = Column(Float, default=0.0)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relacionamentos
    jobs = relationship("BertJob", back_populates="worker")

    # Índices
    __table_args__ = (
        Index("ix_bert_workers_is_active", "is_active"),
        Index("ix_bert_workers_last_heartbeat", "last_heartbeat"),
    )
