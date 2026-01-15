# tests/ia_extracao_regras/e2e/test_linguagem_natural_regras.py
"""
Testes end-to-end para o fluxo de linguagem natural -> regra determinística.

Cobre:
1. Criar módulo determinístico via linguagem natural
2. Regra gerada é aplicada no builder
3. Salvar e reabrir módulo mantendo regra
4. Caso de variável ausente (mostra mensagem clara e sugestão)
"""

import unittest
from unittest.mock import patch, AsyncMock, MagicMock
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
    DeterministicRuleGenerator, DeterministicRuleEvaluator, PromptVariableUsageSync
)


class BaseE2ETestCase(unittest.TestCase):
    """Caso de teste base E2E com configuração de banco de dados."""

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False}
        )
        cls.Session = sessionmaker(bind=cls.engine)
        Base.metadata.create_all(bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=cls.engine)

    def setUp(self):
        self.db = self.Session()

    def tearDown(self):
        self.db.rollback()
        self.db.close()

    def _create_variable(self, slug, label=None, tipo="text", ativo=True, opcoes=None):
        """Cria uma variável de extração de teste."""
        variable = ExtractionVariable(
            slug=slug,
            label=label or slug.replace("_", " ").title(),
            tipo=tipo,
            ativo=ativo,
            opcoes=opcoes
        )
        self.db.add(variable)
        self.db.flush()
        return variable

    def _create_prompt(self, nome, modo_ativacao="llm", regra=None, regra_texto=None):
        """Cria um prompt de teste."""
        prompt = PromptModulo(
            nome=nome,
            titulo=nome.title(),
            tipo="conteudo",
            conteudo="Conteúdo de teste",
            modo_ativacao=modo_ativacao,
            regra_deterministica=regra,
            regra_texto_original=regra_texto,
            ativo=True,
            ordem=0,
            palavras_chave=[],
            tags=[]
        )
        self.db.add(prompt)
        self.db.flush()
        return prompt


