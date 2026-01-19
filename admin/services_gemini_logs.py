# admin/services_gemini_logs.py
"""
Serviço para logging de chamadas da API Gemini.

Funções principais:
- log_gemini_call: Registra uma chamada de forma síncrona
- log_gemini_call_async: Registra de forma assíncrona (não bloqueante)
- get_gemini_logs: Lista logs com filtros
- get_gemini_summary: Estatísticas agregadas
- cleanup_old_gemini_logs: Limpeza de logs antigos
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, and_, case

from database.connection import SessionLocal
from admin.models_gemini_logs import GeminiApiLog

logger = logging.getLogger(__name__)


# ==================================================
# FUNÇÕES DE LOGGING
# ==================================================

def log_gemini_call(
    metrics: Any,  # GeminiMetrics do gemini_service
    sistema: str,
    modulo: str = None,
    user_id: int = None,
    username: str = None,
    has_images: bool = False,
    has_search: bool = False,
    temperature: float = None,
    request_id: str = None,
    route: str = None,
    db: Session = None
) -> Optional[int]:
    """
    Registra uma chamada à API Gemini no banco de dados.

    Args:
        metrics: Objeto GeminiMetrics com métricas da chamada
        sistema: Nome do sistema (gerador_pecas, pedido_calculo, etc)
        modulo: Nome do módulo específico (opcional)
        user_id: ID do usuário que fez a chamada (opcional)
        username: Username do usuário (opcional)
        has_images: Se a chamada incluiu imagens
        has_search: Se usou Google Search Grounding
        temperature: Temperatura usada na chamada
        request_id: ID da request HTTP (para rastreabilidade)
        route: Rota HTTP que originou a chamada
        db: Sessão do banco (se None, cria uma nova)

    Returns:
        ID do log criado ou None se falhar
    """
    close_session = False
    if db is None:
        db = SessionLocal()
        close_session = True

    try:
        log_entry = GeminiApiLog(
            user_id=user_id,
            username=username,
            sistema=sistema or "unknown",
            modulo=modulo,
            request_id=request_id,
            route=route,
            model=metrics.model if hasattr(metrics, 'model') else "unknown",
            prompt_chars=metrics.prompt_chars if hasattr(metrics, 'prompt_chars') else 0,
            prompt_tokens_estimated=metrics.prompt_tokens_estimated if hasattr(metrics, 'prompt_tokens_estimated') else None,
            has_images=has_images,
            has_search=has_search,
            temperature=temperature,
            response_tokens=metrics.response_tokens if hasattr(metrics, 'response_tokens') else None,
            success=metrics.success if hasattr(metrics, 'success') else True,
            cached=metrics.cached if hasattr(metrics, 'cached') else False,
            error=metrics.error[:500] if hasattr(metrics, 'error') and metrics.error else None,
            time_prepare_ms=metrics.time_prepare_ms if hasattr(metrics, 'time_prepare_ms') else None,
            time_connect_ms=metrics.time_connect_ms if hasattr(metrics, 'time_connect_ms') else None,
            time_ttft_ms=metrics.time_ttft_ms if hasattr(metrics, 'time_ttft_ms') else None,
            time_generation_ms=metrics.time_generation_ms if hasattr(metrics, 'time_generation_ms') else None,
            time_total_ms=metrics.time_total_ms if hasattr(metrics, 'time_total_ms') else 0,
            retry_count=metrics.retry_count if hasattr(metrics, 'retry_count') else 0,
        )

        db.add(log_entry)
        db.commit()
        db.refresh(log_entry)

        return log_entry.id

    except Exception as e:
        logger.error(f"[GeminiLogs] Erro ao registrar log: {e}")
        db.rollback()
        return None

    finally:
        if close_session:
            db.close()


async def log_gemini_call_async(
    metrics: Any,
    sistema: str,
    modulo: str = None,
    user_id: int = None,
    username: str = None,
    has_images: bool = False,
    has_search: bool = False,
    temperature: float = None,
    request_id: str = None,
    route: str = None
) -> Optional[int]:
    """
    Registra uma chamada de forma assíncrona (não bloqueante).

    Executa o log em uma thread separada para não impactar a performance.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: log_gemini_call(
            metrics=metrics,
            sistema=sistema,
            modulo=modulo,
            user_id=user_id,
            username=username,
            has_images=has_images,
            has_search=has_search,
            temperature=temperature,
            request_id=request_id,
            route=route
        )
    )


# ==================================================
# FUNÇÕES DE CONSULTA
# ==================================================

