# services/ia_params_resolver.py
"""
Serviço central de resolução de parâmetros de IA por agente.

Implementa hierarquia de resolução:
    Agente (mais específico) → Sistema → Global → Default (fallback final)

Uso:
    from services.ia_params_resolver import get_ia_params

    params = get_ia_params(db, "gerador_pecas", "geracao")
    # Usa params.modelo, params.temperatura, params.max_tokens

Autor: LAB/PGE-MS
"""

import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

from sqlalchemy.orm import Session

from admin.models import ConfiguracaoIA

logger = logging.getLogger(__name__)


# ============================================
# MAPEAMENTO DE AGENTES POR SISTEMA
# ============================================

# Mapeamento completo: sistema -> {agente_slug -> descrição}
AGENTES_POR_SISTEMA: Dict[str, Dict[str, str]] = {
    "gerador_pecas": {
        "coletor": "Agent1 - Coleta e resume documentos do TJ-MS",
        "deteccao": "Agent2 - Detecta módulos de conteúdo relevantes",
        "geracao": "Agent3 - Gera a peça jurídica final",
    },
    "pedido_calculo": {
        "extracao": "Agent2 - Extrai dados dos PDFs do processo",
        "geracao": "Agent3 - Gera o pedido de cálculo",
        "edicao": "Agent4 - Edita via chat interativo",
    },
    "prestacao_contas": {
        "identificacao": "Agent1 - Identifica petição de prestação de contas",
        "analise": "Agent2 - Análise final da prestação",
    },
    "matriculas": {
        "analise": "Agent1 - Análise visual de matrículas",
        "relatorio": "Agent2 - Gera relatório técnico",
    },
    "assistencia_judiciaria": {
        "relatorio": "Agent1 - Gera relatório de assistência judiciária",
    },
    "relatorio_cumprimento": {
        "analise": "Agent1 - Analisa documentos e gera relatório de cumprimento de sentença",
        "edicao": "Agent2 - Edita relatório via chat interativo",
    },
}


# Defaults globais (fallback final)
DEFAULTS = {
    "modelo": "gemini-3-flash-preview",
    "temperatura": 0.3,
    "max_tokens": None,  # None = usa máximo do modelo
    "thinking_level": "low",  # "low" = reduz latência TTFT sem degradar qualidade significativamente
    # IMPORTANTE: None causava TTFT de 60s+ porque Gemini 3 usa "high" como default
}


# Mapeamento de chaves legadas para o novo padrão
# Formato: {(sistema, chave_legada): agente_slug}
ALIASES_CHAVES: Dict[tuple, str] = {
    # gerador_pecas
    ("gerador_pecas", "modelo_agente1"): "coletor",
    ("gerador_pecas", "modelo_deteccao"): "deteccao",
    ("gerador_pecas", "modelo_geracao"): "geracao",
    ("gerador_pecas", "modelo_agente_final"): "geracao",
    ("gerador_pecas", "temperatura_deteccao"): "deteccao",
    ("gerador_pecas", "temperatura_geracao"): "geracao",
    ("gerador_pecas", "max_tokens_deteccao"): "deteccao",
    ("gerador_pecas", "max_tokens_geracao"): "geracao",

    # pedido_calculo
    ("pedido_calculo", "modelo_extracao"): "extracao",
    ("pedido_calculo", "modelo_geracao"): "geracao",
    ("pedido_calculo", "modelo_edicao"): "edicao",
    ("pedido_calculo", "modelo_agente_final"): "geracao",
    ("pedido_calculo", "temperatura_extracao"): "extracao",
    ("pedido_calculo", "temperatura_geracao"): "geracao",

    # prestacao_contas
    ("prestacao_contas", "modelo_identificacao"): "identificacao",
    ("prestacao_contas", "modelo_analise"): "analise",
    ("prestacao_contas", "temperatura_identificacao"): "identificacao",
    ("prestacao_contas", "temperatura_analise"): "analise",

    # matriculas
    ("matriculas", "modelo_analise"): "analise",
    ("matriculas", "modelo_relatorio"): "relatorio",
    ("matriculas", "temperatura_analise"): "analise",
    ("matriculas", "temperatura_relatorio"): "relatorio",
    ("matriculas", "max_tokens_analise"): "analise",
    ("matriculas", "max_tokens_relatorio"): "relatorio",

    # assistencia_judiciaria
    ("assistencia_judiciaria", "modelo_relatorio"): "relatorio",
    ("assistencia_judiciaria", "temperatura_relatorio"): "relatorio",
    ("assistencia_judiciaria", "max_tokens_relatorio"): "relatorio",

    # relatorio_cumprimento
    ("relatorio_cumprimento", "modelo_analise"): "analise",
    ("relatorio_cumprimento", "modelo_edicao"): "edicao",
    ("relatorio_cumprimento", "temperatura_analise"): "analise",
    ("relatorio_cumprimento", "temperatura_edicao"): "edicao",
}