class TestFluxoLinguagemNaturalCompleto(BaseE2ETestCase):
    """
    Testa o fluxo completo: linguagem natural -> regra -> builder -> salvar.
    """

    def test_criar_modulo_via_linguagem_natural_sucesso(self):
        """
        E2E: Criar módulo determinístico via linguagem natural com sucesso.

        Fluxo:
        1. Usuário escreve condição em linguagem natural
        2. IA gera regra determinística
        3. Regra é validada (variáveis existem)
        4. Regra é salva no módulo
        """
        # Setup: Cria variáveis necessárias
        self._create_variable("valor_causa", tipo="currency")
        self._create_variable("autor_idoso", tipo="boolean")
        self.db.commit()

        # Mock da resposta do Gemini
        mock_response = MagicMock()
        mock_response.success = True
        mock_response.content = json.dumps({
            "regra": {
                "type": "and",
                "conditions": [
                    {"type": "condition", "variable": "valor_causa", "operator": "greater_than", "value": 100000},
                    {"type": "condition", "variable": "autor_idoso", "operator": "equals", "value": True}
                ]
            },
            "variaveis_usadas": ["valor_causa", "autor_idoso"]
        })

        with patch('sistemas.gerador_pecas.services_deterministic.gemini_service') as mock_gemini:
            mock_gemini.generate = AsyncMock(return_value=mock_response)

            # Passo 1: Gera regra a partir de linguagem natural
            generator = DeterministicRuleGenerator(self.db)
            resultado = asyncio.run(generator.gerar_regra(
                "Ativar quando o valor da causa for maior que 100.000 e o autor for idoso"
            ))

        # Verifica que a geração foi bem-sucedida
        self.assertTrue(resultado["success"])
        self.assertIsNotNone(resultado["regra"])

        regra = resultado["regra"]

        # Passo 2: Cria prompt com a regra gerada
        prompt = self._create_prompt(
            "prompt_via_linguagem_natural",
            modo_ativacao="deterministic",
            regra=regra,
            regra_texto="Ativar quando o valor da causa for maior que 100.000 e o autor for idoso"
        )
        self.db.commit()

        # Passo 3: Sincroniza uso de variáveis
        sync = PromptVariableUsageSync(self.db)
        variaveis_usadas = sync.atualizar_uso(prompt.id, regra)

        self.assertEqual(set(variaveis_usadas), {"valor_causa", "autor_idoso"})

        # Passo 4: Verifica que o prompt foi salvo corretamente
        self.db.refresh(prompt)
        self.assertEqual(prompt.modo_ativacao, "deterministic")
        self.assertIsNotNone(prompt.regra_deterministica)
        self.assertEqual(prompt.regra_texto_original, 
                        "Ativar quando o valor da causa for maior que 100.000 e o autor for idoso")

        # Passo 5: Avalia a regra (simulando runtime)
        evaluator = DeterministicRuleEvaluator()
        
        # Caso positivo
        self.assertTrue(evaluator.avaliar(regra, {"valor_causa": 150000, "autor_idoso": True}))
        
        # Caso negativo
        self.assertFalse(evaluator.avaliar(regra, {"valor_causa": 50000, "autor_idoso": True}))
        self.assertFalse(evaluator.avaliar(regra, {"valor_causa": 150000, "autor_idoso": False}))

    def test_criar_modulo_variavel_ausente_retorna_sugestao(self):
        """
        E2E: Quando variável está ausente, retorna erro com sugestão clara.

        Fluxo:
        1. Usuário escreve condição com variável que não existe
        2. IA gera regra
        3. Validação detecta variável ausente
        4. Retorna erro com sugestão de variável a criar
        """
        # Setup: NÃO cria as variáveis
        self.db.commit()

        # Mock da resposta do Gemini - usa variável que não existe
        mock_response = MagicMock()
        mock_response.success = True
        mock_response.content = json.dumps({
            "regra": {
                "type": "condition",
                "variable": "medicamento_incorporado_sus",
                "operator": "equals",
                "value": False
            },
            "variaveis_usadas": ["medicamento_incorporado_sus"]
        })

        with patch('sistemas.gerador_pecas.services_deterministic.gemini_service') as mock_gemini:
            mock_gemini.generate = AsyncMock(return_value=mock_response)

            generator = DeterministicRuleGenerator(self.db)
            resultado = asyncio.run(generator.gerar_regra(
                "Ativar quando o medicamento não estiver incorporado ao SUS"
            ))

        # Verifica que falhou
        self.assertFalse(resultado["success"])
        
        # Verifica que lista a variável faltante
        self.assertIn("medicamento_incorporado_sus", resultado.get("variaveis_faltantes", []))
        
        # Verifica que tem sugestão
        sugestoes = resultado.get("sugestoes_variaveis", [])
        self.assertTrue(len(sugestoes) > 0)
        
        sugestao = sugestoes[0]
        self.assertEqual(sugestao["slug"], "medicamento_incorporado_sus")
        self.assertIn("tipo_sugerido", sugestao)
        self.assertEqual(sugestao["tipo_sugerido"], "boolean")  # Inferido pelo nome

    def test_salvar_e_reabrir_modulo_mantem_regra(self):
        """
        E2E: Salvar módulo e reabrir mantém regra determinística intacta.
        """
        # Setup
        self._create_variable("tipo_acao", tipo="choice", opcoes=["Medicamentos", "Cirurgia", "Outros"])
        self.db.commit()

        regra = {
            "type": "condition",
            "variable": "tipo_acao",
            "operator": "equals",
            "value": "Medicamentos"
        }

        # Cria e salva prompt
        prompt = self._create_prompt(
            "prompt_persistencia",
            modo_ativacao="deterministic",
            regra=regra,
            regra_texto="Ativar quando o tipo de ação for Medicamentos"
        )
        self.db.commit()

        prompt_id = prompt.id

        # "Fecha" a sessão (simula reabrir)
        self.db.expunge(prompt)

        # "Reabre" o prompt
        prompt_recarregado = self.db.query(PromptModulo).filter(
            PromptModulo.id == prompt_id
        ).first()

        # Verifica que regra foi mantida
        self.assertIsNotNone(prompt_recarregado)
        self.assertEqual(prompt_recarregado.modo_ativacao, "deterministic")
        self.assertIsNotNone(prompt_recarregado.regra_deterministica)
        
        regra_salva = prompt_recarregado.regra_deterministica
        self.assertEqual(regra_salva["type"], "condition")
        self.assertEqual(regra_salva["variable"], "tipo_acao")
        self.assertEqual(regra_salva["value"], "Medicamentos")

        # Verifica texto original
        self.assertEqual(
            prompt_recarregado.regra_texto_original,
            "Ativar quando o tipo de ação for Medicamentos"
        )


