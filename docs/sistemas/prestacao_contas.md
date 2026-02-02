# Sistema: Prestacao de Contas

> Documentacao tecnica do modulo de analise automatizada de prestacao de contas.

## A) Visao Geral

O sistema de Prestacao de Contas automatiza a analise de processos de prestacao de contas judiciais. Identifica extratos de subcontas, peticoes, movimentacoes financeiras e gera parecer tecnico sobre regularidade das contas prestadas.

**Usuarios**: Procuradores da CPCC e Procuradoria Fiscal
**Problema resolvido**: Automatizar analise de prestacao de contas em processos de cumprimento de sentenca com identificacao de irregularidades

## B) Regras de Negocio

### B.1) Identificacao de Documentos

| Regra | Descricao | Fonte no Codigo |
|-------|-----------|-----------------|
| Extratos de Subconta | Identifica documentos de extrato bancario | `sistemas/prestacao_contas/scrapper_subconta.py` |
| Peticoes | Identifica peticoes de prestacao de contas | `sistemas/prestacao_contas/identificador_peticoes.py` |
| Comprovantes | Identifica comprovantes de pagamento | `sistemas/prestacao_contas/services.py` |

### B.2) Analise de Irregularidades

| Regra | Descricao | Fonte no Codigo |
|-------|-----------|-----------------|
| Divergencia de Valores | Compara valores declarados vs extratos | `sistemas/prestacao_contas/agente_analise.py` |
| Datas Inconsistentes | Verifica consistencia de datas | `sistemas/prestacao_contas/agente_analise.py` |
| Saques Indevidos | Identifica saques sem comprovacao | `sistemas/prestacao_contas/agente_analise.py` |
| Documentacao Faltante | Lista documentos obrigatorios ausentes | `sistemas/prestacao_contas/agente_analise.py` |

### B.3) Geracao de Parecer

| Regra | Descricao | Fonte no Codigo |
|-------|-----------|-----------------|
| Parecer Favoravel | Sem irregularidades identificadas | `sistemas/prestacao_contas/agente_analise.py` |
| Parecer com Ressalvas | Irregularidades saneaveis | `sistemas/prestacao_contas/agente_analise.py` |
| Parecer Desfavoravel | Irregularidades graves | `sistemas/prestacao_contas/agente_analise.py` |
| Perguntas de Duvida | IA pode solicitar esclarecimentos | `sistemas/prestacao_contas/agente_analise.py` |

### B.4) Tratamento de Excecoes

| Situacao | Comportamento | Fonte no Codigo |
|----------|---------------|-----------------|
| Extrato ilegivel | Tenta OCR, solicita esclarecimento | `sistemas/prestacao_contas/services.py` |
| Processo sem prestacao | Retorna erro explicativo | `sistemas/prestacao_contas/services.py` |
| Duvida da IA | Pausa e solicita resposta do usuario | `sistemas/prestacao_contas/router.py:100-133` |

## C) Fluxo Funcional

```
[Usuario] Informa numero CNJ
    |
    v
[Router] POST /prestacao-contas/api/analisar-stream
    |
    v
[Orquestrador] Inicia analise
    |
    +-> Consulta TJ-MS
    +-> Identifica documentos de prestacao
    +-> Baixa extratos e comprovantes
    +-> Extrai informacoes paralelo (extrato_paralelo.py)
    |
    v
[Agente de Analise]
    |
    +-> Compara valores declarados x extratos
    +-> Verifica consistencia de datas
    +-> Identifica irregularidades
    +-> Gera lista de perguntas (se houver duvidas)
    |
    v
[Se houver perguntas]
    |
    +-> Pausa processamento
    +-> Retorna perguntas ao usuario
    +-> Usuario responde via /responder-duvida
    +-> Reavalia com novas informacoes
    |
    v
[Geracao do Parecer]
    |
    +-> Compoe parecer com fundamentacao
    +-> Lista irregularidades encontradas
    +-> Define parecer final
    |
    v
[Banco] Persiste em geracoes_analise
    |
    v
[Response] SSE com progresso + parecer
```

## D) API/Rotas

