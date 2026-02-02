# Banco Vetorial - Busca Semântica de Argumentos Jurídicos

Este documento explica como funciona o sistema de busca vetorial do Portal PGE-MS e como mantê-lo atualizado.

## Visão Geral

O banco vetorial permite que o chatbot do gerador de peças encontre argumentos jurídicos relevantes mesmo quando o usuário não usa as palavras-chave exatas. Isso é feito através de **embeddings** - representações numéricas do significado semântico dos textos.

### Como Funciona

1. **Geração de Embeddings**: Cada módulo de conteúdo tem seu texto convertido em um vetor de 768 dimensões usando a API do Google (`text-embedding-004`)
2. **Armazenamento**: Os vetores são armazenados na tabela `modulo_embeddings`
3. **Busca**: Quando o usuário pede um argumento, a query é convertida em vetor e comparada com os vetores armazenados
4. **Ranking**: Os resultados são ordenados por similaridade de cosseno (0% a 100%)

### Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                    CHATBOT (editar minuta)                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    BUSCA VETORIAL                           │
│         (similaridade semântica via embeddings)             │
│                                                             │
│  - Threshold: 35% de similaridade mínima                    │
│  - Fallback: busca por keyword se não houver embeddings     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                 TABELA: modulo_embeddings                   │
│  - modulo_id (FK → prompt_modulos)                          │
│  - embedding_json (fallback numpy)                          │
│  - embedding_vector (pgvector, se disponível)               │
│  - texto_hash (detecta mudanças)                            │
└─────────────────────────────────────────────────────────────┘
```

### Por que apenas busca vetorial?

A busca por keyword foi desativada porque:
- Retornava resultados irrelevantes por matches parciais (ex: "por" no título)
- A busca vetorial entende o **significado** da query, não apenas palavras
- Resultados mais precisos mesmo com queries informais

A busca por keyword ainda existe como **fallback** caso os embeddings não estejam disponíveis.

## Atualização Automática

### Quando um módulo é criado ou editado

O sistema **atualiza automaticamente** o embedding quando você:
- Cria um novo módulo de conteúdo
- Edita um módulo existente (título, condição, conteúdo, etc.)

A atualização acontece em **background** para não atrasar a resposta da API.

**Campos usados para gerar o embedding:**
- Título
- Categoria e Subcategoria
- Condição de ativação / Regra determinística
- Regra secundária (fallback)
- Conteúdo (truncado em 2048 caracteres)

### Verificação de mudanças

O sistema usa um **hash SHA256** do texto para detectar mudanças. Se o texto não mudou, o embedding não é regerado (economia de API).

## Comandos de Manutenção

### Script de Sincronização

O script `scripts/sync_embeddings.py` permite gerenciar os embeddings manualmente.

#### Ver estatísticas
```bash
python scripts/sync_embeddings.py --stats
```

Saída exemplo:
```
[STATS] ESTATISTICAS DE EMBEDDINGS:
----------------------------------------
    Modulos de conteudo: 55
    Embeddings criados:  55
    Cobertura:           100.0%
    pgvector:            Nao
    Modelo:              text-embedding-004
    Dimensao:            768
```

#### Sincronizar todos os embeddings
```bash
python scripts/sync_embeddings.py
```

Este comando:
- Cria embeddings para módulos que não têm
- Atualiza embeddings de módulos que mudaram
- Ignora módulos que não mudaram

#### Forçar recriação de todos
```bash
python scripts/sync_embeddings.py --force
```

Use quando:
- Mudou o modelo de embedding
- Suspeita de embeddings corrompidos
- Alterou a lógica de `build_embedding_text()`

#### Testar busca
```bash
# Busca vetorial pura
python scripts/sync_embeddings.py --test "prescrição medicamentos"

# Busca híbrida (vetorial + keyword)
python scripts/sync_embeddings.py --test "tema 793" --hibrido
```

## Ambiente de Produção

### Railway (PostgreSQL)

O Railway pode ou não ter o pgvector disponível. O sistema detecta automaticamente:

- **Com pgvector**: Usa índice HNSW para busca vetorial nativa (mais rápido)
- **Sem pgvector**: Usa fallback com numpy (funciona, mas mais lento)

### Primeiro Deploy

Após o deploy, execute o script de sincronização para popular os embeddings:

```bash
# Via Railway CLI ou Console
python scripts/sync_embeddings.py
```

### Monitoramento

Os logs mostram quando embeddings são atualizados:

```
[EMBEDDING] Agendada atualizacao do embedding do modulo 42
[EMBEDDING] Atualizado embedding do modulo 42
```

## Troubleshooting

### Embeddings não estão sendo criados

1. Verifique se `GOOGLE_API_KEY` está configurada
2. Verifique os logs por erros de API
3. Execute `--stats` para ver cobertura

### Busca não encontra resultados esperados

1. Verifique se o módulo tem embedding: `--stats`
2. Teste a busca diretamente: `--test "sua query"`
3. O threshold padrão é 0.35 (35%) - resultados abaixo são filtrados

### Embedding desatualizado após edição

1. Verifique os logs por erros na thread de background
2. Execute sync manual: `python scripts/sync_embeddings.py`
3. Verifique se o hash mudou (o texto pode ser igual)

## Custos

### API do Google

O modelo `text-embedding-004` é cobrado por caracteres processados. Custos aproximados:
- Criação inicial de 55 módulos: ~$0.01
- Atualização de 1 módulo: desprezível

### Performance

| Operação | Tempo Aproximado |
|----------|------------------|
| Gerar embedding (1 módulo) | 200-500ms |
| Busca vetorial (55 módulos, numpy) | 50-100ms |
| Busca vetorial (pgvector, HNSW) | 5-20ms |

## Arquivos Relacionados

| Arquivo | Descrição |
|---------|-----------|
| `sistemas/gerador_pecas/models_embeddings.py` | Modelo SQLAlchemy da tabela |
| `sistemas/gerador_pecas/services_embeddings.py` | Geração e atualização de embeddings |
| `sistemas/gerador_pecas/services_busca_vetorial.py` | Busca vetorial e híbrida |
| `sistemas/gerador_pecas/services.py` | Integração com chatbot |
| `admin/router_prompts.py` | Hooks de atualização automática |
| `scripts/sync_embeddings.py` | Script CLI de manutenção |

## Modelo de Embedding

Atualmente usando: **Google text-embedding-004**

Características:
- 768 dimensões
- Suporta até 2048 tokens (~8000 caracteres)
- Otimizado para busca semântica (RETRIEVAL_DOCUMENT / RETRIEVAL_QUERY)

Para trocar o modelo, altere `EMBEDDING_MODEL` em `services_embeddings.py` e execute `--force` para regenerar todos.
