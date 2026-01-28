# Cumprimento de Sentenca (Beta)

> Sistema de analise inteligente de processos de cumprimento de sentenca.

**Status:** Beta (Acesso restrito)
**Grupo de Acesso:** PS (Procuradoria Setorial) ou Admin
**Modulo:** `sistemas/cumprimento_beta/`

---

## Indice

1. [Visao Geral](#visao-geral)
2. [Arquitetura do Sistema](#arquitetura-do-sistema)
3. [Fluxo de Processamento](#fluxo-de-processamento)
4. [Agentes](#agentes)
   - [Agente 1 - Coleta e Analise](#agente-1---coleta-e-analise)
   - [Agente 2 - Consolidacao](#agente-2---consolidacao)
   - [Chatbot](#chatbot)
   - [Gerador de Pecas](#gerador-de-pecas)
5. [Modelos de Dados](#modelos-de-dados)
6. [Configuracao de IA](#configuracao-de-ia)
7. [Prompts Configuraveis](#prompts-configuraveis)
8. [API Endpoints](#api-endpoints)
9. [Integracao com TJ-MS](#integracao-com-tj-ms)
10. [Troubleshooting](#troubleshooting)

---

## Visao Geral

O modulo **Cumprimento de Sentenca Beta** e um sistema de analise automatizada de processos judiciais que:

1. **Baixa documentos** do TJ-MS via integracao SOAP
2. **Avalia relevancia** de cada documento usando IA
3. **Extrai informacoes estruturadas** em formato JSON
4. **Consolida** todas as informacoes em um resumo executivo
5. **Oferece um chatbot** para interacao com os dados do processo
6. **Gera pecas juridicas** baseadas no contexto consolidado

### Diferencas do Gerador de Pecas Normal

| Aspecto | Gerador Normal | Cumprimento Beta |
|---------|----------------|------------------|
| Foco | Qualquer tipo de peca | Cumprimento de sentenca |
| Fluxo | Linear, uma execucao | Sessao persistente com chatbot |
| Interacao | Input unico | Conversacional |
| Dados | Tabela unica | Modelos isolados (`*_beta`) |
| Acesso | Qualquer usuario | Restrito (grupo PS/admin) |

---

## Arquitetura do Sistema

```
+---------------------------------------------------------------------+
|                         CUMPRIMENTO BETA                            |
+---------------------------------------------------------------------+
|                                                                     |
|  +----------+    +----------+    +----------+    +--------------+   |
|  | AGENTE 1 | -> | AGENTE 2 | -> | CHATBOT  | -> | GERAR PECA   |   |
|  |          |    |          |    |          |    |              |   |
|  | Download |    |Consolida |    | Conversa |    | Markdown +   |   |
|  | Avalia   |    | JSONs    |    | interati |    | DOCX         |   |
|  | Extrai   |    | Sugestoes|    | va       |    |              |   |
|  +----------+    +----------+    +----------+    +--------------+   |
|       |              |               |                 |            |
|       v              v               v                 v            |
|  +-------------------------------------------------------------+    |
|  |                    BANCO DE DADOS (PostgreSQL)               |   |
|  |  SessaoCumprimentoBeta  DocumentoBeta  JSONResumoBeta        |   |
|  |  ConsolidacaoBeta       ConversaBeta   PecaGeradaBeta        |   |
|  +-------------------------------------------------------------+    |
|                                                                     |
+---------------------------------------------------------------------+
```

### Estrutura de Arquivos

**Backend:**
```
sistemas/cumprimento_beta/
├── __init__.py                          # Exports publicos
├── router.py                            # Endpoints FastAPI
├── models.py                            # Modelos SQLAlchemy
├── schemas.py                           # Schemas Pydantic
├── constants.py                         # Constantes e enums
├── dependencies.py                      # Verificacao de acesso
├── exceptions.py                        # Excecoes customizadas
├── seed_config.py                       # Configuracoes padrao
├── agente1.py                           # Orquestrador Agente 1
├── agente2.py                           # Orquestrador Agente 2
├── services_download.py                 # Download TJ-MS
├── services_processamento_unificado.py  # Relevancia + JSON (OTIMIZADO)
├── services_relevancia.py               # (legado, mantido para compatibilidade)
├── services_extracao_json.py            # (legado, mantido para compatibilidade)
├── services_consolidacao.py             # Consolidacao
├── services_chatbot.py                  # Chatbot
├── services_geracao_peca.py             # Geracao de pecas
├── templates/
│   ├── index.html                       # Template HTML (carrega app.js)
│   └── app.js                           # Bundle TypeScript compilado
└── temp_docs/                           # Arquivos DOCX temporarios
```

**Frontend (TypeScript):**
```
frontend/src/sistemas/cumprimento_beta/
├── types.ts                             # Tipos TypeScript
├── api.ts                               # Cliente API tipado
├── app.ts                               # Aplicacao principal (entry point)
├── index.ts                             # Re-exports do modulo
└── components/
    ├── index.ts                         # Exports dos componentes
    ├── JsonViewer.ts                    # Visualizador JSON interativo
    ├── HistoryDrawer.ts                 # Drawer lateral de historico
    ├── ProcessSteps.ts                  # Etapas de processamento
    └── ProcessSummary.ts                # Resumo do processo (tabs)
```

---

## Fluxo de Processamento

### Diagrama de Estados

```
+----------+
| INICIADO |
+----+-----+
     | POST /processar
     v
+---------------+
|BAIXANDO_DOCS  |  <- Download de documentos do TJ-MS
+-------+-------+
        |
        v
+---------------------+
|AVALIANDO_RELEVANCIA |  <- IA classifica cada documento
+-----------+---------+
            |
            v
+----------------+
| EXTRAINDO_JSON |  <- IA extrai dados estruturados
+--------+-------+
         |
         v
+--------------+
| CONSOLIDANDO |  <- IA gera resumo consolidado
+------+-------+
       |
       v
+----------+
| CHATBOT  |  <- Usuario interage via chat
+----+-----+
     | (opcional)
     v
+---------------+
| GERANDO_PECA  |  <- Gera peca juridica
+-------+-------+
        |
        v
+------------+
| FINALIZADO |
+------------+
```

### Fluxo Detalhado

1. **Usuario cria sessao** com numero do processo
2. **Agente 1 e acionado** (background task):
   - Baixa lista de documentos do TJ-MS
   - Filtra codigos na blacklist (`codigos_ignorar`)
   - Baixa conteudo (PDF) dos documentos restantes
   - Extrai texto do PDF via PyMuPDF
   - Avalia relevancia de cada documento (IA)
   - Extrai JSON estruturado dos relevantes (IA)
3. **Agente 2 e acionado** (streaming):
   - Recebe todos os JSONs do Agente 1
   - Gera resumo consolidado do processo
   - Sugere pecas juridicas possiveis
4. **Chatbot disponibilizado**:
   - Usuario faz perguntas sobre o processo
   - Sistema busca argumentos no banco vetorial
   - IA responde com contexto do processo
5. **Geracao de Pecas** (sob demanda):
   - Usuario solicita tipo de peca
   - Sistema gera em Markdown
   - Converte para DOCX automaticamente

---

## Agentes

### Agente 1 - Coleta e Analise

**Arquivo:** `agente1.py`, `services_download.py`, `services_relevancia.py`, `services_extracao_json.py`

**Funcao:** Coletar, avaliar e estruturar documentos do processo.

#### Pipeline do Agente 1 (OTIMIZADO)

```
+------------+   +--------------+   +----------------------------------+
|  DOWNLOAD  | → |    FILTRO    | → | PROCESSAMENTO UNIFICADO          |
|            |   |              |   | (relevancia + extracao em 1 call)|
| TJ-MS SOAP |   | Codigos na   |   |                                  |
| Extrai PDF |   | blacklist    |   | Paralelizado com asyncio.gather  |
+------------+   +--------------+   +----------------------------------+
```

**OTIMIZACAO:** O Agente 1 combina avaliacao de relevancia e extracao de JSON em uma
unica chamada LLM por documento, reduzindo pela metade o numero de chamadas a API.
Alem disso, processa multiplos documentos em paralelo (max 20 simultaneos).

#### Etapa 1: Download (`services_download.py`)

- **Consulta processo** via SOAP para obter lista de documentos
- **Filtra documentos** com codigos na blacklist (configuravel em `/admin/prompts-config`)
- **Baixa conteudo** em batches de 5 documentos
- **Extrai texto** do PDF usando PyMuPDF (fitz)

**Configuracoes:**

| Parametro | Chave | Descricao |
|-----------|-------|-----------|
| Codigos Ignorar | `codigos_ignorar` | Lista JSON de codigos a ignorar (ex: `[10, 20]`) |
| Limite de Docs | `MAX_DOCS_POR_PROCESSO` | Maximo 500 documentos por processo |

#### Etapa 2: Processamento Unificado (`services_processamento_unificado.py`)

**ANTES (2 chamadas por documento):**
1. `services_relevancia.py` → Gemini retorna `{relevante: true/false}`
2. `services_extracao_json.py` → Gemini extrai dados estruturados

**DEPOIS (1 chamada por documento + paralelo):**
- `services_processamento_unificado.py` → UMA chamada que retorna relevancia + dados
- Processa ate 20 documentos simultaneamente com `asyncio.gather()`

**Beneficios:**
- 50% menos chamadas de API
- Processamento muito mais rapido (paralelo)
- Consistencia entre avaliacao e extracao

A IA avalia cada documento e classifica como:

| Status | Descricao |
|--------|-----------|
| `pendente` | Aguardando avaliacao |
| `relevante` | Documento importante para cumprimento |
| `irrelevante` | Documento sem valor para analise |
| `ignorado` | Codigo na blacklist (nao avaliado) |

**Prompt de Avaliacao:**

```
Voce e um assistente juridico especializado em avaliar relevancia de documentos.

Analise o documento abaixo e determine se ele e RELEVANTE ou IRRELEVANTE
para um processo de cumprimento de sentenca.

[CRITERIOS DE RELEVANCIA - configuravel via admin]

Responda com JSON: {"relevante": true/false, "motivo": "..."}
```

**Criterios de Relevancia (configuravel):**

```markdown
## DOCUMENTOS RELEVANTES:
- Sentencas, acordaos e decisoes
- Peticoes iniciais e contestacoes
- Calculos e planilhas de valores
- Laudos periciais
- Manifestacoes das partes sobre valores

## DOCUMENTOS IRRELEVANTES:
- Certidoes de publicacao genericas
- Comprovantes de protocolo
- Despachos de mero expediente
- Documentos ilegiveis ou vazios
```

#### Etapa 3: Extracao de JSON (`services_extracao_json.py`)

Para cada documento **relevante**, a IA extrai informacoes estruturadas:

**Schema Padrao:**

```json
{
  "document_id": "string - ID do documento",
  "tipo_documento": "string - Tipo/descricao",
  "data_documento": "string - DD/MM/YYYY",
  "resumo": "string - Resumo do conteudo",
  "pontos_relevantes": ["lista de pontos"],
  "pedidos_ou_determinacoes": ["lista de pedidos"],
  "valores_mencionados": ["R$ X.XXX,XX"],
  "prazos_mencionados": ["DD/MM/YYYY"],
  "partes_mencionadas": ["Nome da Parte"],
  "observacoes": "string"
}
```

**Personalizacao:** Crie uma categoria "cumprimento_sentenca" em `/admin/categorias-resumo-json` para usar schema customizado.

#### Modelo de IA do Agente 1

| Parametro | Chave | Default |
|-----------|-------|---------|
| Modelo | `modelo_agente1` | `gemini-3-flash-preview` |
| Temperatura | `temperatura_agente1` | `0.1` |
| Max Tokens | `max_tokens_agente1` | `2048` |

---

### Agente 2 - Consolidacao

**Arquivo:** `agente2.py`, `services_consolidacao.py`

**Funcao:** Analisar todos os JSONs e gerar um resumo consolidado com sugestoes de pecas.

#### Entrada

Todos os `JSONResumoBeta` gerados pelo Agente 1.

#### Saida

```json
{
  "resumo_consolidado": "Texto com resumo executivo do processo...",
  "dados_processo": {
    "exequente": "Nome do Exequente",
    "executado": "Estado de MS",
    "valor_execucao": "R$ XXX.XXX,XX",
    "objeto": "Descricao do objeto",
    "status": "Status atual"
  },
  "sugestoes_pecas": [
    {
      "tipo": "Impugnacao ao Cumprimento",
      "descricao": "Recomendada devido a...",
      "prioridade": "alta"
    }
  ]
}
```

#### Prompt de Consolidacao

```
Voce e um assistente juridico especializado em cumprimento de sentenca.

Analise os documentos do processo abaixo e produza:
1. Um RESUMO CONSOLIDADO do caso
2. Uma lista de SUGESTOES DE PECAS

## DOCUMENTOS DO PROCESSO
[JSONs extraidos pelo Agente 1]

## INSTRUCOES
### Resumo Consolidado
- Partes envolvidas (exequente, executado)
- Objeto da execucao
- Valor total envolvido
- Status atual do cumprimento
- Principais eventos processuais
- Prazos relevantes

### Sugestoes de Pecas
Com base no estado atual, sugira pecas juridicas que podem ser necessarias.
```

#### Modelo de IA do Agente 2

| Parametro | Chave | Default |
|-----------|-------|---------|
| Modelo | `modelo_agente2` | `gemini-3-pro-preview` |
| Temperatura | `temperatura_agente2` | `0.3` |
| Max Tokens | `max_tokens_agente2` | `8192` |

---

### Chatbot

**Arquivo:** `services_chatbot.py`

**Funcao:** Permitir interacao conversacional com os dados do processo.

#### Funcionalidades

1. **Historico Persistente:** Mensagens salvas no banco
2. **Contexto do Processo:** Consolidacao incluida no prompt
3. **Busca Vetorial:** Busca argumentos relevantes no banco vetorial
4. **Streaming:** Respostas em tempo real via SSE

#### Prompt de Sistema do Chatbot

```
Voce e um assistente juridico especializado em cumprimento de sentenca,
trabalhando para a PGE-MS.

## Contexto do Processo
[Dados da consolidacao + partes + valores]

## Suas Responsabilidades
1. Auxiliar na elaboracao de pecas de cumprimento
2. Responder duvidas sobre o processo
3. Sugerir estrategias e argumentos juridicos
4. Gerar pecas quando solicitado

## Diretrizes
- Seja objetivo e tecnico
- Use linguagem juridica apropriada
- Baseie-se nas informacoes do processo
- Se nao souber algo, admita claramente
```

#### Modelo de IA do Chatbot

| Parametro | Chave | Default |
|-----------|-------|---------|
| Modelo | `modelo_chatbot` | `gemini-3-pro-preview` |
| Temperatura | `temperatura_chatbot` | `0.5` |
| Max Tokens | `max_tokens_chatbot` | `4096` |

---

### Gerador de Pecas

**Arquivo:** `services_geracao_peca.py`

**Funcao:** Gerar pecas juridicas formatadas baseadas no contexto do processo.

#### Tipos de Pecas Sugeridas

- Impugnacao ao Cumprimento de Sentenca
- Manifestacao sobre Calculos
- Peticao de Extincao
- Embargos a Execucao
- Peticao Simples
- (Qualquer tipo solicitado pelo usuario)

#### Prompt de Geracao

```
Voce e um procurador do Estado de MS especializado em cumprimento de sentenca.

Gere uma peca juridica do tipo: **{tipo_peca}**

## Contexto do Processo
[Resumo consolidado + dados do processo]

## Instrucoes do Usuario
[Instrucoes adicionais se fornecidas]

## Diretrizes
1. Use formatacao adequada para documento juridico
2. Inclua: Enderecamento, Qualificacao, Fundamentacao, Pedidos
3. Use linguagem formal e tecnica
4. Cite legislacao e jurisprudencia quando pertinente

## Formato
Gere a peca em Markdown com a seguinte estrutura:
- Cabecalho com enderecamento
- Preambulo com qualificacao
- Corpo com secoes numeradas
- Pedidos em lista
- Fechamento com data e assinatura
```

#### Saida

- **Markdown:** Texto formatado para visualizacao
- **DOCX:** Arquivo Word para download (conversao automatica)

#### Modelo de IA da Geracao

| Parametro | Chave | Default |
|-----------|-------|---------|
| Modelo | `modelo_geracao_peca` | `gemini-3-pro-preview` |
| Temperatura | `temperatura_geracao_peca` | `0.4` |
| Max Tokens | `max_tokens_geracao_peca` | `16384` |

---

## Modelos de Dados

### SessaoCumprimentoBeta

Sessao principal do fluxo. Uma por processo.

| Campo | Tipo | Descricao |
|-------|------|-----------|
| id | int | PK |
| user_id | int | FK -> users |
| numero_processo | str | CNJ limpo (20 digitos) |
| numero_processo_formatado | str | CNJ formatado |
| status | str | Estado atual da sessao |
| total_documentos | int | Quantidade de docs |
| documentos_processados | int | Docs processados |
| documentos_relevantes | int | Docs relevantes |
| documentos_irrelevantes | int | Docs irrelevantes |
| documentos_ignorados | int | Docs ignorados |
| erro_mensagem | str | Erro (se status == erro) |
| created_at | datetime | Data criacao |
| updated_at | datetime | Data atualizacao |
| finalizado_em | datetime | Data finalizacao |

### DocumentoBeta

Documento baixado do TJ-MS.

| Campo | Tipo | Descricao |
|-------|------|-----------|
| id | int | PK |
| sessao_id | int | FK -> sessoes_cumprimento_beta |
| documento_id_tjms | str | ID no TJ-MS |
| codigo_documento | int | Codigo do tipo |
| descricao_documento | str | Descricao |
| data_documento | datetime | Data de juntada |
| conteudo_texto | str | Texto extraido do PDF |
| tamanho_bytes | int | Tamanho |
| paginas | int | Numero de paginas |
| status_relevancia | str | pendente/relevante/irrelevante/ignorado |
| motivo_irrelevancia | str | Se irrelevante, por que |
| modelo_avaliacao | str | Modelo usado na avaliacao |

### JSONResumoBeta

JSON estruturado extraido de documento relevante.

| Campo | Tipo | Descricao |
|-------|------|-----------|
| id | int | PK |
| documento_id | int | FK -> documentos_beta (unique) |
| json_conteudo | dict | Dados extraidos |
| categoria_nome | str | Categoria usada |
| modelo_usado | str | Modelo Gemini |
| json_valido | bool | Se JSON e valido |

### ConsolidacaoBeta

Resumo consolidado gerado pelo Agente 2.

| Campo | Tipo | Descricao |
|-------|------|-----------|
| id | int | PK |
| sessao_id | int | FK -> sessoes_cumprimento_beta (unique) |
| resumo_consolidado | str | Texto do resumo |
| sugestoes_pecas | list | JSON com sugestoes |
| dados_processo | dict | Partes, valores, etc |
| total_jsons_consolidados | int | JSONs usados |
| modelo_usado | str | Modelo Gemini |

### ConversaBeta

Mensagem do chatbot.

| Campo | Tipo | Descricao |
|-------|------|-----------|
| id | int | PK |
| sessao_id | int | FK -> sessoes_cumprimento_beta |
| role | str | user/assistant/system |
| conteudo | str | Texto da mensagem |
| modelo_usado | str | (para assistant) |
| usou_busca_vetorial | bool | Se usou banco vetorial |
| argumentos_encontrados | list | IDs dos modulos |

### PecaGeradaBeta

Peca juridica gerada.

| Campo | Tipo | Descricao |
|-------|------|-----------|
| id | int | PK |
| sessao_id | int | FK -> sessoes_cumprimento_beta |
| tipo_peca | str | "Impugnacao", "Manifestacao", etc |
| titulo | str | Titulo da peca |
| conteudo_markdown | str | Peca em Markdown |
| conteudo_docx_path | str | Caminho do DOCX |
| instrucoes_usuario | str | Instrucoes adicionais |
| modelo_usado | str | Modelo Gemini |
| tempo_geracao_ms | int | Tempo de geracao |

---

## Configuracao de IA

### Onde Configurar

**Acesse:** `/admin/prompts-config` -> Aba "Cumprimento Beta"

### Parametros por Agente

| Agente | Modelo | Temperatura | Max Tokens |
|--------|--------|-------------|------------|
| Agente 1 | `modelo_agente1` | `temperatura_agente1` (0.1) | `max_tokens_agente1` (2048) |
| Agente 2 | `modelo_agente2` | `temperatura_agente2` (0.3) | `max_tokens_agente2` (8192) |
| Chatbot | `modelo_chatbot` | `temperatura_chatbot` (0.5) | `max_tokens_chatbot` (4096) |
| Geracao | `modelo_geracao_peca` | `temperatura_geracao_peca` (0.4) | `max_tokens_geracao_peca` (16384) |

### Outros Parametros

| Chave | Tipo | Descricao |
|-------|------|-----------|
| `codigos_ignorar` | JSON | Lista de codigos de documento a ignorar `[10, 20]` |
| `thinking_enabled` | boolean | Habilitar modo thinking (se modelo suportar) |
| `thinking_budget_tokens` | number | Budget de tokens para thinking |

---

## Prompts Configuraveis

### Onde Configurar

**Acesse:** `/admin/prompts-config` -> Filtro "Cumprimento de Sentenca (Beta)"

### Prompts Disponiveis

| Nome | Tipo | Descricao |
|------|------|-----------|
| `prompt_sistema_chatbot` | system | Prompt de sistema do chatbot |
| `prompt_consolidacao` | consolidacao | Prompt para consolidacao do Agente 2 |
| `prompt_criterios_relevancia` | relevancia | Criterios de classificacao de documentos |

### Criando Prompts

Se os prompts nao existirem, clique no botao "Cumprimento Beta" na secao "Nenhum prompt encontrado" para criar os prompts padrao.

---

## API Endpoints

### Base URL

```
/api/cumprimento-beta
```

### Endpoints

| Metodo | Endpoint | Descricao |
|--------|----------|-----------|
| GET | `/acesso` | Verifica se usuario tem acesso ao beta |
| POST | `/sessoes` | Cria nova sessao |
| GET | `/sessoes` | Lista sessoes do usuario |
| GET | `/sessoes/{id}` | Obtem status de uma sessao |
| POST | `/sessoes/{id}/processar` | Inicia Agente 1 (background) |
| GET | `/sessoes/{id}/documentos` | Lista documentos da sessao |
| POST | `/sessoes/{id}/consolidar` | Inicia Agente 2 (streaming) |
| GET | `/sessoes/{id}/consolidacao` | Obtem consolidacao |
| POST | `/sessoes/{id}/chat` | Envia mensagem no chat |
| GET | `/sessoes/{id}/conversas` | Lista historico do chat |
| POST | `/sessoes/{id}/gerar-peca` | Gera peca juridica |
| GET | `/sessoes/{id}/pecas` | Lista pecas geradas |
| GET | `/sessoes/{id}/pecas/{peca_id}/download` | Download do DOCX |

### Exemplo: Fluxo Completo

```python
# 1. Criar sessao
POST /api/cumprimento-beta/sessoes
{
    "numero_processo": "0800123-45.2024.8.12.0001"
}

# 2. Iniciar processamento (Agente 1)
POST /api/cumprimento-beta/sessoes/1/processar

# 3. Aguardar conclusao (polling)
GET /api/cumprimento-beta/sessoes/1
# Espera status == "consolidando" ou "chatbot"

# 4. Iniciar consolidacao (Agente 2) com streaming
POST /api/cumprimento-beta/sessoes/1/consolidar?streaming=true

# 5. Interagir via chat
POST /api/cumprimento-beta/sessoes/1/chat
{
    "conteudo": "Qual o valor total da execucao?"
}

# 6. Gerar peca
POST /api/cumprimento-beta/sessoes/1/gerar-peca
{
    "tipo_peca": "Impugnacao ao Cumprimento",
    "instrucoes_adicionais": "Focar na prescricao"
}

# 7. Download DOCX
GET /api/cumprimento-beta/sessoes/1/pecas/1/download
```

---

## Integracao com TJ-MS

### Comunicacao SOAP

O modulo usa chamadas SOAP diretas via `aiohttp` (async) para comunicar com o TJ-MS.

**Endpoint:** Configurado em `services/tjms/config.py`

### Operacoes

| Operacao | Metodo SOAP | Descricao |
|----------|-------------|-----------|
| Consultar Processo | `consultarProcesso` | Lista documentos do processo |
| Baixar Documentos | `consultarProcesso` + `<documento>ID</documento>` | Baixa conteudo PDF |

### Formato XML

```xml
<soapenv:Envelope xmlns:soapenv="..." xmlns:ser="..." xmlns:tip="...">
    <soapenv:Body>
        <ser:consultarProcesso>
            <tip:idConsultante>{user}</tip:idConsultante>
            <tip:senhaConsultante>{pass}</tip:senhaConsultante>
            <tip:numeroProcesso>{cnj}</tip:numeroProcesso>
            <tip:movimentos>true</tip:movimentos>
            <tip:incluirDocumentos>true</tip:incluirDocumentos>
            <!-- Para baixar conteudo especifico: -->
            <tip:documento>ID1</tip:documento>
            <tip:documento>ID2</tip:documento>
        </ser:consultarProcesso>
    </soapenv:Body>
</soapenv:Envelope>
```

### Extracao de Texto

PDFs sao processados pelo PyMuPDF (fitz):

```python
pdf_bytes = base64.b64decode(conteudo_base64)
doc = fitz.open(stream=pdf_bytes, filetype="pdf")
texto = ""
for page in doc:
    texto += page.get_text()
```

---

## Troubleshooting

### Erro: "Nenhum documento encontrado"

**Causa:** Processo nao existe ou nao tem documentos no TJ-MS.

**Solucao:** Verifique o numero do processo no portal do TJ-MS.

### Erro: "Erro de conexao com TJ-MS"

**Causa:** Falha de rede ou TJ-MS indisponivel.

**Solucao:**
1. Verifique conectividade com o TJ-MS
2. Verifique credenciais em `.env`
3. Aguarde e tente novamente

### Erro: "Acesso negado"

**Causa:** Usuario nao pertence ao grupo PS e nao e admin.

**Solucao:** Adicione o usuario ao grupo PS ou defina como admin.

### Documentos importantes marcados como irrelevantes

**Causa:** Criterios de relevancia muito restritivos.

**Solucao:**
1. Acesse `/admin/prompts-config`
2. Edite o prompt `prompt_criterios_relevancia`
3. Adicione tipos de documentos que devem ser considerados relevantes

### Consolidacao vazia ou incompleta

**Causa:** Poucos documentos relevantes ou JSONs vazios.

**Solucao:**
1. Verifique se ha documentos relevantes na sessao
2. Ajuste criterios de relevancia
3. Verifique logs para erros de extracao

### Chatbot nao responde com contexto do processo

**Causa:** Consolidacao nao foi gerada corretamente.

**Solucao:**
1. Verifique se existe consolidacao para a sessao
2. Reconsolide se necessario: `POST /consolidar`

---

## Testes

```bash
# Rodar testes do modulo
pytest tests/cumprimento_beta/ -v

# Testes especificos
pytest tests/cumprimento_beta/test_acesso.py -v
pytest tests/cumprimento_beta/test_agente1.py -v
pytest tests/cumprimento_beta/test_agente2.py -v
pytest tests/cumprimento_beta/test_chatbot.py -v
```

---

## Frontend TypeScript

### Arquitetura

O frontend foi migrado para TypeScript com arquitetura baseada em componentes:

```
+----------------------------------------------------------+
|                    CumprimentoBetaApp                     |
|                                                          |
|  +-------------+  +--------------+  +------------------+ |
|  | History     |  | Process      |  | Process          | |
|  | Drawer      |  | Steps        |  | Summary          | |
|  |             |  |              |  |                  | |
|  | - Busca CNJ |  | - Progresso  |  | - Tabs           | |
|  | - Filtros   |  | - Duracao    |  | - JsonViewer     | |
|  | - Sessoes   |  | - Aviso      |  | - Sugestoes      | |
|  +-------------+  +--------------+  +------------------+ |
|                                                          |
+----------------------------------------------------------+
```

### Componentes

| Componente | Arquivo | Descricao |
|------------|---------|-----------|
| `JsonViewer` | `components/JsonViewer.ts` | Visualizador JSON interativo com tree view, busca, copia e download |
| `HistoryDrawer` | `components/HistoryDrawer.ts` | Drawer lateral para historico de sessoes com busca e filtros |
| `ProcessSteps` | `components/ProcessSteps.ts` | Indicador de progresso por etapa com aviso de demora |
| `ProcessSummary` | `components/ProcessSummary.ts` | Resumo do processo com tabs (Resumo/Dados/JSON) |

### Tipos TypeScript

Todos os tipos estao em `types.ts`:

```typescript
// Status da sessao
type SessionStatus = 'iniciado' | 'baixando_docs' | 'avaliando_relevancia' |
                     'extraindo_json' | 'consolidando' | 'chatbot' |
                     'gerando_peca' | 'finalizado' | 'erro';

// Response da API
interface SessionResponse {
  id: number;
  numero_processo: string;
  status: SessionStatus;
  // ...
}

// Eventos SSE para streaming
type SSEEvent = SSEEventInicio | SSEEventChunk | SSEEventConcluido | SSEEventErro;
```

### API Client

O cliente API em `api.ts` fornece metodos tipados para todas as operacoes:

```typescript
import { api } from './api';

// Criar sessao
const session = await api.createSession({ numero_processo: '1234567890123456789' });

// Streaming de consolidacao
for await (const event of api.streamConsolidation(sessionId)) {
  if (event.event === 'chunk') {
    console.log(event.data.texto);
  }
}

// Streaming de chat
for await (const chunk of api.streamChat(sessionId, 'Qual o valor?')) {
  console.log(chunk);
}
```

### Build do Frontend

```bash
# Build de todos os arquivos TypeScript
cd frontend && npm run build

# Typecheck (verificacao de tipos sem gerar arquivos)
cd frontend && npm run typecheck

# Watch mode (rebuild automatico)
cd frontend && npm run build:watch
```

Os arquivos compilados sao gerados em `sistemas/cumprimento_beta/templates/`:
- `app.js` - Bundle principal
- `app.js.map` - Source map para debug

### Estilos CSS

Os estilos sao encapsulados em cada componente e injetados no `<head>`:

```typescript
// Exemplo de componente
export class JsonViewer {
  // ...
}

// CSS exportado com o componente
export const jsonViewerStyles = `
  .json-viewer { ... }
  .json-key { color: #7c3aed; }
  // ...
`;
```

A aplicacao injeta todos os estilos ao inicializar:

```typescript
private injectStyles(): void {
  const style = document.createElement('style');
  style.textContent = `
    ${historyDrawerStyles}
    ${processStepsStyles}
    ${processSummaryStyles}
    ${jsonViewerStyles}
    ${this.getAppStyles()}
  `;
  document.head.appendChild(style);
}
```

---

## Changelog

### v1.2.0 (Janeiro 2025) - Migracao TypeScript

- **REFATORACAO COMPLETA:** Frontend migrado de JavaScript inline para TypeScript
- **NOVO:** Estrutura modular com componentes reutilizaveis
- **NOVO:** Componente `JsonViewer` com tree view, busca, copia e download
- **NOVO:** Componente `HistoryDrawer` com drawer lateral, busca por CNJ e filtros
- **NOVO:** Componente `ProcessSteps` com progresso visual e aviso de demora
- **NOVO:** Componente `ProcessSummary` com tabs (Resumo/Dados/JSON)
- **MELHORIA:** API client tipado com suporte a streaming SSE
- **MELHORIA:** Strict mode TypeScript habilitado
- **MELHORIA:** Build automatizado via esbuild

### v1.1.0 (Janeiro 2025)

- **OTIMIZACAO:** Unificacao de relevancia + extracao em uma unica chamada LLM
- **OTIMIZACAO:** Processamento paralelo de documentos (ate 20 simultaneos)
- Novo servico: `services_processamento_unificado.py`
- Reducao de 50% nas chamadas de API do Agente 1

### v1.0.0 (Janeiro 2025)

- Versao inicial do modulo beta
- Agente 1: Download, relevancia e extracao
- Agente 2: Consolidacao
- Chatbot com busca vetorial
- Geracao de pecas com DOCX
- Configuracao via `/admin/prompts-config`

---

**Equipe:** LAB/PGE-MS
**Ultima Atualizacao:** Janeiro 2025
