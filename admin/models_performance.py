# admin/models_performance.py
"""
Modelos para sistema de logs de performance MVP.

Objetivo: identificar rapidamente se o gargalo e LLM, DB ou Parse.
- Todos os usuarios geram logs
- Apenas admin visualiza
- Sempre ativo (sem toggle)
"""

import re
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, Text, Index, ForeignKey
from sqlalchemy.orm import relationship
from database.connection import Base
from utils.timezone import get_utc_now, to_iso_utc


class RouteSystemMap(Base):
    """
    Mapeamento de rotas para nomes de sistema.

    Permite ao admin definir nomes amigaveis para sistemas baseado na rota.
    Ex: /api/gerador-pecas/* -> "Gerador de Pecas"
    """
    __tablename__ = "route_system_map"

    id = Column(Integer, primary_key=True, index=True)
    route_pattern = Column(String(500), nullable=False, unique=True, index=True)
    system_name = Column(String(100), nullable=False)
    match_type = Column(String(20), nullable=False, default='prefix')  # exact, prefix, regex
    priority = Column(Integer, nullable=False, default=0)  # maior = mais prioritario
    created_at = Column(DateTime, default=get_utc_now)
    updated_at = Column(DateTime, default=get_utc_now, onupdate=get_utc_now)

    def matches(self, route: str) -> bool:
        """Verifica se a rota casa com este mapeamento."""
        if self.match_type == 'exact':
            return route == self.route_pattern
        elif self.match_type == 'prefix':
            return route.startswith(self.route_pattern)
        elif self.match_type == 'regex':
            try:
                return bool(re.match(self.route_pattern, route))
            except re.error:
                return False
        return False

    def to_dict(self):
        return {
            "id": self.id,
            "route_pattern": self.route_pattern,
            "system_name": self.system_name,
            "match_type": self.match_type,
            "priority": self.priority,
            "created_at": to_iso_utc(self.created_at),
            "updated_at": to_iso_utc(self.updated_at),
        }

    def __repr__(self):
        return f"<RouteSystemMap(pattern='{self.route_pattern}', system='{self.system_name}', type='{self.match_type}')>"


class AdminSettings(Base):
    """
    Configuracoes globais do admin.
    Mantido para compatibilidade.
    """
    __tablename__ = "admin_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=get_utc_now, onupdate=get_utc_now)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)


class PerformanceLog(Base):
    """
    Logs de performance MVP para diagnostico de gargalos.

    Foco: responder rapidamente se lentidao vem de LLM, DB ou Parse.
    """
    __tablename__ = "performance_logs"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=get_utc_now, index=True)

    # Identificacao
    request_id = Column(String(36), nullable=True, index=True)  # UUID da request
    admin_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    admin_username = Column(String(100), nullable=True)
    route = Column(String(500), nullable=False, index=True)  # endpoint
    method = Column(String(10), nullable=True)  # GET, POST, etc
    layer = Column(String(50), nullable=False, default='middleware')  # middleware, controller, service, db, io
    action = Column(String(100), nullable=True, index=True)  # label: gerar_json_ia, atualizar_json, etc
    status = Column(String(20), nullable=False, default='ok')  # ok, error

    # Tempos (ms) - FOCO DO MVP
    duration_ms = Column(Float, nullable=False, default=0)  # Tempo total (campo legado)
    total_ms = Column(Float, nullable=True)  # Tempo total da request
    llm_request_ms = Column(Float, nullable=True)  # Tempo chamando LLM
    json_parse_ms = Column(Float, nullable=True)  # Tempo parse/validacao JSON
    db_total_ms = Column(Float, nullable=True)  # Tempo total no BD
    db_slowest_query_ms = Column(Float, nullable=True)  # Query mais lenta

    # Volume
    prompt_tokens = Column(Integer, nullable=True)  # Tokens enviados (estimativa)
    response_tokens = Column(Integer, nullable=True)  # Tokens recebidos (estimativa)
    json_size_chars = Column(Integer, nullable=True)  # Tamanho JSON persistido

    # Erro (curto)
    error_type = Column(String(50), nullable=True)  # timeout, parse_error, db_error, network_error
    error_message_short = Column(String(200), nullable=True)  # Mensagem curta

    # Campo calculado para exibicao (nao persistido, calculado no frontend/query)
    # bottleneck: LLM, DB, PARSE, OUTRO

    # Indexes para queries frequentes
    __table_args__ = (
        Index('ix_perf_logs_date_route', 'created_at', 'route'),
        Index('ix_perf_logs_date_action', 'created_at', 'action'),
        Index('ix_perf_logs_user_date', 'admin_user_id', 'created_at'),
    )

    def to_dict(self):
        """Converte para dicionario com bottleneck calculado."""
        data = {
            "id": self.id,
            "created_at": to_iso_utc(self.created_at),
            "request_id": self.request_id,
            "admin_user_id": self.admin_user_id,
            "admin_username": self.admin_username,
            "route": self.route,
            "method": self.method,
            "layer": self.layer,
            "action": self.action,
            "status": self.status,
            "total_ms": self.total_ms,
            "llm_request_ms": self.llm_request_ms,
            "json_parse_ms": self.json_parse_ms,
            "db_total_ms": self.db_total_ms,
            "db_slowest_query_ms": self.db_slowest_query_ms,
            "prompt_tokens": self.prompt_tokens,
            "response_tokens": self.response_tokens,
            "json_size_chars": self.json_size_chars,
            "error_type": self.error_type,
            "error_message_short": self.error_message_short,
            "bottleneck": self._calc_bottleneck(),
        }
        return data

    def _calc_bottleneck(self) -> str:
        """Calcula qual componente e o gargalo."""
        llm = self.llm_request_ms or 0
        db = self.db_total_ms or 0
        parse = self.json_parse_ms or 0
        total = self.total_ms or 0

        # Se nenhum tempo significativo, retorna OUTRO
        if total < 100:
            return "-"

        max_component = max(llm, db, parse)

        # Precisa representar pelo menos 40% do total para ser considerado gargalo
        threshold = total * 0.4

        if max_component < threshold:
            return "OUTRO"

        if llm == max_component:
            return "LLM"
        elif db == max_component:
            return "DB"
        elif parse == max_component:
            return "PARSE"

        return "OUTRO"

    def __repr__(self):
        return f"<PerformanceLog(id={self.id}, route='{self.route}', action='{self.action}', total={self.total_ms}ms, bottleneck={self._calc_bottleneck()})>"
