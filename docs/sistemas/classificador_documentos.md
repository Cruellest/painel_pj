# Sistema: Classificador de Documentos

> Documentacao tecnica do modulo de classificacao automatica de documentos PDF.

## A) Visao Geral

O Classificador de Documentos permite classificar automaticamente PDFs em categorias predefinidas usando IA (OpenRouter/Gemini). Pode ser usado de forma standalone para classificar documentos juridicos em categorias (peticoes, decisoes, pareceres, etc) ou integrado com TJ-MS para processar documentos de processos.

**Usuarios**: Procuradores e sistemas automatizados
**Problema resolvido**: Classificar automaticamente documentos juridicos em lote, com integracao ao TJ-MS

## B) Funcionalidades Principais

### B.1) Prompts de Classificacao

Prompts sao templates de instrucoes para a IA classificar documentos. Cada prompt pode definir:

| Campo | Descricao |
|-------|-----------|
| `nome` | Nome identificador do prompt |
| `descricao` | Descricao do objetivo do prompt |
| `conteudo` | Texto completo do prompt enviado a IA |
| `codigos_documento` | Codigos de tipos de documento TJ-MS que o prompt classifica (ex: "8,15,34") |

**Codigos de Documento TJ-MS**: Quando um prompt tem codigos configurados, ao seleciona-lo na interface:
- Os tipos de documento sao pre-selecionados automaticamente
- Um popup informa os codigos configurados

### B.2) Lotes (Projetos de Classificacao)

Lotes agrupam multiplos documentos para classificacao em batch:

| Funcionalidade | Descricao |
|----------------|-----------|
| Upload Manual | Arrastar e soltar PDFs |
| Importar TJ-MS | Buscar documentos de processos por numero CNJ |
| Filtro por Tipo | Selecionar apenas tipos especificos (Sentenca, Decisao, etc) |
| Execucao em Lote | Classificar todos os documentos do lote |
| Exportacao | Exportar resultados em Excel, CSV ou JSON |

### B.3) Teste Rapido

Permite testar um prompt com um documento antes de criar um lote:

| Modo | Descricao |
|------|-----------|
| Upload | Arrasta um PDF local |
| TJ-MS | Busca documento de um processo e visualiza o PDF |

O visualizador PDF permite navegar pelas paginas do documento ao lado do resultado da classificacao.

## C) Regras de Negocio

### C.1) Classificacao

| Regra | Descricao |
|-------|-----------|
| Modo Chunk | Envia apenas parte do texto (inicio ou fim) para economizar tokens |
| Modo Completo | Envia o texto completo do documento |
| Fallback OCR | Se extracao de texto falhar, usa OCR via PyMuPDF |
| Confianca | IA retorna nivel de confianca (alta, media, baixa) |

### C.2) Integracao TJ-MS

| Regra | Descricao |
|-------|-----------|
| Tipos de Documento | Filtra por codigo de tipo (8=Sentenca, 15=Decisao Interlocutoria, etc) |
| Pre-selecao | Prompts com `codigos_documento` pre-selecionam os tipos automaticamente |

## D) Fluxo Funcional

### Fluxo de Classificacao em Lote

```
[Usuario] Cria Lote com nome e prompt
    |
    v
[Usuario] Adiciona documentos (upload ou TJ-MS)
    |
    v
[Sistema] Para cada documento:
    |-- Extrai texto do PDF
    |-- Aplica modo chunk se configurado
    |-- Envia para IA via OpenRouter
    |-- Salva resultado (categoria, confianca, justificativa)
    |
    v
[Usuario] Visualiza resultados e exporta
```

### Fluxo de Teste Rapido

```
[Usuario] Seleciona prompt
    |
    v
[Sistema] Pre-seleciona tipos de documento do prompt (se configurados)
    |
    v
[Usuario] Upload PDF ou busca no TJ-MS
    |
    v
[Sistema] Exibe PDF no visualizador
    |
    v
[Usuario] Clica "Classificar"
    |
    v
[Sistema] Retorna resultado ao lado do PDF
```

## E) API/Rotas

### Endpoints de Prompts

| Metodo | Rota | Descricao |
|--------|------|-----------|
| GET | `/classificador/api/prompts` | Listar prompts |
| POST | `/classificador/api/prompts` | Criar prompt |
| GET | `/classificador/api/prompts/{id}` | Obter prompt |
| PUT | `/classificador/api/prompts/{id}` | Atualizar prompt |
| DELETE | `/classificador/api/prompts/{id}` | Deletar prompt |

### Endpoints de Projetos (Lotes)

