# utils/circuit_breaker.py
"""
Implementação do padrão Circuit Breaker para resiliência.

O Circuit Breaker previne cascatas de falhas quando um serviço externo
está indisponível, permitindo recuperação graciosa.

ESTADOS:
- CLOSED: Operação normal, requisições passam
- OPEN: Serviço indisponível, falha imediatamente (fail-fast)
- HALF_OPEN: Testando recuperação, permite uma requisição

FLUXO:
1. CLOSED: Funciona normalmente
2. Após N falhas consecutivas → OPEN
3. OPEN: Rejeita requisições por X segundos (timeout)
4. Após timeout → HALF_OPEN
5. HALF_OPEN: Testa uma requisição
   - Sucesso → CLOSED
   - Falha → OPEN (reinicia timeout)

USO:
    from utils.circuit_breaker import CircuitBreaker, circuit_breaker

    # Criação manual
    cb = CircuitBreaker("gemini-api", failure_threshold=5, recovery_timeout=30)

    async def chamar_api():
        if not cb.allow_request():
            raise CircuitOpenError("Gemini API temporariamente indisponível")
        try:
            result = await api.call()
            cb.record_success()
            return result
        except Exception as e:
            cb.record_failure()
            raise

    # Ou usando decorador
    @circuit_breaker("gemini-api", failure_threshold=5)
    async def chamar_api():
        return await api.call()

Autor: LAB/PGE-MS
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from functools import wraps
from threading import Lock
from typing import Any, Callable, Coroutine, Dict, Optional, Tuple, Type, TypeVar

# Tenta usar logging estruturado
try:
    from utils.logging_config import get_logger
    logger = get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)


T = TypeVar("T")


class CircuitState(str, Enum):
    """Estados do Circuit Breaker."""
    CLOSED = "closed"        # Normal - requisições passam
    OPEN = "open"            # Bloqueado - fail-fast
    HALF_OPEN = "half_open"  # Testando recuperação


class CircuitOpenError(Exception):
    """
    Exceção lançada quando o circuito está aberto.

    Indica que o serviço está temporariamente indisponível
    e a requisição foi rejeitada para evitar sobrecarga.
    """

    def __init__(self, service: str, retry_after: float = None):
        self.service = service
        self.retry_after = retry_after
        message = f"Circuit breaker aberto para '{service}'"
        if retry_after:
            message += f" - retry em {retry_after:.0f}s"
        super().__init__(message)


@dataclass
class CircuitBreakerConfig:
    """
    Configuração do Circuit Breaker.

    Attributes:
        failure_threshold: Falhas consecutivas para abrir circuito (default: 5)
        success_threshold: Sucessos consecutivos para fechar em HALF_OPEN (default: 2)
        recovery_timeout: Segundos para tentar recuperação (default: 30)
        half_open_max_calls: Requisições permitidas em HALF_OPEN (default: 1)
        excluded_exceptions: Exceções que NÃO contam como falha
        include_status_codes: Códigos HTTP que contam como falha (para httpx)
    """
    failure_threshold: int = 5
    success_threshold: int = 2
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 1
    excluded_exceptions: Tuple[Type[Exception], ...] = ()
    include_status_codes: Tuple[int, ...] = (500, 502, 503, 504)


class CircuitBreaker:
    """
    Implementação thread-safe do padrão Circuit Breaker.

    Exemplo:
        cb = CircuitBreaker("api-externa")

        async def chamar():
            if not cb.allow_request():
                raise CircuitOpenError(cb.name, cb.time_until_retry())

            try:
                result = await api.call()
                cb.record_success()
                return result
            except Exception as e:
                cb.record_failure()
                raise
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        success_threshold: int = 2,
        config: CircuitBreakerConfig = None
    ):
        """
        Inicializa o Circuit Breaker.

        Args:
            name: Nome identificador do circuito
            failure_threshold: Falhas para abrir (ou use config)
            recovery_timeout: Timeout de recuperação em segundos (ou use config)
            success_threshold: Sucessos para fechar em HALF_OPEN (ou use config)
            config: Objeto de configuração (sobrescreve parâmetros individuais)
        """
        self.name = name

        if config:
            self._config = config
        else:
            self._config = CircuitBreakerConfig(
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
                success_threshold=success_threshold
            )

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._half_open_calls = 0
        self._lock = Lock()

        # Métricas
        self._total_calls = 0
        self._total_successes = 0
        self._total_failures = 0
        self._total_rejected = 0
        self._state_changes: list = []

    @property
    def state(self) -> CircuitState:
        """Retorna o estado atual do circuito."""
        with self._lock:
            self._check_state_transition()
            return self._state

    @property
    def is_closed(self) -> bool:
        """Retorna True se o circuito está fechado (operação normal)."""
        return self.state == CircuitState.CLOSED

    @property
    def is_open(self) -> bool:
        """Retorna True se o circuito está aberto (bloqueado)."""
        return self.state == CircuitState.OPEN

    def allow_request(self) -> bool:
        """
        Verifica se uma requisição pode ser feita.

        Returns:
            True se a requisição é permitida, False caso contrário
        """
        with self._lock:
            self._check_state_transition()

            if self._state == CircuitState.CLOSED:
                return True

            if self._state == CircuitState.OPEN:
                self._total_rejected += 1
                return False

            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls < self._config.half_open_max_calls:
                    self._half_open_calls += 1
                    return True
                return False

            return False

    def record_success(self):
        """
        Registra uma requisição bem sucedida.

        Em HALF_OPEN: pode fechar o circuito após N sucessos.
        Em CLOSED: reseta contador de falhas.
        """
        with self._lock:
            self._total_calls += 1
            self._total_successes += 1

            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self._config.success_threshold:
                    self._transition_to(CircuitState.CLOSED)
                    logger.info(
                        f"[CircuitBreaker] {self.name}: CLOSED (recuperado)"
                    )
            elif self._state == CircuitState.CLOSED:
                self._failure_count = 0

    def record_failure(self, exception: Exception = None):
        """
        Registra uma falha.

        Em CLOSED: incrementa contador, pode abrir circuito.
        Em HALF_OPEN: reabre circuito imediatamente.

        Args:
            exception: Exceção que causou a falha (opcional, para filtrar)
        """
        # Verifica se é uma exceção excluída
        if exception and self._config.excluded_exceptions:
            if isinstance(exception, self._config.excluded_exceptions):
                logger.debug(
                    f"[CircuitBreaker] {self.name}: Exceção excluída ({type(exception).__name__}), não conta como falha"
                )
                return

        with self._lock:
            self._total_calls += 1
            self._total_failures += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                # Falha em HALF_OPEN - volta para OPEN
                self._transition_to(CircuitState.OPEN)
                logger.warning(
                    f"[CircuitBreaker] {self.name}: OPEN (falha em teste)"
                )

            elif self._state == CircuitState.CLOSED:
                self._failure_count += 1
                if self._failure_count >= self._config.failure_threshold:
                    self._transition_to(CircuitState.OPEN)
                    logger.warning(
                        f"[CircuitBreaker] {self.name}: OPEN "
                        f"(threshold: {self._config.failure_threshold} falhas, count={self._failure_count})"
                    )

    def time_until_retry(self) -> Optional[float]:
        """
        Retorna segundos até próxima tentativa se circuito está aberto.

        Returns:
            Segundos restantes ou None se não está em OPEN
        """
        with self._lock:
            if self._state != CircuitState.OPEN or not self._last_failure_time:
                return None

            elapsed = time.time() - self._last_failure_time
            remaining = self._config.recovery_timeout - elapsed
            return max(0, remaining)

    def reset(self):
        """Força reset do circuito para CLOSED."""
        with self._lock:
            self._transition_to(CircuitState.CLOSED)
            self._failure_count = 0
            self._success_count = 0
            self._last_failure_time = None
            logger.info(
                f"[CircuitBreaker] {self.name}: Reset manual para CLOSED"
            )

    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do Circuit Breaker."""
        with self._lock:
            return {
                "name": self.name,
                "state": self._state.value,
                "failure_count": self._failure_count,
                "success_count": self._success_count,
                "total_calls": self._total_calls,
                "total_successes": self._total_successes,
                "total_failures": self._total_failures,
                "total_rejected": self._total_rejected,
                "config": {
                    "failure_threshold": self._config.failure_threshold,
                    "recovery_timeout": self._config.recovery_timeout,
                    "success_threshold": self._config.success_threshold,
                },
                "time_until_retry": self.time_until_retry(),
                "recent_changes": self._state_changes[-5:],  # Últimas 5 mudanças
            }

    def _check_state_transition(self):
        """
        Verifica se deve fazer transição de estado baseado no tempo.

        Deve ser chamado com lock adquirido.
        """
        if self._state == CircuitState.OPEN and self._last_failure_time:
            elapsed = time.time() - self._last_failure_time
            if elapsed >= self._config.recovery_timeout:
                self._transition_to(CircuitState.HALF_OPEN)
                logger.info(
                    f"[CircuitBreaker] {self.name}: HALF_OPEN (testando recuperação)"
                )

    def _transition_to(self, new_state: CircuitState):
        """
        Transiciona para novo estado.

        Deve ser chamado com lock adquirido.
        """
        old_state = self._state
        self._state = new_state

        # Reset contadores na transição
        if new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._success_count = 0
        elif new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0
            self._success_count = 0
        elif new_state == CircuitState.OPEN:
            self._last_failure_time = time.time()

        # Registra mudança
        self._state_changes.append({
            "from": old_state.value,
            "to": new_state.value,
            "timestamp": datetime.utcnow().isoformat()
        })

        # Mantém histórico limitado
        if len(self._state_changes) > 20:
            self._state_changes = self._state_changes[-20:]


# Registro global de Circuit Breakers
_circuit_breakers: Dict[str, CircuitBreaker] = {}
_registry_lock = Lock()


def get_circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 30.0,
    **kwargs
) -> CircuitBreaker:
    """
    Obtém ou cria um Circuit Breaker pelo nome.

    Circuit Breakers são singletons por nome - chamadas subsequentes
    retornam a mesma instância.

    Args:
        name: Nome único do circuito
        failure_threshold: Falhas para abrir (se criando novo)
        recovery_timeout: Timeout de recuperação (se criando novo)
        **kwargs: Outros parâmetros para CircuitBreaker

    Returns:
        Instância do CircuitBreaker
    """
    with _registry_lock:
        if name not in _circuit_breakers:
            _circuit_breakers[name] = CircuitBreaker(
                name=name,
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
                **kwargs
            )
        return _circuit_breakers[name]


def get_all_circuit_breakers() -> Dict[str, Dict[str, Any]]:
    """Retorna estatísticas de todos os Circuit Breakers registrados."""
    with _registry_lock:
        return {
            name: cb.get_stats()
            for name, cb in _circuit_breakers.items()
        }


def reset_circuit_breaker(name: str) -> bool:
    """
    Reseta um Circuit Breaker específico.

    Args:
        name: Nome do circuito

    Returns:
        True se encontrado e resetado, False se não existe
    """
    with _registry_lock:
        if name in _circuit_breakers:
            _circuit_breakers[name].reset()
            return True
        return False


def circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 30.0,
    success_threshold: int = 2,
    fallback: Callable[..., Any] = None,
    excluded_exceptions: Tuple[Type[Exception], ...] = ()
):
    """
    Decorador que aplica Circuit Breaker a uma função assíncrona.

    Args:
        name: Nome único do circuito
        failure_threshold: Falhas consecutivas para abrir
        recovery_timeout: Segundos antes de testar recuperação
        success_threshold: Sucessos para fechar em HALF_OPEN
        fallback: Função a chamar quando circuito está aberto
        excluded_exceptions: Exceções que não contam como falha

    Returns:
        Decorador configurado

    Exemplo:
        @circuit_breaker("gemini-api", failure_threshold=5, recovery_timeout=30)
        async def chamar_gemini(prompt):
            return await api.generate(prompt)

        # Com fallback
        @circuit_breaker("api-externa", fallback=lambda: {"cached": True})
        async def chamar_api():
            return await api.call()
    """
    config = CircuitBreakerConfig(
        failure_threshold=failure_threshold,
        recovery_timeout=recovery_timeout,
        success_threshold=success_threshold,
        excluded_exceptions=excluded_exceptions
    )

    def decorator(func: Callable[..., Coroutine[Any, Any, T]]) -> Callable[..., Coroutine[Any, Any, T]]:
        # Obtém ou cria o Circuit Breaker
        cb = get_circuit_breaker(name, config=config)

        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            if not cb.allow_request():
                retry_after = cb.time_until_retry()

                if fallback:
                    logger.info(
                        f"[CircuitBreaker] {name}: Usando fallback (circuito aberto)"
                    )
                    result = fallback(*args, **kwargs)
                    if asyncio.iscoroutine(result):
                        return await result
                    return result

                raise CircuitOpenError(name, retry_after)

            try:
                result = await func(*args, **kwargs)
                cb.record_success()
                return result

            except excluded_exceptions:
                # Exceções excluídas não contam como falha
                raise

            except Exception as e:
                cb.record_failure(e)
                raise

        return wrapper
    return decorator


# Circuit Breakers pré-configurados para serviços comuns
def get_gemini_circuit_breaker() -> CircuitBreaker:
    """Retorna Circuit Breaker configurado para Gemini API."""
    return get_circuit_breaker(
        "gemini-api",
        failure_threshold=5,
        recovery_timeout=30.0,
        success_threshold=2
    )


def get_tjms_circuit_breaker() -> CircuitBreaker:
    """Retorna Circuit Breaker configurado para TJ-MS."""
    return get_circuit_breaker(
        "tjms-api",
        failure_threshold=3,
        recovery_timeout=60.0,  # TJ-MS pode demorar mais para recuperar
        success_threshold=1
    )


__all__ = [
    # Classes
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitState",
    "CircuitOpenError",
    # Decorador
    "circuit_breaker",
    # Funções de registro
    "get_circuit_breaker",
    "get_all_circuit_breakers",
    "reset_circuit_breaker",
    # Instâncias pré-configuradas
    "get_gemini_circuit_breaker",
    "get_tjms_circuit_breaker",
]
