# admin/models_performance.py
"""
Modelos para sistema de logs de performance.

Armazena logs de performance e configurações de admin.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, Text, Index, ForeignKey
from sqlalchemy.orm import relationship
from database.connection import Base


class AdminSettings(Base):
    """
    Configurações globais do admin.
    Usado para toggle de logs de performance.
    """
    __tablename__ = "admin_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Chaves conhecidas:
    # - "performance_logs_enabled": "true" / "false"
    # - "performance_logs_admin_id": ID do admin que ativou


class PerformanceLog(Base):
    """
    Logs de performance para diagnóstico.

    Armazena timing de requests por camada:
    - middleware: entrada/saída do request
    - controller: processamento no endpoint
    - service: lógica de negócio
    - repository/db: acesso ao banco de dados
    - io: operações de filesystem
    """
    __tablename__ = "performance_logs"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Usuário que gerou o log (apenas admin)
    admin_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    admin_username = Column(String(50), nullable=True)

    # Request info
    request_id = Column(String(36), nullable=True, index=True)  # UUID para agrupar camadas
    method = Column(String(10), nullable=False)  # GET, POST, etc
    route = Column(String(500), nullable=False, index=True)  # /api/admin/...

    # Camada medida
    layer = Column(String(50), nullable=False, index=True)  # middleware, controller, service, db, io
    action = Column(String(200), nullable=True)  # Nome da função/operação

    # Métricas
    duration_ms = Column(Float, nullable=False)  # Tempo em milissegundos

    # Metadados opcionais (curtos)
    status_code = Column(Integer, nullable=True)
    extra_info = Column(String(500), nullable=True)  # Info adicional curta

    # Indexes compostos para queries frequentes
    __table_args__ = (
        Index('ix_perf_logs_date_route', 'created_at', 'route'),
        Index('ix_perf_logs_admin_date', 'admin_user_id', 'created_at'),
        Index('ix_perf_logs_request', 'request_id'),
    )

    def __repr__(self):
        return f"<PerformanceLog(id={self.id}, route='{self.route}', layer='{self.layer}', duration={self.duration_ms}ms)>"
