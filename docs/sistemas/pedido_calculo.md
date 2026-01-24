# Sistema: Pedido de Calculo

> Documentacao tecnica do modulo de geracao automatizada de pedidos de calculo.

## A) Visao Geral

O sistema de Pedido de Calculo automatiza a geracao de pedidos de calculo para processos de cumprimento de sentenca. Analisa XML do TJ-MS, identifica documentos relevantes (sentencas, acordaos, certidoes), extrai informacoes financeiras e gera o pedido de calculo estruturado.

**Usuarios**: Procuradores da Procuradoria Fiscal e CPCC
**Problema resolvido**: Automatizar a analise de processos de cumprimento de sentenca e geracao de pedidos de calculo com identificacao de datas, indices de correcao, juros e valores

## B) Regras de Negocio

### B.1) Pipeline de 3 Agentes

| Agente | Funcao | Usa IA? | Fonte no Codigo |
|--------|--------|---------|-----------------|
| Agente 1 | Analise do XML do processo - extracao direta | Nao | `sistemas/pedido_calculo/agentes.py:91-200` |
| Agente 2 | Extracao de informacoes dos PDFs | Sim (Gemini) | `sistemas/pedido_calculo/agentes.py` |
| Agente 3 | Geracao do pedido de calculo | Sim (Gemini) | `sistemas/pedido_calculo/agentes.py` |

### B.2) Identificacao de Documentos

| Regra | Descricao | Fonte no Codigo |
|-------|-----------|-----------------|
| Sentencas | Codigos 3/523 - decisao de primeiro grau | `sistemas/pedido_calculo/xml_parser.py` |
| Acordaos | Codigos 9500-9599 - decisao de segundo grau | `sistemas/pedido_calculo/xml_parser.py` |
| Certidoes | Codigos especificos para certidao de citacao/intimacao | `sistemas/pedido_calculo/xml_parser.py` |
| Cumprimento | Documentos do processo de cumprimento | `sistemas/pedido_calculo/xml_parser.py` |

### B.3) Extracao de Informacoes Financeiras

| Regra | Descricao | Fonte no Codigo |
|-------|-----------|-----------------|
| Correcao Monetaria | Identifica indice (IPCA-E, SELIC) e data base | `sistemas/pedido_calculo/agentes.py` |
| Juros Moratorios | Taxa e termo inicial (citacao, vencimento, etc) | `sistemas/pedido_calculo/agentes.py` |
| Periodo de Condenacao | Data inicial e final para calculo | `sistemas/pedido_calculo/agentes.py` |
| Valor da Causa | Extrai do XML ou documentos | `sistemas/pedido_calculo/xml_parser.py` |

### B.4) Datas Processuais

| Regra | Descricao | Fonte no Codigo |
|-------|-----------|-----------------|
| Data Citacao | Primeiro dia util posterior a juntada | `sistemas/pedido_calculo/xml_parser.py` |
| Data Transito | Data do transito em julgado | `sistemas/pedido_calculo/agentes.py` |
| Data Intimacao | Data da intimacao para cumprimento | `sistemas/pedido_calculo/agentes.py` |

### B.5) Tratamento de Excecoes

| Situacao | Comportamento | Fonte no Codigo |
|----------|---------------|-----------------|
| RTF ao inves de PDF | Converte RTF para PDF automaticamente | `sistemas/pedido_calculo/router.py:39-119` |
| XML malformado | Retorna erro 400 com detalhes | `sistemas/pedido_calculo/xml_parser.py` |
| Documento ilegivel | Tenta OCR, senao marca como ilegivel | `sistemas/pedido_calculo/agentes.py` |

## C) Fluxo Funcional

```
[Usuario] Informa numero CNJ
    |
    v
[Router] POST /pedido-calculo/api/processar-stream
    |
    v
[AGENTE 1: Analise XML]
    |
    +-> Consulta TJ-MS (SOAP via proxy)
    +-> Extrai dados basicos (partes, datas, valores)
    +-> Identifica documentos para download
    +-> Mapeia movimentos de citacao/intimacao
    |
    v
[AGENTE 2: Extracao de PDFs]
    |
    +-> Baixa documentos identificados
    +-> Extrai texto (PyMuPDF ou OCR)
    +-> Chama Gemini para extrair:
        - Tipo de intimacao
        - Periodo de condenacao
        - Indices de correcao e juros
        - Datas processuais
        - Calculo do exequente (se existir)
    |
    v
[AGENTE 3: Geracao do Pedido]
    |
    +-> Consolida informacoes dos agentes anteriores
    +-> Gera pedido de calculo estruturado
    +-> Retorna em formato JSON + Markdown
    |
    v
[Banco] Persiste em pedidos_calculo
    |
    v
[Response] SSE com progresso + resultado final
```

