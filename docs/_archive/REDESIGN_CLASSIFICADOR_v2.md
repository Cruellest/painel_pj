# REDESIGN DO CLASSIFICADOR DE DOCUMENTOS
## Proposta de Nova Arquitetura UX + Fluxo em Escala + TJ Sincrono

**Data:** 2026-01-24
**Autor:** LAB/PGE-MS
**Status:** Proposta para Aprovacao

---

## 1. ANALISE CRITICA DO SISTEMA ATUAL

### 1.1 Problemas Identificados na UX

#### A) Header Inconsistente (BUG)
- O classificador usa um header custom com icone generico
- **NAO** usa a logo oficial da PGE que existe em `/logo/logo-pge.png`
- Cria sensacao de "sistema paralelo" ao inves de parte do portal

#### B) Conceito de "Projeto" (CONFUSO)
O termo "Projeto" nao reflete o uso real:
- Usuario pensa: "Quero classificar 5.000 documentos"
- Sistema oferece: "Crie um projeto, adicione codigos, configure modelo..."
- Muitos cliques para uma operacao simples

**Problemas especificos:**
1. Projeto agrupa "codigos de documentos" - termo tecnico demais
2. Precisa vincular prompt ANTES de adicionar documentos
3. Separacao artificial entre "criar projeto" e "executar"
4. Nao suporta upload de PDFs locais em lote

#### C) Separacao Artificial TJ vs Upload
- Integracao TJ busca UM processo por vez
- Upload de arquivo e apenas para "classificacao avulsa" (1 arquivo)
- Nao existe forma de subir centenas de PDFs locais

#### D) Fluxo Mental Quebrado
Usuario pergunta:
- "Onde coloco meus 2.000 PDFs?" -> Nao ha resposta clara
- "Como baixo documentos do TJ em lote?" -> Modal busca 1 processo
- "Onde vejo resultados consolidados?" -> Precisa entrar em cada execucao

### 1.2 Analise do Schema de Banco (Restricao)

Tabelas existentes que DEVEMOS preservar:
```
projetos_classificacao      -> Pode ser renomeado para "Lote" conceitualmente
codigos_documento_projeto   -> Funciona bem, apenas adicionar campo para arquivo local
execucoes_classificacao     -> Funciona bem
resultados_classificacao    -> Funciona bem
prompts_classificacao       -> OK, manter
logs_classificacao_ia       -> OK, manter
```

**DECISAO:** Nao migrar banco. Adaptar fluxo e nomenclatura na UI.

---

## 2. PROPOSTA DE NOVO MODELO MENTAL

### 2.1 Renomeacao de Conceitos

| Atual (Confuso) | Novo (Claro) | Justificativa |
|-----------------|--------------|---------------|
| Projeto | **Lote** | Reflete processamento em massa |
| Codigo de Documento | **Item** | Mais generico, suporta TJ + upload |
| Execucao | **Rodada** | Linguagem mais natural |
| Classificacao Avulsa | **Teste Rapido** | Proposito real: testar prompt |

### 2.2 Nova Estrutura de Abas

```
ANTES:                          DEPOIS:
[Projetos] [Prompts] [Avulsa]   [Novo Lote] [Meus Lotes] [Prompts] [Teste Rapido]
```

**Explicacao:**
1. **Novo Lote** - Acao principal em destaque (criar lote para processar)
2. **Meus Lotes** - Historico de lotes anteriores e resultados
3. **Prompts** - Manter (funciona bem)
4. **Teste Rapido** - Renomeado, para testar prompt com 1 documento

### 2.3 Fluxo Principal Simplificado

```
USUARIO QUER: Classificar documentos em massa

PASSO 1: [Novo Lote]
         |
         v
PASSO 2: Escolha como adicionar documentos:
         +----------------------------------+
         | [Upload de Arquivos]             |  <- Arrasta PDFs/TXTs/ZIP
         |    ou                            |
         | [Baixar do TJ-MS]                |  <- Cole lista de processos
         |    ou                            |
         | [Ambos]                          |  <- Combina fontes
         +----------------------------------+
         |
         v
PASSO 3: Selecione o Prompt
         |
         v
PASSO 4: [Iniciar Classificacao]
         |
         v
PASSO 5: Acompanhe progresso em tempo real
         |
         v
PASSO 6: [Exportar Resultados] Excel/CSV/JSON
```

