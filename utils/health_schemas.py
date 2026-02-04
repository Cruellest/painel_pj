# utils/health_schemas.py
"""
Schemas Pydantic para respostas de Health Check e Metrics.

Usado para documentação OpenAPI detalhada.

Autor: LAB/PGE-MS
"""

from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum


class HealthStatusEnum(str, Enum):
    """Status possíveis de saúde do sistema."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class ComponentHealthResponse(BaseModel):
    """Status de saúde de um componente individual."""
    name: str = Field(..., description="Nome do componente")
    status: HealthStatusEnum = Field(..., description="Status do componente")
    latency_ms: Optional[float] = Field(None, description="Latência em milissegundos")
    message: Optional[str] = Field(None, description="Mensagem adicional")
    details: Optional[Dict[str, Any]] = Field(None, description="Detalhes extras")

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "database",
                "status": "healthy",
                "latency_ms": 12.5,
                "message": None
            }
        }
    }


class HealthBasicResponse(BaseModel):
    """Resposta do health check básico."""
    status: HealthStatusEnum = Field(..., description="Status geral do sistema")
    timestamp: str = Field(..., description="Timestamp ISO 8601")
    version: str = Field(..., description="Versão da aplicação")

    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "healthy",
                "timestamp": "2024-01-15T10:30:00Z",
                "version": "1.0.0"
            }
        }
    }


class HealthDetailedResponse(BaseModel):
    """Resposta do health check detalhado."""
    status: HealthStatusEnum = Field(..., description="Status geral do sistema")
    timestamp: str = Field(..., description="Timestamp ISO 8601")
    version: str = Field(..., description="Versão da aplicação")
    components: List[ComponentHealthResponse] = Field(
        ...,
        description="Status de cada componente"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "healthy",
                "timestamp": "2024-01-15T10:30:00Z",
                "version": "1.0.0",
                "components": [
                    {"name": "database", "status": "healthy", "latency_ms": 12.5},
                    {"name": "gemini_api", "status": "healthy", "latency_ms": 150.0}
                ]
            }
        }
    }


class ReadinessResponse(BaseModel):
    """Resposta do readiness probe."""
    ready: bool = Field(..., description="Se o serviço está pronto")
    status: str = Field(default="ready", description="Status textual")

    model_config = {
        "json_schema_extra": {
            "example": {"ready": True, "status": "ready"}
        }
    }


class LivenessResponse(BaseModel):
    """Resposta do liveness probe."""
    alive: bool = Field(default=True, description="Se o processo está vivo")

    model_config = {
        "json_schema_extra": {
            "example": {"alive": True}
        }
    }


class MetricsSummary(BaseModel):
    """Resumo de métricas em formato JSON."""
    total_requests: int = Field(..., description="Total de requests processados")
    requests_per_second: float = Field(..., description="Taxa atual de requests")
    avg_latency_ms: float = Field(..., description="Latência média")
    error_rate: float = Field(..., description="Taxa de erros (0-1)")
    uptime_seconds: float = Field(..., description="Tempo de uptime")

    model_config = {
        "json_schema_extra": {
            "example": {
                "total_requests": 15420,
                "requests_per_second": 12.5,
                "avg_latency_ms": 85.3,
                "error_rate": 0.002,
                "uptime_seconds": 86400.0
            }
        }
    }


__all__ = [
    "HealthStatusEnum",
    "ComponentHealthResponse",
    "HealthBasicResponse",
    "HealthDetailedResponse",
    "ReadinessResponse",
    "LivenessResponse",
    "MetricsSummary",
]
