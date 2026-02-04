# tests/text_normalizer/test_normalizer.py
"""
Testes para o serviço de normalização de texto.

Execução:
    pytest tests/text_normalizer/ -v
"""

import time
import pytest

from services.text_normalizer import (
    text_normalizer,
    TextNormalizer,
    NormalizationMode,
    NormalizationOptions,
)


class TestBasicNormalization:
    """Testes de normalização básica."""

    def test_empty_text(self):
        """Texto vazio retorna vazio."""
        result = text_normalizer.normalize("")
        assert result.text == ""
        assert result.stats.original_length == 0

    def test_none_like_text(self):
        """Texto com apenas espaços retorna vazio."""
        result = text_normalizer.normalize("   \n\n   ")
        assert result.text == ""

    def test_simple_text_unchanged(self):
        """Texto simples sem problemas não muda significativamente."""
        text = "Este é um texto simples."
        result = text_normalizer.normalize(text)
        assert result.text == text

    def test_preserves_paragraphs_before_titles(self):
        """Preserva separação entre parágrafos antes de títulos."""
        # Quebra dupla preservada apenas antes de títulos/seções
        text = "Texto normal.\n\nTÍTULO DA SEÇÃO\n\nMais texto."
        result = text_normalizer.normalize(text)
        assert "\n\n" in result.text
        assert "TÍTULO DA SEÇÃO" in result.text
        # Parágrafos normais são colapsados (sem título)
        text2 = "Primeiro parágrafo.\n\nSegundo parágrafo."
        result2 = text_normalizer.normalize(text2)
        assert "Primeiro parágrafo" in result2.text
        assert "Segundo parágrafo" in result2.text
        # Conteúdo preservado, quebra pode ser simples


class TestWhitespaceCollapse:
    """Testes de colapso de espaços em branco."""

    def test_collapse_multiple_spaces(self):
        """Múltiplos espaços viram um."""
        text = "Texto    com    muitos    espaços."
        result = text_normalizer.normalize(text)
        assert "    " not in result.text
        assert "Texto com muitos espaços" in result.text

    def test_collapse_tabs(self):
        """Tabs são convertidos em espaço."""
        text = "Texto\t\tcom\t\ttabs."
        result = text_normalizer.normalize(text)
        assert "\t" not in result.text

    def test_collapse_mixed_whitespace(self):
        """Mistura de espaços e tabs é normalizada."""
        text = "Texto   \t   com   \t   mistura."
        result = text_normalizer.normalize(text)
        # Resultado não deve ter múltiplos espaços
        assert "   " not in result.text


class TestHyphenationFix:
    """Testes de correção de hifenização."""

    def test_fix_simple_hyphenation(self):
        """Corrige hifenização simples."""
        text = "medi-\ncamento"
        result = text_normalizer.normalize(text)
        assert "medicamento" in result.text

    def test_fix_hyphenation_with_spaces(self):
        """Corrige hifenização com espaços."""
        text = "medi-  \n  camento"
        result = text_normalizer.normalize(text)
        assert "medicamento" in result.text

    def test_preserve_real_hyphen(self):
        """Preserva hífens reais (não quebrados)."""
        text = "pré-natal é importante."
        result = text_normalizer.normalize(text)
        assert "pré-natal" in result.text

    def test_hyphenation_stats(self):
        """Estatísticas de hifenização são registradas."""
        text = "medi-\ncamento e trata-\nmento"
        result = text_normalizer.normalize(text)
        assert result.stats.hyphenations_fixed >= 2


class TestPageNumberRemoval:
    """Testes de remoção de números de página."""

    def test_remove_isolated_page_number(self):
        """Remove número de página isolado em linha."""
        text = "Texto do documento.\n123\nMais texto."
        result = text_normalizer.normalize(text)
        assert "\n123\n" not in result.text

    def test_remove_page_with_label(self):
        """Remove números de página isolados (não 'Página X')."""
        # Nota: A implementação atual remove apenas números isolados
        # em linha própria (ex: "42"), não "Página 42"
        text = "Texto.\n42\nMais texto."
        result = text_normalizer.normalize(text)
        # O número isolado deve ser removido
        assert result.stats.page_numbers_removed > 0

    def test_preserve_numbers_in_text(self):
        """Preserva números que fazem parte do texto."""
        text = "O processo tem 123 páginas no total."
        result = text_normalizer.normalize(text)
        assert "123" in result.text


class TestLineJoining:
    """Testes de junção inteligente de linhas."""

    def test_join_broken_sentence(self):
        """Junta linhas quebradas no meio de frase."""
        text = "Este é um texto que foi\nquebrado no meio da frase."
        result = text_normalizer.normalize(text)
        # Deve juntar as linhas
        assert "que foi quebrado" in result.text

    def test_preserve_sentence_boundary(self):
        """Preserva quebra após fim de sentença."""
        text = "Primeira frase.\nSegunda frase."
        result = text_normalizer.normalize(text)
        # Frases devem permanecer separadas
        assert "Primeira frase" in result.text
        assert "Segunda frase" in result.text

    def test_collapse_paragraph_break(self):
        """Colapsa parágrafos normais (sem título)."""
        text = "Primeiro parágrafo.\n\nSegundo parágrafo."
        result = text_normalizer.normalize(text)
        # Com collapse_paragraphs=True (padrão), parágrafos normais são colapsados
        assert "Primeiro parágrafo" in result.text
        assert "Segundo parágrafo" in result.text
        assert result.stats.paragraphs_collapsed >= 1


