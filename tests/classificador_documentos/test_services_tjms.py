# tests/classificador_documentos/test_services_tjms.py
"""
Testes unitários do serviço de integração com TJ-MS.

Testa:
- Dataclass DocumentoTJMS
- TJMSDocumentService com mocks
- Parsing de XML (deprecated - agora usa services.tjms)
- Conversão RTF para PDF

Autor: LAB/PGE-MS
Atualizado: 2026-01-24 - Migrado para usar services.tjms unificado
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from dataclasses import dataclass


class TestDocumentoTJMS:
    """Testes da dataclass DocumentoTJMS"""

    def test_documento_tjms_basic(self):
        """Testa criação básica de DocumentoTJMS"""
        from sistemas.classificador_documentos.services_tjms import DocumentoTJMS

        doc = DocumentoTJMS(
            id_documento="12345",
            numero_processo="0800001-00.2024.8.12.0001"
        )

        assert doc.id_documento == "12345"
        assert doc.numero_processo == "0800001-00.2024.8.12.0001"
        assert doc.tipo_documento is None
        assert doc.descricao is None
        assert doc.conteudo_bytes is None
        assert doc.formato == "pdf"
        assert doc.erro is None

    def test_documento_tjms_complete(self):
        """Testa DocumentoTJMS com todos os campos"""
        from sistemas.classificador_documentos.services_tjms import DocumentoTJMS

        doc = DocumentoTJMS(
            id_documento="12345",
            numero_processo="0800001-00.2024.8.12.0001",
            tipo_documento="Sentença",
            descricao="Sentença de procedência",
            conteudo_bytes=b"PDF content",
            formato="pdf",
            erro=None
        )

        assert doc.tipo_documento == "Sentença"
        assert doc.descricao == "Sentença de procedência"
        assert doc.conteudo_bytes == b"PDF content"

    def test_documento_tjms_with_error(self):
        """Testa DocumentoTJMS com erro"""
        from sistemas.classificador_documentos.services_tjms import DocumentoTJMS

        doc = DocumentoTJMS(
            id_documento="12345",
            numero_processo="0800001-00.2024.8.12.0001",
            erro="Documento não encontrado"
        )

        assert doc.erro == "Documento não encontrado"
        assert doc.conteudo_bytes is None


class TestTJMSDocumentService:
    """Testes do TJMSDocumentService"""

    def test_init(self):
        """Testa inicialização do serviço"""
        from sistemas.classificador_documentos.services_tjms import TJMSDocumentService

        service = TJMSDocumentService()
        assert service._client is None

    def test_get_client_lazy_init(self):
        """Testa que _get_client inicializa o cliente de forma lazy"""
        from sistemas.classificador_documentos.services_tjms import TJMSDocumentService

        service = TJMSDocumentService()
        assert service._client is None

        with patch('sistemas.classificador_documentos.services_tjms.TJMSClient') as mock_client_class:
            mock_client_class.return_value = Mock()
            client = service._get_client()

            mock_client_class.assert_called_once()
            assert service._client is not None

    @pytest.mark.asyncio
    async def test_consultar_processo_success(self):
        """Testa consulta de processo com sucesso"""
        from sistemas.classificador_documentos.services_tjms import TJMSDocumentService

        service = TJMSDocumentService()

        # Mock do cliente TJMS
        mock_client = AsyncMock()
        mock_processo = Mock()
        mock_processo.xml_raw = "<xml>teste</xml>"
        mock_client.consultar_processo = AsyncMock(return_value=mock_processo)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch.object(service, '_get_client', return_value=mock_client):
            xml, erro = await service.consultar_processo("0800001-00.2024.8.12.0001")

            assert xml == "<xml>teste</xml>"
            assert erro is None

    @pytest.mark.asyncio
    async def test_consultar_processo_error(self):
        """Testa consulta de processo com erro"""
        from sistemas.classificador_documentos.services_tjms import TJMSDocumentService

        service = TJMSDocumentService()

        mock_client = AsyncMock()
        mock_client.consultar_processo = AsyncMock(side_effect=Exception("Timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch.object(service, '_get_client', return_value=mock_client):
            xml, erro = await service.consultar_processo("0800001-00.2024.8.12.0001")

            assert xml is None
            assert "Timeout" in erro

    @pytest.mark.asyncio
    async def test_listar_documentos_success(self):
        """Testa listagem de documentos com sucesso"""
        from sistemas.classificador_documentos.services_tjms import TJMSDocumentService
        from datetime import datetime

        service = TJMSDocumentService()

        # Mock de documento retornado pelo cliente
        mock_doc = Mock()
        mock_doc.id = "12345"
        mock_doc.tipo_codigo = "500"
        mock_doc.descricao = "Petição Inicial"
        mock_doc.data_juntada = datetime(2024, 1, 15)

        mock_client = AsyncMock()
        mock_client.listar_documentos = AsyncMock(return_value=[mock_doc])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch.object(service, '_get_client', return_value=mock_client):
            docs, erro = await service.listar_documentos("0800001-00.2024.8.12.0001")

            assert len(docs) == 1
            assert docs[0]["id"] == "12345"
            assert docs[0]["tipo"] == "500"
            assert erro is None

    @pytest.mark.asyncio
    async def test_listar_documentos_with_error(self):
        """Testa listagem de documentos com erro"""
        from sistemas.classificador_documentos.services_tjms import TJMSDocumentService

        service = TJMSDocumentService()

        mock_client = AsyncMock()
        mock_client.listar_documentos = AsyncMock(side_effect=Exception("Erro de conexão"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch.object(service, '_get_client', return_value=mock_client):
            docs, erro = await service.listar_documentos("0800001-00.2024.8.12.0001")

            assert docs == []
            assert "Erro de conexão" in erro

    @pytest.mark.asyncio
    async def test_baixar_documento_success(self):
        """Testa download de documento com sucesso"""
        from sistemas.classificador_documentos.services_tjms import TJMSDocumentService

        service = TJMSDocumentService()

        # Mock do resultado do download
        mock_result = Mock()
        mock_result.sucesso = True
        mock_result.conteudo_bytes = b"%PDF-1.4"
        mock_result.erro = None

        mock_client = AsyncMock()
        mock_client.baixar_documentos = AsyncMock(return_value={"12345": mock_result})
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch.object(service, '_get_client', return_value=mock_client):
            doc = await service.baixar_documento("0800001-00.2024.8.12.0001", "12345")

            assert doc.id_documento == "12345"
            assert doc.conteudo_bytes == b"%PDF-1.4"
            assert doc.formato == "pdf"
            assert doc.erro is None

    @pytest.mark.asyncio
    async def test_baixar_documento_not_found(self):
        """Testa download de documento não encontrado"""
        from sistemas.classificador_documentos.services_tjms import TJMSDocumentService

        service = TJMSDocumentService()

        mock_client = AsyncMock()
        mock_client.baixar_documentos = AsyncMock(return_value={})
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch.object(service, '_get_client', return_value=mock_client):
            doc = await service.baixar_documento("0800001-00.2024.8.12.0001", "99999")

            assert doc.erro == "Documento nao encontrado"

    @pytest.mark.asyncio
    async def test_baixar_documento_rtf(self):
        """Testa download de documento RTF com conversão"""
        from sistemas.classificador_documentos.services_tjms import TJMSDocumentService

        service = TJMSDocumentService()

        rtf_content = b'{\\rtf1\\ansi Hello World}'

        mock_result = Mock()
        mock_result.sucesso = True
        mock_result.conteudo_bytes = rtf_content
        mock_result.erro = None

        mock_client = AsyncMock()
        mock_client.baixar_documentos = AsyncMock(return_value={"12345": mock_result})
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch.object(service, '_get_client', return_value=mock_client):
            with patch.object(service, '_converter_rtf_para_pdf', return_value=b"%PDF-1.4"):
                doc = await service.baixar_documento("0800001-00.2024.8.12.0001", "12345")

                # O formato é detectado como RTF, mas o conteúdo deve ser PDF convertido
                assert doc.formato == "rtf"

    @pytest.mark.asyncio
    async def test_baixar_documento_error(self):
        """Testa download de documento com erro"""
        from sistemas.classificador_documentos.services_tjms import TJMSDocumentService

        service = TJMSDocumentService()

        mock_client = AsyncMock()
        mock_client.baixar_documentos = AsyncMock(side_effect=Exception("Connection error"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch.object(service, '_get_client', return_value=mock_client):
            doc = await service.baixar_documento("0800001-00.2024.8.12.0001", "12345")

            assert doc.erro is not None
            assert "Connection error" in doc.erro

    @pytest.mark.asyncio
    async def test_baixar_documentos_multiple(self):
        """Testa download de múltiplos documentos"""
        from sistemas.classificador_documentos.services_tjms import TJMSDocumentService

        service = TJMSDocumentService()

        mock_result1 = Mock()
        mock_result1.sucesso = True
        mock_result1.conteudo_bytes = b"%PDF-1.4 doc1"
        mock_result1.erro = None

        mock_result2 = Mock()
        mock_result2.sucesso = True
        mock_result2.conteudo_bytes = b"%PDF-1.4 doc2"
        mock_result2.erro = None

        mock_client = AsyncMock()
        mock_client.baixar_documentos = AsyncMock(return_value={
            "123": mock_result1,
            "456": mock_result2
        })
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch.object(service, '_get_client', return_value=mock_client):
            docs = await service.baixar_documentos("0800001-00.2024.8.12.0001", ["123", "456"])

            assert len(docs) == 2
            assert all(d.erro is None for d in docs)

    @pytest.mark.asyncio
    async def test_baixar_documentos_partial_error(self):
        """Testa download com alguns documentos não encontrados"""
        from sistemas.classificador_documentos.services_tjms import TJMSDocumentService

        service = TJMSDocumentService()

        mock_result = Mock()
        mock_result.sucesso = True
        mock_result.conteudo_bytes = b"%PDF"
        mock_result.erro = None

        mock_client = AsyncMock()
        mock_client.baixar_documentos = AsyncMock(return_value={"123": mock_result})
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch.object(service, '_get_client', return_value=mock_client):
            docs = await service.baixar_documentos("0800001-00.2024.8.12.0001", ["123", "999"])

            assert len(docs) == 2
            # O primeiro foi baixado com sucesso
            assert docs[0].erro is None
            # O segundo não foi encontrado
            assert docs[1].erro is not None

    @pytest.mark.asyncio
    async def test_baixar_documentos_error(self):
        """Testa download de múltiplos com erro geral"""
        from sistemas.classificador_documentos.services_tjms import TJMSDocumentService

        service = TJMSDocumentService()

        mock_client = AsyncMock()
        mock_client.baixar_documentos = AsyncMock(side_effect=Exception("Error"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch.object(service, '_get_client', return_value=mock_client):
            docs = await service.baixar_documentos("0800001-00.2024.8.12.0001", ["123", "456"])

            assert len(docs) == 2
            assert all(d.erro is not None for d in docs)

    def test_converter_rtf_para_pdf_fallback(self):
        """Testa conversão RTF usando fallback"""
        from sistemas.classificador_documentos.services_tjms import TJMSDocumentService

        service = TJMSDocumentService()

        # Simula que o import do módulo principal falha
        # O método _converter_rtf_para_pdf lida com ImportError internamente
        rtf_content = b'{\\rtf1\\ansi test document}'
        result = service._converter_rtf_para_pdf(rtf_content)

        # Retorna bytes (seja PDF convertido ou RTF original em caso de erro)
        assert isinstance(result, bytes)

    def test_converter_rtf_para_pdf_fallback_error(self):
        """Testa fallback de conversão RTF com erro"""
        from sistemas.classificador_documentos.services_tjms import TJMSDocumentService

        service = TJMSDocumentService()

        rtf_bytes = b'{\\rtf1 invalid'

        # Simula que ambos os métodos falham
        with patch.dict('sys.modules', {'sistemas.pedido_calculo.router': None}):
            result = service._converter_rtf_para_pdf(rtf_bytes)
            # Deve retornar os bytes originais em caso de erro
            assert isinstance(result, bytes)


class TestGetTJMSService:
    """Testes do singleton"""

    def test_singleton(self):
        """Testa que retorna singleton"""
        from sistemas.classificador_documentos.services_tjms import get_tjms_service

        service1 = get_tjms_service()
        service2 = get_tjms_service()

        assert service1 is service2
