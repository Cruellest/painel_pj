# tests/classificador_documentos/test_services.py
"""
Testes do serviço principal de classificação.

Testa:
- CRUD de Prompts
- CRUD de Projetos
- CRUD de Códigos
- Orquestração de classificação (com mocks)

Autor: LAB/PGE-MS
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime


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


class TestClassificadorServicePrompts:
    """Testes de CRUD de Prompts"""

    def test_listar_prompts_empty(self, mock_db):
        """Testa listagem de prompts vazia"""
        from sistemas.classificador_documentos.services import ClassificadorService

        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

        service = ClassificadorService(mock_db)
        prompts = service.listar_prompts()

        assert prompts == []

    def test_listar_prompts_apenas_ativos(self, mock_db):
        """Testa listagem apenas de prompts ativos"""
        from sistemas.classificador_documentos.services import ClassificadorService

        service = ClassificadorService(mock_db)
        service.listar_prompts(apenas_ativos=True)

        # Verifica que o filtro foi aplicado
        mock_db.query.return_value.filter.assert_called()

    def test_criar_prompt(self, mock_db):
        """Testa criação de prompt"""
        from sistemas.classificador_documentos.services import ClassificadorService
        from sistemas.classificador_documentos.models import PromptClassificacao

        service = ClassificadorService(mock_db)

        prompt = service.criar_prompt(
            nome="Teste",
            conteudo="Conteúdo do prompt",
            descricao="Descrição",
            usuario_id=1
        )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

    def test_obter_prompt_existente(self, mock_db):
        """Testa obtenção de prompt existente"""
        from sistemas.classificador_documentos.services import ClassificadorService
        from sistemas.classificador_documentos.models import PromptClassificacao

        mock_prompt = Mock(spec=PromptClassificacao)
        mock_prompt.id = 1
        mock_prompt.nome = "Teste"

        mock_db.query.return_value.filter.return_value.first.return_value = mock_prompt

        service = ClassificadorService(mock_db)
        prompt = service.obter_prompt(1)

        assert prompt is not None
        assert prompt.id == 1

    def test_obter_prompt_inexistente(self, mock_db):
        """Testa obtenção de prompt inexistente"""
        from sistemas.classificador_documentos.services import ClassificadorService

        mock_db.query.return_value.filter.return_value.first.return_value = None

        service = ClassificadorService(mock_db)
        prompt = service.obter_prompt(999)

        assert prompt is None


class TestClassificadorServiceProjetos:
    """Testes de CRUD de Projetos"""

    def test_listar_projetos_usuario(self, mock_db):
        """Testa listagem de projetos do usuário"""
        from sistemas.classificador_documentos.services import ClassificadorService

        mock_db.query.return_value.filter.return_value.filter.return_value.order_by.return_value.all.return_value = []

        service = ClassificadorService(mock_db)
        projetos = service.listar_projetos(usuario_id=1)

        assert projetos == []

    def test_criar_projeto(self, mock_db):
        """Testa criação de projeto"""
        from sistemas.classificador_documentos.services import ClassificadorService

        service = ClassificadorService(mock_db)

        projeto = service.criar_projeto(
            nome="Projeto Teste",
            usuario_id=1,
            descricao="Descrição do projeto"
        )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    def test_obter_projeto_existente(self, mock_db):
        """Testa obtenção de projeto existente"""
        from sistemas.classificador_documentos.services import ClassificadorService
        from sistemas.classificador_documentos.models import ProjetoClassificacao

        mock_projeto = Mock(spec=ProjetoClassificacao)
        mock_projeto.id = 1
        mock_projeto.nome = "Projeto Teste"

        mock_db.query.return_value.filter.return_value.first.return_value = mock_projeto

        service = ClassificadorService(mock_db)
        projeto = service.obter_projeto(1)

        assert projeto is not None
        assert projeto.id == 1

    def test_atualizar_projeto(self, mock_db):
        """Testa atualização de projeto"""
        from sistemas.classificador_documentos.services import ClassificadorService
        from sistemas.classificador_documentos.models import ProjetoClassificacao

        mock_projeto = Mock(spec=ProjetoClassificacao)
        mock_projeto.id = 1
        mock_projeto.nome = "Projeto Original"

        mock_db.query.return_value.filter.return_value.first.return_value = mock_projeto

        service = ClassificadorService(mock_db)
        projeto = service.atualizar_projeto(1, nome="Projeto Atualizado")

        assert projeto is not None
        mock_db.commit.assert_called()


class TestClassificadorServiceCodigos:
    """Testes de CRUD de Códigos de Documentos"""

    def test_adicionar_codigos(self, mock_db):
        """Testa adição de códigos"""
        from sistemas.classificador_documentos.services import ClassificadorService

        # Simula que não existe código duplicado
        mock_db.query.return_value.filter.return_value.first.return_value = None

        service = ClassificadorService(mock_db)

        codigos = service.adicionar_codigos(
            projeto_id=1,
            codigos=["COD001", "COD002", "COD003"],
            numero_processo="0800001-00.2024.8.12.0001"
        )

        # Deve ter chamado add 3 vezes
        assert mock_db.add.call_count == 3
        mock_db.commit.assert_called()

    def test_adicionar_codigos_duplicados(self, mock_db):
        """Testa que códigos duplicados são ignorados"""
        from sistemas.classificador_documentos.services import ClassificadorService
        from sistemas.classificador_documentos.models import CodigoDocumentoProjeto

        # Simula que já existe um código
        mock_existente = Mock(spec=CodigoDocumentoProjeto)
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            mock_existente,  # Primeiro código existe
            None,  # Segundo não existe
            None   # Terceiro não existe
        ]

        service = ClassificadorService(mock_db)

        codigos = service.adicionar_codigos(
            projeto_id=1,
            codigos=["COD001", "COD002", "COD003"]
        )

        # Deve ter chamado add apenas 2 vezes (ignorando o duplicado)
        assert mock_db.add.call_count == 2

    def test_adicionar_codigos_vazios(self, mock_db):
        """Testa adição de códigos vazios"""
        from sistemas.classificador_documentos.services import ClassificadorService

        service = ClassificadorService(mock_db)

        codigos = service.adicionar_codigos(
            projeto_id=1,
            codigos=["", "  ", "   "]
        )

        assert len(codigos) == 0
        assert mock_db.add.call_count == 0

    def test_remover_codigo_existente(self, mock_db):
        """Testa remoção de código existente"""
        from sistemas.classificador_documentos.services import ClassificadorService
        from sistemas.classificador_documentos.models import CodigoDocumentoProjeto

        mock_codigo = Mock(spec=CodigoDocumentoProjeto)
        mock_db.query.return_value.filter.return_value.first.return_value = mock_codigo

        service = ClassificadorService(mock_db)
        resultado = service.remover_codigo(1)

        assert resultado is True
        mock_db.delete.assert_called_once()
        mock_db.commit.assert_called()

    def test_remover_codigo_inexistente(self, mock_db):
        """Testa remoção de código inexistente"""
        from sistemas.classificador_documentos.services import ClassificadorService

        mock_db.query.return_value.filter.return_value.first.return_value = None

        service = ClassificadorService(mock_db)
        resultado = service.remover_codigo(999)

        assert resultado is False
        mock_db.delete.assert_not_called()


class TestClassificadorServiceClassificacao:
    """Testes de classificação"""

    @pytest.mark.asyncio
    async def test_classificar_documento_avulso_success(self, mock_db):
        """Testa classificação avulsa com sucesso"""
        from sistemas.classificador_documentos.services import ClassificadorService
        from sistemas.classificador_documentos.services_extraction import ExtractionResult, TextExtractor
        from sistemas.classificador_documentos.services_openrouter import OpenRouterResult, OpenRouterService

        # Mock do extractor
        mock_extraction = ExtractionResult(
            texto="Texto extraído do documento para classificação. " * 10,
            via_ocr=False,
            tokens_total=500,
            paginas_processadas=5
        )

        # Mock do OpenRouter
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
            with patch.object(TextExtractor, 'extrair_chunk', return_value="Chunk de texto"):
                with patch.object(OpenRouterService, 'classificar', new_callable=AsyncMock) as mock_classificar:
                    mock_classificar.return_value = mock_openrouter_result

                    service = ClassificadorService(mock_db)
                    resultado = await service.classificar_documento_avulso(
                        pdf_bytes=b"fake pdf bytes",
                        nome_arquivo="documento.pdf",
                        prompt_texto="Classifique este documento"
                    )

                    assert resultado.sucesso is True
                    assert resultado.categoria == "decisao"
                    assert resultado.confianca == "alta"

    @pytest.mark.asyncio
    async def test_classificar_documento_avulso_texto_vazio(self, mock_db):
        """Testa classificação avulsa com texto vazio"""
        from sistemas.classificador_documentos.services import ClassificadorService
        from sistemas.classificador_documentos.services_extraction import ExtractionResult

        service = ClassificadorService(mock_db)

        # Mock do extractor retornando texto vazio
        mock_extraction = ExtractionResult(
            texto="",
            via_ocr=False,
            tokens_total=0,
            paginas_processadas=0
        )

        with patch.object(service.extractor, 'extrair_texto', return_value=mock_extraction):
            resultado = await service.classificar_documento_avulso(
                pdf_bytes=b"fake pdf bytes",
                nome_arquivo="documento.pdf",
                prompt_texto="Classifique este documento"
            )

            assert resultado.sucesso is False
            assert "vazio" in resultado.erro.lower()


class TestClassificadorServiceConsultas:
    """Testes de consultas"""

    def test_listar_execucoes(self, mock_db):
        """Testa listagem de execuções"""
        from sistemas.classificador_documentos.services import ClassificadorService

        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

        service = ClassificadorService(mock_db)
        execucoes = service.listar_execucoes(projeto_id=1)

        assert execucoes == []

    def test_listar_resultados_com_filtros(self, mock_db):
        """Testa listagem de resultados com filtros"""
        from sistemas.classificador_documentos.services import ClassificadorService

        mock_db.query.return_value.filter.return_value.filter.return_value.filter.return_value.order_by.return_value.all.return_value = []

        service = ClassificadorService(mock_db)
        resultados = service.listar_resultados(
            execucao_id=1,
            categoria="decisao",
            confianca="alta"
        )

        assert resultados == []
