# BERT Training - Sistema de Treinamento de Classificadores

> Documentacao tecnica do modulo de treinamento BERT integrado ao Portal PGE-MS.

## Visao Geral

O sistema BERT Training permite treinar classificadores de texto usando modelos BERT, com arquitetura hibrida:

- **Cloud (Railway)**: UI + API + BD + storage Excel + logs/metricas
- **Worker Local (GPU)**: Executa treinamento na GPU do PC local

```
┌─────────────────────────────────────────────────────────────────┐
│                    ARQUITETURA BERT TRAINING                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   [Browser] ──────► [Railway/Cloud]                              │
│       │             ┌──────────────────┐                         │
│       │             │ FastAPI Server   │                         │
│       │             │ - Upload Excel   │                         │
│       │             │ - Criar Runs     │                         │
│       │             │ - Fila de Jobs   │                         │
│       │             │ - Metricas/Logs  │                         │
│       │             └────────┬─────────┘                         │
│       │                      │ API                               │
│       │                      ▼                                   │
│       │             ┌──────────────────┐                         │
│       │             │ PostgreSQL       │                         │
│       │             │ - Datasets       │                         │
│       │             │ - Runs           │                         │
│       │             │ - Jobs           │                         │
│       │             │ - Metricas       │                         │
│       │             │ - Workers        │                         │
│       │             └──────────────────┘                         │
│       │                                                          │
│       └─────────────────────────────────────────────┐            │
│                                                      │            │
│   [Worker Local]                                     │ Pull Jobs  │
│   ┌──────────────────────────────────────────┐      │            │
│   │ PC com GPU (RTX 4080, etc)               │◄─────┘            │
│   │ - Faz pull de jobs pendentes             │                   │
│   │ - Baixa Excel do dataset                 │                   │
│   │ - Treina modelo com PyTorch/CUDA         │                   │
│   │ - Envia metricas/logs para cloud         │                   │
│   │ - Salva modelo LOCAL (nao envia pesos)   │                   │
│   └──────────────────────────────────────────┘                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Tipos de Tarefa Suportados

### 1. Text Classification
- **Entrada**: Coluna de texto (strings)
- **Saida**: Coluna de labels (categorias)
- **Exemplo**: Classificar documentos juridicos por tipo

### 2. Token Classification (NER/BIO)
- **Entrada**: Coluna de tokens (JSON array de strings)
- **Saida**: Coluna de tags (JSON array de tags BIO)
- **Exemplo**: Identificar entidades em textos (pessoas, locais, etc)

## Formato do Excel

### Text Classification
| texto | label |
|-------|-------|
| "O autor requer indenizacao..." | "indenizacao" |
| "Trata-se de acao de cobranca..." | "cobranca" |

### Token Classification
| tokens | tags |
|--------|------|
| `["O", "Joao", "mora", "em", "SP"]` | `["O", "B-PER", "O", "O", "B-LOC"]` |
| `["Maria", "trabalha", "no", "RJ"]` | `["B-PER", "O", "O", "B-LOC"]` |

## Endpoints da API

### Datasets
```
POST   /bert-training/api/datasets/validate     # Validar Excel antes de upload
POST   /bert-training/api/datasets/upload       # Upload de dataset
GET    /bert-training/api/datasets              # Listar datasets
GET    /bert-training/api/datasets/{id}         # Detalhes do dataset
GET    /bert-training/api/datasets/{id}/download # Download do Excel
```

### Runs
```
POST   /bert-training/api/runs                  # Criar run e colocar na fila
GET    /bert-training/api/runs                  # Listar runs
GET    /bert-training/api/runs/{id}             # Detalhes do run
GET    /bert-training/api/runs/{id}/metrics     # Metricas por epoca
GET    /bert-training/api/runs/{id}/logs        # Logs em tempo real (SSE)
POST   /bert-training/api/runs/{id}/reproduce   # Reproduzir run existente
```

### Jobs (Worker API)
```
POST   /bert-training/api/jobs/claim            # Worker pega job da fila
POST   /bert-training/api/jobs/{id}/progress    # Worker atualiza progresso
POST   /bert-training/api/jobs/{id}/complete    # Worker marca job completo
```

### Metricas e Logs (Worker API)
```
POST   /bert-training/api/metrics               # Worker envia metricas
POST   /bert-training/api/logs                  # Worker envia log
POST   /bert-training/api/logs/batch            # Worker envia logs em lote
```

### Workers (Admin)
```
POST   /bert-training/api/workers/register      # Registrar novo worker
GET    /bert-training/api/workers               # Listar workers
POST   /bert-training/api/workers/heartbeat     # Worker envia heartbeat
```

### Fila
```
GET    /bert-training/api/queue/status          # Status da fila de jobs
```

## Configuracao do Worker Local

### Requisitos
- Python 3.10+
- CUDA 12.x
- GPU NVIDIA (RTX 4080 recomendado)
- 16GB+ VRAM

### Instalacao
```bash
# Clonar repo e instalar dependencias
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
pip install transformers pandas openpyxl requests loguru scikit-learn
```

### Registrar Worker (Admin)
1. No painel admin, va em Workers
2. Clique em "Registrar Worker"
3. Preencha nome e descricao
4. Copie o token gerado (mostrado apenas uma vez!)

### Executar Worker
```bash
cd portal-pge
python -m sistemas.bert_training.worker.bert_worker \
    --api-url https://portal-pge.up.railway.app \
    --token SEU_TOKEN_AQUI \
    --models-dir ./bert_models
