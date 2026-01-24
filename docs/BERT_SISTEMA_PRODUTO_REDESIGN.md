# REDESIGN DO SISTEMA BERT COMO PRODUTO

> Documento de Arquitetura e Design de Produto
> Data: 2026-01-24
> Autor: Engenheiro de IA Senior / Arquiteto de Sistemas ML

---

## SUMARIO EXECUTIVO

Este documento propoe um redesign completo do sistema BERT Training, transformando-o de um pipeline tecnico em um **produto de ML para usuarios nao tecnicos**. O foco principal e **esconder a complexidade sem sacrificar o poder**, permitindo que usuarios leigos treinem classificadores de texto com confianca, enquanto usuarios avancados mantem controle total quando necessario.

---

## 1. ANALISE DO ESTADO ATUAL

### 1.1 O que ja existe (Pontos Fortes)

| Componente | Avaliacao | Comentario |
|------------|-----------|------------|
| Arquitetura hibrida (cloud + worker local) | Excelente | Separa controle (cloud) de computacao (GPU local) |
| Reproducibilidade | Bom | Hash de dataset, seed, git commit, env fingerprint |
| API REST bem estruturada | Bom | Endpoints claros, Pydantic schemas |
| Validacao de datasets | Bom | Preview, deteccao de colunas, validacao de formato |
| Sistema de filas | Adequado | Job queue com status, heartbeat de workers |
| Modelo de dados | Solido | Bem normalizado, indices apropriados |

### 1.2 Gaps Criticos Identificados

| Problema | Impacto | Prioridade |
|----------|---------|------------|
| **UX assume conhecimento de ML** | Usuario nao sabe o que e epoch, learning rate, batch size | CRITICA |
| **Sem presets/wizards** | Usuario deve configurar todos os parametros | CRITICA |
| **Falta de feedback inteligente** | Metricas brutas sem interpretacao | ALTA |
| **Sem validacao proativa** | Problemas no dataset so aparecem na hora do erro | ALTA |
| **Logs tecnicos demais** | Usuario ve "CrossEntropyLoss: 0.4523" sem contexto | MEDIA |
| **Sem estimativa de tempo** | Usuario nao sabe quanto vai demorar | MEDIA |
| **Falta "modo rapido"** | Todo treino e completo, mesmo para testes | MEDIA |
| **Sem alertas de qualidade** | Overfitting/underfitting nao sao sinalizados | ALTA |
| **Sem comparacao de runs** | Dificil ver evolucao entre experimentos | BAIXA |
| **Worker management manual** | Admin precisa intervir para problemas | MEDIA |

### 1.3 Analise de Risco de Usuario

**Cenarios de erro provavel para usuario amador:**

1. **Dataset desbalanceado** - 95% classe A, 5% classe B
2. **Dataset muito pequeno** - menos de 100 amostras
3. **Overfitting** - accuracy de treino 99%, validacao 60%
4. **Batch size muito grande** - OOM na GPU
5. **Max length muito baixo** - textos cortados perdem contexto
6. **Learning rate muito alta** - modelo diverge
7. **Poucas epocas** - modelo sub-treinado

---

## 2. JORNADA DO USUARIO PROPOSTA

### 2.1 Personas

**Persona 1: Ana (Usuario Amador)**
- Procuradora, nao sabe programar
- Quer classificar documentos juridicos automaticamente
- Nao entende terminologia de ML
- Expectativa: "Treinar um modelo que funcione"

**Persona 2: Carlos (Usuario Avancado)**
- Desenvolvedor da equipe de TI
- Entende ML, quer controle fino
- Precisa reproduzir experimentos
- Expectativa: "Configurar hiperparametros especificos"

### 2.2 Fluxo Principal (Modo Simples)

```
                    JORNADA DO USUARIO (MODO SIMPLES)

    [1. WELCOME]                [2. UPLOAD]                [3. VALIDACAO]
    ┌─────────────┐            ┌─────────────┐            ┌─────────────┐
    │             │            │             │            │ "Analisando │
    │  "O que e   │───────────►│  Arraste    │───────────►│  seu Excel" │
    │   isso?"    │            │  seu Excel  │            │             │
    │             │            │             │            │ [Auto-fix]  │
    └─────────────┘            └─────────────┘            └─────────────┘
          │                          │                          │
          │                          │                          │
          ▼                          ▼                          ▼
    ┌─────────────┐            ┌─────────────┐            ┌─────────────┐
    │ Tooltip:    │            │ - Drag&Drop │            │ Alertas:    │
    │ "Ensine o   │            │ - Preview   │            │ - Poucos    │
    │  computador │            │   intelig.  │            │   dados?    │
    │  a classif. │            │ - Auto-     │            │ - Desbalan- │
    │  textos"    │            │   detecta   │            │   ceado?    │
    │             │            │   colunas   │            │ - Nulos?    │
    └─────────────┘            └─────────────┘            └─────────────┘
                                                                │
                                                                ▼
    [6. RESULTADO]             [5. TREINO]                [4. CONFIG]
    ┌─────────────┐            ┌─────────────┐            ┌─────────────┐
    │             │            │             │            │             │
    │ "Seu modelo │◄───────────│ "Treinando" │◄───────────│  PRESET:    │
    │  esta       │            │             │            │  [Rapido]   │
    │  pronto!"   │            │ Progresso   │            │  [Padrao]   │
    │             │            │ visual      │            │  [Preciso]  │
    │ [Testar]    │            │             │            │             │
    └─────────────┘            └─────────────┘            └─────────────┘
```

