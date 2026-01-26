# utils/health_check.py
"""
Sistema de Health Check com verificação de dependências.

Verifica o status de:
- Banco de dados (PostgreSQL)
- Serviços externos (Gemini API)
- Circuit Breakers
- Cache
- Background Tasks

USO:
    from utils.health_check import get_health_status, HealthStatus

    # Health check completo
    status = await get_health_status()

    # Health check específico
    db_status = await check_database()

Autor: LAB/PGE-MS
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from sqlalchemy import text
from typing import Any, Dict, List, Optional

# Tenta usar logging estruturado
try:
    from utils.logging_config import get_logger
    logger = get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    """Status possíveis de um componente."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ComponentHealth:
    """Saúde de um componente individual."""
    name: str
    status: HealthStatus
    latency_ms: Optional[float] = None
    message: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        result = {
            "name": self.name,
            "status": self.status.value,
        }
        if self.latency_ms is not None:
            result["latency_ms"] = round(self.latency_ms, 2)
        if self.message:
            result["message"] = self.message
        if self.details:
            result["details"] = self.details
        return result


@dataclass
class SystemHealth:
    """Saúde geral do sistema."""
    status: HealthStatus
    components: List[ComponentHealth]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    version: str = "1.0.0"

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "timestamp": self.timestamp.isoformat() + "Z",
            "version": self.version,
            "components": [c.to_dict() for c in self.components]
        }


async def check_database() -> ComponentHealth:
    """
    Verifica conectividade com o banco de dados.

    Executa uma query simples para verificar se o banco responde.
    """
    start = time.perf_counter()
    try:
        from database.connection import SessionLocal

        db = SessionLocal()
        try:
            # Query simples para testar conexão
            result = db.execute(text("SELECT 1")).fetchone()
            latency = (time.perf_counter() - start) * 1000

            if result and result[0] == 1:
                return ComponentHealth(
                    name="database",
                    status=HealthStatus.HEALTHY,
                    latency_ms=latency,
                    message="PostgreSQL conectado"
                )
            else:
                return ComponentHealth(
                    name="database",
                    status=HealthStatus.UNHEALTHY,
                    latency_ms=latency,
                    message="Query retornou resultado inesperado"
                )
        finally:
            db.close()

    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        logger.error(f"[HealthCheck] Database falhou: {e}")
        return ComponentHealth(
            name="database",
            status=HealthStatus.UNHEALTHY,
            latency_ms=latency,
            message=f"Erro: {str(e)[:100]}"
        )


async def check_gemini_api() -> ComponentHealth:
    """
    Verifica se a API do Gemini está acessível.

    Não faz chamada real, apenas verifica:
    - Se a API key está configurada
    - Status do Circuit Breaker
    - Status do HTTP client
    """
    start = time.perf_counter()
    try:
        from services.gemini_service import gemini_service, get_service_status

        # Verifica configuração
        if not gemini_service.is_configured():
            return ComponentHealth(
                name="gemini_api",
                status=HealthStatus.UNHEALTHY,
                message="GEMINI_KEY não configurada"
            )

        # Obtém status detalhado
        status = await get_service_status()
        latency = (time.perf_counter() - start) * 1000

        # Verifica Circuit Breaker
        try:
            from utils.circuit_breaker import get_gemini_circuit_breaker
            cb = get_gemini_circuit_breaker()
            cb_stats = cb.get_stats()

            if cb_stats["state"] == "open":
                return ComponentHealth(
                    name="gemini_api",
                    status=HealthStatus.DEGRADED,
                    latency_ms=latency,
                    message="Circuit breaker aberto",
                    details={
                        "circuit_state": cb_stats["state"],
                        "time_until_retry": cb_stats.get("time_until_retry")
                    }
                )
        except ImportError:
            pass

        return ComponentHealth(
            name="gemini_api",
            status=HealthStatus.HEALTHY,
            latency_ms=latency,
            message="Configurado e disponível",
            details={
                "http_client_active": status.get("http_client_active", False),
                "cache_hit_rate": status.get("cache", {}).get("hit_rate", "N/A")
            }
        )

    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        logger.error(f"[HealthCheck] Gemini API falhou: {e}")
        return ComponentHealth(
            name="gemini_api",
            status=HealthStatus.UNKNOWN,
            latency_ms=latency,
            message=f"Erro ao verificar: {str(e)[:100]}"
        )


async def check_background_tasks() -> ComponentHealth:
    """
    Verifica status das tarefas em background.
    """
    start = time.perf_counter()
    try:
        from utils.background_tasks import get_background_stats

        stats = get_background_stats()
        latency = (time.perf_counter() - start) * 1000

        pending = stats.get("pending", 0)
        failed = stats.get("failed_total", 0)

        # Muitas tarefas pendentes ou falhas indica problema
        if failed > 10:
            status = HealthStatus.DEGRADED
            message = f"{failed} falhas registradas"
        elif pending > 50:
            status = HealthStatus.DEGRADED
            message = f"{pending} tarefas pendentes"
        else:
            status = HealthStatus.HEALTHY
            message = "Operando normalmente"

        return ComponentHealth(
            name="background_tasks",
            status=status,
            latency_ms=latency,
            message=message,
            details=stats
        )

    except ImportError:
        return ComponentHealth(
            name="background_tasks",
            status=HealthStatus.UNKNOWN,
            message="Módulo não disponível"
        )
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        return ComponentHealth(
            name="background_tasks",
            status=HealthStatus.UNKNOWN,
            latency_ms=latency,
            message=f"Erro: {str(e)[:100]}"
        )


