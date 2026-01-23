# sistemas/relatorio_cumprimento/router.py
"""
Router do Sistema de Relatório de Cumprimento de Sentença

Endpoints:
- POST /processar-stream: Pipeline completo com SSE
- POST /exportar-docx: Exporta para DOCX
- POST /exportar-pdf: Exporta para PDF (via DOCX)
- POST /editar: Edita relatório via chat
- GET /historico: Lista histórico de relatórios gerados
- GET /historico/{id}: Obtém relatório específico
- GET /documento/{numero_processo}/{id_documento}: Obtém documento do TJ-MS

Autor: LAB/PGE-MS
"""

import os
import json
import uuid
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, AsyncGenerator

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth.dependencies import get_current_active_user, get_current_user_from_token_or_query
from auth.models import User
from database.connection import get_db
from utils.timezone import to_iso_utc

from .models import (
    GeracaoRelatorioCumprimento,
    StatusProcessamento,
    CategoriaDocumento,
    DocumentoClassificado,
    DadosProcesso,
    InfoTransitoJulgado
)
from .services import RelatorioCumprimentoService

# Reutiliza o conversor DOCX do gerador de peças
from sistemas.gerador_pecas.docx_converter import DocxConverter


router = APIRouter(tags=["Relatório de Cumprimento"])

# Nome do sistema para configurações
SISTEMA = "relatorio_cumprimento"

# Diretório temporário para arquivos exportados
TEMP_DIR = os.path.join(os.path.dirname(__file__), 'temp_docs')
os.makedirs(TEMP_DIR, exist_ok=True)


# ============================================
# Request/Response Models
# ============================================

class ProcessarRequest(BaseModel):
    """Request para processar processo de cumprimento"""
    numero_cnj: str
    sobrescrever_existente: bool = False


class ExportarDocxRequest(BaseModel):
    """Request para exportar markdown para DOCX"""
    markdown: str
    numero_processo: Optional[str] = None


class EditarRelatorioRequest(BaseModel):
    """Request para editar relatório via chat"""
    geracao_id: int
    mensagem_usuario: str


class FeedbackRequest(BaseModel):
    """Request para enviar feedback sobre o relatório gerado"""
    geracao_id: int
    avaliacao: str  # 'correto', 'parcial', 'incorreto', 'erro_ia'
    nota: Optional[int] = None
    comentario: Optional[str] = None
    campos_incorretos: Optional[list] = None


# ============================================
# Endpoints
# ============================================

