# tests/test_categorias_resumo_json.py
"""
Testes automatizados para o sistema de categorias-resumo-json.

Este arquivo cobre os seguintes cenários obrigatórios:

1. ATUALIZAR JSON (sem recriar variáveis)
   - [ ] Atualizar JSON sem alterações não recria variáveis
   - [ ] Atualizar JSON preserva IDs das variáveis existentes
   - [ ] Alterar dependências atualiza o JSON sem recriar variáveis
   - [ ] Alterar slug/tipo/options atualiza apenas os campos afetados

2. CRIAÇÃO DE PERGUNTA/VARIÁVEL
   - [ ] Criar pergunta com slug cria variável imediatamente no BD
   - [ ] Variável recém-criada pode ser usada em dependências
   - [ ] Slug duplicado é bloqueado
   - [ ] Alterar slug não cria variável duplicada

3. REORDENAÇÃO COM IA
   - [ ] Pedido principal e dependentes permanecem juntos
   - [ ] IA não pode separar pai e filhos
   - [ ] Árvores com múltiplos níveis mantêm ordem consistente
"""

import unittest
import json
import sys
import os
import asyncio

# Adiciona diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime

from database.connection import Base, get_db
from main import app


class TestCategoriasResumoJSONBase(unittest.TestCase):
    """Classe base com fixtures comuns para todos os testes."""

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

        # Limpa dados entre testes
        from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON
        from sistemas.gerador_pecas.models_extraction import ExtractionQuestion, ExtractionVariable

        self.db.query(ExtractionVariable).delete()
        self.db.query(ExtractionQuestion).delete()
        self.db.query(CategoriaResumoJSON).delete()
        self.db.commit()

    def tearDown(self):
        """Limpa sessão."""
        self.db.rollback()
        self.db.close()

    def _criar_usuario_admin(self):
        """Cria usuário admin para testes."""
        from auth.models import User

        user = self.db.query(User).filter(User.username == "test_admin").first()
        if user:
            return user

        user = User(
            username="test_admin",
            full_name="Test Admin",
            email="admin@test.com",
            hashed_password="$2b$12$test",
            role="admin",
            is_active=True
        )
        self.db.add(user)
        self.db.commit()
        return user

    def _criar_categoria(self, nome="teste_categoria", formato_json=None):
        """Cria categoria de teste."""
        from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON

        categoria = CategoriaResumoJSON(
            nome=nome,
            titulo=f"Categoria {nome}",
            descricao="Categoria de teste",
            codigos_documento=[100],
            formato_json=json.dumps(formato_json) if formato_json else "{}"
        )
        self.db.add(categoria)
        self.db.commit()
        return categoria

    def _criar_pergunta(self, categoria_id, slug=None, tipo="text", pergunta="Pergunta teste",
                        depends_on=None, dependency_operator=None, dependency_value=None,
                        opcoes=None, ordem=0, ativo=True):
        """Cria pergunta de extração."""
        from sistemas.gerador_pecas.models_extraction import ExtractionQuestion

        p = ExtractionQuestion(
            categoria_id=categoria_id,
            pergunta=pergunta,
            nome_variavel_sugerido=slug,
            tipo_sugerido=tipo,
            depends_on_variable=depends_on,
            dependency_operator=dependency_operator,
            dependency_value=dependency_value,
            opcoes_sugeridas=opcoes,
            ordem=ordem,
            ativo=ativo
        )
        self.db.add(p)
        self.db.commit()
        return p

    def _criar_variavel(self, slug, tipo="text", categoria_id=None, source_question_id=None):
        """Cria variável de extração."""
        from sistemas.gerador_pecas.models_extraction import ExtractionVariable

        v = ExtractionVariable(
            slug=slug,
            label=slug.replace("_", " ").title(),
            tipo=tipo,
            categoria_id=categoria_id,
            source_question_id=source_question_id,
            ativo=True
        )
        self.db.add(v)
        self.db.commit()
        return v

    def _executar_sincronizacao(self, categoria_id, user):
        """Executa o endpoint de sincronização diretamente (sem HTTP)."""
        from sistemas.gerador_pecas.router_extraction import sincronizar_json_sem_ia

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                sincronizar_json_sem_ia(categoria_id, self.db, user)
            )
            return result
        finally:
            loop.close()


