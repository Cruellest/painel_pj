# services/text_normalizer/patterns.py
"""
Regex patterns pré-compilados para normalização de texto.

Padrões são compilados no import para melhor performance.
"""

import re


# =============================================================================
# Caracteres de Controle e Invisíveis
# =============================================================================

# Caracteres de controle ASCII (exceto \n = 0x0A)
# Inclui: NUL, SOH-TAB, VT, FF, CR-US (0x00-0x09, 0x0B, 0x0C, 0x0E-0x1F)
CONTROL_CHARS = re.compile(r'[\x00-\x09\x0b\x0c\x0e-\x1f]')

# Caracteres Unicode invisíveis
# Inclui: Zero-width spaces, joiners, marks, etc.
INVISIBLE_UNICODE = re.compile(
    r'[\u200B-\u200F'  # Zero-width space, joiners, marks
    r'\u2028-\u202F'   # Line/paragraph separators, narrow no-break space
    r'\u205F-\u206F'   # Medium math space, word joiner, invisible operators
    r'\uFEFF'          # BOM / Zero-width no-break space
    r'\u00AD'          # Soft hyphen
    r'\u180E'          # Mongolian vowel separator
    r'\u2060]'         # Word joiner
)


# =============================================================================
# Espaços em Branco
# =============================================================================

# Múltiplos espaços/tabs horizontais
MULTIPLE_SPACES = re.compile(r'[ \t]+')

# Múltiplas quebras de linha (3+)
MULTIPLE_NEWLINES = re.compile(r'\n{3,}')

# Espaço antes de quebra de linha
SPACE_BEFORE_NEWLINE = re.compile(r' +\n')

# Espaço no início de linha
LEADING_SPACE = re.compile(r'(?m)^[ \t]+')


# =============================================================================
# Números de Página
# =============================================================================

# Padrões comuns de número de página
# - "Página 123" / "Pág. 123" / "Page 123"
# - "- 123 -" / "— 123 —"
# - "123/456" (página atual/total)
# - Número sozinho em linha
PAGE_NUMBER_PATTERNS = re.compile(
    r'(?m)'  # Multiline mode
    r'^(?:'
    r'(?:Página|Pág\.?|Page|Fl\.?|Folha)\s*:?\s*\d+(?:\s*/\s*\d+)?'  # Página 1 / Página 1/10
    r'|[-–—]\s*\d+\s*[-–—]'  # - 123 -
    r'|\d+\s*/\s*\d+'  # 123/456
    r'|\d{1,4}'  # Número sozinho (1-4 dígitos)
    r')$'
    r'(?:\s*\n)?',  # Opcional: newline após
    re.IGNORECASE
)

# Número de página isolado (linha contém apenas número)
ISOLATED_PAGE_NUMBER = re.compile(r'^[ \t]*\d{1,4}[ \t]*$', re.MULTILINE)


# =============================================================================
# Hifenização
# =============================================================================

# Palavra hifenizada quebrada entre linhas
# Ex: "medi-\ncamento" -> "medicamento"
# Captura: (palavra com hífen no final)(quebra de linha)(continuação minúscula)
BROKEN_HYPHENATION = re.compile(
    r'(\w+)-\s*\n\s*([a-záàâãéèêíìîóòôõúùûüç])',
    re.IGNORECASE
)


# =============================================================================
# Identificadores Jurídicos
# =============================================================================

# Número de processo CNJ
# Formato: NNNNNNN-DD.AAAA.J.TR.OOOO
CNJ_NUMBER = re.compile(
    r'\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}'
)

# Número de processo formato antigo MS
# Formato: NNNN.AAAA.NNNNNN-N ou variações
OLD_MS_NUMBER = re.compile(
    r'\d{4}\.\d{4}\.\d{6}-\d'
)


# =============================================================================
# Headers/Footers Repetidos
# =============================================================================

# Padrão para detectar linhas candidatas a header/footer
# Linhas curtas (< 100 chars) que podem ser repetidas
HEADER_FOOTER_CANDIDATE = re.compile(
    r'^.{5,100}$',  # Linhas de 5-100 caracteres
    re.MULTILINE
)


# =============================================================================
# Blocos de Texto
# =============================================================================

# Separador de blocos (duas ou mais quebras de linha)
BLOCK_SEPARATOR = re.compile(r'\n\n+')

# Linha vazia
EMPTY_LINE = re.compile(r'^\s*$', re.MULTILINE)


# =============================================================================
# Pontuação de Fim de Sentença
# =============================================================================

# Caracteres que indicam fim de sentença/frase
END_OF_SENTENCE = '.!?;:'

# Regex para verificar se linha termina com pontuação
ENDS_WITH_PUNCTUATION = re.compile(r'[.!?;:]$')


# =============================================================================
# Unicode para Normalizar
# =============================================================================

# Smart quotes e aspas tipográficas
SMART_QUOTES = {
    '\u201C': '"',  # "
    '\u201D': '"',  # "
    '\u2018': "'",  # '
    '\u2019': "'",  # '
    '\u00AB': '"',  # «
    '\u00BB': '"',  # »
    '\u201A': "'",  # ‚
    '\u201E': '"',  # „
}

# Dashes tipográficos
SMART_DASHES = {
    '\u2013': '-',  # en-dash
    '\u2014': '-',  # em-dash
    '\u2015': '-',  # horizontal bar
    '\u2212': '-',  # minus sign
}

# Espaços especiais
SPECIAL_SPACES = {
    '\u00A0': ' ',  # No-break space
    '\u2000': ' ',  # En quad
    '\u2001': ' ',  # Em quad
    '\u2002': ' ',  # En space
    '\u2003': ' ',  # Em space
    '\u2004': ' ',  # Three-per-em space
    '\u2005': ' ',  # Four-per-em space
    '\u2006': ' ',  # Six-per-em space
    '\u2007': ' ',  # Figure space
    '\u2008': ' ',  # Punctuation space
    '\u2009': ' ',  # Thin space
    '\u200A': ' ',  # Hair space
    '\u202F': ' ',  # Narrow no-break space
    '\u205F': ' ',  # Medium mathematical space
    '\u3000': ' ',  # Ideographic space
}

# Combinado para substituição rápida
UNICODE_NORMALIZE_MAP = {**SMART_QUOTES, **SMART_DASHES, **SPECIAL_SPACES}
