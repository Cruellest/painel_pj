import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from admin.models_prompt_groups import PromptGroup, PromptSubgroup, PromptSubcategoria
from admin.models_prompts import PromptModulo, PromptModuloHistorico
from auth.models import User
from database.connection import Base
from database.init_db import seed_prompt_groups
from sistemas.gerador_pecas.services import GeradorPecasService


class PromptGroupTests(unittest.TestCase):
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

    def test_tem_acesso_grupo_respeita_default_e_permitidos(self):
        grupo_ps = PromptGroup(name="PS", slug="ps", active=True)
        grupo_pp = PromptGroup(name="PP", slug="pp", active=True)
        self.db.add_all([grupo_ps, grupo_pp])
        self.db.flush()

        user = self._create_user("usuario")
        user.default_group_id = grupo_ps.id
        self.db.commit()

        self.assertTrue(user.tem_acesso_grupo(grupo_ps.id))
        self.assertFalse(user.tem_acesso_grupo(grupo_pp.id))

        user.allowed_groups.append(grupo_pp)
        self.db.commit()

        self.assertTrue(user.tem_acesso_grupo(grupo_pp.id))

        admin = self._create_user("admin", role="admin")
        self.db.commit()
        self.assertTrue(admin.tem_acesso_grupo(grupo_pp.id))

    def test_carregar_modulos_conteudo_filtra_por_grupo_e_subgrupo(self):
        grupo_ps = PromptGroup(name="PS", slug="ps", active=True)
        grupo_pp = PromptGroup(name="PP", slug="pp", active=True)
        self.db.add_all([grupo_ps, grupo_pp])
        self.db.flush()

        sub_a = PromptSubgroup(group_id=grupo_ps.id, name="A", slug="a", active=True)
        sub_b = PromptSubgroup(group_id=grupo_ps.id, name="B", slug="b", active=True)
        self.db.add_all([sub_a, sub_b])
        self.db.flush()

        subcat_a = PromptSubcategoria(group_id=grupo_ps.id, nome="A", slug="a", active=True)
        subcat_b = PromptSubcategoria(group_id=grupo_ps.id, nome="B", slug="b", active=True)
        self.db.add_all([subcat_a, subcat_b])
        self.db.flush()

        modulo_a = self._create_modulo(
            nome="mod_a",
            titulo="Modulo A",
            ordem=1,
            group_id=grupo_ps.id,
            subgroup_id=sub_a.id,
        )
        modulo_a.subcategorias.append(subcat_a)
        modulo_b = self._create_modulo(
            nome="mod_b",
            titulo="Modulo B",
            ordem=2,
            group_id=grupo_ps.id,
            subgroup_id=sub_b.id,
        )
        modulo_b.subcategorias.append(subcat_b)
        # Módulo C não tem subcategoria - será tratado como "universal"
        modulo_c = self._create_modulo(
            nome="mod_c",
            titulo="Modulo C",
            ordem=3,
            group_id=grupo_ps.id,
            subgroup_id=None,
        )
        self._create_modulo(
            nome="mod_d",
            titulo="Modulo D",
            ordem=4,
            group_id=grupo_pp.id,
            subgroup_id=None,
        )
        self.db.commit()

        service = GeradorPecasService.__new__(GeradorPecasService)
        service.db = self.db
        service.group_id = grupo_ps.id
        service.subcategoria_ids = [subcat_a.id]

        modulos = service._carregar_modulos_conteudo()
        modulos_ids = [modulo.id for modulo in modulos]

        # Módulos retornados: A (tem subcategoria A) e C (sem subcategoria = universal)
        self.assertEqual(modulos_ids, [modulo_a.id, modulo_c.id])

    def test_seed_prompt_groups_define_ps_default(self):
        """
        Verifica que seed_prompt_groups:
        - Define grupo PS como padrao
        - Vincula modulos ao grupo PS
        - NAO cria subgrupos (funcionalidade descontinuada)
        """
        user = self._create_user("usuario_seed")
        modulo_meds = self._create_modulo(
            nome="mod_meds",
            titulo="Modulo Medicamentos",
            categoria="Medicamentos",
        )
        modulo_cir = self._create_modulo(
            nome="mod_cir",
            titulo="Modulo Cirurgia",
            categoria="Cirurgia",
        )
        historico = PromptModuloHistorico(
            modulo_id=modulo_meds.id,
            versao=1,
            conteudo="Historico",
            palavras_chave=[],
            tags=[],
        )
        self.db.add(historico)
        self.db.commit()

        seed_prompt_groups(self.db)

        grupo_ps = self.db.query(PromptGroup).filter(PromptGroup.slug == "ps").one()

        self.db.refresh(modulo_meds)
        self.db.refresh(modulo_cir)
        self.assertEqual(modulo_meds.group_id, grupo_ps.id)
        self.assertEqual(modulo_cir.group_id, grupo_ps.id)

        # ATUALIZADO: Subgrupos foram descontinuados - nao devem ser criados
        self.assertIsNone(modulo_meds.subgroup_id, "Subgrupos foram descontinuados")
        self.assertIsNone(modulo_cir.subgroup_id, "Subgrupos foram descontinuados")

        # Categoria deve permanecer intacta
        self.assertEqual(modulo_meds.categoria, "Medicamentos")
        self.assertEqual(modulo_cir.categoria, "Cirurgia")

        historico_ref = self.db.query(PromptModuloHistorico).filter(
            PromptModuloHistorico.id == historico.id
        ).one()
        self.assertEqual(historico_ref.group_id, grupo_ps.id)

        user_ref = self.db.query(User).filter(User.id == user.id).one()
        self.assertEqual(user_ref.default_group_id, grupo_ps.id)
        self.assertTrue(any(grupo.id == grupo_ps.id for grupo in user_ref.allowed_groups))


if __name__ == "__main__":
    unittest.main()
