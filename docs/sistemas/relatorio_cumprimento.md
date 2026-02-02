# Sistema: Relatorio de Cumprimento

> Documentacao tecnica do modulo de geracao automatizada de relatorios de cumprimento de sentenca.

## A) Visao Geral

O sistema de Relatorio de Cumprimento automatiza a geracao de relatorios sobre processos de cumprimento de sentenca. Identifica o processo principal (conhecimento), localiza o transito em julgado, baixa documentos relevantes e gera relatorio estruturado sobre o estado do cumprimento.

**Usuarios**: Procuradores da CPCC
**Problema resolvido**: Automatizar a analise de processos de cumprimento de sentenca com identificacao de transito em julgado, valores devidos e status do cumprimento

## B) Regras de Negocio

### B.1) Identificacao de Processos

| Regra | Descricao | Fonte no Codigo |
|-------|-----------|-----------------|
| Processo de Cumprimento | Processo informado pelo usuario (CNJ) | `sistemas/relatorio_cumprimento/services.py` |
| Processo Principal | Identificado automaticamente via incidentes/apensos | `sistemas/relatorio_cumprimento/services.py` |
| Processo de Conhecimento | Processo original onde houve condenacao | `sistemas/relatorio_cumprimento/services.py` |

### B.2) Classificacao de Documentos

| Regra | Descricao | Fonte no Codigo |
|-------|-----------|-----------------|
| Sentencas | Codigo 3 ou 523 - decisao de primeiro grau | `sistemas/relatorio_cumprimento/models.py` |
| Acordaos | Codigos 9500-9599 - decisao de segundo grau | `sistemas/relatorio_cumprimento/models.py` |
| Certidoes | Certidao de transito em julgado | `sistemas/relatorio_cumprimento/models.py` |
| Peticoes | Peticoes de cumprimento | `sistemas/relatorio_cumprimento/models.py` |

### B.3) Localizacao do Transito em Julgado

| Regra | Descricao | Fonte no Codigo |
|-------|-----------|-----------------|
| Certidao de Transito | Busca certidao especifica | `sistemas/relatorio_cumprimento/services.py` |
| Movimentos | Analisa movimentos do processo | `sistemas/relatorio_cumprimento/services.py` |
| Acordao Final | Ultimo acordao sem recurso pendente | `sistemas/relatorio_cumprimento/services.py` |

### B.4) Deteccao de Agravo de Instrumento

| Regra | Descricao | Fonte no Codigo |
|-------|-----------|-----------------|
| Agravo Pendente | Verifica se ha agravo de instrumento pendente | `sistemas/relatorio_cumprimento/agravo_detector.py` |
| Efeito Suspensivo | Verifica se foi concedido efeito suspensivo | `sistemas/relatorio_cumprimento/agravo_detector.py` |

### B.5) Tratamento de Excecoes

| Situacao | Comportamento | Fonte no Codigo |
|----------|---------------|-----------------|
| Processo sem transito | Alerta no relatorio | `sistemas/relatorio_cumprimento/services.py` |
| Processo nao encontrado | Retorna erro 404 | `sistemas/relatorio_cumprimento/services.py` |
| Documentos inacessiveis | Continua com dados disponiveis | `sistemas/relatorio_cumprimento/services.py` |

## C) Fluxo Funcional

```
[Usuario] Informa numero CNJ do cumprimento
    |
    v
[Router] POST /relatorio-cumprimento/api/processar-stream
    |
    v
[ETAPA 1: Consulta TJ-MS]
    |
    +-> Consulta processo de cumprimento
    +-> Identifica processo principal (conhecimento)
    +-> Extrai dados basicos
    |
    v
[ETAPA 2: Download de Documentos]
    |
    +-> Baixa sentencas do conhecimento
    +-> Baixa acordaos (se houver recurso)
    +-> Baixa certidoes de transito
    +-> Baixa peticoes relevantes
    |
    v
[ETAPA 3: Analise de Transito]
    |
    +-> Localiza data do transito em julgado
    +-> Verifica se ha agravo pendente
    +-> Identifica ultimo ato decisorio
    |
    v
[ETAPA 4: Geracao do Relatorio]
    |
    +-> Consolida informacoes
    +-> Gera relatorio em Markdown
    +-> Inclui cronologia processual
    +-> Lista pendencias (se houver)
    |
    v
[Banco] Persiste em geracoes_relatorio_cumprimento
    |
    v
[Response] SSE com progresso + relatorio final
```

## D) API/Rotas

### Endpoints Principais

