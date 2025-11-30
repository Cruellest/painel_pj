# sistemas/matriculas_confrontantes/router.py
"""
Router do sistema Matrículas Confrontantes
Convertido de Flask para FastAPI com integração ao portal unificado
"""

import os
import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from werkzeug.utils import secure_filename

from database.connection import get_db
from auth.dependencies import get_current_active_user, get_current_user_from_token_or_query
from auth.models import User
from config import UPLOAD_FOLDER, ALLOWED_EXTENSIONS, DEFAULT_MODEL, FULL_REPORT_MODEL

from sistemas.matriculas_confrontantes.models import Analise, Registro, LogSistema, FeedbackMatricula
from sistemas.matriculas_confrontantes.schemas import (
    FileInfo, FileUploadResponse, AnaliseResponse, AnaliseStatusResponse,
    ResultadoAnalise, RegistroCreate, RegistroUpdate, RegistroResponse,
    ConfigResponse, ApiKeyRequest, ModelRequest, RelatorioResponse, LogEntry,
    LoteConfrontante
)
from sistemas.matriculas_confrontantes.services import (
    allowed_file, get_file_type, get_file_size, load_api_key, save_api_key,
    result_to_dict, APP_VERSION
)

router = APIRouter(tags=["Matrículas Confrontantes"])


# Schema para feedback
class FeedbackMatriculaRequest(BaseModel):
    analise_id: int
    avaliacao: str  # 'correto', 'parcial', 'incorreto', 'erro_ia'
    comentario: Optional[str] = None
    campos_incorretos: Optional[list] = None


# Estado global (em memória - será migrado para DB posteriormente)
class AppState:
    def __init__(self):
        self.processing: Dict[str, bool] = {}
        self.api_key: str = load_api_key()
        self.model: str = DEFAULT_MODEL
        self.cached_report: Optional[str] = None
        self.cached_report_payload: Optional[str] = None
        self.cached_report_file_id: Optional[str] = None

state = AppState()

# Garante que a pasta de uploads existe
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)


# ============================================
# Funções auxiliares
# ============================================

def add_log(db: Session, message: str, status: str = "info"):
    """Adiciona um log ao banco de dados"""
    log = LogSistema(
        time=datetime.now().strftime("%H:%M:%S"),
        status=status,
        message=message,
        sistema="matriculas"
    )
    db.add(log)
    db.commit()
    return log


# ============================================
# API - Arquivos
# ============================================

