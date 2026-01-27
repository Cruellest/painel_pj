# tests/ia_extracao_regras/backend/unit/test_slug_rename.py
"""
Testes para o servico de renomeacao de slugs de variaveis.

Cobre:
- Renomeacao simples de slug
- Propagacao para JSON da categoria
- Propagacao para regras deterministicas
- Propagacao para dependencias
- Validacao de slug duplicado
- Verificacao de consistencia
- Reparo de inconsistencias
"""

import unittest
import json
from datetime import datetime
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.connection import Base

# Models
from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON
from sistemas.gerador_pecas.models_extraction import (
    ExtractionVariable, ExtractionQuestion, PromptVariableUsage
)
from admin.models_prompts import PromptModulo, RegraDeterministicaTipoPeca
from admin.models_prompt_groups import PromptGroup, PromptSubgroup
from auth.models import User

# Services
from sistemas.gerador_pecas.services_slug_rename import (
    SlugRenameService, SlugConsistencyChecker, SlugRenameResult
)


class BaseSlugTestCase(unittest.TestCase):
    """Caso de teste base com configuracao de banco em memoria."""

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

    def _create_user(self, username="test_user", role="admin"):
        """Cria um usuario de teste."""
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

    def _create_categoria(self, nome="test_categoria", formato_json=None):
        """Cria uma categoria de teste."""
        if formato_json is None:
            formato_json = json.dumps({
                "variavel_teste": {"type": "text", "description": "Variavel de teste"}
            })

        categoria = CategoriaResumoJSON(
            nome=nome,
            titulo=nome.title(),
            formato_json=formato_json,
            ativo=True
        )
        self.db.add(categoria)
        self.db.flush()
        return categoria

    def _create_variavel(self, slug, categoria_id=None, ativo=True, **kwargs):
        """Cria uma variavel de extracao de teste."""
        variavel = ExtractionVariable(
            slug=slug,
            label=kwargs.get("label", slug.replace("_", " ").title()),
            descricao=kwargs.get("descricao"),
            tipo=kwargs.get("tipo", "text"),
            categoria_id=categoria_id,
            ativo=ativo,
            depends_on_variable=kwargs.get("depends_on_variable"),
            is_conditional=kwargs.get("is_conditional", False),
            source_question_id=kwargs.get("source_question_id")
        )
        self.db.add(variavel)
        self.db.flush()
        return variavel

    def _create_pergunta(self, categoria_id, nome_variavel_sugerido=None, **kwargs):
        """Cria uma pergunta de extracao de teste."""
        pergunta = ExtractionQuestion(
            categoria_id=categoria_id,
            pergunta=kwargs.get("pergunta", "Pergunta de teste?"),
            nome_variavel_sugerido=nome_variavel_sugerido,
            ativo=True
        )
        self.db.add(pergunta)
        self.db.flush()
        return pergunta

    def _create_prompt_modulo(self, nome="modulo_teste", regra_deterministica=None, **kwargs):
        """Cria um prompt modulo de teste."""
        modulo = PromptModulo(
            tipo="conteudo",
            nome=nome,
            titulo=nome.title(),
            conteudo="Conteudo de teste",
            regra_deterministica=regra_deterministica,
            ativo=True
        )
        self.db.add(modulo)
        self.db.flush()
        return modulo


