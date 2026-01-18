# services/text_normalizer/__init__.py
"""
Serviço Central de Normalização de Texto

Este módulo fornece normalização centralizada de texto extraído de PDFs
antes de enviar para processamento por IA.

Uso básico:
    from services.text_normalizer import text_normalizer

    result = text_normalizer.normalize(texto_pdf)
    texto_limpo = result.text

Uso com opções:
    from services.text_normalizer import text_normalizer, NormalizationMode, NormalizationOptions

    options = NormalizationOptions(mode=NormalizationMode.AGGRESSIVE)
    result = text_normalizer.normalize(texto_pdf, options)

Módulos:
    - normalizer: Classe TextNormalizer e singleton text_normalizer
    - models: Enums, dataclasses e Pydantic models
    - patterns: Regex patterns pré-compilados
    - utils: Funções utilitárias
    - router: Endpoints FastAPI
"""

from .normalizer import TextNormalizer, text_normalizer
from .models import (
    NormalizationMode,
    NormalizationOptions,
    NormalizationStats,
    NormalizationResult,
    NormalizationRequest,
    NormalizationResponse,
)
from .router import router as text_normalizer_router
from .utils import estimate_tokens, normalize_unicode_chars


__all__ = [
    # Classes principais
    "TextNormalizer",
    "text_normalizer",

    # Models
    "NormalizationMode",
    "NormalizationOptions",
    "NormalizationStats",
    "NormalizationResult",
    "NormalizationRequest",
    "NormalizationResponse",

    # Router
    "text_normalizer_router",

    # Utils
    "estimate_tokens",
    "normalize_unicode_chars",
]