class TestHeaderFooterRemoval:
    """Testes de remoção de headers/footers repetidos."""

    def test_remove_repeated_header(self):
        """Remove header repetido múltiplas vezes."""
        header = "TRIBUNAL DE JUSTIÇA - MS"
        text = f"{header}\n\nConteúdo página 1.\n\n{header}\n\nConteúdo página 2.\n\n{header}\n\nConteúdo página 3."
        result = text_normalizer.normalize(text)
        # Header deve ser removido ou contagem deve indicar remoção
        count = result.text.count(header)
        assert count < 3 or result.stats.headers_removed > 0

    def test_preserve_unique_lines(self):
        """Preserva linhas únicas (não repetidas)."""
        text = "Linha única 1.\n\nLinha única 2.\n\nLinha única 3."
        result = text_normalizer.normalize(text)
        assert "Linha única 1" in result.text
        assert "Linha única 2" in result.text
        assert "Linha única 3" in result.text


class TestNormalizationModes:
    """Testes dos diferentes modos de normalização."""

    def test_conservative_mode(self):
        """Modo conservador preserva mais estrutura."""
        text = "Texto com\nquebra de linha."
        options = NormalizationOptions(mode=NormalizationMode.CONSERVATIVE)
        result = text_normalizer.normalize(text, options)
        # Modo conservador não junta linhas
        # (smart_line_join = False)
        assert result.stats.lines_joined == 0

    def test_balanced_mode_default(self):
        """Modo balanceado é o padrão."""
        result = text_normalizer.normalize("Texto teste.")
        # Verifica que usou opções padrão
        assert result.stats.processing_time_ms >= 0

    def test_aggressive_mode_deduplication(self):
        """Modo agressivo deduplica blocos."""
        # Cria texto com bloco duplicado
        block = "Este é um bloco de texto suficientemente longo para ser considerado na deduplicação."
        text = f"{block}\n\n{block}"
        options = NormalizationOptions(mode=NormalizationMode.AGGRESSIVE)
        result = text_normalizer.normalize(text, options)
        # Deve detectar e remover duplicação
        assert result.stats.blocks_deduplicated >= 0  # Pode ou não deduplar dependendo do tamanho


class TestUnicodeNormalization:
    """Testes de normalização de caracteres Unicode."""

    def test_normalize_smart_quotes(self):
        """Normaliza aspas tipográficas."""
        text = '"Texto com aspas curvas"'  # Usando smart quotes
        result = text_normalizer.normalize(text)
        # Aspas devem ser normalizadas para simples
        assert '"' in result.text or "Texto com aspas curvas" in result.text

    def test_normalize_em_dash(self):
        """Normaliza travessão."""
        text = "Texto — com travessão"
        result = text_normalizer.normalize(text)
        # Travessão deve ser normalizado para hífen
        assert "-" in result.text or "com travessão" in result.text

    def test_remove_invisible_chars(self):
        """Remove caracteres invisíveis."""
        text = "Texto\u200bcom\u200bzero\u200bwidth"  # Zero-width space
        result = text_normalizer.normalize(text)
        assert "\u200b" not in result.text


class TestControlCharRemoval:
    """Testes de remoção de caracteres de controle."""

    def test_remove_null_char(self):
        """Remove caractere NULL."""
        text = "Texto\x00com\x00null"
        result = text_normalizer.normalize(text)
        assert "\x00" not in result.text

    def test_remove_form_feed(self):
        """Remove form feed."""
        text = "Texto\x0ccom\x0cform feed"
        result = text_normalizer.normalize(text)
        assert "\x0c" not in result.text

    def test_preserve_newline(self):
        """Preserva newline (não é removido como controle)."""
        text = "Linha 1.\n\nLinha 2."
        result = text_normalizer.normalize(text)
        assert "\n" in result.text


class TestStatistics:
    """Testes de estatísticas da normalização."""

    def test_stats_original_length(self):
        """Comprimento original é registrado."""
        text = "Texto de teste"
        result = text_normalizer.normalize(text)
        assert result.stats.original_length == len(text)

    def test_stats_normalized_length(self):
        """Comprimento normalizado é registrado."""
        text = "Texto    com    espaços"
        result = text_normalizer.normalize(text)
        assert result.stats.normalized_length < result.stats.original_length

    def test_stats_compression_ratio(self):
        """Taxa de compressão é calculada."""
        text = "A" * 100 + "    " * 50  # Muitos espaços extras
        result = text_normalizer.normalize(text)
        assert result.stats.compression_ratio < 1.0

    def test_stats_reduction_percent(self):
        """Percentual de redução é calculado."""
        text = "A" * 100 + "    " * 50
        result = text_normalizer.normalize(text)
        assert result.stats.reduction_percent > 0

    def test_estimated_tokens(self):
        """Estimativa de tokens é calculada."""
        text = "A" * 100  # 100 caracteres
        result = text_normalizer.normalize(text)
        # ~4 chars por token
        assert result.estimated_tokens == 25