---

## 3. NOVA FEATURE: UPLOAD EM LOTE

### 3.1 Requisitos

- Arrastar multiplos PDFs/TXTs
- Suporte a ZIP com arquivos dentro
- Limite: 500 arquivos por vez (pode ajustar)
- Tamanho maximo por arquivo: 50MB
- Formatos: PDF, TXT

### 3.2 Fluxo Tecnico

```python
# Nova coluna em codigos_documento_projeto (sem migrar, apenas adicionar)
# arquivo_local = Column(LargeBinary, nullable=True)  # NAO ARMAZENAR PDF INTEIRO
# Em vez disso, usar path temporario ou extrair texto e armazenar hash

# Alternativa melhor: armazenar apenas referencia
arquivo_nome = Column(String(500), nullable=True)
arquivo_hash = Column(String(64), nullable=True)  # SHA256 para dedup
texto_extraido = Column(Text, nullable=True)  # Cache do texto
```

### 3.3 Interface de Upload

```
+------------------------------------------------------+
|  ADICIONAR DOCUMENTOS                                |
|                                                      |
|  +----------------------------------------------+   |
|  |                                              |   |
|  |     [Arraste arquivos aqui]                  |   |
|  |                                              |   |
|  |     ou clique para selecionar               |   |
|  |                                              |   |
|  |     PDF, TXT ou ZIP (max 500 arquivos)       |   |
|  |                                              |   |
|  +----------------------------------------------+   |
|                                                      |
|  Arquivos selecionados: 347                          |
|  +---------------------+                             |
|  | documento_001.pdf   | [x]                         |
|  | documento_002.pdf   | [x]                         |
|  | ...                 |                             |
|  +---------------------+                             |
|                                                      |
|  [Adicionar ao Lote]                                 |
+------------------------------------------------------+
```

---

## 4. NOVA FEATURE: TJ-MS EM LOTE + FLUXO SINCRONO

### 4.1 Fluxo Real do TJ-MS (Baseado na API-TJ existente)

**IMPORTANTE:** O usuario NUNCA baixa todos os documentos de um processo.

O fluxo real e:
1. Informar **lista de processos** (numeros CNJ)
2. Selecionar **tipos/categorias de documentos** para baixar (ex: Sentenca, Peticao, Decisao)
3. O sistema consulta cada processo, filtra pelos tipos, baixa apenas os documentos das categorias selecionadas

### 4.2 Mapa de Categorias de Documentos (tipoDocumento do TJ-MS)

```python
CATEGORIAS_MAP = {
    "8": "Sentenca",
    "15": "Decisoes Interlocutorias",
    "34": "Acordaos",
    "44": "Decisoes Monocraticas",
    "137": "Decisao Interlocutoria",
    "500": "Peticao Inicial",
    "510": "Peticao Intermediaria",
    "8305": "Contrarrazoes de Apelacao",
    "8320": "Contestacao",
    "8335": "Recurso de Apelacao",
    "8369": "Laudo Pericial",
    "9500": "Peticao",
    # ... mais de 150 tipos disponiveis
}
```

### 4.3 Nova Interface TJ-MS (CORRIGIDA)

