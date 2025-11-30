# sistemas/assistencia_judiciaria/router.py
"""
Router do sistema Assistência Judiciária
Adaptado para integração com o portal unificado
"""

import os
import re
import json
import tempfile
from datetime import datetime
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session

from auth.dependencies import get_current_active_user
from auth.models import User
from database.connection import get_db
from sistemas.assistencia_judiciaria.core.logic import full_flow, DEFAULT_MODEL
from sistemas.assistencia_judiciaria.core.document import markdown_to_docx, docx_to_pdf
from sistemas.assistencia_judiciaria.models import ConsultaProcesso, FeedbackAnalise

router = APIRouter(tags=["Assistência Judiciária"])

# Caminho do arquivo de configurações
SETTINGS_FILE = os.path.join(os.path.dirname(__file__), 'settings.json')


class ConsultationRequest(BaseModel):
    cnj: str
    model: str = DEFAULT_MODEL
    force: bool = False  # Forçar nova consulta mesmo se já existir cache


class FeedbackRequest(BaseModel):
    consulta_id: int
    avaliacao: str  # 'correto', 'parcial', 'incorreto', 'erro_ia'
    comentario: Optional[str] = None
    campos_incorretos: Optional[list] = None


class DocumentRequest(BaseModel):
    markdown_text: str
    cnj: str
    format: str  # 'docx' or 'pdf'


class SettingsRequest(BaseModel):
    openrouter_api_key: str = ""
    default_model: str = "google/gemini-2.5-flash"


def load_settings():
    """Carrega as configurações do arquivo JSON"""
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {
        "openrouter_api_key": os.getenv("OPENROUTER_API_KEY", ""),
        "default_model": DEFAULT_MODEL
    }


def save_settings(settings: dict):
    """Salva as configurações no arquivo JSON"""
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, indent=2)


@router.get("/settings")
async def get_settings(current_user: User = Depends(get_current_active_user)):
    """Retorna as configurações atuais (com API key mascarada)"""
    settings = load_settings()
    api_key = settings.get("openrouter_api_key", "")
    if api_key and len(api_key) > 10:
        masked_key = api_key[:8] + "*" * (len(api_key) - 12) + api_key[-4:]
    else:
        masked_key = api_key
    return {
        "openrouter_api_key": masked_key,
        "default_model": settings.get("default_model", DEFAULT_MODEL)
    }


