# tests/classificador_documentos/test_services_execution.py
"""
Testes do orquestrador de execução de projetos.

Testa:
- Execução de projeto completo
- Processamento de códigos
- Streaming de eventos
- Tratamento de erros

Autor: LAB/PGE-MS
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime, timezone
import asyncio


@pytest.fixture
def mock_db():
    """Mock da sessão do banco de dados"""
    db = Mock()
    db.query = Mock()
    db.add = Mock()
    db.commit = Mock()
    db.refresh = Mock()
    db.delete = Mock()
    return db


class TestExecutarProjeto:
    """Testes de executar_projeto"""

    @pytest.mark.asyncio
    async def test_executar_projeto_nao_encontrado(self, mock_db):
        """Testa execução quando projeto não existe"""
        from sistemas.classificador_documentos.services import ClassificadorService

        mock_db.query.return_value.filter.return_value.first.return_value = None

        service = ClassificadorService(mock_db)

        eventos = []
        async for evento in service.executar_projeto(
            projeto_id=999,
            usuario_id=1
        ):
            eventos.append(evento)

        assert len(eventos) == 1
        assert eventos[0]["tipo"] == "erro"
        assert "não encontrado" in eventos[0]["mensagem"]

    @pytest.mark.asyncio
    async def test_executar_projeto_sem_prompt(self, mock_db):
        """Testa execução quando projeto não tem prompt"""
        from sistemas.classificador_documentos.services import ClassificadorService
        from sistemas.classificador_documentos.models import ProjetoClassificacao

        mock_projeto = Mock(spec=ProjetoClassificacao)
        mock_projeto.id = 1
        mock_projeto.prompt_id = None

        mock_db.query.return_value.filter.return_value.first.return_value = mock_projeto

        service = ClassificadorService(mock_db)

        eventos = []
        async for evento in service.executar_projeto(
            projeto_id=1,
            usuario_id=1
        ):
            eventos.append(evento)

        assert len(eventos) == 1
        assert eventos[0]["tipo"] == "erro"
        assert "prompt" in eventos[0]["mensagem"].lower()

    @pytest.mark.asyncio
    async def test_executar_projeto_sem_codigos(self, mock_db):
        """Testa execução quando projeto não tem códigos"""
        from sistemas.classificador_documentos.services import ClassificadorService
        from sistemas.classificador_documentos.models import ProjetoClassificacao, PromptClassificacao

        mock_projeto = Mock(spec=ProjetoClassificacao)
        mock_projeto.id = 1
        mock_projeto.prompt_id = 1

        mock_prompt = Mock(spec=PromptClassificacao)
        mock_prompt.conteudo = "Classifique este documento"

        # Configura retornos
        def query_side_effect(model):
            result = Mock()
            result.filter = Mock(return_value=result)
            if model == ProjetoClassificacao:
                result.first.return_value = mock_projeto
            elif model == PromptClassificacao:
                result.first.return_value = mock_prompt
            else:
                result.all.return_value = []
                result.first.return_value = None
            return result

        mock_db.query.side_effect = query_side_effect

        service = ClassificadorService(mock_db)

        eventos = []
        async for evento in service.executar_projeto(
            projeto_id=1,
            usuario_id=1
        ):
            eventos.append(evento)

        assert len(eventos) == 1
        assert eventos[0]["tipo"] == "erro"
        assert "código" in eventos[0]["mensagem"].lower()


class TestProcessarCodigo:
    """Testes de _processar_codigo"""

    @pytest.mark.asyncio
    async def test_processar_codigo_sem_processo(self, mock_db):
        """Testa processamento de código sem processo associado"""
        from sistemas.classificador_documentos.services import ClassificadorService
        from sistemas.classificador_documentos.models import (
            ProjetoClassificacao, CodigoDocumentoProjeto, ExecucaoClassificacao,
            FonteDocumento
        )

        service = ClassificadorService(mock_db)

        mock_execucao = Mock(spec=ExecucaoClassificacao)
        mock_execucao.id = 1

        mock_codigo = Mock(spec=CodigoDocumentoProjeto)
        mock_codigo.codigo = "COD001"
        mock_codigo.numero_processo = None
        mock_codigo.fonte = FonteDocumento.TJMS.value

        mock_projeto = Mock(spec=ProjetoClassificacao)

        resultado = await service._processar_codigo(
            mock_execucao,
            mock_codigo,
            mock_projeto,
            "Prompt texto"
        )

        assert resultado.sucesso is False
        assert resultado.erro is not None

    @pytest.mark.asyncio
    async def test_processar_codigo_download_erro(self, mock_db):
        """Testa processamento quando download falha"""
        from sistemas.classificador_documentos.services import ClassificadorService
        from sistemas.classificador_documentos.services_tjms import DocumentoTJMS, TJMSDocumentService
        from sistemas.classificador_documentos.models import (
            ProjetoClassificacao, CodigoDocumentoProjeto, ExecucaoClassificacao,
            FonteDocumento
        )

        service = ClassificadorService(mock_db)

        mock_execucao = Mock(spec=ExecucaoClassificacao)
        mock_execucao.id = 1

        mock_codigo = Mock(spec=CodigoDocumentoProjeto)
        mock_codigo.codigo = "COD001"
        mock_codigo.numero_processo = "0800001-00.2024.8.12.0001"
        mock_codigo.fonte = FonteDocumento.TJMS.value

        mock_projeto = Mock(spec=ProjetoClassificacao)

        # Mock do TJ-MS retornando erro
        mock_doc = DocumentoTJMS(
            id_documento="COD001",
            numero_processo="0800001-00.2024.8.12.0001",
            erro="Documento não encontrado no TJ-MS"
        )

        with patch.object(service.tjms, 'baixar_documento', new_callable=AsyncMock) as mock_baixar:
            mock_baixar.return_value = mock_doc

            resultado = await service._processar_codigo(
                mock_execucao,
                mock_codigo,
                mock_projeto,
                "Prompt texto"
            )

            assert resultado.sucesso is False
            assert resultado.erro is not None

    @pytest.mark.asyncio
    async def test_processar_codigo_texto_vazio(self, mock_db):
        """Testa processamento quando texto extraído é vazio"""
        from sistemas.classificador_documentos.services import ClassificadorService
        from sistemas.classificador_documentos.services_tjms import DocumentoTJMS, TJMSDocumentService
        from sistemas.classificador_documentos.services_extraction import ExtractionResult, TextExtractor
        from sistemas.classificador_documentos.models import (
            ProjetoClassificacao, CodigoDocumentoProjeto, ExecucaoClassificacao,
            FonteDocumento
        )

        service = ClassificadorService(mock_db)

        mock_execucao = Mock(spec=ExecucaoClassificacao)
        mock_execucao.id = 1

        mock_codigo = Mock(spec=CodigoDocumentoProjeto)
        mock_codigo.codigo = "COD001"
        mock_codigo.numero_processo = "0800001-00.2024.8.12.0001"
        mock_codigo.fonte = FonteDocumento.TJMS.value

        mock_projeto = Mock(spec=ProjetoClassificacao)

        # Mock do TJ-MS retornando documento válido
        mock_doc = DocumentoTJMS(
            id_documento="COD001",
            numero_processo="0800001-00.2024.8.12.0001",
            conteudo_bytes=b"%PDF-1.4"
        )

        # Mock de extração retornando texto vazio
        mock_extraction = ExtractionResult(
            texto="",
            via_ocr=False,
            tokens_total=0,
            paginas_processadas=0
        )

        with patch.object(service.tjms, 'baixar_documento', new_callable=AsyncMock) as mock_baixar:
            mock_baixar.return_value = mock_doc

            with patch.object(service.extractor, 'extrair_texto', return_value=mock_extraction):
                resultado = await service._processar_codigo(
                    mock_execucao,
                    mock_codigo,
                    mock_projeto,
                    "Prompt texto"
                )

                assert resultado.sucesso is False
                assert "vazio" in resultado.erro.lower()

    @pytest.mark.asyncio
    async def test_processar_codigo_sucesso(self, mock_db):
        """Testa processamento com sucesso"""
        from sistemas.classificador_documentos.services import ClassificadorService
        from sistemas.classificador_documentos.services_tjms import DocumentoTJMS
        from sistemas.classificador_documentos.services_extraction import ExtractionResult
        from sistemas.classificador_documentos.services_openrouter import OpenRouterResult
        from sistemas.classificador_documentos.models import (
            ProjetoClassificacao, CodigoDocumentoProjeto, ExecucaoClassificacao,
            FonteDocumento
        )

        service = ClassificadorService(mock_db)

        mock_execucao = Mock(spec=ExecucaoClassificacao)
        mock_execucao.id = 1

        mock_codigo = Mock(spec=CodigoDocumentoProjeto)
        mock_codigo.codigo = "COD001"
        mock_codigo.numero_processo = "0800001-00.2024.8.12.0001"
        mock_codigo.fonte = FonteDocumento.TJMS.value

        mock_projeto = Mock(spec=ProjetoClassificacao)
        mock_projeto.modo_processamento = "chunk"
        mock_projeto.tamanho_chunk = 512
        mock_projeto.posicao_chunk = "fim"
        mock_projeto.modelo = "google/gemini-2.5-flash-lite"

        # Mock do TJ-MS
        mock_doc = DocumentoTJMS(
            id_documento="COD001",
            numero_processo="0800001-00.2024.8.12.0001",
            conteudo_bytes=b"%PDF-1.4"
        )

        # Mock de extração
        mock_extraction = ExtractionResult(
            texto="Texto extraído do documento. " * 50,
            via_ocr=False,
            tokens_total=500,
            paginas_processadas=5
        )

        # Mock de classificação
        mock_openrouter = OpenRouterResult(
            sucesso=True,
            resultado={
                "categoria": "decisao",
                "subcategoria": "deferida",
                "confianca": "alta",
                "justificativa_breve": "Decisão deferitória"
            },
            tokens_entrada=100,
            tokens_saida=50,
            tempo_ms=500
        )

        with patch.object(service.tjms, 'baixar_documento', new_callable=AsyncMock) as mock_baixar:
            mock_baixar.return_value = mock_doc

            with patch.object(service.extractor, 'extrair_texto', return_value=mock_extraction):
                with patch.object(service.extractor, 'extrair_chunk', return_value="Chunk de texto"):
                    with patch.object(service.openrouter, 'classificar', new_callable=AsyncMock) as mock_class:
                        mock_class.return_value = mock_openrouter

                        resultado = await service._processar_codigo(
                            mock_execucao,
                            mock_codigo,
                            mock_projeto,
                            "Prompt texto"
                        )

                        assert resultado.sucesso is True
                        assert resultado.categoria == "decisao"
                        assert resultado.confianca == "alta"


class TestProcessarCodigoComSemaforo:
    """Testes de _processar_codigo_com_semaforo"""

    @pytest.mark.asyncio
    async def test_processar_com_semaforo(self, mock_db):
        """Testa processamento com semáforo"""
        from sistemas.classificador_documentos.services import ClassificadorService
        from sistemas.classificador_documentos.models import (
            ProjetoClassificacao, CodigoDocumentoProjeto, ExecucaoClassificacao,
            FonteDocumento, ResultadoClassificacaoDTO
        )

        service = ClassificadorService(mock_db)

        semaforo = asyncio.Semaphore(1)

        mock_execucao = Mock(spec=ExecucaoClassificacao)
        mock_execucao.id = 1

        mock_codigo = Mock(spec=CodigoDocumentoProjeto)
        mock_codigo.codigo = "COD001"
        mock_codigo.numero_processo = None
        mock_codigo.fonte = FonteDocumento.TJMS.value

        mock_projeto = Mock(spec=ProjetoClassificacao)

        # _processar_codigo será chamado e retornará erro por não ter processo
        resultado = await service._processar_codigo_com_semaforo(
            semaforo,
            mock_execucao,
            mock_codigo,
            mock_projeto,
            "Prompt texto"
        )

        assert resultado is not None
        assert resultado.sucesso is False


class TestClassificarDocumentoAvulsoExtended:
    """Testes estendidos de classificação avulsa"""

    @pytest.mark.asyncio
    async def test_classificar_avulso_erro_classificacao(self, mock_db):
        """Testa classificação avulsa com erro na classificação"""
        from sistemas.classificador_documentos.services import ClassificadorService
        from sistemas.classificador_documentos.services_extraction import ExtractionResult, TextExtractor
        from sistemas.classificador_documentos.services_openrouter import OpenRouterResult, OpenRouterService

        mock_extraction = ExtractionResult(
            texto="Texto extraído do documento. " * 10,
            via_ocr=False,
            tokens_total=100,
            paginas_processadas=2
        )

        mock_openrouter = OpenRouterResult(
            sucesso=False,
            erro="Erro de parsing: JSON inválido",
            tempo_ms=500
        )

        with patch.object(TextExtractor, 'extrair_texto', return_value=mock_extraction):
            with patch.object(TextExtractor, 'extrair_chunk', return_value="Chunk"):
                with patch.object(OpenRouterService, 'classificar', new_callable=AsyncMock) as mock_class:
                    mock_class.return_value = mock_openrouter

                    service = ClassificadorService(mock_db)
                    resultado = await service.classificar_documento_avulso(
                        pdf_bytes=b"fake pdf",
                        nome_arquivo="doc.pdf",
                        prompt_texto="Classifique"
                    )

                    assert resultado.sucesso is False
                    assert resultado.erro is not None

    @pytest.mark.asyncio
    async def test_classificar_avulso_modo_completo(self, mock_db):
        """Testa classificação avulsa com modo completo"""
        from sistemas.classificador_documentos.services import ClassificadorService
        from sistemas.classificador_documentos.services_extraction import ExtractionResult, TextExtractor
        from sistemas.classificador_documentos.services_openrouter import OpenRouterResult, OpenRouterService

        mock_extraction = ExtractionResult(
            texto="Texto do documento completo. " * 100,
            via_ocr=True,
            tokens_total=800,
            paginas_processadas=10
        )

        mock_openrouter = OpenRouterResult(
            sucesso=True,
            resultado={
                "categoria": "petição",
                "subcategoria": "inicial",
                "confianca": "media",
                "justificativa_breve": "Petição inicial"
            },
            tokens_entrada=200,
            tokens_saida=80,
            tempo_ms=1000
        )

        with patch.object(TextExtractor, 'extrair_texto', return_value=mock_extraction):
            with patch.object(OpenRouterService, 'classificar', new_callable=AsyncMock) as mock_class:
                mock_class.return_value = mock_openrouter

                service = ClassificadorService(mock_db)
                resultado = await service.classificar_documento_avulso(
                    pdf_bytes=b"fake pdf",
                    nome_arquivo="doc.pdf",
                    prompt_texto="Classifique",
                    modo_processamento="completo"
                )

                assert resultado.sucesso is True
                assert resultado.categoria == "petição"
                assert resultado.texto_via == "ocr"
