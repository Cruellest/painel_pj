# tests/classificador_documentos/test_services_extended.py
"""
Testes estendidos do ClassificadorService.

Testa cenários adicionais para aumentar cobertura:
- Atualização de prompts
- Atualização de projetos
- Listagem de códigos
- Obtenção de execuções
- Classificação com diferentes modos

Autor: LAB/PGE-MS
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime, timezone


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


class TestClassificadorServicePromptsExtended:
    """Testes estendidos de prompts"""

    def test_atualizar_prompt_existente(self, mock_db):
        """Testa atualização de prompt existente"""
        from sistemas.classificador_documentos.services import ClassificadorService
        from sistemas.classificador_documentos.models import PromptClassificacao

        mock_prompt = Mock(spec=PromptClassificacao)
        mock_prompt.id = 1
        mock_prompt.nome = "Original"

        mock_db.query.return_value.filter.return_value.first.return_value = mock_prompt

        service = ClassificadorService(mock_db)
        result = service.atualizar_prompt(1, nome="Atualizado")

        assert result is not None
        mock_db.commit.assert_called()

    def test_atualizar_prompt_inexistente(self, mock_db):
        """Testa atualização de prompt inexistente"""
        from sistemas.classificador_documentos.services import ClassificadorService

        mock_db.query.return_value.filter.return_value.first.return_value = None

        service = ClassificadorService(mock_db)
        result = service.atualizar_prompt(999, nome="Teste")

        assert result is None

    def test_deletar_prompt(self, mock_db):
        """Testa deleção (desativação) de prompt"""
        from sistemas.classificador_documentos.services import ClassificadorService
        from sistemas.classificador_documentos.models import PromptClassificacao

        mock_prompt = Mock(spec=PromptClassificacao)
        mock_prompt.id = 1
        mock_prompt.ativo = True

        mock_db.query.return_value.filter.return_value.first.return_value = mock_prompt

        service = ClassificadorService(mock_db)
        result = service.atualizar_prompt(1, ativo=False)

        assert result is not None
        mock_db.commit.assert_called()


class TestClassificadorServiceProjetosExtended:
    """Testes estendidos de projetos"""

    def test_atualizar_projeto_inexistente(self, mock_db):
        """Testa atualização de projeto inexistente"""
        from sistemas.classificador_documentos.services import ClassificadorService

        mock_db.query.return_value.filter.return_value.first.return_value = None

        service = ClassificadorService(mock_db)
        result = service.atualizar_projeto(999, nome="Teste")

        assert result is None

    def test_deletar_projeto(self, mock_db):
        """Testa deleção (desativação) de projeto"""
        from sistemas.classificador_documentos.services import ClassificadorService
        from sistemas.classificador_documentos.models import ProjetoClassificacao

        mock_projeto = Mock(spec=ProjetoClassificacao)
        mock_projeto.id = 1
        mock_projeto.ativo = True

        mock_db.query.return_value.filter.return_value.first.return_value = mock_projeto

        service = ClassificadorService(mock_db)
        result = service.atualizar_projeto(1, ativo=False)

        assert result is not None


class TestClassificadorServiceCodigosExtended:
    """Testes estendidos de códigos"""

    def test_listar_codigos(self, mock_db):
        """Testa listagem de códigos de um projeto"""
        from sistemas.classificador_documentos.services import ClassificadorService
        from sistemas.classificador_documentos.models import CodigoDocumentoProjeto

        mock_codigo = Mock(spec=CodigoDocumentoProjeto)
        mock_codigo.id = 1
        mock_codigo.codigo = "COD001"

        mock_db.query.return_value.filter.return_value.filter.return_value.all.return_value = [mock_codigo]

        service = ClassificadorService(mock_db)
        codigos = service.listar_codigos(projeto_id=1)

        assert len(codigos) == 1


class TestClassificadorServiceExecucoesExtended:
    """Testes estendidos de execuções"""

    def test_obter_execucao_existente(self, mock_db):
        """Testa obtenção de execução existente"""
        from sistemas.classificador_documentos.services import ClassificadorService
        from sistemas.classificador_documentos.models import ExecucaoClassificacao

        mock_execucao = Mock(spec=ExecucaoClassificacao)
        mock_execucao.id = 1
        mock_execucao.status = "concluido"

        mock_db.query.return_value.filter.return_value.first.return_value = mock_execucao

        service = ClassificadorService(mock_db)
        execucao = service.obter_execucao(1)

        assert execucao is not None
        assert execucao.status == "concluido"

    def test_obter_execucao_inexistente(self, mock_db):
        """Testa obtenção de execução inexistente"""
        from sistemas.classificador_documentos.services import ClassificadorService

        mock_db.query.return_value.filter.return_value.first.return_value = None

        service = ClassificadorService(mock_db)
        execucao = service.obter_execucao(999)

        assert execucao is None


class TestClassificadorServiceResultadosExtended:
    """Testes estendidos de resultados"""

    def test_listar_resultados_apenas_erros(self, mock_db):
        """Testa listagem de resultados apenas com erros"""
        from sistemas.classificador_documentos.services import ClassificadorService
        from sistemas.classificador_documentos.models import ResultadoClassificacao

        # Mock configurado corretamente para a cadeia de filtros
        mock_query = Mock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = []

        service = ClassificadorService(mock_db)
        resultados = service.listar_resultados(
            execucao_id=1,
            apenas_erros=True
        )

        assert resultados == []


class TestClassificadorServiceClassificacaoExtended:
    """Testes estendidos de classificação"""

    @pytest.mark.asyncio
    async def test_classificar_documento_avulso_modo_completo(self, mock_db):
        """Testa classificação avulsa com modo completo"""
        from sistemas.classificador_documentos.services import ClassificadorService
        from sistemas.classificador_documentos.services_extraction import ExtractionResult, TextExtractor
        from sistemas.classificador_documentos.services_openrouter import OpenRouterResult, OpenRouterService

        mock_extraction = ExtractionResult(
            texto="Texto extraído do documento. " * 50,
            via_ocr=False,
            tokens_total=500,
            paginas_processadas=5
        )

        mock_openrouter_result = OpenRouterResult(
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

        with patch.object(TextExtractor, 'extrair_texto', return_value=mock_extraction):
            with patch.object(TextExtractor, 'extrair_chunk', return_value="Texto completo"):
                with patch.object(OpenRouterService, 'classificar', new_callable=AsyncMock) as mock_classificar:
                    mock_classificar.return_value = mock_openrouter_result

                    service = ClassificadorService(mock_db)
                    resultado = await service.classificar_documento_avulso(
                        pdf_bytes=b"fake pdf bytes",
                        nome_arquivo="documento.pdf",
                        prompt_texto="Classifique este documento",
                        modo_processamento="completo"
                    )

                    assert resultado.sucesso is True

    @pytest.mark.asyncio
    async def test_classificar_documento_avulso_modo_chunk_inicio(self, mock_db):
        """Testa classificação avulsa com chunk do início"""
        from sistemas.classificador_documentos.services import ClassificadorService
        from sistemas.classificador_documentos.services_extraction import ExtractionResult, TextExtractor
        from sistemas.classificador_documentos.services_openrouter import OpenRouterResult, OpenRouterService

        mock_extraction = ExtractionResult(
            texto="Texto extraído do documento. " * 50,
            via_ocr=True,
            tokens_total=500,
            paginas_processadas=5
        )

        mock_openrouter_result = OpenRouterResult(
            sucesso=True,
            resultado={
                "categoria": "petição",
                "subcategoria": "inicial",
                "confianca": "media",
                "justificativa_breve": "Petição inicial"
            },
            tokens_entrada=100,
            tokens_saida=50,
            tempo_ms=500
        )

        with patch.object(TextExtractor, 'extrair_texto', return_value=mock_extraction):
            with patch.object(TextExtractor, 'extrair_chunk', return_value="Chunk inicial"):
                with patch.object(OpenRouterService, 'classificar', new_callable=AsyncMock) as mock_classificar:
                    mock_classificar.return_value = mock_openrouter_result

                    service = ClassificadorService(mock_db)
                    resultado = await service.classificar_documento_avulso(
                        pdf_bytes=b"fake pdf bytes",
                        nome_arquivo="documento.pdf",
                        prompt_texto="Classifique este documento",
                        modo_processamento="chunk",
                        posicao_chunk="inicio",
                        tamanho_chunk=256
                    )

                    assert resultado.sucesso is True
                    assert resultado.texto_via == "ocr"

    @pytest.mark.asyncio
    async def test_classificar_documento_avulso_erro_openrouter(self, mock_db):
        """Testa classificação avulsa com erro do OpenRouter"""
        from sistemas.classificador_documentos.services import ClassificadorService
        from sistemas.classificador_documentos.services_extraction import ExtractionResult, TextExtractor
        from sistemas.classificador_documentos.services_openrouter import OpenRouterResult, OpenRouterService

        mock_extraction = ExtractionResult(
            texto="Texto extraído do documento. " * 10,
            via_ocr=False,
            tokens_total=100,
            paginas_processadas=2
        )

        mock_openrouter_result = OpenRouterResult(
            sucesso=False,
            erro="Timeout após 60s",
            tempo_ms=60000
        )

        with patch.object(TextExtractor, 'extrair_texto', return_value=mock_extraction):
            with patch.object(TextExtractor, 'extrair_chunk', return_value="Chunk de texto"):
                with patch.object(OpenRouterService, 'classificar', new_callable=AsyncMock) as mock_classificar:
                    mock_classificar.return_value = mock_openrouter_result

                    service = ClassificadorService(mock_db)
                    resultado = await service.classificar_documento_avulso(
                        pdf_bytes=b"fake pdf bytes",
                        nome_arquivo="documento.pdf",
                        prompt_texto="Classifique este documento"
                    )

                    assert resultado.sucesso is False
                    assert "Timeout" in resultado.erro

    @pytest.mark.asyncio
    async def test_classificar_documento_avulso_texto_curto(self, mock_db):
        """Testa classificação avulsa com texto muito curto"""
        from sistemas.classificador_documentos.services import ClassificadorService
        from sistemas.classificador_documentos.services_extraction import ExtractionResult, TextExtractor

        mock_extraction = ExtractionResult(
            texto="Texto",  # Muito curto
            via_ocr=False,
            tokens_total=1,
            paginas_processadas=1
        )

        with patch.object(TextExtractor, 'extrair_texto', return_value=mock_extraction):
            service = ClassificadorService(mock_db)
            resultado = await service.classificar_documento_avulso(
                pdf_bytes=b"fake pdf bytes",
                nome_arquivo="documento.pdf",
                prompt_texto="Classifique este documento"
            )

            # Deve falhar ou processar mesmo assim
            assert resultado is not None

    @pytest.mark.asyncio
    async def test_classificar_documento_avulso_excecao(self, mock_db):
        """Testa classificação avulsa com exceção na extração"""
        from sistemas.classificador_documentos.services import ClassificadorService
        from sistemas.classificador_documentos.services_extraction import ExtractionResult, TextExtractor

        # Simula extração que retorna erro
        mock_extraction = ExtractionResult(
            texto="",
            via_ocr=False,
            tokens_total=0,
            paginas_processadas=0,
            erro="Erro ao processar PDF"
        )

        with patch.object(TextExtractor, 'extrair_texto', return_value=mock_extraction):
            service = ClassificadorService(mock_db)
            resultado = await service.classificar_documento_avulso(
                pdf_bytes=b"fake pdf bytes",
                nome_arquivo="documento.pdf",
                prompt_texto="Classifique este documento"
            )

            assert resultado.sucesso is False


class TestClassificadorServiceInit:
    """Testes de inicialização do serviço"""

    def test_init_with_db(self, mock_db):
        """Testa inicialização com banco de dados"""
        from sistemas.classificador_documentos.services import ClassificadorService

        service = ClassificadorService(mock_db)

        assert service.db is mock_db
        assert service.extractor is not None
        assert service.openrouter is not None

    def test_init_creates_extractor(self, mock_db):
        """Testa que inicialização cria extractor"""
        from sistemas.classificador_documentos.services import ClassificadorService
        from sistemas.classificador_documentos.services_extraction import TextExtractor

        service = ClassificadorService(mock_db)

        assert isinstance(service.extractor, TextExtractor)

    def test_init_creates_openrouter(self, mock_db):
        """Testa que inicialização cria cliente OpenRouter"""
        from sistemas.classificador_documentos.services import ClassificadorService
        from sistemas.classificador_documentos.services_openrouter import OpenRouterService

        service = ClassificadorService(mock_db)

        assert isinstance(service.openrouter, OpenRouterService)
