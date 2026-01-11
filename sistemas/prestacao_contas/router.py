# sistemas/prestacao_contas/router.py
"""
Router principal do sistema de Prestação de Contas

Endpoints:
- POST /analisar-stream - Pipeline completo via SSE
- POST /responder-duvida - Responde perguntas da IA
- POST /feedback - Registra feedback
- POST /exportar-parecer - Gera DOCX do parecer
- GET /historico - Lista análises do usuário
- GET /historico/{id} - Detalhes de uma análise

Autor: LAB/PGE-MS
"""

import json
import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

from auth.dependencies import get_current_active_user
from auth.models import User
from database.connection import get_db
from sistemas.prestacao_contas.models import GeracaoAnalise, FeedbackPrestacao
from sistemas.prestacao_contas.schemas import (
    AnalisarProcessoRequest,
    ResponderDuvidaRequest,
    FeedbackRequest,
    FeedbackResponse,
    GeracaoResponse,
    GeracaoDetalhadaResponse,
    HistoricoResponse,
)
from sistemas.prestacao_contas.services import OrquestradorPrestacaoContas

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Prestação de Contas"])


# =====================================================
# ANÁLISE VIA SSE (Server-Sent Events)
# =====================================================

@router.post("/analisar-stream")
async def analisar_processo_stream(
    request: AnalisarProcessoRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Executa análise completa de prestação de contas com streaming de eventos.

    Retorna eventos SSE com progresso do processamento.
    """

    async def gerar_eventos():
        logger.debug(f"SSE: Iniciando stream para {request.numero_cnj}")
        orquestrador = OrquestradorPrestacaoContas(
            db=db,
            usuario_id=current_user.id
        )

        try:
            async for evento in orquestrador.processar_completo(
                numero_cnj=request.numero_cnj,
                sobrescrever=request.sobrescrever_existente
            ):
                evento_json = evento.model_dump_json()
                yield f"data: {evento_json}\n\n"
        except Exception as e:
            logger.error(f"SSE: Erro no stream: {e}")
            import traceback
            traceback.print_exc()
            yield f'data: {{"tipo": "erro", "mensagem": "{str(e)}"}}\n\n'
        finally:
            logger.debug("SSE: Stream finalizado")

    return StreamingResponse(
        gerar_eventos(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


# =====================================================
# RESPONDER DÚVIDA
# =====================================================

@router.post("/responder-duvida")
async def responder_duvida(
    request: ResponderDuvidaRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Processa respostas do usuário às perguntas de dúvida da IA.
    Reavalia a prestação de contas com as novas informações.
    """
    orquestrador = OrquestradorPrestacaoContas(
        db=db,
        usuario_id=current_user.id
    )

    try:
        resultado = await orquestrador.responder_duvida(
            geracao_id=request.geracao_id,
            respostas=request.respostas
        )

        return {
            "sucesso": True,
            "parecer": resultado.parecer,
            "fundamentacao": resultado.fundamentacao,
            "irregularidades": resultado.irregularidades,
            "perguntas": resultado.perguntas,
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"Erro ao responder dúvida: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================
# FEEDBACK
# =====================================================

@router.post("/feedback", response_model=FeedbackResponse)
async def registrar_feedback(
    request: FeedbackRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Registra feedback do usuário sobre a análise"""

    # Verifica se geração existe
    geracao = db.query(GeracaoAnalise).filter(
        GeracaoAnalise.id == request.geracao_id
    ).first()

    if not geracao:
        raise HTTPException(status_code=404, detail="Análise não encontrada")

    # Cria feedback
    feedback = FeedbackPrestacao(
        geracao_id=request.geracao_id,
        usuario_id=current_user.id,
        avaliacao=request.avaliacao,
        nota=request.nota,
        comentario=request.comentario,
        parecer_correto=request.parecer_correto,
        valores_corretos=request.valores_corretos,
        medicamento_correto=request.medicamento_correto,
    )

    db.add(feedback)
    db.commit()
    db.refresh(feedback)

    return FeedbackResponse(
        sucesso=True,
        mensagem="Feedback registrado com sucesso",
        feedback_id=feedback.id
    )


# =====================================================
# EXPORTAR PARECER (DOCX)
# =====================================================

class ExportarParecerRequest(BaseModel):
    geracao_id: int


@router.post("/exportar-parecer")
async def exportar_parecer(
    request: ExportarParecerRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Exporta o parecer em formato DOCX"""
    from sistemas.prestacao_contas.docx_converter import converter_parecer_docx

    geracao = db.query(GeracaoAnalise).filter(
        GeracaoAnalise.id == request.geracao_id
    ).first()

    if not geracao:
        raise HTTPException(status_code=404, detail="Análise não encontrada")

    if not geracao.fundamentacao:
        raise HTTPException(status_code=400, detail="Análise não possui fundamentação")

    try:
        caminho_docx = await converter_parecer_docx(
            numero_cnj=geracao.numero_cnj_formatado or geracao.numero_cnj,
            parecer=geracao.parecer,
            fundamentacao=geracao.fundamentacao,
            irregularidades=geracao.irregularidades,
        )

        return FileResponse(
            path=caminho_docx,
            filename=f"parecer_{geracao.numero_cnj}.docx",
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

    except Exception as e:
        logger.exception(f"Erro ao exportar DOCX: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================
# VISUALIZAR EXTRATO SUBCONTA (PDF)
# =====================================================

@router.get("/extrato-subconta/{geracao_id}")
async def obter_extrato_subconta(
    geracao_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Retorna o PDF do extrato da subconta em base64.
    """
    geracao = db.query(GeracaoAnalise).filter(
        GeracaoAnalise.id == geracao_id
    ).first()

    if not geracao:
        raise HTTPException(status_code=404, detail="Análise não encontrada")

    # Verifica permissão
    if geracao.usuario_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Sem permissão")

    if not geracao.extrato_subconta_pdf_base64:
        raise HTTPException(status_code=404, detail="PDF do extrato não disponível")

    return {
        "id": f"extrato_{geracao_id}",
        "conteudo_base64": geracao.extrato_subconta_pdf_base64,
        "tipo": "application/pdf"
    }


# =====================================================
# VISUALIZAR DOCUMENTO (PDF)
# =====================================================

@router.get("/documento/{numero_processo}/{id_documento}")
async def obter_documento(
    numero_processo: str,
    id_documento: str,
    current_user: User = Depends(get_current_active_user),
):
    """
    Obtém um documento específico do TJ-MS.
    Retorna o PDF em base64 para visualização no frontend.
    """
    import base64

    try:
        from sistemas.pedido_calculo.document_downloader import DocumentDownloader

        async with DocumentDownloader() as downloader:
            docs = await downloader.baixar_documentos(numero_processo, [id_documento])

        if not docs or id_documento not in docs:
            raise HTTPException(status_code=404, detail="Documento não encontrado")

        doc_bytes = docs[id_documento]

        # Verifica se é RTF e converte para PDF
        if doc_bytes.startswith(b'{\\rtf'):
            try:
                from sistemas.pedido_calculo.router import _converter_rtf_para_pdf
                pdf_bytes = _converter_rtf_para_pdf(doc_bytes)
            except:
                pdf_bytes = doc_bytes
        else:
            pdf_bytes = doc_bytes

        pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')

        return {
            "id": id_documento,
            "conteudo_base64": pdf_base64,
            "tipo": "application/pdf"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Erro ao obter documento: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================
# VERIFICAR EXISTENTE
# =====================================================

@router.get("/verificar-existente")
async def verificar_processo_existente(
    numero_cnj: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Verifica se um processo já existe no histórico do usuário.
    Retorna informações sobre o registro existente se encontrado.
    """
    from datetime import timezone, timedelta

    # Normaliza o número CNJ (remove formatação)
    numero_cnj_limpo = numero_cnj.replace(".", "").replace("-", "").replace("/", "").strip()

    # Busca registro existente (qualquer status)
    geracao_existente = db.query(GeracaoAnalise).filter(
        GeracaoAnalise.numero_cnj == numero_cnj_limpo,
        GeracaoAnalise.usuario_id == current_user.id
    ).order_by(GeracaoAnalise.criado_em.desc()).first()

    if not geracao_existente:
        return {"existe": False}

    # Timezone de Brasília (UTC-3)
    tz_brasilia = timezone(timedelta(hours=-3))

    def converter_para_brasilia(dt):
        if not dt:
            return None
        dt_utc = dt.replace(tzinfo=timezone.utc)
        dt_brasilia = dt_utc.astimezone(tz_brasilia)
        return dt_brasilia.strftime("%d/%m/%Y às %H:%M")

    return {
        "existe": True,
        "geracao_id": geracao_existente.id,
        "numero_cnj_formatado": geracao_existente.numero_cnj_formatado or geracao_existente.numero_cnj,
        "criado_em": converter_para_brasilia(geracao_existente.criado_em),
        "parecer": geracao_existente.parecer,
        "status": geracao_existente.status,
        "erro": geracao_existente.erro,
    }


# =====================================================
# HISTÓRICO
# =====================================================

@router.get("/historico", response_model=HistoricoResponse)
async def listar_historico(
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0),
    parecer: Optional[str] = Query(default=None),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Lista histórico de análises do usuário"""

    query = db.query(GeracaoAnalise).filter(
        GeracaoAnalise.usuario_id == current_user.id
    )

    if parecer:
        query = query.filter(GeracaoAnalise.parecer == parecer)

    total = query.count()

    geracoes = query.order_by(
        GeracaoAnalise.criado_em.desc()
    ).offset(offset).limit(limit).all()

    return HistoricoResponse(
        total=total,
        geracoes=[
            GeracaoResponse(
                id=g.id,
                numero_cnj=g.numero_cnj,
                numero_cnj_formatado=g.numero_cnj_formatado,
                status=g.status,
                parecer=g.parecer,
                fundamentacao=g.fundamentacao,
                irregularidades=g.irregularidades,
                perguntas_usuario=g.perguntas_usuario,
                valor_bloqueado=g.valor_bloqueado,
                valor_utilizado=g.valor_utilizado,
                valor_devolvido=g.valor_devolvido,
                medicamento_pedido=g.medicamento_pedido,
                medicamento_comprado=g.medicamento_comprado,
                modelo_usado=g.modelo_usado,
                tempo_processamento_ms=g.tempo_processamento_ms,
                erro=g.erro,
                criado_em=g.criado_em,
            )
            for g in geracoes
        ]
    )


@router.get("/historico/{geracao_id}", response_model=GeracaoDetalhadaResponse)
async def obter_geracao(
    geracao_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Obtém detalhes de uma análise específica"""

    geracao = db.query(GeracaoAnalise).filter(
        GeracaoAnalise.id == geracao_id
    ).first()

    if not geracao:
        raise HTTPException(status_code=404, detail="Análise não encontrada")

    # Verifica permissão (dono ou admin)
    if geracao.usuario_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Sem permissão para acessar esta análise")

    return GeracaoDetalhadaResponse(
        id=geracao.id,
        numero_cnj=geracao.numero_cnj,
        numero_cnj_formatado=geracao.numero_cnj_formatado,
        status=geracao.status,
        parecer=geracao.parecer,
        fundamentacao=geracao.fundamentacao,
        irregularidades=geracao.irregularidades,
        perguntas_usuario=geracao.perguntas_usuario,
        valor_bloqueado=geracao.valor_bloqueado,
        valor_utilizado=geracao.valor_utilizado,
        valor_devolvido=geracao.valor_devolvido,
        medicamento_pedido=geracao.medicamento_pedido,
        medicamento_comprado=geracao.medicamento_comprado,
        modelo_usado=geracao.modelo_usado,
        tempo_processamento_ms=geracao.tempo_processamento_ms,
        erro=geracao.erro,
        criado_em=geracao.criado_em,
        extrato_subconta_texto=geracao.extrato_subconta_texto,
        extrato_subconta_pdf_base64=geracao.extrato_subconta_pdf_base64,
        peticao_inicial_id=geracao.peticao_inicial_id,
        peticao_inicial_texto=geracao.peticao_inicial_texto,
        peticao_prestacao_id=geracao.peticao_prestacao_id,
        peticao_prestacao_texto=geracao.peticao_prestacao_texto,
        documentos_anexos=geracao.documentos_anexos,
        peticoes_relevantes=geracao.peticoes_relevantes,
        dados_processo_xml=geracao.dados_processo_xml,
        prompt_identificacao=geracao.prompt_identificacao,
        prompt_analise=geracao.prompt_analise,
        resposta_ia_bruta=geracao.resposta_ia_bruta,
        respostas_usuario=geracao.respostas_usuario,
    )
