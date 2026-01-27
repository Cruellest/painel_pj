#!/bin/bash

# Navigate to script directory to ensure commands run from project root
cd "$(dirname "$0")"

echo ""
echo "========================================"
echo "   Portal PGE-MS - Dev Server (Linux/Mac)"
echo "========================================"
echo ""

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Criando ambiente virtual..."
    python3 -m venv .venv
    echo "Ambiente virtual criado!"
    echo ""
fi

# Activate virtual environment
# Check for standard venv or windows style if someone copied folder
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
elif [ -f ".venv/Scripts/activate" ]; then
    source .venv/Scripts/activate
else
    echo "Erro: Script de ativação do venv não encontrado."
    exit 1
fi

# Install/Update dependencies
if [ -f "requirements.txt" ]; then
    echo "Instalando/Atualizando dependências..."
    pip install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo "Erro ao instalar dependências."
        exit 1
    fi
    echo "Dependências atualizadas!"
    echo ""
else
    echo "Aviso: requirements.txt não encontrado. Pulando instalação de dependências."
    echo ""
fi

# Install Frontend dependencies
if [ -d "frontend" ]; then
    echo "Instalando dependências do Frontend..."
    cd frontend
    npm install
    if [ $? -ne 0 ]; then
        echo "Erro ao instalar dependências do frontend."
        exit 1
    fi
    cd ..
    echo "Dependências do Frontend atualizadas!"
    echo ""
fi

# Clean Python cache
echo "Limpando cache Python..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -type f -name "*.pyc" -delete
echo "Cache limpo!"
echo ""

# Display URLs
echo "   Portal:           http://localhost:8000"
echo "   Prestacao Contas: http://localhost:8000/prestacao-contas"
echo "   Gerador Pecas:    http://localhost:8000/gerador-pecas"
echo "   API Docs:         http://localhost:8000/docs"
echo ""
echo "   Pressione Ctrl+C para encerrar"
echo "========================================"
echo ""

# Start server with reload
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
