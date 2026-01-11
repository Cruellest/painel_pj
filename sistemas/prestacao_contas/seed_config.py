# sistemas/prestacao_contas/seed_config.py
"""
Seed de configurações iniciais para o sistema de Prestação de Contas

Popula a tabela configuracoes_ia com valores padrão.

Autor: LAB/PGE-MS
"""

import logging
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# Configurações padrão do sistema
CONFIGURACOES_PADRAO = [
    # Modelos de IA
    {
        "sistema": "prestacao_contas",
        "chave": "modelo_identificacao",
        "valor": "gemini-2.0-flash-lite",
        "tipo_valor": "string",
        "descricao": "Modelo usado para identificar petição de prestação de contas",
    },
    {
        "sistema": "prestacao_contas",
        "chave": "modelo_analise",
        "valor": "gemini-3-flash-preview",
        "tipo_valor": "string",
        "descricao": "Modelo usado para análise final da prestação de contas",
    },

    # Temperaturas
    {
        "sistema": "prestacao_contas",
        "chave": "temperatura_identificacao",
        "valor": "0.1",
        "tipo_valor": "number",
        "descricao": "Temperatura para identificação de petição (baixa = mais determinístico)",
    },
    {
        "sistema": "prestacao_contas",
        "chave": "temperatura_analise",
        "valor": "0.3",
        "tipo_valor": "number",
        "descricao": "Temperatura para análise final",
    },
]


# Prompts padrão
PROMPTS_PADRAO = [
    {
        "sistema": "prestacao_contas",
        "tipo": "system",
        "nome": "system_prompt_analise",
        "conteudo": """Você é um analista jurídico especializado em prestação de contas de processos judiciais de medicamentos.

Sua função é analisar documentos de prestação de contas e emitir um parecer sobre a regularidade da utilização dos valores bloqueados judicialmente para aquisição de medicamentos.

CRITÉRIOS DE ANÁLISE:

1. ORIGEM DOS RECURSOS
   - Verificar no extrato da subconta se os valores são provenientes de bloqueio judicial contra o Estado de Mato Grosso do Sul
   - Confirmar que são recursos públicos

2. UTILIZAÇÃO INTEGRAL OU DEVOLUÇÃO
   - Comparar valor bloqueado/levantado com valor efetivamente gasto
   - Verificar se houve devolução de saldo excedente
   - Identificar se há saldo remanescente não utilizado

3. ADERÊNCIA AO PEDIDO INICIAL
   - O medicamento comprado corresponde ao pedido na petição inicial?
   - A quantidade adquirida é compatível com o tratamento autorizado?
   - O período de uso/tratamento foi respeitado?

4. DOCUMENTAÇÃO COMPROBATÓRIA
   - Notas fiscais estão legíveis e identificáveis?
   - Os valores nas notas conferem com o declarado?
   - Há recibos ou comprovantes de pagamento?

PARECERES POSSÍVEIS:

- FAVORÁVEL: Prestação de contas regular, valores utilizados corretamente
- DESFAVORÁVEL: Irregularidades identificadas (listar quais)
- DÚVIDA: Informações insuficientes para conclusão (formular perguntas específicas)

Seja objetivo e fundamentado em sua análise.""",
        "is_active": True,
    },
    {
        "sistema": "prestacao_contas",
        "tipo": "identificacao",
        "nome": "prompt_identificar_prestacao",
        "conteudo": """Analise o documento abaixo e classifique-o em relação a um processo de PRESTAÇÃO DE CONTAS de medicamentos judiciais.

TIPOS DE DOCUMENTOS:

1. PETICAO_PRESTACAO - Petição principal de prestação de contas que:
   - Informa compra do medicamento determinado judicialmente
   - Apresenta ou menciona notas fiscais/recibos
   - Demonstra como o dinheiro bloqueado foi utilizado
   - Solicita arquivamento ou devolução de saldo

2. PETICAO_RELEVANTE - Outras petições relevantes para contexto:
   - Petição inicial do processo (pedido original do medicamento)
   - Manifestações sobre valores ou medicamentos
   - Pedidos de complementação ou esclarecimentos
   - Decisões judiciais sobre bloqueio/liberação de valores

3. NOTA_FISCAL - Documento fiscal/comercial:
   - Notas fiscais de compra de medicamento
   - Cupons fiscais
   - Recibos de compra
   - Orçamentos de farmácia

4. COMPROVANTE - Comprovantes financeiros:
   - Comprovantes de transferência/PIX
   - Comprovantes de pagamento
   - Extratos bancários
   - Recibos de depósito

5. IRRELEVANTE - Documentos não relacionados:
   - Procurações
   - Certidões diversas
   - Documentos pessoais
   - Petições sobre outros assuntos

TEXTO DO DOCUMENTO:
{texto}

Responda em formato JSON:
```json
{{
  "tipo": "PETICAO_PRESTACAO" | "PETICAO_RELEVANTE" | "NOTA_FISCAL" | "COMPROVANTE" | "IRRELEVANTE",
  "confianca": 0.0 a 1.0,
  "resumo": "breve descrição do conteúdo (max 100 caracteres)"
}}
```""",
        "is_active": True,
    },
    {
        "sistema": "prestacao_contas",
        "tipo": "analise",
        "nome": "prompt_analise",
        "conteudo": """Analise a prestação de contas abaixo e emita um parecer.

## EXTRATO DA SUBCONTA (Valores bloqueados judicialmente)
{extrato_subconta}

## PETIÇÃO INICIAL (O que foi pedido)
{peticao_inicial}

## PETIÇÃO DE PRESTAÇÃO DE CONTAS
{peticao_prestacao}

## OUTRAS PETIÇÕES RELEVANTES
{peticoes_contexto}

## DOCUMENTOS ANEXOS (Notas fiscais, comprovantes)
{documentos_anexos}

---

Com base nos documentos acima, responda em formato JSON:

```json
{{
  "parecer": "favoravel" | "desfavoravel" | "duvida",
  "fundamentacao": "Texto em markdown explicando a análise e conclusão",
  "valor_bloqueado": número ou null,
  "valor_utilizado": número ou null,
  "valor_devolvido": número ou null,
  "medicamento_pedido": "nome do medicamento pedido" ou null,
  "medicamento_comprado": "nome do medicamento comprado" ou null,
  "irregularidades": ["lista de irregularidades"] ou null (se desfavorável),
  "perguntas": ["lista de perguntas ao usuário"] ou null (se dúvida),
  "contexto_duvida": "explicação do que precisa ser esclarecido" ou null (se dúvida)
}}
```

IMPORTANTE:
- Seja objetivo e fundamentado
- Extraia os valores monetários quando possível
- Se não conseguir determinar algo, use null
- A fundamentação deve ser clara e em markdown""",
        "is_active": True,
    },
]


