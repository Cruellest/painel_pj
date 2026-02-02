# sistemas/cumprimento_beta/router.py
"""
Router do módulo Cumprimento de Sentença Beta.

Endpoints para:
- Gerenciamento de sessões
- Processamento de documentos (Agente 1)
- Consolidação (Agente 2)
- Chatbot
- Geração de peças
"""

import os
import re
import json
import logging
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from database.connection import get_db
from auth.models import User
from auth.dependencies import get_current_active_user
from sistemas.cumprimento_beta.dependencies import require_beta_access, get_user_pode_acessar_beta
from sistemas.cumprimento_beta.models import (
    SessaoCumprimentoBeta, DocumentoBeta, JSONResumoBeta,
    ConsolidacaoBeta, ConversaBeta, PecaGeradaBeta
)
from sistemas.cumprimento_beta.schemas import (
    IniciarSessaoRequest, IniciarSessaoResponse,
    StatusSessaoResponse, DocumentoResumoResponse,
    ConsolidacaoResponse, MensagemChatRequest, MensagemChatResponse,
    HistoricoConversaResponse, GerarPecaRequest, PecaGeradaResponse,
    ListaSessoesResponse
)
from sistemas.cumprimento_beta.constants import StatusSessao, StatusRelevancia
from sistemas.cumprimento_beta.agente1 import processar_agente1
from sistemas.cumprimento_beta.agente2 import processar_agente2, processar_agente2_streaming
from sistemas.cumprimento_beta.services_chatbot import (
    enviar_mensagem_chat, enviar_mensagem_chat_streaming, obter_historico_chat
)
from sistemas.cumprimento_beta.services_geracao_peca import (
    gerar_peca, obter_peca, listar_pecas_sessao
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cumprimento-beta", tags=["Cumprimento de Sentença Beta"])


def _limpar_cnj(numero_cnj: str) -> str:
    """Limpa número CNJ removendo formatação"""
    if '/' in numero_cnj:
        numero_cnj = numero_cnj.split('/')[0]
    return re.sub(r'\D', '', numero_cnj)


def _formatar_cnj(numero_limpo: str) -> str:
    """Formata número CNJ no padrão NNNNNNN-DD.AAAA.J.TR.OOOO"""
    if len(numero_limpo) != 20:
        return numero_limpo

    return (
        f"{numero_limpo[:7]}-{numero_limpo[7:9]}."
        f"{numero_limpo[9:13]}.{numero_limpo[13]}.{numero_limpo[14:16]}."
        f"{numero_limpo[16:]}"
    )


# ==========================================
# Verificação de Acesso
# ==========================================

@router.get("/acesso")
async def verificar_acesso(
    acesso: dict = Depends(get_user_pode_acessar_beta)
):
    """
    Verifica se o usuário atual pode acessar o beta.

    Útil para o frontend decidir se deve mostrar o botão.
    """
    return acesso


# ==========================================
# Gerenciamento de Sessões
# ==========================================

@router.post("/sessoes", response_model=IniciarSessaoResponse)
async def criar_sessao(
    request: IniciarSessaoRequest,
    current_user: User = Depends(require_beta_access),
    db: Session = Depends(get_db)
):
    """
    Cria uma nova sessão de cumprimento de sentença.

    Requer acesso ao beta (admin ou grupo PS).
    """
    numero_limpo = _limpar_cnj(request.numero_processo)

    if len(numero_limpo) != 20:
        raise HTTPException(
            status_code=400,
            detail="Número de processo inválido. Deve ter 20 dígitos."
        )

    # Cria sessão
    sessao = SessaoCumprimentoBeta(
        user_id=current_user.id,
        numero_processo=numero_limpo,
        numero_processo_formatado=_formatar_cnj(numero_limpo),
        status=StatusSessao.INICIADO
    )

    db.add(sessao)
    db.commit()
    db.refresh(sessao)

    logger.info(f"[BETA] Sessão {sessao.id} criada para processo {numero_limpo}")

    return IniciarSessaoResponse(
        sessao_id=sessao.id,
        numero_processo=sessao.numero_processo,
        numero_processo_formatado=sessao.numero_processo_formatado,
        status=sessao.status,
        created_at=sessao.created_at
    )


@router.get("/sessoes", response_model=ListaSessoesResponse)
async def listar_sessoes(
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(10, ge=1, le=50),
    current_user: User = Depends(require_beta_access),
    db: Session = Depends(get_db)
):
    """Lista sessões do usuário atual."""
    query = db.query(SessaoCumprimentoBeta).filter(
        SessaoCumprimentoBeta.user_id == current_user.id
    )

    # Admin pode ver todas
    if current_user.role == "admin":
        query = db.query(SessaoCumprimentoBeta)

    total = query.count()
    sessoes = query.order_by(
        SessaoCumprimentoBeta.created_at.desc()
    ).offset(
        (pagina - 1) * por_pagina
    ).limit(por_pagina).all()

    return ListaSessoesResponse(
        sessoes=[_sessao_para_response(s, db) for s in sessoes],
        total=total,
        pagina=pagina,
        por_pagina=por_pagina
    )


@router.get("/sessoes/{sessao_id}", response_model=StatusSessaoResponse)
async def obter_sessao(
    sessao_id: int,
    current_user: User = Depends(require_beta_access),
    db: Session = Depends(get_db)
):
    """Obtém status detalhado de uma sessão."""
    sessao = _obter_sessao_usuario(db, sessao_id, current_user)
    return _sessao_para_response(sessao, db)


def _obter_sessao_usuario(
    db: Session,
    sessao_id: int,
    current_user: User
) -> SessaoCumprimentoBeta:
    """Obtém sessão verificando permissão do usuário"""
    sessao = db.query(SessaoCumprimentoBeta).filter(
        SessaoCumprimentoBeta.id == sessao_id
    ).first()

    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    # Verifica permissão (admin vê todas)
    if current_user.role != "admin" and sessao.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Acesso negado a esta sessão")

    return sessao


def _sessao_para_response(sessao: SessaoCumprimentoBeta, db: Session) -> StatusSessaoResponse:
    """Converte sessão para response"""
    tem_consolidacao = db.query(ConsolidacaoBeta).filter(
        ConsolidacaoBeta.sessao_id == sessao.id
    ).count() > 0

    total_conversas = db.query(ConversaBeta).filter(
        ConversaBeta.sessao_id == sessao.id
    ).count()

    total_pecas = db.query(PecaGeradaBeta).filter(
        PecaGeradaBeta.sessao_id == sessao.id
    ).count()

    return StatusSessaoResponse(
        id=sessao.id,
        numero_processo=sessao.numero_processo,
        numero_processo_formatado=sessao.numero_processo_formatado,
        status=sessao.status,
        total_documentos=sessao.total_documentos,
        documentos_processados=sessao.documentos_processados,
        documentos_relevantes=sessao.documentos_relevantes,
        documentos_irrelevantes=sessao.documentos_irrelevantes,
        documentos_ignorados=sessao.documentos_ignorados,
        erro_mensagem=sessao.erro_mensagem,
        created_at=sessao.created_at,
        updated_at=sessao.updated_at,
        finalizado_em=sessao.finalizado_em,
        tem_consolidacao=tem_consolidacao,
        total_conversas=total_conversas,
        total_pecas=total_pecas
    )


# ==========================================
# Processamento (Agente 1)
# ==========================================

@router.post("/sessoes/{sessao_id}/processar")
async def processar_sessao(
    sessao_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_beta_access),
    db: Session = Depends(get_db)
):
    """
    Inicia processamento da sessão (Agente 1).

    Baixa documentos, avalia relevância e extrai JSONs.
    """
    sessao = _obter_sessao_usuario(db, sessao_id, current_user)

    # Verifica se já está processando
    if sessao.status not in [StatusSessao.INICIADO, StatusSessao.ERRO]:
        raise HTTPException(
            status_code=400,
            detail=f"Sessão já está em processamento ou finalizada (status: {sessao.status})"
        )

    # Processa em background
    background_tasks.add_task(
        _processar_agente1_background,
        sessao_id=sessao_id
    )

    return {
        "mensagem": "Processamento iniciado",
        "sessao_id": sessao_id,
        "status": "processando"
    }


