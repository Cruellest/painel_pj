# tests/ia_extracao_regras/backend/unit/test_dependencies.py
"""
Testes unitários para o sistema de dependências entre perguntas.

Testa:
- DependencyEvaluator: avaliação de visibilidade condicional
- Operadores de dependência (exists, not_exists, equals, etc.)
- Preprocessamento de dados condicionais
- Integração com DeterministicRuleEvaluator
"""

import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime

# Importações do sistema
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

from sistemas.gerador_pecas.services_dependencies import (
    DependencyEvaluator, DependencyGraphBuilder
)
from sistemas.gerador_pecas.services_deterministic import (
    DeterministicRuleEvaluator
)


class TestDependencyEvaluator(unittest.TestCase):
    """Testes para o DependencyEvaluator"""

    def setUp(self):
        """Configuração antes de cada teste"""
        self.evaluator = DependencyEvaluator()

    def test_pergunta_sem_dependencia_sempre_visivel(self):
        """Pergunta sem dependência deve estar sempre visível"""
        pergunta = MagicMock()
        pergunta.depends_on_variable = None
        pergunta.dependency_config = None

        resultado = self.evaluator.avaliar_visibilidade(pergunta, {})

        self.assertTrue(resultado)

    def test_dependencia_equals_satisfeita(self):
        """Dependência equals deve ser satisfeita quando valor é igual"""
        pergunta = MagicMock()
        pergunta.depends_on_variable = "tipo_acao"
        pergunta.dependency_operator = "equals"
        pergunta.dependency_value = "medicamento"
        pergunta.dependency_config = None

        dados = {"tipo_acao": "medicamento"}

        resultado = self.evaluator.avaliar_visibilidade(pergunta, dados)

        self.assertTrue(resultado)

    def test_dependencia_equals_nao_satisfeita(self):
        """Dependência equals não satisfeita quando valor é diferente"""
        pergunta = MagicMock()
        pergunta.depends_on_variable = "tipo_acao"
        pergunta.dependency_operator = "equals"
        pergunta.dependency_value = "medicamento"
        pergunta.dependency_config = None

        dados = {"tipo_acao": "cirurgia"}

        resultado = self.evaluator.avaliar_visibilidade(pergunta, dados)

        self.assertFalse(resultado)

    def test_dependencia_exists_com_valor(self):
        """Operador exists deve ser True quando variável tem valor"""
        pergunta = MagicMock()
        pergunta.depends_on_variable = "medicamento"
        pergunta.dependency_operator = "exists"
        pergunta.dependency_value = None
        pergunta.dependency_config = None

        dados = {"medicamento": "Dipirona"}

        resultado = self.evaluator.avaliar_visibilidade(pergunta, dados)

        self.assertTrue(resultado)

    def test_dependencia_exists_sem_valor(self):
        """Operador exists deve ser False quando variável não tem valor"""
        pergunta = MagicMock()
        pergunta.depends_on_variable = "medicamento"
        pergunta.dependency_operator = "exists"
        pergunta.dependency_value = None
        pergunta.dependency_config = None

        dados = {"medicamento": None}

        resultado = self.evaluator.avaliar_visibilidade(pergunta, dados)

        self.assertFalse(resultado)

    def test_dependencia_exists_variavel_ausente(self):
        """Operador exists deve ser False quando variável não existe"""
        pergunta = MagicMock()
        pergunta.depends_on_variable = "medicamento"
        pergunta.dependency_operator = "exists"
        pergunta.dependency_value = None
        pergunta.dependency_config = None

        dados = {}

        resultado = self.evaluator.avaliar_visibilidade(pergunta, dados)

        self.assertFalse(resultado)

    def test_dependencia_not_exists_variavel_ausente(self):
        """Operador not_exists deve ser True quando variável não existe"""
        pergunta = MagicMock()
        pergunta.depends_on_variable = "medicamento"
        pergunta.dependency_operator = "not_exists"
        pergunta.dependency_value = None
        pergunta.dependency_config = None

        dados = {}

        resultado = self.evaluator.avaliar_visibilidade(pergunta, dados)

        self.assertTrue(resultado)

    def test_dependencia_not_exists_com_valor(self):
        """Operador not_exists deve ser False quando variável tem valor"""
        pergunta = MagicMock()
        pergunta.depends_on_variable = "medicamento"
        pergunta.dependency_operator = "not_exists"
        pergunta.dependency_value = None
        pergunta.dependency_config = None

        dados = {"medicamento": "Dipirona"}

        resultado = self.evaluator.avaliar_visibilidade(pergunta, dados)

        self.assertFalse(resultado)

    def test_dependencia_in_list(self):
        """Operador in_list deve funcionar corretamente"""
        pergunta = MagicMock()
        pergunta.depends_on_variable = "tipo_acao"
        pergunta.dependency_operator = "in_list"
        pergunta.dependency_value = ["medicamento", "procedimento"]
        pergunta.dependency_config = None

        dados = {"tipo_acao": "medicamento"}

        resultado = self.evaluator.avaliar_visibilidade(pergunta, dados)

        self.assertTrue(resultado)

    def test_dependencia_in_list_nao_pertence(self):
        """Operador in_list deve ser False quando valor não está na lista"""
        pergunta = MagicMock()
        pergunta.depends_on_variable = "tipo_acao"
        pergunta.dependency_operator = "in_list"
        pergunta.dependency_value = ["medicamento", "procedimento"]
        pergunta.dependency_config = None

        dados = {"tipo_acao": "internacao"}

        resultado = self.evaluator.avaliar_visibilidade(pergunta, dados)

        self.assertFalse(resultado)

    def test_dependencia_booleana_sim(self):
        """Dependência booleana com valor 'sim' deve funcionar"""
        pergunta = MagicMock()
        pergunta.depends_on_variable = "autor_idoso"
        pergunta.dependency_operator = "equals"
        pergunta.dependency_value = True
        pergunta.dependency_config = None

        dados = {"autor_idoso": "sim"}

        resultado = self.evaluator.avaliar_visibilidade(pergunta, dados)

        self.assertTrue(resultado)

    def test_dependencia_booleana_nao(self):
        """Dependência booleana com valor 'não' deve funcionar"""
        pergunta = MagicMock()
        pergunta.depends_on_variable = "autor_idoso"
        pergunta.dependency_operator = "equals"
        pergunta.dependency_value = False
        pergunta.dependency_config = None

        dados = {"autor_idoso": "não"}

        resultado = self.evaluator.avaliar_visibilidade(pergunta, dados)

        self.assertTrue(resultado)

    def test_dependencia_complexa_and(self):
        """Dependência complexa com AND deve funcionar"""
        pergunta = MagicMock()
        pergunta.depends_on_variable = None
        pergunta.dependency_config = {
            "conditions": [
                {"variable": "medicamento", "operator": "equals", "value": True},
                {"variable": "alto_custo", "operator": "equals", "value": True}
            ],
            "logic": "and"
        }

        dados = {"medicamento": True, "alto_custo": True}

        resultado = self.evaluator.avaliar_visibilidade(pergunta, dados)

        self.assertTrue(resultado)

    def test_dependencia_complexa_and_parcial(self):
        """Dependência complexa com AND parcial deve ser False"""
        pergunta = MagicMock()
        pergunta.depends_on_variable = None
        pergunta.dependency_config = {
            "conditions": [
                {"variable": "medicamento", "operator": "equals", "value": True},
                {"variable": "alto_custo", "operator": "equals", "value": True}
            ],
            "logic": "and"
        }

        dados = {"medicamento": True, "alto_custo": False}

        resultado = self.evaluator.avaliar_visibilidade(pergunta, dados)

        self.assertFalse(resultado)

    def test_dependencia_complexa_or(self):
        """Dependência complexa com OR deve funcionar"""
        pergunta = MagicMock()
        pergunta.depends_on_variable = None
        pergunta.dependency_config = {
            "conditions": [
                {"variable": "autor_idoso", "operator": "equals", "value": True},
                {"variable": "autor_deficiente", "operator": "equals", "value": True}
            ],
            "logic": "or"
        }

        dados = {"autor_idoso": True, "autor_deficiente": False}

        resultado = self.evaluator.avaliar_visibilidade(pergunta, dados)

        self.assertTrue(resultado)


