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
from admin.models import ConfiguracaoIA

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
    default_model: str = "google/gemini-3-flash-preview"


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


@router.get("/test-tjms")
async def test_tjms_connection(current_user: User = Depends(get_current_active_user)):
    """
    Testa conexão com o TJ-MS (endpoint de debug - REQUER ADMIN).
    SECURITY: Endpoint protegido por autenticação e role admin.
    """
    # SECURITY: Apenas admins podem acessar endpoints de debug
    if current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Acesso restrito a administradores"
        )

    import requests
    from config import TJ_WSDL_URL, TJ_WS_USER, TJ_WS_PASS

    # URL direta do TJ-MS para teste
    TJ_DIRECT_URL = "https://esaj.tjms.jus.br/mniws/servico-intercomunicacao-2.2.2/intercomunicacao"

    # SECURITY: Não expõe credenciais completas
    result = {
        "proxy_url": TJ_WSDL_URL,
        "direct_url": TJ_DIRECT_URL,
        "user_configured": bool(TJ_WS_USER),
        "pass_configured": bool(TJ_WS_PASS),
    }
    
    # Teste via proxy (GET)
    try:
        r = requests.get(TJ_WSDL_URL, timeout=15)
        result["proxy_status"] = r.status_code
        result["proxy_ok"] = r.status_code == 200
    except requests.exceptions.Timeout:
        result["proxy_status"] = "timeout"
        result["proxy_ok"] = False
    except requests.exceptions.RequestException as e:
        result["proxy_status"] = str(e)[:100]
        result["proxy_ok"] = False
    
    # Teste direto ao TJ-MS
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/xml, application/soap+xml",
        }
        r = requests.get(TJ_DIRECT_URL + "?wsdl", headers=headers, timeout=15)
        result["direct_status"] = r.status_code
        result["direct_ok"] = r.status_code == 200
    except requests.exceptions.Timeout:
        result["direct_status"] = "timeout"
        result["direct_ok"] = False
    except requests.exceptions.RequestException as e:
        result["direct_status"] = str(e)[:100]
        result["direct_ok"] = False
    
    # Teste SOAP via proxy
    if result.get("proxy_ok"):
        try:
            envelope = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:ser="http://www.cnj.jus.br/servico-intercomunicacao-2.2.2/"
                  xmlns:tip="http://www.cnj.jus.br/tipos-servico-intercomunicacao-2.2.2">
    <soapenv:Header/>
    <soapenv:Body>
        <ser:consultarProcesso>
            <tip:idConsultante>{TJ_WS_USER}</tip:idConsultante>
            <tip:senhaConsultante>{TJ_WS_PASS}</tip:senhaConsultante>
            <tip:numeroProcesso>00000000000000000000</tip:numeroProcesso>
            <tip:movimentos>false</tip:movimentos>
            <tip:incluirDocumentos>false</tip:incluirDocumentos>
        </ser:consultarProcesso>
    </soapenv:Body>
</soapenv:Envelope>"""
            
            r = requests.post(TJ_WSDL_URL, data=envelope.encode('utf-8'), timeout=30, headers={
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": ""
            })
            result["soap_status"] = r.status_code
            result["soap_preview"] = r.text[:300] if r.text else "empty"
            
        except requests.exceptions.Timeout:
            result["soap_status"] = "timeout"
        except requests.exceptions.RequestException as e:
            result["soap_status"] = str(e)[:100]
    
    return result


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
    import logging
    logger = logging.getLogger("assistencia_router")
    
    try:
        # Normaliza o CNJ (remove caracteres não numéricos)
        cnj_limpo = re.sub(r'\D', '', req.cnj)
        logger.info(f"Consultando processo: {cnj_limpo}")
        
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
        logger.info("Iniciando full_flow...")
        try:
            dados, relatorio = full_flow(req.cnj, req.model)
        except RuntimeError as e:
            error_msg = str(e)
            if "Timeout" in error_msg or "timeout" in error_msg:
                raise HTTPException(
                    status_code=503, 
                    detail="O servidor do TJ-MS não está respondendo. Tente novamente em alguns minutos."
                )
            raise HTTPException(status_code=500, detail=error_msg)
        
        logger.info("full_flow concluído com sucesso")
        
        # Busca o modelo real usado (configurado no banco)
        config_modelo = db.query(ConfiguracaoIA).filter(
            ConfiguracaoIA.sistema == "assistencia_judiciaria",
            ConfiguracaoIA.chave == "modelo_relatorio"
        ).first()
        modelo_real = config_modelo.valor if config_modelo else req.model
        
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
        consulta.modelo_usado = modelo_real
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
        import traceback
        logger.error(f"Erro na consulta: {str(e)}")
        logger.error(traceback.format_exc())
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
    """Remove uma consulta do histórico do usuário - PRESERVA feedbacks."""
    try:
        consulta = db.query(ConsultaProcesso).filter(
            ConsultaProcesso.id == consulta_id,
            ConsultaProcesso.usuario_id == current_user.id
        ).first()
        
        if not consulta:
            raise HTTPException(status_code=404, detail="Consulta não encontrada")
        
        # Verifica se tem feedback associado - se tiver, não permite excluir
        from sistemas.assistencia_judiciaria.models import FeedbackAnalise
        feedback = db.query(FeedbackAnalise).filter(FeedbackAnalise.consulta_id == consulta_id).first()
        if feedback:
            raise HTTPException(
                status_code=400, 
                detail="Não é possível excluir consulta que possui feedback registrado"
            )
        
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
