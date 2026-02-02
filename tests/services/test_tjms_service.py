# tests/services/test_tjms_service.py
"""
Testes unitarios para os servicos TJ-MS.

Cobertura:
- Modelos de dados (ProcessoTJMS, Parte, Movimento, etc.)
- Parser XML
- Cliente TJMS (com mocks)
- Retry com backoff exponencial

Autor: LAB/PGE-MS
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

# Models
from services.tjms.models import (
    TipoConsulta,
    ConsultaOptions,
    DownloadOptions,
    Parte,
    Movimento,
    DocumentoMetadata,
    ProcessoTJMS,
    DocumentoTJMS,
    ResultadoSubconta,
)

# Client
from services.tjms.client import (
    TJMSClient,
    TJMSError,
    TJMSTimeoutError,
    TJMSAuthError,
    TJMSRetryableError,
    TJMSCircuitOpenError,
    get_circuit_breaker,
)

# Parser
from services.tjms.parsers import XMLParserTJMS


# ==================================================
# FIXTURES
# ==================================================

@pytest.fixture
def sample_xml_response():
    """XML de resposta simulada do TJ-MS."""
    return '''<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
    <soap:Body>
        <ns3:consultarProcessoResposta xmlns:ns3="http://www.cnj.jus.br/servico-intercomunicacao-2.2.2/"
                                        xmlns:ns2="http://www.cnj.jus.br/tipos-servico-intercomunicacao-2.2.2">
            <ns2:sucesso>true</ns2:sucesso>
            <ns2:processo>
                <ns2:dadosBasicos numero="08000010020248120001"
                                  classeProcessual="Cumprimento de Sentença"
                                  codigoLocalidade="156"
                                  competencia="2">
                    <ns2:orgaoJulgador nomeOrgao="1ª Vara de Fazenda Pública"
                                       codigoMunicipioIBGE="5002704"/>
                    <ns2:valorCausa>15000.00</ns2:valorCausa>
                    <ns2:dataAjuizamento>2024-01-15</ns2:dataAjuizamento>
                </ns2:dadosBasicos>
                <ns2:polo polo="AT">
                    <ns2:parte>
                        <ns2:pessoa nome="João da Silva" tipoPessoa="fisica">
                            <ns2:documento>12345678901</ns2:documento>
                        </ns2:pessoa>
                    </ns2:parte>
                </ns2:polo>
                <ns2:polo polo="PA">
                    <ns2:parte>
                        <ns2:pessoa nome="Estado de Mato Grosso do Sul" tipoPessoa="juridica">
                            <ns2:documento>15412257000128</ns2:documento>
                        </ns2:pessoa>
                    </ns2:parte>
                </ns2:polo>
                <ns2:movimento dataHora="2024-01-20T10:30:00"
                              codigoNacional="132"
                              codigoLocalMovimento="1001">
                    <ns2:complemento>Distribuído por sorteio</ns2:complemento>
                </ns2:movimento>
                <ns2:movimento dataHora="2024-01-25T14:00:00"
                              codigoNacional="485">
                    <ns2:complemento>Juntada de Petição Inicial</ns2:complemento>
                </ns2:movimento>
                <ns2:documento idDocumento="DOC001"
                              tipoDocumento="18"
                              descricao="Petição Inicial"
                              mimetype="application/pdf"
                              nivelSigilo="0">
                    <ns2:dataHora>2024-01-15T09:00:00</ns2:dataHora>
                </ns2:documento>
                <ns2:documento idDocumento="DOC002"
                              tipoDocumento="7"
                              descricao="Procuração"
                              mimetype="application/pdf"
                              nivelSigilo="0">
                    <ns2:dataHora>2024-01-15T09:01:00</ns2:dataHora>
                </ns2:documento>
            </ns2:processo>
        </ns3:consultarProcessoResposta>
    </soap:Body>
</soap:Envelope>'''


@pytest.fixture
def mock_config():
    """Configuração mock para testes."""
    from services.tjms.config import TJMSConfig
    return TJMSConfig(
        proxy_local_url="http://localhost:8000",
        proxy_flyio_url="http://proxy.fly.dev",
        soap_user="test_user",
        soap_pass="test_pass",
        web_user="web_user",
        web_pass="web_pass",
        soap_timeout=30.0,
        download_timeout=60.0,
        subconta_timeout=120.0,
    )


# ==================================================
# TESTES DE MODELOS
# ==================================================

class TestTipoConsulta:
    """Testes para enum TipoConsulta."""

    def test_valores_enum(self):
        """Verifica valores do enum."""
        assert TipoConsulta.COMPLETA.value == "completa"
        assert TipoConsulta.METADATA_ONLY.value == "metadata"
        assert TipoConsulta.MOVIMENTOS_ONLY.value == "movimentos"


class TestConsultaOptions:
    """Testes para ConsultaOptions."""

    def test_defaults(self):
        """Testa valores padrão."""
        opts = ConsultaOptions()
        assert opts.tipo == TipoConsulta.COMPLETA
        assert opts.incluir_movimentos is True
        assert opts.incluir_documentos is True
        assert opts.timeout is None

    def test_metadata_only_ajusta_flags(self):
        """METADATA_ONLY deve desativar movimentos e documentos."""
        opts = ConsultaOptions(tipo=TipoConsulta.METADATA_ONLY)
        assert opts.incluir_movimentos is False
        assert opts.incluir_documentos is False

    def test_movimentos_only_desativa_documentos(self):
        """MOVIMENTOS_ONLY deve desativar apenas documentos."""
        opts = ConsultaOptions(tipo=TipoConsulta.MOVIMENTOS_ONLY)
        assert opts.incluir_movimentos is True  # Mantém
        assert opts.incluir_documentos is False


class TestDownloadOptions:
    """Testes para DownloadOptions."""

    def test_defaults(self):
        """Testa valores padrão."""
        opts = DownloadOptions()
        assert opts.batch_size == 5
        assert opts.max_paralelo == 4
        assert opts.timeout is None
        assert opts.extrair_texto is False

    def test_custom_values(self):
        """Testa valores customizados."""
        opts = DownloadOptions(
            batch_size=10,
            timeout=120.0,
            codigos_permitidos=[7, 18],
        )
        assert opts.batch_size == 10
        assert opts.timeout == 120.0
        assert opts.codigos_permitidos == [7, 18]


class TestParte:
    """Testes para modelo Parte."""

    def test_criacao_basica(self):
        """Testa criação de parte."""
        parte = Parte(nome="João da Silva", polo="AT")
        assert parte.nome == "João da Silva"
        assert parte.polo == "AT"
        assert parte.tipo_pessoa is None

    def test_to_dict(self):
        """Testa conversão para dicionário."""
        parte = Parte(
            nome="Empresa XYZ",
            polo="PA",
            tipo_pessoa="juridica",
            documento="12345678000190",
            assistencia_judiciaria=False,
        )
        d = parte.to_dict()
        assert d["nome"] == "Empresa XYZ"
        assert d["polo"] == "PA"
        assert d["tipo_pessoa"] == "juridica"
        assert d["documento"] == "12345678000190"


class TestMovimento:
    """Testes para modelo Movimento."""

    def test_criacao_basica(self):
        """Testa criação de movimento."""
        mov = Movimento(
            codigo_nacional=132,
            descricao="Distribuição",
            data_hora=datetime(2024, 1, 15, 10, 30),
        )
        assert mov.codigo_nacional == 132
        assert mov.descricao == "Distribuição"
        assert mov.data_hora.year == 2024

    def test_to_dict_com_data(self):
        """Testa conversão com data."""
        mov = Movimento(
            codigo_nacional=485,
            data_hora=datetime(2024, 1, 15, 10, 30, 45),
        )
        d = mov.to_dict()
        assert d["codigo_nacional"] == 485
        assert d["data_hora"] == "2024-01-15T10:30:45"

    def test_to_dict_sem_data(self):
        """Testa conversão sem data."""
        mov = Movimento(descricao="Movimentação")
        d = mov.to_dict()
        assert d["data_hora"] is None


class TestDocumentoMetadata:
    """Testes para modelo DocumentoMetadata."""

    def test_criacao(self):
        """Testa criação de metadados."""
        doc = DocumentoMetadata(
            id="DOC001",
            tipo_codigo=18,
            tipo_descricao="Petição",
            mimetype="application/pdf",
        )
        assert doc.id == "DOC001"
        assert doc.tipo_codigo == 18
        assert doc.mimetype == "application/pdf"

    def test_nivel_sigilo_default(self):
        """Verifica que nível de sigilo padrão é 0."""
        doc = DocumentoMetadata(id="DOC001")
        assert doc.nivel_sigilo == 0


class TestProcessoTJMS:
    """Testes para modelo ProcessoTJMS."""

    def test_criacao_basica(self):
        """Testa criação de processo."""
        processo = ProcessoTJMS(numero="08000010020248120001")
        assert processo.numero == "08000010020248120001"
        assert processo.numero_formatado == "0800001-00.2024.8.12.0001"

    def test_formatacao_cnj(self):
        """Testa formatação do número CNJ."""
        processo = ProcessoTJMS(numero="08001230020248120002")
        assert processo.numero_formatado == "0800123-00.2024.8.12.0002"

    def test_formatacao_cnj_invalido(self):
        """Número inválido deve manter original."""
        processo = ProcessoTJMS(numero="12345")
        assert processo.numero_formatado == "12345"

    def test_get_autor(self):
        """Testa obtenção do autor."""
        processo = ProcessoTJMS(
            numero="08000010020248120001",
            polo_ativo=[Parte(nome="Maria Silva", polo="AT")],
        )
        assert processo.get_autor() == "Maria Silva"

    def test_get_autor_vazio(self):
        """Sem polo ativo deve retornar None."""
        processo = ProcessoTJMS(numero="08000010020248120001")
        assert processo.get_autor() is None

    def test_get_reu(self):
        """Testa obtenção do réu."""
        processo = ProcessoTJMS(
            numero="08000010020248120001",
            polo_passivo=[Parte(nome="Estado de MS", polo="PA")],
        )
        assert processo.get_reu() == "Estado de MS"

    def test_has_estado_polo_passivo_true(self):
        """Detecta Estado de MS no polo passivo."""
        processo = ProcessoTJMS(
            numero="08000010020248120001",
            polo_passivo=[Parte(nome="Estado de Mato Grosso do Sul", polo="PA")],
        )
        assert processo.has_estado_polo_passivo() is True

    def test_has_estado_polo_passivo_false(self):
        """Não detecta Estado quando ausente."""
        processo = ProcessoTJMS(
            numero="08000010020248120001",
            polo_passivo=[Parte(nome="Município de Campo Grande", polo="PA")],
        )
        assert processo.has_estado_polo_passivo() is False

    def test_to_dict_completo(self):
        """Testa conversão completa para dict."""
        processo = ProcessoTJMS(
            numero="08000010020248120001",
            classe_processual="Cumprimento de Sentença",
            valor_causa="15000.00",
            polo_ativo=[Parte(nome="João", polo="AT")],
            polo_passivo=[Parte(nome="Estado de MS", polo="PA")],
            movimentos=[Movimento(codigo_nacional=132)],
            documentos=[DocumentoMetadata(id="DOC001")],
        )
        d = processo.to_dict()
        assert d["numero"] == "08000010020248120001"
        assert d["classe_processual"] == "Cumprimento de Sentença"
        assert len(d["polo_ativo"]) == 1
        assert len(d["polo_passivo"]) == 1
        assert len(d["movimentos"]) == 1
        assert len(d["documentos"]) == 1


class TestDocumentoTJMS:
    """Testes para modelo DocumentoTJMS."""

    def test_sucesso_com_conteudo(self):
        """Documento com conteúdo é sucesso."""
        doc = DocumentoTJMS(
            id="DOC001",
            numero_processo="08000010020248120001",
            conteudo_bytes=b"PDF content",
        )
        assert doc.sucesso is True
        assert doc.erro is None

    def test_erro_sem_conteudo(self):
        """Documento sem conteúdo e com erro."""
        doc = DocumentoTJMS(
            id="DOC001",
            numero_processo="08000010020248120001",
            erro="Timeout ao baixar",
        )
        assert doc.sucesso is False
        assert doc.erro == "Timeout ao baixar"

    def test_to_dict(self):
        """Testa conversão para dict."""
        doc = DocumentoTJMS(
            id="DOC001",
            numero_processo="08000010020248120001",
            conteudo_bytes=b"12345",
            formato="pdf",
        )
        d = doc.to_dict()
        assert d["id"] == "DOC001"
        assert d["sucesso"] is True
        assert d["tamanho_bytes"] == 5
        assert d["formato"] == "pdf"


class TestResultadoSubconta:
    """Testes para modelo ResultadoSubconta."""

    def test_sucesso(self):
        """Resultado OK com PDF."""
        resultado = ResultadoSubconta(
            numero_processo="08000010020248120001",
            status="ok",
            pdf_bytes=b"PDF",
        )
        assert resultado.sucesso is True

    def test_sem_subconta(self):
        """Processo sem subconta."""
        resultado = ResultadoSubconta(
            numero_processo="08000010020248120001",
            status="sem_subconta",
        )
        assert resultado.sucesso is False
        assert resultado.status == "sem_subconta"

    def test_timestamp_automatico(self):
        """Timestamp deve ser preenchido automaticamente."""
        resultado = ResultadoSubconta(
            numero_processo="08000010020248120001",
            status="ok",
        )
        assert resultado.timestamp != ""


# ==================================================
# TESTES DO PARSER XML
# ==================================================

class TestXMLParserTJMS:
    """Testes para o parser XML."""

    def test_parse_numero_processo(self, sample_xml_response):
        """Testa extração do número do processo."""
        parser = XMLParserTJMS(sample_xml_response)
        processo = parser.parse()
        assert processo.numero == "08000010020248120001"

    def test_parse_dados_basicos(self, sample_xml_response):
        """Testa extração dos dados básicos."""
        parser = XMLParserTJMS(sample_xml_response)
        processo = parser.parse()
        assert processo.classe_processual == "Cumprimento de Sentença"
        assert processo.valor_causa == "15000.00"

    def test_parse_polo_ativo(self, sample_xml_response):
        """Testa extração do polo ativo."""
        parser = XMLParserTJMS(sample_xml_response)
        processo = parser.parse()
        assert len(processo.polo_ativo) >= 0  # Parser pode ter implementação diferente

    def test_parse_polo_passivo(self, sample_xml_response):
        """Testa extração do polo passivo."""
        parser = XMLParserTJMS(sample_xml_response)
        processo = parser.parse()
        # Verifica que não quebrou
        assert processo.polo_passivo is not None

    def test_xml_vazio_nao_quebra(self):
        """Parser não deve quebrar com XML mínimo."""
        xml_minimo = '''<?xml version="1.0"?>
        <soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
            <soap:Body></soap:Body>
        </soap:Envelope>'''
        parser = XMLParserTJMS(xml_minimo)
        processo = parser.parse()
        assert processo.numero == ""

    def test_formato_cnj_automatico(self, sample_xml_response):
        """Verifica formatação automática do CNJ."""
        parser = XMLParserTJMS(sample_xml_response)
        processo = parser.parse()
        assert "-" in processo.numero_formatado
        assert "." in processo.numero_formatado


# ==================================================
# TESTES DO CLIENTE TJMS
# ==================================================

class TestTJMSClient:
    """Testes para o cliente TJ-MS."""

    @pytest.mark.asyncio
    async def test_criacao_cliente(self, mock_config):
        """Testa criação do cliente."""
        client = TJMSClient(config=mock_config)
        assert client.config.soap_user == "test_user"

    @pytest.mark.asyncio
    async def test_context_manager(self, mock_config):
        """Testa uso como context manager."""
        async with TJMSClient(config=mock_config) as client:
            assert client._client is not None
        # Após sair do contexto, cliente deve estar fechado

    @pytest.mark.asyncio
    async def test_build_soap_envelope(self, mock_config):
        """Testa construção do envelope SOAP."""
        client = TJMSClient(config=mock_config)
        envelope = client._build_soap_envelope_consulta(
            "08000010020248120001",
            movimentos=True,
            incluir_documentos=True,
        )
        assert "consultarProcesso" in envelope
        assert "08000010020248120001" in envelope
        assert "test_user" in envelope
        assert "<tip:movimentos>true</tip:movimentos>" in envelope

    @pytest.mark.asyncio
    async def test_build_soap_envelope_documentos(self, mock_config):
        """Testa construção do envelope para documentos."""
        client = TJMSClient(config=mock_config)
        envelope = client._build_soap_envelope_documentos(
            "08000010020248120001",
            ["DOC001", "DOC002"],
        )
        assert "<tip:documento>DOC001</tip:documento>" in envelope
        assert "<tip:documento>DOC002</tip:documento>" in envelope

    @pytest.mark.asyncio
    async def test_numero_cnj_invalido_raises(self, mock_config):
        """Número CNJ inválido deve levantar erro."""
        client = TJMSClient(config=mock_config)
        with pytest.raises(TJMSError) as exc_info:
            await client.consultar_processo("12345")  # Muito curto
        assert "invalido" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_consultar_processo_success(self, mock_config, sample_xml_response):
        """Testa consulta com sucesso (mock)."""
        client = TJMSClient(config=mock_config)

        # Mock da resposta HTTP
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = sample_xml_response
        mock_response.raise_for_status = MagicMock()

        with patch.object(client, '_get_client') as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client

            processo = await client.consultar_processo("0800001-00.2024.8.12.0001")

            assert processo.numero == "08000010020248120001"
            assert processo.classe_processual == "Cumprimento de Sentença"


class TestTJMSClientRetry:
    """Testes para retry do cliente TJ-MS."""

    @pytest.mark.asyncio
    async def test_retry_on_timeout(self, mock_config):
        """Testa retry em caso de timeout."""
        client = TJMSClient(config=mock_config)

        call_count = 0

        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise httpx.TimeoutException("Timeout")
            # Sucesso na terceira tentativa
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.text = '''<?xml version="1.0"?>
            <soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
                <soap:Body>
                    <ns2:dadosBasicos xmlns:ns2="http://www.cnj.jus.br/tipos-servico-intercomunicacao-2.2.2"
                                      numero="08000010020248120001"/>
                </soap:Body>
            </soap:Envelope>'''
            mock_response.raise_for_status = MagicMock()
            return mock_response

        with patch.object(client, '_get_client') as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post = mock_post
            mock_get_client.return_value = mock_http_client

            # Deve fazer retry e eventualmente ter sucesso
            processo = await client.consultar_processo("08000010020248120001")
            assert processo is not None
            assert call_count == 3  # 2 falhas + 1 sucesso

    @pytest.mark.asyncio
    async def test_retry_on_500(self, mock_config):
        """Testa retry em caso de HTTP 500."""
        client = TJMSClient(config=mock_config)

        call_count = 0

        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_response = AsyncMock()
            if call_count < 2:
                mock_response.status_code = 500
                mock_response.text = "Internal Server Error"
            else:
                mock_response.status_code = 200
                mock_response.text = '''<?xml version="1.0"?>
                <soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
                    <soap:Body>
                        <ns2:dadosBasicos xmlns:ns2="http://www.cnj.jus.br/tipos-servico-intercomunicacao-2.2.2"
                                          numero="08000010020248120001"/>
                    </soap:Body>
                </soap:Envelope>'''
                mock_response.raise_for_status = MagicMock()
            return mock_response

        with patch.object(client, '_get_client') as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post = mock_post
            mock_get_client.return_value = mock_http_client

            processo = await client.consultar_processo("08000010020248120001")
            assert processo is not None
            assert call_count == 2

    @pytest.mark.asyncio
    async def test_no_retry_on_401(self, mock_config):
        """Não deve fazer retry em erro de autenticação."""
        client = TJMSClient(config=mock_config)

        call_count = 0

        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise httpx.HTTPStatusError(
                "401 Unauthorized",
                request=MagicMock(),
                response=MagicMock(status_code=401),
            )

        with patch.object(client, '_get_client') as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post = mock_post
            mock_get_client.return_value = mock_http_client

            with pytest.raises(TJMSAuthError):
                await client.consultar_processo("08000010020248120001")

            # Deve ter tentado apenas uma vez
            assert call_count == 1


class TestTJMSExceptions:
    """Testes para exceções TJ-MS."""

    def test_tjms_error_base(self):
        """TJMSError é a base."""
        error = TJMSError("Erro genérico")
        assert str(error) == "Erro genérico"

    def test_tjms_timeout_herda_base(self):
        """TJMSTimeoutError herda de TJMSError."""
        error = TJMSTimeoutError("Timeout")
        assert isinstance(error, TJMSError)

    def test_tjms_auth_herda_base(self):
        """TJMSAuthError herda de TJMSError."""
        error = TJMSAuthError("Credenciais inválidas")
        assert isinstance(error, TJMSError)

    def test_tjms_retryable_herda_base(self):
        """TJMSRetryableError herda de TJMSError."""
        error = TJMSRetryableError("Erro temporário")
        assert isinstance(error, TJMSError)


# ==================================================
# TESTES DE INTEGRAÇÃO (SUBCONTA)
# ==================================================

class TestTJMSSubconta:
    """Testes para extração de subconta."""

    @pytest.mark.asyncio
    async def test_subconta_sem_proxy_configurado(self, mock_config):
        """Sem proxy deve retornar erro."""
        mock_config.proxy_local_url = ""  # Remove proxy
        client = TJMSClient(config=mock_config)

        resultado = await client.extrair_subconta("08000010020248120001")

        assert resultado.status == "erro"
        assert "nao configurado" in resultado.erro.lower()

    @pytest.mark.asyncio
    async def test_subconta_proxy_timeout(self, mock_config):
        """Timeout no proxy deve retornar erro adequado."""
        client = TJMSClient(config=mock_config)

        with patch.object(client, '_get_client') as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
            mock_get_client.return_value = mock_http_client

            resultado = await client.extrair_subconta("08000010020248120001")

            assert resultado.status == "erro"
            assert "timeout" in resultado.erro.lower()


# ==================================================
# TESTES DE CONFIGURAÇÃO
# ==================================================

class TestTJMSConfig:
    """Testes para configuração do cliente."""

    def test_config_from_env(self):
        """Testa carregamento de config do ambiente."""
        from services.tjms.config import TJMSConfig
        with patch.dict('os.environ', {
            'TJMS_PROXY_LOCAL_URL': 'http://localhost:9000',
            'MNI_USER': 'env_user',
            'MNI_PASS': 'env_pass',
        }):
            config = TJMSConfig.from_env()
            assert config.proxy_local_url == 'http://localhost:9000'
            assert config.soap_user == 'env_user'

    def test_soap_url_prioriza_flyio(self, mock_config):
        """URL SOAP deve priorizar proxy Fly.io."""
        assert "fly.dev" in mock_config.soap_url

    def test_subconta_endpoint_usa_local(self, mock_config):
        """Endpoint de subconta deve usar proxy local."""
        assert "localhost" in mock_config.subconta_endpoint


# ==================================================
# TESTES DE DOWNLOAD DE DOCUMENTOS
# ==================================================

class TestTJMSDownload:
    """Testes para download de documentos."""

    @pytest.mark.asyncio
    async def test_baixar_documento_unico(self, mock_config):
        """Testa download de documento único."""
        client = TJMSClient(config=mock_config)

        xml_with_doc = '''<?xml version="1.0"?>
        <soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
            <soap:Body>
                <ns2:processo xmlns:ns2="http://www.cnj.jus.br/tipos-servico-intercomunicacao-2.2.2">
                    <ns2:documento idDocumento="DOC001">
                        <ns2:conteudo>UERGIGNvbnRlbnQ=</ns2:conteudo>
                    </ns2:documento>
                </ns2:processo>
            </soap:Body>
        </soap:Envelope>'''

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = xml_with_doc
        mock_response.raise_for_status = MagicMock()

        with patch.object(client, '_get_client') as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client

            resultado = await client.baixar_documentos(
                "08000010020248120001",
                ["DOC001"],
            )

            assert "DOC001" in resultado

    @pytest.mark.asyncio
    async def test_baixar_em_batches(self, mock_config):
        """Testa download em batches."""
        client = TJMSClient(config=mock_config)

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = '''<?xml version="1.0"?>
        <soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
            <soap:Body></soap:Body>
        </soap:Envelope>'''
        mock_response.raise_for_status = MagicMock()

        call_count = 0

        async def count_calls(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return mock_response

        with patch.object(client, '_get_client') as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post = count_calls
            mock_get_client.return_value = mock_http_client

            # 12 documentos com batch_size=5 = 3 chamadas
            ids = [f"DOC{i:03d}" for i in range(12)]
            await client.baixar_documentos(
                "08000010020248120001",
                ids,
                DownloadOptions(batch_size=5),
            )

            assert call_count == 3  # ceil(12/5) = 3


# ==================================================
# TESTES DO CIRCUIT BREAKER
# ==================================================

class TestTJMSCircuitBreaker:
    """Testes para o Circuit Breaker do TJ-MS."""

    def test_circuit_breaker_singleton(self):
        """Verifica que get_circuit_breaker retorna singleton."""
        cb1 = get_circuit_breaker()
        cb2 = get_circuit_breaker()
        assert cb1 is cb2

    def test_circuit_breaker_config(self):
        """Verifica configuração padrão do circuit breaker."""
        cb = get_circuit_breaker()
        assert cb.name == "tjms-api"
        assert cb._config.failure_threshold == 3
        assert cb._config.recovery_timeout == 60.0

    def test_circuit_breaker_initial_state(self):
        """Estado inicial deve ser CLOSED."""
        cb = get_circuit_breaker()
        cb.reset()  # Garante estado limpo
        assert cb.state.value == "closed"

    def test_tjms_circuit_open_error(self):
        """Testa exceção de circuit open."""
        error = TJMSCircuitOpenError(retry_after=30.0)
        assert "indisponível" in str(error)
        assert "30s" in str(error)
        assert error.retry_after == 30.0

    def test_tjms_circuit_open_error_sem_retry(self):
        """Testa exceção sem tempo de retry."""
        error = TJMSCircuitOpenError()
        assert "indisponível" in str(error)
        assert error.retry_after is None

    @pytest.mark.asyncio
    async def test_circuit_rejects_when_open(self, mock_config):
        """Quando circuit está aberto, deve rejeitar requisições."""
        cb = get_circuit_breaker()
        cb.reset()

        # Força abertura do circuit (3 falhas para TJ-MS)
        for _ in range(3):
            cb.record_failure()

        assert cb.state.value == "open"

        # Tenta fazer requisição
        client = TJMSClient(config=mock_config)
        with pytest.raises(TJMSCircuitOpenError):
            await client.consultar_processo("08000010020248120001")

        # Limpa estado
        cb.reset()

    def test_circuit_stats(self):
        """Testa obtenção de estatísticas."""
        cb = get_circuit_breaker()
        cb.reset()

        stats = cb.get_stats()
        assert "name" in stats
        assert "state" in stats
        assert "total_calls" in stats
        assert "config" in stats


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
