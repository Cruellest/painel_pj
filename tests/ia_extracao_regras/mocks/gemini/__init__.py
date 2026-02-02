# tests/ia_extracao_regras/mocks/gemini/__init__.py
"""
Mocks para o serviço Gemini.

Permite testar funcionalidades de IA sem chamadas reais à API.
"""

from .mock_gemini_service import (
    MockGeminiService,
    MockGeminiResponse,
    criar_mock_schema_response,
    criar_mock_regra_response,
)

__all__ = [
    "MockGeminiService",
    "MockGeminiResponse",
    "criar_mock_schema_response",
    "criar_mock_regra_response",
]