| Metodo | Rota | Descricao |
|--------|------|-----------|
| POST | `/relatorio-cumprimento/api/processar-stream` | Pipeline completo com SSE |
| POST | `/relatorio-cumprimento/api/exportar-docx` | Exportar para DOCX |
| POST | `/relatorio-cumprimento/api/exportar-pdf` | Exportar para PDF |
| POST | `/relatorio-cumprimento/api/editar` | Editar relatorio via chat |
| GET | `/relatorio-cumprimento/api/historico` | Lista relatorios do usuario |
| GET | `/relatorio-cumprimento/api/historico/{id}` | Detalhes de um relatorio |
| GET | `/relatorio-cumprimento/api/documento/{numero}/{id}` | Obtem documento do TJ-MS |

### Payload de Processamento

```json
{
  "numero_cnj": "0804330-09.2024.8.12.0017",
  "sobrescrever_existente": false
}
```

### Estrutura do Relatorio

```markdown
# RELATÓRIO DE CUMPRIMENTO DE SENTENÇA

## 1. IDENTIFICAÇÃO
- **Processo de Cumprimento**: 0804330-09.2024.8.12.0017
- **Processo Principal**: 0012345-67.2020.8.12.0001
- **Exequente**: JOÃO SILVA
- **Executado**: ESTADO DE MATO GROSSO DO SUL

## 2. TRÂNSITO EM JULGADO
- **Data**: 15/03/2024
- **Fundamento**: Certidão de Trânsito às fls. 450

## 3. CRONOLOGIA PROCESSUAL
...

## 4. PENDÊNCIAS
- [ ] Agravo de Instrumento pendente
- [x] Trânsito em julgado certificado
```

## E) Dados e Persistencia

### Tabelas

| Tabela | Descricao |
|--------|-----------|
| `geracoes_relatorio_cumprimento` | Registro de relatorios |
| `documentos_classificados` | Documentos baixados e classificados |
| `dados_processo` | Dados estruturados do processo |
| `info_transito_julgado` | Informacoes de transito |

### Modelo `GeracaoRelatorioCumprimento`

| Campo | Tipo | Descricao |
|-------|------|-----------|
| id | Integer | PK |
| numero_processo_cumprimento | String | CNJ do cumprimento |
| numero_processo_principal | String | CNJ do conhecimento |
| dados_processo | JSON | Dados extraidos |
| documentos | JSON | Lista de documentos |
| transito_julgado | JSON | Info do transito |
| relatorio_markdown | Text | Relatorio gerado |
| status | String | processando, concluido, erro |
| usuario_id | Integer | FK para users |
| created_at | DateTime | Data de criacao |

## F) Integracoes Externas

### TJ-MS (SOAP/MNI)

- Consulta de processos (conhecimento e cumprimento)
- Download de documentos
- Listagem de movimentos

### Google Gemini

| Funcao | Modelo Default |
|--------|----------------|
| Analise de documentos | gemini-3-flash-preview |
| Geracao de relatorio | gemini-3-flash-preview |

## G) Operacao e Validacao

### Como Rodar

```bash
uvicorn main:app --reload
# Acessar: http://localhost:8000/relatorio-cumprimento
```

### Como Testar

```bash
curl -X POST http://localhost:8000/relatorio-cumprimento/api/processar-stream \
  -H "Authorization: Bearer TOKEN" \
  -d '{"numero_cnj": "0804330-09.2024.8.12.0017"}'
```

## H) Riscos e Dividas Tecnicas

### Riscos

| Risco | Impacto | Mitigacao Sugerida |
|-------|---------|-------------------|
| Processo principal nao identificado | Alto - relatorio incompleto | Melhorar heuristica de identificacao |
| Transito em julgado incorreto | Alto - informacao critica errada | Validacao manual obrigatoria |

### Dividas Tecnicas

| Item | Descricao | Prioridade |
|------|-----------|------------|
| Identificacao de principal | Heuristica pode falhar em casos complexos | P1 |
| Cache de documentos | Documentos re-baixados a cada processamento | P2 |
| Integracao com pedido de calculo | Nao compartilha dados com sistema de calculo | P2 |

## Arquivos Principais

| Arquivo | Descricao |
|---------|-----------|
| `sistemas/relatorio_cumprimento/router.py` | Endpoints FastAPI |
| `sistemas/relatorio_cumprimento/services.py` | Orquestrador do pipeline |
| `sistemas/relatorio_cumprimento/agravo_detector.py` | Detector de agravos |
| `sistemas/relatorio_cumprimento/models.py` | Modelos SQLAlchemy |
