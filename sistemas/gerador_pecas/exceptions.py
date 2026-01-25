# sistemas/gerador_pecas/exceptions.py
"""
Exceções customizadas do sistema Gerador de Peças.

Este módulo define exceções específicas do domínio para melhor
tratamento de erros e mensagens mais claras.
"""


class GeradorPecasError(Exception):
    """Exceção base para erros do Gerador de Peças."""

    def __init__(self, message: str, code: str = None, details: dict = None):
        super().__init__(message)
        self.message = message
        self.code = code or "GERADOR_ERROR"
        self.details = details or {}


# =============================================================================
# ERROS DE INTEGRAÇÃO
# =============================================================================

class TJMSError(GeradorPecasError):
    """Erro de comunicação com o TJ-MS."""

    def __init__(self, message: str, details: dict = None):
        super().__init__(message, "TJMS_ERROR", details)


class TJMSTimeoutError(TJMSError):
    """Timeout na comunicação com o TJ-MS."""

    def __init__(self, message: str = "Timeout na consulta ao TJ-MS", details: dict = None):
        super().__init__(message, details)
        self.code = "TJMS_TIMEOUT"


class TJMSProcessoNaoEncontradoError(TJMSError):
    """Processo não encontrado no TJ-MS."""

    def __init__(self, numero_cnj: str):
        super().__init__(
            f"Processo {numero_cnj} não encontrado no TJ-MS",
            {"numero_cnj": numero_cnj}
        )
        self.code = "TJMS_PROCESSO_NAO_ENCONTRADO"


class GeminiError(GeradorPecasError):
    """Erro de comunicação com o Gemini."""

    def __init__(self, message: str, details: dict = None):
        super().__init__(message, "GEMINI_ERROR", details)


class GeminiTimeoutError(GeminiError):
    """Timeout na comunicação com o Gemini."""

    def __init__(self, message: str = "Timeout na chamada ao Gemini", details: dict = None):
        super().__init__(message, details)
        self.code = "GEMINI_TIMEOUT"


class GeminiRateLimitError(GeminiError):
    """Rate limit atingido no Gemini."""

    def __init__(self, message: str = "Limite de requisições atingido", details: dict = None):
        super().__init__(message, details)
        self.code = "GEMINI_RATE_LIMIT"


# =============================================================================
# ERROS DE VALIDAÇÃO
# =============================================================================

class ValidationError(GeradorPecasError):
    """Erro de validação de dados."""

    def __init__(self, message: str, field: str = None, details: dict = None):
        super().__init__(message, "VALIDATION_ERROR", details)
        self.field = field


class TipoPecaInvalidoError(ValidationError):
    """Tipo de peça inválido ou não suportado."""

    def __init__(self, tipo_peca: str):
        super().__init__(
            f"Tipo de peça '{tipo_peca}' não é válido ou não está configurado",
            field="tipo_peca",
            details={"tipo_peca": tipo_peca}
        )
        self.code = "TIPO_PECA_INVALIDO"


class GrupoNaoPermitidoError(ValidationError):
    """Usuário não tem acesso ao grupo de prompts."""

    def __init__(self, group_id: int, user_id: int):
        super().__init__(
            f"Usuário não tem acesso ao grupo de prompts {group_id}",
            field="group_id",
            details={"group_id": group_id, "user_id": user_id}
        )
        self.code = "GRUPO_NAO_PERMITIDO"


class CNJInvalidoError(ValidationError):
    """Número CNJ inválido."""

    def __init__(self, numero_cnj: str):
        super().__init__(
            f"Número CNJ '{numero_cnj}' é inválido",
            field="numero_cnj",
            details={"numero_cnj": numero_cnj}
        )
        self.code = "CNJ_INVALIDO"


# =============================================================================
# ERROS DE PROCESSAMENTO
# =============================================================================

class ProcessamentoError(GeradorPecasError):
    """Erro durante o processamento da peça."""

    def __init__(self, message: str, etapa: str = None, details: dict = None):
        super().__init__(message, "PROCESSAMENTO_ERROR", details)
        self.etapa = etapa


class Agente1Error(ProcessamentoError):
    """Erro no Agente 1 (Coletor)."""

    def __init__(self, message: str, details: dict = None):
        super().__init__(message, etapa="agente1", details=details)
        self.code = "AGENTE1_ERROR"


class Agente2Error(ProcessamentoError):
    """Erro no Agente 2 (Detector)."""

    def __init__(self, message: str, details: dict = None):
        super().__init__(message, etapa="agente2", details=details)
        self.code = "AGENTE2_ERROR"


class Agente3Error(ProcessamentoError):
    """Erro no Agente 3 (Gerador)."""

    def __init__(self, message: str, details: dict = None):
        super().__init__(message, etapa="agente3", details=details)
        self.code = "AGENTE3_ERROR"


class DocumentoError(ProcessamentoError):
    """Erro no processamento de documento."""

    def __init__(self, message: str, documento_id: str = None, details: dict = None):
        details = details or {}
        if documento_id:
            details["documento_id"] = documento_id
        super().__init__(message, etapa="documento", details=details)
        self.code = "DOCUMENTO_ERROR"


class ExtracaoError(ProcessamentoError):
    """Erro na extração de dados do documento."""

    def __init__(self, message: str, details: dict = None):
        super().__init__(message, etapa="extracao", details=details)
        self.code = "EXTRACAO_ERROR"


class DocxConversionError(ProcessamentoError):
    """Erro na conversão para DOCX."""

    def __init__(self, message: str, details: dict = None):
        super().__init__(message, etapa="docx", details=details)
        self.code = "DOCX_ERROR"


# =============================================================================
# ERROS DE REGRAS
# =============================================================================

class RegraError(GeradorPecasError):
    """Erro na avaliação de regras."""

    def __init__(self, message: str, regra_id: int = None, details: dict = None):
        details = details or {}
        if regra_id:
            details["regra_id"] = regra_id
        super().__init__(message, "REGRA_ERROR", details)


class RegraInvalidaError(RegraError):
    """Regra com sintaxe ou estrutura inválida."""

    def __init__(self, message: str, regra_id: int = None, details: dict = None):
        super().__init__(message, regra_id, details)
        self.code = "REGRA_INVALIDA"


class VariavelNaoEncontradaError(RegraError):
    """Variável necessária para regra não encontrada."""

    def __init__(self, variavel: str, regra_id: int = None):
        super().__init__(
            f"Variável '{variavel}' não encontrada para avaliação da regra",
            regra_id,
            {"variavel": variavel}
        )
        self.code = "VARIAVEL_NAO_ENCONTRADA"
