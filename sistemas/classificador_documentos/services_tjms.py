# sistemas/classificador_documentos/services_tjms.py
"""
Servico de integracao com TJ-MS para download de documentos.

MIGRADO para usar services.tjms unificado em 2026-01-24.

Funcionalidades:
- Consultar processos no TJ-MS
- Listar documentos disponiveis
- Baixar documentos por ID
- Converter RTF para PDF quando necessario

Autor: LAB/PGE-MS
"""

import logging
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass

# Cliente TJMS unificado
from services.tjms import (
    TJMSClient,
    ConsultaOptions,
    DownloadOptions,
    TipoConsulta,
    DocumentoTJMS as TJMSDocumento,
    DocumentoMetadata,
)

logger = logging.getLogger(__name__)


@dataclass
class DocumentoTJMS:
    """Documento baixado do TJ-MS (modelo local para compatibilidade)"""
    id_documento: str
    numero_processo: str
    tipo_documento: Optional[str] = None
    descricao: Optional[str] = None
    conteudo_bytes: Optional[bytes] = None
    formato: str = "pdf"  # "pdf" ou "rtf"
    erro: Optional[str] = None


class TJMSDocumentService:
    """
    Servico para baixar documentos do TJ-MS.

    Usa o TJMSClient unificado de services.tjms.
    """

    def __init__(self):
        self._client: Optional[TJMSClient] = None

    def _get_client(self) -> TJMSClient:
        """Retorna cliente TJMS (lazy init)"""
        if self._client is None:
            self._client = TJMSClient()
        return self._client

    async def consultar_processo(self, numero_cnj: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Consulta processo no TJ-MS e retorna XML.

        Args:
            numero_cnj: Numero CNJ do processo (apenas digitos ou formatado)

        Returns:
            Tupla (xml_texto, erro)
        """
        try:
            client = self._get_client()
            async with client:
                options = ConsultaOptions(tipo=TipoConsulta.COMPLETA)
                processo = await client.consultar_processo(numero_cnj, options)
                return processo.xml_raw, None
        except Exception as e:
            logger.error(f"Erro ao consultar processo {numero_cnj}: {e}")
            return None, str(e)

    async def listar_documentos(self, numero_cnj: str) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        Lista documentos disponiveis em um processo.

        Args:
            numero_cnj: Numero CNJ do processo

        Returns:
            Tupla (lista_documentos, erro)
        """
        try:
            client = self._get_client()
            async with client:
                documentos = await client.listar_documentos(numero_cnj)

            # Converte para formato de dict esperado
            lista = []
            for doc in documentos:
                lista.append({
                    "id": doc.id,
                    "tipo": doc.tipo_codigo,
                    "descricao": doc.descricao,
                    "data": doc.data_juntada.isoformat() if doc.data_juntada else None
                })

            return lista, None

        except Exception as e:
            logger.error(f"Erro ao listar documentos do processo {numero_cnj}: {e}")
            return [], str(e)

    async def baixar_documento(
        self,
        numero_cnj: str,
        id_documento: str
    ) -> DocumentoTJMS:
        """
        Baixa um documento especifico do TJ-MS.

        Args:
            numero_cnj: Numero CNJ do processo
            id_documento: ID do documento no TJ-MS

        Returns:
            DocumentoTJMS com bytes do documento ou erro
        """
        try:
            client = self._get_client()
            async with client:
                options = DownloadOptions(
                    batch_size=1,
                    timeout=180.0
                )
                docs = await client.baixar_documentos(numero_cnj, [id_documento], options)

            if id_documento not in docs or not docs[id_documento].sucesso:
                erro = docs[id_documento].erro if id_documento in docs else "Documento nao encontrado"
                return DocumentoTJMS(
                    id_documento=id_documento,
                    numero_processo=numero_cnj,
                    erro=erro
                )

            doc = docs[id_documento]
            doc_bytes = doc.conteudo_bytes

            # Detecta formato e converte RTF se necessario
            formato = "pdf"
            if doc_bytes and doc_bytes.startswith(b'{\\rtf'):
                formato = "rtf"
                doc_bytes = self._converter_rtf_para_pdf(doc_bytes)

            return DocumentoTJMS(
                id_documento=id_documento,
                numero_processo=numero_cnj,
                conteudo_bytes=doc_bytes,
                formato=formato
            )

        except Exception as e:
            logger.error(f"Erro ao baixar documento {id_documento}: {e}")
            return DocumentoTJMS(
                id_documento=id_documento,
                numero_processo=numero_cnj,
                erro=str(e)
            )

    async def baixar_documentos(
        self,
        numero_cnj: str,
        ids_documentos: List[str]
    ) -> List[DocumentoTJMS]:
        """
        Baixa multiplos documentos do TJ-MS.

        Args:
            numero_cnj: Numero CNJ do processo
            ids_documentos: Lista de IDs de documentos

        Returns:
            Lista de DocumentoTJMS
        """
        try:
            client = self._get_client()
            async with client:
                options = DownloadOptions(
                    batch_size=5,
                    max_paralelo=4,
                    timeout=180.0
                )
                docs = await client.baixar_documentos(numero_cnj, ids_documentos, options)

            resultados = []
            for id_doc in ids_documentos:
                if id_doc in docs and docs[id_doc].sucesso:
                    doc_bytes = docs[id_doc].conteudo_bytes
                    formato = "pdf"

                    if doc_bytes and doc_bytes.startswith(b'{\\rtf'):
                        formato = "rtf"
                        doc_bytes = self._converter_rtf_para_pdf(doc_bytes)

                    resultados.append(DocumentoTJMS(
                        id_documento=id_doc,
                        numero_processo=numero_cnj,
                        conteudo_bytes=doc_bytes,
                        formato=formato
                    ))
                else:
                    erro = docs[id_doc].erro if id_doc in docs else "Documento nao encontrado"
                    resultados.append(DocumentoTJMS(
                        id_documento=id_doc,
                        numero_processo=numero_cnj,
                        erro=erro
                    ))

            return resultados

        except Exception as e:
            logger.error(f"Erro ao baixar documentos: {e}")
            return [
                DocumentoTJMS(
                    id_documento=id_doc,
                    numero_processo=numero_cnj,
                    erro=str(e)
                )
                for id_doc in ids_documentos
            ]

    def _converter_rtf_para_pdf(self, rtf_bytes: bytes) -> bytes:
        """
        Converte RTF para PDF.

        Tenta usar funcao existente do pedido_calculo ou faz conversao simples.
        """
        try:
            from sistemas.pedido_calculo.router import _converter_rtf_para_pdf
            return _converter_rtf_para_pdf(rtf_bytes)
        except ImportError:
            # Fallback: conversao simples com striprtf + reportlab
            try:
                from striprtf.striprtf import rtf_to_text
                from reportlab.lib.pagesizes import A4
                from reportlab.pdfgen import canvas
                import io

                texto = rtf_to_text(rtf_bytes.decode('utf-8', errors='ignore'))

                buffer = io.BytesIO()
                c = canvas.Canvas(buffer, pagesize=A4)
                width, height = A4

                # Configuracoes basicas
                margin = 50
                y_position = height - margin
                line_height = 14

                for line in texto.split('\n'):
                    if y_position < margin:
                        c.showPage()
                        y_position = height - margin

                    c.drawString(margin, y_position, line[:100])  # Limita largura
                    y_position -= line_height

                c.save()
                return buffer.getvalue()

            except Exception as e:
                logger.error(f"Erro ao converter RTF para PDF: {e}")
                # Retorna bytes originais se conversao falhar
                return rtf_bytes


# ============================================
# Instancia global
# ============================================

_tjms_service: Optional[TJMSDocumentService] = None


def get_tjms_service() -> TJMSDocumentService:
    """Retorna instancia singleton do servico TJ-MS"""
    global _tjms_service
    if _tjms_service is None:
        _tjms_service = TJMSDocumentService()
    return _tjms_service
