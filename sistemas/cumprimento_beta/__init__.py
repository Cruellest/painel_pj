# sistemas/cumprimento_beta/__init__.py
"""
Módulo Beta: Cumprimento de Sentença

Subsistema isolado para geração de peças de cumprimento de sentença,
operando com dois agentes de IA:
- Agente 1: Coleta documentos, avalia relevância e gera JSONs de resumo
- Agente 2: Consolida JSONs, sugere peças e conduz chatbot até geração final
"""

from sistemas.cumprimento_beta.router import router

__all__ = ["router"]
