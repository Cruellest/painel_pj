# services/route_config.py
"""
Configuração de rotas por perfil de latência (fast/slow path).

PROBLEMA: Diferentes operações têm diferentes tolerâncias de latência:
- Chat/edição: usuário espera resposta rápida (< 5s TTFT)
- Geração de peça: pode demorar mais (aceita 15-60s)
- Extração de documentos: batch processing (aceita minutos)

SOLUÇÃO: Configuração por rota que define:
- Modelo preferido e fallback
- Timeout SLA para fallback automático
- Se usa streaming ou não
- Thinking level apropriado

IMPORTANTE: O fallback SLA está DESABILITADO por padrão.
Para habilitar, configure no painel admin (/admin/prompts-config):
- global.sla_fallback_habilitado = true
- global.sla_timeout_segundos = 30
- global.modelo_fallback = gemini-2.0-flash-lite

Uso:
    from services.route_config import get_route_config, RouteProfile, is_sla_fallback_enabled

    config = get_route_config("/api/gerador/editar-minuta")

    # Verifica se fallback está habilitado antes de usar
    if is_sla_fallback_enabled(db):
        response = await gemini_service.generate_with_sla(...)
    else:
        response = await gemini_service.generate(...)

Autor: LAB/PGE-MS
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, List
from datetime import datetime, timedelta
from collections import defaultdict
from enum import Enum

logger = logging.getLogger(__name__)


class RouteProfile(Enum):
    """Perfis de latência para rotas."""

    # Interativo - usuário aguardando, precisa de resposta rápida
    INTERACTIVE = "interactive"

    # Geração - pode demorar mais, usuário sabe que é complexo
    GENERATION = "generation"

    # Batch - processamento em lote, sem usuário aguardando
    BATCH = "batch"

    # Extração - análise de documentos, tolerante a latência
    EXTRACTION = "extraction"


@dataclass
class RouteConfig:
    """Configuração de uma rota específica."""

    # Identificação
    route_pattern: str
    profile: RouteProfile

    # Modelos
    model_primary: str = "gemini-3-flash-preview"
    model_fallback: str = "gemini-2.0-flash-lite"

    # Timeouts e SLA
    sla_timeout: float = 5.0  # segundos para TTFT antes de fallback
    max_timeout: float = 120.0  # timeout total máximo

    # Configurações de IA
    thinking_level: Optional[str] = "low"  # minimal, low, medium, high
    use_streaming: bool = True
    temperature: float = 0.3

    # Truncamento
    max_prompt_chars: int = 100000
    auto_truncate: bool = True

    def __post_init__(self):
        """Ajusta configurações baseado no perfil."""
        if self.profile == RouteProfile.INTERACTIVE:
            # Interativo: resposta rápida é prioridade
            self.sla_timeout = min(self.sla_timeout, 5.0)
            self.use_streaming = True
            self.thinking_level = "low"

        elif self.profile == RouteProfile.GENERATION:
            # Geração: qualidade é prioridade
            self.sla_timeout = 15.0
            self.max_timeout = 180.0
            self.thinking_level = "medium"

        elif self.profile == RouteProfile.BATCH:
            # Batch: sem urgência
            self.sla_timeout = 30.0
            self.max_timeout = 300.0
            self.use_streaming = False

        elif self.profile == RouteProfile.EXTRACTION:
            # Extração: tolerante a latência
            self.sla_timeout = 20.0
            self.max_timeout = 240.0
            self.thinking_level = "low"


# Configurações padrão por rota
DEFAULT_ROUTE_CONFIGS: Dict[str, RouteConfig] = {
    # === ROTAS INTERATIVAS (fast path) ===
    "/api/gerador/editar-minuta": RouteConfig(
        route_pattern="/api/gerador/editar-minuta",
        profile=RouteProfile.INTERACTIVE,
        sla_timeout=5.0,
        thinking_level="low",
        use_streaming=True
    ),
    "/api/gerador/editar-minuta-stream": RouteConfig(
        route_pattern="/api/gerador/editar-minuta-stream",
        profile=RouteProfile.INTERACTIVE,
        sla_timeout=5.0,
        thinking_level="low",
        use_streaming=True
    ),
    "/admin/api/teste-ativacao/relatorio-ativacao": RouteConfig(
        route_pattern="/admin/api/teste-ativacao/relatorio-ativacao",
        profile=RouteProfile.INTERACTIVE,
        sla_timeout=5.0,
        thinking_level="low"
    ),

    # === ROTAS DE GERAÇÃO (slow path) ===
    "/api/gerador/processar-stream": RouteConfig(
        route_pattern="/api/gerador/processar-stream",
        profile=RouteProfile.GENERATION,
        sla_timeout=15.0,
        thinking_level="medium",
        max_prompt_chars=150000
    ),
    "/api/gerador/gerar": RouteConfig(
        route_pattern="/api/gerador/gerar",
        profile=RouteProfile.GENERATION,
        sla_timeout=15.0,
        thinking_level="medium"
    ),

    # === ROTAS DE EXTRAÇÃO ===
    "/api/gerador/extrair": RouteConfig(
        route_pattern="/api/gerador/extrair",
        profile=RouteProfile.EXTRACTION,
        sla_timeout=20.0,
        thinking_level="low"
    ),
    "/api/gerador/extraction/": RouteConfig(
        route_pattern="/api/gerador/extraction/",
        profile=RouteProfile.EXTRACTION,
        sla_timeout=20.0,
        thinking_level="low"
    ),

    # === ROTAS DE TESTE (fast path) ===
    "/admin/api/teste-ativacao/gerar-variaveis": RouteConfig(
        route_pattern="/admin/api/teste-ativacao/gerar-variaveis",
        profile=RouteProfile.INTERACTIVE,
        sla_timeout=5.0,
        thinking_level="low"
    ),
}


def get_route_config(route: str) -> RouteConfig:
    """
    Obtém configuração para uma rota específica.

    Tenta match exato primeiro, depois por prefixo.

    Args:
        route: Caminho da rota (ex: "/api/gerador/editar-minuta")

    Returns:
        RouteConfig para a rota ou config padrão
    """
    # Match exato
    if route in DEFAULT_ROUTE_CONFIGS:
        return DEFAULT_ROUTE_CONFIGS[route]

    # Match por prefixo
    for pattern, config in DEFAULT_ROUTE_CONFIGS.items():
        if route.startswith(pattern):
            return config

    # Config padrão para rotas desconhecidas
    return RouteConfig(
        route_pattern=route,
        profile=RouteProfile.GENERATION  # Conservador
    )


# ============================================
# MÉTRICAS POR ROTA
# ============================================

@dataclass
class RouteMetrics:
    """Métricas agregadas de uma rota."""

    route: str
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    fallback_calls: int = 0

    # Latências em ms
    total_latency_ms: float = 0
    min_latency_ms: float = float('inf')
    max_latency_ms: float = 0

    # TTFT em ms
    total_ttft_ms: float = 0
    min_ttft_ms: float = float('inf')
    max_ttft_ms: float = 0

    # Timestamps
    first_call: Optional[datetime] = None
    last_call: Optional[datetime] = None

    @property
    def avg_latency_ms(self) -> float:
        if self.total_calls == 0:
            return 0
        return self.total_latency_ms / self.total_calls

    @property
    def avg_ttft_ms(self) -> float:
        if self.total_calls == 0:
            return 0
        return self.total_ttft_ms / self.total_calls

    @property
    def success_rate(self) -> float:
        if self.total_calls == 0:
            return 0
        return self.successful_calls / self.total_calls * 100

    @property
    def fallback_rate(self) -> float:
        if self.total_calls == 0:
            return 0
        return self.fallback_calls / self.total_calls * 100

    def to_dict(self) -> dict:
        return {
            "route": self.route,
            "calls": {
                "total": self.total_calls,
                "successful": self.successful_calls,
                "failed": self.failed_calls,
                "fallback": self.fallback_calls,
                "success_rate": f"{self.success_rate:.1f}%",
                "fallback_rate": f"{self.fallback_rate:.1f}%"
            },
            "latency_ms": {
                "avg": round(self.avg_latency_ms, 2),
                "min": round(self.min_latency_ms, 2) if self.min_latency_ms != float('inf') else 0,
                "max": round(self.max_latency_ms, 2)
            },
            "ttft_ms": {
                "avg": round(self.avg_ttft_ms, 2),
                "min": round(self.min_ttft_ms, 2) if self.min_ttft_ms != float('inf') else 0,
                "max": round(self.max_ttft_ms, 2)
            },
            "period": {
                "first_call": self.first_call.isoformat() if self.first_call else None,
                "last_call": self.last_call.isoformat() if self.last_call else None
            }
        }


# Armazenamento de métricas por rota (in-memory)
_route_metrics: Dict[str, RouteMetrics] = defaultdict(lambda: RouteMetrics(route="unknown"))


def record_route_call(
    route: str,
    success: bool,
    latency_ms: float,
    ttft_ms: float = 0,
    used_fallback: bool = False
):
    """
    Registra uma chamada a uma rota para métricas.

    Args:
        route: Caminho da rota
        success: Se a chamada foi bem sucedida
        latency_ms: Latência total em ms
        ttft_ms: Time to First Token em ms
        used_fallback: Se usou modelo de fallback
    """
    metrics = _route_metrics[route]

    # Inicializa rota se necessário
    if metrics.route == "unknown":
        metrics.route = route

    # Atualiza contadores
    metrics.total_calls += 1
    if success:
        metrics.successful_calls += 1
    else:
        metrics.failed_calls += 1

    if used_fallback:
        metrics.fallback_calls += 1

    # Atualiza latências
    metrics.total_latency_ms += latency_ms
    metrics.min_latency_ms = min(metrics.min_latency_ms, latency_ms)
    metrics.max_latency_ms = max(metrics.max_latency_ms, latency_ms)

    # Atualiza TTFT
    if ttft_ms > 0:
        metrics.total_ttft_ms += ttft_ms
        metrics.min_ttft_ms = min(metrics.min_ttft_ms, ttft_ms)
        metrics.max_ttft_ms = max(metrics.max_ttft_ms, ttft_ms)

    # Timestamps
    now = datetime.utcnow()
    if metrics.first_call is None:
        metrics.first_call = now
    metrics.last_call = now

    # Log para monitoramento
    logger.debug(
        f"[Metrics] {route}: {latency_ms:.0f}ms "
        f"(TTFT: {ttft_ms:.0f}ms, fallback: {used_fallback})"
    )


def get_route_metrics(route: str = None) -> dict:
    """
    Obtém métricas de rotas.

    Args:
        route: Rota específica ou None para todas

    Returns:
        Dict com métricas
    """
    if route:
        if route in _route_metrics:
            return _route_metrics[route].to_dict()
        return {"error": f"Rota '{route}' não encontrada"}

    # Todas as rotas
    return {
        "routes": [m.to_dict() for m in _route_metrics.values()],
        "summary": {
            "total_routes": len(_route_metrics),
            "total_calls": sum(m.total_calls for m in _route_metrics.values()),
            "avg_latency_ms": round(
                sum(m.total_latency_ms for m in _route_metrics.values()) /
                max(sum(m.total_calls for m in _route_metrics.values()), 1),
                2
            )
        }
    }


def reset_route_metrics(route: str = None):
    """
    Reseta métricas de rotas.

    Args:
        route: Rota específica ou None para todas
    """
    global _route_metrics

    if route:
        if route in _route_metrics:
            del _route_metrics[route]
    else:
        _route_metrics.clear()

    logger.info(f"[Metrics] Reset: {route or 'todas as rotas'}")


# ============================================
# CONFIGURAÇÃO SLA DO BANCO DE DADOS
# ============================================

def is_sla_fallback_enabled(db) -> bool:
    """
    Verifica se o fallback SLA está habilitado no banco.

    IMPORTANTE: Desabilitado por padrão. Habilite em /admin/prompts-config
    configurando global.sla_fallback_habilitado = true

    Args:
        db: Sessão SQLAlchemy

    Returns:
        True se fallback está habilitado, False caso contrário
    """
    try:
        from admin.models import ConfiguracaoIA

        config = db.query(ConfiguracaoIA).filter(
            ConfiguracaoIA.sistema == "global",
            ConfiguracaoIA.chave == "sla_fallback_habilitado"
        ).first()

        if config and config.valor:
            return config.valor.lower() in ("true", "1", "yes", "sim")

        return False  # Desabilitado por padrão

    except Exception as e:
        logger.warning(f"[SLA Config] Erro ao verificar fallback: {e}")
        return False


def get_sla_config(db) -> dict:
    """
    Obtém configurações de SLA do banco de dados.

    Returns:
        Dict com:
        - enabled: bool - se fallback está habilitado
        - timeout_seconds: float - timeout antes de fallback
        - fallback_model: str - modelo de fallback
    """
    try:
        from admin.models import ConfiguracaoIA

        # Busca todas as configs de SLA
        configs = db.query(ConfiguracaoIA).filter(
            ConfiguracaoIA.sistema == "global",
            ConfiguracaoIA.chave.in_([
                "sla_fallback_habilitado",
                "sla_timeout_segundos",
                "modelo_fallback"
            ])
        ).all()

        config_dict = {c.chave: c.valor for c in configs}

        enabled = config_dict.get("sla_fallback_habilitado", "false")
        enabled = enabled.lower() in ("true", "1", "yes", "sim")

        timeout = config_dict.get("sla_timeout_segundos", "30")
        try:
            timeout = float(timeout)
        except:
            timeout = 30.0

        fallback_model = config_dict.get("modelo_fallback", "gemini-2.0-flash-lite")

        return {
            "enabled": enabled,
            "timeout_seconds": timeout,
            "fallback_model": fallback_model
        }

    except Exception as e:
        logger.warning(f"[SLA Config] Erro ao obter config: {e}")
        return {
            "enabled": False,
            "timeout_seconds": 30.0,
            "fallback_model": "gemini-2.0-flash-lite"
        }


# ============================================
# EXPORTS
# ============================================

__all__ = [
    "RouteProfile",
    "RouteConfig",
    "get_route_config",
    "RouteMetrics",
    "record_route_call",
    "get_route_metrics",
    "reset_route_metrics",
    "DEFAULT_ROUTE_CONFIGS",
    # SLA Config
    "is_sla_fallback_enabled",
    "get_sla_config",
]
