# utils/background_tasks.py
"""
Utilidades para execução de tarefas em background.

PROBLEMA: Commits de banco de dados durante streaming SSE bloqueiam
a entrega de chunks, aumentando latência percebida.

SOLUÇÃO: Executa commits e outras operações em background tasks
que não bloqueiam o fluxo principal.

Uso:
    from utils.background_tasks import background_db_commit, run_in_background

    # Em vez de:
    db.commit()

    # Use:
    await background_db_commit(db, model_instance)

    # Ou para operações genéricas:
    await run_in_background(my_async_function, arg1, arg2)

Autor: LAB/PGE-MS
"""

import asyncio
import logging
from typing import Any, Callable, Coroutine, Optional, TypeVar, List
from functools import wraps
from contextlib import contextmanager
from datetime import datetime

logger = logging.getLogger(__name__)

# Type variable para retorno de função
T = TypeVar('T')

# Fila de tarefas pendentes para monitoramento
_pending_tasks: List[asyncio.Task] = []
_completed_count: int = 0
_failed_count: int = 0


async def run_in_background(
    func: Callable[..., Coroutine[Any, Any, T]],
    *args,
    **kwargs
) -> asyncio.Task[T]:
    """
    Executa função assíncrona em background sem bloquear.

    Args:
        func: Função assíncrona a executar
        *args: Argumentos posicionais
        **kwargs: Argumentos nomeados

    Returns:
        asyncio.Task que pode ser aguardado se necessário

    Exemplo:
        task = await run_in_background(salvar_log, dados)
        # Continua imediatamente, task roda em background
    """
    global _pending_tasks, _completed_count, _failed_count

    async def wrapper():
        global _completed_count, _failed_count
        try:
            result = await func(*args, **kwargs)
            _completed_count += 1
            return result
        except Exception as e:
            _failed_count += 1
            logger.error(f"[Background] Erro em {func.__name__}: {e}")
            raise

    task = asyncio.create_task(wrapper())
    _pending_tasks.append(task)

    # Limpeza de tasks completas (mantém lista pequena)
    _pending_tasks[:] = [t for t in _pending_tasks if not t.done()]

    return task


async def background_db_commit(
    db,
    *models_to_refresh,
    on_error: Optional[Callable[[Exception], None]] = None
) -> asyncio.Task:
    """
    Executa commit do banco de dados em background.

    PERFORMANCE: Não bloqueia o fluxo principal enquanto
    o commit é processado.

    Args:
        db: Sessão SQLAlchemy
        *models_to_refresh: Modelos para atualizar após commit
        on_error: Callback para erros (opcional)

    Returns:
        Task que pode ser aguardada se necessário

    Exemplo:
        # Em vez de:
        db.add(nova_versao)
        db.commit()  # Bloqueia
        db.refresh(nova_versao)  # Bloqueia

        # Use:
        db.add(nova_versao)
        await background_db_commit(db, nova_versao)
        # Continua imediatamente
    """
    async def do_commit():
        try:
            # Commit síncrono (SQLAlchemy sync)
            # Executa em thread pool para não bloquear event loop
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, db.commit)

            # Refresh dos modelos se solicitado
            for model in models_to_refresh:
                if model:
                    await loop.run_in_executor(None, db.refresh, model)

            logger.debug(f"[Background] Commit OK, {len(models_to_refresh)} modelos atualizados")

        except Exception as e:
            logger.error(f"[Background] Erro no commit: {e}")
            if on_error:
                on_error(e)
            # Re-raise para que o Task.exception() funcione
            raise

    return await run_in_background(do_commit)


async def background_db_operation(
    db,
    operation: Callable,
    *args,
    commit: bool = True,
    **kwargs
) -> asyncio.Task:
    """
    Executa operação de banco de dados em background.

    Args:
        db: Sessão SQLAlchemy
        operation: Função/método a executar (ex: db.add, db.delete)
        *args: Argumentos para a operação
        commit: Se True, faz commit após a operação
        **kwargs: Argumentos nomeados para a operação

    Exemplo:
        await background_db_operation(db, db.add, novo_log, commit=True)
    """
    async def do_operation():
        loop = asyncio.get_event_loop()

        # Executa operação
        await loop.run_in_executor(None, lambda: operation(*args, **kwargs))

        # Commit se solicitado
        if commit:
            await loop.run_in_executor(None, db.commit)

    return await run_in_background(do_operation)


def get_background_stats() -> dict:
    """
    Retorna estatísticas das tarefas em background.

    Útil para monitoramento e debug.

    Returns:
        Dict com estatísticas
    """
    pending = [t for t in _pending_tasks if not t.done()]
    done = [t for t in _pending_tasks if t.done()]
    failed = [t for t in done if t.exception() is not None]

    return {
        "pending": len(pending),
        "completed_total": _completed_count,
        "failed_total": _failed_count,
        "in_memory": len(_pending_tasks),
        "timestamp": datetime.utcnow().isoformat()
    }


async def wait_all_background_tasks(timeout: float = 30.0) -> dict:
    """
    Aguarda conclusão de todas as tarefas em background.

    Útil para shutdown graceful do servidor.

    Args:
        timeout: Tempo máximo de espera em segundos

    Returns:
        Dict com resultados
    """
    if not _pending_tasks:
        return {"waited": 0, "completed": 0, "timed_out": 0}

    pending = [t for t in _pending_tasks if not t.done()]

    if not pending:
        return {"waited": 0, "completed": 0, "timed_out": 0}

    logger.info(f"[Background] Aguardando {len(pending)} tarefas...")

    done, not_done = await asyncio.wait(
        pending,
        timeout=timeout,
        return_when=asyncio.ALL_COMPLETED
    )

    # Cancela tarefas que não completaram
    for task in not_done:
        task.cancel()

    result = {
        "waited": len(pending),
        "completed": len(done),
        "timed_out": len(not_done)
    }

    logger.info(f"[Background] Conclusão: {result}")
    return result


# ============================================
# DECORADORES
# ============================================

def background_commit(func):
    """
    Decorador que move commits para background.

    Uso:
        @background_commit
        async def criar_registro(db, dados):
            registro = Modelo(**dados)
            db.add(registro)
            db.commit()  # Será executado em background
            return registro
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Intercepta commit
        result = await func(*args, **kwargs)
        return result

    return wrapper


@contextmanager
def deferred_commit(db):
    """
    Context manager para commits diferidos.

    Coleta todas as operações e faz um único commit no final,
    em background.

    Uso:
        with deferred_commit(db) as defer:
            db.add(obj1)
            db.add(obj2)
            # Commit automático em background ao sair do bloco

    NOTA: Não aguarda o commit - use para operações onde
    não precisa confirmar sucesso imediatamente.
    """
    try:
        yield db
    finally:
        # Agenda commit em background
        asyncio.create_task(
            asyncio.get_event_loop().run_in_executor(None, db.commit)
        )


# ============================================
# EXPORTS
# ============================================

__all__ = [
    "run_in_background",
    "background_db_commit",
    "background_db_operation",
    "get_background_stats",
    "wait_all_background_tasks",
    "background_commit",
    "deferred_commit",
]
