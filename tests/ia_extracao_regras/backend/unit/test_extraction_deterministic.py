# tests/test_extraction_deterministic.py
"""
Testes automatizados para o sistema de extração e regras determinísticas.

Este módulo cobre:
- Geração de schema por IA (com mock)
- Validação de schemas
- Geração de regras determinísticas
- Avaliação de regras no runtime
- Sincronização de uso de variáveis
- Compatibilidade com modo legado
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.connection import Base

# Import all models to ensure tables are created
from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON
from sistemas.gerador_pecas.models_extraction import (
    ExtractionQuestion, ExtractionModel, ExtractionVariable,
    PromptVariableUsage, PromptActivationLog, ExtractionQuestionType
)
from sistemas.gerador_pecas.services_extraction import (
    ExtractionSchemaGenerator, ExtractionSchemaValidator
)
from sistemas.gerador_pecas.services_deterministic import (
    DeterministicRuleGenerator, DeterministicRuleEvaluator,
    PromptVariableUsageSync, avaliar_ativacao_prompt
)
from admin.models_prompts import PromptModulo
from admin.models_prompt_groups import PromptGroup, PromptSubgroup
from auth.models import User


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

    def _create_user(self, username="test_user", role="user"):
        """Cria um usuário de teste."""
        user = User(
            username=username,
            full_name=username,
            email=None,
            hashed_password="x",
            role=role,
        )
        self.db.add(user)
        self.db.flush()
        return user

    def _create_variable(self, slug, label=None, tipo="text", ativo=True, **kwargs):
        """Cria uma variável de extração de teste."""
        variable = ExtractionVariable(
            slug=slug,
            label=label or slug.replace("_", " ").title(),
            tipo=tipo,
            ativo=ativo,
            **kwargs
        )
        self.db.add(variable)
        self.db.flush()
        return variable

    def _create_prompt(self, nome="test_prompt", modo_ativacao="llm", **kwargs):
        """Cria um prompt de teste."""
        prompt = PromptModulo(
            nome=nome,
            titulo=kwargs.get("titulo", nome),
            tipo=kwargs.get("tipo", "conteudo"),
            conteudo=kwargs.get("conteudo", "Conteúdo de teste"),
            modo_ativacao=modo_ativacao,
            ativo=kwargs.get("ativo", True),
            ordem=kwargs.get("ordem", 0),
            palavras_chave=kwargs.get("palavras_chave", []),
            tags=kwargs.get("tags", []),
            **{k: v for k, v in kwargs.items() if k not in ["titulo", "tipo", "conteudo", "ativo", "ordem", "palavras_chave", "tags"]}
        )
        self.db.add(prompt)
        self.db.flush()
        return prompt


class TestExtractionSchemaValidator(BaseTestCase):
    """Testes para o validador de schemas de extração."""

    def test_schema_valido_simples(self):
        """Testa validação de schema válido com tipos básicos."""
        schema = {
            "nome_autor": {"type": "text", "description": "Nome do autor"},
            "valor_causa": {"type": "currency", "description": "Valor da causa"},
            "data_ajuizamento": {"type": "date", "description": "Data de ajuizamento"}
        }

        resultado = ExtractionSchemaValidator.validar_schema(schema)

        self.assertTrue(resultado["valid"])
        self.assertEqual(len(resultado["errors"]), 0)

    def test_schema_valido_com_choice(self):
        """Testa validação de schema com campo choice."""
        schema = {
            "tipo_acao": {
                "type": "choice",
                "description": "Tipo da ação",
                "options": ["Mandado de Segurança", "Ação Civil Pública", "Ação Ordinária"]
            }
        }

        resultado = ExtractionSchemaValidator.validar_schema(schema)

        self.assertTrue(resultado["valid"])

    def test_schema_invalido_vazio(self):
        """Testa que schema vazio é rejeitado."""
        resultado = ExtractionSchemaValidator.validar_schema({})

        self.assertFalse(resultado["valid"])
        self.assertIn("Schema não pode estar vazio", resultado["errors"])

    def test_schema_invalido_tipo_errado(self):
        """Testa que tipo inválido é rejeitado."""
        schema = {
            "campo": {"type": "tipo_invalido", "description": "Campo inválido"}
        }

        resultado = ExtractionSchemaValidator.validar_schema(schema)

        self.assertFalse(resultado["valid"])
        self.assertTrue(any("inválido" in e.lower() for e in resultado["errors"]))

    def test_schema_invalido_sem_tipo(self):
        """Testa que variável sem tipo é rejeitada."""
        schema = {
            "campo": {"description": "Campo sem tipo"}
        }

        resultado = ExtractionSchemaValidator.validar_schema(schema)

        self.assertFalse(resultado["valid"])
        self.assertTrue(any("não tem tipo" in e for e in resultado["errors"]))

    def test_schema_invalido_choice_sem_opcoes(self):
        """Testa que choice sem opções é rejeitado."""
        schema = {
            "campo": {"type": "choice", "description": "Choice sem opções"}
        }

        resultado = ExtractionSchemaValidator.validar_schema(schema)

        self.assertFalse(resultado["valid"])
        self.assertTrue(any("pelo menos 2 opções" in e for e in resultado["errors"]))

    def test_aviso_nome_fora_padrao(self):
        """Testa que nome fora do padrão snake_case gera aviso."""
        schema = {
            "NomeComMaiusculas": {"type": "text", "description": "Nome inválido"}
        }

        resultado = ExtractionSchemaValidator.validar_schema(schema)

        # Schema é válido mas tem aviso
        self.assertTrue(resultado["valid"])
        self.assertTrue(any("snake_case" in w for w in resultado["warnings"]))


class TestDeterministicRuleEvaluator(BaseTestCase):
    """Testes para o avaliador de regras determinísticas."""

    def setUp(self):
        super().setUp()
        self.evaluator = DeterministicRuleEvaluator()

    def test_equals_string_case_insensitive(self):
        """Testa operador equals com strings (case insensitive)."""
        regra = {
            "type": "condition",
            "variable": "tipo_acao",
            "operator": "equals",
            "value": "medicamentos"
        }

        self.assertTrue(self.evaluator.avaliar(regra, {"tipo_acao": "Medicamentos"}))
        self.assertTrue(self.evaluator.avaliar(regra, {"tipo_acao": "MEDICAMENTOS"}))
        self.assertTrue(self.evaluator.avaliar(regra, {"tipo_acao": "  medicamentos  "}))
        self.assertFalse(self.evaluator.avaliar(regra, {"tipo_acao": "Cirurgia"}))

    def test_equals_boolean(self):
        """Testa operador equals com booleanos."""
        regra = {
            "type": "condition",
            "variable": "autor_idoso",
            "operator": "equals",
            "value": True
        }

        self.assertTrue(self.evaluator.avaliar(regra, {"autor_idoso": True}))
        self.assertTrue(self.evaluator.avaliar(regra, {"autor_idoso": "sim"}))
        self.assertTrue(self.evaluator.avaliar(regra, {"autor_idoso": "true"}))
        self.assertFalse(self.evaluator.avaliar(regra, {"autor_idoso": False}))
        self.assertFalse(self.evaluator.avaliar(regra, {"autor_idoso": "não"}))

    def test_not_equals(self):
        """Testa operador not_equals."""
        regra = {
            "type": "condition",
            "variable": "status",
            "operator": "not_equals",
            "value": "arquivado"
        }

        self.assertTrue(self.evaluator.avaliar(regra, {"status": "ativo"}))
        self.assertFalse(self.evaluator.avaliar(regra, {"status": "arquivado"}))

    def test_contains(self):
        """Testa operador contains."""
        regra = {
            "type": "condition",
            "variable": "medicamento",
            "operator": "contains",
            "value": "insulina"
        }

        self.assertTrue(self.evaluator.avaliar(regra, {"medicamento": "Insulina NPH"}))
        self.assertTrue(self.evaluator.avaliar(regra, {"medicamento": "Caneta de INSULINA"}))
        self.assertFalse(self.evaluator.avaliar(regra, {"medicamento": "Ozempic"}))
        self.assertFalse(self.evaluator.avaliar(regra, {"medicamento": None}))

    def test_not_contains(self):
        """Testa operador not_contains."""
        regra = {
            "type": "condition",
            "variable": "texto",
            "operator": "not_contains",
            "value": "urgente"
        }

        self.assertTrue(self.evaluator.avaliar(regra, {"texto": "Processo normal"}))
        self.assertTrue(self.evaluator.avaliar(regra, {"texto": None}))
        self.assertFalse(self.evaluator.avaliar(regra, {"texto": "URGENTE: ação"}))

    def test_starts_with(self):
        """Testa operador starts_with."""
        regra = {
            "type": "condition",
            "variable": "processo",
            "operator": "starts_with",
            "value": "0001234"
        }

        self.assertTrue(self.evaluator.avaliar(regra, {"processo": "0001234-56.2024.8.12.0001"}))
        self.assertFalse(self.evaluator.avaliar(regra, {"processo": "9999999-00.2024.8.12.0001"}))

    def test_ends_with(self):
        """Testa operador ends_with."""
        regra = {
            "type": "condition",
            "variable": "processo",
            "operator": "ends_with",
            "value": "0001"
        }

        self.assertTrue(self.evaluator.avaliar(regra, {"processo": "0001234-56.2024.8.12.0001"}))
        self.assertFalse(self.evaluator.avaliar(regra, {"processo": "0001234-56.2024.8.12.0002"}))

    def test_greater_than(self):
        """Testa operador greater_than com números."""
        regra = {
            "type": "condition",
            "variable": "valor_causa",
            "operator": "greater_than",
            "value": 100000
        }

        self.assertTrue(self.evaluator.avaliar(regra, {"valor_causa": 150000}))
        self.assertTrue(self.evaluator.avaliar(regra, {"valor_causa": "200000.50"}))
        self.assertTrue(self.evaluator.avaliar(regra, {"valor_causa": "R$ 250.000,00"}))
        self.assertFalse(self.evaluator.avaliar(regra, {"valor_causa": 100000}))
        self.assertFalse(self.evaluator.avaliar(regra, {"valor_causa": 50000}))

    def test_less_than(self):
        """Testa operador less_than."""
        regra = {
            "type": "condition",
            "variable": "idade",
            "operator": "less_than",
            "value": 18
        }

        self.assertTrue(self.evaluator.avaliar(regra, {"idade": 10}))
        self.assertFalse(self.evaluator.avaliar(regra, {"idade": 18}))
        self.assertFalse(self.evaluator.avaliar(regra, {"idade": 25}))

    def test_greater_or_equal(self):
        """Testa operador greater_or_equal."""
        regra = {
            "type": "condition",
            "variable": "idade",
            "operator": "greater_or_equal",
            "value": 60
        }

        self.assertTrue(self.evaluator.avaliar(regra, {"idade": 60}))
        self.assertTrue(self.evaluator.avaliar(regra, {"idade": 65}))
        self.assertFalse(self.evaluator.avaliar(regra, {"idade": 59}))

    def test_less_or_equal(self):
        """Testa operador less_or_equal."""
        regra = {
            "type": "condition",
            "variable": "valor",
            "operator": "less_or_equal",
            "value": 1000
        }

        self.assertTrue(self.evaluator.avaliar(regra, {"valor": 1000}))
        self.assertTrue(self.evaluator.avaliar(regra, {"valor": 500}))
        self.assertFalse(self.evaluator.avaliar(regra, {"valor": 1001}))

    def test_is_empty(self):
        """Testa operador is_empty."""
        regra = {
            "type": "condition",
            "variable": "campo",
            "operator": "is_empty",
            "value": True
        }

        self.assertTrue(self.evaluator.avaliar(regra, {"campo": None}))
        self.assertTrue(self.evaluator.avaliar(regra, {"campo": ""}))
        self.assertTrue(self.evaluator.avaliar(regra, {"campo": []}))
        self.assertTrue(self.evaluator.avaliar(regra, {}))  # Variável não existe
        self.assertFalse(self.evaluator.avaliar(regra, {"campo": "valor"}))

    def test_is_not_empty(self):
        """Testa operador is_not_empty."""
        regra = {
            "type": "condition",
            "variable": "campo",
            "operator": "is_not_empty",
            "value": True
        }

        self.assertTrue(self.evaluator.avaliar(regra, {"campo": "valor"}))
        self.assertTrue(self.evaluator.avaliar(regra, {"campo": ["item"]}))
        self.assertFalse(self.evaluator.avaliar(regra, {"campo": None}))
        self.assertFalse(self.evaluator.avaliar(regra, {"campo": ""}))

    def test_in_list(self):
        """Testa operador in_list."""
        regra = {
            "type": "condition",
            "variable": "estado",
            "operator": "in_list",
            "value": ["MS", "MT", "GO"]
        }

        self.assertTrue(self.evaluator.avaliar(regra, {"estado": "MS"}))
        self.assertTrue(self.evaluator.avaliar(regra, {"estado": "MT"}))
        self.assertFalse(self.evaluator.avaliar(regra, {"estado": "SP"}))

    def test_not_in_list(self):
        """Testa operador not_in_list."""
        regra = {
            "type": "condition",
            "variable": "estado",
            "operator": "not_in_list",
            "value": ["SP", "RJ"]
        }

        self.assertTrue(self.evaluator.avaliar(regra, {"estado": "MS"}))
        self.assertFalse(self.evaluator.avaliar(regra, {"estado": "SP"}))

    def test_matches_regex(self):
        """Testa operador matches_regex."""
        regra = {
            "type": "condition",
            "variable": "cpf",
            "operator": "matches_regex",
            "value": r"^\d{3}\.\d{3}\.\d{3}-\d{2}$"
        }

        self.assertTrue(self.evaluator.avaliar(regra, {"cpf": "123.456.789-00"}))
        self.assertFalse(self.evaluator.avaliar(regra, {"cpf": "12345678900"}))

    def test_and_operator(self):
        """Testa operador lógico AND."""
        regra = {
            "type": "and",
            "conditions": [
                {"type": "condition", "variable": "autor_idoso", "operator": "equals", "value": True},
                {"type": "condition", "variable": "valor_causa", "operator": "greater_than", "value": 50000}
            ]
        }

        self.assertTrue(self.evaluator.avaliar(regra, {"autor_idoso": True, "valor_causa": 100000}))
        self.assertFalse(self.evaluator.avaliar(regra, {"autor_idoso": True, "valor_causa": 30000}))
        self.assertFalse(self.evaluator.avaliar(regra, {"autor_idoso": False, "valor_causa": 100000}))
        self.assertFalse(self.evaluator.avaliar(regra, {"autor_idoso": False, "valor_causa": 30000}))

    def test_or_operator(self):
        """Testa operador lógico OR."""
        regra = {
            "type": "or",
            "conditions": [
                {"type": "condition", "variable": "autor_idoso", "operator": "equals", "value": True},
                {"type": "condition", "variable": "autor_crianca", "operator": "equals", "value": True}
            ]
        }

        self.assertTrue(self.evaluator.avaliar(regra, {"autor_idoso": True, "autor_crianca": False}))
        self.assertTrue(self.evaluator.avaliar(regra, {"autor_idoso": False, "autor_crianca": True}))
        self.assertTrue(self.evaluator.avaliar(regra, {"autor_idoso": True, "autor_crianca": True}))
        self.assertFalse(self.evaluator.avaliar(regra, {"autor_idoso": False, "autor_crianca": False}))

    def test_not_operator(self):
        """Testa operador lógico NOT."""
        regra = {
            "type": "not",
            "conditions": [
                {"type": "condition", "variable": "status", "operator": "equals", "value": "arquivado"}
            ]
        }

        self.assertTrue(self.evaluator.avaliar(regra, {"status": "ativo"}))
        self.assertFalse(self.evaluator.avaliar(regra, {"status": "arquivado"}))

    def test_nested_conditions(self):
        """Testa condições aninhadas (AND/OR combinados)."""
        # (autor_idoso OR autor_crianca) AND valor_causa > 50000
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

        # Idoso + valor alto = True
        self.assertTrue(self.evaluator.avaliar(regra, {"autor_idoso": True, "autor_crianca": False, "valor_causa": 100000}))

        # Criança + valor alto = True
        self.assertTrue(self.evaluator.avaliar(regra, {"autor_idoso": False, "autor_crianca": True, "valor_causa": 100000}))

        # Idoso + valor baixo = False
        self.assertFalse(self.evaluator.avaliar(regra, {"autor_idoso": True, "autor_crianca": False, "valor_causa": 30000}))

        # Nenhum + valor alto = False
        self.assertFalse(self.evaluator.avaliar(regra, {"autor_idoso": False, "autor_crianca": False, "valor_causa": 100000}))

    def test_complex_real_world_rule(self):
        """Testa regra complexa de caso real."""
        # Regra: Medicamento é de alto custo E (não está na RENAME OU valor > 100000)
        regra = {
            "type": "and",
            "conditions": [
                {"type": "condition", "variable": "medicamento_alto_custo", "operator": "equals", "value": True},
                {
                    "type": "or",
                    "conditions": [
                        {"type": "condition", "variable": "medicamento_rename", "operator": "equals", "value": False},
                        {"type": "condition", "variable": "valor_tratamento", "operator": "greater_than", "value": 100000}
                    ]
                }
            ]
        }

        # Alto custo + não RENAME = True
        self.assertTrue(self.evaluator.avaliar(regra, {
            "medicamento_alto_custo": True,
            "medicamento_rename": False,
            "valor_tratamento": 50000
        }))

        # Alto custo + RENAME + valor alto = True
        self.assertTrue(self.evaluator.avaliar(regra, {
            "medicamento_alto_custo": True,
            "medicamento_rename": True,
            "valor_tratamento": 150000
        }))

        # Alto custo + RENAME + valor baixo = False
        self.assertFalse(self.evaluator.avaliar(regra, {
            "medicamento_alto_custo": True,
            "medicamento_rename": True,
            "valor_tratamento": 50000
        }))

        # Não é alto custo = False
        self.assertFalse(self.evaluator.avaliar(regra, {
            "medicamento_alto_custo": False,
            "medicamento_rename": False,
            "valor_tratamento": 200000
        }))


class TestPromptVariableUsageSync(BaseTestCase):
    """Testes para sincronização de uso de variáveis em prompts."""

    def test_atualizar_uso_regra_simples(self):
        """Testa sincronização com regra simples."""
        prompt = self._create_prompt("prompt_teste", modo_ativacao="deterministic")
        self._create_variable("valor_causa", tipo="currency")
        self.db.commit()

        regra = {
            "type": "condition",
            "variable": "valor_causa",
            "operator": "greater_than",
            "value": 100000
        }

        sync = PromptVariableUsageSync(self.db)
        variaveis = sync.atualizar_uso(prompt.id, regra)

        self.assertEqual(variaveis, ["valor_causa"])

        # Verifica se foi persistido
        usage = self.db.query(PromptVariableUsage).filter(
            PromptVariableUsage.prompt_id == prompt.id
        ).all()
        self.assertEqual(len(usage), 1)
        self.assertEqual(usage[0].variable_slug, "valor_causa")

    def test_atualizar_uso_regra_composta(self):
        """Testa sincronização com regra AND/OR."""
        prompt = self._create_prompt("prompt_teste", modo_ativacao="deterministic")
        self._create_variable("autor_idoso", tipo="boolean")
        self._create_variable("autor_crianca", tipo="boolean")
        self._create_variable("valor_causa", tipo="currency")
        self.db.commit()

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

        sync = PromptVariableUsageSync(self.db)
        variaveis = sync.atualizar_uso(prompt.id, regra)

        self.assertEqual(set(variaveis), {"autor_idoso", "autor_crianca", "valor_causa"})

    def test_atualizar_uso_remove_anteriores(self):
        """Testa que atualização remove usos anteriores."""
        prompt = self._create_prompt("prompt_teste", modo_ativacao="deterministic")
        self._create_variable("var1", tipo="text")
        self._create_variable("var2", tipo="text")
        self.db.commit()

        sync = PromptVariableUsageSync(self.db)

        # Primeira regra usa var1
        regra1 = {"type": "condition", "variable": "var1", "operator": "is_not_empty", "value": True}
        sync.atualizar_uso(prompt.id, regra1)

        # Segunda regra usa var2
        regra2 = {"type": "condition", "variable": "var2", "operator": "is_not_empty", "value": True}
        variaveis = sync.atualizar_uso(prompt.id, regra2)

        # Deve ter apenas var2
        self.assertEqual(variaveis, ["var2"])

        usage = self.db.query(PromptVariableUsage).filter(
            PromptVariableUsage.prompt_id == prompt.id
        ).all()
        self.assertEqual(len(usage), 1)
        self.assertEqual(usage[0].variable_slug, "var2")

    def test_atualizar_uso_regra_none(self):
        """Testa que passar regra None limpa os usos."""
        prompt = self._create_prompt("prompt_teste", modo_ativacao="deterministic")
        self._create_variable("var1", tipo="text")
        self.db.commit()

        sync = PromptVariableUsageSync(self.db)

        # Adiciona uso
        regra = {"type": "condition", "variable": "var1", "operator": "is_not_empty", "value": True}
        sync.atualizar_uso(prompt.id, regra)

        # Limpa passando None
        variaveis = sync.atualizar_uso(prompt.id, None)

        self.assertEqual(variaveis, [])

        usage = self.db.query(PromptVariableUsage).filter(
            PromptVariableUsage.prompt_id == prompt.id
        ).all()
        self.assertEqual(len(usage), 0)

    def test_obter_prompts_por_variavel(self):
        """Testa busca de prompts que usam uma variável."""
        prompt1 = self._create_prompt("prompt1", modo_ativacao="deterministic")
        prompt2 = self._create_prompt("prompt2", modo_ativacao="deterministic")
        prompt3 = self._create_prompt("prompt3", modo_ativacao="llm")

        self._create_variable("valor_causa", tipo="currency")
        self._create_variable("tipo_acao", tipo="text")
        self.db.commit()

        sync = PromptVariableUsageSync(self.db)

        # prompt1 usa valor_causa
        sync.atualizar_uso(prompt1.id, {
            "type": "condition", "variable": "valor_causa", "operator": "greater_than", "value": 100000
        })

        # prompt2 usa valor_causa e tipo_acao
        sync.atualizar_uso(prompt2.id, {
            "type": "and",
            "conditions": [
                {"type": "condition", "variable": "valor_causa", "operator": "greater_than", "value": 50000},
                {"type": "condition", "variable": "tipo_acao", "operator": "equals", "value": "medicamentos"}
            ]
        })

        # Busca prompts que usam valor_causa
        prompts = sync.obter_prompts_por_variavel("valor_causa")

        self.assertEqual(len(prompts), 2)
        nomes = {p["nome"] for p in prompts}
        self.assertEqual(nomes, {"prompt1", "prompt2"})


class TestAvaliarAtivacaoPrompt(BaseTestCase):
    """Testes para a função de conveniência avaliar_ativacao_prompt."""

    def test_modo_deterministico_ativa(self):
        """Testa ativação em modo determinístico quando regra é satisfeita."""
        prompt = self._create_prompt("teste", modo_ativacao="deterministic")
        self.db.commit()

        regra = {
            "type": "condition",
            "variable": "valor_causa",
            "operator": "greater_than",
            "value": 100000
        }

        resultado = avaliar_ativacao_prompt(
            prompt_id=prompt.id,
            modo_ativacao="deterministic",
            regra_deterministica=regra,
            dados_extracao={"valor_causa": 150000},
            db=self.db
        )

        self.assertTrue(resultado["ativar"])
        self.assertEqual(resultado["modo"], "deterministic")

    def test_modo_deterministico_nao_ativa(self):
        """Testa que modo determinístico não ativa quando regra não é satisfeita."""
        prompt = self._create_prompt("teste", modo_ativacao="deterministic")
        self.db.commit()

        regra = {
            "type": "condition",
            "variable": "valor_causa",
            "operator": "greater_than",
            "value": 100000
        }

        resultado = avaliar_ativacao_prompt(
            prompt_id=prompt.id,
            modo_ativacao="deterministic",
            regra_deterministica=regra,
            dados_extracao={"valor_causa": 50000},
            db=self.db
        )

        self.assertFalse(resultado["ativar"])
        self.assertEqual(resultado["modo"], "deterministic")

    def test_modo_llm_retorna_none(self):
        """Testa que modo LLM retorna ativar=None (precisa chamar LLM)."""
        prompt = self._create_prompt("teste", modo_ativacao="llm")
        self.db.commit()

        resultado = avaliar_ativacao_prompt(
            prompt_id=prompt.id,
            modo_ativacao="llm",
            regra_deterministica=None,
            dados_extracao={"valor_causa": 150000},
            db=self.db
        )

        self.assertIsNone(resultado["ativar"])
        self.assertEqual(resultado["modo"], "llm")


class TestLegacyModeCompatibility(BaseTestCase):
    """Testes de compatibilidade com modo legado (manual)."""

    def test_modelo_manual_e_valido(self):
        """Testa que modelo manual é aceito pelo validador."""
        schema_manual = {
            "nome_autor": {"type": "text", "description": "Nome do autor"},
            "cpf_autor": {"type": "text", "description": "CPF do autor"},
            "valor_causa": {"type": "currency", "description": "Valor da causa"},
            "tipo_acao": {
                "type": "choice",
                "description": "Tipo da ação",
                "options": ["Medicamentos", "Cirurgia", "Outros"]
            }
        }

        resultado = ExtractionSchemaValidator.validar_schema(schema_manual)

        self.assertTrue(resultado["valid"])

    def test_prompt_modo_llm_padrao(self):
        """Testa que prompts sem modo especificado usam LLM por padrão."""
        prompt = self._create_prompt("teste_legado")
        self.db.commit()

        self.assertEqual(prompt.modo_ativacao, "llm")

    def test_prompt_pode_alternar_modos(self):
        """Testa que prompt pode alternar entre modos."""
        prompt = self._create_prompt("teste", modo_ativacao="llm")
        self.db.commit()

        # Muda para determinístico
        prompt.modo_ativacao = "deterministic"
        prompt.regra_deterministica = {
            "type": "condition",
            "variable": "valor_causa",
            "operator": "greater_than",
            "value": 100000
        }
        self.db.commit()

        self.db.refresh(prompt)
        self.assertEqual(prompt.modo_ativacao, "deterministic")

        # Volta para LLM
        prompt.modo_ativacao = "llm"
        prompt.regra_deterministica = None
        self.db.commit()

        self.db.refresh(prompt)
        self.assertEqual(prompt.modo_ativacao, "llm")


class TestExtractionSchemaGeneratorNormalization(BaseTestCase):
    """Testes para normalização de slugs no gerador de schema."""

    def test_normalizar_slug_acentos(self):
        """Testa remoção de acentos em slugs."""
        generator = ExtractionSchemaGenerator(self.db)

        self.assertEqual(generator._normalizar_slug("AÇÃO"), "acao")
        self.assertEqual(generator._normalizar_slug("número"), "numero")
        self.assertEqual(generator._normalizar_slug("situação_jurídica"), "situacao_juridica")
        self.assertEqual(generator._normalizar_slug("Cálculo Atuarial"), "calculo_atuarial")

    def test_normalizar_slug_espacos(self):
        """Testa conversão de espaços em underscores."""
        generator = ExtractionSchemaGenerator(self.db)

        self.assertEqual(generator._normalizar_slug("nome do autor"), "nome_do_autor")
        self.assertEqual(generator._normalizar_slug("valor da causa"), "valor_da_causa")

    def test_normalizar_slug_caracteres_especiais(self):
        """Testa remoção de caracteres especiais."""
        generator = ExtractionSchemaGenerator(self.db)

        self.assertEqual(generator._normalizar_slug("CPF/CNPJ"), "cpf_cnpj")
        self.assertEqual(generator._normalizar_slug("valor (R$)"), "valor_r")
        self.assertEqual(generator._normalizar_slug("data: início"), "data_inicio")

    def test_normalizar_slug_vazio(self):
        """Testa que slug vazio retorna 'variavel'."""
        generator = ExtractionSchemaGenerator(self.db)

        self.assertEqual(generator._normalizar_slug(""), "variavel")
        self.assertEqual(generator._normalizar_slug("   "), "variavel")


if __name__ == "__main__":
    unittest.main()
