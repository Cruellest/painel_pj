# services/__init__.py
"""
Serviços compartilhados do Portal PGE-MS
"""

from services.gemini_service import GeminiService, gemini_service
from services.tjms_client import (
    TJMSConfig,
    get_config as get_tjms_config,
    reload_config as reload_tjms_config,
    soap_consultar_processo,
    soap_baixar_documentos,
    extrair_subconta,
    ResultadoSubconta,
    diagnostico_tjms,
)

__all__ = [
    "GeminiService",
    "gemini_service",
    "TJMSConfig",
    "get_tjms_config",
    "reload_tjms_config",
    "soap_consultar_processo",
    "soap_baixar_documentos",
    "extrair_subconta",
    "ResultadoSubconta",
    "diagnostico_tjms",
]
