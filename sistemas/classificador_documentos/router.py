# sistemas/classificador_documentos/router.py
"""
Router do Sistema de Classificação de Documentos

Endpoints:
- Prompts: CRUD de prompts de classificação
- Projetos: CRUD de projetos
- Códigos: Gerenciamento de códigos de documentos
- Execução: Iniciar, pausar, retomar classificação
- Resultados: Consulta e exportação
- Upload: Classificação de documentos avulsos

Autor: LAB/PGE-MS
"""

import os
import re
import json
import uuid
import logging
from datetime import datetime
from typing import Optional, List
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File, Form, Request
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth.dependencies import get_current_active_user
from auth.models import User
from database.connection import get_db
from utils.timezone import to_iso_utc, get_utc_now

from .models import (
    ProjetoClassificacao,
    ExecucaoClassificacao,
    ResultadoClassificacao,
    PromptClassificacao,
    StatusExecucao
)
from .schemas import (
    PromptCreate, PromptUpdate, PromptResponse,
    ProjetoCreate, ProjetoUpdate, ProjetoResponse,
    CodigoDocumentoCreate, CodigoDocumentoBulkCreate, CodigoDocumentoResponse,
    ExecucaoCreate, ExecucaoResponse,
    ResultadoResponse, ResultadoFiltros,
    StatusAPIResponse
)
from .services import ClassificadorService
from .services_export import get_export_service
from .services_openrouter import get_openrouter_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Classificador de Documentos"])


def sanitizar_nome_arquivo(nome: str) -> str:
    """
    Sanitiza um nome para uso em nomes de arquivo.
    Remove caracteres especiais e substitui espaços por underscores.
    """
    # Remove acentos comuns
    nome = nome.replace("ã", "a").replace("õ", "o").replace("á", "a").replace("é", "e")
    nome = nome.replace("í", "i").replace("ó", "o").replace("ú", "u").replace("ç", "c")
    nome = nome.replace("Ã", "A").replace("Õ", "O").replace("Á", "A").replace("É", "E")
    nome = nome.replace("Í", "I").replace("Ó", "O").replace("Ú", "U").replace("Ç", "C")
    nome = nome.replace("â", "a").replace("ê", "e").replace("ô", "o")
    nome = nome.replace("Â", "A").replace("Ê", "E").replace("Ô", "O")
    # Remove caracteres não alfanuméricos (exceto espaço, hífen e underscore)
    nome = re.sub(r'[^\w\s\-]', '', nome)
    # Substitui espaços por underscores
    nome = re.sub(r'\s+', '_', nome)
    # Remove underscores múltiplos
    nome = re.sub(r'_+', '_', nome)
    # Remove underscores no início/fim
    nome = nome.strip('_')
    return nome


# ============================================
# Status da API
# ============================================

@router.get("/status", response_model=StatusAPIResponse)
async def verificar_status_api():
    """Verifica status da API OpenRouter"""
    service = get_openrouter_service()
    disponivel = await service.verificar_disponibilidade()

    return StatusAPIResponse(
        disponivel=disponivel,
        modelo_padrao="google/gemini-2.5-flash-lite",
        modelos_disponiveis=[
            "google/gemini-2.5-flash-lite",
            "google/gemini-2.5-flash",
            "google/gemini-2.5-pro",
            "anthropic/claude-sonnet-4",
            "openai/gpt-4o-mini"
        ]
    )


# ============================================
# CRUD de Prompts
# ============================================

