# SKILLS: Desenvolvimento Frontend com TypeScript

## Arquitetura Geral

O frontend do Portal PGE-MS utiliza uma arquitetura híbrida:

- **Templates Jinja2** (`.html`) para renderização server-side
- **TypeScript** compilado para JavaScript servido estaticamente
- **Tailwind CSS** para estilização
- **FastAPI** como servidor backend

### Estrutura de Diretórios

```
portal-pge/
├── frontend/
│   ├── package.json          # Dependências Node.js
│   ├── tsconfig.json         # Configuração TypeScript
│   ├── scripts/
│   │   └── build.mjs         # Script de build (esbuild)
│   ├── src/
│   │   ├── shared/           # Código compartilhado entre sistemas
│   │   │   ├── api.ts        # Cliente API base
│   │   │   ├── ui.ts         # Utilitários de UI (toast, modais)
│   │   │   ├── security.ts   # Funções anti-XSS
│   │   │   └── timezone.ts   # Formatação de datas (UTC -> local)
│   │   ├── types/            # Tipos TypeScript globais
│   │   │   └── api.ts        # Interfaces de API
│   │   └── sistemas/         # Código por sistema
│   │       ├── assistencia_judiciaria/
│   │       │   └── app.ts
│   │       └── matriculas_confrontantes/
│   │           └── components.ts
│   ├── static/
│   │   ├── css/
│   │   └── js/               # JS compilado dos shared
│   └── templates/            # Templates Jinja2 globais
│       ├── base.html
│       └── ...
├── sistemas/
│   ├── assistencia_judiciaria/
│   │   └── templates/
│   │       ├── index.html    # Template com <script src="app.js">
│   │       └── app.js        # JS compilado do TS
│   └── .../
```

## Organização por Sistemas

Cada sistema (ex: `assistencia_judiciaria`, `bert_training`) é independente:

1. **Backend**: `sistemas/{sistema}/router.py`, `services.py`, `models.py`
2. **Frontend**: `sistemas/{sistema}/templates/` com HTML e JS
3. **TypeScript**: `frontend/src/sistemas/{sistema}/` com arquivos `.ts`

### Fluxo de Build

```
frontend/src/sistemas/{sistema}/app.ts
        ↓ (esbuild)
sistemas/{sistema}/templates/app.js
```

## Como Criar uma Nova Tela

### 1. Criar o Template HTML

```html
<!-- sistemas/meu_sistema/templates/index.html -->
{% extends "base.html" %}
{% block title %}Meu Sistema{% endblock %}

{% block content %}
<div id="app">
    <!-- Conteúdo da página -->
    <div id="estado-inicial">
        <!-- Estado inicial -->
    </div>
    <div id="estado-loading" class="hidden">
        <!-- Estado de loading -->
    </div>
    <div id="estado-resultado" class="hidden">
        <!-- Resultado -->
    </div>
</div>
{% endblock %}

{% block scripts %}
<script src="{{ url_for('meu_sistema.static', path='app.js') }}"></script>
{% endblock %}
```

### 2. Criar o TypeScript

```typescript
// frontend/src/sistemas/meu_sistema/app.ts

import { createApiClient, checkAuth } from '../../shared/api';
import { showToast, showState } from '../../shared/ui';
import type { ApiResponse } from '../../types/api';

// ============================================
// Types
// ============================================

interface MeuDado {
  id: number;
  nome: string;
}

// ============================================
// Config
// ============================================

const API_BASE = '/meu-sistema/api';
const api = createApiClient(API_BASE);
const ESTADOS = ['inicial', 'loading', 'resultado'];

// ============================================
// State
// ============================================

interface AppState {
  dados: MeuDado[];
}

const state: AppState = {
  dados: [],
};

// ============================================
// API Calls
// ============================================

async function carregarDados(): Promise<void> {
  showState('loading', ESTADOS, 'estado-');

  try {
    const dados = await api.get<MeuDado[]>('/dados');
    if (dados) {
      state.dados = dados;
      renderDados();
      showState('resultado', ESTADOS, 'estado-');
    }
  } catch (error) {
    showToast('Erro ao carregar dados', 'error');
    showState('inicial', ESTADOS, 'estado-');
  }
}

// ============================================
// Rendering
// ============================================

function renderDados(): void {
  const container = document.getElementById('lista-dados');
  if (!container) return;

  container.innerHTML = state.dados
    .map(d => `<div class="p-2">${escapeHtml(d.nome)}</div>`)
    .join('');
}

// ============================================
// Init
// ============================================

function init(): void {
  if (!checkAuth('/meu-sistema')) return;

  // Event listeners
  document.getElementById('btn-carregar')?.addEventListener('click', carregarDados);
}

document.addEventListener('DOMContentLoaded', init);

// ============================================
// Global Exports (para onclick no HTML)
// ============================================

declare global {
  interface Window {
    carregarDados: typeof carregarDados;
  }
}

window.carregarDados = carregarDados;
```

