# services/tjms/__init__.py
"""
Servico unificado de integracao com TJ-MS.

Este modulo centraliza TODAS as operacoes de comunicacao com o TJ-MS:
- Consulta de processos via SOAP (MNI)
- Download de documentos
- Extracao de subconta via Playwright

Uso:
    from services.tjms import TJMSClient, ConsultaOptions, DownloadOptions

    async with TJMSClient() as client:
        processo = await client.consultar_processo("0800001-00.2024.8.12.0001")
        docs = await client.baixar_documentos(cnj, ["id1", "id2"])
"""

from .config import TJMSConfig, get_config, reload_config
from .models import (
    TipoConsulta,
    ConsultaOptions,
    DownloadOptions,
    Parte,
    Movimento,
    DocumentoMetadata,
    ProcessoTJMS,
    DocumentoTJMS,
    ResultadoSubconta,
)
from .client import TJMSClient, get_client
from .parsers import XMLParserTJMS
from .adapters import (
    TJMSDocumentDownloader,
    DocumentDownloader,
    consultar_processo_async,
    baixar_documentos_async,
    extrair_texto_pdf,
)
from .constants import (
    TipoDocumentoTJMS,
    CodigoMovimento,
    DOCUMENTOS_ADMINISTRATIVOS,
    DOCUMENTOS_TEXTO_INTEGRAL,
    DOCUMENTOS_TECNICOS_SAUDE,
    DOCUMENTOS_DECISAO,
    is_documento_administrativo,
    is_documento_decisao,
    is_documento_tecnico_saude,
    get_nome_tipo_documento,
    get_nome_movimento,
)

__all__ = [
    # Config
    "TJMSConfig",
    "get_config",
    "reload_config",
    # Models
    "TipoConsulta",
    "ConsultaOptions",
    "DownloadOptions",
    "Parte",
    "Movimento",
    "DocumentoMetadata",
    "ProcessoTJMS",
    "DocumentoTJMS",
    "ResultadoSubconta",
    # Client
    "TJMSClient",
    "get_client",
    # Parsers
    "XMLParserTJMS",
    # Adapters
    "TJMSDocumentDownloader",
    "DocumentDownloader",
    # Funcoes de compatibilidade
    "consultar_processo_async",
    "baixar_documentos_async",
    "extrair_texto_pdf",
    # Constants
    "TipoDocumentoTJMS",
    "CodigoMovimento",
    "DOCUMENTOS_ADMINISTRATIVOS",
    "DOCUMENTOS_TEXTO_INTEGRAL",
    "DOCUMENTOS_TECNICOS_SAUDE",
    "DOCUMENTOS_DECISAO",
    "is_documento_administrativo",
    "is_documento_decisao",
    "is_documento_tecnico_saude",
    "get_nome_tipo_documento",
    "get_nome_movimento",
]
