# sistemas/prestacao_contas/router_admin.py
"""
Router de administração do sistema de Prestação de Contas

Endpoints para debug e visualização de histórico:
- GET /geracoes - Lista todas as gerações
- GET /geracoes/{id} - Detalhes com logs de IA
- GET /logs/{geracao_id} - Logs de chamadas de IA
- DELETE /geracoes/{id} - Deleta geração

Autor: LAB/PGE-MS
"""

import logging
from typing import Optional, List, Any

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime

from auth.dependencies import get_current_active_user
from auth.models import User
from database.connection import get_db
from sistemas.prestacao_contas.models import GeracaoAnalise, LogChamadaIAPrestacao, FeedbackPrestacao

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/api/prestacao-admin", tags=["Prestação de Contas - Admin"])


# =====================================================
# Schemas
# =====================================================

class GeracaoAdminResponse(BaseModel):
    id: int
    numero_cnj: str
    numero_cnj_formatado: Optional[str] = None
    usuario_id: Optional[int] = None
    status: str
    parecer: Optional[str] = None
    fundamentacao: Optional[str] = None
    modelo_usado: Optional[str] = None
    tempo_processamento_ms: Optional[int] = None
    erro: Optional[str] = None
    criado_em: datetime

    # Debug
    prompt_analise: Optional[str] = None
    resposta_ia_bruta: Optional[str] = None

    class Config:
        from_attributes = True


class LogChamadaResponse(BaseModel):
    id: int
    etapa: str
    descricao: Optional[str] = None
    modelo_usado: Optional[str] = None
    tokens_entrada: Optional[int] = None
    tokens_saida: Optional[int] = None
    tempo_ms: Optional[int] = None
    sucesso: bool
    erro: Optional[str] = None
    criado_em: datetime

    # Dados completos
    prompt_enviado: Optional[str] = None
    documento_id: Optional[str] = None
    resposta_ia: Optional[str] = None
    resposta_parseada: Optional[Any] = None

    class Config:
        from_attributes = True


class GeracaoComLogsResponse(GeracaoAdminResponse):
    logs_ia: List[LogChamadaResponse] = []
    total_feedbacks: int = 0

    # Dados de debug adicionais
    extrato_subconta_texto: Optional[str] = None
    peticao_inicial_texto: Optional[str] = None
    peticao_prestacao_texto: Optional[str] = None
    documentos_anexos: Optional[Any] = None
    dados_processo_xml: Optional[Any] = None


# =====================================================
# Endpoints
# =====================================================

@router.get("/geracoes", response_model=List[GeracaoAdminResponse])
async def listar_geracoes(
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0),
    status: Optional[str] = Query(default=None),
    parecer: Optional[str] = Query(default=None),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Lista todas as gerações (apenas admin)"""

    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores")

    query = db.query(GeracaoAnalise)

    if status:
        query = query.filter(GeracaoAnalise.status == status)

    if parecer:
        query = query.filter(GeracaoAnalise.parecer == parecer)

    geracoes = query.order_by(
        GeracaoAnalise.criado_em.desc()
    ).offset(offset).limit(limit).all()

    return geracoes


@router.get("/geracoes/{geracao_id}", response_model=GeracaoComLogsResponse)
async def obter_geracao_admin(
    geracao_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Obtém detalhes de uma geração com logs de IA"""

    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores")

    geracao = db.query(GeracaoAnalise).filter(
        GeracaoAnalise.id == geracao_id
    ).first()

    if not geracao:
        raise HTTPException(status_code=404, detail="Geração não encontrada")

    # Busca logs de IA
    logs = db.query(LogChamadaIAPrestacao).filter(
        LogChamadaIAPrestacao.geracao_id == geracao_id
    ).order_by(LogChamadaIAPrestacao.criado_em).all()

    # Conta feedbacks
    total_feedbacks = db.query(FeedbackPrestacao).filter(
        FeedbackPrestacao.geracao_id == geracao_id
    ).count()

    return GeracaoComLogsResponse(
        id=geracao.id,
        numero_cnj=geracao.numero_cnj,
        numero_cnj_formatado=geracao.numero_cnj_formatado,
        usuario_id=geracao.usuario_id,
        status=geracao.status,
        parecer=geracao.parecer,
        fundamentacao=geracao.fundamentacao,
        modelo_usado=geracao.modelo_usado,
        tempo_processamento_ms=geracao.tempo_processamento_ms,
        erro=geracao.erro,
        criado_em=geracao.criado_em,
        prompt_analise=geracao.prompt_analise,
        resposta_ia_bruta=geracao.resposta_ia_bruta,
        extrato_subconta_texto=geracao.extrato_subconta_texto,
        peticao_inicial_texto=geracao.peticao_inicial_texto,
        peticao_prestacao_texto=geracao.peticao_prestacao_texto,
        documentos_anexos=geracao.documentos_anexos,
        dados_processo_xml=geracao.dados_processo_xml,
        logs_ia=[
            LogChamadaResponse(
                id=log.id,
                etapa=log.etapa,
                descricao=log.descricao,
                modelo_usado=log.modelo_usado,
                tokens_entrada=log.tokens_entrada,
                tokens_saida=log.tokens_saida,
                tempo_ms=log.tempo_ms,
                sucesso=log.sucesso,
                erro=log.erro,
                criado_em=log.criado_em,
                prompt_enviado=log.prompt_enviado,
                documento_id=log.documento_id,
                resposta_ia=log.resposta_ia,
                resposta_parseada=log.resposta_parseada,
            )
            for log in logs
        ],
        total_feedbacks=total_feedbacks,
    )


