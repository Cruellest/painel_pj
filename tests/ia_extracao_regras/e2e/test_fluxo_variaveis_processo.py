# tests/ia_extracao_regras/e2e/test_fluxo_variaveis_processo.py
"""
Testes end-to-end para o fluxo de variáveis derivadas do processo.

Simula o fluxo completo:
1. SOAP retorna dados do processo (mockado)
2. Agente 1 extrai DadosProcesso do XML
3. ProcessVariableResolver resolve variáveis derivadas
4. Agente 2 usa variáveis para ativação determinística
5. Módulos são ativados/desativados corretamente
"""

import unittest
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Optional
import asyncio

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.connection import Base


# Mock de ParteProcesso para testes
@dataclass
class MockParteProcesso:
    """Mock de ParteProcesso para testes."""
    nome: str
    tipo_pessoa: str = "fisica"
    polo: str = "AT"
    representante: Optional[str] = None
    tipo_representante: Optional[str] = None
    assistencia_judiciaria: bool = False


# Mock de DadosProcesso para testes
@dataclass
class MockDadosProcesso:
    """Mock de DadosProcesso para testes."""
    numero_processo: str
    polo_ativo: List[MockParteProcesso] = field(default_factory=list)
    polo_passivo: List[MockParteProcesso] = field(default_factory=list)
    valor_causa: Optional[str] = None
    classe_processual: Optional[str] = None
    data_ajuizamento: Optional[datetime] = None
    orgao_julgador: Optional[str] = None

    def to_json(self):
        return {
            "numero_processo": self.numero_processo,
            "polo_ativo": [{"nome": p.nome} for p in self.polo_ativo],
            "polo_passivo": [{"nome": p.nome} for p in self.polo_passivo],
            "valor_causa": self.valor_causa,
            "data_ajuizamento": self.data_ajuizamento.strftime("%d/%m/%Y") if self.data_ajuizamento else None,
        }


# Mock de ResultadoAnalise para testes
@dataclass
class MockResultadoAnalise:
    """Mock de ResultadoAnalise para testes."""
    numero_processo: str
    dados_processo: Optional[MockDadosProcesso] = None
    documentos: List = field(default_factory=list)

    def documentos_com_resumo(self):
        return []

    def documentos_analisados(self):
        return 0


# Mock de ResultadoAgente1 para testes
@dataclass
class MockResultadoAgente1:
    """Mock de ResultadoAgente1 para testes."""
    resumo_consolidado: str = ""
    dados_brutos: Optional[MockResultadoAnalise] = None
    erro: Optional[str] = None