def get_gemini_logs(
    db: Session,
    sistema: str = None,
    model: str = None,
    success: bool = None,
    user_id: int = None,
    start_date: datetime = None,
    end_date: datetime = None,
    limit: int = 100,
    offset: int = 0
) -> List[Dict[str, Any]]:
    """
    Lista logs de chamadas Gemini com filtros.

    Args:
        db: Sessão do banco
        sistema: Filtrar por sistema
        model: Filtrar por modelo
        success: Filtrar por sucesso/falha
        user_id: Filtrar por usuário
        start_date: Data inicial
        end_date: Data final
        limit: Limite de resultados
        offset: Offset para paginação

    Returns:
        Lista de logs como dicionários
    """
    query = db.query(GeminiApiLog)

    # Aplica filtros
    if sistema:
        query = query.filter(GeminiApiLog.sistema == sistema)
    if model:
        query = query.filter(GeminiApiLog.model == model)
    if success is not None:
        query = query.filter(GeminiApiLog.success == success)
    if user_id:
        query = query.filter(GeminiApiLog.user_id == user_id)
    if start_date:
        query = query.filter(GeminiApiLog.created_at >= start_date)
    if end_date:
        query = query.filter(GeminiApiLog.created_at <= end_date)

    # Ordena por data decrescente e aplica paginação
    logs = query.order_by(desc(GeminiApiLog.created_at)).offset(offset).limit(limit).all()

    return [log.to_dict() for log in logs]


def get_gemini_summary(db: Session, hours: int = 24) -> Dict[str, Any]:
    """
    Retorna estatísticas agregadas dos logs de Gemini.

    Args:
        db: Sessão do banco
        hours: Período em horas para análise

    Returns:
        Dicionário com estatísticas
    """
    start_date = datetime.utcnow() - timedelta(hours=hours)

    # Total de logs no período
    total_logs = db.query(func.count(GeminiApiLog.id)).filter(
        GeminiApiLog.created_at >= start_date
    ).scalar() or 0

    # Estatísticas gerais
    stats_query = db.query(
        func.count(GeminiApiLog.id).label('count'),
        func.avg(GeminiApiLog.time_total_ms).label('avg_ms'),
        func.max(GeminiApiLog.time_total_ms).label('max_ms'),
        func.min(GeminiApiLog.time_total_ms).label('min_ms'),
        func.sum(GeminiApiLog.response_tokens).label('total_response_tokens'),
        func.sum(GeminiApiLog.prompt_tokens_estimated).label('total_prompt_tokens'),
        func.avg(GeminiApiLog.time_ttft_ms).label('avg_ttft_ms'),
        func.avg(GeminiApiLog.time_generation_ms).label('avg_generation_ms'),
        func.avg(GeminiApiLog.time_connect_ms).label('avg_connect_ms'),
        func.sum(GeminiApiLog.retry_count).label('total_retries'),
    ).filter(
        GeminiApiLog.created_at >= start_date
    ).first()

    # Taxa de sucesso
    success_count = db.query(func.count(GeminiApiLog.id)).filter(
        and_(
            GeminiApiLog.created_at >= start_date,
            GeminiApiLog.success == True
        )
    ).scalar() or 0

    # Taxa de cache hit
    cache_count = db.query(func.count(GeminiApiLog.id)).filter(
        and_(
            GeminiApiLog.created_at >= start_date,
            GeminiApiLog.cached == True
        )
    ).scalar() or 0

    # Chamadas com imagens
    image_count = db.query(func.count(GeminiApiLog.id)).filter(
        and_(
            GeminiApiLog.created_at >= start_date,
            GeminiApiLog.has_images == True
        )
    ).scalar() or 0

    # Chamadas com search
    search_count = db.query(func.count(GeminiApiLog.id)).filter(
        and_(
            GeminiApiLog.created_at >= start_date,
            GeminiApiLog.has_search == True
        )
    ).scalar() or 0

    # Por sistema
    by_sistema = db.query(
        GeminiApiLog.sistema,
        func.count(GeminiApiLog.id).label('count'),
        func.avg(GeminiApiLog.time_total_ms).label('avg_ms'),
        func.sum(GeminiApiLog.response_tokens).label('total_tokens'),
        func.sum(
            case({GeminiApiLog.success == True: 1}, else_=0)
        ).label('success_count'),
    ).filter(
        GeminiApiLog.created_at >= start_date
    ).group_by(GeminiApiLog.sistema).order_by(desc('count')).all()

    # Por modelo
    by_model = db.query(
        GeminiApiLog.model,
        func.count(GeminiApiLog.id).label('count'),
        func.avg(GeminiApiLog.time_total_ms).label('avg_ms'),
        func.sum(GeminiApiLog.response_tokens).label('total_tokens'),
    ).filter(
        GeminiApiLog.created_at >= start_date
    ).group_by(GeminiApiLog.model).order_by(desc('count')).all()

    # Chamadas mais lentas
    slowest = db.query(GeminiApiLog).filter(
        GeminiApiLog.created_at >= start_date
    ).order_by(desc(GeminiApiLog.time_total_ms)).limit(5).all()

    # Erros recentes
    recent_errors = db.query(GeminiApiLog).filter(
        and_(
            GeminiApiLog.created_at >= start_date,
            GeminiApiLog.success == False
        )
    ).order_by(desc(GeminiApiLog.created_at)).limit(10).all()

    return {
        "period_hours": hours,
        "total_calls": total_logs,
        "stats": {
            "avg_latency_ms": round(stats_query.avg_ms, 2) if stats_query.avg_ms else 0,
            "max_latency_ms": round(stats_query.max_ms, 2) if stats_query.max_ms else 0,
            "min_latency_ms": round(stats_query.min_ms, 2) if stats_query.min_ms else 0,
            "total_response_tokens": stats_query.total_response_tokens or 0,
            "total_prompt_tokens": stats_query.total_prompt_tokens or 0,
            "avg_ttft_ms": round(stats_query.avg_ttft_ms, 2) if stats_query.avg_ttft_ms else 0,
            "avg_generation_ms": round(stats_query.avg_generation_ms, 2) if stats_query.avg_generation_ms else 0,
            "avg_connect_ms": round(stats_query.avg_connect_ms, 2) if stats_query.avg_connect_ms else 0,
            "total_retries": stats_query.total_retries or 0,
            "success_count": success_count,
            "error_count": total_logs - success_count,
            "success_rate": round((success_count / total_logs * 100), 1) if total_logs > 0 else 0,
            "cache_hits": cache_count,
            "cache_rate": round((cache_count / total_logs * 100), 1) if total_logs > 0 else 0,
            "image_calls": image_count,
            "search_calls": search_count,
        },
        "by_sistema": [
            {
                "sistema": s.sistema,
                "count": s.count,
                "avg_ms": round(s.avg_ms, 2) if s.avg_ms else 0,
                "total_tokens": s.total_tokens or 0,
                "success_rate": round((s.success_count / s.count * 100), 1) if s.count > 0 else 0,
            }
            for s in by_sistema
        ],
        "by_model": [
            {
                "model": m.model,
                "count": m.count,
                "avg_ms": round(m.avg_ms, 2) if m.avg_ms else 0,
                "total_tokens": m.total_tokens or 0,
            }
            for m in by_model
        ],
        "slowest_calls": [log.to_dict() for log in slowest],
        "recent_errors": [log.to_dict() for log in recent_errors],
    }