# =============================================================================
# TESTES: ATUALIZAR JSON (SEM RECRIAR VARIÁVEIS)
# =============================================================================

class TestAtualizarJSONSemRecriarVariaveis(TestCategoriasResumoJSONBase):
    """
    Testes para verificar que o botão "Atualizar JSON" não recria variáveis.
    """

    def test_atualizar_json_sem_alteracoes_nao_recria_variaveis(self):
        """
        TESTE: Atualizar JSON sem alterações não recria variáveis.

        Cenário:
        1. Categoria com perguntas e variáveis existentes
        2. JSON já sincronizado
        3. Executar sincronização
        4. IDs das variáveis devem permanecer inalterados
        """
        from sistemas.gerador_pecas.models_extraction import ExtractionVariable

        user = self._criar_usuario_admin()

        # JSON inicial sincronizado
        json_inicial = {
            "nome_autor": {"type": "text", "description": "Qual o nome do autor?"},
            "valor_causa": {"type": "number", "description": "Qual o valor da causa?"}
        }
        categoria = self._criar_categoria("test_sem_alteracao", json_inicial)

        # Cria perguntas idênticas ao JSON
        p1 = self._criar_pergunta(categoria.id, "nome_autor", "text", "Qual o nome do autor?", ordem=0)
        p2 = self._criar_pergunta(categoria.id, "valor_causa", "number", "Qual o valor da causa?", ordem=1)

        # Cria variáveis vinculadas
        v1 = self._criar_variavel("nome_autor", "text", categoria.id, p1.id)
        v2 = self._criar_variavel("valor_causa", "number", categoria.id, p2.id)

        # Guarda IDs originais
        id_original_v1 = v1.id
        id_original_v2 = v2.id

        # Executa sincronização
        result = self._executar_sincronizacao(categoria.id, user)

        # Verifica que sincronização foi bem sucedida
        self.assertTrue(result.success)
        self.assertFalse(result.houve_alteracao,
            "Não deveria haver alteração quando JSON está sincronizado")

        # Verifica que IDs das variáveis permanecem iguais
        self.db.refresh(v1)
        self.db.refresh(v2)
        self.assertEqual(v1.id, id_original_v1, "ID da variável 1 não deveria mudar")
        self.assertEqual(v2.id, id_original_v2, "ID da variável 2 não deveria mudar")

        # Verifica quantidade de variáveis no BD
        variaveis = self.db.query(ExtractionVariable).filter(
            ExtractionVariable.categoria_id == categoria.id
        ).all()
        self.assertEqual(len(variaveis), 2, "Não deveria criar variáveis extras")

    def test_atualizar_json_preserva_ids_variaveis_existentes(self):
        """
        TESTE: Atualizar JSON preserva IDs das variáveis existentes.

        Cenário:
        1. Variáveis existentes com IDs específicos
        2. Executar múltiplas sincronizações
        3. IDs devem permanecer estáveis
        """
        from sistemas.gerador_pecas.models_extraction import ExtractionVariable

        user = self._criar_usuario_admin()
        categoria = self._criar_categoria("test_preserva_ids")

        # Cria pergunta e variável
        p1 = self._criar_pergunta(categoria.id, "campo_teste", "text", "Pergunta teste", ordem=0)
        v1 = self._criar_variavel("campo_teste", "text", categoria.id, p1.id)
        id_original = v1.id

        # Executa múltiplas sincronizações
        for i in range(3):
            result = self._executar_sincronizacao(categoria.id, user)
            self.assertTrue(result.success)

            # Verifica ID permanece igual após cada sincronização
            variavel = self.db.query(ExtractionVariable).filter(
                ExtractionVariable.slug == "campo_teste"
            ).first()
            self.assertEqual(variavel.id, id_original,
                f"ID da variável mudou após sincronização {i+1}")

    def test_alterar_dependencias_atualiza_json_sem_recriar_variaveis(self):
        """
        TESTE: Alterar dependências atualiza o JSON sem recriar variáveis.

        Cenário:
        1. Perguntas sem dependência
        2. Adicionar dependência
        3. Sincronizar
        4. JSON atualizado, variáveis preservadas
        """
        from sistemas.gerador_pecas.models_extraction import ExtractionVariable

        user = self._criar_usuario_admin()

        json_inicial = {
            "pergunta_pai": {"type": "boolean", "description": "Pergunta pai?"},
            "pergunta_filho": {"type": "text", "description": "Pergunta filho?"}
        }
        categoria = self._criar_categoria("test_deps_preserva", json_inicial)

        # Cria perguntas - filho SEM dependência inicialmente
        p1 = self._criar_pergunta(categoria.id, "pergunta_pai", "boolean", "Pergunta pai?", ordem=0)
        p2 = self._criar_pergunta(categoria.id, "pergunta_filho", "text", "Pergunta filho?", ordem=1)

        # Cria variáveis
        v1 = self._criar_variavel("pergunta_pai", "boolean", categoria.id, p1.id)
        v2 = self._criar_variavel("pergunta_filho", "text", categoria.id, p2.id)
        id_v2_original = v2.id

        # Adiciona dependência ao filho
        p2.depends_on_variable = "pergunta_pai"
        p2.dependency_operator = "equals"
        p2.dependency_value = True
        self.db.commit()

        # Executa sincronização
        result = self._executar_sincronizacao(categoria.id, user)

        # Verifica que houve alteração no JSON
        self.assertTrue(result.success)
        self.assertTrue(result.houve_alteracao,
            "Deveria detectar alteração ao adicionar dependência")

        # Verifica que JSON tem dependência
        self.assertTrue(result.schema_json["pergunta_filho"].get("conditional"))
        self.assertEqual(result.schema_json["pergunta_filho"].get("depends_on"), "pergunta_pai")

        # Verifica que ID da variável permanece igual
        self.db.refresh(v2)
        self.assertEqual(v2.id, id_v2_original,
            "ID da variável não deveria mudar ao adicionar dependência")

    def test_alterar_slug_tipo_options_atualiza_apenas_campos_afetados(self):
        """
        TESTE: Alterar slug/tipo/options atualiza apenas os campos afetados.

        Cenário:
        1. Variável existente com tipo "text"
        2. Alterar para "choice" com options
        3. Sincronizar
        4. Campo atualizado, ID preservado
        """
        from sistemas.gerador_pecas.models_extraction import ExtractionVariable

        user = self._criar_usuario_admin()

        json_inicial = {
            "tipo_acao": {"type": "text", "description": "Tipo de ação?"}
        }
        categoria = self._criar_categoria("test_atualiza_campos", json_inicial)

        # Cria pergunta e variável
        p1 = self._criar_pergunta(categoria.id, "tipo_acao", "text", "Tipo de ação?", ordem=0)
        v1 = self._criar_variavel("tipo_acao", "text", categoria.id, p1.id)
        id_original = v1.id
        criado_em_original = v1.criado_em

        # Altera tipo e adiciona opções
        p1.tipo_sugerido = "choice"
        p1.opcoes_sugeridas = ["Civil", "Criminal", "Trabalhista"]
        self.db.commit()

        # Executa sincronização
        result = self._executar_sincronizacao(categoria.id, user)

        # Verifica JSON atualizado
        self.assertTrue(result.success)
        self.assertEqual(result.schema_json["tipo_acao"]["type"], "choice")
        self.assertIn("Civil", result.schema_json["tipo_acao"]["options"])

        # Verifica que ID e data de criação permanecem iguais
        variavel = self.db.query(ExtractionVariable).filter(
            ExtractionVariable.slug == "tipo_acao"
        ).first()
        self.assertEqual(variavel.id, id_original,
            "ID da variável não deveria mudar ao alterar tipo")