class TestSlugRenameService(BaseSlugTestCase):
    """Testes para SlugRenameService"""

    def test_renomear_slug_simples(self):
        """Teste: renomear slug simples sem dependencias"""
        variavel = self._create_variavel("slug_antigo")
        self.db.commit()

        service = SlugRenameService(self.db)
        result = service.renomear(variavel.id, "slug_novo")

        self.assertTrue(result.success)
        self.assertEqual(result.old_slug, "slug_antigo")
        self.assertEqual(result.new_slug, "slug_novo")

        # Verifica que a variavel foi atualizada
        self.db.refresh(variavel)
        self.assertEqual(variavel.slug, "slug_novo")

    def test_renomear_slug_com_normalizacao(self):
        """Teste: slug com acentos e espacos e normalizado"""
        variavel = self._create_variavel("slug_antigo")
        self.db.commit()

        service = SlugRenameService(self.db)
        result = service.renomear(variavel.id, "Variável com Acentos!", normalizar=True)

        self.assertTrue(result.success)
        self.assertEqual(result.new_slug, "variavel_com_acentos")

    def test_renomear_slug_duplicado_falha(self):
        """Teste: nao permite renomear para slug ja existente"""
        variavel1 = self._create_variavel("slug_existente")
        variavel2 = self._create_variavel("slug_para_renomear")
        self.db.commit()

        service = SlugRenameService(self.db)
        result = service.renomear(variavel2.id, "slug_existente")

        self.assertFalse(result.success)
        self.assertIn("ja existe", result.error.lower())

    def test_renomear_mesmo_slug_noop(self):
        """Teste: renomear para mesmo slug nao faz nada"""
        variavel = self._create_variavel("mesmo_slug")
        self.db.commit()

        service = SlugRenameService(self.db)
        result = service.renomear(variavel.id, "mesmo_slug")

        self.assertTrue(result.success)
        self.assertIn("mesmo", result.detalhes[0].lower())

    def test_renomear_propaga_json_categoria(self):
        """Teste: renomear slug propaga para JSON da categoria"""
        formato_json = json.dumps({
            "slug_antigo": {"type": "text", "description": "Teste"}
        })
        categoria = self._create_categoria("cat_teste", formato_json)
        variavel = self._create_variavel("slug_antigo", categoria_id=categoria.id)
        self.db.commit()

        service = SlugRenameService(self.db)
        result = service.renomear(variavel.id, "slug_novo")

        self.assertTrue(result.success)
        self.assertTrue(result.categoria_json_atualizada)

        # Verifica que o JSON foi atualizado
        self.db.refresh(categoria)
        schema = json.loads(categoria.formato_json)
        self.assertNotIn("slug_antigo", schema)
        self.assertIn("slug_novo", schema)

    def test_renomear_propaga_pergunta(self):
        """Teste: renomear slug propaga para pergunta de origem"""
        categoria = self._create_categoria()
        pergunta = self._create_pergunta(categoria.id, nome_variavel_sugerido="slug_antigo")
        variavel = self._create_variavel(
            "slug_antigo",
            categoria_id=categoria.id,
            source_question_id=pergunta.id
        )
        self.db.commit()

        service = SlugRenameService(self.db)
        result = service.renomear(variavel.id, "slug_novo")

        self.assertTrue(result.success)
        self.assertEqual(result.perguntas_atualizadas, 1)

        # Verifica que a pergunta foi atualizada
        self.db.refresh(pergunta)
        self.assertEqual(pergunta.nome_variavel_sugerido, "slug_novo")

    def test_renomear_propaga_regra_deterministica(self):
        """Teste: renomear slug propaga para regras deterministicas"""
        regra = {
            "type": "condition",
            "variable": "slug_antigo",
            "operator": "equals",
            "value": True
        }
        modulo = self._create_prompt_modulo("modulo_teste", regra_deterministica=regra)
        variavel = self._create_variavel("slug_antigo")
        self.db.commit()

        service = SlugRenameService(self.db)
        result = service.renomear(variavel.id, "slug_novo")

        self.assertTrue(result.success)
        self.assertEqual(result.prompts_atualizados, 1)

        # Verifica que a regra foi atualizada
        self.db.refresh(modulo)
        self.assertEqual(modulo.regra_deterministica["variable"], "slug_novo")

    def test_renomear_propaga_regra_composta(self):
        """Teste: renomear slug propaga para regras compostas (AND/OR)"""
        regra = {
            "type": "and",
            "conditions": [
                {
                    "type": "condition",
                    "variable": "slug_antigo",
                    "operator": "equals",
                    "value": True
                },
                {
                    "type": "condition",
                    "variable": "outra_variavel",
                    "operator": "exists"
                }
            ]
        }
        modulo = self._create_prompt_modulo("modulo_composto", regra_deterministica=regra)
        variavel = self._create_variavel("slug_antigo")
        self.db.commit()

        service = SlugRenameService(self.db)
        result = service.renomear(variavel.id, "slug_novo")

        self.assertTrue(result.success)

        # Verifica que apenas a variavel correta foi atualizada
        self.db.refresh(modulo)
        self.assertEqual(modulo.regra_deterministica["conditions"][0]["variable"], "slug_novo")
        self.assertEqual(modulo.regra_deterministica["conditions"][1]["variable"], "outra_variavel")

    def test_renomear_propaga_regra_tipo_peca(self):
        """Teste: renomear slug propaga para regras por tipo de peca"""
        modulo = self._create_prompt_modulo("modulo_tipo_peca")

        regra_tipo = RegraDeterministicaTipoPeca(
            modulo_id=modulo.id,
            tipo_peca="contestacao",
            regra_deterministica={
                "type": "condition",
                "variable": "slug_antigo",
                "operator": "equals",
                "value": "sim"
            },
            ativo=True
        )
        self.db.add(regra_tipo)

        variavel = self._create_variavel("slug_antigo")
        self.db.commit()

        service = SlugRenameService(self.db)
        result = service.renomear(variavel.id, "slug_novo")

        self.assertTrue(result.success)
        self.assertEqual(result.regras_tipo_peca_atualizadas, 1)

        # Verifica que a regra foi atualizada
        self.db.refresh(regra_tipo)
        self.assertEqual(regra_tipo.regra_deterministica["variable"], "slug_novo")

    def test_renomear_propaga_prompt_usage(self):
        """Teste: renomear slug propaga para PromptVariableUsage"""
        modulo = self._create_prompt_modulo("modulo_usage")

        usage = PromptVariableUsage(
            prompt_id=modulo.id,
            variable_slug="slug_antigo"
        )
        self.db.add(usage)

        variavel = self._create_variavel("slug_antigo")
        self.db.commit()

        service = SlugRenameService(self.db)
        result = service.renomear(variavel.id, "slug_novo")

        self.assertTrue(result.success)
        self.assertEqual(result.prompt_usages_atualizados, 1)

        # Verifica que o usage foi atualizado
        self.db.refresh(usage)
        self.assertEqual(usage.variable_slug, "slug_novo")

    def test_renomear_propaga_dependencias_variaveis(self):
        """Teste: renomear slug propaga para variaveis dependentes"""
        variavel_pai = self._create_variavel("variavel_pai")
        variavel_filha = self._create_variavel(
            "variavel_filha",
            depends_on_variable="variavel_pai",
            is_conditional=True
        )
        self.db.commit()

        service = SlugRenameService(self.db)
        result = service.renomear(variavel_pai.id, "variavel_pai_novo")

        self.assertTrue(result.success)
        self.assertEqual(result.variaveis_dependentes_atualizadas, 1)

        # Verifica que a dependencia foi atualizada
        self.db.refresh(variavel_filha)
        self.assertEqual(variavel_filha.depends_on_variable, "variavel_pai_novo")

    def test_renomear_propaga_dependencias_perguntas(self):
        """Teste: renomear slug propaga para perguntas dependentes"""
        categoria = self._create_categoria()
        variavel = self._create_variavel("variavel_condicao", categoria_id=categoria.id)

        pergunta = ExtractionQuestion(
            categoria_id=categoria.id,
            pergunta="Pergunta condicional?",
            depends_on_variable="variavel_condicao",
            dependency_operator="equals",
            dependency_value=True,
            ativo=True
        )
        self.db.add(pergunta)
        self.db.commit()

        service = SlugRenameService(self.db)
        result = service.renomear(variavel.id, "variavel_condicao_nova")

        self.assertTrue(result.success)
        self.assertEqual(result.perguntas_dependentes_atualizadas, 1)

        # Verifica que a dependencia foi atualizada
        self.db.refresh(pergunta)
        self.assertEqual(pergunta.depends_on_variable, "variavel_condicao_nova")


