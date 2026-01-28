# Beta do Gerador de Peças para Cumprimento de Sentença
Requisitos completos (funcionais, técnicos e arquiteturais)

## Objetivo
Criar um modo novo de geração de peças voltado a **Cumprimento de Sentença**, chamado **“Cumprimento de Sentença (beta)”**, acessível a partir do **/gerador-pecas/**, mas com implementação **totalmente modularizada**, garantindo que **NADA da lógica do gerador normal seja afetado**.

O beta opera com **dois agentes de IA**:
- **Agente 1**: coleta documentos, avalia relevância e gera **JSONs de resumo por documento**
- **Agente 2**: consolida os JSONs relevantes, resume o processo, sugere peças e conduz o chatbot até a geração final

---

## Escopo do beta

### Inclui
- Novo botão e novo fluxo no front em `/gerador-pecas/`
- Pipeline próprio de cumprimento de sentença
- Avaliação de relevância de documentos
- Chatbot com streaming e histórico lateral
- Integração com `/admin/categorias-resumo-json`
- Integração com `/admin/prompts-config`
- Reuso do banco vetorial existente
- Persistência completa para auditoria e debug

### Não inclui
- Qualquer alteração de comportamento do gerador normal
- Reaproveitamento inseguro de código que cause efeitos colaterais

---

## Regras de acesso

### Pode acessar
- Usuários cujo **grupo padrão** seja **PS** (configurado em `/admin/users`)
- Usuários **admin**, independentemente do grupo padrão

### Não pode acessar
- Usuários não admin cujo grupo padrão não seja PS

### Segurança
- O botão deve ser controlado no front
- A rota deve ser validada no backend
- Acesso direto por URL sem permissão deve ser bloqueado

---

## Experiência de usuário (UI/UX)

### Acesso
Em `/gerador-pecas/`, deve existir um botão visível:
- Texto: **Cumprimento de Sentença (beta)**

### Tela do beta
- Input para número do processo CNJ
- Etapas visíveis de processamento
- Área principal com streaming
- Chatbot integrado
- Histórico de conversa na lateral
- Mesma base visual do gerador normal

---

## Fluxo funcional detalhado

### Passo 1: Entrada do processo
- Usuário informa número do processo de cumprimento
- Validação CNJ client e server-side

---

### Passo 2: Download de documentos
- Baixar todos os documentos do processo
- Exceção:
  - Documentos cujo código conste em  
    `/admin/categorias-resumo-json` → **Códigos Ignorados na Extração JSON**

---

## Avaliação de Relevância de Documentos (obrigatória)

### Fonte única de verdade
O **Agente 1** deve aplicar **EXATAMENTE** os mesmos **Critérios de Relevância de Documentos** já utilizados pelo sistema atual, reutilizando o prompt configurado em:

- `/admin/prompts-config`  
  (Critérios de Relevância de Documentos)

Esse prompt:
- Não pode ser duplicado
- Não pode ser reescrito
- Não pode ser hardcoded

---

### Ordem obrigatória do pipeline (Agente 1)

Para cada documento baixado:

1) Verificar se o código está na lista de **Códigos Ignorados**
   - Se estiver: documento descartado

2) Aplicar **Critérios de Relevância**
   - Classificar como:
     - Relevante
     - Irrelevante

3) Apenas documentos **RELEVANTES** seguem adiante

---

### Consequências da avaliação
- Documentos **irrelevantes**:
  - ❌ Não geram JSON
  - ❌ Não são enviados ao Agente 2
  - ✔️ Devem ser registrados para auditoria

---

## Geração de JSON padrão por documento (Agente 1)

### Características
- Um único schema padrão
- Não usar categorias normais do gerador
- Usar exclusivamente a categoria:
  - **Cumprimento de Sentença**

### Local de configuração do schema
- `/admin/categorias-resumo-json`
- Categoria: **Cumprimento de Sentença**

---

### Schema mínimo esperado
(O schema exato é configurável no admin)

- `document_id`
- `tipo_documento`
- `data_documento`
- `resumo`
- `pontos_relevantes`
- `pedidos_ou_determinacoes`
- `partes_mencionadas` (opcional)
- `observacoes` (opcional)

Regras:
- JSON válido
- Sem markdown
- Campos obrigatórios sempre presentes
- Documento sem texto deve ser explicitamente indicado

---

## Modelo do Agente 1
- Modelo Gemini
- Configurável em `/admin/prompts-config`
- Alterável sem deploy
- Modelo usado deve ser registrado em log

---

## Consolidação e sugestões (Agente 2)

### Funções
- Analisar todos os JSONs relevantes
- Gerar resumo consolidado do cumprimento
- Sugerir peças possíveis ao usuário

### Streaming
- As sugestões devem ser exibidas via streaming no front

### Modelo
- Configurável separadamente em `/admin/prompts-config`

---

## Chatbot e geração da peça final

### Funcionamento
- Usuário pode:
  - Escolher uma sugestão
  - Ou pedir algo livremente

### Geração da peça
- Usar prompt de sistema específico do beta
- Prompt editável em `/admin/prompts-config`
- Totalmente separado do prompt do gerador normal

---

## Banco vetorial
- Usar o mesmo banco vetorial do gerador normal
- Mesmo mecanismo de busca
- Logs de consulta vetorial obrigatórios

---

## Persistência obrigatória

### Deve ser armazenado
- Sessão do beta
- Documentos baixados
- Avaliação de relevância por documento
- JSONs gerados
- Consolidação do Agente 2
- Conversas do chatbot
- Peça final

---

## Modularização do código

### Regra central
O beta deve ser **um módulo isolado**, apesar de aparecer junto ao gerador normal no front.

### Requisitos
- Rotas próprias
- Services próprios
- DTOs próprios
- Testes próprios

### Proibido
- Colocar `if` no pipeline do gerador normal
- Alterar comportamento do gerador existente

---

## Testes obrigatórios

### Funcionais
- Controle de acesso
- Fluxo completo do beta

### Pipeline
- Documento irrelevante não chega ao Agente 2
- Documento relevante gera JSON
- Ignorados não entram no fluxo

### Configuração
- Troca de modelos afeta execução
- Troca de prompt afeta execução

### Não regressão
- Gerador normal funciona exatamente igual

---

## Critérios de aceite finais

- Botão visível corretamente
- Documentos irrelevantes não influenciam o beta
- JSONs seguem o schema configurado
- Modelos e prompts controlados via admin
- Sugestões em streaming
- Chat funcional com histórico lateral
- Peça gerada no mesmo padrão do gerador normal
- Código modular, seguro e testado
