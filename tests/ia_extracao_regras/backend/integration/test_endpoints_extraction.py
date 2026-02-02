# tests/ia_extracao_regras/backend/integration/test_endpoints_extraction.py
"""
Testes de integração para endpoints de extração.

Testa endpoints da API de extração com banco de dados em memória.
"""

import unittest
from unittest.mock import patch, AsyncMock
import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from database.connection import Base, get_db
from main import app


class TestExtractionEndpoints(unittest.TestCase):
    """Testes de integração para endpoints de extração."""

    @classmethod
    def setUpClass(cls):
        """Configura banco em memória para todos os testes."""
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False}
        )
        cls.TestingSessionLocal = sessionmaker(bind=cls.engine)

        # Importa todos os modelos para criar tabelas
        from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON
        from sistemas.gerador_pecas.models_extraction import (
            ExtractionQuestion, ExtractionModel, ExtractionVariable,
            PromptVariableUsage, PromptActivationLog
        )
        from admin.models_prompts import PromptModulo
        from admin.models_prompt_groups import PromptGroup, PromptSubgroup
        from auth.models import User

        Base.metadata.create_all(bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        """Limpa recursos."""
        Base.metadata.drop_all(bind=cls.engine)

    def setUp(self):
        """Configura sessão para cada teste."""
        self.db = self.TestingSessionLocal()

        # Override dependency
        def override_get_db():
            try:
                yield self.db
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

    def tearDown(self):
        """Limpa sessão."""
        self.db.rollback()
        self.db.close()

    def _criar_usuario_teste(self):
        """Cria usuário de teste."""
        from auth.models import User

        user = User(
            username="test_user",
            full_name="Test User",
            email="test@test.com",
            hashed_password="$2b$12$test",
            role="admin",
            is_active=True
        )
        self.db.add(user)
        self.db.commit()
        return user

    def _criar_categoria_teste(self):
        """Cria categoria de teste."""
        from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON

        categoria = CategoriaResumoJSON(
            nome="medicamentos",
            titulo="Medicamentos",
            descricao="Ações de medicamentos",
            codigos_documento=[500, 510],
            formato_json='{"tipo": "string"}'
        )
        self.db.add(categoria)
        self.db.commit()
        return categoria

    def _criar_variavel_teste(self, slug, tipo="text"):
        """Cria variável de teste."""
        from sistemas.gerador_pecas.models_extraction import ExtractionVariable

        variavel = ExtractionVariable(
            slug=slug,
            label=slug.replace("_", " ").title(),
            tipo=tipo,
            ativo=True
        )
        self.db.add(variavel)
        self.db.commit()
        return variavel

    def test_validar_schema_valido(self):
        """Testa validação de schema válido."""
        schema = {
            "nome_autor": {"type": "text", "description": "Nome do autor"},
            "valor_causa": {"type": "currency", "description": "Valor da causa"}
        }

        # Nota: este endpoint requer autenticação, então testamos o serviço diretamente
        from sistemas.gerador_pecas.services_extraction import ExtractionSchemaValidator

        resultado = ExtractionSchemaValidator.validar_schema(schema)

        self.assertTrue(resultado["valid"])
        self.assertEqual(len(resultado["errors"]), 0)

    def test_validar_schema_invalido(self):
        """Testa validação de schema inválido."""
        from sistemas.gerador_pecas.services_extraction import ExtractionSchemaValidator

        # Schema vazio
        resultado = ExtractionSchemaValidator.validar_schema({})
        self.assertFalse(resultado["valid"])

        # Schema com tipo inválido
        resultado = ExtractionSchemaValidator.validar_schema({
            "campo": {"type": "invalido", "description": "Tipo inválido"}
        })
        self.assertFalse(resultado["valid"])

    def test_criar_variavel_persistencia(self):
        """Testa persistência de variável no banco."""
        from sistemas.gerador_pecas.models_extraction import ExtractionVariable

        variavel = self._criar_variavel_teste("teste_variavel", "text")

        # Verifica se foi salva
        variavel_db = self.db.query(ExtractionVariable).filter(
            ExtractionVariable.slug == "teste_variavel"
        ).first()

        self.assertIsNotNone(variavel_db)
        self.assertEqual(variavel_db.tipo, "text")

    def test_variavel_slug_unico(self):
        """Testa que slug de variável é único."""
        from sistemas.gerador_pecas.models_extraction import ExtractionVariable
        from sqlalchemy.exc import IntegrityError

        self._criar_variavel_teste("slug_unico", "text")

        # Tenta criar outra com mesmo slug
        variavel2 = ExtractionVariable(
            slug="slug_unico",
            label="Outro Label",
            tipo="number",
            ativo=True
        )
        self.db.add(variavel2)

        with self.assertRaises(IntegrityError):
            self.db.commit()

        self.db.rollback()


class TestMigrations(unittest.TestCase):
    """Testes para verificar que migrações funcionam corretamente."""

    def test_tabelas_existem(self):
        """Testa que todas as tabelas necessárias existem."""
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False}
        )

        # Importa modelos
        from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON
        from sistemas.gerador_pecas.models_extraction import (
            ExtractionQuestion, ExtractionModel, ExtractionVariable,
            PromptVariableUsage, PromptActivationLog
        )
        from admin.models_prompts import PromptModulo
        from admin.models_prompt_groups import PromptGroup, PromptSubgroup
        from auth.models import User

        # Cria tabelas
        Base.metadata.create_all(bind=engine)

        # Verifica tabelas
        from sqlalchemy import inspect
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        tabelas_esperadas = [
            "extraction_questions",
            "extraction_models",
            "extraction_variables",
            "prompt_variable_usage",
            "prompt_activation_logs",
            "prompt_modulos",
            "users"
        ]

        for tabela in tabelas_esperadas:
            self.assertIn(tabela, tables, f"Tabela {tabela} não encontrada")

        Base.metadata.drop_all(bind=engine)

    def test_colunas_modo_ativacao(self):
        """Testa que coluna modo_ativacao existe em prompt_modulos."""
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False}
        )

        from admin.models_prompts import PromptModulo
        Base.metadata.create_all(bind=engine)

        from sqlalchemy import inspect
        inspector = inspect(engine)
        columns = [c["name"] for c in inspector.get_columns("prompt_modulos")]

        self.assertIn("modo_ativacao", columns)
        self.assertIn("regra_deterministica", columns)

        Base.metadata.drop_all(bind=engine)


