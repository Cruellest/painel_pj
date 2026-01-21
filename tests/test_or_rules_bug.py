# tests/test_or_rules_bug.py
"""
Testes para reproduzir e corrigir o bug critico de regras OR com value: 1.

BUG IDENTIFICADO:
- Regras com operador OR e value: 1 (integer) nao estao ativando corretamente
- O problema esta em _avaliar_condicao() que so normaliza variaveis inexistentes
  quando valor_esperado esta em (True, False, "true", "false"), mas nao para 1/0.

CASO ESPECIFICO: Modulo evt_tres_orcamentos
- Regra: OR de varias condicoes com value: 1
- Uma variavel (peticao_inicial_pedido_cirurgia) foi extraida como True
- Mas o modulo nao ativou

ROOT CAUSE:
- Linha 1094 de services_deterministic.py:
    if valor_esperado in (True, False, "true", "false"):
- Quando value e 1, a condicao e falsa, entao valor_atual permanece None
- _comparar_igual(None, 1) retorna False
"""

import pytest
import sys
import os

# Adiciona o diretorio raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sistemas.gerador_pecas.services_deterministic import (
    DeterministicRuleEvaluator,
    pode_avaliar_regra,
    _pode_avaliar_no,
)


class TestOrRuleWithIntegerValues:
    """Testes especificos para regras OR com value: 1 (bug critico)."""

    def setup_method(self):
        """Setup para cada teste."""
        self.avaliador = DeterministicRuleEvaluator()

    def test_or_rule_with_value_1_and_single_true_variable(self):
        """
        CASO DO BUG: Regra OR com value: 1, apenas uma variavel existe com valor True.

        ESPERADO: Deve ativar (True)
        BUG ATUAL: Retorna False
        """
        regra = {
            "type": "or",
            "conditions": [
                {"type": "condition", "variable": "var_a", "operator": "equals", "value": 1},
                {"type": "condition", "variable": "var_b", "operator": "equals", "value": 1},
                {"type": "condition", "variable": "var_c", "operator": "equals", "value": 1},
            ]
        }

        # Apenas var_b existe com valor True
        dados = {"var_b": True}

        resultado = self.avaliador.avaliar(regra, dados)

        # DEVE retornar True porque var_b=True deve ser equivalente a value=1
        assert resultado is True, \
            f"Regra OR com var_b=True deveria ativar, mas retornou {resultado}"

    def test_or_rule_with_value_true_and_single_true_variable(self):
        """
        Regra OR com value: true (booleano), apenas uma variavel existe com valor True.

        ESPERADO: Deve ativar (True)
        """
        regra = {
            "type": "or",
            "conditions": [
                {"type": "condition", "variable": "var_a", "operator": "equals", "value": True},
                {"type": "condition", "variable": "var_b", "operator": "equals", "value": True},
                {"type": "condition", "variable": "var_c", "operator": "equals", "value": True},
            ]
        }

        # Apenas var_b existe com valor True
        dados = {"var_b": True}

        resultado = self.avaliador.avaliar(regra, dados)

        assert resultado is True, \
            f"Regra OR com var_b=True (value: true) deveria ativar, mas retornou {resultado}"

    def test_comparar_igual_true_vs_1(self):
        """
        Teste direto de _comparar_igual(True, 1).

        ESPERADO: Deve retornar True (1 e equivalente a True)
        """
        resultado = self.avaliador._comparar_igual(True, 1)
        assert resultado is True, \
            f"_comparar_igual(True, 1) deveria retornar True, mas retornou {resultado}"

    def test_comparar_igual_none_vs_1(self):
        """
        Teste direto de _comparar_igual(None, 1).

        ESPERADO: Deve retornar False
        """
        resultado = self.avaliador._comparar_igual(None, 1)
        assert resultado is False, \
            f"_comparar_igual(None, 1) deveria retornar False, mas retornou {resultado}"

    def test_comparar_igual_false_vs_0(self):
        """
        Teste direto de _comparar_igual(False, 0).

        ESPERADO: Deve retornar True (0 e equivalente a False)
        """
        resultado = self.avaliador._comparar_igual(False, 0)
        assert resultado is True, \
            f"_comparar_igual(False, 0) deveria retornar True, mas retornou {resultado}"