def get_available_systems(db: Session) -> List[str]:
    """
    Lista todos os sistemas que já fizeram chamadas Gemini.
    """
    result = db.query(GeminiApiLog.sistema).distinct().all()
    return [r[0] for r in result if r[0]]


def get_available_models(db: Session) -> List[str]:
    """
    Lista todos os modelos que já foram usados.
    """
    result = db.query(GeminiApiLog.model).distinct().all()
    return [r[0] for r in result if r[0]]


# ==================================================
# FUNÇÕES DE LIMPEZA
# ==================================================

def cleanup_old_gemini_logs(db: Session, days: int = 30) -> int:
    """
    Remove logs mais antigos que X dias.

    Args:
        db: Sessão do banco
        days: Número de dias para manter

    Returns:
        Número de logs removidos
    """
    cutoff_date = datetime.utcnow() - timedelta(days=days)

    deleted = db.query(GeminiApiLog).filter(
        GeminiApiLog.created_at < cutoff_date
    ).delete(synchronize_session=False)

    db.commit()
    logger.info(f"[GeminiLogs] {deleted} logs antigos removidos (> {days} dias)")

    return deleted


def cleanup_excess_gemini_logs(db: Session, max_logs: int = 10000) -> int:
    """
    Mantém apenas os X logs mais recentes.

    Args:
        db: Sessão do banco
        max_logs: Número máximo de logs a manter

    Returns:
        Número de logs removidos
    """
    # Conta total de logs
    total = db.query(func.count(GeminiApiLog.id)).scalar() or 0

    if total <= max_logs:
        return 0

    # Encontra o ID do log que é o limite
    cutoff_log = db.query(GeminiApiLog.id).order_by(
        desc(GeminiApiLog.created_at)
    ).offset(max_logs).first()

    if not cutoff_log:
        return 0

    # Remove logs mais antigos que o cutoff
    deleted = db.query(GeminiApiLog).filter(
        GeminiApiLog.id < cutoff_log[0]
    ).delete(synchronize_session=False)

    db.commit()
    logger.info(f"[GeminiLogs] {deleted} logs excedentes removidos (mantidos {max_logs})")

    return deleted
