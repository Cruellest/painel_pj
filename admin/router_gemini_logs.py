# admin/router_gemini_logs.py
"""
Router para gerenciamento de logs de chamadas Gemini.

Endpoints:
- GET /admin/api/gemini-logs - Lista logs com filtros
- GET /admin/api/gemini-logs/summary - Estatísticas agregadas
- GET /admin/api/gemini-logs/systems - Lista sistemas disponíveis
- GET /admin/api/gemini-logs/models - Lista modelos disponíveis
- DELETE /admin/api/gemini-logs/cleanup - Limpa logs antigos
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

from database.connection import get_db
from auth.dependencies import require_admin
from auth.models import User

from admin.services_gemini_logs import (
    get_gemini_logs,
    get_gemini_summary,
    get_available_systems,
    get_available_models,
    cleanup_old_gemini_logs,
    cleanup_excess_gemini_logs
)

router = APIRouter(prefix="/admin/api/gemini-logs", tags=["Gemini Logs"])


# ==================================================
# SCHEMAS
# ==================================================

class LogEntry(BaseModel):
    id: int
    created_at: Optional[str]
    user_id: Optional[int]
    username: Optional[str]
    sistema: str
    modulo: Optional[str]
    model: str
    prompt_chars: int
    prompt_tokens_estimated: Optional[int]
    has_images: bool
    has_search: bool
    temperature: Optional[float]
    response_tokens: Optional[int]
    success: bool
    cached: bool
    error: Optional[str]
    time_prepare_ms: Optional[float]
    time_connect_ms: Optional[float]
    time_ttft_ms: Optional[float]
    time_generation_ms: Optional[float]
    time_total_ms: float
    retry_count: int


class LogsResponse(BaseModel):
    logs: List[Dict[str, Any]]
    total: int
    limit: int
    offset: int


class SummaryResponse(BaseModel):
    period_hours: int
    total_calls: int
    stats: Dict[str, Any]
    by_sistema: List[Dict[str, Any]]
    by_model: List[Dict[str, Any]]
    slowest_calls: List[Dict[str, Any]]
    recent_errors: List[Dict[str, Any]]


class SystemsResponse(BaseModel):
    systems: List[str]


class ModelsResponse(BaseModel):
    models: List[str]


class CleanupResponse(BaseModel):
    deleted_count: int
    message: str


# ==================================================
# ENDPOINTS
# ==================================================

@router.get("", response_model=LogsResponse)
async def list_logs(
    sistema: Optional[str] = Query(None, description="Filtrar por sistema"),
    model: Optional[str] = Query(None, description="Filtrar por modelo"),
    success: Optional[bool] = Query(None, description="Filtrar por sucesso/falha"),
    user_id: Optional[int] = Query(None, description="Filtrar por usuário"),
    hours: int = Query(24, ge=1, le=720, description="Logs das últimas X horas"),
    limit: int = Query(100, ge=1, le=1000, description="Limite de resultados"),
    offset: int = Query(0, ge=0, description="Offset para paginação"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Lista logs de chamadas Gemini com filtros.

    Filtros disponíveis:
    - sistema: Nome do sistema (gerador_pecas, pedido_calculo, etc)
    - model: Nome do modelo (gemini-3-flash-preview, etc)
    - success: true/false para filtrar por sucesso
    - user_id: ID do usuário
    - hours: Período em horas (padrão: 24h)
    """
    start_date = datetime.utcnow() - timedelta(hours=hours)

    logs = get_gemini_logs(
        db=db,
        sistema=sistema,
        model=model,
        success=success,
        user_id=user_id,
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
    hours: int = Query(24, ge=1, le=720, description="Período em horas para análise"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Retorna estatísticas agregadas dos logs de Gemini.

    Inclui:
    - Total de chamadas e taxa de sucesso
    - Latência média, máxima e mínima
    - Distribuição por sistema e modelo
    - Chamadas mais lentas
    - Erros recentes
    """
    summary = get_gemini_summary(db, hours)
    return SummaryResponse(**summary)


@router.get("/systems", response_model=SystemsResponse)
async def list_systems(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Lista todos os sistemas que já fizeram chamadas Gemini.
    """
    systems = get_available_systems(db)
    return SystemsResponse(systems=systems)


@router.get("/models", response_model=ModelsResponse)
async def list_models(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Lista todos os modelos Gemini que já foram usados.
    """
    models = get_available_models(db)
    return ModelsResponse(models=models)


@router.delete("/cleanup", response_model=CleanupResponse)
async def cleanup_logs(
    days: int = Query(30, ge=1, le=90, description="Remover logs mais antigos que X dias"),
    max_logs: Optional[int] = Query(None, ge=100, le=100000, description="Manter apenas X logs mais recentes"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Limpa logs antigos ou excedentes.

    Opções:
    - days: Remove logs mais antigos que X dias (padrão: 30)
    - max_logs: Se especificado, mantém apenas os X mais recentes
    """
    deleted = 0

    # Limpeza por idade
    deleted += cleanup_old_gemini_logs(db, days)

    # Limpeza por quantidade
    if max_logs:
        deleted += cleanup_excess_gemini_logs(db, max_logs)

    return CleanupResponse(
        deleted_count=deleted,
        message=f"{deleted} logs removidos"
    )


# ==================================================
# MÉTRICAS DE ROTA (LATÊNCIA)
# ==================================================

@router.get("/route-metrics")
async def get_route_latency_metrics(
    route: Optional[str] = Query(None, description="Rota específica ou vazia para todas"),
    current_user: User = Depends(require_admin)
):
    """
    Retorna métricas de latência por rota.

    Métricas incluem:
    - Total de chamadas
    - Taxa de sucesso/fallback
    - Latência média/min/max
    - TTFT (Time to First Token) média/min/max

    Útil para identificar rotas problemáticas e ajustar configurações.
    """
    from services.route_config import get_route_metrics

    return get_route_metrics(route)


@router.delete("/route-metrics")
async def reset_route_latency_metrics(
    route: Optional[str] = Query(None, description="Rota específica ou vazia para todas"),
    current_user: User = Depends(require_admin)
):
    """
    Reseta métricas de latência por rota.
    """
    from services.route_config import reset_route_metrics

    reset_route_metrics(route)
    return {"message": f"Métricas resetadas: {route or 'todas as rotas'}"}


@router.get("/route-config")
async def get_route_configurations(
    route: Optional[str] = Query(None, description="Rota específica ou vazia para todas"),
    current_user: User = Depends(require_admin)
):
    """
    Retorna configurações de rota (modelo, timeout, streaming, etc).

    Mostra as configurações de fast/slow path para cada rota.
    """
    from services.route_config import get_route_config, DEFAULT_ROUTE_CONFIGS

    if route:
        config = get_route_config(route)
        return {
            "route": route,
            "profile": config.profile.value,
            "model_primary": config.model_primary,
            "model_fallback": config.model_fallback,
            "sla_timeout": config.sla_timeout,
            "max_timeout": config.max_timeout,
            "thinking_level": config.thinking_level,
            "use_streaming": config.use_streaming,
            "temperature": config.temperature,
            "max_prompt_chars": config.max_prompt_chars,
            "auto_truncate": config.auto_truncate
        }

    # Todas as rotas configuradas
    return {
        "routes": [
            {
                "route": pattern,
                "profile": config.profile.value,
                "model_primary": config.model_primary,
                "model_fallback": config.model_fallback,
                "sla_timeout": config.sla_timeout,
                "use_streaming": config.use_streaming
            }
            for pattern, config in DEFAULT_ROUTE_CONFIGS.items()
        ]
    }


@router.get("/service-status")
async def get_gemini_service_status(
    current_user: User = Depends(require_admin)
):
    """
    Retorna status do serviço Gemini.

    Inclui:
    - Status do HTTP client
    - Estatísticas de cache
    - Configurações de timeout
    - Background tasks pendentes
    """
    from services.gemini_service import get_service_status, get_cache_stats
    from utils.background_tasks import get_background_stats

    service_status = await get_service_status()

    return {
        "gemini_service": service_status,
        "cache": get_cache_stats(),
        "background_tasks": get_background_stats()
    }


# ==================================================
# VERIFICAÇÃO DE THINKING_LEVEL
# ==================================================

@router.get("/thinking-level-status")
async def get_thinking_level_status(
    sistema: Optional[str] = Query(None, description="Sistema específico ou todos"),
    hours: int = Query(24, ge=1, le=168, description="Período em horas para análise"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Verifica se o thinking_level configurado está sendo usado efetivamente.

    Compara:
    - Configuração esperada (da ConfiguracaoIA por agente/sistema)
    - Uso real (registrado nos logs de GeminiApiLog)

    Retorna alertas quando há discrepâncias, indicando que a configuração
    pode não estar sendo aplicada corretamente.
    """
    from sqlalchemy import func, and_
    from admin.models_gemini_logs import GeminiApiLog
    from admin.models import ConfiguracaoIA
    from services.ia_params_resolver import AGENTES_POR_SISTEMA, resolve_ia_params

    start_date = datetime.utcnow() - timedelta(hours=hours)

    # Obtém sistemas para análise
    if sistema:
        sistemas = [sistema]
    else:
        sistemas = list(AGENTES_POR_SISTEMA.keys())

    resultado = {
        "periodo_horas": hours,
        "sistemas": {},
        "alertas": [],
        "resumo": {
            "total_sistemas": 0,
            "sistemas_com_dados": 0,
            "sistemas_com_alerta": 0,
            "total_chamadas_analisadas": 0
        }
    }

    for sis in sistemas:
        if sis not in AGENTES_POR_SISTEMA:
            continue

        resultado["resumo"]["total_sistemas"] += 1

        # Obtém configuração esperada para cada agente do sistema
        agentes = AGENTES_POR_SISTEMA.get(sis, {})
        config_esperada = {}

        for agente_slug in agentes.keys():
            params = resolve_ia_params(db, sis, agente_slug)
            config_esperada[agente_slug] = {
                "thinking_level": params.thinking_level,
                "fonte": params.thinking_level_source
            }

        # Busca logs reais do sistema no período
        logs_sistema = db.query(
            GeminiApiLog.modulo,
            GeminiApiLog.thinking_level,
            func.count(GeminiApiLog.id).label('count')
        ).filter(
            and_(
                GeminiApiLog.sistema == sis,
                GeminiApiLog.created_at >= start_date,
                GeminiApiLog.success == True
            )
        ).group_by(
            GeminiApiLog.modulo,
            GeminiApiLog.thinking_level
        ).all()

        # Agrupa por módulo
        uso_real = {}
        total_chamadas = 0
        for log in logs_sistema:
            modulo = log.modulo or "unknown"
            if modulo not in uso_real:
                uso_real[modulo] = {"total": 0, "por_level": {}}
            count = log.count
            level = log.thinking_level or "none"
            uso_real[modulo]["total"] += count
            uso_real[modulo]["por_level"][level] = uso_real[modulo]["por_level"].get(level, 0) + count
            total_chamadas += count

        if total_chamadas > 0:
            resultado["resumo"]["sistemas_com_dados"] += 1
        resultado["resumo"]["total_chamadas_analisadas"] += total_chamadas

        # Verifica discrepâncias
        alertas_sistema = []
        for agente_slug, config in config_esperada.items():
            esperado = config["thinking_level"]

            # Verifica se há dados para esse agente
            if agente_slug in uso_real:
                usado = uso_real[agente_slug]
                levels_usados = usado.get("por_level", {})

                # Verifica se o level esperado foi o mais usado
                if esperado:
                    total_com_esperado = levels_usados.get(esperado, 0)
                    total_sem_esperado = sum(
                        c for l, c in levels_usados.items()
                        if l != esperado
                    )

                    if total_com_esperado == 0 and usado["total"] > 0:
                        # Configuração não está sendo usada
                        alertas_sistema.append({
                            "agente": agente_slug,
                            "tipo": "nao_aplicado",
                            "esperado": esperado,
                            "encontrado": list(levels_usados.keys()),
                            "mensagem": f"Agente '{agente_slug}' tem thinking_level='{esperado}' configurado mas não está sendo usado nas chamadas"
                        })
                    elif total_sem_esperado > total_com_esperado * 0.1:  # Mais de 10% diferente
                        alertas_sistema.append({
                            "agente": agente_slug,
                            "tipo": "parcial",
                            "esperado": esperado,
                            "encontrado": levels_usados,
                            "mensagem": f"Agente '{agente_slug}' usa thinking_level='{esperado}' parcialmente ({total_com_esperado}/{usado['total']} chamadas)"
                        })
                else:
                    # Não há configuração mas há chamadas com thinking_level
                    levels_nao_none = {l: c for l, c in levels_usados.items() if l != "none"}
                    if levels_nao_none:
                        alertas_sistema.append({
                            "agente": agente_slug,
                            "tipo": "info",
                            "esperado": None,
                            "encontrado": levels_nao_none,
                            "mensagem": f"Agente '{agente_slug}' não tem thinking_level configurado mas está usando: {list(levels_nao_none.keys())}"
                        })

        if alertas_sistema:
            resultado["resumo"]["sistemas_com_alerta"] += 1
            resultado["alertas"].extend([{**a, "sistema": sis} for a in alertas_sistema])

        resultado["sistemas"][sis] = {
            "config_esperada": config_esperada,
            "uso_real": uso_real,
            "total_chamadas": total_chamadas,
            "alertas": alertas_sistema
        }

    return resultado
