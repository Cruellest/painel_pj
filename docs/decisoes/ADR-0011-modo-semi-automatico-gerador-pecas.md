# ADR-0011: Modo Semi-Automático para Gerador de Peças Jurídicas

**Data**: 2026-01-30
**Status**: Aceito
**Autores**: LAB/PGE-MS

## Contexto

O Gerador de Peças Jurídicas utiliza uma arquitetura de três agentes:

1. **Agente 1** (Coletor): Coleta documentos do processo via TJ-MS
2. **Agente 2** (Detector): Analisa documentos e detecta módulos/argumentos aplicáveis
3. **Agente 3** (Gerador): Gera a peça jurídica final com base nos módulos detectados

**Problema identificado**:
- O modo automático gera peças sem intervenção do usuário
- Procuradores experientes querem revisar/ajustar os argumentos ANTES da geração
- Argumentos relevantes podem não ser detectados automaticamente
- Não há forma de adicionar argumentos do banco vetorial manualmente

**Requisitos do usuário**:
- Visualizar argumentos detectados pelo Agente 2 antes da geração
- Reorganizar argumentos entre seções (Preliminar, Mérito, etc.)
- Buscar argumentos adicionais por palavra-chave e semanticamente
- Marcar argumentos adicionados manualmente como validados
- Manter Agente 3 inalterado - apenas o prompt de entrada muda

## Decisão

Implementar modo semi-automático opcional que insere uma etapa de curadoria entre o Agente 2 e o Agente 3.

### 1. Arquitetura do Fluxo

```
┌─────────────┐    ┌─────────────┐    ┌─────────────────┐    ┌─────────────┐
│  Agente 1   │ → │  Agente 2   │ → │   CURADORIA     │ → │  Agente 3   │
│  (Coletor)  │    │ (Detector)  │    │  (Nova Etapa)   │    │ (Gerador)   │
└─────────────┘    └─────────────┘    └─────────────────┘    └─────────────┘
                                              ↓
                                    ┌─────────────────────┐
                                    │ Interface Visual    │
                                    │ - Drag & Drop       │
                                    │ - Busca Semântica   │
                                    │ - Organização       │
                                    └─────────────────────┘
```

### 2. Categorias de Seções

Enum `CategoriaSecao` define as seções válidas:

| Seção | Descrição |
|-------|-----------|
| `PRELIMINAR` | Argumentos preliminares/processuais |
| `MERITO` | Argumentos de mérito principal |
| `EVENTUALIDADE` | Argumentos subsidiários |
| `HONORARIOS` | Questões de honorários |
| `PEDIDOS` | Pedidos ao juízo |

### 3. Estruturas de Dados

**ModuloCurado**:
```python
@dataclass
class ModuloCurado:
    id: str                    # UUID único
    titulo: str                # Título do argumento
    conteudo: str              # Texto completo
    secao: CategoriaSecao      # Seção atual
    ordem: int                 # Ordem na seção
    fonte: str                 # "automatico" ou "busca"
    validado: bool             # True se adicionado manualmente
    score_similaridade: float  # Score da busca (0-1)
```

**ResultadoCuradoria**:
```python
@dataclass
class ResultadoCuradoria:
    processo: str
    tipo_peca: str
    modulos: List[ModuloCurado]
    prompt_base: str           # Prompt do Agente 2
    dados_processo: Dict       # Dados coletados
```

### 4. Endpoints da API

| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/curadoria/preview` | POST | Executa Agentes 1+2, retorna módulos para curadoria |
| `/curadoria/buscar` | POST | Busca argumentos adicionais (keyword + semântico) |
| `/curadoria/gerar-stream` | POST | Gera peça com módulos curados (SSE) |

**Parâmetros de `/curadoria/preview`**:
- `numero_processo`: Número do processo
- `tipo_peca`: Tipo de peça jurídica
- `subcategorias_ids`: IDs das subcategorias ativas

**Parâmetros de `/curadoria/buscar`**:
- `query`: Texto de busca
- `tipo_peca`: Tipo de peça (filtro)
- `limite`: Máximo de resultados (padrão: 10)

**Parâmetros de `/curadoria/gerar-stream`**:
- `resultado_curadoria`: Objeto ResultadoCuradoria completo
- `modelo_ia`: Modelo a usar (ex: "gemini-2.0-flash")

### 5. Marcação de Argumentos Validados

Argumentos adicionados manualmente são marcados no prompt final:

```
## ARGUMENTO: [VALIDADO] Título do Argumento

