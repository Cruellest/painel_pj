# Plano de Migração Completa: Vue 3 + TypeScript

> **Versão:** 2.0
> **Data:** 2026-01-18
> **Objetivo:** Migrar 100% do frontend para Vue 3 + TypeScript
> **Princípio:** Cada fase é independente, testável e não quebra o sistema

---

## Visão Geral da Migração

```
FASE 0-1: Preparação
┌─────────────────────┐
│ FastAPI + Jinja2    │  ← Sistema atual (100%)
│ 17 templates        │
│ JS inline           │
└─────────────────────┘

FASE 2-3: Coexistência
┌─────────────────────┐
│ Jinja2 (80%)        │  ← Páginas legadas
│ Vue 3 + TS (20%)    │  ← Novas páginas migradas
└─────────────────────┘

FASE 4-6: Migração Massiva
┌─────────────────────┐
│ Jinja2 (20%)        │  ← Últimas páginas
│ Vue 3 + TS (80%)    │  ← Maioria migrada
└─────────────────────┘

FASE 7-8: Finalização
┌─────────────────────┐
│ Vue 3 + TS (100%)   │  ← Frontend completo
│ FastAPI (API only)  │  ← Backend puro
└─────────────────────┘
```

---

## Inventário Atual do Frontend

### Templates Jinja2 (17 arquivos)

| Arquivo | Complexidade | Linhas JS | Prioridade |
|---------|--------------|-----------|------------|
| `base.html` | Baixa | ~50 | Fase 7 (último) |
| `login.html` | Baixa | ~30 | Fase 4 |
| `index.html` (home) | Baixa | ~20 | Fase 4 |
| `admin_usuarios.html` | Média | ~200 | Fase 5 |
| `admin_variaveis.html` | Alta | ~400 | Fase 3 |
| `admin_modulos.html` | Alta | ~500 | Fase 3 |
| `admin_tipos_peca.html` | Média | ~300 | Fase 5 |
| `admin_grupos.html` | Média | ~250 | Fase 5 |
| `admin_subcategorias.html` | Média | ~200 | Fase 5 |
| `consulta_processo.html` | Média | ~300 | Fase 4 |
| `gerador_pecas.html` | Muito Alta | ~600 | Fase 6 |
| `resultado_peca.html` | Alta | ~400 | Fase 6 |
| `historico.html` | Média | ~200 | Fase 5 |
| `relatorios.html` | Média | ~250 | Fase 5 |
| `perfil.html` | Baixa | ~100 | Fase 4 |
| `erro_*.html` | Baixa | ~20 | Fase 7 |
| `partials/*.html` | Média | ~150 | Fase 7 |

**Total estimado:** ~4.000 linhas de JavaScript inline

### Arquivo JS Externo

| Arquivo | Linhas | Descrição |
|---------|--------|-----------|
| `security.js` | 257 | Utilitários de segurança |

---

## Fases de Migração

---

## Fase 0: Preparação do Ambiente

**Objetivo:** Configurar tooling Vue + TS sem alterar sistema existente

**Duração estimada:** 1-2 dias

### 0.1 Criar estrutura de diretórios

```
portal-pge/
├── frontend/              # EXISTENTE - manter intacto
│   ├── templates/
│   └── static/
└── vue-app/               # NOVO
    ├── src/
    │   ├── main.ts
    │   ├── App.vue
    │   ├── assets/
    │   │   └── styles/
    │   │       ├── variables.scss
    │   │       └── global.scss
    │   ├── components/
    │   │   ├── ui/           # Componentes base
    │   │   ├── layout/       # Header, Sidebar, Footer
    │   │   └── shared/       # Componentes compartilhados
    │   ├── views/            # Páginas
    │   │   ├── auth/
    │   │   ├── admin/
    │   │   ├── processos/
    │   │   └── pecas/
    │   ├── stores/           # Pinia stores
    │   ├── composables/      # Composables Vue
    │   ├── types/            # Tipos TypeScript
    │   ├── api/              # Cliente API
    │   ├── router/           # Vue Router
    │   └── utils/            # Utilitários
    ├── public/
    ├── index.html
    ├── package.json
    ├── tsconfig.json
    ├── vite.config.ts
    └── vitest.config.ts
```

