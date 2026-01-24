# Sistema: Classificador de Documentos

> Documentacao tecnica do modulo de classificacao automatica de documentos PDF.

## A) Visao Geral

O Classificador de Documentos permite classificar automaticamente PDFs em categorias predefinidas usando IA (Google Gemini). E utilizado como componente auxiliar do Gerador de Pecas para processar documentos anexados, mas tambem pode ser usado de forma standalone.

**Usuarios**: Procuradores e sistemas automatizados
**Problema resolvido**: Classificar automaticamente documentos juridicos em categorias (peticoes, decisoes, pareceres, etc) para processamento posterior

## B) Regras de Negocio

### B.1) Classificacao de PDFs

| Regra | Descricao | Fonte no Codigo |
|-------|-----------|-----------------|
| Categorias do Banco | Categorias sao carregadas dinamicamente de `categorias_resumo_json` | `sistemas/classificador_documentos/services.py:50-80` |
| Categoria Residual | Se confianca baixa ou erro, usa categoria com `is_residual=True` | `sistemas/classificador_documentos/services.py:120-140` |
| Threshold de Confianca | Classificacao aceita se confianca >= 0.5 (configuravel) | `sistemas/classificador_documentos/services.py:90-110` |

### B.2) Heuristica de Conteudo

| Condicao | Acao | Fonte no Codigo |
|----------|------|-----------------|
| PDF com texto extraivel de boa qualidade | Envia primeiros 1000 + ultimos 1000 tokens | `sistemas/classificador_documentos/services.py:150-180` |
| PDF com texto de ma qualidade | Converte para imagens | `sistemas/classificador_documentos/services.py:190-210` |
| PDF e imagem nativa | Envia imagens das paginas | `sistemas/classificador_documentos/services.py:220-240` |
| OCR falha | Envia imagens das paginas | `sistemas/classificador_documentos/services.py:250-270` |

### B.3) Integracao com Gerador de Pecas

| Regra | Descricao | Fonte no Codigo |
|-------|-----------|-----------------|
| Selecao de Primarios | Documento principal e selecionado por prioridade do tipo de peca | `sistemas/gerador_pecas/document_selector.py` |
| Extracao JSON | Apos classificado, JSON e extraido conforme formato da categoria | `sistemas/gerador_pecas/services_extraction.py` |

### B.4) Tratamento de Excecoes

| Situacao | Comportamento | Fonte no Codigo |
|----------|---------------|-----------------|
| IA retorna categoria inexistente | Fallback para categoria residual | `sistemas/classificador_documentos/services.py` |
| IA retorna JSON malformado | Fallback para categoria residual | `sistemas/classificador_documentos/services.py` |
| Confianca abaixo do threshold | Fallback para categoria residual | `sistemas/classificador_documentos/services.py` |
| Erro de comunicacao com IA | Fallback para categoria residual | `sistemas/classificador_documentos/services.py` |

## C) Fluxo Funcional

### Fluxo de Classificacao Standalone

```
[Usuario] Upload de PDF(s)
    |
    v
[API] POST /classificador/api/classificar
    |
    v
[Service] Extrai texto ou converte para imagem
    |
    v
[Gemini] Classifica em uma das categorias
    |
    v
[Response] Retorna categoria_id, confianca, justificativa
```

### Fluxo Integrado (Gerador de Pecas)

```
[Usuario] Upload PDFs no Gerador de Pecas
    |
    v
[Classificador] Classifica cada PDF individualmente
    |
    v
[Selector] Seleciona documentos primarios/secundarios por tipo de peca
    |
    v
[Extractor] Extrai JSON de cada documento classificado
    |
    v
[Agente 2/3] Usa dados extraidos para gerar peca
```

## D) API/Rotas

### Endpoints

| Metodo | Rota | Descricao |
|--------|------|-----------|
| POST | `/classificador/api/classificar` | Classificar um ou mais PDFs |
| GET | `/classificador/api/categorias` | Listar categorias disponiveis |
| POST | `/classificador/api/classificar-batch` | Classificar em lote |