Conteúdo do argumento...
```

O prefixo `[VALIDADO]` indica ao Agente 3 que este argumento foi explicitamente selecionado pelo procurador e deve ser incluído na peça.

### 6. Interface Frontend

**Componentes**:
- Modal de curadoria com duas colunas
- Coluna esquerda: Seções com argumentos (drag & drop)
- Coluna direita: Painel de busca
- Cada argumento: título, preview, botões de ação

**Drag & Drop**:
- Argumentos podem ser movidos entre seções
- Ordem dentro da seção é controlável
- Visual feedback durante arraste

**Busca**:
- Campo de texto para busca
- Resultados com score de similaridade
- Botão "Adicionar" em cada resultado
- Argumentos adicionados vão para seção padrão (MERITO)

### 7. Integração com Busca Existente

Reutiliza serviços existentes:
- `services_busca_argumentos.py`: Busca por keyword
- `services_busca_vetorial.py`: Busca semântica com pgvector
- `services_embeddings.py`: Geração de embeddings

A busca combina:
1. Correspondência exata de palavras-chave
2. Similaridade vetorial (cosine similarity)
3. Filtro por tipo de peça

## Consequências

### Positivas

- Procuradores têm controle total sobre argumentos
- Argumentos relevantes não detectados podem ser adicionados
- Peças geradas são mais precisas e personalizadas
- Agente 3 permanece inalterado (baixo risco)
- Modo é opcional - não afeta fluxo automático

### Negativas

- Adiciona etapa no fluxo de geração
- Requer mais interação do usuário
- Interface de drag & drop pode ser complexa em mobile

### Riscos

- **Usuário pode adicionar argumentos inconsistentes**
  - Mitigação: Agente 3 ainda valida coerência
- **Performance em lotes grandes de argumentos**
  - Mitigação: Paginação na busca, limite de resultados

## Alternativas Consideradas

1. **Edição pós-geração**: Descartado - não resolve problema de argumentos faltantes
2. **Sugestões automáticas de argumentos**: Descartado - ainda não dá controle ao usuário
3. **Prompt de confirmação simples**: Descartado - não permite reorganização

### 8. Categorias Dinâmicas (Atualização 2026-02)

**Problema anterior**: O frontend tinha um mapeamento hardcoded de categorias (`categoriasMap`), fazendo com que módulos com categorias customizadas (ex: "Introdução", "Conclusão") caíssem em "Outros" incorretamente.

**Solução implementada**:
1. Frontend carrega categorias dinamicamente da API (`/admin/api/prompts-modulos/categorias`)
2. Módulos usam a categoria diretamente do banco de dados
3. Apenas módulos com `categoria = NULL` ou vazia vão para "Outros"

**Como funciona**:
```javascript
// Antes (hardcoded - problemático)
const categoriasMap = { 'preliminar': 'Preliminar', ... };
const categoria = categoriasMap[modulo.categoria.toLowerCase()] || 'Outros';

// Depois (dinâmico - correto)
const categoria = (modulo.categoria && modulo.categoria.trim()) ? modulo.categoria : 'Outros';
```

**Benefícios**:
- Novas categorias criadas no admin são automaticamente reconhecidas
- Não requer mudança de código para adicionar categorias
- "Outros" só aparece quando realmente não há categoria definida

**Arquivos modificados**:
- `sistemas/gerador_pecas/templates/curadoria.js` - Carrega categorias da API
- `tests/test_curadoria_semi_automatico.py` - Novos testes de regressão

## Implementação

### Arquivos criados:
1. `sistemas/gerador_pecas/services_curadoria.py` - Serviço de curadoria
2. `sistemas/gerador_pecas/templates/curadoria.js` - Módulo frontend
3. `tests/test_curadoria_semi_automatico.py` - 21 testes automatizados

### Arquivos modificados:
1. `sistemas/gerador_pecas/router.py` - 3 novos endpoints
2. `sistemas/gerador_pecas/templates/index.html` - Botão semi-automático
3. `frontend/src/sistemas/gerador_pecas/app.ts` - Método iniciarModoSemiAutomatico

### Testes implementados:
- Criação de ModuloCurado com valores padrão
- Criação de ResultadoCuradoria
- Aplicação de alterações de curadoria
- Marcação [VALIDADO] em módulos manuais
- Ordenação correta das seções no prompt
- Busca de argumentos adicionais
- Formatação do prompt de saída
- 21 testes no total, todos passando

### 9. Rastreamento de Módulos Manuais (Correção 2026-02-02)

**Problema identificado**: Os módulos adicionados manualmente pelo usuário na interface de curadoria não estavam sendo distinguidos dos módulos detectados automaticamente (determinísticos ou LLM) ao serem enviados ao Agente 3 e salvos no histórico.

**Causa**: O frontend rastreava módulos manuais localmente (via `origem_ativacao: 'manual'`), mas ao enviar a requisição para `/curadoria/gerar-stream`, apenas os IDs eram enviados. O backend carregava os módulos do banco e perdia a informação de origem.

**Solução implementada**:

1. **Frontend** (`curadoria.js`):
   - Adicionado `this.modulosManuais = new Set()` para rastrear IDs de módulos adicionados manualmente
   - `adicionarArgumento()` agora adiciona o ID ao set de manuais
   - `gerarComCuradoria()` envia `modulos_manuais_ids` na requisição

2. **Backend** (`router.py`):
   - `CurationGenerateRequest` agora aceita `modulos_manuais_ids: Optional[List[int]]`
   - O endpoint `/curadoria/gerar-stream` processa e loga módulos manuais separadamente
   - Ao salvar `GeracaoPeca`, armazena contagem de manuais em `modulos_ativados_llm` (reutilizado no modo semi-automático)

**Fluxo atualizado**:
```
Frontend                           Backend
---------                          -------
modulosSelecionados: {1, 2, 42}    modulos_ids_curados: [1, 2, 42]
modulosManuais: {42}            -> modulos_manuais_ids: [42]
                                         |
                                   Processa e loga:
                                   "[CURADORIA] Modulo MANUAL: ID 42"
                                         |
                                   Salva no histórico:
                                   modo_ativacao_agente2: "semi_automatico"
                                   modulos_ativados_det: 2 (total - manuais)
                                   modulos_ativados_llm: 1 (manuais)
