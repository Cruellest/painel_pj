# sistemas/cumprimento_beta/exceptions.py
"""
Exceções específicas do módulo Cumprimento de Sentença Beta
"""


class CumprimentoBetaError(Exception):
    """Erro base do módulo"""
    pass


class AcessoNegadoError(CumprimentoBetaError):
    """Usuário não tem acesso ao beta"""
    pass


class SessaoNaoEncontradaError(CumprimentoBetaError):
    """Sessão não existe ou não pertence ao usuário"""
    pass


class ProcessoInvalidoError(CumprimentoBetaError):
    """Número do processo CNJ inválido"""
    pass


class DocumentoNaoEncontradoError(CumprimentoBetaError):
    """Documento não encontrado no TJ-MS"""
    pass


class CategoriaNaoEncontradaError(CumprimentoBetaError):
    """Categoria de resumo JSON não encontrada no admin"""
    pass


class PromptNaoEncontradoError(CumprimentoBetaError):
    """Prompt não configurado no admin"""
    pass


class ExtracaoJSONError(CumprimentoBetaError):
    """Erro ao extrair JSON do documento"""
    pass


class ConsolidacaoError(CumprimentoBetaError):
    """Erro ao consolidar JSONs"""
    pass


class GeracaoPecaError(CumprimentoBetaError):
    """Erro ao gerar peça final"""
    pass


class TJMSError(CumprimentoBetaError):
    """Erro de comunicação com TJ-MS"""
    pass


class GeminiError(CumprimentoBetaError):
    """Erro de comunicação com Gemini"""
    pass