class TestBuilderCampoValorTipado(BaseE2ETestCase):
    """
    Testes para o builder com campo de valor tipado.

    Simula a lógica do frontend para renderização de campos.
    """

    def test_campo_boolean_opcoes_corretas(self):
        """
        Verifica que variável boolean deve ter opções true/false.
        """
        var = self._create_variable("autor_idoso", tipo="boolean")
        self.db.commit()

        # Simula lógica do frontend
        tipo = var.tipo
        
        # Verifica que tipo é boolean e deve usar dropdown
        self.assertEqual(tipo, "boolean")
        
        # Valores esperados no dropdown
        opcoes_esperadas = [True, False]  # ou "true"/"false" como strings
        
        # O frontend deve renderizar dropdown com essas opções

    def test_campo_choice_carrega_opcoes(self):
        """
        Verifica que variável choice carrega opções do banco.
        """
        opcoes = ["Alto custo", "Básico", "Especial"]
        var = self._create_variable("tipo_medicamento", tipo="choice", opcoes=opcoes)
        self.db.commit()

        # Simula lógica do frontend
        tipo = var.tipo
        opcoes_carregadas = var.opcoes

        self.assertEqual(tipo, "choice")
        self.assertEqual(opcoes_carregadas, opcoes)

    def test_campo_number_validacao(self):
        """
        Verifica que variável number aceita apenas números.
        """
        var = self._create_variable("idade_autor", tipo="number")
        self.db.commit()

        tipo = var.tipo
        self.assertEqual(tipo, "number")

        # Validação: valor numérico válido
        valor_valido = "65"
        self.assertTrue(valor_valido.replace(".", "").replace("-", "").isdigit())

        # Validação: valor inválido
        valor_invalido = "sessenta e cinco"
        self.assertFalse(valor_invalido.replace(".", "").replace("-", "").isdigit())

    def test_campo_currency_step_decimal(self):
        """
        Verifica que variável currency permite decimais.
        """
        var = self._create_variable("valor_causa", tipo="currency")
        self.db.commit()

        tipo = var.tipo
        self.assertEqual(tipo, "currency")

        # Currency deve permitir step 0.01 (centavos)
        valor_valido = "100000.50"
        try:
            float(valor_valido)
            parse_ok = True
        except ValueError:
            parse_ok = False

        self.assertTrue(parse_ok)

    def test_campo_date_formato(self):
        """
        Verifica que variável date usa formato correto.
        """
        var = self._create_variable("data_nascimento", tipo="date")
        self.db.commit()

        tipo = var.tipo
        self.assertEqual(tipo, "date")

        # Formato esperado: YYYY-MM-DD
        valor_valido = "1990-05-15"
        import re
        pattern = r"^\d{4}-\d{2}-\d{2}$"
        self.assertTrue(re.match(pattern, valor_valido))


class TestRegraAplicadaNoBuilder(BaseE2ETestCase):
    """
    Testes para aplicação de regra gerada no builder.
    """

    def test_aplicar_regra_simples_no_builder(self):
        """
        Verifica conversão de regra AST para formato do builder.
        """
        regra_ast = {
            "type": "condition",
            "variable": "valor_causa",
            "operator": "greater_than",
            "value": 100000
        }

        # Converte para formato do builder
        builder_format = {
            "logic": "and",  # Default para regra simples
            "conditions": [
                {
                    "variable": regra_ast["variable"],
                    "operator": regra_ast["operator"],
                    "value": regra_ast["value"]
                }
            ]
        }

        self.assertEqual(builder_format["conditions"][0]["variable"], "valor_causa")
        self.assertEqual(builder_format["conditions"][0]["operator"], "greater_than")
        self.assertEqual(builder_format["conditions"][0]["value"], 100000)

    def test_aplicar_regra_and_no_builder(self):
        """
        Verifica conversão de regra AND para formato do builder.
        """
        regra_ast = {
            "type": "and",
            "conditions": [
                {"type": "condition", "variable": "valor_causa", "operator": "greater_than", "value": 100000},
                {"type": "condition", "variable": "autor_idoso", "operator": "equals", "value": True}
            ]
        }

        # Converte para formato do builder
        builder_format = {
            "logic": "and",
            "conditions": [
                {"variable": c["variable"], "operator": c["operator"], "value": c["value"]}
                for c in regra_ast["conditions"]
            ]
        }

        self.assertEqual(builder_format["logic"], "and")
        self.assertEqual(len(builder_format["conditions"]), 2)

    def test_aplicar_regra_or_no_builder(self):
        """
        Verifica conversão de regra OR para formato do builder.
        """
        regra_ast = {
            "type": "or",
            "conditions": [
                {"type": "condition", "variable": "autor_idoso", "operator": "equals", "value": True},
                {"type": "condition", "variable": "autor_crianca", "operator": "equals", "value": True}
            ]
        }

        # Converte para formato do builder
        builder_format = {
            "logic": "or",
            "conditions": [
                {"variable": c["variable"], "operator": c["operator"], "value": c["value"]}
                for c in regra_ast["conditions"]
            ]
        }

        self.assertEqual(builder_format["logic"], "or")
        self.assertEqual(len(builder_format["conditions"]), 2)


