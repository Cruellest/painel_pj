# admin/router_performance.py
"""
Router para gerenciamento de logs de performance.

Endpoints:
- GET/POST /admin/performance/toggle - Ativa/desativa logs
- GET /admin/performance/logs - Lista logs
- GET /admin/performance/summary - Resumo estatístico
- DELETE /admin/performance/cleanup - Limpa logs antigos
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

from database.connection import get_db
from auth.dependencies import require_admin
from auth.models import User

from admin.services_performance import (
    is_performance_logging_enabled,
    get_enabled_admin_id,
    set_performance_logging,
    get_performance_logs,
    get_performance_summary,
    cleanup_old_logs,
    cleanup_excess_logs
)

router = APIRouter(prefix="/admin/performance", tags=["Performance Logs"])


# ==================================================
# SCHEMAS
# ==================================================

class ToggleRequest(BaseModel):
    enabled: bool


class ToggleResponse(BaseModel):
    enabled: bool
    admin_id: Optional[int] = None
    admin_username: Optional[str] = None
    message: str


class LogEntry(BaseModel):
    id: int
    created_at: str
    admin_user_id: int
    admin_username: Optional[str]
    request_id: Optional[str]
    method: str
    route: str
    layer: str
    action: Optional[str]
    duration_ms: float
    status_code: Optional[int]
    extra_info: Optional[str]


class LogsResponse(BaseModel):
    logs: List[Dict[str, Any]]
    total: int
    limit: int
    offset: int


class SummaryResponse(BaseModel):
    period_hours: int
    total_logs: int
    layers: List[Dict[str, Any]]
    slowest_routes: List[Dict[str, Any]]


class CleanupResponse(BaseModel):
    deleted_count: int
    message: str


# ==================================================
# ENDPOINTS
# ==================================================

@router.get("/toggle", response_model=ToggleResponse)
async def get_toggle_status(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Retorna o status atual do toggle de logs de performance.
    """
    enabled = is_performance_logging_enabled(db)
    admin_id = get_enabled_admin_id(db)

    admin_username = None
    if admin_id:
        admin = db.query(User).filter(User.id == admin_id).first()
        if admin:
            admin_username = admin.username

    return ToggleResponse(
        enabled=enabled,
        admin_id=admin_id,
        admin_username=admin_username,
        message="Logs de performance estão " + ("ativados" if enabled else "desativados")
    )


