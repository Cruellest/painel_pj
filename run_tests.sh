#!/bin/bash
# ============================================================================
# Script para executar testes do sistema PGE em ambiente local de desenvolvimento
# Cria e ativa venv automaticamente se necessário
# ============================================================================
# 
# Uso:
#   ./run_tests.sh                      # Executa todos os testes
#   ./run_tests.sh tests/services/      # Executa testes de um diretório
#   ./run_tests.sh -v                   # Verbose
#   ./run_tests.sh -k "test_gemini"     # Filtra por padrão
#   ./run_tests.sh --cov=sistemas       # Com coverage
#
# Pre-requisitos:
#   - Python 3.10+
#
# O script automaticamente:
#   - Cria venv se não existir
#   - Ativa o venv
#   - Instala dependências
#   - Executa testes
#
# ============================================================================

set -e

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configurações
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_ROOT/venv"
PYTHON_CMD=${PYTHON_CMD:-python3}
PYTHON_VENV="$VENV_DIR/bin/python"
PIP_VENV="$VENV_DIR/bin/pip"

# Define PYTHONPATH antes de tudo
export PYTHONPATH="$PROJECT_ROOT${PYTHONPATH:+:$PYTHONPATH}"

# ============================================================================
# Funções
# ============================================================================

print_header() {
    echo -e "\n${BLUE}================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}================================${NC}\n"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

# Verifica se arquivo/diretório existe
check_exists() {
    if [ ! -e "$1" ]; then
        print_error "Não encontrado: $1"
        return 1
    fi
    return 0
}

# Verifica se Python está instalado
check_python() {
    if ! command -v "$PYTHON_CMD" &> /dev/null; then
        print_error "Python não encontrado. Instale Python 3.10+"
        exit 1
    fi
    
    PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | awk '{print $2}')
    print_success "Python $PYTHON_VERSION encontrado"
}

# Cria venv se não existir
setup_venv() {
    if [ ! -d "$VENV_DIR" ]; then
        print_header "Criando ambiente virtual..."
        $PYTHON_CMD -m venv "$VENV_DIR"
        print_success "venv criado em $VENV_DIR"
    else
        print_success "venv já existe em $VENV_DIR"
    fi
    
    # Ativa venv
    if [ -f "$VENV_DIR/bin/activate" ]; then
        print_success "Ativando venv..."
        source "$VENV_DIR/bin/activate"
    else
        print_error "Não foi possível ativar venv"
        exit 1
    fi
}

# Instala dependências
install_deps() {
    print_header "Instalando dependências..."
    
    # Atualiza pip
    $PIP_VENV install -q --upgrade pip setuptools wheel
    
    # Instala requirements_app.txt
    if [ -f "$PROJECT_ROOT/requirements_app.txt" ]; then
        $PIP_VENV install -q -r "$PROJECT_ROOT/requirements_app.txt"
        print_success "requirements_app.txt instalado"
    else
        # Fallback: instala pytest manualmente
        $PIP_VENV install -q \
            pytest>=7.4.0 \
            pytest-asyncio>=0.23.0 \
            pytest-cov>=4.1.0 \
            pytest-timeout>=2.2.0
        print_success "pytest e dependências instalados"
    fi
}

# Configura variáveis de ambiente para testes
setup_env() {
    print_header "Configurando ambiente de teste..."
    
    # PYTHONPATH já foi definido no início do script
    export ENV="test"
    export GEMINI_KEY="test-key-for-tests"
    export DATABASE_URL="postgresql://test:test@localhost/pge_test"  # Opcional
    
    print_success "Ambiente configurado (PYTHONPATH=$PYTHONPATH)"
}

# Exibe informações de ajuda
show_help() {
    cat << EOF
${BLUE}PGE Tests - Test Runner Script${NC}

${BLUE}Uso:${NC}
  $0 [opções] [caminho_dos_testes]

${BLUE}Opções comuns:${NC}
  -v, --verbose              Output verbose
  -x, --exitfirst            Para no primeiro erro
  -k PATTERN                 Executa tests que casam com padrão
  --cov=MODULO               Gera relatório de coverage
  -h, --help                 Mostra esta ajuda

${BLUE}Exemplos:${NC}
  $0                                    # Todos os testes
  $0 tests/services/                    # Testes de um diretório
  $0 -v -x tests/test_bert_training.py  # Um arquivo, verbose, para no erro
  $0 -k "gemini" -v                     # Testes que contêm "gemini"
  $0 --cov=sistemas --cov=services      # Com coverage

${BLUE}Diretórios de teste:${NC}
  tests/
  ├── services/                 # Testes de serviços
  ├── classificador_documentos/ # Testes do classificador
  ├── ia_extracao_regras/       # Testes de extração com IA
  ├── e2e/                      # Testes end-to-end
  └── load/                     # Testes de carga

${BLUE}Variáveis de ambiente:${NC}
  PYTHON_CMD        Comando Python (default: python3)
  ENV               Ambiente (default: test)
  GEMINI_KEY        Chave Gemini para testes (default: test-key-for-tests)

EOF
}

# ============================================================================
# Main
# ============================================================================

main() {
    # Se passou --help ou -h, mostra ajuda
    if [[ "$*" == *"-h"* ]] || [[ "$*" == *"--help"* ]]; then
        show_help
        exit 0
    fi
    
    print_header "🧪 PGE Test Runner"
    
    # Setup automático
    check_python
    setup_venv
    
    # Ativa venv ANTES de instalar deps e setup_env
    if [ -f "$VENV_DIR/bin/activate" ]; then
        source "$VENV_DIR/bin/activate"
        print_success "venv ativado"
    else
        print_error "Não foi possível ativar venv"
        exit 1
    fi
    
    install_deps
    setup_env
    
    # Verificações
    check_exists "$PROJECT_ROOT/tests" || exit 1
    
    # Se não passou argumentos, usa default
    if [ $# -eq 0 ]; then
        set -- "-v" "tests/"
    fi
    
    print_header "Executando testes..."
    
    # Executa pytest com PYTHONPATH exportado DEPOIS de ativar venv
    cd "$PROJECT_ROOT"
    PYTHONPATH="$PROJECT_ROOT" python -m pytest "$@"
    
    local EXIT_CODE=$?
    
    if [ $EXIT_CODE -eq 0 ]; then
        print_header "✅ Testes passaram!"
    else
        print_header "❌ Alguns testes falharam (exit code: $EXIT_CODE)"
    fi
    
    exit $EXIT_CODE
}

# Executa main com todos os argumentos
main "$@"