class TestBulkQuestionsEndpoint(unittest.TestCase):
    """
    Testes de integração para endpoint de criação de perguntas em lote.

    Valida a regra 1:1: A IA não pode criar perguntas extras.
    """

    @classmethod
    def setUpClass(cls):
        """Configura banco em memória."""
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False}
        )
        cls.TestingSessionLocal = sessionmaker(bind=cls.engine)

        from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON
        from sistemas.gerador_pecas.models_extraction import (
            ExtractionQuestion, ExtractionModel, ExtractionVariable,
            PromptVariableUsage, PromptActivationLog
        )
        from admin.models_prompts import PromptModulo
        from admin.models_prompt_groups import PromptGroup, PromptSubgroup
        from auth.models import User

        Base.metadata.create_all(bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        """Limpa recursos."""
        Base.metadata.drop_all(bind=cls.engine)

    def setUp(self):
        """Configura sessão para cada teste."""
        self.db = self.TestingSessionLocal()

        def override_get_db():
            try:
                yield self.db
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

        # Cria dados de teste
        self.user = self._criar_usuario_teste()
        self.categoria = self._criar_categoria_teste()

    def tearDown(self):
        """Limpa sessão."""
        self.db.rollback()
        self.db.close()

    def _criar_usuario_teste(self):
        """Cria usuário de teste."""
        from auth.models import User

        user = User(
            username="bulk_test_user",
            full_name="Bulk Test User",
            email="bulk@test.com",
            hashed_password="$2b$12$test",
            role="admin",
            is_active=True
        )
        self.db.add(user)
        self.db.commit()
        return user

    def _criar_categoria_teste(self):
        """Cria categoria de teste."""
        from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON

        categoria = CategoriaResumoJSON(
            nome="bulk_test",
            titulo="Bulk Test",
            descricao="Categoria para teste de bulk",
            codigos_documento=[999],
            formato_json='{}'
        )
        self.db.add(categoria)
        self.db.commit()
        return categoria

    @patch('sistemas.gerador_pecas.services_dependencies.gemini_service')
    @patch('sistemas.gerador_pecas.services_dependencies.get_thinking_level')
    def test_endpoint_rejeita_ia_com_perguntas_extras(self, mock_thinking, mock_gemini):
        """
        Testa que endpoint rejeita quando IA retorna mais perguntas.
        """
        mock_thinking.return_value = "medium"

        # IA retorna 4 perguntas quando usuário enviou 3
        resposta_ia = {
            "perguntas_normalizadas": [
                {"indice": 0, "texto_final": "P1?", "nome_base_variavel": "v1", "tipo_sugerido": "text"},
                {"indice": 1, "texto_final": "P2?", "nome_base_variavel": "v2", "tipo_sugerido": "text"},
                {"indice": 2, "texto_final": "P3?", "nome_base_variavel": "v3", "tipo_sugerido": "text"},
                {"indice": 3, "texto_final": "Extra inventada?", "nome_base_variavel": "v4", "tipo_sugerido": "text"},
            ],
            "dependencias": [],
            "ordem_recomendada": [0, 1, 2, 3],
            "arvore": {}
        }

        mock_response = AsyncMock()
        mock_response.success = True
        mock_response.content = json.dumps(resposta_ia)
        mock_gemini.generate = AsyncMock(return_value=mock_response)

        # Patch para retornar JSON mockado
        with patch('sistemas.gerador_pecas.services_dependencies.DependencyInferenceService._extrair_json_resposta',
                   return_value=resposta_ia):

            # Chama diretamente o serviço para testar validação
            from sistemas.gerador_pecas.services_dependencies import DependencyInferenceService
            import asyncio

            service = DependencyInferenceService(self.db)
            resultado = asyncio.get_event_loop().run_until_complete(
                service.analisar_dependencias_batch(
                    perguntas=["P1 original", "P2 original", "P3 original"],  # 3 perguntas
                    nomes_variaveis=[None, None, None],
                    categoria_nome="Teste"
                )
            )

        # DEVE falhar - 4 retornadas vs 3 enviadas
        self.assertFalse(resultado.get("success", True))
        self.assertIn("retornou 4", resultado.get("erro", ""))

    @patch('sistemas.gerador_pecas.services_dependencies.gemini_service')
    @patch('sistemas.gerador_pecas.services_dependencies.get_thinking_level')
    def test_endpoint_aceita_quantidade_correta(self, mock_thinking, mock_gemini):
        """
        Testa que endpoint aceita quando IA retorna quantidade correta.
        """
        mock_thinking.return_value = "medium"

        # IA retorna exatamente 3 perguntas
        resposta_ia = {
            "perguntas_normalizadas": [
                {"indice": 0, "texto_final": "Pergunta 1 normalizada?", "nome_base_variavel": "var1", "tipo_sugerido": "boolean"},
                {"indice": 1, "texto_final": "Pergunta 2 normalizada?", "nome_base_variavel": "var2", "tipo_sugerido": "text"},
                {"indice": 2, "texto_final": "Pergunta 3 normalizada?", "nome_base_variavel": "var3", "tipo_sugerido": "choice", "opcoes_sugeridas": ["a", "b"]},
            ],
            "dependencias": [],
            "ordem_recomendada": [0, 1, 2],
            "arvore": {}
        }

        mock_response = AsyncMock()
        mock_response.success = True
        mock_response.content = json.dumps(resposta_ia)
        mock_gemini.generate = AsyncMock(return_value=mock_response)

        with patch('sistemas.gerador_pecas.services_dependencies.DependencyInferenceService._extrair_json_resposta',
                   return_value=resposta_ia):

            from sistemas.gerador_pecas.services_dependencies import DependencyInferenceService
            import asyncio

            service = DependencyInferenceService(self.db)
            resultado = asyncio.get_event_loop().run_until_complete(
                service.analisar_dependencias_batch(
                    perguntas=["P1 bagunçada", "P2 bagunçada", "P3 bagunçada"],  # 3 perguntas
                    nomes_variaveis=[None, None, None],
                    categoria_nome="Teste"
                )
            )

        # DEVE aceitar - quantidade correta
        self.assertTrue(resultado.get("success", False))
        self.assertEqual(len(resultado.get("perguntas_normalizadas", {})), 3)


if __name__ == "__main__":
    unittest.main()
