# services/text_normalizer/utils.py
"""
Funções utilitárias para normalização de texto.
"""

from typing import List, Dict, Tuple
from collections import Counter

from .patterns import UNICODE_NORMALIZE_MAP


def estimate_tokens(text: str) -> int:
    """
    Estima o número de tokens para modelos de linguagem.

    Usa a aproximação de ~4 caracteres por token, que é uma
    média razoável para textos em português/inglês.

    Args:
        text: Texto para estimar tokens

    Returns:
        Estimativa de número de tokens
    """
    if not text:
        return 0
    return len(text) // 4


def normalize_unicode_chars(text: str) -> str:
    """
    Normaliza caracteres Unicode para equivalentes ASCII/básicos.

    Converte:
    - Smart quotes para aspas simples/duplas normais
    - Dashes tipográficos para hífen
    - Espaços especiais para espaço normal

    Args:
        text: Texto com possíveis caracteres especiais

    Returns:
        Texto com caracteres normalizados
    """
    if not text:
        return ""

    # Usa translation table para eficiência
    result = text
    for char, replacement in UNICODE_NORMALIZE_MAP.items():
        if char in result:
            result = result.replace(char, replacement)

    return result


def find_repeated_lines(lines: List[str], min_occurrences: int = 3) -> set:
    """
    Encontra linhas que aparecem múltiplas vezes (candidatas a header/footer).

    Args:
        lines: Lista de linhas do texto
        min_occurrences: Mínimo de ocorrências para considerar repetida

    Returns:
        Set com linhas repetidas
    """
    # Filtra linhas muito curtas ou muito longas
    valid_lines = [
        line.strip()
        for line in lines
        if 5 <= len(line.strip()) <= 100
    ]

    # Conta ocorrências
    counter = Counter(valid_lines)

    # Retorna linhas com ocorrências >= min_occurrences
    return {
        line for line, count in counter.items()
        if count >= min_occurrences
    }


def detect_headers_footers(
    text: str,
    min_occurrences: int = 3
) -> Tuple[set, set]:
    """
    Detecta possíveis headers e footers repetidos no texto.

    Heurística: headers tendem a aparecer no início de blocos,
    footers no final.

    Args:
        text: Texto para análise
        min_occurrences: Mínimo de ocorrências

    Returns:
        Tupla (headers, footers) com sets de strings detectadas
    """
    lines = text.split('\n')
    repeated = find_repeated_lines(lines, min_occurrences)

    if not repeated:
        return set(), set()

    # Analisa posição das linhas repetidas
    headers = set()
    footers = set()

    # Divide em blocos (separados por linhas vazias)
    blocks = text.split('\n\n')

    for block in blocks:
        block_lines = block.strip().split('\n')
        if not block_lines:
            continue

        # Primeira linha do bloco pode ser header
        first_line = block_lines[0].strip()
        if first_line in repeated:
            headers.add(first_line)

        # Última linha do bloco pode ser footer
        if len(block_lines) > 1:
            last_line = block_lines[-1].strip()
            if last_line in repeated:
                footers.add(last_line)

    return headers, footers


def remove_duplicate_blocks(
    text: str,
    min_block_length: int = 50,
    similarity_threshold: float = 0.95
) -> Tuple[str, int]:
    """
    Remove blocos de texto duplicados ou muito similares.

    Útil para remover repetições causadas por problemas de extração de PDF.

    Args:
        text: Texto com possíveis duplicações
        min_block_length: Tamanho mínimo do bloco para considerar
        similarity_threshold: Limiar de similaridade (0-1)

    Returns:
        Tupla (texto limpo, número de blocos removidos)
    """
    # Divide em blocos
    blocks = text.split('\n\n')

    if len(blocks) <= 1:
        return text, 0

    unique_blocks = []
    removed_count = 0

    for block in blocks:
        block = block.strip()
        if len(block) < min_block_length:
            unique_blocks.append(block)
            continue

        # Verifica se bloco é duplicado
        is_duplicate = False
        for existing in unique_blocks:
            if len(existing) < min_block_length:
                continue

            # Verifica similaridade simples (baseada em comprimento e início/fim)
            if _blocks_similar(block, existing, similarity_threshold):
                is_duplicate = True
                removed_count += 1
                break

        if not is_duplicate:
            unique_blocks.append(block)

    return '\n\n'.join(unique_blocks), removed_count


def _blocks_similar(block1: str, block2: str, threshold: float) -> bool:
    """
    Verifica se dois blocos são similares.

    Usa heurística simples baseada em comprimento e conteúdo.

    Args:
        block1: Primeiro bloco
        block2: Segundo bloco
        threshold: Limiar de similaridade

    Returns:
        True se blocos são considerados similares
    """
    # Se comprimentos muito diferentes, não são similares
    len_ratio = min(len(block1), len(block2)) / max(len(block1), len(block2))
    if len_ratio < threshold:
        return False

    # Compara primeiros e últimos caracteres
    sample_size = min(100, len(block1), len(block2))

    start_match = block1[:sample_size] == block2[:sample_size]
    end_match = block1[-sample_size:] == block2[-sample_size:]

    # Se início E fim são iguais, considera duplicado
    return start_match and end_match


def count_lines(text: str) -> int:
    """Conta número de linhas no texto."""
    if not text:
        return 0
    return text.count('\n') + 1


def is_sentence_end(char: str) -> bool:
    """Verifica se caractere indica fim de sentença."""
    return char in '.!?;:'


def starts_with_lowercase(text: str) -> bool:
    """Verifica se texto começa com letra minúscula."""
    if not text:
        return False
    return text[0].islower()
