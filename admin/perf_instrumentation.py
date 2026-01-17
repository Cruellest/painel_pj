# admin/perf_instrumentation.py
"""
Instrumentação automática para coleta de métricas de performance.

Este módulo configura listeners automáticos para:
- Queries de banco de dados (SQLAlchemy)
- Parse de JSON
- Chamadas LLM (via integração com gemini_service)

Uso:
    from admin.perf_instrumentation import setup_instrumentation
    setup_instrumentation(app)  # No main.py
"""

import json
import time
import logging
import functools
from typing import Any, Callable
from contextlib import contextmanager

from sqlalchemy import event
from sqlalchemy.engine import Engine

from admin.perf_context import perf_ctx

logger = logging.getLogger(__name__)

# Flag para evitar múltiplas configurações
_instrumentation_configured = False


# ==================================================
# INSTRUMENTAÇÃO DE BANCO DE DADOS (SQLAlchemy)
# ==================================================

def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    """Callback antes de executar query - marca tempo inicial."""
    conn.info.setdefault('query_start_time', []).append(time.perf_counter())


def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    """Callback após executar query - calcula tempo e registra."""
    start_times = conn.info.get('query_start_time', [])
    if start_times:
        start_time = start_times.pop()
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Registra no contexto de performance
        perf_ctx.add_db_time(elapsed_ms)

        # Log para queries lentas (> 100ms)
        if elapsed_ms > 100:
            # Trunca statement para log
            stmt_short = statement[:200] + "..." if len(statement) > 200 else statement
            logger.debug(f"[PerfDB] Query lenta: {elapsed_ms:.1f}ms - {stmt_short}")


def setup_db_instrumentation(engine: Engine):
    """
    Configura listeners de eventos do SQLAlchemy para medir tempo de queries.

    Args:
        engine: Engine do SQLAlchemy
    """
    # Remove listeners existentes para evitar duplicação
    if event.contains(engine, "before_cursor_execute", _before_cursor_execute):
        return

    event.listen(engine, "before_cursor_execute", _before_cursor_execute)
    event.listen(engine, "after_cursor_execute", _after_cursor_execute)

    logger.info("[PerfInstrumentation] Instrumentação de DB configurada")


# ==================================================
# INSTRUMENTAÇÃO DE JSON PARSE
# ==================================================

# Guarda referência ao json.loads original
_original_json_loads = json.loads


def _instrumented_json_loads(s, *args, **kwargs):
    """
    Wrapper para json.loads que mede tempo de parse.

    Só registra métricas se houver um contexto de performance ativo.
    """
    start = time.perf_counter()
    try:
        result = _original_json_loads(s, *args, **kwargs)
        return result
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000

        # Só registra se tiver contexto ativo e for significativo (> 1ms)
        if elapsed_ms > 1:
            metrics = perf_ctx.get_metrics()
            if metrics:
                json_size = len(s) if isinstance(s, (str, bytes)) else 0
                perf_ctx.add_json_parse_time(elapsed_ms, json_size)


def setup_json_instrumentation():
    """
    Substitui json.loads por versão instrumentada.

    Nota: Isso afeta todo o processo Python.
    """
    json.loads = _instrumented_json_loads
    logger.info("[PerfInstrumentation] Instrumentação de JSON configurada")


# ==================================================
# INSTRUMENTAÇÃO DE LLM (Gemini)
# ==================================================