### 2.3 Primeira Experiencia (Onboarding)

**Tela de Boas-Vindas (primeira vez):**

```
┌────────────────────────────────────────────────────────────────────────┐
│                                                                        │
│     ┌───────┐                                                          │
│     │  🎓  │    BEM-VINDO AO BERT TRAINING                            │
│     └───────┘                                                          │
│                                                                        │
│     Aqui voce pode ensinar o computador a classificar                  │
│     documentos automaticamente.                                        │
│                                                                        │
│     ┌─────────────────────────────────────────────────────────┐        │
│     │                                                         │        │
│     │  1. Envie uma planilha com exemplos                     │        │
│     │     (textos + categorias que voce quer)                 │        │
│     │                                                         │        │
│     │  2. O sistema aprende com esses exemplos                │        │
│     │                                                         │        │
│     │  3. Depois, ele classifica novos textos sozinho         │        │
│     │                                                         │        │
│     └─────────────────────────────────────────────────────────┘        │
│                                                                        │
│     ┌────────────────────┐   ┌────────────────────┐                    │
│     │ ▶ Comecar agora    │   │ 📚 Ver tutorial    │                    │
│     └────────────────────┘   └────────────────────┘                    │
│                                                                        │
│     □ Nao mostrar isso novamente                                       │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. CAMADAS DE ABSTRACAO

### 3.1 Hierarquia de Complexidade

```
                    PIRAMIDE DE COMPLEXIDADE

                          ┌───────────┐
                          │ TRAVADO   │  ← Parametros criticos
                          │ (hidden)  │     que podem quebrar tudo
                          ├───────────┤
                          │           │
                          │ AVANCADO  │  ← Para quem sabe o que faz
                          │ (opt-in)  │
                          │           │
                          ├───────────┤
                          │           │
                          │           │
                          │  SIMPLES  │  ← Visivel por padrao
                          │ (default) │     Presets + linguagem simples
                          │           │
                          │           │
                          └───────────┘
```

### 3.2 Mapeamento de Parametros

| Parametro Tecnico | Camada | Como Apresentar | Valor Padrao |
|-------------------|--------|-----------------|--------------|
| epochs | SIMPLES | Preset (Rapido/Padrao/Preciso) | 10 |
| learning_rate | AVANCADO | "Velocidade de aprendizado" | 5e-5 |
| batch_size | AVANCADO | "Tamanho do lote" | Auto-calculado |
| max_length | AVANCADO | "Maximo de texto" | 512 |
| train_split | AVANCADO | "% para treino" | 0.8 |
| seed | AVANCADO | "Semente aleatoria" | 42 |
| warmup_steps | AVANCADO | Escondido atras de "mais opcoes" | 0 |
| weight_decay | TRAVADO | Nao mostrar | 0.01 |
| gradient_accumulation | TRAVADO | Nao mostrar (calcular auto) | Auto |
| early_stopping | SIMPLES | "Parar quando nao melhorar" (checkbox) | Sim, 3 |
| use_class_weights | AVANCADO | "Balancear classes" (checkbox) | Auto-detectar |
| truncation_side | TRAVADO | Nao mostrar | right |

### 3.3 Presets Inteligentes

```
┌────────────────────────────────────────────────────────────────────────┐
│  ESCOLHA O MODO DE TREINAMENTO                                         │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  ┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────┐
│  │                      │  │                      │  │                  │
│  │     ⚡ RAPIDO        │  │     ⚖️ EQUILIBRADO   │  │    🎯 PRECISO    │
│  │                      │  │    (Recomendado)     │  │                  │
│  │  Ideal para testar   │  │  Melhor custo-       │  │  Maximo de       │
│  │  se o dataset esta   │  │  beneficio para      │  │  qualidade,      │
│  │  no formato certo    │  │  maioria dos casos   │  │  mais demorado   │
│  │                      │  │                      │  │                  │
│  │  ~5-10 minutos       │  │  ~30-60 minutos      │  │  ~2-4 horas      │
│  │                      │  │                      │  │                  │
│  │  3 epocas            │  │  10 epocas           │  │  30 epocas       │
│  │  Sem early stopping  │  │  Early stopping: 3   │  │  Early stop: 5   │
│  │                      │  │                      │  │                  │
│  └──────────────────────┘  └──────────────────────┘  └──────────────────┘
│                                                                        │
│  ▼ Configurar manualmente (avancado)                                   │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

**Configuracao interna dos presets:**

