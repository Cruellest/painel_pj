# sistemas/gerador_pecas/router.py
"""
Router do sistema Gerador de Peças Jurídicas
"""

import os
import re
import json
import uuid
import asyncio
from datetime import datetime
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, Query, UploadFile, File, Form
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, AsyncGenerator
import fitz  # PyMuPDF para extração de texto de PDFs
fitz.TOOLS.mupdf_warnings(False)  # Suprime warnings de imagens JPEG2000 corrompidas
from sqlalchemy.orm import Session

from auth.dependencies import get_current_active_user, get_current_user_from_token_or_query
from auth.models import User
from database.connection import get_db
from utils.timezone import to_iso_utc
from services.text_normalizer import text_normalizer
from services.performance_tracker import (
    create_tracker, get_tracker, mark, record_chunk, PerformanceTracker
)
from services.config_cache import config_cache
from admin.services_request_perf import log_request_perf
from sistemas.gerador_pecas.models import GeracaoPeca, FeedbackPeca, VersaoPeca
from sistemas.gerador_pecas.services import GeradorPecasService
from sistemas.gerador_pecas.orquestrador_agentes import consolidar_dados_extracao
from sistemas.gerador_pecas.versoes import (
    criar_versao_inicial,
    criar_nova_versao,
    obter_versoes,
    obter_versao_detalhada,
    comparar_versoes,
    restaurar_versao
)
from admin.models import ConfiguracaoIA, PromptConfig
from admin.models_prompt_groups import PromptGroup, PromptSubgroup

router = APIRouter(tags=["Gerador de Peças"])

# Diretório temporário para arquivos DOCX
TEMP_DIR = os.path.join(os.path.dirname(__file__), 'temp_docs')
os.makedirs(TEMP_DIR, exist_ok=True)


def _limpar_cnj(numero_cnj: str) -> str:
    """
    Limpa número CNJ removendo formatação e sufixos.
    
    Exemplos:
        - 0804330-09.2024.8.12.0017 -> 08043300920248120017
        - 0804330-09.2024.8.12.0017/50003 -> 08043300920248120017
    """
    # Remove sufixo após barra (ex: /50003)
    if '/' in numero_cnj:
        numero_cnj = numero_cnj.split('/')[0]
    # Remove caracteres não-dígitos
    return re.sub(r'\D', '', numero_cnj)

def _listar_grupos_permitidos(current_user: User, db: Session) -> List[PromptGroup]:
    query = db.query(PromptGroup).filter(PromptGroup.active == True)
    if current_user.role == "admin":
        return query.order_by(PromptGroup.order, PromptGroup.name).all()

    group_ids = set(current_user.allowed_group_ids or [])
    if current_user.default_group_id:
        group_ids.add(current_user.default_group_id)

    if not group_ids:
        return []

    return query.filter(PromptGroup.id.in_(group_ids)).order_by(PromptGroup.order, PromptGroup.name).all()


def _resolver_grupo_e_subcategorias(
    current_user: User,
    db: Session,
    group_id: Optional[int],
    subcategoria_ids: Optional[List[int]]
):
    from admin.models_prompt_groups import PromptSubcategoria

    grupos = _listar_grupos_permitidos(current_user, db)
    if not grupos:
        raise HTTPException(status_code=400, detail="Usuario sem grupo de prompts.")

    if group_id is None:
        if len(grupos) == 1:
            grupo = grupos[0]
        else:
            raise HTTPException(status_code=400, detail="Selecione o grupo de prompts.")
    else:
        grupo = db.query(PromptGroup).filter(
            PromptGroup.id == group_id,
            PromptGroup.active == True
        ).first()
        if not grupo:
            raise HTTPException(status_code=400, detail="Grupo invalido ou inativo.")
        if current_user.role != "admin":
            allowed_ids = {g.id for g in grupos}
            if group_id not in allowed_ids:
                raise HTTPException(status_code=403, detail="Usuario sem acesso ao grupo selecionado.")

    subcategoria_ids_normalized = []
    if subcategoria_ids:
        for item in subcategoria_ids:
            try:
                value = int(item)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="Subcategorias invalidas.")
            if value not in subcategoria_ids_normalized:
                subcategoria_ids_normalized.append(value)

        if subcategoria_ids_normalized:
            subcategorias = db.query(PromptSubcategoria).filter(
                PromptSubcategoria.id.in_(subcategoria_ids_normalized),
                PromptSubcategoria.group_id == grupo.id,
                PromptSubcategoria.active == True
            ).all()
            if len(subcategorias) != len(subcategoria_ids_normalized):
                raise HTTPException(status_code=400, detail="Subcategorias invalidas para o grupo selecionado.")

    return grupo, subcategoria_ids_normalized


def _parse_subcategoria_ids_form(subcategoria_ids_raw: Optional[str]) -> Optional[List[int]]:
    if not subcategoria_ids_raw:
        return None

    try:
        payload = json.loads(subcategoria_ids_raw)
        if isinstance(payload, list):
            return payload
    except Exception:
        pass

    try:
        return [int(value) for value in subcategoria_ids_raw.split(",") if value.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="Subcategorias invalidas.")
# Armazena estado de processamento em memória (para SSE)
_processamento_status = {}


class ProcessarProcessoRequest(BaseModel):
    numero_cnj: str
    tipo_peca: Optional[str] = None
    resposta_usuario: Optional[str] = None
    observacao_usuario: Optional[str] = None  # Observações do usuário para incluir no prompt
    group_id: Optional[int] = None
    subcategoria_ids: Optional[List[int]] = None


class ExportarDocxRequest(BaseModel):
    """Request para exportar markdown para DOCX"""
    markdown: str  # Conteúdo markdown da minuta
    numero_cnj: Optional[str] = None  # Número do processo para nome do arquivo
    tipo_peca: Optional[str] = None  # Tipo da peça para nome do arquivo


class FeedbackRequest(BaseModel):
    geracao_id: int
    avaliacao: str  # 'correto', 'parcial', 'incorreto', 'erro_ia'
    nota: Optional[int] = None  # 1-5
    comentario: Optional[str] = None
    campos_incorretos: Optional[list] = None


class EditarMinutaRequest(BaseModel):
    """Request para edição de minuta via chat"""
    minuta_atual: str  # Markdown da minuta atual
    mensagem: str  # Pedido de alteração do usuário
    historico: Optional[List[Dict]] = None  # Histórico de mensagens anteriores
    tipo_peca: Optional[str] = None  # Tipo de peça atual (para busca de argumentos)


class BuscarArgumentosRequest(BaseModel):
    """Request para buscar argumentos na base de conhecimento"""
    query: str  # Texto de busca
    tipo_peca: Optional[str] = None  # Tipo de peça para filtrar regras específicas
    limit: int = 5  # Número máximo de resultados


