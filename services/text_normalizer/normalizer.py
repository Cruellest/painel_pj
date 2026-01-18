# services/text_normalizer/normalizer.py
"""
Serviço central de normalização de texto para PDFs.

Este módulo consolida a lógica de normalização de texto anteriormente
duplicada em múltiplos arquivos do sistema.
"""

import time
import logging
from typing import Optional

from .models import (
    NormalizationMode,
    NormalizationOptions,
    NormalizationStats,
    NormalizationResult,
)
from .patterns import (
    CONTROL_CHARS,
    INVISIBLE_UNICODE,
    MULTIPLE_SPACES,
    MULTIPLE_NEWLINES,
    BROKEN_HYPHENATION,
    ISOLATED_PAGE_NUMBER,
    is_section_title,
)
from .utils import (
    normalize_unicode_chars,
    detect_headers_footers,
    remove_duplicate_blocks,
    count_lines,
    is_sentence_end,
    starts_with_lowercase,
)


logger = logging.getLogger(__name__)


class TextNormalizer:
    """
    Normalizador de texto extraído de PDFs.

    Aplica um pipeline de transformações para limpar e normalizar
    texto antes de enviar para processamento por IA.

    Exemplo de uso:
        from services.text_normalizer import text_normalizer

        result = text_normalizer.normalize(texto_pdf)
        texto_limpo = result.text
    """

    def __init__(self):
        """Inicializa o normalizador."""
        self._default_options = NormalizationOptions()

    def normalize(
        self,
        text: str,
        options: Optional[NormalizationOptions] = None
    ) -> NormalizationResult:
        """
        Normaliza texto aplicando pipeline de transformações.

        Args:
            text: Texto bruto para normalizar
            options: Opções de normalização (usa padrões se None)

        Returns:
            NormalizationResult com texto normalizado e estatísticas
        """
        start_time = time.perf_counter()

        # Usa opções padrão se não fornecidas
        if options is None:
            options = self._get_options_for_mode(NormalizationMode.BALANCED)
        elif options.mode != NormalizationMode.BALANCED:
            # Ajusta opções baseado no modo
            options = self._get_options_for_mode(options.mode)

        # Inicializa estatísticas
        stats = NormalizationStats(
            original_length=len(text) if text else 0,
            original_lines=count_lines(text) if text else 0,
        )

        # Texto vazio
        if not text or not text.strip():
            stats.processing_time_ms = (time.perf_counter() - start_time) * 1000
            return NormalizationResult(text="", stats=stats)

        # Pipeline de normalização
        result = text

        # 1. Remove caracteres de controle
        if options.remove_control_chars:
            result = self._remove_control_chars(result)

        # 2. Remove unicode invisível
        if options.remove_invisible_unicode:
            result = self._remove_invisible_unicode(result)

        # 3. Normaliza caracteres unicode
        if options.normalize_unicode:
            result = normalize_unicode_chars(result)

        # 4. Colapsa whitespace
        if options.collapse_whitespace:
            result = self._collapse_whitespace(result)

        # 5. Remove números de página
        if options.remove_page_numbers:
            result, removed = self._remove_page_numbers(result)
            stats.page_numbers_removed = removed

        # 6. Detecta e remove headers/footers repetidos
        if options.detect_headers_footers:
            result, h_removed, f_removed = self._remove_headers_footers(result)
            stats.headers_removed = h_removed
            stats.footers_removed = f_removed

        # 7. Corrige hifenização quebrada
        if options.fix_hyphenation:
            result, fixed = self._fix_hyphenation(result)
            stats.hyphenations_fixed = fixed

        # 8. Junção inteligente de linhas
        if options.smart_line_join:
            result, joined = self._smart_line_join(result)
            stats.lines_joined = joined

        # 9. Colapsa parágrafos (mantém quebra dupla apenas antes de títulos)
        if options.collapse_paragraphs:
            result, collapsed = self._collapse_paragraphs(result)
            stats.paragraphs_collapsed = collapsed

        # 10. Deduplicação de blocos (apenas modo aggressive)
        if options.deduplicate_blocks:
            result, deduped = remove_duplicate_blocks(result)
            stats.blocks_deduplicated = deduped

        # 11. Limpeza final
        result = self._final_cleanup(result, options.max_consecutive_newlines)

        # Calcula estatísticas finais
        stats.normalized_length = len(result)
        stats.normalized_lines = count_lines(result)
        stats.chars_removed = stats.original_length - stats.normalized_length
        stats.processing_time_ms = (time.perf_counter() - start_time) * 1000

        # Log métricas (sem conteúdo)
        if stats.reduction_percent > 5:
            logger.debug(
                f"Texto normalizado: {stats.original_length} -> {stats.normalized_length} chars "
                f"({stats.reduction_percent:.1f}% redução) em {stats.processing_time_ms:.2f}ms"
            )

        return NormalizationResult(text=result, stats=stats)

    def _get_options_for_mode(self, mode: NormalizationMode) -> NormalizationOptions:
        """Retorna opções pré-configuradas para cada modo."""
        if mode == NormalizationMode.CONSERVATIVE:
            return NormalizationOptions(
                mode=mode,
                remove_control_chars=True,
                remove_invisible_unicode=True,
                collapse_whitespace=True,
                remove_page_numbers=False,
                detect_headers_footers=False,
                fix_hyphenation=True,
                smart_line_join=False,  # Preserva quebras originais
                collapse_paragraphs=False,  # Preserva parágrafos originais
                deduplicate_blocks=False,
                normalize_unicode=True,
                max_consecutive_newlines=3,
            )
        elif mode == NormalizationMode.AGGRESSIVE:
            return NormalizationOptions(
                mode=mode,
                remove_control_chars=True,
                remove_invisible_unicode=True,
                collapse_whitespace=True,
                remove_page_numbers=True,
                detect_headers_footers=True,
                fix_hyphenation=True,
                smart_line_join=True,
                collapse_paragraphs=True,  # Colapsa parágrafos
                deduplicate_blocks=True,  # Remove blocos duplicados
                normalize_unicode=True,
                max_consecutive_newlines=2,
            )
        else:  # BALANCED (padrão)
            return NormalizationOptions(
                mode=mode,
                remove_control_chars=True,
                remove_invisible_unicode=True,
                collapse_whitespace=True,
                remove_page_numbers=True,
                detect_headers_footers=True,
                fix_hyphenation=True,
                smart_line_join=True,
                collapse_paragraphs=True,  # Colapsa parágrafos
                deduplicate_blocks=False,
                normalize_unicode=True,
                max_consecutive_newlines=2,
            )

    def _remove_control_chars(self, text: str) -> str:
        """Remove caracteres de controle ASCII (exceto newline)."""
        return CONTROL_CHARS.sub('', text)

    def _remove_invisible_unicode(self, text: str) -> str:
        """Remove caracteres unicode invisíveis."""
        return INVISIBLE_UNICODE.sub('', text)

    def _collapse_whitespace(self, text: str) -> str:
        """Colapsa múltiplos espaços/tabs em um único espaço."""
        return MULTIPLE_SPACES.sub(' ', text)

    def _remove_page_numbers(self, text: str) -> tuple[str, int]:
        """
        Remove números de página isolados.

        Returns:
            Tupla (texto limpo, número de páginas removidas)
        """
        count = 0
        lines = text.split('\n')
        result = []

        for line in lines:
            if ISOLATED_PAGE_NUMBER.match(line):
                count += 1
            else:
                result.append(line)

        return '\n'.join(result), count

    def _remove_headers_footers(self, text: str) -> tuple[str, int, int]:
        """
        Remove headers e footers repetidos.

        Returns:
            Tupla (texto limpo, headers removidos, footers removidos)
        """
        headers, footers = detect_headers_footers(text)

        if not headers and not footers:
            return text, 0, 0

        lines = text.split('\n')
        result = []
        h_count = 0
        f_count = 0

        for line in lines:
            stripped = line.strip()
            if stripped in headers:
                h_count += 1
            elif stripped in footers:
                f_count += 1
            else:
                result.append(line)

        return '\n'.join(result), h_count, f_count

    def _fix_hyphenation(self, text: str) -> tuple[str, int]:
        """
        Corrige palavras hifenizadas quebradas entre linhas.

        Ex: "medi-\ncamento" -> "medicamento"

        Returns:
            Tupla (texto corrigido, número de correções)
        """
        count = 0

        def replace_hyphen(match):
            nonlocal count
            count += 1
            return match.group(1) + match.group(2)

        result = BROKEN_HYPHENATION.sub(replace_hyphen, text)
        return result, count

    def _smart_line_join(self, text: str) -> tuple[str, int]:
        """
        Junta linhas quebradas no meio de frases.

        Preserva parágrafos (linhas vazias) e quebras após pontuação.

        Returns:
            Tupla (texto com linhas juntas, número de junções)
        """
        lines = [line.strip() for line in text.split('\n')]
        resultado = []
        buffer = ""
        join_count = 0

        for linha in lines:
            if not linha:
                # Linha vazia indica parágrafo
                if buffer:
                    resultado.append(buffer)
                    buffer = ""
                continue

            if buffer:
                ultima_char = buffer[-1] if buffer else ''
                primeira_char = linha[0] if linha else ''

                # Junta se: linha anterior não termina com pontuação
                # E linha atual começa com minúscula
                if not is_sentence_end(ultima_char) and starts_with_lowercase(linha):
                    buffer += ' ' + linha
                    join_count += 1
                else:
                    # Nova frase/parágrafo
                    resultado.append(buffer)
                    buffer = linha
            else:
                buffer = linha

        if buffer:
            resultado.append(buffer)

        # Junta parágrafos com dupla quebra de linha
        return '\n\n'.join(resultado), join_count

    def _collapse_paragraphs(self, text: str) -> tuple[str, int]:
        """
        Colapsa parágrafos, mantendo quebra dupla apenas antes de títulos/seções.

        Isso reduz a fragmentação do contexto para análise por IA,
        mantendo apenas as quebras semanticamente importantes.

        Returns:
            Tupla (texto com parágrafos colapsados, número de parágrafos colapsados)
        """
        # Divide em blocos (separados por \n\n)
        blocks = text.split('\n\n')

        if len(blocks) <= 1:
            return text, 0

        result = []
        collapsed_count = 0

        for i, block in enumerate(blocks):
            block = block.strip()
            if not block:
                continue

            if i == 0:
                # Primeiro bloco sempre entra
                result.append(block)
            else:
                # Verifica se este bloco é um título de seção
                first_line = block.split('\n')[0] if '\n' in block else block
                if is_section_title(first_line):
                    # Mantém quebra dupla antes de títulos
                    result.append('\n\n' + block)
                else:
                    # Colapsa: usa quebra simples
                    result.append('\n' + block)
                    collapsed_count += 1

        return ''.join(result), collapsed_count

    def _final_cleanup(self, text: str, max_newlines: int = 2) -> str:
        """
        Limpeza final do texto.

        - Remove mais de N quebras de linha consecutivas
        - Remove espaços em branco no início/fim
        - Remove linhas que contêm apenas espaços
        """
        # Remove mais de max_newlines quebras consecutivas
        pattern = f'\\n{{{max_newlines + 1},}}'
        replacement = '\n' * max_newlines
        result = __import__('re').sub(pattern, replacement, text)

        # Remove linhas vazias que contêm apenas espaços
        lines = result.split('\n')
        result = '\n'.join(line if line.strip() else '' for line in lines)

        return result.strip()


# Singleton para uso direto
text_normalizer = TextNormalizer()
