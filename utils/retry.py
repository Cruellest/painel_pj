# utils/retry.py
"""
Utilitário de retry com backoff exponencial.

Fornece decoradores e funções para retry de operações que podem falhar
transitoriamente (conexões de rede, APIs externas, etc.).

USO:
    from utils.retry import retry_async, RetryConfig

    # Decorador simples
    @retry_async(max_retries=3, base_delay=1.0)
    async def chamar_api():
        response = await httpx.get("https://api.example.com")
        return response.json()

    # Configuração customizada
    config = RetryConfig(
        max_retries=5,
        base_delay=0.5,
        max_delay=30.0,
        exponential_base=2,
        retryable_exceptions=(httpx.TimeoutException, httpx.ConnectError)
    )

    @retry_async(config=config)
    async def operacao_critica():
        ...

Autor: LAB/PGE-MS
"""

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from functools import wraps
from typing import (
    Any,
    Callable,
    Coroutine,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
)

# Tenta usar logging estruturado
try:
    from utils.logging_config import get_logger
    logger = get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)


T = TypeVar("T")


@dataclass
class RetryConfig:
    """
    Configuração para retry com backoff exponencial.

    Attributes:
        max_retries: Número máximo de tentativas (default: 3)
        base_delay: Delay inicial em segundos (default: 1.0)
        max_delay: Delay máximo em segundos (default: 30.0)
        exponential_base: Base para cálculo exponencial (default: 2)
        jitter: Se True, adiciona variação aleatória ao delay (default: True)
        jitter_factor: Fator de variação (0-1, default: 0.25)
        retryable_exceptions: Tupla de exceções que disparam retry
        retryable_status_codes: Códigos HTTP que disparam retry (para httpx)
        on_retry: Callback chamado antes de cada retry
        logger_name: Nome do logger para mensagens (default: usa __name__)
    """
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    exponential_base: int = 2
    jitter: bool = True
    jitter_factor: float = 0.25
    retryable_exceptions: Tuple[Type[Exception], ...] = field(
        default_factory=lambda: (
            ConnectionError,
            TimeoutError,
            asyncio.TimeoutError,
        )
    )
    retryable_status_codes: Tuple[int, ...] = (429, 500, 502, 503, 504)
    on_retry: Optional[Callable[[int, Exception, float], None]] = None
    logger_name: Optional[str] = None

    def calculate_delay(self, attempt: int) -> float:
        """
        Calcula o delay para uma tentativa específica.

        Args:
            attempt: Número da tentativa (0-indexed)

        Returns:
            Delay em segundos
        """
        # Exponential backoff
        delay = min(
            self.base_delay * (self.exponential_base ** attempt),
            self.max_delay
        )

        # Adiciona jitter para evitar thundering herd
        if self.jitter:
            jitter_range = delay * self.jitter_factor
            delay = delay + random.uniform(-jitter_range, jitter_range)
            delay = max(0.1, delay)  # Mínimo de 100ms

        return delay


# Configurações pré-definidas para casos comuns
RETRY_CONFIG_API_EXTERNAL = RetryConfig(
    max_retries=3,
    base_delay=1.0,
    max_delay=10.0,
    jitter=True,
)

RETRY_CONFIG_DATABASE = RetryConfig(
    max_retries=2,
    base_delay=0.5,
    max_delay=5.0,
    jitter=False,
)

RETRY_CONFIG_CRITICAL = RetryConfig(
    max_retries=5,
    base_delay=2.0,
    max_delay=60.0,
    jitter=True,
)

# Configuração específica para TJ-MS SOAP
# O TJ-MS frequentemente retorna 5xx em momentos de alta carga
RETRY_CONFIG_TJMS = RetryConfig(
    max_retries=3,
    base_delay=2.0,
    max_delay=30.0,
    exponential_base=2,
    jitter=True,
    jitter_factor=0.3,  # Maior variação para evitar thundering herd
    retryable_exceptions=(
        ConnectionError,
        TimeoutError,
        asyncio.TimeoutError,
    ),
    retryable_status_codes=(429, 500, 502, 503, 504),
)