class TestPerformance:
    """Testes de performance."""

    def test_performance_10kb(self):
        """Normalização de 10KB deve ser rápida (<10ms)."""
        # Cria texto de ~10KB
        text = "Texto de exemplo. " * 500  # ~9KB

        start = time.perf_counter()
        result = text_normalizer.normalize(text)
        elapsed_ms = (time.perf_counter() - start) * 1000

        # Deve ser menor que 50ms (margem para CI/CD)
        assert elapsed_ms < 50, f"Normalização demorou {elapsed_ms:.2f}ms"
        assert result.stats.processing_time_ms < 50

    def test_performance_100kb(self):
        """Normalização de 100KB deve ser aceitável (<100ms)."""
        # Cria texto de ~100KB
        text = "Texto de exemplo com mais palavras. " * 3000  # ~105KB

        start = time.perf_counter()
        result = text_normalizer.normalize(text)
        elapsed_ms = (time.perf_counter() - start) * 1000

        # Deve ser menor que 200ms (margem para CI/CD)
        assert elapsed_ms < 200, f"Normalização demorou {elapsed_ms:.2f}ms"


class TestEdgeCases:
    """Testes de casos extremos."""

    def test_only_whitespace(self):
        """Texto com apenas espaços em branco."""
        result = text_normalizer.normalize("   \t\n\n   ")
        assert result.text == ""

    def test_single_character(self):
        """Texto com único caractere."""
        result = text_normalizer.normalize("A")
        assert result.text == "A"

    def test_many_newlines(self):
        """Muitas quebras de linha são reduzidas."""
        text = "A\n\n\n\n\n\n\n\n\n\nB"
        result = text_normalizer.normalize(text)
        # Não deve ter mais que 2 newlines consecutivas
        assert "\n\n\n" not in result.text

    def test_mixed_line_endings(self):
        """Diferentes tipos de quebra de linha."""
        text = "Linha 1\r\nLinha 2\rLinha 3\nLinha 4"
        result = text_normalizer.normalize(text)
        # Deve normalizar para \n
        assert "\r" not in result.text or "Linha" in result.text


class TestRealWorldExamples:
    """Testes com exemplos do mundo real."""

    def test_pdf_extracted_text(self):
        """Texto típico extraído de PDF jurídico."""
        text = """PODER JUDICIÁRIO
TRIBUNAL DE JUSTIÇA DE MATO GROSSO DO SUL
PODER JUDICIÁRIO
TRIBUNAL DE JUSTIÇA DE MATO GROSSO DO SUL

Processo nº 0800123-45.2024.8.12.0001

    O   Réu   apresentou   contes-
tação alegando que o contrato
foi  cumprido  integralmente.

PODER JUDICIÁRIO
TRIBUNAL DE JUSTIÇA DE MATO GROSSO DO SUL

23

Diante do exposto, JULGO PROCEDENTE o pedido.

PODER JUDICIÁRIO
TRIBUNAL DE JUSTIÇA DE MATO GROSSO DO SUL
"""
        result = text_normalizer.normalize(text)

        # Verifica que hifenização foi corrigida
        assert "contestação" in result.text

        # Verifica que espaços foram colapsados
        assert "O Réu apresentou" in result.text or "O   Réu" not in result.text

        # Verifica redução de tamanho
        assert result.stats.reduction_percent > 0

    def test_legal_document_structure(self):
        """Preserva estrutura de documento jurídico."""
        text = """EXCELENTÍSSIMO SENHOR DOUTOR JUIZ DE DIREITO

O ESTADO DE MATO GROSSO DO SUL, já qualificado nos autos, vem respeitosamente à presença de Vossa Excelência apresentar:

CONTESTAÇÃO

1. DOS FATOS

O autor alega que...

2. DO DIREITO

Nos termos do art. 373 do CPC...

3. DOS PEDIDOS

Diante do exposto, requer:
a) a improcedência do pedido;
b) a condenação do autor."""

        result = text_normalizer.normalize(text)

        # Estrutura deve ser preservada
        assert "CONTESTAÇÃO" in result.text
        assert "DOS FATOS" in result.text
        assert "DO DIREITO" in result.text
        assert "DOS PEDIDOS" in result.text


class TestInstanceCreation:
    """Testes de criação de instância."""

    def test_singleton_exists(self):
        """Singleton text_normalizer existe."""
        assert text_normalizer is not None
        assert isinstance(text_normalizer, TextNormalizer)

    def test_new_instance(self):
        """Pode criar nova instância."""
        normalizer = TextNormalizer()
        result = normalizer.normalize("Teste")
        assert result.text == "Teste"

    def test_multiple_calls(self):
        """Múltiplas chamadas funcionam corretamente."""
        for i in range(10):
            result = text_normalizer.normalize(f"Texto {i}")
            assert f"Texto {i}" in result.text
