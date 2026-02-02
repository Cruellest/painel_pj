# tests/conftest.py
"""
Configuração global do pytest para o Portal PGE-MS.

Este arquivo é executado automaticamente pelo pytest antes dos testes.

IMPORTANTE: Este arquivo deve ser carregado antes de qualquer módulo de teste.
O pytest carrega conftest.py antes de importar os módulos de teste.
"""

import sys
import os

# Adiciona o diretório raiz do projeto ao PYTHONPATH
# para que os imports funcionem corretamente nos testes
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Força reload do sys.path para garantir que o projeto seja encontrado
# Isso é necessário porque pytest pode ter cacheado o path antes de carregar conftest
import importlib
importlib.invalidate_caches()

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