def seed_configuracoes(db: Session):
    """
    Popula configurações iniciais no banco de dados.

    Args:
        db: Sessão do SQLAlchemy
    """
    from admin.models import ConfiguracaoIA, PromptConfig

    logger.info("Iniciando seed de configurações do sistema de Prestação de Contas...")

    # Seed de configurações de IA
    for config in CONFIGURACOES_PADRAO:
        existente = db.query(ConfiguracaoIA).filter(
            ConfiguracaoIA.sistema == config["sistema"],
            ConfiguracaoIA.chave == config["chave"]
        ).first()

        if not existente:
            nova_config = ConfiguracaoIA(
                sistema=config["sistema"],
                chave=config["chave"],
                valor=config["valor"],
                tipo_valor=config.get("tipo_valor", "string"),
            )
            db.add(nova_config)
            logger.info(f"Adicionada configuração: {config['chave']}")

    # Seed de prompts
    for prompt in PROMPTS_PADRAO:
        existente = db.query(PromptConfig).filter(
            PromptConfig.sistema == prompt["sistema"],
            PromptConfig.nome == prompt["nome"]
        ).first()

        if not existente:
            novo_prompt = PromptConfig(
                sistema=prompt["sistema"],
                tipo=prompt["tipo"],
                nome=prompt["nome"],
                conteudo=prompt["conteudo"],
                is_active=prompt.get("is_active", True),
            )
            db.add(novo_prompt)
            logger.info(f"Adicionado prompt: {prompt['nome']}")

    db.commit()
    logger.info("Seed de configurações concluído!")


def executar_seed():
    """Executa o seed (pode ser chamado standalone)"""
    from database.connection import SessionLocal

    db = SessionLocal()
    try:
        seed_configuracoes(db)
    finally:
        db.close()


if __name__ == "__main__":
    executar_seed()