@router.get("/files", response_model=List[FileInfo])
async def list_files(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Lista todos os arquivos importados"""
    files = []
    
    if UPLOAD_FOLDER.exists():
        for filepath in UPLOAD_FOLDER.iterdir():
            if filepath.is_file() and allowed_file(filepath.name):
                file_id = filepath.name
                
                # Verifica se foi analisado
                analise = db.query(Analise).filter(Analise.file_id == file_id).first()
                
                files.append(FileInfo(
                    id=file_id,
                    name=filepath.name,
                    path=str(filepath),
                    type=get_file_type(filepath.name),
                    size=get_file_size(filepath),
                    date=datetime.fromtimestamp(filepath.stat().st_mtime).strftime("%Y-%m-%d"),
                    analyzed=analise is not None
                ))
    
    return files


@router.get("/files/{file_id}/view")
async def view_file(
    file_id: str,
    current_user: User = Depends(get_current_user_from_token_or_query)
):
    """Serve arquivo para visualização (aceita token via header ou query string)"""
    filepath = UPLOAD_FOLDER / file_id
    
    if filepath.exists():
        media_type = 'application/pdf' if filepath.suffix.lower() == '.pdf' else None
        return FileResponse(filepath, media_type=media_type)
    
    raise HTTPException(status_code=404, detail="Arquivo não encontrado")


@router.get("/files/{file_id}/content")
async def get_file_content(
    file_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """Retorna o conteúdo do arquivo em base64"""
    filepath = UPLOAD_FOLDER / file_id
    
    if filepath.exists():
        import base64
        with open(filepath, "rb") as f:
            content = base64.b64encode(f.read()).decode("utf-8")
        
        return {
            "name": filepath.name,
            "type": get_file_type(filepath.name),
            "content": content
        }
    
    raise HTTPException(status_code=404, detail="Arquivo não encontrado")


@router.post("/files/upload", response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Upload de arquivo"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Nome de arquivo vazio")
    
    if not allowed_file(file.filename):
        raise HTTPException(status_code=400, detail="Tipo de arquivo não permitido")
    
    filename = secure_filename(file.filename)
    filepath = UPLOAD_FOLDER / filename
    
    # Salva o arquivo
    with open(filepath, "wb") as f:
        content = await file.read()
        f.write(content)
    
    add_log(db, f"Arquivo importado: {filename}", "success")
    
    return FileUploadResponse(
        success=True,
        file=FileInfo(
            id=filename,
            name=filename,
            path=str(filepath),
            type=get_file_type(filename),
            size=get_file_size(filepath),
            date=datetime.now().strftime("%Y-%m-%d"),
            analyzed=False
        )
    )


@router.delete("/files/{file_id}")
async def delete_file(
    file_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Exclui um arquivo"""
    filepath = UPLOAD_FOLDER / file_id
    
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    
    try:
        os.remove(filepath)
        
        # Remove análise associada
        db.query(Analise).filter(Analise.file_id == file_id).delete()
        db.commit()
        
        add_log(db, f"Arquivo excluído: {file_id}", "warning")
        
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# API - Análises
# ============================================

@router.get("/analyses", response_model=List[AnaliseResponse])
async def list_analyses(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Lista todas as análises salvas"""
    analises = db.query(Analise).all()
    
    result = []
    for analise in analises:
        # Verifica se o arquivo ainda existe
        filepath = UPLOAD_FOLDER / analise.file_id
        if not filepath.exists():
            db.delete(analise)
            continue
        
        # Extrai confrontantes do resultado JSON
        confrontantes = []
        if analise.resultado_json:
            lotes = analise.resultado_json.get("lotes_confrontantes", [])
            for lote in lotes:
                if isinstance(lote, dict):
                    confrontantes.append(LoteConfrontante(
                        descricao=lote.get("identificador", ""),
                        direcao=lote.get("direcao"),
                        proprietarios=lote.get("proprietarios", [])
                    ))
        
        result.append(AnaliseResponse(
            id=analise.file_id,
            matricula=analise.matricula_principal or "N/A",
            lote=analise.lote or "N/A",
            dataOperacao=analise.analisado_em.strftime("%d/%m/%Y") if analise.analisado_em else datetime.now().strftime("%d/%m/%Y"),
            tipo="Matrícula",
            proprietario=analise.proprietario or "N/A",
            estado="Analisado",
            confianca=int(analise.confianca * 100) if analise.confianca and analise.confianca <= 1 else int(analise.confianca or 0),
            confrontantes=confrontantes,
            num_confrontantes=len(confrontantes)
        ))
    
    db.commit()
    return result


@router.post("/analisar/{file_id}")
async def analisar_documento(
    file_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
    force: bool = False
):
    """Inicia análise de documento com IA"""
    filepath = UPLOAD_FOLDER / file_id
    
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    
    # Verifica se já existe análise salva (e não está forçando reanálise)
    if not force:
        analise_existente = db.query(Analise).filter(Analise.file_id == file_id).first()
        if analise_existente and analise_existente.resultado_json:
            add_log(db, f"Análise já existente recuperada: {file_id}", "info")
            return {"success": True, "message": "Análise já realizada", "cached": True}
    
    if not state.api_key:
        raise HTTPException(status_code=400, detail="API Key não configurada")
    
    if state.processing.get(file_id):
        raise HTTPException(status_code=400, detail="Análise já em andamento")
    
    state.processing[file_id] = True
    add_log(db, f"Iniciando análise: {file_id}", "info")
    
    # Executa análise em background
    background_tasks.add_task(
        run_analysis_task,
        file_id,
        str(filepath),
        state.model,
        state.api_key,
        current_user.id
    )
    
    return {"success": True, "message": "Análise iniciada"}


def run_analysis_task(file_id: str, file_path: str, model: str, api_key: str, user_id: int):
    """Task de análise executada em background"""
    from database.connection import SessionLocal
    from admin.models import ConfiguracaoIA
    
    db = SessionLocal()
    try:
        # Verifica se há modelo configurado no banco
        try:
            config_model = db.query(ConfiguracaoIA).filter(
                ConfiguracaoIA.sistema == "matriculas",
                ConfiguracaoIA.chave == "modelo"
            ).first()
            if config_model and config_model.valor:
                model = config_model.valor
        except Exception as e:
            print(f"Erro ao buscar modelo do banco: {e}")
        
        # Importa função de análise
        from sistemas.matriculas_confrontantes.services_ia import analyze_with_vision_llm
        
        result = analyze_with_vision_llm(model, file_path, api_key)
        result_dict = result_to_dict(result)
        
        # Extrai dados principais
        matricula_principal = result_dict.get("matricula_principal")
        proprietarios = result_dict.get("proprietarios_identificados", {})
        lotes = result_dict.get("lotes_confrontantes", [])
        confidence = result_dict.get("confidence", 0)
        
        # Extrai lote e proprietário da matrícula principal
        lote_principal = None
        proprietario_str = "N/A"
        for mat in result_dict.get("matriculas_encontradas", []):
            if isinstance(mat, dict) and mat.get("numero") == matricula_principal:
                lote_principal = mat.get("lote")
                # Busca proprietários diretamente da matrícula encontrada
                props_mat = mat.get("proprietarios", [])
                if props_mat:
                    proprietario_str = ", ".join(props_mat[:2])
                break
        
        # Se não encontrou proprietário na matrícula, tenta em proprietarios_identificados
        if proprietario_str == "N/A" and matricula_principal and matricula_principal in proprietarios:
            props = proprietarios[matricula_principal]
            if props:
                proprietario_str = ", ".join(props[:2])
        
        # Salva ou atualiza análise
        analise = db.query(Analise).filter(Analise.file_id == file_id).first()
        if not analise:
            analise = Analise(
                file_id=file_id,
                file_name=os.path.basename(file_path),
                file_path=file_path,
                usuario_id=user_id
            )
            db.add(analise)
        
        analise.matricula_principal = matricula_principal
        analise.resultado_json = result_dict
        analise.confianca = confidence if confidence else 0
        analise.lote = lote_principal
        analise.proprietario = proprietario_str
        analise.num_confrontantes = len(lotes)
        analise.analisado_em = datetime.utcnow()
        
        db.commit()
        
        # Limpa cache de relatório
        state.cached_report = None
        state.cached_report_payload = None
        state.cached_report_file_id = None
        
        add_log(db, f"Análise concluída: {file_id}", "success")
        
    except Exception as e:
        add_log(db, f"Erro na análise: {str(e)[:100]}", "error")
    finally:
        state.processing[file_id] = False
        db.close()


@router.get("/analisar/{file_id}/status", response_model=AnaliseStatusResponse)
async def status_analise(
    file_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Retorna status da análise"""
    processing = state.processing.get(file_id, False)
    analise = db.query(Analise).filter(Analise.file_id == file_id).first()
    
    return AnaliseStatusResponse(
        processing=processing,
        analyzed=analise is not None,
        has_result=analise is not None
    )


@router.get("/resultado/{file_id}")
async def get_resultado(
    file_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Retorna resultado completo da análise"""
    analise = db.query(Analise).filter(Analise.file_id == file_id).first()
    
    if not analise:
        raise HTTPException(status_code=404, detail="Resultado não encontrado")
    
    resultado = analise.resultado_json or {}
    resultado["analise_id"] = analise.id
    return resultado


# ============================================
# API - Registros
# ============================================

@router.get("/registros", response_model=List[RegistroResponse])
async def list_registros(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Lista todos os registros"""
    return db.query(Registro).all()


@router.post("/registros", response_model=RegistroResponse, status_code=201)
async def create_registro(
    registro_data: RegistroCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Cria um novo registro"""
    registro = Registro(
        matricula=registro_data.matricula,
        data_operacao=registro_data.dataOperacao or datetime.now().strftime("%d/%m/%Y"),
        tipo=registro_data.tipo,
        proprietario=registro_data.proprietario,
        estado=registro_data.estado,
        confianca=registro_data.confianca,
        children=registro_data.children,
        usuario_id=current_user.id
    )
    
    db.add(registro)
    db.commit()
    db.refresh(registro)
    
    add_log(db, f"Registro criado: Matrícula {registro.matricula}", "success")
    
    return registro


@router.get("/registros/{registro_id}", response_model=RegistroResponse)
async def get_registro(
    registro_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Retorna um registro específico"""
    registro = db.query(Registro).filter(Registro.id == registro_id).first()
    
    if not registro:
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    
    return registro


@router.put("/registros/{registro_id}", response_model=RegistroResponse)
async def update_registro(
    registro_id: int,
    registro_data: RegistroUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Atualiza um registro"""
    registro = db.query(Registro).filter(Registro.id == registro_id).first()
    
    if not registro:
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    
    update_data = registro_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "dataOperacao":
            setattr(registro, "data_operacao", value)
        else:
            setattr(registro, field, value)
    
    db.commit()
    db.refresh(registro)
    
    add_log(db, f"Registro atualizado: Matrícula {registro.matricula}", "info")
    
    return registro


@router.delete("/registros/{registro_id}")
async def delete_registro(
    registro_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Exclui um registro"""
    registro = db.query(Registro).filter(Registro.id == registro_id).first()
    
    if not registro:
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    
    matricula = registro.matricula
    db.delete(registro)
    db.commit()
    
    add_log(db, f"Registro excluído: Matrícula {matricula}", "warning")
    
    return {"success": True}


# ============================================
# API - Configuração
# ============================================

@router.get("/config", response_model=ConfigResponse)
async def get_config(current_user: User = Depends(get_current_active_user)):
    """Retorna configurações do sistema"""
    return ConfigResponse(
        version=APP_VERSION,
        model=state.model,
        hasApiKey=bool(state.api_key),
        has_api_key=bool(state.api_key),
        analysis_available=True
    )


@router.post("/config/apikey")
async def set_api_key(
    request: ApiKeyRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Define a API Key"""
    api_key = request.api_key.strip()
    
    if not api_key:
        raise HTTPException(status_code=400, detail="API Key vazia")
    
    state.api_key = api_key
    save_api_key(api_key)
    add_log(db, "API Key configurada", "success")
    
    return {"success": True}


@router.post("/config/model")
async def set_model(
    request: ModelRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Define o modelo de IA"""
    state.model = request.model
    add_log(db, f"Modelo alterado: {request.model}", "info")
    
    return {"success": True, "model": request.model}


# ============================================
# API - Logs
# ============================================

@router.get("/logs", response_model=List[LogEntry])
async def get_logs(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Retorna os logs do sistema"""
    logs = db.query(LogSistema).filter(
        LogSistema.sistema == "matriculas"
    ).order_by(LogSistema.id.desc()).limit(100).all()
    
    return [LogEntry(time=log.time, status=log.status, message=log.message) for log in logs]


@router.delete("/logs")
async def clear_logs(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Limpa os logs"""
    db.query(LogSistema).filter(LogSistema.sistema == "matriculas").delete()
    db.commit()
    
    add_log(db, "Logs limpos pelo usuário", "info")
    
    return {"success": True}


# ============================================
# API - Relatório
# ============================================

@router.post("/relatorio/gerar", response_model=RelatorioResponse)
async def gerar_relatorio(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Gera relatório completo usando IA"""
    # Busca última análise
    analise = db.query(Analise).order_by(Analise.id.desc()).first()
    
    if not analise:
        return RelatorioResponse(success=False, error="Nenhum resultado para gerar relatório")
    
    if not state.api_key:
        return RelatorioResponse(success=False, error="API Key não configurada")
    
    # Verifica cache
    if state.cached_report and state.cached_report_file_id == analise.file_id:
        add_log(db, "Retornando relatório em cache", "info")
        return RelatorioResponse(
            success=True,
            report=state.cached_report,
            payload=state.cached_report_payload,
            cached=True
        )
    
    try:
        from sistemas.matriculas_confrontantes.services_ia import (
            call_openrouter_text, build_full_report_prompt, get_system_prompt
        )
        
        # Monta payload
        payload = analise.resultado_json or {}
        payload["gerado_em"] = datetime.now().isoformat()
        payload["modelo_utilizado"] = FULL_REPORT_MODEL
        
        payload_json = json.dumps(payload, ensure_ascii=False, indent=2)
        
        # Gera relatório - usa prompt do banco se disponível
        prompt = build_full_report_prompt(payload_json)
        system_prompt = get_system_prompt()
        
        report_text = call_openrouter_text(
            model=FULL_REPORT_MODEL,
            system_prompt=system_prompt,
            user_prompt=prompt,
            temperature=0.2,
            max_tokens=3200,
            api_key=state.api_key
        )
        
        state.cached_report = report_text.strip()
        state.cached_report_payload = payload_json
        state.cached_report_file_id = analise.file_id
        
        add_log(db, "Relatório completo gerado", "success")
        
        return RelatorioResponse(
            success=True,
            report=state.cached_report,
            payload=payload_json,
            cached=False
        )
        
    except Exception as e:
        add_log(db, f"Erro ao gerar relatório: {str(e)[:100]}", "error")
        return RelatorioResponse(success=False, error=str(e))


# ============================================
# API - Feedback
# ============================================

@router.post("/feedback")
async def enviar_feedback_matricula(
    req: FeedbackMatriculaRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Envia feedback sobre a análise de matrícula.
    """
    try:
        # Verifica se a análise existe
        analise = db.query(Analise).filter(Analise.id == req.analise_id).first()
        
        if not analise:
            raise HTTPException(status_code=404, detail="Análise não encontrada")
        
        # Verifica se já existe feedback para esta análise
        feedback_existente = db.query(FeedbackMatricula).filter(
            FeedbackMatricula.analise_id == req.analise_id
        ).first()
        
        if feedback_existente:
            # Atualiza feedback existente
            feedback_existente.avaliacao = req.avaliacao
            feedback_existente.comentario = req.comentario
            feedback_existente.campos_incorretos = req.campos_incorretos
        else:
            # Cria novo feedback
            feedback = FeedbackMatricula(
                analise_id=req.analise_id,
                usuario_id=current_user.id,
                avaliacao=req.avaliacao,
                comentario=req.comentario,
                campos_incorretos=req.campos_incorretos
            )
            db.add(feedback)
        
        db.commit()
        add_log(db, f"Feedback registrado para análise {req.analise_id}: {req.avaliacao}", "info")
        
        return {"success": True, "message": "Feedback registrado com sucesso"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/feedback/{analise_id}")
async def obter_feedback_matricula(
    analise_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Obtém o feedback de uma análise específica."""
    try:
        feedback = db.query(FeedbackMatricula).filter(
            FeedbackMatricula.analise_id == analise_id
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
