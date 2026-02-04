# tests/test_regras_tipo_peca.py
"""
Testes automatizados para o sistema de REGRAS DETERMINÍSTICAS POR TIPO DE PEÇA.

Cobre:
1. Regras GLOBAIS funcionando sozinhas
2. Regras ESPECÍFICAS por tipo de peça funcionando sozinhas
3. Combinação GLOBAL + ESPECÍFICA (lógica FALLBACK - v3)
   - Se existe regra específica ATIVA → ignora global
   - Se NÃO existe regra específica → usa global como fallback
4. Ausência de regras
5. Múltiplas regras válidas
6. Conflito de regras
7. Tipos de peça diferentes no mesmo processo
8. Módulos ativos/inativos por tipo
9. Modo "IA decide" - detecção automática de tipo
10. Fallback quando detecção falha

NOTA: Estes testes usam o banco de dados configurado no .env (SQLite local ou PostgreSQL).
"""

import pytest
import os
from typing import Dict, Any, Optional
from unittest.mock import MagicMock, patch, AsyncMock

# Imports do projeto
from database.connection import SessionLocal
# Importa todos os modelos para garantir que SQLAlchemy resolva as relações
from admin.models_prompts import (
    PromptModulo,
    RegraDeterministicaTipoPeca,
)
from admin.models_prompt_groups import PromptGroup
from auth.models import User  # Necessário para resolver relações do SQLAlchemy
from sistemas.gerador_pecas.services_deterministic import (
    DeterministicRuleEvaluator,
    avaliar_ativacao_prompt,
    verificar_variaveis_existem,
    _carregar_regra_tipo_peca,
    _existe_regra_especifica_ativa,
    carregar_regras_tipo_peca_modulo,
)


# ============================================================================
# CONFIGURAÇÃO DE TESTES
# ============================================================================

