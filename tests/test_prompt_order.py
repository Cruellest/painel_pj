"""
Teste para verificar se a ordem dos prompts modulares é respeitada
quando enviados ao Agente 3 (gerador de peças).

A ordem deve ser:
1. Primeiro por categoria (usando CategoriaOrdem.ordem)
2. Depois por ordem do módulo (PromptModulo.ordem)
"""

import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from admin.models_prompt_groups import PromptGroup, CategoriaOrdem
from admin.models_prompts import PromptModulo
from auth.models import User
from database.connection import Base
from sistemas.gerador_pecas.services import GeradorPecasService


class TestPromptOrder(unittest.TestCase):
    """Testes para verificar ordenação correta dos prompts modulares."""

    def setUp(self):
        """Configura banco de dados em memória para cada teste."""
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False}
        )
        self.Session = sessionmaker(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = self.Session()

    def tearDown(self):
        """Limpa banco após cada teste."""
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)

    def _criar_grupo(self, name="Teste"):
        """Cria um grupo de prompts."""
        grupo = PromptGroup(name=name, slug=name.lower(), active=True)
        self.db.add(grupo)
        self.db.flush()
        return grupo

    def _criar_categoria_ordem(self, group_id, nome, ordem):
        """Cria configuração de ordem para uma categoria."""
        cat_ordem = CategoriaOrdem(
            group_id=group_id,
            nome=nome,
            ordem=ordem,
            ativo=True
        )
        self.db.add(cat_ordem)
        self.db.flush()
        return cat_ordem

    def _criar_modulo(self, group_id, categoria, ordem, titulo):
        """Cria um módulo de conteúdo."""
        modulo = PromptModulo(
            tipo="conteudo",
            categoria=categoria,
            nome=titulo.lower().replace(" ", "_"),
            titulo=titulo,
            conteudo=f"Conteúdo do módulo {titulo}",
            palavras_chave=[],
            tags=[],
            ativo=True,
            ordem=ordem,
            group_id=group_id,
        )
        self.db.add(modulo)
        self.db.flush()
        return modulo

    def test_ordem_categoria_e_modulo_respeitada(self):
        """
        Testa se a ordem configurada das categorias e módulos é respeitada.

        Cenário:
        - Categoria "Eventualidade" com ordem 2
        - Categoria "Preliminar" com ordem 0
        - Categoria "Mérito" com ordem 1

        - Módulos em cada categoria com ordens variadas

        Resultado esperado:
        1. Preliminar (ordem_cat=0) -> módulos ordenados por ordem
        2. Mérito (ordem_cat=1) -> módulos ordenados por ordem
        3. Eventualidade (ordem_cat=2) -> módulos ordenados por ordem
        """
        # Cria grupo
        grupo = self._criar_grupo("Saúde")

        # Configura ordem das categorias (propositalmente fora de ordem alfabética)
        self._criar_categoria_ordem(grupo.id, "Eventualidade", 2)
        self._criar_categoria_ordem(grupo.id, "Preliminar", 0)
        self._criar_categoria_ordem(grupo.id, "Mérito", 1)

        # Cria módulos (propositalmente em ordem aleatória no banco)
        # Eventualidade
        m_event_2 = self._criar_modulo(grupo.id, "Eventualidade", 1, "Eventualidade - Segundo")
        m_event_1 = self._criar_modulo(grupo.id, "Eventualidade", 0, "Eventualidade - Primeiro")

        # Mérito
        m_merito_3 = self._criar_modulo(grupo.id, "Mérito", 2, "Mérito - Terceiro")
        m_merito_1 = self._criar_modulo(grupo.id, "Mérito", 0, "Mérito - Primeiro")
        m_merito_2 = self._criar_modulo(grupo.id, "Mérito", 1, "Mérito - Segundo")

        # Preliminar
        m_prelim_2 = self._criar_modulo(grupo.id, "Preliminar", 1, "Preliminar - Segundo")
        m_prelim_1 = self._criar_modulo(grupo.id, "Preliminar", 0, "Preliminar - Primeiro")

        self.db.commit()

        # Cria serviço e carrega módulos
        service = GeradorPecasService(db=self.db, group_id=grupo.id)
        modulos = service._carregar_modulos_conteudo()

        # Verifica quantidade
        self.assertEqual(len(modulos), 7, "Deve retornar 7 módulos")

        # Verifica ordem esperada
        ordem_esperada = [
            "Preliminar - Primeiro",    # cat=0, ordem=0
            "Preliminar - Segundo",     # cat=0, ordem=1
            "Mérito - Primeiro",        # cat=1, ordem=0
            "Mérito - Segundo",         # cat=1, ordem=1
            "Mérito - Terceiro",        # cat=1, ordem=2
            "Eventualidade - Primeiro", # cat=2, ordem=0
            "Eventualidade - Segundo",  # cat=2, ordem=1
        ]

        ordem_retornada = [m.titulo for m in modulos]

        print("\n" + "="*60)
        print("ORDEM ESPERADA:")
        for i, titulo in enumerate(ordem_esperada):
            print(f"  {i+1}. {titulo}")
        print("\nORDEM RETORNADA:")
        for i, titulo in enumerate(ordem_retornada):
            print(f"  {i+1}. {titulo}")
        print("="*60 + "\n")

        self.assertEqual(
            ordem_retornada,
            ordem_esperada,
            f"Ordem dos módulos não está correta!\n"
            f"Esperado: {ordem_esperada}\n"
            f"Retornado: {ordem_retornada}"
        )

    def test_categoria_sem_ordem_vai_pro_final(self):
        """
        Testa se categorias sem ordem configurada vão para o final.
        """
        grupo = self._criar_grupo("Teste")

        # Apenas "Preliminar" tem ordem configurada
        self._criar_categoria_ordem(grupo.id, "Preliminar", 0)

        # Cria módulos em várias categorias
        m1 = self._criar_modulo(grupo.id, "Preliminar", 0, "Preliminar - Item")
        m2 = self._criar_modulo(grupo.id, "Sem Ordem", 0, "Sem Ordem - Item")
        m3 = self._criar_modulo(grupo.id, "Outra Sem Ordem", 0, "Outra - Item")

        self.db.commit()

        service = GeradorPecasService(db=self.db, group_id=grupo.id)
        modulos = service._carregar_modulos_conteudo()

        # Preliminar deve vir primeiro
        self.assertEqual(modulos[0].titulo, "Preliminar - Item")
        # Os outros vão pro final (ordem 9999)
        self.assertIn(modulos[1].categoria, ["Sem Ordem", "Outra Sem Ordem"])
        self.assertIn(modulos[2].categoria, ["Sem Ordem", "Outra Sem Ordem"])

    def test_ordem_modulos_dentro_mesma_categoria(self):
        """
        Testa se módulos dentro da mesma categoria são ordenados por PromptModulo.ordem.
        """
        grupo = self._criar_grupo("Teste")
        self._criar_categoria_ordem(grupo.id, "Única", 0)

        # Cria módulos fora de ordem
        m5 = self._criar_modulo(grupo.id, "Única", 4, "Quinto")
        m1 = self._criar_modulo(grupo.id, "Única", 0, "Primeiro")
        m3 = self._criar_modulo(grupo.id, "Única", 2, "Terceiro")
        m2 = self._criar_modulo(grupo.id, "Única", 1, "Segundo")
        m4 = self._criar_modulo(grupo.id, "Única", 3, "Quarto")

        self.db.commit()

        service = GeradorPecasService(db=self.db, group_id=grupo.id)
        modulos = service._carregar_modulos_conteudo()

        ordem_esperada = ["Primeiro", "Segundo", "Terceiro", "Quarto", "Quinto"]
        ordem_retornada = [m.titulo for m in modulos]

        self.assertEqual(ordem_retornada, ordem_esperada)

    def test_prompt_sistema_monta_na_ordem_correta(self):
        """
        Testa se _montar_prompt_sistema inclui os módulos na ordem correta.
        """
        grupo = self._criar_grupo("Teste")

        # Configura ordens invertidas propositalmente
        self._criar_categoria_ordem(grupo.id, "Z-Ultimo", 1)
        self._criar_categoria_ordem(grupo.id, "A-Primeiro", 0)

        self._criar_modulo(grupo.id, "Z-Ultimo", 0, "Módulo Z")
        self._criar_modulo(grupo.id, "A-Primeiro", 0, "Módulo A")

        self.db.commit()

        service = GeradorPecasService(db=self.db, group_id=grupo.id)
        prompt = service._montar_prompt_sistema()

        # Verifica se "Módulo A" aparece antes de "Módulo Z" no prompt
        pos_a = prompt.find("Módulo A")
        pos_z = prompt.find("Módulo Z")

        self.assertNotEqual(pos_a, -1, "Módulo A deve estar no prompt")
        self.assertNotEqual(pos_z, -1, "Módulo Z deve estar no prompt")
        self.assertLess(
            pos_a, pos_z,
            f"Módulo A (pos={pos_a}) deve vir antes de Módulo Z (pos={pos_z})"
        )


if __name__ == "__main__":
    # Executa testes com output detalhado
    unittest.main(verbosity=2)
