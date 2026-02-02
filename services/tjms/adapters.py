# services/tjms/adapters.py
"""
Adaptadores de compatibilidade para migracao gradual.

Este modulo fornece wrappers que mantem interfaces compativeis
com implementacoes antigas enquanto usam TJMSClient internamente.

Autor: LAB/PGE-MS
"""

import logging
from typing import List, Dict, Optional

from .client import TJMSClient, TJMSError
from .models import DownloadOptions

logger = logging.getLogger(__name__)


# Importa funcao de extracao de texto do pedido_calculo
# NOTA: Futuramente pode ser movida para um modulo compartilhado
def _get_extrair_texto_pdf():
    """Importa funcao de extracao de texto de forma lazy."""
    try:
        from sistemas.pedido_calculo.document_downloader import extrair_texto_pdf
        return extrair_texto_pdf
    except ImportError:
        logger.warning("Funcao extrair_texto_pdf nao disponivel")
        return None


class TJMSDocumentDownloader:
    """
    Wrapper compativel com DocumentDownloader usando TJMSClient.

    Fornece a mesma interface que sistemas.pedido_calculo.DocumentDownloader
    para facilitar migracao gradual.

    Uso:
        async with TJMSDocumentDownloader() as downloader:
            xml = await downloader.consultar_processo(numero_cnj)
            textos = await downloader.baixar_e_extrair_textos(numero_cnj, ids)
    """

    def __init__(self):
        self._client: Optional[TJMSClient] = None
        self._extrair_texto_pdf = _get_extrair_texto_pdf()

    async def __aenter__(self):
        self._client = TJMSClient()
        await self._client.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.__aexit__(exc_type, exc_val, exc_tb)

    async def consultar_processo(self, numero_processo: str) -> str:
        """
        Consulta XML completo do processo.

        Args:
            numero_processo: Numero CNJ (com ou sem formatacao)

        Returns:
            XML da resposta SOAP
        """
        if not self._client:
            raise RuntimeError("Use 'async with TJMSDocumentDownloader()' para gerenciar a sessao")

        processo = await self._client.consultar_processo(numero_processo)
        return processo.xml_raw

    async def baixar_documentos(
        self,
        numero_processo: str,
        ids_documentos: List[str]
    ) -> Dict[str, bytes]:
        """
        Baixa documentos e retorna conteudo binario.

        Args:
            numero_processo: Numero do processo
            ids_documentos: Lista de IDs para baixar

        Returns:
            Dict com id -> bytes do documento
        """
        if not self._client:
            raise RuntimeError("Use 'async with TJMSDocumentDownloader()' para gerenciar a sessao")

        if not ids_documentos:
            return {}

        options = DownloadOptions(batch_size=3, timeout=180.0)
        docs = await self._client.baixar_documentos(
            numero_processo, ids_documentos, options
        )

        resultado = {}
        for doc_id, doc in docs.items():
            if doc.sucesso and doc.conteudo_bytes:
                resultado[doc_id] = doc.conteudo_bytes

        return resultado

    async def baixar_e_extrair_textos(
        self,
        numero_processo: str,
        ids_documentos: List[str]
    ) -> Dict[str, str]:
        """
        Baixa documentos e extrai texto de cada um.

        Args:
            numero_processo: Numero do processo
            ids_documentos: Lista de IDs para baixar

        Returns:
            Dict com id -> texto extraido
        """
        if not self._extrair_texto_pdf:
            raise RuntimeError("Funcao extrair_texto_pdf nao disponivel")

        docs_bytes = await self.baixar_documentos(numero_processo, ids_documentos)

        resultado = {}
        for doc_id, pdf_bytes in docs_bytes.items():
            try:
                texto = self._extrair_texto_pdf(pdf_bytes)
                if texto and not texto.startswith("[Erro"):
                    resultado[doc_id] = texto
            except Exception as e:
                logger.warning(f"Erro ao extrair texto do documento {doc_id}: {e}")

        return resultado

    async def baixar_todos_relevantes(
        self,
        numero_processo: str,
        ids_sentencas: List[str] = None,
        ids_acordaos: List[str] = None,
        ids_certidoes: List[str] = None,
        ids_cumprimento: List[str] = None,
        docs_info_cumprimento: List[Dict] = None,
        usar_ia_planilha: bool = True,
        logger = None,
        id_certidao_transito: str = None
    ) -> Dict[str, str]:
        """
        Baixa e extrai texto de todos os documentos relevantes.

        NOTA: Este metodo delega para a implementacao original em
        pedido_calculo/document_downloader.py que contem logica
        complexa de classificacao de documentos.

        Args:
            numero_processo: Numero CNJ do processo
            ids_sentencas: IDs de sentencas
            ids_acordaos: IDs de acordaos
            ids_certidoes: IDs de certidoes
            ids_cumprimento: IDs de documentos do cumprimento
            docs_info_cumprimento: Info dos docs para classificacao
            usar_ia_planilha: Se True, usa IA para identificar planilha
            logger: Logger opcional
            id_certidao_transito: ID da certidao de transito

        Returns:
            Dict categorizado com textos extraidos
        """
        # Delega para implementacao original (logica complexa de classificacao)
        try:
            from sistemas.pedido_calculo.document_downloader import DocumentDownloader as OriginalDownloader
            async with OriginalDownloader() as original:
                return await original.baixar_todos_relevantes(
                    numero_processo,
                    ids_sentencas=ids_sentencas or [],
                    ids_acordaos=ids_acordaos or [],
                    ids_certidoes=ids_certidoes or [],
                    ids_cumprimento=ids_cumprimento or [],
                    docs_info_cumprimento=docs_info_cumprimento,
                    usar_ia_planilha=usar_ia_planilha,
                    logger=logger,
                    id_certidao_transito=id_certidao_transito
                )
        except ImportError:
            logger.error("Implementacao original de baixar_todos_relevantes nao disponivel")
            return {}