```python
PRESETS = {
    "rapido": {
        "epochs": 3,
        "early_stopping_patience": None,  # Desativado
        "batch_size": 32,  # Maior = mais rapido
        "learning_rate": 2e-5,  # Mais conservador
    },
    "equilibrado": {  # PADRAO
        "epochs": 10,
        "early_stopping_patience": 3,
        "batch_size": 16,
        "learning_rate": 5e-5,
    },
    "preciso": {
        "epochs": 30,
        "early_stopping_patience": 5,
        "batch_size": 8,  # Menor = mais estavel
        "learning_rate": 3e-5,  # Mais conservador
        "warmup_steps": 100,  # Warmup ajuda
    }
}
```

---

## 4. DATASET E VALIDACAO

### 4.1 Validacoes Automaticas Propostas

| Validacao | Trigger | Mensagem Amigavel | Acao Sugerida |
|-----------|---------|-------------------|---------------|
| Poucas amostras (<100) | Upload | "Seu dataset tem poucas amostras. Recomendamos pelo menos 100 exemplos por categoria." | Mostrar quantas faltam |
| Muito desbalanceado (>10:1) | Upload | "Algumas categorias tem muito menos exemplos. Isso pode fazer o modelo ignorar categorias raras." | Oferecer "balancear automaticamente" |
| Textos muito curtos (<20 chars) | Upload | "Alguns textos sao muito curtos. Textos muito pequenos podem nao ter informacao suficiente." | Mostrar exemplos |
| Textos muito longos (>5000 chars) | Upload | "Alguns textos serao cortados. O modelo processa ate X caracteres." | Mostrar % afetado |
| Valores nulos | Upload | "X linhas tem campos vazios e serao ignoradas." | Mostrar quais |
| Classe unica | Upload (ERRO) | "Todas as amostras tem a mesma categoria. Voce precisa de pelo menos 2 categorias diferentes." | Bloquear upload |
| Labels suspeitas | Upload | "Detectamos categorias muito parecidas: 'Petição' e 'PETICAO'. Sao a mesma coisa?" | Oferecer merge |

### 4.2 Preview Visual do Dataset

```
┌────────────────────────────────────────────────────────────────────────┐
│  ANALISE DO SEU DATASET                                                │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  📊 RESUMO                                                             │
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │  Total: 1.250 amostras                                       │      │
│  │  Categorias: 5                                               │      │
│  │  Qualidade: ████████░░ 80% (Bom)                            │      │
│  └──────────────────────────────────────────────────────────────┘      │
│                                                                        │
│  📈 DISTRIBUICAO DE CATEGORIAS                                         │
│                                                                        │
│  Indenizacao      ████████████████████████████████░░░░░░ 45% (562)     │
│  Cobranca         ████████████████████░░░░░░░░░░░░░░░░░░ 25% (312)     │
│  Execucao Fiscal  ██████████████░░░░░░░░░░░░░░░░░░░░░░░░ 18% (225)     │
│  Mandado Segur.   ████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ 8%  (100)     │
│  Outros           ██░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ 4%  (51)      │
│                                                                        │
│  ⚠️ AVISOS                                                             │
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │  ! A categoria "Outros" tem poucos exemplos (51).            │      │
│  │    O modelo pode ter dificuldade em reconhece-la.            │      │
│  │    [Adicionar mais exemplos] [Remover categoria]             │      │
│  └──────────────────────────────────────────────────────────────┘      │
│                                                                        │
│  📋 AMOSTRA DOS DADOS                                                  │
│  ┌───────────────────────────────────────────────────┬──────────────┐  │
│  │ Texto                                              │ Categoria    │  │
│  ├───────────────────────────────────────────────────┼──────────────┤  │
│  │ "O autor requer indenizacao por danos morais..." │ Indenizacao  │  │
│  │ "Trata-se de acao de cobranca referente a..."    │ Cobranca     │  │
│  │ "A Fazenda Publica move execucao fiscal..."      │ Exec. Fiscal │  │
│  └───────────────────────────────────────────────────┴──────────────┘  │
│                                                                        │
│  ┌────────────────────┐   ┌────────────────────┐                       │
│  │ ← Voltar           │   │ Continuar →        │                       │
│  └────────────────────┘   └────────────────────┘                       │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

### 4.3 Sugestao de Colunas Inteligente

```python
def suggest_columns(df):
    """
    Detecta automaticamente quais colunas sao texto e label.
    Regras:
    - Coluna de texto: strings longas (media > 50 chars), alta variancia
    - Coluna de label: poucos valores unicos (<50), strings curtas ou inteiros
    """
    text_score = {}
    label_score = {}

    for col in df.columns:
        sample = df[col].dropna().head(100)

        # Score para texto
        if sample.dtype == object:
            avg_len = sample.str.len().mean()
            text_score[col] = avg_len

        # Score para label
        unique_ratio = df[col].nunique() / len(df)
        if unique_ratio < 0.1:  # <10% unicos
            label_score[col] = 1 - unique_ratio

    return {
        'text_column': max(text_score, key=text_score.get),
        'label_column': max(label_score, key=label_score.get),
        'confidence': 'alta' if len(text_score) == 1 else 'media'
    }