async def check_circuit_breakers() -> ComponentHealth:
    """
    Verifica status de todos os Circuit Breakers.
    """
    start = time.perf_counter()
    try:
        from utils.circuit_breaker import get_all_circuit_breakers

        all_cb = get_all_circuit_breakers()
        latency = (time.perf_counter() - start) * 1000

        if not all_cb:
            return ComponentHealth(
                name="circuit_breakers",
                status=HealthStatus.HEALTHY,
                latency_ms=latency,
                message="Nenhum circuit breaker registrado"
            )

        # Conta estados
        open_count = sum(1 for cb in all_cb.values() if cb["state"] == "open")
        half_open_count = sum(1 for cb in all_cb.values() if cb["state"] == "half_open")

        if open_count > 0:
            status = HealthStatus.DEGRADED
            message = f"{open_count} circuit(s) aberto(s)"
        elif half_open_count > 0:
            status = HealthStatus.DEGRADED
            message = f"{half_open_count} circuit(s) em teste"
        else:
            status = HealthStatus.HEALTHY
            message = "Todos os circuitos fechados"

        return ComponentHealth(
            name="circuit_breakers",
            status=status,
            latency_ms=latency,
            message=message,
            details={
                "total": len(all_cb),
                "open": open_count,
                "half_open": half_open_count,
                "circuits": {name: cb["state"] for name, cb in all_cb.items()}
            }
        )

    except ImportError:
        return ComponentHealth(
            name="circuit_breakers",
            status=HealthStatus.UNKNOWN,
            message="Módulo não disponível"
        )
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        return ComponentHealth(
            name="circuit_breakers",
            status=HealthStatus.UNKNOWN,
            latency_ms=latency,
            message=f"Erro: {str(e)[:100]}"
        )


async def check_environment() -> ComponentHealth:
    """
    Verifica variáveis de ambiente essenciais.
    """
    start = time.perf_counter()

    required_vars = [
        "DATABASE_URL",
        "SECRET_KEY",
    ]

    optional_vars = [
        "GEMINI_KEY",
        "OPENROUTER_API_KEY",
    ]

    missing_required = [var for var in required_vars if not os.getenv(var)]
    missing_optional = [var for var in optional_vars if not os.getenv(var)]

    latency = (time.perf_counter() - start) * 1000

    if missing_required:
        return ComponentHealth(
            name="environment",
            status=HealthStatus.UNHEALTHY,
            latency_ms=latency,
            message=f"Variáveis obrigatórias ausentes: {', '.join(missing_required)}",
            details={
                "missing_required": missing_required,
                "missing_optional": missing_optional
            }
        )

    if missing_optional:
        return ComponentHealth(
            name="environment",
            status=HealthStatus.DEGRADED,
            latency_ms=latency,
            message=f"Variáveis opcionais ausentes: {', '.join(missing_optional)}",
            details={
                "missing_optional": missing_optional
            }
        )

    return ComponentHealth(
        name="environment",
        status=HealthStatus.HEALTHY,
        latency_ms=latency,
        message="Todas as variáveis configuradas"
    )


async def get_health_status(include_details: bool = True) -> SystemHealth:
    """
    Executa health check completo do sistema.

    Args:
        include_details: Se True, inclui detalhes de cada componente

    Returns:
        SystemHealth com status geral e de cada componente
    """
    # Executa checks em paralelo
    checks = await asyncio.gather(
        check_database(),
        check_gemini_api(),
        check_background_tasks(),
        check_circuit_breakers(),
        check_environment(),
        return_exceptions=True
    )

    components = []
    for check in checks:
        if isinstance(check, Exception):
            components.append(ComponentHealth(
                name="unknown",
                status=HealthStatus.UNKNOWN,
                message=f"Erro no check: {str(check)[:100]}"
            ))
        else:
            components.append(check)

    # Determina status geral
    statuses = [c.status for c in components]

    if HealthStatus.UNHEALTHY in statuses:
        overall_status = HealthStatus.UNHEALTHY
    elif HealthStatus.DEGRADED in statuses:
        overall_status = HealthStatus.DEGRADED
    elif HealthStatus.UNKNOWN in statuses:
        overall_status = HealthStatus.DEGRADED
    else:
        overall_status = HealthStatus.HEALTHY

    return SystemHealth(
        status=overall_status,
        components=components,
        version=os.getenv("APP_VERSION", "1.0.0")
    )


async def get_health_summary() -> dict:
    """
    Retorna resumo simplificado do health check.

    Útil para endpoints de liveness/readiness do Kubernetes.
    """
    health = await get_health_status(include_details=False)

    return {
        "status": health.status.value,
        "timestamp": health.timestamp.isoformat() + "Z",
        "checks": {
            c.name: c.status.value
            for c in health.components
        }
    }


__all__ = [
    # Classes
    "ComponentHealth",
    "SystemHealth",
    "HealthStatus",
    # Funções
    "get_health_status",
    "get_health_summary",
    "check_database",
    "check_gemini_api",
    "check_background_tasks",
    "check_circuit_breakers",
    "check_environment",
]