### Endpoints Principais

| Metodo | Rota | Descricao |
|--------|------|-----------|
| POST | `/prestacao-contas/api/analisar-stream` | Pipeline completo via SSE |
| POST | `/prestacao-contas/api/responder-duvida` | Responde perguntas da IA |
| POST | `/prestacao-contas/api/feedback` | Registra feedback |
| POST | `/prestacao-contas/api/exportar-parecer` | Gera DOCX do parecer |
| GET | `/prestacao-contas/api/historico` | Lista analises do usuario |
| GET | `/prestacao-contas/api/historico/{id}` | Detalhes de uma analise |

### Payload de Analise

```json
{
  "numero_cnj": "0804330-09.2024.8.12.0017",
  "sobrescrever_existente": false
}
```

### Payload de Resposta a Duvida

```json
{
  "geracao_id": 123,
  "respostas": {
    "pergunta_1": "Sim, o valor foi depositado em 15/03/2024",
    "pergunta_2": "Comprovante anexado ao processo"
  }
}
```

## E) Dados e Persistencia

### Tabelas

| Tabela | Descricao |
|--------|-----------|
| `geracoes_analise` | Registro de analises de prestacao |
| `feedbacks_prestacao` | Feedback dos usuarios |

### Modelo `GeracaoAnalise`

| Campo | Tipo | Descricao |
|-------|------|-----------|
| id | Integer | PK |
| numero_processo | String | CNJ |
| dados_extratos | JSON | Extratos identificados |
| irregularidades | JSON | Lista de irregularidades |
| perguntas | JSON | Perguntas pendentes |
| parecer | Text | Parecer final |
| fundamentacao | Text | Fundamentacao do parecer |
| usuario_id | Integer | FK para users |
| status | String | em_analise, aguardando_resposta, concluido |
| created_at | DateTime | Data de criacao |

## F) Integracoes Externas

### TJ-MS (SOAP/MNI)

- Mesma integracao do Gerador de Pecas
- Download de extratos e comprovantes

### Google Gemini

| Funcao | Modelo Default |
|--------|----------------|
| Analise de extratos | gemini-3-flash-preview |
| Identificacao de irregularidades | gemini-3-flash-preview |
| Geracao de parecer | gemini-3-flash-preview |

## G) Operacao e Validacao

### Como Rodar

```bash
uvicorn main:app --reload
# Acessar: http://localhost:8000/prestacao-contas
```

### Como Testar

```bash
curl -X POST http://localhost:8000/prestacao-contas/api/analisar-stream \
  -H "Authorization: Bearer TOKEN" \
  -d '{"numero_cnj": "0804330-09.2024.8.12.0017"}'
```

## H) Riscos e Dividas Tecnicas

### Riscos

| Risco | Impacto | Mitigacao Sugerida |
|-------|---------|-------------------|
| Extratos mal formatados | Alto - analise incorreta | Melhorar parser de extratos |
| Identificacao errada de irregularidades | Alto - parecer incorreto | Validacao humana obrigatoria |

### Dividas Tecnicas

| Item | Descricao | Prioridade |
|------|-----------|------------|
| Parser de extratos | Muitos formatos nao suportados | P1 |
| Validacao de valores | Nao valida calculos aritmeticos | P2 |
| Testes de integracao | Suite de testes incompleta | P2 |

## Arquivos Principais

| Arquivo | Descricao |
|---------|-----------|
| `sistemas/prestacao_contas/router.py` | Endpoints FastAPI |
| `sistemas/prestacao_contas/services.py` | Orquestrador principal |
| `sistemas/prestacao_contas/agente_analise.py` | Agente de analise |
| `sistemas/prestacao_contas/extrato_paralelo.py` | Extracao paralela |
| `sistemas/prestacao_contas/identificador_peticoes.py` | Identificador de peticoes |
| `sistemas/prestacao_contas/scrapper_subconta.py` | Scrapper de subcontas |
| `sistemas/prestacao_contas/models.py` | Modelos SQLAlchemy |
| `sistemas/prestacao_contas/schemas.py` | Schemas Pydantic |