# Alias para compatibilidade
DocumentDownloader = TJMSDocumentDownloader


# ============================================
# Funcoes de compatibilidade com pedido_calculo
# ============================================

async def consultar_processo_async(
    session,  # aiohttp.ClientSession - ignorado, usa TJMSClient
    numero_processo: str,
    timeout: int = 60
) -> str:
    """
    Consulta processo via SOAP - compativel com pedido_calculo.

    Nota: O parametro session e ignorado, pois TJMSClient gerencia
    sua propria sessao HTTP.

    Args:
        session: Sessao aiohttp (ignorada para compatibilidade)
        numero_processo: Numero CNJ do processo
        timeout: Timeout em segundos

    Returns:
        XML da resposta SOAP
    """
    from .client import TJMSClient
    from .models import ConsultaOptions

    async with TJMSClient() as client:
        options = ConsultaOptions(timeout=float(timeout))
        processo = await client.consultar_processo(numero_processo, options)
        return processo.xml_raw


async def baixar_documentos_async(
    session,  # aiohttp.ClientSession - ignorado
    numero_processo: str,
    lista_ids: List[str],
    timeout: int = 180
) -> str:
    """
    Baixa documentos via SOAP - retorna XML com conteudo base64.

    Nota: O parametro session e ignorado.

    Args:
        session: Sessao aiohttp (ignorada)
        numero_processo: Numero CNJ do processo
        lista_ids: Lista de IDs de documentos
        timeout: Timeout em segundos

    Returns:
        XML da resposta SOAP com documentos em base64
    """
    import base64
    from .client import TJMSClient
    from .models import DownloadOptions

    # Limpa numero
    numero_limpo = "".join(c for c in numero_processo if c.isdigit())

    async with TJMSClient() as client:
        options = DownloadOptions(timeout=float(timeout), batch_size=len(lista_ids))
        docs = await client.baixar_documentos(numero_processo, lista_ids, options)

        # Reconstroi XML no formato esperado pelo codigo legado
        xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>']
        xml_parts.append('<resposta>')
        for doc_id, doc in docs.items():
            if doc.sucesso and doc.conteudo_bytes:
                conteudo_b64 = base64.b64encode(doc.conteudo_bytes).decode('utf-8')
                xml_parts.append(f'<documento idDocumento="{doc_id}">')
                xml_parts.append(f'<conteudo>{conteudo_b64}</conteudo>')
                xml_parts.append('</documento>')
        xml_parts.append('</resposta>')

        return '\n'.join(xml_parts)


def extrair_texto_pdf(pdf_bytes: bytes) -> str:
    """
    Extrai texto de PDF - redireciona para funcao original.

    Esta funcao existe em pedido_calculo/document_downloader.py
    e e reutilizada aqui para compatibilidade.
    """
    try:
        from sistemas.pedido_calculo.document_downloader import extrair_texto_pdf as _extrair
        return _extrair(pdf_bytes)
    except ImportError:
        logger.warning("Funcao extrair_texto_pdf nao disponivel")
        return "[Erro: funcao de extracao nao disponivel]"
