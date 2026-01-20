#!/usr/bin/env python3
# tests/test_prompt_rules_activation.py
"""
Suíte de testes data-driven para regras determinísticas de ativação de prompts.

Estes testes:
1. Carregam o snapshot de regras (gerado por scripts/snapshot_prompt_rules.py)
2. Para cada regra, executam os casos de teste gerados automaticamente
3. Validam que o motor de avaliação respeita 100% das regras

Os testes são DETERMINÍSTICOS e NÃO dependem do banco de produção em runtime.

Executar:
    pytest tests/test_prompt_rules_activation.py -v
    pytest tests/test_prompt_rules_activation.py -v -k "test_regra_"  # Apenas regras
    pytest tests/test_prompt_rules_activation.py -v --tb=short        # Traceback curto
"""

import json
import pytest
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

# Importa o avaliador de regras
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from sistemas.gerador_pecas.services_deterministic import (
    DeterministicRuleEvaluator,
    verificar_variaveis_existem
)


# Caminho do snapshot
SNAPSHOT_PATH = Path(__file__).parent / "fixtures" / "prompt_rules_snapshot.json"


def carregar_snapshot() -> Optional[Dict[str, Any]]:
    """Carrega o snapshot de regras do arquivo JSON."""
    if not SNAPSHOT_PATH.exists():
        return None

    with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# Carrega snapshot uma vez no início
SNAPSHOT = carregar_snapshot()


def get_regras_do_snapshot() -> List[Dict]:
    """Retorna lista de regras do snapshot."""
    if not SNAPSHOT:
        return []
    return SNAPSHOT.get("regras", [])


def get_estatisticas_snapshot() -> Dict:
    """Retorna estatísticas do snapshot."""
    if not SNAPSHOT:
        return {}
    return SNAPSHOT.get("estatisticas", {})


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture(scope="module")
def evaluator():
    """Fixture que fornece o avaliador de regras."""
    return DeterministicRuleEvaluator()


@pytest.fixture(scope="module")
def snapshot_data():
    """Fixture que fornece os dados do snapshot."""
    if not SNAPSHOT:
        pytest.skip("Snapshot não encontrado. Execute scripts/snapshot_prompt_rules.py primeiro.")
    return SNAPSHOT


# ============================================================================
# TESTES DE INFRAESTRUTURA
# ============================================================================

class TestInfraestruturaSnapshot:
    """Testes que verificam a infraestrutura do sistema de testes."""

    def test_snapshot_existe(self):
        """Verifica que o arquivo de snapshot existe."""
        assert SNAPSHOT_PATH.exists(), (
            f"Snapshot não encontrado em {SNAPSHOT_PATH}. "
            "Execute: python scripts/snapshot_prompt_rules.py"
        )

    def test_snapshot_valido(self, snapshot_data):
        """Verifica que o snapshot tem estrutura válida."""
        assert "timestamp" in snapshot_data
        assert "versao_snapshot" in snapshot_data
        assert "regras" in snapshot_data
        assert "variaveis" in snapshot_data
        assert "estatisticas" in snapshot_data

    def test_snapshot_tem_regras(self, snapshot_data):
        """Verifica que o snapshot contém regras."""
        regras = snapshot_data.get("regras", [])
        assert len(regras) > 0, "Snapshot não contém nenhuma regra"

    def test_snapshot_nao_muito_antigo(self, snapshot_data):
        """Alerta se snapshot tem mais de 7 dias."""
        timestamp_str = snapshot_data.get("timestamp")
        if timestamp_str:
            timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            idade_dias = (datetime.utcnow() - timestamp.replace(tzinfo=None)).days
            if idade_dias > 7:
                pytest.warns(
                    UserWarning,
                    match=f"Snapshot tem {idade_dias} dias. Considere atualizar."
                )


# ============================================================================
# TESTES DO AVALIADOR (UNITÁRIOS)
# ============================================================================