def retry_async(
    max_retries: int = None,
    base_delay: float = None,
    max_delay: float = None,
    retryable_exceptions: Tuple[Type[Exception], ...] = None,
    config: RetryConfig = None,
    log_retries: bool = True
):
    """
    Decorador para retry assíncrono com backoff exponencial.

    Pode ser usado de duas formas:

    1. Com parâmetros individuais:
        @retry_async(max_retries=3, base_delay=1.0)
        async def funcao():
            ...

    2. Com objeto de configuração:
        @retry_async(config=RetryConfig(...))
        async def funcao():
            ...

    Args:
        max_retries: Número máximo de tentativas
        base_delay: Delay inicial em segundos
        max_delay: Delay máximo em segundos
        retryable_exceptions: Exceções que disparam retry
        config: Objeto RetryConfig com todas as configurações
        log_retries: Se True, loga cada retry (default: True)

    Returns:
        Decorador configurado
    """
    def decorator(func: Callable[..., Coroutine[Any, Any, T]]) -> Callable[..., Coroutine[Any, Any, T]]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            # Monta configuração final
            cfg = config or RetryConfig()

            # Override com parâmetros individuais se fornecidos
            if max_retries is not None:
                cfg.max_retries = max_retries
            if base_delay is not None:
                cfg.base_delay = base_delay
            if max_delay is not None:
                cfg.max_delay = max_delay
            if retryable_exceptions is not None:
                cfg.retryable_exceptions = retryable_exceptions

            last_exception: Optional[Exception] = None
            func_name = func.__name__

            for attempt in range(cfg.max_retries):
                try:
                    return await func(*args, **kwargs)

                except cfg.retryable_exceptions as e:
                    last_exception = e
                    is_last_attempt = attempt >= cfg.max_retries - 1

                    if is_last_attempt:
                        if log_retries:
                            logger.error(
                                f"[Retry] {func_name}: Falhou após {cfg.max_retries} tentativas "
                                f"(attempt={attempt + 1}, error={str(e)[:100]}, error_type={type(e).__name__})"
                            )
                        raise

                    delay = cfg.calculate_delay(attempt)

                    if log_retries:
                        logger.warning(
                            f"[Retry] {func_name}: Tentativa {attempt + 1}/{cfg.max_retries} "
                            f"falhou ({type(e).__name__}), retry em {delay:.1f}s"
                        )

                    # Callback de retry
                    if cfg.on_retry:
                        try:
                            cfg.on_retry(attempt, e, delay)
                        except Exception:
                            pass  # Ignora erros no callback

                    await asyncio.sleep(delay)

                except Exception as e:
                    # Exceção não retryable - propaga imediatamente
                    if log_retries:
                        logger.debug(
                            f"[Retry] {func_name}: Exceção não retryable: {type(e).__name__}"
                        )
                    raise

            # Não deveria chegar aqui, mas por segurança
            if last_exception:
                raise last_exception
            raise RuntimeError(f"Retry loop terminou inesperadamente para {func_name}")

        return wrapper
    return decorator


async def retry_operation(
    operation: Callable[..., Coroutine[Any, Any, T]],
    *args,
    config: RetryConfig = None,
    **kwargs
) -> T:
    """
    Executa uma operação assíncrona com retry.

    Alternativa ao decorador para casos onde não se pode usar decorador.

    Args:
        operation: Função assíncrona a executar
        *args: Argumentos posicionais para a função
        config: Configuração de retry (usa default se não fornecido)
        **kwargs: Argumentos nomeados para a função

    Returns:
        Resultado da operação

    Raises:
        Última exceção se todas as tentativas falharem

    Exemplo:
        result = await retry_operation(
            api.fetch_data,
            url,
            timeout=30,
            config=RetryConfig(max_retries=3)
        )
    """
    cfg = config or RetryConfig()

    @retry_async(config=cfg)
    async def wrapped():
        return await operation(*args, **kwargs)

    return await wrapped()