@router.get("/logs/{geracao_id}", response_model=List[LogChamadaResponse])
async def listar_logs_geracao(
    geracao_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Lista logs de chamadas de IA de uma geração"""

    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores")

    logs = db.query(LogChamadaIAPrestacao).filter(
        LogChamadaIAPrestacao.geracao_id == geracao_id
    ).order_by(LogChamadaIAPrestacao.criado_em).all()

    return logs


@router.delete("/geracoes/{geracao_id}")
async def deletar_geracao(
    geracao_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Deleta uma geração e seus logs"""

    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores")

    geracao = db.query(GeracaoAnalise).filter(
        GeracaoAnalise.id == geracao_id
    ).first()

    if not geracao:
        raise HTTPException(status_code=404, detail="Geração não encontrada")

    # Deleta logs relacionados
    db.query(LogChamadaIAPrestacao).filter(
        LogChamadaIAPrestacao.geracao_id == geracao_id
    ).delete()

    # Deleta feedbacks relacionados
    db.query(FeedbackPrestacao).filter(
        FeedbackPrestacao.geracao_id == geracao_id
    ).delete()

    # Deleta geração
    db.delete(geracao)
    db.commit()

    return {"sucesso": True, "mensagem": "Geração deletada com sucesso"}


@router.get("/estatisticas")
async def obter_estatisticas(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Obtém estatísticas do sistema"""

    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores")

    total_geracoes = db.query(GeracaoAnalise).count()
    total_concluidas = db.query(GeracaoAnalise).filter(
        GeracaoAnalise.status == "concluido"
    ).count()
    total_erros = db.query(GeracaoAnalise).filter(
        GeracaoAnalise.status == "erro"
    ).count()

    # Por parecer
    favoraveis = db.query(GeracaoAnalise).filter(
        GeracaoAnalise.parecer == "favoravel"
    ).count()
    desfavoraveis = db.query(GeracaoAnalise).filter(
        GeracaoAnalise.parecer == "desfavoravel"
    ).count()
    duvidas = db.query(GeracaoAnalise).filter(
        GeracaoAnalise.parecer == "duvida"
    ).count()

    # Feedbacks
    total_feedbacks = db.query(FeedbackPrestacao).count()
    feedbacks_corretos = db.query(FeedbackPrestacao).filter(
        FeedbackPrestacao.avaliacao == "correto"
    ).count()

    return {
        "total_geracoes": total_geracoes,
        "total_concluidas": total_concluidas,
        "total_erros": total_erros,
        "pareceres": {
            "favoravel": favoraveis,
            "desfavoravel": desfavoraveis,
            "duvida": duvidas,
        },
        "feedbacks": {
            "total": total_feedbacks,
            "corretos": feedbacks_corretos,
            "taxa_acerto": round(feedbacks_corretos / total_feedbacks * 100, 1) if total_feedbacks > 0 else 0,
        }
    }