```

---

## 5. EXPERIMENTOS, RUNS E REPRODUTIBILIDADE

### 5.1 Apresentacao de Runs para Leigos

**Atual (tecnico):**
```
Run #42 - status: completed
learning_rate: 5e-5, epochs: 10, seed: 42
final_accuracy: 0.8734, final_macro_f1: 0.8521
```

**Proposto (amigavel):**
```
┌────────────────────────────────────────────────────────────────────────┐
│                                                                        │
│  ✅ TREINAMENTO CONCLUIDO                                              │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │                                                              │      │
│  │     SEU MODELO ACERTA                                        │      │
│  │                                                              │      │
│  │          █████████░    87%                                   │      │
│  │                        dos casos                             │      │
│  │                                                              │      │
│  │     Isso e um resultado BOM para este tipo de tarefa.        │      │
│  │                                                              │      │
│  └──────────────────────────────────────────────────────────────┘      │
│                                                                        │
│  📊 DETALHAMENTO POR CATEGORIA                                         │
│                                                                        │
│  Indenizacao      ████████████████████░░░░ 95% de acerto              │
│  Cobranca         ████████████████░░░░░░░░ 85% de acerto              │
│  Execucao Fiscal  ████████████████░░░░░░░░ 82% de acerto              │
│  Mandado Segur.   ████████████░░░░░░░░░░░░ 72% de acerto   ⚠️         │
│  Outros           ████████░░░░░░░░░░░░░░░░ 61% de acerto   ⚠️         │
│                                                                        │
│  💡 DICA: "Mandado Segur." e "Outros" tem menos acertos porque        │
│     tinham poucos exemplos no dataset.                                 │
│                                                                        │
│  ▼ Ver metricas tecnicas                                               │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

### 5.2 Conceito de "Reproduzir" sem Jargao

**Tela atual:** `POST /runs/{id}/reproduce`

**Proposta:**

```
┌────────────────────────────────────────────────────────────────────────┐
│                                                                        │
│  🔄 TREINAR NOVAMENTE                                                  │
│                                                                        │
│  Voce quer treinar outro modelo igual a este?                          │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │  O novo treino vai usar:                                     │      │
│  │  ✓ O mesmo dataset (planilha_documentos.xlsx)               │      │
│  │  ✓ As mesmas configuracoes                                   │      │
│  │                                                              │      │
│  │  💡 Por que fazer isso?                                      │      │
│  │  - Para verificar se o resultado e consistente               │      │
│  │  - Apos adicionar mais dados ao dataset                      │      │
│  │  - Para ter um modelo de backup                              │      │
│  └──────────────────────────────────────────────────────────────┘      │
│                                                                        │
│  ┌────────────────────┐   ┌────────────────────┐                       │
│  │ Cancelar           │   │ Treinar novamente  │                       │
│  └────────────────────┘   └────────────────────┘                       │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

### 5.3 Informacoes Tecnicas (Escondidas mas Registradas)

**Registro automatico (sem exibir):**

```json
{
    "reproducibility": {
        "dataset_sha256": "abc123...",
        "code_git_commit": "def456...",
        "environment": {
            "python_version": "3.10.12",
            "torch_version": "2.1.0",
            "transformers_version": "4.35.0",
            "cuda_version": "12.1"
        },
        "random_seeds": {
            "python": 42,
            "numpy": 42,
            "torch": 42
        }
    }
}
```

**Acesso apenas via "Detalhes tecnicos" colapsado ou API.**

---

## 6. WORKER, JOBS E CONFIABILIDADE

### 6.1 Prevencao de Jobs Travados

```python
# Proposta: Sistema de Watchdog
class JobWatchdog:
    """
    Monitora jobs e detecta problemas automaticamente.
    """

    RULES = {
        'no_progress': {
            'condition': lambda job: (
                job.status == 'training' and
                job.last_progress_update < now() - timedelta(minutes=15)
            ),
            'action': 'warn_then_restart',
            'message': 'Job sem progresso por 15 minutos'
        },
        'stuck_epoch': {
            'condition': lambda job: (
                job.current_epoch == job.last_known_epoch and
                job.last_epoch_update < now() - timedelta(minutes=30)
            ),
            'action': 'restart_from_checkpoint',
            'message': 'Epoch travada por 30 minutos'
        },
        'worker_dead': {
            'condition': lambda job: (
                job.worker.last_heartbeat < now() - timedelta(minutes=5) and
                job.status in ['training', 'claimed']
            ),
            'action': 'reassign_job',
            'message': 'Worker parou de responder'
        }
    }
