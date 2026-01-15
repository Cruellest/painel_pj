# tests/ia_extracao_regras/e2e/test_fluxo_completo_ia.py
"""
Testes end-to-end para o fluxo completo do modo IA.

Simula o fluxo completo:
1. Criar perguntas de extração
2. Gerar schema por IA (mockado)
3. Criar regras determinísticas
4. Avaliar regras no runtime
5. Verificar painel de variáveis
"""

import unittest
from unittest.mock import patch, AsyncMock
import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.connection import Base


class TestFluxoCompletoModoIA(unittest.TestCase):
    """
    Testes E2E para o fluxo completo do modo IA.

    Simula todo o ciclo de vida desde criação de perguntas
    até avaliação de regras no runtime.
    """

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False}
        )
        cls.Session = sessionmaker(bind=cls.engine)

        # Importa todos os modelos
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
        Base.metadata.drop_all(bind=cls.engine)

    def setUp(self):
        self.db = self.Session()

    def tearDown(self):
        self.db.rollback()
        self.db.close()

    def _criar_categoria(self, nome="medicamentos"):
        """Cria categoria de teste."""
        from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON

        categoria = CategoriaResumoJSON(
            nome=nome,
            titulo=nome.title(),
            descricao=f"Categoria {nome}",
            codigos_documento=[500],
            formato_json='{}'
        )
        self.db.add(categoria)
        self.db.commit()
        return categoria

    def _criar_perguntas(self, categoria_id):
        """Cria perguntas de extração de teste."""
        from sistemas.gerador_pecas.models_extraction import ExtractionQuestion

        perguntas_data = [
            {"pergunta": "Qual é o nome do autor?", "tipo_sugerido": "text"},
            {"pergunta": "Qual é o valor da causa?", "tipo_sugerido": "currency"},
            {"pergunta": "O autor é idoso?", "tipo_sugerido": "boolean"},
        ]

        perguntas = []
        for i, p in enumerate(perguntas_data):
            pergunta = ExtractionQuestion(
                categoria_id=categoria_id,
                pergunta=p["pergunta"],
                tipo_sugerido=p.get("tipo_sugerido"),
                ativo=True,
                ordem=i
            )
            self.db.add(pergunta)
            perguntas.append(pergunta)

        self.db.commit()
        return perguntas

    def _criar_variaveis(self):
        """Cria variáveis de teste."""
        from sistemas.gerador_pecas.models_extraction import ExtractionVariable

        variaveis_data = [
            ("nome_autor", "text"),
            ("valor_causa", "currency"),
            ("autor_idoso", "boolean"),
        ]

        variaveis = []
        for slug, tipo in variaveis_data:
            var = ExtractionVariable(
                slug=slug,
                label=slug.replace("_", " ").title(),
                tipo=tipo,
                ativo=True
            )
            self.db.add(var)
            variaveis.append(var)

        self.db.commit()
        return variaveis

    def _criar_prompt_deterministico(self, regra):
        """Cria prompt com regra determinística."""
        from admin.models_prompts import PromptModulo

        prompt = PromptModulo(
            nome="prompt_teste_e2e",
            titulo="Prompt Teste E2E",
            tipo="conteudo",
            conteudo="Conteúdo de teste",
            modo_ativacao="deterministic",
            regra_deterministica=regra,
            ativo=True,
            ordem=0,
            palavras_chave=[],
            tags=[]
        )
        self.db.add(prompt)
        self.db.commit()
        return prompt

    def test_fluxo_e2e_criacao_ate_avaliacao(self):
        """
        Testa fluxo completo: perguntas -> variáveis -> regra -> avaliação.
        """
        from sistemas.gerador_pecas.services_deterministic import (
            DeterministicRuleEvaluator, PromptVariableUsageSync
        )

        # 1. Cria categoria
        categoria = self._criar_categoria("teste_e2e")

        # 2. Cria perguntas
        perguntas = self._criar_perguntas(categoria.id)
        self.assertEqual(len(perguntas), 3)

        # 3. Cria variáveis (simula geração por IA)
        variaveis = self._criar_variaveis()
        self.assertEqual(len(variaveis), 3)

        # 4. Cria regra determinística
        regra = {
            "type": "and",
            "conditions": [
                {"type": "condition", "variable": "autor_idoso", "operator": "equals", "value": True},
                {"type": "condition", "variable": "valor_causa", "operator": "greater_than", "value": 50000}
            ]
        }

        # 5. Cria prompt com a regra
        prompt = self._criar_prompt_deterministico(regra)

        # 6. Sincroniza uso de variáveis
        sync = PromptVariableUsageSync(self.db)
        variaveis_usadas = sync.atualizar_uso(prompt.id, regra)

        self.assertEqual(set(variaveis_usadas), {"autor_idoso", "valor_causa"})

        # 7. Avalia regra com dados de teste
        evaluator = DeterministicRuleEvaluator()

        # Caso positivo: idoso + valor alto
        dados_positivo = {"autor_idoso": True, "valor_causa": 100000}
        self.assertTrue(evaluator.avaliar(regra, dados_positivo))

        # Caso negativo: não idoso
        dados_negativo = {"autor_idoso": False, "valor_causa": 100000}
        self.assertFalse(evaluator.avaliar(regra, dados_negativo))

        # 8. Verifica painel de variáveis
        prompts_usando = sync.obter_prompts_por_variavel("autor_idoso")
        self.assertEqual(len(prompts_usando), 1)
        self.assertEqual(prompts_usando[0]["nome"], "prompt_teste_e2e")