def setup_llm_instrumentation():
    """
    Configura integração do gemini_service com perf_ctx.

    O gemini_service já tem métricas internas. Esta função
    garante que elas sejam propagadas para o contexto de performance.
    """
    try:
        from services.gemini_service import gemini_service

        # Adiciona hook para propagar métricas LLM para perf_ctx
        original_generate = gemini_service.generate

        @functools.wraps(original_generate)
        async def instrumented_generate(*args, **kwargs):
            result = await original_generate(*args, **kwargs)

            # Propaga métricas para perf_ctx se houver contexto ativo
            if result.metrics and perf_ctx.get_metrics():
                perf_ctx.add_llm_time(
                    ms=result.metrics.time_total_ms,
                    prompt_tokens=result.metrics.prompt_tokens_estimated,
                    response_tokens=result.metrics.response_tokens
                )

            return result

        gemini_service.generate = instrumented_generate
        logger.info("[PerfInstrumentation] Instrumentação de LLM (generate) configurada")

        # Também instrumenta generate_with_images se existir
        if hasattr(gemini_service, 'generate_with_images'):
            original_generate_images = gemini_service.generate_with_images

            @functools.wraps(original_generate_images)
            async def instrumented_generate_images(*args, **kwargs):
                result = await original_generate_images(*args, **kwargs)

                if result.metrics and perf_ctx.get_metrics():
                    perf_ctx.add_llm_time(
                        ms=result.metrics.time_total_ms,
                        prompt_tokens=result.metrics.prompt_tokens_estimated,
                        response_tokens=result.metrics.response_tokens
                    )

                return result

            gemini_service.generate_with_images = instrumented_generate_images
            logger.info("[PerfInstrumentation] Instrumentação de LLM (generate_with_images) configurada")

    except ImportError as e:
        logger.warning(f"[PerfInstrumentation] Não foi possível instrumentar LLM: {e}")
    except Exception as e:
        logger.error(f"[PerfInstrumentation] Erro ao instrumentar LLM: {e}")


# ==================================================
# SETUP PRINCIPAL
# ==================================================

def setup_instrumentation(app=None):
    """
    Configura toda a instrumentação de performance.

    Args:
        app: Instância do FastAPI (opcional, para referência futura)

    Deve ser chamado uma única vez no startup da aplicação.
    """
    global _instrumentation_configured

    if _instrumentation_configured:
        logger.debug("[PerfInstrumentation] Instrumentação já configurada, ignorando")
        return

    logger.info("[PerfInstrumentation] Iniciando configuração de instrumentação automática...")

    # 1. Instrumentação de banco de dados
    try:
        from database.connection import engine
        setup_db_instrumentation(engine)
    except Exception as e:
        logger.error(f"[PerfInstrumentation] Erro ao configurar DB: {e}")

    # 2. Instrumentação de JSON
    try:
        setup_json_instrumentation()
    except Exception as e:
        logger.error(f"[PerfInstrumentation] Erro ao configurar JSON: {e}")

    # 3. Instrumentação de LLM
    try:
        setup_llm_instrumentation()
    except Exception as e:
        logger.error(f"[PerfInstrumentation] Erro ao configurar LLM: {e}")

    _instrumentation_configured = True
    logger.info("[PerfInstrumentation] Instrumentação automática configurada com sucesso!")


# ==================================================
# UTILITÁRIOS PARA INSTRUMENTAÇÃO MANUAL
# ==================================================

@contextmanager
def measure_operation(operation_name: str):
    """
    Context manager para medir tempo de operações customizadas.

    Uso:
        with measure_operation("minha_operacao"):
            # código a ser medido
            fazer_algo_pesado()

    O tempo é registrado como "outro" no contexto.
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.debug(f"[PerfMeasure] {operation_name}: {elapsed_ms:.1f}ms")


def measure_async(func: Callable):
    """
    Decorator para medir tempo de funções async.

    Uso:
        @measure_async
        async def minha_funcao():
            await fazer_algo()
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        start = time.perf_counter()
        try:
            return await func(*args, **kwargs)
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.debug(f"[PerfMeasure] {func.__name__}: {elapsed_ms:.1f}ms")

    return wrapper


def measure_sync(func: Callable):
    """
    Decorator para medir tempo de funções síncronas.

    Uso:
        @measure_sync
        def minha_funcao():
            fazer_algo()
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.debug(f"[PerfMeasure] {func.__name__}: {elapsed_ms:.1f}ms")

    return wrapper