async def _processar_agente1_background(sessao_id: int):
    """Processa Agente 1 em background"""
    from database.connection import SessionLocal

    db = SessionLocal()
    try:
        sessao = db.query(SessaoCumprimentoBeta).filter(
            SessaoCumprimentoBeta.id == sessao_id
        ).first()

        if sessao:
            await processar_agente1(db, sessao)

    except Exception as e:
        logger.error(f"[BETA] Erro no processamento background: {e}")
    finally:
        db.close()


@router.get("/sessoes/{sessao_id}/documentos")
async def listar_documentos(
    sessao_id: int,
    status: Optional[str] = None,
    current_user: User = Depends(require_beta_access),
    db: Session = Depends(get_db)
):
    """Lista documentos de uma sessão com status de relevância."""
    sessao = _obter_sessao_usuario(db, sessao_id, current_user)

    query = db.query(DocumentoBeta).filter(
        DocumentoBeta.sessao_id == sessao_id
    )

    if status:
        query = query.filter(DocumentoBeta.status_relevancia == status)

    documentos = query.order_by(DocumentoBeta.created_at.asc()).all()

    return [
        DocumentoResumoResponse(
            id=d.id,
            documento_id_tjms=d.documento_id_tjms,
            codigo_documento=d.codigo_documento,
            descricao_documento=d.descricao_documento,
            data_documento=d.data_documento,
            status_relevancia=d.status_relevancia,
            motivo_irrelevancia=d.motivo_irrelevancia,
            tem_json=d.json_resumo is not None
        )
        for d in documentos
    ]


