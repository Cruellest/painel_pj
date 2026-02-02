#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de teste para integracao com Supermemory SDK.
Le a API key do arquivo .env e testa operacoes de escrita e busca de memoria.

Baseado na documentacao oficial:
https://github.com/supermemoryai/claude-supermemory
"""

import os
import sys
from datetime import datetime
from pathlib import Path

# Configurar encoding UTF-8 para Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Carregar variaveis do .env
def load_env():
    """Carrega variaveis de ambiente do arquivo .env"""
    env_path = Path(__file__).parent.parent / ".env"

    if not env_path.exists():
        print(f"[ERRO] Arquivo .env nao encontrado em: {env_path}")
        sys.exit(1)

    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key] = value

# Carregar .env antes de importar supermemory
load_env()

# Verificar se a API key esta disponivel
api_key = os.environ.get('SUPERMEMORY_API_KEY')
if not api_key:
    print("[ERRO] SUPERMEMORY_API_KEY nao encontrada no .env")
    sys.exit(1)

print(f"[OK] API Key carregada do .env (formato: {api_key[:15]}...)")

# Importar SDK apos configurar ambiente
from supermemory import Supermemory

def test_supermemory_integration():
    """Testa a integracao completa com Supermemory usando metodos oficiais"""

    print("\n" + "="*60)
    print("TESTE DE INTEGRACAO SUPERMEMORY SDK")
    print("="*60)

    # 1. Inicializar cliente
    print("\n[1/4] Inicializando cliente Supermemory...")
    try:
        client = Supermemory(api_key=api_key)
        print("[OK] Cliente inicializado com sucesso")
    except Exception as e:
        print(f"[ERRO] Erro ao inicializar cliente: {e}")
        return False

    # 2. Definir container tag unico para este teste
    container_tag = "portal_pge_test"
    test_timestamp = datetime.now().isoformat()

    # 3. Adicionar memoria usando client.memories.add (metodo oficial)
    print("\n[2/4] Adicionando memoria de teste (client.memories.add)...")
    test_content = f"""
    Este e um teste de integracao do Supermemory SDK com o projeto Portal PGE.

    Contexto do teste:
    - Projeto: Portal PGE (Procuradoria Geral do Estado - MS)
    - Sistemas: Gerador de Pecas, Classificador de Documentos, Relatorios
    - Tecnologias: FastAPI, Python, SQLAlchemy, Gemini AI
    - Timestamp: {test_timestamp}

    O Portal PGE e um sistema juridico que automatiza a geracao de documentos
    legais como contestacoes, apelacoes e agravos usando inteligencia artificial.
    """

    try:
        # Metodo oficial: client.memories.add
        result = client.memories.add(
            content=test_content,
            container_tag=container_tag,
            metadata={
                "source": "test_script",
                "project": "portal_pge",
                "type": "integration_test",
                "timestamp": test_timestamp
            }
        )
        print(f"[OK] Memoria adicionada com sucesso!")
        print(f"   ID: {result.id}")
        print(f"   Status: {result.status}")
        if hasattr(result, 'workflowInstanceId'):
            print(f"   Workflow: {result.workflowInstanceId}")
    except Exception as e:
        print(f"[ERRO] Erro ao adicionar memoria: {e}")
        return False

    # 4. Aguardar um momento para indexacao
    print("\n[3/4] Aguardando indexacao (3 segundos)...")
    import time
    time.sleep(3)

    # 5. Buscar memoria usando client.search.execute (metodo oficial)
    print("\n[4/4] Buscando memorias (client.search.execute)...")
    try:
        # Metodo oficial: client.search.execute
        search_result = client.search.execute(
            q="Portal PGE sistema juridico FastAPI"
        )

        print(f"[OK] Busca executada com sucesso!")

        if hasattr(search_result, 'results') and search_result.results:
            print(f"   Total de resultados: {len(search_result.results)}")
            print("\n   Resultados encontrados:")
            for i, mem in enumerate(search_result.results[:3], 1):
                score = getattr(mem, 'score', 0)
                title = getattr(mem, 'title', 'Sem titulo')
                doc_id = getattr(mem, 'document_id', getattr(mem, 'documentId', 'N/A'))

                print(f"\n   [{i}] Score: {score:.2%}")
                print(f"       Titulo: {title}")
                print(f"       ID: {doc_id}")

                # Mostrar conteudo dos chunks se disponivel
                if hasattr(mem, 'chunks') and mem.chunks:
                    content = mem.chunks[0].content[:150] if mem.chunks[0].content else ''
                    print(f"       Conteudo: {content}...")
        else:
            print("   [AVISO] Nenhum resultado retornado (indexacao pode levar alguns segundos)")

    except Exception as e:
        print(f"[ERRO] Erro na busca: {e}")
        return False

    print("\n" + "="*60)
    print("[OK] TESTE CONCLUIDO COM SUCESSO!")
    print("="*60)
    print(f"\nResumo:")
    print(f"  - API Key: Carregada do .env [OK]")
    print(f"  - Cliente: Inicializado [OK]")
    print(f"  - Memoria: Adicionada via client.memories.add [OK]")
    print(f"  - Busca: Executada via client.search.execute [OK]")
    print(f"  - Container: {container_tag}")

    return True

if __name__ == "__main__":
    success = test_supermemory_integration()
    sys.exit(0 if success else 1)
