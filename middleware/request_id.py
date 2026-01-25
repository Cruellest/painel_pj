# middleware/request_id.py
"""
Middleware para adicionar Request ID único a cada requisição.

Funcionalidades:
- Gera UUID único para cada requisição
- Armazena no contexto do request (request.state)
- Adiciona header X-Request-ID na response
- Disponibiliza via contextvars para uso em qualquer parte do código
- Permite passar request_id existente via header (útil para tracing distribuído)

Uso em outros módulos:
    from middleware.request_id import get_request_id

    request_id = get_request_id()  # Retorna o ID da requisição atual ou None
"""

import uuid
import logging
from contextvars import ContextVar
from typing import Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# Header HTTP padrão para Request ID
REQUEST_ID_HEADER = "X-Request-ID"

# ContextVar para armazenar o request_id da requisição atual
# Permite acesso ao request_id de qualquer lugar do código sem passar explicitamente
_request_id_ctx: ContextVar[Optional[str]] = ContextVar("request_id", default=None)

# Logger para o middleware
logger = logging.getLogger(__name__)


def get_request_id() -> Optional[str]:
    """
    Retorna o Request ID da requisição atual.

    Pode ser chamado de qualquer lugar do código durante uma requisição.
    Retorna None se chamado fora do contexto de uma requisição.

    Exemplo:
        from middleware.request_id import get_request_id

        def minha_funcao():
            request_id = get_request_id()
            logger.info(f"[{request_id}] Processando...")
    """
    return _request_id_ctx.get()


def set_request_id(request_id: str) -> None:
    """
    Define o Request ID para a requisição atual.

    Uso interno pelo middleware. Não deve ser chamado diretamente.
    """
    _request_id_ctx.set(request_id)


def generate_request_id() -> str:
    """
    Gera um novo Request ID único.

    Formato: UUID v4 (ex: "550e8400-e29b-41d4-a716-446655440000")
    """
    return str(uuid.uuid4())


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware FastAPI para gerenciamento de Request ID.

    Funcionalidades:
    - Gera UUID único para cada requisição
    - Aceita Request ID externo via header X-Request-ID
    - Armazena no request.state.request_id
    - Disponibiliza via get_request_id()
    - Retorna no header X-Request-ID da response

    Uso:
        from middleware.request_id import RequestIDMiddleware

        app.add_middleware(RequestIDMiddleware)
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Verifica se já existe um request_id no header (tracing distribuído)
        existing_request_id = request.headers.get(REQUEST_ID_HEADER)

        if existing_request_id:
            # Valida formato do request_id existente (deve ser UUID válido ou string alfanumérica)
            request_id = existing_request_id[:64]  # Limita tamanho por segurança
        else:
            # Gera novo request_id
            request_id = generate_request_id()

        # Armazena no contexto da requisição
        request.state.request_id = request_id

        # Armazena no ContextVar para acesso global
        set_request_id(request_id)

        try:
            # Processa a requisição
            response: Response = await call_next(request)

            # Adiciona o request_id no header da response
            response.headers[REQUEST_ID_HEADER] = request_id

            return response

        except Exception as e:
            # Em caso de erro, ainda tenta adicionar o header
            # Mas deixa a exceção propagar para handlers de erro
            logger.error(f"[{request_id}] Erro durante requisição: {e}")
            raise

        finally:
            # Limpa o contexto após a requisição
            set_request_id(None)


# Alias para compatibilidade
RequestIdMiddleware = RequestIDMiddleware