class TestEvtTresOrcamentosScenario:
    """
    Testes especificos para o cenario do modulo evt_tres_orcamentos.

    Este modulo tem uma regra OR com 10+ condicoes usando value: 1.
    Processo 08686828720258120001 tinha peticao_inicial_pedido_cirurgia = true
    mas o modulo NAO ATIVOU.
    """

    def setup_method(self):
        """Setup para cada teste."""
        self.avaliador = DeterministicRuleEvaluator()

        # Regra real do modulo evt_tres_orcamentos (reproduzida do banco)
        self.regra_evt_tres_orcamentos = {
            "type": "or",
            "conditions": [
                {"type": "condition", "variable": "peticao_inicial_pedido_medicamento", "operator": "equals", "value": 1},
                {"type": "condition", "variable": "peticao_inicial_pedido_exame", "operator": "equals", "value": 1},
                {"type": "condition", "variable": "peticao_inicial_pedido_consulta", "operator": "equals", "value": 1},
                {"type": "condition", "variable": "peticao_inicial_pedido_cirurgia", "operator": "equals", "value": 1},
                {"type": "condition", "variable": "peticao_inicial_pedido_dieta_suplemento", "operator": "equals", "value": 1},
                {"type": "condition", "variable": "peticao_inicial_pedido_home_care", "operator": "equals", "value": 1},
                {"type": "condition", "variable": "peticao_inicial_pedido_transferencia_hospitalar", "operator": "equals", "value": 1},
                {"type": "condition", "variable": "peticao_inicial_equipamentos_materiais", "operator": "equals", "value": 1},
                {"type": "condition", "variable": "peticao_inicial_tratamentos", "operator": "equals", "value": 1},
                {"type": "condition", "variable": "peticao_inicial_procedimentos", "operator": "equals", "value": 1},
            ]
        }

    def test_pode_avaliar_regra_com_uma_variavel(self):
        """
        Verifica se pode_avaliar_regra() permite avaliacao com apenas uma variavel.

        Para OR, deve retornar True se PELO MENOS UMA variavel existe.
        """
        dados = {"peticao_inicial_pedido_cirurgia": True}

        pode, existentes, faltantes = pode_avaliar_regra(self.regra_evt_tres_orcamentos, dados)

        assert pode is True, \
            f"pode_avaliar_regra() deveria retornar True para OR com 1 variavel existente"
        assert "peticao_inicial_pedido_cirurgia" in existentes
        assert len(faltantes) == 9  # 9 outras variaveis faltantes

    def test_cenario_real_processo_08686828720258120001(self):
        """
        Reproduz o cenario real do processo 08686828720258120001.

        Dados: peticao_inicial_pedido_cirurgia = true
        Regra: OR com value: 1

        ESPERADO: Deve ativar (True)
        BUG: Retorna False
        """
        dados = {"peticao_inicial_pedido_cirurgia": True}

        # Primeiro verifica se pode avaliar
        pode, existentes, faltantes = pode_avaliar_regra(self.regra_evt_tres_orcamentos, dados)
        assert pode is True, "Deveria poder avaliar a regra"

        # Agora avalia
        resultado = self.avaliador.avaliar(self.regra_evt_tres_orcamentos, dados)

        assert resultado is True, \
            f"Modulo evt_tres_orcamentos deveria ter ativado com peticao_inicial_pedido_cirurgia=True, " \
            f"mas resultado foi {resultado}"

    def test_cenario_com_multiplas_variaveis_true(self):
        """
        Cenario com multiplas variaveis True.

        ESPERADO: Deve ativar (True)
        """
        dados = {
            "peticao_inicial_pedido_medicamento": True,
            "peticao_inicial_pedido_cirurgia": True,
        }

        resultado = self.avaliador.avaliar(self.regra_evt_tres_orcamentos, dados)

        assert resultado is True, \
            f"Regra OR com 2 variaveis True deveria ativar, mas resultado foi {resultado}"

    def test_cenario_com_todas_variaveis_false(self):
        """
        Cenario com todas as variaveis False.

        ESPERADO: Nao deve ativar (False)
        """
        dados = {
            "peticao_inicial_pedido_medicamento": False,
            "peticao_inicial_pedido_exame": False,
            "peticao_inicial_pedido_consulta": False,
            "peticao_inicial_pedido_cirurgia": False,
            "peticao_inicial_pedido_dieta_suplemento": False,
            "peticao_inicial_pedido_home_care": False,
            "peticao_inicial_pedido_transferencia_hospitalar": False,
            "peticao_inicial_equipamentos_materiais": False,
            "peticao_inicial_tratamentos": False,
            "peticao_inicial_procedimentos": False,
        }

        resultado = self.avaliador.avaliar(self.regra_evt_tres_orcamentos, dados)

        assert resultado is False, \
            f"Regra OR com todas variaveis False deveria NAO ativar, mas resultado foi {resultado}"

    def test_cenario_sem_nenhuma_variavel(self):
        """
        Cenario sem nenhuma variavel extraida.

        ESPERADO: Nao deve ativar (False) pois nenhuma condicao pode ser avaliada como True
        """
        dados = {}

        # Primeiro verifica se pode avaliar
        pode, existentes, faltantes = pode_avaliar_regra(self.regra_evt_tres_orcamentos, dados)
        assert pode is False, "Nao deveria poder avaliar sem variaveis"

        # Avaliacao com dados vazios deve retornar False
        resultado = self.avaliador.avaliar(self.regra_evt_tres_orcamentos, dados)
        assert resultado is False


