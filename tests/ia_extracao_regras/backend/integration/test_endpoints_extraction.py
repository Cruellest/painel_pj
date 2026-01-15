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


if __name__ == "__main__":
    unittest.main()