@pytest.fixture(scope="function")
def db():
    """
    Fornece uma sessão do banco de dados configurado no .env.
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def db_transactional():
    """
    Fornece uma sessão transacional que faz rollback no final.
    Útil para testes que criam dados temporários.
    """
    session = SessionLocal()
    try:
        yield session
        session.rollback()  # Descarta todas as mudanças
    finally:
        session.close()


@pytest.fixture
def avaliador():
    """Instância do avaliador de regras."""
    return DeterministicRuleEvaluator()


# ============================================================================
# FIXTURES DE DADOS
# ============================================================================

@pytest.fixture
def regra_global_valor_alto():
    """Regra global: valor da causa superior a 210SM."""
    return {
        "type": "condition",
        "variable": "valor_causa_superior_210sm",
        "operator": "equals",
        "value": True
    }


@pytest.fixture
def regra_especifica_contestacao():
    """Regra específica para contestação: autor com defensoria."""
    return {
        "type": "condition",
        "variable": "autor_com_defensoria",
        "operator": "equals",
        "value": True
    }


@pytest.fixture
def regra_especifica_apelacao():
    """Regra específica para apelação: sentença desfavorável."""
    return {
        "type": "condition",
        "variable": "sentenca_desfavoravel",
        "operator": "equals",
        "value": True
    }


@pytest.fixture
def dados_valor_alto():
    """Dados com valor da causa superior a 210SM."""
    return {
        "valor_causa_superior_210sm": True,
        "valor_causa_numerico": 500000.00,
    }


@pytest.fixture
def dados_valor_baixo():
    """Dados com valor da causa baixo."""
    return {
        "valor_causa_superior_210sm": False,
        "valor_causa_numerico": 50000.00,
    }


@pytest.fixture
def dados_autor_defensoria():
    """Dados com autor representado pela Defensoria."""
    return {
        "autor_com_defensoria": True,
        "autor_com_assistencia_judiciaria": True,
    }


@pytest.fixture
def dados_sentenca_desfavoravel():
    """Dados com sentença desfavorável."""
    return {
        "sentenca_desfavoravel": True,
        "resultado_sentenca": "procedente",
    }


def criar_mock_regra_tipo_peca(tipo_peca, regra_deterministica, ativo=True):
    """Helper para criar mock de regra por tipo de peça."""
    mock = MagicMock()
    mock.tipo_peca = tipo_peca
    mock.regra_deterministica = regra_deterministica
    mock.ativo = ativo
    return mock


# ============================================================================
# TESTES: REGRA GLOBAL FUNCIONANDO SOZINHA
# ============================================================================

class TestRegraGlobalSozinha:
    """Testes para regras globais funcionando isoladamente."""

    @patch('sistemas.gerador_pecas.services_deterministic._registrar_log_ativacao')
    def test_regra_global_ativa_quando_satisfeita(self, mock_log, db, regra_global_valor_alto, dados_valor_alto):
        """
        Regra global deve ativar o módulo quando satisfeita.
        """
        resultado = avaliar_ativacao_prompt(
            prompt_id=1,  # ID fictício
            modo_ativacao="deterministic",
            regra_deterministica=regra_global_valor_alto,
            dados_extracao=dados_valor_alto,
            db=db,
            tipo_peca=None  # Sem tipo específico
        )

        assert resultado["ativar"] is True
        assert resultado["modo"] == "deterministic"
        assert "global" in resultado["regra_usada"]

    @patch('sistemas.gerador_pecas.services_deterministic._registrar_log_ativacao')
    def test_regra_global_nao_ativa_quando_nao_satisfeita(self, mock_log, db, regra_global_valor_alto, dados_valor_baixo):
        """
        Regra global NÃO deve ativar o módulo quando não satisfeita.
        """
        resultado = avaliar_ativacao_prompt(
            prompt_id=1,
            modo_ativacao="deterministic",
            regra_deterministica=regra_global_valor_alto,
            dados_extracao=dados_valor_baixo,
            db=db,
            tipo_peca=None
        )

        assert resultado["ativar"] is False
        assert resultado["modo"] == "deterministic"

    @patch('sistemas.gerador_pecas.services_deterministic._registrar_log_ativacao')
    def test_regra_global_indeterminada_quando_variavel_ausente(self, mock_log, db, regra_global_valor_alto):
        """
        Regra global deve retornar None quando a variável não existe nos dados.
        """
        dados_sem_variavel = {"outra_variavel": True}

        resultado = avaliar_ativacao_prompt(
            prompt_id=1,
            modo_ativacao="deterministic",
            regra_deterministica=regra_global_valor_alto,
            dados_extracao=dados_sem_variavel,
            db=db,
            tipo_peca=None
        )

        assert resultado["ativar"] is None
        assert resultado["modo"] == "deterministic"


# ============================================================================
# TESTES: REGRA ESPECÍFICA FUNCIONANDO SOZINHA (com mock)
# ============================================================================

class TestRegraEspecificaSozinha:
    """Testes para regras específicas por tipo de peça funcionando isoladamente."""

    @patch('sistemas.gerador_pecas.services_deterministic._registrar_log_ativacao')
    @patch('sistemas.gerador_pecas.services_deterministic._existe_regra_especifica_ativa')
    @patch('sistemas.gerador_pecas.services_deterministic._carregar_regra_tipo_peca')
    def test_regra_especifica_ativa_quando_tipo_corresponde(
        self, mock_carregar, mock_existe, mock_log, db, regra_especifica_contestacao, dados_autor_defensoria
    ):
        """
        Regra específica deve ativar quando o tipo de peça corresponde.
        """
        # Mock indica que existe regra específica ativa
        mock_existe.return_value = True
        # Mock retorna regra específica
        mock_regra = criar_mock_regra_tipo_peca("contestacao", regra_especifica_contestacao)
        mock_carregar.return_value = mock_regra

        resultado = avaliar_ativacao_prompt(
            prompt_id=1,
            modo_ativacao="deterministic",
            regra_deterministica=None,  # Sem regra global
            dados_extracao=dados_autor_defensoria,
            db=db,
            tipo_peca="contestacao"
        )

        assert resultado["ativar"] is True
        assert "especifica_contestacao" in resultado["regra_usada"]

    @patch('sistemas.gerador_pecas.services_deterministic._registrar_log_ativacao')
    @patch('sistemas.gerador_pecas.services_deterministic._existe_regra_especifica_ativa')
    @patch('sistemas.gerador_pecas.services_deterministic._carregar_regra_tipo_peca')
    def test_regra_especifica_nao_ativa_quando_tipo_diferente(
        self, mock_carregar, mock_existe, mock_log, db, regra_especifica_contestacao, dados_autor_defensoria
    ):
        """
        Regra específica NÃO deve ativar quando o tipo de peça é diferente.
        """
        # Mock indica que NÃO existe regra específica ativa para recurso_apelacao
        mock_existe.return_value = False
        # Mock retorna None (não há regra para recurso_apelacao)
        mock_carregar.return_value = None

        # Tenta com tipo de peça diferente
        resultado = avaliar_ativacao_prompt(
            prompt_id=1,
            modo_ativacao="deterministic",
            regra_deterministica=None,
            dados_extracao=dados_autor_defensoria,
            db=db,
            tipo_peca="recurso_apelacao"  # Tipo diferente!
        )

        # Deve ser None porque não há regra para apelação nem global
        assert resultado["ativar"] is None

    @patch('sistemas.gerador_pecas.services_deterministic._registrar_log_ativacao')
    @patch('sistemas.gerador_pecas.services_deterministic._existe_regra_especifica_ativa')
    @patch('sistemas.gerador_pecas.services_deterministic._carregar_regra_tipo_peca')
    def test_regra_especifica_inativa_nao_avaliada(
        self, mock_carregar, mock_existe, mock_log, db, regra_especifica_contestacao, dados_autor_defensoria
    ):
        """
        Regra específica INATIVA não deve ser avaliada.
        """
        # Mock indica que NÃO existe regra específica ATIVA (está inativa)
        mock_existe.return_value = False
        # Mock retorna regra INATIVA
        mock_regra = criar_mock_regra_tipo_peca("contestacao", regra_especifica_contestacao, ativo=False)
        mock_carregar.return_value = mock_regra

        resultado = avaliar_ativacao_prompt(
            prompt_id=1,
            modo_ativacao="deterministic",
            regra_deterministica=None,
            dados_extracao=dados_autor_defensoria,
            db=db,
            tipo_peca="contestacao"
        )

        # Deve ser None porque a regra está inativa e não há global
        assert resultado["ativar"] is None


# ============================================================================
# TESTES: COMBINAÇÃO GLOBAL + ESPECÍFICA (FALLBACK - v3)
# ============================================================================

class TestCombinacaoGlobalEspecifica:
    """
    Testes para combinação de regras globais e específicas com lógica FALLBACK.

    REGRA DE NEGÓCIO (v3):
    - Se EXISTE regra específica ATIVA para o tipo → avalia APENAS específica (ignora global)
    - Se NÃO existe regra específica ATIVA → usa global como FALLBACK
    """

    @patch('sistemas.gerador_pecas.services_deterministic._registrar_log_ativacao')
    @patch('sistemas.gerador_pecas.services_deterministic._existe_regra_especifica_ativa')
    @patch('sistemas.gerador_pecas.services_deterministic._carregar_regra_tipo_peca')
    def test_especifica_ativa_true_ignora_global(
        self, mock_carregar, mock_existe, mock_log, db, regra_global_valor_alto, regra_especifica_contestacao
    ):
        """
        Se existe regra específica ATIVA que retorna TRUE:
        - Módulo deve ativar pela regra específica
        - Regra global deve ser IGNORADA (não avaliada)
        """
        # Mock indica que existe regra específica ativa
        mock_existe.return_value = True
        # Mock da regra específica
        mock_regra = criar_mock_regra_tipo_peca("contestacao", regra_especifica_contestacao)
        mock_carregar.return_value = mock_regra

        # Dados satisfazem a específica (autor_defensoria=True)
        # Global também seria TRUE, mas deve ser ignorada
        dados = {
            "valor_causa_superior_210sm": True,  # Global seria TRUE
            "autor_com_defensoria": True  # Específica é TRUE
        }

        resultado = avaliar_ativacao_prompt(
            prompt_id=1,
            modo_ativacao="deterministic",
            regra_deterministica=regra_global_valor_alto,
            dados_extracao=dados,
            db=db,
            tipo_peca="contestacao"
        )

        assert resultado["ativar"] is True
        # Deve ativar pela ESPECÍFICA (global ignorada)
        assert "especifica" in resultado["regra_usada"]

    @patch('sistemas.gerador_pecas.services_deterministic._registrar_log_ativacao')
    @patch('sistemas.gerador_pecas.services_deterministic._existe_regra_especifica_ativa')
    @patch('sistemas.gerador_pecas.services_deterministic._carregar_regra_tipo_peca')
    def test_especifica_ativa_false_nao_usa_global(
        self, mock_carregar, mock_existe, mock_log, db, regra_global_valor_alto, regra_especifica_contestacao
    ):
        """
        CASO CRÍTICO: Se existe regra específica ATIVA que retorna FALSE:
        - Módulo NÃO deve ativar
        - Regra global NÃO deve ser usada como fallback (porque existe específica)

        Isso garante que a regra específica tem precedência total.
        """
        # Mock indica que existe regra específica ativa
        mock_existe.return_value = True
        # Mock da regra específica
        mock_regra = criar_mock_regra_tipo_peca("contestacao", regra_especifica_contestacao)
        mock_carregar.return_value = mock_regra

        # Dados NÃO satisfazem a específica, mas satisfazem a global
        dados = {
            "valor_causa_superior_210sm": True,  # Global seria TRUE
            "autor_com_defensoria": False  # Específica é FALSE
        }

        resultado = avaliar_ativacao_prompt(
            prompt_id=1,
            modo_ativacao="deterministic",
            regra_deterministica=regra_global_valor_alto,
            dados_extracao=dados,
            db=db,
            tipo_peca="contestacao"
        )

        # Não deve ativar! A regra específica retornou FALSE e a global é ignorada
        assert resultado["ativar"] is False

    @patch('sistemas.gerador_pecas.services_deterministic._registrar_log_ativacao')
    @patch('sistemas.gerador_pecas.services_deterministic._existe_regra_especifica_ativa')
    @patch('sistemas.gerador_pecas.services_deterministic._carregar_regra_tipo_peca')
    def test_sem_especifica_usa_global_fallback(
        self, mock_carregar, mock_existe, mock_log, db, regra_global_valor_alto, dados_valor_alto
    ):
        """
        Se NÃO existe regra específica ATIVA para o tipo:
        - Usa regra global como FALLBACK
        """
        # Mock indica que NÃO existe regra específica ativa
        mock_existe.return_value = False
        # Mock retorna None (sem regra específica)
        mock_carregar.return_value = None

        resultado = avaliar_ativacao_prompt(
            prompt_id=1,
            modo_ativacao="deterministic",
            regra_deterministica=regra_global_valor_alto,
            dados_extracao=dados_valor_alto,
            db=db,
            tipo_peca="contestacao"
        )

        assert resultado["ativar"] is True
        # Deve ativar pela GLOBAL (usada como fallback)
        assert "global" in resultado["regra_usada"]

    @patch('sistemas.gerador_pecas.services_deterministic._registrar_log_ativacao')
    @patch('sistemas.gerador_pecas.services_deterministic._existe_regra_especifica_ativa')
    @patch('sistemas.gerador_pecas.services_deterministic._carregar_regra_tipo_peca')
    def test_especifica_inativa_usa_global_fallback(
        self, mock_carregar, mock_existe, mock_log, db, regra_global_valor_alto, regra_especifica_contestacao, dados_valor_alto
    ):
        """
        Se existe regra específica mas está INATIVA:
        - A função _existe_regra_especifica_ativa retorna False
        - Usa regra global como FALLBACK
        """
        # Mock indica que NÃO existe regra específica ATIVA (porque está inativa)
        mock_existe.return_value = False
        # Mock retorna regra INATIVA (que será ignorada)
        mock_regra = criar_mock_regra_tipo_peca("contestacao", regra_especifica_contestacao, ativo=False)
        mock_carregar.return_value = mock_regra

        resultado = avaliar_ativacao_prompt(
            prompt_id=1,
            modo_ativacao="deterministic",
            regra_deterministica=regra_global_valor_alto,
            dados_extracao=dados_valor_alto,
            db=db,
            tipo_peca="contestacao"
        )

        assert resultado["ativar"] is True
        # Deve ativar pela GLOBAL (porque específica está inativa)
        assert "global" in resultado["regra_usada"]

    @patch('sistemas.gerador_pecas.services_deterministic._registrar_log_ativacao')
    @patch('sistemas.gerador_pecas.services_deterministic._existe_regra_especifica_ativa')
    @patch('sistemas.gerador_pecas.services_deterministic._carregar_regra_tipo_peca')
    def test_especifica_false_global_true_nao_ativa(
        self, mock_carregar, mock_existe, mock_log, db, regra_global_valor_alto, regra_especifica_contestacao
    ):
        """
        TESTE DE REGRESSÃO CRÍTICO (mudança de comportamento OR → FALLBACK):

        Antes (OR): Específica FALSE + Global TRUE → ATIVAVA
        Agora (FALLBACK): Específica FALSE + Global TRUE → NÃO ATIVA (específica tem precedência)
        """
        # Mock indica que existe regra específica ativa
        mock_existe.return_value = True
        # Mock da regra específica
        mock_regra = criar_mock_regra_tipo_peca("contestacao", regra_especifica_contestacao)
        mock_carregar.return_value = mock_regra

        # Dados: específica FALSE, global TRUE
        dados = {
            "valor_causa_superior_210sm": True,  # Global seria TRUE
            "autor_com_defensoria": False  # Específica é FALSE
        }

        resultado = avaliar_ativacao_prompt(
            prompt_id=1,
            modo_ativacao="deterministic",
            regra_deterministica=regra_global_valor_alto,
            dados_extracao=dados,
            db=db,
            tipo_peca="contestacao"
        )

        # COM A NOVA LÓGICA: NÃO deve ativar (específica tem precedência)
        assert resultado["ativar"] is False


# ============================================================================
# TESTES: AUSÊNCIA DE REGRAS
# ============================================================================

class TestAusenciaRegras:
    """Testes para cenários sem regras configuradas."""

    @patch('sistemas.gerador_pecas.services_deterministic._registrar_log_ativacao')
    @patch('sistemas.gerador_pecas.services_deterministic._existe_regra_especifica_ativa')
    @patch('sistemas.gerador_pecas.services_deterministic._carregar_regra_tipo_peca')
    def test_sem_regra_global_nem_especifica(self, mock_carregar, mock_existe, mock_log, db):
        """
        Sem regra global nem específica, resultado deve ser indeterminado.
        """
        mock_existe.return_value = False
        mock_carregar.return_value = None

        dados = {"qualquer_variavel": True}

        resultado = avaliar_ativacao_prompt(
            prompt_id=1,
            modo_ativacao="deterministic",
            regra_deterministica=None,
            dados_extracao=dados,
            db=db,
            tipo_peca="contestacao"
        )

        assert resultado["ativar"] is None
        assert resultado["modo"] == "deterministic"

    @patch('sistemas.gerador_pecas.services_deterministic._registrar_log_ativacao')
    def test_modo_llm_ignora_regras(self, mock_log, db, regra_global_valor_alto, dados_valor_alto):
        """
        Modo LLM deve ignorar regras determinísticas.
        """
        resultado = avaliar_ativacao_prompt(
            prompt_id=1,
            modo_ativacao="llm",  # Modo LLM!
            regra_deterministica=regra_global_valor_alto,
            dados_extracao=dados_valor_alto,
            db=db,
            tipo_peca="contestacao"
        )

        assert resultado["ativar"] is None
        assert resultado["modo"] == "llm"


# ============================================================================
# TESTES: MÚLTIPLAS REGRAS VÁLIDAS
# ============================================================================

class TestMultiplasRegras:
    """Testes para módulos com múltiplas regras por tipo de peça."""

    @patch('sistemas.gerador_pecas.services_deterministic._registrar_log_ativacao')
    @patch('sistemas.gerador_pecas.services_deterministic._existe_regra_especifica_ativa')
    @patch('sistemas.gerador_pecas.services_deterministic._carregar_regra_tipo_peca')
    def test_multiplos_tipos_peca_diferentes_regras(
        self, mock_carregar, mock_existe, mock_log, db, regra_global_valor_alto, regra_especifica_contestacao, regra_especifica_apelacao
    ):
        """
        Mesmo módulo com regras diferentes para tipos de peça diferentes.
        """
        # Teste 1: Contestação com autor_defensoria=True
        mock_existe.return_value = True  # Existe regra específica ativa
        mock_carregar.return_value = criar_mock_regra_tipo_peca("contestacao", regra_especifica_contestacao)

        dados_contestacao = {
            "valor_causa_superior_210sm": False,
            "autor_com_defensoria": True
        }

        resultado_contestacao = avaliar_ativacao_prompt(
            prompt_id=1,
            modo_ativacao="deterministic",
            regra_deterministica=regra_global_valor_alto,
            dados_extracao=dados_contestacao,
            db=db,
            tipo_peca="contestacao"
        )

        assert resultado_contestacao["ativar"] is True
        assert "especifica_contestacao" in resultado_contestacao["regra_usada"]

        # Teste 2: Apelação com sentença_desfavoravel=True
        mock_existe.return_value = True  # Existe regra específica ativa
        mock_carregar.return_value = criar_mock_regra_tipo_peca("recurso_apelacao", regra_especifica_apelacao)

        dados_apelacao = {
            "valor_causa_superior_210sm": False,
            "sentenca_desfavoravel": True
        }

        resultado_apelacao = avaliar_ativacao_prompt(
            prompt_id=1,
            modo_ativacao="deterministic",
            regra_deterministica=regra_global_valor_alto,
            dados_extracao=dados_apelacao,
            db=db,
            tipo_peca="recurso_apelacao"
        )

        assert resultado_apelacao["ativar"] is True
        assert "especifica_recurso_apelacao" in resultado_apelacao["regra_usada"]


# ============================================================================
# TESTES: TIPOS DE PEÇA DIFERENTES NO MESMO PROCESSO
# ============================================================================

class TestTiposPecaDiferentes:
    """Testes para mesmo processo gerando peças diferentes."""

    @patch('sistemas.gerador_pecas.services_deterministic._registrar_log_ativacao')
    @patch('sistemas.gerador_pecas.services_deterministic._existe_regra_especifica_ativa')
    @patch('sistemas.gerador_pecas.services_deterministic._carregar_regra_tipo_peca')
    def test_mesmo_dados_tipos_diferentes(
        self, mock_carregar, mock_existe, mock_log, db, regra_global_valor_alto, regra_especifica_contestacao, regra_especifica_apelacao
    ):
        """
        Mesmos dados do processo podem gerar resultados diferentes para tipos de peça diferentes.
        """
        dados = {
            "valor_causa_superior_210sm": False,
            "autor_com_defensoria": True,
            "sentenca_desfavoravel": False
        }

        # Para contestação: deve ativar (autor_defensoria = True)
        mock_existe.return_value = True  # Existe regra específica ativa
        mock_carregar.return_value = criar_mock_regra_tipo_peca("contestacao", regra_especifica_contestacao)

        resultado_contestacao = avaliar_ativacao_prompt(
            prompt_id=1,
            modo_ativacao="deterministic",
            regra_deterministica=regra_global_valor_alto,
            dados_extracao=dados,
            db=db,
            tipo_peca="contestacao"
        )

        # Para apelação: não deve ativar (sentenca_desfavoravel = False)
        mock_existe.return_value = True  # Existe regra específica ativa
        mock_carregar.return_value = criar_mock_regra_tipo_peca("recurso_apelacao", regra_especifica_apelacao)

        resultado_apelacao = avaliar_ativacao_prompt(
            prompt_id=1,
            modo_ativacao="deterministic",
            regra_deterministica=regra_global_valor_alto,
            dados_extracao=dados,
            db=db,
            tipo_peca="recurso_apelacao"
        )

        assert resultado_contestacao["ativar"] is True
        assert resultado_apelacao["ativar"] is False


# ============================================================================
# TESTES: CARREGAMENTO DE REGRAS (usa mock para evitar dependências de modelo)
# ============================================================================

class TestCarregamentoRegras:
    """Testes para funções de carregamento de regras usando mocks."""

    def test_carregar_regra_tipo_peca_inexistente(self):
        """
        Deve retornar None para regra inexistente.
        """
        # Mock da sessão do banco
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None  # Simula regra não encontrada

        regra = _carregar_regra_tipo_peca(mock_db, 999999, "tipo_inexistente")
        assert regra is None

    def test_carregar_todas_regras_modulo_vazio(self):
        """
        Deve retornar lista vazia para módulo sem regras específicas.
        """
        # Mock da sessão do banco
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = []  # Simula lista vazia

        regras = carregar_regras_tipo_peca_modulo(mock_db, 999999)
        assert regras == []


# ============================================================================
# TESTES: FUNÇÃO _existe_regra_especifica_ativa
# ============================================================================

class TestExisteRegraEspecificaAtiva:
    """Testes para a função _existe_regra_especifica_ativa."""

    def test_retorna_true_quando_existe_regra_ativa(self):
        """
        Deve retornar True quando existe pelo menos uma regra ativa.
        """
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 1  # Simula 1 regra ativa encontrada

        resultado = _existe_regra_especifica_ativa(mock_db, 1, "contestacao")
        assert resultado is True

    def test_retorna_false_quando_nao_existe_regra(self):
        """
        Deve retornar False quando não existe nenhuma regra ativa.
        """
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 0  # Simula nenhuma regra encontrada

        resultado = _existe_regra_especifica_ativa(mock_db, 1, "contestacao")
        assert resultado is False

    def test_retorna_true_para_multiplas_regras_ativas(self):
        """
        Deve retornar True quando existem múltiplas regras ativas.
        """
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 3  # Simula 3 regras ativas

        resultado = _existe_regra_especifica_ativa(mock_db, 1, "contestacao")
        assert resultado is True


# ============================================================================
# TESTES: CENÁRIOS DE NEGÓCIO FALLBACK (v3)
# ============================================================================

class TestCenariosNegocioFallback:
    """
    Testes de integração para os cenários de negócio da lógica FALLBACK.

    Cenários solicitados:
    1. Tipo com regra específica ativa → global NÃO roda
    2. Tipo sem regra específica → global roda
    3. Tipo com regra específica inativa → global roda
    4. Regressão: tipos sem regras funcionam
    """

    @patch('sistemas.gerador_pecas.services_deterministic._registrar_log_ativacao')
    @patch('sistemas.gerador_pecas.services_deterministic._existe_regra_especifica_ativa')
    @patch('sistemas.gerador_pecas.services_deterministic._carregar_regra_tipo_peca')
    def test_cenario1_especifica_ativa_global_ignorada(
        self, mock_carregar, mock_existe, mock_log, db, regra_global_valor_alto, regra_especifica_contestacao
    ):
        """
        CENÁRIO 1: Tipo com regra específica ATIVA
        - Regra global NÃO deve ser executada
        - Apenas regra específica é avaliada
        """
        # Setup: existe regra específica ativa para contestacao
        mock_existe.return_value = True
        mock_carregar.return_value = criar_mock_regra_tipo_peca("contestacao", regra_especifica_contestacao)

        # Dados: global seria TRUE, específica é FALSE
        dados = {
            "valor_causa_superior_210sm": True,  # Global SERIA TRUE
            "autor_com_defensoria": False  # Específica é FALSE
        }

        resultado = avaliar_ativacao_prompt(
            prompt_id=1,
            modo_ativacao="deterministic",
            regra_deterministica=regra_global_valor_alto,
            dados_extracao=dados,
            db=db,
            tipo_peca="contestacao"
        )

        # RESULTADO: NÃO ativa porque a específica é FALSE
        # (se fosse OR, ativaria pela global)
        assert resultado["ativar"] is False
        # Confirma que a regra usada não é a global
        assert "global" not in resultado["regra_usada"]

    @patch('sistemas.gerador_pecas.services_deterministic._registrar_log_ativacao')
    @patch('sistemas.gerador_pecas.services_deterministic._existe_regra_especifica_ativa')
    @patch('sistemas.gerador_pecas.services_deterministic._carregar_regra_tipo_peca')
    def test_cenario2_sem_especifica_usa_global(
        self, mock_carregar, mock_existe, mock_log, db, regra_global_valor_alto, dados_valor_alto
    ):
        """
        CENÁRIO 2: Tipo sem regra específica
        - Regra global é usada como FALLBACK
        """
        # Setup: NÃO existe regra específica ativa para contestacao
        mock_existe.return_value = False
        mock_carregar.return_value = None

        resultado = avaliar_ativacao_prompt(
            prompt_id=1,
            modo_ativacao="deterministic",
            regra_deterministica=regra_global_valor_alto,
            dados_extracao=dados_valor_alto,
            db=db,
            tipo_peca="contestacao"
        )

        # RESULTADO: Ativa pela global (usada como fallback)
        assert resultado["ativar"] is True
        assert "global" in resultado["regra_usada"]

    @patch('sistemas.gerador_pecas.services_deterministic._registrar_log_ativacao')
    @patch('sistemas.gerador_pecas.services_deterministic._existe_regra_especifica_ativa')
    @patch('sistemas.gerador_pecas.services_deterministic._carregar_regra_tipo_peca')
    def test_cenario3_especifica_inativa_usa_global(
        self, mock_carregar, mock_existe, mock_log, db, regra_global_valor_alto, regra_especifica_contestacao, dados_valor_alto
    ):
        """
        CENÁRIO 3: Tipo com regra específica INATIVA
        - _existe_regra_especifica_ativa retorna False (porque está inativa)
        - Regra global é usada como FALLBACK
        """
        # Setup: existe regra específica mas está INATIVA
        mock_existe.return_value = False  # Retorna False porque a regra está inativa
        mock_regra = criar_mock_regra_tipo_peca("contestacao", regra_especifica_contestacao, ativo=False)
        mock_carregar.return_value = mock_regra

        resultado = avaliar_ativacao_prompt(
            prompt_id=1,
            modo_ativacao="deterministic",
            regra_deterministica=regra_global_valor_alto,
            dados_extracao=dados_valor_alto,
            db=db,
            tipo_peca="contestacao"
        )

        # RESULTADO: Ativa pela global (porque específica está inativa)
        assert resultado["ativar"] is True
        assert "global" in resultado["regra_usada"]

    @patch('sistemas.gerador_pecas.services_deterministic._registrar_log_ativacao')
    def test_cenario4_regressao_tipo_nulo_usa_global(
        self, mock_log, db, regra_global_valor_alto, dados_valor_alto
    ):
        """
        CENÁRIO 4: Regressão - tipos sem regras (tipo_peca=None)
        - Comportamento antigo preservado
        - Usa regra global diretamente
        """
        resultado = avaliar_ativacao_prompt(
            prompt_id=1,
            modo_ativacao="deterministic",
            regra_deterministica=regra_global_valor_alto,
            dados_extracao=dados_valor_alto,
            db=db,
            tipo_peca=None  # Sem tipo de peça
        )

        # RESULTADO: Funciona normalmente com regra global
        assert resultado["ativar"] is True
        assert "global" in resultado["regra_usada"]

    @patch('sistemas.gerador_pecas.services_deterministic._registrar_log_ativacao')
    @patch('sistemas.gerador_pecas.services_deterministic._existe_regra_especifica_ativa')
    @patch('sistemas.gerador_pecas.services_deterministic._carregar_regra_tipo_peca')
    def test_cenario_especifica_true_ignora_global_que_seria_false(
        self, mock_carregar, mock_existe, mock_log, db, regra_global_valor_alto, regra_especifica_contestacao
    ):
        """
        Cenário complementar: específica TRUE ignora global que seria FALSE.
        Confirma que a específica tem precedência total.
        """
        # Setup: existe regra específica ativa
        mock_existe.return_value = True
        mock_carregar.return_value = criar_mock_regra_tipo_peca("contestacao", regra_especifica_contestacao)

        # Dados: global seria FALSE, específica é TRUE
        dados = {
            "valor_causa_superior_210sm": False,  # Global seria FALSE
            "autor_com_defensoria": True  # Específica é TRUE
        }

        resultado = avaliar_ativacao_prompt(
            prompt_id=1,
            modo_ativacao="deterministic",
            regra_deterministica=regra_global_valor_alto,
            dados_extracao=dados,
            db=db,
            tipo_peca="contestacao"
        )

        # RESULTADO: Ativa pela específica (global ignorada)
        assert resultado["ativar"] is True
        assert "especifica" in resultado["regra_usada"]


# ============================================================================
# TESTES: MIGRAÇÃO E RETROCOMPATIBILIDADE
# ============================================================================

class TestRetrocompatibilidade:
    """Testes de retrocompatibilidade com regras existentes."""

    @patch('sistemas.gerador_pecas.services_deterministic._registrar_log_ativacao')
    def test_regra_global_existente_continua_funcionando(self, mock_log, db, regra_global_valor_alto, dados_valor_alto):
        """
        Regras globais existentes devem continuar funcionando normalmente.
        Cenário: tipo_peca=None (sem tipo específico).
        """
        # Simula comportamento antigo (sem tipo_peca)
        resultado = avaliar_ativacao_prompt(
            prompt_id=1,
            modo_ativacao="deterministic",
            regra_deterministica=regra_global_valor_alto,
            dados_extracao=dados_valor_alto,
            db=db,
            tipo_peca=None  # Sem tipo (compatibilidade)
        )

        assert resultado["ativar"] is True

    @patch('sistemas.gerador_pecas.services_deterministic._registrar_log_ativacao')
    @patch('sistemas.gerador_pecas.services_deterministic._existe_regra_especifica_ativa')
    @patch('sistemas.gerador_pecas.services_deterministic._carregar_regra_tipo_peca')
    def test_comportamento_manual_sem_especifica_usa_global(
        self, mock_carregar, mock_existe, mock_log, db, regra_global_valor_alto, dados_valor_alto
    ):
        """
        Quando usuário seleciona tipo manualmente mas NÃO existe regra específica:
        - Usa regra global como fallback
        """
        # Mock indica que NÃO existe regra específica ativa
        mock_existe.return_value = False
        mock_carregar.return_value = None

        # Simula seleção manual de tipo
        resultado = avaliar_ativacao_prompt(
            prompt_id=1,
            modo_ativacao="deterministic",
            regra_deterministica=regra_global_valor_alto,
            dados_extracao=dados_valor_alto,
            db=db,
            tipo_peca="contestacao"  # Seleção manual
        )

        assert resultado["ativar"] is True
        assert "global" in resultado["regra_usada"]

    @patch('sistemas.gerador_pecas.services_deterministic._registrar_log_ativacao')
    @patch('sistemas.gerador_pecas.services_deterministic._existe_regra_especifica_ativa')
    @patch('sistemas.gerador_pecas.services_deterministic._carregar_regra_tipo_peca')
    def test_comportamento_manual_com_especifica_usa_especifica(
        self, mock_carregar, mock_existe, mock_log, db, regra_global_valor_alto, regra_especifica_contestacao, dados_autor_defensoria
    ):
        """
        Quando usuário seleciona tipo manualmente e EXISTE regra específica:
        - Usa apenas regra específica (ignora global)
        """
        # Mock indica que existe regra específica ativa
        mock_existe.return_value = True
        mock_carregar.return_value = criar_mock_regra_tipo_peca("contestacao", regra_especifica_contestacao)

        # Simula seleção manual de tipo
        resultado = avaliar_ativacao_prompt(
            prompt_id=1,
            modo_ativacao="deterministic",
            regra_deterministica=regra_global_valor_alto,
            dados_extracao=dados_autor_defensoria,
            db=db,
            tipo_peca="contestacao"  # Seleção manual
        )

        assert resultado["ativar"] is True
        assert "especifica" in resultado["regra_usada"]


# ============================================================================
# TESTES: VERIFICAÇÃO DE VARIÁVEIS
# ============================================================================

class TestVerificacaoVariaveis:
    """Testes para verificação de existência de variáveis."""

    def test_verificar_variaveis_existem_todas(self):
        """
        Deve retornar True quando todas as variáveis existem.
        """
        regra = {
            "type": "and",
            "conditions": [
                {"type": "condition", "variable": "var1", "operator": "equals", "value": True},
                {"type": "condition", "variable": "var2", "operator": "equals", "value": False}
            ]
        }
        dados = {"var1": True, "var2": False}

        existem, vars_usadas = verificar_variaveis_existem(regra, dados)

        assert existem is True
        assert "var1" in vars_usadas
        assert "var2" in vars_usadas

    def test_verificar_variaveis_faltando_uma(self):
        """
        Deve retornar False quando alguma variável está ausente.
        """
        regra = {
            "type": "and",
            "conditions": [
                {"type": "condition", "variable": "var1", "operator": "equals", "value": True},
                {"type": "condition", "variable": "var2", "operator": "equals", "value": False}
            ]
        }
        dados = {"var1": True}  # var2 ausente

        existem, vars_usadas = verificar_variaveis_existem(regra, dados)

        assert existem is False


# ============================================================================
# TESTES: AVALIADOR DE REGRAS
# ============================================================================

class TestAvaliadorRegras:
    """Testes para o avaliador de regras determinísticas."""

    def test_avaliar_regra_simples_true(self, avaliador):
        """
        Regra simples deve retornar True quando satisfeita.
        """
        regra = {
            "type": "condition",
            "variable": "teste",
            "operator": "equals",
            "value": True
        }
        dados = {"teste": True}

        resultado = avaliador.avaliar(regra, dados)

        assert resultado is True

    def test_avaliar_regra_simples_false(self, avaliador):
        """
        Regra simples deve retornar False quando não satisfeita.
        """
        regra = {
            "type": "condition",
            "variable": "teste",
            "operator": "equals",
            "value": True
        }
        dados = {"teste": False}

        resultado = avaliador.avaliar(regra, dados)

        assert resultado is False

    def test_avaliar_regra_and(self, avaliador):
        """
        Regra AND deve retornar True apenas se TODAS as condições forem True.
        """
        regra = {
            "type": "and",
            "conditions": [
                {"type": "condition", "variable": "a", "operator": "equals", "value": True},
                {"type": "condition", "variable": "b", "operator": "equals", "value": True}
            ]
        }

        # Ambos True
        assert avaliador.avaliar(regra, {"a": True, "b": True}) is True

        # Um False
        assert avaliador.avaliar(regra, {"a": True, "b": False}) is False

    def test_avaliar_regra_or(self, avaliador):
        """
        Regra OR deve retornar True se QUALQUER condição for True.
        """
        regra = {
            "type": "or",
            "conditions": [
                {"type": "condition", "variable": "a", "operator": "equals", "value": True},
                {"type": "condition", "variable": "b", "operator": "equals", "value": True}
            ]
        }

        # Ambos True
        assert avaliador.avaliar(regra, {"a": True, "b": True}) is True

        # Um True
        assert avaliador.avaliar(regra, {"a": True, "b": False}) is True

        # Ambos False
        assert avaliador.avaliar(regra, {"a": False, "b": False}) is False


# ============================================================================
# TESTES: MODO "IA DECIDE" (detecção automática)
# ============================================================================

class TestModoIADecide:
    """
    Testes para o modo "IA decide" - detecção automática de tipo de peça.

    Cenários:
    - IA detecta "Contestação" → aplica módulos/regras de contestação
    - IA detecta "Apelação" → aplica módulos/regras de apelação
    - Tipo sem regra específica → usa global como fallback
    """

    @patch('sistemas.gerador_pecas.services_deterministic._registrar_log_ativacao')
    @patch('sistemas.gerador_pecas.services_deterministic._existe_regra_especifica_ativa')
    @patch('sistemas.gerador_pecas.services_deterministic._carregar_regra_tipo_peca')
    def test_ia_detecta_contestacao_aplica_regras_contestacao(
        self, mock_carregar, mock_existe, mock_log, db, regra_global_valor_alto, regra_especifica_contestacao
    ):
        """
        Quando IA detecta 'Contestação' e existe regra específica ativa:
        - Deve aplicar APENAS regra específica de contestação
        - Regra global é IGNORADA
        """
        # Mock indica que existe regra específica ativa
        mock_existe.return_value = True
        # Mock da regra específica de contestação
        mock_carregar.return_value = criar_mock_regra_tipo_peca("contestacao", regra_especifica_contestacao)

        # Simula cenário onde IA detectou tipo_peca = "contestacao"
        tipo_peca_detectado = "contestacao"

        dados = {
            "valor_causa_superior_210sm": False,  # Global não satisfaz (mas será ignorada)
            "autor_com_defensoria": True  # Específica de contestação satisfaz
        }

        resultado = avaliar_ativacao_prompt(
            prompt_id=1,
            modo_ativacao="deterministic",
            regra_deterministica=regra_global_valor_alto,
            dados_extracao=dados,
            db=db,
            tipo_peca=tipo_peca_detectado
        )

        assert resultado["ativar"] is True
        assert "especifica_contestacao" in resultado["regra_usada"]

    @patch('sistemas.gerador_pecas.services_deterministic._registrar_log_ativacao')
    @patch('sistemas.gerador_pecas.services_deterministic._existe_regra_especifica_ativa')
    @patch('sistemas.gerador_pecas.services_deterministic._carregar_regra_tipo_peca')
    def test_ia_detecta_apelacao_aplica_regras_apelacao(
        self, mock_carregar, mock_existe, mock_log, db, regra_global_valor_alto, regra_especifica_apelacao
    ):
        """
        Quando IA detecta 'Apelação' e existe regra específica ativa:
        - Deve aplicar APENAS regra específica de apelação
        - Regra global é IGNORADA
        """
        # Mock indica que existe regra específica ativa
        mock_existe.return_value = True
        # Mock da regra específica de apelação
        mock_carregar.return_value = criar_mock_regra_tipo_peca("recurso_apelacao", regra_especifica_apelacao)

        tipo_peca_detectado = "recurso_apelacao"

        dados = {
            "valor_causa_superior_210sm": False,  # Global não satisfaz (mas será ignorada)
            "sentenca_desfavoravel": True  # Específica de apelação satisfaz
        }

        resultado = avaliar_ativacao_prompt(
            prompt_id=1,
            modo_ativacao="deterministic",
            regra_deterministica=regra_global_valor_alto,
            dados_extracao=dados,
            db=db,
            tipo_peca=tipo_peca_detectado
        )

        assert resultado["ativar"] is True
        assert "especifica_recurso_apelacao" in resultado["regra_usada"]

    @patch('sistemas.gerador_pecas.services_deterministic._registrar_log_ativacao')
    @patch('sistemas.gerador_pecas.services_deterministic._existe_regra_especifica_ativa')
    @patch('sistemas.gerador_pecas.services_deterministic._carregar_regra_tipo_peca')
    def test_ia_detecta_sem_especifica_usa_global_fallback(
        self, mock_carregar, mock_existe, mock_log, db, regra_global_valor_alto
    ):
        """
        Quando IA detecta tipo mas NÃO existe regra específica ativa:
        - Deve usar regra GLOBAL como fallback
        """
        # Mock indica que NÃO existe regra específica ativa
        mock_existe.return_value = False
        # Mock retorna None (sem regra específica)
        mock_carregar.return_value = None

        tipo_peca_detectado = "contestacao"

        # Dados satisfazem a global
        dados = {
            "valor_causa_superior_210sm": True,  # Global satisfaz
            "autor_com_defensoria": False
        }

        resultado = avaliar_ativacao_prompt(
            prompt_id=1,
            modo_ativacao="deterministic",
            regra_deterministica=regra_global_valor_alto,
            dados_extracao=dados,
            db=db,
            tipo_peca=tipo_peca_detectado
        )

        assert resultado["ativar"] is True
        # Deve ativar pela GLOBAL (usada como fallback)
        assert "global" in resultado["regra_usada"]


# ============================================================================
# TESTES: FALLBACK QUANDO DETECÇÃO FALHA
# ============================================================================

class TestFallbackDeteccao:
    """
    Testes para comportamento de fallback quando a detecção automática falha.
    """

    @patch('sistemas.gerador_pecas.services_deterministic._registrar_log_ativacao')
    def test_tipo_nulo_usa_apenas_global(self, mock_log, db, regra_global_valor_alto, dados_valor_alto):
        """
        Se tipo_peca for None (detecção falhou), deve usar apenas regras globais.
        """
        resultado = avaliar_ativacao_prompt(
            prompt_id=1,
            modo_ativacao="deterministic",
            regra_deterministica=regra_global_valor_alto,
            dados_extracao=dados_valor_alto,
            db=db,
            tipo_peca=None  # Tipo não definido
        )

        # Deve funcionar com regra global
        assert resultado["ativar"] is True
        assert "global" in resultado["regra_usada"]

    @patch('sistemas.gerador_pecas.services_deterministic._registrar_log_ativacao')
    @patch('sistemas.gerador_pecas.services_deterministic._existe_regra_especifica_ativa')
    @patch('sistemas.gerador_pecas.services_deterministic._carregar_regra_tipo_peca')
    def test_tipo_inexistente_nao_quebra(self, mock_carregar, mock_existe, mock_log, db, regra_global_valor_alto, dados_valor_alto):
        """
        Se tipo_peca for inválido, não deve quebrar - usa apenas global.
        """
        # Mock indica que não existe regra específica para o tipo inexistente
        mock_existe.return_value = False
        mock_carregar.return_value = None

        resultado = avaliar_ativacao_prompt(
            prompt_id=1,
            modo_ativacao="deterministic",
            regra_deterministica=regra_global_valor_alto,
            dados_extracao=dados_valor_alto,
            db=db,
            tipo_peca="tipo_inexistente_xyz"  # Tipo que não existe
        )

        # Não deve quebrar, deve usar global
        assert resultado["ativar"] is True
        assert "global" in resultado["regra_usada"]


# ============================================================================
# TESTES: REGRESSÃO
# ============================================================================

class TestRegressao:
    """
    Testes de regressão para garantir que comportamento antigo está preservado.
    """

    @patch('sistemas.gerador_pecas.services_deterministic._registrar_log_ativacao')
    def test_comportamento_antigo_sem_tipo_preservado(
        self, mock_log, db, regra_global_valor_alto, dados_valor_alto
    ):
        """
        Comportamento antigo (sem tipo de peça) deve funcionar igual.
        """
        # Simula chamada antiga sem tipo_peca
        resultado = avaliar_ativacao_prompt(
            prompt_id=1,
            modo_ativacao="deterministic",
            regra_deterministica=regra_global_valor_alto,
            dados_extracao=dados_valor_alto,
            db=db
            # tipo_peca não informado (default None)
        )

        assert resultado["ativar"] is True
        assert resultado["modo"] == "deterministic"

    @patch('sistemas.gerador_pecas.services_deterministic._registrar_log_ativacao')
    @patch('sistemas.gerador_pecas.services_deterministic._existe_regra_especifica_ativa')
    @patch('sistemas.gerador_pecas.services_deterministic._carregar_regra_tipo_peca')
    def test_selecao_manual_funciona_igual_deteccao(
        self, mock_carregar, mock_existe, mock_log, db, regra_global_valor_alto, regra_especifica_contestacao
    ):
        """
        Seleção manual de tipo deve ter mesmo comportamento que detecção automática.
        """
        # Mock indica que existe regra específica ativa
        mock_existe.return_value = True
        # Mock da regra específica
        mock_carregar.return_value = criar_mock_regra_tipo_peca("contestacao", regra_especifica_contestacao)

        dados = {
            "valor_causa_superior_210sm": False,
            "autor_com_defensoria": True
        }

        # Simula seleção manual
        resultado_manual = avaliar_ativacao_prompt(
            prompt_id=1,
            modo_ativacao="deterministic",
            regra_deterministica=regra_global_valor_alto,
            dados_extracao=dados,
            db=db,
            tipo_peca="contestacao"
        )

        # Simula detecção automática (mesmo tipo)
        resultado_auto = avaliar_ativacao_prompt(
            prompt_id=1,
            modo_ativacao="deterministic",
            regra_deterministica=regra_global_valor_alto,
            dados_extracao=dados,
            db=db,
            tipo_peca="contestacao"  # Mesmo tipo detectado
        )

        assert resultado_manual["ativar"] == resultado_auto["ativar"]
        assert resultado_manual["regra_usada"] == resultado_auto["regra_usada"]


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