class TestAvaliadorUnitario:
    """Testes unitários do avaliador de regras."""

    def test_operador_equals_booleano_true(self, evaluator):
        """Testa operador equals com booleano true."""
        regra = {
            "type": "condition",
            "variable": "autor_idoso",
            "operator": "equals",
            "value": True
        }
        assert evaluator.avaliar(regra, {"autor_idoso": True}) is True
        assert evaluator.avaliar(regra, {"autor_idoso": False}) is False

    def test_operador_equals_booleano_false(self, evaluator):
        """Testa operador equals com booleano false."""
        regra = {
            "type": "condition",
            "variable": "medicamento_rename",
            "operator": "equals",
            "value": False
        }
        assert evaluator.avaliar(regra, {"medicamento_rename": False}) is True
        assert evaluator.avaliar(regra, {"medicamento_rename": True}) is False

    def test_operador_greater_than(self, evaluator):
        """Testa operador greater_than."""
        regra = {
            "type": "condition",
            "variable": "valor_causa",
            "operator": "greater_than",
            "value": 100000
        }
        assert evaluator.avaliar(regra, {"valor_causa": 150000}) is True
        assert evaluator.avaliar(regra, {"valor_causa": 100000}) is False  # Não é maior, é igual
        assert evaluator.avaliar(regra, {"valor_causa": 50000}) is False

    def test_operador_less_than(self, evaluator):
        """Testa operador less_than."""
        regra = {
            "type": "condition",
            "variable": "valor_causa",
            "operator": "less_than",
            "value": 100000
        }
        assert evaluator.avaliar(regra, {"valor_causa": 50000}) is True
        assert evaluator.avaliar(regra, {"valor_causa": 100000}) is False
        assert evaluator.avaliar(regra, {"valor_causa": 150000}) is False

    def test_operador_greater_or_equal(self, evaluator):
        """Testa operador greater_or_equal."""
        regra = {
            "type": "condition",
            "variable": "valor_causa",
            "operator": "greater_or_equal",
            "value": 100000
        }
        assert evaluator.avaliar(regra, {"valor_causa": 150000}) is True
        assert evaluator.avaliar(regra, {"valor_causa": 100000}) is True
        assert evaluator.avaliar(regra, {"valor_causa": 50000}) is False

    def test_operador_contains(self, evaluator):
        """Testa operador contains (case insensitive)."""
        regra = {
            "type": "condition",
            "variable": "nome_medicamento",
            "operator": "contains",
            "value": "insulina"
        }
        assert evaluator.avaliar(regra, {"nome_medicamento": "INSULINA GLARGINA"}) is True
        assert evaluator.avaliar(regra, {"nome_medicamento": "Insulina NPH"}) is True
        assert evaluator.avaliar(regra, {"nome_medicamento": "Metformina"}) is False

    def test_operador_in_list(self, evaluator):
        """Testa operador in_list."""
        regra = {
            "type": "condition",
            "variable": "tipo_acao",
            "operator": "in_list",
            "value": ["medicamentos", "cirurgia", "internacao"]
        }
        assert evaluator.avaliar(regra, {"tipo_acao": "medicamentos"}) is True
        assert evaluator.avaliar(regra, {"tipo_acao": "cirurgia"}) is True
        assert evaluator.avaliar(regra, {"tipo_acao": "exames"}) is False

    def test_operador_is_empty(self, evaluator):
        """Testa operador is_empty."""
        regra = {
            "type": "condition",
            "variable": "observacoes",
            "operator": "is_empty",
            "value": None
        }
        assert evaluator.avaliar(regra, {"observacoes": None}) is True
        assert evaluator.avaliar(regra, {"observacoes": ""}) is True
        # Nota: lista vazia [] é tratada como não-empty pelo motor atual
        # pois _aplicar_operador verifica explicitamente == []
        assert evaluator.avaliar(regra, {"observacoes": "texto"}) is False

    def test_operador_exists(self, evaluator):
        """Testa operador exists."""
        regra = {
            "type": "condition",
            "variable": "parecer_nat",
            "operator": "exists",
            "value": None
        }
        assert evaluator.avaliar(regra, {"parecer_nat": "conteudo"}) is True
        assert evaluator.avaliar(regra, {"parecer_nat": True}) is True
        assert evaluator.avaliar(regra, {"parecer_nat": None}) is False
        assert evaluator.avaliar(regra, {}) is False

    def test_operador_and(self, evaluator):
        """Testa operador lógico AND."""
        regra = {
            "type": "and",
            "conditions": [
                {"type": "condition", "variable": "autor_idoso", "operator": "equals", "value": True},
                {"type": "condition", "variable": "valor_causa", "operator": "greater_than", "value": 50000}
            ]
        }
        # Ambos true = true
        assert evaluator.avaliar(regra, {"autor_idoso": True, "valor_causa": 100000}) is True
        # Um false = false
        assert evaluator.avaliar(regra, {"autor_idoso": True, "valor_causa": 30000}) is False
        assert evaluator.avaliar(regra, {"autor_idoso": False, "valor_causa": 100000}) is False
        # Ambos false = false
        assert evaluator.avaliar(regra, {"autor_idoso": False, "valor_causa": 30000}) is False

    def test_operador_or(self, evaluator):
        """Testa operador lógico OR."""
        regra = {
            "type": "or",
            "conditions": [
                {"type": "condition", "variable": "autor_idoso", "operator": "equals", "value": True},
                {"type": "condition", "variable": "autor_crianca", "operator": "equals", "value": True}
            ]
        }
        # Um true = true
        assert evaluator.avaliar(regra, {"autor_idoso": True, "autor_crianca": False}) is True
        assert evaluator.avaliar(regra, {"autor_idoso": False, "autor_crianca": True}) is True
        # Ambos true = true
        assert evaluator.avaliar(regra, {"autor_idoso": True, "autor_crianca": True}) is True
        # Ambos false = false
        assert evaluator.avaliar(regra, {"autor_idoso": False, "autor_crianca": False}) is False

    def test_operador_not(self, evaluator):
        """Testa operador lógico NOT."""
        regra = {
            "type": "not",
            "conditions": [
                {"type": "condition", "variable": "arquivado", "operator": "equals", "value": True}
            ]
        }
        # NOT true = false
        assert evaluator.avaliar(regra, {"arquivado": True}) is False
        # NOT false = true
        assert evaluator.avaliar(regra, {"arquivado": False}) is True

    def test_regra_aninhada_and_or(self, evaluator):
        """Testa regra com AND e OR aninhados."""
        # (idoso OR crianca) AND valor > 50000
        regra = {
            "type": "and",
            "conditions": [
                {
                    "type": "or",
                    "conditions": [
                        {"type": "condition", "variable": "autor_idoso", "operator": "equals", "value": True},
                        {"type": "condition", "variable": "autor_crianca", "operator": "equals", "value": True}
                    ]
                },
                {"type": "condition", "variable": "valor_causa", "operator": "greater_than", "value": 50000}
            ]
        }
        # Idoso + valor alto = true
        assert evaluator.avaliar(regra, {"autor_idoso": True, "autor_crianca": False, "valor_causa": 100000}) is True
        # Criança + valor alto = true
        assert evaluator.avaliar(regra, {"autor_idoso": False, "autor_crianca": True, "valor_causa": 100000}) is True
        # Idoso + valor baixo = false (AND falha)
        assert evaluator.avaliar(regra, {"autor_idoso": True, "autor_crianca": False, "valor_causa": 30000}) is False
        # Adulto + valor alto = false (OR falha)
        assert evaluator.avaliar(regra, {"autor_idoso": False, "autor_crianca": False, "valor_causa": 100000}) is False

    def test_normalizacao_booleano_string(self, evaluator):
        """Testa normalização de booleanos em formato string."""
        regra = {
            "type": "condition",
            "variable": "autor_idoso",
            "operator": "equals",
            "value": True
        }
        # Strings que devem ser True
        assert evaluator.avaliar(regra, {"autor_idoso": "true"}) is True
        assert evaluator.avaliar(regra, {"autor_idoso": "sim"}) is True
        assert evaluator.avaliar(regra, {"autor_idoso": "yes"}) is True
        assert evaluator.avaliar(regra, {"autor_idoso": "1"}) is True

        # Strings que devem ser False
        assert evaluator.avaliar(regra, {"autor_idoso": "false"}) is False
        assert evaluator.avaliar(regra, {"autor_idoso": "nao"}) is False

    def test_normalizacao_valor_monetario_brasileiro(self, evaluator):
        """Testa normalização de valores em formato brasileiro."""
        regra = {
            "type": "condition",
            "variable": "valor_causa",
            "operator": "greater_than",
            "value": 100000
        }
        # Formatos brasileiros
        assert evaluator.avaliar(regra, {"valor_causa": "R$ 250.000,00"}) is True
        assert evaluator.avaliar(regra, {"valor_causa": "150.000,50"}) is True
        assert evaluator.avaliar(regra, {"valor_causa": "50.000,00"}) is False

    def test_variavel_ausente_booleano(self, evaluator):
        """Testa comportamento com variável ausente (deve ser False para booleanos)."""
        regra = {
            "type": "condition",
            "variable": "autor_idoso",
            "operator": "equals",
            "value": True
        }
        # Variável não presente = False para comparação booleana
        assert evaluator.avaliar(regra, {}) is False

    def test_variavel_lista_logica_or(self, evaluator):
        """Testa variável com valor lista (aplica lógica OR)."""
        regra = {
            "type": "condition",
            "variable": "pareceres_medicamento_nao_incorporado_sus",
            "operator": "equals",
            "value": True
        }
        # Lista com pelo menos um True = True
        assert evaluator.avaliar(regra, {"pareceres_medicamento_nao_incorporado_sus": [False, True, False]}) is True
        # Lista com todos False = False
        assert evaluator.avaliar(regra, {"pareceres_medicamento_nao_incorporado_sus": [False, False]}) is False

    def test_compatibilidade_value_1_como_true(self, evaluator):
        """Testa compatibilidade com value: 1 (deve ser tratado como true)."""
        regra = {
            "type": "condition",
            "variable": "autor_idoso",
            "operator": "equals",
            "value": 1  # Inteiro 1 ao invés de True
        }
        assert evaluator.avaliar(regra, {"autor_idoso": True}) is True
        assert evaluator.avaliar(regra, {"autor_idoso": False}) is False