@router.post("/test-log")
async def test_log_manually(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Endpoint de diagnóstico: testa se o log_performance funciona.
    """
    from admin.services_performance import log_performance, invalidate_cache

    # Invalida cache para garantir leitura fresca
    invalidate_cache()

    # Tenta registrar um log manualmente
    log_performance(
        admin_user_id=current_user.id,
        admin_username=current_user.username,
        request_id="diag0001",
        method="POST",
        route="/admin/performance/test-log",
        layer="controller",
        action="diagnostic_test",
        duration_ms=1.0,
        status_code=200,
        db=db
    )

    # Verifica se foi registrado
    from admin.models_performance import PerformanceLog
    count = db.query(PerformanceLog).filter(
        PerformanceLog.request_id == "diag0001"
    ).count()

    return {
        "success": count > 0,
        "message": f"Log {'registrado' if count > 0 else 'NAO registrado'}",
        "user_id": current_user.id,
        "enabled": is_performance_logging_enabled(db),
        "enabled_admin_id": get_enabled_admin_id(db)
    }


@router.get("/diag-middleware")
async def diagnose_middleware(
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Endpoint de diagnóstico: simula exatamente o que o middleware faz.
    """
    from admin.services_performance import invalidate_cache

    # Invalida cache para leitura fresca
    invalidate_cache()

    result = {
        "step_1_is_enabled": None,
        "step_2_enabled_admin_id": None,
        "step_3_auth_header": None,
        "step_4_token_found": None,
        "step_5_payload": None,
        "step_6_user_id_from_token": None,
        "step_7_role": None,
        "step_8_should_log": None,
        "expected_user_id": current_user.id
    }

    # Step 1: Check if enabled
    result["step_1_is_enabled"] = is_performance_logging_enabled(db)

    # Step 2: Get enabled admin id
    result["step_2_enabled_admin_id"] = get_enabled_admin_id(db)

    # Step 3: Get auth header
    auth_header = request.headers.get("Authorization")
    result["step_3_auth_header"] = auth_header[:50] if auth_header else None

    # Step 4: Extract token
    token = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
    else:
        token = request.cookies.get("access_token")
    result["step_4_token_found"] = token is not None

    # Step 5: Decode token
    if token:
        try:
            from auth.utils import decode_access_token
            payload = decode_access_token(token)
            result["step_5_payload"] = {
                "user_id": payload.get("user_id") if payload else None,
                "sub": payload.get("sub") if payload else None,
                "role": payload.get("role") if payload else None
            } if payload else "DECODE_FAILED"

            if payload:
                result["step_6_user_id_from_token"] = payload.get("user_id")
                result["step_7_role"] = payload.get("role")
        except Exception as e:
            result["step_5_payload"] = f"ERROR: {str(e)}"

    # Step 8: Would middleware log?
    if result["step_1_is_enabled"]:
        if result["step_7_role"] == "admin":
            if result["step_6_user_id_from_token"] == result["step_2_enabled_admin_id"]:
                result["step_8_should_log"] = True
            else:
                result["step_8_should_log"] = f"NO: user_id mismatch ({result['step_6_user_id_from_token']} != {result['step_2_enabled_admin_id']})"
        else:
            result["step_8_should_log"] = f"NO: role is not admin ({result['step_7_role']})"
    else:
        result["step_8_should_log"] = "NO: logging not enabled"

    return result


@router.post("/toggle", response_model=ToggleResponse)
async def set_toggle_status(
    data: ToggleRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Ativa ou desativa logs de performance.

    Quando ativado, apenas requisições do admin que ativou serão logadas.
    """
    success = set_performance_logging(data.enabled, current_user.id, db)

    if not success:
        raise HTTPException(status_code=500, detail="Erro ao alterar configuração")

    return ToggleResponse(
        enabled=data.enabled,
        admin_id=current_user.id if data.enabled else None,
        admin_username=current_user.username if data.enabled else None,
        message=f"Logs de performance {'ativados' if data.enabled else 'desativados'} para {current_user.username}"
    )


@router.get("/logs", response_model=LogsResponse)
async def list_logs(
    route: Optional[str] = Query(None, description="Filtrar por rota (parcial)"),
    layer: Optional[str] = Query(None, description="Filtrar por camada"),
    hours: int = Query(24, description="Logs das últimas X horas"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Lista logs de performance com filtros.
    """
    start_date = datetime.utcnow() - timedelta(hours=hours)

    logs = get_performance_logs(
        db=db,
        admin_user_id=current_user.id,  # Só logs do próprio admin
        route_filter=route,
        layer_filter=layer,
        start_date=start_date,
        limit=limit,
        offset=offset
    )

    return LogsResponse(
        logs=logs,
        total=len(logs),
        limit=limit,
        offset=offset
    )


@router.get("/summary", response_model=SummaryResponse)
async def get_summary(
    hours: int = Query(24, description="Período em horas para análise"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Retorna resumo estatístico dos logs de performance.

    Inclui:
    - Estatísticas por camada (avg, max, min)
    - Rotas mais lentas
    """
    summary = get_performance_summary(db, hours)
    return SummaryResponse(**summary)


@router.delete("/cleanup", response_model=CleanupResponse)
async def cleanup_logs(
    days: int = Query(7, ge=1, le=30, description="Remover logs mais antigos que X dias"),
    max_logs: Optional[int] = Query(None, ge=100, le=100000, description="Manter apenas X logs mais recentes"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Limpa logs antigos ou excedentes.

    Opções:
    - days: Remove logs mais antigos que X dias (padrão: 7)
    - max_logs: Se especificado, mantém apenas os X mais recentes
    """
    deleted = 0

    # Limpeza por idade
    deleted += cleanup_old_logs(db, days)

    # Limpeza por quantidade
    if max_logs:
        deleted += cleanup_excess_logs(db, max_logs)

    return CleanupResponse(
        deleted_count=deleted,
        message=f"{deleted} logs removidos"
    )
