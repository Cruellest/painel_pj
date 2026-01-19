# admin/middleware_performance.py
"""
Middleware de performance MVP para FastAPI.

Objetivo: identificar gargalos (LLM vs DB vs Parse)
- SEMPRE ativo
- Registra logs de TODOS os usuarios
- Apenas admin VISUALIZA os logs
"""

import time
import logging
from typing import Callable, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from admin.perf_context import perf_ctx
from admin.ia_context import ia_ctx

logger = logging.getLogger(__name__)

# Rotas a ignorar (nao geram logs de performance)
IGNORED_ROUTES = {
    "/favicon.ico",
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/static",
    "/_next",
}

# Rotas que sao endpoints de performance (evita recursao)
PERF_ROUTES = {
    "/admin/performance",
    "/admin/api/performance",
    "/admin/api/gemini-logs",
}


class PerformanceMiddleware(BaseHTTPMiddleware):
    """
    Middleware que mede o tempo total de cada request.

    - SEMPRE ativo (sem toggle)
    - Registra para TODOS os usuarios
    - Usa PerfContext para acumular metricas de LLM, DB, Parse
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        route = str(request.url.path)

        # Ignora rotas que nao devem ser logadas
        if self._should_ignore(route):
            return await call_next(request)

        # Inicia contexto de performance
        user_info = await self._get_user_from_request(request)
        request_id = perf_ctx.start_request(
            route=route,
            method=request.method,
            user_id=user_info.get('id') if user_info else None,
            username=user_info.get('username') if user_info else None
        )

        # Disponibiliza request_id para outras camadas
        request.state.perf_request_id = request_id

        # Inicia contexto de IA (para rastreabilidade de chamadas Gemini)
        ia_ctx.start_request(
            request_id=request_id,
            route=route,
            method=request.method,
            user_id=user_info.get('id') if user_info else None,
            username=user_info.get('username') if user_info else None
        )

        # Processa request
        response = None
        try:
            response = await call_next(request)
            return response
        except Exception as e:
            # Registra erro
            error_type = self._classify_error(e)
            perf_ctx.set_error(error_type, str(e))
            raise
        finally:
            # Finaliza e persiste metricas
            status_code = response.status_code if response else 500
            metrics = perf_ctx.finish_request(status_code)

            # Limpa contexto de IA
            ia_ctx.clear()

            if metrics and metrics.total_ms > 10:  # Loga requests > 10ms
                self._persist_metrics(metrics)

    def _should_ignore(self, route: str) -> bool:
        """Verifica se a rota deve ser ignorada."""
        # Ignora rotas estaticas
        for ignored in IGNORED_ROUTES:
            if route.startswith(ignored):
                return True

        # Ignora rotas de performance (evita recursao)
        for perf in PERF_ROUTES:
            if route.startswith(perf):
                return True

        return False

    def _classify_error(self, error: Exception) -> str:
        """Classifica o tipo de erro."""
        error_str = str(type(error).__name__).lower()

        if 'timeout' in error_str:
            return 'timeout'
        elif 'connection' in error_str or 'network' in error_str:
            return 'network_error'
        elif 'json' in error_str or 'parse' in error_str or 'decode' in error_str:
            return 'parse_error'
        elif 'database' in error_str or 'sql' in error_str or 'integrity' in error_str:
            return 'db_error'
        elif 'validation' in error_str or 'pydantic' in error_str:
            return 'validation_error'
        else:
            return 'unknown_error'

    async def _get_user_from_request(self, request: Request) -> Optional[dict]:
        """Extrai informacoes do usuario do token JWT."""
        try:
            auth_header = request.headers.get("Authorization")
            if not auth_header or not auth_header.startswith("Bearer "):
                token = request.cookies.get("access_token")
                if not token:
                    return None
            else:
                token = auth_header.split(" ")[1]

            from auth.security import decode_token
            payload = decode_token(token)
            if not payload:
                return None

            return {
                "id": payload.get("user_id"),
                "username": payload.get("sub"),
                "role": payload.get("role")
            }
        except Exception:
            return None

    def _persist_metrics(self, metrics):
        """Persiste metricas no banco de dados."""
        try:
            # Ignora requests sem usuario autenticado (admin_user_id é NOT NULL)
            if not metrics.user_id:
                return

            from database.connection import SessionLocal
            from admin.models_performance import PerformanceLog

            db = SessionLocal()
            try:
                log = PerformanceLog(
                    request_id=metrics.request_id,
                    admin_user_id=metrics.user_id,
                    admin_username=metrics.username,
                    route=metrics.route,
                    method=metrics.method,
                    layer='middleware',
                    action=metrics.action,
                    status=metrics.status,
                    duration_ms=metrics.total_ms or 0,  # Campo legado obrigatório
                    total_ms=metrics.total_ms,
                    llm_request_ms=metrics.llm_request_ms if metrics.llm_request_ms > 0 else None,
                    json_parse_ms=metrics.json_parse_ms if metrics.json_parse_ms > 0 else None,
                    db_total_ms=metrics.db_total_ms if metrics.db_total_ms > 0 else None,
                    db_slowest_query_ms=metrics.db_slowest_query_ms if metrics.db_slowest_query_ms > 0 else None,
                    prompt_tokens=metrics.prompt_tokens if metrics.prompt_tokens > 0 else None,
                    response_tokens=metrics.response_tokens if metrics.response_tokens > 0 else None,
                    json_size_chars=metrics.json_size_chars if metrics.json_size_chars > 0 else None,
                    error_type=metrics.error_type,
                    error_message_short=metrics.error_message_short,
                )
                db.add(log)
                db.commit()
            finally:
                db.close()

        except Exception as e:
            # Nao falha a request por erro de logging
            logger.warning(f"[PerfMiddleware] Erro ao persistir metricas: {e}")


def create_performance_middleware():
    """Factory para criar o middleware."""
    return PerformanceMiddleware
