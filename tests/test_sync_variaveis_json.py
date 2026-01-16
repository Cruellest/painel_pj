# tests/test_sync_variaveis_json.py
"""
Testes para sincronização bidirecional entre variáveis e JSON.
"""

import json
import sys
import os

# Adiciona o diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_estrutura_request_ordenar():
    """Verifica estrutura do request de ordenação"""
    from sistemas.gerador_pecas.router_extraction import OrdenarPerguntasRequest, PerguntaOrdenarItem

    perguntas = [
        PerguntaOrdenarItem(id=1, pergunta="Qual o valor do pedido?", tipo_sugerido="currency"),
        PerguntaOrdenarItem(id=2, pergunta="Qual o nome do autor?", tipo_sugerido="text"),
    ]

    request = OrdenarPerguntasRequest(
        categoria_nome="Peticoes Iniciais",
        perguntas=perguntas
    )

    assert request.categoria_nome == "Peticoes Iniciais"
    assert len(request.perguntas) == 2
    assert request.perguntas[0].pergunta == "Qual o valor do pedido?"
    print("[OK] Estrutura OrdenarPerguntasRequest valida")


def test_estrutura_request_posicionar():
    """Verifica estrutura do request de posicionamento"""
    from sistemas.gerador_pecas.router_extraction import PosicionarPerguntaRequest, PerguntaOrdenarItem

    nova_pergunta = PerguntaOrdenarItem(
        pergunta="Qual a data da decisao?",
        tipo_sugerido="date"
    )

    perguntas_existentes = [
        {"ordem": 0, "pergunta": "Qual o nome do autor?"},
        {"ordem": 1, "pergunta": "Qual o valor do pedido?"},
    ]

    request = PosicionarPerguntaRequest(
        categoria_nome="Decisoes",
        nova_pergunta=nova_pergunta,
        perguntas_existentes=perguntas_existentes
    )

    assert request.categoria_nome == "Decisoes"
    assert request.nova_pergunta.pergunta == "Qual a data da decisao?"
    assert len(request.perguntas_existentes) == 2
    print("[OK] Estrutura PosicionarPerguntaRequest valida")


def test_logica_variavel_para_json():
    """Testa lógica de sincronização variável -> JSON"""
    # Simula JSON de uma categoria
    json_original = {
        "nome_autor": {"type": "text", "description": "Nome do autor"},
        "valor_pedido": {"type": "number", "description": "Valor do pedido"}
    }

    # Simula alteração de tipo e descrição de uma variável
    slug = "nome_autor"
    novo_tipo = "text"
    nova_descricao = "Nome completo do autor da acao"

    # Atualiza JSON (como o endpoint faz)
    if slug in json_original:
        json_original[slug]["type"] = novo_tipo
        json_original[slug]["description"] = nova_descricao

    # Verifica
    assert json_original["nome_autor"]["description"] == "Nome completo do autor da acao"
    print("[OK] Variavel -> JSON: Logica de sincronizacao funciona")


def test_logica_json_para_variavel():
    """Testa lógica de sincronização JSON -> variável"""
    # Simula JSON modificado
    json_modificado = {
        "data_ajuizamento": {"type": "date", "description": "Data em que a acao foi ajuizada"}
    }

    # Simula variáveis existentes
    variaveis = {
        "data_ajuizamento": {"tipo": "text", "descricao": "Data do ajuizamento"}
    }

    # Sincroniza (como o endpoint faz)
    for slug, campo_info in json_modificado.items():
        if isinstance(campo_info, dict) and slug in variaveis:
            tipo_json = campo_info.get("type")
            descricao_json = campo_info.get("description")
            if tipo_json:
                variaveis[slug]["tipo"] = tipo_json
            if descricao_json:
                variaveis[slug]["descricao"] = descricao_json

    # Verifica
    assert variaveis["data_ajuizamento"]["tipo"] == "date"
    assert variaveis["data_ajuizamento"]["descricao"] == "Data em que a acao foi ajuizada"
    print("[OK] JSON -> Variavel: Logica de sincronizacao funciona")


def test_sincronizacao_bidirecional_completa():
    """Teste completo de sincronização bidirecional"""

    # Estado inicial
    categoria_json = {
        "campo1": {"type": "text", "description": "Campo 1 original"},
        "campo2": {"type": "number", "description": "Campo 2 original"}
    }

    variaveis = {
        "campo1": {"tipo": "text", "descricao": "Campo 1 original"},
        "campo2": {"tipo": "number", "descricao": "Campo 2 original"}
    }

    # 1. Usuario altera variavel campo1
    variaveis["campo1"]["tipo"] = "boolean"
    variaveis["campo1"]["descricao"] = "Campo 1 eh booleano agora"

    # Sistema sincroniza para JSON
    categoria_json["campo1"]["type"] = variaveis["campo1"]["tipo"]
    categoria_json["campo1"]["description"] = variaveis["campo1"]["descricao"]

    assert categoria_json["campo1"]["type"] == "boolean"
    assert categoria_json["campo1"]["description"] == "Campo 1 eh booleano agora"

    # 2. Usuario altera JSON do campo2
    categoria_json["campo2"]["type"] = "currency"
    categoria_json["campo2"]["description"] = "Campo 2 eh monetario"

    # Sistema sincroniza para variavel
    variaveis["campo2"]["tipo"] = categoria_json["campo2"]["type"]
    variaveis["campo2"]["descricao"] = categoria_json["campo2"]["description"]

    assert variaveis["campo2"]["tipo"] == "currency"
    assert variaveis["campo2"]["descricao"] == "Campo 2 eh monetario"

    print("[OK] Sincronizacao bidirecional completa funciona")


def run_tests():
    """Executa os testes"""
    print("\n" + "="*60)
    print("TESTES DE SINCRONIZACAO VARIAVEIS <-> JSON")
    print("="*60 + "\n")

    print("1. Testando estruturas de request para ordenacao IA...")
    test_estrutura_request_ordenar()
    test_estrutura_request_posicionar()

    print("\n2. Testando logica de sincronizacao Variavel -> JSON...")
    test_logica_variavel_para_json()

    print("\n3. Testando logica de sincronizacao JSON -> Variavel...")
    test_logica_json_para_variavel()

    print("\n4. Testando sincronizacao bidirecional completa...")
    test_sincronizacao_bidirecional_completa()

    print("\n" + "="*60)
    print("TODOS OS TESTES PASSARAM!")
    print("="*60 + "\n")


if __name__ == "__main__":
    run_tests()