```

**Arquivos modificados**:
- `sistemas/gerador_pecas/router.py` - Schema e endpoint atualizados
- `sistemas/gerador_pecas/router_admin.py` - Comentários de documentação
- `sistemas/gerador_pecas/templates/curadoria.js` - Rastreamento de manuais
- `tests/test_curadoria_semi_automatico.py` - 12 novos testes

**Como verificar no histórico**:
- Acessar `/admin/gerador-pecas/historico`
- Gerações com `modo_ativacao_agente2 = "semi_automatico"` mostram:
  - `modulos_ativados_det`: Módulos vindos do preview (não manuais)
  - `modulos_ativados_llm`: Módulos adicionados manualmente pelo usuário

### 10. Drag and Drop Aprimorado (Correção 2026-02-02)

**Problema identificado**: O frontend apresentava problemas visuais durante o drag and drop de módulos (classes CSS não eram removidas corretamente) e não havia suporte para reordenar categorias inteiras.

**Solução implementada**:

1. **Correção visual do drag and drop**:
   - Adicionado `onDragLeave` para remover classes quando o cursor sai de uma zona
   - Criado método `limparEstadoDrag()` centralizado para limpar TODAS as classes de feedback
   - Classes removidas: `drag-over`, `bg-primary-50`, `bg-amber-50`, `category-drop-above`, `category-drop-below`

2. **Drag and drop de categorias**:
   - Adicionado handle de arrastar (`fa-grip-vertical`) no cabeçalho de cada seção
   - Estado `dragType` distingue entre drag de módulo (`'modulo'`) e categoria (`'categoria'`)
   - Estado `draggedCategory` armazena a categoria sendo arrastada
   - `categoriasOrdem` mantém a ordem das categorias definida pelo usuário

3. **Persistência da ordem no backend**:
   - Schema `CurationGenerateRequest` já incluía `categorias_ordem`
   - Backend usa ordem do frontend se fornecida, senão usa `ORDEM_CATEGORIAS_PADRAO`
   - Frontend envia `categorias_ordem` no body de `/curadoria/gerar-stream`

**Fluxo de drag de categoria**:
```
1. Usuário arrasta handle da categoria "Eventualidade"
2. onCategoryDragStart() marca dragType='categoria', guarda referência
3. onCategoryDragOver() mostra indicador visual (borda acima/abaixo)
4. onCategoryDrop() atualiza categoriasOrdem e re-renderiza
5. Ao gerar, categorias_ordem é enviada ao backend
```

**Arquivos modificados**:
- `sistemas/gerador_pecas/templates/curadoria.js`:
  - Novos métodos: `onCategoryDragStart`, `onCategoryDragOver`, `onCategoryDrop`, `onDragLeave`, `limparEstadoDrag`
  - CSS inline para feedback visual de drop de categorias
  - Handle de drag no cabeçalho de cada seção
  - `gerarComCuradoria()` envia `categorias_ordem`
- `tests/test_curadoria_semi_automatico.py`:
  - Classe `TestDragAndDropCategorias` com 11 testes
  - Classe `TestDragAndDropModulos` com 4 testes

**Como verificar**:
1. Acessar `/gerador-pecas/` e iniciar modo semi-automático
2. Arrastar o ícone de "grip" ao lado do nome da categoria para reordenar
3. Verificar que módulos dentro da categoria mantêm sua ordem
4. Gerar peça e verificar em `/admin/gerador-pecas/historico` se a ordem está correta no prompt

### 11. Instrumentação e Auditoria Completa (2026-02-02)

**Objetivo**: Permitir análise detalhada do uso do modo semi-automático para ajuste do modo automático e auditoria de decisões.

**Problema identificado**: As telas administrativas (/admin/feedbacks e /admin/gerador-pecas/historico) não distinguiam claramente gerações feitas no modo semi-automático, nem mostravam quais módulos foram adicionados/removidos manualmente.

**Solução implementada**:

1. **Persistência completa em `curadoria_metadata`**:
   ```python
   curadoria_metadata = {
       "modulos_preview_ids": [1, 2, 3],      # Sugeridos pelo Agente 2
       "modulos_curados_ids": [1, 2, 4],       # Finais selecionados
       "modulos_manuais_ids": [4],             # Adicionados manualmente
       "modulos_excluidos_ids": [3],           # Removidos pelo usuário
       "modulos_detalhados": [                 # Detalhes de cada módulo
           {"id": 1, "origem": "preview", "status": "[VALIDADO]"},
           {"id": 2, "origem": "preview", "status": "[VALIDADO]"},
           {"id": 4, "origem": "manual", "status": "[VALIDADO-MANUAL]"},
       ],
       "categorias_ordem": ["Preliminar", "Mérito"],
       "preview_timestamp": "2026-02-02T10:00:00Z",
       "total_preview": 3,
       "total_curados": 3,
       "total_manuais": 1,
       "total_excluidos": 1
   }
   ```

2. **Marcação diferenciada no prompt**:
   - Módulos do preview: `#### Título [VALIDADO]`
   - Módulos manuais: `#### Título [VALIDADO-MANUAL]`