class TestSlugConsistencyChecker(BaseSlugTestCase):
    """Testes para SlugConsistencyChecker"""

    def test_verificar_categoria_consistente(self):
        """Teste: categoria consistente retorna consistente=True"""
        formato_json = json.dumps({
            "variavel_a": {"type": "text"},
            "variavel_b": {"type": "number"}
        })
        categoria = self._create_categoria("cat_consistente", formato_json)
        self._create_variavel("variavel_a", categoria_id=categoria.id)
        self._create_variavel("variavel_b", categoria_id=categoria.id)
        self.db.commit()

        checker = SlugConsistencyChecker(self.db)
        resultado = checker.verificar_categoria(categoria.id)

        self.assertTrue(resultado["consistente"])
        self.assertEqual(len(resultado["slugs_orfaos_json"]), 0)
        self.assertEqual(len(resultado["slugs_orfaos_variaveis"]), 0)

    def test_verificar_categoria_com_slug_orfao_json(self):
        """Teste: detecta slug no JSON sem variavel"""
        formato_json = json.dumps({
            "variavel_existente": {"type": "text"},
            "variavel_orfao": {"type": "text"}
        })
        categoria = self._create_categoria("cat_orfao_json", formato_json)
        self._create_variavel("variavel_existente", categoria_id=categoria.id)
        # NAO cria variavel para "variavel_orfao"
        self.db.commit()

        checker = SlugConsistencyChecker(self.db)
        resultado = checker.verificar_categoria(categoria.id)

        self.assertFalse(resultado["consistente"])
        self.assertIn("variavel_orfao", resultado["slugs_orfaos_json"])

    def test_verificar_categoria_com_variavel_orfao(self):
        """Teste: detecta variavel sem entrada no JSON"""
        formato_json = json.dumps({
            "variavel_no_json": {"type": "text"}
        })
        categoria = self._create_categoria("cat_var_orfao", formato_json)
        self._create_variavel("variavel_no_json", categoria_id=categoria.id)
        self._create_variavel("variavel_sem_json", categoria_id=categoria.id)
        self.db.commit()

        checker = SlugConsistencyChecker(self.db)
        resultado = checker.verificar_categoria(categoria.id)

        self.assertFalse(resultado["consistente"])
        self.assertIn("variavel_sem_json", resultado["slugs_orfaos_variaveis"])

    def test_verificar_referencias_prompts(self):
        """Teste: verifica referencias de slug em prompts"""
        regra = {
            "type": "condition",
            "variable": "variavel_usada",
            "operator": "equals",
            "value": True
        }
        modulo = self._create_prompt_modulo("modulo_usa_var", regra_deterministica=regra)
        self.db.commit()

        checker = SlugConsistencyChecker(self.db)
        resultado = checker.verificar_referencias_prompts("variavel_usada")

        self.assertEqual(resultado["total_prompts"], 1)
        self.assertEqual(resultado["prompts"][0]["nome"], "modulo_usa_var")

    def test_reparar_categoria_remove_orfaos_json(self):
        """Teste: reparo remove slugs orfaos do JSON"""
        formato_json = json.dumps({
            "variavel_ok": {"type": "text"},
            "variavel_orfao": {"type": "text"}
        })
        categoria = self._create_categoria("cat_reparo", formato_json)
        self._create_variavel("variavel_ok", categoria_id=categoria.id)
        self.db.commit()

        checker = SlugConsistencyChecker(self.db)
        resultado = checker.reparar_categoria(categoria.id)

        self.assertTrue(resultado["success"])
        self.assertGreater(resultado["correcoes_aplicadas"], 0)

        # Verifica que o JSON foi corrigido
        self.db.refresh(categoria)
        schema = json.loads(categoria.formato_json)
        self.assertIn("variavel_ok", schema)
        self.assertNotIn("variavel_orfao", schema)

    def test_reparar_categoria_adiciona_variaveis_faltantes(self):
        """Teste: reparo adiciona variaveis faltantes ao JSON"""
        formato_json = json.dumps({
            "variavel_existente": {"type": "text"}
        })
        categoria = self._create_categoria("cat_add_var", formato_json)
        self._create_variavel("variavel_existente", categoria_id=categoria.id)
        self._create_variavel(
            "variavel_nova",
            categoria_id=categoria.id,
            tipo="number",
            descricao="Variavel que falta no JSON"
        )
        self.db.commit()

        checker = SlugConsistencyChecker(self.db)
        resultado = checker.reparar_categoria(categoria.id)

        self.assertTrue(resultado["success"])

        # Verifica que a variavel foi adicionada ao JSON
        self.db.refresh(categoria)
        schema = json.loads(categoria.formato_json)
        self.assertIn("variavel_nova", schema)