```

### 6.2 Comunicacao de Falhas ao Usuario

**Atual:** `error_message: "RuntimeError: CUDA out of memory..."`

**Proposto:**

```
┌────────────────────────────────────────────────────────────────────────┐
│                                                                        │
│  ❌ TREINAMENTO FALHOU                                                 │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │                                                              │      │
│  │  O que aconteceu:                                            │      │
│  │  O computador que estava treinando ficou sem memoria.        │      │
│  │                                                              │      │
│  │  O que fazer:                                                │      │
│  │  ✓ Tente novamente com configuracoes mais leves              │      │
│  │                                                              │      │
│  │  ┌────────────────────────────────────────────────────┐      │      │
│  │  │ ▶ Tentar novamente (config. automatica)            │      │      │
│  │  └────────────────────────────────────────────────────┘      │      │
│  │                                                              │      │
│  │  O sistema vai usar:                                         │      │
│  │  - Batch size menor (8 em vez de 16)                        │      │
│  │  - Textos mais curtos (256 em vez de 512)                   │      │
│  │                                                              │      │
│  └──────────────────────────────────────────────────────────────┘      │
│                                                                        │
│  ▼ Ver erro tecnico (para suporte)                                     │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

### 6.3 Progresso Compreensivel

**Atual:**
```
Epoch 3/10 - Batch 45/128 - Loss: 0.3421
```

**Proposto:**

```
┌────────────────────────────────────────────────────────────────────────┐
│                                                                        │
│  ⏳ TREINANDO SEU MODELO                                               │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │                                                              │      │
│  │  Progresso geral                                             │      │
│  │  ████████████████████░░░░░░░░░░░░░░░░░░░░░░░░░░ 35%         │      │
│  │                                                              │      │
│  │  Rodada 3 de 10                                              │      │
│  │  ████████████████████████████████████░░░░░░░░░░ 78%         │      │
│  │                                                              │      │
│  │  Tempo estimado: ~25 minutos restantes                       │      │
│  │                                                              │      │
│  └──────────────────────────────────────────────────────────────┘      │
│                                                                        │
│  📈 COMO ESTA INDO (atualizacao em tempo real)                         │
│                                                                        │
│  Acerto ate agora: 72% → 78% → 81%  ▲ Melhorando                       │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │                                                              │      │
│  │     100% ┤                                              *    │      │
│  │      80% ┤                              *   *   *   *        │      │
│  │      60% ┤              *   *   *   *                        │      │
│  │      40% ┤  *   *   *                                        │      │
│  │      20% ┤                                                   │      │
│  │          └────────────────────────────────────────────────   │      │
│  │            R1   R2   R3   R4   R5   R6   R7   R8   R9  R10   │      │
│  │                                                              │      │
│  └──────────────────────────────────────────────────────────────┘      │
│                                                                        │
│  💡 O modelo esta aprendendo bem. A cada rodada, ele erra menos.       │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

### 6.4 Separacao Cloud vs Local (Explicada)

```
┌────────────────────────────────────────────────────────────────────────┐
│                                                                        │
│  ℹ️ COMO FUNCIONA                                                      │
│                                                                        │
│  ┌─────────────────────┐          ┌─────────────────────┐              │
│  │                     │          │                     │              │
│  │   ☁️ NUVEM          │◄────────►│   💻 SEU PC         │              │
│  │   (Este site)       │          │   (Com GPU)         │              │
│  │                     │          │                     │              │
│  │   - Guardar dados   │          │   - Treinar modelo  │              │
│  │   - Mostrar result. │          │   - Usar GPU        │              │
│  │   - Fila de tarefas │          │   - Guardar modelo  │              │
│  │                     │          │     treinado        │              │
│  │                     │          │                     │              │
│  └─────────────────────┘          └─────────────────────┘              │
│                                                                        │
│  ✓ Seus dados originais ficam seguros na nuvem                         │
│  ✓ O treino pesado acontece no seu computador                          │
│  ✓ O modelo treinado fica no seu PC (nao enviamos para nuvem)          │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 7. METRICAS E AVALIACAO

### 7.1 Metricas "Traduzidas" para Leigos

| Metrica Tecnica | Traducao Amigavel | Quando Mostrar |
|-----------------|-------------------|----------------|
| Accuracy | "Acertos" | SEMPRE |
| Macro F1 | "Equilibrio entre categorias" | Quando desbalan. |
| Weighted F1 | Ocultar | NUNCA para leigos |
| Precision | "Quando o modelo diz X, esta certo?" | AVANCADO |
| Recall | "O modelo encontra todos os X?" | AVANCADO |
| Confusion Matrix | "Tabela de acertos e erros" | AVANCADO |
| Loss | "Erro durante treino (quanto menor, melhor)" | GRAFICO apenas |

### 7.2 Alertas Automaticos de Qualidade