### 3. Compilar

```bash
cd frontend
npm run build
```

## Consumindo APIs com TypeScript

### Cliente API Base

```typescript
import { createApiClient } from '../../shared/api';

const api = createApiClient('/meu-sistema/api');

// GET
const dados = await api.get<MeuTipo[]>('/endpoint');

// POST
const resultado = await api.post<RespostaTipo>('/endpoint', { campo: 'valor' });

// PUT
await api.put('/endpoint/123', { campo: 'novo valor' });

// DELETE
await api.delete('/endpoint/123');

// Download (blob)
const arquivo = await api.blob('/download/arquivo.pdf');
```

### Tipando Respostas

```typescript
// frontend/src/types/api.ts

export interface MeuSistemaResponse {
  items: MeuItem[];
  total: number;
  page: number;
}

export interface MeuItem {
  id: number;
  nome: string;
  criado_em: string;
}
```

## Padrões de TypeScript

### 1. Tipos Explícitos

```typescript
// BOM
function calcularTotal(items: Item[]): number {
  return items.reduce((acc, item) => acc + item.valor, 0);
}

// EVITAR
function calcularTotal(items) { // implicit any
  return items.reduce((acc, item) => acc + item.valor, 0);
}
```

### 2. Null Safety

```typescript
// BOM
const elemento = document.getElementById('meu-id');
if (elemento) {
  elemento.textContent = 'Texto';
}

// OU com optional chaining
document.getElementById('meu-id')?.classList.add('active');

// EVITAR
document.getElementById('meu-id').textContent = 'Texto'; // pode ser null
```

### 3. Union Types para Estados

```typescript
type EstadoApp = 'inicial' | 'loading' | 'sucesso' | 'erro';

let estadoAtual: EstadoApp = 'inicial';

function setEstado(estado: EstadoApp): void {
  estadoAtual = estado;
  // TypeScript garante que só valores válidos são passados
}
```

### 4. Interfaces para Dados da API

```typescript
// Sempre tipar respostas da API
interface ProcessoResponse {
  numero: string;
  classe: string;
  partes: Parte[];
}

interface Parte {
  nome: string;
  tipo: 'autor' | 'reu';
}
```

## Segurança (XSS Prevention)

### SEMPRE escapar dados do usuário

```typescript
import { escapeHtml } from '../../shared/ui';

// BOM
container.innerHTML = `<div>${escapeHtml(dadoUsuario)}</div>`;

// RUIM - vulnerável a XSS
container.innerHTML = `<div>${dadoUsuario}</div>`;
```

### Use textContent quando possível

```typescript
// MELHOR - não interpreta HTML
elemento.textContent = dadoUsuario;

// OK - precisa de HTML, mas escapa dados
elemento.innerHTML = `<strong>${escapeHtml(dadoUsuario)}</strong>`;
```

## Formatação de Datas

O backend grava em UTC. Use as funções de timezone:

```typescript
// Importa automaticamente via window global
// formatDateTime, formatDate, formatTime, formatRelativeTime

// Template
<td>${formatDateTime(item.criado_em)}</td>  // "24/01/2026 15:30:00"
<td>${formatDate(item.criado_em)}</td>       // "24/01/2026"
<td>${formatRelativeTime(item.criado_em)}</td> // "há 5 min"
```

## Checklist Anti-Regressão

Antes de enviar PR:

- [ ] `npm run build` passa sem erros
- [ ] `npm run typecheck` (tsc --noEmit) passa
- [ ] Testou manualmente no navegador
- [ ] Dados do usuário são escapados com `escapeHtml()`
- [ ] Datas são formatadas com funções de timezone
- [ ] Funções usadas em `onclick` estão exportadas para `window`
- [ ] Tipos de resposta da API estão definidos
- [ ] Estados de loading/erro são tratados
- [ ] Console não tem erros TypeScript ou warnings

## Comandos Úteis

```bash
# Instalar dependências
cd frontend && npm install

# Build único
npm run build

# Build com watch (desenvolvimento)
npm run build:watch

# Verificar tipos sem compilar
npm run typecheck
```

## Migração de JS para TS

Para migrar um arquivo `.js` existente:

1. Copie para `frontend/src/sistemas/{sistema}/`
2. Renomeie para `.ts`
3. Adicione tipos gradualmente (comece com `any` se necessário)
4. Use o tsconfig strict para encontrar problemas
5. Execute `npm run build` e corrija erros
6. O arquivo JS gerado sobrescreve o original

### Estratégia Incremental

Para arquivos muito grandes, migre por partes:

1. Extraia funções utilitárias para módulos separados
2. Crie interfaces para tipos de dados
3. Migre funções uma a uma
4. Mantenha compatibilidade com código JS existente via `window.*`
