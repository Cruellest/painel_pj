# sistemas/cumprimento_beta/seed_config.py
"""
Configurações padrão do módulo Cumprimento de Sentença Beta.

Registra as configurações de IA no banco de dados para que possam ser
gerenciadas via /admin/prompts-config.
"""

from sqlalchemy.orm import Session
from admin.models import ConfiguracaoIA, PromptConfig
from sistemas.cumprimento_beta.constants import (
    MODELO_PADRAO_AGENTE1,
    MODELO_PADRAO_AGENTE2,
    MODELO_PADRAO_CHATBOT,
)

SISTEMA = "cumprimento_beta"


def seed_configuracoes(db: Session) -> int:
    """
    Cria configurações padrão de IA para o módulo Cumprimento Beta.

    Returns:
        Número de configurações criadas
    """
    configuracoes = [
        # === MODELOS ===
        {
            "chave": "modelo_agente1",
            "valor": MODELO_PADRAO_AGENTE1,
            "tipo_valor": "string",
            "descricao": "Modelo de IA para Agente 1 (avaliação de relevância e extração de JSON)"
        },
        {
            "chave": "modelo_agente2",
            "valor": MODELO_PADRAO_AGENTE2,
            "tipo_valor": "string",
            "descricao": "Modelo de IA para Agente 2 (consolidação do processo)"
        },
        {
            "chave": "modelo_chatbot",
            "valor": MODELO_PADRAO_CHATBOT,
            "tipo_valor": "string",
            "descricao": "Modelo de IA para chatbot de cumprimento de sentença"
        },
        {
            "chave": "modelo_geracao_peca",
            "valor": MODELO_PADRAO_AGENTE2,
            "tipo_valor": "string",
            "descricao": "Modelo de IA para geração de peças jurídicas"
        },

        # === TEMPERATURAS ===
        {
            "chave": "temperatura_agente1",
            "valor": "0.1",
            "tipo_valor": "number",
            "descricao": "Temperatura para Agente 1 (menor = mais determinístico)"
        },
        {
            "chave": "temperatura_agente2",
            "valor": "0.3",
            "tipo_valor": "number",
            "descricao": "Temperatura para Agente 2"
        },
        {
            "chave": "temperatura_chatbot",
            "valor": "0.5",
            "tipo_valor": "number",
            "descricao": "Temperatura para chatbot (maior = mais criativo)"
        },
        {
            "chave": "temperatura_geracao_peca",
            "valor": "0.4",
            "tipo_valor": "number",
            "descricao": "Temperatura para geração de peças"
        },

        # === MAX TOKENS ===
        {
            "chave": "max_tokens_agente1",
            "valor": "2048",
            "tipo_valor": "number",
            "descricao": "Máximo de tokens na resposta do Agente 1"
        },
        {
            "chave": "max_tokens_agente2",
            "valor": "8192",
            "tipo_valor": "number",
            "descricao": "Máximo de tokens na resposta do Agente 2"
        },
        {
            "chave": "max_tokens_chatbot",
            "valor": "4096",
            "tipo_valor": "number",
            "descricao": "Máximo de tokens na resposta do chatbot"
        },
        {
            "chave": "max_tokens_geracao_peca",
            "valor": "16384",
            "tipo_valor": "number",
            "descricao": "Máximo de tokens na geração de peças"
        },

        # === THINKING (se suportado pelo modelo) ===
        {
            "chave": "thinking_enabled",
            "valor": "false",
            "tipo_valor": "boolean",
            "descricao": "Habilitar modo thinking (raciocínio expandido) quando disponível"
        },
        {
            "chave": "thinking_budget_tokens",
            "valor": "8192",
            "tipo_valor": "number",
            "descricao": "Budget de tokens para thinking (se habilitado)"
        },

        # === FILTROS ===
        {
            "chave": "codigos_ignorar",
            "valor": "[10]",
            "tipo_valor": "json",
            "descricao": "Lista de códigos de documento a ignorar automaticamente (ex: [10, 20, 30])"
        },
    ]

    criadas = 0

    for config_data in configuracoes:
        # Verifica se já existe
        existente = db.query(ConfiguracaoIA).filter(
            ConfiguracaoIA.sistema == SISTEMA,
            ConfiguracaoIA.chave == config_data["chave"]
        ).first()

        if not existente:
            config = ConfiguracaoIA(
                sistema=SISTEMA,
                chave=config_data["chave"],
                valor=config_data["valor"],
                tipo_valor=config_data["tipo_valor"],
                descricao=config_data["descricao"]
            )
            db.add(config)
            criadas += 1

    db.commit()
    return criadas


