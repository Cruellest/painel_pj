# utils/timeouts.py
"""
Configuração centralizada de timeouts para integrações externas.

Define timeouts padrão para diferentes tipos de operações,
garantindo consistência e facilitando ajustes globais.

USO:
    from utils.timeouts import Timeouts, get_timeout

    # Usar constantes diretamente
    timeout = Timeouts.HTTP_DEFAULT

    # Ou via função (permite override por env var)
    timeout = get_timeout("gemini_api")

VARIÁVEIS DE AMBIENTE:
    TIMEOUT_HTTP_DEFAULT=30
    TIMEOUT_HTTP_CONNECT=10
    TIMEOUT_GEMINI_API=120
    TIMEOUT_TJMS_SOAP=60
    TIMEOUT_TJMS_DOWNLOAD=180
    TIMEOUT_OPENROUTER=60

Autor: LAB/PGE-MS
"""

import os
from dataclasses import dataclass
from typing import Optional, Union
import httpx


@dataclass(frozen=True)
class Timeouts:
    """
    Timeouts padrão para diferentes tipos de operações.

    Valores em segundos.
    """

    # HTTP genérico
    HTTP_DEFAULT: float = 30.0          # Request HTTP genérico
    HTTP_CONNECT: float = 10.0          # Tempo para estabelecer conexão
    HTTP_READ: float = 30.0             # Tempo para ler resposta

    # Gemini API
    GEMINI_API: float = 120.0           # Chamada ao Gemini (pode demorar para modelos grandes)
    GEMINI_STREAMING: float = 300.0     # Streaming (total, incluindo geração)

    # TJ-MS
    TJMS_SOAP: float = 60.0             # Consulta SOAP padrão
    TJMS_DOWNLOAD: float = 180.0        # Download de documentos (pode ser grande)
    TJMS_SUBCONTA: float = 180.0        # Extração de subconta (Playwright)

    # OpenRouter
    OPENROUTER: float = 60.0            # Chamada ao OpenRouter

    # Database
    DATABASE_QUERY: float = 30.0        # Query ao banco
    DATABASE_CONNECT: float = 10.0      # Conexão ao banco

    # Outros serviços
    EXTERNAL_API: float = 30.0          # API externa genérica
    INTERNAL_SERVICE: float = 10.0      # Serviço interno


def get_timeout(
    operation: str,
    default: Optional[float] = None,
    as_httpx: bool = False
) -> Union[float, httpx.Timeout]:
    """
    Obtém timeout para uma operação, com suporte a override via env var.

    Args:
        operation: Nome da operação (ex: "gemini_api", "tjms_soap")
        default: Valor padrão se não encontrado
        as_httpx: Se True, retorna httpx.Timeout ao invés de float

    Returns:
        Timeout em segundos ou httpx.Timeout

    Example:
        # Timeout simples
        timeout = get_timeout("gemini_api")  # 120.0

        # Com override via TIMEOUT_GEMINI_API=180
        timeout = get_timeout("gemini_api")  # 180.0

        # Como httpx.Timeout
        timeout = get_timeout("tjms_soap", as_httpx=True)
        # httpx.Timeout(60.0, connect=10.0)
    """
    # Mapeamento de operações para constantes
    defaults_map = {
        "http_default": Timeouts.HTTP_DEFAULT,
        "http_connect": Timeouts.HTTP_CONNECT,
        "http_read": Timeouts.HTTP_READ,
        "gemini_api": Timeouts.GEMINI_API,
        "gemini_streaming": Timeouts.GEMINI_STREAMING,
        "tjms_soap": Timeouts.TJMS_SOAP,
        "tjms_download": Timeouts.TJMS_DOWNLOAD,
        "tjms_subconta": Timeouts.TJMS_SUBCONTA,
        "openrouter": Timeouts.OPENROUTER,
        "database_query": Timeouts.DATABASE_QUERY,
        "database_connect": Timeouts.DATABASE_CONNECT,
        "external_api": Timeouts.EXTERNAL_API,
        "internal_service": Timeouts.INTERNAL_SERVICE,
    }

    # Busca valor padrão
    operation_lower = operation.lower().replace("-", "_")
    timeout_default = defaults_map.get(operation_lower, default or Timeouts.HTTP_DEFAULT)

    # Verifica override via env var (TIMEOUT_GEMINI_API, etc.)
    env_var = f"TIMEOUT_{operation_lower.upper()}"
    env_value = os.getenv(env_var)

    if env_value:
        try:
            timeout_default = float(env_value)
        except ValueError:
            pass  # Mantém o default se env var for inválida

    if as_httpx:
        # Retorna httpx.Timeout com connect separado
        connect_timeout = get_timeout("http_connect")
        return httpx.Timeout(timeout_default, connect=connect_timeout)

    return timeout_default


def get_httpx_timeout(
    total: Optional[float] = None,
    connect: Optional[float] = None,
    read: Optional[float] = None,
    write: Optional[float] = None
) -> httpx.Timeout:
    """
    Cria um httpx.Timeout com valores padrão sensatos.

    Args:
        total: Timeout total (default: HTTP_DEFAULT)
        connect: Timeout de conexão (default: HTTP_CONNECT)
        read: Timeout de leitura (default: igual a total)
        write: Timeout de escrita (default: igual a total)

    Returns:
        httpx.Timeout configurado
    """
    return httpx.Timeout(
        timeout=total or Timeouts.HTTP_DEFAULT,
        connect=connect or Timeouts.HTTP_CONNECT,
        read=read,
        write=write
    )


def get_aiohttp_timeout(total: Optional[float] = None):
    """
    Cria um aiohttp.ClientTimeout com valores padrão.

    Args:
        total: Timeout total (default: HTTP_DEFAULT)

    Returns:
        aiohttp.ClientTimeout configurado

    Note:
        Importa aiohttp apenas quando necessário para evitar
        dependência obrigatória.
    """
    import aiohttp
    return aiohttp.ClientTimeout(
        total=total or Timeouts.HTTP_DEFAULT,
        connect=Timeouts.HTTP_CONNECT
    )


# ============================================
# DECORATORS PARA TIMEOUT
# ============================================

def with_timeout(seconds: float = Timeouts.HTTP_DEFAULT):
    """
    Decorator para adicionar timeout a funções async.

    Args:
        seconds: Timeout em segundos

    Example:
        @with_timeout(30)
        async def fetch_data():
            ...

    Raises:
        asyncio.TimeoutError: Se a operação exceder o timeout
    """
    import asyncio
    import functools

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            return await asyncio.wait_for(
                func(*args, **kwargs),
                timeout=seconds
            )
        return wrapper
    return decorator


# ============================================
# EXPORTS
# ============================================

__all__ = [
    "Timeouts",
    "get_timeout",
    "get_httpx_timeout",
    "get_aiohttp_timeout",
    "with_timeout",
]
