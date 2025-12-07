## 🖥️ INTERFACE WEB PARA EDIÇÃO DE PROMPTS (CRÍTICO)

### ⚠️ REQUISITO FUNDAMENTAL

**TODOS os prompts modulares** (base, peças e conteúdo) **DEVEM ser editáveis através de interface web** por usuários autorizados (procuradores/administradores), sem necessidade de acesso ao código-fonte.

### 📋 JUSTIFICATIVA

- Jurisprudência muda constantemente (novas súmulas, temas repetitivos)
- Teses jurídicas precisam ser refinadas baseado em feedback
- Procuradores experientes precisam ajustar argumentações
- Novos módulos devem ser criados sem envolvimento de TI
- Rastreabilidade de alterações é essencial

---

## 🏗️ ARQUITETURA DE ARMAZENAMENTO

### Banco de Dados - Nova Tabela
```sql
CREATE TABLE prompt_modulos (
    id SERIAL PRIMARY KEY,
    tipo VARCHAR(20) NOT NULL,  -- 'base', 'peca', 'conteudo'
    categoria VARCHAR(50),       -- Para conteúdo: 'medicamento', 'laudo', etc.
    subcategoria VARCHAR(50),    -- 'nao_incorporado_sus', 'experimental', etc.
    nome VARCHAR(100) NOT NULL,
    titulo VARCHAR(200) NOT NULL,
    conteudo TEXT NOT NULL,      -- O prompt em si (markdown)
    ativo BOOLEAN DEFAULT true,
    ordem INTEGER DEFAULT 0,
    
    -- Metadados
    palavras_chave TEXT[],       -- Para detecção automática
    tags TEXT[],                 -- Organização/busca
    
    -- Versionamento
    versao INTEGER DEFAULT 1,
    criado_por INTEGER REFERENCES usuarios(id),
    criado_em TIMESTAMP DEFAULT NOW(),
    atualizado_por INTEGER REFERENCES usuarios(id),
    atualizado_em TIMESTAMP DEFAULT NOW(),
    
    UNIQUE(tipo, categoria, subcategoria)
);

-- Histórico de versões
CREATE TABLE prompt_modulos_historico (
    id SERIAL PRIMARY KEY,
    modulo_id INTEGER REFERENCES prompt_modulos(id),
    versao INTEGER NOT NULL,
    conteudo TEXT NOT NULL,
    alterado_por INTEGER REFERENCES usuarios(id),
    alterado_em TIMESTAMP DEFAULT NOW(),
    motivo TEXT,
    diff_resumo TEXT  -- Resumo das alterações
);

-- Índices
CREATE INDEX idx_prompt_tipo ON prompt_modulos(tipo);
CREATE INDEX idx_prompt_categoria ON prompt_modulos(categoria);
CREATE INDEX idx_prompt_ativo ON prompt_modulos(ativo);
CREATE INDEX idx_historico_modulo ON prompt_modulos_historico(modulo_id);
```

### Migration SQL
```sql
-- migrations/add_prompt_modulos.sql
-- (incluir SQL acima)

-- Inserir módulo base
INSERT INTO prompt_modulos (tipo, nome, titulo, conteudo, criado_por) VALUES
('base', 'base', 'Prompt Base', '[CONTEÚDO DO base.py]', 1);

-- Inserir módulos de peças
INSERT INTO prompt_modulos (tipo, categoria, nome, titulo, conteudo, criado_por) VALUES
('peca', 'peca', 'contestacao', 'Contestação', '[CONTEÚDO DO contestacao.py]', 1),
('peca', 'peca', 'recurso_apelacao', 'Recurso de Apelação', '[CONTEÚDO]', 1);

-- Inserir módulos de conteúdo
INSERT INTO prompt_modulos (tipo, categoria, subcategoria, nome, titulo, conteudo, palavras_chave, criado_por) VALUES
('conteudo', 'medicamento', 'nao_incorporado_sus', 'nao_incorporado_sus', 'Medicamento Não Incorporado ao SUS', '[CONTEÚDO]', 
ARRAY['não incorporado', 'conitec', 'rename', 'pcdt'], 1);
```

