# utils/logging_config.py
"""
Configuração centralizada de logging estruturado com structlog.

BENEFÍCIOS:
- Logs em formato JSON (parseable por ferramentas de observabilidade)
- Request ID automático em todos os logs
- Contexto adicional (usuário, endpoint, etc.)
- Timestamps consistentes em UTC
- Níveis de log configuráveis por módulo

USO:
    from utils.logging_config import get_logger

    logger = get_logger(__name__)
    logger.info("Operação concluída", user_id=123, action="upload")

    # O request_id é adicionado automaticamente se disponível

Autor: LAB/PGE-MS
"""

import logging
import sys
from typing import Optional
from functools import lru_cache

from config import IS_PRODUCTION

# Tenta importar structlog, fallback para logging padrão se não disponível
try:
    import structlog
    from structlog.typing import EventDict
    STRUCTLOG_AVAILABLE = True
except ImportError:
    STRUCTLOG_AVAILABLE = False


def add_request_id(logger, method_name: str, event_dict: dict) -> dict:
    """
    Processador structlog que adiciona request_id automaticamente.

    Obtém o request_id do ContextVar definido no middleware.
    """
    try:
        from middleware.request_id import get_request_id
        request_id = get_request_id()
        if request_id:
            event_dict["request_id"] = request_id
    except ImportError:
        pass
    return event_dict


def add_service_info(logger, method_name: str, event_dict: dict) -> dict:
    """
    Adiciona informações do serviço ao log.
    """
    event_dict["service"] = "portal-pge"
    return event_dict


def configure_structlog():
    """
    Configura structlog para logging estruturado.

    Em produção: JSON formatado para parsing por ferramentas
    Em desenvolvimento: Console colorido legível
    """
    if not STRUCTLOG_AVAILABLE:
        return

    # Processadores comuns
    shared_processors = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
        add_request_id,
        add_service_info,
    ]

    if IS_PRODUCTION:
        # Produção: JSON para ferramentas de observabilidade
        processors = shared_processors + [
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(ensure_ascii=False)
        ]
    else:
        # Desenvolvimento: Console colorido legível
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True)
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def configure_stdlib_logging():
    """
    Configura logging padrão do Python para integração com structlog.
    """
    # Nível base
    root_level = logging.INFO if IS_PRODUCTION else logging.DEBUG

    # Handler para stdout
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(root_level)

    if STRUCTLOG_AVAILABLE and IS_PRODUCTION:
        # Em produção com structlog: usa processador JSON
        handler.setFormatter(structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer(ensure_ascii=False),
            foreign_pre_chain=[
                structlog.stdlib.add_log_level,
                structlog.processors.TimeStamper(fmt="iso", utc=True),
                add_request_id,
            ],
        ))
    else:
        # Desenvolvimento ou sem structlog: formato legível
        handler.setFormatter(logging.Formatter(
            "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))

    # Configura root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(root_level)
    root_logger.handlers = [handler]

    # Silencia loggers verbosos
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


def setup_logging():
    """
    Função principal de configuração de logging.

    Chame esta função no início da aplicação (em main.py lifespan).
    """
    configure_stdlib_logging()
    configure_structlog()


@lru_cache(maxsize=128)
def get_logger(name: str):
    """
    Obtém um logger configurado.

    Args:
        name: Nome do módulo (use __name__)

    Returns:
        Logger structlog ou stdlib dependendo da disponibilidade

    Uso:
        logger = get_logger(__name__)
        logger.info("mensagem", chave="valor")
    """
    if STRUCTLOG_AVAILABLE:
        return structlog.get_logger(name)
    else:
        return logging.getLogger(name)


class LoggerAdapter:
    """
    Adapter que provê interface consistente independente do backend.

    Permite migração gradual para structlog.
    """

    def __init__(self, name: str):
        self.name = name
        self._logger = get_logger(name)

    def _log_with_context(self, level: str, message: str, **kwargs):
        """Loga com contexto adicional."""
        # Adiciona request_id se disponível
        try:
            from middleware.request_id import get_request_id
            request_id = get_request_id()
            if request_id and 'request_id' not in kwargs:
                kwargs['request_id'] = request_id
        except ImportError:
            pass

        if STRUCTLOG_AVAILABLE:
            getattr(self._logger, level)(message, **kwargs)
        else:
            # Fallback: formata kwargs no message
            if kwargs:
                extra = " ".join(f"{k}={v}" for k, v in kwargs.items())
                message = f"{message} | {extra}"
            getattr(self._logger, level)(message)

    def debug(self, message: str, **kwargs):
        self._log_with_context("debug", message, **kwargs)

    def info(self, message: str, **kwargs):
        self._log_with_context("info", message, **kwargs)

    def warning(self, message: str, **kwargs):
        self._log_with_context("warning", message, **kwargs)

    def error(self, message: str, **kwargs):
        self._log_with_context("error", message, **kwargs)

    def critical(self, message: str, **kwargs):
        self._log_with_context("critical", message, **kwargs)

    def exception(self, message: str, **kwargs):
        """Loga exceção com stack trace."""
        if STRUCTLOG_AVAILABLE:
            self._logger.exception(message, **kwargs)
        else:
            self._logger.exception(message)


def create_logger(name: str) -> LoggerAdapter:
    """
    Cria um logger com interface consistente.

    Alternativa a get_logger() que garante interface uniforme.

    Args:
        name: Nome do módulo (use __name__)

    Returns:
        LoggerAdapter com métodos padronizados
    """
    return LoggerAdapter(name)


# Inicializa logging na importação se structlog estiver disponível
if STRUCTLOG_AVAILABLE:
    configure_structlog()


__all__ = [
    "setup_logging",
    "get_logger",
    "create_logger",
    "LoggerAdapter",
    "STRUCTLOG_AVAILABLE",
]
