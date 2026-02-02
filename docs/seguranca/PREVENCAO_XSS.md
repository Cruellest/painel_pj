# Prevencao XSS - Portal PGE-MS

Documentacao das medidas de protecao contra Cross-Site Scripting (XSS).

## 1. Protecoes Implementadas

### 1.1 Backend (Jinja2)

O Jinja2 ja faz escape automatico de variaveis por padrao:

```html
<!-- Seguro: escape automatico -->
{{ user.name }}

<!-- PERIGOSO: nao usar |safe com dados de usuario -->
{{ user_input|safe }}
```

**REGRA**: Nunca use `|safe` com dados que vem de usuarios.

### 1.2 Frontend (security.ts)

Biblioteca centralizada em `frontend/src/shared/security.ts`:

| Funcao | Uso |
|--------|-----|
| `escapeHtml(str)` | Escapa caracteres HTML perigosos |
| `sanitizeHtml(html)` | Remove scripts e event handlers |
| `createElement(tag, attrs, children)` | Cria elementos DOM de forma segura |
| `setInnerHTML(el, html)` | innerHTML com sanitizacao |
| `safeHtml\`template\`` | Template literal com escape automatico |
| `sanitizeUrl(url)` | Valida URLs (bloqueia javascript:) |
| `escapeAttr(str)` | Para atributos HTML |
| `escapeJs(str)` | Para JavaScript inline |

### 1.3 Uso Correto

```javascript
// CORRETO: usando escapeHtml
element.innerHTML = `<div class="user">${escapeHtml(userData)}</div>`;

// CORRETO: usando textContent (mais seguro ainda)
element.textContent = userData;

// CORRETO: usando safeHtml template tag
element.innerHTML = safeHtml`<div class="user">${userData}</div>`;

// CORRETO: usando createElement
const div = createElement('div', { class: 'user' }, userData);

// PERIGOSO: innerHTML direto com dados de usuario
element.innerHTML = userData;  // NAO FAZER!
```

## 2. Auditoria de Templates

### 2.1 Padroes Verificados

- [x] Nenhum uso de `|safe` com dados de usuario
- [x] `escapeHtml` disponivel em todos os templates que usam innerHTML
- [x] `textContent` usado para texto simples
- [x] URLs validadas antes de inserir em href/src

### 2.2 Templates Auditados

| Template | Status | Notas |
|----------|--------|-------|
| admin_*.html | OK | Usam escapeHtml corretamente |
| dashboard.html | OK | Usa textContent para dados de usuario |
| login.html | OK | Sem dados dinamicos de risco |

## 3. Headers de Seguranca

Configurados em `main.py`:

```python
# Content Security Policy (CSP)
response.headers["Content-Security-Policy"] = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline';"
)

# Previne MIME type sniffing
response.headers["X-Content-Type-Options"] = "nosniff"

# Previne clickjacking
response.headers["X-Frame-Options"] = "DENY"
```

## 4. Checklist para Novos Templates

Ao criar novos templates:

- [ ] Incluir security.js no template
- [ ] Usar `escapeHtml()` para dados de usuario em innerHTML
- [ ] Preferir `textContent` quando possivel
- [ ] Nao usar `|safe` sem justificativa documentada
- [ ] Validar URLs antes de usar em href/src
- [ ] Testar com payloads XSS comuns

## 5. Payloads de Teste

Usar estes payloads para testar formularios:

```html
<script>alert('XSS')</script>
<img src=x onerror="alert('XSS')">
<svg onload="alert('XSS')">
javascript:alert('XSS')
"><script>alert('XSS')</script>
```

Se algum desses executar um alert, ha vulnerabilidade.

## 6. Resposta a Incidentes

Se identificar vulnerabilidade XSS:

1. Corrigir imediatamente usando escapeHtml
2. Verificar logs de acesso por uso malicioso
3. Notificar time de seguranca
4. Documentar e criar teste de regressao

---

**Ultima atualizacao**: Janeiro 2024
**Autor**: LAB/PGE-MS
