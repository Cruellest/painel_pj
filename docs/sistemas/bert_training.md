# Sistema: BERT Training

> Documentacao tecnica do modulo de treinamento de classificadores BERT.

## A) Visao Geral

O sistema BERT Training permite treinar classificadores de texto usando modelos BERT, com arquitetura hibrida cloud/local. O servidor (Railway) gerencia datasets, runs e metricas, enquanto workers locais com GPU executam o treinamento.

**Usuarios**: Cientistas de dados e desenvolvedores da PGE-MS
**Problema resolvido**: Treinar modelos de classificacao de documentos juridicos sem infraestrutura propria de GPU na nuvem

## B) Regras de Negocio

### B.1) Gerenciamento de Datasets

| Regra | Descricao | Fonte no Codigo |
|-------|-----------|-----------------|
| Formato Excel | Dataset deve ser arquivo Excel (.xlsx) com colunas texto/label ou tokens/tags | `sistemas/bert_training/services.py:50-120` |
| Validacao Previa | Excel e validado antes do upload (colunas, tipos, valores) | `sistemas/bert_training/router.py:80-130` |
| Hash SHA256 | Cada dataset tem hash unico para idempotencia | `sistemas/bert_training/models.py:BertDataset` |
| Tipos de Tarefa | Suporta `text_classification` e `token_classification` (NER/BIO) | `sistemas/bert_training/schemas.py` |

### B.2) Gerenciamento de Runs

| Regra | Descricao | Fonte no Codigo |
|-------|-----------|-----------------|
| Fila de Jobs | Runs sao enfileirados como jobs pendentes | `sistemas/bert_training/services.py:200-250` |
| Status de Run | pending -> running -> completed/failed | `sistemas/bert_training/models.py:BertRun` |
| Reproducibilidade | Cada run salva seed, hiperparametros e hash do dataset | `sistemas/bert_training/models.py:BertRun` |
| Hiperparametros | learning_rate, batch_size, epochs, max_length, train_split, etc | `sistemas/bert_training/schemas.py` |

### B.3) Workers e Fila

| Regra | Descricao | Fonte no Codigo |
|-------|-----------|-----------------|
| Registro de Worker | Workers sao registrados com token unico (SHA256) | `sistemas/bert_training/services.py:300-350` |
| Claim de Job | Worker faz pull de job pendente, marca como running | `sistemas/bert_training/router.py:200-230` |
| Heartbeat | Workers enviam heartbeat periodico para monitoramento | `sistemas/bert_training/router.py:250-270` |
| Timeout de Job | Jobs sem heartbeat por X minutos sao marcados como failed | `sistemas/bert_training/services.py` |

### B.4) Metricas e Logs

| Regra | Descricao | Fonte no Codigo |
|-------|-----------|-----------------|
| Metricas por Epoca | loss, accuracy, f1-score enviados a cada epoca | `sistemas/bert_training/router.py:280-310` |
| Logs Estruturados | Logs de treinamento armazenados em batch | `sistemas/bert_training/router.py:320-350` |
| Early Stopping | Treinamento para apos N epocas sem melhoria (default: 3) | `sistemas/bert_training/ml/training.py` |

### B.5) Tratamento de Excecoes

| Situacao | Comportamento | Fonte no Codigo |
|----------|---------------|-----------------|
| Excel invalido | Retorna erro 422 com detalhes de validacao | `sistemas/bert_training/router.py` |
| Worker desconectado | Job volta para fila apos timeout | `sistemas/bert_training/services.py` |
| OOM GPU | Worker reporta erro, job marcado como failed | `sistemas/bert_training/ml/training.py` |
| Token invalido | Worker rejeitado com 401 | `sistemas/bert_training/router.py` |

## C) Fluxo Funcional

### Fluxo de Treinamento

```
[Admin] Upload Excel
    |
    v
[API] Valida e persiste dataset
    |
    v
[Admin] Cria Run com hiperparametros
    |
    v
[API] Cria Job na fila (status=pending)
    |
    v
[Worker Local] Poll /jobs/claim
    |
    v
[Worker] Baixa Excel, treina modelo com GPU
    |
    +-> Envia metricas/logs para cloud
    |
    v
[Worker] Salva modelo LOCAL, marca job=completed
    |
    v
[API] Atualiza run com status final e metricas
```

### Fluxo do Worker

```
[Worker] Registra-se com token
    |
    v
[Loop] Poll /jobs/claim a cada 30s
    |
    v
[Job Encontrado] Baixa dataset, inicia treinamento
    |
    v
[Treinamento] Para cada epoca:
    +-> Envia metricas POST /metrics
    +-> Envia logs POST /logs/batch
    +-> Envia heartbeat POST /workers/heartbeat
    |
    v
[Fim] POST /jobs/{id}/complete
    |
    v
[Modelo] Salvo em disco local (nao enviado para cloud)
```

## D) API/Rotas

### Datasets

| Metodo | Rota | Descricao |
|--------|------|-----------|
| POST | `/bert-training/api/datasets/validate` | Validar Excel antes de upload |
| POST | `/bert-training/api/datasets/upload` | Upload de dataset |
| GET | `/bert-training/api/datasets` | Listar datasets |
| GET | `/bert-training/api/datasets/{id}` | Detalhes do dataset |
| GET | `/bert-training/api/datasets/{id}/download` | Download do Excel |

### Runs

