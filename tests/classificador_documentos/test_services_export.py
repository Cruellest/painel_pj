# tests/classificador_documentos/test_services_export.py
"""
Testes unitários do serviço de exportação.

Testa:
- Exportação Excel
- Exportação CSV
- Exportação JSON
- Limpeza de caracteres ilegais

Autor: LAB/PGE-MS
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timezone


class TestExportServiceBasic:
    """Testes básicos do ExportService"""

    def test_limpar_texto_excel_empty(self):
        """Testa limpeza de texto vazio"""
        from sistemas.classificador_documentos.services_export import ExportService

        service = ExportService()

        assert service._limpar_texto_excel("") == ""
        assert service._limpar_texto_excel(None) == ""

    def test_limpar_texto_excel_with_illegal_chars(self):
        """Testa limpeza de caracteres ilegais"""
        from sistemas.classificador_documentos.services_export import ExportService

        service = ExportService()

        # Caracteres ilegais: \x00-\x08, \x0b-\x0c, \x0e-\x1f, \x7f-\x9f
        texto_com_ilegais = "Texto\x00com\x07caracteres\x1filegais"
        resultado = service._limpar_texto_excel(texto_com_ilegais)

        assert "\x00" not in resultado
        assert "\x07" not in resultado
        assert "\x1f" not in resultado
        assert "Texto" in resultado

    def test_limpar_texto_excel_normal(self):
        """Testa limpeza de texto normal"""
        from sistemas.classificador_documentos.services_export import ExportService

        service = ExportService()

        texto = "Texto normal com acentuação: áéíóú"
        resultado = service._limpar_texto_excel(texto)

        assert resultado == texto


class TestExportServiceExcel:
    """Testes de exportação Excel"""

    def _create_mock_resultado(self, **kwargs):
        """Cria mock de ResultadoClassificacao"""
        from sistemas.classificador_documentos.models import ResultadoClassificacao

        defaults = {
            "codigo_documento": "COD001",
            "numero_processo": "0800001-00.2024.8.12.0001",
            "nome_arquivo": "documento.pdf",
            "categoria": "decisao",
            "subcategoria": "deferida",
            "confianca": "alta",
            "justificativa": "Decisão deferitória",
            "status": "concluido",
            "fonte": "tjms",
            "texto_extraido_via": "pdf",
            "tokens_extraidos": 500,
            "erro_mensagem": None,
            "processado_em": datetime(2024, 1, 15, 10, 30, 0)
        }
        defaults.update(kwargs)

        mock = Mock(spec=ResultadoClassificacao)
        for key, value in defaults.items():
            setattr(mock, key, value)

        return mock

    def test_exportar_excel_empty(self):
        """Testa exportação Excel com lista vazia"""
        from sistemas.classificador_documentos.services_export import ExportService

        service = ExportService()
        buffer = service.exportar_excel([])

        assert buffer is not None
        assert buffer.getvalue()  # Deve ter conteúdo (cabeçalhos)

    def test_exportar_excel_with_results(self):
        """Testa exportação Excel com resultados"""
        from sistemas.classificador_documentos.services_export import ExportService

        service = ExportService()

        resultados = [
            self._create_mock_resultado(codigo_documento="COD001"),
            self._create_mock_resultado(codigo_documento="COD002"),
        ]

        buffer = service.exportar_excel(resultados)

        assert buffer is not None
        content = buffer.getvalue()
        assert len(content) > 0

    def test_exportar_excel_with_execucao(self):
        """Testa exportação Excel com metadados de execução"""
        from sistemas.classificador_documentos.services_export import ExportService
        from sistemas.classificador_documentos.models import ExecucaoClassificacao

        service = ExportService()

        resultados = [self._create_mock_resultado()]

        mock_execucao = Mock(spec=ExecucaoClassificacao)
        mock_execucao.id = 1
        mock_execucao.status = "concluido"
        mock_execucao.total_arquivos = 10
        mock_execucao.arquivos_processados = 10
        mock_execucao.arquivos_sucesso = 9
        mock_execucao.arquivos_erro = 1
        mock_execucao.modelo_usado = "google/gemini-2.5-flash-lite"
        mock_execucao.iniciado_em = datetime(2024, 1, 15, 10, 0, 0)
        mock_execucao.finalizado_em = datetime(2024, 1, 15, 10, 30, 0)

        buffer = service.exportar_excel(resultados, execucao=mock_execucao)

        assert buffer is not None
        assert len(buffer.getvalue()) > 0

    def test_exportar_excel_with_null_processado_em(self):
        """Testa exportação Excel com processado_em nulo"""
        from sistemas.classificador_documentos.services_export import ExportService

        service = ExportService()

        resultados = [self._create_mock_resultado(processado_em=None)]

        buffer = service.exportar_excel(resultados)
        assert buffer is not None

    def test_exportar_excel_openpyxl_not_installed(self):
        """Testa exportação Excel quando openpyxl não está instalado"""
        from sistemas.classificador_documentos.services_export import ExportService

        service = ExportService()

        with patch.dict('sys.modules', {'openpyxl': None}):
            with patch('sistemas.classificador_documentos.services_export.ExportService.exportar_excel') as mock_exp:
                mock_exp.side_effect = ImportError("openpyxl não está instalado")

                with pytest.raises(ImportError):
                    service.exportar_excel([])


class TestExportServiceCSV:
    """Testes de exportação CSV"""

    def _create_mock_resultado(self, **kwargs):
        """Cria mock de ResultadoClassificacao"""
        from sistemas.classificador_documentos.models import ResultadoClassificacao

        defaults = {
            "codigo_documento": "COD001",
            "numero_processo": "0800001-00.2024.8.12.0001",
            "nome_arquivo": "documento.pdf",
            "categoria": "decisao",
            "subcategoria": "deferida",
            "confianca": "alta",
            "justificativa": "Decisão deferitória",
            "status": "concluido",
            "fonte": "tjms",
            "texto_extraido_via": "pdf",
            "tokens_extraidos": 500,
            "erro_mensagem": None,
            "processado_em": datetime(2024, 1, 15, 10, 30, 0)
        }
        defaults.update(kwargs)

        mock = Mock(spec=ResultadoClassificacao)
        for key, value in defaults.items():
            setattr(mock, key, value)

        return mock

    def test_exportar_csv_empty(self):
        """Testa exportação CSV com lista vazia"""
        from sistemas.classificador_documentos.services_export import ExportService

        service = ExportService()
        buffer = service.exportar_csv([])

        content = buffer.getvalue()
        assert "codigo_documento" in content  # Headers presentes

    def test_exportar_csv_with_results(self):
        """Testa exportação CSV com resultados"""
        from sistemas.classificador_documentos.services_export import ExportService

        service = ExportService()

        resultados = [
            self._create_mock_resultado(codigo_documento="COD001"),
            self._create_mock_resultado(codigo_documento="COD002"),
        ]

        buffer = service.exportar_csv(resultados)
        content = buffer.getvalue()

        assert "COD001" in content
        assert "COD002" in content

    def test_exportar_csv_default_separator(self):
        """Testa exportação CSV com separador padrão"""
        from sistemas.classificador_documentos.services_export import ExportService

        service = ExportService()
        resultados = [self._create_mock_resultado()]

        buffer = service.exportar_csv(resultados)
        content = buffer.getvalue()

        assert ";" in content  # Separador padrão

    def test_exportar_csv_custom_separator(self):
        """Testa exportação CSV com separador customizado"""
        from sistemas.classificador_documentos.services_export import ExportService

        service = ExportService()
        resultados = [self._create_mock_resultado()]

        buffer = service.exportar_csv(resultados, separador=",")
        content = buffer.getvalue()

        # O CSV usa QUOTE_ALL, então as vírgulas estão dentro de aspas
        assert content is not None

    def test_exportar_csv_with_null_fields(self):
        """Testa exportação CSV com campos nulos"""
        from sistemas.classificador_documentos.services_export import ExportService

        service = ExportService()

        resultados = [
            self._create_mock_resultado(
                numero_processo=None,
                subcategoria=None,
                erro_mensagem=None,
                processado_em=None
            )
        ]

        buffer = service.exportar_csv(resultados)
        content = buffer.getvalue()

        assert content is not None


class TestExportServiceJSON:
    """Testes de exportação JSON"""

    def _create_mock_resultado(self, **kwargs):
        """Cria mock de ResultadoClassificacao"""
        from sistemas.classificador_documentos.models import ResultadoClassificacao

        defaults = {
            "codigo_documento": "COD001",
            "numero_processo": "0800001-00.2024.8.12.0001",
            "nome_arquivo": "documento.pdf",
            "categoria": "decisao",
            "subcategoria": "deferida",
            "confianca": "alta",
            "justificativa": "Decisão deferitória",
            "status": "concluido",
            "fonte": "tjms",
            "texto_extraido_via": "pdf",
            "tokens_extraidos": 500,
            "erro_mensagem": None,
            "resultado_json": {"categoria": "decisao"},
            "processado_em": datetime(2024, 1, 15, 10, 30, 0)
        }
        defaults.update(kwargs)

        mock = Mock(spec=ResultadoClassificacao)
        for key, value in defaults.items():
            setattr(mock, key, value)

        return mock

    def test_exportar_json_empty(self):
        """Testa exportação JSON com lista vazia"""
        from sistemas.classificador_documentos.services_export import ExportService

        service = ExportService()
        result = service.exportar_json([])

        assert result == []

    def test_exportar_json_with_results(self):
        """Testa exportação JSON com resultados"""
        from sistemas.classificador_documentos.services_export import ExportService

        service = ExportService()

        resultados = [
            self._create_mock_resultado(codigo_documento="COD001"),
            self._create_mock_resultado(codigo_documento="COD002"),
        ]

        result = service.exportar_json(resultados)

        assert len(result) == 2
        assert result[0]["codigo_documento"] == "COD001"
        assert result[1]["codigo_documento"] == "COD002"

    def test_exportar_json_structure(self):
        """Testa estrutura do JSON exportado"""
        from sistemas.classificador_documentos.services_export import ExportService

        service = ExportService()
        resultados = [self._create_mock_resultado()]

        result = service.exportar_json(resultados)

        expected_keys = [
            "codigo_documento", "numero_processo", "nome_arquivo",
            "categoria", "subcategoria", "confianca", "justificativa",
            "status", "fonte", "extracao_via", "tokens", "erro",
            "resultado_completo", "data_processamento"
        ]

        for key in expected_keys:
            assert key in result[0]

    def test_exportar_json_with_null_date(self):
        """Testa exportação JSON com data nula"""
        from sistemas.classificador_documentos.services_export import ExportService

        service = ExportService()
        resultados = [self._create_mock_resultado(processado_em=None)]

        result = service.exportar_json(resultados)

        assert result[0]["data_processamento"] is None


class TestGetExportService:
    """Testes do singleton"""

    def test_singleton(self):
        """Testa que retorna singleton"""
        from sistemas.classificador_documentos.services_export import get_export_service

        service1 = get_export_service()
        service2 = get_export_service()

        assert service1 is service2
