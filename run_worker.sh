#!/bin/bash

# Define cores
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}[*] Inicializando Worker de Inferencia Local...${NC}"

# Verifica se o venv existe
if [ ! -d ".venv" ]; then
    echo -e "${RED}[!] Ambiente virtual nao encontrado! Execute ./run.sh primeiro.${NC}"
    exit 1
fi

# Ativa o venv
source .venv/bin/activate

# Instala dependencias do worker se necessario
echo -e "${GREEN}[*] Verificando dependencias do worker...${NC}"
pip install -r requirements_worker.txt

# Inicia o servidor
echo -e "${GREEN}[*] Iniciando servidor na porta 8765...${NC}"
python -m sistemas.bert_training.worker.inference_server --port 8765
