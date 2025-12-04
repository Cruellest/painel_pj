# sistemas/gerador_pecas/router.py
"""
Router do sistema Gerador de Peças Jurídicas
"""

import os
import re
import json
import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List, Dict
from sqlalchemy.orm import Session

from auth.dependencies import get_current_active_user
from auth.models import User
from database.connection import get_db
from sistemas.gerador_pecas.models import GeracaoPeca, FeedbackPeca
from sistemas.gerador_pecas.services import GeradorPecasService
from admin.models import ConfiguracaoIA, PromptConfig

router = APIRouter(tags=["Gerador de Peças"])

# Diretório temporário para arquivos DOCX
TEMP_DIR = os.path.join(os.path.dirname(__file__), 'temp_docs')
os.makedirs(TEMP_DIR, exist_ok=True)


class ProcessarProcessoRequest(BaseModel):
    numero_cnj: str
    tipo_peca: Optional[str] = None
    resposta_usuario: Optional[str] = None


class RegenerarDocxRequest(BaseModel):
    conteudo_editado: str  # JSON string do documento editado


class FeedbackRequest(BaseModel):
    geracao_id: int
    avaliacao: str  # 'correto', 'parcial', 'incorreto', 'erro_ia'
    nota: Optional[int] = None  # 1-5
    comentario: Optional[str] = None
    campos_incorretos: Optional[list] = None


@router.post("/processar")
async def processar_processo(
    req: ProcessarProcessoRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Processa um processo e gera a peça jurídica
    
    Returns:
        - Se status == "pergunta": {"pergunta": "...", "opcoes": [...]}
        - Se status == "sucesso": {"url_download": "...", "tipo_peca": "...", "conteudo_json": {...}}
        - Se status == "erro": {"mensagem": "..."}
    """
    try:
        # Normaliza o CNJ
        cnj_limpo = re.sub(r'\D', '', req.numero_cnj)
        
        # Busca configurações de IA
        config_modelo = db.query(ConfiguracaoIA).filter(
            ConfiguracaoIA.sistema == "gerador_pecas",
            ConfiguracaoIA.chave == "modelo_geracao"
        ).first()
        modelo = config_modelo.valor if config_modelo else "anthropic/claude-3.5-sonnet"
        
        # Busca prompt do sistema
        prompt_config = db.query(PromptConfig).filter(
            PromptConfig.sistema == "gerador_pecas",
            PromptConfig.tipo == "system",
            PromptConfig.is_active == True
        ).first()
        prompt_sistema = prompt_config.conteudo if prompt_config else None
        
        # Inicializa o serviço
        service = GeradorPecasService(
            modelo=modelo,
            prompt_sistema=prompt_sistema,
            db=db
        )
        
        # Processa o processo
        resultado = await service.processar_processo(
            numero_cnj=cnj_limpo,
            numero_cnj_formatado=req.numero_cnj,
            tipo_peca=req.tipo_peca,
            resposta_usuario=req.resposta_usuario,
            usuario_id=current_user.id
        )
        
        return resultado
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/regenerar")
async def regenerar_docx(
    req: RegenerarDocxRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Regenera o DOCX com conteúdo editado pelo usuário
    """
    try:
        conteudo_json = json.loads(req.conteudo_editado)
        
        service = GeradorPecasService(db=db)
        
        # Gera novo documento
        filename = f"{uuid.uuid4()}.docx"
        filepath = os.path.join(TEMP_DIR, filename)
        
        service.gerar_docx(conteudo_json, filepath)
        
        return {
            "status": "sucesso",
            "url_download": f"/gerador-pecas/api/download/{filename}"
        }
        
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=400,
            detail="JSON inválido"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao regenerar documento: {str(e)}"
        )


@router.get("/download/{filename}")
async def download_documento(
    filename: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user)
):
    """Download do documento gerado"""
    
    filepath = os.path.join(TEMP_DIR, filename)
    
    if not os.path.exists(filepath):
        raise HTTPException(
            status_code=404,
            detail="Documento não encontrado ou expirado"
        )
    
    return FileResponse(
        filepath,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"peca_judicial_{filename}"
    )


@router.get("/historico")
async def listar_historico(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Lista o histórico de gerações do usuário.
    """
    try:
        geracoes = db.query(GeracaoPeca).filter(
            GeracaoPeca.usuario_id == current_user.id
        ).order_by(GeracaoPeca.criado_em.desc()).limit(50).all()
        
        return [
            {
                "id": g.id,
                "cnj": g.numero_cnj_formatado or g.numero_cnj,
                "tipo_peca": g.tipo_peca,
                "data": g.criado_em.isoformat() if g.criado_em else None
            }
            for g in geracoes
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/historico/{geracao_id}")
async def excluir_historico(
    geracao_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Remove uma geração do histórico do usuário."""
    try:
        geracao = db.query(GeracaoPeca).filter(
            GeracaoPeca.id == geracao_id,
            GeracaoPeca.usuario_id == current_user.id
        ).first()
        
        if not geracao:
            raise HTTPException(status_code=404, detail="Geração não encontrada")
        
        db.delete(geracao)
        db.commit()
        
        return {"success": True, "message": "Geração removida do histórico"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# Endpoints de Feedback
# ============================================

@router.post("/feedback")
async def enviar_feedback(
    req: FeedbackRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Envia feedback sobre a peça gerada."""
    try:
        geracao = db.query(GeracaoPeca).filter(
            GeracaoPeca.id == req.geracao_id
        ).first()
        
        if not geracao:
            raise HTTPException(status_code=404, detail="Geração não encontrada")
        
        feedback_existente = db.query(FeedbackPeca).filter(
            FeedbackPeca.geracao_id == req.geracao_id
        ).first()
        
        if feedback_existente:
            feedback_existente.avaliacao = req.avaliacao
            feedback_existente.nota = req.nota
            feedback_existente.comentario = req.comentario
            feedback_existente.campos_incorretos = req.campos_incorretos
        else:
            feedback = FeedbackPeca(
                geracao_id=req.geracao_id,
                usuario_id=current_user.id,
                avaliacao=req.avaliacao,
                nota=req.nota,
                comentario=req.comentario,
                campos_incorretos=req.campos_incorretos
            )
            db.add(feedback)
        
        db.commit()
        
        return {"success": True, "message": "Feedback registrado com sucesso"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/feedback/{geracao_id}")
async def obter_feedback(
    geracao_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Obtém o feedback de uma geração específica."""
    try:
        feedback = db.query(FeedbackPeca).filter(
            FeedbackPeca.geracao_id == geracao_id
        ).first()
        
        if not feedback:
            return {"has_feedback": False}
        
        return {
            "has_feedback": True,
            "avaliacao": feedback.avaliacao,
            "nota": feedback.nota,
            "comentario": feedback.comentario,
            "campos_incorretos": feedback.campos_incorretos,
            "criado_em": feedback.criado_em.isoformat() if feedback.criado_em else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
