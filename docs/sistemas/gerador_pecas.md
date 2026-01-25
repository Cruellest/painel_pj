# Sistema: Gerador de Pecas Juridicas

> Documentacao tecnica do modulo de geracao automatizada de pecas juridicas.

## A) Visao Geral

O Gerador de Pecas e o sistema principal do Portal PGE-MS. Ele automatiza a criacao de contestacoes, recursos, contrarrazoes e outras pecas juridicas usando um pipeline de 3 agentes de IA que coletam documentos do TJ-MS, detectam argumentos aplicaveis e geram a peca final.

**Usuarios**: Procuradores da PGE-MS
**Problema resolvido**: Automatizar a criacao de pecas juridicas de defesa do Estado, reduzindo tempo de elaboracao de horas para minutos

## B) Regras de Negocio

### B.1) Pipeline de 3 Agentes

| Agente | Funcao | Modelo Default | Fonte no Codigo |
|--------|--------|----------------|-----------------|
| Agente 1 (Coletor) | Baixa documentos do TJ-MS e gera resumo consolidado em JSON | gemini-3-flash-preview | `sistemas/gerador_pecas/agente_tjms_integrado.py` |
| Agente 2 (Detector) | Analisa resumo e ativa prompts modulares relevantes | gemini-3-flash-preview | `sistemas/gerador_pecas/detector_modulos.py` |
| Agente 3 (Gerador) | Gera a peca juridica final em Markdown | gemini-3-pro-preview | `sistemas/gerador_pecas/orquestrador_agentes.py` |

### B.2) Selecao de Documentos

| Regra | Descricao | Fonte no Codigo |
|-------|-----------|-----------------|
| Codigos Permitidos | Filtra documentos por codigos TJ-MS configurados por tipo de peca | `sistemas/gerador_pecas/filtro_categorias.py` |
| Modo 2o Grau | Processos com competencia=999 usam selecao deterministica | `sistemas/gerador_pecas/services_segundo_grau.py` |
| Agrupamento | Documentos do mesmo codigo em janela de 2 horas sao agrupados | `sistemas/gerador_pecas/agente_tjms_integrado.py` |
| Primeiro Documento | Peticao inicial e sempre o primeiro doc do codigo 500/510/9500 | `sistemas/gerador_pecas/agente_tjms_integrado.py` |

### B.3) Ativacao de Modulos

| Regra | Descricao | Fonte no Codigo |
|-------|-----------|-----------------|
| Modo Deterministico | Avalia regras AST JSON sem chamar LLM (fast path) | `sistemas/gerador_pecas/services_deterministic.py` |
| Modo LLM | Usa Gemini para avaliar condicoes em linguagem natural | `sistemas/gerador_pecas/detector_modulos.py` |
| Fast Path | Se TODOS os modulos sao deterministicos, nao chama LLM | `sistemas/gerador_pecas/detector_modulos.py:320-400` |
| Consolidacao de Variaveis | Booleanos: OR; Listas: concatena unicos; Outros: mantém primeiro | `sistemas/gerador_pecas/orquestrador_agentes.py:128-275` |

### B.4) Grupos e Subcategorias

| Regra | Descricao | Fonte no Codigo |
|-------|-----------|-----------------|
| Grupo Obrigatorio | Usuario deve ter acesso a pelo menos um grupo de prompts | `sistemas/gerador_pecas/router.py:65-78` |
| Subcategorias | Filtram modulos adicionalmente (Alto Custo, Experimental, etc) | `sistemas/gerador_pecas/router.py:80-128` |
| Ordem de Categorias | Preliminar > Merito > Eventualidade > Honorarios | `sistemas/gerador_pecas/orquestrador_agentes.py:280-293` |

### B.5) Tratamento de Excecoes

| Situacao | Comportamento | Fonte no Codigo |
|----------|---------------|-----------------|
| TJ-MS indisponivel | Retorna erro, nao gera peca | `sistemas/gerador_pecas/agente_tjms_integrado.py` |
| Timeout no Agente 2 | Continua com modulos vazios | `sistemas/gerador_pecas/orquestrador_agentes.py:706-724` |
| Nenhum modulo ativado | Gera peca so com prompt base e tipo | `sistemas/gerador_pecas/orquestrador_agentes.py` |
| Tipo de peca nao informado | Se permitido, Agente 2 detecta; senao, HTTP 400 | `sistemas/gerador_pecas/router.py:189-232` |

## C) Fluxo Funcional

### Fluxo Principal (CNJ -> Peca)

