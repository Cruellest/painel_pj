# admin/services_performance.py
"""
Service para sistema de logs de performance.

Gerencia:
- Toggle de ativação (apenas admin)
- Registro de logs de performance
- Limpeza/rotação de logs antigos
- Consultas para análise
"""

import logging
import time
import uuid
import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from functools import wraps
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

from database.connection import SessionLocal
from utils.timezone import to_iso_utc

logger = logging.getLogger(__name__)


# ==================================================
# CACHE EM MEMÓRIA PARA EVITAR CONSULTAS REPETIDAS
# ==================================================

_cache = {
    "enabled": None,
    "admin_id": None,
    "last_check": None,
    "ttl_seconds": 5  # Revalida a cada 5 segundos
}


def _is_cache_valid() -> bool:
    """Verifica se o cache ainda é válido."""
    if _cache["last_check"] is None:
        return False
    elapsed = (datetime.utcnow() - _cache["last_check"]).total_seconds()
    return elapsed < _cache["ttl_seconds"]


def _update_cache(enabled: bool, admin_id: Optional[int]):
    """Atualiza o cache."""
    _cache["enabled"] = enabled
    _cache["admin_id"] = admin_id
    _cache["last_check"] = datetime.utcnow()


def invalidate_cache():
    """Invalida o cache (chamar ao alterar toggle)."""
    _cache["last_check"] = None


# ==================================================
# VERIFICAÇÃO DE ATIVAÇÃO
# ==================================================

def is_performance_logging_enabled(db: Optional[Session] = None) -> bool:
    """
    Verifica se logs de performance estão ativados.

    Usa cache para evitar consultas repetidas ao BD.
    """
    if _is_cache_valid():
        return _cache["enabled"] or False

    # Precisa consultar o BD
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        from admin.models_performance import AdminSettings

        setting = db.query(AdminSettings).filter(
            AdminSettings.key == "performance_logs_enabled"
        ).first()

        enabled = setting and setting.value == "true"

        admin_id = None
        if enabled:
            admin_setting = db.query(AdminSettings).filter(
                AdminSettings.key == "performance_logs_admin_id"
            ).first()
            if admin_setting and admin_setting.value:
                admin_id = int(admin_setting.value)

        _update_cache(enabled, admin_id)
        return enabled

    except Exception as e:
        logger.error(f"Erro ao verificar toggle de performance: {e}")
        return False
    finally:
        if close_db:
            db.close()


def get_enabled_admin_id(db: Optional[Session] = None) -> Optional[int]:
    """Retorna o ID do admin que ativou os logs."""
    if _is_cache_valid():
        return _cache["admin_id"]

    # Força recarga
    is_performance_logging_enabled(db)
    return _cache["admin_id"]


def set_performance_logging(enabled: bool, admin_id: int, db: Session) -> bool:
    """
    Ativa/desativa logs de performance.

    Args:
        enabled: True para ativar, False para desativar
        admin_id: ID do admin que está alterando
        db: Sessão do banco

    Returns:
        True se alterou com sucesso
    """
    try:
        from admin.models_performance import AdminSettings

        # Atualiza ou cria setting de enabled
        setting = db.query(AdminSettings).filter(
            AdminSettings.key == "performance_logs_enabled"
        ).first()

        if setting:
            setting.value = "true" if enabled else "false"
            setting.updated_by = admin_id
        else:
            setting = AdminSettings(
                key="performance_logs_enabled",
                value="true" if enabled else "false",
                updated_by=admin_id
            )
            db.add(setting)

        # Atualiza ou cria setting de admin_id
        admin_setting = db.query(AdminSettings).filter(
            AdminSettings.key == "performance_logs_admin_id"
        ).first()

        if admin_setting:
            admin_setting.value = str(admin_id) if enabled else None
            admin_setting.updated_by = admin_id
        else:
            admin_setting = AdminSettings(
                key="performance_logs_admin_id",
                value=str(admin_id) if enabled else None,
                updated_by=admin_id
            )
            db.add(admin_setting)

        db.commit()
        invalidate_cache()

        logger.info(f"Performance logging {'ativado' if enabled else 'desativado'} por admin_id={admin_id}")
        return True

    except Exception as e:
        logger.error(f"Erro ao alterar toggle de performance: {e}")
        db.rollback()
        return False


# ==================================================
# REGISTRO DE LOGS
# ==================================================