@router.get("/tipos-peca")
async def listar_tipos_peca(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Lista os tipos de peças disponíveis baseado nos prompts modulares ativos.
    Retorna apenas os tipos de peça que têm prompt configurado no banco.

    Retorna também `permite_auto` que indica se a detecção automática está habilitada.
    Quando `permite_auto=false`, o usuário DEVE selecionar um tipo de peça manualmente.
    """
    from admin.models_prompts import PromptModulo
    from admin.models import ConfiguracaoIA

    # Busca módulos do tipo "peca" que estão ativos
    modulos_peca = db.query(PromptModulo).filter(
        PromptModulo.tipo == "peca",
        PromptModulo.ativo == True
    ).order_by(PromptModulo.ordem).all()

    tipos = []
    for modulo in modulos_peca:
        tipos.append({
            "valor": modulo.nome,    # Identificador único: "contestacao", "agravo_instrumento", etc.
            "label": modulo.titulo,  # Ex: "Contestação", "Agravo de Instrumento"
            "descricao": modulo.conteudo[:100] + "..." if len(modulo.conteudo) > 100 else modulo.conteudo
        })

    # Verifica flag de detecção automática
    config_auto = db.query(ConfiguracaoIA).filter(
        ConfiguracaoIA.sistema == "gerador_pecas",
        ConfiguracaoIA.chave == "enable_auto_piece_detection"
    ).first()

    # Por padrão, não permite auto se a flag não existir (fail-safe)
    permite_auto = False
    if config_auto and config_auto.valor:
        permite_auto = config_auto.valor.lower() == "true"

    return {
        "tipos": tipos,
        "permite_auto": permite_auto
    }


@router.post("/buscar-argumentos")
async def buscar_argumentos(
    req: BuscarArgumentosRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Busca argumentos jurídicos relevantes na base de conhecimento.

    Usado pelo chatbot de edição para encontrar módulos de conteúdo
    que podem ser inseridos na minuta baseado na mensagem do usuário.

    Busca em:
    - Título do módulo
    - Condição de ativação
    - Regras determinísticas
    - Categoria/subcategoria
    """
    from sistemas.gerador_pecas.services_busca_argumentos import buscar_argumentos_relevantes

    print(f"\n{'='*60}")
    print(f"[ENDPOINT] 🔎 Busca de argumentos solicitada")
    print(f"[ENDPOINT] 👤 Usuário: {current_user.username}")
    print(f"{'='*60}")

    argumentos = buscar_argumentos_relevantes(
        db=db,
        query=req.query,
        tipo_peca=req.tipo_peca,
        limit=req.limit
    )

    print(f"[ENDPOINT] ✅ Retornando {len(argumentos)} argumento(s)\n")

    return {
        "query": req.query,
        "tipo_peca": req.tipo_peca,
        "total": len(argumentos),
        "argumentos": argumentos
    }


@router.get("/grupos-disponiveis")
async def listar_grupos_disponiveis(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    grupos = _listar_grupos_permitidos(current_user, db)
    default_group_id = current_user.default_group_id
    if default_group_id and not any(g.id == default_group_id for g in grupos):
        default_group_id = grupos[0].id if len(grupos) == 1 else None

    return {
        "grupos": [
            {"id": grupo.id, "nome": grupo.name, "slug": grupo.slug}
            for grupo in grupos
        ],
        "default_group_id": default_group_id,
        "requires_selection": len(grupos) > 1
    }


@router.get("/grupos/{group_id}/subgrupos")
async def listar_subgrupos_por_grupo(
    group_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Lista subgrupos operacionais de um grupo.

    Subgrupos sao recortes operacionais (ex: Conhecimento, Cumprimento).
    """
    grupo, _ = _resolver_grupo_e_subcategorias(current_user, db, group_id, [])

    subgrupos = db.query(PromptSubgroup).filter(
        PromptSubgroup.group_id == grupo.id,
        PromptSubgroup.active == True
    ).order_by(PromptSubgroup.order, PromptSubgroup.name).all()

    return {
        "subgrupos": [
            {"id": subgrupo.id, "nome": subgrupo.name, "slug": subgrupo.slug}
            for subgrupo in subgrupos
        ]
    }


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
        cnj_limpo = _limpar_cnj(req.numero_cnj)

        grupo, subcategoria_ids = _resolver_grupo_e_subcategorias(
            current_user,
            db,
            req.group_id,
            req.subcategoria_ids
        )
        
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
        # O prompt_sistema não é mais usado diretamente - agora vem dos módulos
        
        # Inicializa o serviço
        service = GeradorPecasService(
            modelo=modelo,
            db=db,
            group_id=grupo.id,
            subcategoria_ids=subcategoria_ids
        )
        
        # Processa o processo
        resultado = await service.processar_processo(
            numero_cnj=cnj_limpo,
            numero_cnj_formatado=cnj_limpo,
            tipo_peca=req.tipo_peca,
            resposta_usuario=req.resposta_usuario,
            usuario_id=current_user.id
        )
        
        return resultado
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/processar-stream")
async def processar_processo_stream(
    req: ProcessarProcessoRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Processa um processo com streaming SSE para atualização em tempo real.
    Retorna eventos conforme cada agente processa.

    Se tipo_peca não for especificado e a flag `enable_auto_piece_detection` estiver habilitada,
    o Agente 2 detecta automaticamente qual tipo de peça é mais adequado.

    Se a flag estiver desabilitada, tipo_peca é OBRIGATÓRIO.
    """
    from admin.models import ConfiguracaoIA

    # Verifica se detecção automática está habilitada (com cache)
    permite_auto = config_cache.get_auto_detection_enabled(db)

    # Validação: se auto-detecção está desabilitada, tipo_peca é obrigatório
    if not permite_auto and not req.tipo_peca:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tipo de peça é obrigatório. Selecione o tipo de peça antes de gerar."
        )

    grupo, subcategoria_ids = _resolver_grupo_e_subcategorias(
        current_user,
        db,
        req.group_id,
        req.subcategoria_ids
    )
    group_id = grupo.id

    # Cria tracker de performance para esta request
    tracker = create_tracker(
        request_id=str(uuid.uuid4())[:8],
        sistema="gerador_pecas",
        route="/processar-stream"
    )
    tracker.mark("auth_done")

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            cnj_limpo = _limpar_cnj(req.numero_cnj)
            tracker.set_metadata("numero_cnj", cnj_limpo)

            # Evento inicial
            yield f"data: {json.dumps({'tipo': 'inicio', 'mensagem': 'Iniciando processamento...', 'request_id': tracker.request_id})}\n\n"
            
            # Busca configurações (com cache)
            tracker.mark("load_config_start")
            modelo = config_cache.get_config(
                "gerador_pecas",
                "modelo_geracao",
                db,
                default="google/gemini-2.5-pro-preview-05-06"
            )
            tracker.mark("load_config_done", modelo=modelo)
            tracker.set_metadata("modelo", modelo)

            # Inicializa o serviço
            service = GeradorPecasService(
                modelo=modelo,
                db=db,
                group_id=group_id,
                subcategoria_ids=subcategoria_ids
            )
            
            # Se tem orquestrador, processa com eventos
            if service.orquestrador:
                orq = service.orquestrador
                
                # Determina tipo de peça inicial (se fornecido manualmente)
                tipo_peca_inicial = req.tipo_peca or req.resposta_usuario
                print(f"[ROUTER] tipo_peca_inicial: {tipo_peca_inicial}")
                print(f"[ROUTER] group_id: {group_id}, subcategoria_ids: {subcategoria_ids}")

                # Se tipo de peça foi escolhido manualmente, configura filtro de categorias ANTES do Agente 1
                if tipo_peca_inicial:
                    try:
                        from sistemas.gerador_pecas.filtro_categorias import FiltroCategoriasDocumento
                        filtro = FiltroCategoriasDocumento(db)
                        if filtro.tem_configuracao():
                            codigos = filtro.get_codigos_permitidos(tipo_peca_inicial)
                            codigos_primeiro = filtro.get_codigos_primeiro_documento(tipo_peca_inicial)
                            if codigos:
                                orq.agente1.atualizar_codigos_permitidos(codigos, codigos_primeiro)
                                yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'Filtro ativado: {len(codigos)} categorias para {tipo_peca_inicial}'})}\n\n"
                    except Exception as e:
                        import traceback
                        print(f"[ROUTER] ERRO ao carregar filtro de categorias: {e}")
                        print(f"[ROUTER] Traceback: {traceback.format_exc()}")
                
                # Agente 1: Coletor TJ-MS
                print(f"[ROUTER] >>> Iniciando Agente 1...")
                tracker.mark("agente1_start")
                yield f"data: {json.dumps({'tipo': 'agente', 'agente': 1, 'status': 'ativo', 'mensagem': 'Baixando documentos do TJ-MS...'})}\n\n"

                resultado_agente1 = await orq.agente1.coletar_e_resumir(cnj_limpo)

                tracker.mark("agente1_done", docs=resultado_agente1.documentos_analisados)
                print(f"[ROUTER] <<< Agente 1 finalizado")
                print(f"[ROUTER] Agente 1 - erro: {resultado_agente1.erro}")
                print(f"[ROUTER] Agente 1 - total_documentos: {resultado_agente1.total_documentos}")
                print(f"[ROUTER] Agente 1 - documentos_analisados: {resultado_agente1.documentos_analisados}")
                print(f"[ROUTER] Agente 1 - resumo tamanho: {len(resultado_agente1.resumo_consolidado)} chars")

                if resultado_agente1.erro:
                    print(f"[ROUTER] Agente 1 retornou erro: {resultado_agente1.erro}")
                    yield f"data: {json.dumps({'tipo': 'agente', 'agente': 1, 'status': 'erro', 'mensagem': resultado_agente1.erro})}\n\n"
                    yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': resultado_agente1.erro})}\n\n"
                    return

                yield f"data: {json.dumps({'tipo': 'agente', 'agente': 1, 'status': 'concluido', 'mensagem': f'{resultado_agente1.documentos_analisados} documentos processados'})}\n\n"
                
                # Usa o tipo de peça inicial (já determinado acima)
                tipo_peca = tipo_peca_inicial
                
                # Agente 2: Detector de Módulos (e tipo de peça se necessário)
                # Variável para controlar se foi modo automático
                modo_automatico = False
                resumo_para_geracao = resultado_agente1.resumo_consolidado
                
                if not tipo_peca:
                    modo_automatico = True
                    yield f"data: {json.dumps({'tipo': 'agente', 'agente': 2, 'status': 'ativo', 'mensagem': 'Detectando tipo de peça automaticamente...'})}\n\n"
                    
                    # Detecta o tipo de peça via IA
                    deteccao_tipo = await orq.agente2.detectar_tipo_peca(resultado_agente1.resumo_consolidado)
                    tipo_peca = deteccao_tipo.get("tipo_peca")
                    
                    if tipo_peca:
                        confianca = deteccao_tipo.get("confianca", "media")
                        justificativa = deteccao_tipo.get("justificativa", "")
                        yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'Tipo detectado: {tipo_peca} (confiança: {confianca})'})}\n\n"
                    else:
                        # Fallback se não conseguiu detectar
                        tipo_peca = "contestacao"
                        yield f"data: {json.dumps({'tipo': 'info', 'mensagem': 'Não foi possível detectar automaticamente. Usando: contestação'})}\n\n"
                
                # No modo automático, após detectar o tipo, filtra os resumos
                if modo_automatico and tipo_peca:
                    try:
                        codigos_tipo = filtro.get_codigos_permitidos(tipo_peca)
                        if codigos_tipo:
                            yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'Filtrando resumos para {tipo_peca}: {len(codigos_tipo)} categorias'})}\n\n"
                            
                            # Usa o método do agente para filtrar e remontar o resumo
                            resumo_para_geracao = orq.agente1.filtrar_e_remontar_resumo(
                                resultado_agente1,
                                codigos_tipo
                            )
                    except Exception as e:
                        print(f"Aviso: Erro ao filtrar resumos no modo automático: {e}")
                        # Continua com o resumo completo
                
                tracker.mark("agente2_start")
                yield f"data: {json.dumps({'tipo': 'agente', 'agente': 2, 'status': 'ativo', 'mensagem': 'Analisando e ativando prompts...'})}\n\n"

                # Extrai dados das variáveis dos resumos JSON para avaliação determinística
                dados_extracao = consolidar_dados_extracao(resultado_agente1)
                print(f"[ROUTER] dados_extracao consolidados: {len(dados_extracao)} variáveis")

                # Passa dados de extração para permitir fast path determinístico
                resultado_agente2 = await orq._executar_agente2(
                    resumo_para_geracao,
                    tipo_peca,
                    dados_processo=resultado_agente1.dados_brutos,
                    dados_extracao=dados_extracao
                )

                tracker.mark("agente2_done", modulos=len(resultado_agente2.modulos_ids) if not resultado_agente2.erro else 0)

                if resultado_agente2.erro:
                    yield f"data: {json.dumps({'tipo': 'agente', 'agente': 2, 'status': 'erro', 'mensagem': resultado_agente2.erro})}\n\n"
                    yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': resultado_agente2.erro})}\n\n"
                    return
                
                yield f"data: {json.dumps({'tipo': 'agente', 'agente': 2, 'status': 'concluido', 'mensagem': f'{len(resultado_agente2.modulos_ids)} módulos ativados'})}\n\n"
                
                # Agente 3: Gerador (COM STREAMING REAL)
                tracker.mark("prompt_build_start")
                yield f"data: {json.dumps({'tipo': 'agente', 'agente': 3, 'status': 'ativo', 'mensagem': 'Gerando peça jurídica com IA...'})}\n\n"

                # Log se há observação do usuário
                if req.observacao_usuario:
                    yield f"data: {json.dumps({'tipo': 'info', 'mensagem': 'Observações do usuário serão consideradas na geração'})}\n\n"

                # Usa versão STREAMING do Agente 3 para TTFT rápido
                tracker.mark("prompt_build_done")
                tracker.mark("llm_call_start")
                resultado_agente3 = None
                first_chunk_received = False
                async for event in orq._executar_agente3_stream(
                    resumo_consolidado=resumo_para_geracao,
                    prompt_sistema=resultado_agente2.prompt_sistema,
                    prompt_peca=resultado_agente2.prompt_peca,
                    prompt_conteudo=resultado_agente2.prompt_conteudo,
                    tipo_peca=tipo_peca,
                    observacao_usuario=req.observacao_usuario
                ):
                    if event["tipo"] == "chunk":
                        # Registra primeiro token (TTFT)
                        if not first_chunk_received:
                            tracker.mark("first_token")
                            first_chunk_received = True

                        # Registra chunk para estatisticas de streaming
                        tracker.record_chunk(event['content'])

                        # Envia chunk de texto para o frontend em tempo real
                        yield f"data: {json.dumps({'tipo': 'geracao_chunk', 'content': event['content']})}\n\n"

                    elif event["tipo"] == "done":
                        tracker.mark("last_token")
                        resultado_agente3 = event["resultado"]

                    elif event["tipo"] == "error":
                        tracker.mark("last_token")
                        resultado_agente3 = event["resultado"]
                        yield f"data: {json.dumps({'tipo': 'agente', 'agente': 3, 'status': 'erro', 'mensagem': event['error']})}\n\n"
                        yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': event['error']})}\n\n"
                        return

                if resultado_agente3 and resultado_agente3.erro:
                    yield f"data: {json.dumps({'tipo': 'agente', 'agente': 3, 'status': 'erro', 'mensagem': resultado_agente3.erro})}\n\n"
                    yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': resultado_agente3.erro})}\n\n"
                    return

                yield f"data: {json.dumps({'tipo': 'agente', 'agente': 3, 'status': 'concluido', 'mensagem': 'Peça gerada com sucesso!'})}\n\n"
                
                # Prepara lista de documentos processados para salvar
                tracker.mark("postprocess_start")
                documentos_processados = None
                if resultado_agente1.dados_brutos and resultado_agente1.dados_brutos.documentos:
                    documentos_processados = []
                    for doc in resultado_agente1.dados_brutos.documentos:
                        if not doc.irrelevante:
                            documentos_processados.append({
                                "id": doc.id,
                                "ids": doc.ids_agrupados if doc.ids_agrupados else [doc.id],
                                "descricao": doc.descricao,
                                "descricao_ia": doc.descricao_ia,
                                "tipo_documento": doc.tipo_documento,
                                "data_juntada": to_iso_utc(doc.data_juntada),
                                "data_formatada": doc.data_formatada,
                                "processo_origem": doc.processo_origem
                            })
                tracker.mark("postprocess_done")

                # Salva no banco (usa resumo filtrado se disponível)
                tracker.mark("db_save_start")
                geracao = GeracaoPeca(
                    numero_cnj=cnj_limpo,
                    numero_cnj_formatado=cnj_limpo,
                    tipo_peca=tipo_peca,
                    dados_processo=dados_extracao,  # Persiste variáveis extraídas para auditoria
                    conteudo_gerado=resultado_agente3.conteudo_markdown,
                    prompt_enviado=resultado_agente3.prompt_enviado,
                    resumo_consolidado=resumo_para_geracao,
                    documentos_processados=documentos_processados,
                    modelo_usado=modelo,
                    usuario_id=current_user.id
                )

                # Campos de modo de ativação (podem não existir no banco se migration pendente)
                try:
                    geracao.modo_ativacao_agente2 = resultado_agente2.modo_ativacao
                    geracao.modulos_ativados_det = resultado_agente2.modulos_ativados_det
                    geracao.modulos_ativados_llm = resultado_agente2.modulos_ativados_llm
                except AttributeError:
                    pass

                try:
                    db.add(geracao)
                    db.flush()  # Flush para obter o ID sem commit

                    # Cria versão inicial na mesma transação (evita commit duplo)
                    versao = VersaoPeca(
                        geracao_id=geracao.id,
                        numero_versao=1,
                        conteudo=resultado_agente3.conteudo_markdown,
                        origem='geracao_inicial',
                        descricao_alteracao='Versão inicial gerada pela IA',
                        diff_anterior=None
                    )
                    db.add(versao)

                    db.commit()
                    db.refresh(geracao)
                except Exception as e:
                    # Se falhou por colunas inexistentes, tenta sem os campos de modo de ativação
                    if 'modo_ativacao_agente2' in str(e) or 'modulos_ativados' in str(e):
                        db.rollback()
                        geracao.modo_ativacao_agente2 = None
                        geracao.modulos_ativados_det = None
                        geracao.modulos_ativados_llm = None
                        from sqlalchemy import inspect
                        state = inspect(geracao)
                        for attr in ['modo_ativacao_agente2', 'modulos_ativados_det', 'modulos_ativados_llm']:
                            if attr in state.dict:
                                del state.dict[attr]
                        db.add(geracao)
                        db.flush()

                        versao = VersaoPeca(
                            geracao_id=geracao.id,
                            numero_versao=1,
                            conteudo=resultado_agente3.conteudo_markdown,
                            origem='geracao_inicial',
                            descricao_alteracao='Versão inicial gerada pela IA',
                            diff_anterior=None
                        )
                        db.add(versao)

                        db.commit()
                        db.refresh(geracao)
                    else:
                        raise

                tracker.mark("db_save_done")

                # Resultado final
                tracker.mark("response_sent")
                tracker.set_metadata("tipo_peca", tipo_peca)
                tracker.set_metadata("modelo", modelo)
                tracker.log_summary()

                # Inclui metricas de performance no evento final
                perf_report = tracker.get_report()

                # Salva log de performance detalhado no banco
                try:
                    log_request_perf(
                        report=perf_report,
                        db=db,
                        user_id=current_user.id if current_user else None,
                        username=current_user.username if current_user else None,
                        success=True
                    )
                except Exception as e:
                    print(f"[PERF] Erro ao salvar log: {e}")

                yield f"data: {json.dumps({'tipo': 'sucesso', 'geracao_id': geracao.id, 'tipo_peca': tipo_peca, 'minuta_markdown': resultado_agente3.conteudo_markdown, 'performance': {'ttft_ms': perf_report['metrics'].get('ttft_ms'), 'total_ms': perf_report['total_ms'], 'request_id': tracker.request_id}})}\n\n"
            else:
                # Fallback sem orquestrador
                yield f"data: {json.dumps({'tipo': 'info', 'mensagem': 'Usando modo simplificado...'})}\n\n"
                resultado = await service.processar_processo(
                    numero_cnj=cnj_limpo,
                    numero_cnj_formatado=cnj_limpo,
                    tipo_peca=req.tipo_peca,
                    resposta_usuario=req.resposta_usuario,
                    usuario_id=current_user.id
                )
                yield f"data: {json.dumps(resultado)}\n\n"
                
        except asyncio.TimeoutError:
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': 'A solicitação demorou mais que o esperado. Tente com um pedido menor ou divida em partes.'})}\n\n"
        except Exception as e:
            import traceback
            traceback.print_exc()
            # Mensagem mais amigável para erros comuns
            erro_str = str(e)
            if 'timeout' in erro_str.lower() or 'timed out' in erro_str.lower():
                mensagem_erro = 'A geração demorou mais que o esperado. Tente novamente ou use um pedido mais simples.'
            elif 'token' in erro_str.lower() and ('limit' in erro_str.lower() or 'exceeded' in erro_str.lower()):
                mensagem_erro = 'O conteúdo é muito extenso. Tente dividir em partes menores ou reduzir as observações.'
            elif 'connection' in erro_str.lower() or 'network' in erro_str.lower():
                mensagem_erro = 'Erro de conexão com o servidor. Verifique sua internet e tente novamente.'
            else:
                mensagem_erro = f'Erro ao processar: {erro_str}'
            yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': mensagem_erro})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


