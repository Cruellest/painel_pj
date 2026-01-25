# services/tjms/constants.py
"""
Constantes e enums para integração com TJ-MS.

Centraliza todos os códigos de tipos de documento, movimentos e outros
valores fixos usados na comunicação com o TJ-MS.

Autor: LAB/PGE-MS
"""

from enum import IntEnum
from typing import Set


# ==================================================
# TIPOS DE DOCUMENTO TJ-MS
# ==================================================

class TipoDocumentoTJMS(IntEnum):
    """
    Códigos de tipos de documento do TJ-MS (MNI).

    Estes códigos são retornados no campo tipoDocumento
    das respostas SOAP do TJ-MS.
    """
    # Documentos principais
    PETICAO_INICIAL = 18
    CONTESTACAO = 71
    REPLICA = 72
    SENTENCA = 85
    ACORDAO = 3
    DECISAO_INTERLOCUTORIA = 4

    # Documentos probatórios
    LAUDO_PERICIAL = 8369
    PARECER_CATES = 207  # Câmara Técnica em Saúde
    PARECER_NAT = 8451  # Núcleo de Apoio Técnico
    PARECER_NAT_ORIGEM = 9636  # Parecer NAT de Origem
    NOTA_TECNICA_NATJUS = 59
    NOTA_TECNICA_NATJUS_ALT = 8490

    # Procuração e representação
    PROCURACAO = 7

    # Administrativos (geralmente excluídos)
    CERTIDAO_DIVERSA = 10
    CERTIDAO = 2
    OFICIO = 13
    OFICIO_EXPEDIDO = 9508
    ATO_ORDINATORIO = 8
    ATO_ORDINATORIO_PRATICADO = 53
    COMUNICACAO = 8449
    COMUNICACAO_INTERNA = 8450
    ATA = 5
    TERMO = 9614
    OUTROS = 9999
    ALVARA = 192
    ALVARA_DIVERSOS = 8494
    CERTIDAO_TRANSITO_JULGADO = 8433
    OUTROS_DOCUMENTOS = 8500
    TERMOS_DIVERSOS = 9558

    # Recursos
    RECURSO_APELACAO = 99
    RECURSO_AGRAVO = 100
    CONTRARRAZOES = 101


# ==================================================
# CÓDIGOS DE MOVIMENTO TJ-MS
# ==================================================

class CodigoMovimento(IntEnum):
    """
    Códigos de movimento processual (CNJ).

    Alguns códigos importantes para lógica de negócio.
    """
    DISTRIBUICAO = 132
    JUNTADA_PETICAO = 485
    JUNTADA_DOCUMENTO = 581
    CONCLUSOS_PARA_JULGAMENTO = 51
    SENTENCA_PROFERIDA = 22
    ACORDAO_PROFERIDO = 21
    TRANSITO_EM_JULGADO = 848
    ARQUIVAMENTO = 246
    CITACAO = 14
    INTIMACAO = 12


# ==================================================
# CONJUNTOS PRÉ-DEFINIDOS
# ==================================================

# Documentos administrativos que geralmente são excluídos da análise
DOCUMENTOS_ADMINISTRATIVOS: Set[int] = {
    TipoDocumentoTJMS.CERTIDAO_DIVERSA,
    TipoDocumentoTJMS.CERTIDAO,
    TipoDocumentoTJMS.OFICIO,
    TipoDocumentoTJMS.OFICIO_EXPEDIDO,
    TipoDocumentoTJMS.ATO_ORDINATORIO,
    TipoDocumentoTJMS.ATO_ORDINATORIO_PRATICADO,
    TipoDocumentoTJMS.COMUNICACAO,
    TipoDocumentoTJMS.COMUNICACAO_INTERNA,
    TipoDocumentoTJMS.ATA,
    TipoDocumentoTJMS.TERMO,
    TipoDocumentoTJMS.OUTROS,
    TipoDocumentoTJMS.ALVARA,
    TipoDocumentoTJMS.ALVARA_DIVERSOS,
    TipoDocumentoTJMS.CERTIDAO_TRANSITO_JULGADO,
    TipoDocumentoTJMS.OUTROS_DOCUMENTOS,
    TipoDocumentoTJMS.TERMOS_DIVERSOS,
}

# Documentos que devem ser enviados integralmente para análise (sem extração JSON)
DOCUMENTOS_TEXTO_INTEGRAL: Set[int] = {
    TipoDocumentoTJMS.PARECER_CATES,
    TipoDocumentoTJMS.LAUDO_PERICIAL,
}

# Documentos técnicos de saúde (NAT/NATJus)
DOCUMENTOS_TECNICOS_SAUDE: Set[int] = {
    TipoDocumentoTJMS.PARECER_NAT,
    TipoDocumentoTJMS.PARECER_NAT_ORIGEM,
    TipoDocumentoTJMS.NOTA_TECNICA_NATJUS,
    TipoDocumentoTJMS.NOTA_TECNICA_NATJUS_ALT,
    TipoDocumentoTJMS.PARECER_CATES,
}

# Documentos de decisão
DOCUMENTOS_DECISAO: Set[int] = {
    TipoDocumentoTJMS.SENTENCA,
    TipoDocumentoTJMS.ACORDAO,
    TipoDocumentoTJMS.DECISAO_INTERLOCUTORIA,
}


# ==================================================
# FUNÇÕES AUXILIARES
# ==================================================

def is_documento_administrativo(tipo: int) -> bool:
    """Verifica se o documento é administrativo (certidão, ofício, etc)."""
    return tipo in DOCUMENTOS_ADMINISTRATIVOS


def is_documento_decisao(tipo: int) -> bool:
    """Verifica se o documento é uma decisão judicial."""
    return tipo in DOCUMENTOS_DECISAO


def is_documento_tecnico_saude(tipo: int) -> bool:
    """Verifica se o documento é técnico de saúde (NAT/NATJus)."""
    return tipo in DOCUMENTOS_TECNICOS_SAUDE


def get_nome_tipo_documento(tipo: int) -> str:
    """
    Retorna o nome legível do tipo de documento.

    Args:
        tipo: Código do tipo de documento

    Returns:
        Nome do documento ou "Desconhecido (código)"
    """
    try:
        return TipoDocumentoTJMS(tipo).name.replace("_", " ").title()
    except ValueError:
        return f"Desconhecido ({tipo})"


def get_nome_movimento(codigo: int) -> str:
    """
    Retorna o nome legível do movimento processual.

    Args:
        codigo: Código do movimento

    Returns:
        Nome do movimento ou "Desconhecido (código)"
    """
    try:
        return CodigoMovimento(codigo).name.replace("_", " ").title()
    except ValueError:
        return f"Movimento {codigo}"


__all__ = [
    # Enums
    "TipoDocumentoTJMS",
    "CodigoMovimento",
    # Conjuntos
    "DOCUMENTOS_ADMINISTRATIVOS",
    "DOCUMENTOS_TEXTO_INTEGRAL",
    "DOCUMENTOS_TECNICOS_SAUDE",
    "DOCUMENTOS_DECISAO",
    # Funções
    "is_documento_administrativo",
    "is_documento_decisao",
    "is_documento_tecnico_saude",
    "get_nome_tipo_documento",
    "get_nome_movimento",
]