class TestDeterministicRuleEvaluatorExists(unittest.TestCase):
    """Testes para operadores exists/not_exists no DeterministicRuleEvaluator"""

    def setUp(self):
        """Configuração antes de cada teste"""
        self.evaluator = DeterministicRuleEvaluator()

    def test_operador_exists_com_valor(self):
        """Operador exists deve ser True quando variável tem valor"""
        regra = {
            "type": "condition",
            "variable": "medicamento",
            "operator": "exists",
            "value": None
        }

        dados = {"medicamento": "Dipirona"}

        resultado = self.evaluator.avaliar(regra, dados)

        self.assertTrue(resultado)

    def test_operador_exists_sem_valor(self):
        """Operador exists deve ser False quando variável não tem valor"""
        regra = {
            "type": "condition",
            "variable": "medicamento",
            "operator": "exists",
            "value": None
        }

        dados = {"medicamento": None}

        resultado = self.evaluator.avaliar(regra, dados)

        self.assertFalse(resultado)

    def test_operador_exists_variavel_ausente(self):
        """Operador exists deve ser False quando variável não existe"""
        regra = {
            "type": "condition",
            "variable": "medicamento",
            "operator": "exists",
            "value": None
        }

        dados = {}

        resultado = self.evaluator.avaliar(regra, dados)

        self.assertFalse(resultado)

    def test_operador_not_exists_variavel_ausente(self):
        """Operador not_exists deve ser True quando variável não existe"""
        regra = {
            "type": "condition",
            "variable": "medicamento",
            "operator": "not_exists",
            "value": None
        }

        dados = {}

        resultado = self.evaluator.avaliar(regra, dados)

        self.assertTrue(resultado)

    def test_operador_not_exists_com_valor(self):
        """Operador not_exists deve ser False quando variável tem valor"""
        regra = {
            "type": "condition",
            "variable": "medicamento",
            "operator": "not_exists",
            "value": None
        }

        dados = {"medicamento": "Dipirona"}

        resultado = self.evaluator.avaliar(regra, dados)

        self.assertFalse(resultado)

    def test_operador_exists_variavel_nao_aplicavel(self):
        """Operador exists deve ser False para variável marcada como não aplicável"""
        regra = {
            "type": "condition",
            "variable": "detalhe_medicamento",
            "operator": "exists",
            "value": None
        }

        dados = {"detalhe_medicamento": "__NOT_APPLICABLE__"}

        resultado = self.evaluator.avaliar(regra, dados)

        self.assertFalse(resultado)

    def test_operador_not_exists_variavel_nao_aplicavel(self):
        """Operador not_exists deve ser True para variável marcada como não aplicável"""
        regra = {
            "type": "condition",
            "variable": "detalhe_medicamento",
            "operator": "not_exists",
            "value": None
        }

        dados = {"detalhe_medicamento": "__NOT_APPLICABLE__"}

        resultado = self.evaluator.avaliar(regra, dados)

        self.assertTrue(resultado)


