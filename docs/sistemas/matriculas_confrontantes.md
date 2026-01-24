# Sistema: Matriculas Confrontantes

> Documentacao tecnica do modulo de analise de matriculas imobiliarias confrontantes.

## A) Visao Geral

O sistema de Matriculas Confrontantes analisa documentos de matriculas imobiliarias para identificar confrontacoes, sobreposicoes e inconsistencias entre propriedades. Usa IA para extrair informacoes de PDFs de matriculas e comparar descricoes de divisas.

**Usuarios**: Procuradores da Procuradoria Patrimonial
**Problema resolvido**: Automatizar a analise de confrontacao de matriculas imobiliarias em processos de regularizacao fundiaria e conflitos de terras

## B) Regras de Negocio

### B.1) Upload e Gerenciamento de Arquivos

| Regra | Descricao | Fonte no Codigo |
|-------|-----------|-----------------|
| Formatos Aceitos | PDF e imagens (PNG, JPG) | `sistemas/matriculas_confrontantes/services.py` |
| Vinculo a Usuario | Arquivos sao vinculados ao usuario que fez upload | `sistemas/matriculas_confrontantes/router.py:109-144` |
| Persistencia | Arquivos salvos em disco + metadados no banco | `sistemas/matriculas_confrontantes/models.py` |

### B.2) Extracao de Informacoes

| Regra | Descricao | Fonte no Codigo |
|-------|-----------|-----------------|
| Numero da Matricula | Extrai numero de registro | `sistemas/matriculas_confrontantes/services_ia.py` |
| Descricao do Imovel | Endereco, area, confrontacoes | `sistemas/matriculas_confrontantes/services_ia.py` |
| Proprietario | Nome e qualificacao | `sistemas/matriculas_confrontantes/services_ia.py` |
| Confrontantes | Lista de imoveis confrontantes | `sistemas/matriculas_confrontantes/services_ia.py` |

### B.3) Analise de Confrontacao

| Regra | Descricao | Fonte no Codigo |
|-------|-----------|-----------------|
| Comparacao de Divisas | Verifica se divisas citam mesmos confrontantes | `sistemas/matriculas_confrontantes/services_ia.py` |
| Deteccao de Sobreposicao | Identifica descricoes que sugerem sobreposicao | `sistemas/matriculas_confrontantes/services_ia.py` |
| Inconsistencias | Lista divergencias entre matriculas | `sistemas/matriculas_confrontantes/services_ia.py` |

### B.4) Analise em Lote

| Regra | Descricao | Fonte no Codigo |
|-------|-----------|-----------------|
| Grupo de Analise | Multiplas matriculas podem ser agrupadas | `sistemas/matriculas_confrontantes/router.py:58-61` |
| Matricula Principal | Uma matricula e definida como principal para comparacao | `sistemas/matriculas_confrontantes/router.py` |
| Relatorio Consolidado | Gera relatorio comparando todas as matriculas do grupo | `sistemas/matriculas_confrontantes/services.py` |

### B.5) Tratamento de Excecoes

| Situacao | Comportamento | Fonte no Codigo |
|----------|---------------|-----------------|
| PDF ilegivel | Tenta OCR, senao marca como erro | `sistemas/matriculas_confrontantes/services.py` |
| Matricula sem confrontantes | Retorna analise parcial | `sistemas/matriculas_confrontantes/services_ia.py` |
| Arquivo muito grande | Rejeita com erro 413 | `sistemas/matriculas_confrontantes/router.py` |

## C) Fluxo Funcional

### Fluxo de Analise Individual

```
[Usuario] Upload de PDF da matricula
    |
    v
[Router] POST /matriculas/api/files/upload
    |
    v
[Service] Salva arquivo + metadados
    |
    v
[Usuario] Solicita analise
    |
    v
[Router] POST /matriculas/api/analyze/{file_id}
    |
    v
[IA Service] Extrai texto do PDF
    |
    v
[Gemini] Extrai informacoes estruturadas
    |
    +-> Numero da matricula
    +-> Descricao do imovel
    +-> Area
    +-> Confrontantes
    +-> Proprietario
    |
    v
[Banco] Persiste em analises
    |
    v
[Response] Dados extraidos + status
```

### Fluxo de Analise em Lote