```python
QUALITY_RULES = {
    'excellent': {
        'condition': lambda m: m['accuracy'] > 0.95,
        'message': "Excelente! Seu modelo esta muito preciso.",
        'color': 'green'
    },
    'good': {
        'condition': lambda m: 0.85 <= m['accuracy'] <= 0.95,
        'message': "Bom! Seu modelo tem uma precisao adequada.",
        'color': 'green'
    },
    'acceptable': {
        'condition': lambda m: 0.70 <= m['accuracy'] < 0.85,
        'message': "Aceitavel, mas pode melhorar. Considere adicionar mais exemplos.",
        'color': 'yellow'
    },
    'poor': {
        'condition': lambda m: m['accuracy'] < 0.70,
        'message': "O modelo precisa de melhorias. Verifique se os dados estao corretos.",
        'color': 'red'
    },
    'overfitting': {
        'condition': lambda m: m['train_accuracy'] - m['val_accuracy'] > 0.15,
        'message': "⚠️ O modelo decorou os exemplos de treino. Adicione mais dados variados.",
        'color': 'orange'
    },
    'underfitting': {
        'condition': lambda m: m['train_accuracy'] < 0.70 and m['val_accuracy'] < 0.70,
        'message': "O modelo nao conseguiu aprender. Verifique a qualidade dos dados.",
        'color': 'red'
    },
    'class_imbalance_issue': {
        'condition': lambda m: m['macro_f1'] < m['accuracy'] - 0.10,
        'message': "Algumas categorias estao sendo ignoradas. Adicione mais exemplos das categorias menores.",
        'color': 'orange'
    }
}
```

### 7.3 Visualizacoes Simples

**Grafico de Evolucao (Simplificado):**

```
┌────────────────────────────────────────────────────────────────────────┐
│                                                                        │
│  COMO O MODELO APRENDEU                                                │
│                                                                        │
│     100% ┤                                        ✓ Validacao          │
│          │                              ●   ●   ●─────────────         │
│      80% ┤                  ●   ●   ●                                  │
│          │      ●   ●   ●                                              │
│      60% ┤  ●                                                          │
│          │                                                             │
│      40% ┤                                                             │
│          └────────────────────────────────────────────────────         │
│            R1  R2  R3  R4  R5  R6  R7  R8  R9  R10                     │
│                                                                        │
│  💡 O modelo parou de melhorar na rodada 7.                            │
│     Isso e normal - significa que ele aprendeu o que podia.            │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 8. GOVERNANCA, SEGURANCA E LIMITES

### 8.1 Permissoes por Papel

| Acao | Usuario Normal | Admin |
|------|----------------|-------|
| Upload dataset | ✓ (proprio) | ✓ (todos) |
| Ver datasets | ✓ (proprios) | ✓ (todos) |
| Criar run | ✓ (proprio dataset) | ✓ (qualquer) |
| Ver runs | ✓ (proprios) | ✓ (todos) |
| Registrar worker | ✗ | ✓ |
| Ver workers | ✗ | ✓ |
| Cancelar job | ✓ (proprio) | ✓ (qualquer) |
| Deletar dataset | ✓ (proprio, sem runs) | ✓ (qualquer) |

### 8.2 Limites Operacionais

```python
LIMITS = {
    'dataset': {
        'max_file_size_mb': 100,
        'max_rows': 1_000_000,
        'max_columns': 50,
        'max_text_length': 50_000,  # caracteres
    },
    'run': {
        'max_epochs': 100,
        'max_batch_size': 128,
        'max_length': 1024,
        'max_concurrent_runs_per_user': 3,
        'max_total_concurrent_runs': 10,
    },
    'job': {
        'timeout_hours': 24,
        'max_retries': 3,
    }
}
```

### 8.3 Versionamento e Historico

```sql
-- Proposta: Tabela de auditoria simples
CREATE TABLE bert_audit_log (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT NOW(),
    user_id INTEGER REFERENCES users(id),
    action VARCHAR(50),  -- 'create_run', 'upload_dataset', etc
    entity_type VARCHAR(50),  -- 'run', 'dataset', 'job'
    entity_id INTEGER,
    details JSONB,
    ip_address INET
);

