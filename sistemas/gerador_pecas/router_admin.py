# sistemas/gerador_pecas/router_admin.py
"""
Router de administração do Gerador de Peças
- Visualização de prompts enviados
- Histórico detalhado de gerações
"""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime

from auth.dependencies import get_current_active_user
from auth.models import User
from database.connection import get_db
from utils.timezone import to_iso_utc
from sistemas.gerador_pecas.models import GeracaoPeca, VersaoPeca

router = APIRouter(prefix="/gerador-pecas-admin", tags=["Gerador de Peças - Admin"])


# ==========================================
# Schemas
# ==========================================

class GeracaoDetalhadaResponse(BaseModel):
    id: int
    numero_cnj: str
    numero_cnj_formatado: Optional[str]
    tipo_peca: Optional[str]
    modelo_usado: Optional[str]
    tempo_processamento: Optional[int]
    prompt_enviado: Optional[str]
    resumo_consolidado: Optional[str]
    conteudo_gerado: Optional[str] = None  # Markdown string
    historico_chat: Optional[List[Any]] = None  # Histórico de edições via chat
    modo_ativacao_agente2: Optional[str] = None  # 'fast_path', 'misto', 'llm'
    modulos_ativados_det: Optional[int] = None  # Ativados por regra determinística
    modulos_ativados_llm: Optional[int] = None  # Ativados por LLM
    criado_em: datetime

    class Config:
        from_attributes = True


# ==========================================
# Endpoints de Histórico de Gerações
# ==========================================

def _safe_get_attr(obj, attr, default=None):
    """Obtém atributo de forma segura, retornando default se coluna não existe no banco"""
    try:
        return getattr(obj, attr, default)
    except Exception:
        return default


def _geracao_to_dict(geracao: GeracaoPeca) -> dict:
    """Converte GeracaoPeca para dict, tratando colunas que podem não existir"""
    return {
        "id": geracao.id,
        "numero_cnj": geracao.numero_cnj,
        "numero_cnj_formatado": geracao.numero_cnj_formatado,
        "tipo_peca": geracao.tipo_peca,
        "modelo_usado": geracao.modelo_usado,
        "tempo_processamento": geracao.tempo_processamento,
        "prompt_enviado": geracao.prompt_enviado,
        "resumo_consolidado": geracao.resumo_consolidado,
        "conteudo_gerado": geracao.conteudo_gerado,
        "historico_chat": geracao.historico_chat,
        # Colunas que podem não existir em produção (migration pendente)
        "modo_ativacao_agente2": _safe_get_attr(geracao, 'modo_ativacao_agente2'),
        "modulos_ativados_det": _safe_get_attr(geracao, 'modulos_ativados_det'),
        "modulos_ativados_llm": _safe_get_attr(geracao, 'modulos_ativados_llm'),
        "criado_em": geracao.criado_em,
    }


@router.get("/geracoes", response_model=List[GeracaoDetalhadaResponse])
async def listar_geracoes(
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Lista histórico de gerações com detalhes"""
    geracoes = db.query(GeracaoPeca).order_by(
        GeracaoPeca.criado_em.desc()
    ).offset(offset).limit(limit).all()

    return [_geracao_to_dict(g) for g in geracoes]


@router.get("/geracoes/{geracao_id}", response_model=GeracaoDetalhadaResponse)
async def obter_geracao(
    geracao_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Obtém detalhes de uma geração específica"""
    geracao = db.query(GeracaoPeca).filter(GeracaoPeca.id == geracao_id).first()
    if not geracao:
        raise HTTPException(status_code=404, detail="Geração não encontrada")
    return _geracao_to_dict(geracao)


@router.get("/geracoes/{geracao_id}/prompt")
async def obter_prompt_geracao(
    geracao_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Obtém apenas o prompt enviado de uma geração"""
    geracao = db.query(GeracaoPeca).filter(GeracaoPeca.id == geracao_id).first()
    if not geracao:
        raise HTTPException(status_code=404, detail="Geração não encontrada")
    
    return {
        "id": geracao.id,
        "numero_cnj": geracao.numero_cnj_formatado or geracao.numero_cnj,
        "tipo_peca": geracao.tipo_peca,
        "prompt_enviado": geracao.prompt_enviado,
        "resumo_consolidado": geracao.resumo_consolidado,
        "criado_em": to_iso_utc(geracao.criado_em)
    }


@router.get("/geracoes/{geracao_id}/versoes")
async def listar_versoes_geracao(
    geracao_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Lista todas as versões de uma geração"""
    geracao = db.query(GeracaoPeca).filter(GeracaoPeca.id == geracao_id).first()
    if not geracao:
        raise HTTPException(status_code=404, detail="Geração não encontrada")

    versoes = db.query(VersaoPeca).filter(
        VersaoPeca.geracao_id == geracao_id
    ).order_by(VersaoPeca.numero_versao.desc()).all()

    return {
        "geracao_id": geracao_id,
        "total_versoes": len(versoes),
        "versoes": [
            {
                "id": v.id,
                "numero_versao": v.numero_versao,
                "tipo_alteracao": v.origem,  # Campo correto do modelo
                "descricao": v.descricao_alteracao,  # Campo correto do modelo
                "conteudo_markdown": v.conteudo,  # Campo correto do modelo
                "criado_em": to_iso_utc(v.criado_em)
            }
            for v in versoes
        ]
    }


@router.get("/geracoes/{geracao_id}/versoes/{versao_id}")
async def obter_versao_geracao(
    geracao_id: int,
    versao_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Obtém detalhes de uma versão específica"""
    versao = db.query(VersaoPeca).filter(
        VersaoPeca.id == versao_id,
        VersaoPeca.geracao_id == geracao_id
    ).first()

    if not versao:
        raise HTTPException(status_code=404, detail="Versão não encontrada")

    return {
        "id": versao.id,
        "geracao_id": versao.geracao_id,
        "numero_versao": versao.numero_versao,
        "tipo_alteracao": versao.origem,  # Campo correto do modelo
        "descricao": versao.descricao_alteracao,  # Campo correto do modelo
        "conteudo_markdown": versao.conteudo,  # Campo correto do modelo
        "criado_em": to_iso_utc(versao.criado_em)
    }
