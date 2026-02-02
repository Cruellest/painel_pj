# tests/ia_extracao_regras/backend/runtime/test_runtime_evaluation.py
"""
Testes de runtime para avaliação de regras determinísticas.

Verifica que regras são avaliadas corretamente sem chamadas LLM.
"""

import unittest
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.connection import Base
from sistemas.gerador_pecas.services_deterministic import (
    DeterministicRuleEvaluator, avaliar_ativacao_prompt
)

# Importa fixtures
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from fixtures.test_data import REGRAS_DETERMINISTICAS, DADOS_EXTRACAO


class TestRuntimeEvaluationSemLLM(unittest.TestCase):
    """
    Testes que verificam que avaliação de regras NÃO usa LLM.

    Estas avaliações devem ser puramente determinísticas.
    """

    def setUp(self):
        self.evaluator = DeterministicRuleEvaluator()

    def test_avaliacao_nao_chama_servico_externo(self):
        """Verifica que avaliação não faz chamadas externas."""
        # Este teste garante que a avaliação é local
        regra = REGRAS_DETERMINISTICAS["simples"]
        dados = DADOS_EXTRACAO["idoso_valor_alto"]

        # Se chamasse serviço externo, levantaria exceção sem mock
        resultado = self.evaluator.avaliar(regra, dados)

        self.assertIsInstance(resultado, bool)

    def test_performance_avaliacao(self):
        """Verifica que avaliação é rápida (< 10ms)."""
        import time

        regra = REGRAS_DETERMINISTICAS["aninhada"]
        dados = DADOS_EXTRACAO["idoso_valor_alto"]

        inicio = time.time()
        for _ in range(100):
            self.evaluator.avaliar(regra, dados)
        fim = time.time()

        tempo_medio = (fim - inicio) / 100
        self.assertLess(tempo_medio, 0.01, "Avaliação deve ser < 10ms")

    def test_determinismo_resultado(self):
        """Verifica que resultado é determinístico (sempre igual)."""
        regra = REGRAS_DETERMINISTICAS["and"]
        dados = DADOS_EXTRACAO["idoso_valor_alto"]

        resultados = [self.evaluator.avaliar(regra, dados) for _ in range(10)]

        # Todos devem ser iguais
        self.assertEqual(len(set(resultados)), 1)


class TestRuntimeRegrasComplexas(unittest.TestCase):
    """Testes de runtime com regras complexas e casos reais."""

    def setUp(self):
        self.evaluator = DeterministicRuleEvaluator()

    def test_regra_medicamento_alto_custo_fora_rename(self):
        """
        Caso real: Medicamento é alto custo E não está na RENAME.

        Deve ativar apenas quando ambas condições são verdadeiras.
        """
        regra = REGRAS_DETERMINISTICAS["medicamento_alto_custo"]

        # Alto custo + fora RENAME = True
        self.assertTrue(self.evaluator.avaliar(regra, {
            "medicamento_alto_custo": True,
            "medicamento_rename": False
        }))

        # Alto custo + na RENAME = False
        self.assertFalse(self.evaluator.avaliar(regra, {
            "medicamento_alto_custo": True,
            "medicamento_rename": True
        }))

        # Não é alto custo = False
        self.assertFalse(self.evaluator.avaliar(regra, {
            "medicamento_alto_custo": False,
            "medicamento_rename": False
        }))

    def test_regra_vulnerabilidade_autor(self):
        """
        Caso real: Autor é idoso OU é criança.

        Deve ativar para qualquer vulnerabilidade.
        """
        regra = REGRAS_DETERMINISTICAS["or"]

        # Idoso = True
        self.assertTrue(self.evaluator.avaliar(regra, {
            "autor_idoso": True,
            "autor_crianca": False
        }))

        # Criança = True
        self.assertTrue(self.evaluator.avaliar(regra, {
            "autor_idoso": False,
            "autor_crianca": True
        }))

        # Ambos = True
        self.assertTrue(self.evaluator.avaliar(regra, {
            "autor_idoso": True,
            "autor_crianca": True
        }))

        # Nenhum = False
        self.assertFalse(self.evaluator.avaliar(regra, {
            "autor_idoso": False,
            "autor_crianca": False
        }))

    def test_regra_vulnerabilidade_e_valor_alto(self):
        """
        Caso real: (Autor idoso OU criança) E valor > 50000.

        Combina vulnerabilidade com valor da causa.
        """
        regra = REGRAS_DETERMINISTICAS["aninhada"]

        # Idoso + valor alto = True
        self.assertTrue(self.evaluator.avaliar(regra, {
            "autor_idoso": True,
            "autor_crianca": False,
            "valor_causa": 100000
        }))

        # Criança + valor alto = True
        self.assertTrue(self.evaluator.avaliar(regra, {
            "autor_idoso": False,
            "autor_crianca": True,
            "valor_causa": 100000
        }))

        # Idoso + valor baixo = False
        self.assertFalse(self.evaluator.avaliar(regra, {
            "autor_idoso": True,
            "autor_crianca": False,
            "valor_causa": 30000
        }))

        # Adulto + valor alto = False
        self.assertFalse(self.evaluator.avaliar(regra, {
            "autor_idoso": False,
            "autor_crianca": False,
            "valor_causa": 100000
        }))

    def test_valores_formato_brasileiro(self):
        """Testa avaliação com valores em formato brasileiro."""
        regra = REGRAS_DETERMINISTICAS["simples"]  # valor > 100000

        # R$ 250.000,00 > 100000 = True
        self.assertTrue(self.evaluator.avaliar(regra, {
            "valor_causa": "R$ 250.000,00"
        }))

        # R$ 50.000,00 > 100000 = False
        self.assertFalse(self.evaluator.avaliar(regra, {
            "valor_causa": "R$ 50.000,00"
        }))

    def test_valores_booleanos_texto(self):
        """Testa avaliação com booleanos em formato texto."""
        regra = {
            "type": "condition",
            "variable": "autor_idoso",
            "operator": "equals",
            "value": True
        }

        # "sim" = True
        self.assertTrue(self.evaluator.avaliar(regra, {"autor_idoso": "sim"}))
        self.assertTrue(self.evaluator.avaliar(regra, {"autor_idoso": "true"}))
        self.assertTrue(self.evaluator.avaliar(regra, {"autor_idoso": "Yes"}))

        # "não" = False
        self.assertFalse(self.evaluator.avaliar(regra, {"autor_idoso": "não"}))
        self.assertFalse(self.evaluator.avaliar(regra, {"autor_idoso": "false"}))


