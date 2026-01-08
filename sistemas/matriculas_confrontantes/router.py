# sistemas/matriculas_confrontantes/router.py
"""
Router do sistema Matrículas Confrontantes
Convertido de Flask para FastAPI com integração ao portal unificado
"""

import os
import json
import threading
import logging
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

from sistemas.matriculas_confrontantes.models import Analise, Registro, LogSistema, FeedbackMatricula, GrupoAnalise, ArquivoUpload
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

# Configura logger específico para matrículas
logger = logging.getLogger("matriculas")
logger.setLevel(logging.INFO)

# Handler para console com formato limpo
if not logger.handlers:
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter(
        '\033[36m[MATRÍCULAS]\033[0m %(asctime)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

router = APIRouter(tags=["Matrículas Confrontantes"])


# Schema para análise em lote
class AnaliseLoteRequest(BaseModel):
    file_ids: List[str]
    nome_grupo: Optional[str] = None
    matricula_principal: Optional[str] = None


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
    """Lista arquivos do usuário atual"""
    files = []
    
    # Busca arquivos do usuário no banco
    arquivos_usuario = db.query(ArquivoUpload).filter(
        ArquivoUpload.usuario_id == current_user.id
    ).all()
    
    for arquivo in arquivos_usuario:
        filepath = UPLOAD_FOLDER / arquivo.file_id
        
        # Verifica se o arquivo ainda existe no disco
        if filepath.exists():
            # Verifica se foi analisado
            analise = db.query(Analise).filter(Analise.file_id == arquivo.file_id).first()
            
            files.append(FileInfo(
                id=arquivo.file_id,
                name=arquivo.file_name,
                path=str(filepath),
                type=get_file_type(arquivo.file_name),
                size=get_file_size(filepath),
                date=arquivo.criado_em.strftime("%Y-%m-%d") if arquivo.criado_em else datetime.now().strftime("%Y-%m-%d"),
                analyzed=analise is not None
            ))
        else:
            # Arquivo não existe mais, remove do banco
            db.delete(arquivo)
    
    db.commit()
    return files


@router.get("/files/{file_id}/view")
async def view_file(
    file_id: str,
    current_user: User = Depends(get_current_user_from_token_or_query),
    db: Session = Depends(get_db)
):
    """Serve arquivo para visualização"""
    # Verifica se o arquivo pertence ao usuário
    arquivo = db.query(ArquivoUpload).filter(
        ArquivoUpload.file_id == file_id,
        ArquivoUpload.usuario_id == current_user.id
    ).first()
    
    if not arquivo:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    
    filepath = UPLOAD_FOLDER / file_id
    
    if filepath.exists():
        media_type = 'application/pdf' if filepath.suffix.lower() == '.pdf' else None
        return FileResponse(filepath, media_type=media_type)
    
    raise HTTPException(status_code=404, detail="Arquivo não encontrado no disco")


@router.get("/files/{file_id}/content")
async def get_file_content(
    file_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Retorna o conteúdo do arquivo em base64"""
    # Verifica se o arquivo pertence ao usuário
    arquivo = db.query(ArquivoUpload).filter(
        ArquivoUpload.file_id == file_id,
        ArquivoUpload.usuario_id == current_user.id
    ).first()
    
    if not arquivo:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    
    filepath = UPLOAD_FOLDER / file_id
    
    if filepath.exists():
        import base64
        with open(filepath, "rb") as f:
            content = base64.b64encode(f.read()).decode("utf-8")
        
        return {
            "name": arquivo.file_name,
            "type": get_file_type(arquivo.file_name),
            "content": content
        }
    
    raise HTTPException(status_code=404, detail="Arquivo não encontrado no disco")


@router.get("/files/check-duplicate/{filename}")
async def check_duplicate_file(
    filename: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Verifica se já existe um arquivo com o mesmo nome para o usuário"""
    original_name = secure_filename(filename)
    
    # Busca arquivo com mesmo nome do usuário
    arquivo_existente = db.query(ArquivoUpload).filter(
        ArquivoUpload.file_name == original_name,
        ArquivoUpload.usuario_id == current_user.id
    ).first()
    
    if arquivo_existente:
        return {
            "exists": True,
            "file_id": arquivo_existente.file_id,
            "file_name": arquivo_existente.file_name
        }
    
    return {"exists": False}


@router.post("/files/upload", response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
    replace: bool = False
):
    """Upload de arquivo. Se replace=True, substitui arquivo existente com mesmo nome."""
    import uuid
    
    if not file.filename:
        raise HTTPException(status_code=400, detail="Nome de arquivo vazio")
    
    if not allowed_file(file.filename):
        raise HTTPException(status_code=400, detail="Tipo de arquivo não permitido")
    
    original_name = secure_filename(file.filename)
    
    # Verifica se já existe arquivo com mesmo nome
    arquivo_existente = db.query(ArquivoUpload).filter(
        ArquivoUpload.file_name == original_name,
        ArquivoUpload.usuario_id == current_user.id
    ).first()
    
    if arquivo_existente:
        if not replace:
            # Retorna indicando que precisa confirmação
            return FileUploadResponse(
                success=False,
                error="duplicate",
                message=f"Já existe um arquivo '{original_name}'. Deseja substituir?"
            )
        else:
            # Remove arquivo antigo
            old_filepath = UPLOAD_FOLDER / arquivo_existente.file_id
            if old_filepath.exists():
                os.remove(old_filepath)
            
            # NÃO remove análise nem feedback - preserva histórico
            # A análise antiga ficará órfã mas com feedback preservado
            
            # Remove apenas registro do arquivo antigo
            db.delete(arquivo_existente)
            db.commit()
    
    # Gera ID único
    unique_id = f"{uuid.uuid4().hex[:8]}_{original_name}"
    filepath = UPLOAD_FOLDER / unique_id
    
    # Salva o arquivo
    content = await file.read()
    with open(filepath, "wb") as f:
        f.write(content)
    
    # Registra o arquivo no banco associado ao usuário
    arquivo_registro = ArquivoUpload(
        file_id=unique_id,
        file_name=original_name,
        usuario_id=current_user.id
    )
    db.add(arquivo_registro)
    db.commit()
    
    add_log(db, f"Arquivo importado: {original_name}", "success")
    
    return FileUploadResponse(
        success=True,
        file=FileInfo(
            id=unique_id,
            name=original_name,
            path=str(filepath),
            type=get_file_type(original_name),
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
    """Exclui um arquivo - PRESERVA análise e feedback para histórico"""
    # Verifica se o arquivo pertence ao usuário
    arquivo = db.query(ArquivoUpload).filter(
        ArquivoUpload.file_id == file_id,
        ArquivoUpload.usuario_id == current_user.id
    ).first()
    
    if not arquivo:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    
    filepath = UPLOAD_FOLDER / file_id
    
    try:
        # Remove arquivo do disco se existir
        if filepath.exists():
            os.remove(filepath)
        
        # Remove registro do arquivo
        db.delete(arquivo)
        
        # NÃO remove análise nem feedback - preserva para histórico de feedbacks
        # A análise ficará com file_id referenciando arquivo inexistente
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
        # Verifica se o arquivo ainda existe - mas NÃO deleta análise/feedback
        # Apenas marca como indisponível
        filepath = UPLOAD_FOLDER / analise.file_id
        arquivo_existe = filepath.exists()
        
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
            estado="Analisado" if arquivo_existe else "Arquivo Indisponível",
            confianca=int(analise.confianca * 100) if analise.confianca and analise.confianca <= 1 else int(analise.confianca or 0),
            confrontantes=confrontantes,
            num_confrontantes=len(confrontantes)
        ))
    
    return result


@router.post("/analisar/{file_id}")
async def analisar_documento(
    file_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
    force: bool = False,
    matricula_principal: Optional[str] = None
):
    """Inicia análise de documento com IA"""
    from admin.models import ConfiguracaoIA
    
    filepath = UPLOAD_FOLDER / file_id
    
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    
    # Verifica se já existe análise salva (e não está forçando reanálise)
    if not force:
        analise_existente = db.query(Analise).filter(Analise.file_id == file_id).first()
        if analise_existente and analise_existente.resultado_json:
            add_log(db, f"Análise já existente recuperada: {file_id}", "info")
            return {"success": True, "message": "Análise já realizada", "cached": True}
    
    # Busca API key da configuração global ou do ambiente
    import os
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    
    if not api_key:
        # Busca do banco (configuração global)
        config_api = db.query(ConfiguracaoIA).filter(
            ConfiguracaoIA.sistema == "global",
            ConfiguracaoIA.chave == "openrouter_api_key"
        ).first()
        api_key = config_api.valor if config_api and config_api.valor else None
    
    if not api_key:
        raise HTTPException(status_code=400, detail="API Key não configurada. Solicite ao administrador.")
    
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
        api_key,
        current_user.id,
        matricula_principal
    )
    
    return {"success": True, "message": "Análise iniciada"}


@router.post("/analisar-lote")
async def analisar_lote(
    request: AnaliseLoteRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Inicia análise conjunta de múltiplos documentos"""
    from admin.models import ConfiguracaoIA
    
    if not request.file_ids or len(request.file_ids) == 0:
        raise HTTPException(status_code=400, detail="Nenhum arquivo selecionado")
    
    # Verifica se todos os arquivos existem
    file_paths = []
    for file_id in request.file_ids:
        filepath = UPLOAD_FOLDER / file_id
        if not filepath.exists():
            raise HTTPException(status_code=404, detail=f"Arquivo não encontrado: {file_id}")
        file_paths.append(str(filepath))
    
    # Busca API key
    import os
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    
    if not api_key:
        config_api = db.query(ConfiguracaoIA).filter(
            ConfiguracaoIA.sistema == "global",
            ConfiguracaoIA.chave == "openrouter_api_key"
        ).first()
        api_key = config_api.valor if config_api and config_api.valor else None
    
    if not api_key:
        raise HTTPException(status_code=400, detail="API Key não configurada")
    
    # Cria grupo de análise
    grupo = GrupoAnalise(
        nome=request.nome_grupo or f"Análise de {len(request.file_ids)} documentos",
        status="processando",
        usuario_id=current_user.id
    )
    db.add(grupo)
    db.commit()
    db.refresh(grupo)
    
    # Marca arquivos como em processamento
    for file_id in request.file_ids:
        state.processing[file_id] = True
    
    add_log(db, f"Iniciando análise em lote: {len(request.file_ids)} arquivos (grupo {grupo.id})", "info")
    
    # Executa análise em background
    background_tasks.add_task(
        run_batch_analysis_task,
        grupo.id,
        request.file_ids,
        file_paths,
        state.model,
        api_key,
        current_user.id,
        request.matricula_principal
    )
    
    return {
        "success": True, 
        "message": f"Análise em lote iniciada com {len(request.file_ids)} arquivos",
        "grupo_id": grupo.id
    }


@router.get("/grupo/{grupo_id}/status")
async def status_grupo(
    grupo_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Retorna status de um grupo de análise"""
    grupo = db.query(GrupoAnalise).filter(GrupoAnalise.id == grupo_id).first()
    
    if not grupo:
        raise HTTPException(status_code=404, detail="Grupo não encontrado")
    
    analises = db.query(Analise).filter(Analise.grupo_id == grupo_id).all()
    
    return {
        "id": grupo.id,
        "nome": grupo.nome,
        "status": grupo.status,
        "total_arquivos": len(analises),
        "arquivos": [a.file_id for a in analises],
        "criado_em": grupo.criado_em.isoformat() if grupo.criado_em else None,
        "has_result": grupo.resultado_json is not None
    }


@router.get("/grupo/{grupo_id}/resultado")
async def resultado_grupo(
    grupo_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Retorna resultado consolidado de um grupo de análise"""
    grupo = db.query(GrupoAnalise).filter(GrupoAnalise.id == grupo_id).first()
    
    if not grupo:
        raise HTTPException(status_code=404, detail="Grupo não encontrado")
    
    if not grupo.resultado_json:
        raise HTTPException(status_code=404, detail="Resultado ainda não disponível")
    
    resultado = grupo.resultado_json.copy() if isinstance(grupo.resultado_json, dict) else {}
    
    # Adiciona ID da primeira análise do grupo para feedback
    primeira_analise = db.query(Analise).filter(Analise.grupo_id == grupo_id).first()
    if primeira_analise:
        resultado["analise_id"] = primeira_analise.id
    resultado["grupo_id"] = grupo_id
    
    return resultado


def run_batch_analysis_task(grupo_id: int, file_ids: List[str], file_paths: List[str], 
                            model: str, api_key: str, user_id: int, matricula_hint: Optional[str] = None):
    """Task de análise em lote - processa múltiplos PDFs em uma única chamada à IA"""
    from database.connection import SessionLocal
    from admin.models import ConfiguracaoIA
    from sistemas.matriculas_confrontantes.services_ia import (
        pdf_to_images, image_to_base64, call_openrouter_vision, 
        get_system_prompt, get_analysis_prompt, clean_json_response,
        get_config_from_db
    )
    import logging
    logger = logging.getLogger("matriculas_batch_task")
    
    logger.info(f"Iniciando análise em lote para grupo {grupo_id} com {len(file_ids)} arquivos")
    
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
            logger.warning(f"Erro ao buscar modelo do banco: {e}")
        
        # Coleta todas as imagens de todos os PDFs
        all_images_b64 = []
        file_page_map = {}  # Mapeia qual página pertence a qual arquivo
        
        for idx, (file_id, file_path) in enumerate(zip(file_ids, file_paths)):
            logger.info(f"Processando arquivo {idx+1}/{len(file_ids)}: {file_id}")
            
            ext = os.path.splitext(file_path.lower())[1]
            
            if ext == ".pdf":
                from PIL import Image
                images = pdf_to_images(file_path, max_pages=None)
            elif ext in [".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"]:
                from PIL import Image
                images = [Image.open(file_path)]
            else:
                logger.warning(f"Formato não suportado: {ext}")
                continue
            
            start_page = len(all_images_b64)
            for img in images:
                if img and hasattr(img, 'size'):
                    b64 = image_to_base64(img, max_size=1536)
                    if b64:
                        all_images_b64.append(b64)
            
            file_page_map[file_id] = {
                "start": start_page,
                "end": len(all_images_b64),
                "file_name": os.path.basename(file_path)
            }
        
        if not all_images_b64:
            raise ValueError("Não foi possível extrair imagens dos arquivos")
        
        logger.info(f"Total de {len(all_images_b64)} páginas extraídas de {len(file_ids)} arquivos")
        
        # Monta prompt especial para análise em lote
        system_prompt = get_system_prompt()
        base_prompt = get_analysis_prompt()
        
        # Adiciona hint da matrícula principal se fornecido
        hint_text = ""
        if matricula_hint:
            hint_text = f"\n\nATENÇÃO: A MATRÍCULA PRINCIPAL (OBJETO DA ANÁLISE) É: {matricula_hint}\nDê prioridade total a esta matrícula como sendo o imóvel central.\n"

        # Adiciona instruções específicas para análise em lote
        batch_instructions = f"""
ATENÇÃO: Esta é uma ANÁLISE CONJUNTA de {len(file_ids)} documentos que devem ser analisados como um único processo de usucapião.

Os documentos anexados são:
{chr(10).join([f"- {info['file_name']} (páginas {info['start']+1} a {info['end']})" for file_id, info in file_page_map.items()])}
{hint_text}
INSTRUÇÕES ESPECIAIS PARA ANÁLISE EM LOTE:
1. Identifique a MATRÍCULA PRINCIPAL (objeto do usucapião) entre todos os documentos
2. As demais matrículas são provavelmente dos CONFRONTANTES
3. Cruze as informações entre os documentos para validar confrontações
4. Se um lote confrontante menciona matrícula X, verifique se X está entre os documentos anexados
5. Consolide todas as informações em um único resultado estruturado

"""
        vision_prompt = batch_instructions + base_prompt
        
        # Obtém configurações do banco
        temperatura = float(get_config_from_db("matriculas", "temperatura_analise") or "0.1")
        max_tokens = int(get_config_from_db("matriculas", "max_tokens_analise") or "100000")
        modelo_analise = get_config_from_db("matriculas", "modelo_analise") or model
        
        # Faz chamada à IA com todas as imagens
        data = call_openrouter_vision(
            model=modelo_analise,
            system_prompt=system_prompt,
            user_prompt=vision_prompt,
            images_base64=all_images_b64,
            temperature=temperatura,
            max_tokens=max_tokens,
            api_key=api_key
        )
        
        content = data["choices"][0]["message"].get("content", "")
        clean_content = clean_json_response(content)
        
        try:
            parsed = json.loads(clean_content)
        except json.JSONDecodeError:
            parsed = {
                "matriculas_encontradas": [],
                "matricula_principal": None,
                "erro": "Falha ao processar resposta da IA"
            }
        
        # Adiciona metadados do lote
        parsed["analise_em_lote"] = True
        parsed["arquivos_analisados"] = [info["file_name"] for info in file_page_map.values()]
        parsed["total_paginas"] = len(all_images_b64)
        
        # Atualiza grupo com resultado
        grupo = db.query(GrupoAnalise).filter(GrupoAnalise.id == grupo_id).first()
        if grupo:
            grupo.resultado_json = parsed
            grupo.status = "concluido"
            grupo.confianca = parsed.get("confidence", 0)
        
        # Cria registros de análise para cada arquivo
        matricula_principal = parsed.get("matricula_principal")
        lotes = parsed.get("lotes_confrontantes", [])
        
        for file_id, info in file_page_map.items():
            analise = db.query(Analise).filter(Analise.file_id == file_id).first()
            if not analise:
                analise = Analise(
                    file_id=file_id,
                    file_name=info["file_name"],
                    usuario_id=user_id
                )
                db.add(analise)
            
            analise.grupo_id = grupo_id
            analise.resultado_json = parsed  # Mesmo resultado para todos
            analise.matricula_principal = matricula_principal
            analise.confianca = parsed.get("confidence", 0)
            analise.num_confrontantes = len(lotes)
            analise.analisado_em = datetime.utcnow()
        
        db.commit()
        logger.info(f"Análise em lote concluída para grupo {grupo_id}")
        
        # Limpa cache de relatório
        state.cached_report = None
        state.cached_report_payload = None
        state.cached_report_file_id = None
        
        add_log(db, f"Análise em lote concluída: {len(file_ids)} arquivos", "success")
        
    except Exception as e:
        import traceback
        logger.error(f"Erro na análise em lote {grupo_id}: {str(e)}")
        logger.error(traceback.format_exc())
        
        # Atualiza grupo com erro
        grupo = db.query(GrupoAnalise).filter(GrupoAnalise.id == grupo_id).first()
        if grupo:
            grupo.status = "erro"
            grupo.resultado_json = {"erro": str(e)}
        
        db.commit()
        add_log(db, f"Erro na análise em lote: {str(e)[:100]}", "error")
    finally:
        # Limpa flags de processamento
        for file_id in file_ids:
            state.processing[file_id] = False
        db.close()


def run_analysis_task(file_id: str, file_path: str, model: str, api_key: str, user_id: int, matricula_hint: Optional[str] = None):
    """Task de análise executada em background - não armazena o PDF, apenas o JSON"""
    from database.connection import SessionLocal
    from admin.models import ConfiguracaoIA
    
    file_name = os.path.basename(file_path)
    logger.info(f"📄 Iniciando análise: {file_name}")
    if matricula_hint:
        logger.info(f"   └─ Matrícula principal informada: {matricula_hint}")
    
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
            logger.warning(f"   ⚠️ Erro ao buscar modelo do banco: {e}")
        
        logger.info(f"   └─ Modelo: {model}")
        
        # Importa função de análise
        from sistemas.matriculas_confrontantes.services_ia import analyze_with_vision_llm
        
        logger.info(f"🤖 Enviando para IA...")
        result = analyze_with_vision_llm(model, file_path, api_key, matricula_hint)
        result_dict = result_to_dict(result)
        
        # Extrai dados principais
        matricula_principal = result_dict.get("matricula_principal")
        proprietarios = result_dict.get("proprietarios_identificados", {})
        lotes = result_dict.get("lotes_confrontantes", [])
        confidence = result_dict.get("confidence", 0)
        
        logger.info(f"✅ Análise concluída!")
        logger.info(f"   └─ Matrícula identificada: {matricula_principal or 'N/A'}")
        logger.info(f"   └─ Confrontantes encontrados: {len(lotes)}")
        logger.info(f"   └─ Confiança: {confidence}%")
        
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
        
        # Salva ou atualiza análise (não armazena o caminho do arquivo)
        analise = db.query(Analise).filter(Analise.file_id == file_id).first()
        if not analise:
            analise = Analise(
                file_id=file_id,
                file_name=os.path.basename(file_path),
                file_path=None,  # Não armazena o caminho do arquivo
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
        analise.file_path = None  # Limpa o caminho do arquivo se existia
        
        db.commit()
        logger.info(f"💾 Salvo no banco: ID={analise.id}")
        
        # Limpa cache de relatório
        state.cached_report = None
        state.cached_report_payload = None
        state.cached_report_file_id = None
        
        add_log(db, f"Análise concluída: {file_name}", "success")
        
        # PDF permanece no disco até o usuário excluir manualmente pelo frontend
        
    except Exception as e:
        import traceback
        logger.error(f"❌ Erro na análise: {str(e)}")
        logger.error(traceback.format_exc())
        db.rollback()
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
async def get_config(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Retorna configurações do sistema (API Key é gerenciada pelo admin)"""
    from admin.models import ConfiguracaoIA
    import os
    
    # Verifica se há API key configurada (ambiente ou banco)
    has_api_key = bool(os.getenv("OPENROUTER_API_KEY", ""))
    
    if not has_api_key:
        try:
            config_api = db.query(ConfiguracaoIA).filter(
                ConfiguracaoIA.sistema == "global",
                ConfiguracaoIA.chave == "openrouter_api_key"
            ).first()
            has_api_key = bool(config_api and config_api.valor)
        except:
            pass
    
    return ConfigResponse(
        version=APP_VERSION,
        model=state.model,
        hasApiKey=has_api_key,
        has_api_key=has_api_key,
        analysis_available=has_api_key
    )


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
    """Gera relatório completo usando IA ou retorna o salvo"""
    import logging
    logger = logging.getLogger("matriculas_router")
    
    # Busca última análise
    analise = db.query(Analise).order_by(Analise.id.desc()).first()
    
    if not analise:
        logger.error("Nenhuma análise encontrada no banco")
        return RelatorioResponse(success=False, error="Nenhum resultado para gerar relatório")
    
    logger.info(f"Análise encontrada: {analise.file_id}, resultado_json existe: {bool(analise.resultado_json)}")
    
    if not analise.resultado_json:
        return RelatorioResponse(success=False, error="Análise sem resultado JSON")
    
    # Se já tem relatório salvo, retorna ele
    if analise.relatorio_texto:
        logger.info(f"Retornando relatório salvo para {analise.file_id}")
        payload = analise.resultado_json or {}
        payload_json = json.dumps(payload, ensure_ascii=False, indent=2)
        return RelatorioResponse(
            success=True,
            report=analise.relatorio_texto,
            payload=payload_json,
            cached=True
        )
    
    if not state.api_key:
        # Tenta buscar API key do banco
        import os
        from admin.models import ConfiguracaoIA
        api_key = os.getenv("OPENROUTER_API_KEY", "")
        if not api_key:
            config = db.query(ConfiguracaoIA).filter(
                ConfiguracaoIA.sistema == "global",
                ConfiguracaoIA.chave == "openrouter_api_key"
            ).first()
            api_key = config.valor if config else None
        
        if not api_key:
            return RelatorioResponse(success=False, error="API Key não configurada")
        state.api_key = api_key
    
    try:
        from sistemas.matriculas_confrontantes.services_ia import (
            call_openrouter_text, build_full_report_prompt, get_system_prompt
        )
        
        # Monta payload
        payload = analise.resultado_json or {}
        payload["gerado_em"] = datetime.now().isoformat()
        
        # Obtém configurações do banco
        from sistemas.matriculas_confrontantes.services_ia import get_config_from_db
        
        modelo_relatorio = get_config_from_db("matriculas", "modelo_relatorio") or FULL_REPORT_MODEL
        temperatura = float(get_config_from_db("matriculas", "temperatura_relatorio") or "0.2")
        max_tokens = int(get_config_from_db("matriculas", "max_tokens_relatorio") or "3200")
        
        payload["modelo_utilizado"] = modelo_relatorio
        
        payload_json = json.dumps(payload, ensure_ascii=False, indent=2)
        
        # Gera relatório - usa prompt do banco se disponível
        prompt = build_full_report_prompt(payload_json)
        system_prompt = get_system_prompt()
        
        report_text = call_openrouter_text(
            model=modelo_relatorio,
            system_prompt=system_prompt,
            user_prompt=prompt,
            temperature=temperatura,
            max_tokens=max_tokens,
            api_key=state.api_key
        )
        
        report_text = report_text.strip()
        
        # Salva relatório e modelo usado no banco para não precisar regenerar
        analise.relatorio_texto = report_text
        analise.modelo_usado = modelo_relatorio
        db.commit()
        logger.info(f"Relatório salvo no banco para {analise.file_id}")
        
        state.cached_report = report_text
        state.cached_report_payload = payload_json
        state.cached_report_file_id = analise.file_id
        
        add_log(db, "Relatório completo gerado", "success")
        
        return RelatorioResponse(
            success=True,
            report=report_text,
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
