# tests/classificador_documentos/test_models.py
"""
Testes dos modelos do Sistema de Classificação de Documentos.

Testa:
- Enums
- Dataclasses
- Modelos SQLAlchemy (estrutura)

Autor: LAB/PGE-MS
"""

import pytest


class TestEnums:
    """Testes dos enums"""

    def test_status_execucao_values(self):
        """Testa valores do enum StatusExecucao"""
        from sistemas.classificador_documentos.models import StatusExecucao

        assert StatusExecucao.PENDENTE.value == "pendente"
        assert StatusExecucao.EM_ANDAMENTO.value == "em_andamento"
        assert StatusExecucao.PAUSADO.value == "pausado"
        assert StatusExecucao.CONCLUIDO.value == "concluido"
        assert StatusExecucao.ERRO.value == "erro"

    def test_status_arquivo_values(self):
        """Testa valores do enum StatusArquivo"""
        from sistemas.classificador_documentos.models import StatusArquivo

        assert StatusArquivo.PENDENTE.value == "pendente"
        assert StatusArquivo.PROCESSANDO.value == "processando"
        assert StatusArquivo.CONCLUIDO.value == "concluido"
        assert StatusArquivo.ERRO.value == "erro"

    def test_fonte_documento_values(self):
        """Testa valores do enum FonteDocumento"""
        from sistemas.classificador_documentos.models import FonteDocumento

        assert FonteDocumento.UPLOAD.value == "upload"
        assert FonteDocumento.TJMS.value == "tjms"

    def test_nivel_confianca_values(self):
        """Testa valores do enum NivelConfianca"""
        from sistemas.classificador_documentos.models import NivelConfianca

        assert NivelConfianca.ALTA.value == "alta"
        assert NivelConfianca.MEDIA.value == "media"
        assert NivelConfianca.BAIXA.value == "baixa"


class TestDataclasses:
    """Testes das dataclasses"""

    def test_documento_para_classificar(self):
        """Testa DocumentoParaClassificar"""
        from sistemas.classificador_documentos.models import (
            DocumentoParaClassificar, FonteDocumento
        )

        doc = DocumentoParaClassificar(
            codigo="123456",
            numero_processo="0800001-00.2024.8.12.0001",
            nome_arquivo="documento.pdf",
            fonte=FonteDocumento.TJMS,
            texto_extraido="Texto do documento",
            texto_via_ocr=False,
            tokens_total=500
        )

        assert doc.codigo == "123456"
        assert doc.numero_processo == "0800001-00.2024.8.12.0001"
        assert doc.fonte == FonteDocumento.TJMS
        assert doc.texto_via_ocr is False
        assert doc.tokens_total == 500
        assert doc.erro is None

    def test_documento_para_classificar_defaults(self):
        """Testa valores padrão de DocumentoParaClassificar"""
        from sistemas.classificador_documentos.models import (
            DocumentoParaClassificar, FonteDocumento
        )

        doc = DocumentoParaClassificar(codigo="123")

        assert doc.numero_processo is None
        assert doc.nome_arquivo is None
        assert doc.fonte == FonteDocumento.TJMS
        assert doc.texto_extraido is None
        assert doc.texto_via_ocr is False
        assert doc.tokens_total == 0
        assert doc.erro is None

    def test_resultado_classificacao_dto(self):
        """Testa ResultadoClassificacaoDTO"""
        from sistemas.classificador_documentos.models import ResultadoClassificacaoDTO

        resultado = ResultadoClassificacaoDTO(
            codigo_documento="123",
            numero_processo="0800001-00.2024.8.12.0001",
            categoria="decisao",
            subcategoria="deferida",
            confianca="alta",
            justificativa="Decisão deferitória",
            sucesso=True,
            texto_via="pdf",
            tokens_usados=500
        )

        assert resultado.codigo_documento == "123"
        assert resultado.categoria == "decisao"
        assert resultado.confianca == "alta"
        assert resultado.sucesso is True
        assert resultado.erro is None

    def test_resultado_classificacao_dto_to_dict(self):
        """Testa conversão para dicionário"""
        from sistemas.classificador_documentos.models import ResultadoClassificacaoDTO

        resultado = ResultadoClassificacaoDTO(
            codigo_documento="123",
            categoria="teste",
            confianca="media",
            justificativa="Justificativa",
            sucesso=True,
            texto_via="ocr",
            tokens_usados=200
        )

        d = resultado.to_dict()

        assert d["codigo_documento"] == "123"
        assert d["categoria"] == "teste"
        assert d["confianca"] == "media"
        assert d["sucesso"] is True
        assert d["texto_via"] == "ocr"
        assert d["tokens_usados"] == 200


class TestSQLAlchemyModels:
    """Testes estruturais dos modelos SQLAlchemy"""

    def test_projeto_classificacao_tablename(self):
        """Testa nome da tabela ProjetoClassificacao"""
        from sistemas.classificador_documentos.models import ProjetoClassificacao

        assert ProjetoClassificacao.__tablename__ == "projetos_classificacao"

    def test_codigo_documento_projeto_tablename(self):
        """Testa nome da tabela CodigoDocumentoProjeto"""
        from sistemas.classificador_documentos.models import CodigoDocumentoProjeto

        assert CodigoDocumentoProjeto.__tablename__ == "codigos_documento_projeto"

    def test_execucao_classificacao_tablename(self):
        """Testa nome da tabela ExecucaoClassificacao"""
        from sistemas.classificador_documentos.models import ExecucaoClassificacao

        assert ExecucaoClassificacao.__tablename__ == "execucoes_classificacao"

    def test_resultado_classificacao_tablename(self):
        """Testa nome da tabela ResultadoClassificacao"""
        from sistemas.classificador_documentos.models import ResultadoClassificacao

        assert ResultadoClassificacao.__tablename__ == "resultados_classificacao"

    def test_prompt_classificacao_tablename(self):
        """Testa nome da tabela PromptClassificacao"""
        from sistemas.classificador_documentos.models import PromptClassificacao

        assert PromptClassificacao.__tablename__ == "prompts_classificacao"

    def test_log_classificacao_ia_tablename(self):
        """Testa nome da tabela LogClassificacaoIA"""
        from sistemas.classificador_documentos.models import LogClassificacaoIA

        assert LogClassificacaoIA.__tablename__ == "logs_classificacao_ia"

    def test_execucao_progresso_percentual(self):
        """Testa cálculo de progresso percentual"""
        from sistemas.classificador_documentos.models import ExecucaoClassificacao

        execucao = ExecucaoClassificacao()
        execucao.total_arquivos = 100
        execucao.arquivos_processados = 50

        assert execucao.progresso_percentual == 50.0

    def test_execucao_progresso_percentual_zero_total(self):
        """Testa progresso com total zero"""
        from sistemas.classificador_documentos.models import ExecucaoClassificacao

        execucao = ExecucaoClassificacao()
        execucao.total_arquivos = 0
        execucao.arquivos_processados = 0

        assert execucao.progresso_percentual == 0.0