### 0.2 package.json

```json
{
  "name": "portal-pge-vue",
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vue-tsc --noEmit && vite build",
    "preview": "vite preview",
    "test": "vitest",
    "test:coverage": "vitest --coverage",
    "lint": "eslint src --ext .vue,.ts,.tsx --fix",
    "type-check": "vue-tsc --noEmit"
  },
  "dependencies": {
    "vue": "^3.4.0",
    "vue-router": "^4.2.0",
    "pinia": "^2.1.0",
    "axios": "^1.6.0",
    "@vueuse/core": "^10.7.0"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^5.0.0",
    "@vue/test-utils": "^2.4.0",
    "typescript": "^5.3.0",
    "vite": "^5.0.0",
    "vitest": "^1.2.0",
    "vue-tsc": "^1.8.0",
    "@types/node": "^20.0.0",
    "eslint": "^8.56.0",
    "@typescript-eslint/eslint-plugin": "^6.0.0",
    "@typescript-eslint/parser": "^6.0.0",
    "eslint-plugin-vue": "^9.0.0",
    "sass": "^1.69.0"
  }
}
```

### 0.3 vite.config.ts

```typescript
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src')
    }
  },
  css: {
    preprocessorOptions: {
      scss: {
        additionalData: `@import "@/assets/styles/variables.scss";`
      }
    }
  },
  build: {
    outDir: '../frontend/static/vue-dist',
    emptyOutDir: true,
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['vue', 'vue-router', 'pinia', 'axios']
        }
      }
    }
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/auth': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  }
})
```