```
[Usuario] Informa numero CNJ + tipo de peca
    |
    v
[Router] POST /gerador-pecas/api/processar-stream
    |
    v
[Orquestrador] Inicializa 3 agentes
    |
    +---> [AGENTE 1: Coletor]
    |         |
    |         +-> Consulta TJ-MS (SOAP via proxy)
    |         +-> Filtra documentos por codigos permitidos
    |         +-> Baixa PDFs relevantes
    |         +-> Extrai texto (PyMuPDF) ou envia imagens
    |         +-> Gera resumo JSON por documento
    |         +-> Consolida em resumo_consolidado
    |
    +---> [AGENTE 2: Detector]
    |         |
    |         +-> Recebe resumo_consolidado
    |         +-> Extrai variaveis dos JSONs (dados_extracao)
    |         +-> Avalia modulos deterministicos (fast path)
    |         +-> Se necessario, chama LLM para modulos restantes
    |         +-> Monta prompts: sistema + peca + conteudo
    |
    +---> [AGENTE 3: Gerador]
              |
              +-> Recebe prompts + resumo + dados_processo
              +-> Chama Gemini 3 Pro
              +-> Retorna peca em Markdown (streaming)
    |
    v
[Banco] Persiste em geracoes_pecas + versoes_pecas
    |
    v
[Response] SSE com chunks da peca + metadata final
```

### Fluxo de PDFs Anexados

```
[Usuario] Upload de PDFs manuais
    |
    v
[Classificador] Classifica cada PDF em categoria
    |
    v
[Selector] Seleciona primarios/secundarios por tipo de peca
    |
    v
[Extractor] Extrai JSON de cada documento
    |
    v
[Orquestrador] Continua pipeline normal (Agentes 2 e 3)
```

## D) API/Rotas

### Endpoints Principais

| Metodo | Rota | Descricao |
|--------|------|-----------|
| GET | `/gerador-pecas/api/tipos-peca` | Listar tipos de peca disponiveis |
| GET | `/gerador-pecas/api/grupos-disponiveis` | Listar grupos de prompts do usuario |
| GET | `/gerador-pecas/api/grupos/{id}/subgrupos` | Listar subgrupos de um grupo |
| POST | `/gerador-pecas/api/processar-stream` | Processar por CNJ (SSE) |
| POST | `/gerador-pecas/api/processar-pdfs-stream` | Processar PDFs anexados (SSE) |
| POST | `/gerador-pecas/api/editar-minuta` | Editar via chat (chatbot) |
| POST | `/gerador-pecas/api/exportar-docx` | Exportar Markdown para DOCX |
| GET | `/gerador-pecas/api/historico` | Listar geracoes do usuario |
| POST | `/gerador-pecas/api/feedback` | Enviar feedback |

### Payload de Processamento

```json
{
  "numero_cnj": "0804330-09.2024.8.12.0017",
  "tipo_peca": "contestacao",
  "observacao_usuario": "Foco na tese de prescricao",
  "group_id": 1,
  "subcategoria_ids": [3, 4]
}
```

### Eventos SSE

| Evento | Descricao |
|--------|-----------|
| `status` | Atualiza etapa (agente1, agente2, agente3) |
| `chunk` | Fragmento da peca gerada |
| `metadata` | Informacoes finais (geracao_id, tempos, etc) |
| `error` | Erro durante processamento |
| `done` | Processamento concluido |

## E) Dados e Persistencia

### Tabelas Principais

| Tabela | Descricao |
|--------|-----------|
| `geracoes_pecas` | Registro de cada geracao (numero, resumo, prompt, resultado) |
| `versoes_pecas` | Versionamento de edicoes da peca |
| `feedbacks_pecas` | Feedback dos usuarios |
| `prompt_modulos` | Modulos de prompt (base, peca, conteudo) |
| `prompt_groups` | Grupos de prompts (PS, PP, DETRAN) |
| `categorias_resumo_json` | Categorias de documento e formato de extracao |
| `extraction_variables` | Variaveis extraidas dos documentos |

### Modelo `GeracaoPeca`

| Campo | Tipo | Descricao |
|-------|------|-----------|
| id | Integer | PK |
| numero_processo | String | CNJ |
| tipo_peca | String | contestacao, recurso_apelacao, etc |
| resumo_consolidado | Text | Resumo do Agente 1 |
| prompt_enviado | Text | Prompt completo do Agente 3 |
| conteudo_gerado | Text | Peca em Markdown |
| tempo_agente1 | Float | Tempo em segundos |
| tempo_agente2 | Float | Tempo em segundos |
| tempo_agente3 | Float | Tempo em segundos |
| usuario_id | Integer | FK para users |
| created_at | DateTime | Data de criacao |

### O que NAO e persistido

- PDFs baixados do TJ-MS (processados em memoria)
- Imagens de documentos escaneados
- Tokens intermediarios do streaming

## F) Integracoes Externas

