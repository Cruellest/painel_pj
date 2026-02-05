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
from starlette.middleware.base import BaseHTTPMiddleware

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
RATE_LIMIT_EXPORT = os.getenv("RATE_LIMIT_EXPORT", "3/minute")
RATE_LIMIT_HEAVY = os.getenv("RATE_LIMIT_HEAVY", "5/minute")
RATE_LIMIT_UPLOAD = os.getenv("RATE_LIMIT_UPLOAD", "10/minute")

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

async def rate_limit_exceeded_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Handler customizado para rate limit excedido.

    Retorna resposta JSON amigável em português.
    Trata tanto RateLimitExceeded quanto outras exceções.
    """
    # Extrai informações da exceção de forma segura
    exc_detail = getattr(exc, 'detail', str(exc))
    exc_type = type(exc).__name__
    
    logger.warning(
        f"Rate limit exceeded: {get_real_ip(request)} - {request.url.path} - {exc_type}: {exc_detail}"
    )

    # Tenta extrair o tempo de retry de forma segura
    retry_after = "60"
    try:
        if hasattr(exc, 'detail') and exc.detail:
            # Se temos detail, tenta extrair o tempo
            detail_str = str(exc.detail)
            if "per" in detail_str:
                retry_after = detail_str.split("per")[0].strip()
    except Exception as parse_error:
        logger.debug(f"Could not parse retry_after from exception: {parse_error}")

    return JSONResponse(
        status_code=429,
        content={
            "detail": "Limite de requisições excedido. Tente novamente em alguns minutos.",
            "error": "rate_limit_exceeded",
            "retry_after": retry_after
        },
        headers={
            "Retry-After": retry_after,
            "X-RateLimit-Limit": RATE_LIMIT_DEFAULT,
        }
    )


# ==================================================
# MIDDLEWARE CUSTOMIZADO
# ==================================================


class SafeRateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware que intercepta erros do slowapi e trata ValueError corretamente.
    
    Este middleware:
    1. Substitui a função handler padrão do slowapi por uma segura
    2. Captura ValueError e RateLimitExceeded
    3. Retorna respostas JSON amigáveis
    
    IMPORTANTE: Deve ser registrado ANTES de SlowAPIMiddleware (se usado)
    ou SOZINHO sem SlowAPIMiddleware.
    """
    
    async def dispatch(self, request: Request, call_next):
        # Substitui o handler padrão do slowapi no limiter
        # para evitar o erro de AttributeError com ValueError
        original_handler = None
        if hasattr(limiter, '_default_handler'):
            original_handler = limiter._default_handler
        
        # Define um handler seguro
        async def safe_handler(request: Request, exc: Exception):
            exc_detail = getattr(exc, 'detail', str(exc))
            exc_type = type(exc).__name__
            
            logger.warning(
                f"Rate limit {exc_type}: {get_real_ip(request)} - {request.url.path}"
            )
            
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Limite de requisições excedido. Tente novamente em alguns minutos.",
                    "error": "rate_limit_exceeded",
                    "retry_after": "60"
                },
                headers={
                    "Retry-After": "60",
                    "X-RateLimit-Limit": RATE_LIMIT_DEFAULT,
                }
            )
        
        # Tenta usar o handler seguro
        if hasattr(limiter, '_default_handler'):
            limiter._default_handler = safe_handler
        
        try:
            response = await call_next(request)
            return response
        except ValueError as e:
            # Rate limit ValueError - trata com nosso handler
            logger.warning(
                f"Rate limit ValueError caught: {get_real_ip(request)} - {request.url.path} - {str(e)}"
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Limite de requisições excedido. Tente novamente em alguns minutos.",
                    "error": "rate_limit_exceeded",
                    "retry_after": "60"
                },
                headers={
                    "Retry-After": "60",
                    "X-RateLimit-Limit": RATE_LIMIT_DEFAULT,
                }
            )
        except RateLimitExceeded as e:
            # Rate limit exceedido - usa handler customizado
            return await rate_limit_exceeded_handler(request, e)
        finally:
            # Restaura o handler original (se havia)
            if original_handler is not None and hasattr(limiter, '_default_handler'):
                limiter._default_handler = original_handler


# ==================================================
# DECORATORS PRONTOS
# ==================================================

def limit_login(func):
    """Decorator para limitar tentativas de login."""
    return limiter.limit(RATE_LIMIT_LOGIN, key_func=get_user_identifier)(func)


def limit_ai_request(func):
    """Decorator para limitar requisições de IA (por usuário)."""
    return limiter.limit(RATE_LIMIT_AI, key_func=get_user_identifier)(func)


def limit_default(func):
    """Decorator para limite padrão."""
    return limiter.limit(RATE_LIMIT_DEFAULT, key_func=get_user_identifier)(func)


def limit_export(func):
    """Decorator para limitar exportação de documentos (por usuário)."""
    return limiter.limit(RATE_LIMIT_EXPORT, key_func=get_user_identifier)(func)

def limit_heavy(func):
    """Decorator para operações pesadas."""
    return limiter.limit(RATE_LIMIT_HEAVY, key_func=get_user_identifier)(func)

def limit_upload(func):
    """Decorator para uploads de arquivos."""
    return limiter.limit(RATE_LIMIT_UPLOAD, key_func=get_user_identifier)(func)


# ==================================================
# CONSTANTES PARA USO DIRETO
# ==================================================

# Para usar com @limiter.limit() diretamente
LIMITS = {
    "login": RATE_LIMIT_LOGIN,           # 5/minute
    "ai": RATE_LIMIT_AI,                  # 10/minute
    "default": RATE_LIMIT_DEFAULT,        # 100/minute
    "heavy": RATE_LIMIT_HEAVY,                  # Operações pesadas
    "upload": RATE_LIMIT_UPLOAD,                # Upload de arquivos
    "export": RATE_LIMIT_EXPORT,                 # Exportação de documentos
}
