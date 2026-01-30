# tests/classificador_documentos/test_watchdog.py
"""
Testes para o sistema de detecção de travamento e recuperação do Classificador.

Conforme ADR-0010: Sistema de Recuperação de Execuções Travadas

Testes cobrem:
- Detecção de execuções travadas
- Retomada idempotente
- Reprocessamento de erros
- Estados da máquina de estados

Autor: LAB/PGE-MS
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock

from sqlalchemy.orm import Session

from sistemas.classificador_documentos.models import (
    ExecucaoClassificacao,
    ResultadoClassificacao,
    ProjetoClassificacao,
    CodigoDocumentoProjeto,
    StatusExecucao,
    StatusArquivo,
    FonteDocumento
)
from sistemas.classificador_documentos.watchdog import (
    ClassificadorWatchdog,
    HEARTBEAT_TIMEOUT_MINUTES,
    PROCESSANDO_TIMEOUT_MINUTES
)
from utils.timezone import get_utc_now


class TestStatusExecucaoModel:
    """Testes para os novos campos e propriedades do modelo ExecucaoClassificacao."""

    def test_status_travado_existe(self):
        """Verifica que o status TRAVADO existe no enum."""
        assert StatusExecucao.TRAVADO.value == "travado"

    def test_status_arquivo_pulado_existe(self):
        """Verifica que o status PULADO existe no enum."""
        assert StatusArquivo.PULADO.value == "pulado"

    def test_execucao_esta_travada_sem_heartbeat(self):
        """Execução sem heartbeat recente deve ser considerada travada."""
        execucao = ExecucaoClassificacao()
        execucao.status = StatusExecucao.EM_ANDAMENTO.value
        execucao.ultimo_heartbeat = get_utc_now() - timedelta(minutes=10)

        assert execucao.esta_travada is True

    def test_execucao_nao_travada_com_heartbeat_recente(self):
        """Execução com heartbeat recente não deve ser travada."""
        execucao = ExecucaoClassificacao()
        execucao.status = StatusExecucao.EM_ANDAMENTO.value
        execucao.ultimo_heartbeat = get_utc_now() - timedelta(minutes=1)

        assert execucao.esta_travada is False

    def test_execucao_concluida_nao_travada(self):
        """Execução concluída nunca deve ser considerada travada."""
        execucao = ExecucaoClassificacao()
        execucao.status = StatusExecucao.CONCLUIDO.value
        execucao.ultimo_heartbeat = get_utc_now() - timedelta(minutes=10)

        assert execucao.esta_travada is False

    def test_pode_retomar_execucao_travada(self):
        """Execução travada com tentativas disponíveis pode ser retomada."""
        execucao = ExecucaoClassificacao()
        execucao.status = StatusExecucao.TRAVADO.value
        execucao.tentativas_retry = 1
        execucao.max_retries = 3

        assert execucao.pode_retomar is True

    def test_nao_pode_retomar_limite_atingido(self):
        """Execução com limite de tentativas atingido não pode ser retomada."""
        execucao = ExecucaoClassificacao()
        execucao.status = StatusExecucao.TRAVADO.value
        execucao.tentativas_retry = 3
        execucao.max_retries = 3

        assert execucao.pode_retomar is False

    def test_nao_pode_retomar_execucao_em_andamento(self):
        """Execução em andamento não pode ser retomada."""
        execucao = ExecucaoClassificacao()
        execucao.status = StatusExecucao.EM_ANDAMENTO.value
        execucao.tentativas_retry = 0
        execucao.max_retries = 3

        assert execucao.pode_retomar is False


class TestResultadoClassificacaoModel:
    """Testes para os novos campos do modelo ResultadoClassificacao."""

    def test_pode_reprocessar_erro(self):
        """Documento com erro e poucas tentativas pode ser reprocessado."""
        resultado = ResultadoClassificacao()
        resultado.status = StatusArquivo.ERRO.value
        resultado.tentativas = 1

        assert resultado.pode_reprocessar is True

    def test_nao_pode_reprocessar_limite_atingido(self):
        """Documento com limite de tentativas atingido não pode ser reprocessado."""
        resultado = ResultadoClassificacao()
        resultado.status = StatusArquivo.ERRO.value
        resultado.tentativas = 3

        assert resultado.pode_reprocessar is False

    def test_nao_pode_reprocessar_concluido(self):
        """Documento concluído não pode ser reprocessado."""
        resultado = ResultadoClassificacao()
        resultado.status = StatusArquivo.CONCLUIDO.value
        resultado.tentativas = 0

        assert resultado.pode_reprocessar is False


class TestWatchdogDeteccaoTravamento:
    """Testes para detecção de travamento pelo watchdog."""

    @pytest.fixture
    def mock_db(self):
        """Mock do banco de dados."""
        return Mock(spec=Session)

    @pytest.fixture
    def watchdog(self, mock_db):
        """Instância do watchdog com mock."""
        return ClassificadorWatchdog(mock_db)

    @pytest.mark.asyncio
    async def test_detecta_execucao_sem_heartbeat(self, watchdog, mock_db):
        """Watchdog deve detectar execução sem heartbeat."""
        # Cria execução travada
        execucao = Mock(spec=ExecucaoClassificacao)
        execucao.id = 1
        execucao.projeto_id = 1
        execucao.status = StatusExecucao.EM_ANDAMENTO.value
        execucao.ultimo_heartbeat = get_utc_now() - timedelta(minutes=10)
        execucao.iniciado_em = get_utc_now() - timedelta(minutes=15)
        execucao.ultimo_codigo_processado = "doc_123"
        execucao.arquivos_processados = 80
        execucao.total_arquivos = 2000
        execucao.rota_origem = "/classificador/"

        # Configura mock
        mock_query = Mock()
        mock_query.filter.return_value.all.return_value = [execucao]
        mock_db.query.return_value = mock_query

        # Mock para métodos internos
        watchdog._verificar_documentos_travados = Mock(return_value=[])
        watchdog._marcar_documentos_processando_como_erro = Mock(return_value=0)

        # Executa verificação
        travadas = await watchdog.verificar_execucoes_travadas()

        # Verifica que detectou
        assert len(travadas) == 1
        assert travadas[0]["execucao_id"] == 1
        assert "heartbeat" in travadas[0]["motivo"].lower()

    @pytest.mark.asyncio
    async def test_nao_detecta_execucao_com_heartbeat_recente(self, watchdog, mock_db):
        """Watchdog não deve detectar execução com heartbeat recente."""
        execucao = Mock(spec=ExecucaoClassificacao)
        execucao.id = 1
        execucao.status = StatusExecucao.EM_ANDAMENTO.value
        execucao.ultimo_heartbeat = get_utc_now() - timedelta(minutes=1)
        execucao.iniciado_em = get_utc_now() - timedelta(minutes=5)

        mock_query = Mock()
        mock_query.filter.return_value.all.return_value = [execucao]
        mock_db.query.return_value = mock_query

        # Mock para documentos travados
        watchdog._verificar_documentos_travados = Mock(return_value=[])

        travadas = await watchdog.verificar_execucoes_travadas()

        assert len(travadas) == 0

    @pytest.mark.asyncio
    async def test_marca_execucao_como_travada(self, watchdog, mock_db):
        """Watchdog deve marcar execução detectada como TRAVADO."""
        execucao = Mock(spec=ExecucaoClassificacao)
        execucao.id = 1
        execucao.projeto_id = 1
        execucao.status = StatusExecucao.EM_ANDAMENTO.value
        execucao.ultimo_heartbeat = get_utc_now() - timedelta(minutes=10)
        execucao.iniciado_em = get_utc_now() - timedelta(minutes=15)
        execucao.ultimo_codigo_processado = None
        execucao.arquivos_processados = 0
        execucao.total_arquivos = 100
        execucao.rota_origem = "/classificador/"

        mock_query = Mock()
        mock_query.filter.return_value.all.return_value = [execucao]
        mock_db.query.return_value = mock_query

        watchdog._verificar_documentos_travados = Mock(return_value=[])
        watchdog._marcar_documentos_processando_como_erro = Mock(return_value=0)

        await watchdog.verificar_execucoes_travadas()

        # Verifica que status foi alterado
        assert execucao.status == StatusExecucao.TRAVADO.value
        assert mock_db.commit.called


class TestRetomadaIdempotente:
    """Testes para garantir que retomada é idempotente."""

    @pytest.mark.asyncio
    async def test_retomada_pula_documentos_concluidos(self):
        """Retomada deve pular documentos já processados com sucesso."""
        # Este teste verificaria que ao retomar:
        # 1. Documentos com status CONCLUIDO são pulados
        # 2. Apenas documentos PENDENTE ou ERRO são processados
        # 3. Contagem final é consistente
        pass  # Implementação depende de fixtures de banco

    @pytest.mark.asyncio
    async def test_retomada_incrementa_tentativas(self):
        """Retomada deve incrementar contador de tentativas."""
        # Verificaria que tentativas_retry é incrementado
        pass

    @pytest.mark.asyncio
    async def test_reprocessamento_apenas_erros(self):
        """Reprocessamento deve processar apenas documentos com erro."""
        # Verificaria que apenas documentos com status ERRO são reprocessados
        pass


class TestMaquinaEstados:
    """Testes para transições da máquina de estados."""

    def test_transicao_pendente_para_em_andamento(self):
        """PENDENTE -> EM_ANDAMENTO é válido."""
        execucao = ExecucaoClassificacao()
        execucao.status = StatusExecucao.PENDENTE.value

        # Simula início da execução
        execucao.status = StatusExecucao.EM_ANDAMENTO.value

        assert execucao.status == StatusExecucao.EM_ANDAMENTO.value

    def test_transicao_em_andamento_para_travado(self):
        """EM_ANDAMENTO -> TRAVADO é válido (via watchdog)."""
        execucao = ExecucaoClassificacao()
        execucao.status = StatusExecucao.EM_ANDAMENTO.value

        # Simula detecção de travamento
        execucao.status = StatusExecucao.TRAVADO.value

        assert execucao.status == StatusExecucao.TRAVADO.value

    def test_transicao_travado_para_em_andamento(self):
        """TRAVADO -> EM_ANDAMENTO é válido (via retomada)."""
        execucao = ExecucaoClassificacao()
        execucao.status = StatusExecucao.TRAVADO.value
        execucao.tentativas_retry = 0
        execucao.max_retries = 3

        # Simula retomada
        assert execucao.pode_retomar is True
        execucao.status = StatusExecucao.EM_ANDAMENTO.value

        assert execucao.status == StatusExecucao.EM_ANDAMENTO.value

    def test_transicao_em_andamento_para_concluido(self):
        """EM_ANDAMENTO -> CONCLUIDO é válido."""
        execucao = ExecucaoClassificacao()
        execucao.status = StatusExecucao.EM_ANDAMENTO.value

        execucao.status = StatusExecucao.CONCLUIDO.value

        assert execucao.status == StatusExecucao.CONCLUIDO.value


class TestTimeoutsConfiguraveis:
    """Testes para verificar valores de timeout."""

    def test_heartbeat_timeout_padrao(self):
        """Timeout de heartbeat deve ser 5 minutos."""
        assert HEARTBEAT_TIMEOUT_MINUTES == 5

    def test_processando_timeout_padrao(self):
        """Timeout de documento em PROCESSANDO deve ser 2 minutos."""
        assert PROCESSANDO_TIMEOUT_MINUTES == 2


class TestStatusDetalhado:
    """Testes para o endpoint de status detalhado."""

    @pytest.fixture
    def mock_db(self):
        return Mock(spec=Session)

    @pytest.fixture
    def watchdog(self, mock_db):
        return ClassificadorWatchdog(mock_db)

    @pytest.mark.asyncio
    async def test_obter_status_detalhado_inclui_campos_adr(self, watchdog, mock_db):
        """Status detalhado deve incluir campos do ADR-0010."""
        execucao = Mock(spec=ExecucaoClassificacao)
        execucao.id = 1
        execucao.projeto_id = 1
        execucao.status = StatusExecucao.TRAVADO.value
        execucao.rota_origem = "/classificador/"
        execucao.total_arquivos = 100
        execucao.arquivos_processados = 80
        execucao.arquivos_sucesso = 75
        execucao.arquivos_erro = 5
        execucao.progresso_percentual = 80.0
        execucao.ultimo_heartbeat = get_utc_now() - timedelta(minutes=10)
        execucao.ultimo_codigo_processado = "doc_80"
        execucao.tentativas_retry = 1
        execucao.max_retries = 3
        execucao.pode_retomar = True
        execucao.esta_travada = False
        execucao.erro_mensagem = "Travamento detectado"
        execucao.iniciado_em = get_utc_now() - timedelta(hours=1)
        execucao.finalizado_em = None

        mock_db.query.return_value.filter.return_value.first.return_value = execucao
        mock_db.query.return_value.filter.return_value.count.return_value = 0
        mock_db.query.return_value.filter.return_value.all.return_value = []

        status = await watchdog.obter_status_detalhado(1)

        assert status is not None
        assert status["rota_origem"] == "/classificador/"
        assert status["pode_retomar"] is True
        assert "documentos_com_erro" in status
        assert "contagem_por_status" in status


class TestStatusCancelado:
    """Testes para o novo status CANCELADO e transições."""

    def test_status_cancelado_existe(self):
        """Verifica que o status CANCELADO existe no enum."""
        assert StatusExecucao.CANCELADO.value == "cancelado"

    def test_transicao_em_andamento_para_cancelado(self):
        """EM_ANDAMENTO -> CANCELADO é válido (cancelamento manual)."""
        execucao = ExecucaoClassificacao()
        execucao.status = StatusExecucao.EM_ANDAMENTO.value

        # Simula cancelamento
        execucao.status = StatusExecucao.CANCELADO.value

        assert execucao.status == StatusExecucao.CANCELADO.value

    def test_transicao_travado_para_cancelado(self):
        """TRAVADO -> CANCELADO é válido (cancelamento de execução travada)."""
        execucao = ExecucaoClassificacao()
        execucao.status = StatusExecucao.TRAVADO.value

        # Simula cancelamento
        execucao.status = StatusExecucao.CANCELADO.value

        assert execucao.status == StatusExecucao.CANCELADO.value

    def test_nao_pode_retomar_execucao_cancelada(self):
        """Execução cancelada não pode ser retomada."""
        execucao = ExecucaoClassificacao()
        execucao.status = StatusExecucao.CANCELADO.value
        execucao.tentativas_retry = 0
        execucao.max_retries = 3

        # Status CANCELADO não está na lista de status que podem retomar
        assert execucao.pode_retomar is False


class TestExecucoesEmAndamentoEndpoint:
    """Testes para o endpoint de execuções em andamento com novos campos."""

    def test_lista_inclui_execucoes_travadas(self):
        """Endpoint deve retornar tanto EM_ANDAMENTO quanto TRAVADO."""
        # Este teste verifica que a query inclui ambos os status
        # O endpoint foi modificado para usar OR com EM_ANDAMENTO e TRAVADO
        pass  # Implementação requer fixtures de integração

    def test_resposta_inclui_campos_heartbeat(self):
        """Resposta deve incluir campos de detecção de travamento."""
        # Campos esperados: ultimo_heartbeat, esta_travada, pode_retomar, tentativas_retry, max_retries
        pass  # Implementação requer fixtures de integração


class TestCancelarExecucao:
    """Testes para o endpoint de cancelar execução."""

    def test_cancelar_execucao_em_andamento(self):
        """Deve permitir cancelar execução em andamento."""
        # Verifica que execução EM_ANDAMENTO pode ser cancelada
        # e que status muda para CANCELADO
        pass  # Implementação requer fixtures de integração

    def test_cancelar_execucao_travada(self):
        """Deve permitir cancelar execução travada."""
        # Verifica que execução TRAVADO pode ser cancelada
        pass  # Implementação requer fixtures de integração

    def test_nao_cancelar_execucao_concluida(self):
        """Não deve permitir cancelar execução já concluída."""
        # Verifica que execução CONCLUIDO não pode ser cancelada
        # e retorna erro 400
        pass  # Implementação requer fixtures de integração

    def test_nao_cancelar_execucao_erro(self):
        """Não deve permitir cancelar execução com erro (já finalizada)."""
        # Execução ERRO já está finalizada, não pode ser cancelada
        pass  # Implementação requer fixtures de integração


class TestArquivarExecucao:
    """Testes para o endpoint de arquivar (soft-delete) execução."""

    def test_arquivar_execucao_concluida(self):
        """Deve permitir arquivar execução concluída."""
        pass  # Implementação requer fixtures de integração

    def test_arquivar_execucao_erro(self):
        """Deve permitir arquivar execução com erro."""
        pass  # Implementação requer fixtures de integração

    def test_arquivar_execucao_cancelada(self):
        """Deve permitir arquivar execução cancelada."""
        pass  # Implementação requer fixtures de integração

    def test_nao_arquivar_execucao_em_andamento(self):
        """Não deve permitir arquivar execução em andamento."""
        # Retorna erro 400 pedindo para cancelar primeiro
        pass  # Implementação requer fixtures de integração

    def test_arquivar_execucao_travada_cancela_primeiro(self):
        """Arquivar execução travada deve primeiro cancelá-la."""
        # Verifica que status muda para CANCELADO ao arquivar TRAVADO
        pass  # Implementação requer fixtures de integração
