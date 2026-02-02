# sistemas/gerador_pecas/services_comparacao.py
"""
Servico de comparacao de resultados de modelos de IA.

Este modulo implementa a logica de normalizacao e comparacao de JSONs
extraidos por diferentes modelos, focando em campos estruturados
(boolean, number, choice, date, list, object) e ignorando campos 'text'.
"""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class DiferencaCampo:
    """Representa uma diferenca entre dois valores de um campo."""
    campo: str
    tipo_campo: str
    valor_a: Any
    valor_b: Any
    comparavel: bool  # True se foi comparado, False se ignorado (ex: text)


@dataclass
class RelatorioComparacao:
    """Relatorio completo da comparacao entre dois JSONs."""
    total_campos: int
    campos_comparados: int
    campos_iguais: int
    campos_diferentes: int
    campos_text_ignorados: int
    porcentagem_acordo: float
    diferencas: List[DiferencaCampo] = field(default_factory=list)
    resumo: str = ""


def obter_tipo_campo(chave: str, schema: Dict[str, Any]) -> str:
    """
    Retorna o tipo do campo baseado no schema.

    Args:
        chave: Nome do campo
        schema: Schema JSON com definicoes de tipos

    Returns:
        Tipo do campo: 'boolean', 'number', 'text', 'choice', 'date', 'list', 'object'
    """
    if not schema or chave not in schema:
        return "text"  # Default para text se nao encontrar no schema

    campo_def = schema[chave]
    if not isinstance(campo_def, dict):
        return "text"

    tipo = campo_def.get("type", "string")

    # Mapeamento de tipos
    if tipo == "boolean":
        return "boolean"
    elif tipo == "number" or tipo == "integer":
        return "number"
    elif tipo == "array":
        return "list"
    elif tipo == "object":
        return "object"
    elif tipo == "string":
        # Verifica se e um choice (enum) ou date
        if "enum" in campo_def:
            return "choice"
        # Verifica formato de data
        formato = campo_def.get("format", "")
        if formato in ("date", "date-time") or "data" in chave.lower():
            return "date"
        # Verifica se e um campo de texto longo
        descricao = campo_def.get("description", "").lower()
        if any(x in descricao for x in ["descreva", "explique", "justifique", "resumo", "detalhes"]):
            return "text"
        # Verifica pelo nome do campo
        if any(x in chave.lower() for x in ["descricao", "observacao", "justificativa", "motivo", "resumo", "texto"]):
            return "text"
        return "choice"  # Strings curtas sao tratadas como choice

    return "text"


def normalizar_valor_para_comparacao(valor: Any, tipo_campo: str) -> Any:
    """
    Normaliza um valor para comparacao independente de formato.

    Args:
        valor: Valor a normalizar
        tipo_campo: Tipo do campo

    Returns:
        Valor normalizado para comparacao
    """
    # null/None
    if valor is None:
        return None

    # Boolean
    if tipo_campo == "boolean":
        if isinstance(valor, bool):
            return valor
        if isinstance(valor, str):
            valor_lower = valor.lower().strip()
            if valor_lower in ("true", "sim", "yes", "1", "verdadeiro"):
                return True
            if valor_lower in ("false", "nao", "no", "0", "falso"):
                return False
        if isinstance(valor, (int, float)):
            return valor != 0
        return bool(valor)

    # Number
    if tipo_campo == "number":
        if valor is None:
            return None
        try:
            return float(valor)
        except (ValueError, TypeError):
            return None

    # Choice (strings)
    if tipo_campo == "choice":
        if valor is None:
            return None
        return str(valor).strip().lower()

    # Date
    if tipo_campo == "date":
        if valor is None:
            return None
        # Remove espacos e padroniza formato
        valor_str = str(valor).strip()
        # Remove horario se presente (pega so a data)
        if "T" in valor_str:
            valor_str = valor_str.split("T")[0]
        if " " in valor_str and ":" in valor_str:
            valor_str = valor_str.split(" ")[0]
        return valor_str

    # List
    if tipo_campo == "list":
        if not isinstance(valor, list):
            return []
        # Ordena para comparacao independente de ordem
        # Para listas de strings/numeros, ordena diretamente
        # Para listas de objetos, serializa e ordena
        try:
            if all(isinstance(item, (str, int, float, bool)) or item is None for item in valor):
                return sorted([normalizar_valor_para_comparacao(item, "choice") for item in valor])
            else:
                # Lista de objetos - serializa cada um ordenadamente
                serialized = []
                for item in valor:
                    if isinstance(item, dict):
                        # Ordena as chaves e normaliza valores
                        sorted_item = json.dumps(item, sort_keys=True, ensure_ascii=False)
                        serialized.append(sorted_item)
                    else:
                        serialized.append(str(item))
                return sorted(serialized)
        except (TypeError, ValueError):
            return valor

    # Object
    if tipo_campo == "object":
        if not isinstance(valor, dict):
            return {}
        # Normaliza recursivamente
        resultado = {}
        for k, v in valor.items():
            # Para objetos aninhados, trata como choice por padrao
            resultado[k] = normalizar_valor_para_comparacao(v, "choice")
        return resultado

    # Text - retorna como esta (sera ignorado na comparacao)
    return valor