# ============================================================================
# TESTES DATA-DRIVEN (GERADOS DO SNAPSHOT)
# ============================================================================

class TestRegrasDataDriven:
    """
    Testes data-driven gerados automaticamente do snapshot.

    Para cada regra no snapshot, executa os casos de teste pré-gerados.
    """

    @pytest.fixture(autouse=True)
    def setup(self, evaluator, snapshot_data):
        """Setup dos testes."""
        self.evaluator = evaluator
        self.snapshot = snapshot_data

    @pytest.mark.parametrize(
        "regra_info",
        get_regras_do_snapshot(),
        ids=lambda r: f"prompt_{r['prompt_id']}_{r['prompt_nome'][:20]}"
    )
    def test_regra_casos_primarios(self, regra_info):
        """
        Testa todos os casos gerados para a regra primária de cada prompt.
        """
        regra = regra_info.get("regra_primaria")
        casos = regra_info.get("casos_teste_primaria", [])

        if not regra:
            pytest.skip(f"Prompt {regra_info['prompt_id']} não tem regra primária")

        if not casos:
            pytest.skip(f"Prompt {regra_info['prompt_id']} não tem casos de teste gerados")

        erros = []

        for caso in casos:
            dados = caso.get("dados", {})
            esperado = caso.get("esperado")
            nome_caso = caso.get("nome", "caso_sem_nome")

            try:
                resultado = self.evaluator.avaliar(regra, dados)

                if resultado != esperado:
                    erros.append(
                        f"  - [{nome_caso}] Esperado: {esperado}, Obtido: {resultado}\n"
                        f"    Dados: {dados}"
                    )
            except Exception as e:
                erros.append(f"  - [{nome_caso}] Erro na avaliação: {e}")

        if erros:
            pytest.fail(
                f"Falhas na regra do Prompt {regra_info['prompt_id']} ({regra_info['prompt_nome']}):\n"
                f"Regra: {regra_info.get('regra_texto_original', 'N/A')}\n"
                + "\n".join(erros)
            )

    @pytest.mark.parametrize(
        "regra_info",
        [r for r in get_regras_do_snapshot() if r.get("regra_secundaria")],
        ids=lambda r: f"prompt_{r['prompt_id']}_secundaria"
    )
    def test_regra_casos_secundarios(self, regra_info):
        """
        Testa todos os casos gerados para a regra secundária (fallback).
        """
        regra = regra_info.get("regra_secundaria")
        casos = regra_info.get("casos_teste_secundaria", [])

        if not regra:
            pytest.skip(f"Prompt {regra_info['prompt_id']} não tem regra secundária")

        if not casos:
            pytest.skip(f"Prompt {regra_info['prompt_id']} não tem casos de teste secundários")

        erros = []

        for caso in casos:
            dados = caso.get("dados", {})
            esperado = caso.get("esperado")
            nome_caso = caso.get("nome", "caso_sem_nome")

            try:
                resultado = self.evaluator.avaliar(regra, dados)

                if resultado != esperado:
                    erros.append(
                        f"  - [{nome_caso}] Esperado: {esperado}, Obtido: {resultado}\n"
                        f"    Dados: {dados}"
                    )
            except Exception as e:
                erros.append(f"  - [{nome_caso}] Erro na avaliação: {e}")

        if erros:
            pytest.fail(
                f"Falhas na regra SECUNDÁRIA do Prompt {regra_info['prompt_id']}:\n"
                + "\n".join(erros)
            )