class TestOrAndInteraction:
    """
    Testes para garantir que a correcao nao quebra AND.
    """

    def setup_method(self):
        """Setup para cada teste."""
        self.avaliador = DeterministicRuleEvaluator()

    def test_and_rule_with_all_true(self):
        """
        Regra AND com todas variaveis True.

        ESPERADO: Deve ativar (True)
        """
        regra = {
            "type": "and",
            "conditions": [
                {"type": "condition", "variable": "var_a", "operator": "equals", "value": 1},
                {"type": "condition", "variable": "var_b", "operator": "equals", "value": 1},
            ]
        }

        dados = {"var_a": True, "var_b": True}

        resultado = self.avaliador.avaliar(regra, dados)

        assert resultado is True

    def test_and_rule_with_one_false(self):
        """
        Regra AND com uma variavel False.

        ESPERADO: Nao deve ativar (False)
        """
        regra = {
            "type": "and",
            "conditions": [
                {"type": "condition", "variable": "var_a", "operator": "equals", "value": 1},
                {"type": "condition", "variable": "var_b", "operator": "equals", "value": 1},
            ]
        }

        dados = {"var_a": True, "var_b": False}

        resultado = self.avaliador.avaliar(regra, dados)

        assert resultado is False

    def test_and_rule_with_missing_variable(self):
        """
        Regra AND com uma variavel faltante.

        ESPERADO: Nao deve ativar (False) porque AND requer TODAS as variaveis
        """
        regra = {
            "type": "and",
            "conditions": [
                {"type": "condition", "variable": "var_a", "operator": "equals", "value": 1},
                {"type": "condition", "variable": "var_b", "operator": "equals", "value": 1},
            ]
        }

        # Apenas var_a existe
        dados = {"var_a": True}

        # Para AND, pode_avaliar_regra deve retornar False se falta variavel
        pode, existentes, faltantes = pode_avaliar_regra(regra, dados)
        assert pode is False, "AND nao deveria poder ser avaliado com variavel faltante"