@router.post("/settings")
async def update_settings(
    req: SettingsRequest,
    current_user: User = Depends(get_current_active_user)
):
    """Atualiza as configurações"""
    try:
        current_settings = load_settings()
        
        # Se a nova key contém asteriscos, mantém a key atual
        if "*" in req.openrouter_api_key:
            new_key = current_settings.get("openrouter_api_key", "")
        else:
            new_key = req.openrouter_api_key
        
        new_settings = {
            "openrouter_api_key": new_key,
            "default_model": req.default_model
        }
        
        save_settings(new_settings)
        
        # Atualiza a variável de ambiente para a sessão atual
        if new_key:
            os.environ["OPENROUTER_API_KEY"] = new_key
        
        return {"message": "Configurações salvas com sucesso"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/consultar")
async def consultar_processo(
    req: ConsultationRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Consulta um processo no TJ-MS e gera relatório com IA.
    
    - **cnj**: Número do processo no formato CNJ
    - **model**: Modelo de IA a ser usado (opcional)
    - **force**: Forçar nova consulta mesmo se já existir cache
    """
    try:
        # Normaliza o CNJ (remove caracteres não numéricos)
        cnj_limpo = re.sub(r'\D', '', req.cnj)
        
        # Verifica se já existe consulta no cache (e não está forçando)
        if not req.force:
            consulta_existente = db.query(ConsultaProcesso).filter(
                ConsultaProcesso.cnj == cnj_limpo
            ).first()
            
            if consulta_existente and consulta_existente.relatorio:
                return {
                    "consulta_id": consulta_existente.id,
                    "dados": consulta_existente.dados_json or {},
                    "relatorio": consulta_existente.relatorio,
                    "cached": True,
                    "consultado_em": consulta_existente.consultado_em.isoformat() if consulta_existente.consultado_em else None
                }
        
        # Faz nova consulta
        dados, relatorio = full_flow(req.cnj, req.model)
        
        # Salva ou atualiza no banco
        consulta = db.query(ConsultaProcesso).filter(
            ConsultaProcesso.cnj == cnj_limpo
        ).first()
        
        if not consulta:
            consulta = ConsultaProcesso(
                cnj=cnj_limpo,
                cnj_formatado=req.cnj,
                usuario_id=current_user.id
            )
            db.add(consulta)
        
        consulta.dados_json = dados
        consulta.relatorio = relatorio
        consulta.modelo_usado = req.model
        consulta.atualizado_em = datetime.utcnow()
        
        db.commit()
        db.refresh(consulta)
        
        return {
            "consulta_id": consulta.id,
            "dados": dados,
            "relatorio": relatorio,
            "cached": False
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/historico")
async def listar_historico(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Lista o histórico de consultas do usuário.
    Retorna as últimas 50 consultas ordenadas por data.
    """
    try:
        consultas = db.query(ConsultaProcesso).filter(
            ConsultaProcesso.usuario_id == current_user.id
        ).order_by(ConsultaProcesso.consultado_em.desc()).limit(50).all()
        
        return [
            {
                "id": c.id,
                "cnj": c.cnj_formatado or c.cnj,
                "classe": c.dados_json.get("classeProcessual") if c.dados_json else None,
                "data": c.consultado_em.isoformat() if c.consultado_em else None
            }
            for c in consultas
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/historico/{consulta_id}")
async def excluir_historico(
    consulta_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Remove uma consulta do histórico do usuário."""
    try:
        consulta = db.query(ConsultaProcesso).filter(
            ConsultaProcesso.id == consulta_id,
            ConsultaProcesso.usuario_id == current_user.id
        ).first()
        
        if not consulta:
            raise HTTPException(status_code=404, detail="Consulta não encontrada")
        
        db.delete(consulta)
        db.commit()
        
        return {"success": True, "message": "Consulta removida do histórico"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate-doc")
async def generate_document(
    req: DocumentRequest, 
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user)
):
    """
    Gera documento DOCX ou PDF a partir do relatório markdown.
    
    - **markdown_text**: Texto do relatório em markdown
    - **cnj**: Número do processo
    - **format**: 'docx' ou 'pdf'
    """
    try:
        # Criar arquivo temporário
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{req.format}") as tmp:
            output_path = tmp.name

        if req.format == 'docx':
            result = markdown_to_docx(req.markdown_text, output_path, req.cnj)
        elif req.format == 'pdf':
            # Para PDF, primeiro gera DOCX depois converte
            docx_path = output_path.replace('.pdf', '.docx')
            res_docx = markdown_to_docx(req.markdown_text, docx_path, req.cnj)
            if res_docx is not True:
                raise Exception(f"Falha ao gerar DOCX intermediário: {res_docx}")
            
            result = docx_to_pdf(docx_path, output_path)
            # Limpar DOCX intermediário
            if os.path.exists(docx_path):
                os.remove(docx_path)
        else:
            raise HTTPException(status_code=400, detail="Formato não suportado. Use 'docx' ou 'pdf'.")

        if result is not True:
            raise Exception(f"Falha na geração do documento: {result}")

        # Agendar remoção do arquivo após envio
        background_tasks.add_task(os.remove, output_path)

        filename = f"relatorio_{req.cnj.replace('.', '').replace('-', '')}.{req.format}"
        return FileResponse(
            output_path, 
            media_type='application/octet-stream', 
            filename=filename
        )

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
    """
    Envia feedback sobre a análise da IA.
    
    - **consulta_id**: ID da consulta
    - **avaliacao**: 'correto', 'parcial', 'incorreto', 'erro_ia'
    - **comentario**: Comentário opcional
    - **campos_incorretos**: Lista de campos que estavam incorretos (opcional)
    """
    try:
        # Verifica se a consulta existe
        consulta = db.query(ConsultaProcesso).filter(
            ConsultaProcesso.id == req.consulta_id
        ).first()
        
        if not consulta:
            raise HTTPException(status_code=404, detail="Consulta não encontrada")
        
        # Verifica se já existe feedback para esta consulta
        feedback_existente = db.query(FeedbackAnalise).filter(
            FeedbackAnalise.consulta_id == req.consulta_id
        ).first()
        
        if feedback_existente:
            # Atualiza feedback existente
            feedback_existente.avaliacao = req.avaliacao
            feedback_existente.comentario = req.comentario
            feedback_existente.campos_incorretos = req.campos_incorretos
        else:
            # Cria novo feedback
            feedback = FeedbackAnalise(
                consulta_id=req.consulta_id,
                usuario_id=current_user.id,
                avaliacao=req.avaliacao,
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


@router.get("/feedback/{consulta_id}")
async def obter_feedback(
    consulta_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Obtém o feedback de uma consulta específica."""
    try:
        feedback = db.query(FeedbackAnalise).filter(
            FeedbackAnalise.consulta_id == consulta_id
        ).first()
        
        if not feedback:
            return {"has_feedback": False}
        
        return {
            "has_feedback": True,
            "avaliacao": feedback.avaliacao,
            "comentario": feedback.comentario,
            "campos_incorretos": feedback.campos_incorretos,
            "criado_em": feedback.criado_em.isoformat() if feedback.criado_em else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/feedback/pendentes/count")
async def contar_feedbacks_pendentes(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Conta quantas consultas do usuário ainda não têm feedback."""
    try:
        from sqlalchemy import and_, not_, exists
        
        # Consultas do usuário sem feedback
        count = db.query(ConsultaProcesso).filter(
            ConsultaProcesso.usuario_id == current_user.id,
            ConsultaProcesso.relatorio.isnot(None),
            ~exists().where(FeedbackAnalise.consulta_id == ConsultaProcesso.id)
        ).count()
        
        return {"pendentes": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
