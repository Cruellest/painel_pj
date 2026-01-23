# tests/test_relatorio_cumprimento.py
"""
Testes para o Sistema de Relatorio de Cumprimento de Sentenca

Cobertura:
- Modelos de dados
- Services
- Router/endpoints
- Seed config
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date
import json

from sistemas.relatorio_cumprimento.models import (
    CategoriaDocumento,
    StatusProcessamento,
    DocumentoClassificado,
    DadosProcesso,
    InfoTransitoJulgado,
    ResultadoColeta,
    ResultadoRelatorio,
    GeracaoRelatorioCumprimento,
    LogChamadaIARelatorioCumprimento,
    FeedbackRelatorioCumprimento
)
from sistemas.relatorio_cumprimento.seed_config import (
    SISTEMA,
    PROMPTS,
    CONFIGURACOES,
    seed_prompts,
    seed_configuracoes,
    seed_all
)


# ============================================
# Testes de Modelos (Dataclasses)
# ============================================

class TestDocumentoClassificado:
    """Testes para o modelo DocumentoClassificado"""

    def test_criar_documento_classificado(self):
        """Testa criacao de documento classificado"""
        doc = DocumentoClassificado(
            id_documento="12345",
            categoria=CategoriaDocumento.SENTENCA,
            nome_original="Sentenca",
            nome_padronizado="02_sentenca_01.pdf",
            processo_origem="principal"
        )

        assert doc.id_documento == "12345"
        assert doc.categoria == CategoriaDocumento.SENTENCA
        assert doc.nome_padronizado == "02_sentenca_01.pdf"

    def test_documento_to_dict(self):
        """Testa conversao para dicionario"""
        doc = DocumentoClassificado(
            id_documento="12345",
            categoria=CategoriaDocumento.ACORDAO,
            nome_original="Acordao",
            nome_padronizado="03_acordao_01.pdf",
            data_documento=date(2024, 1, 15)
        )

        d = doc.to_dict()

        assert d["id_documento"] == "12345"
        assert d["categoria"] == "acordao"
        assert d["data_documento"] == "15/01/2024"


class TestDadosProcesso:
    """Testes para o modelo DadosProcesso"""

    def test_criar_dados_processo(self):
        """Testa criacao de dados do processo"""
        dados = DadosProcesso(
            numero_processo="08012345678901234560001",
            numero_processo_formatado="0801234-56.7890.1.23.4560",
            autor="Joao Silva",
            cpf_cnpj_autor="123.456.789-00",
            comarca="Campo Grande",
            vara="1a Vara da Fazenda"
        )

        assert dados.numero_processo == "08012345678901234560001"
        assert dados.autor == "Joao Silva"
        assert dados.reu == "Estado de Mato Grosso do Sul"

    def test_dados_to_dict(self):
        """Testa conversao para dicionario"""
        dados = DadosProcesso(
            numero_processo="08012345678901234560001",
            autor="Maria Santos",
            data_ajuizamento=date(2023, 6, 10),
            valor_causa=50000.00
        )

        d = dados.to_dict()

        assert d["autor"] == "Maria Santos"
        assert d["data_ajuizamento"] == "10/06/2023"
        assert d["valor_causa"] == 50000.00


class TestInfoTransitoJulgado:
    """Testes para o modelo InfoTransitoJulgado"""

    def test_transito_localizado(self):
        """Testa info de transito localizado"""
        info = InfoTransitoJulgado(
            localizado=True,
            data_transito=date(2024, 3, 20),
            fonte="certidao",
            id_documento="99999"
        )

        assert info.localizado is True
        assert info.fonte == "certidao"

    def test_transito_nao_localizado(self):
        """Testa info de transito nao localizado"""
        info = InfoTransitoJulgado(
            localizado=False,
            observacao="Nao foi possivel identificar"
        )

        assert info.localizado is False
        assert "possivel identificar" in info.observacao

    def test_transito_to_dict(self):
        """Testa conversao para dicionario"""
        info = InfoTransitoJulgado(
            localizado=True,
            data_transito=date(2024, 3, 20),
            fonte="movimento"
        )

        d = info.to_dict()

        assert d["localizado"] is True
        assert d["data_transito"] == "20/03/2024"
        assert d["fonte"] == "movimento"


class TestResultadoColeta:
    """Testes para o modelo ResultadoColeta"""

    def test_resultado_completo(self):
        """Testa resultado de coleta completo"""
        dados_cumprimento = DadosProcesso(
            numero_processo="08012345678901234560001",
            autor="Teste"
        )
        dados_principal = DadosProcesso(
            numero_processo="08012345678901234560000",
            autor="Teste"
        )
        doc = DocumentoClassificado(
            id_documento="123",
            categoria=CategoriaDocumento.SENTENCA,
            nome_original="Sentenca",
            nome_padronizado="sentenca.pdf"
        )
        transito = InfoTransitoJulgado(localizado=True)

        resultado = ResultadoColeta(
            dados_cumprimento=dados_cumprimento,
            dados_principal=dados_principal,
            documentos=[doc],
            transito_julgado=transito
        )

        d = resultado.to_dict()

        assert "dados_cumprimento" in d
        assert "dados_principal" in d
        assert len(d["documentos"]) == 1
        assert d["transito_julgado"]["localizado"] is True


# ============================================
# Testes de Enums
# ============================================

class TestEnums:
    """Testes para os enums do sistema"""

    def test_categoria_documento_valores(self):
        """Testa valores do enum CategoriaDocumento"""
        assert CategoriaDocumento.PETICAO_INICIAL_CUMPRIMENTO.value == "peticao_inicial_cumprimento"
        assert CategoriaDocumento.SENTENCA.value == "sentenca"
        assert CategoriaDocumento.ACORDAO.value == "acordao"
        assert CategoriaDocumento.CERTIDAO_TRANSITO.value == "certidao_transito"

    def test_status_processamento_valores(self):
        """Testa valores do enum StatusProcessamento"""
        assert StatusProcessamento.INICIADO.value == "iniciado"
        assert StatusProcessamento.BAIXANDO_DOCUMENTOS.value == "baixando_documentos"
        assert StatusProcessamento.ANALISANDO.value == "analisando"
        assert StatusProcessamento.GERANDO_RELATORIO.value == "gerando_relatorio"
        assert StatusProcessamento.CONCLUIDO.value == "concluido"
        assert StatusProcessamento.ERRO.value == "erro"


# ============================================
# Testes de Seed Config
# ============================================

class TestSeedConfig:
    """Testes para o seed_config do sistema"""

    def test_sistema_correto(self):
        """Testa que o nome do sistema esta correto"""
        assert SISTEMA == "relatorio_cumprimento"

    def test_prompts_definidos(self):
        """Testa que prompts estao definidos"""
        assert len(PROMPTS) >= 2

        tipos = [p["tipo"] for p in PROMPTS]
        assert "geracao_relatorio" in tipos
        assert "edicao_relatorio" in tipos

    def test_prompt_geracao_completo(self):
        """Testa que o prompt de geracao esta completo"""
        prompt_geracao = next(p for p in PROMPTS if p["tipo"] == "geracao_relatorio")

        assert "nome" in prompt_geracao
        assert "descricao" in prompt_geracao
        assert "conteudo" in prompt_geracao
        assert len(prompt_geracao["conteudo"]) > 100

    def test_configuracoes_definidas(self):
        """Testa que configuracoes estao definidas"""
        assert len(CONFIGURACOES) >= 3

        chaves = [c["chave"] for c in CONFIGURACOES]
        assert "modelo_analise" in chaves
        assert "temperatura_analise" in chaves
        assert "thinking_level" in chaves

    def test_configuracao_modelo_padrao(self):
        """Testa modelo padrao configurado"""
        config_modelo = next(c for c in CONFIGURACOES if c["chave"] == "modelo_analise")

        assert "gemini" in config_modelo["valor"].lower() or "flash" in config_modelo["valor"].lower()

    def test_seed_prompts_nao_duplica(self):
        """Testa que seed_prompts nao duplica entradas existentes"""
        # Mock do banco de dados
        mock_db = MagicMock()

        # Simula prompt ja existente
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = MagicMock()  # Prompt ja existe

        seed_prompts(mock_db)

        # Nao deve ter adicionado nada
        mock_db.add.assert_not_called()

    def test_seed_configuracoes_nao_duplica(self):
        """Testa que seed_configuracoes nao duplica entradas existentes"""
        mock_db = MagicMock()

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = MagicMock()  # Config ja existe

        seed_configuracoes(mock_db)

        mock_db.add.assert_not_called()


# ============================================
# Testes de Modelos SQLAlchemy (estrutura)
# ============================================

class TestModelosSQLAlchemy:
    """Testes para estrutura dos modelos SQLAlchemy"""

    def test_geracao_relatorio_campos(self):
        """Testa que GeracaoRelatorioCumprimento tem campos necessarios"""
        # Verifica que os campos estao definidos
        assert hasattr(GeracaoRelatorioCumprimento, 'numero_cumprimento')
        assert hasattr(GeracaoRelatorioCumprimento, 'numero_principal')
        assert hasattr(GeracaoRelatorioCumprimento, 'conteudo_gerado')
        assert hasattr(GeracaoRelatorioCumprimento, 'status')
        assert hasattr(GeracaoRelatorioCumprimento, 'modelo_usado')

    def test_log_chamada_ia_campos(self):
        """Testa que LogChamadaIARelatorioCumprimento tem campos necessarios"""
        assert hasattr(LogChamadaIARelatorioCumprimento, 'geracao_id')
        assert hasattr(LogChamadaIARelatorioCumprimento, 'etapa')
        assert hasattr(LogChamadaIARelatorioCumprimento, 'prompt_enviado')
        assert hasattr(LogChamadaIARelatorioCumprimento, 'resposta_ia')

    def test_feedback_campos(self):
        """Testa que FeedbackRelatorioCumprimento tem campos necessarios"""
        assert hasattr(FeedbackRelatorioCumprimento, 'geracao_id')
        assert hasattr(FeedbackRelatorioCumprimento, 'avaliacao')
        assert hasattr(FeedbackRelatorioCumprimento, 'nota')


# ============================================
# Testes de Integracao (Router)
# ============================================

class TestRouterIntegracao:
    """Testes de integracao com router (requer app)"""

    @pytest.fixture
    def mock_db(self):
        """Fixture para mock do banco de dados"""
        return MagicMock()

    @pytest.fixture
    def mock_user(self):
        """Fixture para mock do usuario"""
        user = MagicMock()
        user.id = 1
        user.username = "test_user"
        return user

    def test_processar_request_model(self):
        """Testa modelo de request do processamento"""
        from sistemas.relatorio_cumprimento.router import ProcessarRequest

        req = ProcessarRequest(
            numero_cnj="08012345678901234560001",
            sobrescrever_existente=False
        )

        assert req.numero_cnj == "08012345678901234560001"
        assert req.sobrescrever_existente is False

    def test_exportar_docx_request_model(self):
        """Testa modelo de request da exportacao DOCX"""
        from sistemas.relatorio_cumprimento.router import ExportarDocxRequest

        req = ExportarDocxRequest(
            markdown="# Teste\n\nConteudo",
            numero_processo="0801234567890"
        )

        assert "Teste" in req.markdown
        assert req.numero_processo == "0801234567890"

    def test_feedback_request_model(self):
        """Testa modelo de request do feedback"""
        from sistemas.relatorio_cumprimento.router import FeedbackRequest

        req = FeedbackRequest(
            geracao_id=1,
            avaliacao="correto",
            nota=5,
            comentario="Muito bom"
        )

        assert req.geracao_id == 1
        assert req.avaliacao == "correto"
        assert req.nota == 5


# ============================================
# Testes de Service
# ============================================

class TestRelatorioCumprimentoService:
    """Testes para o servico principal"""

    @pytest.fixture
    def mock_db(self):
        """Fixture para mock do banco de dados"""
        db = MagicMock()

        # Mock para configuracoes
        def mock_config_filter(*args, **kwargs):
            config_mock = MagicMock()
            config_mock.first.return_value = None
            return config_mock

        db.query.return_value.filter.side_effect = mock_config_filter

        return db

    def test_localizar_transito_julgado_por_movimento(self, mock_db):
        """Testa localizacao de transito via movimento"""
        from sistemas.relatorio_cumprimento.services import RelatorioCumprimentoService

        service = RelatorioCumprimentoService(mock_db)

        # Mock de movimentos com transito
        movimentos = MagicMock()
        movimentos.transito_julgado = date(2024, 3, 15)

        documentos = []

        info = service.localizar_transito_julgado(movimentos, documentos)

        assert info.localizado is True
        assert info.data_transito == date(2024, 3, 15)
        assert info.fonte == "movimento"

    def test_localizar_transito_julgado_por_certidao(self, mock_db):
        """Testa localizacao de transito via certidao"""
        from sistemas.relatorio_cumprimento.services import RelatorioCumprimentoService

        service = RelatorioCumprimentoService(mock_db)

        # Mock sem transito nos movimentos
        movimentos = MagicMock()
        movimentos.transito_julgado = None

        # Documento de certidao
        doc = DocumentoClassificado(
            id_documento="99999",
            categoria=CategoriaDocumento.CERTIDAO_TRANSITO,
            nome_original="Certidao Transito",
            nome_padronizado="certidao.pdf"
        )

        info = service.localizar_transito_julgado(movimentos, [doc])

        assert info.localizado is True
        assert info.fonte == "certidao"
        assert info.id_documento == "99999"

    def test_localizar_transito_julgado_nao_encontrado(self, mock_db):
        """Testa quando transito nao e encontrado"""
        from sistemas.relatorio_cumprimento.services import RelatorioCumprimentoService

        service = RelatorioCumprimentoService(mock_db)

        movimentos = MagicMock()
        movimentos.transito_julgado = None

        info = service.localizar_transito_julgado(movimentos, [])

        assert info.localizado is False
        assert "identificar" in info.observacao.lower()


# ============================================
# Testes de Consistencia
# ============================================

class TestConsistencia:
    """Testes de consistencia do sistema"""

    def test_prompt_usa_variaveis_corretas(self):
        """Testa que prompts usam variaveis esperadas"""
        prompt_geracao = next(p for p in PROMPTS if p["tipo"] == "geracao_relatorio")

        # Deve conter placeholders
        assert "{dados_json}" in prompt_geracao["conteudo"]
        assert "{documentos}" in prompt_geracao["conteudo"]

    def test_prompt_edicao_usa_variaveis_corretas(self):
        """Testa que prompt de edicao usa variaveis esperadas"""
        prompt_edicao = next(p for p in PROMPTS if p["tipo"] == "edicao_relatorio")

        assert "{mensagem_usuario}" in prompt_edicao["conteudo"]
        assert "{relatorio_markdown}" in prompt_edicao["conteudo"]

    def test_temperatura_valida(self):
        """Testa que temperatura esta em range valido"""
        config_temp = next(c for c in CONFIGURACOES if c["chave"] == "temperatura_analise")

        temp = float(config_temp["valor"])
        assert 0.0 <= temp <= 1.0

    def test_thinking_level_valido(self):
        """Testa que thinking level e valido"""
        config_thinking = next(c for c in CONFIGURACOES if c["chave"] == "thinking_level")

        assert config_thinking["valor"] in ["minimal", "low", "medium", "high"]


# ============================================
# Testes de Importacao
# ============================================

class TestImportacao:
    """Testes de importacao dos modulos"""

    def test_importa_models(self):
        """Testa que models pode ser importado"""
        from sistemas.relatorio_cumprimento import models
        assert models is not None

    def test_importa_services(self):
        """Testa que services pode ser importado"""
        from sistemas.relatorio_cumprimento import services
        assert services is not None

    def test_importa_router(self):
        """Testa que router pode ser importado"""
        from sistemas.relatorio_cumprimento import router
        assert router is not None

    def test_importa_seed_config(self):
        """Testa que seed_config pode ser importado"""
        from sistemas.relatorio_cumprimento import seed_config
        assert seed_config is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