class TestSlugValidation(BaseSlugTestCase):
    """Testes para validacao de slugs"""

    def test_validar_slug_vazio_falha(self):
        """Teste: slug vazio e rejeitado"""
        variavel = self._create_variavel("slug_original")
        self.db.commit()

        service = SlugRenameService(self.db)
        result = service.renomear(variavel.id, "", normalizar=False)

        self.assertFalse(result.success)
        self.assertIn("vazio", result.error.lower())

    def test_validar_slug_muito_curto_falha(self):
        """Teste: slug com menos de 3 caracteres e rejeitado"""
        variavel = self._create_variavel("slug_original")
        self.db.commit()

        service = SlugRenameService(self.db)
        result = service.renomear(variavel.id, "ab", normalizar=False)

        self.assertFalse(result.success)
        self.assertIn("3 caracteres", result.error.lower())

    def test_validar_slug_comeca_com_numero_falha(self):
        """Teste: slug que comeca com numero e rejeitado"""
        variavel = self._create_variavel("slug_original")
        self.db.commit()

        service = SlugRenameService(self.db)
        result = service.renomear(variavel.id, "123abc", normalizar=False)

        self.assertFalse(result.success)
        self.assertIn("comecar com letra", result.error.lower())

    def test_validar_slug_com_espacos_falha(self):
        """Teste: slug com espacos e rejeitado (sem normalizacao)"""
        variavel = self._create_variavel("slug_original")
        self.db.commit()

        service = SlugRenameService(self.db)
        result = service.renomear(variavel.id, "slug com espacos", normalizar=False)

        self.assertFalse(result.success)

    def test_validar_slug_com_hifen_falha(self):
        """Teste: slug com hifen e rejeitado (sem normalizacao)"""
        variavel = self._create_variavel("slug_original")
        self.db.commit()

        service = SlugRenameService(self.db)
        result = service.renomear(variavel.id, "slug-com-hifen", normalizar=False)

        self.assertFalse(result.success)


