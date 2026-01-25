# Sistemas

Documentacao detalhada de cada sistema do Portal PGE-MS.

## Sistemas Disponiveis

| Sistema | Descricao | Status |
|---------|-----------|--------|
| [gerador_pecas.md](gerador_pecas.md) | Geracao de pecas juridicas com IA | Producao |
| [pedido_calculo.md](pedido_calculo.md) | Geracao de pedidos de calculo | Producao |
| [prestacao_contas.md](prestacao_contas.md) | Analise de prestacao de contas | Producao |
| [relatorio_cumprimento.md](relatorio_cumprimento.md) | Relatorios de cumprimento de sentenca | Producao |
| [matriculas_confrontantes.md](matriculas_confrontantes.md) | Analise de matriculas imobiliarias | Producao |
| [assistencia_judiciaria.md](assistencia_judiciaria.md) | Consulta e relatorio de processos | Producao |
| [bert_training.md](bert_training.md) | Treinamento de classificadores | Producao |
| [classificador_documentos.md](classificador_documentos.md) | Classificacao de PDFs com IA | Producao |

## Integracao com TJ-MS

Todos os sistemas (exceto BERT Training) usam o cliente TJMS unificado em `services/tjms/`.

Ver [../integracoes/PLANO_UNIFICACAO_TJMS.md](../integracoes/PLANO_UNIFICACAO_TJMS.md) para detalhes.

## Padrao de Documentacao

Cada sistema deve ter um `.md` com:
1. Descricao geral
2. Fluxo de uso
3. Endpoints
4. Modelos de dados
5. Dependencias
6. Observacoes
