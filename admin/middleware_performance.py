# admin/middleware_performance.py
"""
Middleware de performance para FastAPI.

Mede tempo total de cada request e registra logs
apenas para usuários admin quando o toggle está ativado.
"""

import time
import uuid
import logging
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from admin.services_performance import (
    is_performance_logging_enabled,
    get_enabled_admin_id,
    log_performance
)

logger = logging.getLogger(__name__)


class PerformanceMiddleware(BaseHTTPMiddleware):
    """
    Middleware que mede o tempo total de cada request.

    Apenas registra logs quando:
    1. Toggle de performance está ativado
    2. Usuário é admin
    3. É o admin que ativou os logs

    O middleware adiciona contexto ao request.state para que
    outras camadas possam registrar suas métricas.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Início do timing
        start_time = time.perf_counter()
        request_id = str(uuid.uuid4())[:8]  # ID curto para agrupar logs

        # Inicializa contexto de performance no request
        request.state.perf_context = None
        request.state.perf_request_id = request_id

        # Verifica se deve coletar métricas (verificação rápida)
        should_log = False
        admin_user_id = None
        admin_username = None

        if is_performance_logging_enabled():
            # Tenta identificar o usuário do token JWT
            try:
                admin_info = await self._get_admin_from_request(request)
                if admin_info:
                    admin_user_id = admin_info.get('id')
                    admin_username = admin_info.get('username')

                    # Verifica se é o admin que ativou os logs
                    enabled_admin = get_enabled_admin_id()
                    if enabled_admin and admin_user_id == enabled_admin:
                        should_log = True

                        # Configura contexto para outras camadas
                        request.state.perf_context = {
                            'admin_user_id': admin_user_id,
                            'admin_username': admin_username,
                            'request_id': request_id,
                            'method': request.method,
                            'route': str(request.url.path)
                        }
            except Exception as e:
                logger.debug(f"Erro ao verificar admin para performance: {e}")

        # Processa request
        response = await call_next(request)

        # Fim do timing
        duration_ms = (time.perf_counter() - start_time) * 1000

        # Registra log se necessário
        if should_log and admin_user_id:
            log_performance(
                admin_user_id=admin_user_id,
                admin_username=admin_username,
                request_id=request_id,
                method=request.method,
                route=str(request.url.path),
                layer="middleware",
                action="request_total",
                duration_ms=duration_ms,
                status_code=response.status_code
            )

        return response

    async def _get_admin_from_request(self, request: Request) -> dict:
        """
        Extrai informações do admin do token JWT.

        Retorna None se não for admin ou não tiver token válido.
        """
        try:
            # Tenta pegar o header Authorization
            auth_header = request.headers.get("Authorization")
            if not auth_header or not auth_header.startswith("Bearer "):
                # Tenta pegar do cookie
                token = request.cookies.get("access_token")
                if not token:
                    return None
            else:
                token = auth_header.split(" ")[1]

            # Decodifica o token
            from auth.security import decode_token
            payload = decode_token(token)
            if not payload:
                return None

            # Verifica se é admin
            role = payload.get("role")
            if role != "admin":
                return None

            return {
                "id": payload.get("user_id"),
                "username": payload.get("sub")
            }

        except Exception:
            return None


def create_performance_middleware():
    """Factory para criar o middleware."""
    return PerformanceMiddleware
