# tests/classificador_documentos/test_services_extraction.py
"""
Testes unitários do serviço de extração de texto.

Testa:
- Extração de texto de PDFs
- Fallback para OCR
- Normalização de texto
- Extração de chunks
- Contagem de tokens

Autor: LAB/PGE-MS
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import io


class TestTextExtractor:
    """Testes do TextExtractor"""

    def test_init_default(self):
        """Testa inicialização com valores padrão"""
        from sistemas.classificador_documentos.services_extraction import TextExtractor

        extractor = TextExtractor()
        assert extractor.use_normalizer is True
        assert extractor._normalizer is None
        assert extractor._tiktoken_encoding is None

    def test_init_without_normalizer(self):
        """Testa inicialização sem normalizer"""
        from sistemas.classificador_documentos.services_extraction import TextExtractor

        extractor = TextExtractor(use_normalizer=False)
        assert extractor.use_normalizer is False

    def test_contar_tokens_empty(self):
        """Testa contagem de tokens com texto vazio"""
        from sistemas.classificador_documentos.services_extraction import TextExtractor

        extractor = TextExtractor()
        assert extractor.contar_tokens("") == 0
        assert extractor.contar_tokens(None) == 0

    def test_contar_tokens_with_tiktoken(self):
        """Testa contagem de tokens com tiktoken disponível"""
        from sistemas.classificador_documentos.services_extraction import TextExtractor

        extractor = TextExtractor()
        texto = "Este é um texto de exemplo para testar a contagem de tokens."

        # Tenta usar tiktoken se disponível
        try:
            import tiktoken
            tokens = extractor.contar_tokens(texto)
            assert tokens > 0
            assert isinstance(tokens, (int, float))
        except ImportError:
            # Se tiktoken não está disponível, usa fallback
            tokens = extractor.contar_tokens(texto)
            assert tokens > 0

    def test_extrair_chunk_inicio(self):
        """Testa extração de chunk do início"""
        from sistemas.classificador_documentos.services_extraction import TextExtractor

        extractor = TextExtractor()
        texto = "Palavra1 palavra2 palavra3 palavra4 palavra5 " * 100  # Texto longo

        chunk = extractor.extrair_chunk(texto, 10, "inicio")
        assert len(chunk) > 0
        assert chunk != texto  # Deve ser menor que o original
        assert texto.startswith(chunk[:20])  # Deve começar com o mesmo texto

    def test_extrair_chunk_fim(self):
        """Testa extração de chunk do fim"""
        from sistemas.classificador_documentos.services_extraction import TextExtractor

        extractor = TextExtractor()
        texto = "Palavra1 palavra2 palavra3 palavra4 palavra5 " * 100

        chunk = extractor.extrair_chunk(texto, 10, "fim")
        assert len(chunk) > 0
        assert chunk != texto

    def test_extrair_chunk_empty(self):
        """Testa extração de chunk com texto vazio"""
        from sistemas.classificador_documentos.services_extraction import TextExtractor

        extractor = TextExtractor()
        assert extractor.extrair_chunk("", 100, "inicio") == ""
        assert extractor.extrair_chunk("", 100, "fim") == ""

    @patch('sistemas.classificador_documentos.services_extraction.TextExtractor._extrair_com_pymupdf')
    def test_extrair_texto_success(self, mock_pymupdf):
        """Testa extração de texto com sucesso via PyMuPDF"""
        from sistemas.classificador_documentos.services_extraction import TextExtractor

        mock_pymupdf.return_value = ("Texto extraído do PDF com sucesso. " * 10, 5)

        extractor = TextExtractor(use_normalizer=False)
        result = extractor.extrair_texto(b"fake pdf bytes")

        assert result.texto != ""
        assert result.via_ocr is False
        assert result.paginas_processadas == 5
        assert result.erro is None

    @patch('sistemas.classificador_documentos.services_extraction.TextExtractor._extrair_com_pymupdf')
    @patch('sistemas.classificador_documentos.services_extraction.TextExtractor._extrair_com_ocr')
    def test_extrair_texto_fallback_ocr(self, mock_ocr, mock_pymupdf):
        """Testa fallback para OCR quando PyMuPDF retorna vazio"""
        from sistemas.classificador_documentos.services_extraction import TextExtractor

        # PyMuPDF retorna vazio
        mock_pymupdf.return_value = ("", 5)
        # OCR retorna texto
        mock_ocr.return_value = ("Texto extraído via OCR com sucesso. " * 10, 5, None)

        extractor = TextExtractor(use_normalizer=False)
        result = extractor.extrair_texto(b"fake pdf bytes")

        assert result.texto != ""
        assert result.via_ocr is True
        mock_ocr.assert_called_once()

    @patch('sistemas.classificador_documentos.services_extraction.TextExtractor._extrair_com_pymupdf')
    def test_extrair_texto_empty_pdf(self, mock_pymupdf):
        """Testa extração de PDF sem texto"""
        from sistemas.classificador_documentos.services_extraction import TextExtractor

        mock_pymupdf.return_value = ("", 0)

        extractor = TextExtractor(use_normalizer=False)
        result = extractor.extrair_texto(b"fake pdf bytes")

        # Resultado pode ser vazio ou via OCR
        assert result.erro is None or result.texto == ""


class TestExtractionIntegration:
    """Testes de integração do serviço de extração"""

    def test_get_text_extractor_singleton(self):
        """Testa que get_text_extractor retorna singleton"""
        from sistemas.classificador_documentos.services_extraction import get_text_extractor

        extractor1 = get_text_extractor()
        extractor2 = get_text_extractor()

        assert extractor1 is extractor2

    def test_extraction_result_dataclass(self):
        """Testa dataclass ExtractionResult"""
        from sistemas.classificador_documentos.services_extraction import ExtractionResult

        result = ExtractionResult(
            texto="Texto de teste",
            via_ocr=False,
            tokens_total=10,
            paginas_processadas=2,
            erro=None
        )

        assert result.texto == "Texto de teste"
        assert result.via_ocr is False
        assert result.tokens_total == 10
        assert result.paginas_processadas == 2
        assert result.erro is None