# ==========================================
# Consolidação (Agente 2)
# ==========================================

@router.get("/sessoes/{sessao_id}/consolidacao")
async def obter_consolidacao(
    sessao_id: int,
    current_user: User = Depends(require_beta_access),
    db: Session = Depends(get_db)
):
    """Obtém consolidação de uma sessão."""
    sessao = _obter_sessao_usuario(db, sessao_id, current_user)

    consolidacao = db.query(ConsolidacaoBeta).filter(
        ConsolidacaoBeta.sessao_id == sessao_id
    ).first()

    if not consolidacao:
        raise HTTPException(status_code=404, detail="Consolidação não encontrada")

    return ConsolidacaoResponse(
        id=consolidacao.id,
        sessao_id=consolidacao.sessao_id,
        resumo_consolidado=consolidacao.resumo_consolidado,
        sugestoes_pecas=consolidacao.sugestoes_pecas,
        dados_processo=consolidacao.dados_processo,
        total_jsons_consolidados=consolidacao.total_jsons_consolidados,
        modelo_usado=consolidacao.modelo_usado,
        created_at=consolidacao.created_at
    )


@router.post("/sessoes/{sessao_id}/consolidar")
async def iniciar_consolidacao(
    sessao_id: int,
    streaming: bool = Query(True),
    current_user: User = Depends(require_beta_access),
    db: Session = Depends(get_db)
):
    """
    Inicia consolidação (Agente 2).

    Se streaming=True, retorna SSE com chunks.
    """
    sessao = _obter_sessao_usuario(db, sessao_id, current_user)

    if sessao.status not in [StatusSessao.CONSOLIDANDO, StatusSessao.CHATBOT]:
        raise HTTPException(
            status_code=400,
            detail="Sessão não está pronta para consolidação"
        )

    if streaming:
        return StreamingResponse(
            _consolidar_streaming(db, sessao),
            media_type="text/event-stream"
        )

    resultado = await processar_agente2(db, sessao)
    return resultado


async def _consolidar_streaming(db: Session, sessao: SessaoCumprimentoBeta):
    """Generator para streaming da consolidação"""
    async for evento in processar_agente2_streaming(db, sessao):
        yield f"data: {json.dumps(evento, ensure_ascii=False)}\n\n"


# ==========================================
# Chatbot
# ==========================================

@router.post("/sessoes/{sessao_id}/chat")
async def enviar_mensagem(
    sessao_id: int,
    request: MensagemChatRequest,
    streaming: bool = Query(True),
    current_user: User = Depends(require_beta_access),
    db: Session = Depends(get_db)
):
    """
    Envia mensagem no chatbot.

    Se streaming=True, retorna SSE com chunks.
    """
    sessao = _obter_sessao_usuario(db, sessao_id, current_user)

    if sessao.status not in [StatusSessao.CHATBOT, StatusSessao.CONSOLIDANDO]:
        raise HTTPException(
            status_code=400,
            detail="Sessão não está no modo chatbot"
        )

    if streaming:
        return StreamingResponse(
            _chat_streaming(db, sessao, request.conteudo),
            media_type="text/event-stream"
        )

    mensagem = await enviar_mensagem_chat(db, sessao, request.conteudo)
    return MensagemChatResponse(
        id=mensagem.id,
        role=mensagem.role,
        conteudo=mensagem.conteudo,
        modelo_usado=mensagem.modelo_usado,
        usou_busca_vetorial=mensagem.usou_busca_vetorial,
        created_at=mensagem.created_at
    )


