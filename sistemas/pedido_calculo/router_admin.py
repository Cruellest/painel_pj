# sistemas/pedido_calculo/router_admin.py
"""
Router de administração do Pedido de Cálculo
- Visualização de prompts enviados
- Histórico detalhado de gerações
- Logs de chamadas de IA
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import desc, func, case
from pydantic import BaseModel
from typing import Optional, List, Any, Dict
from datetime import datetime

from auth.dependencies import get_current_active_user
from auth.models import User
from database.connection import get_db
from .models import GeracaoPedidoCalculo, LogChamadaIA, FeedbackPedidoCalculo

router = APIRouter(prefix="/pedido-calculo-admin", tags=["Pedido de Cálculo - Admin"])


# ==========================================
# Schemas
# ==========================================

class LogChamadaResponse(BaseModel):
    id: int
    etapa: str
    descricao: Optional[str]
    documento_id: Optional[str]
    prompt_enviado: Optional[str]
    documento_texto: Optional[str]
    resposta_ia: Optional[str]
    resposta_parseada: Optional[Dict[str, Any]]
    modelo_usado: Optional[str]
    tokens_entrada: Optional[int]
    tokens_saida: Optional[int]
    tempo_ms: Optional[int]
    sucesso: bool
    erro: Optional[str]
    criado_em: datetime

    class Config:
        from_attributes = True


class GeracaoDetalhadaResponse(BaseModel):
    id: int
    numero_cnj: str
    numero_cnj_formatado: Optional[str]
    dados_processo: Optional[Dict[str, Any]]
    dados_agente1: Optional[Dict[str, Any]]
    dados_agente2: Optional[Dict[str, Any]]
    documentos_baixados: Optional[List[Dict[str, Any]]]
    conteudo_gerado: Optional[str]
    modelo_usado: Optional[str]
    tempo_processamento: Optional[int]
    criado_em: datetime
    logs_ia: List[LogChamadaResponse] = []

    class Config:
        from_attributes = True


class GeracaoResumoResponse(BaseModel):
    id: int
    numero_cnj: str
    numero_cnj_formatado: Optional[str]
    modelo_usado: Optional[str]
    tempo_processamento: Optional[int]
    criado_em: datetime
    total_logs: int = 0
    tem_erro: bool = False

    class Config:
        from_attributes = True


# ==========================================
# Endpoints de Histórico de Gerações
# ==========================================

@router.get("/geracoes", response_model=List[GeracaoResumoResponse])
async def listar_geracoes(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Lista histórico de gerações com resumo"""
    # PERFORMANCE: Usa subquery para contar logs e verificar erros em uma única query
    # Evita N+1 queries (antes: 1 + N queries, agora: 1 query)
    from sqlalchemy.orm import aliased

    # Subquery para contar logs por geração
    log_stats = db.query(
        LogChamadaIA.geracao_id,
        func.count(LogChamadaIA.id).label('total_logs'),
        func.sum(case((LogChamadaIA.sucesso == False, 1), else_=0)).label('total_erros')
    ).group_by(LogChamadaIA.geracao_id).subquery()

    # Query principal com join na subquery
    geracoes = db.query(
        GeracaoPedidoCalculo,
        func.coalesce(log_stats.c.total_logs, 0).label('total_logs'),
        func.coalesce(log_stats.c.total_erros, 0).label('total_erros')
    ).outerjoin(
        log_stats, GeracaoPedidoCalculo.id == log_stats.c.geracao_id
    ).order_by(
        desc(GeracaoPedidoCalculo.criado_em)
    ).offset(offset).limit(limit).all()

    resultado = []
    for g, total_logs, total_erros in geracoes:
        resultado.append(GeracaoResumoResponse(
            id=g.id,
            numero_cnj=g.numero_cnj,
            numero_cnj_formatado=g.numero_cnj_formatado,
            modelo_usado=g.modelo_usado,
            tempo_processamento=g.tempo_processamento,
            criado_em=g.criado_em,
            total_logs=total_logs or 0,
            tem_erro=(total_erros or 0) > 0
        ))

    return resultado


