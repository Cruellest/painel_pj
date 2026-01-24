# sistemas/classificador_documentos/services_tjms.py
"""
Serviço de integração com TJ-MS para download de documentos.

Reutiliza a infraestrutura existente do portal-pge para:
- Consultar processos no TJ-MS
- Baixar documentos por ID
- Converter RTF para PDF quando necessário

Autor: LAB/PGE-MS
"""

import logging
import asyncio
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class DocumentoTJMS:
    """Documento baixado do TJ-MS"""
    id_documento: str
    numero_processo: str
    tipo_documento: Optional[str] = None
    descricao: Optional[str] = None
    conteudo_bytes: Optional[bytes] = None
    formato: str = "pdf"  # "pdf" ou "rtf"
    erro: Optional[str] = None


class TJMSDocumentService:
    """
    Serviço para baixar documentos do TJ-MS.

    Reutiliza o DocumentDownloader existente do sistema pedido_calculo.
    """

    def __init__(self):
        self._downloader = None

    async def _get_downloader(self):
        """Lazy load do DocumentDownloader"""
        if self._downloader is None:
            try:
                from sistemas.pedido_calculo.document_downloader import DocumentDownloader
                self._downloader = DocumentDownloader()
            except ImportError:
                logger.error("DocumentDownloader não disponível")
                raise ImportError("Módulo pedido_calculo.document_downloader não encontrado")
        return self._downloader

    async def consultar_processo(self, numero_cnj: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Consulta processo no TJ-MS e retorna XML.

        Args:
            numero_cnj: Número CNJ do processo (apenas dígitos ou formatado)

        Returns:
            Tupla (xml_texto, erro)
        """
        try:
            downloader = await self._get_downloader()
            async with downloader:
                xml_texto = await downloader.consultar_processo(numero_cnj)
                return xml_texto, None
        except Exception as e:
            logger.error(f"Erro ao consultar processo {numero_cnj}: {e}")
            return None, str(e)

    async def listar_documentos(self, numero_cnj: str) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        Lista documentos disponíveis em um processo.

        Args:
            numero_cnj: Número CNJ do processo

        Returns:
            Tupla (lista_documentos, erro)
        """
        try:
            xml_texto, erro = await self.consultar_processo(numero_cnj)
            if erro:
                return [], erro

            # Parse do XML para extrair documentos
            documentos = self._extrair_documentos_do_xml(xml_texto)
            return documentos, None

        except Exception as e:
            logger.error(f"Erro ao listar documentos do processo {numero_cnj}: {e}")
            return [], str(e)

    def _extrair_documentos_do_xml(self, xml_texto: str) -> List[Dict[str, Any]]:
        """
        Extrai lista de documentos do XML do TJ-MS.

        Returns:
            Lista de dicionários com informações dos documentos
        """
        try:
            import xml.etree.ElementTree as ET

            # Namespaces do MNI
            ns = {
                "ns2": "http://www.cnj.jus.br/intercomunicacao-2.2.2"
            }

            root = ET.fromstring(xml_texto)
            documentos = []

            # Busca documentos no XML
            for doc in root.findall(".//ns2:documento", ns):
                id_doc = doc.get("idDocumento") or doc.findtext("ns2:idDocumento", namespaces=ns)
                tipo = doc.findtext("ns2:tipoDocumento", namespaces=ns)
                descricao = doc.findtext("ns2:descricao", namespaces=ns)
                data = doc.findtext("ns2:dataHora", namespaces=ns)

                if id_doc:
                    documentos.append({
                        "id": id_doc,
                        "tipo": tipo,
                        "descricao": descricao,
                        "data": data
                    })

            return documentos

        except Exception as e:
            logger.error(f"Erro ao extrair documentos do XML: {e}")
            return []

    async def baixar_documento(
        self,
        numero_cnj: str,
        id_documento: str
    ) -> DocumentoTJMS:
        """
        Baixa um documento específico do TJ-MS.

        Args:
            numero_cnj: Número CNJ do processo
            id_documento: ID do documento no TJ-MS

        Returns:
            DocumentoTJMS com bytes do documento ou erro
        """
        try:
            downloader = await self._get_downloader()
            async with downloader:
                docs = await downloader.baixar_documentos(numero_cnj, [id_documento])

            if not docs or id_documento not in docs:
                return DocumentoTJMS(
                    id_documento=id_documento,
                    numero_processo=numero_cnj,
                    erro="Documento não encontrado"
                )

            doc_bytes = docs[id_documento]

            # Detecta formato
            formato = "pdf"
            if doc_bytes.startswith(b'{\\rtf'):
                formato = "rtf"
                # Converte RTF para PDF
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
        Baixa múltiplos documentos do TJ-MS.

        Args:
            numero_cnj: Número CNJ do processo
            ids_documentos: Lista de IDs de documentos

        Returns:
            Lista de DocumentoTJMS
        """
        try:
            downloader = await self._get_downloader()
            async with downloader:
                docs = await downloader.baixar_documentos(numero_cnj, ids_documentos)

            resultados = []
            for id_doc in ids_documentos:
                if id_doc in docs:
                    doc_bytes = docs[id_doc]
                    formato = "pdf"

                    if doc_bytes.startswith(b'{\\rtf'):
                        formato = "rtf"
                        doc_bytes = self._converter_rtf_para_pdf(doc_bytes)

                    resultados.append(DocumentoTJMS(
                        id_documento=id_doc,
                        numero_processo=numero_cnj,
                        conteudo_bytes=doc_bytes,
                        formato=formato
                    ))
                else:
                    resultados.append(DocumentoTJMS(
                        id_documento=id_doc,
                        numero_processo=numero_cnj,
                        erro="Documento não encontrado"
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

        Reutiliza a função existente do sistema pedido_calculo.
        """
        try:
            from sistemas.pedido_calculo.router import _converter_rtf_para_pdf
            return _converter_rtf_para_pdf(rtf_bytes)
        except ImportError:
            # Fallback: tenta conversão simples com striprtf + reportlab
            try:
                from striprtf.striprtf import rtf_to_text
                from reportlab.lib.pagesizes import A4
                from reportlab.pdfgen import canvas
                import io

                texto = rtf_to_text(rtf_bytes.decode('utf-8', errors='ignore'))

                buffer = io.BytesIO()
                c = canvas.Canvas(buffer, pagesize=A4)
                width, height = A4

                # Configurações básicas
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
                # Retorna bytes originais se conversão falhar
                return rtf_bytes


# ============================================
# Instância global
# ============================================

_tjms_service: Optional[TJMSDocumentService] = None


def get_tjms_service() -> TJMSDocumentService:
    """Retorna instância singleton do serviço TJ-MS"""
    global _tjms_service
    if _tjms_service is None:
        _tjms_service = TJMSDocumentService()
    return _tjms_service
