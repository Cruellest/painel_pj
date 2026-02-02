# admin/services_request_perf.py
"""
Servicos para logs de performance detalhados de requests.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, Integer

from admin.models_request_perf import RequestPerfLog

logger = logging.getLogger(__name__)


def log_request_perf(
    report: dict,
    db: Session,
    user_id: int = None,
    username: str = None,
    success: bool = True,
    error: str = None
) -> Optional[int]:
    """
    Salva log de performance de request no banco.

    Args:
        report: Dicionario do PerformanceTracker.get_report()
        db: Sessao do banco
        user_id: ID do usuario
        username: Nome do usuario
        success: Se o request foi bem-sucedido
        error: Mensagem de erro (se houver)

    Returns:
        ID do log criado ou None se falhou
    """
    try:
        log = RequestPerfLog.from_tracker_report(report, user_id, username)
        log.success = success
        log.error = error

        db.add(log)
        db.commit()
        db.refresh(log)

        return log.id

    except Exception as e:
        logger.error(f"Erro ao salvar log de performance: {e}")
        db.rollback()
        return None


async def log_request_perf_async(
    report: dict,
    db_factory,
    user_id: int = None,
    username: str = None,
    success: bool = True,
    error: str = None
):
    """
    Versao assincrona do log_request_perf.

    Executa em background sem bloquear o request.
    """
    def _save():
        try:
            db = db_factory()
            try:
                log_request_perf(report, db, user_id, username, success, error)
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Erro ao salvar log async: {e}")

    # Executa em thread separada
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _save)


def get_request_perf_logs(
    db: Session,
    sistema: str = None,
    hours: int = 24,
    limit: int = 100,
    offset: int = 0,
    success_only: bool = None,
    min_total_ms: float = None
) -> List[RequestPerfLog]:
    """
    Busca logs de performance com filtros.

    Args:
        db: Sessao do banco
        sistema: Filtrar por sistema
        hours: Periodo em horas
        limit: Limite de resultados
        offset: Offset para paginacao
        success_only: Filtrar por sucesso
        min_total_ms: Filtrar por latencia minima

    Returns:
        Lista de RequestPerfLog
    """
    start_date = datetime.utcnow() - timedelta(hours=hours)

    query = db.query(RequestPerfLog).filter(
        RequestPerfLog.created_at >= start_date
    )

    if sistema:
        query = query.filter(RequestPerfLog.sistema == sistema)

    if success_only is not None:
        query = query.filter(RequestPerfLog.success == success_only)

    if min_total_ms is not None:
        query = query.filter(RequestPerfLog.total_ms >= min_total_ms)

    return query.order_by(desc(RequestPerfLog.created_at)).offset(offset).limit(limit).all()


def get_request_perf_summary(
    db: Session,
    sistema: str = None,
    hours: int = 24
) -> Dict[str, Any]:
    """
    Retorna estatisticas agregadas de performance.

    Args:
        db: Sessao do banco
        sistema: Filtrar por sistema
        hours: Periodo em horas

    Returns:
        Dicionario com estatisticas
    """
    start_date = datetime.utcnow() - timedelta(hours=hours)

    query = db.query(
        func.count(RequestPerfLog.id).label('total'),
        func.sum(func.cast(RequestPerfLog.success, Integer)).label('success_count'),
        func.avg(RequestPerfLog.total_ms).label('avg_total'),
        func.min(RequestPerfLog.total_ms).label('min_total'),
        func.max(RequestPerfLog.total_ms).label('max_total'),
        func.avg(RequestPerfLog.ttft_ms).label('avg_ttft'),
        func.avg(RequestPerfLog.generation_ms).label('avg_generation'),
        func.avg(RequestPerfLog.agente1_ms).label('avg_agente1'),
        func.avg(RequestPerfLog.agente2_ms).label('avg_agente2'),
        func.avg(RequestPerfLog.prompt_build_ms).label('avg_prompt_build'),
        func.avg(RequestPerfLog.postprocess_ms).label('avg_postprocess'),
        func.avg(RequestPerfLog.db_save_ms).label('avg_db_save'),
        func.avg(RequestPerfLog.overhead_ms).label('avg_overhead'),
        func.avg(RequestPerfLog.streaming_chunks).label('avg_chunks'),
        func.avg(RequestPerfLog.avg_chunk_interval_ms).label('avg_chunk_interval'),
    ).filter(
        RequestPerfLog.created_at >= start_date
    )

    if sistema:
        query = query.filter(RequestPerfLog.sistema == sistema)

    result = query.first()

    if not result or not result.total:
        return {
            "total": 0,
            "success_count": 0,
            "success_rate": 0,
            "avg_total_ms": 0,
            "min_total_ms": 0,
            "max_total_ms": 0,
            "breakdown": {},
            "streaming": {}
        }

    total = result.total or 0
    success_count = result.success_count or 0

    return {
        "total": total,
        "success_count": success_count,
        "error_count": total - success_count,
        "success_rate": round((success_count / total) * 100, 1) if total > 0 else 0,

        # Latencia total
        "avg_total_ms": round(result.avg_total or 0, 1),
        "min_total_ms": round(result.min_total or 0, 1),
        "max_total_ms": round(result.max_total or 0, 1),

        # TTFT e Geracao
        "avg_ttft_ms": round(result.avg_ttft or 0, 1),
        "avg_generation_ms": round(result.avg_generation or 0, 1),

        # Breakdown por etapa
        "breakdown": {
            "agente1_ms": round(result.avg_agente1 or 0, 1),
            "agente2_ms": round(result.avg_agente2 or 0, 1),
            "prompt_build_ms": round(result.avg_prompt_build or 0, 1),
            "postprocess_ms": round(result.avg_postprocess or 0, 1),
            "db_save_ms": round(result.avg_db_save or 0, 1),
            "overhead_ms": round(result.avg_overhead or 0, 1),
        },

        # Streaming
        "streaming": {
            "avg_chunks": round(result.avg_chunks or 0, 1),
            "avg_chunk_interval_ms": round(result.avg_chunk_interval or 0, 2),
        }
    }


def get_slowest_requests(
    db: Session,
    sistema: str = None,
    hours: int = 24,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Retorna os requests mais lentos.
    """
    start_date = datetime.utcnow() - timedelta(hours=hours)

    query = db.query(RequestPerfLog).filter(
        RequestPerfLog.created_at >= start_date
    )

    if sistema:
        query = query.filter(RequestPerfLog.sistema == sistema)

    logs = query.order_by(desc(RequestPerfLog.total_ms)).limit(limit).all()

    return [log.to_dict() for log in logs]


def cleanup_old_logs(db: Session, days: int = 7) -> int:
    """
    Remove logs mais antigos que X dias.

    Returns:
        Numero de logs removidos
    """
    cutoff = datetime.utcnow() - timedelta(days=days)

    count = db.query(RequestPerfLog).filter(
        RequestPerfLog.created_at < cutoff
    ).delete()

    db.commit()
    return count
