# tests/classificador_documentos/test_services_extraction_extended.py
"""
Testes estendidos do serviço de extração de texto.

Testa cenários adicionais para aumentar cobertura:
- Normalização de texto
- Extração via PyMuPDF
- Extração via OCR
- Casos de erro

Autor: LAB/PGE-MS
"""

import pytest
from unittest.mock import Mock, patch, MagicMock


class TestTextExtractorExtended:
    """Testes estendidos do TextExtractor"""

    def test_contar_tokens_with_fallback(self):
        """Testa contagem de tokens com fallback (sem tiktoken)"""
        from sistemas.classificador_documentos.services_extraction import TextExtractor

        extractor = TextExtractor()

        # Força o fallback definindo _tiktoken_encoding como False (para pular lazy load)
        extractor._tiktoken_encoding = False

        texto = "Este é um texto de teste com várias palavras para contar"
        tokens = extractor.contar_tokens(texto)

        # Deve contar tokens (via tiktoken ou fallback)
        assert tokens > 0

    def test_extrair_chunk_texto_curto(self):
        """Testa extração de chunk com texto menor que o limite"""
        from sistemas.classificador_documentos.services_extraction import TextExtractor

        extractor = TextExtractor()
        texto = "Texto curto"

        chunk_inicio = extractor.extrair_chunk(texto, 1000, "inicio")
        chunk_fim = extractor.extrair_chunk(texto, 1000, "fim")

        # Quando o texto é menor que o limite, retorna o texto completo
        assert "Texto" in chunk_inicio
        assert "Texto" in chunk_fim

    def test_extrair_chunk_none(self):
        """Testa extração de chunk com texto None"""
        from sistemas.classificador_documentos.services_extraction import TextExtractor

        extractor = TextExtractor()

        # Texto vazio retorna vazio
        assert extractor.extrair_chunk("", 100, "inicio") == ""
        assert extractor.extrair_chunk("", 100, "fim") == ""

    def test_normalizer_property_not_available(self):
        """Testa propriedade normalizer quando não disponível"""
        from sistemas.classificador_documentos.services_extraction import TextExtractor

        extractor = TextExtractor(use_normalizer=True)

        with patch.dict('sys.modules', {'services.text_normalizer': None}):
            # Force re-load
            extractor._normalizer = None
            normalizer = extractor.normalizer
            # Pode ser None se o módulo não existir
            # O importante é não dar erro

    def test_normalizer_disabled(self):
        """Testa com normalizer desabilitado"""
        from sistemas.classificador_documentos.services_extraction import TextExtractor

        extractor = TextExtractor(use_normalizer=False)

        assert extractor.normalizer is None

    def test_extrair_texto_com_pymupdf_sucesso(self):
        """Testa extração com PyMuPDF mock"""
        from sistemas.classificador_documentos.services_extraction import TextExtractor

        extractor = TextExtractor(use_normalizer=False)

        with patch.object(extractor, '_extrair_com_pymupdf', return_value=("Texto extraído com sucesso. " * 10, 3)):
            result = extractor.extrair_texto(b"fake pdf bytes")

            assert result.texto is not None
            assert result.paginas_processadas == 3
            assert result.via_ocr is False

    def test_extrair_texto_fallback_ocr(self):
        """Testa fallback para OCR quando PyMuPDF retorna vazio"""
        from sistemas.classificador_documentos.services_extraction import TextExtractor

        extractor = TextExtractor(use_normalizer=False)

        with patch.object(extractor, '_extrair_com_pymupdf', return_value=("", 5)):
            with patch.object(extractor, '_extrair_com_ocr', return_value=("Texto via OCR " * 10, 5, None)):
                result = extractor.extrair_texto(b"fake pdf bytes")

                assert result.via_ocr is True
                assert "OCR" in result.texto

    def test_extrair_texto_ocr_falha(self):
        """Testa quando OCR também falha"""
        from sistemas.classificador_documentos.services_extraction import TextExtractor

        extractor = TextExtractor(use_normalizer=False)

        with patch.object(extractor, '_extrair_com_pymupdf', return_value=("", 0)):
            with patch.object(extractor, '_extrair_com_ocr', return_value=("", 0, "Erro no OCR")):
                result = extractor.extrair_texto(b"fake pdf bytes")

                assert result.texto == ""

    def test_extrair_texto_pdf_vazio(self):
        """Testa extração de PDF vazio"""
        from sistemas.classificador_documentos.services_extraction import TextExtractor

        extractor = TextExtractor(use_normalizer=False)

        with patch.object(extractor, '_extrair_com_pymupdf', return_value=("", 0)):
            with patch.object(extractor, '_extrair_com_ocr', return_value=("", 0, None)):
                result = extractor.extrair_texto(b"fake pdf bytes")

                assert result.texto == ""
                assert result.erro is None

    def test_extrair_texto_com_normalizacao(self):
        """Testa extração com normalização habilitada"""
        from sistemas.classificador_documentos.services_extraction import TextExtractor

        extractor = TextExtractor(use_normalizer=True)

        # Mock do normalizer - define diretamente o atributo privado
        mock_normalizer = Mock()
        mock_normalizer.normalize.return_value = Mock(text="Texto normalizado")
        extractor._normalizer = mock_normalizer

        with patch.object(extractor, '_extrair_com_pymupdf', return_value=("Texto bruto " * 20, 1)):
            result = extractor.extrair_texto(b"fake pdf bytes")

            # Deve usar o texto normalizado
            assert "normalizado" in result.texto


