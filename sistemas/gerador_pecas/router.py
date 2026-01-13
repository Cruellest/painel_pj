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
from sqlalchemy.orm import Session

from auth.dependencies import get_current_active_user, get_current_user_from_token_or_query
from auth.models import User
from database.connection import get_db
from sistemas.gerador_pecas.models import GeracaoPeca, FeedbackPeca, VersaoPeca
from sistemas.gerador_pecas.services import GeradorPecasService
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


@router.get("/tipos-peca")
async def listar_tipos_peca(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Lista os tipos de peças disponíveis baseado nos prompts modulares ativos.
    Retorna apenas os tipos de peça que têm prompt configurado no banco.
    """
    from admin.models_prompts import PromptModulo
    
    # Busca módulos do tipo "peca" que estão ativos
    modulos_peca = db.query(PromptModulo).filter(
        PromptModulo.tipo == "peca",
        PromptModulo.ativo == True
    ).order_by(PromptModulo.ordem).all()
    
    tipos = []
    for modulo in modulos_peca:
        tipos.append({
            "valor": modulo.categoria,  # Ex: "contestacao", "recurso_apelacao"
            "label": modulo.titulo,      # Ex: "Contestação", "Recurso de Apelação"
            "descricao": modulo.conteudo[:100] + "..." if len(modulo.conteudo) > 100 else modulo.conteudo
        })
    
    return {
        "tipos": tipos,
        "permite_auto": True  # Permite a opção "detectar automaticamente"
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
    
    Se tipo_peca não for especificado, o Agente 2 detecta automaticamente
    qual tipo de peça é mais adequado baseado nos documentos do processo.
    """
    grupo, subcategoria_ids = _resolver_grupo_e_subcategorias(
        current_user,
        db,
        req.group_id,
        req.subcategoria_ids
    )
    group_id = grupo.id
    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            cnj_limpo = _limpar_cnj(req.numero_cnj)
            
            # Evento inicial
            yield f"data: {json.dumps({'tipo': 'inicio', 'mensagem': 'Iniciando processamento...'})}\n\n"
            
            # Busca configurações
            config_modelo = db.query(ConfiguracaoIA).filter(
                ConfiguracaoIA.sistema == "gerador_pecas",
                ConfiguracaoIA.chave == "modelo_geracao"
            ).first()
            modelo = config_modelo.valor if config_modelo else "google/gemini-2.5-pro-preview-05-06"
            
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
                yield f"data: {json.dumps({'tipo': 'agente', 'agente': 1, 'status': 'ativo', 'mensagem': 'Baixando documentos do TJ-MS...'})}\n\n"

                resultado_agente1 = await orq.agente1.coletar_e_resumir(cnj_limpo)

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
                
                yield f"data: {json.dumps({'tipo': 'agente', 'agente': 2, 'status': 'ativo', 'mensagem': 'Analisando e ativando prompts...'})}\n\n"
                
                resultado_agente2 = await orq._executar_agente2(resumo_para_geracao, tipo_peca)
                
                if resultado_agente2.erro:
                    yield f"data: {json.dumps({'tipo': 'agente', 'agente': 2, 'status': 'erro', 'mensagem': resultado_agente2.erro})}\n\n"
                    yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': resultado_agente2.erro})}\n\n"
                    return
                
                yield f"data: {json.dumps({'tipo': 'agente', 'agente': 2, 'status': 'concluido', 'mensagem': f'{len(resultado_agente2.modulos_ids)} módulos ativados'})}\n\n"
                
                # Agente 3: Gerador
                yield f"data: {json.dumps({'tipo': 'agente', 'agente': 3, 'status': 'ativo', 'mensagem': 'Gerando peça jurídica com IA...'})}\n\n"

                # Log se há observação do usuário
                if req.observacao_usuario:
                    yield f"data: {json.dumps({'tipo': 'info', 'mensagem': 'Observações do usuário serão consideradas na geração'})}\n\n"

                resultado_agente3 = await orq._executar_agente3(
                    resumo_consolidado=resumo_para_geracao,
                    prompt_sistema=resultado_agente2.prompt_sistema,
                    prompt_peca=resultado_agente2.prompt_peca,
                    prompt_conteudo=resultado_agente2.prompt_conteudo,
                    tipo_peca=tipo_peca,
                    observacao_usuario=req.observacao_usuario
                )
                
                if resultado_agente3.erro:
                    yield f"data: {json.dumps({'tipo': 'agente', 'agente': 3, 'status': 'erro', 'mensagem': resultado_agente3.erro})}\n\n"
                    yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': resultado_agente3.erro})}\n\n"
                    return
                
                yield f"data: {json.dumps({'tipo': 'agente', 'agente': 3, 'status': 'concluido', 'mensagem': 'Peça gerada com sucesso!'})}\n\n"
                
                # Prepara lista de documentos processados para salvar
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
                                "data_juntada": doc.data_juntada.isoformat() if doc.data_juntada else None,
                                "data_formatada": doc.data_formatada,
                                "processo_origem": doc.processo_origem
                            })
                
                # Salva no banco (usa resumo filtrado se disponível)
                geracao = GeracaoPeca(
                    numero_cnj=cnj_limpo,
                    numero_cnj_formatado=cnj_limpo,
                    tipo_peca=tipo_peca,
                    conteudo_gerado=resultado_agente3.conteudo_markdown,
                    prompt_enviado=resultado_agente3.prompt_enviado,
                    resumo_consolidado=resumo_para_geracao,
                    documentos_processados=documentos_processados,
                    modelo_usado=modelo,
                    usuario_id=current_user.id
                )
                db.add(geracao)
                db.commit()
                db.refresh(geracao)

                # Cria versão inicial no histórico de versões
                criar_versao_inicial(db, geracao.id, resultado_agente3.conteudo_markdown)

                # Resultado final
                yield f"data: {json.dumps({'tipo': 'sucesso', 'geracao_id': geracao.id, 'tipo_peca': tipo_peca, 'minuta_markdown': resultado_agente3.conteudo_markdown})}\n\n"
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
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': str(e)})}\n\n"
    
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
    Normaliza texto extraído de PDF removendo quebras excessivas e espaços.
    
    Args:
        texto: Texto bruto extraído do PDF
        
    Returns:
        Texto normalizado
    """
    import re
    
    if not texto:
        return ""
    
    # Remove caracteres de controle exceto \n
    texto = re.sub(r'[\x00-\x09\x0b\x0c\x0e-\x1f]', '', texto)
    
    # Substitui múltiplos espaços por um só
    texto = re.sub(r'[ \t]+', ' ', texto)
    
    # Remove espaços no início e fim de cada linha
    linhas = [linha.strip() for linha in texto.split('\n')]
    
    # Junta linhas que foram quebradas no meio de frases
    # (linha que não termina com pontuação seguida de linha que começa com minúscula)
    resultado = []
    buffer = ""
    
    for linha in linhas:
        if not linha:
            # Linha vazia indica parágrafo
            if buffer:
                resultado.append(buffer)
                buffer = ""
            continue
        
        if buffer:
            # Verifica se deve juntar com a linha anterior
            # Junta se: linha anterior não termina com .!?:; e linha atual começa com minúscula
            ultima_char = buffer[-1] if buffer else ''
            primeira_char = linha[0] if linha else ''
            
            if ultima_char not in '.!?;:' and primeira_char.islower():
                # Continua a mesma frase
                buffer += ' ' + linha
            elif ultima_char == '-':
                # Palavra hifenizada quebrada
                buffer = buffer[:-1] + linha
            else:
                # Nova frase/parágrafo
                resultado.append(buffer)
                buffer = linha
        else:
            buffer = linha
    
    if buffer:
        resultado.append(buffer)
    
    # Junta parágrafos com dupla quebra de linha
    texto_final = '\n\n'.join(resultado)
    
    # Remove mais de 2 quebras de linha consecutivas
    texto_final = re.sub(r'\n{3,}', '\n\n', texto_final)
    
    return texto_final.strip()


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
    
    Returns:
        Stream SSE com progresso da geração
    """
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
            
            # Extrai texto dos PDFs
            yield f"data: {json.dumps({'tipo': 'agente', 'agente': 1, 'status': 'ativo', 'mensagem': f'Extraindo texto de {len(arquivos)} arquivo(s)...'})}\n\n"
            
            documentos_texto = []
            for i, arquivo in enumerate(arquivos):
                if not arquivo.filename.lower().endswith('.pdf'):
                    yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'Ignorando arquivo não-PDF: {arquivo.filename}'})}\n\n"
                    continue
                    
                conteudo = await arquivo.read()
                texto = _extrair_texto_pdf(conteudo)
                
                if texto.strip():
                    documentos_texto.append({
                        "nome": arquivo.filename,
                        "texto": texto,
                        "ordem": i + 1
                    })
                    yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'Extraído: {arquivo.filename} ({len(texto)} caracteres)'})}\n\n"
                else:
                    yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'Sem texto extraível: {arquivo.filename}'})}\n\n"
            
            if not documentos_texto:
                yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': 'Nenhum texto foi extraído dos PDFs. Verifique se os arquivos contêm texto legível.'})}\n\n"
                return
            
            # Monta o resumo consolidado a partir dos textos extraídos
            resumo_consolidado = _montar_resumo_pdfs(documentos_texto)
            
            yield f"data: {json.dumps({'tipo': 'agente', 'agente': 1, 'status': 'concluido', 'mensagem': f'{len(documentos_texto)} documento(s) processado(s)'})}\n\n"
            
            # Busca configurações
            config_modelo = db.query(ConfiguracaoIA).filter(
                ConfiguracaoIA.sistema == "gerador_pecas",
                ConfiguracaoIA.chave == "modelo_geracao"
            ).first()
            modelo = config_modelo.valor if config_modelo else "google/gemini-2.5-pro-preview-05-06"
            
            # Inicializa o serviço
            service = GeradorPecasService(
                modelo=modelo,
                db=db,
                group_id=group_id,
                subcategoria_ids=subcategoria_ids
            )
            
            # Se tem orquestrador, usa os agentes 2 e 3
            if service.orquestrador:
                orq = service.orquestrador
                tipo_peca_final = tipo_peca
                
                # Agente 2: Detector de Módulos (e tipo de peça se necessário)
                if not tipo_peca_final:
                    yield f"data: {json.dumps({'tipo': 'agente', 'agente': 2, 'status': 'ativo', 'mensagem': 'Detectando tipo de peça automaticamente...'})}\n\n"
                    
                    deteccao_tipo = await orq.agente2.detectar_tipo_peca(resumo_consolidado)
                    tipo_peca_final = deteccao_tipo.get("tipo_peca")
                    
                    if tipo_peca_final:
                        confianca = deteccao_tipo.get("confianca", "media")
                        yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'Tipo detectado: {tipo_peca_final} (confiança: {confianca})'})}\n\n"
                    else:
                        tipo_peca_final = "contestacao"
                        yield f"data: {json.dumps({'tipo': 'info', 'mensagem': 'Não foi possível detectar automaticamente. Usando: contestação'})}\n\n"
                
                yield f"data: {json.dumps({'tipo': 'agente', 'agente': 2, 'status': 'ativo', 'mensagem': 'Analisando e ativando prompts...'})}\n\n"
                
                resultado_agente2 = await orq._executar_agente2(resumo_consolidado, tipo_peca_final)
                
                if resultado_agente2.erro:
                    yield f"data: {json.dumps({'tipo': 'agente', 'agente': 2, 'status': 'erro', 'mensagem': resultado_agente2.erro})}\n\n"
                    yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': resultado_agente2.erro})}\n\n"
                    return
                
                yield f"data: {json.dumps({'tipo': 'agente', 'agente': 2, 'status': 'concluido', 'mensagem': f'{len(resultado_agente2.modulos_ids)} módulos ativados'})}\n\n"

                # Agente 3: Gerador
                yield f"data: {json.dumps({'tipo': 'agente', 'agente': 3, 'status': 'ativo', 'mensagem': 'Gerando peça jurídica com IA...'})}\n\n"

                # Log se há observação do usuário
                if observacao_usuario:
                    yield f"data: {json.dumps({'tipo': 'info', 'mensagem': 'Observações do usuário serão consideradas na geração'})}\n\n"

                resultado_agente3 = await orq._executar_agente3(
                    resumo_consolidado=resumo_consolidado,
                    prompt_sistema=resultado_agente2.prompt_sistema,
                    prompt_peca=resultado_agente2.prompt_peca,
                    prompt_conteudo=resultado_agente2.prompt_conteudo,
                    tipo_peca=tipo_peca_final,
                    observacao_usuario=observacao_usuario
                )

                if resultado_agente3.erro:
                    yield f"data: {json.dumps({'tipo': 'agente', 'agente': 3, 'status': 'erro', 'mensagem': resultado_agente3.erro})}\n\n"
                    yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': resultado_agente3.erro})}\n\n"
                    return
                
                yield f"data: {json.dumps({'tipo': 'agente', 'agente': 3, 'status': 'concluido', 'mensagem': 'Peça gerada com sucesso!'})}\n\n"
                
                # Prepara lista de documentos processados
                documentos_processados = [
                    {"nome": doc["nome"], "ordem": doc["ordem"]}
                    for doc in documentos_texto
                ]
                
                # Salva no banco
                geracao = GeracaoPeca(
                    numero_cnj="PDF_UPLOAD",  # Identificador para uploads de PDF
                    numero_cnj_formatado="PDFs Anexados",
                    tipo_peca=tipo_peca_final,
                    conteudo_gerado=resultado_agente3.conteudo_markdown,
                    prompt_enviado=resultado_agente3.prompt_enviado,
                    resumo_consolidado=resumo_consolidado,
                    documentos_processados=documentos_processados,
                    modelo_usado=modelo,
                    usuario_id=current_user.id
                )
                db.add(geracao)
                db.commit()
                db.refresh(geracao)

                # Cria versão inicial no histórico de versões
                criar_versao_inicial(db, geracao.id, resultado_agente3.conteudo_markdown)

                # Resultado final
                yield f"data: {json.dumps({'tipo': 'sucesso', 'geracao_id': geracao.id, 'tipo_peca': tipo_peca_final, 'minuta_markdown': resultado_agente3.conteudo_markdown})}\n\n"
            else:
                # Fallback sem orquestrador
                yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': 'Orquestrador de agentes não disponível'})}\n\n"
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': str(e)})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


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
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


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
        
        # Monta nome amigável baseado no processo
        if req.numero_cnj and req.tipo_peca:
            cnj_clean = _limpar_cnj(req.numero_cnj)[-8:]  # Últimos 8 dígitos
            tipo_map = {
                'contestacao': 'contestacao',
                'recurso_apelacao': 'apelacao',
                'contrarrazoes': 'contrarrazoes',
                'parecer': 'parecer'
            }
            tipo_nome = tipo_map.get(req.tipo_peca, req.tipo_peca)
            base_filename = f"{tipo_nome}_{cnj_clean}"
        else:
            base_filename = "peca_juridica"
        
        filename = f"{base_filename}_{file_id[:8]}.docx"
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
    background_tasks: BackgroundTasks,
    token: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user_from_token_or_query)
):
    """Download do documento gerado (aceita token via header ou query param)"""
    
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
            "data": geracao.criado_em.isoformat() if geracao.criado_em else None,
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
            "criado_em": feedback.criado_em.isoformat() if feedback.criado_em else None
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
