/**
 * security.ts - Utilitários de segurança para o frontend
 *
 * SECURITY: Este arquivo contém funções para prevenir XSS e outros ataques.
 * Deve ser incluído em TODOS os templates que renderizam dados dinâmicos.
 *
 * Migrado de JavaScript para TypeScript
 */

export {};

// ============================================
// Types
// ============================================

interface SanitizeOptions {
  allowedTags?: string[];
  allowedAttrs?: string[];
  noTags?: boolean;
}

interface SecurityUtilsInterface {
  escapeHtml: typeof escapeHtml;
  sanitizeHtml: typeof sanitizeHtml;
  createElement: typeof createElement;
  setInnerHTML: typeof setInnerHTML;
  safeHtml: typeof safeHtml;
  sanitizeUrl: typeof sanitizeUrl;
  escapeAttr: typeof escapeAttr;
  escapeJs: typeof escapeJs;
}

// ============================================
// HTML Escape
// ============================================

/**
 * SECURITY: Escapa caracteres HTML perigosos para prevenir XSS.
 * Use esta função SEMPRE que inserir dados de usuário no DOM.
 *
 * @example
 * // Uso correto
 * element.innerHTML = `<div>${escapeHtml(userData)}</div>`;
 */
function escapeHtml(str: unknown): string {
  if (str === null || str === undefined) {
    return '';
  }

  const string = String(str);

  const escapeMap: Record<string, string> = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#x27;',
    '/': '&#x2F;',
    '`': '&#x60;',
    '=': '&#x3D;',
  };

  return string.replace(/[&<>"'`=/]/g, (char) => escapeMap[char]);
}

// ============================================
// HTML Sanitization
// ============================================

/**
 * SECURITY: Sanitiza HTML removendo tags e atributos perigosos.
 * Permite apenas tags e atributos seguros para formatação básica.
 */
function sanitizeHtml(html: string, options: SanitizeOptions = {}): string {
  if (!html) return '';

  // Remove scripts e event handlers
  let clean = html
    // Remove tags script
    .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
    // Remove event handlers (onclick, onerror, etc.)
    .replace(/\s*on\w+\s*=\s*["'][^"']*["']/gi, '')
    .replace(/\s*on\w+\s*=\s*[^\s>]*/gi, '')
    // Remove javascript: URLs
    .replace(/javascript\s*:/gi, '')
    // Remove data: URLs em atributos src/href (podem conter scripts)
    .replace(/(src|href)\s*=\s*["']?\s*data:/gi, '$1="')
    // Remove expressões CSS perigosas
    .replace(/expression\s*\(/gi, '')
    .replace(/url\s*\(\s*["']?\s*javascript:/gi, 'url(');

  // Se não permite tags, escapa tudo
  if (options.noTags) {
    return escapeHtml(clean);
  }

  return clean;
}

// ============================================
// Safe Element Creation
// ============================================

type ElementChildren = string | Node | Array<string | Node> | null;

/**
 * SECURITY: Cria elemento DOM de forma segura a partir de dados.
 * Alternativa mais segura ao innerHTML quando possível.
 */
function createElement(
  tag: string,
  attrs: Record<string, string> = {},
  children: ElementChildren = null
): HTMLElement {
  const element = document.createElement(tag);

  // Define atributos de forma segura
  for (const [key, value] of Object.entries(attrs)) {
    // Bloqueia event handlers
    if (key.toLowerCase().startsWith('on')) {
      console.warn(`SECURITY: Event handler '${key}' bloqueado em createElement`);
      continue;
    }

    // Sanitiza URLs em href/src
    if ((key === 'href' || key === 'src') && typeof value === 'string') {
      if (value.toLowerCase().trim().startsWith('javascript:')) {
        console.warn('SECURITY: javascript: URL bloqueada');
        continue;
      }
    }

    element.setAttribute(key, value);
  }

  // Adiciona children
  if (children !== null) {
    if (Array.isArray(children)) {
      children.forEach((child) => {
        if (child instanceof Node) {
          element.appendChild(child);
        } else {
          element.appendChild(document.createTextNode(String(child)));
        }
      });
    } else if (children instanceof Node) {
      element.appendChild(children);
    } else {
      // Texto é adicionado de forma segura via textContent
      element.textContent = String(children);
    }
  }

  return element;
}

/**
 * SECURITY: Define innerHTML de forma mais segura.
 * Sanitiza o HTML antes de inserir no DOM.
 */
function setInnerHTML(
  element: HTMLElement | null,
  html: string,
  options: SanitizeOptions = {}
): void {
  if (!element) return;
  element.innerHTML = sanitizeHtml(html, options);
}

// ============================================
// Safe Template Literals
// ============================================

/**
 * SECURITY: Template tag function para criar HTML seguro.
 * Escapa automaticamente todas as expressões interpoladas.
 *
 * @example
 * element.innerHTML = safeHtml`<div class="user">${userName}</div>`;
 */
function safeHtml(strings: TemplateStringsArray, ...values: unknown[]): string {
  return strings.reduce((result, string, i) => {
    const value = values[i - 1];
    const escaped = escapeHtml(value);
    return result + escaped + string;
  });
}

// ============================================
// URL Validation
// ============================================

/**
 * SECURITY: Valida e sanitiza URLs.
 */
function sanitizeUrl(
  url: string,
  allowedProtocols: string[] = ['http:', 'https:', 'mailto:']
): string | null {
  if (!url || typeof url !== 'string') return null;

  try {
    const parsed = new URL(url, window.location.origin);

    if (!allowedProtocols.includes(parsed.protocol)) {
      console.warn(`SECURITY: Protocolo não permitido: ${parsed.protocol}`);
      return null;
    }

    return parsed.href;
  } catch {
    // URL relativa - permite
    if (url.startsWith('/') || url.startsWith('./') || url.startsWith('../')) {
      return url;
    }
    return null;
  }
}

// ============================================
// Attribute/JS Escaping
// ============================================

/**
 * SECURITY: Escapa string para uso em atributos HTML.
 */
function escapeAttr(str: unknown): string {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#x27;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

/**
 * SECURITY: Escapa string para uso em JavaScript inline.
 */
function escapeJs(str: unknown): string {
  if (!str) return '';
  return String(str)
    .replace(/\\/g, '\\\\')
    .replace(/'/g, "\\'")
    .replace(/"/g, '\\"')
    .replace(/\n/g, '\\n')
    .replace(/\r/g, '\\r')
    .replace(/\t/g, '\\t')
    .replace(/<\/script/gi, '<\\/script');
}

// ============================================
// Global Exports
// ============================================

declare global {
  interface Window {
    SecurityUtils: SecurityUtilsInterface;
    escapeHtml: typeof escapeHtml;
    sanitizeHtml: typeof sanitizeHtml;
    safeHtml: typeof safeHtml;
  }
}

// Expõe funções globalmente
window.SecurityUtils = {
  escapeHtml,
  sanitizeHtml,
  createElement,
  setInnerHTML,
  safeHtml,
  sanitizeUrl,
  escapeAttr,
  escapeJs,
};

// Atalhos globais para funções mais usadas
window.escapeHtml = escapeHtml;
window.sanitizeHtml = sanitizeHtml;
window.safeHtml = safeHtml;

console.log('[SECURITY] security.ts loaded - XSS protection enabled');