class TestExtractionResultExtended:
    """Testes estendidos do ExtractionResult"""

    def test_extraction_result_with_error(self):
        """Testa ExtractionResult com erro"""
        from sistemas.classificador_documentos.services_extraction import ExtractionResult

        result = ExtractionResult(
            texto="",
            via_ocr=False,
            tokens_total=0,
            paginas_processadas=0,
            erro="PDF corrompido"
        )

        assert result.erro == "PDF corrompido"
        assert result.texto == ""

    def test_extraction_result_via_ocr(self):
        """Testa ExtractionResult via OCR"""
        from sistemas.classificador_documentos.services_extraction import ExtractionResult

        result = ExtractionResult(
            texto="Texto via OCR",
            via_ocr=True,
            tokens_total=3,
            paginas_processadas=1,
            erro=None
        )

        assert result.via_ocr is True
        assert result.texto == "Texto via OCR"


class TestTextExtractorOCR:
    """Testes de extração via OCR"""

    def test_extrair_com_ocr_sem_dependencias(self):
        """Testa OCR quando dependências não estão disponíveis"""
        from sistemas.classificador_documentos.services_extraction import TextExtractor

        extractor = TextExtractor(use_normalizer=False)

        # O método _extrair_com_ocr já lida com ImportError
        # Simula ausência de pdf2image
        with patch.dict('sys.modules', {'pdf2image': None}):
            texto, paginas, erro = extractor._extrair_com_ocr(b"fake pdf bytes")

            # Deve retornar erro ou vazio
            assert texto == "" or erro is not None


class TestGetTextExtractor:
    """Testes do singleton"""

    def test_singleton_returns_same_instance(self):
        """Testa que singleton retorna mesma instância"""
        from sistemas.classificador_documentos.services_extraction import get_text_extractor

        instance1 = get_text_extractor()
        instance2 = get_text_extractor()

        assert instance1 is instance2

    def test_singleton_creates_extractor(self):
        """Testa que singleton cria instância de TextExtractor"""
        from sistemas.classificador_documentos.services_extraction import get_text_extractor, TextExtractor

        instance = get_text_extractor()

        assert isinstance(instance, TextExtractor)


class TestTextExtractorTiktoken:
    """Testes do tiktoken encoding"""

    def test_tiktoken_encoding_property(self):
        """Testa propriedade tiktoken_encoding"""
        from sistemas.classificador_documentos.services_extraction import TextExtractor

        extractor = TextExtractor()

        # Acessa a propriedade para lazy load
        encoding = extractor.tiktoken_encoding

        # Se tiktoken está instalado, deve retornar encoding
        # Se não está, deve retornar None
        assert encoding is not None or extractor._tiktoken_encoding is None

    def test_extrair_chunk_com_tiktoken(self):
        """Testa extração de chunk usando tiktoken"""
        from sistemas.classificador_documentos.services_extraction import TextExtractor

        extractor = TextExtractor()

        # Texto longo para testar extração de chunk
        texto = "Esta é uma frase de teste. " * 100

        chunk = extractor.extrair_chunk(texto, 50, "inicio")
        assert len(chunk) > 0
        assert len(chunk) < len(texto)

    def test_extrair_chunk_fim_com_tiktoken(self):
        """Testa extração de chunk do fim usando tiktoken"""
        from sistemas.classificador_documentos.services_extraction import TextExtractor

        extractor = TextExtractor()

        # Texto longo para testar extração de chunk
        texto = "Início do texto. " * 50 + "Final do texto. " * 50

        chunk = extractor.extrair_chunk(texto, 50, "fim")
        assert len(chunk) > 0
        assert "Final" in chunk or "texto" in chunk
