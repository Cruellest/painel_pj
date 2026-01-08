# services/__init__.py
"""
Serviços compartilhados do Portal PGE-MS
"""

from services.gemini_service import GeminiService, gemini_service

__all__ = ["GeminiService", "gemini_service"]