class TestFluxoVariaveisProcesso(unittest.TestCase):
    """
    Testes E2E para o fluxo de variáveis do processo.

    Simula todo o ciclo desde extração SOAP até ativação de módulos.
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

    def _criar_modulo(self, nome, modo_ativacao="llm", regra_deterministica=None, **kwargs):
        """Cria um módulo de teste."""
        from admin.models_prompts import PromptModulo

        modulo = PromptModulo(
            nome=nome,
            titulo=kwargs.get("titulo", nome),
            tipo=kwargs.get("tipo", "conteudo"),
            conteudo=kwargs.get("conteudo", "Conteúdo de teste"),
            condicao_ativacao=kwargs.get("condicao_ativacao", "Condição de teste"),
            modo_ativacao=modo_ativacao,
            regra_deterministica=regra_deterministica,
            ativo=kwargs.get("ativo", True),
            ordem=kwargs.get("ordem", 0),
            palavras_chave=[],
            tags=[]
        )
        self.db.add(modulo)
        self.db.commit()
        return modulo


class TestFluxoTema106(TestFluxoVariaveisProcesso):
    """Testes para o fluxo do Tema 106 STF (modulação de efeitos)."""

    def test_processo_apos_corte_ativa_modulo(self):
        """Processo ajuizado após 19/04/2024 deve ativar módulo do Tema 106."""
        # 1. Cria módulo determinístico para Tema 106
        regra = {
            "type": "condition",
            "variable": "processo_ajuizado_apos_2024_04_19",
            "operator": "equals",
            "value": True
        }
        modulo = self._criar_modulo(
            nome="tema_106_modulacao",
            titulo="Modulação de Efeitos - Tema 106 STF",
            modo_ativacao="deterministic",
            regra_deterministica=regra
        )

        # 2. Simula dados do processo (após 19/04/2024)
        dados_processo = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            data_ajuizamento=datetime(2024, 5, 15, 10, 30, 0),
            polo_passivo=[
                MockParteProcesso(nome="Estado de Mato Grosso do Sul", polo="PA")
            ],
            polo_ativo=[
                MockParteProcesso(nome="João da Silva", polo="AT")
            ]
        )

        # 3. Resolve variáveis
        from sistemas.gerador_pecas.services_process_variables import ProcessVariableResolver
        resolver = ProcessVariableResolver(dados_processo)
        variaveis = resolver.resolver_todas()

        # 4. Verifica que variável foi resolvida corretamente
        self.assertTrue(variaveis["processo_ajuizado_apos_2024_04_19"])

        # 5. Avalia regra
        from sistemas.gerador_pecas.services_deterministic import avaliar_ativacao_prompt
        resultado = avaliar_ativacao_prompt(
            prompt_id=modulo.id,
            modo_ativacao="deterministic",
            regra_deterministica=regra,
            dados_extracao=variaveis,
            db=self.db
        )

        # 6. Verifica ativação
        self.assertTrue(resultado["ativar"])
        self.assertEqual(resultado["modo"], "deterministic")

    def test_processo_antes_corte_nao_ativa_modulo(self):
        """Processo ajuizado antes de 19/04/2024 não deve ativar módulo do Tema 106."""
        regra = {
            "type": "condition",
            "variable": "processo_ajuizado_apos_2024_04_19",
            "operator": "equals",
            "value": True
        }
        modulo = self._criar_modulo(
            nome="tema_106_modulacao",
            titulo="Modulação de Efeitos - Tema 106 STF",
            modo_ativacao="deterministic",
            regra_deterministica=regra
        )

        # Processo ANTES de 19/04/2024
        dados_processo = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            data_ajuizamento=datetime(2024, 3, 1, 10, 30, 0)
        )

        from sistemas.gerador_pecas.services_process_variables import ProcessVariableResolver
        resolver = ProcessVariableResolver(dados_processo)
        variaveis = resolver.resolver_todas()

        # Variável deve ser False
        self.assertFalse(variaveis["processo_ajuizado_apos_2024_04_19"])

        from sistemas.gerador_pecas.services_deterministic import avaliar_ativacao_prompt
        resultado = avaliar_ativacao_prompt(
            prompt_id=modulo.id,
            modo_ativacao="deterministic",
            regra_deterministica=regra,
            dados_extracao=variaveis,
            db=self.db
        )

        # NÃO deve ativar
        self.assertFalse(resultado["ativar"])


class TestFluxoRegraComposta(TestFluxoVariaveisProcesso):
    """Testes para regras compostas com múltiplas variáveis do processo."""

    def test_regra_and_com_variaveis_processo(self):
        """Regra AND com múltiplas variáveis do processo."""
        # Regra: processo após corte E Estado no polo passivo
        regra = {
            "type": "and",
            "conditions": [
                {
                    "type": "condition",
                    "variable": "processo_ajuizado_apos_2024_04_19",
                    "operator": "equals",
                    "value": True
                },
                {
                    "type": "condition",
                    "variable": "estado_polo_passivo",
                    "operator": "equals",
                    "value": True
                }
            ]
        }
        modulo = self._criar_modulo(
            nome="defesa_estado_tema_106",
            titulo="Defesa do Estado com Tema 106",
            modo_ativacao="deterministic",
            regra_deterministica=regra
        )

        # Cenário: AMBAS as condições satisfeitas
        dados_processo = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            data_ajuizamento=datetime(2024, 5, 15),
            polo_passivo=[
                MockParteProcesso(nome="Estado de Mato Grosso do Sul", polo="PA")
            ]
        )

        from sistemas.gerador_pecas.services_process_variables import ProcessVariableResolver
        resolver = ProcessVariableResolver(dados_processo)
        variaveis = resolver.resolver_todas()

        self.assertTrue(variaveis["processo_ajuizado_apos_2024_04_19"])
        self.assertTrue(variaveis["estado_polo_passivo"])

        from sistemas.gerador_pecas.services_deterministic import avaliar_ativacao_prompt
        resultado = avaliar_ativacao_prompt(
            prompt_id=modulo.id,
            modo_ativacao="deterministic",
            regra_deterministica=regra,
            dados_extracao=variaveis,
            db=self.db
        )

        self.assertTrue(resultado["ativar"])

    def test_regra_and_com_uma_condicao_falsa(self):
        """Regra AND deve falhar se uma condição não for satisfeita."""
        regra = {
            "type": "and",
            "conditions": [
                {
                    "type": "condition",
                    "variable": "processo_ajuizado_apos_2024_04_19",
                    "operator": "equals",
                    "value": True
                },
                {
                    "type": "condition",
                    "variable": "estado_polo_passivo",
                    "operator": "equals",
                    "value": True
                }
            ]
        }
        modulo = self._criar_modulo(
            nome="defesa_estado_tema_106",
            modo_ativacao="deterministic",
            regra_deterministica=regra
        )

        # Processo após corte, MAS Estado NÃO está no polo passivo
        dados_processo = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            data_ajuizamento=datetime(2024, 5, 15),
            polo_passivo=[
                MockParteProcesso(nome="Município de Campo Grande", polo="PA")
            ]
        )

        from sistemas.gerador_pecas.services_process_variables import ProcessVariableResolver
        resolver = ProcessVariableResolver(dados_processo)
        variaveis = resolver.resolver_todas()

        self.assertTrue(variaveis["processo_ajuizado_apos_2024_04_19"])
        self.assertFalse(variaveis["estado_polo_passivo"])

        from sistemas.gerador_pecas.services_deterministic import avaliar_ativacao_prompt
        resultado = avaliar_ativacao_prompt(
            prompt_id=modulo.id,
            modo_ativacao="deterministic",
            regra_deterministica=regra,
            dados_extracao=variaveis,
            db=self.db
        )

        # NÃO deve ativar (AND requer ambas as condições)
        self.assertFalse(resultado["ativar"])


class TestFluxoOrquestradorComVariaveisProcesso(TestFluxoVariaveisProcesso):
    """Testes E2E simulando o fluxo completo do orquestrador."""

    def test_fluxo_completo_orquestrador(self):
        """Simula fluxo completo: SOAP → Agente 1 → Agente 2 com variáveis."""
        # 1. Cria módulo determinístico
        regra = {
            "type": "condition",
            "variable": "processo_ajuizado_apos_2024_04_19",
            "operator": "equals",
            "value": True
        }
        modulo = self._criar_modulo(
            nome="tema_106",
            titulo="Tema 106 STF",
            modo_ativacao="deterministic",
            regra_deterministica=regra
        )

        # 2. Simula resultado do Agente 1
        dados_processo = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            data_ajuizamento=datetime(2024, 5, 15),
            polo_passivo=[
                MockParteProcesso(nome="Estado de Mato Grosso do Sul", polo="PA")
            ]
        )

        resultado_analise = MockResultadoAnalise(
            numero_processo="0001234-56.2024.8.12.0001",
            dados_processo=dados_processo
        )

        resultado_agente1 = MockResultadoAgente1(
            resumo_consolidado="Resumo do processo de teste",
            dados_brutos=resultado_analise
        )

        # 3. Simula extração de dados_processo (como faz o orquestrador)
        dados_processo_extraido = None
        if resultado_agente1.dados_brutos and resultado_agente1.dados_brutos.dados_processo:
            dados_processo_extraido = resultado_agente1.dados_brutos.dados_processo

        self.assertIsNotNone(dados_processo_extraido)

        # 4. Resolve variáveis (como faz o detector)
        from sistemas.gerador_pecas.services_process_variables import ProcessVariableResolver
        resolver = ProcessVariableResolver(dados_processo_extraido)
        variaveis = resolver.resolver_todas()

        # 5. Verifica que variáveis foram resolvidas
        self.assertIn("processo_ajuizado_apos_2024_04_19", variaveis)
        self.assertTrue(variaveis["processo_ajuizado_apos_2024_04_19"])

        # 6. Avalia módulo
        from sistemas.gerador_pecas.services_deterministic import avaliar_ativacao_prompt
        resultado = avaliar_ativacao_prompt(
            prompt_id=modulo.id,
            modo_ativacao="deterministic",
            regra_deterministica=regra,
            dados_extracao=variaveis,
            db=self.db
        )

        # 7. Verifica ativação
        self.assertTrue(resultado["ativar"])


class TestCenariosReais(TestFluxoVariaveisProcesso):
    """Testes com cenários reais de uso."""

    def test_cenario_saude_com_tema_106(self):
        """Cenário: Ação de saúde com modulação do Tema 106."""
        # Módulo: Tema 106 para ações de saúde ajuizadas após corte
        regra = {
            "type": "and",
            "conditions": [
                {
                    "type": "condition",
                    "variable": "processo_ajuizado_apos_2024_04_19",
                    "operator": "equals",
                    "value": True
                },
                {
                    "type": "condition",
                    "variable": "autor_com_assistencia_judiciaria",
                    "operator": "equals",
                    "value": True
                }
            ]
        }
        modulo = self._criar_modulo(
            nome="tema_106_assistencia",
            titulo="Tema 106 com Assistência Judiciária",
            modo_ativacao="deterministic",
            regra_deterministica=regra
        )

        # Cenário: Autor hipossuficiente em ação após corte
        dados_processo = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            data_ajuizamento=datetime(2024, 6, 1),
            valor_causa="50.000,00",
            polo_passivo=[
                MockParteProcesso(nome="Estado de Mato Grosso do Sul", polo="PA")
            ],
            polo_ativo=[
                MockParteProcesso(
                    nome="Maria da Silva",
                    polo="AT",
                    assistencia_judiciaria=True,
                    tipo_representante="defensoria"
                )
            ]
        )

        from sistemas.gerador_pecas.services_process_variables import ProcessVariableResolver
        resolver = ProcessVariableResolver(dados_processo)
        variaveis = resolver.resolver_todas()

        # Verifica todas as variáveis
        self.assertTrue(variaveis["processo_ajuizado_apos_2024_04_19"])
        self.assertEqual(variaveis["valor_causa_numerico"], 50000.0)
        self.assertTrue(variaveis["estado_polo_passivo"])
        self.assertTrue(variaveis["autor_com_assistencia_judiciaria"])
        self.assertTrue(variaveis["autor_com_defensoria"])

        from sistemas.gerador_pecas.services_deterministic import avaliar_ativacao_prompt
        resultado = avaliar_ativacao_prompt(
            prompt_id=modulo.id,
            modo_ativacao="deterministic",
            regra_deterministica=regra,
            dados_extracao=variaveis,
            db=self.db
        )

        self.assertTrue(resultado["ativar"])


if __name__ == "__main__":
    unittest.main()