```
[Usuario] Seleciona multiplos arquivos + define matricula principal
    |
    v
[Router] POST /matriculas/api/analyze-batch
    |
    v
[Service] Cria grupo de analise
    |
    v
[Para cada arquivo]
    +-> Extrai informacoes com IA
    |
    v
[IA Service] Compara matriculas do grupo
    |
    +-> Verifica confrontacoes cruzadas
    +-> Identifica sobreposicoes
    +-> Lista inconsistencias
    |
    v
[Response] Relatorio consolidado
```

## D) API/Rotas

### Endpoints de Arquivos

| Metodo | Rota | Descricao |
|--------|------|-----------|
| GET | `/matriculas/api/files` | Lista arquivos do usuario |
| POST | `/matriculas/api/files/upload` | Upload de arquivo |
| GET | `/matriculas/api/files/{file_id}/view` | Visualiza arquivo |
| DELETE | `/matriculas/api/files/{file_id}` | Remove arquivo |

### Endpoints de Analise

| Metodo | Rota | Descricao |
|--------|------|-----------|
| POST | `/matriculas/api/analyze/{file_id}` | Analisa arquivo individual |
| POST | `/matriculas/api/analyze-batch` | Analisa lote de arquivos |
| GET | `/matriculas/api/analyze/{file_id}/result` | Resultado da analise |

### Payload de Analise em Lote

```json
{
  "file_ids": ["file_001", "file_002", "file_003"],
  "nome_grupo": "Fazenda Santa Maria",
  "matricula_principal": "file_001"
}
```

## E) Dados e Persistencia

### Tabelas

| Tabela | Descricao |
|--------|-----------|
| `analises_matricula` | Registro de analises |
| `registros_matricula` | Dados extraidos |
| `logs_sistema` | Logs de operacao |
| `feedbacks_matricula` | Feedback dos usuarios |
| `grupos_analise` | Grupos de matriculas |
| `arquivos_upload` | Metadados de arquivos |

### Modelo `Analise`

| Campo | Tipo | Descricao |
|-------|------|-----------|
| id | Integer | PK |
| file_id | String | ID do arquivo |
| numero_matricula | String | Numero extraido |
| descricao_imovel | Text | Descricao completa |
| area | String | Area em hectares/m2 |
| confrontantes | JSON | Lista de confrontantes |
| proprietario | String | Nome do proprietario |
| status | String | pendente, processando, concluido, erro |
| usuario_id | Integer | FK para users |
| created_at | DateTime | Data de criacao |

## F) Integracoes Externas

### Google Gemini

| Funcao | Modelo Default |
|--------|----------------|
| Extracao de dados | gemini-3-flash-preview |
| Analise de confrontacao | gemini-3-flash-preview |
| Relatorio consolidado | gemini-3-pro-preview |

### Armazenamento

| Local | Conteudo |
|-------|----------|
| `uploads/matriculas/` | Arquivos PDF originais |
| Banco de dados | Metadados e resultados |

## G) Operacao e Validacao

### Como Rodar

```bash
uvicorn main:app --reload
# Acessar: http://localhost:8000/matriculas
```

### Como Testar

```bash
# Upload de arquivo
curl -X POST http://localhost:8000/matriculas/api/files/upload \
  -H "Authorization: Bearer TOKEN" \
  -F "file=@matricula.pdf"

# Analisar arquivo
curl -X POST http://localhost:8000/matriculas/api/analyze/FILE_ID \
  -H "Authorization: Bearer TOKEN"
```

## H) Riscos e Dividas Tecnicas

### Riscos

| Risco | Impacto | Mitigacao Sugerida |
|-------|---------|-------------------|
| Matriculas antigas (manuscritas) | Alto - OCR falha | Melhorar pipeline de OCR |
| Descricoes de divisas ambiguas | Medio - analise incorreta | Validacao humana |

### Dividas Tecnicas

| Item | Descricao | Prioridade |
|------|-----------|------------|
| OCR para manuscritos | Nao suporta matriculas antigas | P1 |
| Georeferenciamento | Nao integra com mapas | P2 |
| Comparacao automatica | Logica de sobreposicao simplificada | P2 |

## Arquivos Principais

| Arquivo | Descricao |
|---------|-----------|
| `sistemas/matriculas_confrontantes/router.py` | Endpoints FastAPI |
| `sistemas/matriculas_confrontantes/services.py` | Logica de negocio |
| `sistemas/matriculas_confrontantes/services_ia.py` | Integracao com IA |
| `sistemas/matriculas_confrontantes/models.py` | Modelos SQLAlchemy |
| `sistemas/matriculas_confrontantes/schemas.py` | Schemas Pydantic |