-- Indices
CREATE INDEX ix_audit_user ON bert_audit_log(user_id);
CREATE INDEX ix_audit_timestamp ON bert_audit_log(timestamp);
CREATE INDEX ix_audit_entity ON bert_audit_log(entity_type, entity_id);
```

### 8.4 Trilha de Auditoria (Oculta para Usuario)

**Admin ve:**
```
[2024-01-24 10:15:32] usuario@pge.ms.gov.br criou run "Classificador v2"
[2024-01-24 10:15:35] Job #123 criado para run #45
[2024-01-24 10:16:01] Worker "GPU-Local" claimou job #123
[2024-01-24 10:45:22] Job #123 completou (accuracy: 0.87)
[2024-01-24 10:45:23] Run #45 marcado como completed
```

**Usuario ve:**
```
Criado em: 24/01/2024 as 10:15
Concluido em: 24/01/2024 as 10:45
Duracao: ~30 minutos
```

---

## 9. ARQUITETURA FINAL RECOMENDADA

### 9.1 Diagrama de Componentes

```
┌────────────────────────────────────────────────────────────────────────────────┐
│                              ARQUITETURA BERT TRAINING v2                       │
├────────────────────────────────────────────────────────────────────────────────┤
│                                                                                │
│   ┌─────────────────────────────────────────────────────────────────────────┐  │
│   │                              FRONTEND                                    │  │
│   │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │  │
│   │  │  Wizard     │  │  Dashboard  │  │  Monitor    │  │  Resultados │    │  │
│   │  │  Upload     │  │  Runs       │  │  Progresso  │  │  Metricas   │    │  │
│   │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘    │  │
│   │                                                                         │  │
│   │                    ┌───────────────────────┐                            │  │
│   │                    │  UX Layer             │                            │  │
│   │                    │  - Presets            │                            │  │
│   │                    │  - Traducao metricas  │                            │  │
│   │                    │  - Alertas intelig.   │                            │  │
│   │                    └───────────────────────┘                            │  │
│   └─────────────────────────────────────────────────────────────────────────┘  │
│                                       │                                        │
│                                       ▼                                        │
│   ┌─────────────────────────────────────────────────────────────────────────┐  │
│   │                              BACKEND (Cloud)                             │  │
│   │                                                                         │  │
│   │   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐             │  │
│   │   │   Router     │    │   Services   │    │   Validators │             │  │
│   │   │   (FastAPI)  │───►│   (Logica)   │───►│   (Regras)   │             │  │
│   │   └──────────────┘    └──────────────┘    └──────────────┘             │  │
│   │          │                   │                   │                      │  │
│   │          ▼                   ▼                   ▼                      │  │
│   │   ┌──────────────────────────────────────────────────────────────┐     │  │
│   │   │                     PostgreSQL                                │     │  │
│   │   │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐│     │  │
│   │   │  │ Datasets│ │  Runs   │ │  Jobs   │ │ Metrics │ │ Workers ││     │  │
│   │   │  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘│     │  │
│   │   │  ┌─────────┐ ┌─────────┐ ┌─────────┐                        │     │  │
│   │   │  │  Logs   │ │ Presets │ │  Audit  │  (NOVO)                │     │  │
│   │   │  └─────────┘ └─────────┘ └─────────┘                        │     │  │
│   │   └──────────────────────────────────────────────────────────────┘     │  │
│   │                                                                         │  │
│   │   ┌──────────────────────┐    ┌──────────────────────┐                 │  │
│   │   │  Job Scheduler       │    │  Watchdog (NOVO)     │                 │  │
│   │   │  - Fila FIFO         │    │  - Monitora jobs     │                 │  │
│   │   │  - Prioridade        │    │  - Detecta travados  │                 │  │
│   │   │  - Retry logic       │    │  - Alertas           │                 │  │
│   │   └──────────────────────┘    └──────────────────────┘                 │  │
│   └─────────────────────────────────────────────────────────────────────────┘  │
│                                       │                                        │
│                                       │ API (HTTPS)                            │
│                                       │ Heartbeat, Progress, Metrics           │
│                                       ▼                                        │
│   ┌─────────────────────────────────────────────────────────────────────────┐  │
│   │                              WORKER (Local GPU)                          │  │
│   │                                                                         │  │
│   │   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐             │  │
│   │   │   Fetcher    │    │   Trainer    │    │   Reporter   │             │  │
│   │   │   - Download │───►│   - PyTorch  │───►│   - Metrics  │             │  │
│   │   │   - Validate │    │   - CUDA     │    │   - Logs     │             │  │
│   │   └──────────────┘    └──────────────┘    └──────────────┘             │  │
│   │                              │                                          │  │
│   │                              ▼                                          │  │
│   │                       ┌──────────────┐                                  │  │
│   │                       │  GPU Memory  │                                  │  │
│   │                       │  Manager     │  (NOVO)                          │  │
│   │                       │  - Auto batch│                                  │  │
│   │                       │  - OOM guard │                                  │  │
│   │                       └──────────────┘                                  │  │
│   │                              │                                          │  │
│   │                              ▼                                          │  │
│   │                       ┌──────────────┐                                  │  │
│   │                       │ Local Storage│                                  │  │
│   │                       │ - Models     │                                  │  │
│   │                       │ - Checkpoints│                                  │  │
│   │                       └──────────────┘                                  │  │
│   └─────────────────────────────────────────────────────────────────────────┘  │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────┘
```

### 9.2 Componentes Novos Propostos

| Componente | Responsabilidade | Prioridade |
|------------|------------------|------------|
| **UX Layer** | Presets, traducao, alertas inteligentes | ALTA |
| **Presets Table** | Armazenar configuracoes pre-definidas | ALTA |
| **Audit Table** | Trilha de auditoria automatica | MEDIA |
| **Watchdog Service** | Monitorar jobs travados | MEDIA |
| **GPU Memory Manager** | Auto-ajustar batch size | MEDIA |
| **Onboarding Component** | Tutorial primeira vez | BAIXA |
| **Comparison View** | Comparar multiplos runs | BAIXA |

### 9.3 Pontos de Extensao Futuros

1. **Multi-GPU**: Suporte a treinamento distribuido
2. **AutoML**: Otimizacao automatica de hiperparametros
3. **Inferencia API**: Endpoint para usar modelo treinado
4. **Export ONNX**: Exportar modelo para deploy
5. **Active Learning**: Sugerir novos exemplos para rotular
6. **Model Hub**: Compartilhar modelos entre usuarios

---

## 10. CHECKLIST DE REQUISITOS OBRIGATORIOS

### 10.1 UX (Prioridade Maxima)

- [ ] Wizard de upload com deteccao automatica de colunas
- [ ] 3 presets de treinamento (Rapido, Equilibrado, Preciso)
- [ ] Esconder hiperparametros tecnicos por padrao
- [ ] Mensagens de erro em linguagem simples
- [ ] Barra de progresso com estimativa de tempo
- [ ] Alertas automaticos de qualidade
- [ ] Metricas traduzidas (accuracy = "acertos")
- [ ] Tela de onboarding na primeira vez

### 10.2 Backend (Prioridade Alta)

- [ ] Validacao proativa de datasets
- [ ] Tabela de presets configuravel
- [ ] Auto-calculo de batch size baseado em VRAM
- [ ] Watchdog para jobs travados
- [ ] Sistema de alertas por email (opcional)
- [ ] Rate limiting por usuario

### 10.3 Worker (Prioridade Media)

- [ ] OOM guard com auto-retry menor batch
- [ ] Checkpoint saving a cada epoca
- [ ] Metricas de GPU em tempo real
- [ ] Log rotation automatico

### 10.4 Governanca (Prioridade Media)

- [ ] Tabela de auditoria
- [ ] Limites por usuario
- [ ] Politica de retencao de dados
- [ ] Backup automatico de datasets

---

## 11. DECISOES DE ENGENHARIA (TRADE-OFFS)

### 11.1 Presets vs Controle Total

**Decisao:** Presets como padrao, avancado opt-in.

**Justificativa:** 80% dos usuarios nao precisam ajustar hiperparametros. Para eles, escolher entre 3 opcoes e suficiente. Os 20% que precisam de controle podem expandir a secao avancada.

**Trade-off:** Usuarios avancados precisam de um clique extra.

### 11.2 Complexidade na UI vs Backend

**Decisao:** Backend inteligente, UI simples.

**Justificativa:** E mais facil manter logica complexa no backend (Python) do que no frontend (JavaScript). Validacoes, calculos automaticos e alertas devem acontecer no servidor.

**Trade-off:** Mais requisicoes ao servidor.

### 11.3 Metricas Detalhadas vs Simplicidade

**Decisao:** Mostrar apenas accuracy por padrao, resto colapsado.

**Justificativa:** Precision, recall, F1 confundem usuarios leigos. Accuracy e intuitivo ("X de cada 100 acertos").

**Trade-off:** Usuarios avancados precisam expandir para ver F1.

### 11.4 Auto-Batch vs Manual

**Decisao:** Calcular batch size automaticamente baseado em VRAM disponivel.

**Justificativa:** OOM e o erro mais comum. Calcular automaticamente previne frustracao.

**Implementacao proposta:**
```python
def calculate_optimal_batch_size(vram_gb: float, max_length: int, model_size: str) -> int:
    """
    Calcula batch size seguro baseado em VRAM.
    Deixa 20% de margem para seguranca.
    """
    VRAM_PER_SAMPLE = {
        'base': {'512': 0.5, '256': 0.3, '128': 0.15},  # GB
        'large': {'512': 1.2, '256': 0.7, '128': 0.35},
    }

    vram_per_sample = VRAM_PER_SAMPLE[model_size][str(max_length)]
    safe_vram = vram_gb * 0.8
    optimal = int(safe_vram / vram_per_sample)

    # Arredonda para potencia de 2 mais proxima
    return min(max(2, 2 ** int(optimal).bit_length() - 1), 64)
