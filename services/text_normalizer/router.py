# services/text_normalizer/router.py
"""
Endpoints da API para normalização de texto.
"""

from fastapi import APIRouter, HTTPException
from typing import List

from .models import (
    NormalizationMode,
    NormalizationOptions,
    NormalizationRequest,
    NormalizationResponse,
)
from .normalizer import text_normalizer


router = APIRouter(
    prefix="/api/text",
    tags=["text-normalizer"],
)


@router.post(
    "/normalize",
    response_model=NormalizationResponse,
    summary="Normaliza texto extraído de PDF",
    description="""
    Normaliza texto aplicando pipeline de transformações para limpeza
    e preparação antes de enviar para processamento por IA.

    **Modos disponíveis:**
    - `conservative`: Apenas limpezas básicas, preserva formatação original
    - `balanced`: Limpeza moderada, bom equilíbrio entre qualidade e preservação (padrão)
    - `aggressive`: Máxima compressão, remove redundâncias e duplicações

    **Transformações aplicadas:**
    1. Remoção de caracteres de controle
    2. Remoção de unicode invisível
    3. Colapso de whitespace múltiplo
    4. Remoção de números de página
    5. Detecção/remoção de headers/footers repetidos
    6. Correção de hifenização quebrada
    7. Junção inteligente de linhas
    8. Deduplicação de blocos (modo aggressive)
    9. Limpeza final
    """
)
async def normalize_text(request: NormalizationRequest) -> NormalizationResponse:
    """
    Normaliza texto extraído de PDF.

    Args:
        request: Texto e opções de normalização

    Returns:
        Texto normalizado com estatísticas
    """
    try:
        # Usa opções do request ou padrões
        options = request.options

        # Executa normalização
        result = text_normalizer.normalize(request.text, options)

        return result.to_response()

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao normalizar texto: {str(e)}"
        )


@router.get(
    "/normalize/modes",
    response_model=List[dict],
    summary="Lista modos de normalização disponíveis",
    description="Retorna os modos de normalização disponíveis com descrições."
)
async def get_normalization_modes() -> List[dict]:
    """
    Lista modos de normalização disponíveis.

    Returns:
        Lista de modos com nome e descrição
    """
    return [
        {
            "mode": NormalizationMode.CONSERVATIVE.value,
            "name": "Conservador",
            "description": "Apenas limpezas básicas. Preserva formatação original, ideal para textos que precisam manter estrutura.",
            "features": [
                "Remove caracteres de controle",
                "Remove unicode invisível",
                "Colapsa espaços múltiplos",
                "Corrige hifenização quebrada",
                "Normaliza caracteres unicode"
            ]
        },
        {
            "mode": NormalizationMode.BALANCED.value,
            "name": "Balanceado",
            "description": "Limpeza moderada. Bom equilíbrio entre qualidade e preservação. Recomendado para uso geral.",
            "features": [
                "Todas as features do modo conservador",
                "Remove números de página",
                "Detecta e remove headers/footers repetidos",
                "Junta linhas quebradas no meio de frases"
            ]
        },
        {
            "mode": NormalizationMode.AGGRESSIVE.value,
            "name": "Agressivo",
            "description": "Máxima compressão. Remove redundâncias e duplicações. Ideal para textos muito grandes.",
            "features": [
                "Todas as features do modo balanceado",
                "Remove blocos de texto duplicados",
                "Máxima redução de tamanho"
            ]
        }
    ]


@router.post(
    "/normalize/preview",
    response_model=dict,
    summary="Preview de normalização",
    description="Retorna preview da normalização com primeiros/últimos caracteres e estatísticas."
)
async def preview_normalization(request: NormalizationRequest) -> dict:
    """
    Preview de normalização sem retornar texto completo.

    Útil para textos muito grandes onde queremos ver
    o impacto da normalização sem transferir todo o conteúdo.

    Args:
        request: Texto e opções de normalização

    Returns:
        Preview com início/fim do texto e estatísticas
    """
    try:
        # Executa normalização
        result = text_normalizer.normalize(request.text, request.options)

        # Limita preview
        preview_size = 500
        text = result.text

        return {
            "preview_start": text[:preview_size] if len(text) > preview_size else text,
            "preview_end": text[-preview_size:] if len(text) > preview_size else None,
            "full_length": len(text),
            "stats": result.stats.to_dict(),
            "estimated_tokens": result.estimated_tokens,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao normalizar texto: {str(e)}"
        )