---

## 🎨 INTERFACE FRONTEND

### 1. Página Principal - Lista de Módulos

**Rota**: `/admin/prompts` (apenas para usuários com permissão)

**Layout**:
```
┌─────────────────────────────────────────────────────────────┐
│ Gerenciamento de Prompts Modulares                         │
│                                                             │
│ [Criar Novo Módulo] [Importar] [Exportar Todos]           │
│                                                             │
│ Filtros: [Tipo ▼] [Categoria ▼] [Buscar____________] 🔍   │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ 📄 PROMPT BASE                                             │
│ ├─ Prompt Base Geral                        [Editar] [Ver] │
│                                                             │
│ 📋 PEÇAS (5)                                               │
│ ├─ Contestação                              [Editar] [Ver] │
│ ├─ Recurso de Apelação                      [Editar] [Ver] │
│ ├─ Contrarrazões de Recurso                 [Editar] [Ver] │
│ ├─ Agravo de Instrumento                    [Editar] [Ver] │
│ └─ Embargos de Declaração                   [Editar] [Ver] │
│                                                             │
│ 💊 CONTEÚDO: MEDICAMENTO (5)                               │
│ ├─ Não Incorporado ao SUS         ⚡[5 palavras-chave]    │
│ │                                           [Editar] [Ver] │
│ ├─ Sem Registro ANVISA            ⚡[4 palavras-chave]    │
│ │                                           [Editar] [Ver] │
│ ├─ Experimental                   ⚡[3 palavras-chave]    │
│ │                                           [Editar] [Ver] │
│ ├─ Alternativa Disponível         ⚡[6 palavras-chave]    │
│ │                                           [Editar] [Ver] │
│ └─ Custo Desproporcional          ⚡[4 palavras-chave]    │
│                                             [Editar] [Ver] │
│                                                             │
│ 📋 CONTEÚDO: LAUDO MÉDICO (4)                              │
│ └─ ... [expandir]                                          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Funcionalidades**:
- ✅ Listagem hierárquica (Base → Peças → Conteúdos)
- ✅ Expandir/colapsar categorias
- ✅ Busca por título ou conteúdo
- ✅ Filtros por tipo/categoria
- ✅ Indicador visual de palavras-chave (detector)
- ✅ Botões de ação: Editar, Ver, Duplicar, Desativar

### 2. Editor de Módulo

**Rota**: `/admin/prompts/editar/:id`

**Layout**:
```
┌─────────────────────────────────────────────────────────────┐
│ ← Voltar │ Editando: Medicamento Não Incorporado ao SUS    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ Tipo: [Conteúdo ▼]                                         │
│ Categoria: [Medicamento ▼]                                 │
│ Subcategoria: [nao_incorporado_sus_______]                 │
│ Título: [Medicamento Não Incorporado ao SUS____________]   │
│                                                             │
│ Status: [x] Ativo  [ ] Inativo                             │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│ CONTEÚDO DO PROMPT (Markdown)                              │
│ ┌─────────────────────────────────────────────────────────┐│
│ │═════════════════════════════════════════════════════════││
│ │ARGUMENTO: MEDICAMENTO NÃO INCORPORADO AO SUS           ││
│ │═════════════════════════════════════════════════════════││
│ │                                                          ││
│ │## QUANDO USAR                                           ││
│ │- Medicamento não consta em listas oficiais do SUS      ││
│ │- Sem decisão CONITEC                                    ││
│ │...                                                       ││
│ │                                                          ││
│ │[30 linhas de conteúdo editável]                         ││
│ │                                                          ││
│ └─────────────────────────────────────────────────────────┘│
│                                [Editor em tela cheia]       │
├─────────────────────────────────────────────────────────────┤
│ PALAVRAS-CHAVE PARA DETECÇÃO AUTOMÁTICA                    │
│ [não incorporado] [x] [conitec] [x] [rename] [x]           │
│ [+ Adicionar palavra-chave]                                │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│ TAGS (organizacionais)                                      │
│ [saúde] [x] [medicamento] [x] [sus] [x]                   │
│ [+ Adicionar tag]                                          │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│ MOTIVO DA ALTERAÇÃO (obrigatório)                          │
│ [Atualização de jurisprudência - Tema 106 STJ____________] │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│ [Cancelar] [Preview] [Salvar e Continuar] [Salvar e Sair] │
└─────────────────────────────────────────────────────────────┘
```

**Funcionalidades**:
- ✅ Editor de texto rico (Markdown com syntax highlight)
- ✅ Preview em tempo real (split screen opcional)
- ✅ Autocompletar para jurisprudência comum
- ✅ Validação de formato (seções obrigatórias)
- ✅ Sistema de tags e palavras-chave
- ✅ Campo obrigatório: motivo da alteração
- ✅ Salvar rascunho (auto-save)

### 3. Visualizador de Módulo (Preview)

**Rota**: `/admin/prompts/ver/:id`

**Layout**:
```
┌─────────────────────────────────────────────────────────────┐
│ ← Voltar │ Medicamento Não Incorporado ao SUS              │
│                                          [Editar] [Histórico]│
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ [Conteúdo renderizado em Markdown, somente leitura]        │
│                                                             │
│ ═══════════════════════════════════════════════════════════ │
│ ARGUMENTO: MEDICAMENTO NÃO INCORPORADO AO SUS              │
│ ═══════════════════════════════════════════════════════════ │
│                                                             │
│ ## QUANDO USAR                                             │
│ • Medicamento não consta em listas oficiais do SUS         │
│ • Sem decisão CONITEC                                      │
│ ...                                                         │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│ METADADOS                                                   │
│ Criado por: João Silva em 10/01/2025                       │
│ Última alteração: Maria Santos em 15/11/2025              │
│ Versão: 3                                                  │
│ Palavras-chave: não incorporado, conitec, rename           │
│ Status: ✅ Ativo                                            │
└─────────────────────────────────────────────────────────────┘
```

### 4. Histórico de Versões

**Rota**: `/admin/prompts/:id/historico`

**Layout**:
```
┌─────────────────────────────────────────────────────────────┐
│ ← Voltar │ Histórico: Medicamento Não Incorporado ao SUS   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ 📊 Versão Atual: v5 (15/11/2025)                           │
│                                                             │
│ ┌─────────────────────────────────────────────────────────┐│
│ │ v5 • 15/11/2025 14:30 • Maria Santos                    ││
│ │ Motivo: Atualização Tema 106 STJ                        ││
│ │ [Ver] [Comparar] [Restaurar]                            ││
│ └─────────────────────────────────────────────────────────┘│
│                                                             │
│ ┌─────────────────────────────────────────────────────────┐│
│ │ v4 • 02/10/2025 09:15 • João Silva                      ││
│ │ Motivo: Inclusão de jurisprudência TJMS                 ││
│ │ [Ver] [Comparar] [Restaurar]                            ││
│ └─────────────────────────────────────────────────────────┘│
│                                                             │
│ ┌─────────────────────────────────────────────────────────┐│
│ │ v3 • 20/08/2025 16:45 • Maria Santos                    ││
│ │ Motivo: Refinamento de argumentação                     ││
│ │ [Ver] [Comparar] [Restaurar]                            ││
│ └─────────────────────────────────────────────────────────┘│
│                                                             │
│ ... [mais 2 versões anteriores]                            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Funcionalidades**:
- ✅ Timeline completa de alterações
- ✅ Quem alterou, quando e por quê
- ✅ Visualizar versão específica
- ✅ Comparar duas versões (diff visual)
- ✅ Restaurar versão anterior (cria nova versão)