class TestConvivenciaModoLegado(unittest.TestCase):
    """
    Testes E2E para verificar convivência do modo IA com modo legado.

    Garante que funcionalidades existentes não são quebradas.
    """

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False}
        )
        cls.Session = sessionmaker(bind=cls.engine)

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
        Base.metadata.drop_all(bind=cls.engine)

    def setUp(self):
        self.db = self.Session()

    def tearDown(self):
        self.db.rollback()
        self.db.close()

    def test_prompt_modo_llm_padrao(self):
        """Testa que prompts sem modo especificado usam LLM por padrão."""
        from admin.models_prompts import PromptModulo

        prompt = PromptModulo(
            nome="prompt_legado",
            titulo="Prompt Legado",
            tipo="conteudo",
            conteudo="Conteúdo",
            ativo=True,
            ordem=0,
            palavras_chave=[],
            tags=[]
        )
        self.db.add(prompt)
        self.db.commit()

        self.assertEqual(prompt.modo_ativacao, "llm")
        self.assertIsNone(prompt.regra_deterministica)

    def test_coexistencia_prompts_llm_e_deterministico(self):
        """Testa que prompts LLM e determinísticos coexistem."""
        from admin.models_prompts import PromptModulo
        from sistemas.gerador_pecas.services_deterministic import avaliar_ativacao_prompt

        # Cria prompt LLM
        prompt_llm = PromptModulo(
            nome="prompt_llm",
            titulo="Prompt LLM",
            tipo="conteudo",
            conteudo="Conteúdo",
            modo_ativacao="llm",
            ativo=True,
            ordem=0,
            palavras_chave=[],
            tags=[]
        )

        # Cria prompt determinístico
        regra = {
            "type": "condition",
            "variable": "valor_causa",
            "operator": "greater_than",
            "value": 100000
        }

        prompt_det = PromptModulo(
            nome="prompt_det",
            titulo="Prompt Determinístico",
            tipo="conteudo",
            conteudo="Conteúdo",
            modo_ativacao="deterministic",
            regra_deterministica=regra,
            ativo=True,
            ordem=1,
            palavras_chave=[],
            tags=[]
        )

        self.db.add_all([prompt_llm, prompt_det])
        self.db.commit()

        # Verifica ambos existem (filtra pelos nomes específicos)
        prompts = self.db.query(PromptModulo).filter(
            PromptModulo.nome.in_(["prompt_llm", "prompt_det"])
        ).all()
        self.assertEqual(len(prompts), 2)

        # Avalia LLM - deve retornar None (precisa chamar LLM)
        resultado_llm = avaliar_ativacao_prompt(
            prompt_id=prompt_llm.id,
            modo_ativacao="llm",
            regra_deterministica=None,
            dados_extracao={"valor_causa": 150000},
            db=self.db
        )
        self.assertIsNone(resultado_llm["ativar"])

        # Avalia determinístico - deve retornar True
        resultado_det = avaliar_ativacao_prompt(
            prompt_id=prompt_det.id,
            modo_ativacao="deterministic",
            regra_deterministica=regra,
            dados_extracao={"valor_causa": 150000},
            db=self.db
        )
        self.assertTrue(resultado_det["ativar"])

    def test_modelo_extracao_manual_aceito(self):
        """Testa que modelo de extração manual (legado) é aceito."""
        from sistemas.gerador_pecas.models_extraction import ExtractionModel
        from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON

        # Cria categoria
        categoria = CategoriaResumoJSON(
            nome="legado",
            titulo="Legado",
            descricao="Categoria legado",
            codigos_documento=[600],
            formato_json='{}'
        )
        self.db.add(categoria)
        self.db.commit()

        # Cria modelo manual
        schema_manual = {
            "nome_autor": {"type": "text", "description": "Nome do autor"},
            "valor_causa": {"type": "currency", "description": "Valor da causa"}
        }

        modelo = ExtractionModel(
            categoria_id=categoria.id,
            modo="manual",
            schema_json=schema_manual,
            versao=1,
            ativo=True
        )
        self.db.add(modelo)
        self.db.commit()

        # Verifica modelo criado
        modelo_db = self.db.query(ExtractionModel).filter(
            ExtractionModel.categoria_id == categoria.id
        ).first()

        self.assertIsNotNone(modelo_db)
        self.assertEqual(modelo_db.modo, "manual")

    def test_alternar_entre_modos(self):
        """Testa que prompt pode alternar entre modos sem perda de dados."""
        from admin.models_prompts import PromptModulo

        # Cria como LLM
        prompt = PromptModulo(
            nome="prompt_alternar",
            titulo="Prompt Alternar",
            tipo="conteudo",
            conteudo="Conteúdo importante",
            modo_ativacao="llm",
            ativo=True,
            ordem=0,
            palavras_chave=["teste"],
            tags=["e2e"]
        )
        self.db.add(prompt)
        self.db.commit()

        # Altera para determinístico
        regra = {
            "type": "condition",
            "variable": "valor_causa",
            "operator": "greater_than",
            "value": 100000
        }
        prompt.modo_ativacao = "deterministic"
        prompt.regra_deterministica = regra
        prompt.regra_texto_original = "Valor da causa maior que 100000"
        self.db.commit()

        # Verifica dados preservados
        self.db.refresh(prompt)
        self.assertEqual(prompt.modo_ativacao, "deterministic")
        self.assertEqual(prompt.conteudo, "Conteúdo importante")
        self.assertEqual(prompt.palavras_chave, ["teste"])

        # Volta para LLM
        prompt.modo_ativacao = "llm"
        prompt.regra_deterministica = None
        self.db.commit()

        self.db.refresh(prompt)
        self.assertEqual(prompt.modo_ativacao, "llm")
        self.assertEqual(prompt.conteudo, "Conteúdo importante")


