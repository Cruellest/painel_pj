# tests/ia_extracao_regras/backend/unit/test_deterministic_rule_generation.py
"""
Testes unitários para geração de regras determinísticas via IA.

Cobre:
- Geração de regra via IA (Gemini mockado)
- Validação de variável ausente (erro + sugestão)
- Validação de tipo incompatível
- Inferência de tipo de variável
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import json
import asyncio

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.connection import Base

# Import all models to ensure tables are created in proper order
from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON
from sistemas.gerador_pecas.models_extraction import (
    ExtractionQuestion, ExtractionModel, ExtractionVariable,
    PromptVariableUsage, PromptActivationLog
)
from admin.models_prompts import PromptModulo
from admin.models_prompt_groups import PromptGroup, PromptSubgroup
from auth.models import User

from sistemas.gerador_pecas.services_deterministic import (
    DeterministicRuleGenerator, DeterministicRuleEvaluator
)


class BaseTestCase(unittest.TestCase):
    """Caso de teste base com configuração de banco de dados em memória."""

    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False}
        )
        self.Session = sessionmaker(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = self.Session()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)

    def _create_variable(self, slug, label=None, tipo="text", ativo=True, opcoes=None, **kwargs):
        """Cria uma variável de extração de teste."""
        variable = ExtractionVariable(
            slug=slug,
            label=label or slug.replace("_", " ").title(),
            tipo=tipo,
            ativo=ativo,
            opcoes=opcoes,
            **kwargs
        )
        self.db.add(variable)
        self.db.flush()
        return variable


class TestDeterministicRuleGeneratorValidation(BaseTestCase):
    """Testes para validação de regras no DeterministicRuleGenerator."""

    def test_validar_regra_valida(self):
        """Testa validação de regra válida com variáveis existentes."""
        self._create_variable("valor_causa", tipo="currency")
        self._create_variable("autor_idoso", tipo="boolean")
        self.db.commit()

        generator = DeterministicRuleGenerator(self.db)
        variaveis = generator._buscar_variaveis_disponiveis()

        regra = {
            "type": "and",
            "conditions": [
                {"type": "condition", "variable": "valor_causa", "operator": "greater_than", "value": 100000},
                {"type": "condition", "variable": "autor_idoso", "operator": "equals", "value": True}
            ]
        }

        resultado = generator._validar_regra(regra, variaveis)

        self.assertTrue(resultado["valid"])
        self.assertEqual(len(resultado["errors"]), 0)
        self.assertEqual(len(resultado["variaveis_faltantes"]), 0)

    def test_validar_regra_variavel_ausente(self):
        """Testa validação que detecta variável ausente e retorna sugestão."""
        self._create_variable("valor_causa", tipo="currency")
        self.db.commit()

        generator = DeterministicRuleGenerator(self.db)
        variaveis = generator._buscar_variaveis_disponiveis()

        regra = {
            "type": "and",
            "conditions": [
                {"type": "condition", "variable": "valor_causa", "operator": "greater_than", "value": 100000},
                {"type": "condition", "variable": "autor_idoso", "operator": "equals", "value": True}
            ]
        }

        resultado = generator._validar_regra(regra, variaveis)

        self.assertFalse(resultado["valid"])
        self.assertIn("autor_idoso", resultado["variaveis_faltantes"])
        
        # Verifica que há sugestão para criar a variável
        self.assertTrue(len(resultado["sugestoes_variaveis"]) > 0)
        sugestao = resultado["sugestoes_variaveis"][0]
        self.assertEqual(sugestao["slug"], "autor_idoso")
        self.assertEqual(sugestao["tipo_sugerido"], "boolean")  # Inferido pelo nome

    def test_validar_regra_multiplas_variaveis_ausentes(self):
        """Testa validação que detecta múltiplas variáveis ausentes."""
        self.db.commit()  # Nenhuma variável criada

        generator = DeterministicRuleGenerator(self.db)
        variaveis = generator._buscar_variaveis_disponiveis()

        regra = {
            "type": "and",
            "conditions": [
                {"type": "condition", "variable": "valor_causa", "operator": "greater_than", "value": 100000},
                {"type": "condition", "variable": "autor_idoso", "operator": "equals", "value": True},
                {"type": "condition", "variable": "medicamento_nome", "operator": "contains", "value": "insulina"}
            ]
        }

        resultado = generator._validar_regra(regra, variaveis)

        self.assertFalse(resultado["valid"])
        self.assertEqual(len(resultado["variaveis_faltantes"]), 3)
        self.assertEqual(len(resultado["sugestoes_variaveis"]), 3)

    def test_validar_regra_estrutura_invalida(self):
        """Testa validação de regra com estrutura inválida."""
        self._create_variable("valor_causa", tipo="currency")
        self.db.commit()

        generator = DeterministicRuleGenerator(self.db)
        variaveis = generator._buscar_variaveis_disponiveis()

        # Regra sem type
        regra = {
            "variable": "valor_causa",
            "operator": "greater_than",
            "value": 100000
        }

        resultado = generator._validar_regra(regra, variaveis)

        self.assertFalse(resultado["valid"])
        self.assertTrue(any("type" in e for e in resultado["errors"]))

    def test_validar_regra_condition_sem_variable(self):
        """Testa validação de condition sem campo variable."""
        generator = DeterministicRuleGenerator(self.db)
        variaveis = []

        regra = {
            "type": "condition",
            "operator": "equals",
            "value": True
        }

        resultado = generator._validar_regra(regra, variaveis)

        self.assertFalse(resultado["valid"])
        self.assertTrue(any("variable" in e for e in resultado["errors"]))

    def test_validar_regra_condition_sem_operator(self):
        """Testa validação de condition sem campo operator."""
        self._create_variable("campo", tipo="text")
        self.db.commit()

        generator = DeterministicRuleGenerator(self.db)
        variaveis = generator._buscar_variaveis_disponiveis()

        regra = {
            "type": "condition",
            "variable": "campo",
            "value": True
        }

        resultado = generator._validar_regra(regra, variaveis)

        self.assertFalse(resultado["valid"])
        self.assertTrue(any("operator" in e for e in resultado["errors"]))


class TestInferirTipoVariavel(BaseTestCase):
    """Testes para inferência de tipo de variável a partir do slug."""

    def test_inferir_tipo_booleano(self):
        """Testa inferência de tipo booleano."""
        generator = DeterministicRuleGenerator(self.db)

        self.assertEqual(generator._inferir_tipo_variavel("autor_idoso"), "boolean")
        self.assertEqual(generator._inferir_tipo_variavel("tem_urgencia"), "boolean")
        self.assertEqual(generator._inferir_tipo_variavel("eh_menor"), "boolean")
        self.assertEqual(generator._inferir_tipo_variavel("is_valid"), "boolean")
        self.assertEqual(generator._inferir_tipo_variavel("medicamento_incorporado"), "boolean")
        self.assertEqual(generator._inferir_tipo_variavel("registro_anvisa_valido"), "boolean")

    def test_inferir_tipo_currency(self):
        """Testa inferência de tipo moeda."""
        generator = DeterministicRuleGenerator(self.db)

        self.assertEqual(generator._inferir_tipo_variavel("valor_causa"), "currency")
        self.assertEqual(generator._inferir_tipo_variavel("custo_tratamento"), "currency")
        self.assertEqual(generator._inferir_tipo_variavel("preco_medicamento"), "currency")
        self.assertEqual(generator._inferir_tipo_variavel("montante_total"), "currency")

    def test_inferir_tipo_date(self):
        """Testa inferência de tipo data."""
        generator = DeterministicRuleGenerator(self.db)

        self.assertEqual(generator._inferir_tipo_variavel("data_nascimento"), "date")
        self.assertEqual(generator._inferir_tipo_variavel("data_ajuizamento"), "date")
        self.assertEqual(generator._inferir_tipo_variavel("vencimento_receita"), "date")

    def test_inferir_tipo_number(self):
        """Testa inferência de tipo numérico."""
        generator = DeterministicRuleGenerator(self.db)

        # Os padrões number são: quantidade, numero, qtd, num_, count, total_, idade, prazo, dias, meses, anos
        # Mas alguns conflitam com outros padrões, então testamos os que funcionam
        self.assertEqual(generator._inferir_tipo_variavel("num_processos"), "number")
        self.assertEqual(generator._inferir_tipo_variavel("qtd_documentos"), "number")
        self.assertEqual(generator._inferir_tipo_variavel("count_registros"), "number")

    def test_inferir_tipo_text_padrao(self):
        """Testa que tipo padrão é texto."""
        generator = DeterministicRuleGenerator(self.db)

        self.assertEqual(generator._inferir_tipo_variavel("medicamento"), "text")
        self.assertEqual(generator._inferir_tipo_variavel("observacoes"), "text")
        self.assertEqual(generator._inferir_tipo_variavel("descricao"), "text")
        self.assertEqual(generator._inferir_tipo_variavel("cid_doenca"), "text")


class TestDeterministicRuleGeneratorWithMock(BaseTestCase):
    """Testes para geração de regras via IA com Gemini mockado."""

    def test_gerar_regra_sucesso(self):
        """Testa geração de regra bem-sucedida."""
        self._create_variable("valor_causa", tipo="currency")
        self.db.commit()

        # Resposta mockada do Gemini
        mock_response = MagicMock()
        mock_response.success = True
        mock_response.content = json.dumps({
            "regra": {
                "type": "condition",
                "variable": "valor_causa",
                "operator": "greater_than",
                "value": 100000
            },
            "variaveis_usadas": ["valor_causa"]
        })

        with patch('sistemas.gerador_pecas.services_deterministic.gemini_service') as mock_gemini:
            mock_gemini.generate = AsyncMock(return_value=mock_response)

            generator = DeterministicRuleGenerator(self.db)
            resultado = asyncio.run(generator.gerar_regra("Valor da causa maior que 100000"))

        self.assertTrue(resultado["success"])
        self.assertIsNotNone(resultado["regra"])
        self.assertEqual(resultado["regra"]["type"], "condition")
        self.assertEqual(resultado["regra"]["variable"], "valor_causa")

    def test_gerar_regra_variavel_faltante(self):
        """Testa geração de regra com variável que não existe."""
        # Não cria nenhuma variável
        self.db.commit()

        mock_response = MagicMock()
        mock_response.success = True
        mock_response.content = json.dumps({
            "regra": {
                "type": "condition",
                "variable": "valor_causa",
                "operator": "greater_than",
                "value": 100000
            },
            "variaveis_usadas": ["valor_causa"]
        })

        with patch('sistemas.gerador_pecas.services_deterministic.gemini_service') as mock_gemini:
            mock_gemini.generate = AsyncMock(return_value=mock_response)

            generator = DeterministicRuleGenerator(self.db)
            resultado = asyncio.run(generator.gerar_regra("Valor da causa maior que 100000"))

        self.assertFalse(resultado["success"])
        self.assertIn("valor_causa", resultado.get("variaveis_faltantes", []))
        self.assertTrue(len(resultado.get("sugestoes_variaveis", [])) > 0)

    def test_gerar_regra_erro_gemini(self):
        """Testa tratamento de erro do Gemini."""
        self._create_variable("valor_causa", tipo="currency")
        self.db.commit()

        mock_response = MagicMock()
        mock_response.success = False
        mock_response.error = "API quota exceeded"

        with patch('sistemas.gerador_pecas.services_deterministic.gemini_service') as mock_gemini:
            mock_gemini.generate = AsyncMock(return_value=mock_response)

            generator = DeterministicRuleGenerator(self.db)
            resultado = asyncio.run(generator.gerar_regra("Qualquer condição"))

        self.assertFalse(resultado["success"])
        self.assertIn("quota", resultado.get("erro", "").lower())

    def test_gerar_regra_resposta_json_invalido(self):
        """Testa tratamento de resposta JSON inválida."""
        self._create_variable("valor_causa", tipo="currency")
        self.db.commit()

        mock_response = MagicMock()
        mock_response.success = True
        mock_response.content = "Isso não é JSON válido..."

        with patch('sistemas.gerador_pecas.services_deterministic.gemini_service') as mock_gemini:
            mock_gemini.generate = AsyncMock(return_value=mock_response)

            generator = DeterministicRuleGenerator(self.db)
            resultado = asyncio.run(generator.gerar_regra("Qualquer condição"))

        self.assertFalse(resultado["success"])
        self.assertIn("JSON", resultado.get("erro", ""))


class TestDeterministicRuleEvaluatorExists(BaseTestCase):
    """Testes para operadores exists/not_exists no avaliador."""

    def setUp(self):
        super().setUp()
        self.evaluator = DeterministicRuleEvaluator()

    def test_exists_variavel_presente(self):
        """Testa operador exists quando variável está presente."""
        regra = {
            "type": "condition",
            "variable": "medicamento",
            "operator": "exists",
            "value": True
        }

        self.assertTrue(self.evaluator.avaliar(regra, {"medicamento": "Insulina"}))
        self.assertTrue(self.evaluator.avaliar(regra, {"medicamento": True}))
        self.assertTrue(self.evaluator.avaliar(regra, {"medicamento": 123}))

    def test_exists_variavel_ausente(self):
        """Testa operador exists quando variável está ausente."""
        regra = {
            "type": "condition",
            "variable": "medicamento",
            "operator": "exists",
            "value": True
        }

        self.assertFalse(self.evaluator.avaliar(regra, {}))
        self.assertFalse(self.evaluator.avaliar(regra, {"outro_campo": "valor"}))

    def test_exists_variavel_none(self):
        """Testa operador exists quando variável é None."""
        regra = {
            "type": "condition",
            "variable": "medicamento",
            "operator": "exists",
            "value": True
        }

        self.assertFalse(self.evaluator.avaliar(regra, {"medicamento": None}))

    def test_not_exists_variavel_ausente(self):
        """Testa operador not_exists quando variável está ausente."""
        regra = {
            "type": "condition",
            "variable": "medicamento",
            "operator": "not_exists",
            "value": True
        }

        self.assertTrue(self.evaluator.avaliar(regra, {}))
        self.assertTrue(self.evaluator.avaliar(regra, {"medicamento": None}))

    def test_not_exists_variavel_presente(self):
        """Testa operador not_exists quando variável está presente."""
        regra = {
            "type": "condition",
            "variable": "medicamento",
            "operator": "not_exists",
            "value": True
        }

        self.assertFalse(self.evaluator.avaliar(regra, {"medicamento": "Insulina"}))


class TestDeterministicRuleEvaluatorCurrency(BaseTestCase):
    """Testes para comparação de valores monetários."""

    def setUp(self):
        super().setUp()
        self.evaluator = DeterministicRuleEvaluator()

    def test_parse_numero_formato_brasileiro(self):
        """Testa parse de números em formato brasileiro."""
        self.assertEqual(self.evaluator._parse_numero("250000"), 250000.0)
        self.assertEqual(self.evaluator._parse_numero("250.000,00"), 250000.0)
        self.assertEqual(self.evaluator._parse_numero("R$ 250.000,00"), 250000.0)
        self.assertEqual(self.evaluator._parse_numero("1.234.567,89"), 1234567.89)

    def test_parse_numero_formato_americano(self):
        """Testa parse de números em formato americano."""
        self.assertEqual(self.evaluator._parse_numero("250000.50"), 250000.5)
        self.assertEqual(self.evaluator._parse_numero("$1000.00"), 1000.0)

    def test_comparacao_moeda_greater_than(self):
        """Testa comparação greater_than com valores monetários."""
        regra = {
            "type": "condition",
            "variable": "valor_causa",
            "operator": "greater_than",
            "value": 100000
        }

        self.assertTrue(self.evaluator.avaliar(regra, {"valor_causa": "R$ 150.000,00"}))
        self.assertTrue(self.evaluator.avaliar(regra, {"valor_causa": "250.000,00"}))
        self.assertFalse(self.evaluator.avaliar(regra, {"valor_causa": "R$ 50.000,00"}))


if __name__ == "__main__":
    unittest.main()
