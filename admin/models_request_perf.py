# admin/models_request_perf.py
"""
Modelo para logs de performance detalhados de requests.

Captura metricas do PerformanceTracker incluindo:
- Timeline completa de cada request (t0 a t11)
- Tempo de cada agente
- Estatisticas de streaming
- Overhead do sistema

Usado para diagnostico avancado de latencia.
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, Text, Index, JSON
from database.connection import Base
from utils.timezone import get_utc_now, to_iso_utc


class RequestPerfLog(Base):
    """
    Log de performance detalhado de requests.

    Armazena dados do PerformanceTracker para analise de gargalos.
    """
    __tablename__ = "request_perf_logs"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=get_utc_now, index=True)

    # Identificacao
    request_id = Column(String(36), nullable=False, index=True)
    sistema = Column(String(100), nullable=False, index=True)
    route = Column(String(255), nullable=True)

    # Usuario (opcional)
    user_id = Column(Integer, nullable=True)
    username = Column(String(100), nullable=True)

    # Tempos principais (ms)
    total_ms = Column(Float, nullable=False, index=True)
    ttft_ms = Column(Float, nullable=True)  # Time to First Token
    generation_ms = Column(Float, nullable=True)  # Tempo de geracao LLM

    # Tempos por etapa (ms)
    auth_ms = Column(Float, nullable=True)  # t1 - t0
    load_config_ms = Column(Float, nullable=True)  # t2 - t1
    agente1_ms = Column(Float, nullable=True)  # Coleta TJ-MS
    agente2_ms = Column(Float, nullable=True)  # Detector modulos
    prompt_build_ms = Column(Float, nullable=True)  # Montagem prompt
    postprocess_ms = Column(Float, nullable=True)  # Pos-processamento
    db_save_ms = Column(Float, nullable=True)  # Salvamento BD
    overhead_ms = Column(Float, nullable=True)  # Tempo nao contabilizado

    # Streaming stats
    streaming_chunks = Column(Integer, nullable=True)
    streaming_bytes = Column(Integer, nullable=True)
    avg_chunk_size = Column(Float, nullable=True)
    avg_chunk_interval_ms = Column(Float, nullable=True)

    # Metadados
    numero_cnj = Column(String(30), nullable=True)
    tipo_peca = Column(String(100), nullable=True)
    modelo_llm = Column(String(100), nullable=True)

    # Timeline completa (JSON)
    timeline_json = Column(JSON, nullable=True)

    # Status
    success = Column(Boolean, default=True)
    error = Column(String(500), nullable=True)

    # Indexes
    __table_args__ = (
        Index('ix_req_perf_date_sistema', 'created_at', 'sistema'),
        Index('ix_req_perf_request_id', 'request_id'),
    )

    def __repr__(self):
        return f"<RequestPerfLog(id={self.id}, request_id='{self.request_id}', total={self.total_ms}ms)>"

    def to_dict(self):
        """Converte para dicionario para serializacao"""
        return {
            "id": self.id,
            "created_at": to_iso_utc(self.created_at),
            "request_id": self.request_id,
            "sistema": self.sistema,
            "route": self.route,
            "user_id": self.user_id,
            "username": self.username,

            # Tempos principais
            "total_ms": round(self.total_ms, 1) if self.total_ms else None,
            "ttft_ms": round(self.ttft_ms, 1) if self.ttft_ms else None,
            "generation_ms": round(self.generation_ms, 1) if self.generation_ms else None,

            # Tempos por etapa
            "auth_ms": round(self.auth_ms, 1) if self.auth_ms else None,
            "load_config_ms": round(self.load_config_ms, 1) if self.load_config_ms else None,
            "agente1_ms": round(self.agente1_ms, 1) if self.agente1_ms else None,
            "agente2_ms": round(self.agente2_ms, 1) if self.agente2_ms else None,
            "prompt_build_ms": round(self.prompt_build_ms, 1) if self.prompt_build_ms else None,
            "postprocess_ms": round(self.postprocess_ms, 1) if self.postprocess_ms else None,
            "db_save_ms": round(self.db_save_ms, 1) if self.db_save_ms else None,
            "overhead_ms": round(self.overhead_ms, 1) if self.overhead_ms else None,

            # Streaming
            "streaming_chunks": self.streaming_chunks,
            "streaming_bytes": self.streaming_bytes,
            "avg_chunk_size": round(self.avg_chunk_size, 1) if self.avg_chunk_size else None,
            "avg_chunk_interval_ms": round(self.avg_chunk_interval_ms, 2) if self.avg_chunk_interval_ms else None,

            # Metadados
            "numero_cnj": self.numero_cnj,
            "tipo_peca": self.tipo_peca,
            "modelo_llm": self.modelo_llm,

            # Timeline
            "timeline": self.timeline_json,

            # Status
            "success": self.success,
            "error": self.error,
        }

    @classmethod
    def from_tracker_report(cls, report: dict, user_id: int = None, username: str = None):
        """
        Cria instancia a partir do report do PerformanceTracker.

        Args:
            report: Dicionario retornado por tracker.get_report()
            user_id: ID do usuario (opcional)
            username: Nome do usuario (opcional)

        Returns:
            RequestPerfLog instance
        """
        metrics = report.get("metrics", {})
        streaming = report.get("streaming", {})
        metadata = report.get("metadata", {})

        return cls(
            request_id=report.get("request_id", ""),
            sistema=report.get("sistema", ""),
            route=report.get("route", ""),
            user_id=user_id,
            username=username,

            # Tempos principais
            total_ms=report.get("total_ms", 0),
            ttft_ms=metrics.get("ttft_ms"),
            generation_ms=metrics.get("generation_ms"),

            # Tempos por etapa
            agente1_ms=metrics.get("agente1_ms"),
            agente2_ms=metrics.get("agente2_ms"),
            prompt_build_ms=metrics.get("prompt_build_ms"),
            postprocess_ms=metrics.get("postprocess_ms"),
            db_save_ms=metrics.get("db_save_ms"),
            overhead_ms=metrics.get("overhead_ms"),

            # Streaming
            streaming_chunks=streaming.get("total_chunks"),
            streaming_bytes=streaming.get("total_bytes"),
            avg_chunk_size=streaming.get("avg_chunk_size"),
            avg_chunk_interval_ms=streaming.get("avg_chunk_interval_ms"),

            # Metadados
            numero_cnj=metadata.get("numero_cnj"),
            tipo_peca=metadata.get("tipo_peca"),
            modelo_llm=metadata.get("modelo"),

            # Timeline completa
            timeline_json=report.get("timeline"),
        )
