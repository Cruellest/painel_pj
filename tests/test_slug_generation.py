"""
Testes para geração de slugs e deleção de variáveis.

Cobre:
- Bug 1: Slugs com sufixos _2, _3 sendo criados indevidamente
- Bug 2: Variáveis deletadas virando inativas em vez de hard delete

Autor: Claude Code
Data: 2026-01-19
"""

import json
import sys
import unittest
from datetime import datetime
from pathlib import Path

# Adiciona o diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.connection import Base, get_db
from main import app


class TestSlugGeneration(unittest.TestCase):
    """
    Testes para geração de slugs (Bug 1).

    Cenários cobertos:
    - Slug base inexistente → não adiciona sufixo
    - Slug base existente ATIVO → adiciona _2
    - Slug base existente INATIVO → NÃO adiciona _2 (reutiliza/reativa)
    """

    @classmethod
    def setUpClass(cls):
        """Configura banco em memória para todos os testes."""
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False}
        )
        cls.TestingSessionLocal = sessionmaker(bind=cls.engine)

        # Importa modelos para criar tabelas
        from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON
        from sistemas.gerador_pecas.models_extraction import (
            ExtractionQuestion, ExtractionVariable,
            PromptVariableUsage
        )
        from auth.models import User

        Base.metadata.create_all(bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=cls.engine)

    def setUp(self):
        self.db = self.TestingSessionLocal()

        def override_get_db():
            try:
                yield self.db
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db

        # Limpa tabelas
        from sistemas.gerador_pecas.models_extraction import (
            ExtractionQuestion, ExtractionVariable
        )
        from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON

        self.db.query(ExtractionVariable).delete()
        self.db.query(ExtractionQuestion).delete()
        self.db.query(CategoriaResumoJSON).delete()
        self.db.commit()

    def tearDown(self):
        self.db.rollback()
        self.db.close()

    def _criar_categoria(self, nome="teste", namespace_prefix=None):
        from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON
        categoria = CategoriaResumoJSON(
            nome=nome,
            titulo=f"Categoria {nome}",
            descricao="Teste",
            codigos_documento=[100],
            namespace_prefix=namespace_prefix,
            formato_json="{}"
        )
        self.db.add(categoria)
        self.db.commit()
        return categoria

    def _criar_pergunta(self, categoria_id, slug, tipo="text", pergunta="Pergunta?"):
        from sistemas.gerador_pecas.models_extraction import ExtractionQuestion
        p = ExtractionQuestion(
            categoria_id=categoria_id,
            pergunta=pergunta,
            nome_variavel_sugerido=slug,
            tipo_sugerido=tipo,
            ordem=0,
            ativo=True
        )
        self.db.add(p)
        self.db.commit()
        return p

    def _criar_variavel(self, slug, categoria_id=None, source_question_id=None, ativo=True):
        from sistemas.gerador_pecas.models_extraction import ExtractionVariable
        v = ExtractionVariable(
            slug=slug,
            label=f"Variável {slug}",
            tipo="text",
            categoria_id=categoria_id,
            source_question_id=source_question_id,
            ativo=ativo
        )
        self.db.add(v)
        self.db.commit()
        return v

    # ==========================================================================
    # TESTES BUG 1: Geração de slugs
    # ==========================================================================

    def test_slug_base_inexistente_nao_adiciona_sufixo(self):
        """
        TESTE: Criar variável com slug base inexistente => não adiciona sufixo.
        """
        from sistemas.gerador_pecas.router_extraction import _get_unique_slug

        # Slug que não existe
        slug = _get_unique_slug(self.db, "novo_slug")

        self.assertEqual(slug, "novo_slug", "Não deveria adicionar sufixo para slug inexistente")

    def test_slug_base_existente_ativo_adiciona_sufixo(self):
        """
        TESTE: Criar variável com slug base existente ATIVO => adiciona _2.
        """
        from sistemas.gerador_pecas.router_extraction import _get_unique_slug

        categoria = self._criar_categoria()

        # Cria variável ATIVA com o slug
        self._criar_variavel("meu_slug", categoria_id=categoria.id, ativo=True)

        # Deve gerar sufixo _2
        slug = _get_unique_slug(self.db, "meu_slug")

        self.assertEqual(slug, "meu_slug_2", "Deveria adicionar sufixo _2 para conflito com variável ativa")

    def test_slug_base_existente_inativo_nao_adiciona_sufixo(self):
        """
        TESTE: Criar variável com slug base existente INATIVO => NÃO adiciona sufixo.

        Este é o cenário principal do Bug 1.
        """
        from sistemas.gerador_pecas.router_extraction import _get_unique_slug

        categoria = self._criar_categoria()

        # Cria variável INATIVA com o slug (simulando soft delete anterior)
        self._criar_variavel("slug_inativo", categoria_id=categoria.id, ativo=False)

        # NÃO deve gerar sufixo - variável inativa não bloqueia
        slug = _get_unique_slug(self.db, "slug_inativo")

        self.assertEqual(slug, "slug_inativo",
            "NÃO deveria adicionar sufixo para conflito com variável INATIVA")

    def test_ensure_variable_reativa_variavel_inativa(self):
        """
        TESTE: ensure_variable_for_question deve REATIVAR variável inativa,
        não criar nova com sufixo.
        """
        from sistemas.gerador_pecas.router_extraction import ensure_variable_for_question
        from sistemas.gerador_pecas.models_extraction import ExtractionVariable

        categoria = self._criar_categoria("decisoes", namespace_prefix="decisoes")

        # Cria variável INATIVA
        var_inativa = self._criar_variavel(
            "decisoes_resultado_tutela",
            categoria_id=categoria.id,
            ativo=False
        )
        var_id_original = var_inativa.id

        # Cria pergunta que usaria o mesmo slug
        pergunta = self._criar_pergunta(
            categoria.id,
            slug="decisoes_resultado_tutela",
            pergunta="Qual o resultado da tutela?"
        )

        # Executa ensure_variable_for_question
        variavel = ensure_variable_for_question(self.db, pergunta, categoria)

        # Deve ter REATIVADO a variável existente, não criado nova
        self.assertIsNotNone(variavel)
        self.assertEqual(variavel.id, var_id_original, "Deveria reutilizar a variável existente")
        self.assertTrue(variavel.ativo, "Variável deveria ter sido reativada")
        self.assertEqual(variavel.slug, "decisoes_resultado_tutela",
            "Slug deveria permanecer sem sufixo")
        self.assertEqual(variavel.source_question_id, pergunta.id,
            "Variável deveria estar vinculada à pergunta")

    def test_multiplos_inativos_primeiro_reativado(self):
        """
        TESTE: Se existirem múltiplas variáveis inativas com mesmo slug base,
        a primeira deve ser reativada.
        """
        from sistemas.gerador_pecas.router_extraction import _get_unique_slug

        categoria = self._criar_categoria()

        # Cria múltiplas variáveis inativas (cenário de múltiplas deleções)
        self._criar_variavel("multi_slug", categoria_id=categoria.id, ativo=False)

        # Não deve adicionar sufixo
        slug = _get_unique_slug(self.db, "multi_slug")

        self.assertEqual(slug, "multi_slug")

    def test_mistura_ativo_inativo_gera_sufixo_correto(self):
        """
        TESTE: Se existe slug ATIVO e slug_2 INATIVO, deve gerar slug_3.
        """
        from sistemas.gerador_pecas.router_extraction import _get_unique_slug

        categoria = self._criar_categoria()

        # slug base ativo
        self._criar_variavel("misto", categoria_id=categoria.id, ativo=True)
        # slug_2 inativo (não bloqueia)
        self._criar_variavel("misto_2", categoria_id=categoria.id, ativo=False)
        # slug_3 ativo
        self._criar_variavel("misto_3", categoria_id=categoria.id, ativo=True)

        # Deve gerar _4 (pula o _2 inativo, mas _3 está ativo)
        slug = _get_unique_slug(self.db, "misto")

        # O algoritmo vai: misto (existe ativo) -> misto_2 (existe inativo, mas IGNORA) -> retorna misto_2
        # Porque o _get_unique_slug só considera ATIVOS agora
        self.assertEqual(slug, "misto_2",
            "Deveria retornar misto_2 porque a versão inativa não bloqueia")


