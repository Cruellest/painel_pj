# tests/ia_extracao_regras/backend/integration/test_detector_with_process_vars.py
"""
Testes de integração para o detector de módulos com variáveis derivadas do processo.

Este módulo cobre:
- Integração do ProcessVariableResolver com o DetectorModulosIA
- Fast path: 100% determinístico (pula LLM)
- Modo misto: determinísticos + LLM
- Avaliação de regras com variáveis do processo
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.connection import Base
from admin.models_prompts import PromptModulo
from sistemas.gerador_pecas.detector_modulos import DetectorModulosIA


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


class TestDetectorWithProcessVars(unittest.TestCase):
    """Testes de integração para detector com variáveis do processo."""

    def setUp(self):
        """Configura banco de dados em memória."""
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False}
        )
        self.Session = sessionmaker(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = self.Session()

    def tearDown(self):
        """Limpa recursos."""
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)

    def _create_modulo(self, nome, modo_ativacao="llm", regra_deterministica=None, **kwargs):
        """Cria um módulo de teste."""
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
        self.db.flush()
        return modulo


class TestFastPathDeterministico(TestDetectorWithProcessVars):
    """Testes para fast path (100% determinístico)."""

    @patch('sistemas.gerador_pecas.detector_modulos.avaliar_ativacao_prompt')
    async def test_fast_path_todos_deterministicos_pula_llm(self, mock_avaliar):
        """Quando todos os módulos são determinísticos, deve pular LLM."""
        # Cria módulo determinístico
        regra = {
            "type": "condition",
            "variable": "processo_ajuizado_apos_2024_04_19",
            "operator": "equals",
            "value": True
        }
        modulo = self._create_modulo(
            nome="tema_106",
            titulo="Modulação Tema 106",
            modo_ativacao="deterministic",
            regra_deterministica=regra
        )

        # Mock da avaliação
        mock_avaliar.return_value = {
            "ativar": True,
            "modo": "deterministic",
            "regra_usada": "primaria",
            "detalhes": "OK"
        }

        # Cria dados do processo com data após 19/04/2024
        dados_processo = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            data_ajuizamento=datetime(2024, 5, 1)
        )

        # Executa detecção
        detector = DetectorModulosIA(db=self.db)

        # Mock do _chamar_ia para verificar que NÃO é chamado
        with patch.object(detector, '_chamar_ia', new_callable=AsyncMock) as mock_ia:
            result = await detector.detectar_modulos_relevantes(
                documentos_resumo="Resumo de teste",
                tipo_peca="contestacao",
                dados_processo=dados_processo
            )

            # Verifica que LLM NÃO foi chamada
            mock_ia.assert_not_called()

        # Verifica que módulo foi ativado
        self.assertIn(modulo.id, result)

    @patch('sistemas.gerador_pecas.detector_modulos.avaliar_ativacao_prompt')
    async def test_fast_path_modulo_nao_ativado(self, mock_avaliar):
        """Módulo determinístico não deve ser ativado se condição não satisfeita."""
        # Cria módulo determinístico
        regra = {
            "type": "condition",
            "variable": "processo_ajuizado_apos_2024_04_19",
            "operator": "equals",
            "value": True
        }
        modulo = self._create_modulo(
            nome="tema_106",
            titulo="Modulação Tema 106",
            modo_ativacao="deterministic",
            regra_deterministica=regra
        )

        # Mock: regra NÃO ativada (processo antes do corte)
        mock_avaliar.return_value = {
            "ativar": False,
            "modo": "deterministic",
            "regra_usada": "primaria",
            "detalhes": "Condição não satisfeita"
        }

        # Cria dados do processo com data ANTES de 19/04/2024
        dados_processo = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            data_ajuizamento=datetime(2024, 3, 15)
        )

        detector = DetectorModulosIA(db=self.db)

        with patch.object(detector, '_chamar_ia', new_callable=AsyncMock) as mock_ia:
            result = await detector.detectar_modulos_relevantes(
                documentos_resumo="Resumo de teste",
                tipo_peca="contestacao",
                dados_processo=dados_processo
            )

            # Verifica que LLM NÃO foi chamada
            mock_ia.assert_not_called()

        # Verifica que módulo NÃO foi ativado
        self.assertNotIn(modulo.id, result)
        self.assertEqual(result, [])


class TestModoMisto(TestDetectorWithProcessVars):
    """Testes para modo misto (determinísticos + LLM)."""

    @patch('sistemas.gerador_pecas.detector_modulos.avaliar_ativacao_prompt')
    async def test_modo_misto_avalia_deterministicos_e_chama_llm(self, mock_avaliar):
        """Em modo misto, deve avaliar determinísticos e chamar LLM para os demais."""
        # Cria módulo determinístico
        regra = {
            "type": "condition",
            "variable": "processo_ajuizado_apos_2024_04_19",
            "operator": "equals",
            "value": True
        }
        modulo_det = self._create_modulo(
            nome="tema_106",
            titulo="Modulação Tema 106",
            modo_ativacao="deterministic",
            regra_deterministica=regra
        )

        # Cria módulo LLM
        modulo_llm = self._create_modulo(
            nome="tese_generica",
            titulo="Tese Genérica",
            modo_ativacao="llm"
        )

        # Mock da avaliação determinística
        mock_avaliar.return_value = {
            "ativar": True,
            "modo": "deterministic",
            "regra_usada": "primaria",
            "detalhes": "OK"
        }

        dados_processo = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            data_ajuizamento=datetime(2024, 5, 1)
        )

        detector = DetectorModulosIA(db=self.db)

        # Mock do método _detectar_via_llm
        with patch.object(detector, '_detectar_via_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = [modulo_llm.id]

            result = await detector.detectar_modulos_relevantes(
                documentos_resumo="Resumo de teste",
                tipo_peca="contestacao",
                dados_processo=dados_processo
            )

            # Verifica que LLM FOI chamada
            mock_llm.assert_called_once()

        # Verifica que ambos os módulos foram ativados
        self.assertIn(modulo_det.id, result)
        self.assertIn(modulo_llm.id, result)

    @patch('sistemas.gerador_pecas.detector_modulos.avaliar_ativacao_prompt')
    async def test_modulo_indeterminado_vai_para_llm(self, mock_avaliar):
        """Módulo com resultado indeterminado deve ir para LLM."""
        # Cria módulo determinístico
        regra = {
            "type": "condition",
            "variable": "variavel_inexistente",
            "operator": "equals",
            "value": True
        }
        modulo = self._create_modulo(
            nome="modulo_indeterminado",
            titulo="Módulo Indeterminado",
            modo_ativacao="deterministic",
            regra_deterministica=regra
        )

        # Mock: resultado INDETERMINADO (variável não existe)
        mock_avaliar.return_value = {
            "ativar": None,  # Indeterminado
            "modo": "deterministic",
            "regra_usada": "nenhuma",
            "detalhes": "Variável inexistente"
        }

        dados_processo = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            data_ajuizamento=datetime(2024, 5, 1)
        )

        detector = DetectorModulosIA(db=self.db)

        with patch.object(detector, '_detectar_via_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = [modulo.id]

            result = await detector.detectar_modulos_relevantes(
                documentos_resumo="Resumo de teste",
                tipo_peca="contestacao",
                dados_processo=dados_processo
            )

            # Verifica que LLM foi chamada COM o módulo indeterminado
            mock_llm.assert_called_once()
            call_args = mock_llm.call_args
            modulos_para_llm = call_args[0][2]  # terceiro argumento posicional
            self.assertEqual(len(modulos_para_llm), 1)
            self.assertEqual(modulos_para_llm[0].id, modulo.id)


class TestIntegracaoVariaveisProcesso(TestDetectorWithProcessVars):
    """Testes de integração real com variáveis do processo."""

    async def test_variavel_processo_ajuizado_resolvida(self):
        """Variável do processo deve ser resolvida corretamente."""
        # Cria módulo que depende de variável do processo
        regra = {
            "type": "condition",
            "variable": "processo_ajuizado_apos_2024_04_19",
            "operator": "equals",
            "value": True
        }
        modulo = self._create_modulo(
            nome="tema_106",
            titulo="Modulação Tema 106",
            modo_ativacao="deterministic",
            regra_deterministica=regra
        )

        # Processo ajuizado APÓS 19/04/2024
        dados_processo = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            data_ajuizamento=datetime(2024, 5, 1)
        )

        detector = DetectorModulosIA(db=self.db)

        with patch.object(detector, '_chamar_ia', new_callable=AsyncMock):
            result = await detector.detectar_modulos_relevantes(
                documentos_resumo="Resumo de teste",
                tipo_peca="contestacao",
                dados_processo=dados_processo
            )

        # Módulo deve ser ativado (processo após 19/04/2024)
        self.assertIn(modulo.id, result)

    async def test_variavel_estado_polo_passivo_resolvida(self):
        """Variável estado_polo_passivo deve ser resolvida corretamente."""
        regra = {
            "type": "condition",
            "variable": "estado_polo_passivo",
            "operator": "equals",
            "value": True
        }
        modulo = self._create_modulo(
            nome="defesa_estado",
            titulo="Defesa do Estado",
            modo_ativacao="deterministic",
            regra_deterministica=regra
        )

        # Estado no polo passivo
        dados_processo = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            polo_passivo=[
                MockParteProcesso(nome="Estado de Mato Grosso do Sul", polo="PA")
            ]
        )

        detector = DetectorModulosIA(db=self.db)

        with patch.object(detector, '_chamar_ia', new_callable=AsyncMock):
            result = await detector.detectar_modulos_relevantes(
                documentos_resumo="Resumo de teste",
                tipo_peca="contestacao",
                dados_processo=dados_processo
            )

        self.assertIn(modulo.id, result)


class TestCacheComVariaveisProcesso(TestDetectorWithProcessVars):
    """Testes para cache com variáveis do processo."""

    @patch('sistemas.gerador_pecas.detector_modulos.avaliar_ativacao_prompt')
    async def test_cache_funciona_com_fast_path(self, mock_avaliar):
        """Cache deve funcionar corretamente com fast path."""
        regra = {
            "type": "condition",
            "variable": "processo_ajuizado_apos_2024_04_19",
            "operator": "equals",
            "value": True
        }
        modulo = self._create_modulo(
            nome="tema_106",
            modo_ativacao="deterministic",
            regra_deterministica=regra
        )

        mock_avaliar.return_value = {
            "ativar": True,
            "modo": "deterministic",
            "regra_usada": "primaria",
            "detalhes": "OK"
        }

        dados_processo = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            data_ajuizamento=datetime(2024, 5, 1)
        )

        detector = DetectorModulosIA(db=self.db)

        # Primeira chamada
        result1 = await detector.detectar_modulos_relevantes(
            documentos_resumo="Resumo de teste",
            tipo_peca="contestacao",
            dados_processo=dados_processo
        )

        # Segunda chamada (deve usar cache)
        result2 = await detector.detectar_modulos_relevantes(
            documentos_resumo="Resumo de teste",
            tipo_peca="contestacao",
            dados_processo=dados_processo
        )

        # Resultados devem ser iguais
        self.assertEqual(result1, result2)

        # Avaliação deve ter sido chamada apenas uma vez (cache na segunda)
        self.assertEqual(mock_avaliar.call_count, 1)


# Wrapper para rodar testes assíncronos
def async_test(coro):
    """Decorator para rodar testes assíncronos."""
    import asyncio

    def wrapper(*args, **kwargs):
        return asyncio.get_event_loop().run_until_complete(coro(*args, **kwargs))

    return wrapper


# Aplica decorator a todos os métodos de teste assíncronos
for cls in [TestFastPathDeterministico, TestModoMisto, TestIntegracaoVariaveisProcesso, TestCacheComVariaveisProcesso]:
    for name in dir(cls):
        if name.startswith('test_'):
            method = getattr(cls, name)
            if asyncio.iscoroutinefunction(method):
                setattr(cls, name, async_test(method))


if __name__ == "__main__":
    unittest.main()