```

### Opcoes do Worker
```
--api-url       URL da API (obrigatorio)
--token         Token de autenticacao (obrigatorio)
--models-dir    Diretorio para salvar modelos (default: ./bert_models)
--poll-interval Intervalo entre verificacoes em segundos (default: 30)
--dry-run       Simula execucao sem treinar (para testes)
--debug         Ativa logs de debug
```

## Hiperparametros

| Parametro | Default | Descricao |
|-----------|---------|-----------|
| learning_rate | 5e-5 | Taxa de aprendizado |
| batch_size | 16 | Tamanho do batch |
| epochs | 10 | Numero de epocas |
| max_length | 512 | Tamanho maximo da sequencia |
| train_split | 0.7 | Proporcao treino/validacao |
| warmup_steps | 0 | Steps de warmup |
| weight_decay | 0.01 | Regularizacao |
| early_stopping_patience | 3 | Epocas sem melhoria para parar |
| use_class_weights | true | Balanceamento de classes |
| seed | 42 | Seed para reproducibilidade |
| truncation_side | right | Lado do truncamento (right/left) |

## Modelos Base Suportados

| Modelo | Tamanho | Uso |
|--------|---------|-----|
| neuralmind/bert-base-portuguese-cased | ~440MB | Portugues (recomendado) |
| neuralmind/bert-large-portuguese-cased | ~1.3GB | Portugues (maior) |
| bert-base-multilingual-cased | ~680MB | Multilingue |
| xlm-roberta-base | ~1.1GB | Multilingue (melhor) |

## Reproducibilidade

Cada run salva:
- SHA256 do dataset
- Todos os hiperparametros
- Commit hash do codigo (git)
- Fingerprint do ambiente (hash do requirements.txt)
- Seed para split deterministico

Para reproduzir um run, use o botao "Reproduzir" na UI ou:
```
POST /bert-training/api/runs/{id}/reproduce
```

## Banco de Dados

### Tabelas
| Tabela | Descricao |
|--------|-----------|
| bert_datasets | Datasets Excel enviados |
| bert_runs | Experimentos de treinamento |
| bert_jobs | Fila de jobs |
| bert_metrics | Metricas por epoca |
| bert_logs | Logs estruturados |
| bert_workers | Workers registrados |

### Indices
- `ix_bert_datasets_sha256_hash` - Busca por hash (idempotencia)
- `ix_bert_runs_status` - Filtragem por status
- `ix_bert_jobs_status` - Fila de jobs pendentes
- `ix_bert_metrics_run_id` - Metricas por run
- `ix_bert_logs_timestamp` - Logs ordenados

## Seguranca

### Autenticacao Worker
- Cada worker tem token unico (SHA256 hash no banco)
- Token e mostrado apenas uma vez no registro
- Workers inativos podem ser desativados

### Nao Enviamos para Cloud
- Pesos do modelo treinado (ficam no PC local)
- Dados sensíveis do Excel alem do hash

### Enviamos para Cloud
- Excel original (para reproducibilidade)
- Configuracoes e hiperparametros
- Metricas e logs de treinamento
- Fingerprint do modelo (hash, sem pesos)

## Troubleshooting

### Worker nao conecta
1. Verifique se a URL da API esta correta
2. Verifique se o token esta correto
3. Teste com `--dry-run` para verificar conectividade

### GPU nao detectada
1. Verifique instalacao do CUDA: `nvidia-smi`
2. Verifique PyTorch: `python -c "import torch; print(torch.cuda.is_available())"`
3. Reinstale PyTorch com CUDA correto

### Out of Memory
1. Reduza `batch_size`
2. Reduza `max_length`
3. Ative `gradient_accumulation_steps`

### Treinamento muito lento
1. Verifique se esta usando GPU (logs mostram device)
2. Aumente `batch_size` se tiver VRAM disponivel
3. Use modelo base menor

## Estrutura de Arquivos

```
sistemas/bert_training/
├── __init__.py
├── router.py           # Endpoints FastAPI
├── models.py           # SQLAlchemy models
├── schemas.py          # Pydantic schemas
├── services.py         # Logica de negocio
├── ml/
│   ├── __init__.py
│   ├── classifier.py   # BertClassifier
│   ├── dataset.py      # TextClassificationDataset
│   ├── training.py     # Trainer
│   └── evaluation.py   # Evaluator
├── worker/
│   ├── __init__.py
│   └── bert_worker.py  # Worker local GPU
└── templates/
    ├── index.html      # Frontend
    └── app.js          # JavaScript
```