### 5. Comparador de Versões (Diff)

**Rota**: `/admin/prompts/:id/comparar?v1=3&v2=5`

**Layout**:
```
┌─────────────────────────────────────────────────────────────┐
│ ← Voltar │ Comparando v3 vs v5                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ v3 (20/08/2025)              │  v5 (15/11/2025)            │
│ ─────────────────────────────┼──────────────────────────────│
│ ## FUNDAMENTAÇÃO LEGAL       │  ## FUNDAMENTAÇÃO LEGAL     │
│                              │                              │
│ Tema 106 - STJ (2018)        │  Tema 106 - STJ (2018)      │
│                              │  ➕ Atualizado em 2024      │
│                              │                              │
│ "Requisitos cumulativos..."  │  "Requisitos cumulativos..."│
│                              │                              │
│ ➖ [Trecho removido antigo]  │                              │
│                              │  ➕ [Novo trecho adicionado]│
│                              │                              │
└─────────────────────────────────────────────────────────────┘
```

**Funcionalidades**:
- ✅ Diff visual lado a lado
- ✅ Highlight de alterações (verde = adição, vermelho = remoção)
- ✅ Navegação por alterações (próxima/anterior)
- ✅ Opção de restaurar qualquer versão

### 6. Criar Novo Módulo

**Rota**: `/admin/prompts/novo`