class TestSlugRenameViaPergunta(BaseSlugTestCase):
    """Testes para cenario de renomeacao via edicao de pergunta"""

    def test_renomear_slug_com_maiusculas_aceita(self):
        """
        Teste do bug onde slugs com maiusculas eram rejeitados.

        Cenario real: usuario editava slug para 'pareceres_procedimento_materiais_nao_SUS'
        e o sistema REJEITAVA por causa das letras maiusculas, sem mostrar erro claro.
        """
        # Setup
        formato_json = json.dumps({
            "pareceres_procedimento_materiais_etc_SUS": {"type": "text", "description": "Parecer"}
        })
        categoria = self._create_categoria("cat_maiusculas", formato_json)
        pergunta = self._create_pergunta(
            categoria.id,
            nome_variavel_sugerido="pareceres_procedimento_materiais_etc_SUS",
            pergunta="Qual o parecer sobre os procedimentos materiais SUS?"
        )
        variavel = self._create_variavel(
            "pareceres_procedimento_materiais_etc_SUS",
            categoria_id=categoria.id,
            source_question_id=pergunta.id
        )
        self.db.commit()

        # Renomeia para slug com maiusculas (caso real)
        service = SlugRenameService(self.db)
        result = service.renomear(
            variavel_id=variavel.id,
            novo_slug="pareceres_procedimento_materiais_nao_SUS",
            normalizar=False,  # Sem normalizar, como faz o endpoint
            skip_pergunta=True
        )

        # DEVE aceitar slugs com maiusculas
        self.assertTrue(result.success, f"Falha inesperada: {result.error}")
        self.assertEqual(result.new_slug, "pareceres_procedimento_materiais_nao_SUS")

        # Verifica que a variavel foi atualizada
        self.db.refresh(variavel)
        self.assertEqual(variavel.slug, "pareceres_procedimento_materiais_nao_SUS")

        # Verifica que o JSON foi atualizado
        self.db.refresh(categoria)
        schema = json.loads(categoria.formato_json)
        self.assertNotIn("pareceres_procedimento_materiais_etc_SUS", schema)
        self.assertIn("pareceres_procedimento_materiais_nao_SUS", schema)

    def test_renomear_slug_via_pergunta_persiste(self):
        """
        Teste do bug reportado: editar slug da pergunta e garantir que persiste.

        Cenario:
        1. Criar pergunta com slug "despacho_data"
        2. Editar para "despacho_data_"
        3. Verificar que slug foi persistido na pergunta
        4. Verificar que variavel foi renomeada
        5. Verificar que JSON da categoria foi atualizado
        """
        # Setup
        formato_json = json.dumps({
            "despacho_data": {"type": "date", "description": "Data do despacho"}
        })
        categoria = self._create_categoria("cat_bug_test", formato_json)
        pergunta = self._create_pergunta(
            categoria.id,
            nome_variavel_sugerido="despacho_data",
            pergunta="Qual a data do despacho?"
        )
        variavel = self._create_variavel(
            "despacho_data",
            categoria_id=categoria.id,
            source_question_id=pergunta.id
        )
        self.db.commit()

        # Simula edicao do slug
        novo_slug = "despacho_data_"

        # Usa o SlugRenameService com skip_pergunta=True (como faz o endpoint)
        service = SlugRenameService(self.db)
        result = service.renomear(
            variavel_id=variavel.id,
            novo_slug=novo_slug,
            normalizar=False,
            skip_pergunta=True
        )

        # Atualiza a pergunta manualmente (como faz o endpoint)
        pergunta.nome_variavel_sugerido = novo_slug

        self.db.commit()

        # Verificacoes
        self.assertTrue(result.success, f"Falha: {result.error}")

        # 1. Pergunta deve ter o novo slug
        self.db.refresh(pergunta)
        self.assertEqual(pergunta.nome_variavel_sugerido, "despacho_data_")

        # 2. Variavel deve ter o novo slug
        self.db.refresh(variavel)
        self.assertEqual(variavel.slug, "despacho_data_")

        # 3. JSON da categoria deve ter o novo slug
        self.db.refresh(categoria)
        schema = json.loads(categoria.formato_json)
        self.assertNotIn("despacho_data", schema)
        self.assertIn("despacho_data_", schema)

    def test_reabrir_pergunta_nao_reverte_slug(self):
        """
        Testa que ao reabrir a pergunta, o slug nao reverte para o antigo.

        Este teste simula o cenario onde:
        1. Usuario edita slug
        2. Salva
        3. Reabre o modal
        4. Slug deve continuar com o novo valor
        """
        # Setup
        formato_json = json.dumps({
            "variavel_original": {"type": "text"}
        })
        categoria = self._create_categoria("cat_reabrir", formato_json)
        pergunta = self._create_pergunta(
            categoria.id,
            nome_variavel_sugerido="variavel_original",
            pergunta="Pergunta teste"
        )
        variavel = self._create_variavel(
            "variavel_original",
            categoria_id=categoria.id,
            source_question_id=pergunta.id
        )
        self.db.commit()

        # Renomeia
        service = SlugRenameService(self.db)
        result = service.renomear(
            variavel_id=variavel.id,
            novo_slug="variavel_nova",
            normalizar=False,
            skip_pergunta=True
        )
        pergunta.nome_variavel_sugerido = "variavel_nova"
        self.db.commit()

        # Simula "reabrir" - busca do banco novamente
        pergunta_recarregada = self.db.query(ExtractionQuestion).filter(
            ExtractionQuestion.id == pergunta.id
        ).first()

        variavel_recarregada = self.db.query(ExtractionVariable).filter(
            ExtractionVariable.id == variavel.id
        ).first()

        # O slug NAO deve ter revertido
        self.assertEqual(pergunta_recarregada.nome_variavel_sugerido, "variavel_nova")
        self.assertEqual(variavel_recarregada.slug, "variavel_nova")


if __name__ == "__main__":
    unittest.main()
