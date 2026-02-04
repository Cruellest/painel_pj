# tests/test_fallback_persistence.py
"""
Testes para verificar a persistência correta da regra secundária (fallback)
em módulos de prompts.

Bug reportado: Ao editar um módulo no modo determinístico, a regra secundária
(fallback) não persiste após salvar e reabrir o módulo.

Execução:
    pytest tests/test_fallback_persistence.py -v
"""

import unittest
from datetime import datetime

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from admin.models_prompt_groups import PromptGroup
from admin.models_prompts import PromptModulo, PromptModuloHistorico
from auth.models import User
from database.connection import Base


class FallbackPersistenceTests(unittest.TestCase):
    """Testes de persistência de regras secundárias (fallback)."""

    def setUp(self):
        """Configura banco de dados em memória para testes."""
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False}
        )
        self.Session = sessionmaker(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = self.Session()

        # Cria grupo de teste
        self.grupo = PromptGroup(name="Test", slug="test", active=True)
        self.db.add(self.grupo)

        # Cria usuário de teste
        self.user = User(
            username="testuser",
            full_name="Test User",
            email=None,
            hashed_password="x",
            role="admin",
        )
        self.db.add(self.user)
        self.db.commit()

    def tearDown(self):
        """Limpa o banco de dados."""
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)

    def test_schema_has_fallback_columns(self):
        """Verifica se as colunas de fallback existem no schema."""
        inspector = inspect(self.engine)
        columns = [col['name'] for col in inspector.get_columns('prompt_modulos')]

        self.assertIn('regra_deterministica_secundaria', columns)
        self.assertIn('regra_secundaria_texto_original', columns)
        self.assertIn('fallback_habilitado', columns)

    def test_schema_historico_has_fallback_columns(self):
        """Verifica se as colunas de fallback existem no histórico."""
        inspector = inspect(self.engine)
        columns = [col['name'] for col in inspector.get_columns('prompt_modulos_historico')]

        self.assertIn('regra_deterministica_secundaria', columns)
        self.assertIn('regra_secundaria_texto_original', columns)
        self.assertIn('fallback_habilitado', columns)

    def test_create_modulo_with_fallback(self):
        """Testa criação de módulo com fallback habilitado."""
        regra_primaria = {
            "type": "condition",
            "variable": "autor_idoso",
            "operator": "equals",
            "value": True
        }
        regra_secundaria = {
            "type": "condition",
            "variable": "valor_causa",
            "operator": "greater_than",
            "value": 50000
        }

        modulo = PromptModulo(
            tipo="conteudo",
            categoria="teste",
            nome="mod_fallback_test",
            titulo="Módulo com Fallback",
            conteudo="Conteúdo de teste",
            group_id=self.grupo.id,
            modo_ativacao="deterministic",
            regra_deterministica=regra_primaria,
            regra_texto_original="Quando o autor for idoso",
            regra_deterministica_secundaria=regra_secundaria,
            regra_secundaria_texto_original="Quando o valor da causa for maior que 50000",
            fallback_habilitado=True,
            criado_por=self.user.id,
            atualizado_por=self.user.id,
        )
        self.db.add(modulo)
        self.db.commit()

        # Recarrega do banco
        self.db.refresh(modulo)

        # Verifica campos primários
        self.assertEqual(modulo.modo_ativacao, "deterministic")
        self.assertEqual(modulo.regra_deterministica, regra_primaria)
        self.assertEqual(modulo.regra_texto_original, "Quando o autor for idoso")

        # Verifica campos de fallback
        self.assertTrue(modulo.fallback_habilitado)
        self.assertEqual(modulo.regra_deterministica_secundaria, regra_secundaria)
        self.assertEqual(modulo.regra_secundaria_texto_original, "Quando o valor da causa for maior que 50000")

    def test_update_modulo_add_fallback(self):
        """Testa adição de fallback em módulo existente."""
        # Cria módulo sem fallback
        modulo = PromptModulo(
            tipo="conteudo",
            categoria="teste",
            nome="mod_update_test",
            titulo="Módulo para Update",
            conteudo="Conteúdo",
            group_id=self.grupo.id,
            modo_ativacao="deterministic",
            regra_deterministica={"type": "condition", "variable": "x", "operator": "equals", "value": True},
            fallback_habilitado=False,
            criado_por=self.user.id,
        )
        self.db.add(modulo)
        self.db.commit()
        modulo_id = modulo.id

        # Limpa sessão para simular nova requisição
        self.db.expire_all()

        # Busca e atualiza
        modulo_atualizado = self.db.query(PromptModulo).filter(PromptModulo.id == modulo_id).first()

        regra_secundaria = {
            "type": "and",
            "conditions": [
                {"type": "condition", "variable": "a", "operator": "equals", "value": 1},
                {"type": "condition", "variable": "b", "operator": "equals", "value": 2}
            ]
        }

        modulo_atualizado.fallback_habilitado = True
        modulo_atualizado.regra_deterministica_secundaria = regra_secundaria
        modulo_atualizado.regra_secundaria_texto_original = "Quando a=1 e b=2"
        modulo_atualizado.atualizado_por = self.user.id
        modulo_atualizado.atualizado_em = datetime.utcnow()

        self.db.commit()

        # Limpa sessão e recarrega
        self.db.expire_all()

        modulo_recarregado = self.db.query(PromptModulo).filter(PromptModulo.id == modulo_id).first()

        # Verifica persistência
        self.assertTrue(modulo_recarregado.fallback_habilitado)
        self.assertEqual(modulo_recarregado.regra_deterministica_secundaria, regra_secundaria)
        self.assertEqual(modulo_recarregado.regra_secundaria_texto_original, "Quando a=1 e b=2")

    def test_update_modulo_fallback_with_null_text(self):
        """Testa que fallback persiste mesmo com texto original nulo."""
        regra_secundaria = {"type": "condition", "variable": "y", "operator": "exists", "value": True}

        modulo = PromptModulo(
            tipo="conteudo",
            categoria="teste",
            nome="mod_null_text",
            titulo="Módulo Null Text",
            conteudo="Conteúdo",
            group_id=self.grupo.id,
            modo_ativacao="deterministic",
            regra_deterministica={"type": "condition", "variable": "x", "operator": "equals", "value": True},
            # Fallback com AST mas SEM texto original (simula bug onde texto é limpo)
            fallback_habilitado=True,
            regra_deterministica_secundaria=regra_secundaria,
            regra_secundaria_texto_original=None,  # Texto nulo
            criado_por=self.user.id,
        )
        self.db.add(modulo)
        self.db.commit()

        self.db.expire_all()

        modulo_recarregado = self.db.query(PromptModulo).filter(PromptModulo.id == modulo.id).first()

        # O AST deve persistir mesmo sem o texto
        self.assertTrue(modulo_recarregado.fallback_habilitado)
        self.assertEqual(modulo_recarregado.regra_deterministica_secundaria, regra_secundaria)
        self.assertIsNone(modulo_recarregado.regra_secundaria_texto_original)

    def test_historico_preserves_fallback(self):
        """Testa que histórico preserva campos de fallback."""
        regra_sec = {"type": "condition", "variable": "z", "operator": "equals", "value": 42}

        modulo = PromptModulo(
            tipo="conteudo",
            categoria="teste",
            nome="mod_historico",
            titulo="Módulo Histórico",
            conteudo="Conteúdo",
            group_id=self.grupo.id,
            modo_ativacao="deterministic",
            regra_deterministica={"type": "condition", "variable": "x", "operator": "equals", "value": True},
            fallback_habilitado=True,
            regra_deterministica_secundaria=regra_sec,
            regra_secundaria_texto_original="Texto original da secundária",
            versao=1,
            criado_por=self.user.id,
        )
        self.db.add(modulo)
        self.db.commit()

        # Cria histórico
        historico = PromptModuloHistorico(
            modulo_id=modulo.id,
            versao=modulo.versao,
            condicao_ativacao=modulo.condicao_ativacao,
            conteudo=modulo.conteudo,
            modo_ativacao=modulo.modo_ativacao,
            regra_deterministica=modulo.regra_deterministica,
            regra_texto_original=modulo.regra_texto_original,
            regra_deterministica_secundaria=modulo.regra_deterministica_secundaria,
            regra_secundaria_texto_original=modulo.regra_secundaria_texto_original,
            fallback_habilitado=modulo.fallback_habilitado,
            alterado_por=self.user.id,
        )
        self.db.add(historico)
        self.db.commit()

        self.db.expire_all()

        historico_recarregado = self.db.query(PromptModuloHistorico).filter(
            PromptModuloHistorico.modulo_id == modulo.id
        ).first()

        # Verifica que histórico preservou campos de fallback
        self.assertTrue(historico_recarregado.fallback_habilitado)
        self.assertEqual(historico_recarregado.regra_deterministica_secundaria, regra_sec)
        self.assertEqual(historico_recarregado.regra_secundaria_texto_original, "Texto original da secundária")