| Metodo | Rota | Descricao |
|--------|------|-----------|
| GET | `/classificador/api/projetos` | Listar projetos do usuario |
| POST | `/classificador/api/projetos` | Criar projeto |
| GET | `/classificador/api/projetos/{id}` | Obter projeto |
| POST | `/classificador/api/lotes/{id}/upload` | Upload de arquivos |
| POST | `/classificador/api/lotes/{id}/tjms-lote` | Importar do TJ-MS |
| POST | `/classificador/api/lotes/{id}/executar-sincrono` | Executar classificacao |

### Endpoints TJ-MS

| Metodo | Rota | Descricao |
|--------|------|-----------|
| POST | `/classificador/api/tjms/consultar-processo` | Listar documentos de um processo |
| POST | `/classificador/api/tjms/baixar-documento` | Baixar documento em base64 |

### Endpoints de Classificacao

| Metodo | Rota | Descricao |
|--------|------|-----------|
| POST | `/classificador/api/classificar-avulso` | Classificar documento (upload) |

### Endpoints de Exportacao

| Metodo | Rota | Descricao |
|--------|------|-----------|
| GET | `/classificador/api/execucoes/{id}/exportar/excel` | Exportar Excel |
| GET | `/classificador/api/execucoes/{id}/exportar/csv` | Exportar CSV |
| GET | `/classificador/api/execucoes/{id}/exportar/json` | Exportar JSON |

## F) Dados e Persistencia

### Tabelas

| Tabela | Descricao |
|--------|-----------|
| `prompts_classificacao` | Prompts de classificacao |
| `projetos_classificacao` | Projetos/Lotes de classificacao |
| `codigos_documento_projeto` | Documentos vinculados a um projeto |
| `execucoes_classificacao` | Execucoes de classificacao |
| `resultados_classificacao` | Resultados individuais por documento |
| `logs_classificacao_ia` | Logs de chamadas a IA |

### Modelo de Dados Principal

```
ProjetoClassificacao (Lote)
  |-- prompt_id -> PromptClassificacao
  |-- usuario_id -> User
  |-- codigos[] -> CodigoDocumentoProjeto
  |-- execucoes[] -> ExecucaoClassificacao
        |-- resultados[] -> ResultadoClassificacao
```

## G) Integracoes Externas

### OpenRouter (IA)

| Configuracao | Descricao |
|--------------|-----------|
| API Key | `OPENROUTER_API_KEY` |
| Modelo padrao | `google/gemini-2.5-flash-lite` |
| Modelos disponiveis | Configuravel por projeto |

### TJ-MS

| Configuracao | Descricao |
|--------------|-----------|
| Endpoint | Via `services/tjms/` |
| Tipos de documento | Filtrados por codigo (8, 15, 34, etc) |

### Tipos de Documento TJ-MS Comuns

| Codigo | Descricao |
|--------|-----------|
| 8 | Sentenca |
| 15 | Decisao Interlocutoria |
| 34 | Acordao |
| 44 | Decisao Monocratica |
| 500 | Peticao Inicial |
| 9500 | Peticao |
| 8320 | Contestacao |
| 8335 | Apelacao |

## H) Operacao e Validacao

### Como Rodar

```bash
# Servidor
uvicorn main:app --reload

# Acessar frontend
http://localhost:8000/classificador
```

### Testes

```bash
# Rodar testes do classificador
pytest tests/classificador_documentos/ -v
```

## I) Arquivos Principais

| Arquivo | Descricao |
|---------|-----------|
| `sistemas/classificador_documentos/router.py` | Endpoints FastAPI |
| `sistemas/classificador_documentos/services.py` | Logica de classificacao |
| `sistemas/classificador_documentos/services_tjms.py` | Integracao com TJ-MS |
| `sistemas/classificador_documentos/services_openrouter.py` | Cliente OpenRouter |
| `sistemas/classificador_documentos/services_extraction.py` | Extracao de texto |
| `sistemas/classificador_documentos/services_export.py` | Exportacao de resultados |
| `sistemas/classificador_documentos/models.py` | Modelos SQLAlchemy |
| `sistemas/classificador_documentos/schemas.py` | Schemas Pydantic |
| `sistemas/classificador_documentos/templates/index.html` | Frontend SPA |

## J) Historico de Alteracoes

| Data | Alteracao |
|------|-----------|
| 2025-01 | Redesign completo: Lotes, TJ-MS, Teste Rapido com visualizador PDF |
| 2025-01 | Campo `codigos_documento` nos prompts para pre-selecao de tipos |
