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
from sistemas.gerador_pecas.models import GeracaoPeca

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
    criado_em: datetime

    class Config:
        from_attributes = True


# ==========================================
# Endpoints de Histórico de Gerações
# ==========================================

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
    
    return geracoes


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
    return geracao


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
        "criado_em": geracao.criado_em.isoformat() if geracao.criado_em else None
    }