## D) API/Rotas

### Endpoints Principais

| Metodo | Rota | Descricao |
|--------|------|-----------|
| POST | `/pedido-calculo/api/processar-xml` | Processar XML do processo (Agente 1) |
| POST | `/pedido-calculo/api/baixar-documentos` | Baixar documentos identificados |
| POST | `/pedido-calculo/api/extrair-informacoes` | Extrair informacoes dos PDFs (Agente 2) |
| POST | `/pedido-calculo/api/gerar-pedido` | Gerar pedido de calculo (Agente 3) |
| POST | `/pedido-calculo/api/processar-stream` | Pipeline completo com SSE |
| POST | `/pedido-calculo/api/exportar-docx` | Exportar para DOCX |
| GET | `/pedido-calculo/api/historico` | Listar pedidos do usuario |
| POST | `/pedido-calculo/api/feedback` | Enviar feedback |

### Payload de Processamento

```json
{
  "numero_cnj": "0804330-09.2024.8.12.0017",
  "sobrescrever_existente": false
}
```

### Estrutura do Pedido Gerado

```json
{
  "dados_basicos": {
    "numero_processo": "0804330-09.2024.8.12.0017",
    "autor": "JOAO SILVA",
    "reu": "ESTADO DE MATO GROSSO DO SUL"
  },
  "datas": {
    "citacao": "2024-01-15",
    "transito": "2024-03-20",
    "intimacao": "2024-04-01"
  },
  "correcao_monetaria": {
    "indice": "IPCA-E",
    "data_base": "2024-01-01"
  },
  "juros": {
    "taxa": "1% ao mes",
    "termo_inicial": "citacao"
  },
  "pedido_markdown": "..."
}
```

## E) Dados e Persistencia

### Tabelas

| Tabela | Descricao |
|--------|-----------|
| `pedidos_calculo` | Registro de pedidos gerados |
| `feedbacks_pedido_calculo` | Feedback dos usuarios |

### Modelo `PedidoCalculo`

| Campo | Tipo | Descricao |
|-------|------|-----------|
| id | Integer | PK |
| numero_processo | String | CNJ |
| dados_basicos | JSON | Partes, datas do XML |
| documentos_analisados | JSON | Lista de docs processados |
| resultado_agente2 | JSON | Informacoes extraidas |
| pedido_gerado | Text | Pedido em Markdown |
| usuario_id | Integer | FK para users |
| created_at | DateTime | Data de criacao |

## F) Integracoes Externas

### TJ-MS (SOAP/MNI)

- Mesma integracao do Gerador de Pecas
- Consulta XML do processo
- Download de documentos PDF

### Google Gemini

| Agente | Modelo Default |
|--------|----------------|
| Agente 2 (Extracao) | gemini-3-flash-preview |
| Agente 3 (Geracao) | gemini-3-flash-preview |

## G) Operacao e Validacao

### Como Rodar

```bash
uvicorn main:app --reload
# Acessar: http://localhost:8000/pedido-calculo
```

### Como Testar

```bash
curl -X POST http://localhost:8000/pedido-calculo/api/processar-stream \
  -H "Authorization: Bearer TOKEN" \
  -d '{"numero_cnj": "0804330-09.2024.8.12.0017"}'
```

## H) Riscos e Dividas Tecnicas

### Riscos

| Risco | Impacto | Mitigacao Sugerida |
|-------|---------|-------------------|
| Extracao de datas incorreta | Alto - calculo errado | Validacao manual obrigatoria |
| Documentos escaneados | Medio - OCR falha | Melhorar pipeline de OCR |

### Dividas Tecnicas

| Item | Descricao | Prioridade |
|------|-----------|------------|
| Validacao de calculos | Nao valida consistencia numerica | P1 |
| Integracao com calculadora | Nao integra com calculadora judicial | P2 |
| Testes de extracao | Poucos testes para formatos diversos | P2 |

## Arquivos Principais

| Arquivo | Descricao |
|---------|-----------|
| `sistemas/pedido_calculo/router.py` | Endpoints FastAPI |
| `sistemas/pedido_calculo/services.py` | Orquestracao do pipeline |
| `sistemas/pedido_calculo/agentes.py` | Agentes de IA |
| `sistemas/pedido_calculo/xml_parser.py` | Parser de XML do TJ-MS |
| `sistemas/pedido_calculo/document_downloader.py` | Download de documentos |
| `sistemas/pedido_calculo/models.py` | Modelos de dados |
