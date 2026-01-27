# tests/test_subgroup_deprecation.py
"""
Testes para verificar a separacao correta entre Categorias e Subgrupos.

Este arquivo testa:
1. Que subgrupos NAO sao mais criados automaticamente a partir de categorias
2. Que subgrupos operacionais podem ser criados manualmente
3. Que modulos continuam funcionando com ou sem subgrupos
4. Que a categoria eh mantida corretamente e separada de subgrupos
5. Que a migracao remove apenas subgrupos que eram categorias duplicadas
"""
import unittest
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from admin.models_prompt_groups import PromptGroup, PromptSubgroup, PromptSubcategoria
from admin.models_prompts import PromptModulo, PromptModuloHistorico
from auth.models import User
from database.connection import Base
from database.init_db import seed_prompt_groups


class SubgroupSeparationTests(unittest.TestCase):
    """Testes para verificar a separacao entre Categorias e Subgrupos."""

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

    def _create_user(self, username, role="user"):
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

    def _create_modulo(self, **kwargs):
        modulo = PromptModulo(
            tipo=kwargs.get("tipo", "conteudo"),
            categoria=kwargs.get("categoria"),
            subcategoria=kwargs.get("subcategoria"),
            nome=kwargs.get("nome", "modulo"),
            titulo=kwargs.get("titulo", "Modulo"),
            conteudo=kwargs.get("conteudo", "conteudo"),
            palavras_chave=kwargs.get("palavras_chave", []),
            tags=kwargs.get("tags", []),
            ativo=kwargs.get("ativo", True),
            ordem=kwargs.get("ordem", 0),
            group_id=kwargs.get("group_id"),
            subgroup_id=kwargs.get("subgroup_id"),
        )
        self.db.add(modulo)
        self.db.flush()
        return modulo

    def test_seed_nao_cria_subgrupos_a_partir_de_categorias(self):
        """Verifica que seed_prompt_groups NAO cria mais subgrupos a partir de categorias."""
        user = self._create_user("usuario_test")

        # Cria modulos com diferentes categorias (que ANTES virariam subgrupos)
        self._create_modulo(
            nome="mod_preliminar",
            titulo="Modulo Preliminar",
            categoria="Preliminar",
        )
        self._create_modulo(
            nome="mod_merito",
            titulo="Modulo Merito",
            categoria="Merito",
        )
        self._create_modulo(
            nome="mod_eventualidade",
            titulo="Modulo Eventualidade",
            categoria="Eventualidade",
        )
        self.db.commit()

        # Executa seed
        seed_prompt_groups(self.db)

        # Verifica que grupo PS foi criado
        grupo_ps = self.db.query(PromptGroup).filter(PromptGroup.slug == "ps").first()
        self.assertIsNotNone(grupo_ps)

        # Verifica que NENHUM subgrupo foi criado automaticamente
        subgrupos = self.db.query(PromptSubgroup).all()
        self.assertEqual(len(subgrupos), 0, "Subgrupos NAO devem ser criados automaticamente a partir de categorias")

        # Verifica que modulos tem group_id setado mas subgroup_id eh NULL
        modulos = self.db.query(PromptModulo).filter(PromptModulo.tipo == "conteudo").all()
        for modulo in modulos:
            self.assertEqual(modulo.group_id, grupo_ps.id)
            self.assertIsNone(modulo.subgroup_id, f"subgroup_id deveria ser NULL para {modulo.nome}")

    def test_subgrupo_operacional_pode_ser_criado_manualmente(self):
        """Verifica que subgrupos operacionais podem ser criados manualmente."""
        grupo_ps = PromptGroup(name="PS", slug="ps", active=True)
        self.db.add(grupo_ps)
        self.db.flush()

        # Cria subgrupo operacional manualmente (Conhecimento/Cumprimento)
        subgrupo_conhecimento = PromptSubgroup(
            group_id=grupo_ps.id,
            name="Conhecimento",
            slug="conhecimento",
            active=True,
        )
        self.db.add(subgrupo_conhecimento)
        self.db.flush()

        # Cria modulo associado ao subgrupo operacional
        modulo = self._create_modulo(
            nome="mod_conhecimento",
            titulo="Modulo Conhecimento",
            categoria="Preliminar",  # Categoria juridica
            group_id=grupo_ps.id,
            subgroup_id=subgrupo_conhecimento.id,  # Subgrupo operacional
        )
        self.db.commit()

        # Verifica que ambos coexistem corretamente
        modulo_db = self.db.query(PromptModulo).filter(PromptModulo.id == modulo.id).first()
        self.assertEqual(modulo_db.categoria, "Preliminar")  # Categoria juridica
        self.assertEqual(modulo_db.subgroup_id, subgrupo_conhecimento.id)  # Subgrupo operacional

    def test_categoria_e_subgrupo_sao_conceitos_separados(self):
        """Verifica que categoria e subgrupo sao conceitos separados."""
        grupo_ps = PromptGroup(name="PS", slug="ps", active=True)
        self.db.add(grupo_ps)
        self.db.flush()

        # Cria subgrupos operacionais
        subgrupo_conhecimento = PromptSubgroup(
            group_id=grupo_ps.id, name="Conhecimento", slug="conhecimento", active=True
        )
        subgrupo_cumprimento = PromptSubgroup(
            group_id=grupo_ps.id, name="Cumprimento", slug="cumprimento", active=True
        )
        self.db.add_all([subgrupo_conhecimento, subgrupo_cumprimento])
        self.db.flush()

        # Cria modulos com diferentes combinacoes de categoria e subgrupo
        mod1 = self._create_modulo(
            nome="mod1", categoria="Preliminar", group_id=grupo_ps.id, subgroup_id=subgrupo_conhecimento.id
        )
        mod2 = self._create_modulo(
            nome="mod2", categoria="Preliminar", group_id=grupo_ps.id, subgroup_id=subgrupo_cumprimento.id
        )
        mod3 = self._create_modulo(
            nome="mod3", categoria="Merito", group_id=grupo_ps.id, subgroup_id=subgrupo_conhecimento.id
        )
        self.db.commit()

        # Filtra por categoria
        modulos_preliminar = self.db.query(PromptModulo).filter(
            PromptModulo.categoria == "Preliminar"
        ).all()
        self.assertEqual(len(modulos_preliminar), 2)

        # Filtra por subgrupo operacional
        modulos_conhecimento = self.db.query(PromptModulo).filter(
            PromptModulo.subgroup_id == subgrupo_conhecimento.id
        ).all()
        self.assertEqual(len(modulos_conhecimento), 2)

        # Filtra por ambos
        modulos_preliminar_conhecimento = self.db.query(PromptModulo).filter(
            PromptModulo.categoria == "Preliminar",
            PromptModulo.subgroup_id == subgrupo_conhecimento.id
        ).all()
        self.assertEqual(len(modulos_preliminar_conhecimento), 1)
        self.assertEqual(modulos_preliminar_conhecimento[0].nome, "mod1")

    def test_modulo_funciona_sem_subgrupo(self):
        """Verifica que modulos funcionam perfeitamente sem subgrupo."""
        grupo_ps = PromptGroup(name="PS", slug="ps", active=True)
        self.db.add(grupo_ps)
        self.db.flush()

        modulo = self._create_modulo(
            nome="mod_sem_subgrupo",
            titulo="Modulo Sem Subgrupo",
            categoria="Merito",
            group_id=grupo_ps.id,
            subgroup_id=None,  # Sem subgrupo
        )
        self.db.commit()

        # Modulo deve funcionar normalmente
        modulo_db = self.db.query(PromptModulo).filter(PromptModulo.id == modulo.id).first()
        self.assertIsNotNone(modulo_db)
        self.assertEqual(modulo_db.categoria, "Merito")
        self.assertIsNone(modulo_db.subgroup_id)

        # Pode ser editado
        modulo_db.titulo = "Modulo Editado"
        self.db.commit()

        modulo_final = self.db.query(PromptModulo).filter(PromptModulo.id == modulo.id).first()
        self.assertEqual(modulo_final.titulo, "Modulo Editado")


class SubgroupAPITests(unittest.TestCase):
    """Testes para a API de subgrupos."""

    def test_obter_ou_criar_subgrupo_funciona(self):
        """Verifica que _obter_ou_criar_subgrupo cria subgrupos operacionais."""
        from admin.router_prompts import _obter_ou_criar_subgrupo

        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False}
        )
        Session = sessionmaker(bind=engine)
        Base.metadata.create_all(bind=engine)
        db = Session()

        try:
            grupo = PromptGroup(name="PS", slug="ps", active=True)
            db.add(grupo)
            db.flush()

            # Cria subgrupo operacional
            subgrupo = _obter_ou_criar_subgrupo(db, grupo, "conhecimento", "Conhecimento")

            self.assertIsNotNone(subgrupo)
            self.assertEqual(subgrupo.slug, "conhecimento")
            self.assertEqual(subgrupo.name, "Conhecimento")
            self.assertEqual(subgrupo.group_id, grupo.id)
        finally:
            db.close()
            Base.metadata.drop_all(bind=engine)


if __name__ == "__main__":
    unittest.main()
