# admin/perf_context.py
"""
Contexto de performance para acumular metricas durante uma request.

Uso:
    from admin.perf_context import perf_ctx

    # No inicio da request (middleware)
    perf_ctx.start_request(request_id, user_id, route)

    # Durante o processamento
    perf_ctx.add_llm_time(1234.5)
    perf_ctx.add_db_time(56.7)
    perf_ctx.add_json_parse_time(12.3)

    # No final (middleware)
    perf_ctx.finish_request(total_ms, status)
"""

import time
import uuid
import logging
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class PerfMetrics:
    """Metricas acumuladas durante uma request."""
    request_id: str = ""
    user_id: Optional[int] = None
    username: Optional[str] = None
    route: str = ""
    method: str = ""
    action: Optional[str] = None

    # Tempos (ms)
    start_time: float = 0
    total_ms: float = 0
    llm_request_ms: float = 0
    json_parse_ms: float = 0
    db_total_ms: float = 0
    db_query_times: List[float] = field(default_factory=list)

    # Volume
    prompt_tokens: int = 0
    response_tokens: int = 0
    json_size_chars: int = 0

    # Status
    status: str = "ok"
    error_type: Optional[str] = None
    error_message_short: Optional[str] = None

    @property
    def db_slowest_query_ms(self) -> float:
        """Retorna o tempo da query mais lenta."""
        return max(self.db_query_times) if self.db_query_times else 0


# ContextVar para armazenar metricas por request (thread-safe)
_perf_metrics: ContextVar[Optional[PerfMetrics]] = ContextVar('perf_metrics', default=None)


class PerfContext:
    """
    Gerenciador de contexto de performance.

    Acumula metricas durante uma request de forma thread-safe.
    """

    def start_request(
        self,
        route: str,
        method: str = "GET",
        user_id: int = None,
        username: str = None,
        action: str = None
    ) -> str:
        """
        Inicia coleta de metricas para uma request.

        Returns:
            request_id gerado
        """
        request_id = str(uuid.uuid4())[:8]  # ID curto
        metrics = PerfMetrics(
            request_id=request_id,
            user_id=user_id,
            username=username,
            route=route,
            method=method,
            action=action,
            start_time=time.perf_counter()
        )
        _perf_metrics.set(metrics)
        return request_id

    def get_metrics(self) -> Optional[PerfMetrics]:
        """Retorna metricas da request atual."""
        return _perf_metrics.get()

    def set_action(self, action: str):
        """Define a action/label da request."""
        metrics = self.get_metrics()
        if metrics:
            metrics.action = action

    def set_user(self, user_id: int, username: str = None):
        """Define o usuario da request."""
        metrics = self.get_metrics()
        if metrics:
            metrics.user_id = user_id
            metrics.username = username

    # ==========================================
    # Acumuladores de tempo
    # ==========================================

    def add_llm_time(self, ms: float, prompt_tokens: int = 0, response_tokens: int = 0):
        """Adiciona tempo de chamada LLM."""
        metrics = self.get_metrics()
        if metrics:
            metrics.llm_request_ms += ms
            metrics.prompt_tokens += prompt_tokens
            metrics.response_tokens += response_tokens

    def add_db_time(self, ms: float):
        """Adiciona tempo de query no BD."""
        metrics = self.get_metrics()
        if metrics:
            metrics.db_total_ms += ms
            metrics.db_query_times.append(ms)

    def add_json_parse_time(self, ms: float, json_size: int = 0):
        """Adiciona tempo de parse/validacao JSON."""
        metrics = self.get_metrics()
        if metrics:
            metrics.json_parse_ms += ms
            if json_size > 0:
                metrics.json_size_chars = json_size

    def set_json_size(self, size_chars: int):
        """Define tamanho do JSON persistido."""
        metrics = self.get_metrics()
        if metrics:
            metrics.json_size_chars = size_chars

    # ==========================================
    # Status e erros
    # ==========================================

    def set_error(self, error_type: str, message: str = None):
        """
        Marca a request como erro.

        Args:
            error_type: timeout, parse_error, db_error, network_error, llm_error, validation_error
            message: Mensagem curta (sera truncada em 200 chars)
        """
        metrics = self.get_metrics()
        if metrics:
            metrics.status = "error"
            metrics.error_type = error_type
            if message:
                # Trunca e remove dados sensiveis
                clean_msg = str(message)[:200].replace('\n', ' ')
                metrics.error_message_short = clean_msg

    # ==========================================
    # Finalizacao
    # ==========================================

    def finish_request(self, status_code: int = 200) -> Optional[PerfMetrics]:
        """
        Finaliza a coleta e retorna as metricas.

        Args:
            status_code: HTTP status code

        Returns:
            PerfMetrics com todos os dados acumulados
        """
        metrics = self.get_metrics()
        if not metrics:
            return None

        # Calcula tempo total
        metrics.total_ms = (time.perf_counter() - metrics.start_time) * 1000

        # Atualiza status baseado no status code
        if status_code >= 400:
            metrics.status = "error"
            if not metrics.error_type:
                if status_code >= 500:
                    metrics.error_type = "server_error"
                else:
                    metrics.error_type = "client_error"

        # Limpa contexto
        _perf_metrics.set(None)

        return metrics

    def clear(self):
        """Limpa o contexto sem persistir."""
        _perf_metrics.set(None)


# ==========================================
# Context managers para instrumentacao
# ==========================================

class TimeLLM:
    """Context manager para medir tempo de LLM."""

    def __init__(self, prompt_tokens: int = 0):
        self.start = 0
        self.prompt_tokens = prompt_tokens
        self.response_tokens = 0

    def __enter__(self):
        self.start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed_ms = (time.perf_counter() - self.start) * 1000
        perf_ctx.add_llm_time(elapsed_ms, self.prompt_tokens, self.response_tokens)

        if exc_type:
            perf_ctx.set_error("llm_error", str(exc_val)[:100] if exc_val else "LLM error")

        return False  # Nao suprime excecoes


class TimeDB:
    """Context manager para medir tempo de DB."""

    def __init__(self):
        self.start = 0

    def __enter__(self):
        self.start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed_ms = (time.perf_counter() - self.start) * 1000
        perf_ctx.add_db_time(elapsed_ms)

        if exc_type:
            perf_ctx.set_error("db_error", str(exc_val)[:100] if exc_val else "DB error")

        return False


class TimeJSONParse:
    """Context manager para medir tempo de parse JSON."""

    def __init__(self):
        self.start = 0
        self.json_size = 0

    def __enter__(self):
        self.start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed_ms = (time.perf_counter() - self.start) * 1000
        perf_ctx.add_json_parse_time(elapsed_ms, self.json_size)

        if exc_type:
            perf_ctx.set_error("parse_error", str(exc_val)[:100] if exc_val else "Parse error")

        return False


# Instancia global
perf_ctx = PerfContext()
