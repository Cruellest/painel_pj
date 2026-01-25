# middleware/metrics.py
"""
Middleware para coleta de métricas de requests HTTP.

Integra com o sistema de métricas em utils/metrics.py para
coletar automaticamente:
- Contagem de requests por endpoint
- Latência (histograma)
- Erros por tipo

Autor: LAB/PGE-MS
"""

import time
import logging
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from utils.metrics import get_metrics

logger = logging.getLogger(__name__)

# Rotas a ignorar na coleta de métricas
IGNORED_ROUTES = {
    "/favicon.ico",
    "/metrics",
    "/health",
    "/health/live",
    "/health/ready",
    "/health/detailed",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/static",
}


class MetricsMiddleware(BaseHTTPMiddleware):
    """
    Middleware que coleta métricas de cada request.

    Métricas coletadas:
    - Contagem por método/path/status
    - Latência em segundos
    - Tipo de erro (se houver)
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = str(request.url.path)

        # Ignora rotas que não devem gerar métricas
        if self._should_ignore(path):
            return await call_next(request)

        metrics = get_metrics()

        # Registra início do request
        metrics.start_request()
        start_time = time.perf_counter()

        error_type = None
        status_code = 500  # Default para erros não tratados

        try:
            response = await call_next(request)
            status_code = response.status_code
            return response

        except Exception as e:
            error_type = self._classify_error(e)
            raise

        finally:
            # Registra fim do request
            duration = time.perf_counter() - start_time
            metrics.end_request()

            # Registra métricas
            metrics.record_request(
                method=request.method,
                path=path,
                status_code=status_code,
                duration_seconds=duration,
                error_type=error_type
            )

    def _should_ignore(self, path: str) -> bool:
        """Verifica se a rota deve ser ignorada."""
        for ignored in IGNORED_ROUTES:
            if path.startswith(ignored):
                return True
        return False

    def _classify_error(self, error: Exception) -> str:
        """Classifica o tipo de erro."""
        error_name = type(error).__name__.lower()

        if 'timeout' in error_name:
            return 'timeout'
        elif 'connection' in error_name or 'network' in error_name:
            return 'network_error'
        elif 'json' in error_name or 'parse' in error_name or 'decode' in error_name:
            return 'parse_error'
        elif 'database' in error_name or 'sql' in error_name or 'integrity' in error_name:
            return 'db_error'
        elif 'validation' in error_name or 'pydantic' in error_name:
            return 'validation_error'
        elif 'http' in error_name:
            return 'http_error'
        else:
            return f'error_{type(error).__name__}'


def create_metrics_middleware():
    """Factory para criar o middleware de métricas."""
    return MetricsMiddleware
