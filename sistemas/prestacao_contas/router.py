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
import base64
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends, Query, File, UploadFile, Form
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

from auth.dependencies import get_current_active_user
from auth.models import User
from database.connection import get_db
from sistemas.prestacao_contas.models import GeracaoAnalise, FeedbackPrestacao

# SECURITY: Sanitização de inputs
from utils.security_sanitizer import sanitize_feedback_input
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

    # SECURITY: Sanitiza comentário para prevenir XSS
    clean_comentario = sanitize_feedback_input(request.comentario) if request.comentario else None

    # Cria feedback
    feedback = FeedbackPrestacao(
        geracao_id=request.geracao_id,
        usuario_id=current_user.id,
        avaliacao=request.avaliacao,
        nota=request.nota,
        comentario=clean_comentario,
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
# UPLOAD DE DOCUMENTOS FALTANTES
# =====================================================

@router.post("/upload-documentos-faltantes")
async def upload_documentos_faltantes(
    geracao_id: int = Form(...),
    numero_cnj: Optional[str] = Form(default=None),
    arquivos: List[UploadFile] = File(default=[]),
    notas_fiscais: List[UploadFile] = File(default=[]),
    extrato_subconta: Optional[UploadFile] = File(default=None),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Recebe documentos enviados manualmente pelo usuário quando o sistema
    não conseguiu encontrá-los automaticamente.

    Aceita arquivos via:
    - arquivos: Lista genérica de arquivos
    - notas_fiscais: Notas fiscais específicas
    - extrato_subconta: Extrato da subconta

    Retorna JSON simples indicando sucesso e se reprocessamento é necessário.
    O usuário pode então ir para a página de análise para reprocessar.
    """
    from sistemas.pedido_calculo.document_downloader import extrair_texto_pdf
    from sistemas.prestacao_contas.services import converter_pdf_para_imagens, verificar_estado_expirado

    # Combina todos os arquivos recebidos (de qualquer campo)
    todos_arquivos = []
    
    # Adiciona arquivos genéricos
    todos_arquivos.extend([a for a in arquivos if a.filename and a.size and a.size > 0])
    
    # Adiciona notas fiscais
    todos_arquivos.extend([a for a in notas_fiscais if a.filename and a.size and a.size > 0])
    
    # Adiciona extrato da subconta
    if extrato_subconta and extrato_subconta.filename and extrato_subconta.size and extrato_subconta.size > 0:
        todos_arquivos.append(extrato_subconta)

    if not todos_arquivos:
        raise HTTPException(status_code=400, detail="Nenhum arquivo enviado. Selecione pelo menos um documento.")

    geracao = db.query(GeracaoAnalise).filter(
        GeracaoAnalise.id == geracao_id
    ).first()

    if not geracao:
        raise HTTPException(status_code=404, detail="Análise não encontrada")

    # Verifica permissão
    if geracao.usuario_id != current_user.id:
        raise HTTPException(status_code=403, detail="Sem permissão")

    # Verifica se o estado expirou (mais de 24h)
    estado_expirado = verificar_estado_expirado(geracao)

    try:
        # Processa todos os arquivos enviados
        docs_anexos = geracao.documentos_anexos or []
        arquivos_processados = []

        for i, arquivo in enumerate(todos_arquivos):
            pdf_bytes = await arquivo.read()
            filename = arquivo.filename or f"documento_{i+1}.pdf"

            # Tenta extrair texto
            texto_extraido = extrair_texto_pdf(pdf_bytes)

            # Se texto muito curto, converte para imagem
            if len(texto_extraido) < 500:
                logger.info(f"Documento {filename} com pouco texto, convertendo para imagem...")
                imagens = converter_pdf_para_imagens(pdf_bytes)
                docs_anexos.append({
                    "id": f"manual_{i+1}",
                    "tipo": f"Documento Manual - {filename}",
                    "imagens": imagens,
                    "texto": None
                })
                arquivos_processados.append(f"{filename} (como imagem, {len(imagens)} páginas)")
            else:
                docs_anexos.append({
                    "id": f"manual_{i+1}",
                    "tipo": f"Documento Manual - {filename}",
                    "texto": texto_extraido,
                    "imagens": None
                })
                arquivos_processados.append(f"{filename} (texto extraído)")

            # Se parece ser extrato da subconta, salva também nos campos específicos
            if "extrato" in filename.lower() or "subconta" in filename.lower():
                geracao.extrato_subconta_texto = f"## EXTRATO DA SUBCONTA (ENVIADO MANUALMENTE)\n\n{texto_extraido}"
                geracao.extrato_subconta_pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')

        geracao.documentos_anexos = docs_anexos

        if estado_expirado:
            # Estado expirou - marca para reprocessamento completo
            logger.info(f"Estado expirado para geração {geracao_id} - documentos salvos para nova análise")
            geracao.status = "expirado_com_documentos"
            geracao.erro = "Estado expirado - execute nova análise"
            mensagem = f"Documentos salvos! Como passaram mais de 24h, execute uma nova análise do processo {geracao.numero_cnj}."
        else:
            # Estado válido - marca como pronto para continuar
            logger.info(f"Documentos salvos para geração {geracao_id} - pronto para continuar análise")
            geracao.status = "documentos_recebidos"
            geracao.erro = None
            geracao.documentos_faltantes = None
            geracao.mensagem_erro_usuario = None
            mensagem = f"Documentos recebidos! Execute nova análise para processar os documentos anexados."

        db.commit()

        return {
            "sucesso": True,
            "mensagem": mensagem,
            "arquivos_processados": arquivos_processados,
            "reprocessando": False,
            "estado_expirado": estado_expirado,
            "numero_cnj": geracao.numero_cnj
        }

    except Exception as e:
        logger.exception(f"Erro ao processar documentos: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================
# CANCELAR POR FALTA DE DOCUMENTOS
# =====================================================

class CancelarPorFaltaRequest(BaseModel):
    geracao_id: int
    motivo: str


@router.post("/cancelar-por-falta-documentos")
async def cancelar_por_falta_documentos(
    request: CancelarPorFaltaRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Cancela análise quando o usuário informa que não possui os documentos necessários.
    A análise é salva no histórico com status de erro.
    """
    geracao = db.query(GeracaoAnalise).filter(
        GeracaoAnalise.id == request.geracao_id
    ).first()

    if not geracao:
        raise HTTPException(status_code=404, detail="Análise não encontrada")

    # Verifica permissão
    if geracao.usuario_id != current_user.id:
        raise HTTPException(status_code=403, detail="Sem permissão")

    # Atualiza status para erro
    geracao.status = "erro"
    geracao.erro = f"Análise cancelada: {request.motivo}"
    geracao.parecer = None
    geracao.fundamentacao = None

    db.commit()

    logger.info(f"Análise {request.geracao_id} cancelada por falta de documentos: {request.motivo}")

    return {
        "sucesso": True,
        "mensagem": "Análise cancelada e salva no histórico com status de erro"
    }


# =====================================================
# CONTINUAR SEM NOTA FISCAL
# =====================================================

class ContinuarSemNotaFiscalRequest(BaseModel):
    geracao_id: int


@router.post("/continuar-sem-nota-fiscal")
async def continuar_sem_nota_fiscal(
    request: ContinuarSemNotaFiscalRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Permite ao usuário prosseguir com a análise mesmo sem ter encontrado
    a nota fiscal. A análise continuará com os documentos disponíveis.
    """
    geracao = db.query(GeracaoAnalise).filter(
        GeracaoAnalise.id == request.geracao_id
    ).first()

    if not geracao:
        raise HTTPException(status_code=404, detail="Análise não encontrada")

    # Verifica permissão
    if geracao.usuario_id != current_user.id:
        raise HTTPException(status_code=403, detail="Sem permissão")

    # Verifica se está no status correto
    if geracao.status != "aguardando_nota_fiscal":
        raise HTTPException(
            status_code=400,
            detail=f"Análise não está aguardando nota fiscal (status atual: {geracao.status})"
        )

    # Atualiza status para permitir continuação
    geracao.status = "continuando_sem_nota_fiscal"
    db.commit()

    logger.info(f"Usuário optou por continuar análise {request.geracao_id} sem nota fiscal")

    # Continua a análise
    async def continuar_analise():
        orquestrador = OrquestradorPrestacaoContas(
            db=db,
            usuario_id=current_user.id
        )

        async for evento in orquestrador.continuar_com_documentos_manuais(request.geracao_id):
            evento_json = evento.model_dump_json()
            yield f"data: {evento_json}\n\n"

    return StreamingResponse(
        continuar_analise(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


# =====================================================
# REPROCESSAR COM DOCUMENTOS SALVOS
# =====================================================

class ReprocessarComDocumentosRequest(BaseModel):
    geracao_id: int


@router.post("/reprocessar-com-documentos")
async def reprocessar_com_documentos(
    request: ReprocessarComDocumentosRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Reprocessa uma análise existente usando os documentos já salvos.
    Não deleta o registro, apenas continua a análise de onde parou.
    """
    geracao = db.query(GeracaoAnalise).filter(
        GeracaoAnalise.id == request.geracao_id
    ).first()

    if not geracao:
        raise HTTPException(status_code=404, detail="Análise não encontrada")

    # Verifica permissão
    if geracao.usuario_id != current_user.id:
        raise HTTPException(status_code=403, detail="Sem permissão")

    # Verifica se tem documentos salvos
    tem_extrato = bool(geracao.extrato_subconta_pdf_base64 or geracao.extrato_subconta_texto)
    tem_docs_anexos = bool(geracao.documentos_anexos and len(geracao.documentos_anexos) > 0)

    if not tem_extrato and not tem_docs_anexos:
        raise HTTPException(
            status_code=400,
            detail="Nenhum documento salvo para reprocessar. Anexe os documentos primeiro."
        )

    # Atualiza status para permitir continuação
    geracao.status = "reprocessando"
    geracao.erro = None
    db.commit()

    logger.info(f"Reprocessando análise {request.geracao_id} com documentos salvos")

    # Continua a análise
    async def continuar_analise():
        orquestrador = OrquestradorPrestacaoContas(
            db=db,
            usuario_id=current_user.id
        )

        async for evento in orquestrador.continuar_com_documentos_manuais(request.geracao_id):
            evento_json = evento.model_dump_json()
            yield f"data: {evento_json}\n\n"

    return StreamingResponse(
        continuar_analise(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


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

def _calcular_estado_expirado(geracao: GeracaoAnalise) -> bool:
    """Verifica se o estado salvo expirou."""
    if not geracao.estado_expira_em:
        return True
    from datetime import datetime
    return datetime.utcnow() > geracao.estado_expira_em


def _pode_anexar_documentos(geracao: GeracaoAnalise) -> bool:
    """Verifica se pode anexar documentos.

    Permite anexar se:
    1. Status é aguardando_documentos/aguardando_nota_fiscal E não expirou, OU
    2. Status é erro MAS tem documentos_faltantes (para permitir retry)
    """
    # Se tem documentos faltantes registrados, sempre permite (para retry)
    if geracao.documentos_faltantes and len(geracao.documentos_faltantes) > 0:
        # Verifica se não expirou
        if geracao.estado_expira_em:
            from datetime import datetime
            if datetime.utcnow() > geracao.estado_expira_em:
                return True  # Expirou mas ainda pode anexar para reprocessar
        return True

    # Lógica original para status aguardando
    if geracao.status not in ("aguardando_documentos", "aguardando_nota_fiscal"):
        return False
    return not _calcular_estado_expirado(geracao)


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
                # Campos para retomada de análise
                documentos_faltantes=g.documentos_faltantes,
                mensagem_erro_usuario=g.mensagem_erro_usuario,
                estado_expira_em=g.estado_expira_em,
                estado_expirado=_calcular_estado_expirado(g) if g.status in ("aguardando_documentos", "aguardando_nota_fiscal") else None,
                permite_anexar=_pode_anexar_documentos(g),
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

    # Calcula campos de estado
    is_aguardando = geracao.status in ("aguardando_documentos", "aguardando_nota_fiscal")
    estado_expirado = _calcular_estado_expirado(geracao) if is_aguardando else None
    permite_anexar = _pode_anexar_documentos(geracao)

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
        # Campos de estado para retomada de análise
        documentos_faltantes=geracao.documentos_faltantes,
        mensagem_erro_usuario=geracao.mensagem_erro_usuario,
        estado_expira_em=geracao.estado_expira_em,
        estado_expirado=estado_expirado,
        permite_anexar=permite_anexar,
        # Campos detalhados
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