```
+------------------------------------------------------+
|  IMPORTAR DO TJ-MS                                   |
|                                                      |
|  Cole a lista de processos (1 por linha):            |
|  +----------------------------------------------+   |
|  | 0800123-45.2024.8.12.0001                    |   |
|  | 0800456-78.2024.8.12.0002                    |   |
|  | 0800789-01.2024.8.12.0003                    |   |
|  | ...                                          |   |
|  +----------------------------------------------+   |
|  Total: 3 processos                                  |
|                                                      |
|  TIPOS DE DOCUMENTOS A BAIXAR:                       |
|  +--------------------+    +--------------------+   |
|  | Disponiveis        |    | Selecionados       |   |
|  |--------------------|    |--------------------|   |
|  | [ ] Mandado        |    | [x] Sentenca       |   |
|  | [ ] Certidao       |    | [x] Decisao Interl.|   |
|  | [ ] Despacho       |    | [x] Acordao        |   |
|  | [ ] Oficio         |    | [x] Peticao Inicial|   |
|  | ...                |    |                    |   |
|  +--------------------+    +--------------------+   |
|  [Adicionar ->]  [<- Remover]  [Adicionar Todas]   |
|                                                      |
|  Codigos em lote (opcional):                         |
|  [8, 15, 34, 500, 9500________________]              |
|  [Adicionar Lote]                                    |
|                                                      |
|  FILTROS OPCIONAIS:                                  |
|  [ ] Filtrar por ano: [2024, 2025] Mes: [Todos v]   |
|                                                      |
|  [Adicionar ao Lote]                                 |
+------------------------------------------------------+
```

**Funcionamento:**
1. Usuario cola lista de processos
2. Seleciona tipos de documentos desejados (categorias)
3. Opcionalmente filtra por ano/mes
4. Sistema consulta cada processo e baixa apenas docs das categorias selecionadas

### 4.4 Fluxo Sincrono TJ + Classificacao

```
BACKEND PIPELINE (corrigido):

+------------------------+     +---------------------+     +------------------+
| Lista Processos CNJ    | --> | Worker: Consultar   | --> | Worker: Filtrar  |
| + Tipos Selecionados   |     | XML do Processo     |     | por tipoDocumento|
+------------------------+     +---------------------+     +------------------+
                                                                   |
                                                                   v
                               +------------------+     +----------------+     +---------------+
                               | Worker: Baixar   | <-- | IDs filtrados  | --> | Worker: Class.|
                               | docs selecionados|     | (por categoria)|     | via OpenRouter|
                               +------------------+     +----------------+     +---------------+
                                      |                                               |
                                      v                                               v
                                [Evento SSE]                                    [Evento SSE]
                                "Baixando doc X"                                "Classificando X"
```

**Implementacao (CORRIGIDA):**

```python
async def processar_lote_tjms_sincrono(
    lote_id: int,
    processos: List[str],              # Lista de numeros CNJ
    tipos_documento: List[str],        # Categorias: ["8", "15", "34", "500"]
    prompt_id: int,
    modelo: str,
    filtro_ano: Optional[List[str]] = None,
    filtro_mes: Optional[int] = None
) -> AsyncGenerator[Dict, None]:
    """
    Pipeline: Consulta processos -> Filtra por tipo -> Baixa -> Classifica
    """
    for numero_cnj in processos:
        yield {"tipo": "consultando", "processo": numero_cnj}

        # 1. Consulta XML do processo (NAO SALVA O XML)
        xml_texto = await tjms.consultar_processo(numero_cnj)

        # 2. Extrai info de todos os documentos do XML
        todos_docs = extrair_docs_info(xml_texto)

        # 3. Filtra pelos tipos selecionados (tipoDocumento)
        docs_filtrados = [d for d in todos_docs if d["tipo_documento"] in tipos_documento]

        # 4. Aplica filtro de ano/mes se especificado
        if filtro_ano:
            docs_filtrados = [d for d in docs_filtrados if d["ano"] in filtro_ano]

        yield {"tipo": "filtrado", "processo": numero_cnj, "docs": len(docs_filtrados)}

        # 5. Para cada documento filtrado: baixar + classificar
        for doc in docs_filtrados:
            yield {"tipo": "baixando", "doc_id": doc["id"], "processo": numero_cnj}
            pdf_bytes = await tjms.baixar_documento(numero_cnj, doc["id"])

            yield {"tipo": "extraindo", "doc_id": doc["id"]}
            texto = extrair_texto(pdf_bytes)

            yield {"tipo": "classificando", "doc_id": doc["id"]}
            resultado = await openrouter.classificar(texto, prompt)

            yield {"tipo": "concluido", "doc_id": doc["id"], "resultado": resultado}
```

**Diferenca crucial vs versao anterior:**
- NAO baixa todos os documentos do processo
- Primeiro consulta XML, depois filtra por `tipoDocumento`
- So baixa os documentos das categorias selecionadas pelo usuario
- Usuario NUNCA baixa XML (conforme requisito)