# =============================================================================
# TESTES: CRIAÇÃO DE PERGUNTA/VARIÁVEL
# =============================================================================

class TestCriacaoPerguntaVariavel(TestCategoriasResumoJSONBase):
    """
    Testes para verificar criação automática de variáveis ao definir slug.
    """

    def test_criar_pergunta_com_slug_cria_variavel_imediatamente(self):
        """
        TESTE: Criar pergunta com slug cria variável imediatamente no BD.

        Cenário:
        1. Criar pergunta com slug definido
        2. Variável deve existir no BD imediatamente
        """
        from sistemas.gerador_pecas.models_extraction import ExtractionVariable
        from sistemas.gerador_pecas.router_extraction import ensure_variable_for_question

        user = self._criar_usuario_admin()
        categoria = self._criar_categoria("test_cria_var")

        # Cria pergunta com slug e tipo
        p1 = self._criar_pergunta(
            categoria.id,
            slug="minha_variavel",
            tipo="text",
            pergunta="Qual o valor?"
        )

        # Chama função para garantir variável
        variavel = ensure_variable_for_question(self.db, p1, categoria)
        self.db.commit()

        # Verifica que variável foi criada
        self.assertIsNotNone(variavel, "Variável deveria ser criada")
        self.assertEqual(variavel.slug, "minha_variavel")

        # Verifica no BD
        variavel_bd = self.db.query(ExtractionVariable).filter(
            ExtractionVariable.slug == "minha_variavel"
        ).first()
        self.assertIsNotNone(variavel_bd, "Variável deveria existir no BD")
        self.assertEqual(variavel_bd.source_question_id, p1.id)

    def test_criar_pergunta_com_slug_sem_tipo_usa_text_como_default(self):
        """
        TESTE: Criar pergunta com slug mas sem tipo usa "text" como default.

        Cenário:
        1. Criar pergunta com slug mas sem tipo
        2. Variável deve ser criada com tipo "text"
        """
        from sistemas.gerador_pecas.models_extraction import ExtractionVariable, ExtractionQuestion
        from sistemas.gerador_pecas.router_extraction import ensure_variable_for_question

        user = self._criar_usuario_admin()
        categoria = self._criar_categoria("test_tipo_default")

        # Cria pergunta com slug mas SEM tipo
        p1 = ExtractionQuestion(
            categoria_id=categoria.id,
            pergunta="Qual o nome?",
            nome_variavel_sugerido="nome_campo",
            tipo_sugerido=None,  # Sem tipo
            ativo=True,
            ordem=0
        )
        self.db.add(p1)
        self.db.flush()

        # Chama função para garantir variável
        variavel = ensure_variable_for_question(self.db, p1, categoria, criar_sem_tipo=True)
        self.db.commit()

        # Verifica que variável foi criada com tipo text
        self.assertIsNotNone(variavel, "Variável deveria ser criada mesmo sem tipo")
        self.assertEqual(variavel.tipo, "text", "Tipo default deveria ser 'text'")

    def test_variavel_recem_criada_pode_ser_usada_em_dependencias(self):
        """
        TESTE: Variável recém-criada pode ser usada em dependências.

        Cenário:
        1. Criar pergunta pai com slug
        2. Criar pergunta filho que depende do pai
        3. Ambas devem ter variáveis criadas
        4. Dependência deve funcionar
        """
        from sistemas.gerador_pecas.models_extraction import ExtractionVariable
        from sistemas.gerador_pecas.router_extraction import ensure_variable_for_question

        user = self._criar_usuario_admin()
        categoria = self._criar_categoria("test_dependencia_imediata")

        # Cria pergunta pai
        p_pai = self._criar_pergunta(
            categoria.id,
            slug="pergunta_pai",
            tipo="boolean",
            pergunta="É verdade?",
            ordem=0
        )

        # Garante variável do pai
        v_pai = ensure_variable_for_question(self.db, p_pai, categoria)
        self.db.commit()

        # Cria pergunta filho que depende do pai
        p_filho = self._criar_pergunta(
            categoria.id,
            slug="pergunta_filho",
            tipo="text",
            pergunta="Detalhes?",
            depends_on="pergunta_pai",
            dependency_operator="equals",
            dependency_value=True,
            ordem=1
        )

        # Garante variável do filho
        v_filho = ensure_variable_for_question(self.db, p_filho, categoria)
        self.db.commit()

        # Verifica que ambas variáveis existem
        self.assertIsNotNone(v_pai)
        self.assertIsNotNone(v_filho)

        # Verifica dependência no filho
        self.assertTrue(v_filho.is_conditional)
        self.assertEqual(v_filho.depends_on_variable, "pergunta_pai")

    def test_slug_duplicado_e_bloqueado(self):
        """
        TESTE: Slug duplicado é bloqueado.

        Cenário:
        1. Criar pergunta com slug "teste"
        2. Tentar criar outra pergunta com mesmo slug
        3. Deve falhar com erro
        """
        from fastapi import HTTPException
        import asyncio

        user = self._criar_usuario_admin()
        categoria = self._criar_categoria("test_slug_duplicado")

        # Cria primeira pergunta
        p1 = self._criar_pergunta(
            categoria.id,
            slug="slug_unico",
            tipo="text",
            pergunta="Primeira pergunta",
            ordem=0
        )

        # Tenta criar segunda pergunta com mesmo slug via endpoint
        from sistemas.gerador_pecas.router_extraction import criar_pergunta
        from sistemas.gerador_pecas.router_extraction import ExtractionQuestionCreate

        data = ExtractionQuestionCreate(
            categoria_id=categoria.id,
            pergunta="Segunda pergunta",
            nome_variavel_sugerido="slug_unico",  # Mesmo slug!
            tipo_sugerido="text"
        )

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            with self.assertRaises(HTTPException) as context:
                loop.run_until_complete(criar_pergunta(data, self.db, user))

            self.assertEqual(context.exception.status_code, 400)
            self.assertIn("slug", context.exception.detail.lower())
        finally:
            loop.close()

    def test_alterar_slug_nao_cria_variavel_duplicada(self):
        """
        TESTE: Alterar slug não cria variável duplicada.

        Cenário:
        1. Pergunta com slug "antigo"
        2. Alterar slug para "novo"
        3. Deve atualizar, não criar duplicata
        """
        from sistemas.gerador_pecas.models_extraction import ExtractionVariable
        from sistemas.gerador_pecas.router_extraction import ensure_variable_for_question

        user = self._criar_usuario_admin()
        categoria = self._criar_categoria("test_alterar_slug")

        # Cria pergunta com slug inicial
        p1 = self._criar_pergunta(
            categoria.id,
            slug="slug_antigo",
            tipo="text",
            pergunta="Minha pergunta",
            ordem=0
        )

        # Cria variável vinculada
        v1 = ensure_variable_for_question(self.db, p1, categoria)
        self.db.commit()
        id_variavel_original = v1.id

        # Conta variáveis antes
        count_antes = self.db.query(ExtractionVariable).filter(
            ExtractionVariable.categoria_id == categoria.id
        ).count()

        # Altera slug da pergunta
        p1.nome_variavel_sugerido = "slug_novo"
        self.db.commit()

        # Chama ensure_variable novamente
        v2 = ensure_variable_for_question(self.db, p1, categoria)
        self.db.commit()

        # Verifica que é a mesma variável (preserva vínculo por source_question_id)
        self.assertEqual(v2.id, id_variavel_original,
            "Deveria ser a mesma variável, não criar nova")

        # Verifica que não criou duplicata
        count_depois = self.db.query(ExtractionVariable).filter(
            ExtractionVariable.categoria_id == categoria.id
        ).count()
        self.assertEqual(count_antes, count_depois,
            "Não deveria criar variável duplicada")