@dataclass
class IAParams:
    """
    Parâmetros resolvidos para uma chamada de IA.

    Inclui metadados de auditoria indicando a fonte de cada parâmetro.
    """
    # Parâmetros principais
    modelo: str
    temperatura: float
    max_tokens: Optional[int]
    thinking_level: Optional[str] = None

    # Metadados de origem (para auditoria e logging)
    modelo_source: str = "default"  # "agent", "system", "global", "default"
    temperatura_source: str = "default"
    max_tokens_source: str = "default"
    thinking_level_source: str = "default"

    # Contexto
    sistema: str = ""
    agente: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário (para serialização/logging)"""
        return {
            "modelo": self.modelo,
            "temperatura": self.temperatura,
            "max_tokens": self.max_tokens,
            "thinking_level": self.thinking_level,
            "sources": {
                "modelo": self.modelo_source,
                "temperatura": self.temperatura_source,
                "max_tokens": self.max_tokens_source,
                "thinking_level": self.thinking_level_source,
            },
            "sistema": self.sistema,
            "agente": self.agente,
        }

    def log_summary(self) -> str:
        """Retorna string formatada para logging estruturado"""
        sources = f"modelo:{self.modelo_source[:3]}, temp:{self.temperatura_source[:3]}, tokens:{self.max_tokens_source[:3]}"
        max_tok_str = str(self.max_tokens) if self.max_tokens else "auto"
        return (
            f"[IA] sistema={self.sistema} agente={self.agente} "
            f"modelo={self.modelo} temp={self.temperatura} max_tokens={max_tok_str} "
            f"sources={{{sources}}}"
        )


def _get_config_value(db: Session, sistema: str, chave: str) -> Optional[str]:
    """
    Busca valor de configuração no banco de dados.

    Args:
        db: Sessão do SQLAlchemy
        sistema: Nome do sistema ou "global"
        chave: Nome da chave de configuração

    Returns:
        Valor da configuração ou None se não encontrado
    """
    try:
        config = db.query(ConfiguracaoIA).filter(
            ConfiguracaoIA.sistema == sistema,
            ConfiguracaoIA.chave == chave
        ).first()
        return config.valor if config else None
    except Exception as e:
        logger.warning(f"[IAParams] Erro ao buscar config {sistema}.{chave}: {e}")
        return None


def _parse_float(value: Optional[str], default: float) -> float:
    """Converte string para float com fallback para default"""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _parse_int(value: Optional[str], default: Optional[int]) -> Optional[int]:
    """Converte string para int com fallback para default"""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def get_ia_params(
    db: Session,
    sistema: str,
    agente: str,
    defaults_override: Optional[Dict[str, Any]] = None
) -> IAParams:
    """
    Resolve parâmetros de IA com hierarquia de precedência.

    Hierarquia de resolução (mais específico primeiro):
        1. Agente: {param}_{agente_slug} no sistema
        2. Sistema: {param} no sistema
        3. Global: {param} em sistema="global"
        4. Default: valores hardcoded

    Args:
        db: Sessão do SQLAlchemy
        sistema: Nome do sistema (ex: "gerador_pecas", "pedido_calculo")
        agente: Slug do agente (ex: "geracao", "extracao", "analise")
        defaults_override: Dicionário opcional para sobrescrever defaults

    Returns:
        IAParams com valores resolvidos e metadados de origem

    Exemplo:
        params = get_ia_params(db, "gerador_pecas", "geracao")
        response = await gemini_service.generate(
            prompt=prompt,
            model=params.modelo,
            temperature=params.temperatura,
            max_tokens=params.max_tokens,
            thinking_level=params.thinking_level
        )
    """
    # Mescla defaults com override
    defaults = {**DEFAULTS}
    if defaults_override:
        defaults.update(defaults_override)

    result = IAParams(
        modelo=defaults["modelo"],
        temperatura=defaults["temperatura"],
        max_tokens=defaults["max_tokens"],
        thinking_level=defaults.get("thinking_level"),
        sistema=sistema,
        agente=agente,
    )

    # ==== MODELO ====
    # 1. Tenta chave por agente: modelo_{agente}
    valor = _get_config_value(db, sistema, f"modelo_{agente}")
    if valor:
        result.modelo = valor
        result.modelo_source = "agent"
    else:
        # 2. Tenta chave legada do sistema
        chave_legada = _encontrar_chave_legada(sistema, agente, "modelo")
        if chave_legada:
            valor = _get_config_value(db, sistema, chave_legada)
            if valor:
                result.modelo = valor
                result.modelo_source = "system"

        if result.modelo_source == "default":
            # 3. Tenta chave genérica do sistema: modelo
            valor = _get_config_value(db, sistema, "modelo")
            if valor:
                result.modelo = valor
                result.modelo_source = "system"
            else:
                # 4. Tenta global
                valor = _get_config_value(db, "global", "modelo")
                if valor:
                    result.modelo = valor
                    result.modelo_source = "global"

    # ==== TEMPERATURA ====
    # 1. Tenta chave por agente: temperatura_{agente}
    valor = _get_config_value(db, sistema, f"temperatura_{agente}")
    if valor:
        result.temperatura = _parse_float(valor, defaults["temperatura"])
        result.temperatura_source = "agent"
    else:
        # 2. Tenta chave legada do sistema
        chave_legada = _encontrar_chave_legada(sistema, agente, "temperatura")
        if chave_legada:
            valor = _get_config_value(db, sistema, chave_legada)
            if valor:
                result.temperatura = _parse_float(valor, defaults["temperatura"])
                result.temperatura_source = "system"

        if result.temperatura_source == "default":
            # 3. Tenta chave genérica do sistema: temperatura
            valor = _get_config_value(db, sistema, "temperatura")
            if valor:
                result.temperatura = _parse_float(valor, defaults["temperatura"])
                result.temperatura_source = "system"
            else:
                # 4. Tenta global
                valor = _get_config_value(db, "global", "temperatura")
                if valor:
                    result.temperatura = _parse_float(valor, defaults["temperatura"])
                    result.temperatura_source = "global"

    # ==== MAX_TOKENS ====
    # 1. Tenta chave por agente: max_tokens_{agente}
    valor = _get_config_value(db, sistema, f"max_tokens_{agente}")
    if valor:
        result.max_tokens = _parse_int(valor, defaults["max_tokens"])
        result.max_tokens_source = "agent"
    else:
        # 2. Tenta chave legada do sistema
        chave_legada = _encontrar_chave_legada(sistema, agente, "max_tokens")
        if chave_legada:
            valor = _get_config_value(db, sistema, chave_legada)
            if valor:
                result.max_tokens = _parse_int(valor, defaults["max_tokens"])
                result.max_tokens_source = "system"

        if result.max_tokens_source == "default":
            # 3. Tenta chave genérica do sistema: max_tokens
            valor = _get_config_value(db, sistema, "max_tokens")
            if valor:
                result.max_tokens = _parse_int(valor, defaults["max_tokens"])
                result.max_tokens_source = "system"
            else:
                # 4. Tenta global
                valor = _get_config_value(db, "global", "max_tokens")
                if valor:
                    result.max_tokens = _parse_int(valor, defaults["max_tokens"])
                    result.max_tokens_source = "global"

    # ==== THINKING_LEVEL ====
    # 1. Tenta chave por agente: thinking_level_{agente}
    valor = _get_config_value(db, sistema, f"thinking_level_{agente}")
    if valor and valor.strip():
        result.thinking_level = valor.strip().lower()
        result.thinking_level_source = "agent"
    else:
        # 2. Tenta chave genérica do sistema: thinking_level
        valor = _get_config_value(db, sistema, "thinking_level")
        if valor and valor.strip():
            result.thinking_level = valor.strip().lower()
            result.thinking_level_source = "system"
        else:
            # 3. Tenta global
            valor = _get_config_value(db, "global", "thinking_level")
            if valor and valor.strip():
                result.thinking_level = valor.strip().lower()
                result.thinking_level_source = "global"

    # Valida thinking_level
    if result.thinking_level and result.thinking_level not in ("minimal", "low", "medium", "high"):
        logger.warning(f"[IAParams] thinking_level inválido '{result.thinking_level}', usando None")
        result.thinking_level = None

    # Log estruturado
    logger.info(result.log_summary())

    return result


def _encontrar_chave_legada(sistema: str, agente: str, param: str) -> Optional[str]:
    """
    Encontra chave legada correspondente a um parâmetro.

    Args:
        sistema: Nome do sistema
        agente: Slug do agente
        param: Tipo de parâmetro ("modelo", "temperatura", "max_tokens")

    Returns:
        Nome da chave legada ou None
    """
    # Busca no mapeamento de aliases
    for (sist, chave), slug in ALIASES_CHAVES.items():
        if sist == sistema and slug == agente and chave.startswith(param):
            return chave
    return None


def listar_agentes(sistema: str) -> Dict[str, str]:
    """
    Lista os agentes disponíveis para um sistema.

    Args:
        sistema: Nome do sistema

    Returns:
        Dict com {agente_slug: descrição}
    """
    return AGENTES_POR_SISTEMA.get(sistema, {})


def listar_sistemas() -> List[str]:
    """
    Lista todos os sistemas disponíveis.

    Returns:
        Lista de nomes de sistemas
    """
    return list(AGENTES_POR_SISTEMA.keys())


def get_config_per_agent(db: Session, sistema: str) -> Dict[str, IAParams]:
    """
    Obtém configurações de todos os agentes de um sistema.

    Útil para a interface admin mostrar configurações por agente.

    Args:
        db: Sessão do SQLAlchemy
        sistema: Nome do sistema

    Returns:
        Dict com {agente_slug: IAParams}
    """
    agentes = listar_agentes(sistema)
    resultado = {}

    for agente_slug in agentes:
        resultado[agente_slug] = get_ia_params(db, sistema, agente_slug)

    return resultado


# ============================================
# EXPORTS
# ============================================

__all__ = [
    "IAParams",
    "get_ia_params",
    "listar_agentes",
    "listar_sistemas",
    "get_config_per_agent",
    "AGENTES_POR_SISTEMA",
    "DEFAULTS",
]