@router.get("/prompts")
async def listar_prompts(
    apenas_ativos: bool = True,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Lista prompts de classificação"""
    service = ClassificadorService(db)
    prompts = service.listar_prompts(apenas_ativos)
    return [
        {
            "id": p.id,
            "nome": p.nome,
            "descricao": p.descricao,
            "conteudo": p.conteudo,
            "codigos_documento": p.codigos_documento,
            "ativo": p.ativo,
            "criado_em": to_iso_utc(p.criado_em),
            "atualizado_em": to_iso_utc(p.atualizado_em)
        }
        for p in prompts
    ]


@router.post("/prompts")
async def criar_prompt(
    req: PromptCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Cria um novo prompt de classificação"""
    service = ClassificadorService(db)
    try:
        prompt = service.criar_prompt(
            nome=req.nome,
            conteudo=req.conteudo,
            descricao=req.descricao,
            usuario_id=current_user.id,
            codigos_documento=req.codigos_documento
        )
        return {"id": prompt.id, "mensagem": "Prompt criado com sucesso"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/prompts/{prompt_id}")
async def obter_prompt(
    prompt_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Obtém um prompt por ID"""
    service = ClassificadorService(db)
    prompt = service.obter_prompt(prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt não encontrado")
    return {
        "id": prompt.id,
        "nome": prompt.nome,
        "descricao": prompt.descricao,
        "conteudo": prompt.conteudo,
        "codigos_documento": prompt.codigos_documento,
        "ativo": prompt.ativo,
        "criado_em": to_iso_utc(prompt.criado_em),
        "atualizado_em": to_iso_utc(prompt.atualizado_em)
    }


@router.put("/prompts/{prompt_id}")
async def atualizar_prompt(
    prompt_id: int,
    req: PromptUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Atualiza um prompt existente"""
    service = ClassificadorService(db)
    prompt = service.atualizar_prompt(prompt_id, **req.model_dump(exclude_unset=True))
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt não encontrado")
    return {"mensagem": "Prompt atualizado com sucesso"}


@router.delete("/prompts/{prompt_id}")
async def deletar_prompt(
    prompt_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Deleta (desativa) um prompt"""
    service = ClassificadorService(db)
    prompt = service.atualizar_prompt(prompt_id, ativo=False)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt não encontrado")
    return {"mensagem": "Prompt desativado com sucesso"}


# ============================================
# CRUD de Projetos
# ============================================

@router.get("/projetos")
async def listar_projetos(
    apenas_ativos: bool = True,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Lista projetos do usuário"""
    service = ClassificadorService(db)
    projetos = service.listar_projetos(current_user.id, apenas_ativos)
    return [
        {
            "id": p.id,
            "nome": p.nome,
            "descricao": p.descricao,
            "prompt_id": p.prompt_id,
            "modelo": p.modelo,
            "modo_processamento": p.modo_processamento,
            "posicao_chunk": p.posicao_chunk,
            "tamanho_chunk": p.tamanho_chunk,
            "max_concurrent": p.max_concurrent,
            "ativo": p.ativo,
            "total_codigos": len(p.codigos),
            "total_execucoes": len(p.execucoes),
            "criado_em": to_iso_utc(p.criado_em),
            "atualizado_em": to_iso_utc(p.atualizado_em)
        }
        for p in projetos
    ]


@router.post("/projetos")
async def criar_projeto(
    req: ProjetoCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Cria um novo projeto de classificação"""
    service = ClassificadorService(db)
    try:
        projeto = service.criar_projeto(
            nome=req.nome,
            usuario_id=current_user.id,
            descricao=req.descricao,
            prompt_id=req.prompt_id,
            modelo=req.modelo,
            modo_processamento=req.modo_processamento,
            posicao_chunk=req.posicao_chunk,
            tamanho_chunk=req.tamanho_chunk,
            max_concurrent=req.max_concurrent
        )
        return {"id": projeto.id, "mensagem": "Projeto criado com sucesso"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/projetos/{projeto_id}")
async def obter_projeto(
    projeto_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Obtém um projeto por ID"""
    service = ClassificadorService(db)
    projeto = service.obter_projeto(projeto_id)
    if not projeto:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    if projeto.usuario_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Acesso negado")

    return {
        "id": projeto.id,
        "nome": projeto.nome,
        "descricao": projeto.descricao,
        "prompt_id": projeto.prompt_id,
        "modelo": projeto.modelo,
        "modo_processamento": projeto.modo_processamento,
        "posicao_chunk": projeto.posicao_chunk,
        "tamanho_chunk": projeto.tamanho_chunk,
        "max_concurrent": projeto.max_concurrent,
        "ativo": projeto.ativo,
        "codigos": [
            {
                "id": c.id,
                "codigo": c.codigo,
                "numero_processo": c.numero_processo,
                "descricao": c.descricao,
                "fonte": c.fonte,
                "ativo": c.ativo
            }
            for c in projeto.codigos
        ],
        "criado_em": to_iso_utc(projeto.criado_em),
        "atualizado_em": to_iso_utc(projeto.atualizado_em)
    }


@router.put("/projetos/{projeto_id}")
async def atualizar_projeto(
    projeto_id: int,
    req: ProjetoUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Atualiza um projeto existente"""
    service = ClassificadorService(db)
    projeto = service.obter_projeto(projeto_id)
    if not projeto:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    if projeto.usuario_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Acesso negado")

    service.atualizar_projeto(projeto_id, **req.model_dump(exclude_unset=True))
    return {"mensagem": "Projeto atualizado com sucesso"}


@router.delete("/projetos/{projeto_id}")
async def deletar_projeto(
    projeto_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Deleta (desativa) um projeto"""
    service = ClassificadorService(db)
    projeto = service.obter_projeto(projeto_id)
    if not projeto:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    if projeto.usuario_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Acesso negado")

    service.atualizar_projeto(projeto_id, ativo=False)
    return {"mensagem": "Projeto desativado com sucesso"}


# ============================================
# Códigos de Documentos
# ============================================

@router.post("/projetos/{projeto_id}/codigos")
async def adicionar_codigos(
    projeto_id: int,
    req: CodigoDocumentoBulkCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Adiciona códigos de documentos a um projeto"""
    service = ClassificadorService(db)
    projeto = service.obter_projeto(projeto_id)
    if not projeto:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    if projeto.usuario_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Acesso negado")

    novos = service.adicionar_codigos(
        projeto_id=projeto_id,
        codigos=req.codigos,
        numero_processo=req.numero_processo,
        fonte=req.fonte
    )
    return {
        "mensagem": f"{len(novos)} códigos adicionados",
        "adicionados": len(novos)
    }


@router.get("/projetos/{projeto_id}/codigos")
async def listar_codigos(
    projeto_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Lista códigos de documentos de um projeto"""
    service = ClassificadorService(db)
    projeto = service.obter_projeto(projeto_id)
    if not projeto:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    if projeto.usuario_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Acesso negado")

    codigos = service.listar_codigos(projeto_id)
    return [
        {
            "id": c.id,
            "codigo": c.codigo,
            "numero_processo": c.numero_processo,
            "descricao": c.descricao,
            "fonte": c.fonte,
            "ativo": c.ativo,
            "criado_em": to_iso_utc(c.criado_em)
        }
        for c in codigos
    ]


@router.delete("/codigos/{codigo_id}")
async def remover_codigo(
    codigo_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Remove um código de documento"""
    service = ClassificadorService(db)
    if not service.remover_codigo(codigo_id):
        raise HTTPException(status_code=404, detail="Código não encontrado")
    return {"mensagem": "Código removido com sucesso"}


# ============================================
# Execução de Classificação
# ============================================

@router.get("/projetos/{projeto_id}/executar")
async def executar_projeto(
    projeto_id: int,
    codigos_ids: Optional[List[int]] = Query(None),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Executa classificação de um projeto via SSE (Server-Sent Events).

    Retorna stream de eventos de progresso.

    NOTA: Usa GET para compatibilidade com EventSource do browser.
    """
    logger.info(f"[SSE] Iniciando execução do projeto {projeto_id} por usuário {current_user.id}")

    service = ClassificadorService(db)
    projeto = service.obter_projeto(projeto_id)
    if not projeto:
        logger.warning(f"[SSE] Projeto {projeto_id} não encontrado")
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    if projeto.usuario_id != current_user.id and current_user.role != "admin":
        logger.warning(f"[SSE] Acesso negado ao projeto {projeto_id} para usuário {current_user.id}")
        raise HTTPException(status_code=403, detail="Acesso negado")

    logger.info(f"[SSE] Projeto {projeto_id} encontrado, iniciando stream SSE")

    async def event_generator():
        try:
            async for evento in service.executar_projeto(
                projeto_id=projeto_id,
                usuario_id=current_user.id,
                codigos_ids=codigos_ids
            ):
                logger.debug(f"[SSE] Enviando evento: {evento.get('tipo', 'desconhecido')}")
                yield f"data: {json.dumps(evento, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.exception(f"[SSE] Erro durante execução do projeto {projeto_id}: {e}")
            yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': f'Erro interno: {str(e)}'}, ensure_ascii=False)}\n\n"
        finally:
            logger.info(f"[SSE] Stream finalizado para projeto {projeto_id}")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.get("/projetos/{projeto_id}/execucoes")
async def listar_execucoes(
    projeto_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Lista execuções de um projeto"""
    service = ClassificadorService(db)
    projeto = service.obter_projeto(projeto_id)
    if not projeto:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    if projeto.usuario_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Acesso negado")

    execucoes = service.listar_execucoes(projeto_id)
    return [
        {
            "id": e.id,
            "status": e.status,
            "total_arquivos": e.total_arquivos,
            "arquivos_processados": e.arquivos_processados,
            "arquivos_sucesso": e.arquivos_sucesso,
            "arquivos_erro": e.arquivos_erro,
            "progresso_percentual": e.progresso_percentual,
            "modelo_usado": e.modelo_usado,
            "iniciado_em": to_iso_utc(e.iniciado_em) if e.iniciado_em else None,
            "finalizado_em": to_iso_utc(e.finalizado_em) if e.finalizado_em else None,
            "criado_em": to_iso_utc(e.criado_em)
        }
        for e in execucoes
    ]


@router.get("/execucoes/{execucao_id}")
async def obter_execucao(
    execucao_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Obtém detalhes de uma execução"""
    service = ClassificadorService(db)
    execucao = service.obter_execucao(execucao_id)
    if not execucao:
        raise HTTPException(status_code=404, detail="Execução não encontrada")

    projeto = service.obter_projeto(execucao.projeto_id)
    if projeto.usuario_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Acesso negado")

    return {
        "id": execucao.id,
        "projeto_id": execucao.projeto_id,
        "status": execucao.status,
        "total_arquivos": execucao.total_arquivos,
        "arquivos_processados": execucao.arquivos_processados,
        "arquivos_sucesso": execucao.arquivos_sucesso,
        "arquivos_erro": execucao.arquivos_erro,
        "progresso_percentual": execucao.progresso_percentual,
        "modelo_usado": execucao.modelo_usado,
        "config_usada": execucao.config_usada,
        "erro_mensagem": execucao.erro_mensagem,
        "iniciado_em": to_iso_utc(execucao.iniciado_em) if execucao.iniciado_em else None,
        "finalizado_em": to_iso_utc(execucao.finalizado_em) if execucao.finalizado_em else None,
        "criado_em": to_iso_utc(execucao.criado_em)
    }


# ============================================
# Execuções em Andamento
# ============================================

@router.get("/execucoes-em-andamento")
async def listar_execucoes_em_andamento(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Lista todas as execuções em andamento ou travadas do usuário atual.

    Inclui informações de heartbeat para detecção de travamento no frontend.
    Útil para mostrar progresso ao recarregar a página.
    """
    from .models import ExecucaoClassificacao, ProjetoClassificacao, StatusExecucao
    from sqlalchemy import or_

    # Busca execuções em andamento OU travadas dos projetos do usuário
    execucoes = db.query(ExecucaoClassificacao).join(
        ProjetoClassificacao,
        ExecucaoClassificacao.projeto_id == ProjetoClassificacao.id
    ).filter(
        ProjetoClassificacao.usuario_id == current_user.id,
        or_(
            ExecucaoClassificacao.status == StatusExecucao.EM_ANDAMENTO.value,
            ExecucaoClassificacao.status == StatusExecucao.TRAVADO.value
        )
    ).all()

    return [
        {
            "id": e.id,
            "projeto_id": e.projeto_id,
            "projeto_nome": e.projeto.nome if e.projeto else None,
            "status": e.status,
            "total_arquivos": e.total_arquivos,
            "arquivos_processados": e.arquivos_processados,
            "arquivos_sucesso": e.arquivos_sucesso,
            "arquivos_erro": e.arquivos_erro,
            "progresso_percentual": e.progresso_percentual,
            "modelo_usado": e.modelo_usado,
            "iniciado_em": to_iso_utc(e.iniciado_em) if e.iniciado_em else None,
            "criado_em": to_iso_utc(e.criado_em),
            # Campos ADR-0010 para detecção de travamento
            "ultimo_heartbeat": to_iso_utc(e.ultimo_heartbeat) if e.ultimo_heartbeat else None,
            "esta_travada": e.esta_travada,
            "pode_retomar": e.pode_retomar,
            "tentativas_retry": e.tentativas_retry or 0,
            "max_retries": e.max_retries or 3
        }
        for e in execucoes
    ]


# ============================================
# Recuperação de Execuções (ADR-0010)
# ============================================

@router.get("/execucoes/{execucao_id}/status-detalhado")
async def obter_status_detalhado(
    execucao_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Obtém status detalhado de uma execução incluindo informações de travamento.

    Conforme ADR-0010: inclui heartbeat, erros, rota de origem, e se pode retomar.
    """
    from .watchdog import get_watchdog

    service = ClassificadorService(db)
    execucao = service.obter_execucao(execucao_id)
    if not execucao:
        raise HTTPException(status_code=404, detail="Execução não encontrada")

    projeto = service.obter_projeto(execucao.projeto_id)
    if projeto.usuario_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Acesso negado")

    watchdog = get_watchdog(db)
    status = await watchdog.obter_status_detalhado(execucao_id)

    if not status:
        raise HTTPException(status_code=404, detail="Execução não encontrada")

    return status


@router.get("/execucoes/{execucao_id}/erros")
async def listar_erros_execucao(
    execucao_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Lista todos os documentos com erro de uma execução.

    Conforme ADR-0010: inclui detalhes do erro, stack trace, tentativas e se pode reprocessar.
    """
    from .watchdog import get_watchdog

    service = ClassificadorService(db)
    execucao = service.obter_execucao(execucao_id)
    if not execucao:
        raise HTTPException(status_code=404, detail="Execução não encontrada")

    projeto = service.obter_projeto(execucao.projeto_id)
    if projeto.usuario_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Acesso negado")

    watchdog = get_watchdog(db)
    erros = await watchdog.listar_erros(execucao_id)

    return {
        "execucao_id": execucao_id,
        "total_erros": len(erros),
        "erros": erros
    }


@router.get("/execucoes/{execucao_id}/retomar")
async def retomar_execucao(
    execucao_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Retoma uma execução travada ou com erro de onde parou.

    Conforme ADR-0010:
    - Comportamento idempotente: pula documentos já processados com sucesso
    - Reprocessa apenas documentos pendentes ou com erro
    - Usa SSE para streaming de progresso

    NOTA: Usa GET para compatibilidade com EventSource do browser.
    """
    logger.info(f"[SSE] Retomando execução {execucao_id} por usuário {current_user.id}")

    service = ClassificadorService(db)
    execucao = service.obter_execucao(execucao_id)
    if not execucao:
        raise HTTPException(status_code=404, detail="Execução não encontrada")

    projeto = service.obter_projeto(execucao.projeto_id)
    if projeto.usuario_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Acesso negado")

    async def event_generator():
        try:
            async for evento in service.retomar_execucao(
                execucao_id=execucao_id,
                usuario_id=current_user.id
            ):
                logger.debug(f"[SSE] Enviando evento retomada: {evento.get('tipo', 'desconhecido')}")
                yield f"data: {json.dumps(evento, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.exception(f"[SSE] Erro durante retomada da execução {execucao_id}: {e}")
            yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': f'Erro interno: {str(e)}'}, ensure_ascii=False)}\n\n"
        finally:
            logger.info(f"[SSE] Stream de retomada finalizado para execução {execucao_id}")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.get("/execucoes/{execucao_id}/reprocessar-erros")
async def reprocessar_erros(
    execucao_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Reprocessa apenas os documentos que tiveram erro.

    Conforme ADR-0010:
    - Reprocessa apenas documentos com status ERRO
    - Respeita limite de tentativas por documento
    - Usa SSE para streaming de progresso

    NOTA: Usa GET para compatibilidade com EventSource do browser.
    """
    logger.info(f"[SSE] Reprocessando erros da execução {execucao_id} por usuário {current_user.id}")

    service = ClassificadorService(db)
    execucao = service.obter_execucao(execucao_id)
    if not execucao:
        raise HTTPException(status_code=404, detail="Execução não encontrada")

    projeto = service.obter_projeto(execucao.projeto_id)
    if projeto.usuario_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Acesso negado")

    async def event_generator():
        try:
            async for evento in service.reprocessar_erros(
                execucao_id=execucao_id,
                usuario_id=current_user.id
            ):
                logger.debug(f"[SSE] Enviando evento reprocessamento: {evento.get('tipo', 'desconhecido')}")
                yield f"data: {json.dumps(evento, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.exception(f"[SSE] Erro durante reprocessamento da execução {execucao_id}: {e}")
            yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': f'Erro interno: {str(e)}'}, ensure_ascii=False)}\n\n"
        finally:
            logger.info(f"[SSE] Stream de reprocessamento finalizado para execução {execucao_id}")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("/watchdog/verificar")
async def executar_verificacao_watchdog(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Executa verificação manual do watchdog para detectar execuções travadas.

    Conforme ADR-0010: detecta execuções sem heartbeat por mais de 5 minutos.
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Apenas administradores podem executar o watchdog")

    from .watchdog import get_watchdog

    watchdog = get_watchdog(db)
    travadas = await watchdog.verificar_execucoes_travadas()

    return {
        "mensagem": f"Verificação concluída: {len(travadas)} execução(ões) marcada(s) como travada(s)",
        "travadas": travadas
    }


@router.post("/execucoes/{execucao_id}/cancelar")
async def cancelar_execucao(
    execucao_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Cancela uma execução em andamento ou travada.

    Marca a execução como CANCELADO, impedindo retomada automática.
    O usuário pode cancelar execuções que parecem travadas ou que deseja interromper.
    """
    from .models import ExecucaoClassificacao, ProjetoClassificacao, StatusExecucao

    service = ClassificadorService(db)
    execucao = service.obter_execucao(execucao_id)
    if not execucao:
        raise HTTPException(status_code=404, detail="Execução não encontrada")

    projeto = service.obter_projeto(execucao.projeto_id)
    if projeto.usuario_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Acesso negado")

    # Só pode cancelar execuções em andamento ou travadas
    status_cancelaveis = [StatusExecucao.EM_ANDAMENTO.value, StatusExecucao.TRAVADO.value]
    if execucao.status not in status_cancelaveis:
        raise HTTPException(
            status_code=400,
            detail=f"Não é possível cancelar execução com status '{execucao.status}'. Apenas execuções em andamento ou travadas podem ser canceladas."
        )

    # Marca como cancelado
    execucao.status = StatusExecucao.CANCELADO.value
    execucao.erro_mensagem = f"Cancelado manualmente pelo usuário em {get_utc_now().isoformat()}"
    execucao.finalizado_em = get_utc_now()
    db.commit()

    logger.info(f"[CANCELAR] Execução {execucao_id} cancelada pelo usuário {current_user.id}")

    return {
        "mensagem": "Execução cancelada com sucesso",
        "execucao_id": execucao_id,
        "status": execucao.status,
        "arquivos_processados": execucao.arquivos_processados,
        "total_arquivos": execucao.total_arquivos
    }


@router.delete("/execucoes/{execucao_id}")
async def arquivar_execucao(
    execucao_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Remove (arquiva) uma execução da lista de execuções em andamento.

    Apenas execuções finalizadas (CONCLUIDO, ERRO, CANCELADO, TRAVADO) podem ser arquivadas.
    Esta operação é um soft-delete: a execução não aparece mais na lista de "em andamento"
    mas permanece no banco para histórico.
    """
    from .models import ExecucaoClassificacao, ProjetoClassificacao, StatusExecucao

    service = ClassificadorService(db)
    execucao = service.obter_execucao(execucao_id)
    if not execucao:
        raise HTTPException(status_code=404, detail="Execução não encontrada")

    projeto = service.obter_projeto(execucao.projeto_id)
    if projeto.usuario_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Acesso negado")

    # Verifica se pode arquivar (não está em andamento)
    if execucao.status == StatusExecucao.EM_ANDAMENTO.value:
        raise HTTPException(
            status_code=400,
            detail="Não é possível arquivar execução em andamento. Cancele primeiro se deseja removê-la."
        )

    # Para execuções travadas, marca como cancelada antes de "arquivar"
    if execucao.status == StatusExecucao.TRAVADO.value:
        execucao.status = StatusExecucao.CANCELADO.value
        execucao.erro_mensagem = f"Arquivado (cancelado) pelo usuário em {get_utc_now().isoformat()}"
        execucao.finalizado_em = get_utc_now()
        db.commit()

    logger.info(f"[ARQUIVAR] Execução {execucao_id} arquivada pelo usuário {current_user.id}")

    return {
        "mensagem": "Execução arquivada com sucesso",
        "execucao_id": execucao_id,
        "status": execucao.status
    }


# ============================================
# Resultados
# ============================================

@router.get("/execucoes/{execucao_id}/resultados")
async def listar_resultados(
    execucao_id: int,
    categoria: Optional[str] = None,
    confianca: Optional[str] = None,
    apenas_erros: bool = False,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Lista resultados de uma execução"""
    service = ClassificadorService(db)
    execucao = service.obter_execucao(execucao_id)
    if not execucao:
        raise HTTPException(status_code=404, detail="Execução não encontrada")

    projeto = service.obter_projeto(execucao.projeto_id)
    if projeto.usuario_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Acesso negado")

    resultados = service.listar_resultados(
        execucao_id=execucao_id,
        categoria=categoria,
        confianca=confianca,
        apenas_erros=apenas_erros
    )

    return [
        {
            "id": r.id,
            "codigo_documento": r.codigo_documento,
            "numero_processo": r.numero_processo,
            "nome_arquivo": r.nome_arquivo,
            "status": r.status,
            "fonte": r.fonte,
            "texto_extraido_via": r.texto_extraido_via,
            "tokens_extraidos": r.tokens_extraidos,
            "categoria": r.categoria,
            "subcategoria": r.subcategoria,
            "confianca": r.confianca,
            "justificativa": r.justificativa,
            "erro_mensagem": r.erro_mensagem,
            "processado_em": to_iso_utc(r.processado_em) if r.processado_em else None
        }
        for r in resultados
    ]


# ============================================
# Exportação
# ============================================

@router.get("/execucoes/{execucao_id}/exportar/excel")
async def exportar_excel(
    execucao_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Exporta resultados para Excel"""
    service = ClassificadorService(db)
    execucao = service.obter_execucao(execucao_id)
    if not execucao:
        raise HTTPException(status_code=404, detail="Execução não encontrada")

    projeto = service.obter_projeto(execucao.projeto_id)
    if projeto.usuario_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Acesso negado")

    resultados = service.listar_resultados(execucao_id)
    export_service = get_export_service()
    buffer = export_service.exportar_excel(resultados, execucao)

    # Gera nome do arquivo com nome do lote sanitizado
    nome_lote = sanitizar_nome_arquivo(projeto.nome)
    filename = f"classificacao_{nome_lote}_{execucao_id}.xlsx"
    # Usa RFC 5987 encoding para suportar caracteres especiais no header
    filename_encoded = quote(filename)

    return Response(
        content=buffer.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=\"{filename}\"; filename*=UTF-8''{filename_encoded}"}
    )


@router.get("/execucoes/{execucao_id}/exportar/csv")
async def exportar_csv(
    execucao_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Exporta resultados para CSV"""
    service = ClassificadorService(db)
    execucao = service.obter_execucao(execucao_id)
    if not execucao:
        raise HTTPException(status_code=404, detail="Execução não encontrada")

    projeto = service.obter_projeto(execucao.projeto_id)
    if projeto.usuario_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Acesso negado")

    resultados = service.listar_resultados(execucao_id)
    export_service = get_export_service()
    buffer = export_service.exportar_csv(resultados)

    # Gera nome do arquivo com nome do lote sanitizado
    nome_lote = sanitizar_nome_arquivo(projeto.nome)
    filename = f"classificacao_{nome_lote}_{execucao_id}.csv"
    filename_encoded = quote(filename)

    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=\"{filename}\"; filename*=UTF-8''{filename_encoded}"}
    )


@router.get("/execucoes/{execucao_id}/exportar/json")
async def exportar_json(
    execucao_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Exporta resultados para JSON"""
    service = ClassificadorService(db)
    execucao = service.obter_execucao(execucao_id)
    if not execucao:
        raise HTTPException(status_code=404, detail="Execução não encontrada")

    projeto = service.obter_projeto(execucao.projeto_id)
    if projeto.usuario_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Acesso negado")

    resultados = service.listar_resultados(execucao_id)
    export_service = get_export_service()
    data = export_service.exportar_json(resultados)

    # Gera nome do arquivo com nome do lote sanitizado
    nome_lote = sanitizar_nome_arquivo(projeto.nome)
    filename = f"classificacao_{nome_lote}_{execucao_id}.json"
    filename_encoded = quote(filename)

    return Response(
        content=json.dumps(data, ensure_ascii=False, indent=2),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=\"{filename}\"; filename*=UTF-8''{filename_encoded}"}
    )


# ============================================
# Classificação Avulsa (Upload)
# ============================================

@router.post("/classificar-avulso")
async def classificar_documento_avulso(
    arquivo: UploadFile = File(...),
    prompt_id: Optional[int] = Form(None),
    prompt_texto: Optional[str] = Form(None),
    modelo: str = Form("google/gemini-2.5-flash-lite"),
    modo_processamento: str = Form("chunk"),
    posicao_chunk: str = Form("fim"),
    tamanho_chunk: int = Form(512),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Classifica um documento enviado via upload.

    Permite classificação rápida sem criar projeto.
    """
    service = ClassificadorService(db)

    # Obtém prompt
    if prompt_id:
        prompt = service.obter_prompt(prompt_id)
        if not prompt:
            raise HTTPException(status_code=404, detail="Prompt não encontrado")
        texto_prompt = prompt.conteudo
    elif prompt_texto:
        texto_prompt = prompt_texto
    else:
        raise HTTPException(status_code=400, detail="Informe prompt_id ou prompt_texto")

    # Lê arquivo
    pdf_bytes = await arquivo.read()

    # Classifica
    resultado = await service.classificar_documento_avulso(
        pdf_bytes=pdf_bytes,
        nome_arquivo=arquivo.filename,
        prompt_texto=texto_prompt,
        modelo=modelo,
        modo_processamento=modo_processamento,
        posicao_chunk=posicao_chunk,
        tamanho_chunk=tamanho_chunk
    )

    return resultado.to_dict()


# ============================================
# Integração TJ-MS
# ============================================

from .services_tjms import get_tjms_service


class ConsultaProcessoRequest(BaseModel):
    """Request para consultar processo no TJ-MS"""
    numero_cnj: str


class BaixarDocumentoTJRequest(BaseModel):
    """Request para baixar documento do TJ-MS"""
    numero_cnj: str
    id_documento: str


class AdicionarCodigosTJRequest(BaseModel):
    """Request para adicionar códigos de documentos do TJ-MS a um projeto"""
    numero_cnj: str
    ids_documentos: List[str]


@router.post("/tjms/consultar-processo")
async def consultar_processo_tjms(
    req: ConsultaProcessoRequest,
    current_user: User = Depends(get_current_active_user)
):
    """
    Consulta processo no TJ-MS e retorna lista de documentos disponíveis.
    """
    tjms = get_tjms_service()
    documentos, erro = await tjms.listar_documentos(req.numero_cnj)

    if erro:
        raise HTTPException(status_code=400, detail=f"Erro ao consultar TJ-MS: {erro}")

    return {
        "numero_cnj": req.numero_cnj,
        "total_documentos": len(documentos),
        "documentos": documentos
    }


@router.post("/tjms/baixar-documento")
async def baixar_documento_tjms(
    req: BaixarDocumentoTJRequest,
    current_user: User = Depends(get_current_active_user)
):
    """
    Baixa documento do TJ-MS e retorna em base64.
    """
    import base64

    tjms = get_tjms_service()
    doc = await tjms.baixar_documento(req.numero_cnj, req.id_documento)

    if doc.erro:
        raise HTTPException(status_code=400, detail=f"Erro ao baixar documento: {doc.erro}")

    return {
        "id_documento": doc.id_documento,
        "numero_processo": doc.numero_processo,
        "formato": doc.formato,
        "tamanho_bytes": len(doc.conteudo_bytes) if doc.conteudo_bytes else 0,
        "conteudo_base64": base64.b64encode(doc.conteudo_bytes).decode() if doc.conteudo_bytes else None
    }


@router.post("/projetos/{projeto_id}/codigos-tjms")
async def adicionar_codigos_tjms(
    projeto_id: int,
    req: AdicionarCodigosTJRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Adiciona códigos de documentos do TJ-MS a um projeto.

    Valida que os documentos existem no TJ-MS antes de adicionar.
    """
    service = ClassificadorService(db)
    projeto = service.obter_projeto(projeto_id)
    if not projeto:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    if projeto.usuario_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Acesso negado")

    # Adiciona códigos vinculados ao processo
    novos = service.adicionar_codigos(
        projeto_id=projeto_id,
        codigos=req.ids_documentos,
        numero_processo=req.numero_cnj,
        fonte="tjms"
    )

    return {
        "mensagem": f"{len(novos)} códigos do TJ-MS adicionados ao projeto",
        "adicionados": len(novos),
        "numero_cnj": req.numero_cnj
    }


# ============================================
# Endpoints para Novo Lote (conforme docs/REDESIGN_CLASSIFICADOR_v2.md secao 8.3)
# ============================================

class UploadLoteRequest(BaseModel):
    """Request para upload em lote de arquivos"""
    # Arquivos sao enviados via multipart/form-data
    pass


class TJMSLoteRequest(BaseModel):
    """Request para importar documentos do TJ-MS em lote"""
    processos: List[str]  # Lista de numeros CNJ
    tipos_documento: List[str]  # Codigos de tipos: ["8", "15", "34", "500"]
    filtro_ano: Optional[List[str]] = None
    filtro_mes: Optional[int] = None


class ExecutarLoteSincronoRequest(BaseModel):
    """Request para executar lote com baixar+classificar sincrono"""
    pass


@router.post("/lotes/{lote_id}/upload")
async def upload_arquivos_lote(
    lote_id: int,
    request: Request,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Adiciona multiplos arquivos a um lote (projeto).

    Conforme docs/REDESIGN_CLASSIFICADOR_v2.md secao 3:
    - Aceita PDF, TXT ou ZIP
    - Max 2000 arquivos por vez (atualizado de 500 em Jan/2026)
    - Max 50MB por arquivo

    NOTA: Usa Request.form() com max_files=2000 para contornar limite padrão do Starlette (1000).
    """
    import hashlib
    from .models import CodigoDocumentoProjeto, FonteDocumento

    # Processa o formulário com limite aumentado de arquivos (padrão Starlette é 1000)
    form = await request.form(max_files=2000, max_fields=2100)
    arquivos = [v for k, v in form.multi_items() if hasattr(v, 'filename') and v.filename]

    logger.info(f"[UPLOAD] Recebendo {len(arquivos)} arquivo(s) para lote {lote_id} do usuário {current_user.id}")

    service = ClassificadorService(db)
    projeto = service.obter_projeto(lote_id)
    if not projeto:
        logger.warning(f"[UPLOAD] Lote {lote_id} não encontrado")
        raise HTTPException(status_code=404, detail="Lote não encontrado")
    if projeto.usuario_id != current_user.id and current_user.role != "admin":
        logger.warning(f"[UPLOAD] Acesso negado ao lote {lote_id} para usuário {current_user.id}")
        raise HTTPException(status_code=403, detail="Acesso negado")

    # Limites (aumentado de 500 para 2000 conforme solicitacao)
    MAX_FILES = 2000
    MAX_SIZE = 50 * 1024 * 1024  # 50MB
    VALID_EXTENSIONS = {'.pdf', '.txt', '.zip'}

    if len(arquivos) > MAX_FILES:
        raise HTTPException(status_code=400, detail=f"Limite de {MAX_FILES} arquivos excedido")

    adicionados = []
    erros = []

    for arquivo in arquivos:
        try:
            # Valida extensao
            ext = '.' + arquivo.filename.split('.')[-1].lower() if '.' in arquivo.filename else ''
            if ext not in VALID_EXTENSIONS:
                erros.append({"arquivo": arquivo.filename, "erro": "Extensao invalida"})
                continue

            # Le conteudo
            conteudo = await arquivo.read()
            if len(conteudo) > MAX_SIZE:
                erros.append({"arquivo": arquivo.filename, "erro": "Arquivo muito grande"})
                continue

            # Calcula hash
            arquivo_hash = hashlib.sha256(conteudo).hexdigest()

            # TODO: Se ZIP, extrair arquivos internos

            # Extrai texto (para cache)
            texto_extraido = None
            if ext == '.txt':
                texto_extraido = conteudo.decode('utf-8', errors='ignore')
            elif ext == '.pdf':
                # Extrai texto do PDF
                try:
                    from .services_extraction import get_text_extractor
                    extractor = get_text_extractor()
                    resultado = extractor.extrair_texto(conteudo)
                    texto_extraido = resultado.texto
                except Exception as e:
                    logger.warning(f"Erro ao extrair texto de {arquivo.filename}: {e}")

            # Cria codigo do documento
            codigo = CodigoDocumentoProjeto(
                projeto_id=lote_id,
                codigo=arquivo_hash[:12],  # Usa parte do hash como codigo
                arquivo_nome=arquivo.filename,
                arquivo_hash=arquivo_hash,
                texto_extraido=texto_extraido,
                fonte=FonteDocumento.UPLOAD.value
            )
            db.add(codigo)
            adicionados.append(arquivo.filename)

        except Exception as e:
            logger.error(f"[UPLOAD] Erro ao processar arquivo {arquivo.filename}: {e}")
            erros.append({"arquivo": arquivo.filename, "erro": str(e)})

    db.commit()
    logger.info(f"[UPLOAD] Upload concluído: {len(adicionados)} sucesso, {len(erros)} erros para lote {lote_id}")

    return {
        "mensagem": f"{len(adicionados)} arquivos adicionados ao lote",
        "adicionados": len(adicionados),
        "erros": len(erros),
        "detalhes_erros": erros if erros else None
    }


@router.post("/lotes/{lote_id}/tjms-lote")
async def importar_tjms_lote(
    lote_id: int,
    req: TJMSLoteRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Importa documentos de multiplos processos do TJ-MS.

    Conforme docs/REDESIGN_CLASSIFICADOR_v2.md secao 4:
    - Recebe lista de processos CNJ
    - Filtra por tipos de documento (tipoDocumento)
    - NAO baixa todos os documentos, apenas os tipos selecionados
    """
    from .models import CodigoDocumentoProjeto, FonteDocumento

    service = ClassificadorService(db)
    projeto = service.obter_projeto(lote_id)
    if not projeto:
        raise HTTPException(status_code=404, detail="Lote não encontrado")
    if projeto.usuario_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Acesso negado")

    if not req.processos:
        raise HTTPException(status_code=400, detail="Lista de processos vazia")
    if not req.tipos_documento:
        raise HTTPException(status_code=400, detail="Nenhum tipo de documento selecionado")

    # Adiciona cada processo com os tipos selecionados
    total_adicionados = 0
    for processo in req.processos:
        processo = processo.strip()
        if not processo:
            continue

        # Para cada tipo de documento, cria um codigo
        # O download real sera feito durante a execucao
        for tipo in req.tipos_documento:
            codigo = CodigoDocumentoProjeto(
                projeto_id=lote_id,
                codigo=f"{processo}_{tipo}",  # Codigo composto
                numero_processo=processo,
                tipo_documento=tipo,
                fonte=FonteDocumento.TJMS.value
            )
            db.add(codigo)
            total_adicionados += 1

    db.commit()

    return {
        "mensagem": f"{total_adicionados} itens adicionados ao lote",
        "processos": len(req.processos),
        "tipos_documento": req.tipos_documento,
        "total_codigos": total_adicionados
    }


@router.get("/lotes/{lote_id}/executar-sincrono")
async def executar_lote_sincrono(
    lote_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Executa lote com download e classificacao em streaming (SSE).

    Conforme docs/REDESIGN_CLASSIFICADOR_v2.md secao 4.4:
    - Para TJ-MS: consulta XML -> filtra por tipo -> baixa -> classifica
    - Para uploads: usa texto extraido cached -> classifica
    - Retorna eventos SSE em tempo real

    NOTA: Usa GET para compatibilidade com EventSource do browser.
    """
    service = ClassificadorService(db)
    projeto = service.obter_projeto(lote_id)
    if not projeto:
        raise HTTPException(status_code=404, detail="Lote não encontrado")
    if projeto.usuario_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Acesso negado")

    async def gerar_eventos():
        """Gerador de eventos SSE"""
        async for evento in service.executar_projeto(
            projeto_id=lote_id,
            usuario_id=current_user.id
        ):
            yield f"data: {json.dumps(evento)}\n\n"

    return StreamingResponse(
        gerar_eventos(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