def log_performance(
    admin_user_id: int,
    method: str,
    route: str,
    layer: str,
    duration_ms: float,
    request_id: Optional[str] = None,
    action: Optional[str] = None,
    status_code: Optional[int] = None,
    extra_info: Optional[str] = None,
    admin_username: Optional[str] = None,
    db: Optional[Session] = None
):
    """
    Registra um log de performance.

    Esta função é leve e falha silenciosamente para não impactar a performance.
    """
    # Curto-circuito: não loga se não estiver ativado
    if not is_performance_logging_enabled(db):
        return

    # Curto-circuito: só loga para o admin que ativou
    enabled_admin = get_enabled_admin_id(db)
    if enabled_admin != admin_user_id:
        return

    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        from admin.models_performance import PerformanceLog

        log_entry = PerformanceLog(
            admin_user_id=admin_user_id,
            admin_username=admin_username,
            request_id=request_id,
            method=method,
            route=route[:500],  # Trunca se muito longo
            layer=layer,
            action=action[:200] if action else None,
            duration_ms=round(duration_ms, 2),
            status_code=status_code,
            extra_info=extra_info[:500] if extra_info else None
        )
        db.add(log_entry)
        db.commit()

        # Log em arquivo também
        _log_to_file(log_entry)

    except Exception as e:
        # Falha silenciosamente para não impactar performance
        logger.debug(f"Erro ao salvar log de performance (ignorado): {e}")
        if close_db:
            db.rollback()
    finally:
        if close_db:
            db.close()


def _log_to_file(log_entry):
    """
    Salva log em arquivo (backup).
    Cria arquivo por dia em /logs/performance/
    """
    try:
        # Cria diretório se não existir
        log_dir = Path(__file__).resolve().parent.parent / "logs" / "performance"
        log_dir.mkdir(parents=True, exist_ok=True)

        # Arquivo por dia
        today = datetime.utcnow().strftime("%Y-%m-%d")
        log_file = log_dir / f"perf_{today}.log"

        # Formato compacto
        line = (
            f"{to_iso_utc(log_entry.created_at)} | "
            f"user={log_entry.admin_user_id} | "
            f"{log_entry.method} {log_entry.route} | "
            f"layer={log_entry.layer} | "
            f"action={log_entry.action or '-'} | "
            f"duration={log_entry.duration_ms}ms | "
            f"status={log_entry.status_code or '-'}\n"
        )

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line)

    except Exception:
        pass  # Ignora erros de escrita em arquivo


# ==================================================
# DECORATORS PARA INSTRUMENTAÇÃO
# ==================================================

def measure_performance(layer: str, action: Optional[str] = None):
    """
    Decorator para medir performance de funções.

    Uso:
        @measure_performance("service", "gerar_json")
        async def minha_funcao(...):
            ...

    O decorator precisa que a função tenha acesso a:
    - request com state.perf_context (via middleware)
    - OU parâmetros request_id, admin_user_id passados

    Para funções simples, use context manager `measure_block`.
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return await func(*args, **kwargs)
            finally:
                duration_ms = (time.perf_counter() - start) * 1000
                # Tenta extrair contexto dos kwargs ou args
                _try_log_from_context(layer, action or func.__name__, duration_ms, kwargs)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                duration_ms = (time.perf_counter() - start) * 1000
                _try_log_from_context(layer, action or func.__name__, duration_ms, kwargs)

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def _try_log_from_context(layer: str, action: str, duration_ms: float, kwargs: dict):
    """Tenta logar usando contexto disponível."""
    try:
        # Tenta pegar do request.state
        request = kwargs.get('request')
        if request and hasattr(request, 'state') and hasattr(request.state, 'perf_context'):
            ctx = request.state.perf_context
            log_performance(
                admin_user_id=ctx.get('admin_user_id'),
                method=ctx.get('method', 'UNKNOWN'),
                route=ctx.get('route', 'unknown'),
                layer=layer,
                duration_ms=duration_ms,
                request_id=ctx.get('request_id'),
                action=action,
                admin_username=ctx.get('admin_username')
            )
    except Exception:
        pass


@contextmanager
def measure_block(
    layer: str,
    action: str,
    admin_user_id: int,
    method: str = "INTERNAL",
    route: str = "internal",
    request_id: Optional[str] = None,
    admin_username: Optional[str] = None
):
    """
    Context manager para medir blocos de código.

    Uso:
        with measure_block("db", "query_perguntas", admin_id, "GET", "/api/..."):
            resultado = db.query(...).all()

    Args:
        layer: Camada (middleware, controller, service, db, io)
        action: Nome da operação
        admin_user_id: ID do admin
        method: Método HTTP
        route: Rota
        request_id: ID único do request (opcional)
        admin_username: Username do admin (opcional)
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        log_performance(
            admin_user_id=admin_user_id,
            method=method,
            route=route,
            layer=layer,
            duration_ms=duration_ms,
            request_id=request_id,
            action=action,
            admin_username=admin_username
        )


# ==================================================
# CONSULTAS E ANÁLISE
# ==================================================