**Layout**: Similar ao editor, mas com:
- Campos vazios
- Assistente opcional: "Qual tipo de módulo deseja criar?"
  - Peça (estrutura)
  - Argumento de medicamento
  - Argumento de laudo
  - Argumento de competência
  - Outro
- Templates pré-preenchidos baseado na escolha

---

## 🔧 BACKEND - API REST

### Endpoints Necessários
```python
# src/api/routes/prompts.py

@router.get("/api/prompts")
async def listar_modulos(
    tipo: Optional[str] = None,
    categoria: Optional[str] = None,
    busca: Optional[str] = None,
    apenas_ativos: bool = True
):
    """Lista todos os módulos com filtros"""
    pass

@router.get("/api/prompts/{id}")
async def obter_modulo(id: int):
    """Obtém módulo específico"""
    pass

@router.post("/api/prompts")
async def criar_modulo(modulo: PromptModuloCreate):
    """Cria novo módulo"""
    pass

@router.put("/api/prompts/{id}")
async def atualizar_modulo(id: int, modulo: PromptModuloUpdate):
    """Atualiza módulo (cria nova versão)"""
    pass

@router.delete("/api/prompts/{id}")
async def desativar_modulo(id: int):
    """Desativa módulo (não deleta, apenas ativo=false)"""
    pass

@router.get("/api/prompts/{id}/historico")
async def listar_historico(id: int):
    """Lista histórico de versões"""
    pass

@router.get("/api/prompts/{id}/versao/{versao}")
async def obter_versao(id: int, versao: int):
    """Obtém versão específica"""
    pass

@router.post("/api/prompts/{id}/restaurar/{versao}")
async def restaurar_versao(id: int, versao: int, motivo: str):
    """Restaura versão anterior (cria nova versão)"""
    pass

@router.get("/api/prompts/comparar")
async def comparar_versoes(id: int, v1: int, v2: int):
    """Compara duas versões (retorna diff)"""
    pass

@router.post("/api/prompts/exportar")
async def exportar_todos():
    """Exporta todos os módulos para JSON/YAML"""
    pass

@router.post("/api/prompts/importar")
async def importar_modulos(arquivo: UploadFile):
    """Importa módulos de arquivo JSON/YAML"""
    pass
```

### Models Pydantic
```python
# src/models/prompt_modulo.py

class PromptModuloBase(BaseModel):
    tipo: str  # 'base', 'peca', 'conteudo'
    categoria: Optional[str]
    subcategoria: Optional[str]
    nome: str
    titulo: str
    conteudo: str
    palavras_chave: List[str] = []
    tags: List[str] = []
    ativo: bool = True
    ordem: int = 0

class PromptModuloCreate(PromptModuloBase):
    pass

class PromptModuloUpdate(PromptModuloBase):
    motivo: str  # Obrigatório para rastrear alterações

class PromptModulo(PromptModuloBase):
    id: int
    versao: int
    criado_por: int
    criado_em: datetime
    atualizado_por: Optional[int]
    atualizado_em: Optional[datetime]
    
    class Config:
        from_attributes = True
```

