# admin/router_performance.py
"""
Router para logs de performance MVP.

Objetivo: identificar gargalos (LLM vs DB vs Parse)
- Sem toggle (sempre ativo)
- Todos usuarios geram logs
- Apenas admin visualiza

Endpoints:
- GET /admin/performance/logs - Lista logs
- GET /admin/performance/summary - Resumo com gargalos
- DELETE /admin/performance/cleanup - Limpa logs antigos
- CRUD /admin/performance/route-maps - Mapeamento rota -> sistema
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

from database.connection import get_db
from auth.dependencies import require_admin, get_optional_user
from auth.models import User
from admin.models_performance import PerformanceLog, RouteSystemMap

router = APIRouter(prefix="/admin/api/performance", tags=["Performance Logs"])


# ==================================================
# HELPER: Calcular system_name baseado nos mapeamentos
# ==================================================

def get_system_name_for_route(route: str, mappings: List[RouteSystemMap]) -> str:
    """
    Retorna o nome do sistema para uma rota baseado nos mapeamentos.

    Regras de prioridade:
    1. Match exact sempre vence
    2. Para prefix, o mais longo vence
    3. Para regex, usa o campo priority
    """
    if not route or not mappings:
        return "unknown"

    best_match = None
    best_score = -1

    for mapping in mappings:
        if not mapping.matches(route):
            continue

        # Calcula score para determinar prioridade
        if mapping.match_type == 'exact':
            # Exact match tem prioridade maxima
            score = 1000000 + mapping.priority
        elif mapping.match_type == 'prefix':
            # Prefix mais longo tem prioridade maior
            score = len(mapping.route_pattern) * 1000 + mapping.priority
        elif mapping.match_type == 'regex':
            # Regex usa apenas o campo priority
            score = mapping.priority
        else:
            score = 0

        if score > best_score:
            best_score = score
            best_match = mapping

    return best_match.system_name if best_match else "unknown"


def enrich_log_with_system(log_dict: dict, mappings: List[RouteSystemMap]) -> dict:
    """Adiciona system_name ao dict do log."""
    log_dict["system_name"] = get_system_name_for_route(log_dict.get("route", ""), mappings)
    return log_dict


# ==================================================
# SCHEMAS
# ==================================================

class LogsResponse(BaseModel):
    logs: List[Dict[str, Any]]
    total: int
    limit: int
    offset: int


class SummaryResponse(BaseModel):
    period_hours: int
    total_logs: int
    bottleneck_summary: Dict[str, int]  # {LLM: 45, DB: 30, PARSE: 15, OUTRO: 10}
    avg_times: Dict[str, float]  # {total: 500, llm: 300, db: 100, parse: 50}
    slowest_by_bottleneck: Dict[str, List[Dict]]  # Top 3 por tipo
    recent_errors: List[Dict[str, Any]]


class CleanupResponse(BaseModel):
    deleted_count: int
    message: str


# Schemas para RouteSystemMap
class RouteMapCreate(BaseModel):
    route_pattern: str = Field(..., min_length=1, max_length=500)
    system_name: str = Field(..., min_length=1, max_length=100)
    match_type: str = Field(default='prefix', pattern='^(exact|prefix|regex)$')
    priority: int = Field(default=0, ge=0, le=1000)


class RouteMapUpdate(BaseModel):
    route_pattern: Optional[str] = Field(None, min_length=1, max_length=500)
    system_name: Optional[str] = Field(None, min_length=1, max_length=100)
    match_type: Optional[str] = Field(None, pattern='^(exact|prefix|regex)$')
    priority: Optional[int] = Field(None, ge=0, le=1000)


class RouteMapResponse(BaseModel):
    id: int
    route_pattern: str
    system_name: str
    match_type: str
    priority: int
    created_at: Optional[str]
    updated_at: Optional[str]


class TopRoutesResponse(BaseModel):
    routes: List[Dict[str, Any]]


# ==================================================
# ENDPOINTS
# ==================================================

@router.get("/logs", response_model=LogsResponse)
async def list_logs(
    route: Optional[str] = Query(None, description="Filtrar por rota (parcial)"),
    action: Optional[str] = Query(None, description="Filtrar por action"),
    bottleneck: Optional[str] = Query(None, description="Filtrar por gargalo: LLM, DB, PARSE"),
    status: Optional[str] = Query(None, description="Filtrar por status: ok, error"),
    system: Optional[str] = Query(None, description="Filtrar por sistema (nome mapeado)"),
    hours: int = Query(24, ge=1, le=168, description="Logs das ultimas X horas"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Lista logs de performance com filtros.

    Filtros:
    - route: Filtro parcial na rota
    - action: Filtro exato na action
    - bottleneck: LLM, DB, PARSE, OUTRO
    - status: ok ou error
    - system: Nome do sistema (baseado no mapeamento rota->sistema)
    - hours: Periodo em horas
    """
    start_date = datetime.utcnow() - timedelta(hours=hours)

    # Carrega mapeamentos de rota->sistema
    mappings = db.query(RouteSystemMap).all()

    query = db.query(PerformanceLog).filter(
        PerformanceLog.created_at >= start_date
    )

    # Filtros
    if route:
        query = query.filter(PerformanceLog.route.contains(route))
    if action:
        query = query.filter(PerformanceLog.action == action)
    if status:
        query = query.filter(PerformanceLog.status == status)

    # Ordena por data decrescente
    query = query.order_by(desc(PerformanceLog.created_at))

    # Executa query (busca mais para filtros calculados)
    fetch_multiplier = 2 if (bottleneck or system) else 1
    logs = query.offset(offset).limit(limit * fetch_multiplier).all()

    # Converte para dict e aplica filtros calculados (bottleneck e system)
    result = []
    for log in logs:
        log_dict = log.to_dict()
        # Enriquece com system_name
        log_dict = enrich_log_with_system(log_dict, mappings)

        # Filtro de bottleneck (calculado)
        if bottleneck and log_dict.get('bottleneck') != bottleneck:
            continue
        # Filtro de sistema (calculado)
        if system and log_dict.get('system_name') != system:
            continue

        result.append(log_dict)
        if len(result) >= limit:
            break

    return LogsResponse(
        logs=result,
        total=len(result),
        limit=limit,
        offset=offset
    )


