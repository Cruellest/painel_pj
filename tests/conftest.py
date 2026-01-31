# tests/conftest.py
"""
Configuração global do pytest para o Portal PGE-MS.
"""

import sys
import os

# Adiciona project root ao sys.path IMEDIATAMENTE quando conftest é importado
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Configura variáveis de ambiente para testes
os.environ.setdefault("ENV", "test")
os.environ.setdefault("GEMINI_KEY", "test-key-for-tests")

import pytest


@pytest.fixture(scope="session")
def event_loop():
    """Cria um event loop para testes assíncronos."""
    import asyncio
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