---

## 5. TELA REDESENHADA: NOVO LOTE

### 5.1 Wireframe Textual

```
+============================================================================+
| [< Dashboard]  PORTAL PGE-MS                           [Usuario] [Sair]    |
|                (logo-pge.png)                                               |
+============================================================================+
|                                                                             |
| [Novo Lote*] [Meus Lotes] [Prompts] [Teste Rapido]                          |
|____________________________________________________________________________|
|                                                                             |
|  # CRIAR NOVO LOTE DE CLASSIFICACAO                                         |
|                                                                             |
|  Nome do Lote (opcional):                                                   |
|  [_Classificacao_Decisoes_Janeiro_2026___________________________]          |
|                                                                             |
|  +-----------------------------------------------------------------+       |
|  | ADICIONAR DOCUMENTOS                                             |       |
|  |                                                                  |       |
|  | [Tab: Upload]  [Tab: TJ-MS]                                      |       |
|  |                                                                  |       |
|  | +------------------------------------------------------------+  |       |
|  | |                                                            |  |       |
|  | |    Arraste PDFs, TXTs ou ZIPs aqui                         |  |       |
|  | |              (ou clique para selecionar)                   |  |       |
|  | |                                                            |  |       |
|  | +------------------------------------------------------------+  |       |
|  |                                                                  |       |
|  | Arquivos: 0 selecionados                                         |       |
|  +-----------------------------------------------------------------+       |
|                                                                             |
|  +-----------------------------------------------------------------+       |
|  | CONFIGURACAO                                                     |       |
|  |                                                                  |       |
|  | Prompt:  [Selecione um prompt... v]  [+ Criar Novo]              |       |
|  |                                                                  |       |
|  | Modelo:  [google/gemini-2.5-flash-lite v]                        |       |
|  |                                                                  |       |
|  | Modo:    (x) Chunk (mais rapido)  ( ) Documento completo         |       |
|  |          Tamanho chunk: [512] tokens   Posicao: [Fim v]          |       |
|  +-----------------------------------------------------------------+       |
|                                                                             |
|  [          INICIAR CLASSIFICACAO          ]                                |
|                                                                             |
+============================================================================+
```

### 5.2 Estados da Tela

**Estado 1: Vazio**
- Nenhum documento adicionado
- Botao "Iniciar" desabilitado

**Estado 2: Com documentos**
- Mostra quantidade: "347 documentos prontos"
- Lista expansivel com preview dos nomes
- Botao "Iniciar" habilitado

**Estado 3: Processando**
- Barra de progresso global
- Lista com status por documento (spinner, check, X)
- Eventos em tempo real via SSE
- Botao "Pausar" e "Cancelar"

**Estado 4: Concluido**
- Resumo: 340 sucesso, 7 erros
- Botoes: [Ver Resultados] [Exportar Excel] [Novo Lote]

---

## 6. TELA REDESENHADA: MEUS LOTES

### 6.1 Wireframe

```
+============================================================================+
| [< Dashboard]  PORTAL PGE-MS                           [Usuario] [Sair]    |
+============================================================================+
|                                                                             |
| [Novo Lote] [Meus Lotes*] [Prompts] [Teste Rapido]                          |
|____________________________________________________________________________|
|                                                                             |
|  # MEUS LOTES                                          [Buscar: _______]   |
|                                                                             |
|  +---------------------------------------------------------------------+   |
|  | Nome                    | Documentos | Status      | Data    | Acoes|   |
|  |-------------------------|------------|-------------|---------|------|   |
|  | Decisoes Janeiro 2026   | 2.450      | Concluido   | 24/01   | ...  |   |
|  | Teste Petições          | 15         | Concluido   | 23/01   | ...  |   |
|  | Lote TJ-MS              | 847        | Em andamento| 24/01   | ...  |   |
|  | Recursos Repetitivos    | 312        | Pausado     | 22/01   | ...  |   |
|  +---------------------------------------------------------------------+   |
|                                                                             |
|  [Mostrando 4 de 23 lotes]  [< Anterior] [Proximo >]                        |
|                                                                             |
+============================================================================+
```

