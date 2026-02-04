<<<<<<< HEAD
# services/__init__.py
"""
Serviços compartilhados do Portal PGE-MS

Nota: Os imports são feitos através de __getattr__ para suportar lazy loading
e evitar problemas com importação durante testes.
"""

import sys
import os

# Garante que o projeto root está no sys.path
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

__all__ = [
    # Gemini
    "GeminiService",
    "gemini_service",

    # TJ-MS
    "TJMSConfig",
    "get_tjms_config",
    "reload_tjms_config",
    "soap_consultar_processo",
    "soap_baixar_documentos",
    "extrair_subconta",
    "ResultadoSubconta",
    "diagnostico_tjms",

    # Text Normalizer
    "text_normalizer",
    "TextNormalizer",
    "NormalizationMode",
    "NormalizationOptions",
    "NormalizationResult",
    "text_normalizer_router",
]


def __getattr__(name: str):
    """
    Lazy loading de atributos para evitar problemas de importação circular.
    """
    if name == "GeminiService" or name == "gemini_service":
        from services.gemini_service import GeminiService, gemini_service
        return GeminiService if name == "GeminiService" else gemini_service
    
    elif name in ("TJMSConfig", "get_tjms_config", "reload_tjms_config", "soap_consultar_processo", 
                  "soap_baixar_documentos", "extrair_subconta", "ResultadoSubconta", "diagnostico_tjms"):
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
        locals_dict = locals()
        if name in locals_dict:
            return locals_dict[name]
        # Map aliases
        if name == "get_tjms_config":
            return get_tjms_config
        if name == "reload_tjms_config":
            return reload_tjms_config
    
    elif name in ("text_normalizer", "TextNormalizer", "NormalizationMode", "NormalizationOptions",
                  "NormalizationResult", "text_normalizer_router"):
        from services.text_normalizer import (
            text_normalizer,
            TextNormalizer,
            NormalizationMode,
            NormalizationOptions,
            NormalizationResult,
            text_normalizer_router,
        )
        locals_dict = locals()
        if name in locals_dict:
            return locals_dict[name]
    
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
=======
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
from services.text_normalizer import (
    text_normalizer,
    TextNormalizer,
    NormalizationMode,
    NormalizationOptions,
    NormalizationResult,
    text_normalizer_router,
)

__all__ = [
    # Gemini
    "GeminiService",
    "gemini_service",

    # TJ-MS
    "TJMSConfig",
    "get_tjms_config",
    "reload_tjms_config",
    "soap_consultar_processo",
    "soap_baixar_documentos",
    "extrair_subconta",
    "ResultadoSubconta",
    "diagnostico_tjms",

    # Text Normalizer
    "text_normalizer",
    "TextNormalizer",
    "NormalizationMode",
    "NormalizationOptions",
    "NormalizationResult",
    "text_normalizer_router",
]
>>>>>>> origin/main