class TestPainelVariaveisAtualizacao(unittest.TestCase):
    """
    Testes E2E para atualização automática do painel de variáveis.
    """

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False}
        )
        cls.Session = sessionmaker(bind=cls.engine)

        from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON
        from sistemas.gerador_pecas.models_extraction import (
            ExtractionVariable, PromptVariableUsage
        )
        from admin.models_prompts import PromptModulo
        from admin.models_prompt_groups import PromptGroup, PromptSubgroup
        from auth.models import User

        Base.metadata.create_all(bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=cls.engine)

    def setUp(self):
        self.db = self.Session()

    def tearDown(self):
        from sistemas.gerador_pecas.models_extraction import (
            ExtractionVariable, PromptVariableUsage
        )
        from admin.models_prompts import PromptModulo

        self.db.query(PromptVariableUsage).delete()
        self.db.query(PromptModulo).delete()
        self.db.query(ExtractionVariable).delete()
        self.db.commit()
        self.db.close()

    def test_painel_reflete_novas_variaveis(self):
        """Testa que painel reflete variáveis recém-criadas."""
        from sistemas.gerador_pecas.models_extraction import ExtractionVariable

        # Conta inicial
        count_inicial = self.db.query(ExtractionVariable).count()

        # Cria variáveis
        for i in range(3):
            var = ExtractionVariable(
                slug=f"var_nova_{i}",
                label=f"Variável Nova {i}",
                tipo="text",
                ativo=True
            )
            self.db.add(var)
        self.db.commit()

        # Conta final
        count_final = self.db.query(ExtractionVariable).count()

        self.assertEqual(count_final - count_inicial, 3)

    def test_painel_reflete_uso_atualizado(self):
        """Testa que painel reflete atualizações de uso em tempo real."""
        from sistemas.gerador_pecas.models_extraction import ExtractionVariable
        from sistemas.gerador_pecas.services_deterministic import PromptVariableUsageSync
        from admin.models_prompts import PromptModulo

        # Cria variáveis
        var1 = ExtractionVariable(slug="var_a", label="Var A", tipo="text", ativo=True)
        var2 = ExtractionVariable(slug="var_b", label="Var B", tipo="text", ativo=True)
        self.db.add_all([var1, var2])

        # Cria prompt
        prompt = PromptModulo(
            nome="prompt_uso",
            titulo="Prompt Uso",
            tipo="conteudo",
            conteudo="Conteúdo",
            modo_ativacao="deterministic",
            ativo=True,
            ordem=0,
            palavras_chave=[],
            tags=[]
        )
        self.db.add(prompt)
        self.db.commit()

        sync = PromptVariableUsageSync(self.db)

        # Primeira regra usa var_a
        regra1 = {"type": "condition", "variable": "var_a", "operator": "is_not_empty", "value": True}
        sync.atualizar_uso(prompt.id, regra1)

        prompts_var_a = sync.obter_prompts_por_variavel("var_a")
        prompts_var_b = sync.obter_prompts_por_variavel("var_b")

        self.assertEqual(len(prompts_var_a), 1)
        self.assertEqual(len(prompts_var_b), 0)

        # Atualiza para usar var_b
        regra2 = {"type": "condition", "variable": "var_b", "operator": "is_not_empty", "value": True}
        sync.atualizar_uso(prompt.id, regra2)

        prompts_var_a = sync.obter_prompts_por_variavel("var_a")
        prompts_var_b = sync.obter_prompts_por_variavel("var_b")

        self.assertEqual(len(prompts_var_a), 0)
        self.assertEqual(len(prompts_var_b), 1)


if __name__ == "__main__":
    unittest.main()
