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
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, AsyncGenerator
from sqlalchemy.orm import Session

from auth.dependencies import get_current_active_user, get_current_user_from_token_or_query
from auth.models import User
from database.connection import get_db
from sistemas.gerador_pecas.models import GeracaoPeca, FeedbackPeca
from sistemas.gerador_pecas.services import GeradorPecasService
from admin.models import ConfiguracaoIA, PromptConfig

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

# Armazena estado de processamento em memória (para SSE)
_processamento_status = {}


class ProcessarProcessoRequest(BaseModel):
    numero_cnj: str
    tipo_peca: Optional[str] = None
    resposta_usuario: Optional[str] = None


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
            service = GeradorPecasService(modelo=modelo, db=db)
            
            # Se tem orquestrador, processa com eventos
            if service.orquestrador:
                orq = service.orquestrador
                
                # Determina tipo de peça inicial (se fornecido manualmente)
                tipo_peca_inicial = req.tipo_peca or req.resposta_usuario
                
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
                        print(f"[AVISO] Erro ao carregar filtro de categorias: {e}")
                
                # Agente 1: Coletor TJ-MS
                yield f"data: {json.dumps({'tipo': 'agente', 'agente': 1, 'status': 'ativo', 'mensagem': 'Baixando documentos do TJ-MS...'})}\n\n"
                
                resultado_agente1 = await orq.agente1.coletar_e_resumir(cnj_limpo)
                
                if resultado_agente1.erro:
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
                
                resultado_agente3 = await orq._executar_agente3(
                    resumo_consolidado=resumo_para_geracao,
                    prompt_sistema=resultado_agente2.prompt_sistema,
                    prompt_peca=resultado_agente2.prompt_peca,
                    prompt_conteudo=resultado_agente2.prompt_conteudo,
                    tipo_peca=tipo_peca
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
                    numero_cnj_formatado=req.numero_cnj,
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
                
                # Resultado final
                yield f"data: {json.dumps({'tipo': 'sucesso', 'geracao_id': geracao.id, 'tipo_peca': tipo_peca, 'minuta_markdown': resultado_agente3.conteudo_markdown})}\n\n"
            else:
                # Fallback sem orquestrador
                yield f"data: {json.dumps({'tipo': 'info', 'mensagem': 'Usando modo simplificado...'})}\n\n"
                resultado = await service.processar_processo(
                    numero_cnj=cnj_limpo,
                    numero_cnj_formatado=req.numero_cnj,
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


@router.put("/historico/{geracao_id}")
async def salvar_geracao(
    geracao_id: int,
    req: SalvarMinutaRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Salva alterações feitas na minuta via chat.
    Atualiza o conteudo_gerado com o novo markdown e o histórico de chat.
    """
    try:
        geracao = db.query(GeracaoPeca).filter(
            GeracaoPeca.id == geracao_id,
            GeracaoPeca.usuario_id == current_user.id
        ).first()
        
        if not geracao:
            raise HTTPException(status_code=404, detail="Geração não encontrada")
        
        # Atualiza o conteúdo com o novo markdown
        geracao.conteudo_gerado = req.minuta_markdown
        
        # Atualiza o histórico de chat se fornecido
        if req.historico_chat is not None:
            geracao.historico_chat = req.historico_chat
        
        db.commit()
        
        return {"success": True, "message": "Minuta salva com sucesso"}
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