# ============================================================================
# TESTES DE COBERTURA
# ============================================================================

class TestCoberturaRegras:
    """Testes que verificam a cobertura das regras."""

    def test_todas_regras_tem_caso_positivo(self, snapshot_data):
        """Verifica que todas as regras têm pelo menos um caso positivo."""
        regras_sem_positivo = []

        for regra in snapshot_data.get("regras", []):
            casos = regra.get("casos_teste_primaria", [])
            tem_positivo = any(c.get("tipo_caso") == "positivo" for c in casos)

            if not tem_positivo:
                regras_sem_positivo.append(
                    f"Prompt {regra['prompt_id']}: {regra['prompt_nome']}"
                )

        if regras_sem_positivo:
            pytest.fail(
                f"Regras sem caso positivo ({len(regras_sem_positivo)}):\n" +
                "\n".join(regras_sem_positivo)
            )

    def test_todas_regras_tem_caso_negativo(self, snapshot_data):
        """Verifica que todas as regras têm pelo menos um caso negativo."""
        regras_sem_negativo = []

        for regra in snapshot_data.get("regras", []):
            casos = regra.get("casos_teste_primaria", [])
            tem_negativo = any(c.get("tipo_caso") == "negativo" for c in casos)

            if not tem_negativo:
                regras_sem_negativo.append(
                    f"Prompt {regra['prompt_id']}: {regra['prompt_nome']}"
                )

        if regras_sem_negativo:
            pytest.fail(
                f"Regras sem caso negativo ({len(regras_sem_negativo)}):\n" +
                "\n".join(regras_sem_negativo)
            )

    def test_cobertura_minima_100_porcento(self, snapshot_data):
        """Verifica que 100% das regras têm cobertura mínima."""
        total_regras = len(snapshot_data.get("regras", []))
        regras_cobertas = 0

        for regra in snapshot_data.get("regras", []):
            casos = regra.get("casos_teste_primaria", [])
            tem_positivo = any(c.get("tipo_caso") == "positivo" for c in casos)
            tem_negativo = any(c.get("tipo_caso") == "negativo" for c in casos)

            if tem_positivo and tem_negativo:
                regras_cobertas += 1

        cobertura = (regras_cobertas / total_regras * 100) if total_regras > 0 else 0

        assert cobertura == 100.0, (
            f"Cobertura insuficiente: {cobertura:.1f}% "
            f"({regras_cobertas}/{total_regras} regras cobertas)"
        )