---

## 🔄 ATUALIZAR BUILDER.PY

### Carregar de Banco ao Invés de Arquivos
```python
# src/services/ai/prompts/builder.py

from sqlalchemy.orm import Session
from src.models.prompt_modulo import PromptModulo

class PromptBuilder:
    def __init__(self, db: Session):
        self.db = db
        self._cache = {}  # Cache em memória
    
    def carregar_modulo_peca(self, tipo: str) -> str:
        """Carrega módulo de peça do banco"""
        if tipo in self._cache:
            return self._cache[tipo]
        
        modulo = self.db.query(PromptModulo).filter(
            PromptModulo.tipo == 'peca',
            PromptModulo.nome == tipo,
            PromptModulo.ativo == True
        ).first()
        
        if modulo:
            self._cache[tipo] = modulo.conteudo
            return modulo.conteudo
        
        return ""
    
    def carregar_modulo_conteudo(self, categoria: str, subcategoria: str) -> str:
        """Carrega módulo de conteúdo do banco"""
        cache_key = f"{categoria}_{subcategoria}"
        
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        modulo = self.db.query(PromptModulo).filter(
            PromptModulo.tipo == 'conteudo',
            PromptModulo.categoria == categoria,
            PromptModulo.subcategoria == subcategoria,
            PromptModulo.ativo == True
        ).first()
        
        if modulo:
            self._cache[cache_key] = modulo.conteudo
            return modulo.conteudo
        
        return ""
    
    def limpar_cache(self):
        """Limpa cache (chamar quando houver atualização)"""
        self._cache = {}
```

---

## 🔐 PERMISSÕES

### Quem Pode Editar Prompts?

**Criar novo grupo de permissão**:
```sql
-- Adicionar em permissoes_servico ou criar tabela específica
INSERT INTO permissoes_especiais (nome, descricao) VALUES
('editar_prompts', 'Pode editar módulos de prompts'),
('criar_prompts', 'Pode criar novos módulos de prompts'),
('excluir_prompts', 'Pode desativar módulos de prompts'),
('ver_historico_prompts', 'Pode ver histórico de alterações');

-- Vincular aos usuários
INSERT INTO usuario_permissoes (usuario_id, permissao) VALUES
(1, 'editar_prompts'),    -- Admin
(5, 'editar_prompts'),    -- Procurador chefe
(10, 'criar_prompts');    -- Coordenador do LAB
```

**Middleware de verificação**:
```python
@router.put("/api/prompts/{id}")
async def atualizar_modulo(
    id: int,
    modulo: PromptModuloUpdate,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Verificar permissão
    if not current_user.tem_permissao('editar_prompts'):
        raise HTTPException(403, "Sem permissão para editar prompts")
    
    # ... resto do código
```

---

## 📊 AUDITORIA E LOGS

### Registrar Todas as Alterações
```python
# Ao salvar módulo atualizado
def atualizar_modulo_com_auditoria(
    db: Session,
    modulo_id: int,
    novo_conteudo: str,
    usuario_id: int,
    motivo: str
):
    # 1. Buscar módulo atual
    modulo = db.query(PromptModulo).get(modulo_id)
    
    # 2. Salvar versão anterior no histórico
    historico = PromptModuloHistorico(
        modulo_id=modulo.id,
        versao=modulo.versao,
        conteudo=modulo.conteudo,
        alterado_por=usuario_id,
        motivo=motivo,
        diff_resumo=gerar_diff_resumo(modulo.conteudo, novo_conteudo)
    )
    db.add(historico)
    
    # 3. Atualizar módulo
    modulo.conteudo = novo_conteudo
    modulo.versao += 1
    modulo.atualizado_por = usuario_id
    modulo.atualizado_em = datetime.now()
    
    # 4. Limpar cache do builder
    # (broadcast para todas as instâncias se multi-servidor)
    
    db.commit()
```