### Payload de Classificacao

```json
{
  "files": [
    {
      "filename": "peticao.pdf",
      "content_base64": "JVBERi0xLjQK..."
    }
  ]
}
```

### Resposta de Classificacao

```json
{
  "results": [
    {
      "filename": "peticao.pdf",
      "categoria_id": 1,
      "categoria_nome": "peticoes",
      "confianca": 0.95,
      "justificativa": "Documento com DOS FATOS e DOS PEDIDOS",
      "source": "text",
      "fallback_aplicado": false
    }
  ]
}
```

## E) Dados e Persistencia

### Tabelas Utilizadas

| Tabela | Descricao |
|--------|-----------|
| `categorias_resumo_json` | Categorias de classificacao (origem do gerador_pecas) |

### O que NAO e persistido

- PDFs enviados para classificacao (processados em memoria)
- Resultados de classificacao (retornados apenas na resposta)

**Nota**: O classificador e stateless - nao persiste dados proprios. Usa categorias definidas no sistema de Categorias JSON do Gerador de Pecas.

## F) Integracoes Externas

### Google Gemini

| Configuracao | Variavel de Ambiente | Descricao |
|--------------|---------------------|-----------|
| API Key | `GEMINI_KEY` | Chave de acesso |
| Modelo | Configuravel em `/admin/prompts-config` | Default: gemini-2.5-flash-lite |
| Temperatura | Configuravel | Default: 0.1 |
| Threshold | Configuravel | Default: 0.5 |

### Pontos Frageis

- PDFs muito grandes podem exceder limite de tokens da IA
- Imagens de baixa qualidade podem gerar classificacoes erradas
- Latencia variavel dependendo do tamanho do documento

## G) Operacao e Validacao

### Como Rodar

```bash
# Servidor
uvicorn main:app --reload

# Acessar frontend
http://localhost:8000/classificador
```

### Como Testar

```bash
# Classificar PDF
curl -X POST http://localhost:8000/classificador/api/classificar \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"files": [{"filename": "doc.pdf", "content_base64": "..."}]}'
```

### Configuracao no Admin

Acesse `/admin/prompts-config` > Aba "Sistemas Acessorios":

| Campo | Descricao | Padrao |
|-------|-----------|--------|
| Modelo | Modelo de IA para classificacao | gemini-2.5-flash-lite |
| Temperatura | Temperatura de geracao | 0.1 |
| Threshold | Confianca minima para aceitar | 0.5 |

## H) Riscos e Dividas Tecnicas

### Riscos

| Risco | Impacto | Mitigacao Sugerida |
|-------|---------|-------------------|
| Classificacao incorreta | Medio - documento vai para categoria errada | Melhorar prompts, ajustar threshold |
| PDFs escaneados de baixa qualidade | Alto - OCR falha | Implementar pre-processamento de imagem |
| Custo de API | Baixo - por documento | Cachear classificacoes similares |

### Dividas Tecnicas

| Item | Descricao | Prioridade |
|------|-----------|------------|
| Testes automatizados | Poucos testes para edge cases | P1 |
| Cache de classificacao | Documentos identicos nao sao cacheados | P2 |
| Metricas de qualidade | Nao ha metricas de acuracia em producao | P2 |
| Limite de paginas | Nao ha limite de paginas por PDF | P3 |

## Arquivos Principais

| Arquivo | Descricao |
|---------|-----------|
| `sistemas/classificador_documentos/router.py` | Endpoints FastAPI |
| `sistemas/classificador_documentos/services.py` | Logica de classificacao |
| `sistemas/classificador_documentos/services_tjms.py` | Integracao com TJ-MS |
| `sistemas/classificador_documentos/templates/` | Frontend SPA |
| `docs/DOCUMENT_CLASSIFIER.md` | Documentacao adicional do classificador |
