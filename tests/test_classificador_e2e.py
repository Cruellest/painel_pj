"""
Teste E2E do Classificador de Documentos

Testa o fluxo completo:
1. Login
2. Criar projeto/lote
3. Upload de PDF
4. Executar classificacao
5. Verificar resultados

Uso: python tests/test_classificador_e2e.py
"""
import os
import sys
import json
import time
import requests
from pathlib import Path

# Configuracao
BASE_URL = os.getenv("TEST_BASE_URL", "http://127.0.0.1:8000")
PDF_PATH = r"E:\Projetos\Datasets\Petições\Lote 6\20180108123212_08000383920188120001 - Petição-1.pdf"

# Tenta pegar credenciais de variaveis de ambiente ou usa default
USERNAME = os.getenv("ADMIN_USERNAME", "admin")
PASSWORD = os.getenv("ADMIN_PASSWORD", "teste123")


def log(msg, level="INFO"):
    print(f"[{level}] {msg}")


def test_classificador():
    """Executa teste E2E do classificador"""
    session = requests.Session()

    # 1. Login
    log("Fazendo login...")
    login_response = session.post(
        f"{BASE_URL}/auth/login",
        data={"username": USERNAME, "password": PASSWORD}
    )

    if login_response.status_code != 200:
        log(f"Login falhou: {login_response.text}", "ERROR")
        log("Tente definir ADMIN_USERNAME e ADMIN_PASSWORD no .env", "INFO")
        return False

    token = login_response.json().get("access_token")
    log(f"Login OK - Token: {token[:20]}...")

    # 2. Verifica status da API
    log("Verificando status da API OpenRouter...")
    status_response = session.get(f"{BASE_URL}/classificador/api/status")
    if status_response.status_code != 200:
        log(f"Status API falhou: {status_response.text}", "ERROR")
        return False
    status = status_response.json()
    log(f"API disponivel: {status.get('disponivel')}, Modelo padrao: {status.get('modelo_padrao')}")

    # 3. Lista prompts disponiveis
    log("Listando prompts...")
    prompts_response = session.get(f"{BASE_URL}/classificador/api/prompts")
    if prompts_response.status_code != 200:
        log(f"Lista prompts falhou: {prompts_response.text}", "ERROR")
        return False
    prompts = prompts_response.json()
    log(f"Encontrados {len(prompts)} prompts")

    if not prompts:
        log("Nenhum prompt encontrado - criando prompt de teste...", "WARN")
        create_prompt = session.post(
            f"{BASE_URL}/classificador/api/prompts",
            json={
                "nome": "Teste E2E",
                "descricao": "Prompt para teste automatizado",
                "conteudo": """Voce e um classificador de documentos juridicos.
Analise o documento e retorne APENAS um JSON com a estrutura:
{
  "categoria": "Peticao",
  "subcategoria": "Inicial",
  "confianca": "alta",
  "justificativa_breve": "motivo da classificacao"
}"""
            }
        )
        if create_prompt.status_code not in [200, 201]:
            log(f"Criar prompt falhou: {create_prompt.text}", "ERROR")
            return False
        prompt_id = create_prompt.json().get("id")
    else:
        prompt_id = prompts[0]["id"]

    log(f"Usando prompt ID: {prompt_id}")

    # 4. Cria projeto/lote
    log("Criando projeto para teste...")
    projeto_response = session.post(
        f"{BASE_URL}/classificador/api/projetos",
        json={
            "nome": f"Teste E2E - {time.strftime('%Y%m%d_%H%M%S')}",
            "descricao": "Projeto criado por teste automatizado",
            "prompt_id": prompt_id,
            "modelo": "google/gemini-2.5-flash-lite",
            "modo_processamento": "chunk",
            "posicao_chunk": "inicio",
            "tamanho_chunk": 1000
        }
    )

    if projeto_response.status_code not in [200, 201]:
        log(f"Criar projeto falhou: {projeto_response.text}", "ERROR")
        return False

    projeto = projeto_response.json()
    projeto_id = projeto.get("id")
    log(f"Projeto criado: ID {projeto_id}")

    # 5. Verifica se PDF existe
    if not Path(PDF_PATH).exists():
        log(f"PDF de teste nao encontrado: {PDF_PATH}", "ERROR")
        return False

    log(f"PDF encontrado: {PDF_PATH}")
    file_size = Path(PDF_PATH).stat().st_size
    log(f"Tamanho: {file_size / 1024:.2f} KB")

    # 6. Upload do PDF
    log("Fazendo upload do PDF...")
    with open(PDF_PATH, "rb") as f:
        files = [("arquivos", (Path(PDF_PATH).name, f, "application/pdf"))]
        upload_response = session.post(
            f"{BASE_URL}/classificador/api/lotes/{projeto_id}/upload",
            files=files
        )

    if upload_response.status_code != 200:
        log(f"Upload falhou: {upload_response.text}", "ERROR")
        return False

    upload_result = upload_response.json()
    log(f"Upload: {upload_result.get('adicionados')} arquivo(s) adicionado(s)")

    if upload_result.get("erros", 0) > 0:
        log(f"Erros no upload: {upload_result.get('detalhes_erros')}", "WARN")

    # 7. Verifica codigos adicionados
    log("Verificando documentos no projeto...")
    codigos_response = session.get(f"{BASE_URL}/classificador/api/projetos/{projeto_id}/codigos")
    if codigos_response.status_code != 200:
        log(f"Lista codigos falhou: {codigos_response.text}", "ERROR")
        return False

    codigos = codigos_response.json()
    log(f"Documentos no projeto: {len(codigos)}")

    if len(codigos) == 0:
        log("ERRO: Nenhum documento foi adicionado ao projeto!", "ERROR")
        return False

    for c in codigos:
        log(f"  - {c.get('codigo')}: fonte={c.get('fonte')}")

    # 8. Executa classificacao via SSE
    log("Iniciando classificacao...")
    log("Conectando ao stream SSE...")

    # Usa requests com stream para SSE
    exec_url = f"{BASE_URL}/classificador/api/projetos/{projeto_id}/executar"

    try:
        with session.post(exec_url, stream=True) as response:
            if response.status_code != 200:
                log(f"Executar falhou: {response.text}", "ERROR")
                return False

            log("Conexao SSE estabelecida - aguardando eventos...")

            execucao_id = None
            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith("data: "):
                        data = json.loads(line_str[6:])
                        tipo = data.get("tipo", "desconhecido")
                        msg = data.get("mensagem", "")

                        log(f"[SSE] {tipo}: {msg}")

                        if tipo == "inicio":
                            execucao_id = data.get("execucao_id")
                            log(f"  Execucao ID: {execucao_id}")

                        elif tipo == "progresso":
                            processados = data.get("processados", 0)
                            total = data.get("total", 0)
                            sucesso = data.get("sucesso", False)
                            log(f"  Progresso: {processados}/{total} - Sucesso: {sucesso}")

                            if data.get("resultado"):
                                r = data["resultado"]
                                log(f"    Categoria: {r.get('categoria')}")
                                log(f"    Subcategoria: {r.get('subcategoria')}")
                                log(f"    Confianca: {r.get('confianca')}")

                        elif tipo == "concluido":
                            log(f"  Sucesso: {data.get('sucesso', 0)}, Erros: {data.get('erros', 0)}")
                            break

                        elif tipo == "erro":
                            log(f"  ERRO: {msg}", "ERROR")
                            break

        log("Stream SSE finalizado")

    except Exception as e:
        log(f"Erro durante execucao: {e}", "ERROR")
        return False

    # 9. Verifica resultados finais
    if execucao_id:
        log(f"Verificando resultados da execucao {execucao_id}...")
        resultados_response = session.get(
            f"{BASE_URL}/classificador/api/execucoes/{execucao_id}/resultados"
        )

        if resultados_response.status_code == 200:
            resultados = resultados_response.json()
            log(f"Total de resultados: {len(resultados)}")

            for r in resultados:
                log(f"  - {r.get('codigo_documento')}: {r.get('categoria')} / {r.get('subcategoria')} ({r.get('confianca')})")
                if r.get("erro_mensagem"):
                    log(f"    ERRO: {r.get('erro_mensagem')}", "WARN")

    log("=" * 50)
    log("TESTE E2E CONCLUIDO COM SUCESSO!", "SUCCESS")
    log("=" * 50)

    return True


if __name__ == "__main__":
    success = test_classificador()
    sys.exit(0 if success else 1)