def valores_sao_iguais(valor_a: Any, valor_b: Any, tipo_campo: str) -> bool:
    """
    Compara dois valores normalizados.

    Args:
        valor_a: Primeiro valor normalizado
        valor_b: Segundo valor normalizado
        tipo_campo: Tipo do campo

    Returns:
        True se os valores sao considerados iguais
    """
    # Ambos None sao iguais
    if valor_a is None and valor_b is None:
        return True

    # Um None e outro nao = diferentes
    if valor_a is None or valor_b is None:
        return False

    # Para listas, compara ordenadamente
    if tipo_campo == "list":
        if not isinstance(valor_a, list) or not isinstance(valor_b, list):
            return False
        return valor_a == valor_b

    # Para objetos, compara chave a chave
    if tipo_campo == "object":
        if not isinstance(valor_a, dict) or not isinstance(valor_b, dict):
            return False
        if set(valor_a.keys()) != set(valor_b.keys()):
            return False
        for k in valor_a:
            if valor_a[k] != valor_b.get(k):
                return False
        return True

    # Para numeros, usa tolerancia para floats
    if tipo_campo == "number":
        try:
            return abs(float(valor_a) - float(valor_b)) < 0.001
        except (ValueError, TypeError):
            return valor_a == valor_b

    # Para outros tipos, comparacao direta
    return valor_a == valor_b


def comparar_jsons_estruturados(
    json_a: Dict[str, Any],
    json_b: Dict[str, Any],
    schema: Dict[str, Any]
) -> RelatorioComparacao:
    """
    Compara dois JSONs extraidos, ignorando campos de texto.

    Args:
        json_a: JSON extraido pelo modelo A
        json_b: JSON extraido pelo modelo B
        schema: Schema da categoria com definicoes de tipos

    Returns:
        RelatorioComparacao com estatisticas e diferencas
    """
    # Coleta todas as chaves de ambos os JSONs
    todas_chaves = set(json_a.keys()) | set(json_b.keys())

    # Remove campos especiais que nao devem ser comparados
    campos_ignorar = {"irrelevante", "motivo"}
    todas_chaves -= campos_ignorar

    diferencas: List[DiferencaCampo] = []
    campos_comparados = 0
    campos_iguais = 0
    campos_diferentes = 0
    campos_text_ignorados = 0

    for chave in sorted(todas_chaves):
        tipo_campo = obter_tipo_campo(chave, schema)
        valor_a = json_a.get(chave)
        valor_b = json_b.get(chave)

        # Se for campo text, ignora na comparacao
        if tipo_campo == "text":
            campos_text_ignorados += 1
            diferencas.append(DiferencaCampo(
                campo=chave,
                tipo_campo=tipo_campo,
                valor_a=valor_a,
                valor_b=valor_b,
                comparavel=False
            ))
            continue

        # Normaliza valores
        valor_a_norm = normalizar_valor_para_comparacao(valor_a, tipo_campo)
        valor_b_norm = normalizar_valor_para_comparacao(valor_b, tipo_campo)

        # Compara
        campos_comparados += 1
        iguais = valores_sao_iguais(valor_a_norm, valor_b_norm, tipo_campo)

        if iguais:
            campos_iguais += 1
        else:
            campos_diferentes += 1
            diferencas.append(DiferencaCampo(
                campo=chave,
                tipo_campo=tipo_campo,
                valor_a=valor_a,
                valor_b=valor_b,
                comparavel=True
            ))

    # Calcula porcentagem de acordo
    if campos_comparados > 0:
        porcentagem = (campos_iguais / campos_comparados) * 100
    else:
        porcentagem = 100.0 if campos_text_ignorados == len(todas_chaves) else 0.0

    # Gera resumo
    if campos_diferentes == 0:
        resumo = f"100% de acordo em {campos_comparados} campo(s) comparado(s)"
    else:
        resumo = f"{campos_diferentes} diferenca(s) em {campos_comparados} campo(s) comparado(s)"

    if campos_text_ignorados > 0:
        resumo += f" ({campos_text_ignorados} campo(s) texto ignorado(s))"

    return RelatorioComparacao(
        total_campos=len(todas_chaves),
        campos_comparados=campos_comparados,
        campos_iguais=campos_iguais,
        campos_diferentes=campos_diferentes,
        campos_text_ignorados=campos_text_ignorados,
        porcentagem_acordo=round(porcentagem, 1),
        diferencas=diferencas,
        resumo=resumo
    )