class TestRuntimeComBancoDados(unittest.TestCase):
    """Testes de runtime com integração ao banco de dados."""

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False}
        )
        cls.Session = sessionmaker(bind=cls.engine)

        # Importa modelos
        from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON
        from sistemas.gerador_pecas.models_extraction import (
            ExtractionVariable, PromptVariableUsage, PromptActivationLog
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

    def _criar_prompt_teste(self, nome, modo_ativacao="deterministic", regra=None):
        """Cria prompt de teste."""
        from admin.models_prompts import PromptModulo

        prompt = PromptModulo(
            nome=nome,
            titulo=nome,
            tipo="conteudo",
            conteudo="Conteúdo de teste",
            modo_ativacao=modo_ativacao,
            regra_deterministica=regra,
            ativo=True,
            ordem=0,
            palavras_chave=[],
            tags=[]
        )
        self.db.add(prompt)
        self.db.commit()
        return prompt

    def test_avaliar_ativacao_modo_deterministico(self):
        """Testa função de conveniência avaliar_ativacao_prompt."""
        regra = REGRAS_DETERMINISTICAS["simples"]
        prompt = self._criar_prompt_teste("prompt_det", "deterministic", regra)

        # Valor alto = ativar
        resultado = avaliar_ativacao_prompt(
            prompt_id=prompt.id,
            modo_ativacao="deterministic",
            regra_deterministica=regra,
            dados_extracao={"valor_causa": 150000},
            db=self.db
        )

        self.assertTrue(resultado["ativar"])
        self.assertEqual(resultado["modo"], "deterministic")

    def test_avaliar_ativacao_modo_llm(self):
        """Testa que modo LLM retorna None (precisa chamada externa)."""
        prompt = self._criar_prompt_teste("prompt_llm", "llm", None)

        resultado = avaliar_ativacao_prompt(
            prompt_id=prompt.id,
            modo_ativacao="llm",
            regra_deterministica=None,
            dados_extracao={"valor_causa": 150000},
            db=self.db
        )

        self.assertIsNone(resultado["ativar"])
        self.assertEqual(resultado["modo"], "llm")

    def test_log_ativacao_registrado(self):
        """Testa que log de ativação é registrado no banco."""
        from sistemas.gerador_pecas.models_extraction import PromptActivationLog

        regra = REGRAS_DETERMINISTICAS["simples"]
        prompt = self._criar_prompt_teste("prompt_log", "deterministic", regra)

        # Executa avaliação
        avaliar_ativacao_prompt(
            prompt_id=prompt.id,
            modo_ativacao="deterministic",
            regra_deterministica=regra,
            dados_extracao={"valor_causa": 150000},
            db=self.db
        )

        # Verifica log
        log = self.db.query(PromptActivationLog).filter(
            PromptActivationLog.prompt_id == prompt.id
        ).first()

        self.assertIsNotNone(log)
        self.assertEqual(log.modo_ativacao, "deterministic")
        self.assertTrue(log.resultado)


if __name__ == "__main__":
    unittest.main()