@router.post("/processar-stream")
async def processar_stream(
    req: ProcessarRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Processa processo de cumprimento via número CNJ com streaming SSE.

    Pipeline completo:
    1. Consulta processo de cumprimento no TJ-MS
    2. Identifica processo principal (conhecimento)
    3. Baixa documentos relevantes
    4. Localiza trânsito em julgado
    5. Gera relatório com IA
    """
    user_id = current_user.id
    numero_cnj = req.numero_cnj
    sobrescrever_existente = req.sobrescrever_existente

    async def event_generator() -> AsyncGenerator[str, None]:
        geracao_id = None
        tempo_inicio = time.time()

        try:
            yield f"data: {json.dumps({'tipo': 'inicio', 'mensagem': 'Iniciando processamento do relatório de cumprimento...'})}\n\n"

            # Cria serviço
            service = RelatorioCumprimentoService(db)

            # ============================================================
            # ETAPA 1: CONSULTA AO TJ-MS
            # ============================================================
            yield f"data: {json.dumps({'tipo': 'etapa', 'etapa': 1, 'status': 'ativo', 'mensagem': 'Consultando processo de cumprimento no TJ-MS...'})}\n\n"

            dados_consulta, erro = await service.consultar_processo(numero_cnj)

            if erro:
                yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': f'Erro ao consultar processo: {erro}'})}\n\n"
                return

            dados_basicos = dados_consulta["dados_basicos"]
            movimentos = dados_consulta["movimentos"]
            documentos_info = dados_consulta["documentos_info"]

            yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'Processo identificado: {dados_basicos.numero_processo}'})}\n\n"
            yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'Autor: {dados_basicos.autor or "[não identificado]"}'})}\n\n"
            yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'Comarca/Vara: {dados_basicos.comarca or "N/I"} - {dados_basicos.vara or "N/I"}'})}\n\n"

            yield f"data: {json.dumps({'tipo': 'etapa', 'etapa': 1, 'status': 'concluido', 'mensagem': 'Consulta ao TJ-MS concluída'})}\n\n"

            # ============================================================
            # ETAPA 2: IDENTIFICAR PROCESSO PRINCIPAL
            # ============================================================
            yield f"data: {json.dumps({'tipo': 'etapa', 'etapa': 2, 'status': 'ativo', 'mensagem': 'Identificando processo principal (conhecimento)...'})}\n\n"

            numero_principal, erro = await service.identificar_processo_principal(
                dados_consulta["xml_texto"],
                documentos_info
            )

            dados_cumprimento = DadosProcesso(
                numero_processo=numero_cnj,
                numero_processo_formatado=dados_basicos.numero_processo,
                autor=dados_basicos.autor,
                cpf_cnpj_autor=dados_basicos.cpf_autor,
                comarca=dados_basicos.comarca,
                vara=dados_basicos.vara,
                data_ajuizamento=dados_basicos.data_ajuizamento,
                valor_causa=dados_basicos.valor_causa
            )

            dados_principal = None
            if numero_principal:
                yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'Processo principal identificado: {numero_principal}'})}\n\n"

                # Consulta dados do processo principal
                dados_principal_consulta, _ = await service.consultar_processo(numero_principal)
                if dados_principal_consulta:
                    db_principal = dados_principal_consulta["dados_basicos"]
                    dados_principal = DadosProcesso(
                        numero_processo=numero_principal,
                        numero_processo_formatado=db_principal.numero_processo,
                        autor=db_principal.autor,
                        cpf_cnpj_autor=db_principal.cpf_autor,
                        comarca=db_principal.comarca,
                        vara=db_principal.vara,
                        data_ajuizamento=db_principal.data_ajuizamento,
                        valor_causa=db_principal.valor_causa
                    )
                    movimentos = dados_principal_consulta["movimentos"]
            else:
                yield f"data: {json.dumps({'tipo': 'info', 'mensagem': 'Cumprimento no mesmo processo do conhecimento'})}\n\n"

            yield f"data: {json.dumps({'tipo': 'etapa', 'etapa': 2, 'status': 'concluido', 'mensagem': 'Processo principal identificado'})}\n\n"

            # ============================================================
            # ETAPA 3: BAIXAR DOCUMENTOS
            # ============================================================
            yield f"data: {json.dumps({'tipo': 'etapa', 'etapa': 3, 'status': 'ativo', 'mensagem': 'Baixando documentos do TJ-MS...'})}\n\n"

            documentos, erro = await service.baixar_documentos(
                numero_cnj,
                numero_principal,
                documentos_info
            )

            if erro and not documentos:
                yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': f'Erro ao baixar documentos: {erro}'})}\n\n"
                return

            # Estatísticas dos documentos
            qtd_peticao = len([d for d in documentos if d.categoria == CategoriaDocumento.PETICAO_INICIAL_CUMPRIMENTO])
            qtd_sentencas = len([d for d in documentos if d.categoria == CategoriaDocumento.SENTENCA])
            qtd_acordaos = len([d for d in documentos if d.categoria == CategoriaDocumento.ACORDAO])
            qtd_decisoes = len([d for d in documentos if d.categoria == CategoriaDocumento.DECISAO])
            qtd_transito = len([d for d in documentos if d.categoria == CategoriaDocumento.CERTIDAO_TRANSITO])

            yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'Documentos baixados: {len(documentos)}'})}\n\n"
            if qtd_peticao:
                yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'  - Petição inicial do cumprimento: {qtd_peticao}'})}\n\n"
            if qtd_sentencas:
                yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'  - Sentenças: {qtd_sentencas}'})}\n\n"
            if qtd_acordaos:
                yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'  - Acórdãos: {qtd_acordaos}'})}\n\n"
            if qtd_decisoes:
                yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'  - Decisões: {qtd_decisoes}'})}\n\n"
            if qtd_transito:
                yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'  - Certidão de trânsito: {qtd_transito}'})}\n\n"

            yield f"data: {json.dumps({'tipo': 'etapa', 'etapa': 3, 'status': 'concluido', 'mensagem': 'Download de documentos concluído'})}\n\n"

            # ============================================================
            # ETAPA 4: LOCALIZAR TRÂNSITO EM JULGADO
            # ============================================================
            yield f"data: {json.dumps({'tipo': 'etapa', 'etapa': 4, 'status': 'ativo', 'mensagem': 'Localizando trânsito em julgado...'})}\n\n"

            transito_julgado = service.localizar_transito_julgado(movimentos, documentos)

            if transito_julgado.localizado:
                data_str = transito_julgado.data_transito.strftime("%d/%m/%Y") if transito_julgado.data_transito else "Data não identificada"
                yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'Trânsito em julgado localizado: {data_str} (fonte: {transito_julgado.fonte})'})}\n\n"
            else:
                yield f"data: {json.dumps({'tipo': 'info', 'mensagem': 'Trânsito em julgado NÃO localizado'})}\n\n"

            yield f"data: {json.dumps({'tipo': 'etapa', 'etapa': 4, 'status': 'concluido', 'mensagem': 'Verificação de trânsito concluída'})}\n\n"

            # ============================================================
            # ETAPA 5: GERAR RELATÓRIO COM IA
            # ============================================================
            yield f"data: {json.dumps({'tipo': 'etapa', 'etapa': 5, 'status': 'ativo', 'mensagem': 'Gerando relatório com IA...'})}\n\n"

            # Cria registro no banco para obter ID
            geracao = GeracaoRelatorioCumprimento(
                numero_cumprimento=numero_cnj,
                numero_cumprimento_formatado=dados_basicos.numero_processo,
                numero_principal=numero_principal,
                numero_principal_formatado=dados_principal.numero_processo_formatado if dados_principal else None,
                dados_processo_cumprimento=dados_cumprimento.to_dict(),
                dados_processo_principal=dados_principal.to_dict() if dados_principal else None,
                documentos_baixados=[d.to_dict() for d in documentos],
                transito_julgado_localizado=transito_julgado.localizado,
                data_transito_julgado=transito_julgado.data_transito.strftime("%d/%m/%Y") if transito_julgado.data_transito else None,
                status=StatusProcessamento.GERANDO_RELATORIO.value,
                modelo_usado=service.modelo,
                temperatura_usada=str(service.temperatura),
                thinking_level_usado=service.thinking_level,
                usuario_id=user_id
            )
            db.add(geracao)
            db.commit()
            geracao_id = geracao.id

            # Gera relatório com streaming
            relatorio_completo = ""
            async for event in service.gerar_relatorio_stream(
                dados_cumprimento,
                dados_principal,
                documentos,
                transito_julgado,
                geracao_id=geracao_id
            ):
                if event["tipo"] == "chunk":
                    relatorio_completo += event["chunk"]
                    yield f"data: {json.dumps({'tipo': 'geracao_chunk', 'content': event['chunk']})}\n\n"
                elif event["tipo"] == "done":
                    relatorio_completo = event["conteudo"]
                elif event["tipo"] == "error":
                    yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': event['error']})}\n\n"
                    geracao.status = StatusProcessamento.ERRO.value
                    geracao.erro_mensagem = event["error"]
                    db.commit()
                    return

            # Atualiza registro
            tempo_total = int(time.time() - tempo_inicio)
            geracao.conteudo_gerado = relatorio_completo
            geracao.status = StatusProcessamento.CONCLUIDO.value
            geracao.tempo_processamento = tempo_total
            geracao.dados_basicos = {
                "cumprimento": dados_cumprimento.to_dict(),
                "principal": dados_principal.to_dict() if dados_principal else None
            }
            db.commit()

            yield f"data: {json.dumps({'tipo': 'etapa', 'etapa': 5, 'status': 'concluido', 'mensagem': f'Relatório gerado em {tempo_total}s'})}\n\n"

            # Resultado final
            yield f"data: {json.dumps({'tipo': 'sucesso', 'geracao_id': geracao_id, 'dados_cumprimento': dados_cumprimento.to_dict(), 'dados_principal': dados_principal.to_dict() if dados_principal else None, 'relatorio_markdown': relatorio_completo, 'documentos_baixados': [d.to_dict() for d in documentos], 'transito_julgado': transito_julgado.to_dict()})}\n\n"

        except Exception as e:
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': f'Erro inesperado: {str(e)}'})}\n\n"

            if geracao_id:
                geracao = db.query(GeracaoRelatorioCumprimento).filter(
                    GeracaoRelatorioCumprimento.id == geracao_id
                ).first()
                if geracao:
                    geracao.status = StatusProcessamento.ERRO.value
                    geracao.erro_mensagem = str(e)
                    db.commit()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("/exportar-docx")
async def exportar_docx(
    req: ExportarDocxRequest,
    current_user: User = Depends(get_current_active_user)
):
    """
    Exporta relatório para DOCX.
    Usa o mesmo conversor do gerador de peças.
    """
    try:
        # Gera nome do arquivo
        file_id = str(uuid.uuid4())[:8]
        if req.numero_processo:
            numero_limpo = ''.join(c for c in req.numero_processo if c.isdigit())[-8:]
            filename = f"relatorio_cumprimento_{numero_limpo}_{file_id}.docx"
        else:
            filename = f"relatorio_cumprimento_{file_id}.docx"

        filepath = os.path.join(TEMP_DIR, filename)

        # Converte usando o conversor do gerador de peças
        converter = DocxConverter()
        success = converter.convert(req.markdown, filepath)

        if not success:
            raise HTTPException(status_code=500, detail="Erro ao gerar DOCX")

        return {
            "status": "sucesso",
            "url_download": f"/relatorio-cumprimento/api/download/{filename}",
            "filename": filename
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/exportar-pdf")
async def exportar_pdf(
    req: ExportarDocxRequest,
    current_user: User = Depends(get_current_active_user)
):
    """
    Exporta relatório para PDF.
    Fluxo: Markdown -> DOCX -> PDF
    """
    try:
        import subprocess

        # Primeiro gera DOCX
        file_id = str(uuid.uuid4())[:8]
        if req.numero_processo:
            numero_limpo = ''.join(c for c in req.numero_processo if c.isdigit())[-8:]
            base_name = f"relatorio_cumprimento_{numero_limpo}_{file_id}"
        else:
            base_name = f"relatorio_cumprimento_{file_id}"

        docx_path = os.path.join(TEMP_DIR, f"{base_name}.docx")
        pdf_path = os.path.join(TEMP_DIR, f"{base_name}.pdf")

        # Converte para DOCX
        converter = DocxConverter()
        success = converter.convert(req.markdown, docx_path)

        if not success:
            raise HTTPException(status_code=500, detail="Erro ao gerar DOCX intermediário")

        # Converte DOCX para PDF usando LibreOffice (se disponível)
        try:
            result = subprocess.run(
                ["soffice", "--headless", "--convert-to", "pdf", "--outdir", TEMP_DIR, docx_path],
                capture_output=True,
                timeout=60
            )
            if result.returncode != 0 or not os.path.exists(pdf_path):
                raise Exception("LibreOffice não conseguiu converter")
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            # Fallback: usa PyMuPDF para converter DOCX para PDF
            try:
                import fitz
                from docx import Document

                doc_word = Document(docx_path)
                pdf_doc = fitz.open()

                # Configurações da página
                page_width = 595  # A4 width in points
                page_height = 842  # A4 height in points
                margin_left = 72  # 1 inch = 72 points
                margin_right = 72
                margin_top = 72
                margin_bottom = 72
                line_height = 16  # Espaçamento entre linhas
                font_size = 11

                # Largura útil para texto
                text_width = page_width - margin_left - margin_right

                # Cria primeira página
                page = pdf_doc.new_page(width=page_width, height=page_height)
                y_position = margin_top

                for para in doc_word.paragraphs:
                    text = para.text.strip()
                    if not text:
                        # Linha em branco - adiciona espaço
                        y_position += line_height
                        continue

                    # Quebra texto longo em múltiplas linhas
                    # Estimativa: ~80 caracteres por linha com fonte 11pt
                    chars_per_line = 85
                    lines = []

                    while text:
                        if len(text) <= chars_per_line:
                            lines.append(text)
                            break

                        # Encontra último espaço antes do limite
                        split_pos = text.rfind(' ', 0, chars_per_line)
                        if split_pos == -1:
                            split_pos = chars_per_line

                        lines.append(text[:split_pos])
                        text = text[split_pos:].lstrip()

                    # Adiciona cada linha ao PDF
                    for line in lines:
                        # Verifica se precisa de nova página
                        if y_position + line_height > page_height - margin_bottom:
                            page = pdf_doc.new_page(width=page_width, height=page_height)
                            y_position = margin_top

                        page.insert_text((margin_left, y_position), line, fontsize=font_size)
                        y_position += line_height

                    # Espaço extra após parágrafo
                    y_position += line_height * 0.5

                pdf_doc.save(pdf_path)
                pdf_doc.close()
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"Não foi possível converter para PDF: {str(e)}"
                )

        return {
            "status": "sucesso",
            "url_download": f"/relatorio-cumprimento/api/download/{base_name}.pdf",
            "filename": f"{base_name}.pdf"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/download/{filename}")
async def download_documento(
    filename: str,
    token: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user_from_token_or_query)
):
    """Download do documento gerado"""
    filepath = os.path.join(TEMP_DIR, filename)

    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    # Determina o media type
    if filename.endswith(".pdf"):
        media_type = "application/pdf"
    else:
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    return FileResponse(
        filepath,
        media_type=media_type,
        filename=filename
    )


@router.get("/documento/{numero_processo}/{id_documento}")
async def obter_documento(
    numero_processo: str,
    id_documento: str,
    token: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user_from_token_or_query)
):
    """
    Obtém um documento específico do TJ-MS.
    Retorna o PDF em base64 para visualização no frontend.
    """
    try:
        from sistemas.pedido_calculo.document_downloader import DocumentDownloader
        import base64

        async with DocumentDownloader() as downloader:
            docs = await downloader.baixar_documentos(numero_processo, [id_documento])

        if not docs or id_documento not in docs:
            raise HTTPException(status_code=404, detail="Documento não encontrado")

        doc_bytes = docs[id_documento]

        # Converte RTF para PDF se necessário
        if doc_bytes.startswith(b'{\\rtf'):
            from sistemas.pedido_calculo.router import _converter_rtf_para_pdf
            pdf_bytes = _converter_rtf_para_pdf(doc_bytes)
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
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/editar")
async def editar_relatorio(
    req: EditarRelatorioRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Edita relatório via chat com IA."""
    try:
        service = RelatorioCumprimentoService(db)
        novo_markdown, erro = await service.editar_relatorio(
            req.geracao_id,
            req.mensagem_usuario
        )

        if erro:
            return {"status": "erro", "mensagem": erro}

        return {
            "status": "sucesso",
            "relatorio_markdown": novo_markdown
        }

    except Exception as e:
        return {"status": "erro", "mensagem": str(e)}


@router.get("/verificar-existente")
async def verificar_processo_existente(
    numero_cnj: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Verifica se um processo já existe no histórico do usuário.
    """
    numero_cnj_limpo = numero_cnj.replace(".", "").replace("-", "").replace("/", "").strip()

    geracao_existente = db.query(GeracaoRelatorioCumprimento).filter(
        GeracaoRelatorioCumprimento.numero_cumprimento == numero_cnj_limpo,
        GeracaoRelatorioCumprimento.usuario_id == current_user.id
    ).order_by(GeracaoRelatorioCumprimento.criado_em.desc()).first()

    if not geracao_existente:
        return {"existe": False}

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
        "numero_cnj_formatado": geracao_existente.numero_cumprimento_formatado,
        "criado_em": converter_para_brasilia(geracao_existente.criado_em),
        "autor": geracao_existente.dados_basicos.get("cumprimento", {}).get("autor") if geracao_existente.dados_basicos else None
    }


@router.get("/historico")
async def listar_historico(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Lista histórico de relatórios gerados pelo usuário.
    """
    historico = db.query(GeracaoRelatorioCumprimento).filter(
        GeracaoRelatorioCumprimento.usuario_id == current_user.id,
        GeracaoRelatorioCumprimento.status == StatusProcessamento.CONCLUIDO.value
    ).order_by(GeracaoRelatorioCumprimento.criado_em.desc()).limit(50).all()

    return [
        {
            "id": h.id,
            "numero_cumprimento": h.numero_cumprimento,
            "numero_cumprimento_formatado": h.numero_cumprimento_formatado,
            "numero_principal": h.numero_principal,
            "numero_principal_formatado": h.numero_principal_formatado,
            "dados_basicos": h.dados_basicos,
            "transito_julgado_localizado": h.transito_julgado_localizado,
            "data_transito_julgado": h.data_transito_julgado,
            "conteudo_gerado": h.conteudo_gerado,
            "documentos_baixados": h.documentos_baixados,
            "criado_em": to_iso_utc(h.criado_em),
            "tempo_processamento": h.tempo_processamento
        }
        for h in historico
    ]


@router.get("/historico/{id}")
async def obter_historico(
    id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Obtém um relatório específico do histórico.
    """
    geracao = db.query(GeracaoRelatorioCumprimento).filter(
        GeracaoRelatorioCumprimento.id == id,
        GeracaoRelatorioCumprimento.usuario_id == current_user.id
    ).first()

    if not geracao:
        raise HTTPException(status_code=404, detail="Relatório não encontrado")

    return {
        "id": geracao.id,
        "numero_cumprimento": geracao.numero_cumprimento,
        "numero_cumprimento_formatado": geracao.numero_cumprimento_formatado,
        "numero_principal": geracao.numero_principal,
        "numero_principal_formatado": geracao.numero_principal_formatado,
        "dados_processo_cumprimento": geracao.dados_processo_cumprimento,
        "dados_processo_principal": geracao.dados_processo_principal,
        "dados_basicos": geracao.dados_basicos,
        "documentos_baixados": geracao.documentos_baixados,
        "transito_julgado_localizado": geracao.transito_julgado_localizado,
        "data_transito_julgado": geracao.data_transito_julgado,
        "conteudo_gerado": geracao.conteudo_gerado,
        "historico_chat": geracao.historico_chat,
        "modelo_usado": geracao.modelo_usado,
        "temperatura_usada": geracao.temperatura_usada,
        "thinking_level_usado": geracao.thinking_level_usado,
        "criado_em": to_iso_utc(geracao.criado_em),
        "tempo_processamento": geracao.tempo_processamento
    }


@router.post("/feedback")
async def enviar_feedback(
    req: FeedbackRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Envia feedback sobre o relatório gerado."""
    try:
        from .models import FeedbackRelatorioCumprimento

        geracao = db.query(GeracaoRelatorioCumprimento).filter(
            GeracaoRelatorioCumprimento.id == req.geracao_id
        ).first()

        if not geracao:
            raise HTTPException(status_code=404, detail="Geração não encontrada")

        feedback_existente = db.query(FeedbackRelatorioCumprimento).filter(
            FeedbackRelatorioCumprimento.geracao_id == req.geracao_id
        ).first()

        if feedback_existente:
            raise HTTPException(
                status_code=400,
                detail="Feedback já foi enviado para esta geração"
            )

        feedback = FeedbackRelatorioCumprimento(
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
        from .models import FeedbackRelatorioCumprimento

        feedback = db.query(FeedbackRelatorioCumprimento).filter(
            FeedbackRelatorioCumprimento.geracao_id == geracao_id
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