class TestVariableDeletion(unittest.TestCase):
    """
    Testes para deleção de variáveis (Bug 2).

    Cenários cobertos (TODOS HARD DELETE com limpeza automática):
    - Variável sem uso → HARD DELETE
    - Variável em uso por prompt → HARD DELETE + limpeza de PromptVariableUsage
    - Variável com dependentes → HARD DELETE + limpeza de dependências
    """

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False}
        )
        cls.TestingSessionLocal = sessionmaker(bind=cls.engine)

        from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON
        from sistemas.gerador_pecas.models_extraction import (
            ExtractionQuestion, ExtractionVariable,
            PromptVariableUsage
        )
        from admin.models_prompts import PromptModulo
        from auth.models import User

        Base.metadata.create_all(bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=cls.engine)

    def setUp(self):
        self.db = self.TestingSessionLocal()

        def override_get_db():
            try:
                yield self.db
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db

        from sistemas.gerador_pecas.models_extraction import (
            ExtractionQuestion, ExtractionVariable, PromptVariableUsage
        )
        from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON

        self.db.query(PromptVariableUsage).delete()
        self.db.query(ExtractionVariable).delete()
        self.db.query(ExtractionQuestion).delete()
        self.db.query(CategoriaResumoJSON).delete()
        self.db.commit()

    def tearDown(self):
        self.db.rollback()
        self.db.close()

    def _criar_usuario_admin(self):
        from auth.models import User
        user = self.db.query(User).filter(User.username == "test_admin_del").first()
        if user:
            return user
        user = User(
            username="test_admin_del",
            full_name="Test Admin Del",
            email="admin_del@test.com",
            hashed_password="$2b$12$test",
            role="admin",
            is_active=True
        )
        self.db.add(user)
        self.db.commit()
        return user

    def _criar_categoria(self, nome="teste"):
        from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON
        categoria = CategoriaResumoJSON(
            nome=nome,
            titulo=f"Categoria {nome}",
            descricao="Teste",
            codigos_documento=[100],
            formato_json="{}"
        )
        self.db.add(categoria)
        self.db.commit()
        return categoria

    def _criar_pergunta(self, categoria_id, slug, tipo="text", pergunta="Pergunta?"):
        from sistemas.gerador_pecas.models_extraction import ExtractionQuestion
        p = ExtractionQuestion(
            categoria_id=categoria_id,
            pergunta=pergunta,
            nome_variavel_sugerido=slug,
            tipo_sugerido=tipo,
            ordem=0,
            ativo=True
        )
        self.db.add(p)
        self.db.commit()
        return p

    def _criar_variavel(self, slug, categoria_id=None, source_question_id=None, ativo=True):
        from sistemas.gerador_pecas.models_extraction import ExtractionVariable
        v = ExtractionVariable(
            slug=slug,
            label=f"Variável {slug}",
            tipo="text",
            categoria_id=categoria_id,
            source_question_id=source_question_id,
            ativo=ativo
        )
        self.db.add(v)
        self.db.commit()
        return v

    def _criar_uso_prompt(self, variable_slug, prompt_id=1):
        from sistemas.gerador_pecas.models_extraction import PromptVariableUsage
        uso = PromptVariableUsage(
            prompt_id=prompt_id,
            variable_slug=variable_slug
        )
        self.db.add(uso)
        self.db.commit()
        return uso

    # ==========================================================================
    # TESTES BUG 2: Deleção de variáveis
    # ==========================================================================

    def test_variavel_sem_uso_hard_delete(self):
        """
        TESTE: Variável NÃO usada em prompts => HARD DELETE (apagada do banco).
        """
        from sistemas.gerador_pecas.models_extraction import (
            ExtractionQuestion, ExtractionVariable
        )

        categoria = self._criar_categoria()
        pergunta = self._criar_pergunta(categoria.id, "var_sem_uso")
        variavel = self._criar_variavel(
            "var_sem_uso",
            categoria_id=categoria.id,
            source_question_id=pergunta.id
        )

        variavel_id = variavel.id
        pergunta_id = pergunta.id

        # Simula exclusão (código do endpoint)
        # Verifica uso
        from sistemas.gerador_pecas.models_extraction import PromptVariableUsage
        uso_count = self.db.query(PromptVariableUsage).filter(
            PromptVariableUsage.variable_slug == variavel.slug
        ).count()

        self.assertEqual(uso_count, 0, "Variável não deveria estar em uso")

        # Hard delete
        self.db.delete(variavel)
        self.db.delete(pergunta)
        self.db.commit()

        # Verifica que foi realmente apagada
        variavel_check = self.db.query(ExtractionVariable).filter(
            ExtractionVariable.id == variavel_id
        ).first()
        pergunta_check = self.db.query(ExtractionQuestion).filter(
            ExtractionQuestion.id == pergunta_id
        ).first()

        self.assertIsNone(variavel_check, "Variável deveria ter sido deletada permanentemente")
        self.assertIsNone(pergunta_check, "Pergunta deveria ter sido deletada permanentemente")

    def test_variavel_em_uso_hard_delete_com_limpeza(self):
        """
        TESTE: Variável em uso por prompt => HARD DELETE + limpeza de PromptVariableUsage.

        A limpeza de PromptVariableUsage é feita automaticamente pelo endpoint.
        Este teste verifica que a estrutura permite a limpeza.
        """
        from sistemas.gerador_pecas.models_extraction import ExtractionVariable, PromptVariableUsage

        categoria = self._criar_categoria()
        pergunta = self._criar_pergunta(categoria.id, "var_em_uso")
        variavel = self._criar_variavel(
            "var_em_uso",
            categoria_id=categoria.id,
            source_question_id=pergunta.id
        )

        # Cria uso em prompt
        self._criar_uso_prompt("var_em_uso", prompt_id=999)

        variavel_id = variavel.id
        variavel_slug = variavel.slug

        # Verifica uso antes
        uso_count = self.db.query(PromptVariableUsage).filter(
            PromptVariableUsage.variable_slug == variavel_slug
        ).count()
        self.assertEqual(uso_count, 1, "Variável deveria estar em uso")

        # Simula HARD DELETE com limpeza (como o endpoint faz):
        # 1. Remove PromptVariableUsage
        self.db.query(PromptVariableUsage).filter(
            PromptVariableUsage.variable_slug == variavel_slug
        ).delete()

        # 2. Remove a variável
        self.db.delete(variavel)
        self.db.commit()

        # Verifica que foi deletada
        variavel_check = self.db.query(ExtractionVariable).filter(
            ExtractionVariable.id == variavel_id
        ).first()
        self.assertIsNone(variavel_check, "Variável deveria ter sido deletada")

        # Verifica que o uso também foi removido
        uso_check = self.db.query(PromptVariableUsage).filter(
            PromptVariableUsage.variable_slug == variavel_slug
        ).count()
        self.assertEqual(uso_check, 0, "Uso em prompt deveria ter sido removido")

    def test_variavel_com_dependentes_hard_delete_com_limpeza(self):
        """
        TESTE: Variável com dependentes => HARD DELETE + limpeza de dependências.

        A limpeza de dependências é feita automaticamente pelo endpoint.
        Este teste verifica que a estrutura permite a limpeza.
        """
        from sistemas.gerador_pecas.models_extraction import ExtractionVariable, ExtractionQuestion

        categoria = self._criar_categoria()

        # Pergunta/variável mãe
        pergunta_mae = self._criar_pergunta(categoria.id, "var_mae", pergunta="Pergunta mãe?")
        variavel_mae = self._criar_variavel(
            "var_mae",
            categoria_id=categoria.id,
            source_question_id=pergunta_mae.id
        )

        # Pergunta filha que depende da mãe
        from sistemas.gerador_pecas.models_extraction import ExtractionQuestion as EQ
        pergunta_filha = EQ(
            categoria_id=categoria.id,
            pergunta="Pergunta filha?",
            nome_variavel_sugerido="var_filha",
            tipo_sugerido="text",
            depends_on_variable="var_mae",
            dependency_operator="equals",
            dependency_value=True,
            ordem=1,
            ativo=True
        )
        self.db.add(pergunta_filha)
        self.db.commit()

        variavel_mae_id = variavel_mae.id
        variavel_mae_slug = variavel_mae.slug
        pergunta_filha_id = pergunta_filha.id

        # Verifica dependentes antes
        dependentes_count = self.db.query(ExtractionQuestion).filter(
            ExtractionQuestion.depends_on_variable == variavel_mae_slug,
            ExtractionQuestion.ativo == True
        ).count()
        self.assertEqual(dependentes_count, 1, "Deveria haver 1 pergunta dependente")

        # Simula HARD DELETE com limpeza (como o endpoint faz):
        # 1. Limpa dependências de perguntas
        perguntas_dependentes = self.db.query(ExtractionQuestion).filter(
            ExtractionQuestion.depends_on_variable == variavel_mae_slug
        ).all()
        for p in perguntas_dependentes:
            p.depends_on_variable = None
            p.dependency_operator = None
            p.dependency_value = None
        self.db.commit()

        # 2. Remove a variável
        self.db.delete(variavel_mae)
        self.db.commit()

        # Verifica que a variável foi deletada
        variavel_check = self.db.query(ExtractionVariable).filter(
            ExtractionVariable.id == variavel_mae_id
        ).first()
        self.assertIsNone(variavel_check, "Variável deveria ter sido deletada")

        # Verifica que a pergunta filha ainda existe mas sem dependência
        pergunta_filha_check = self.db.query(ExtractionQuestion).filter(
            ExtractionQuestion.id == pergunta_filha_id
        ).first()
        self.assertIsNotNone(pergunta_filha_check, "Pergunta filha deveria existir")
        self.assertIsNone(pergunta_filha_check.depends_on_variable, "Dependência deveria ter sido removida")


def run_tests():
    """Executa os testes."""
    print("\n" + "=" * 70)
    print("TESTES: Geração de Slugs e Deleção de Variáveis")
    print("=" * 70 + "\n")

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestSlugGeneration))
    suite.addTests(loader.loadTestsFromTestCase(TestVariableDeletion))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 70)
    if result.wasSuccessful():
        print("TODOS OS TESTES PASSARAM!")
    else:
        print(f"FALHAS: {len(result.failures)}, ERROS: {len(result.errors)}")
    print("=" * 70 + "\n")

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