class FallbackUpdateDataTests(unittest.TestCase):
    """Testes simulando o comportamento do endpoint de update."""

    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False}
        )
        self.Session = sessionmaker(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = self.Session()

        self.grupo = PromptGroup(name="Test", slug="test", active=True)
        self.db.add(self.grupo)

        self.user = User(
            username="testuser",
            full_name="Test User",
            email=None,
            hashed_password="x",
            role="admin",
        )
        self.db.add(self.user)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)

    def test_partial_update_preserves_fallback(self):
        """Testa que update parcial não apaga fallback existente."""
        regra_sec = {"type": "condition", "variable": "test", "operator": "equals", "value": True}

        modulo = PromptModulo(
            tipo="conteudo",
            categoria="teste",
            nome="mod_partial",
            titulo="Módulo Partial",
            conteudo="Conteúdo original",
            group_id=self.grupo.id,
            modo_ativacao="deterministic",
            regra_deterministica={"type": "condition", "variable": "x", "operator": "equals", "value": True},
            fallback_habilitado=True,
            regra_deterministica_secundaria=regra_sec,
            regra_secundaria_texto_original="Texto secundário",
            criado_por=self.user.id,
        )
        self.db.add(modulo)
        self.db.commit()
        modulo_id = modulo.id

        # Simula update parcial (apenas título e conteúdo)
        # Como o backend usa exclude_unset=True, campos não enviados não devem ser alterados
        self.db.expire_all()

        modulo_atualizado = self.db.query(PromptModulo).filter(PromptModulo.id == modulo_id).first()
        modulo_atualizado.titulo = "Título Atualizado"
        modulo_atualizado.conteudo = "Conteúdo atualizado"
        # NÃO altera campos de fallback

        self.db.commit()
        self.db.expire_all()

        modulo_final = self.db.query(PromptModulo).filter(PromptModulo.id == modulo_id).first()

        # Fallback deve estar preservado
        self.assertTrue(modulo_final.fallback_habilitado)
        self.assertEqual(modulo_final.regra_deterministica_secundaria, regra_sec)
        self.assertEqual(modulo_final.regra_secundaria_texto_original, "Texto secundário")

    def test_explicit_null_clears_fallback(self):
        """Testa que enviar null explicitamente limpa o fallback."""
        regra_sec = {"type": "condition", "variable": "test", "operator": "equals", "value": True}

        modulo = PromptModulo(
            tipo="conteudo",
            categoria="teste",
            nome="mod_null_clear",
            titulo="Módulo Clear",
            conteudo="Conteúdo",
            group_id=self.grupo.id,
            modo_ativacao="deterministic",
            regra_deterministica={"type": "condition", "variable": "x", "operator": "equals", "value": True},
            fallback_habilitado=True,
            regra_deterministica_secundaria=regra_sec,
            regra_secundaria_texto_original="Texto secundário",
            criado_por=self.user.id,
        )
        self.db.add(modulo)
        self.db.commit()
        modulo_id = modulo.id

        # Simula desabilitar fallback
        self.db.expire_all()

        modulo_atualizado = self.db.query(PromptModulo).filter(PromptModulo.id == modulo_id).first()
        modulo_atualizado.fallback_habilitado = False
        modulo_atualizado.regra_deterministica_secundaria = None
        modulo_atualizado.regra_secundaria_texto_original = None

        self.db.commit()
        self.db.expire_all()

        modulo_final = self.db.query(PromptModulo).filter(PromptModulo.id == modulo_id).first()

        # Fallback deve estar limpo
        self.assertFalse(modulo_final.fallback_habilitado)
        self.assertIsNone(modulo_final.regra_deterministica_secundaria)
        self.assertIsNone(modulo_final.regra_secundaria_texto_original)