### 6.2 Detalhes ao Clicar em um Lote

```
+============================================================================+
|  LOTE: Decisoes Janeiro 2026                                                |
|                                                                             |
|  Status: CONCLUIDO                                                          |
|  Criado: 24/01/2026 14:30                                                   |
|  Documentos: 2.450 total | 2.398 sucesso | 52 erros                         |
|                                                                             |
|  +--------------------+  +--------------------+  +--------------------+     |
|  | [Exportar Excel]   |  | [Exportar CSV]     |  | [Exportar JSON]    |     |
|  +--------------------+  +--------------------+  +--------------------+     |
|                                                                             |
|  Filtrar: [Todas v] [Somente erros] [Por categoria...]                      |
|                                                                             |
|  +---------------------------------------------------------------------+   |
|  | Documento           | Categoria  | Confianca | Justificativa        |   |
|  |---------------------|------------|-----------|----------------------|   |
|  | DOC_001.pdf         | Decisao    | Alta      | Decisao interlocu... |   |
|  | DOC_002.pdf         | Peticao    | Media     | Peticao inicial...   |   |
|  | DOC_003.pdf         | ERRO       | -         | Texto vazio          |   |
|  +---------------------------------------------------------------------+   |
|                                                                             |
+============================================================================+
```

---

## 7. CORRECAO: HEADER PADRAO PGE

### 7.1 Problema

Codigo atual (index.html linha 107-135):
```html
<header class="glass-effect shadow-sm border-b border-gray-200/50 sticky top-0 z-40">
    ...
    <div class="w-10 h-10 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-xl">
        <i class="fas fa-tags text-white text-lg"></i>  <!-- ICONE GENERICO -->
    </div>
    ...
</header>
```

### 7.2 Correcao

Usar o mesmo header do dashboard.html:
```html
<header class="bg-white shadow-sm border-b border-gray-200 sticky top-0 z-50">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div class="flex items-center justify-between h-16">
            <!-- Logo OFICIAL -->
            <div class="flex items-center gap-3">
                <a href="/dashboard">
                    <img src="/logo/logo-pge.png" alt="PGE-MS" class="h-12 w-auto">
                </a>
                <span class="text-lg font-semibold text-gray-700">Classificador de Documentos</span>
            </div>
            <!-- Menu usuario -->
            ...
        </div>
    </div>
</header>
```

---

## 8. DECISOES DE ENGENHARIA

### 8.1 O Que Muda

| Componente | Mudanca |
|------------|---------|
| index.html | Redesign completo das abas e fluxo |
| router.py | Novos endpoints: `/lotes/criar`, `/lotes/{id}/upload`, `/lotes/{id}/tjms-lote` |
| services.py | Novo metodo `processar_lote_sincrono()` |
| models.py | Adicionar campos `arquivo_nome`, `arquivo_hash` em CodigoDocumentoProjeto |
| Header | Trocar para padrao PGE |

### 8.2 O Que NAO Muda

| Componente | Status |
|------------|--------|
| Schema do banco | Mantido (adicionar colunas nullable) |
| PromptClassificacao | Inalterado |
| OpenRouter service | Inalterado |
| Extraction service | Inalterado |
| TJ-MS service | Apenas novos metodos |
| Exportacao | Inalterada |

### 8.3 Novos Endpoints Necessarios

```python
# Upload em lote
@router.post("/lotes/{lote_id}/upload")
async def upload_arquivos_lote(
    lote_id: int,
    arquivos: List[UploadFile] = File(...)
):
    """Adiciona multiplos arquivos a um lote"""
    pass

# TJ-MS em lote
@router.post("/lotes/{lote_id}/tjms-lote")
async def importar_tjms_lote(
    lote_id: int,
    processos: List[str]
):
    """Importa documentos de multiplos processos do TJ-MS"""
    pass

# Execucao sincrona (baixar + classificar)
@router.post("/lotes/{lote_id}/executar-sincrono")
async def executar_lote_sincrono(
    lote_id: int
):
    """Executa lote com download e classificacao em streaming"""
    pass
```

