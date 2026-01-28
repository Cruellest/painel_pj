# sistemas/cumprimento_beta/constants.py
"""
Constantes do módulo Cumprimento de Sentença Beta
"""

# Status da sessão
class StatusSessao:
    INICIADO = "iniciado"
    BAIXANDO_DOCS = "baixando_docs"
    AVALIANDO_RELEVANCIA = "avaliando_relevancia"
    EXTRAINDO_JSON = "extraindo_json"
    CONSOLIDANDO = "consolidando"
    CHATBOT = "chatbot"
    GERANDO_PECA = "gerando_peca"
    FINALIZADO = "finalizado"
    ERRO = "erro"


# Status de relevância do documento
class StatusRelevancia:
    PENDENTE = "pendente"
    RELEVANTE = "relevante"
    IRRELEVANTE = "irrelevante"
    IGNORADO = "ignorado"  # Código na blacklist


# Roles do chat
class RoleChat:
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


# Chaves de configuração no admin (sistema = "cumprimento_beta")
class ConfigKeys:
    # Modelos
    MODELO_AGENTE1 = "modelo_agente1"
    MODELO_AGENTE2 = "modelo_agente2"
    MODELO_CHATBOT = "modelo_chatbot"
    MODELO_GERACAO_PECA = "modelo_geracao_peca"

    # Temperaturas
    TEMPERATURA_AGENTE1 = "temperatura_agente1"
    TEMPERATURA_AGENTE2 = "temperatura_agente2"
    TEMPERATURA_CHATBOT = "temperatura_chatbot"
    TEMPERATURA_GERACAO_PECA = "temperatura_geracao_peca"

    # Max Tokens
    MAX_TOKENS_AGENTE1 = "max_tokens_agente1"
    MAX_TOKENS_AGENTE2 = "max_tokens_agente2"
    MAX_TOKENS_CHATBOT = "max_tokens_chatbot"
    MAX_TOKENS_GERACAO_PECA = "max_tokens_geracao_peca"

    # Thinking
    THINKING_ENABLED = "thinking_enabled"
    THINKING_BUDGET = "thinking_budget_tokens"

    # Outros
    CODIGOS_IGNORAR = "codigos_ignorar"


# Categoria de resumo JSON para cumprimento
CATEGORIA_CUMPRIMENTO_SENTENCA = "cumprimento_sentenca"

# Grupo de acesso padrão
GRUPO_ACESSO_BETA = "PS"

# Timeouts (em segundos)
TIMEOUT_DOWNLOAD_DOC = 30
TIMEOUT_AVALIACAO_RELEVANCIA = 60
TIMEOUT_EXTRACAO_JSON = 120
TIMEOUT_CONSOLIDACAO = 180
TIMEOUT_CHATBOT = 120

# Limites
MAX_DOCS_POR_PROCESSO = 500
MAX_MENSAGENS_CONTEXTO = 20
MAX_TOKENS_RESPOSTA = 8192

# Modelos padrão (fallback se não configurado no admin)
MODELO_PADRAO_AGENTE1 = "gemini-3-flash-preview"
MODELO_PADRAO_AGENTE2 = "gemini-3-pro-preview"
MODELO_PADRAO_CHATBOT = "gemini-3-pro-preview"