def _normalizar_texto(texto: str) -> str:
    """
    Normaliza texto extraído de PDF.

    NOTA: Esta função agora usa o serviço centralizado text_normalizer.
    """
    result = text_normalizer.normalize(texto)
    return result.text


def _extrair_texto_pdf(pdf_bytes: bytes) -> str:
    """
    Extrai texto de um arquivo PDF usando PyMuPDF e normaliza.
    
    Args:
        pdf_bytes: Bytes do arquivo PDF
        
    Returns:
        Texto extraído e normalizado do PDF
    """
    texto_completo = []
    try:
        pdf = fitz.open(stream=pdf_bytes, filetype="pdf")
        for pagina in pdf:
            texto = pagina.get_text()
            if texto.strip():
                texto_completo.append(texto)
        pdf.close()
    except Exception as e:
        print(f"Erro ao extrair texto do PDF: {e}")
    
    # Junta todas as páginas e normaliza
    texto_bruto = "\n".join(texto_completo)
    return _normalizar_texto(texto_bruto)


@router.post("/processar-pdfs-stream")
async def processar_pdfs_stream(
    arquivos: List[UploadFile] = File(..., description="Arquivos PDF a serem analisados"),
    tipo_peca: Optional[str] = Form(None, description="Tipo de peça a gerar"),
    observacao_usuario: Optional[str] = Form(None, description="Observações do usuário para a IA"),
    group_id: Optional[int] = Form(None, description="Grupo de prompts"),
    subcategoria_ids_json: Optional[str] = Form(None, description="Subcategorias selecionadas (JSON)"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Processa arquivos PDF anexados e gera a peça jurídica.

    Esta rota permite gerar peças a partir de PDFs enviados diretamente,
    sem necessidade de informar um número de processo do TJ-MS.

    Fluxo com classificação de documentos:
    1. Classifica cada PDF em uma categoria (via IA)
    2. Extrai JSON estruturado de cada documento conforme sua categoria
    3. Seleciona documentos primários/secundários para o tipo de peça
    4. Monta resumo consolidado com dados estruturados
    5. Executa Agente 2 (detector de módulos) e Agente 3 (gerador)

    Se a flag `enable_auto_piece_detection` estiver desabilitada, tipo_peca é OBRIGATÓRIO.

    Returns:
        Stream SSE com progresso da geração
    """
    from admin.models import ConfiguracaoIA

    # Verifica se detecção automática está habilitada
    config_auto = db.query(ConfiguracaoIA).filter(
        ConfiguracaoIA.sistema == "gerador_pecas",
        ConfiguracaoIA.chave == "enable_auto_piece_detection"
    ).first()

    permite_auto = False
    if config_auto and config_auto.valor:
        permite_auto = config_auto.valor.lower() == "true"

    # Validação: se auto-detecção está desabilitada, tipo_peca é obrigatório
    if not permite_auto and not tipo_peca:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tipo de peça é obrigatório. Selecione o tipo de peça antes de gerar."
        )

    subcategoria_ids = _parse_subcategoria_ids_form(subcategoria_ids_json)
    grupo, subcategoria_ids = _resolver_grupo_e_subcategorias(
        current_user,
        db,
        group_id,
        subcategoria_ids
    )
    group_id = grupo.id

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            # Evento inicial
            yield f"data: {json.dumps({'tipo': 'inicio', 'mensagem': 'Processando arquivos PDF...'})}\n\n"

            # ==================================================================
            # ESTÁGIO 1: LEITURA E CLASSIFICAÇÃO DE DOCUMENTOS
            # ==================================================================
            yield f"data: {json.dumps({'tipo': 'agente', 'agente': 1, 'status': 'ativo', 'mensagem': f'Lendo {len(arquivos)} arquivo(s)...'})}\n\n"

            # Lê bytes de todos os PDFs
            documentos_bytes = []
            for i, arquivo in enumerate(arquivos):
                if not arquivo.filename.lower().endswith('.pdf'):
                    yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'Ignorando arquivo não-PDF: {arquivo.filename}'})}\n\n"
                    continue

                conteudo = await arquivo.read()
                documentos_bytes.append({
                    "nome": arquivo.filename,
                    "id": f"pdf_{i+1}",
                    "bytes": conteudo,
                    "ordem": i + 1
                })
                yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'Lido: {arquivo.filename} ({len(conteudo)} bytes)'})}\n\n"

            if not documentos_bytes:
                yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': 'Nenhum arquivo PDF válido encontrado.'})}\n\n"
                return

            # Classifica cada documento
            yield f"data: {json.dumps({'tipo': 'info', 'mensagem': 'Classificando documentos por categoria...'})}\n\n"

            from sistemas.gerador_pecas.document_classifier import DocumentClassifier
            from sistemas.gerador_pecas.document_selector import DocumentSelector

            classificador = DocumentClassifier(db)
            classificacoes = await classificador.classificar_lote(documentos_bytes)

            # Exibe resultado da classificação
            for clf in classificacoes:
                status = "fallback" if clf.fallback_aplicado else f"conf: {clf.confianca:.0%}"
                source_label = {"text": "TEXTO", "ocr_text": "OCR", "full_image": "IMAGEM"}.get(clf.source.value, clf.source.value)
                yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'• {clf.arquivo_nome}: {clf.categoria_nome} ({status}) [{source_label}]'})}\n\n"

            # ==================================================================
            # ESTÁGIO 2: SELEÇÃO DE DOCUMENTOS (após saber tipo de peça)
            # ==================================================================
            tipo_peca_final = tipo_peca

            # Se não tem tipo de peça, detecta automaticamente
            if not tipo_peca_final:
                yield f"data: {json.dumps({'tipo': 'info', 'mensagem': 'Detectando tipo de peça automaticamente...'})}\n\n"

                # Busca configurações do modelo de geração
                config_modelo = db.query(ConfiguracaoIA).filter(
                    ConfiguracaoIA.sistema == "gerador_pecas",
                    ConfiguracaoIA.chave == "modelo_geracao"
                ).first()
                modelo = config_modelo.valor if config_modelo else "google/gemini-2.5-pro-preview-05-06"

                # Inicializa serviço para usar o detector do agente 2
                service = GeradorPecasService(
                    modelo=modelo,
                    db=db,
                    group_id=group_id,
                    subcategoria_ids=subcategoria_ids
                )

                if service.orquestrador:
                    # Monta resumo simples para detecção de tipo
                    texto_resumo = "\n\n".join([
                        f"Documento: {clf.arquivo_nome}\nCategoria: {clf.categoria_nome}\nJustificativa: {clf.justificativa}"
                        for clf in classificacoes
                    ])
                    deteccao = await service.orquestrador.agente2.detectar_tipo_peca(texto_resumo)
                    tipo_peca_final = deteccao.get("tipo_peca") or "contestacao"
                    confianca_tipo = deteccao.get("confianca", "media")
                    yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'Tipo detectado: {tipo_peca_final} (confiança: {confianca_tipo})'})}\n\n"
                else:
                    tipo_peca_final = "contestacao"
                    yield f"data: {json.dumps({'tipo': 'info', 'mensagem': 'Usando tipo padrão: contestação'})}\n\n"

            # Seleciona documentos primários e secundários
            seletor = DocumentSelector(db)
            selecao = seletor.selecionar_documentos(classificacoes, tipo_peca_final)

            yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'Seleção: {len(selecao.documentos_primarios)} primário(s), {len(selecao.documentos_secundarios)} secundário(s)'})}\n\n"

            # ==================================================================
            # ESTÁGIO 3: EXTRAÇÃO DE JSON POR CATEGORIA
            # ==================================================================
            yield f"data: {json.dumps({'tipo': 'info', 'mensagem': 'Extraindo dados estruturados dos documentos...'})}\n\n"

            from sistemas.gerador_pecas.extrator_resumo_json import (
                FormatoResumo, gerar_prompt_extracao_json, gerar_prompt_extracao_json_imagem,
                parsear_resposta_json, normalizar_json_com_schema, json_para_markdown
            )
            from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON
            from sistemas.gerador_pecas.gemini_client import chamar_gemini_async, chamar_gemini_com_imagens_async

            # Mapeia classificações por arquivo_id para acesso rápido
            clf_por_id = {clf.arquivo_id: clf for clf in classificacoes}
            doc_bytes_por_id = {d["id"]: d for d in documentos_bytes}

            # Processa documentos primários e secundários
            documentos_processados = []
            dados_extracao_consolidados = {}
            resumos_markdown = []

            todos_docs_selecionados = selecao.get_todos_selecionados()

            for sel_doc in todos_docs_selecionados:
                clf = sel_doc.classificacao
                doc_data = doc_bytes_por_id.get(clf.arquivo_id)

                if not doc_data:
                    continue

                # Busca categoria e formato JSON
                categoria = db.query(CategoriaResumoJSON).filter(
                    CategoriaResumoJSON.id == clf.categoria_id,
                    CategoriaResumoJSON.ativo == True
                ).first()

                if not categoria or not categoria.formato_json:
                    # Sem formato JSON configurado - usa texto bruto
                    texto = _extrair_texto_pdf(doc_data["bytes"])
                    resumos_markdown.append(f"### {clf.arquivo_nome} ({clf.categoria_nome})\n\n{texto[:5000]}...")
                    documentos_processados.append({
                        "nome": clf.arquivo_nome,
                        "ordem": doc_data["ordem"],
                        "categoria": clf.categoria_nome,
                        "categoria_id": clf.categoria_id,
                        "confianca": clf.confianca,
                        "source": clf.source.value,
                        "role": sel_doc.role.value
                    })
                    continue

                # Monta formato para extração
                formato = FormatoResumo(
                    categoria_id=categoria.id,
                    categoria_nome=categoria.nome,
                    formato_json=categoria.formato_json,
                    instrucoes_extracao=categoria.instrucoes_extracao,
                    is_residual=categoria.is_residual
                )

                # Extrai conteúdo do PDF para extração JSON
                from sistemas.gerador_pecas.document_classifier import extrair_conteudo_pdf
                conteudo_pdf = extrair_conteudo_pdf(doc_data["bytes"])

                # Prepara chamada de extração baseado no tipo de conteúdo
                yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'Extraindo JSON de: {clf.arquivo_nome}...'})}\n\n"

                try:
                    if conteudo_pdf.tem_texto and conteudo_pdf.texto_qualidade == "good":
                        # Extração via texto
                        prompt = gerar_prompt_extracao_json(formato, f"Documento: {clf.arquivo_nome}", db)
                        prompt_final = prompt.replace("{texto_documento}", conteudo_pdf.texto[:30000])

                        resposta = await chamar_gemini_async(
                            prompt=prompt_final,
                            modelo="gemini-2.5-flash-lite",
                            temperature=0.1,
                            max_tokens=8000
                        )
                    else:
                        # Extração via imagens
                        prompt = gerar_prompt_extracao_json_imagem(formato, db)

                        # Converte imagens para base64
                        import base64
                        imagens_b64 = [base64.b64encode(img).decode() for img in conteudo_pdf.imagens[:5]]

                        resposta = await chamar_gemini_com_imagens_async(
                            prompt=prompt,
                            imagens_base64=imagens_b64,
                            modelo="gemini-2.5-flash-lite",
                            temperature=0.1,
                            max_tokens=8000
                        )

                    # Parseia resposta JSON
                    json_extraido, erro_parse = parsear_resposta_json(resposta)

                    if erro_parse:
                        print(f"[PDF] Erro ao parsear JSON de {clf.arquivo_nome}: {erro_parse}")
                        texto = _extrair_texto_pdf(doc_data["bytes"])
                        resumos_markdown.append(f"### {clf.arquivo_nome} ({clf.categoria_nome})\n\n{texto[:5000]}...")
                    else:
                        # Normaliza JSON com schema
                        json_normalizado = normalizar_json_com_schema(json_extraido, categoria.formato_json)

                        # Converte para markdown para resumo
                        md = json_para_markdown(json_normalizado)
                        resumos_markdown.append(f"### {clf.arquivo_nome} ({clf.categoria_nome})\n\n{md}")

                        # Consolida dados de extração
                        # NOTA: Se a chave já começa com o namespace (ex: peticao_inicial_),
                        # não duplica o prefixo para evitar peticao_inicial_peticao_inicial_xxx
                        namespace = categoria.namespace or categoria.nome.lower()
                        namespace_prefix = f"{namespace}_" if namespace else ""
                        
                        for chave, valor in json_normalizado.items():
                            # Verifica se a chave já começa com o namespace para evitar duplicação
                            if namespace_prefix and chave.startswith(namespace_prefix):
                                slug = chave  # Já tem o prefixo, usa como está
                            elif namespace:
                                slug = f"{namespace}_{chave}"
                            else:
                                slug = chave

                            if slug not in dados_extracao_consolidados:
                                dados_extracao_consolidados[slug] = valor
                            else:
                                # Lógica de consolidação
                                existente = dados_extracao_consolidados[slug]
                                if isinstance(existente, bool) and isinstance(valor, bool):
                                    dados_extracao_consolidados[slug] = existente or valor
                                elif isinstance(existente, list) and isinstance(valor, list):
                                    dados_extracao_consolidados[slug] = list(set(existente + valor))

                except Exception as e:
                    print(f"[PDF] Erro na extração de {clf.arquivo_nome}: {e}")
                    texto = _extrair_texto_pdf(doc_data["bytes"])
                    resumos_markdown.append(f"### {clf.arquivo_nome} ({clf.categoria_nome})\n\n{texto[:5000]}...")

                documentos_processados.append({
                    "nome": clf.arquivo_nome,
                    "ordem": doc_data["ordem"],
                    "categoria": clf.categoria_nome,
                    "categoria_id": clf.categoria_id,
                    "confianca": clf.confianca,
                    "source": clf.source.value,
                    "role": sel_doc.role.value,
                    "justificativa": clf.justificativa
                })

            yield f"data: {json.dumps({'tipo': 'agente', 'agente': 1, 'status': 'concluido', 'mensagem': f'{len(documentos_processados)} documento(s) processado(s) com extração JSON'})}\n\n"

            # ==================================================================
            # ESTÁGIO 4: BUSCAR NAT NO PROCESSO DE ORIGEM (SE AGRAVO)
            # ==================================================================
            # Quando os PDFs indicam agravo e não há NAT entre os documentos,
            # busca automaticamente o NAT no processo de origem (1º grau)
            nat_source = None
            try:
                from sistemas.gerador_pecas.services_nat_origem import buscar_nat_para_pdfs_anexados

                nat_result = await buscar_nat_para_pdfs_anexados(
                    dados_consolidados=dados_extracao_consolidados,
                    documentos_processados=documentos_processados,
                    db_session=db
                )

                if nat_result.busca_realizada:
                    yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'[NAT-ORIGEM] Buscando Parecer NAT no processo de origem: {nat_result.numero_processo_origem}...'})}\n\n"

                if nat_result.nat_encontrado and nat_result.nat_source == "origem":
                    # NAT encontrado no processo de origem - adiciona ao resumo
                    nat_source = "origem"
                    yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'[NAT-ORIGEM] ✅ Parecer NAT encontrado no processo de origem!'})}\n\n"

                    # Adiciona resumo do NAT aos resumos markdown
                    if nat_result.resumo_markdown:
                        resumos_markdown.append(nat_result.resumo_markdown)

                    # Adiciona documento NAT aos processados
                    documentos_processados.append({
                        "nome": f"Parecer NAT (Processo de Origem)",
                        "ordem": len(documentos_processados) + 1,
                        "categoria": "Parecer NAT",
                        "categoria_id": None,
                        "confianca": 1.0,
                        "source": "origem",
                        "role": "secondary",
                        "processo_origem": nat_result.numero_processo_origem,
                        "nat_source": "origem"
                    })

                    # Consolida dados JSON do NAT
                    if nat_result.dados_json:
                        namespace_prefix = "parecer_nat_"
                        for chave, valor in nat_result.dados_json.items():
                            slug = f"{namespace_prefix}{chave}" if not chave.startswith(namespace_prefix) else chave
                            if slug not in dados_extracao_consolidados:
                                dados_extracao_consolidados[slug] = valor
                            elif isinstance(valor, bool) and isinstance(dados_extracao_consolidados[slug], bool):
                                dados_extracao_consolidados[slug] = dados_extracao_consolidados[slug] or valor

                elif nat_result.nat_encontrado and nat_result.nat_source == "pdfs_anexados":
                    nat_source = "pdfs_anexados"
                    yield f"data: {json.dumps({'tipo': 'info', 'mensagem': '[NAT-ORIGEM] Parecer NAT já presente nos PDFs anexados'})}\n\n"

                elif nat_result.busca_realizada and not nat_result.nat_encontrado:
                    yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'[NAT-ORIGEM] ⚠ {nat_result.motivo}'})}\n\n"

            except Exception as e:
                print(f"[NAT-ORIGEM] Erro na busca de NAT para PDFs: {e}")
                import traceback
                traceback.print_exc()
                # Não interrompe o fluxo - apenas loga o erro
                yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'[NAT-ORIGEM] Busca de NAT não disponível: {str(e)}'})}\n\n"

            # ==================================================================
            # ESTÁGIO 5: MONTAR RESUMO CONSOLIDADO
            # ==================================================================
            resumo_consolidado = _montar_resumo_pdfs_classificados(
                documentos_processados,
                resumos_markdown,
                selecao
            )

            # Adiciona informação de nat_source ao resumo se aplicável
            if nat_source:
                resumo_consolidado = f"**nat_source**: {nat_source}\n\n" + resumo_consolidado

            # ==================================================================
            # ESTÁGIO 6: AGENTE 2 E 3 (mesmo fluxo anterior)
            # ==================================================================
            config_modelo = db.query(ConfiguracaoIA).filter(
                ConfiguracaoIA.sistema == "gerador_pecas",
                ConfiguracaoIA.chave == "modelo_geracao"
            ).first()
            modelo = config_modelo.valor if config_modelo else "google/gemini-2.5-pro-preview-05-06"

            service = GeradorPecasService(
                modelo=modelo,
                db=db,
                group_id=group_id,
                subcategoria_ids=subcategoria_ids
            )

            if service.orquestrador:
                orq = service.orquestrador

                yield f"data: {json.dumps({'tipo': 'agente', 'agente': 2, 'status': 'ativo', 'mensagem': 'Analisando e ativando prompts...'})}\n\n"

                # Log detalhado das variáveis extraídas para debug
                if dados_extracao_consolidados:
                    print(f"[PDF-ROUTER] Variáveis extraídas para avaliação determinística:")
                    for slug, valor in dados_extracao_consolidados.items():
                        print(f"[PDF-ROUTER]   - {slug}: {valor}")
                    print(f"[PDF-ROUTER] Tipo de peça para avaliação: {tipo_peca_final}")
                else:
                    print(f"[PDF-ROUTER] AVISO: Nenhuma variável extraída dos PDFs!")

                # AGORA temos dados de extração estruturados!
                resultado_agente2 = await orq._executar_agente2(
                    resumo_consolidado,
                    tipo_peca_final,
                    dados_processo=None,
                    dados_extracao=dados_extracao_consolidados if dados_extracao_consolidados else None
                )

                if resultado_agente2.erro:
                    yield f"data: {json.dumps({'tipo': 'agente', 'agente': 2, 'status': 'erro', 'mensagem': resultado_agente2.erro})}\n\n"
                    yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': resultado_agente2.erro})}\n\n"
                    return

                # Info sobre modo de ativação
                modo_info = resultado_agente2.modo_ativacao or "llm"
                det_count = resultado_agente2.modulos_ativados_det or 0
                llm_count = resultado_agente2.modulos_ativados_llm or 0
                yield f"data: {json.dumps({'tipo': 'agente', 'agente': 2, 'status': 'concluido', 'mensagem': f'{len(resultado_agente2.modulos_ids)} módulos ({det_count} det, {llm_count} LLM)'})}\n\n"

                # Agente 3: Gerador
                yield f"data: {json.dumps({'tipo': 'agente', 'agente': 3, 'status': 'ativo', 'mensagem': 'Gerando peça jurídica com IA...'})}\n\n"

                if observacao_usuario:
                    yield f"data: {json.dumps({'tipo': 'info', 'mensagem': 'Observações do usuário serão consideradas na geração'})}\n\n"

                # Usa versão STREAMING do Agente 3 para TTFT rápido
                resultado_agente3 = None
                async for event in orq._executar_agente3_stream(
                    resumo_consolidado=resumo_consolidado,
                    prompt_sistema=resultado_agente2.prompt_sistema,
                    prompt_peca=resultado_agente2.prompt_peca,
                    prompt_conteudo=resultado_agente2.prompt_conteudo,
                    tipo_peca=tipo_peca_final,
                    observacao_usuario=observacao_usuario
                ):
                    if event["tipo"] == "chunk":
                        # Envia chunk de texto para o frontend em tempo real
                        yield f"data: {json.dumps({'tipo': 'geracao_chunk', 'content': event['content']})}\n\n"

                    elif event["tipo"] == "done":
                        resultado_agente3 = event["resultado"]

                    elif event["tipo"] == "error":
                        resultado_agente3 = event["resultado"]
                        yield f"data: {json.dumps({'tipo': 'agente', 'agente': 3, 'status': 'erro', 'mensagem': event['error']})}\n\n"
                        yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': event['error']})}\n\n"
                        return

                if resultado_agente3 and resultado_agente3.erro:
                    yield f"data: {json.dumps({'tipo': 'agente', 'agente': 3, 'status': 'erro', 'mensagem': resultado_agente3.erro})}\n\n"
                    yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': resultado_agente3.erro})}\n\n"
                    return

                yield f"data: {json.dumps({'tipo': 'agente', 'agente': 3, 'status': 'concluido', 'mensagem': 'Peça gerada com sucesso!'})}\n\n"

                # Salva no banco
                geracao = GeracaoPeca(
                    numero_cnj="PDF_UPLOAD",
                    numero_cnj_formatado="PDFs Anexados",
                    tipo_peca=tipo_peca_final,
                    dados_processo=dados_extracao_consolidados,  # Persiste variáveis extraídas para auditoria
                    conteudo_gerado=resultado_agente3.conteudo_markdown,
                    prompt_enviado=resultado_agente3.prompt_enviado,
                    resumo_consolidado=resumo_consolidado,
                    documentos_processados=documentos_processados,
                    modelo_usado=modelo,
                    usuario_id=current_user.id
                )

                # Campos de modo de ativação
                try:
                    geracao.modo_ativacao_agente2 = resultado_agente2.modo_ativacao
                    geracao.modulos_ativados_det = resultado_agente2.modulos_ativados_det
                    geracao.modulos_ativados_llm = resultado_agente2.modulos_ativados_llm
                except AttributeError:
                    pass

                db.add(geracao)
                db.commit()
                db.refresh(geracao)

                criar_versao_inicial(db, geracao.id, resultado_agente3.conteudo_markdown)

                yield f"data: {json.dumps({'tipo': 'sucesso', 'geracao_id': geracao.id, 'tipo_peca': tipo_peca_final, 'minuta_markdown': resultado_agente3.conteudo_markdown})}\n\n"
            else:
                yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': 'Orquestrador de agentes não disponível'})}\n\n"

        except asyncio.TimeoutError:
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': 'A solicitação demorou mais que o esperado. Tente com menos arquivos ou documentos menores.'})}\n\n"
        except Exception as e:
            import traceback
            traceback.print_exc()
            # Mensagem mais amigável para erros comuns
            erro_str = str(e)
            if 'timeout' in erro_str.lower() or 'timed out' in erro_str.lower():
                mensagem_erro = 'A geração demorou mais que o esperado. Tente novamente ou use menos arquivos.'
            elif 'token' in erro_str.lower() and ('limit' in erro_str.lower() or 'exceeded' in erro_str.lower()):
                mensagem_erro = 'O conteúdo dos PDFs é muito extenso. Tente com menos arquivos ou documentos menores.'
            elif 'connection' in erro_str.lower() or 'network' in erro_str.lower():
                mensagem_erro = 'Erro de conexão com o servidor. Verifique sua internet e tente novamente.'
            else:
                mensagem_erro = f'Erro ao processar: {erro_str}'
            yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': mensagem_erro})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


def _montar_resumo_pdfs_classificados(
    documentos: List[Dict],
    resumos_markdown: List[str],
    selecao
) -> str:
    """
    Monta resumo consolidado a partir de documentos classificados e JSONs extraídos.
    """
    partes = []

    partes.append("# RESUMO CONSOLIDADO DOS DOCUMENTOS")
    partes.append(f"**Origem**: Arquivos PDF anexados (com classificação por categoria)")
    partes.append(f"**Data da Análise**: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    partes.append(f"**Total de Documentos**: {len(documentos)}")
    partes.append(f"**Tipo de Peça**: {selecao.tipo_peca}")
    partes.append(f"**Seleção**: {selecao.razao_geral}")
    partes.append("\n---\n")

    # Documentos primários
    if selecao.documentos_primarios:
        partes.append("## DOCUMENTOS PRIMÁRIOS (fonte principal)\n")
        for sel_doc in selecao.documentos_primarios:
            clf = sel_doc.classificacao
            partes.append(f"- **{clf.arquivo_nome}** → {clf.categoria_nome} (conf: {clf.confianca:.0%})")
        partes.append("")

    # Documentos secundários
    if selecao.documentos_secundarios:
        partes.append("## DOCUMENTOS SECUNDÁRIOS (fontes auxiliares)\n")
        for sel_doc in selecao.documentos_secundarios:
            clf = sel_doc.classificacao
            partes.append(f"- **{clf.arquivo_nome}** → {clf.categoria_nome} (conf: {clf.confianca:.0%})")
        partes.append("")

    partes.append("---\n")
    partes.append("## CONTEÚDO EXTRAÍDO\n")

    # Adiciona resumos markdown
    for resumo in resumos_markdown:
        partes.append(resumo)
        partes.append("\n---\n")

    partes.append("*Este resumo foi gerado a partir de arquivos PDF classificados automaticamente.*")

    return "\n".join(partes)


def _montar_resumo_pdfs(documentos: List[Dict]) -> str:
    """
    Monta o resumo consolidado a partir dos textos dos PDFs.
    
    Args:
        documentos: Lista de dicts com 'nome', 'texto' e 'ordem'
        
    Returns:
        Resumo consolidado em formato similar ao do Agente 1
    """
    partes = []
    
    partes.append("# RESUMO CONSOLIDADO DOS DOCUMENTOS")
    partes.append(f"**Origem**: Arquivos PDF anexados")
    partes.append(f"**Data da Análise**: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    partes.append(f"**Total de Documentos**: {len(documentos)}")
    partes.append("\n---\n")
    partes.append("## DOCUMENTOS ANALISADOS\n")
    
    for doc in documentos:
        partes.append(f"### {doc['ordem']}. {doc['nome']}")
        partes.append(f"\n{doc['texto']}\n")
        partes.append("---\n")
    
    partes.append("\n---")
    partes.append("*Este resumo foi gerado a partir de arquivos PDF anexados.*")
    
    return "\n".join(partes)


@router.post("/editar-minuta")
async def editar_minuta(
    req: EditarMinutaRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Processa pedido de edição da minuta via chat.
    Usa o mesmo modelo de IA configurado para geração.
    Retorna a minuta atualizada em markdown.
    """
    try:
        # Logging de tamanho para diagnóstico
        minuta_len = len(req.minuta_atual) if req.minuta_atual else 0
        mensagem_len = len(req.mensagem) if req.mensagem else 0
        historico_len = len(req.historico) if req.historico else 0
        print(f"[EDITAR-MINUTA] 📝 Tamanho da minuta: {minuta_len:,} chars, mensagem: {mensagem_len:,} chars, histórico: {historico_len} msgs")
        
        # Busca configurações de IA
        config_modelo = db.query(ConfiguracaoIA).filter(
            ConfiguracaoIA.sistema == "gerador_pecas",
            ConfiguracaoIA.chave == "modelo_geracao"
        ).first()
        modelo = config_modelo.valor if config_modelo else "anthropic/claude-3.5-sonnet"
        
        # Inicializa o serviço
        service = GeradorPecasService(
            modelo=modelo,
            db=db
        )
        
        # Processa a edição
        resultado = await service.editar_minuta(
            minuta_atual=req.minuta_atual,
            mensagem_usuario=req.mensagem,
            historico=req.historico
        )
        
        return resultado
        
    except asyncio.TimeoutError:
        import traceback
        traceback.print_exc()
        return {
            "status": "erro",
            "mensagem": "A edição demorou mais que o esperado. Tente um pedido de alteração mais simples."
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        erro_str = str(e)
        # Mensagem mais amigável para erros comuns
        if 'timeout' in erro_str.lower() or 'timed out' in erro_str.lower():
            mensagem_erro = 'A edição demorou mais que o esperado. Tente um pedido mais simples.'
        elif 'token' in erro_str.lower() and ('limit' in erro_str.lower() or 'exceeded' in erro_str.lower()):
            mensagem_erro = 'A minuta ou o pedido são muito extensos. Tente uma alteração menor.'
        else:
            mensagem_erro = f'Erro ao processar edição: {erro_str}'
        
        return {
            "status": "erro",
            "mensagem": mensagem_erro
        }


@router.post("/editar-minuta-stream")
async def editar_minuta_stream(
    req: EditarMinutaRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Processa edição da minuta via chat com streaming real.

    PERFORMANCE: Usa streamGenerateContent do Gemini para enviar
    tokens assim que são gerados, reduzindo TTFT de 15-60s para 1-3s.

    Retorna um stream SSE com eventos:
    - event: start - início do streaming
    - event: chunk - cada chunk de texto gerado
    - event: done - conclusão do streaming
    - event: error - erro durante o processo
    """
    from fastapi.responses import StreamingResponse
    from services.gemini_service import stream_to_sse
    import json

    try:
        tipo_peca = req.tipo_peca

        # Busca configurações de IA
        config_modelo = db.query(ConfiguracaoIA).filter(
            ConfiguracaoIA.sistema == "gerador_pecas",
            ConfiguracaoIA.chave == "modelo_geracao"
        ).first()
        modelo = config_modelo.valor if config_modelo else "anthropic/claude-3.5-sonnet"

        # Inicializa o serviço
        service = GeradorPecasService(
            modelo=modelo,
            db=db
        )

        # Generator de streaming (com busca de argumentos integrada)
        text_generator = service.editar_minuta_stream(
            minuta_atual=req.minuta_atual,
            mensagem_usuario=req.mensagem,
            historico=req.historico,
            tipo_peca=tipo_peca
        )

        # Converte para SSE com heartbeats
        sse_generator = stream_to_sse(
            text_generator,
            event_type="chunk",
            include_heartbeat=True,
            heartbeat_interval=15.0
        )

        return StreamingResponse(
            sse_generator,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"  # Desabilita buffering no nginx
            }
        )

    except Exception as e:
        import traceback
        traceback.print_exc()

        # Retorna erro como SSE para compatibilidade
        async def error_generator():
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

        return StreamingResponse(
            error_generator(),
            media_type="text/event-stream"
        )


@router.post("/exportar-docx")
async def exportar_docx(
    req: ExportarDocxRequest,
    current_user: User = Depends(get_current_active_user)
):
    """
    Exporta markdown para DOCX usando template personalizado.
    
    Converte o conteúdo markdown da minuta para um documento Word (.docx)
    preservando toda a formatação: negrito, itálico, títulos, listas, citações.
    
    O documento é gerado com:
    - Margens ABNT (3cm esq/sup, 2cm dir/inf)
    - Fonte Arial 12pt
    - Recuo de primeira linha 1.25cm
    - Espaçamento 1.5
    - Citações com recuo de 4cm e fonte 11pt
    
    Returns:
        JSON com URL para download do documento
    """
    try:
        from sistemas.gerador_pecas.docx_converter import markdown_to_docx
        
        # Gera nome único para o arquivo
        file_id = str(uuid.uuid4())
        
        # Monta nome amigável: tipo_peca_numero_processo.docx
        tipo_map = {
            'contestacao': 'contestacao',
            'recurso_apelacao': 'apelacao',
            'contrarrazoes': 'contrarrazoes',
            'parecer': 'parecer'
        }
        tipo_nome = tipo_map.get(req.tipo_peca, req.tipo_peca) if req.tipo_peca else 'peca'

        # Número do processo (formatado ou limpo)
        if req.numero_cnj:
            # Remove caracteres especiais mas mantém o número completo
            numero_processo = _limpar_cnj(req.numero_cnj)
        else:
            numero_processo = file_id[:8]

        filename = f"{tipo_nome}_{numero_processo}.docx"
        filepath = os.path.join(TEMP_DIR, filename)
        
        # Converte markdown para DOCX
        success = markdown_to_docx(req.markdown, filepath)
        
        if not success:
            raise HTTPException(
                status_code=500,
                detail="Erro ao converter documento para DOCX"
            )
        
        return {
            "status": "sucesso",
            "url_download": f"/gerador-pecas/api/download/{filename}",
            "filename": filename
        }
        
    except ImportError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Módulo de conversão não disponível: {str(e)}"
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao exportar documento: {str(e)}"
        )


@router.get("/download/{filename}")
async def download_documento(
    filename: str,
    current_user: User = Depends(get_current_user_from_token_or_query)
):
    """Download do documento gerado (aceita token via header, cookie ou query param)"""
    
    filepath = os.path.join(TEMP_DIR, filename)
    
    if not os.path.exists(filepath):
        raise HTTPException(
            status_code=404,
            detail="Documento não encontrado ou expirado"
        )
    
    # Determina nome amigável do arquivo
    # Extrai informações do nome do arquivo se disponível
    if filename.startswith('peca_juridica_'):
        download_name = filename
    else:
        # Nome já é amigável (contestacao_12345678_abc.docx)
        download_name = filename
    
    return FileResponse(
        filepath,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=download_name
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
                "data": to_iso_utc(g.criado_em)
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
    """Remove uma geração do histórico do usuário - PRESERVA feedbacks."""
    try:
        geracao = db.query(GeracaoPeca).filter(
            GeracaoPeca.id == geracao_id,
            GeracaoPeca.usuario_id == current_user.id
        ).first()

        if not geracao:
            raise HTTPException(status_code=404, detail="Geração não encontrada")

        # Verifica se tem feedback associado - se tiver, não permite excluir
        feedback = db.query(FeedbackPeca).filter(FeedbackPeca.geracao_id == geracao_id).first()
        if feedback:
            raise HTTPException(
                status_code=400,
                detail="Não é possível excluir geração que possui feedback registrado"
            )

        db.delete(geracao)
        db.commit()

        return {"success": True, "message": "Geração removida do histórico"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/historico/{geracao_id}")
async def obter_geracao(
    geracao_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Obtém detalhes completos de uma geração específica.
    Permite reabrir uma peça antiga no editor.
    """
    try:
        geracao = db.query(GeracaoPeca).filter(
            GeracaoPeca.id == geracao_id,
            GeracaoPeca.usuario_id == current_user.id
        ).first()
        
        if not geracao:
            raise HTTPException(status_code=404, detail="Geração não encontrada")
        
        # Detecta se o conteúdo é markdown (string) ou JSON (dict)
        # Novas gerações são markdown, antigas são JSON
        is_markdown = isinstance(geracao.conteudo_gerado, str)
        
        return {
            "id": geracao.id,
            "cnj": geracao.numero_cnj_formatado or geracao.numero_cnj,
            "tipo_peca": geracao.tipo_peca,
            "data": to_iso_utc(geracao.criado_em),
            "minuta_markdown": geracao.conteudo_gerado if is_markdown else None,
            "conteudo_json": geracao.conteudo_gerado if not is_markdown else None,
            "resumo_consolidado": geracao.resumo_consolidado,
            "modelo_usado": geracao.modelo_usado,
            "tempo_processamento": geracao.tempo_processamento,
            "historico_chat": geracao.historico_chat or [],
            "has_markdown": is_markdown
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class SalvarMinutaRequest(BaseModel):
    """Request para salvar alterações na minuta"""
    minuta_markdown: str
    historico_chat: Optional[List[Dict]] = None


class SalvarMinutaComVersaoRequest(BaseModel):
    """Request para salvar alterações na minuta com suporte a versões"""
    minuta_markdown: str
    historico_chat: Optional[List[Dict]] = None
    descricao_alteracao: Optional[str] = None  # Descrição da alteração (mensagem do chat)


@router.put("/historico/{geracao_id}")
async def salvar_geracao(
    geracao_id: int,
    req: SalvarMinutaComVersaoRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Salva alterações feitas na minuta via chat.
    Atualiza o conteudo_gerado com o novo markdown, o histórico de chat,
    e cria uma nova versão no histórico de versões.
    """
    try:
        geracao = db.query(GeracaoPeca).filter(
            GeracaoPeca.id == geracao_id,
            GeracaoPeca.usuario_id == current_user.id
        ).first()

        if not geracao:
            raise HTTPException(status_code=404, detail="Geração não encontrada")

        # Verifica se houve alteração no conteúdo
        conteudo_anterior = geracao.conteudo_gerado or ""
        conteudo_novo = req.minuta_markdown

        versao_criada = None

        # Se o conteúdo mudou, cria uma nova versão
        if conteudo_anterior != conteudo_novo:
            # Obtém a última mensagem do usuário do histórico como descrição
            descricao = req.descricao_alteracao
            if not descricao and req.historico_chat:
                # Pega a última mensagem do usuário
                for msg in reversed(req.historico_chat):
                    if msg.get("role") == "user":
                        descricao = msg.get("content", "")[:200]  # Limita tamanho
                        break

            # Verifica se já existe alguma versão para esta geração
            versao_existente = db.query(VersaoPeca).filter(
                VersaoPeca.geracao_id == geracao_id
            ).first()

            # Se não existe versão, cria a versão inicial primeiro
            if not versao_existente:
                criar_versao_inicial(db, geracao_id, conteudo_anterior)

            # Cria a nova versão
            nova_versao, diff = criar_nova_versao(
                db=db,
                geracao_id=geracao_id,
                conteudo_novo=conteudo_novo,
                descricao=descricao,
                origem='edicao_chat'
            )

            if nova_versao:
                versao_criada = {
                    "id": nova_versao.id,
                    "numero_versao": nova_versao.numero_versao,
                    "resumo_diff": diff.get("resumo", "")
                }

        # Atualiza o conteúdo com o novo markdown
        geracao.conteudo_gerado = req.minuta_markdown

        # Atualiza o histórico de chat se fornecido
        if req.historico_chat is not None:
            geracao.historico_chat = req.historico_chat

        db.commit()

        response = {"success": True, "message": "Minuta salva com sucesso"}
        if versao_criada:
            response["versao"] = versao_criada

        return response
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# Endpoints de Versões (Histórico de Alterações)
# ============================================

@router.get("/historico/{geracao_id}/versoes")
async def listar_versoes(
    geracao_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Lista todas as versões de uma peça específica.
    Retorna lista ordenada da mais recente para a mais antiga.
    """
    try:
        # Verifica se a geração pertence ao usuário
        geracao = db.query(GeracaoPeca).filter(
            GeracaoPeca.id == geracao_id,
            GeracaoPeca.usuario_id == current_user.id
        ).first()

        if not geracao:
            raise HTTPException(status_code=404, detail="Geração não encontrada")

        versoes = obter_versoes(db, geracao_id)

        return {
            "geracao_id": geracao_id,
            "total_versoes": len(versoes),
            "versoes": versoes
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/historico/{geracao_id}/versoes/comparar")
async def comparar_versoes_endpoint(
    geracao_id: int,
    v1: int = Query(..., description="ID da primeira versão"),
    v2: int = Query(..., description="ID da segunda versão"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Compara duas versões específicas e retorna o diff entre elas.
    """
    try:
        # Verifica se a geração pertence ao usuário
        geracao = db.query(GeracaoPeca).filter(
            GeracaoPeca.id == geracao_id,
            GeracaoPeca.usuario_id == current_user.id
        ).first()

        if not geracao:
            raise HTTPException(status_code=404, detail="Geração não encontrada")

        resultado = comparar_versoes(db, v1, v2)

        if not resultado:
            raise HTTPException(status_code=404, detail="Uma ou ambas as versões não foram encontradas")

        return resultado
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/historico/{geracao_id}/versoes/{versao_id}")
async def obter_versao(
    geracao_id: int,
    versao_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Obtém detalhes completos de uma versão específica, incluindo diff.
    """
    try:
        # Verifica se a geração pertence ao usuário
        geracao = db.query(GeracaoPeca).filter(
            GeracaoPeca.id == geracao_id,
            GeracaoPeca.usuario_id == current_user.id
        ).first()

        if not geracao:
            raise HTTPException(status_code=404, detail="Geração não encontrada")

        versao = obter_versao_detalhada(db, versao_id)

        if not versao or versao["geracao_id"] != geracao_id:
            raise HTTPException(status_code=404, detail="Versão não encontrada")

        return versao
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/historico/{geracao_id}/versoes/{versao_id}/restaurar")
async def restaurar_versao_endpoint(
    geracao_id: int,
    versao_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Restaura uma versão anterior, criando uma nova versão com o conteúdo antigo.
    A versão atual não é perdida - fica registrada no histórico.
    """
    try:
        # Verifica se a geração pertence ao usuário
        geracao = db.query(GeracaoPeca).filter(
            GeracaoPeca.id == geracao_id,
            GeracaoPeca.usuario_id == current_user.id
        ).first()

        if not geracao:
            raise HTTPException(status_code=404, detail="Geração não encontrada")

        nova_versao = restaurar_versao(db, geracao_id, versao_id)

        if not nova_versao:
            raise HTTPException(status_code=404, detail="Versão não encontrada ou erro ao restaurar")

        return {
            "success": True,
            "message": f"Versão restaurada com sucesso",
            "nova_versao": {
                "id": nova_versao.id,
                "numero_versao": nova_versao.numero_versao
            },
            "conteudo": nova_versao.conteudo
        }
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
            raise HTTPException(
                status_code=400,
                detail="Feedback já foi enviado para esta geração"
            )

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
            "criado_em": to_iso_utc(feedback.criado_em)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# Endpoints de Autos do Processo (Visualização de PDFs)
# ============================================

def _agrupar_documentos_por_descricao(docs: List) -> List:
    """
    Agrupa documentos com mesma descrição juntados no mesmo minuto.
    Retorna lista de documentos agrupados (cada item pode ter múltiplos IDs).
    """
    from collections import defaultdict
    
    grupos = defaultdict(list)
    
    for doc in docs:
        # Chave: descrição + data arredondada para o minuto
        descricao = doc.descricao or doc.categoria_nome or 'desconhecido'
        if doc.data_juntada:
            data_key = doc.data_juntada.strftime('%Y%m%d%H%M')
        else:
            data_key = 'sem_data'
        
        chave = (descricao, data_key)
        grupos[chave].append(doc)
    
    # Monta resultado agrupado
    resultado = []
    for (descricao, data_key), docs_grupo in grupos.items():
        # Ordena por ID para consistência
        docs_grupo.sort(key=lambda d: d.id)
        
        doc_principal = docs_grupo[0]
        ids_todos = [d.id for d in docs_grupo]
        
        resultado.append({
            "ids": ids_todos,  # Lista de IDs para merge
            "id": ids_todos[0],  # ID principal (retrocompatibilidade)
            "descricao": descricao,
            "tipo_documento": doc_principal.tipo_documento,
            "data_juntada": doc_principal.data_juntada,
            "data_formatada": doc_principal.data_formatada,
            "total_partes": len(ids_todos)
        })
    
    # Ordena por data cronológica
    resultado.sort(key=lambda d: d["data_juntada"] or datetime.min)
    
    return resultado


@router.get("/autos/{numero_cnj}")
async def listar_documentos_processo(
    numero_cnj: str,
    token: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user_from_token_or_query),
    db: Session = Depends(get_db)
):
    """
    Lista todos os documentos de um processo para visualização.
    Retorna lista ordenada cronologicamente com descrição do XML.
    Documentos com mesma descrição e data (até 1 min) são agrupados.
    Se houver processamento anterior, usa descrição identificada pela IA.
    """
    import aiohttp
    from sistemas.gerador_pecas.agente_tjms import (
        consultar_processo_async,
        extrair_documentos_xml,
        documento_permitido
    )
    
    try:
        cnj_limpo = _limpar_cnj(numero_cnj)
        
        # Busca documentos processados salvos no banco (se existir)
        geracao = db.query(GeracaoPeca).filter(
            GeracaoPeca.numero_cnj == cnj_limpo,
            GeracaoPeca.documentos_processados.isnot(None)
        ).order_by(GeracaoPeca.criado_em.desc()).first()
        
        # Mapa de ID -> descricao_ia do processamento anterior
        descricoes_ia_map = {}
        if geracao and geracao.documentos_processados:
            for doc_salvo in geracao.documentos_processados:
                if doc_salvo.get("descricao_ia"):
                    # Mapeia todos os IDs do documento agrupado
                    for doc_id in doc_salvo.get("ids", [doc_salvo.get("id")]):
                        descricoes_ia_map[doc_id] = doc_salvo["descricao_ia"]
        
        async with aiohttp.ClientSession() as session:
            xml_response = await consultar_processo_async(session, cnj_limpo)
            docs = extrair_documentos_xml(xml_response)
        
        # Filtra documentos permitidos
        docs_filtrados = [d for d in docs if documento_permitido(int(d.tipo_documento or 0))]
        
        # Agrupa documentos com mesma descrição/data
        docs_agrupados = _agrupar_documentos_por_descricao(docs_filtrados)
        
        # Retorna lista com informações para exibição
        resultado = []
        for i, doc in enumerate(docs_agrupados, 1):
            # Verifica se há descrição da IA para este documento
            descricao_exibir = doc["descricao"]
            doc_id_principal = doc["ids"][0] if doc["ids"] else doc["id"]
            if doc_id_principal in descricoes_ia_map:
                descricao_exibir = descricoes_ia_map[doc_id_principal]
            
            resultado.append({
                "id": doc["id"],
                "ids": doc["ids"],  # Lista de IDs para merge
                "ordem": i,
                "descricao": descricao_exibir,
                "descricao_original": doc["descricao"],  # Mantém original para referência
                "tipo_documento": doc["tipo_documento"],
                "data_juntada": doc["data_juntada"].isoformat() if doc["data_juntada"] else None,
                "data_formatada": doc["data_formatada"],
                "total_partes": doc["total_partes"]
            })
        
        return {
            "numero_cnj": numero_cnj,
            "total_documentos": len(resultado),
            "documentos": resultado,
            "tem_descricoes_ia": len(descricoes_ia_map) > 0
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/autos/{numero_cnj}/documento/{doc_id}")
async def baixar_documento_processo(
    numero_cnj: str,
    doc_id: str,
    ids: Optional[str] = Query(None, description="Lista de IDs separados por vírgula para merge"),
    token: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user_from_token_or_query)
):
    """
    Baixa um ou mais documentos do processo do TJ-MS.
    Se ids contiver múltiplos IDs (separados por vírgula), faz merge dos PDFs.
    Retorna o PDF diretamente para visualização no navegador.
    """
    import aiohttp
    import base64
    from sistemas.gerador_pecas.agente_tjms import baixar_documentos_async
    import xml.etree.ElementTree as ET
    
    try:
        cnj_limpo = _limpar_cnj(numero_cnj)
        
        # Parse lista de IDs (se fornecida)
        if ids:
            lista_ids = [id.strip() for id in ids.split(',') if id.strip()]
        else:
            lista_ids = [doc_id]
        
        async with aiohttp.ClientSession() as session:
            xml_response = await baixar_documentos_async(session, cnj_limpo, lista_ids)
        
        # Extrai conteúdo base64 de todos os documentos
        root = ET.fromstring(xml_response)
        pdfs_bytes = []
        
        for elem in root.iter():
            tag_no_ns = elem.tag.split('}')[-1].lower() if '}' in elem.tag else elem.tag.lower()
            if tag_no_ns == 'documento':
                doc_id_found = elem.attrib.get("idDocumento") or elem.attrib.get("id")
                if doc_id_found in lista_ids:
                    # Busca conteúdo base64
                    conteudo_base64 = elem.attrib.get("conteudo")
                    if not conteudo_base64:
                        for child in elem:
                            child_tag = child.tag.split('}')[-1].lower()
                            if child_tag == 'conteudo' and child.text:
                                conteudo_base64 = child.text.strip()
                                break
                    
                    if conteudo_base64:
                        pdfs_bytes.append((doc_id_found, base64.b64decode(conteudo_base64)))
        
        if not pdfs_bytes:
            raise HTTPException(status_code=404, detail="Documento não encontrado")
        
        # Se só tem um PDF, retorna direto
        if len(pdfs_bytes) == 1:
            pdf_bytes = pdfs_bytes[0][1]
        else:
            # Faz merge dos PDFs usando PyMuPDF
            import fitz
            
            # Ordena os PDFs pela ordem dos IDs na lista original
            id_order = {id: i for i, id in enumerate(lista_ids)}
            pdfs_bytes.sort(key=lambda x: id_order.get(x[0], 999))
            
            # Merge
            merged_pdf = fitz.open()
            for doc_id_item, pdf_data in pdfs_bytes:
                try:
                    pdf_doc = fitz.open(stream=pdf_data, filetype="pdf")
                    merged_pdf.insert_pdf(pdf_doc)
                    pdf_doc.close()
                except Exception as e:
                    print(f"Erro ao processar PDF {doc_id_item}: {e}")
                    continue
            
            pdf_bytes = merged_pdf.tobytes()
            merged_pdf.close()
        
        # Retorna como PDF para visualização inline
        return StreamingResponse(
            iter([pdf_bytes]),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"inline; filename=doc_{doc_id}.pdf",
                "Cache-Control": "private, max-age=3600"  # Cache de 1h
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