class TestNormalizationEdgeCases:
    """
    Testes para casos de normalizacao de valores.
    """

    def setup_method(self):
        """Setup para cada teste."""
        self.avaliador = DeterministicRuleEvaluator()

    def test_value_1_vs_true_string(self):
        """Valor string "true" comparado com value: 1."""
        resultado = self.avaliador._comparar_igual("true", 1)
        assert resultado is True

    def test_value_0_vs_false_string(self):
        """Valor string "false" comparado com value: 0."""
        resultado = self.avaliador._comparar_igual("false", 0)
        assert resultado is True

    def test_value_1_vs_sim_string(self):
        """Valor string "sim" comparado com value: 1."""
        resultado = self.avaliador._comparar_igual("sim", 1)
        assert resultado is True

    def test_value_0_vs_nao_string(self):
        """Valor string "nao" comparado com value: 0."""
        resultado = self.avaliador._comparar_igual("nao", 0)
        assert resultado is True

    def test_normalizacao_1_e_true_intercambiaveis(self):
        """
        Verifica que value: 1 e value: true sao intercambiaveis para variaveis booleanas.
        """
        regra_com_1 = {
            "type": "condition",
            "variable": "var",
            "operator": "equals",
            "value": 1
        }
        regra_com_true = {
            "type": "condition",
            "variable": "var",
            "operator": "equals",
            "value": True
        }

        dados = {"var": True}

        resultado_1 = self.avaliador.avaliar(regra_com_1, dados)
        resultado_true = self.avaliador.avaliar(regra_com_true, dados)

        assert resultado_1 == resultado_true, \
            f"value: 1 e value: true deveriam ser equivalentes. " \
            f"value:1 retornou {resultado_1}, value:true retornou {resultado_true}"


class TestVariavelInexistenteComValue1:
    """
    Testes especificos para o comportamento quando variavel nao existe
    e a regra usa value: 1.

    Este e o cenario do bug: variaveis inexistentes com value: 1.
    """

    def setup_method(self):
        """Setup para cada teste."""
        self.avaliador = DeterministicRuleEvaluator()

    def test_variavel_inexistente_com_value_1_retorna_false(self):
        """
        Quando variavel nao existe e value e 1, deve retornar False.

        COMPORTAMENTO ESPERADO:
        - Variavel inexistente e tratada como False (para booleanos)
        - False != 1 (True), entao resultado = False
        """
        regra = {
            "type": "condition",
            "variable": "variavel_que_nao_existe",
            "operator": "equals",
            "value": 1
        }

        dados = {}  # Variavel nao existe

        resultado = self.avaliador.avaliar(regra, dados)

        assert resultado is False, \
            "Variavel inexistente comparada com value:1 deveria retornar False"

    def test_variavel_inexistente_com_value_true_retorna_false(self):
        """
        Quando variavel nao existe e value e True, deve retornar False.
        """
        regra = {
            "type": "condition",
            "variable": "variavel_que_nao_existe",
            "operator": "equals",
            "value": True
        }

        dados = {}  # Variavel nao existe

        resultado = self.avaliador.avaliar(regra, dados)

        assert resultado is False, \
            "Variavel inexistente comparada com value:true deveria retornar False"

    def test_or_com_9_inexistentes_e_1_true(self):
        """
        OR com 9 variaveis inexistentes e 1 variavel True.

        Este e EXATAMENTE o cenario do bug do evt_tres_orcamentos!
        """
        regra = {
            "type": "or",
            "conditions": [
                {"type": "condition", "variable": "var_1", "operator": "equals", "value": 1},
                {"type": "condition", "variable": "var_2", "operator": "equals", "value": 1},
                {"type": "condition", "variable": "var_3", "operator": "equals", "value": 1},
                {"type": "condition", "variable": "var_4", "operator": "equals", "value": 1},
                {"type": "condition", "variable": "var_5", "operator": "equals", "value": 1},
                {"type": "condition", "variable": "var_6", "operator": "equals", "value": 1},
                {"type": "condition", "variable": "var_7", "operator": "equals", "value": 1},
                {"type": "condition", "variable": "var_8", "operator": "equals", "value": 1},
                {"type": "condition", "variable": "var_9", "operator": "equals", "value": 1},
                {"type": "condition", "variable": "var_10", "operator": "equals", "value": 1},
            ]
        }

        # Apenas var_5 existe com valor True
        dados = {"var_5": True}

        resultado = self.avaliador.avaliar(regra, dados)

        # OR deve retornar True se PELO MENOS UMA condicao e True
        assert resultado is True, \
            f"OR com 1 variavel True deveria ativar, mas retornou {resultado}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