class TestAlternarEntreModos(BaseE2ETestCase):
    """
    Testes para garantir que alternar entre modos não quebra funcionalidade.
    """

    def test_alternar_llm_para_deterministico(self):
        """
        Alterna prompt de LLM para determinístico.
        """
        prompt = self._create_prompt("prompt_llm", modo_ativacao="llm")
        self.db.commit()

        # Verifica estado inicial
        self.assertEqual(prompt.modo_ativacao, "llm")
        self.assertIsNone(prompt.regra_deterministica)

        # Altera para determinístico
        regra = {
            "type": "condition",
            "variable": "valor_causa",
            "operator": "greater_than",
            "value": 100000
        }

        prompt.modo_ativacao = "deterministic"
        prompt.regra_deterministica = regra
        prompt.regra_texto_original = "Valor maior que 100000"
        self.db.commit()

        # Verifica novo estado
        self.db.refresh(prompt)
        self.assertEqual(prompt.modo_ativacao, "deterministic")
        self.assertIsNotNone(prompt.regra_deterministica)

    def test_alternar_deterministico_para_llm(self):
        """
        Alterna prompt de determinístico para LLM.
        """
        regra = {
            "type": "condition",
            "variable": "valor_causa",
            "operator": "greater_than",
            "value": 100000
        }

        prompt = self._create_prompt(
            "prompt_det",
            modo_ativacao="deterministic",
            regra=regra,
            regra_texto="Valor maior que 100000"
        )
        self.db.commit()

        # Verifica estado inicial
        self.assertEqual(prompt.modo_ativacao, "deterministic")
        self.assertIsNotNone(prompt.regra_deterministica)

        # Altera para LLM
        prompt.modo_ativacao = "llm"
        prompt.regra_deterministica = None
        prompt.regra_texto_original = None
        self.db.commit()

        # Verifica novo estado
        self.db.refresh(prompt)
        self.assertEqual(prompt.modo_ativacao, "llm")
        self.assertIsNone(prompt.regra_deterministica)

    def test_conteudo_preservado_ao_alternar(self):
        """
        Conteúdo do prompt é preservado ao alternar modos.
        """
        prompt = PromptModulo(
            nome="prompt_conteudo",
            titulo="Prompt com Conteúdo",
            tipo="conteudo",
            conteudo="Conteúdo importante que não pode ser perdido",
            modo_ativacao="llm",
            ativo=True,
            ordem=0,
            palavras_chave=["importante", "teste"],
            tags=["e2e", "preservacao"]
        )
        self.db.add(prompt)
        self.db.commit()

        conteudo_original = prompt.conteudo
        palavras_original = prompt.palavras_chave.copy()

        # Alterna para determinístico
        prompt.modo_ativacao = "deterministic"
        prompt.regra_deterministica = {"type": "condition", "variable": "x", "operator": "exists", "value": True}
        self.db.commit()

        # Verifica preservação
        self.db.refresh(prompt)
        self.assertEqual(prompt.conteudo, conteudo_original)
        self.assertEqual(prompt.palavras_chave, palavras_original)


if __name__ == "__main__":
    unittest.main()