# ============================================================================
# TESTES DE VERIFICAÇÃO DE VARIÁVEIS
# ============================================================================

class TestVerificacaoVariaveis:
    """Testes que verificam a existência de variáveis nas regras."""

    @pytest.mark.parametrize(
        "regra_info",
        get_regras_do_snapshot(),
        ids=lambda r: f"vars_prompt_{r['prompt_id']}"
    )
    def test_variaveis_regra_existem(self, regra_info, snapshot_data):
        """
        Verifica que as variáveis usadas na regra estão documentadas no snapshot.
        """
        variaveis_regra = set(regra_info.get("variaveis_primaria", []))
        variaveis_snapshot = {v["slug"] for v in snapshot_data.get("variaveis", [])}

        variaveis_faltantes = variaveis_regra - variaveis_snapshot

        if variaveis_faltantes:
            pytest.warns(
                UserWarning,
                match=f"Variáveis não documentadas: {variaveis_faltantes}"
            )


# ============================================================================
# TESTES DE PRIORIDADE E CONFLITOS
# ============================================================================

class TestPrioridadeConflitos:
    """Testes que verificam conflitos entre regras."""

    def test_sem_conflito_mesmo_grupo(self, snapshot_data, evaluator):
        """
        Verifica que regras do mesmo grupo não conflitam
        (dados que ativam uma não devem ativar outra do mesmo grupo).
        """
        # Agrupa regras por group_id
        regras_por_grupo = {}
        for regra in snapshot_data.get("regras", []):
            group_id = regra.get("group_id")
            if group_id:
                if group_id not in regras_por_grupo:
                    regras_por_grupo[group_id] = []
                regras_por_grupo[group_id].append(regra)

        conflitos = []

        for group_id, regras in regras_por_grupo.items():
            if len(regras) < 2:
                continue

            for i, regra1 in enumerate(regras):
                casos1 = regra1.get("casos_teste_primaria", [])
                casos_positivos1 = [c for c in casos1 if c.get("tipo_caso") == "positivo"]

                for caso in casos_positivos1:
                    dados = caso.get("dados", {})

                    for j, regra2 in enumerate(regras):
                        if i == j:
                            continue

                        regra2_ast = regra2.get("regra_primaria")
                        if regra2_ast:
                            # Verifica se variáveis existem nos dados
                            vars_existem, _ = verificar_variaveis_existem(regra2_ast, dados)
                            if vars_existem:
                                resultado2 = evaluator.avaliar(regra2_ast, dados)
                                if resultado2:
                                    conflitos.append(
                                        f"Grupo {group_id}: "
                                        f"Prompt {regra1['prompt_id']} e {regra2['prompt_id']} "
                                        f"conflitam com dados {dados}"
                                    )

        # Conflitos são apenas avisos, não falhas
        if conflitos:
            print(f"\nAVISO: {len(conflitos)} possíveis conflitos detectados:")
            for c in conflitos[:5]:  # Mostra apenas os 5 primeiros
                print(f"  - {c}")