---

## 🎯 FUNCIONALIDADES EXTRAS

### 1. Testar Módulo Antes de Salvar

**Funcionalidade**: Preview de como o prompt ficará quando montado
```
[Testar Módulo]
↓
Modal: "Testando módulo com caso fictício"
↓
Mostra: PROMPT_BASE + PEÇA + ESTE_MÓDULO
↓
Usuário pode validar antes de salvar
```

### 2. Sugestões de Palavras-Chave

**Funcionalidade**: IA sugere palavras-chave baseado no conteúdo
```python
# Ao criar/editar módulo
def sugerir_palavras_chave(conteudo: str) -> List[str]:
    """Extrai palavras-chave relevantes do conteúdo"""
    # Usar TF-IDF ou modelo simples
    # Retornar top 10 termos mais relevantes
```

### 3. Exportar/Importar Módulos

**Uso**:
- Backup completo dos prompts
- Compartilhar com outras PGEs
- Versionamento externo (Git)

**Formato de exportação** (YAML):
```yaml
versao: 1.0
exportado_em: 2025-11-15T14:30:00
exportado_por: maria.santos@pge.ms.gov.br

modulos:
  - tipo: conteudo
    categoria: medicamento
    subcategoria: nao_incorporado_sus
    titulo: Medicamento Não Incorporado ao SUS
    conteudo: |
      ═══════════════════════════════════════════════════════
      ARGUMENTO: MEDICAMENTO NÃO INCORPORADO AO SUS
      ═══════════════════════════════════════════════════════
      ...
    palavras_chave:
      - não incorporado
      - conitec
      - rename
    tags:
      - saúde
      - medicamento
    ativo: true
```

---

## ✅ CHECKLIST ADICIONAL - INTERFACE DE EDIÇÃO

### Backend
- [ ] Criar tabela `prompt_modulos`
- [ ] Criar tabela `prompt_modulos_historico`
- [ ] Executar migration
- [ ] Criar models Pydantic
- [ ] Implementar endpoints CRUD completos
- [ ] Implementar versionamento automático
- [ ] Implementar sistema de diff
- [ ] Atualizar `PromptBuilder` para carregar de DB
- [ ] Implementar cache com invalidação
- [ ] Adicionar permissões específicas

### Frontend
- [ ] Criar página de listagem de módulos
- [ ] Criar editor de módulo (Markdown)
- [ ] Criar visualizador de módulo
- [ ] Criar página de histórico
- [ ] Criar comparador de versões (diff visual)
- [ ] Implementar busca e filtros
- [ ] Adicionar gerenciamento de palavras-chave
- [ ] Adicionar gerenciamento de tags
- [ ] Implementar exportação
- [ ] Implementar importação

### Migração Inicial
- [ ] Script para popular DB com módulos atuais (dos arquivos .py)
- [ ] Validar integridade dos dados migrados
- [ ] Testar carregamento pelo builder

### Testes
- [ ] Testar edição de módulo
- [ ] Testar versionamento
- [ ] Testar restauração de versão
- [ ] Testar comparação de versões
- [ ] Testar invalidação de cache
- [ ] Testar permissões
- [ ] Testar exportação/importação

---

## 🚨 OBSERVAÇÕES CRÍTICAS

1. **Cache**: Implementar invalidação de cache quando módulo for atualizado (broadcast se multi-servidor)

2. **Backup**: Fazer backup automático antes de qualquer alteração

3. **Validação**: Validar estrutura mínima do prompt (seções obrigatórias)

4. **Performance**: Cache em memória + TTL curto (5 min) para recarregar alterações

5. **Auditoria**: TODAS as alterações devem ser rastreáveis (quem, quando, por quê)

6. **Rollback**: Sempre possível restaurar versões anteriores

7. **Testes A/B** (futuro): Permitir testar duas versões de um módulo e ver qual gera melhores resultados