---

## 9. RESUMO: ANTES vs DEPOIS

### Fluxo Atual (6+ cliques)
1. Criar projeto
2. Configurar modelo/prompt
3. Ir em "Adicionar codigos"
4. Buscar processo no TJ
5. Selecionar documentos
6. Voltar e clicar "Executar"
7. Esperar
8. Ir em historico para ver resultados

### Fluxo Novo (3 cliques)
1. Clicar "Novo Lote"
2. Arrastar arquivos OU colar lista de processos
3. Clicar "Iniciar Classificacao"
4. Ver resultados em tempo real na mesma tela

---

## 10. PROXIMOS PASSOS

### Fase 1: Correcoes Imediatas
- [x] Trocar header para padrao PGE (index.html linha 106-129)
- [x] Renomear "Projeto" para "Lote" na UI (abas e conteudo)
- [x] Renomear "Classificacao Avulsa" para "Teste Rapido"

### Fase 2: Upload em Lote
- [x] Implementar drop zone para multiplos arquivos (index.html)
- [x] Adicionar suporte a ZIP (router.py - validacao de extensoes)
- [x] Criar endpoint de upload em lote (POST /lotes/{id}/upload)

### Fase 3: TJ-MS em Lote
- [x] Interface para colar lista de processos (textarea processosLote)
- [x] Endpoint para importar multiplos processos (POST /lotes/{id}/tjms-lote)
- [x] Selecao de tipos de documentos (tipoDocumento) - NAO "baixar todos"

### Fase 4: Fluxo Sincrono
- [x] Implementar pipeline unificado baixar+classificar (POST /lotes/{id}/executar-sincrono)
- [x] SSE com eventos granulares por etapa (StreamingResponse)
- [x] Interface de progresso detalhada (areaProgressoLote)

### Fase 5: Testes e Polimento
- [ ] Testes com 1.000+ documentos
- [ ] Otimizacao de performance
- [ ] Feedback do usuario real

---

## 11. CONCLUSAO

O sistema atual e funcional mas confuso para uso em escala. A proposta:

1. **Simplifica** o modelo mental (Projeto -> Lote)
2. **Prioriza** operacoes em massa (upload + TJ em lote)
3. **Unifica** o fluxo (baixar e classificar juntos)
4. **Padroniza** a identidade visual (header PGE)
5. **Preserva** o banco de dados existente

O resultado sera um sistema que responde claramente:
- "Como classifico milhares de documentos?" -> Novo Lote + Upload
- "Como integro com o TJ?" -> Colar lista de processos
- "Onde vejo resultados?" -> Mesma tela, em tempo real
- "Como exporto?" -> Botoes na tela de resultados

---

## 12. LOG DE IMPLEMENTACAO

### Data: 2026-01-24

**Arquivos modificados:**
1. `sistemas/classificador_documentos/templates/index.html`
   - Header padrao PGE com logo oficial
   - Novas abas: Novo Lote, Meus Lotes, Prompts, Teste Rapido
   - Interface de upload em lote com drop zone
   - Interface TJ-MS com lista de processos e tipos de documentos
   - Area de progresso e resultados em tempo real

2. `sistemas/classificador_documentos/models.py`
   - Adicionados campos em CodigoDocumentoProjeto:
     - arquivo_nome (String 500)
     - arquivo_hash (String 64)
     - texto_extraido (Text)
     - tipo_documento (String 10)

3. `sistemas/classificador_documentos/router.py`
   - POST /lotes/{id}/upload - Upload multiplos arquivos
   - POST /lotes/{id}/tjms-lote - Importar processos TJ-MS
   - POST /lotes/{id}/executar-sincrono - Execucao com SSE

4. `tests/classificador_documentos/test_router.py`
   - 5 novos testes para endpoints de lote

**Testes:**
- 196 testes passando (eram 191)
- Nenhum teste quebrado

**TODO tecnico:**
- Implementar extracao de arquivos ZIP
- Otimizar upload para arquivos grandes (chunks)
- Implementar filtro por ano/mes na consulta TJ-MS

---

**FIM DO DOCUMENTO DE REDESIGN**