| Metodo | Rota | Descricao |
|--------|------|-----------|
| POST | `/bert-training/api/runs` | Criar run e colocar na fila |
| GET | `/bert-training/api/runs` | Listar runs |
| GET | `/bert-training/api/runs/{id}` | Detalhes do run |
| GET | `/bert-training/api/runs/{id}/metrics` | Metricas por epoca |
| GET | `/bert-training/api/runs/{id}/logs` | Logs em tempo real (SSE) |
| POST | `/bert-training/api/runs/{id}/reproduce` | Reproduzir run existente |

### Jobs (Worker API)

| Metodo | Rota | Descricao |
|--------|------|-----------|
| POST | `/bert-training/api/jobs/claim` | Worker pega job da fila |
| POST | `/bert-training/api/jobs/{id}/progress` | Worker atualiza progresso |
| POST | `/bert-training/api/jobs/{id}/complete` | Worker marca job completo |

### Workers

| Metodo | Rota | Descricao |
|--------|------|-----------|
| POST | `/bert-training/api/workers/register` | Registrar novo worker |
| GET | `/bert-training/api/workers` | Listar workers |
| POST | `/bert-training/api/workers/heartbeat` | Worker envia heartbeat |

## E) Dados e Persistencia

### Tabelas

| Tabela | Descricao |
|--------|-----------|
| `bert_datasets` | Datasets Excel enviados |
| `bert_runs` | Experimentos de treinamento |
| `bert_jobs` | Fila de jobs |
| `bert_metrics` | Metricas por epoca |
| `bert_logs` | Logs estruturados |
| `bert_workers` | Workers registrados |

### Indices

| Indice | Tabela | Uso |
|--------|--------|-----|
| `ix_bert_datasets_sha256_hash` | bert_datasets | Busca por hash (idempotencia) |
| `ix_bert_runs_status` | bert_runs | Filtragem por status |
| `ix_bert_jobs_status` | bert_jobs | Fila de jobs pendentes |
| `ix_bert_metrics_run_id` | bert_metrics | Metricas por run |
| `ix_bert_logs_timestamp` | bert_logs | Logs ordenados |

### O que NAO e persistido

- Pesos do modelo treinado (ficam no PC local do worker)
- Dados intermediarios de treinamento (gradientes, checkpoints)

## F) Integracoes Externas

### Worker Local (GPU)

| Configuracao | Descricao |
|--------------|-----------|
| API URL | URL do servidor Railway |
| Token | Token de autenticacao do worker |
| Models Dir | Diretorio local para salvar modelos |

### Modelos Base (HuggingFace)

| Modelo | Tamanho | Uso |
|--------|---------|-----|
| neuralmind/bert-base-portuguese-cased | ~440MB | Portugues (recomendado) |
| neuralmind/bert-large-portuguese-cased | ~1.3GB | Portugues (maior) |
| bert-base-multilingual-cased | ~680MB | Multilingue |
| xlm-roberta-base | ~1.1GB | Multilingue (melhor) |

### Pontos Frageis

- Worker local pode desconectar durante treinamento longo
- GPU pode ficar sem memoria (OOM) em batches grandes
- Conexao instavel pode perder metricas/logs

## G) Operacao e Validacao

### Como Rodar o Servidor

```bash
# Servidor (Railway ou local)
uvicorn main:app --reload

# Acessar frontend
http://localhost:8000/bert-training
```

### Como Rodar o Worker

```bash
# Requisitos: Python 3.10+, CUDA 12.x, GPU NVIDIA
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
pip install transformers pandas openpyxl requests loguru scikit-learn

# Executar worker
python -m sistemas.bert_training.worker.bert_worker \
    --api-url https://portal-pge.up.railway.app \
    --token SEU_TOKEN_AQUI \
    --models-dir ./bert_models
```

### Como Testar

```bash
# Validar Excel
curl -X POST http://localhost:8000/bert-training/api/datasets/validate \
  -H "Authorization: Bearer TOKEN" \
  -F "file=@dataset.xlsx"

# Verificar status da fila
curl http://localhost:8000/bert-training/api/queue/status \
  -H "Authorization: Bearer TOKEN"
```

## H) Riscos e Dividas Tecnicas

### Riscos

| Risco | Impacto | Mitigacao Sugerida |
|-------|---------|-------------------|
| Worker desconecta no meio | Medio - job perdido | Implementar checkpoints |
| OOM em GPU | Medio - job falha | Ajuste automatico de batch_size |
| Perda de metricas | Baixo - logs perdidos | Buffer local no worker |

### Dividas Tecnicas

| Item | Descricao | Prioridade |
|------|-----------|------------|
| Checkpoints | Nao salva checkpoints intermediarios | P1 |
| Metricas offline | Worker nao bufferiza metricas se cloud indisponivel | P2 |
| Multiplos workers | Nao testado com >1 worker simultaneo | P2 |
| Cancelamento | Nao ha como cancelar job em execucao | P3 |

## Arquivos Principais

| Arquivo | Descricao |
|---------|-----------|
| `sistemas/bert_training/router.py` | Endpoints FastAPI |
| `sistemas/bert_training/models.py` | Modelos SQLAlchemy |
| `sistemas/bert_training/schemas.py` | Schemas Pydantic |
| `sistemas/bert_training/services.py` | Logica de negocio |
| `sistemas/bert_training/ml/classifier.py` | BertClassifier |
| `sistemas/bert_training/ml/training.py` | Trainer |
| `sistemas/bert_training/worker/bert_worker.py` | Worker local GPU |
| `sistemas/bert_training/templates/` | Frontend SPA |
