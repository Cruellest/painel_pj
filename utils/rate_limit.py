# utils/rate_limit.py
# -*- coding: utf-8 -*-
"""
Rate Limiting para o Portal PGE-MS

SECURITY: Protege contra ataques de DoS e brute-force.

Limites padrão:
- Geral: 100 requests/minuto por IP
- Login: 5 tentativas/minuto por IP
- APIs de IA: 10 requests/minuto por usuário

Uso:
    from utils.rate_limit import limiter, rate_limit_exceeded_handler

    # No main.py
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    # Nos routers
    @router.post("/endpoint")
    @limiter.limit("10/minute")
    async def endpoint(request: Request):
        ...
"""

import os
import logging
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# ==================================================
# CONFIGURAÇÃO
# ==================================================

# SECURITY: Detecta IP real atrás de proxy/load balancer
def get_real_ip(request: Request) -> str:
    """
    Obtém IP real do cliente, considerando headers de proxy.

    Prioridade:
    1. X-Forwarded-For (primeiro IP da lista)
    2. X-Real-IP
    3. IP direto da conexão
    """
    # Railway e outros proxies usam X-Forwarded-For
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Pega o primeiro IP (cliente original)
        return forwarded_for.split(",")[0].strip()

    # Fallback para X-Real-IP
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    # Fallback para IP direto
    return get_remote_address(request)


# Identificador baseado em usuário autenticado (quando disponível)
def get_user_identifier(request: Request) -> str:
    """
    Obtém identificador do usuário para rate limiting.

    Se autenticado, usa user_id.
    Caso contrário, usa IP.
    """
    # Tenta extrair user_id do token (se presente)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            from auth.security import decode_token
            token = auth_header.replace("Bearer ", "")
            payload = decode_token(token)
            if payload and "user_id" in payload:
                return f"user:{payload['user_id']}"
        except Exception:
            pass

    # Fallback para IP
    return f"ip:{get_real_ip(request)}"


# ==================================================
# LIMITER INSTANCE
# ==================================================

# Configuração via variáveis de ambiente
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
RATE_LIMIT_DEFAULT = os.getenv("RATE_LIMIT_DEFAULT", "100/minute")
RATE_LIMIT_LOGIN = os.getenv("RATE_LIMIT_LOGIN", "5/minute")
RATE_LIMIT_AI = os.getenv("RATE_LIMIT_AI", "10/minute")

# Storage: memória por padrão, Redis em produção
RATE_LIMIT_STORAGE = os.getenv("RATE_LIMIT_STORAGE", "memory://")

limiter = Limiter(
    key_func=get_real_ip,
    default_limits=[RATE_LIMIT_DEFAULT],
    enabled=RATE_LIMIT_ENABLED,
    storage_uri=RATE_LIMIT_STORAGE,
)


# ==================================================
# HANDLERS
# ==================================================

async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """
    Handler customizado para rate limit excedido.

    Retorna resposta JSON amigável em português.
    """
    logger.warning(
        f"Rate limit excedido: {get_real_ip(request)} - {request.url.path} - {exc.detail}"
    )

    return JSONResponse(
        status_code=429,
        content={
            "detail": "Limite de requisições excedido. Tente novamente em alguns minutos.",
            "error": "rate_limit_exceeded",
            "retry_after": str(exc.detail).split("per")[0].strip() if exc.detail else "60 seconds"
        },
        headers={
            "Retry-After": "60",
            "X-RateLimit-Limit": RATE_LIMIT_DEFAULT,
        }
    )


# ==================================================
# DECORATORS PRONTOS
# ==================================================

def limit_login(func):
    """Decorator para limitar tentativas de login."""
    return limiter.limit(RATE_LIMIT_LOGIN)(func)


def limit_ai_request(func):
    """Decorator para limitar requisições de IA (por usuário)."""
    return limiter.limit(RATE_LIMIT_AI, key_func=get_user_identifier)(func)


def limit_default(func):
    """Decorator para limite padrão."""
    return limiter.limit(RATE_LIMIT_DEFAULT)(func)


# ==================================================
# CONSTANTES PARA USO DIRETO
# ==================================================

# Para usar com @limiter.limit() diretamente
LIMITS = {
    "login": RATE_LIMIT_LOGIN,           # 5/minute
    "ai": RATE_LIMIT_AI,                  # 10/minute
    "default": RATE_LIMIT_DEFAULT,        # 100/minute
    "heavy": "5/minute",                  # Operações pesadas
    "upload": "10/minute",                # Upload de arquivos
    "export": "3/minute",                 # Exportação de documentos
}