class TestPreprocessamentoCondicionais(unittest.TestCase):
    """Testes para preprocessamento de dados condicionais"""

    def setUp(self):
        """Configuração antes de cada teste"""
        self.evaluator = DeterministicRuleEvaluator()

    def test_preprocessa_variavel_condicional_nao_satisfeita(self):
        """Variável condicional deve ser marcada como não aplicável se condição não satisfeita"""
        dados = {
            "tipo_acao": "cirurgia",  # Não é medicamento
            "detalhe_medicamento": "Alguma coisa"
        }

        variaveis_condicionais = [
            {
                "slug": "detalhe_medicamento",
                "depends_on": "tipo_acao",
                "operator": "equals",
                "value": "medicamento"
            }
        ]

        resultado = self.evaluator.preprocessar_dados_condicionais(
            dados, variaveis_condicionais
        )

        self.assertEqual(resultado["detalhe_medicamento"], "__NOT_APPLICABLE__")

    def test_preprocessa_variavel_condicional_satisfeita(self):
        """Variável condicional deve manter valor se condição satisfeita"""
        dados = {
            "tipo_acao": "medicamento",
            "detalhe_medicamento": "Dipirona"
        }

        variaveis_condicionais = [
            {
                "slug": "detalhe_medicamento",
                "depends_on": "tipo_acao",
                "operator": "equals",
                "value": "medicamento"
            }
        ]

        resultado = self.evaluator.preprocessar_dados_condicionais(
            dados, variaveis_condicionais
        )

        self.assertEqual(resultado["detalhe_medicamento"], "Dipirona")

    def test_preprocessa_cadeia_dependencias(self):
        """Cadeia de dependências deve ser processada corretamente"""
        dados = {
            "tipo_acao": "cirurgia",  # Não é medicamento
            "detalhe_medicamento": "Dipirona",
            "dosagem": "500mg"  # Depende de detalhe_medicamento
        }

        variaveis_condicionais = [
            {
                "slug": "detalhe_medicamento",
                "depends_on": "tipo_acao",
                "operator": "equals",
                "value": "medicamento"
            },
            {
                "slug": "dosagem",
                "depends_on": "detalhe_medicamento",
                "operator": "exists",
                "value": None
            }
        ]

        resultado = self.evaluator.preprocessar_dados_condicionais(
            dados, variaveis_condicionais
        )

        # Ambas devem ser marcadas como não aplicáveis
        self.assertEqual(resultado["detalhe_medicamento"], "__NOT_APPLICABLE__")
        self.assertEqual(resultado["dosagem"], "__NOT_APPLICABLE__")

    def test_preprocessa_variaveis_independentes_preservadas(self):
        """Variáveis sem dependência devem ser preservadas"""
        dados = {
            "tipo_acao": "medicamento",
            "valor_causa": "R$ 100.000,00",
            "detalhe_medicamento": "Dipirona"
        }

        variaveis_condicionais = [
            {
                "slug": "detalhe_medicamento",
                "depends_on": "tipo_acao",
                "operator": "equals",
                "value": "medicamento"
            }
        ]

        resultado = self.evaluator.preprocessar_dados_condicionais(
            dados, variaveis_condicionais
        )

        # Variáveis sem dependência preservadas
        self.assertEqual(resultado["tipo_acao"], "medicamento")
        self.assertEqual(resultado["valor_causa"], "R$ 100.000,00")


