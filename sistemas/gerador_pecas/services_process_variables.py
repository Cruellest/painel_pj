# sistemas/gerador_pecas/services_process_variables.py
"""
Serviço de variáveis derivadas do processo XML.

Este módulo implementa:
- Definição de variáveis derivadas de DadosProcesso
- Resolução de variáveis no runtime (sem LLM)
- Variáveis calculadas a partir do XML do processo (não de PDFs)

Diferente de ExtractionVariable (extraído de PDFs via IA),
estas variáveis são calculadas deterministicamente do XML do processo.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from sistemas.gerador_pecas.agente_tjms import DadosProcesso

logger = logging.getLogger(__name__)


@dataclass
class ProcessVariableDefinition:
    """
    Definição de uma variável derivada do processo.

    Attributes:
        slug: Identificador único (snake_case)
        label: Nome legível para UI
        tipo: Tipo de dado (boolean, date, number, text)
        descricao: Descrição do que a variável representa
        resolver: Função que calcula o valor a partir de DadosProcesso
    """
    slug: str
    label: str
    tipo: str  # boolean, date, number, text
    descricao: str
    resolver: Callable[['DadosProcesso'], Any]


class ProcessVariableResolver:
    """
    Resolve variáveis derivadas a partir de DadosProcesso.

    Uso típico:
        resolver = ProcessVariableResolver(dados_processo)
        variaveis = resolver.resolver_todas()
        # variaveis = {"processo_ajuizado_apos_2024_04_19": True, ...}
    """

    # Registry de definições de variáveis
    DEFINITIONS: Dict[str, ProcessVariableDefinition] = {}

    def __init__(self, dados_processo: Optional['DadosProcesso']):
        """
        Args:
            dados_processo: Dados estruturados extraídos do XML do processo
        """
        self.dados_processo = dados_processo

    @classmethod
    def register(cls, definition: ProcessVariableDefinition) -> None:
        """
        Registra uma nova definição de variável.

        Args:
            definition: Definição da variável a registrar
        """
        cls.DEFINITIONS[definition.slug] = definition
        logger.debug(f"Variável de processo registrada: {definition.slug}")

    @classmethod
    def get_all_definitions(cls) -> List[ProcessVariableDefinition]:
        """Retorna todas as definições registradas."""
        return list(cls.DEFINITIONS.values())

    @classmethod
    def get_definition(cls, slug: str) -> Optional[ProcessVariableDefinition]:
        """Retorna uma definição específica pelo slug."""
        return cls.DEFINITIONS.get(slug)

    def resolver_todas(self) -> Dict[str, Any]:
        """
        Resolve TODAS as variáveis registradas.

        Returns:
            Dicionário {slug: valor} com todas as variáveis resolvidas.
            Variáveis que falham retornam None.
        """
        if not self.dados_processo:
            return {}

        resultado = {}
        for slug, definition in self.DEFINITIONS.items():
            try:
                valor = definition.resolver(self.dados_processo)
                resultado[slug] = valor
                logger.debug(f"Variável '{slug}' resolvida: {valor}")
            except Exception as e:
                logger.warning(f"Erro ao resolver variável '{slug}': {e}")
                resultado[slug] = None

        return resultado

    def resolver(self, slug: str) -> Any:
        """
        Resolve uma variável específica.

        Args:
            slug: Identificador da variável

        Returns:
            Valor da variável ou None se não encontrada/erro
        """
        if not self.dados_processo:
            return None

        definition = self.DEFINITIONS.get(slug)
        if not definition:
            logger.warning(f"Variável de processo não encontrada: {slug}")
            return None

        try:
            return definition.resolver(self.dados_processo)
        except Exception as e:
            logger.warning(f"Erro ao resolver variável '{slug}': {e}")
            return None


# =============================================================================
# DEFINIÇÕES DE VARIÁVEIS MVP
# =============================================================================

def _resolver_ajuizado_apos_tema_106(dados: 'DadosProcesso') -> Optional[bool]:
    """
    Verifica se o processo foi ajuizado APÓS 19/04/2024.

    Contexto: Tema 106 STF - modulação de efeitos.
    A data 19/04/2024 é relevante para aplicação de teses jurídicas
    relacionadas à modulação de efeitos do Tema 106.

    Args:
        dados: Dados do processo

    Returns:
        True se ajuizado APÓS 19/04/2024
        False se ajuizado ATÉ 19/04/2024 (inclusive)
        None se data_ajuizamento não disponível
    """
    if not dados.data_ajuizamento:
        return None

    # Data de corte: 19/04/2024
    data_corte = date(2024, 4, 19)

    # Extrai apenas a data (sem hora) para comparação
    data_processo = dados.data_ajuizamento.date()

    # É MAIOR QUE (não maior ou igual)
    return data_processo > data_corte


def _resolver_valor_causa_numerico(dados: 'DadosProcesso') -> Optional[float]:
    """
    Converte o valor da causa para número.

    Suporta formatos:
    - "250000" -> 250000.0
    - "250.000,00" -> 250000.0
    - "R$ 250.000,00" -> 250000.0

    Args:
        dados: Dados do processo

    Returns:
        Valor da causa como float, ou None se não disponível/inválido
    """
    if not dados.valor_causa:
        return None

    try:
        valor = dados.valor_causa

        # Remove símbolos de moeda e espaços
        valor = valor.replace("R$", "").replace("$", "").strip()

        # Detecta formato brasileiro (ponto como separador de milhar, vírgula como decimal)
        if "." in valor and "," in valor:
            # Remove pontos (milhares) e substitui vírgula por ponto (decimal)
            valor = valor.replace(".", "").replace(",", ".")
        elif "," in valor and "." not in valor:
            # Apenas vírgula: pode ser decimal brasileiro
            partes = valor.split(",")
            if len(partes) == 2 and len(partes[1]) <= 2:
                # Vírgula como decimal
                valor = valor.replace(",", ".")
            else:
                # Vírgula como milhar
                valor = valor.replace(",", "")

        return float(valor)
    except (ValueError, TypeError):
        return None


def _resolver_estado_polo_passivo(dados: 'DadosProcesso') -> Optional[bool]:
    """
    Verifica se o Estado está no polo passivo (réu).

    Considera como "Estado":
    - Nomes contendo "Estado de Mato Grosso do Sul"
    - Nomes contendo "Estado do Mato Grosso do Sul"
    - Siglas: ESTADO DE MS, ESTADO-MS, etc.

    Args:
        dados: Dados do processo

    Returns:
        True se Estado está no polo passivo
        False se Estado NÃO está no polo passivo
        None se não há partes no polo passivo
    """
    if not dados.polo_passivo:
        return None

    termos_estado = [
        "estado de mato grosso do sul",
        "estado do mato grosso do sul",
        "estado de ms",
        "estado-ms",
        "estado ms"
    ]

    for parte in dados.polo_passivo:
        nome_lower = parte.nome.lower()
        for termo in termos_estado:
            if termo in nome_lower:
                return True

    return False


def _resolver_autor_com_assistencia_judiciaria(dados: 'DadosProcesso') -> Optional[bool]:
    """
    Verifica se algum autor (polo ativo) tem assistência judiciária gratuita.

    Args:
        dados: Dados do processo

    Returns:
        True se algum autor tem assistência judiciária
        False se nenhum autor tem assistência judiciária
        None se não há partes no polo ativo
    """
    if not dados.polo_ativo:
        return None

    for parte in dados.polo_ativo:
        if parte.assistencia_judiciaria:
            return True

    return False


def _resolver_autor_com_defensoria(dados: 'DadosProcesso') -> Optional[bool]:
    """
    Verifica se algum autor é representado pela Defensoria Pública.

    Args:
        dados: Dados do processo

    Returns:
        True se algum autor é representado por Defensoria
        False caso contrário
        None se não há partes no polo ativo
    """
    if not dados.polo_ativo:
        return None

    for parte in dados.polo_ativo:
        if parte.tipo_representante and "defensoria" in parte.tipo_representante.lower():
            return True

    return False


# Lista de municípios de Mato Grosso do Sul
MUNICIPIOS_MS = [
    "Agua Clara", "Alcinopolis", "Amambai", "Anastacio", "Anaurilandia",
    "Angelica", "Antonio Joao", "Aparecida do Taboado", "Aquidauana", "Aral Moreira",
    "Bandeirantes", "Bataguassu", "Bataypora", "Bela Vista", "Bodoquena",
    "Bonito", "Brasilandia", "Caarapo", "Camapua", "Campo Grande",
    "Caracol", "Cassilandia", "Chapadao do Sul", "Corguinho", "Coronel Sapucaia",
    "Corumba", "Costa Rica", "Coxim", "Deodapolis", "Dois Irmaos do Buriti",
    "Douradina", "Dourados", "Eldorado", "Fatima do Sul", "Figueirao",
    "Gloria de Dourados", "Guia Lopes da Laguna", "Iguatemi", "Inocencia", "Itapora",
    "Itaquirai", "Ivinhema", "Japora", "Jaraguari", "Jardim",
    "Jatei", "Juti", "Ladario", "Laguna Carapa", "Maracaju",
    "Miranda", "Mundo Novo", "Navirai", "Nioaque", "Nova Alvorada do Sul",
    "Nova Andradina", "Novo Horizonte do Sul", "Paraiso das Aguas", "Paranaiba", "Paranhos",
    "Pedro Gomes", "Ponta Pora", "Porto Murtinho", "Ribas do Rio Pardo", "Rio Brilhante",
    "Rio Negro", "Rio Verde de Mato Grosso", "Rochedo", "Santa Rita do Pardo", "Sao Gabriel do Oeste",
    "Selviria", "Sete Quedas", "Sidrolandia", "Sonora", "Tacuru",
    "Taquarussu", "Terenos", "Tres Lagoas", "Vicentina"
]


def _normalizar_texto(texto: str) -> str:
    """Remove acentos e converte para minúsculas."""
    import unicodedata
    # Remove acentos
    texto_normalizado = unicodedata.normalize('NFD', texto)
    texto_sem_acentos = ''.join(c for c in texto_normalizado if unicodedata.category(c) != 'Mn')
    return texto_sem_acentos.lower()


def _resolver_municipio_polo_passivo(dados: 'DadosProcesso') -> Optional[bool]:
    """
    Verifica se algum município de MS está no polo passivo.

    Detecta padrões como:
    - "Município de Bandeirantes/MS"
    - "Município de Campo Grande"
    - "Prefeitura Municipal de Dourados"
    - Nome direto do município

    Args:
        dados: Dados do processo

    Returns:
        True se algum município de MS está no polo passivo
        False se nenhum município de MS está no polo passivo
        None se não há partes no polo passivo
    """
    if not dados.polo_passivo:
        return None

    # Normaliza a lista de municípios para comparação
    municipios_normalizados = [_normalizar_texto(m) for m in MUNICIPIOS_MS]

    for parte in dados.polo_passivo:
        nome = parte.nome
        nome_normalizado = _normalizar_texto(nome)

        # Padrão 1: "Município de X" ou "Municipio de X"
        if "municipio de" in nome_normalizado:
            # Extrai o nome após "município de"
            partes = nome_normalizado.split("municipio de")
            if len(partes) > 1:
                nome_municipio = partes[1].strip()
                # Remove sufixos como "/MS", "-MS", " MS"
                nome_municipio = nome_municipio.replace("/ms", "").replace("-ms", "").replace(" ms", "").strip()
                # Verifica se é um município de MS
                for mun in municipios_normalizados:
                    if mun in nome_municipio or nome_municipio in mun:
                        return True

        # Padrão 2: "Prefeitura Municipal de X"
        elif "prefeitura" in nome_normalizado and "municipal" in nome_normalizado:
            for mun in municipios_normalizados:
                if mun in nome_normalizado:
                    return True

        # Padrão 3: Nome direto do município (menos comum)
        else:
            for mun in municipios_normalizados:
                # Verifica match exato ou parcial
                if mun in nome_normalizado:
                    # Evita falsos positivos: verifica se é pessoa jurídica
                    if parte.tipo_pessoa == "juridica":
                        return True

    return False


# =============================================================================
# REGISTRO DAS VARIÁVEIS
# =============================================================================

# Variável principal para Tema 106 STF
ProcessVariableResolver.register(ProcessVariableDefinition(
    slug="processo_ajuizado_apos_2024_04_19",
    label="Processo Ajuizado Após 19/04/2024",
    tipo="boolean",
    descricao="Tema 106 STF - modulação de efeitos. True se ajuizado APÓS 19/04/2024.",
    resolver=_resolver_ajuizado_apos_tema_106
))

# Valor da causa como número
ProcessVariableResolver.register(ProcessVariableDefinition(
    slug="valor_causa_numerico",
    label="Valor da Causa (Numérico)",
    tipo="number",
    descricao="Valor da causa convertido para número (float).",
    resolver=_resolver_valor_causa_numerico
))

# Estado no polo passivo
ProcessVariableResolver.register(ProcessVariableDefinition(
    slug="estado_polo_passivo",
    label="Estado no Polo Passivo",
    tipo="boolean",
    descricao="True se o Estado de MS está no polo passivo do processo.",
    resolver=_resolver_estado_polo_passivo
))

# Assistência judiciária
ProcessVariableResolver.register(ProcessVariableDefinition(
    slug="autor_com_assistencia_judiciaria",
    label="Autor com Assistência Judiciária",
    tipo="boolean",
    descricao="True se algum autor tem assistência judiciária gratuita.",
    resolver=_resolver_autor_com_assistencia_judiciaria
))

# Representação por Defensoria
ProcessVariableResolver.register(ProcessVariableDefinition(
    slug="autor_com_defensoria",
    label="Autor Representado por Defensoria",
    tipo="boolean",
    descricao="True se algum autor é representado pela Defensoria Pública.",
    resolver=_resolver_autor_com_defensoria
))

# Município no polo passivo
ProcessVariableResolver.register(ProcessVariableDefinition(
    slug="municipio_polo_passivo",
    label="Município no Polo Passivo",
    tipo="boolean",
    descricao="True se algum município de MS está no polo passivo do processo.",
    resolver=_resolver_municipio_polo_passivo
))
