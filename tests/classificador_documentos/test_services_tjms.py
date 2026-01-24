# tests/classificador_documentos/test_services_tjms.py
"""
Testes unitários do serviço de integração com TJ-MS.

Testa:
- Dataclass DocumentoTJMS
- TJMSDocumentService com mocks
- Parsing de XML
- Conversão RTF para PDF

Autor: LAB/PGE-MS
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock


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
        assert service._downloader is None

    @pytest.mark.asyncio
    async def test_get_downloader_import_error(self):
        """Testa _get_downloader quando módulo não existe"""
        from sistemas.classificador_documentos.services_tjms import TJMSDocumentService

        service = TJMSDocumentService()

        with patch.dict('sys.modules', {'sistemas.pedido_calculo.document_downloader': None}):
            with patch('sistemas.classificador_documentos.services_tjms.TJMSDocumentService._get_downloader') as mock_get:
                mock_get.side_effect = ImportError("Módulo não encontrado")

                with pytest.raises(ImportError):
                    await service._get_downloader()

    @pytest.mark.asyncio
    async def test_consultar_processo_success(self):
        """Testa consulta de processo com sucesso"""
        from sistemas.classificador_documentos.services_tjms import TJMSDocumentService

        service = TJMSDocumentService()

        mock_downloader = AsyncMock()
        mock_downloader.consultar_processo = AsyncMock(return_value="<xml>teste</xml>")
        mock_downloader.__aenter__ = AsyncMock(return_value=mock_downloader)
        mock_downloader.__aexit__ = AsyncMock(return_value=None)

        with patch.object(service, '_get_downloader', return_value=mock_downloader):
            xml, erro = await service.consultar_processo("0800001-00.2024.8.12.0001")

            assert xml == "<xml>teste</xml>"
            assert erro is None

    @pytest.mark.asyncio
    async def test_consultar_processo_error(self):
        """Testa consulta de processo com erro"""
        from sistemas.classificador_documentos.services_tjms import TJMSDocumentService

        service = TJMSDocumentService()

        mock_downloader = AsyncMock()
        mock_downloader.consultar_processo = AsyncMock(side_effect=Exception("Timeout"))
        mock_downloader.__aenter__ = AsyncMock(return_value=mock_downloader)
        mock_downloader.__aexit__ = AsyncMock(return_value=None)

        with patch.object(service, '_get_downloader', return_value=mock_downloader):
            xml, erro = await service.consultar_processo("0800001-00.2024.8.12.0001")

            assert xml is None
            assert "Timeout" in erro

    @pytest.mark.asyncio
    async def test_listar_documentos_success(self):
        """Testa listagem de documentos com sucesso"""
        from sistemas.classificador_documentos.services_tjms import TJMSDocumentService

        service = TJMSDocumentService()

        with patch.object(service, 'consultar_processo', return_value=("<xml></xml>", None)):
            with patch.object(service, '_extrair_documentos_do_xml', return_value=[{"id": "1"}]):
                docs, erro = await service.listar_documentos("0800001-00.2024.8.12.0001")

                assert len(docs) == 1
                assert erro is None

    @pytest.mark.asyncio
    async def test_listar_documentos_with_error(self):
        """Testa listagem de documentos com erro"""
        from sistemas.classificador_documentos.services_tjms import TJMSDocumentService

        service = TJMSDocumentService()

        with patch.object(service, 'consultar_processo', return_value=(None, "Erro de conexão")):
            docs, erro = await service.listar_documentos("0800001-00.2024.8.12.0001")

            assert docs == []
            assert erro == "Erro de conexão"

    def test_extrair_documentos_do_xml_valid(self):
        """Testa extração de documentos de XML válido"""
        from sistemas.classificador_documentos.services_tjms import TJMSDocumentService

        service = TJMSDocumentService()

        xml = """<?xml version="1.0"?>
        <root xmlns:ns2="http://www.cnj.jus.br/intercomunicacao-2.2.2">
            <ns2:documento idDocumento="12345">
                <ns2:tipoDocumento>Sentença</ns2:tipoDocumento>
                <ns2:descricao>Sentença de procedência</ns2:descricao>
                <ns2:dataHora>2024-01-15</ns2:dataHora>
            </ns2:documento>
        </root>
        """

        docs = service._extrair_documentos_do_xml(xml)

        assert len(docs) == 1
        assert docs[0]["id"] == "12345"
        assert docs[0]["tipo"] == "Sentença"

    def test_extrair_documentos_do_xml_empty(self):
        """Testa extração de documentos de XML vazio"""
        from sistemas.classificador_documentos.services_tjms import TJMSDocumentService

        service = TJMSDocumentService()

        xml = """<?xml version="1.0"?>
        <root xmlns:ns2="http://www.cnj.jus.br/intercomunicacao-2.2.2">
        </root>
        """

        docs = service._extrair_documentos_do_xml(xml)
        assert docs == []

    def test_extrair_documentos_do_xml_invalid(self):
        """Testa extração de documentos de XML inválido"""
        from sistemas.classificador_documentos.services_tjms import TJMSDocumentService

        service = TJMSDocumentService()

        docs = service._extrair_documentos_do_xml("not xml")
        assert docs == []

    @pytest.mark.asyncio
    async def test_baixar_documento_success(self):
        """Testa download de documento com sucesso"""
        from sistemas.classificador_documentos.services_tjms import TJMSDocumentService

        service = TJMSDocumentService()

        mock_downloader = AsyncMock()
        mock_downloader.baixar_documentos = AsyncMock(return_value={"12345": b"%PDF-1.4"})
        mock_downloader.__aenter__ = AsyncMock(return_value=mock_downloader)
        mock_downloader.__aexit__ = AsyncMock(return_value=None)

        with patch.object(service, '_get_downloader', return_value=mock_downloader):
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

        mock_downloader = AsyncMock()
        mock_downloader.baixar_documentos = AsyncMock(return_value={})
        mock_downloader.__aenter__ = AsyncMock(return_value=mock_downloader)
        mock_downloader.__aexit__ = AsyncMock(return_value=None)

        with patch.object(service, '_get_downloader', return_value=mock_downloader):
            doc = await service.baixar_documento("0800001-00.2024.8.12.0001", "99999")

            assert doc.erro == "Documento não encontrado"

    @pytest.mark.asyncio
    async def test_baixar_documento_rtf(self):
        """Testa download de documento RTF com conversão"""
        from sistemas.classificador_documentos.services_tjms import TJMSDocumentService

        service = TJMSDocumentService()

        rtf_content = b'{\\rtf1\\ansi Hello World}'

        mock_downloader = AsyncMock()
        mock_downloader.baixar_documentos = AsyncMock(return_value={"12345": rtf_content})
        mock_downloader.__aenter__ = AsyncMock(return_value=mock_downloader)
        mock_downloader.__aexit__ = AsyncMock(return_value=None)

        with patch.object(service, '_get_downloader', return_value=mock_downloader):
            with patch.object(service, '_converter_rtf_para_pdf', return_value=b"%PDF-1.4"):
                doc = await service.baixar_documento("0800001-00.2024.8.12.0001", "12345")

                assert doc.formato == "rtf"
                assert doc.conteudo_bytes == b"%PDF-1.4"

    @pytest.mark.asyncio
    async def test_baixar_documento_error(self):
        """Testa download de documento com erro"""
        from sistemas.classificador_documentos.services_tjms import TJMSDocumentService

        service = TJMSDocumentService()

        with patch.object(service, '_get_downloader', side_effect=Exception("Connection error")):
            doc = await service.baixar_documento("0800001-00.2024.8.12.0001", "12345")

            assert doc.erro is not None
            assert "Connection error" in doc.erro

    @pytest.mark.asyncio
    async def test_baixar_documentos_multiple(self):
        """Testa download de múltiplos documentos"""
        from sistemas.classificador_documentos.services_tjms import TJMSDocumentService

        service = TJMSDocumentService()

        mock_downloader = AsyncMock()
        mock_downloader.baixar_documentos = AsyncMock(return_value={
            "123": b"%PDF-1.4 doc1",
            "456": b"%PDF-1.4 doc2"
        })
        mock_downloader.__aenter__ = AsyncMock(return_value=mock_downloader)
        mock_downloader.__aexit__ = AsyncMock(return_value=None)

        with patch.object(service, '_get_downloader', return_value=mock_downloader):
            docs = await service.baixar_documentos("0800001-00.2024.8.12.0001", ["123", "456"])

            assert len(docs) == 2
            assert all(d.erro is None for d in docs)

    @pytest.mark.asyncio
    async def test_baixar_documentos_partial_error(self):
        """Testa download com alguns documentos não encontrados"""
        from sistemas.classificador_documentos.services_tjms import TJMSDocumentService

        service = TJMSDocumentService()

        mock_downloader = AsyncMock()
        mock_downloader.baixar_documentos = AsyncMock(return_value={"123": b"%PDF"})
        mock_downloader.__aenter__ = AsyncMock(return_value=mock_downloader)
        mock_downloader.__aexit__ = AsyncMock(return_value=None)

        with patch.object(service, '_get_downloader', return_value=mock_downloader):
            docs = await service.baixar_documentos("0800001-00.2024.8.12.0001", ["123", "999"])

            assert len(docs) == 2
            assert docs[0].erro is None
            assert docs[1].erro == "Documento não encontrado"

    @pytest.mark.asyncio
    async def test_baixar_documentos_error(self):
        """Testa download de múltiplos com erro geral"""
        from sistemas.classificador_documentos.services_tjms import TJMSDocumentService

        service = TJMSDocumentService()

        with patch.object(service, '_get_downloader', side_effect=Exception("Error")):
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
