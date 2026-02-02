# sistemas/relatorio_cumprimento/seed_config.py
"""
Script para popular prompts e configurações iniciais do Sistema de Relatório de Cumprimento.

Execução:
    python -c "from sistemas.relatorio_cumprimento.seed_config import seed_all; seed_all()"
"""

from database.connection import SessionLocal
from admin.models import PromptConfig, ConfiguracaoIA
from datetime import datetime


SISTEMA = "relatorio_cumprimento"


# ============================================
# Prompts
# ============================================

PROMPTS = [
    {
        "tipo": "geracao_relatorio",
        "nome": "Geração do Relatório Inicial",
        "descricao": "Prompt usado para gerar o relatório inicial de cumprimento de sentença",
        "conteudo": """Analise os documentos do processo e gere um RELATÓRIO INICIAL para cumprimento de sentença.

## DADOS DO PROCESSO
{dados_json}

## DOCUMENTOS PARA ANÁLISE
{documentos}

## OBJETIVO
Gere um relatório inicial estruturado que permita ao procurador compreender rapidamente:
1. O histórico processual relevante
2. O objeto da condenação
3. Os critérios definidos na sentença/acórdão
4. As partes envolvidas
5. Os valores e prazos relevantes

## FORMATO DO RELATÓRIO (MARKDOWN)

# RELATÓRIO INICIAL - CUMPRIMENTO DE SENTENÇA

## 1. DADOS DO PROCESSO

**Processo de Cumprimento:** [número]
**Processo de Conhecimento:** [número, se diferente]
**Autor/Exequente:** [nome]
**Réu/Executado:** Estado de Mato Grosso do Sul
**Comarca/Vara:** [comarca] - [vara]
**Data de Ajuizamento:** [data]

---

## 2. HISTÓRICO PROCESSUAL

[Resumo do histórico relevante do processo, incluindo principais decisões e movimentações]

---

## 3. OBJETO DA CONDENAÇÃO

[Descrição detalhada do que foi condenado, extraído da sentença/acórdão]

---

## 4. CRITÉRIOS DA CONDENAÇÃO

### 4.1 Correção Monetária
- **Índice:** [índice aplicável]
- **Termo Inicial:** [quando começa]
- **Termo Final:** [quando termina]
- **Observação:** [observações sobre EC 113/2021, se aplicável]

### 4.2 Juros Moratórios
- **Taxa:** [taxa aplicável]
- **Termo Inicial:** [quando começa]
- **Termo Final:** [quando termina]
- **Observação:** [observações sobre EC 113/2021, se aplicável]

### 4.3 Período da Condenação
[MM/AAAA a MM/AAAA]

---

## 5. TRÂNSITO EM JULGADO

**Data:** [data ou "Não localizado"]
**Fonte:** [certidão/movimento/documento]

---

## 6. VALORES

**Valor da Causa:** [valor, se disponível]
**Valor do Pedido:** [valor solicitado pelo exequente, se disponível]

---

## 7. OBSERVAÇÕES E PENDÊNCIAS

[Liste aqui quaisquer observações importantes, inconsistências encontradas, ou informações que precisam ser verificadas]

---

**Data do Relatório:** {data_atual}
**Gerado por:** Sistema de Relatórios PGE-MS (IA)

---

## REGRAS OBRIGATÓRIAS

1. Use APENAS as informações fornecidas nos documentos - não invente dados
2. Se alguma informação estiver faltando, indique "[A VERIFICAR]" ou "[NÃO LOCALIZADO]"
3. Mantenha o formato exato do template
4. Para EC 113/2021 (a partir de 09/12/2021):
   - Se citação posterior a 09/12/2021: aplica-se apenas SELIC desde o início
   - Se citação anterior: índice até 08/12/2021, depois SELIC
5. Seja objetivo e conciso, mas completo
6. Destaque informações críticas ou que precisam de atenção especial"""
    },
    {
        "tipo": "edicao_relatorio",
        "nome": "Edição de Relatório via Chat",
        "descricao": "Prompt usado quando o usuário solicita alterações no relatório via chat",
        "conteudo": """Você é um assistente especializado em editar relatórios de cumprimento de sentença.

O usuário solicitou a seguinte alteração no relatório:

"{mensagem_usuario}"

## Relatório Atual (Markdown):
{relatorio_markdown}

## Dados do Processo:
{dados_processo}

## Instruções:
1. Aplique APENAS a alteração solicitada pelo usuário
2. Mantenha toda a estrutura e formatação do relatório
3. Retorne o relatório completo atualizado em Markdown
4. NÃO adicione comentários ou explicações, apenas o relatório atualizado

Relatório atualizado:"""
    }
]


# ============================================
# Configurações de Modelos
# ============================================

CONFIGURACOES = [
    {
        "chave": "modelo_analise",
        "valor": "gemini-3-flash-preview",
        "tipo_valor": "string",
        "descricao": "Modelo de IA para análise de documentos e geração do relatório"
    },
    {
        "chave": "modelo_edicao",
        "valor": "gemini-3-flash-preview",
        "tipo_valor": "string",
        "descricao": "Modelo de IA para edição do relatório via chat"
    },
    {
        "chave": "temperatura_analise",
        "valor": "0.2",
        "tipo_valor": "number",
        "descricao": "Temperatura para análise e geração (baixa = mais preciso)"
    },
    {
        "chave": "thinking_level",
        "valor": "low",
        "tipo_valor": "string",
        "descricao": "Nível de raciocínio do modelo (minimal, low, medium, high)"
    }
]


def seed_prompts(db):
    """Popula prompts iniciais"""
    for prompt_data in PROMPTS:
        existing = db.query(PromptConfig).filter(
            PromptConfig.sistema == SISTEMA,
            PromptConfig.tipo == prompt_data["tipo"]
        ).first()

        if not existing:
            prompt = PromptConfig(
                sistema=SISTEMA,
                tipo=prompt_data["tipo"],
                nome=prompt_data["nome"],
                descricao=prompt_data["descricao"],
                conteudo=prompt_data["conteudo"],
                is_active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(prompt)
            print(f"  Prompt criado: {prompt_data['tipo']}")
        else:
            print(f"  Prompt já existe: {prompt_data['tipo']}")

    db.commit()


def seed_configuracoes(db):
    """Popula configurações de modelos"""
    for config_data in CONFIGURACOES:
        existing = db.query(ConfiguracaoIA).filter(
            ConfiguracaoIA.sistema == SISTEMA,
            ConfiguracaoIA.chave == config_data["chave"]
        ).first()

        if not existing:
            config = ConfiguracaoIA(
                sistema=SISTEMA,
                chave=config_data["chave"],
                valor=config_data["valor"],
                tipo_valor=config_data["tipo_valor"],
                descricao=config_data["descricao"],
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(config)
            print(f"  Configuração criada: {config_data['chave']}")
        else:
            print(f"  Configuração já existe: {config_data['chave']}")

    db.commit()


def seed_all():
    """Executa todos os seeds"""
    print("\nPopulando configurações do Relatório de Cumprimento...")

    db = SessionLocal()
    try:
        seed_prompts(db)
        seed_configuracoes(db)
        print("\nConfigurações populadas com sucesso!\n")
    finally:
        db.close()


if __name__ == "__main__":
    seed_all()