```

**Trade-off:** Pode ser conservador demais em algumas GPUs.

### 11.5 Monorepo vs Separar Worker

**Decisao:** Manter worker no mesmo repositorio.

**Justificativa:** Facilita versionamento sincronizado. Worker usa mesmos modulos de ML.

**Trade-off:** Worker carrega dependencias desnecessarias (FastAPI, etc).

---

## 12. PROXIMOS PASSOS SUGERIDOS

### Fase 1: UX Minima Viavel (1-2 semanas)
1. Implementar 3 presets
2. Esconder hiperparametros avancados
3. Melhorar mensagens de erro
4. Adicionar barra de progresso com estimativa

### Fase 2: Validacao Inteligente (1 semana)
1. Alertas de desbalanceamento
2. Alertas de dataset pequeno
3. Preview visual melhorado

### Fase 3: Robustez (1-2 semanas)
1. Watchdog de jobs
2. Auto-batch baseado em VRAM
3. Retry automatico com config menor

### Fase 4: Polish (1 semana)
1. Onboarding tutorial
2. Traducao de metricas
3. Comparacao de runs

---

## CONCLUSAO

O sistema atual tem uma **base tecnica solida**, mas peca na **experiencia do usuario amador**. O redesign proposto foca em:

1. **Esconder complexidade** sem remove-la
2. **Presets inteligentes** para 80% dos casos
3. **Feedback proativo** antes dos erros acontecerem
4. **Linguagem simples** sem perder precisao tecnica

O resultado sera um sistema que **usuarios leigos conseguem usar com confianca**, enquanto **usuarios avancados mantem controle total** quando necessario.

---

*Documento gerado em 2026-01-24 como parte do redesign do sistema BERT Training para o Portal PGE-MS.*