@router.get("/summary", response_model=SummaryResponse)
async def get_summary(
    hours: int = Query(24, ge=1, le=168, description="Periodo em horas"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Retorna resumo estatistico focado em identificar gargalos.

    Inclui:
    - Contagem por tipo de gargalo (LLM, DB, PARSE, OUTRO)
    - Medias de tempo por componente
    - Top 3 lentas por tipo de gargalo
    - Erros recentes
    """
    start_date = datetime.utcnow() - timedelta(hours=hours)

    # Total de logs
    total_logs = db.query(func.count(PerformanceLog.id)).filter(
        PerformanceLog.created_at >= start_date
    ).scalar() or 0

    # Medias de tempo
    avg_query = db.query(
        func.avg(PerformanceLog.total_ms).label('total'),
        func.avg(PerformanceLog.llm_request_ms).label('llm'),
        func.avg(PerformanceLog.db_total_ms).label('db'),
        func.avg(PerformanceLog.json_parse_ms).label('parse'),
    ).filter(
        PerformanceLog.created_at >= start_date
    ).first()

    avg_times = {
        'total': round(avg_query.total or 0, 1),
        'llm': round(avg_query.llm or 0, 1),
        'db': round(avg_query.db or 0, 1),
        'parse': round(avg_query.parse or 0, 1),
    }

    # Busca logs para calcular bottleneck (campo calculado, nao pode filtrar direto)
    logs = db.query(PerformanceLog).filter(
        PerformanceLog.created_at >= start_date
    ).order_by(desc(PerformanceLog.total_ms)).limit(500).all()

    # Calcula distribuicao de bottleneck
    bottleneck_counts = {'LLM': 0, 'DB': 0, 'PARSE': 0, 'OUTRO': 0, '-': 0}
    slowest_by_type = {'LLM': [], 'DB': [], 'PARSE': [], 'OUTRO': []}

    for log in logs:
        bn = log._calc_bottleneck()
        if bn in bottleneck_counts:
            bottleneck_counts[bn] += 1

        # Top 3 por tipo
        if bn in slowest_by_type and len(slowest_by_type[bn]) < 3:
            slowest_by_type[bn].append({
                'route': log.route,
                'action': log.action,
                'total_ms': log.total_ms,
                'llm_ms': log.llm_request_ms,
                'db_ms': log.db_total_ms,
                'parse_ms': log.json_parse_ms,
            })

    # Remove contagem de "-" (requests rapidas)
    del bottleneck_counts['-']

    # Erros recentes
    errors = db.query(PerformanceLog).filter(
        PerformanceLog.created_at >= start_date,
        PerformanceLog.status == 'error'
    ).order_by(desc(PerformanceLog.created_at)).limit(10).all()

    recent_errors = [{
        'route': e.route,
        'action': e.action,
        'error_type': e.error_type,
        'error_message': e.error_message_short,
        'created_at': e.created_at.isoformat() if e.created_at else None,
    } for e in errors]

    return SummaryResponse(
        period_hours=hours,
        total_logs=total_logs,
        bottleneck_summary=bottleneck_counts,
        avg_times=avg_times,
        slowest_by_bottleneck=slowest_by_type,
        recent_errors=recent_errors
    )


@router.get("/actions")
async def list_actions(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Lista todas as actions disponiveis para filtro.
    """
    result = db.query(PerformanceLog.action).distinct().filter(
        PerformanceLog.action.isnot(None)
    ).all()

    return {"actions": [r[0] for r in result if r[0]]}


@router.delete("/cleanup", response_model=CleanupResponse)
async def cleanup_logs(
    days: int = Query(7, ge=1, le=30, description="Remover logs mais antigos que X dias"),
    max_logs: Optional[int] = Query(10000, ge=100, le=50000, description="Manter apenas X logs mais recentes"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Limpa logs antigos ou excedentes.

    Padrao: mantem ultimos 7 dias e maximo 10.000 logs.
    """
    deleted = 0
    cutoff_date = datetime.utcnow() - timedelta(days=days)

    # Limpeza por idade
    deleted += db.query(PerformanceLog).filter(
        PerformanceLog.created_at < cutoff_date
    ).delete(synchronize_session=False)

    db.commit()

    # Limpeza por quantidade
    if max_logs:
        total = db.query(func.count(PerformanceLog.id)).scalar() or 0
        if total > max_logs:
            # Encontra ID de corte
            cutoff_log = db.query(PerformanceLog.id).order_by(
                desc(PerformanceLog.created_at)
            ).offset(max_logs).first()

            if cutoff_log:
                excess_deleted = db.query(PerformanceLog).filter(
                    PerformanceLog.id < cutoff_log[0]
                ).delete(synchronize_session=False)
                deleted += excess_deleted
                db.commit()

    return CleanupResponse(
        deleted_count=deleted,
        message=f"{deleted} logs removidos"
    )


# ==================================================
# ROUTE SYSTEM MAP - CRUD
# ==================================================

@router.get("/route-maps")
async def list_route_maps(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Lista todos os mapeamentos de rota -> sistema.
    """
    mappings = db.query(RouteSystemMap).order_by(
        desc(RouteSystemMap.priority),
        RouteSystemMap.route_pattern
    ).all()

    return {"mappings": [m.to_dict() for m in mappings]}


@router.post("/route-maps", response_model=RouteMapResponse)
async def create_route_map(
    data: RouteMapCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Cria um novo mapeamento de rota -> sistema.
    """
    # Verifica se ja existe
    existing = db.query(RouteSystemMap).filter(
        RouteSystemMap.route_pattern == data.route_pattern
    ).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Ja existe mapeamento para '{data.route_pattern}'"
        )

    # Valida regex se for o tipo
    if data.match_type == 'regex':
        import re
        try:
            re.compile(data.route_pattern)
        except re.error as e:
            raise HTTPException(
                status_code=400,
                detail=f"Regex invalida: {str(e)}"
            )

    mapping = RouteSystemMap(
        route_pattern=data.route_pattern,
        system_name=data.system_name,
        match_type=data.match_type,
        priority=data.priority
    )
    db.add(mapping)
    db.commit()
    db.refresh(mapping)

    return mapping.to_dict()


@router.put("/route-maps/{map_id}", response_model=RouteMapResponse)
async def update_route_map(
    map_id: int,
    data: RouteMapUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Atualiza um mapeamento existente.
    """
    mapping = db.query(RouteSystemMap).filter(RouteSystemMap.id == map_id).first()
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapeamento nao encontrado")

    # Verifica duplicidade de route_pattern se estiver alterando
    if data.route_pattern and data.route_pattern != mapping.route_pattern:
        existing = db.query(RouteSystemMap).filter(
            RouteSystemMap.route_pattern == data.route_pattern,
            RouteSystemMap.id != map_id
        ).first()
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Ja existe mapeamento para '{data.route_pattern}'"
            )

    # Valida regex se for alterado para regex
    new_match_type = data.match_type or mapping.match_type
    new_pattern = data.route_pattern or mapping.route_pattern
    if new_match_type == 'regex':
        import re
        try:
            re.compile(new_pattern)
        except re.error as e:
            raise HTTPException(
                status_code=400,
                detail=f"Regex invalida: {str(e)}"
            )

    # Atualiza campos
    if data.route_pattern is not None:
        mapping.route_pattern = data.route_pattern
    if data.system_name is not None:
        mapping.system_name = data.system_name
    if data.match_type is not None:
        mapping.match_type = data.match_type
    if data.priority is not None:
        mapping.priority = data.priority

    db.commit()
    db.refresh(mapping)

    return mapping.to_dict()


@router.delete("/route-maps/{map_id}")
async def delete_route_map(
    map_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Remove um mapeamento.
    """
    mapping = db.query(RouteSystemMap).filter(RouteSystemMap.id == map_id).first()
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapeamento nao encontrado")

    db.delete(mapping)
    db.commit()

    return {"message": "Mapeamento removido", "id": map_id}


@router.get("/top-routes", response_model=TopRoutesResponse)
async def get_top_routes(
    hours: int = Query(24, ge=1, le=168, description="Periodo em horas"),
    limit: int = Query(20, ge=1, le=100, description="Quantidade de rotas"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Lista as rotas mais frequentes com contagem.

    Util para identificar rotas que precisam de mapeamento.
    """
    start_date = datetime.utcnow() - timedelta(hours=hours)

    # Carrega mapeamentos existentes
    mappings = db.query(RouteSystemMap).all()

    # Agrupa por rota
    routes = db.query(
        PerformanceLog.route,
        func.count(PerformanceLog.id).label('count')
    ).filter(
        PerformanceLog.created_at >= start_date
    ).group_by(
        PerformanceLog.route
    ).order_by(
        desc('count')
    ).limit(limit).all()

    result = []
    for route, count in routes:
        system_name = get_system_name_for_route(route, mappings)
        result.append({
            "route": route,
            "count": count,
            "system_name": system_name,
            "has_mapping": system_name != "unknown"
        })

    return TopRoutesResponse(routes=result)


@router.get("/systems")
async def list_systems(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Lista todos os nomes de sistema disponiveis para filtro.
    """
    mappings = db.query(RouteSystemMap.system_name).distinct().all()
    systems = [m[0] for m in mappings if m[0]]
    # Adiciona 'unknown' para filtrar logs sem mapeamento
    systems.append("unknown")
    return {"systems": sorted(set(systems))}


# ==================================================
# FRONTEND METRICS - Métricas do lado do cliente
# ==================================================

class FrontendMetricsRequest(BaseModel):
    """Métricas de performance coletadas no frontend."""
    route: str = Field(..., description="Rota onde a ação foi realizada")
    action: str = Field(..., description="Ação realizada (ex: editar_categoria)")
    click_to_loading_ms: float = Field(..., description="Tempo do click até loading aparecer")
    click_to_request_ms: float = Field(..., description="Tempo do click até request iniciar")
    request_duration_ms: float = Field(..., description="Duração da request")
    click_to_modal_ms: float = Field(..., description="Tempo total do click até modal abrir")
    timestamp: Optional[str] = Field(None, description="Timestamp ISO do evento")


@router.post("/frontend-metrics")
async def receive_frontend_metrics(
    metrics: FrontendMetricsRequest,
    request: "Request",
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user)
):
    """
    Recebe métricas de performance coletadas no frontend.

    Estas métricas ajudam a diagnosticar problemas de lag que ocorrem
    antes da request chegar ao backend (ex: renderização, parsing JS).

    Os dados são salvos como um PerformanceLog especial com:
    - method = "FRONTEND"
    - action = ação do frontend
    - total_ms = click_to_modal_ms
    - json_parse_ms = click_to_loading_ms (tempo até feedback visual)
    """
    import logging
    logger = logging.getLogger(__name__)

    # Métricas de frontend requerem usuário autenticado (admin_user_id é NOT NULL)
    if not current_user or not current_user.id:
        logger.debug("[PERF-FRONTEND] Métrica ignorada: usuário não autenticado ou sem ID")
        return {"success": False, "message": "User not authenticated"}

    try:
        # Cria log de performance especial para métricas do frontend
        log = PerformanceLog(
            request_id=f"fe-{datetime.utcnow().strftime('%H%M%S%f')[:10]}",
            admin_user_id=current_user.id,
            admin_username=current_user.username,
            route=metrics.route,
            method="FRONTEND",
            action=metrics.action,
            status="ok",
            total_ms=metrics.click_to_modal_ms,
            # Usamos campos existentes para armazenar métricas específicas do frontend
            # click_to_loading_ms -> json_parse_ms (reaproveitado)
            json_parse_ms=metrics.click_to_loading_ms,
            # request_duration_ms -> db_total_ms (reaproveitado para frontend)
            db_total_ms=metrics.request_duration_ms,
            # json_size_chars para armazenar click_to_request_ms como inteiro
            json_size_chars=int(metrics.click_to_request_ms)
        )

        db.add(log)
        db.commit()

        logger.info(
            f"[PERF-FRONTEND] {metrics.action}: "
            f"click_to_loading={metrics.click_to_loading_ms:.1f}ms, "
            f"request={metrics.request_duration_ms:.1f}ms, "
            f"total={metrics.click_to_modal_ms:.1f}ms"
        )

        return {"success": True, "message": "Metrics recorded"}

    except Exception as e:
        logger.error(f"Erro ao salvar métricas do frontend: {e}")
        # Não falha - métricas são best-effort
        return {"success": False, "message": str(e)}
