# Glossário de Conceitos - Portal PGE-MS

Este documento mapeia todos os conceitos e nomenclaturas do sistema para facilitar o entendimento e manutenção.

---

## Sumário

1. [Documentos e Extração](#documentos-e-extração)
   - [Categoria de Documento (CategoriaResumoJSON)](#categoria-de-documento-categoriaresumo-json)
   - [Código de Documento](#código-de-documento)
   - [Tipo Lógico de Peça](#tipo-lógico-de-peça)
   - [Fonte de Verdade](#fonte-de-verdade)
   - [Namespace](#namespace)
   - [Schema JSON](#schema-json)
   - [Pergunta de Extração](#pergunta-de-extração)
   - [Variável de Extração](#variável-de-extração)
   - [Dependência Condicional](#dependência-condicional)

2. [Prompts e Ativação](#prompts-e-ativação)
   - [Prompt/Módulo de Conteúdo](#promptmódulo-de-conteúdo)
   - [Tipo de Módulo](#tipo-de-módulo)
   - [Grupo de Conteúdo](#grupo-de-conteúdo)
   - [Subgrupo](#subgrupo)
   - [Categoria (de Módulo)](#categoria-de-módulo)
   - [Subcategoria](#subcategoria)
   - [Tags](#tags)
   - [Modo de Ativação](#modo-de-ativação)
   - [Condição de Ativação](#condição-de-ativação)
   - [Regra Determinística](#regra-determinística)

3. [Tipos de Peça](#tipos-de-peça)
   - [Tipo de Peça Jurídica](#tipo-de-peça-jurídica)
   - [Categoria de Documento (Config)](#categoria-de-documento-config)

4. [Rotas e Telas do Admin](#rotas-e-telas-do-admin)

5. [Termos Ambíguos - Como Diferenciar](#termos-ambíguos---como-diferenciar)

---

## Documentos e Extração

### Categoria de Documento (CategoriaResumoJSON)

**O que é:**
Define um grupo de documentos que compartilham o mesmo formato de extração JSON. Agrupa documentos por finalidade jurídica (Petições, Decisões, Pareceres, etc.) e especifica como eles devem ser estruturados quando processados.

**Onde aparece no sistema:**
- Tela: `/admin/categorias-resumo-json`
- Menu: "Categorias JSON"

**Onde está no código:**
- Modelo: `sistemas/gerador_pecas/models_resumo_json.py` → `CategoriaResumoJSON`
- Tabela: `categorias_resumo_json`
- Router: `sistemas/gerador_pecas/router_categorias_json.py`

**Campos principais:**
| Campo | Descrição |
|-------|-----------|
| `nome` | Identificador único (ex: "peticoes", "decisoes", "pareceres") |
| `titulo` | Nome legível para UI (ex: "Petições", "Decisões Judiciais") |
| `codigos_documento` | Lista de códigos TJ-MS que pertencem a esta categoria |
| `formato_json` | Template/exemplo do JSON que a IA deve gerar |
| `instrucoes_extracao` | Instruções adicionais para a IA |
| `namespace_prefix` | Prefixo para variáveis (ex: "peticao", "nat") |
| `tipos_logicos_peca` | Tipos possíveis de documentos nesta categoria |
| `fonte_verdade_tipo` | Qual tipo é a "fonte de verdade" para extração |
| `is_residual` | Se é a categoria padrão (fallback) |

**Relacionamentos:**
- 1→N com Perguntas de Extração
- 1→N com Variáveis de Extração
- 1→N com Modelos de Extração

**Não confundir com:**
- **Categoria de Módulo**: Organização interna dos prompts (Preliminar, Mérito, etc.)
- **Categoria de Documento (Config)**: Modelo legado em `models_config_pecas.py`

---

### Código de Documento

**O que é:**
Identificador numérico padronizado pelo TJ-MS para tipos de documentos processuais. Usado para classificar e rotear documentos para a categoria correta.

**Onde aparece no sistema:**
- Campo "Códigos de Documento" na tela de Categorias JSON
- Endpoint: `GET /admin/api/categorias-resumo-json/codigos-disponiveis`

**Onde está no código:**
- Campo: `CategoriaResumoJSON.codigos_documento` (lista JSON)
- Função: `buscar_categoria_por_codigo()` em `router_categorias_json.py`

**Exemplos:**
| Código | Documento |
|--------|-----------|
| 500 | Petição Inicial |
| 510 | Petição Inicial Digital |
| 9500 | Petição (genérica) |
| 8 | Sentença |
| 6 | Despacho |
| 15 | Decisão |
| 8369 | Parecer |

**Não confundir com:**
- **fonte_verdade_codigo**: Filtro específico para uma variável/pergunta

---

### Tipo Lógico de Peça

**O que é:**
Classificação semântica de um documento dentro de sua categoria. A LLM classifica o documento antes de extrair dados. Usado quando `requer_classificacao=true`.

**Onde aparece no sistema:**
- Campo "Tipos Lógicos de Peça" na tela de Categorias JSON
- Processo de extração com classificação prévia

**Onde está no código:**
- Campo: `CategoriaResumoJSON.tipos_logicos_peca` (lista JSON)
- Usado em: `services_extraction.py` para classificação

**Exemplos por categoria:**
| Categoria | Tipos Lógicos |
|-----------|---------------|
| Petições | "petição inicial", "contestação", "petição intermediária" |
| Pareceres | "parecer do NAT", "parecer do CATES", "laudo pericial", "Nota Técnica NATJus" |
| Decisões | "sentença", "despacho", "decisão interlocutória" |

**Importante:**
O matching é feito SEMANTICAMENTE pela LLM (não por comparação exata de string). Exemplo: "parecer do NAT" casa com "parecer do NATJUS".

---

### Fonte de Verdade

**O que é:**
Define qual tipo de documento é considerado a "fonte confiável" para extração de uma variável ou pergunta. Garante que dados sejam extraídos do documento correto.

**Onde aparece no sistema:**
- Campo "Fonte de Verdade" na tela de Categorias JSON
- Campos "Fonte Verdade" no modal de variáveis

**Onde está no código:**
- **Nível de Grupo**: `CategoriaResumoJSON.fonte_verdade_tipo` + `fonte_verdade_codigo`
- **Nível de Pergunta**: `ExtractionQuestion.fonte_verdade_tipo` + `fonte_verdade_override`
- **Nível de Variável**: `ExtractionVariable.fonte_verdade_tipo` + `fonte_verdade_codigo`

**Hierarquia de precedência:**
1. Se variável/pergunta tem `fonte_verdade_override=true` → usa config individual
2. Senão → usa config do grupo (CategoriaResumoJSON)

**Campos relacionados:**
| Campo | Descrição |
|-------|-----------|
| `fonte_verdade_tipo` | Tipo lógico do documento (ex: "parecer do NAT") |
| `fonte_verdade_codigo` | Código específico (ex: "9500" para só petições iniciais) |
| `fonte_verdade_override` | Se sobrescreve a config do grupo |
| `requer_classificacao` | Se deve classificar antes de extrair |

**Fluxo de Extração:**

1. **Sem fonte de verdade definida:**
   - A LLM extrai a variável de **qualquer documento** do grupo (ex: qualquer documento com código 500, 510, 9500, etc.)
   - Pode pegar informação de contestação, réplica, ou qualquer outra peça

2. **Com fonte de verdade definida:**
   - A LLM primeiro **classifica semanticamente** cada documento (se usar tipo lógico)
   - Ou filtra por código específico (se usar código)
   - Extrai a variável **APENAS** do documento que corresponde ao filtro
   - Ignora os outros documentos para essa variável

**Exemplo Prático:**
```
Grupo: Petições (códigos 500, 510, 9500)
Variável: valor_da_causa
Fonte de verdade: "petição inicial"

Documentos no processo:
├── Petição Inicial (código 9500) ← LLM extrai valor_da_causa DAQUI
├── Contestação (código 9500)     ← Ignorado para esta variável
└── Réplica (código 9500)         ← Ignorado para esta variável
```

---

### Código Específico vs Tipo Lógico (LLM)

**IMPORTANTE: Tipo lógico NÃO é a mesma coisa que fonte de verdade!**

A **fonte de verdade** é o CONCEITO geral ("de qual documento extrair?"). Já **código específico** e **tipo lógico** são MÉTODOS diferentes para definir a fonte de verdade:

```
FONTE DE VERDADE (conceito)
├── Método 1: Código específico (rápido, filtro exato por número)
└── Método 2: Tipo lógico LLM (flexível, classificação semântica pela IA)
```

| Campo | Quando usar | Exemplo |
|-------|-------------|---------|
| **Código específico** | Quando o código é único para aquele tipo | Código 500 = sempre petição inicial |
| **Tipo lógico (LLM)** | Quando vários tipos usam o mesmo código | Código 9500 pode ser petição inicial OU contestação |

**Usando os dois juntos (filtro duplo):**

Quando você define código específico + tipo lógico, funciona como filtro em cascata:

```
Filtro 1: Código específico = 9500
    ↓ (filtra apenas documentos com código 9500)
Filtro 2: Tipo lógico = "petição inicial"
    ↓ (LLM classifica qual dos 9500 é petição inicial)
Resultado: Extrai apenas da petição inicial com código 9500
```

Útil quando o código é compartilhado por vários tipos de documento e você precisa refinar.

**Matching semântico:**
O tipo lógico é comparado SEMANTICAMENTE pela LLM (não por string exata). Exemplos que casam:
- "parecer do NAT" ↔ "parecer do NATJUS" ↔ "parecer técnico do NAT"
- "petição inicial" ↔ "peça vestibular" ↔ "petição inauguradora"

---

### Namespace

**O que é:**
Prefixo usado para agrupar variáveis por categoria de origem, evitando conflitos de nomes entre categorias diferentes.

**Onde aparece no sistema:**
- Campo "Namespace" na tela de Categorias JSON

**Onde está no código:**
- Campo: `CategoriaResumoJSON.namespace_prefix`
- Propriedade: `.namespace` (fallback: namespace_prefix ou nome normalizado)

**Exemplo:**
```
Categoria "pareceres" com namespace "nat"
→ variável "medicamento" fica "nat_medicamento"

Categoria "peticoes" com namespace "peticao"
→ variável "medicamento" fica "peticao_medicamento"
```

**Benefício:**
Permite ter variáveis com mesmo nome base em categorias diferentes sem conflito.

---

### Schema JSON

**O que é:**
Estrutura que define quais campos/variáveis devem ser extraídos de um documento e seus tipos de dados. Pode ser gerado por IA ou criado manualmente.

**Onde aparece no sistema:**
- Gerado via "Gerar Schema" na tela de Categorias JSON
- Campo `formato_json` nas categorias

**Onde está no código:**
- Modelo: `ExtractionModel` em `models_extraction.py`
- Campo: `schema_json` (objeto JSON)
- Serviço: `ExtractionSchemaGenerator` em `services_extraction.py`

**Modos:**
| Modo | Descrição |
|------|-----------|
| `ai_generated` | Gerado automaticamente pela IA a partir das perguntas |
| `manual` | Criado/editado manualmente pelo admin |

**Exemplo de schema:**
```json
{
  "medicamento_nome": {"type": "text", "description": "Nome do medicamento"},
  "incorporado_sus": {"type": "boolean", "description": "Se está incorporado ao SUS"},
  "valor_tratamento": {"type": "currency", "description": "Valor do tratamento"}
}
```

---

### Pergunta de Extração

**O que é:**
Pergunta em linguagem natural criada pelo admin para definir o que extrair de documentos. A IA usa essas perguntas para gerar o schema e criar variáveis normalizadas.

**Onde aparece no sistema:**
- Aba "Perguntas" dentro de uma categoria em `/admin/categorias-resumo-json`
- Criação em lote com análise de dependências

**Onde está no código:**
- Modelo: `ExtractionQuestion` em `models_extraction.py`
- Tabela: `extraction_questions`
- Router: `router_extraction.py` endpoints `/perguntas`

**Campos principais:**
| Campo | Descrição |
|-------|-----------|
| `pergunta` | Texto da pergunta em linguagem natural |
| `nome_variavel_sugerido` | Sugestão de slug para a variável |
| `tipo_sugerido` | Sugestão de tipo de dado |
| `opcoes_sugeridas` | Opções para tipo choice/list |
| `depends_on_variable` | Dependência de outra variável |

**Exemplo:**
```
Pergunta: "O medicamento é incorporado ao SUS?"
Tipo sugerido: boolean
Variável sugerida: medicamento_incorporado_sus
```

---

### Variável de Extração

**O que é:**
Campo técnico normalizado que armazena dados extraídos de documentos. Criada a partir de perguntas (via IA) ou manualmente. Usada em regras determinísticas.

**Onde aparece no sistema:**
- Tela: `/admin/variaveis`
- Menu: "Painel de Variáveis"
- Usada em regras determinísticas de prompts

**Onde está no código:**
- Modelo: `ExtractionVariable` em `models_extraction.py`
- Tabela: `extraction_variables`
- Router: `router_extraction.py` endpoints `/variaveis`

**Campos principais:**
| Campo | Descrição |
|-------|-----------|
| `slug` | Identificador técnico único (ex: "peticao_valor_causa") |
| `label` | Nome legível para UI |
| `tipo` | Tipo de dado (text, number, date, boolean, choice, list, currency) |
| `categoria_id` | Categoria de origem |
| `opcoes` | Lista de opções para tipo choice/list |
| `is_conditional` | Se depende de outra variável |

**Tipos de dados:**
| Tipo | Descrição | Exemplo |
|------|-----------|---------|
| `text` | Texto livre | "Dipirona 500mg" |
| `number` | Valor numérico | 42 |
| `date` | Data (YYYY-MM-DD) | "2024-01-15" |
| `boolean` | Sim/Não | true/false |
| `choice` | Escolha única | "alto_custo" |
| `list` | Lista de valores | ["item1", "item2"] |
| `currency` | Valor monetário | 1500.00 |

---

### Dependência Condicional

**O que é:**
Relação onde uma pergunta/variável só é aplicável quando outra variável satisfaz uma condição específica. Permite criar árvores de perguntas contextuais.

**Onde aparece no sistema:**
- Indicador de dependência na listagem de variáveis
- Grafo de dependências em categorias
- Configuração de dependência em perguntas

**Onde está no código:**
- Campos: `depends_on_variable`, `dependency_operator`, `dependency_value`
- Serviço: `DependencyInferenceService` em `services_dependencies.py`
- Serviço: `DependencyEvaluator` para avaliar visibilidade

**Operadores disponíveis:**
| Operador | Descrição |
|----------|-----------|
| `equals` | Valor igual a |
| `not_equals` | Valor diferente de |
| `in_list` | Está na lista |
| `not_in_list` | Não está na lista |
| `exists` | Variável tem valor |
| `not_exists` | Variável não tem valor |
| `greater_than` | Maior que (numérico) |
| `less_than` | Menor que (numérico) |

**Exemplo:**
```
"Qual alternativa foi tentada?"
  → depends_on_variable: "medicamento_incorporado_sus"
  → dependency_operator: "equals"
  → dependency_value: false

(Só pergunta se medicamento NÃO é incorporado ao SUS)
```

---

## Prompts e Ativação

### Prompt/Módulo de Conteúdo

**O que é:**
Bloco de texto editável que compõe uma peça jurídica. É a unidade básica de conteúdo do sistema gerador de peças. Pode ser base, de peça ou de conteúdo.

**Onde aparece no sistema:**
- Tela: `/admin/prompts-modulos`
- Menu: "Prompts Modulares"

**Onde está no código:**
- Modelo: `PromptModulo` em `admin/models_prompts.py`
- Tabela: `prompt_modulos`
- Router: `admin/router_prompts.py`

**Campos principais:**
| Campo | Descrição |
|-------|-----------|
| `nome` | Identificador técnico único |
| `titulo` | Nome legível para UI |
| `tipo` | base, peca ou conteudo |
| `conteudo` | Texto do prompt em Markdown |
| `condicao_ativacao` | Quando o prompt deve ser usado |
| `modo_ativacao` | "llm" ou "deterministic" |
| `regra_deterministica` | Regra AST (se modo determinístico) |

---

### Tipo de Módulo

**O que é:**
Classificação do módulo de prompt que define seu papel no sistema.

**Onde aparece no sistema:**
- Filtro "Tipo" na tela de Prompts Modulares

**Onde está no código:**
- Campo: `PromptModulo.tipo`

**Tipos:**
| Tipo | Descrição |
|------|-----------|
| `base` | Prompts fundamentais do sistema (instruções gerais) |
| `peca` | Prompts específicos de um tipo de peça jurídica |
| `conteudo` | Blocos de conteúdo temático (a maioria) |

---

### Grupo de Conteúdo

**O que é:**
Agrupa módulos de conteúdo por domínio temático. Representa grandes áreas de atuação jurídica da PGE.

**Onde aparece no sistema:**
- Seletor de grupo na tela de Prompts Modulares
- Menu lateral para filtrar prompts

**Onde está no código:**
- Modelo: `PromptGroup` em `admin/models_prompt_groups.py`
- Tabela: `prompt_groups`

**Exemplos:**
| Slug | Nome |
|------|------|
| `ps` | Prestação de Saúde |
| `pp` | Pessoa e Personalidade |
| `detran` | DETRAN/Trânsito |

**Relacionamentos:**
- 1→N com Subgrupos
- 1→N com Subcategorias
- 1→N com Módulos de Conteúdo

---

### Subgrupo

**O que é:**
Subdivide um grupo em seções temáticas menores. Permite organização mais granular dos prompts.

**Onde aparece no sistema:**
- Seletor de subgrupo na tela de Prompts Modulares (após selecionar grupo)

**Onde está no código:**
- Modelo: `PromptSubgroup` em `admin/models_prompt_groups.py`
- Tabela: `prompt_subgroups`

**Exemplo de hierarquia:**
```
Grupo: PS (Prestação de Saúde)
├── Subgrupo: Medicamentos
├── Subgrupo: Cirurgias
├── Subgrupo: Laudos Médicos
└── Subgrupo: Internações
```

---

### Categoria (de Módulo)

**O que é:**
Organização interna dos módulos dentro de um grupo que define a ORDEM de aparição no texto gerado. NÃO confundir com categoria de documento.

**Onde aparece no sistema:**
- Coluna "Categoria" na tabela de prompts
- Ordenação dos módulos por categoria

**Onde está no código:**
- Campo: `PromptModulo.categoria` (string)
- Ordem: `CategoriaOrdem` em `models_prompt_groups.py`

**Valores comuns:**
| Categoria | Ordem | Descrição |
|-----------|-------|-----------|
| Preliminar | 0 | Questões processuais iniciais |
| Mérito | 1 | Argumentos de mérito |
| Eventualidade | 2 | Argumentos subsidiários |
| Pedidos | 3 | Pedidos finais |

**Não confundir com:**
- **Categoria de Documento**: Agrupa documentos para extração (CategoriaResumoJSON)

---

### Subcategoria

**O que é:**
Classificação adicional para filtrar módulos na geração de peças. Permite ativar/desativar grupos de módulos por contexto.

**Onde aparece no sistema:**
- Chips de subcategoria nos módulos
- Filtro de subcategoria na geração

**Onde está no código:**
- Modelo: `PromptSubcategoria` em `admin/models_prompt_groups.py`
- Tabela: `prompt_subcategorias`
- Relação M:N: `prompt_modulo_subcategorias`

**Exemplos (grupo PS):**
- Alto Custo
- Experimental
- Incorporado SUS
- Urgente

---

### Tags

**O que é:**
Lista de palavras-chave para organização e busca de módulos. Diferente da categoria, é mais granular e flexível.

**Onde aparece no sistema:**
- Campo "Tags" no modal de edição de prompt
- Busca por tags

**Onde está no código:**
- Campo: `PromptModulo.tags` (lista JSON)

**Exemplo:**
```json
["medicamento", "alto_custo", "incorporacao_sus", "urgente"]
```

---

### Modo de Ativação

**O que é:**
Define COMO um prompt é avaliado para decidir se deve ser incluído na peça gerada.

**Onde aparece no sistema:**
- Campo "Modo de Ativação" no modal de edição de prompt
- Indicador visual na listagem (ícone diferente)

**Onde está no código:**
- Campo: `PromptModulo.modo_ativacao`

**Modos:**
| Modo | Descrição | Velocidade |
|------|-----------|------------|
| `llm` | Avaliado por IA (Agente 2 - Detector) | Mais lento |
| `deterministic` | Avaliado por regra AST sem IA | Mais rápido |

---

### Condição de Ativação

**O que é:**
Texto em linguagem natural que descreve QUANDO um prompt deve ser incluído na peça. Interpretado pela IA (modo LLM) ou convertido para regra (modo determinístico).

**Onde aparece no sistema:**
- Campo "Condição de Ativação" no modal de prompt
- Armazenado como referência mesmo em modo determinístico

**Onde está no código:**
- Campo: `PromptModulo.condicao_ativacao`
- Campo: `PromptModulo.regra_texto_original` (texto original da regra)

**Exemplo:**
```
"O medicamento é de alto custo e não está na lista RENAME"
```

---

### Regra Determinística

**O que é:**
Estrutura JSON (AST - Abstract Syntax Tree) que define condições para ativação de prompt SEM usar IA no runtime. Avaliada por lógica pura com dados extraídos.

**Onde aparece no sistema:**
- Gerada automaticamente ao converter condição de ativação
- Visualização da regra no modal de prompt

**Onde está no código:**
- Campo: `PromptModulo.regra_deterministica` (JSON)
- Gerador: `DeterministicRuleGenerator` em `services_deterministic.py`
- Avaliador: `DeterministicRuleEvaluator`

**Estrutura:**
```json
{
  "type": "and",
  "conditions": [
    {
      "type": "condition",
      "variable": "medicamento_alto_custo",
      "operator": "equals",
      "value": true
    },
    {
      "type": "condition",
      "variable": "medicamento_rename",
      "operator": "equals",
      "value": false
    }
  ]
}
```

**Operadores lógicos:** `and`, `or`, `not`
**Operadores de comparação:** `equals`, `not_equals`, `contains`, `greater_than`, `less_than`, `in_list`, `exists`, `is_empty`, etc.

---

## Tipos de Peça

### Tipo de Peça Jurídica

**O que é:**
Define um tipo de documento jurídico que pode ser gerado pelo sistema (Contestação, Recurso de Apelação, etc.).

**Onde aparece no sistema:**
- Seleção de tipo na geração de peças
- Configuração em `/admin/modulos-tipo-peca`

**Onde está no código:**
- Modelo: `TipoPeca` em `models_config_pecas.py`
- Tabela: `tipos_peca`

**Exemplos:**
- Contestação
- Recurso de Apelação
- Contrarrazões
- Parecer

---

### Categoria de Documento (Config)

**O que é:**
Modelo LEGADO que define categorias de documentos analisados para cada tipo de peça. Diferente de CategoriaResumoJSON.

**Onde aparece no sistema:**
- Configuração de tipos de peça

**Onde está no código:**
- Modelo: `CategoriaDocumento` em `models_config_pecas.py`
- Tabela: `categorias_documento`

**Não confundir com:**
- **CategoriaResumoJSON**: Sistema novo de categorias com extração JSON

---

## Rotas e Telas do Admin

| Rota | Tela | Descrição |
|------|------|-----------|
| `/admin/prompts-modulos` | Prompts Modulares | Gerenciamento de prompts/módulos de conteúdo |
| `/admin/categorias-resumo-json` | Categorias JSON | Configuração de categorias de documento e extração |
| `/admin/variaveis` | Painel de Variáveis | Gerenciamento de variáveis de extração |
| `/admin/prompts-config` | Configuração de Prompts | Administração de prompts base de IA |
| `/admin/modulos-tipo-peca` | Módulos por Tipo de Peça | Configuração de módulos ativos por tipo |
| `/admin/gerador-pecas/historico` | Histórico de Gerações | Visualização de peças geradas |
| `/admin/pedido-calculo/debug` | Debug Pedido de Cálculo | Logs e debug do sistema de cálculo |
| `/admin/prestacao-contas/debug` | Debug Prestação de Contas | Logs e debug de prestação de contas |
| `/admin/users` | Gerenciamento de Usuários | Administração de usuários |
| `/admin/feedbacks` | Dashboard de Feedbacks | Visualização de feedbacks |

---

## Termos Ambíguos - Como Diferenciar

### "Categoria"

| Contexto | Significado | Localização |
|----------|-------------|-------------|
| Categoria de Documento | Grupo de docs para extração JSON | `/admin/categorias-resumo-json` |
| Categoria de Módulo | Organização de prompts (Preliminar, Mérito...) | Campo em PromptModulo |
| Categoria de Documento (Config) | Modelo legado para tipos de peça | `models_config_pecas.py` |

**Recomendação:** Usar "Categoria JSON" ou "Categoria de Extração" para CategoriaResumoJSON.

---

### "Tipo"

| Contexto | Significado | Exemplo |
|----------|-------------|---------|
| Tipo de Módulo | Classificação do prompt | base, peca, conteudo |
| Tipo de Variável | Tipo de dado da variável | text, number, boolean |
| Tipo de Peça | Documento jurídico gerado | Contestação, Apelação |
| Tipo Lógico de Peça | Classificação semântica de documento | petição inicial, parecer do NAT |

---

### "Grupo"

| Contexto | Significado | Exemplo |
|----------|-------------|---------|
| Grupo de Conteúdo | Agrupa prompts por área | PS, PP, DETRAN |
| Grupo/Categoria de Documento | Sinônimo de CategoriaResumoJSON | peticoes, decisoes |

**Recomendação:** Usar "Grupo de Prompts" e "Categoria de Documento" para evitar ambiguidade.

---

### "Assunto" / "Tag"

| Contexto | Significado |
|----------|-------------|
| Tags | Lista de palavras-chave em prompts |
| Assunto | Pode referir-se a tags ou subcategorias |

**Recomendação:** Usar "Tags" para palavras-chave livres e "Subcategoria" para classificação estruturada.

---

### "Variável" vs "Pergunta"

| Termo | Significado |
|-------|-------------|
| Pergunta de Extração | Texto em linguagem natural (entrada do admin) |
| Variável de Extração | Campo técnico normalizado (saída do sistema) |

**Fluxo:** Pergunta → (IA gera schema) → Variável

---

### "Schema" vs "Formato JSON"

| Termo | Significado |
|-------|-------------|
| Schema JSON | Estrutura técnica gerada pela IA (ExtractionModel) |
| formato_json | Template/exemplo que orienta a IA (CategoriaResumoJSON) |

---

### "Condição" vs "Regra"

| Termo | Significado |
|-------|-------------|
| Condição de Ativação | Texto em linguagem natural |
| Regra Determinística | Estrutura JSON/AST técnica |

**Fluxo:** Condição (texto) → (IA converte) → Regra (AST)

---

## Diagrama de Relacionamentos

```
┌─────────────────────────────────────────────────────────────────┐
│                    EXTRAÇÃO DE DOCUMENTOS                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  CategoriaResumoJSON (peticoes, decisoes, pareceres)           │
│      │                                                          │
│      ├── codigos_documento: [500, 510, 9500]                   │
│      ├── tipos_logicos_peca: ["petição inicial", ...]          │
│      ├── fonte_verdade_tipo: "petição inicial"                 │
│      ├── namespace_prefix: "peticao"                           │
│      │                                                          │
│      ├─→ ExtractionQuestion (perguntas em linguagem natural)   │
│      │       └── depends_on_variable (dependência)             │
│      │                                                          │
│      ├─→ ExtractionVariable (variáveis normalizadas)           │
│      │       ├── slug: "peticao_valor_causa"                   │
│      │       ├── tipo: boolean | text | number | ...           │
│      │       └── is_conditional: true/false                    │
│      │                                                          │
│      └─→ ExtractionModel (schema gerado)                       │
│              └── schema_json: {...}                            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    PROMPTS E ATIVAÇÃO                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  PromptGroup (PS, PP, DETRAN)                                  │
│      │                                                          │
│      ├─→ PromptSubgroup (Medicamentos, Laudos)                 │
│      ├─→ PromptSubcategoria (Alto Custo, Experimental)         │
│      └─→ CategoriaOrdem (Preliminar, Mérito, Eventualidade)    │
│                                                                 │
│  PromptModulo                                                   │
│      ├── tipo: base | peca | conteudo                          │
│      ├── categoria: "Preliminar" | "Mérito" | ...              │
│      ├── condicao_ativacao: "texto em linguagem natural"       │
│      │                                                          │
│      ├── modo_ativacao: "llm" | "deterministic"                │
│      │   ├── LLM → Agente 2 (Detector) avalia                  │
│      │   └── Deterministic → Regra AST avalia                  │
│      │                                                          │
│      └── regra_deterministica: { AST JSON }                    │
│              └─→ usa ExtractionVariable                        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Changelog

| Data | Alteração |
|------|-----------|
| 2024-01-15 | Documento criado com mapeamento inicial |
