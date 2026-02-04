# tests/test_request_id_scope.py
"""
Teste para garantir que request_id está sempre disponível no router do relatório de cumprimento.

Este teste foi criado para prevenir regressão do bug:
"cannot access local variable 'request_id' where it is not associated with a value"

O bug ocorria porque request_id era redefinido dentro de um bloco condicional,
causando shadowing da variável externa e UnboundLocalError quando a condição era falsa.

Autor: LAB/PGE-MS
"""

import ast
import os


def test_request_id_not_redefined_in_event_generator():
    """
    Verifica que request_id NÃO é redefinido dentro do event_generator.

    O request_id deve ser definido UMA VEZ no escopo externo de processar_stream()
    e NÃO deve ser reatribuído dentro do event_generator() para evitar shadowing.
    """
    # Caminho do arquivo router.py
    router_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "sistemas", "relatorio_cumprimento", "router.py"
    )

    with open(router_path, "r", encoding="utf-8") as f:
        source_code = f.read()

    # Parse o código fonte
    tree = ast.parse(source_code)

    # Encontra a função processar_stream
    processar_stream_func = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "processar_stream":
            processar_stream_func = node
            break

    assert processar_stream_func is not None, "Função processar_stream não encontrada"

    # Encontra a função event_generator dentro de processar_stream
    event_generator_func = None
    for node in ast.walk(processar_stream_func):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "event_generator":
            event_generator_func = node
            break

    assert event_generator_func is not None, "Função event_generator não encontrada"

    # Verifica se há atribuições de request_id dentro de event_generator
    assignments_in_generator = []
    for node in ast.walk(event_generator_func):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "request_id":
                    assignments_in_generator.append(node.lineno)

    # Não deve haver atribuições de request_id dentro do event_generator
    assert len(assignments_in_generator) == 0, (
        f"request_id está sendo reatribuído dentro de event_generator nas linhas: {assignments_in_generator}. "
        f"Isso causa UnboundLocalError quando o bloco condicional não é executado. "
        f"Use o request_id do escopo externo de processar_stream()."
    )


def test_request_id_defined_at_start_of_processar_stream():
    """
    Verifica que request_id é definido no INÍCIO de processar_stream(),
    antes de qualquer try/except que possa falhar.
    """
    router_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "sistemas", "relatorio_cumprimento", "router.py"
    )

    with open(router_path, "r", encoding="utf-8") as f:
        source_code = f.read()

    tree = ast.parse(source_code)

    # Encontra a função processar_stream
    processar_stream_func = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "processar_stream":
            processar_stream_func = node
            break

    assert processar_stream_func is not None, "Função processar_stream não encontrada"

    # Encontra a primeira atribuição de request_id no corpo da função (não em subFunções)
    first_request_id_line = None
    first_try_line = None

    for node in processar_stream_func.body:
        if first_request_id_line is None:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "request_id":
                        first_request_id_line = node.lineno
                        break

        if first_try_line is None:
            if isinstance(node, ast.Try):
                first_try_line = node.lineno

    assert first_request_id_line is not None, (
        "request_id não está sendo definido no corpo principal de processar_stream()"
    )

    # Se houver um try, request_id deve ser definido ANTES dele
    if first_try_line is not None:
        assert first_request_id_line < first_try_line, (
            f"request_id (linha {first_request_id_line}) deve ser definido ANTES do primeiro try (linha {first_try_line}) "
            f"para garantir que esteja disponível em caso de exceção."
        )


def test_request_id_uses_uuid():
    """
    Verifica que request_id é gerado usando UUID para garantir unicidade.
    """
    router_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "sistemas", "relatorio_cumprimento", "router.py"
    )

    with open(router_path, "r", encoding="utf-8") as f:
        source_code = f.read()

    # Verifica se há a definição correta de request_id com UUID
    assert "request_id = str(uuid.uuid4())" in source_code, (
        "request_id deve ser gerado usando uuid.uuid4() para garantir unicidade"
    )


if __name__ == "__main__":
    print("Executando testes de escopo de request_id...")

    try:
        test_request_id_not_redefined_in_event_generator()
        print("[OK] test_request_id_not_redefined_in_event_generator")
    except AssertionError as e:
        print(f"[FAIL] test_request_id_not_redefined_in_event_generator: {e}")

    try:
        test_request_id_defined_at_start_of_processar_stream()
        print("[OK] test_request_id_defined_at_start_of_processar_stream")
    except AssertionError as e:
        print(f"[FAIL] test_request_id_defined_at_start_of_processar_stream: {e}")

    try:
        test_request_id_uses_uuid()
        print("[OK] test_request_id_uses_uuid")
    except AssertionError as e:
        print(f"[FAIL] test_request_id_uses_uuid: {e}")

    print("\nTestes concluídos!")
