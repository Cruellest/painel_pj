# tests/classificador_documentos/test_router.py
"""
Testes de integração dos endpoints do Sistema de Classificação de Documentos.

Testa:
- Endpoints de status
- Endpoints de prompts
- Endpoints de projetos
- Endpoints de códigos
- Endpoints de resultados e exportação

Autor: LAB/PGE-MS
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient


# Fixture para simular autenticação
@pytest.fixture
def mock_auth():
    """Mock da dependência de autenticação"""
    mock_user = Mock()
    mock_user.id = 1
    mock_user.username = "testuser"
    mock_user.role = "user"
    return mock_user


@pytest.fixture
def mock_db():
    """Mock da sessão do banco de dados"""
    db = Mock()
    return db


class TestStatusEndpoint:
    """Testes do endpoint de status"""

    @pytest.mark.asyncio
    async def test_status_api_disponivel(self):
        """Testa status da API quando disponível"""
        from sistemas.classificador_documentos.router import verificar_status_api
        from sistemas.classificador_documentos.services_openrouter import OpenRouterService

        with patch.object(OpenRouterService, 'verificar_disponibilidade', new_callable=AsyncMock) as mock_verif:
            mock_verif.return_value = True

            result = await verificar_status_api()

            assert result.disponivel is True
            assert result.modelo_padrao == "google/gemini-2.5-flash-lite"
            assert len(result.modelos_disponiveis) > 0

    @pytest.mark.asyncio
    async def test_status_api_indisponivel(self):
        """Testa status da API quando indisponível"""
        from sistemas.classificador_documentos.router import verificar_status_api
        from sistemas.classificador_documentos.services_openrouter import OpenRouterService

        with patch.object(OpenRouterService, 'verificar_disponibilidade', new_callable=AsyncMock) as mock_verif:
            mock_verif.return_value = False

            result = await verificar_status_api()

            assert result.disponivel is False


class TestPromptsEndpoints:
    """Testes dos endpoints de prompts"""

    @pytest.mark.asyncio
    async def test_listar_prompts(self, mock_auth, mock_db):
        """Testa listagem de prompts"""
        from sistemas.classificador_documentos.router import listar_prompts
        from sistemas.classificador_documentos.services import ClassificadorService
        from datetime import datetime, timezone

        with patch.object(ClassificadorService, 'listar_prompts') as mock_listar:
            mock_prompt = Mock()
            mock_prompt.id = 1
            mock_prompt.nome = "Teste"
            mock_prompt.descricao = "Descrição"
            mock_prompt.conteudo = "Conteúdo"
            mock_prompt.ativo = True
            mock_prompt.criado_em = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
            mock_prompt.atualizado_em = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

            mock_listar.return_value = [mock_prompt]

            result = await listar_prompts(
                apenas_ativos=True,
                current_user=mock_auth,
                db=mock_db
            )

            assert len(result) == 1
            assert result[0]["nome"] == "Teste"

    @pytest.mark.asyncio
    async def test_criar_prompt_sucesso(self, mock_auth, mock_db):
        """Testa criação de prompt com sucesso"""
        from sistemas.classificador_documentos.router import criar_prompt
        from sistemas.classificador_documentos.schemas import PromptCreate
        from sistemas.classificador_documentos.services import ClassificadorService

        req = PromptCreate(
            nome="Novo Prompt",
            conteudo="Conteúdo do prompt de teste",
            descricao="Descrição do prompt"
        )

        with patch.object(ClassificadorService, 'criar_prompt') as mock_criar:
            mock_prompt = Mock()
            mock_prompt.id = 1
            mock_criar.return_value = mock_prompt

            result = await criar_prompt(
                req=req,
                current_user=mock_auth,
                db=mock_db
            )

            assert "id" in result
            assert result["id"] == 1
            assert "mensagem" in result


class TestProjetosEndpoints:
    """Testes dos endpoints de projetos"""

    @pytest.mark.asyncio
    async def test_listar_projetos(self, mock_auth, mock_db):
        """Testa listagem de projetos"""
        from sistemas.classificador_documentos.router import listar_projetos
        from sistemas.classificador_documentos.services import ClassificadorService
        from datetime import datetime, timezone

        with patch.object(ClassificadorService, 'listar_projetos') as mock_listar:
            mock_projeto = Mock()
            mock_projeto.id = 1
            mock_projeto.nome = "Projeto Teste"
            mock_projeto.descricao = "Descrição"
            mock_projeto.prompt_id = 1
            mock_projeto.modelo = "google/gemini-2.5-flash-lite"
            mock_projeto.modo_processamento = "chunk"
            mock_projeto.posicao_chunk = "fim"
            mock_projeto.tamanho_chunk = 512
            mock_projeto.max_concurrent = 3
            mock_projeto.ativo = True
            mock_projeto.codigos = []
            mock_projeto.execucoes = []
            mock_projeto.criado_em = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
            mock_projeto.atualizado_em = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

            mock_listar.return_value = [mock_projeto]

            result = await listar_projetos(
                apenas_ativos=True,
                current_user=mock_auth,
                db=mock_db
            )

            assert len(result) == 1
            assert result[0]["nome"] == "Projeto Teste"

    @pytest.mark.asyncio
    async def test_criar_projeto_sucesso(self, mock_auth, mock_db):
        """Testa criação de projeto com sucesso"""
        from sistemas.classificador_documentos.router import criar_projeto
        from sistemas.classificador_documentos.schemas import ProjetoCreate
        from sistemas.classificador_documentos.services import ClassificadorService

        req = ProjetoCreate(
            nome="Novo Projeto",
            descricao="Descrição do projeto"
        )

        with patch.object(ClassificadorService, 'criar_projeto') as mock_criar:
            mock_projeto = Mock()
            mock_projeto.id = 1
            mock_criar.return_value = mock_projeto

            result = await criar_projeto(
                req=req,
                current_user=mock_auth,
                db=mock_db
            )

            assert "id" in result
            assert result["id"] == 1


class TestCodigosEndpoints:
    """Testes dos endpoints de códigos"""

    @pytest.mark.asyncio
    async def test_adicionar_codigos(self, mock_auth, mock_db):
        """Testa adição de códigos"""
        from sistemas.classificador_documentos.router import adicionar_codigos
        from sistemas.classificador_documentos.schemas import CodigoDocumentoBulkCreate
        from sistemas.classificador_documentos.services import ClassificadorService
        from sistemas.classificador_documentos.models import ProjetoClassificacao

        req = CodigoDocumentoBulkCreate(
            codigos=["COD001", "COD002", "COD003"],
            numero_processo="0800001-00.2024.8.12.0001"
        )

        with patch.object(ClassificadorService, 'obter_projeto') as mock_obter:
            mock_projeto = Mock(spec=ProjetoClassificacao)
            mock_projeto.usuario_id = 1
            mock_obter.return_value = mock_projeto

            with patch.object(ClassificadorService, 'adicionar_codigos') as mock_add:
                mock_add.return_value = [Mock(), Mock(), Mock()]

                result = await adicionar_codigos(
                    projeto_id=1,
                    req=req,
                    current_user=mock_auth,
                    db=mock_db
                )

                assert "adicionados" in result
                assert result["adicionados"] == 3


class TestExportacaoEndpoints:
    """Testes dos endpoints de exportação"""

    @pytest.mark.asyncio
    async def test_exportar_json(self, mock_auth, mock_db):
        """Testa exportação para JSON"""
        from sistemas.classificador_documentos.router import exportar_json
        from sistemas.classificador_documentos.services import ClassificadorService
        from sistemas.classificador_documentos.services_export import ExportService
        from sistemas.classificador_documentos.models import (
            ExecucaoClassificacao, ProjetoClassificacao
        )

        with patch.object(ClassificadorService, 'obter_execucao') as mock_exec:
            mock_execucao = Mock(spec=ExecucaoClassificacao)
            mock_execucao.projeto_id = 1
            mock_exec.return_value = mock_execucao

            with patch.object(ClassificadorService, 'obter_projeto') as mock_proj:
                mock_projeto = Mock(spec=ProjetoClassificacao)
                mock_projeto.usuario_id = 1
                mock_proj.return_value = mock_projeto

                with patch.object(ClassificadorService, 'listar_resultados') as mock_list:
                    mock_list.return_value = []

                    with patch.object(ExportService, 'exportar_json') as mock_export:
                        mock_export.return_value = []

                        result = await exportar_json(
                            execucao_id=1,
                            current_user=mock_auth,
                            db=mock_db
                        )

                        assert result == []


class TestClassificacaoAvulsaEndpoint:
    """Testes do endpoint de classificação avulsa"""

    @pytest.mark.asyncio
    async def test_classificar_avulso_sem_arquivo(self, mock_auth, mock_db):
        """Testa classificação avulsa sem arquivo"""
        from sistemas.classificador_documentos.router import classificar_documento_avulso
        from fastapi import HTTPException

        # Este teste verificaria o comportamento quando não há arquivo
        # mas como o endpoint usa UploadFile, precisaria de um teste de integração
        # com TestClient para testar completamente
        pass

    @pytest.mark.asyncio
    async def test_classificar_avulso_sem_prompt(self, mock_auth, mock_db):
        """Testa classificação avulsa sem prompt"""
        from sistemas.classificador_documentos.router import classificar_documento_avulso
        from sistemas.classificador_documentos.services import ClassificadorService
        from fastapi import UploadFile, HTTPException
        import pytest

        mock_file = Mock(spec=UploadFile)
        mock_file.filename = "documento.pdf"
        mock_file.read = AsyncMock(return_value=b"fake pdf content")

        with pytest.raises(HTTPException) as exc_info:
            await classificar_documento_avulso(
                arquivo=mock_file,
                prompt_id=None,
                prompt_texto=None,
                modelo="google/gemini-2.5-flash-lite",
                modo_processamento="chunk",
                posicao_chunk="fim",
                tamanho_chunk=512,
                current_user=mock_auth,
                db=mock_db
            )

        assert exc_info.value.status_code == 400
        assert "prompt" in exc_info.value.detail.lower()


class TestTJMSEndpoints:
    """Testes dos endpoints de integração com TJ-MS"""

    @pytest.mark.asyncio
    async def test_consultar_processo_tjms_sucesso(self, mock_auth):
        """Testa consulta de processo no TJ-MS com sucesso"""
        from sistemas.classificador_documentos.router import consultar_processo_tjms, ConsultaProcessoRequest
        from sistemas.classificador_documentos.services_tjms import TJMSDocumentService

        req = ConsultaProcessoRequest(numero_cnj="0800001-00.2024.8.12.0001")

        with patch.object(TJMSDocumentService, 'listar_documentos', new_callable=AsyncMock) as mock_listar:
            mock_listar.return_value = ([
                {"id": "123", "tipo": "Sentença", "descricao": "Sentença de procedência"},
                {"id": "456", "tipo": "Despacho", "descricao": "Despacho inicial"}
            ], None)

            result = await consultar_processo_tjms(req=req, current_user=mock_auth)

            assert result["numero_cnj"] == "0800001-00.2024.8.12.0001"
            assert result["total_documentos"] == 2
            assert len(result["documentos"]) == 2

    @pytest.mark.asyncio
    async def test_consultar_processo_tjms_erro(self, mock_auth):
        """Testa consulta de processo no TJ-MS com erro"""
        from sistemas.classificador_documentos.router import consultar_processo_tjms, ConsultaProcessoRequest
        from sistemas.classificador_documentos.services_tjms import TJMSDocumentService
        from fastapi import HTTPException

        req = ConsultaProcessoRequest(numero_cnj="0800001-00.2024.8.12.0001")

        with patch.object(TJMSDocumentService, 'listar_documentos', new_callable=AsyncMock) as mock_listar:
            mock_listar.return_value = ([], "Processo não encontrado")

            with pytest.raises(HTTPException) as exc_info:
                await consultar_processo_tjms(req=req, current_user=mock_auth)

            assert exc_info.value.status_code == 400
            assert "Processo não encontrado" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_baixar_documento_tjms_sucesso(self, mock_auth):
        """Testa download de documento do TJ-MS com sucesso"""
        from sistemas.classificador_documentos.router import baixar_documento_tjms, BaixarDocumentoTJRequest
        from sistemas.classificador_documentos.services_tjms import TJMSDocumentService, DocumentoTJMS

        req = BaixarDocumentoTJRequest(numero_cnj="0800001-00.2024.8.12.0001", id_documento="12345")

        with patch.object(TJMSDocumentService, 'baixar_documento', new_callable=AsyncMock) as mock_baixar:
            mock_doc = DocumentoTJMS(
                id_documento="12345",
                numero_processo="0800001-00.2024.8.12.0001",
                conteudo_bytes=b"%PDF-1.4 test content",
                formato="pdf"
            )
            mock_baixar.return_value = mock_doc

            result = await baixar_documento_tjms(req=req, current_user=mock_auth)

            assert result["id_documento"] == "12345"
            assert result["formato"] == "pdf"
            assert result["tamanho_bytes"] > 0
            assert result["conteudo_base64"] is not None

    @pytest.mark.asyncio
    async def test_baixar_documento_tjms_erro(self, mock_auth):
        """Testa download de documento do TJ-MS com erro"""
        from sistemas.classificador_documentos.router import baixar_documento_tjms, BaixarDocumentoTJRequest
        from sistemas.classificador_documentos.services_tjms import TJMSDocumentService, DocumentoTJMS
        from fastapi import HTTPException

        req = BaixarDocumentoTJRequest(numero_cnj="0800001-00.2024.8.12.0001", id_documento="99999")

        with patch.object(TJMSDocumentService, 'baixar_documento', new_callable=AsyncMock) as mock_baixar:
            mock_doc = DocumentoTJMS(
                id_documento="99999",
                numero_processo="0800001-00.2024.8.12.0001",
                erro="Documento não encontrado"
            )
            mock_baixar.return_value = mock_doc

            with pytest.raises(HTTPException) as exc_info:
                await baixar_documento_tjms(req=req, current_user=mock_auth)

            assert exc_info.value.status_code == 400
            assert "não encontrado" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_adicionar_codigos_tjms(self, mock_auth, mock_db):
        """Testa adição de códigos do TJ-MS a um projeto"""
        from sistemas.classificador_documentos.router import adicionar_codigos_tjms, AdicionarCodigosTJRequest
        from sistemas.classificador_documentos.services import ClassificadorService
        from sistemas.classificador_documentos.models import ProjetoClassificacao

        req = AdicionarCodigosTJRequest(
            numero_cnj="0800001-00.2024.8.12.0001",
            ids_documentos=["123", "456", "789"]
        )

        with patch.object(ClassificadorService, 'obter_projeto') as mock_obter:
            mock_projeto = Mock(spec=ProjetoClassificacao)
            mock_projeto.usuario_id = 1
            mock_obter.return_value = mock_projeto

            with patch.object(ClassificadorService, 'adicionar_codigos') as mock_add:
                mock_add.return_value = [Mock(), Mock(), Mock()]

                result = await adicionar_codigos_tjms(
                    projeto_id=1,
                    req=req,
                    current_user=mock_auth,
                    db=mock_db
                )

                assert "adicionados" in result
                assert result["adicionados"] == 3
                assert result["numero_cnj"] == "0800001-00.2024.8.12.0001"


class TestEndpointsNaoRetornam500:
    """Testes para garantir que endpoints críticos não retornam 500"""

    @pytest.mark.asyncio
    async def test_prompts_retorna_lista_vazia_nao_500(self, mock_auth, mock_db):
        """Testa que GET /prompts retorna lista vazia, não 500"""
        from sistemas.classificador_documentos.router import listar_prompts
        from sistemas.classificador_documentos.services import ClassificadorService

        with patch.object(ClassificadorService, 'listar_prompts') as mock_listar:
            mock_listar.return_value = []

            result = await listar_prompts(
                apenas_ativos=True,
                current_user=mock_auth,
                db=mock_db
            )

            assert result == []

    @pytest.mark.asyncio
    async def test_projetos_retorna_lista_vazia_nao_500(self, mock_auth, mock_db):
        """Testa que GET /projetos retorna lista vazia, não 500"""
        from sistemas.classificador_documentos.router import listar_projetos
        from sistemas.classificador_documentos.services import ClassificadorService

        with patch.object(ClassificadorService, 'listar_projetos') as mock_listar:
            mock_listar.return_value = []

            result = await listar_projetos(
                apenas_ativos=True,
                current_user=mock_auth,
                db=mock_db
            )

            assert result == []