def seed_prompts(db: Session) -> int:
    """
    Cria prompts padrão para o módulo Cumprimento Beta.

    Returns:
        Número de prompts criados
    """
    prompts = [
        {
            "tipo": "system",
            "nome": "prompt_sistema_chatbot",
            "descricao": "Prompt de sistema para o chatbot de cumprimento de sentença",
            "conteudo": """Você é um assistente jurídico especializado em cumprimento de sentença.

Você tem acesso às informações consolidadas do processo e deve ajudar o usuário com:
- Dúvidas sobre o processo
- Análise de valores e cálculos
- Sugestões de peças jurídicas
- Argumentação jurídica

Seja preciso, cite dados do processo quando relevante, e mantenha uma linguagem profissional."""
        },
        {
            "tipo": "consolidacao",
            "nome": "prompt_consolidacao",
            "descricao": "Prompt para consolidação do processo pelo Agente 2",
            "conteudo": """Analise os documentos JSON abaixo e gere uma consolidação completa do processo.

A consolidação deve incluir:
1. RESUMO DO PROCESSO: Síntese clara do caso
2. PARTES: Exequente(s), executado(s), seus advogados
3. OBJETO: O que está sendo executado/cobrado
4. VALORES: Valores envolvidos, atualizações, honorários
5. SITUAÇÃO ATUAL: Status do cumprimento
6. PONTOS DE ATENÇÃO: Questões relevantes ou pendências
7. SUGESTÕES DE PEÇAS: Peças jurídicas que podem ser elaboradas

Responda em formato JSON estruturado."""
        },
        {
            "tipo": "relevancia",
            "nome": "prompt_criterios_relevancia",
            "descricao": "Critérios para avaliação de relevância de documentos",
            "conteudo": """## CRITÉRIOS DE RELEVÂNCIA PARA CUMPRIMENTO DE SENTENÇA

### DOCUMENTOS RELEVANTES (marcar como relevante=true):
- Sentenças, acórdãos e decisões
- Petições iniciais e contestações
- Cálculos e planilhas de valores
- Laudos periciais
- Manifestações das partes sobre valores
- Certidões de citação e intimação importantes
- Documentos que contenham valores, datas ou informações sobre o mérito

### DOCUMENTOS IRRELEVANTES (marcar como relevante=false):
- Certidões de publicação genéricas
- Comprovantes de protocolo
- Documentos duplicados
- Juntadas meramente processuais
- Despachos de mero expediente
- Documentos ilegíveis ou vazios"""
        },
    ]

    criados = 0

    for prompt_data in prompts:
        existente = db.query(PromptConfig).filter(
            PromptConfig.sistema == SISTEMA,
            PromptConfig.nome == prompt_data["nome"]
        ).first()

        if not existente:
            prompt = PromptConfig(
                sistema=SISTEMA,
                tipo=prompt_data["tipo"],
                nome=prompt_data["nome"],
                descricao=prompt_data["descricao"],
                conteudo=prompt_data["conteudo"],
                is_active=True
            )
            db.add(prompt)
            criados += 1

    db.commit()
    return criados


def seed_all(db: Session) -> dict:
    """
    Executa todos os seeds do módulo.

    Returns:
        Dict com contagem de itens criados
    """
    configs_criadas = seed_configuracoes(db)
    prompts_criados = seed_prompts(db)

    return {
        "sistema": SISTEMA,
        "configuracoes_criadas": configs_criadas,
        "prompts_criados": prompts_criados
    }