3. **Dashboard de Feedbacks** (`/admin/feedbacks`):
   - Coluna "Modo" exibe badge: "Semi-Auto (X curados, Y manuais)"
   - Modal de detalhes mostra seção de curadoria com contagens

4. **Endpoint de Curadoria** (`/gerador-pecas-admin/geracoes/{id}/curadoria`):
   - Retorna lista de módulos incluídos com origem, status e ordem
   - Retorna lista de módulos manuais com status [VALIDADO-MANUAL]
   - Retorna lista de módulos excluídos

**Arquivos modificados**:
- `admin/router.py`:
  - `/feedbacks/lista` inclui `modo_ativacao` com detalhes de curadoria
  - `/feedbacks/consulta/{id}` inclui mesmos dados
- `sistemas/gerador_pecas/router.py`:
  - Salva `modulos_detalhados` com origem e status
  - Marca módulos manuais com [VALIDADO-MANUAL] no prompt
- `sistemas/gerador_pecas/router_admin.py`:
  - Endpoint `/curadoria` retorna detalhes completos
- `frontend/templates/admin_feedbacks.html`:
  - Coluna "Modo" na tabela
  - Seção de curadoria no modal

**Testes adicionados**:
- Classe `TestInstrumentacaoAuditoria` em `tests/test_curadoria_semi_automatico.py`
- 12 testes cobrindo estrutura de metadados, marcação de prompts, endpoints e reconstrução de auditoria

**Como usar para análise**:
1. Acessar `/admin/feedbacks` e filtrar por "gerador_pecas"
2. Identificar gerações semi-automáticas pela coluna "Modo"
3. Clicar para ver detalhes: total preview vs curados, manuais, excluídos
4. Usar endpoint `/curadoria` para análise programática
5. Comparar módulos excluídos para identificar falsos positivos do Agente 2
6. Analisar módulos manuais para identificar argumentos faltando na detecção automática

**Reconstrução de decisão**:
```python
# A partir de curadoria_metadata, é possível reconstruir:
preview = set(metadata["modulos_preview_ids"])
curados = set(metadata["modulos_curados_ids"])
manuais = set(metadata["modulos_manuais_ids"])

aceitos_preview = preview & curados    # Aceitos do Agente 2
removidos = preview - curados           # Falsos positivos
adicionados = curados - preview         # Faltando na detecção
```

## Referências

- CLAUDE.md: Regras de negócio do gerador de peças
- docs/sistemas/gerador_pecas.md: Documentação do sistema
- sistemas/gerador_pecas/orquestrador_agentes.py: Implementação dos agentes
- services/busca_vetorial/: Serviços de busca semântica
