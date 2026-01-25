# sistemas/gerador_pecas/constants.py
"""
Constantes do sistema Gerador de Peças.

Este módulo centraliza todas as constantes usadas pelo sistema,
facilitando a manutenção e evitando magic numbers/strings espalhados.
"""

from typing import Dict, Set, FrozenSet

# =============================================================================
# TIMEOUTS (em segundos)
# =============================================================================

# Timeout para detecção de módulos pelo Agente 2
TIMEOUT_AG2_DETECCAO: int = 60

# Timeout mais curto para fast path (sem LLM)
TIMEOUT_AG2_FAST_PATH: int = 30

# Timeout para chamadas ao TJ-MS
TIMEOUT_TJMS: int = 30

# Timeout para chamadas ao Gemini
TIMEOUT_GEMINI: int = 120

# Timeout para geração de DOCX
TIMEOUT_DOCX: int = 60


# =============================================================================
# MODELOS DE IA
# =============================================================================

# Modelo padrão para Agente 1 (Coletor)
MODELO_AGENTE1_PADRAO: str = "gemini-3-flash-preview"

# Modelo padrão para Agente 2 (Detector)
MODELO_AGENTE2_PADRAO: str = "gemini-3-flash-preview"

# Modelo padrão para Agente 3 (Gerador)
MODELO_AGENTE3_PADRAO: str = "gemini-3-pro-preview"


# =============================================================================
# CÓDIGOS DE DOCUMENTO TJ-MS
# =============================================================================

# Códigos de documentos que devem pegar apenas o primeiro (petição inicial)
CODIGOS_PRIMEIRO_DOC: FrozenSet[int] = frozenset({500, 510, 9500})

# Códigos de documentos NAT (Parecer Técnico)
CODIGOS_NAT: FrozenSet[int] = frozenset({60, 61, 62, 63, 64, 65, 9060})

# Códigos ignorados (não processar)
CODIGOS_IGNORADOS: FrozenSet[int] = frozenset({10})  # Código 10 = Documento anexo genérico


# =============================================================================
# LIMITES DE PROCESSAMENTO
# =============================================================================

# Número máximo de workers para processamento paralelo
MAX_WORKERS_DEFAULT: int = 30

# Limite de documentos por processo antes de paginar
LIMITE_DOCUMENTOS_POR_PROCESSO: int = 100

# Limite de páginas por documento para extração
LIMITE_PAGINAS_POR_DOCUMENTO: int = 50

# Janela de agrupamento de documentos (em horas)
JANELA_AGRUPAMENTO_HORAS: int = 2


# =============================================================================
# SALÁRIOS MÍNIMOS E LIMITES FINANCEIROS
# =============================================================================

# Salário mínimo de referência (2024)
SALARIO_MINIMO: float = 1621.0

# Limite de 60 salários mínimos
LIMITE_60_SM: float = SALARIO_MINIMO * 60  # R$ 97.260,00

# Limite de 210 salários mínimos
LIMITE_210_SM: float = SALARIO_MINIMO * 210  # R$ 340.410,00


# =============================================================================
# CATEGORIAS DE PROMPTS
# =============================================================================

# Ordem padrão das categorias de conteúdo
ORDEM_CATEGORIAS_DEFAULT: Dict[str, int] = {
    "Preliminar": 1,
    "Merito": 2,
    "Eventualidade": 3,
    "Honorarios": 4,
}

# Tipos de módulos de prompt
TIPO_MODULO_SISTEMA: str = "sistema"
TIPO_MODULO_PECA: str = "peca"
TIPO_MODULO_CONTEUDO: str = "conteudo"


# =============================================================================
# MODOS DE ATIVAÇÃO
# =============================================================================

# Modo de ativação por LLM (tradicional)
MODO_ATIVACAO_LLM: str = "llm"

# Modo de ativação determinístico (regras)
MODO_ATIVACAO_DETERMINISTICO: str = "deterministico"

# Modo misto (determinístico + LLM para o resto)
MODO_ATIVACAO_MISTO: str = "misto"

# Fast path (100% determinístico, pula LLM)
MODO_ATIVACAO_FAST_PATH: str = "fast_path"


# =============================================================================
# FORMATOS DE SAÍDA
# =============================================================================

# Formato JSON para resumos
FORMATO_SAIDA_JSON: str = "json"

# Formato Markdown para resumos
FORMATO_SAIDA_MD: str = "md"


# =============================================================================
# MENSAGENS DE ERRO PADRONIZADAS
# =============================================================================

ERRO_TJMS_INDISPONIVEL: str = "Serviço TJ-MS indisponível. Tente novamente mais tarde."
ERRO_GEMINI_INDISPONIVEL: str = "Serviço de IA indisponível. Tente novamente mais tarde."
ERRO_PROCESSO_NAO_ENCONTRADO: str = "Processo não encontrado no TJ-MS."
ERRO_DOCUMENTO_NAO_ENCONTRADO: str = "Documento não encontrado."
ERRO_USUARIO_SEM_GRUPO: str = "Usuário sem grupo de prompts configurado."
ERRO_TIPO_PECA_INVALIDO: str = "Tipo de peça inválido ou não suportado."
ERRO_TIMEOUT_GERACAO: str = "Timeout na geração da peça. Tente novamente."