async def _chat_streaming(db: Session, sessao: SessaoCumprimentoBeta, mensagem: str):
    """Generator para streaming do chat"""
    async for chunk in enviar_mensagem_chat_streaming(db, sessao, mensagem):
        yield f"data: {json.dumps({'chunk': chunk}, ensure_ascii=False)}\n\n"
    yield f"data: {json.dumps({'done': True})}\n\n"


@router.get("/sessoes/{sessao_id}/conversas")
async def listar_conversas(
    sessao_id: int,
    current_user: User = Depends(require_beta_access),
    db: Session = Depends(get_db)
):
    """Lista histórico de conversas de uma sessão."""
    sessao = _obter_sessao_usuario(db, sessao_id, current_user)

    mensagens = obter_historico_chat(db, sessao_id)

    return HistoricoConversaResponse(
        sessao_id=sessao_id,
        mensagens=[
            MensagemChatResponse(
                id=m.id,
                role=m.role,
                conteudo=m.conteudo,
                modelo_usado=m.modelo_usado,
                usou_busca_vetorial=m.usou_busca_vetorial,
                created_at=m.created_at
            )
            for m in mensagens
        ],
        total=len(mensagens)
    )


# ==========================================
# Geração de Peças
# ==========================================

@router.post("/sessoes/{sessao_id}/gerar-peca")
async def criar_peca(
    sessao_id: int,
    request: GerarPecaRequest,
    current_user: User = Depends(require_beta_access),
    db: Session = Depends(get_db)
):
    """Gera uma peça jurídica."""
    sessao = _obter_sessao_usuario(db, sessao_id, current_user)

    if sessao.status not in [StatusSessao.CHATBOT, StatusSessao.CONSOLIDANDO]:
        raise HTTPException(
            status_code=400,
            detail="Sessão não está pronta para gerar peças"
        )

    peca = await gerar_peca(
        db=db,
        sessao=sessao,
        tipo_peca=request.tipo_peca,
        instrucoes=request.instrucoes_adicionais
    )

    download_url = f"/api/cumprimento-beta/sessoes/{sessao_id}/pecas/{peca.id}/download"

    return PecaGeradaResponse(
        id=peca.id,
        sessao_id=peca.sessao_id,
        tipo_peca=peca.tipo_peca,
        titulo=peca.titulo,
        conteudo_markdown=peca.conteudo_markdown,
        download_url=download_url if peca.conteudo_docx_path else None,
        modelo_usado=peca.modelo_usado,
        created_at=peca.created_at
    )


@router.get("/sessoes/{sessao_id}/pecas")
async def listar_pecas(
    sessao_id: int,
    current_user: User = Depends(require_beta_access),
    db: Session = Depends(get_db)
):
    """Lista peças geradas de uma sessão."""
    sessao = _obter_sessao_usuario(db, sessao_id, current_user)

    pecas = listar_pecas_sessao(db, sessao_id)

    return [
        PecaGeradaResponse(
            id=p.id,
            sessao_id=p.sessao_id,
            tipo_peca=p.tipo_peca,
            titulo=p.titulo,
            conteudo_markdown=p.conteudo_markdown,
            download_url=f"/api/cumprimento-beta/sessoes/{sessao_id}/pecas/{p.id}/download" if p.conteudo_docx_path else None,
            modelo_usado=p.modelo_usado,
            created_at=p.created_at
        )
        for p in pecas
    ]


@router.get("/sessoes/{sessao_id}/pecas/{peca_id}/download")
async def download_peca(
    sessao_id: int,
    peca_id: int,
    current_user: User = Depends(require_beta_access),
    db: Session = Depends(get_db)
):
    """Download do DOCX de uma peça."""
    sessao = _obter_sessao_usuario(db, sessao_id, current_user)

    peca = obter_peca(db, peca_id)

    if not peca or peca.sessao_id != sessao_id:
        raise HTTPException(status_code=404, detail="Peça não encontrada")

    if not peca.conteudo_docx_path or not os.path.exists(peca.conteudo_docx_path):
        raise HTTPException(status_code=404, detail="Arquivo DOCX não disponível")

    filename = f"{peca.tipo_peca.replace(' ', '_')}_{sessao.numero_processo}.docx"

    return FileResponse(
        path=peca.conteudo_docx_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=filename
    )