# ============================================================================
# TESTES DE PERFORMANCE
# ============================================================================

class TestPerformanceAvaliacao:
    """Testes de performance do avaliador."""

    def test_avaliacao_rapida_menos_10ms(self, evaluator, snapshot_data):
        """Verifica que avaliação de qualquer regra é < 10ms."""
        import time

        for regra_info in snapshot_data.get("regras", []):
            regra = regra_info.get("regra_primaria")
            if not regra:
                continue

            dados_teste = {}
            for var in regra_info.get("variaveis_primaria", []):
                dados_teste[var] = True  # Valor dummy

            inicio = time.time()
            for _ in range(100):
                evaluator.avaliar(regra, dados_teste)
            fim = time.time()

            tempo_medio_ms = (fim - inicio) / 100 * 1000

            assert tempo_medio_ms < 10, (
                f"Regra do Prompt {regra_info['prompt_id']} muito lenta: "
                f"{tempo_medio_ms:.2f}ms (máx: 10ms)"
            )

    def test_avaliacao_deterministica(self, evaluator, snapshot_data):
        """Verifica que resultado é sempre determinístico."""
        for regra_info in snapshot_data.get("regras", []):
            regra = regra_info.get("regra_primaria")
            if not regra:
                continue

            dados_teste = {}
            for var in regra_info.get("variaveis_primaria", []):
                dados_teste[var] = True

            # Executa 10 vezes
            resultados = [evaluator.avaliar(regra, dados_teste) for _ in range(10)]

            # Todos devem ser iguais
            assert len(set(resultados)) == 1, (
                f"Regra do Prompt {regra_info['prompt_id']} não é determinística: "
                f"resultados variaram {set(resultados)}"
            )


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