### TJ-MS (SOAP/MNI)

| Configuracao | Variavel de Ambiente | Descricao |
|--------------|---------------------|-----------|
| Proxy URL | `TJMS_PROXY_URL` | Proxy Fly.io para SOAP |
| Usuario MNI | `MNI_USER` | Credencial |
| Senha MNI | `MNI_PASS` | Credencial |
| Timeout | `TJMS_SOAP_TIMEOUT` | Default: 30s |

### Google Gemini

| Configuracao | Variavel de Ambiente | Descricao |
|--------------|---------------------|-----------|
| API Key | `GEMINI_KEY` | Chave de acesso |
| Modelo Agente 1 | Configuravel em admin | Default: gemini-3-flash-preview |
| Modelo Agente 2 | Configuravel em admin | Default: gemini-3-flash-preview |
| Modelo Agente 3 | Configuravel em admin | Default: gemini-3-pro-preview |

### Busca Vetorial (Embeddings)

| Configuracao | Descricao |
|--------------|-----------|
| Modelo | Google text-embedding-004 (768 dimensoes) |
| Storage | tabela modulo_embeddings (pgvector ou numpy fallback) |
| Threshold | 35% similaridade minima |

### Pontos Frageis

- Proxy TJ-MS pode estar indisponivel
- Processos grandes (>100 docs) podem timeout
- Gemini Pro tem latencia maior que Flash

## G) Operacao e Validacao

### Como Rodar

```bash
# Servidor
uvicorn main:app --reload

# Acessar frontend
http://localhost:8000/gerador-pecas
```

### Como Testar

```bash
# Processar por CNJ
curl -X POST http://localhost:8000/gerador-pecas/api/processar-stream \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"numero_cnj": "0804330-09.2024.8.12.0017", "tipo_peca": "contestacao"}'

# Testar busca de argumentos
curl -X POST http://localhost:8000/gerador-pecas/api/buscar-argumentos \
  -H "Authorization: Bearer TOKEN" \
  -d '{"query": "medicamento alto custo", "limit": 5}'
```

### Logs e Telemetria

- Logs de agente: console com prefixo [AGENTE1], [AGENTE2], [AGENTE3]
- Metricas de tempo: tabela geracoes_pecas
- Logs de ativacao de modulos: tabela prompt_activation_logs

## H) Riscos e Dividas Tecnicas

### Riscos

| Risco | Impacto | Mitigacao Sugerida |
|-------|---------|-------------------|
| Timeout em processos grandes | Alto - peca nao e gerada | Paginacao de documentos, limite de paginas |
| Modulos mal ativados | Medio - argumentos errados | Melhorar regras deterministicas |
| Custo de Gemini Pro | Medio - custo por geracao | Cachear pecas similares |

### Dividas Tecnicas

| Item | Descricao | Prioridade |
|------|-----------|------------|
| Cache de resumos | Resumos de docs identicos nao sao cacheados | P1 |
| Metricas de qualidade | Nao ha metricas de acuracia de ativacao | P1 |
| Testes E2E | Suite E2E incompleta | P2 |
| Fallback de modelo | Se Gemini Pro falha, nao tenta Flash | P2 |
| Limite de paginas | Sem limite de paginas por documento | P3 |

## Arquivos Principais

| Arquivo | Descricao |
|---------|-----------|
| `sistemas/gerador_pecas/router.py` | Endpoints FastAPI |
| `sistemas/gerador_pecas/orquestrador_agentes.py` | Orquestracao dos 3 agentes |
| `sistemas/gerador_pecas/agente_tjms_integrado.py` | Agente 1 (Coletor) |
| `sistemas/gerador_pecas/detector_modulos.py` | Agente 2 (Detector) |
| `sistemas/gerador_pecas/services_deterministic.py` | Avaliacao de regras deterministicas |
| `sistemas/gerador_pecas/services_extraction.py` | Extracao de variaveis |
| `sistemas/gerador_pecas/services_busca_argumentos.py` | Busca vetorial de argumentos |
| `sistemas/gerador_pecas/document_classifier.py` | Classificador de PDFs anexados |
| `sistemas/gerador_pecas/models.py` | Modelos SQLAlchemy |
| `sistemas/gerador_pecas/constants.py` | Constantes centralizadas (timeouts, limites, mensagens) |
| `sistemas/gerador_pecas/exceptions.py` | Excecoes customizadas do dominio |
| `sistemas/gerador_pecas/templates/` | Frontend SPA |

## Documentacao Complementar

- **Onboarding para novos devs**: `docs/onboarding_gerador_pecas.md`
- **Arquitetura geral**: `docs/arquitetura/ARQUITETURA_GERAL.md`
- **Cliente TJ-MS unificado**: `services/tjms/`