@router.get("/geracoes/{geracao_id}")
async def obter_geracao(
    geracao_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Obtém detalhes completos de uma geração, incluindo logs de IA"""
    geracao = db.query(GeracaoPedidoCalculo).filter(GeracaoPedidoCalculo.id == geracao_id).first()
    if not geracao:
        raise HTTPException(status_code=404, detail="Geração não encontrada")

    # Busca logs
    logs = db.query(LogChamadaIA).filter(
        LogChamadaIA.geracao_id == geracao_id
    ).order_by(LogChamadaIA.criado_em).all()

    return {
        "id": geracao.id,
        "numero_cnj": geracao.numero_cnj,
        "numero_cnj_formatado": geracao.numero_cnj_formatado,
        "dados_processo": geracao.dados_processo,
        "dados_agente1": geracao.dados_agente1,
        "dados_agente2": geracao.dados_agente2,
        "documentos_baixados": geracao.documentos_baixados,
        "conteudo_gerado": geracao.conteudo_gerado,
        "modelo_usado": geracao.modelo_usado,
        "tempo_processamento": geracao.tempo_processamento,
        "criado_em": geracao.criado_em.isoformat() if geracao.criado_em else None,
        "logs_ia": [
            {
                "id": log.id,
                "etapa": log.etapa,
                "descricao": log.descricao,
                "documento_id": log.documento_id,
                "prompt_enviado": log.prompt_enviado,
                "documento_texto": log.documento_texto,
                "resposta_ia": log.resposta_ia,
                "resposta_parseada": log.resposta_parseada,
                "modelo_usado": log.modelo_usado,
                "tempo_ms": log.tempo_ms,
                "sucesso": log.sucesso,
                "erro": log.erro,
                "criado_em": log.criado_em.isoformat() if log.criado_em else None
            }
            for log in logs
        ]
    }


@router.get("/geracoes/{geracao_id}/logs")
async def obter_logs_geracao(
    geracao_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Obtém apenas os logs de IA de uma geração"""
    logs = db.query(LogChamadaIA).filter(
        LogChamadaIA.geracao_id == geracao_id
    ).order_by(LogChamadaIA.criado_em).all()

    return [
        {
            "id": log.id,
            "etapa": log.etapa,
            "descricao": log.descricao,
            "documento_id": log.documento_id,
            "prompt_enviado": log.prompt_enviado,
            "documento_texto": log.documento_texto,
            "resposta_ia": log.resposta_ia,
            "resposta_parseada": log.resposta_parseada,
            "modelo_usado": log.modelo_usado,
            "tempo_ms": log.tempo_ms,
            "sucesso": log.sucesso,
            "erro": log.erro,
            "criado_em": log.criado_em.isoformat() if log.criado_em else None
        }
        for log in logs
    ]


@router.get("/logs/{log_id}")
async def obter_log_detalhado(
    log_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Obtém detalhes de um log específico"""
    log = db.query(LogChamadaIA).filter(LogChamadaIA.id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Log não encontrado")

    return {
        "id": log.id,
        "geracao_id": log.geracao_id,
        "etapa": log.etapa,
        "descricao": log.descricao,
        "documento_id": log.documento_id,
        "prompt_enviado": log.prompt_enviado,
        "documento_texto": log.documento_texto,
        "resposta_ia": log.resposta_ia,
        "resposta_parseada": log.resposta_parseada,
        "modelo_usado": log.modelo_usado,
        "tokens_entrada": log.tokens_entrada,
        "tokens_saida": log.tokens_saida,
        "tempo_ms": log.tempo_ms,
        "sucesso": log.sucesso,
        "erro": log.erro,
        "criado_em": log.criado_em.isoformat() if log.criado_em else None
    }


@router.get("/logs-recentes")
async def listar_logs_recentes(
    limit: int = Query(100, ge=1, le=500),
    etapa: Optional[str] = Query(None),
    apenas_erros: bool = Query(False),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Lista logs recentes, opcionalmente filtrados"""
    query = db.query(LogChamadaIA)

    if etapa:
        query = query.filter(LogChamadaIA.etapa == etapa)

    if apenas_erros:
        query = query.filter(LogChamadaIA.sucesso == False)

    logs = query.order_by(desc(LogChamadaIA.criado_em)).limit(limit).all()

    return [
        {
            "id": log.id,
            "geracao_id": log.geracao_id,
            "etapa": log.etapa,
            "descricao": log.descricao,
            "documento_id": log.documento_id,
            "sucesso": log.sucesso,
            "erro": log.erro,
            "tempo_ms": log.tempo_ms,
            "criado_em": log.criado_em.isoformat() if log.criado_em else None
        }
        for log in logs
    ]


@router.delete("/geracoes/{geracao_id}")
async def deletar_geracao(
    geracao_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Deleta uma geração e seus logs (apenas admin)"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Apenas administradores podem deletar gerações")

    geracao = db.query(GeracaoPedidoCalculo).filter(GeracaoPedidoCalculo.id == geracao_id).first()
    if not geracao:
        raise HTTPException(status_code=404, detail="Geração não encontrada")

    # Deleta logs primeiro
    db.query(LogChamadaIA).filter(LogChamadaIA.geracao_id == geracao_id).delete()

    # Deleta feedback se existir
    db.query(FeedbackPedidoCalculo).filter(FeedbackPedidoCalculo.geracao_id == geracao_id).delete()

    # Deleta geração
    db.delete(geracao)
    db.commit()

    return {"message": f"Geração {geracao_id} deletada com sucesso"}