# =============================================================================
# TESTES: REORDENAÇÃO COM IA
# =============================================================================

class TestReordenacaoComIA(TestCategoriasResumoJSONBase):
    """
    Testes para verificar que a reordenação mantém hierarquia pai-filho.
    """

    def test_pedido_principal_e_dependentes_permanecem_juntos(self):
        """
        TESTE: Pedido principal e dependentes permanecem juntos.

        Cenário:
        1. Pergunta pai e filho dependente
        2. IA sugere ordem que separa
        3. Correção determinística deve juntar
        """
        from sistemas.gerador_pecas.router_extraction import _garantir_hierarquia_dependencias

        # Simula perguntas
        class PerguntaMock:
            def __init__(self, id, slug, depends_on=None):
                self.id = id
                self.nome_variavel_sugerido = slug
                self.depends_on_variable = depends_on
                self.pergunta = f"Pergunta {id}"

        perguntas = [
            PerguntaMock(1, "pai", None),
            PerguntaMock(2, "filho", "pai"),
            PerguntaMock(3, "outro", None),
        ]

        # Ordem sugerida pela IA (errada - separa pai e filho)
        ordem_ia = [
            {"id": 1, "pergunta": "Pergunta 1"},
            {"id": 3, "pergunta": "Pergunta 3"},  # "outro" entre pai e filho
            {"id": 2, "pergunta": "Pergunta 2"},
        ]

        # Aplica correção
        ordem_corrigida = _garantir_hierarquia_dependencias(ordem_ia, perguntas)

        # Verifica que filho está imediatamente após pai
        ids_ordenados = [item["id"] for item in ordem_corrigida]
        idx_pai = ids_ordenados.index(1)
        idx_filho = ids_ordenados.index(2)

        self.assertEqual(idx_filho, idx_pai + 1,
            "Filho deve estar imediatamente após o pai")

    def test_ia_nao_pode_separar_pai_e_filhos(self):
        """
        TESTE: IA não pode separar pai e filhos.

        Cenário:
        1. Pai com múltiplos filhos
        2. IA sugere ordem que dispersa filhos
        3. Todos filhos devem ficar junto ao pai
        """
        from sistemas.gerador_pecas.router_extraction import _garantir_hierarquia_dependencias

        class PerguntaMock:
            def __init__(self, id, slug, depends_on=None):
                self.id = id
                self.nome_variavel_sugerido = slug
                self.depends_on_variable = depends_on
                self.pergunta = f"Pergunta {id}"

        perguntas = [
            PerguntaMock(1, "pai", None),
            PerguntaMock(2, "filho_a", "pai"),
            PerguntaMock(3, "filho_b", "pai"),
            PerguntaMock(4, "outro", None),
        ]

        # Ordem sugerida pela IA (errada - dispersa filhos)
        ordem_ia = [
            {"id": 1, "pergunta": "Pergunta 1"},  # pai
            {"id": 4, "pergunta": "Pergunta 4"},  # outro (intercalado)
            {"id": 2, "pergunta": "Pergunta 2"},  # filho_a
            {"id": 3, "pergunta": "Pergunta 3"},  # filho_b
        ]

        # Aplica correção
        ordem_corrigida = _garantir_hierarquia_dependencias(ordem_ia, perguntas)

        # Verifica que todos os filhos estão logo após o pai
        ids_ordenados = [item["id"] for item in ordem_corrigida]
        idx_pai = ids_ordenados.index(1)
        idx_filho_a = ids_ordenados.index(2)
        idx_filho_b = ids_ordenados.index(3)
        idx_outro = ids_ordenados.index(4)

        # Filhos devem estar nas posições idx_pai+1 e idx_pai+2
        self.assertIn(idx_filho_a, [idx_pai + 1, idx_pai + 2],
            "filho_a deve estar logo após o pai")
        self.assertIn(idx_filho_b, [idx_pai + 1, idx_pai + 2],
            "filho_b deve estar logo após o pai")

        # "outro" deve estar após os filhos
        self.assertGreater(idx_outro, max(idx_filho_a, idx_filho_b),
            "'outro' deve estar após os filhos")

    def test_arvores_multiplos_niveis_mantem_ordem_consistente(self):
        """
        TESTE: Árvores com múltiplos níveis mantêm ordem consistente.

        Cenário:
        1. Pai -> Filho -> Neto (3 níveis)
        2. IA sugere ordem que quebra hierarquia
        3. Correção mantém árvore: Pai -> Filho -> Neto
        """
        from sistemas.gerador_pecas.router_extraction import _garantir_hierarquia_dependencias

        class PerguntaMock:
            def __init__(self, id, slug, depends_on=None):
                self.id = id
                self.nome_variavel_sugerido = slug
                self.depends_on_variable = depends_on
                self.pergunta = f"Pergunta {id}"

        perguntas = [
            PerguntaMock(1, "avo", None),
            PerguntaMock(2, "pai", "avo"),
            PerguntaMock(3, "filho", "pai"),
            PerguntaMock(4, "outro", None),
        ]

        # Ordem sugerida pela IA (totalmente errada)
        ordem_ia = [
            {"id": 4, "pergunta": "Pergunta 4"},  # outro
            {"id": 3, "pergunta": "Pergunta 3"},  # filho (antes do pai!)
            {"id": 1, "pergunta": "Pergunta 1"},  # avo
            {"id": 2, "pergunta": "Pergunta 2"},  # pai
        ]

        # Aplica correção
        ordem_corrigida = _garantir_hierarquia_dependencias(ordem_ia, perguntas)

        # Verifica hierarquia mantida
        ids_ordenados = [item["id"] for item in ordem_corrigida]

        # Encontra posições
        idx_avo = ids_ordenados.index(1)
        idx_pai = ids_ordenados.index(2)
        idx_filho = ids_ordenados.index(3)

        # Verifica ordem: avô < pai < filho
        self.assertLess(idx_avo, idx_pai,
            "Avô deve vir antes do pai")
        self.assertLess(idx_pai, idx_filho,
            "Pai deve vir antes do filho")

        # Verifica que pai está logo após avô
        self.assertEqual(idx_pai, idx_avo + 1,
            "Pai deve estar imediatamente após o avô")

        # Verifica que filho está logo após pai
        self.assertEqual(idx_filho, idx_pai + 1,
            "Filho deve estar imediatamente após o pai")

    def test_sem_dependencias_preserva_ordem_ia(self):
        """
        TESTE: Sem dependências, preserva a ordem sugerida pela IA.

        Cenário:
        1. Perguntas sem dependências
        2. Ordem da IA deve ser preservada
        """
        from sistemas.gerador_pecas.router_extraction import _garantir_hierarquia_dependencias

        class PerguntaMock:
            def __init__(self, id, slug, depends_on=None):
                self.id = id
                self.nome_variavel_sugerido = slug
                self.depends_on_variable = depends_on
                self.pergunta = f"Pergunta {id}"

        perguntas = [
            PerguntaMock(1, "a", None),
            PerguntaMock(2, "b", None),
            PerguntaMock(3, "c", None),
        ]

        # Ordem sugerida pela IA
        ordem_ia = [
            {"id": 3, "pergunta": "Pergunta 3"},
            {"id": 1, "pergunta": "Pergunta 1"},
            {"id": 2, "pergunta": "Pergunta 2"},
        ]

        # Aplica correção
        ordem_corrigida = _garantir_hierarquia_dependencias(ordem_ia, perguntas)

        # Ordem deve ser preservada (sem dependências para corrigir)
        ids_ordenados = [item["id"] for item in ordem_corrigida]
        self.assertEqual(ids_ordenados, [3, 1, 2],
            "Ordem da IA deve ser preservada quando não há dependências")


# =============================================================================
# RUNNER
# =============================================================================

def run_tests():
    """Executa todos os testes."""
    print("\n" + "=" * 70)
    print("TESTES: Sistema de Categorias Resumo JSON")
    print("=" * 70 + "\n")

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Adiciona todas as classes de teste
    suite.addTests(loader.loadTestsFromTestCase(TestAtualizarJSONSemRecriarVariaveis))
    suite.addTests(loader.loadTestsFromTestCase(TestCriacaoPerguntaVariavel))
    suite.addTests(loader.loadTestsFromTestCase(TestReordenacaoComIA))

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