class FallbackEndpointBehaviorTests(unittest.TestCase):
    """Testes simulando o comportamento exato do endpoint PUT."""

    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False}
        )
        self.Session = sessionmaker(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = self.Session()

        self.grupo = PromptGroup(name="Test", slug="test", active=True)
        self.db.add(self.grupo)

        self.user = User(
            username="testuser",
            full_name="Test User",
            email=None,
            hashed_password="x",
            role="admin",
        )
        self.db.add(self.user)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)

    def test_pydantic_exclude_unset_with_explicit_values(self):
        """Testa comportamento de exclude_unset com valores explícitos."""
        from admin.router_prompts import PromptModuloUpdate

        # Simula payload do frontend com fallback
        payload = {
            "titulo": "Novo Título",
            "conteudo": "Novo conteúdo",
            "modo_ativacao": "deterministic",
            "regra_deterministica": {"type": "condition", "variable": "x", "operator": "equals", "value": True},
            "fallback_habilitado": True,
            "regra_deterministica_secundaria": {"type": "condition", "variable": "y", "operator": "equals", "value": 42},
            "regra_secundaria_texto_original": "Quando y = 42",
        }

        modulo_data = PromptModuloUpdate(**payload)
        update_data = modulo_data.model_dump(exclude_unset=True, exclude={"motivo", "subcategoria_ids"})

        # Verifica que os campos de fallback estão no update_data
        self.assertIn("fallback_habilitado", update_data)
        self.assertIn("regra_deterministica_secundaria", update_data)
        self.assertIn("regra_secundaria_texto_original", update_data)

        self.assertTrue(update_data["fallback_habilitado"])
        self.assertEqual(update_data["regra_deterministica_secundaria"]["variable"], "y")
        self.assertEqual(update_data["regra_secundaria_texto_original"], "Quando y = 42")

    def test_pydantic_exclude_unset_with_null_values(self):
        """Testa comportamento de exclude_unset com valores null explícitos."""
        from admin.router_prompts import PromptModuloUpdate

        # Simula payload com fallback habilitado mas sem texto original (null)
        payload = {
            "titulo": "Título",
            "fallback_habilitado": True,
            "regra_deterministica_secundaria": {"type": "condition", "variable": "z", "operator": "exists", "value": True},
            "regra_secundaria_texto_original": None,  # Explicitamente null
        }

        modulo_data = PromptModuloUpdate(**payload)
        update_data = modulo_data.model_dump(exclude_unset=True, exclude={"motivo", "subcategoria_ids"})

        # O campo com null EXPLÍCITO deve estar incluído
        self.assertIn("regra_secundaria_texto_original", update_data)
        self.assertIsNone(update_data["regra_secundaria_texto_original"])

    def test_full_update_flow_with_fallback(self):
        """Testa fluxo completo de update com fallback."""
        from admin.router_prompts import PromptModuloUpdate

        # Cria módulo inicial sem fallback
        modulo = PromptModulo(
            tipo="conteudo",
            categoria="teste",
            nome="mod_flow_test",
            titulo="Módulo Flow Test",
            conteudo="Conteúdo inicial",
            group_id=self.grupo.id,
            modo_ativacao="deterministic",
            regra_deterministica={"type": "condition", "variable": "x", "operator": "equals", "value": True},
            fallback_habilitado=False,
            criado_por=self.user.id,
            versao=1,
        )
        self.db.add(modulo)
        self.db.commit()
        modulo_id = modulo.id

        # Simula payload de update adicionando fallback
        payload = {
            "titulo": "Módulo Flow Test Updated",
            "conteudo": "Conteúdo atualizado",
            "modo_ativacao": "deterministic",
            "regra_deterministica": {"type": "condition", "variable": "x", "operator": "equals", "value": True},
            "fallback_habilitado": True,
            "regra_deterministica_secundaria": {
                "type": "and",
                "conditions": [
                    {"type": "condition", "variable": "a", "operator": "equals", "value": 1},
                    {"type": "condition", "variable": "b", "operator": "equals", "value": 2}
                ]
            },
            "regra_secundaria_texto_original": "Quando a=1 E b=2",
        }

        modulo_data = PromptModuloUpdate(**payload)
        update_data = modulo_data.model_dump(exclude_unset=True, exclude={"motivo", "subcategoria_ids"})

        # Aplica update
        self.db.expire_all()
        modulo_atualizado = self.db.query(PromptModulo).filter(PromptModulo.id == modulo_id).first()

        for field, value in update_data.items():
            setattr(modulo_atualizado, field, value)

        modulo_atualizado.versao += 1
        modulo_atualizado.atualizado_por = self.user.id
        modulo_atualizado.atualizado_em = datetime.utcnow()

        self.db.commit()

        # Verifica persistência
        self.db.expire_all()
        modulo_final = self.db.query(PromptModulo).filter(PromptModulo.id == modulo_id).first()

        self.assertEqual(modulo_final.titulo, "Módulo Flow Test Updated")
        self.assertTrue(modulo_final.fallback_habilitado)
        self.assertIsNotNone(modulo_final.regra_deterministica_secundaria)
        self.assertEqual(modulo_final.regra_deterministica_secundaria["type"], "and")
        self.assertEqual(len(modulo_final.regra_deterministica_secundaria["conditions"]), 2)
        self.assertEqual(modulo_final.regra_secundaria_texto_original, "Quando a=1 E b=2")

    def test_response_includes_fallback_fields(self):
        """Testa que a resposta inclui campos de fallback."""
        from admin.router_prompts import PromptModuloResponse

        regra_sec = {"type": "condition", "variable": "test", "operator": "equals", "value": True}

        modulo = PromptModulo(
            tipo="conteudo",
            categoria="teste",
            nome="mod_response_test",
            titulo="Módulo Response",
            conteudo="Conteúdo",
            group_id=self.grupo.id,
            modo_ativacao="deterministic",
            regra_deterministica={"type": "condition", "variable": "x", "operator": "equals", "value": True},
            fallback_habilitado=True,
            regra_deterministica_secundaria=regra_sec,
            regra_secundaria_texto_original="Texto secundário",
            criado_por=self.user.id,
            versao=1,
        )
        self.db.add(modulo)
        self.db.commit()
        self.db.refresh(modulo)

        # Simula como o endpoint monta a resposta
        response_dict = modulo.__dict__.copy()
        response_dict["subcategoria_ids"] = []
        response_dict["subcategorias_nomes"] = []

        # Remove campos internos do SQLAlchemy
        response_dict.pop("_sa_instance_state", None)

        # Verifica que campos de fallback estão na resposta
        self.assertIn("fallback_habilitado", response_dict)
        self.assertIn("regra_deterministica_secundaria", response_dict)
        self.assertIn("regra_secundaria_texto_original", response_dict)

        self.assertTrue(response_dict["fallback_habilitado"])
        self.assertEqual(response_dict["regra_deterministica_secundaria"], regra_sec)
        self.assertEqual(response_dict["regra_secundaria_texto_original"], "Texto secundário")


if __name__ == "__main__":
    unittest.main()
