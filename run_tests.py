#!/usr/bin/env python
"""
Script para executar testes com o PYTHONPATH configurado corretamente.

Uso:
    python run_tests.py [argumentos do pytest]

Exemplos:
    python run_tests.py tests/services/test_gemini_service.py -v
    python run_tests.py tests/ -v --tb=short
"""

import sys
import os

# Adiciona o diretório raiz ao PYTHONPATH
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

# Configura variáveis de ambiente para testes
os.environ.setdefault("ENV", "test")
os.environ.setdefault("GEMINI_KEY", "test-key-for-tests")

if __name__ == "__main__":
    import pytest
    # Passa todos os argumentos da linha de comando para o pytest
    sys.exit(pytest.main(sys.argv[1:] if len(sys.argv) > 1 else ["-v", "tests/"]))