def get_performance_logs(
    db: Session,
    admin_user_id: Optional[int] = None,
    route_filter: Optional[str] = None,
    layer_filter: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = 100,
    offset: int = 0
) -> List[Dict[str, Any]]:
    """
    Consulta logs de performance com filtros.
    """
    from admin.models_performance import PerformanceLog

    query = db.query(PerformanceLog)

    if admin_user_id:
        query = query.filter(PerformanceLog.admin_user_id == admin_user_id)
    if route_filter:
        query = query.filter(PerformanceLog.route.ilike(f"%{route_filter}%"))
    if layer_filter:
        query = query.filter(PerformanceLog.layer == layer_filter)
    if start_date:
        query = query.filter(PerformanceLog.created_at >= start_date)
    if end_date:
        query = query.filter(PerformanceLog.created_at <= end_date)

    logs = query.order_by(desc(PerformanceLog.created_at)).offset(offset).limit(limit).all()

    return [
        {
            "id": log.id,
            "created_at": to_iso_utc(log.created_at),
            "admin_user_id": log.admin_user_id,
            "admin_username": log.admin_username,
            "request_id": log.request_id,
            "method": log.method,
            "route": log.route,
            "layer": log.layer,
            "action": log.action,
            "duration_ms": log.duration_ms,
            "status_code": log.status_code,
            "extra_info": log.extra_info
        }
        for log in logs
    ]


def get_performance_summary(
    db: Session,
    hours: int = 24
) -> Dict[str, Any]:
    """
    Retorna resumo estatístico dos logs de performance.
    """
    from admin.models_performance import PerformanceLog
    from sqlalchemy import func

    since = datetime.utcnow() - timedelta(hours=hours)

    # Total de logs
    total = db.query(func.count(PerformanceLog.id)).filter(
        PerformanceLog.created_at >= since
    ).scalar() or 0

    # Média de duração por camada
    layers_stats = db.query(
        PerformanceLog.layer,
        func.count(PerformanceLog.id).label('count'),
        func.avg(PerformanceLog.duration_ms).label('avg_ms'),
        func.max(PerformanceLog.duration_ms).label('max_ms'),
        func.min(PerformanceLog.duration_ms).label('min_ms')
    ).filter(
        PerformanceLog.created_at >= since
    ).group_by(PerformanceLog.layer).all()

    # Rotas mais lentas
    slow_routes = db.query(
        PerformanceLog.route,
        func.count(PerformanceLog.id).label('count'),
        func.avg(PerformanceLog.duration_ms).label('avg_ms')
    ).filter(
        PerformanceLog.created_at >= since,
        PerformanceLog.layer == 'middleware'  # Total do request
    ).group_by(
        PerformanceLog.route
    ).order_by(
        desc(func.avg(PerformanceLog.duration_ms))
    ).limit(10).all()

    return {
        "period_hours": hours,
        "total_logs": total,
        "layers": [
            {
                "layer": stat[0],
                "count": stat[1],
                "avg_ms": round(stat[2] or 0, 2),
                "max_ms": round(stat[3] or 0, 2),
                "min_ms": round(stat[4] or 0, 2)
            }
            for stat in layers_stats
        ],
        "slowest_routes": [
            {
                "route": route[0],
                "count": route[1],
                "avg_ms": round(route[2] or 0, 2)
            }
            for route in slow_routes
        ]
    }


# ==================================================
# LIMPEZA / ROTAÇÃO
# ==================================================

def cleanup_old_logs(db: Session, days: int = 7) -> int:
    """
    Remove logs mais antigos que X dias.

    Returns:
        Número de logs removidos
    """
    from admin.models_performance import PerformanceLog

    cutoff = datetime.utcnow() - timedelta(days=days)

    deleted = db.query(PerformanceLog).filter(
        PerformanceLog.created_at < cutoff
    ).delete(synchronize_session=False)

    db.commit()

    logger.info(f"Limpeza de logs: {deleted} registros removidos (mais antigos que {days} dias)")
    return deleted


def cleanup_excess_logs(db: Session, max_logs: int = 10000) -> int:
    """
    Remove logs excedentes, mantendo apenas os mais recentes.

    Returns:
        Número de logs removidos
    """
    from admin.models_performance import PerformanceLog

    total = db.query(func.count(PerformanceLog.id)).scalar() or 0

    if total <= max_logs:
        return 0

    # Encontra o ID de corte
    cutoff_log = db.query(PerformanceLog).order_by(
        desc(PerformanceLog.created_at)
    ).offset(max_logs).first()

    if not cutoff_log:
        return 0

    deleted = db.query(PerformanceLog).filter(
        PerformanceLog.id <= cutoff_log.id
    ).delete(synchronize_session=False)

    db.commit()

    logger.info(f"Limpeza de logs: {deleted} registros removidos (excedeu {max_logs} limite)")
    return deleted
