# sistemas/gerador_pecas/gemini_client.py
"""
Cliente para API direta do Google Gemini.

NOTA: Este módulo é mantido para retrocompatibilidade.
Para novos desenvolvimentos, use o serviço centralizado:
    from services import gemini_service

Autor: LAB/PGE-MS
"""

# Re-exporta do serviço centralizado para compatibilidade
from services.gemini_service import (
    gemini_service,
    GeminiService,
    GeminiResponse,
    chamar_gemini as chamar_gemini_async,
    chamar_gemini_com_imagens as chamar_gemini_com_imagens_async,
)


def normalizar_modelo(modelo: str) -> str:
    """Normaliza o nome do modelo (compatibilidade)"""
    return GeminiService.normalize_model(modelo)


async def chamar_gemini_aiohttp_async(
    session,
    prompt: str,
    system_prompt: str = "",
    modelo: str = "gemini-2.5-flash-lite",
    max_tokens: int = 8192,
    temperature: float = 0.3,
    api_key: str = None
) -> str:
    """Chamada com sessão aiohttp (compatibilidade)"""
    response = await gemini_service.generate_with_session(
        session=session,
        prompt=prompt,
        system_prompt=system_prompt,
        model=modelo,
        max_tokens=max_tokens,
        temperature=temperature
    )
    
    if not response.success:
        raise ValueError(response.error)
    
    return response.content
