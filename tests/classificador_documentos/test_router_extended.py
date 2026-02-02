# tests/classificador_documentos/test_router_extended.py
"""
Testes estendidos dos endpoints do Router.

Testa cenários adicionais para aumentar cobertura:
- Casos de erro (404, 403)
- Endpoints de CRUD completos
- Endpoints de execução e resultados
- Exportação

Autor: LAB/PGE-MS
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timezone
from fastapi import HTTPException


@pytest.fixture
def mock_auth():
    """Mock da dependência de autenticação"""
    mock_user = Mock()
    mock_user.id = 1
    mock_user.username = "testuser"
    mock_user.role = "user"
    return mock_user


@pytest.fixture
def mock_admin():
    """Mock de usuário admin"""
    mock_user = Mock()
    mock_user.id = 99
    mock_user.username = "admin"
    mock_user.role = "admin"
    return mock_user


@pytest.fixture
def mock_db():
    """Mock da sessão do banco de dados"""
    db = Mock()
    return db


class TestPromptEndpointsExtended:
    """Testes estendidos de prompts"""

    @pytest.mark.asyncio
    async def test_obter_prompt_existente(self, mock_auth, mock_db):
        """Testa obtenção de prompt existente"""
        from sistemas.classificador_documentos.router import obter_prompt
        from sistemas.classificador_documentos.services import ClassificadorService

        with patch.object(ClassificadorService, 'obter_prompt') as mock_obter:
            mock_prompt = Mock()
            mock_prompt.id = 1
            mock_prompt.nome = "Teste"
            mock_prompt.descricao = "Desc"
            mock_prompt.conteudo = "Conteúdo"
            mock_prompt.ativo = True
            mock_prompt.criado_em = datetime(2024, 1, 1, tzinfo=timezone.utc)
            mock_prompt.atualizado_em = datetime(2024, 1, 1, tzinfo=timezone.utc)
            mock_obter.return_value = mock_prompt

            result = await obter_prompt(1, mock_auth, mock_db)

            assert result["id"] == 1
            assert result["nome"] == "Teste"

    @pytest.mark.asyncio
    async def test_obter_prompt_nao_encontrado(self, mock_auth, mock_db):
        """Testa obtenção de prompt inexistente"""
        from sistemas.classificador_documentos.router import obter_prompt
        from sistemas.classificador_documentos.services import ClassificadorService

        with patch.object(ClassificadorService, 'obter_prompt') as mock_obter:
            mock_obter.return_value = None

            with pytest.raises(HTTPException) as exc_info:
                await obter_prompt(999, mock_auth, mock_db)

            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_atualizar_prompt_sucesso(self, mock_auth, mock_db):
        """Testa atualização de prompt"""
        from sistemas.classificador_documentos.router import atualizar_prompt
        from sistemas.classificador_documentos.schemas import PromptUpdate
        from sistemas.classificador_documentos.services import ClassificadorService

        req = PromptUpdate(nome="Prompt Atualizado")

        with patch.object(ClassificadorService, 'atualizar_prompt') as mock_atualizar:
            mock_atualizar.return_value = Mock()

            result = await atualizar_prompt(1, req, mock_auth, mock_db)

            assert "mensagem" in result

    @pytest.mark.asyncio
    async def test_atualizar_prompt_nao_encontrado(self, mock_auth, mock_db):
        """Testa atualização de prompt inexistente"""
        from sistemas.classificador_documentos.router import atualizar_prompt
        from sistemas.classificador_documentos.schemas import PromptUpdate
        from sistemas.classificador_documentos.services import ClassificadorService

        req = PromptUpdate(nome="Teste")

        with patch.object(ClassificadorService, 'atualizar_prompt') as mock_atualizar:
            mock_atualizar.return_value = None

            with pytest.raises(HTTPException) as exc_info:
                await atualizar_prompt(999, req, mock_auth, mock_db)

            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_deletar_prompt_sucesso(self, mock_auth, mock_db):
        """Testa deleção de prompt"""
        from sistemas.classificador_documentos.router import deletar_prompt
        from sistemas.classificador_documentos.services import ClassificadorService

        with patch.object(ClassificadorService, 'atualizar_prompt') as mock_atualizar:
            mock_atualizar.return_value = Mock()

            result = await deletar_prompt(1, mock_auth, mock_db)

            assert "mensagem" in result

    @pytest.mark.asyncio
    async def test_deletar_prompt_nao_encontrado(self, mock_auth, mock_db):
        """Testa deleção de prompt inexistente"""
        from sistemas.classificador_documentos.router import deletar_prompt
        from sistemas.classificador_documentos.services import ClassificadorService

        with patch.object(ClassificadorService, 'atualizar_prompt') as mock_atualizar:
            mock_atualizar.return_value = None

            with pytest.raises(HTTPException) as exc_info:
                await deletar_prompt(999, mock_auth, mock_db)

            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_criar_prompt_erro(self, mock_auth, mock_db):
        """Testa criação de prompt com erro"""
        from sistemas.classificador_documentos.router import criar_prompt
        from sistemas.classificador_documentos.schemas import PromptCreate
        from sistemas.classificador_documentos.services import ClassificadorService

        req = PromptCreate(
            nome="Teste",
            conteudo="Conteúdo do prompt com pelo menos 10 caracteres",
            descricao="Descrição do prompt de teste"
        )

        with patch.object(ClassificadorService, 'criar_prompt') as mock_criar:
            mock_criar.side_effect = Exception("Erro no banco")

            with pytest.raises(HTTPException) as exc_info:
                await criar_prompt(req, mock_auth, mock_db)

            assert exc_info.value.status_code == 400


class TestProjetoEndpointsExtended:
    """Testes estendidos de projetos"""

    @pytest.mark.asyncio
    async def test_obter_projeto_existente(self, mock_auth, mock_db):
        """Testa obtenção de projeto existente"""
        from sistemas.classificador_documentos.router import obter_projeto
        from sistemas.classificador_documentos.services import ClassificadorService
        from sistemas.classificador_documentos.models import ProjetoClassificacao

        with patch.object(ClassificadorService, 'obter_projeto') as mock_obter:
            mock_projeto = Mock(spec=ProjetoClassificacao)
            mock_projeto.id = 1
            mock_projeto.nome = "Projeto"
            mock_projeto.descricao = "Desc"
            mock_projeto.prompt_id = 1
            mock_projeto.modelo = "google/gemini-2.5-flash-lite"
            mock_projeto.modo_processamento = "chunk"
            mock_projeto.posicao_chunk = "fim"
            mock_projeto.tamanho_chunk = 512
            mock_projeto.max_concurrent = 3
            mock_projeto.ativo = True
            mock_projeto.usuario_id = 1
            mock_projeto.codigos = []
            mock_projeto.criado_em = datetime(2024, 1, 1, tzinfo=timezone.utc)
            mock_projeto.atualizado_em = datetime(2024, 1, 1, tzinfo=timezone.utc)
            mock_obter.return_value = mock_projeto

            result = await obter_projeto(1, mock_auth, mock_db)

            assert result["id"] == 1

    @pytest.mark.asyncio
    async def test_obter_projeto_nao_encontrado(self, mock_auth, mock_db):
        """Testa obtenção de projeto inexistente"""
        from sistemas.classificador_documentos.router import obter_projeto
        from sistemas.classificador_documentos.services import ClassificadorService

        with patch.object(ClassificadorService, 'obter_projeto') as mock_obter:
            mock_obter.return_value = None

            with pytest.raises(HTTPException) as exc_info:
                await obter_projeto(999, mock_auth, mock_db)

            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_obter_projeto_acesso_negado(self, mock_auth, mock_db):
        """Testa acesso negado a projeto de outro usuário"""
        from sistemas.classificador_documentos.router import obter_projeto
        from sistemas.classificador_documentos.services import ClassificadorService
        from sistemas.classificador_documentos.models import ProjetoClassificacao

        with patch.object(ClassificadorService, 'obter_projeto') as mock_obter:
            mock_projeto = Mock(spec=ProjetoClassificacao)
            mock_projeto.usuario_id = 999  # Outro usuário
            mock_obter.return_value = mock_projeto

            with pytest.raises(HTTPException) as exc_info:
                await obter_projeto(1, mock_auth, mock_db)

            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_obter_projeto_admin_pode_acessar(self, mock_admin, mock_db):
        """Testa que admin pode acessar projeto de outro usuário"""
        from sistemas.classificador_documentos.router import obter_projeto
        from sistemas.classificador_documentos.services import ClassificadorService
        from sistemas.classificador_documentos.models import ProjetoClassificacao

        with patch.object(ClassificadorService, 'obter_projeto') as mock_obter:
            mock_projeto = Mock(spec=ProjetoClassificacao)
            mock_projeto.id = 1
            mock_projeto.nome = "Projeto"
            mock_projeto.descricao = None
            mock_projeto.prompt_id = None
            mock_projeto.modelo = "google/gemini-2.5-flash-lite"
            mock_projeto.modo_processamento = "chunk"
            mock_projeto.posicao_chunk = "fim"
            mock_projeto.tamanho_chunk = 512
            mock_projeto.max_concurrent = 3
            mock_projeto.ativo = True
            mock_projeto.usuario_id = 1  # Outro usuário
            mock_projeto.codigos = []
            mock_projeto.criado_em = datetime(2024, 1, 1, tzinfo=timezone.utc)
            mock_projeto.atualizado_em = datetime(2024, 1, 1, tzinfo=timezone.utc)
            mock_obter.return_value = mock_projeto

            result = await obter_projeto(1, mock_admin, mock_db)

            assert result["id"] == 1

    @pytest.mark.asyncio
    async def test_atualizar_projeto_sucesso(self, mock_auth, mock_db):
        """Testa atualização de projeto"""
        from sistemas.classificador_documentos.router import atualizar_projeto
        from sistemas.classificador_documentos.schemas import ProjetoUpdate
        from sistemas.classificador_documentos.services import ClassificadorService
        from sistemas.classificador_documentos.models import ProjetoClassificacao

        req = ProjetoUpdate(nome="Projeto Atualizado")

        with patch.object(ClassificadorService, 'obter_projeto') as mock_obter:
            mock_projeto = Mock(spec=ProjetoClassificacao)
            mock_projeto.usuario_id = 1
            mock_obter.return_value = mock_projeto

            with patch.object(ClassificadorService, 'atualizar_projeto') as mock_atualizar:
                mock_atualizar.return_value = mock_projeto

                result = await atualizar_projeto(1, req, mock_auth, mock_db)

                assert "mensagem" in result

    @pytest.mark.asyncio
    async def test_deletar_projeto_sucesso(self, mock_auth, mock_db):
        """Testa deleção de projeto"""
        from sistemas.classificador_documentos.router import deletar_projeto
        from sistemas.classificador_documentos.services import ClassificadorService
        from sistemas.classificador_documentos.models import ProjetoClassificacao

        with patch.object(ClassificadorService, 'obter_projeto') as mock_obter:
            mock_projeto = Mock(spec=ProjetoClassificacao)
            mock_projeto.usuario_id = 1
            mock_obter.return_value = mock_projeto

            with patch.object(ClassificadorService, 'atualizar_projeto') as mock_atualizar:
                mock_atualizar.return_value = mock_projeto

                result = await deletar_projeto(1, mock_auth, mock_db)

                assert "mensagem" in result

    @pytest.mark.asyncio
    async def test_criar_projeto_erro(self, mock_auth, mock_db):
        """Testa criação de projeto com erro"""
        from sistemas.classificador_documentos.router import criar_projeto
        from sistemas.classificador_documentos.schemas import ProjetoCreate
        from sistemas.classificador_documentos.services import ClassificadorService

        req = ProjetoCreate(nome="Teste", descricao="Desc")

        with patch.object(ClassificadorService, 'criar_projeto') as mock_criar:
            mock_criar.side_effect = Exception("Erro no banco")

            with pytest.raises(HTTPException) as exc_info:
                await criar_projeto(req, mock_auth, mock_db)

            assert exc_info.value.status_code == 400


class TestCodigosEndpointsExtended:
    """Testes estendidos de códigos"""

    @pytest.mark.asyncio
    async def test_listar_codigos_sucesso(self, mock_auth, mock_db):
        """Testa listagem de códigos"""
        from sistemas.classificador_documentos.router import listar_codigos
        from sistemas.classificador_documentos.services import ClassificadorService
        from sistemas.classificador_documentos.models import ProjetoClassificacao

        with patch.object(ClassificadorService, 'obter_projeto') as mock_obter:
            mock_projeto = Mock(spec=ProjetoClassificacao)
            mock_projeto.usuario_id = 1
            mock_obter.return_value = mock_projeto

            with patch.object(ClassificadorService, 'listar_codigos') as mock_listar:
                mock_codigo = Mock()
                mock_codigo.id = 1
                mock_codigo.codigo = "COD001"
                mock_codigo.numero_processo = "0800001-00.2024.8.12.0001"
                mock_codigo.descricao = "Desc"
                mock_codigo.fonte = "tjms"
                mock_codigo.ativo = True
                mock_codigo.criado_em = datetime(2024, 1, 1, tzinfo=timezone.utc)
                mock_listar.return_value = [mock_codigo]

                result = await listar_codigos(1, mock_auth, mock_db)

                assert len(result) == 1
                assert result[0]["codigo"] == "COD001"

    @pytest.mark.asyncio
    async def test_remover_codigo_sucesso(self, mock_auth, mock_db):
        """Testa remoção de código"""
        from sistemas.classificador_documentos.router import remover_codigo
        from sistemas.classificador_documentos.services import ClassificadorService

        with patch.object(ClassificadorService, 'remover_codigo') as mock_remover:
            mock_remover.return_value = True

            result = await remover_codigo(1, mock_auth, mock_db)

            assert "mensagem" in result

    @pytest.mark.asyncio
    async def test_remover_codigo_nao_encontrado(self, mock_auth, mock_db):
        """Testa remoção de código inexistente"""
        from sistemas.classificador_documentos.router import remover_codigo
        from sistemas.classificador_documentos.services import ClassificadorService

        with patch.object(ClassificadorService, 'remover_codigo') as mock_remover:
            mock_remover.return_value = False

            with pytest.raises(HTTPException) as exc_info:
                await remover_codigo(999, mock_auth, mock_db)

            assert exc_info.value.status_code == 404


class TestExecucaoEndpointsExtended:
    """Testes estendidos de execução"""

    @pytest.mark.asyncio
    async def test_listar_execucoes_sucesso(self, mock_auth, mock_db):
        """Testa listagem de execuções"""
        from sistemas.classificador_documentos.router import listar_execucoes
        from sistemas.classificador_documentos.services import ClassificadorService
        from sistemas.classificador_documentos.models import ProjetoClassificacao

        with patch.object(ClassificadorService, 'obter_projeto') as mock_obter:
            mock_projeto = Mock(spec=ProjetoClassificacao)
            mock_projeto.usuario_id = 1
            mock_obter.return_value = mock_projeto

            with patch.object(ClassificadorService, 'listar_execucoes') as mock_listar:
                mock_exec = Mock()
                mock_exec.id = 1
                mock_exec.status = "concluido"
                mock_exec.total_arquivos = 10
                mock_exec.arquivos_processados = 10
                mock_exec.arquivos_sucesso = 9
                mock_exec.arquivos_erro = 1
                mock_exec.progresso_percentual = 100.0
                mock_exec.modelo_usado = "google/gemini-2.5-flash-lite"
                mock_exec.iniciado_em = datetime(2024, 1, 1, tzinfo=timezone.utc)
                mock_exec.finalizado_em = datetime(2024, 1, 1, tzinfo=timezone.utc)
                mock_exec.criado_em = datetime(2024, 1, 1, tzinfo=timezone.utc)
                mock_listar.return_value = [mock_exec]

                result = await listar_execucoes(1, mock_auth, mock_db)

                assert len(result) == 1
                assert result[0]["status"] == "concluido"

    @pytest.mark.asyncio
    async def test_obter_execucao_sucesso(self, mock_auth, mock_db):
        """Testa obtenção de execução"""
        from sistemas.classificador_documentos.router import obter_execucao
        from sistemas.classificador_documentos.services import ClassificadorService
        from sistemas.classificador_documentos.models import ProjetoClassificacao, ExecucaoClassificacao

        with patch.object(ClassificadorService, 'obter_execucao') as mock_obter_exec:
            mock_exec = Mock(spec=ExecucaoClassificacao)
            mock_exec.id = 1
            mock_exec.projeto_id = 1
            mock_exec.status = "concluido"
            mock_exec.total_arquivos = 10
            mock_exec.arquivos_processados = 10
            mock_exec.arquivos_sucesso = 9
            mock_exec.arquivos_erro = 1
            mock_exec.progresso_percentual = 100.0
            mock_exec.modelo_usado = "google/gemini-2.5-flash-lite"
            mock_exec.config_usada = {}
            mock_exec.erro_mensagem = None
            mock_exec.iniciado_em = datetime(2024, 1, 1, tzinfo=timezone.utc)
            mock_exec.finalizado_em = datetime(2024, 1, 1, tzinfo=timezone.utc)
            mock_exec.criado_em = datetime(2024, 1, 1, tzinfo=timezone.utc)
            mock_obter_exec.return_value = mock_exec

            with patch.object(ClassificadorService, 'obter_projeto') as mock_obter_proj:
                mock_projeto = Mock(spec=ProjetoClassificacao)
                mock_projeto.usuario_id = 1
                mock_obter_proj.return_value = mock_projeto

                result = await obter_execucao(1, mock_auth, mock_db)

                assert result["id"] == 1

    @pytest.mark.asyncio
    async def test_obter_execucao_nao_encontrada(self, mock_auth, mock_db):
        """Testa obtenção de execução inexistente"""
        from sistemas.classificador_documentos.router import obter_execucao
        from sistemas.classificador_documentos.services import ClassificadorService

        with patch.object(ClassificadorService, 'obter_execucao') as mock_obter:
            mock_obter.return_value = None

            with pytest.raises(HTTPException) as exc_info:
                await obter_execucao(999, mock_auth, mock_db)

            assert exc_info.value.status_code == 404


class TestResultadosEndpointsExtended:
    """Testes estendidos de resultados"""

    @pytest.mark.asyncio
    async def test_listar_resultados_sucesso(self, mock_auth, mock_db):
        """Testa listagem de resultados"""
        from sistemas.classificador_documentos.router import listar_resultados
        from sistemas.classificador_documentos.services import ClassificadorService
        from sistemas.classificador_documentos.models import ProjetoClassificacao, ExecucaoClassificacao

        with patch.object(ClassificadorService, 'obter_execucao') as mock_obter_exec:
            mock_exec = Mock(spec=ExecucaoClassificacao)
            mock_exec.projeto_id = 1
            mock_obter_exec.return_value = mock_exec

            with patch.object(ClassificadorService, 'obter_projeto') as mock_obter_proj:
                mock_projeto = Mock(spec=ProjetoClassificacao)
                mock_projeto.usuario_id = 1
                mock_obter_proj.return_value = mock_projeto

                with patch.object(ClassificadorService, 'listar_resultados') as mock_listar:
                    mock_resultado = Mock()
                    mock_resultado.id = 1
                    mock_resultado.codigo_documento = "COD001"
                    mock_resultado.numero_processo = "0800001-00.2024.8.12.0001"
                    mock_resultado.nome_arquivo = "doc.pdf"
                    mock_resultado.status = "concluido"
                    mock_resultado.fonte = "tjms"
                    mock_resultado.texto_extraido_via = "pdf"
                    mock_resultado.tokens_extraidos = 500
                    mock_resultado.categoria = "decisao"
                    mock_resultado.subcategoria = "deferida"
                    mock_resultado.confianca = "alta"
                    mock_resultado.justificativa = "Decisão"
                    mock_resultado.erro_mensagem = None
                    mock_resultado.processado_em = datetime(2024, 1, 1, tzinfo=timezone.utc)
                    mock_listar.return_value = [mock_resultado]

                    result = await listar_resultados(1, None, None, False, mock_auth, mock_db)

                    assert len(result) == 1
                    assert result[0]["categoria"] == "decisao"


class TestExportacaoEndpointsExtended:
    """Testes estendidos de exportação"""

    @pytest.mark.asyncio
    async def test_exportar_excel_sucesso(self, mock_auth, mock_db):
        """Testa exportação Excel"""
        from sistemas.classificador_documentos.router import exportar_excel
        from sistemas.classificador_documentos.services import ClassificadorService
        from sistemas.classificador_documentos.services_export import ExportService
        from sistemas.classificador_documentos.models import ProjetoClassificacao, ExecucaoClassificacao
        import io

        with patch.object(ClassificadorService, 'obter_execucao') as mock_obter_exec:
            mock_exec = Mock(spec=ExecucaoClassificacao)
            mock_exec.projeto_id = 1
            mock_obter_exec.return_value = mock_exec

            with patch.object(ClassificadorService, 'obter_projeto') as mock_obter_proj:
                mock_projeto = Mock(spec=ProjetoClassificacao)
                mock_projeto.nome = "Teste"
                mock_projeto.usuario_id = 1
                mock_obter_proj.return_value = mock_projeto

                with patch.object(ClassificadorService, 'listar_resultados') as mock_listar:
                    mock_listar.return_value = []

                    with patch.object(ExportService, 'exportar_excel') as mock_export:
                        mock_buffer = io.BytesIO(b"excel content")
                        mock_export.return_value = mock_buffer

                        result = await exportar_excel(1, mock_auth, mock_db)

                        assert result.body == b"excel content"

    @pytest.mark.asyncio
    async def test_exportar_csv_sucesso(self, mock_auth, mock_db):
        """Testa exportação CSV"""
        from sistemas.classificador_documentos.router import exportar_csv
        from sistemas.classificador_documentos.services import ClassificadorService
        from sistemas.classificador_documentos.services_export import ExportService
        from sistemas.classificador_documentos.models import ProjetoClassificacao, ExecucaoClassificacao
        import io

        with patch.object(ClassificadorService, 'obter_execucao') as mock_obter_exec:
            mock_exec = Mock(spec=ExecucaoClassificacao)
            mock_exec.projeto_id = 1
            mock_obter_exec.return_value = mock_exec

            with patch.object(ClassificadorService, 'obter_projeto') as mock_obter_proj:
                mock_projeto = Mock(spec=ProjetoClassificacao)
                mock_projeto.nome = "Teste"
                mock_projeto.usuario_id = 1
                mock_obter_proj.return_value = mock_projeto

                with patch.object(ClassificadorService, 'listar_resultados') as mock_listar:
                    mock_listar.return_value = []

                    with patch.object(ExportService, 'exportar_csv') as mock_export:
                        mock_buffer = io.StringIO("csv content")
                        mock_export.return_value = mock_buffer

                        result = await exportar_csv(1, mock_auth, mock_db)

                        assert result.body == b"csv content"


class TestClassificacaoAvulsaExtended:
    """Testes estendidos de classificação avulsa"""

    @pytest.mark.asyncio
    async def test_classificar_avulso_com_prompt_id(self, mock_auth, mock_db):
        """Testa classificação avulsa usando prompt_id"""
        from sistemas.classificador_documentos.router import classificar_documento_avulso
        from sistemas.classificador_documentos.services import ClassificadorService
        from sistemas.classificador_documentos.models import ResultadoClassificacaoDTO
        from fastapi import UploadFile

        mock_file = Mock(spec=UploadFile)
        mock_file.filename = "documento.pdf"
        mock_file.read = AsyncMock(return_value=b"fake pdf content")

        with patch.object(ClassificadorService, 'obter_prompt') as mock_obter:
            mock_prompt = Mock()
            mock_prompt.conteudo = "Classifique este documento"
            mock_obter.return_value = mock_prompt

            with patch.object(ClassificadorService, 'classificar_documento_avulso', new_callable=AsyncMock) as mock_class:
                mock_resultado = ResultadoClassificacaoDTO(
                    codigo_documento="",
                    categoria="decisao",
                    confianca="alta",
                    justificativa="Teste",
                    sucesso=True,
                    texto_via="pdf",
                    tokens_usados=500
                )
                mock_class.return_value = mock_resultado

                result = await classificar_documento_avulso(
                    arquivo=mock_file,
                    prompt_id=1,
                    prompt_texto=None,
                    modelo="google/gemini-2.5-flash-lite",
                    modo_processamento="chunk",
                    posicao_chunk="fim",
                    tamanho_chunk=512,
                    current_user=mock_auth,
                    db=mock_db
                )

                assert result["sucesso"] is True

    @pytest.mark.asyncio
    async def test_classificar_avulso_prompt_nao_encontrado(self, mock_auth, mock_db):
        """Testa classificação avulsa com prompt_id inexistente"""
        from sistemas.classificador_documentos.router import classificar_documento_avulso
        from sistemas.classificador_documentos.services import ClassificadorService
        from fastapi import UploadFile

        mock_file = Mock(spec=UploadFile)
        mock_file.filename = "documento.pdf"
        mock_file.read = AsyncMock(return_value=b"fake pdf content")

        with patch.object(ClassificadorService, 'obter_prompt') as mock_obter:
            mock_obter.return_value = None

            with pytest.raises(HTTPException) as exc_info:
                await classificar_documento_avulso(
                    arquivo=mock_file,
                    prompt_id=999,
                    prompt_texto=None,
                    modelo="google/gemini-2.5-flash-lite",
                    modo_processamento="chunk",
                    posicao_chunk="fim",
                    tamanho_chunk=512,
                    current_user=mock_auth,
                    db=mock_db
                )

            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_classificar_avulso_com_prompt_texto(self, mock_auth, mock_db):
        """Testa classificação avulsa usando prompt_texto"""
        from sistemas.classificador_documentos.router import classificar_documento_avulso
        from sistemas.classificador_documentos.services import ClassificadorService
        from sistemas.classificador_documentos.models import ResultadoClassificacaoDTO
        from fastapi import UploadFile

        mock_file = Mock(spec=UploadFile)
        mock_file.filename = "documento.pdf"
        mock_file.read = AsyncMock(return_value=b"fake pdf content")

        with patch.object(ClassificadorService, 'classificar_documento_avulso', new_callable=AsyncMock) as mock_class:
            mock_resultado = ResultadoClassificacaoDTO(
                codigo_documento="",
                categoria="decisao",
                confianca="alta",
                justificativa="Teste",
                sucesso=True,
                texto_via="pdf",
                tokens_usados=500
            )
            mock_class.return_value = mock_resultado

            result = await classificar_documento_avulso(
                arquivo=mock_file,
                prompt_id=None,
                prompt_texto="Classifique este documento",
                modelo="google/gemini-2.5-flash-lite",
                modo_processamento="chunk",
                posicao_chunk="fim",
                tamanho_chunk=512,
                current_user=mock_auth,
                db=mock_db
            )

            assert result["sucesso"] is True