### 0.4 tsconfig.json

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "module": "ESNext",
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "preserve",
    "strict": true,
    "strictNullChecks": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    }
  },
  "include": ["src/**/*.ts", "src/**/*.tsx", "src/**/*.vue", "env.d.ts"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

### Critérios de Sucesso - Fase 0

- [ ] `cd vue-app && npm install` executa sem erros
- [ ] `npm run dev` inicia servidor em localhost:5173
- [ ] `npm run build` gera arquivos em `frontend/static/vue-dist/`
- [ ] `npm run type-check` passa sem erros
- [ ] Sistema Jinja2 continua funcionando normalmente

**Rollback:** `rm -rf vue-app/`

---

## Fase 1: Infraestrutura Core

**Objetivo:** Criar fundação reutilizável (API, types, stores, components)

**Duração estimada:** 3-5 dias

### 1.1 Cliente API Tipado

**Arquivo:** `src/api/client.ts`

```typescript
import axios, { AxiosError, type AxiosInstance } from 'axios'

export interface ApiError {
  message: string
  code?: string
  details?: Record<string, string[]>
}

const apiClient: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// Request interceptor - adiciona token
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Response interceptor - trata erros
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiError>) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('access_token')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export default apiClient
```

### 1.2 Tipos TypeScript Completos

**Arquivo:** `src/types/index.ts`

```typescript
// ========================================
// AUTENTICAÇÃO
// ========================================
export interface Usuario {
  id: number
  username: string
  nome_completo: string
  email: string
  ativo: boolean
  papel: 'admin' | 'procurador' | 'estagiario'
  data_criacao: string
  ultimo_acesso?: string
}

export interface LoginRequest {
  username: string
  password: string
}

export interface LoginResponse {
  access_token: string
  token_type: string
}

// ========================================
// PROCESSOS
// ========================================
export interface Processo {
  numero_processo: string
  numero_formatado: string
  classe: string
  classe_codigo: number
  assunto: string
  assunto_codigo: number
  comarca: string
  vara: string
  data_ajuizamento: string
  valor_causa: string
  situacao: string
  polo_ativo: Parte[]
  polo_passivo: Parte[]
  movimentacoes?: Movimentacao[]
}

export interface Parte {
  nome: string
  documento?: string
  tipo_pessoa: 'fisica' | 'juridica'
  tipo_parte: string
  assistencia_judiciaria?: boolean
  advogados?: Advogado[]
}

export interface Advogado {
  nome: string
  oab: string
}

export interface Movimentacao {
  data: string
  descricao: string
  complemento?: string
}

// ========================================
// GERADOR DE PEÇAS
// ========================================
export interface TipoPeca {
  id: number
  nome: string
  descricao: string
  categoria: string
  ativo: boolean
  ordem: number
}

export interface PromptModulo {
  id: number
  titulo: string
  descricao: string
  conteudo: string
  modo_ativacao: 'llm' | 'deterministic' | 'always'
  regra_deterministica?: string
  regra_secundaria?: string
  fallback_habilitado: boolean
  ativo: boolean
  ordem: number
  tipo_peca_id: number
}

export interface ExtractionVariable {
  id: number
  slug: string
  label: string
  tipo: 'text' | 'number' | 'boolean' | 'date' | 'list'
  descricao: string
  exemplo?: string
  obrigatoria: boolean
  ativa: boolean
}

export interface GrupoPerguntas {
  id: number
  nome: string
  descricao: string
  ordem: number
  variaveis: ExtractionVariable[]
}

export interface Subcategoria {
  id: number
  nome: string
  descricao: string
  tipo_peca_id: number
}

// ========================================
// RESULTADO DA PEÇA
// ========================================
export interface ResultadoPeca {
  id: string
  numero_processo: string
  tipo_peca: string
  conteudo: string
  conteudo_html: string
  modulos_utilizados: string[]
  variaveis_extraidas: Record<string, any>
  tempo_processamento: number
  data_geracao: string
}

// ========================================
// RESPOSTAS API
// ========================================
export interface ApiResponse<T> {
  success: boolean
  data?: T
  message?: string
  error?: string
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  per_page: number
  pages: number
  has_next: boolean
  has_prev: boolean
}

// ========================================
// HISTÓRICO
// ========================================
export interface HistoricoItem {
  id: string
  numero_processo: string
  tipo_peca: string
  usuario: string
  data_geracao: string
  tempo_processamento: number
  status: 'sucesso' | 'erro' | 'parcial'
}

// ========================================
// RELATÓRIOS
// ========================================
export interface EstatisticasGerais {
  total_pecas_geradas: number
  pecas_hoje: number
  pecas_semana: number
  tempo_medio_geracao: number
  tipos_mais_usados: { tipo: string; count: number }[]
  usuarios_mais_ativos: { usuario: string; count: number }[]
}
```

### 1.3 Stores Pinia

**Arquivo:** `src/stores/auth.ts`

```typescript
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import apiClient from '@/api/client'
import type { Usuario, LoginRequest, LoginResponse } from '@/types'

export const useAuthStore = defineStore('auth', () => {
  // State
  const user = ref<Usuario | null>(null)
  const token = ref<string | null>(localStorage.getItem('access_token'))
  const loading = ref(false)

  // Getters
  const isAuthenticated = computed(() => !!token.value && !!user.value)
  const isAdmin = computed(() => user.value?.papel === 'admin')
  const isProcurador = computed(() => user.value?.papel === 'procurador')

  // Actions
  async function login(credentials: LoginRequest): Promise<boolean> {
    loading.value = true
    try {
      const formData = new URLSearchParams()
      formData.append('username', credentials.username)
      formData.append('password', credentials.password)

      const { data } = await apiClient.post<LoginResponse>('/auth/login', formData, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
      })

      token.value = data.access_token
      localStorage.setItem('access_token', data.access_token)

      await fetchUser()
      return true
    } catch (error) {
      console.error('Login failed:', error)
      return false
    } finally {
      loading.value = false
    }
  }

  async function fetchUser(): Promise<void> {
    if (!token.value) return

    try {
      const { data } = await apiClient.get<Usuario>('/auth/me')
      user.value = data
    } catch (error) {
      logout()
    }
  }

  function logout(): void {
    user.value = null
    token.value = null
    localStorage.removeItem('access_token')
  }

  // Inicialização
  if (token.value) {
    fetchUser()
  }

  return {
    user,
    token,
    loading,
    isAuthenticated,
    isAdmin,
    isProcurador,
    login,
    logout,
    fetchUser
  }
})
```

**Arquivo:** `src/stores/ui.ts`

```typescript
import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface Toast {
  id: string
  type: 'success' | 'error' | 'warning' | 'info'
  message: string
  duration?: number
}

export const useUiStore = defineStore('ui', () => {
  const sidebarCollapsed = ref(false)
  const toasts = ref<Toast[]>([])
  const globalLoading = ref(false)

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  function showToast(toast: Omit<Toast, 'id'>) {
    const id = Date.now().toString()
    toasts.value.push({ ...toast, id })

    setTimeout(() => {
      removeToast(id)
    }, toast.duration || 5000)
  }

  function removeToast(id: string) {
    toasts.value = toasts.value.filter(t => t.id !== id)
  }

  function setLoading(value: boolean) {
    globalLoading.value = value
  }

  return {
    sidebarCollapsed,
    toasts,
    globalLoading,
    toggleSidebar,
    showToast,
    removeToast,
    setLoading
  }
})
```

### 1.4 Componentes UI Base

**Diretório:** `src/components/ui/`

| Componente | Descrição | Props Principais |
|------------|-----------|------------------|
| `BaseButton.vue` | Botão estilizado | variant, size, loading, disabled |
| `BaseInput.vue` | Input com label/erro | label, error, type, modelValue |
| `BaseSelect.vue` | Select dropdown | options, modelValue, placeholder |
| `BaseTextarea.vue` | Textarea | label, rows, modelValue |
| `BaseModal.vue` | Modal dialog | show, title, size |
| `BaseTable.vue` | Tabela com sort/pagination | columns, data, loading |
| `BaseCard.vue` | Card container | title, subtitle |
| `BaseAlert.vue` | Alertas | type, dismissible |
| `BaseSpinner.vue` | Loading spinner | size |
| `BaseBadge.vue` | Badge/tag | variant |
| `BaseDropdown.vue` | Dropdown menu | items |
| `BasePagination.vue` | Paginação | total, perPage, currentPage |
| `BaseConfirmDialog.vue` | Dialog de confirmação | title, message, onConfirm |
| `BaseEmptyState.vue` | Estado vazio | icon, message, action |
| `BaseToast.vue` | Toast notifications | - |

### 1.5 Componentes de Layout

**Diretório:** `src/components/layout/`

| Componente | Descrição |
|------------|-----------|
| `AppHeader.vue` | Header com logo, user menu |
| `AppSidebar.vue` | Menu lateral colapsável |
| `AppFooter.vue` | Footer |
| `AppBreadcrumb.vue` | Breadcrumb navigation |
| `MainLayout.vue` | Layout principal (header + sidebar + content) |
| `AuthLayout.vue` | Layout para login (sem sidebar) |

### Critérios de Sucesso - Fase 1

- [ ] Todos os tipos compilam sem erros
- [ ] Store de auth faz login/logout
- [ ] Todos os componentes UI renderizam
- [ ] Layouts funcionam com conteúdo de teste
- [ ] Cobertura de testes > 80% para stores

**Rollback:** Não afeta sistema existente

---

## Fase 2: Integração FastAPI

**Objetivo:** Configurar coexistência Vue + Jinja2

**Duração estimada:** 1-2 dias

### 2.1 Atualizar main.py

**Adicionar ao final de `main.py`:**

```python
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse

# ========================================
# INTEGRAÇÃO VUE.JS
# ========================================

VUE_DIST_DIR = Path(__file__).parent / "frontend" / "static" / "vue-dist"

# Servir assets Vue
if VUE_DIST_DIR.exists():
    app.mount(
        "/vue-assets",
        StaticFiles(directory=VUE_DIST_DIR / "assets"),
        name="vue-assets"
    )

# Template wrapper para Vue (permite usar header/footer Jinja2)
@app.get("/app/{path:path}", response_class=HTMLResponse)
async def serve_vue_app(request: Request, path: str = ""):
    """
    Serve Vue SPA para todas as rotas /app/*
    Usa template Jinja2 como wrapper para manter header/footer consistentes
    """
    vue_index = VUE_DIST_DIR / "index.html"

    if not vue_index.exists():
        # Fallback: redireciona para página de erro
        return templates.TemplateResponse(
            "erro_404.html",
            {"request": request, "mensagem": "Vue app não buildado"}
        )

    # Lê o HTML do Vue e injeta no template wrapper
    vue_html = vue_index.read_text(encoding="utf-8")

    return templates.TemplateResponse(
        "vue_wrapper.html",
        {
            "request": request,
            "vue_content": vue_html,
            "current_user": getattr(request.state, "user", None)
        }
    )
```

### 2.2 Criar template wrapper

**Arquivo:** `frontend/templates/vue_wrapper.html`

```html
{% extends "base.html" %}

{% block title %}Portal PGE{% endblock %}

{% block head_extra %}
<!-- Vue app styles são injetados automaticamente -->
{% endblock %}

{% block content %}
<!-- Vue mount point -->
<div id="app"></div>

<!-- Scripts Vue -->
<script type="module" src="/vue-assets/index.js"></script>
{% endblock %}

{% block scripts_extra %}
<!-- Scripts adicionais se necessário -->
{% endblock %}
```

### 2.3 Configurar Vue Router

**Arquivo:** `src/router/index.ts`

```typescript
import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

// Lazy loading de views
const routes: RouteRecordRaw[] = [
  // ========================================
  // ROTAS PÚBLICAS
  // ========================================
  {
    path: '/',
    name: 'home',
    component: () => import('@/views/HomeView.vue'),
    meta: { requiresAuth: true }
  },

  // ========================================
  // ROTAS DE ADMIN
  // ========================================
  {
    path: '/admin',
    meta: { requiresAuth: true, requiresAdmin: true },
    children: [
      {
        path: 'variaveis',
        name: 'admin-variaveis',
        component: () => import('@/views/admin/VariaveisView.vue')
      },
      {
        path: 'modulos',
        name: 'admin-modulos',
        component: () => import('@/views/admin/ModulosView.vue')
      },
      {
        path: 'tipos-peca',
        name: 'admin-tipos-peca',
        component: () => import('@/views/admin/TiposPecaView.vue')
      },
      {
        path: 'usuarios',
        name: 'admin-usuarios',
        component: () => import('@/views/admin/UsuariosView.vue')
      },
      {
        path: 'grupos',
        name: 'admin-grupos',
        component: () => import('@/views/admin/GruposView.vue')
      },
      {
        path: 'subcategorias',
        name: 'admin-subcategorias',
        component: () => import('@/views/admin/SubcategoriasView.vue')
      }
    ]
  },

  // ========================================
  // ROTAS DE PROCESSOS
  // ========================================
  {
    path: '/processos',
    meta: { requiresAuth: true },
    children: [
      {
        path: 'consulta',
        name: 'consulta-processo',
        component: () => import('@/views/processos/ConsultaView.vue')
      },
      {
        path: ':numero',
        name: 'detalhes-processo',
        component: () => import('@/views/processos/DetalhesView.vue')
      }
    ]
  },

  // ========================================
  // ROTAS DE PEÇAS
  // ========================================
  {
    path: '/pecas',
    meta: { requiresAuth: true },
    children: [
      {
        path: 'gerar',
        name: 'gerar-peca',
        component: () => import('@/views/pecas/GerarPecaView.vue')
      },
      {
        path: 'resultado/:id',
        name: 'resultado-peca',
        component: () => import('@/views/pecas/ResultadoView.vue')
      },
      {
        path: 'historico',
        name: 'historico',
        component: () => import('@/views/pecas/HistoricoView.vue')
      }
    ]
  },

  // ========================================
  // OUTRAS ROTAS
  // ========================================
  {
    path: '/perfil',
    name: 'perfil',
    component: () => import('@/views/PerfilView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/relatorios',
    name: 'relatorios',
    component: () => import('@/views/RelatoriosView.vue'),
    meta: { requiresAuth: true, requiresAdmin: true }
  },

  // ========================================
  // CATCH-ALL
  // ========================================
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/views/NotFoundView.vue')
  }
]

const router = createRouter({
  history: createWebHistory('/app'),
  routes,
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) return savedPosition
    return { top: 0 }
  }
})

// Navigation guards
router.beforeEach(async (to, from, next) => {
  const authStore = useAuthStore()

  // Aguarda carregar usuário se tem token
  if (authStore.token && !authStore.user) {
    await authStore.fetchUser()
  }

  // Verifica autenticação
  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    // Redireciona para login Jinja2 (ainda não migrado)
    window.location.href = `/login?next=${encodeURIComponent('/app' + to.fullPath)}`
    return
  }

  // Verifica permissão admin
  if (to.meta.requiresAdmin && !authStore.isAdmin) {
    next({ name: 'home' })
    return
  }

  next()
})

export default router
```

### 2.4 Main entry point

**Arquivo:** `src/main.ts`

```typescript
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'

// Styles
import './assets/styles/global.scss'

const app = createApp(App)

app.use(createPinia())
app.use(router)

app.mount('#app')
```

### Critérios de Sucesso - Fase 2

- [ ] `/app/` serve Vue app
- [ ] Rotas Jinja2 (`/login`, `/admin/*`) continuam funcionando
- [ ] Navegação Vue funciona
- [ ] Auth integrada com login existente

**Rollback:** Remover código de `main.py` e `vue_wrapper.html`

---

## Fase 3: Migração - Admin (Primeiro Grupo)

**Objetivo:** Migrar páginas administrativas de alta complexidade

**Duração estimada:** 1-2 semanas

### 3.1 Admin Variáveis

**View:** `src/views/admin/VariaveisView.vue`

**API Service:** `src/api/variaveis.ts`

```typescript
import apiClient from './client'
import type { ExtractionVariable, ApiResponse, PaginatedResponse } from '@/types'

export const variaveisApi = {
  listar: (params?: { page?: number; search?: string }) =>
    apiClient.get<PaginatedResponse<ExtractionVariable>>('/admin/variaveis', { params }),

  buscar: (slug: string) =>
    apiClient.get<ExtractionVariable>(`/admin/variaveis/${slug}`),

  criar: (data: Partial<ExtractionVariable>) =>
    apiClient.post<ExtractionVariable>('/admin/variaveis', data),

  atualizar: (slug: string, data: Partial<ExtractionVariable>) =>
    apiClient.put<ExtractionVariable>(`/admin/variaveis/${slug}`, data),

  excluir: (slug: string) =>
    apiClient.delete(`/admin/variaveis/${slug}`)
}
```

**Funcionalidades:**
- [ ] Listagem com paginação
- [ ] Filtro por tipo/busca
- [ ] Criar variável (modal)
- [ ] Editar variável (modal)
- [ ] Excluir com confirmação
- [ ] Validação de formulário
- [ ] Toast de feedback

### 3.2 Admin Módulos

**View:** `src/views/admin/ModulosView.vue`

**Funcionalidades:**
- [ ] Listagem por tipo de peça
- [ ] CRUD completo
- [ ] Editor de conteúdo (markdown)
- [ ] Configurar regras determinísticas
- [ ] Reordenar (drag & drop)
- [ ] Preview do módulo

### 3.3 Admin Tipos de Peça

**View:** `src/views/admin/TiposPecaView.vue`

**Funcionalidades:**
- [ ] CRUD tipos de peça
- [ ] Associar módulos
- [ ] Configurar categoria
- [ ] Ativar/desativar

### Critérios de Sucesso - Fase 3

- [ ] Todas as funcionalidades CRUD funcionam
- [ ] Validação de formulários
- [ ] Feedback visual (toasts)
- [ ] Páginas Jinja2 originais ainda acessíveis
- [ ] Testes E2E passam

**Rollback:** Páginas Jinja2 permanecem funcionais

---

## Fase 4: Migração - Páginas Simples

**Objetivo:** Migrar páginas de baixa/média complexidade

**Duração estimada:** 1 semana

### 4.1 Login

**View:** `src/views/auth/LoginView.vue`

**Funcionalidades:**
- [ ] Formulário de login
- [ ] Validação
- [ ] Mensagens de erro
- [ ] Redirect após login
- [ ] "Lembrar-me" (opcional)

**Nota:** Esta view será servida diretamente (não via wrapper)

### 4.2 Home/Dashboard

**View:** `src/views/HomeView.vue`

**Funcionalidades:**
- [ ] Estatísticas resumidas
- [ ] Atalhos rápidos
- [ ] Últimas peças geradas
- [ ] Gráficos (opcional)

### 4.3 Consulta de Processo

**View:** `src/views/processos/ConsultaView.vue`

**Funcionalidades:**
- [ ] Campo de busca (número CNJ)
- [ ] Validação de formato
- [ ] Exibição de resultados
- [ ] Loading state
- [ ] Tratamento de erros

### 4.4 Perfil do Usuário

**View:** `src/views/PerfilView.vue`

**Funcionalidades:**
- [ ] Exibir dados do usuário
- [ ] Alterar senha
- [ ] Preferências (opcional)

### Critérios de Sucesso - Fase 4

- [ ] Login funciona e redireciona corretamente
- [ ] Dashboard exibe dados reais
- [ ] Consulta de processo funciona
- [ ] Perfil permite alterar senha

---

## Fase 5: Migração - Admin (Segundo Grupo)

**Objetivo:** Migrar páginas administrativas restantes

**Duração estimada:** 1 semana

### 5.1 Admin Usuários

**Funcionalidades:**
- [ ] Listagem com filtros
- [ ] CRUD usuários
- [ ] Alterar papel/permissões
- [ ] Ativar/desativar
- [ ] Resetar senha

### 5.2 Admin Grupos

**Funcionalidades:**
- [ ] CRUD grupos de perguntas
- [ ] Associar variáveis
- [ ] Reordenar

### 5.3 Admin Subcategorias

**Funcionalidades:**
- [ ] CRUD subcategorias
- [ ] Associar a tipos de peça

### 5.4 Histórico

**Funcionalidades:**
- [ ] Listagem com filtros
- [ ] Paginação
- [ ] Detalhes de cada geração
- [ ] Reprocessar (opcional)

### 5.5 Relatórios

**Funcionalidades:**
- [ ] Estatísticas gerais
- [ ] Gráficos por período
- [ ] Exportar dados

### Critérios de Sucesso - Fase 5

- [ ] Todas as páginas admin migradas
- [ ] Funcionalidades equivalentes ao Jinja2
- [ ] Performance aceitável

---

## Fase 6: Migração - Gerador de Peças (Complexo)

**Objetivo:** Migrar fluxo mais complexo do sistema

**Duração estimada:** 2 semanas

### 6.1 Formulário de Geração

**View:** `src/views/pecas/GerarPecaView.vue`

**Funcionalidades:**
- [ ] Seleção de tipo de peça
- [ ] Upload de arquivos (múltiplos)
- [ ] Seleção de subcategoria
- [ ] Número do processo
- [ ] Preview de arquivos
- [ ] Validação completa

### 6.2 Acompanhamento em Tempo Real

**View:** `src/views/pecas/ProcessamentoView.vue`

**Funcionalidades:**
- [ ] Progress bar
- [ ] Status de cada etapa (Agente 1, 2, 3)
- [ ] Logs em tempo real (SSE ou polling)
- [ ] Cancelar processamento
- [ ] Tratamento de erros

### 6.3 Resultado da Peça

**View:** `src/views/pecas/ResultadoView.vue`

**Funcionalidades:**
- [ ] Visualização do conteúdo
- [ ] Módulos utilizados
- [ ] Variáveis extraídas
- [ ] Edição inline (opcional)
- [ ] Download DOCX
- [ ] Copiar texto
- [ ] Refazer com ajustes

### Critérios de Sucesso - Fase 6

- [ ] Fluxo completo de geração funciona
- [ ] Upload de múltiplos arquivos
- [ ] Progresso em tempo real
- [ ] Download DOCX funciona
- [ ] Performance equivalente ou melhor

---

## Fase 7: Finalização e Limpeza

**Objetivo:** Remover Jinja2, consolidar Vue

**Duração estimada:** 1 semana

### 7.1 Migrar páginas restantes

- [ ] Páginas de erro (404, 500, etc.)
- [ ] Partials → componentes Vue

### 7.2 Remover dependência de Jinja2

**Modificar `main.py`:**
- [ ] Remover `Jinja2Templates`
- [ ] Remover rotas Jinja2
- [ ] Manter apenas rotas `/api/*`

### 7.3 Atualizar deploy

- [ ] Build Vue no CI/CD
- [ ] Servir Vue como SPA
- [ ] Configurar fallback para SPA routing

### 7.4 Limpeza

- [ ] Remover `frontend/templates/`
- [ ] Remover JS inline
- [ ] Remover `security.js`
- [ ] Atualizar documentação

### Critérios de Sucesso - Fase 7

- [ ] 100% do frontend é Vue
- [ ] Nenhum template Jinja2 restante
- [ ] Sistema funcionando em produção
- [ ] Testes E2E passando

---

## Fase 8: Otimização e Polish

**Objetivo:** Melhorias de performance e UX

**Duração estimada:** Contínuo

### 8.1 Performance

- [ ] Code splitting otimizado
- [ ] Lazy loading de rotas
- [ ] Cache de API (Vue Query ou similar)
- [ ] Service Worker (PWA)
- [ ] Otimização de bundle size

### 8.2 UX Melhorias

- [ ] Animações/transições
- [ ] Keyboard shortcuts
- [ ] Dark mode
- [ ] Responsividade mobile
- [ ] Acessibilidade (WCAG)

### 8.3 DX (Developer Experience)

- [ ] Storybook para componentes
- [ ] Documentação de componentes
- [ ] Guia de estilo

---

## Cronograma Resumido

| Fase | Descrição | Duração | Dependências |
|------|-----------|---------|--------------|
| 0 | Preparação | 1-2 dias | - |
| 1 | Infraestrutura | 3-5 dias | Fase 0 |
| 2 | Integração FastAPI | 1-2 dias | Fase 1 |
| 3 | Admin (grupo 1) | 1-2 semanas | Fase 2 |
| 4 | Páginas simples | 1 semana | Fase 2 |
| 5 | Admin (grupo 2) | 1 semana | Fase 3 |
| 6 | Gerador de Peças | 2 semanas | Fase 4, 5 |
| 7 | Finalização | 1 semana | Fase 6 |
| 8 | Otimização | Contínuo | Fase 7 |

**Total estimado:** 6-10 semanas

---

## Comandos de Referência

```bash
# Desenvolvimento
cd vue-app
npm install                    # Instalar dependências
npm run dev                    # Dev server (localhost:5173)
npm run build                  # Build produção
npm run preview                # Preview build local
npm run test                   # Rodar testes
npm run test:coverage          # Testes com coverage
npm run lint                   # ESLint
npm run type-check             # Verificar tipos

# Backend (terminal separado)
cd ..
python -m uvicorn main:app --reload --port 8000
```

---

## Checklist de Validação Final

### Funcionalidade
- [ ] Todas as features do Jinja2 replicadas
- [ ] Nenhuma regressão de funcionalidade
- [ ] Fluxos críticos testados

### Performance
- [ ] TTI (Time to Interactive) < 3s
- [ ] Bundle size < 500KB gzipped
- [ ] Lighthouse score > 80

### Qualidade
- [ ] Cobertura de testes > 70%
- [ ] Sem erros de TypeScript
- [ ] ESLint sem warnings
- [ ] Sem console.logs em produção

### Segurança
- [ ] XSS prevenido (sanitização)
- [ ] CSRF tokens se necessário
- [ ] Tokens armazenados de forma segura

---

## Histórico de Execução

| Data | Fase | Status | Notas |
|------|------|--------|-------|
| - | 0.1 | Pendente | |
| - | 0.2 | Pendente | |
| - | 0.3 | Pendente | |
| - | 0.4 | Pendente | |
| - | 1.1 | Pendente | |
| - | 1.2 | Pendente | |
| - | 1.3 | Pendente | |
| - | 1.4 | Pendente | |
| - | 1.5 | Pendente | |
| - | 2.1 | Pendente | |
| - | 2.2 | Pendente | |
| - | 2.3 | Pendente | |
| - | 2.4 | Pendente | |
| - | 3.1 | Pendente | |
| - | 3.2 | Pendente | |
| - | 3.3 | Pendente | |
| - | 4.1 | Pendente | |
| - | 4.2 | Pendente | |
| - | 4.3 | Pendente | |
| - | 4.4 | Pendente | |
| - | 5.1 | Pendente | |
| - | 5.2 | Pendente | |
| - | 5.3 | Pendente | |
| - | 5.4 | Pendente | |
| - | 5.5 | Pendente | |
| - | 6.1 | Pendente | |
| - | 6.2 | Pendente | |
| - | 6.3 | Pendente | |
| - | 7.1 | Pendente | |
| - | 7.2 | Pendente | |
| - | 7.3 | Pendente | |
| - | 7.4 | Pendente | |
| - | 8.1 | Pendente | |
| - | 8.2 | Pendente | |
| - | 8.3 | Pendente | |
