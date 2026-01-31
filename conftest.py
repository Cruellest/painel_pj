"""
Configuração global de testes pytest
"""
import sys
import os

# Adiciona o diretório raiz ao PYTHONPATH ANTES de qualquer outra coisa
# Isso é necessário para que pytest possa importar módulos do projeto
# durante a coleta de testes
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

# Configura variáveis de ambiente para testes
os.environ.setdefault('ENV', 'test')
os.environ.setdefault('GEMINI_KEY', 'test-key-for-tests')