class TestRegraComVariavelCondicional(unittest.TestCase):
    """Testes de integração: regras usando variáveis condicionais"""

    def setUp(self):
        """Configuração antes de cada teste"""
        self.evaluator = DeterministicRuleEvaluator()

    def test_regra_com_variavel_condicional_aplicavel(self):
        """Regra deve funcionar quando variável condicional é aplicável"""
        regra = {
            "type": "and",
            "conditions": [
                {"type": "condition", "variable": "tipo_acao", "operator": "equals", "value": "medicamento"},
                {"type": "condition", "variable": "medicamento_alto_custo", "operator": "equals", "value": True}
            ]
        }

        dados = {
            "tipo_acao": "medicamento",
            "medicamento_alto_custo": True
        }

        resultado = self.evaluator.avaliar(regra, dados)

        self.assertTrue(resultado)

    def test_regra_com_variavel_ausente(self):
        """Regra deve ser False quando variável está ausente"""
        regra = {
            "type": "condition",
            "variable": "medicamento_alto_custo",
            "operator": "equals",
            "value": True
        }

        dados = {
            "tipo_acao": "cirurgia"
            # medicamento_alto_custo não existe
        }

        resultado = self.evaluator.avaliar(regra, dados)

        self.assertFalse(resultado)

    def test_regra_com_exists_em_condicao_composta(self):
        """Regra composta com exists deve funcionar"""
        regra = {
            "type": "and",
            "conditions": [
                {"type": "condition", "variable": "medicamento", "operator": "exists", "value": None},
                {"type": "condition", "variable": "medicamento_alto_custo", "operator": "equals", "value": True}
            ]
        }

        dados = {
            "medicamento": "Dipirona",
            "medicamento_alto_custo": True
        }

        resultado = self.evaluator.avaliar(regra, dados)

        self.assertTrue(resultado)

    def test_regra_com_not_exists_como_alternativa(self):
        """Regra OR com not_exists deve funcionar como fallback"""
        regra = {
            "type": "or",
            "conditions": [
                {"type": "condition", "variable": "medicamento_alto_custo", "operator": "equals", "value": True},
                {"type": "condition", "variable": "medicamento_alto_custo", "operator": "not_exists", "value": None}
            ]
        }

        # Cenário 1: variável existe e é True
        dados1 = {"medicamento_alto_custo": True}
        self.assertTrue(self.evaluator.avaliar(regra, dados1))

        # Cenário 2: variável não existe
        dados2 = {}
        self.assertTrue(self.evaluator.avaliar(regra, dados2))

        # Cenário 3: variável existe mas é False
        dados3 = {"medicamento_alto_custo": False}
        self.assertFalse(self.evaluator.avaliar(regra, dados3))


if __name__ == '__main__':
    unittest.main()