class RetryContext:
    """
    Context manager para retry com estado.

    Útil quando precisa de controle mais granular sobre o retry.

    Exemplo:
        async with RetryContext(max_retries=3) as retry:
            while retry.should_retry:
                try:
                    result = await api.call()
                    break
                except ConnectionError as e:
                    await retry.handle_error(e)
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        retryable_exceptions: Tuple[Type[Exception], ...] = None
    ):
        self.config = RetryConfig(
            max_retries=max_retries,
            base_delay=base_delay,
            max_delay=max_delay,
            retryable_exceptions=retryable_exceptions or (Exception,)
        )
        self.attempt = 0
        self.last_error: Optional[Exception] = None
        self._exhausted = False

    @property
    def should_retry(self) -> bool:
        """Retorna True se ainda pode tentar novamente."""
        return self.attempt < self.config.max_retries and not self._exhausted

    @property
    def is_exhausted(self) -> bool:
        """Retorna True se todas as tentativas foram usadas."""
        return self._exhausted

    async def handle_error(self, error: Exception) -> bool:
        """
        Processa um erro e aguarda antes do próximo retry.

        Args:
            error: Exceção que ocorreu

        Returns:
            True se vai tentar novamente, False se esgotou tentativas
        """
        self.last_error = error
        self.attempt += 1

        if not isinstance(error, self.config.retryable_exceptions):
            # Erro não retryable
            self._exhausted = True
            raise error

        if self.attempt >= self.config.max_retries:
            self._exhausted = True
            return False

        delay = self.config.calculate_delay(self.attempt - 1)
        logger.warning(
            f"[RetryContext] Tentativa {self.attempt}/{self.config.max_retries} "
            f"falhou, retry em {delay:.1f}s: {type(error).__name__}"
        )
        await asyncio.sleep(delay)
        return True

    def mark_success(self):
        """Marca operação como bem sucedida (para encerrar loop)."""
        self._exhausted = True

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False  # Não suprime exceções


# Métricas de retry (para observabilidade)
@dataclass
class RetryMetrics:
    """Métricas de operações com retry."""
    operation: str
    attempts: int
    total_delay_ms: float
    success: bool
    final_error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "operation": self.operation,
            "attempts": self.attempts,
            "total_delay_ms": round(self.total_delay_ms, 2),
            "success": self.success,
            "error": self.final_error
        }


async def retry_with_metrics(
    operation: Callable[..., Coroutine[Any, Any, T]],
    operation_name: str,
    *args,
    config: RetryConfig = None,
    **kwargs
) -> Tuple[T, RetryMetrics]:
    """
    Executa operação com retry e retorna métricas.

    Args:
        operation: Função assíncrona a executar
        operation_name: Nome da operação (para logs e métricas)
        *args: Argumentos posicionais
        config: Configuração de retry
        **kwargs: Argumentos nomeados

    Returns:
        Tuple[resultado, métricas]

    Raises:
        Última exceção se todas as tentativas falharem
    """
    cfg = config or RetryConfig()
    t_start = time.perf_counter()
    last_error: Optional[Exception] = None
    attempt = 0

    for attempt in range(cfg.max_retries):
        try:
            result = await operation(*args, **kwargs)
            metrics = RetryMetrics(
                operation=operation_name,
                attempts=attempt + 1,
                total_delay_ms=(time.perf_counter() - t_start) * 1000,
                success=True
            )
            return result, metrics

        except cfg.retryable_exceptions as e:
            last_error = e

            if attempt < cfg.max_retries - 1:
                delay = cfg.calculate_delay(attempt)
                logger.warning(
                    f"[Retry] {operation_name}: Tentativa {attempt + 1}/{cfg.max_retries}, "
                    f"retry em {delay:.1f}s"
                )
                await asyncio.sleep(delay)

    # Todas as tentativas falharam
    metrics = RetryMetrics(
        operation=operation_name,
        attempts=attempt + 1,
        total_delay_ms=(time.perf_counter() - t_start) * 1000,
        success=False,
        final_error=str(last_error)[:200] if last_error else None
    )

    if last_error:
        raise last_error

    return None, metrics


__all__ = [
    # Configuração
    "RetryConfig",
    "RETRY_CONFIG_API_EXTERNAL",
    "RETRY_CONFIG_DATABASE",
    "RETRY_CONFIG_CRITICAL",
    "RETRY_CONFIG_TJMS",
    # Decorador
    "retry_async",
    # Funções
    "retry_operation",
    "retry_with_metrics",
    # Context Manager
    "RetryContext",
    # Métricas
    "RetryMetrics",
]
