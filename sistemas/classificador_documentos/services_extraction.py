# sistemas/classificador_documentos/services_extraction.py
"""
Serviço de extração de texto de documentos PDF.

Pipeline de extração:
1. Tentar extrair texto com PyMuPDF
2. Se falhar ou vier vazio, aplicar OCR
3. Normalizar texto com text_normalizer do portal-pge

Autor: LAB/PGE-MS
"""

import logging
import io
import os
from typing import Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    """Resultado da extração de texto"""
    texto: str
    via_ocr: bool
    tokens_total: int
    paginas_processadas: int
    erro: Optional[str] = None


class TextExtractor:
    """
    Extrator de texto de documentos PDF com fallback para OCR.

    Uso:
        extractor = TextExtractor()
        result = extractor.extrair_texto(pdf_bytes)
    """

    def __init__(self, use_normalizer: bool = True):
        """
        Args:
            use_normalizer: Se True, normaliza o texto extraído
        """
        self.use_normalizer = use_normalizer
        self._normalizer = None
        self._tiktoken_encoding = None

    @property
    def normalizer(self):
        """Lazy load do normalizador"""
        if self._normalizer is None and self.use_normalizer:
            try:
                from services.text_normalizer import text_normalizer
                self._normalizer = text_normalizer
            except ImportError:
                logger.warning("text_normalizer não disponível")
        return self._normalizer

    @property
    def tiktoken_encoding(self):
        """Lazy load do encoding tiktoken"""
        if self._tiktoken_encoding is None:
            try:
                import tiktoken
                self._tiktoken_encoding = tiktoken.get_encoding("cl100k_base")
            except ImportError:
                logger.warning("tiktoken não disponível - contagem de tokens desabilitada")
        return self._tiktoken_encoding

    def contar_tokens(self, texto: str) -> int:
        """Conta tokens no texto usando tiktoken"""
        if not texto:
            return 0
        if self.tiktoken_encoding:
            return len(self.tiktoken_encoding.encode(texto))
        # Fallback: estimativa baseada em palavras
        return len(texto.split()) * 1.3

    def extrair_chunk(self, texto: str, tamanho: int, posicao: str = "fim") -> str:
        """
        Extrai um chunk de N tokens do texto.

        Args:
            texto: Texto completo
            tamanho: Número de tokens desejado
            posicao: "inicio" ou "fim"

        Returns:
            Chunk de texto com aproximadamente N tokens
        """
        if not texto:
            return ""

        if self.tiktoken_encoding:
            tokens = self.tiktoken_encoding.encode(texto)
            if posicao == "inicio":
                chunk_tokens = tokens[:tamanho]
            else:
                chunk_tokens = tokens[-tamanho:]
            return self.tiktoken_encoding.decode(chunk_tokens)
        else:
            # Fallback: estimativa baseada em caracteres
            chars_per_token = 4  # Aproximação
            char_limit = tamanho * chars_per_token
            if posicao == "inicio":
                return texto[:char_limit]
            else:
                return texto[-char_limit:]

    def extrair_texto(self, pdf_bytes: bytes) -> ExtractionResult:
        """
        Extrai texto de um PDF.

        Pipeline:
        1. Tenta extrair com PyMuPDF
        2. Se falhar ou vazio, tenta OCR
        3. Normaliza o resultado

        Args:
            pdf_bytes: Bytes do arquivo PDF

        Returns:
            ExtractionResult com texto extraído
        """
        # Tenta extração direta com PyMuPDF
        texto, paginas = self._extrair_com_pymupdf(pdf_bytes)

        via_ocr = False

        # Se texto vazio ou muito curto, tenta OCR
        if not texto or len(texto.strip()) < 50:
            logger.info("Texto extraído vazio ou muito curto, tentando OCR...")
            texto_ocr, paginas_ocr, erro_ocr = self._extrair_com_ocr(pdf_bytes)

            if texto_ocr and len(texto_ocr.strip()) > len(texto.strip()):
                texto = texto_ocr
                paginas = paginas_ocr
                via_ocr = True
            elif erro_ocr:
                logger.warning(f"OCR falhou: {erro_ocr}")

        # Normaliza texto se configurado
        if texto and self.normalizer:
            try:
                result = self.normalizer.normalize(texto)
                texto = result.text
            except Exception as e:
                logger.warning(f"Erro ao normalizar texto: {e}")

        # Conta tokens
        tokens = int(self.contar_tokens(texto))

        return ExtractionResult(
            texto=texto,
            via_ocr=via_ocr,
            tokens_total=tokens,
            paginas_processadas=paginas
        )

    def _extrair_com_pymupdf(self, pdf_bytes: bytes) -> Tuple[str, int]:
        """
        Extrai texto usando PyMuPDF (fitz).

        Returns:
            Tupla (texto, num_paginas)
        """
        try:
            import fitz

            # Suprime warnings de imagens corrompidas
            # (comum em PDFs escaneados com JPEG2000)
            fitz.TOOLS.mupdf_warnings(False)

            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            textos = []
            num_paginas = len(doc)

            for page in doc:
                texto_pagina = page.get_text("text")
                if texto_pagina:
                    textos.append(texto_pagina)

            doc.close()

            return "\n\n".join(textos), num_paginas

        except ImportError:
            logger.error("PyMuPDF (fitz) não instalado")
            return "", 0
        except Exception as e:
            logger.error(f"Erro ao extrair texto com PyMuPDF: {e}")
            return "", 0

    def _extrair_com_ocr(self, pdf_bytes: bytes) -> Tuple[str, int, Optional[str]]:
        """
        Extrai texto usando OCR (pytesseract + pdf2image).

        Returns:
            Tupla (texto, num_paginas, erro)
        """
        try:
            # Tenta importar dependências de OCR
            try:
                from pdf2image import convert_from_bytes
                import pytesseract
            except ImportError as e:
                return "", 0, f"Dependências de OCR não instaladas: {e}"

            # Converte PDF para imagens
            try:
                images = convert_from_bytes(pdf_bytes, dpi=300)
            except Exception as e:
                return "", 0, f"Erro ao converter PDF para imagens: {e}"

            textos = []
            for i, image in enumerate(images):
                try:
                    # Configura pytesseract para português
                    texto_pagina = pytesseract.image_to_string(
                        image,
                        lang='por',
                        config='--psm 1'  # Automatic page segmentation with OSD
                    )
                    if texto_pagina:
                        textos.append(texto_pagina)
                except Exception as e:
                    logger.warning(f"Erro no OCR da página {i+1}: {e}")

            return "\n\n".join(textos), len(images), None

        except Exception as e:
            logger.exception(f"Erro no OCR: {e}")
            return "", 0, str(e)


# ============================================
# Instância global
# ============================================

_text_extractor: Optional[TextExtractor] = None


def get_text_extractor() -> TextExtractor:
    """Retorna instância singleton do extrator de texto"""
    global _text_extractor
    if _text_extractor is None:
        _text_extractor = TextExtractor()
    return _text_extractor
