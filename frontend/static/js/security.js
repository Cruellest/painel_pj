// Generated from TypeScript - DO NOT EDIT DIRECTLY
// Source: src\shared\security.ts
// Built at: 2026-01-28T13:55:56.202Z

"use strict";
(() => {
  // src/shared/security.ts
  function escapeHtml(str) {
    if (str === null || str === void 0) {
      return "";
    }
    const string = String(str);
    const escapeMap = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#x27;",
      "/": "&#x2F;",
      "`": "&#x60;",
      "=": "&#x3D;"
    };
    return string.replace(/[&<>"'`=/]/g, (char) => escapeMap[char]);
  }
  function sanitizeHtml(html, options = {}) {
    if (!html) return "";
    let clean = html.replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, "").replace(/\s*on\w+\s*=\s*["'][^"']*["']/gi, "").replace(/\s*on\w+\s*=\s*[^\s>]*/gi, "").replace(/javascript\s*:/gi, "").replace(/(src|href)\s*=\s*["']?\s*data:/gi, '$1="').replace(/expression\s*\(/gi, "").replace(/url\s*\(\s*["']?\s*javascript:/gi, "url(");
    if (options.noTags) {
      return escapeHtml(clean);
    }
    return clean;
  }
  function createElement(tag, attrs = {}, children = null) {
    const element = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
      if (key.toLowerCase().startsWith("on")) {
        console.warn(`SECURITY: Event handler '${key}' bloqueado em createElement`);
        continue;
      }
      if ((key === "href" || key === "src") && typeof value === "string") {
        if (value.toLowerCase().trim().startsWith("javascript:")) {
          console.warn("SECURITY: javascript: URL bloqueada");
          continue;
        }
      }
      element.setAttribute(key, value);
    }
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
        element.textContent = String(children);
      }
    }
    return element;
  }
  function setInnerHTML(element, html, options = {}) {
    if (!element) return;
    element.innerHTML = sanitizeHtml(html, options);
  }
  function safeHtml(strings, ...values) {
    return strings.reduce((result, string, i) => {
      const value = values[i - 1];
      const escaped = escapeHtml(value);
      return result + escaped + string;
    });
  }
  function sanitizeUrl(url, allowedProtocols = ["http:", "https:", "mailto:"]) {
    if (!url || typeof url !== "string") return null;
    try {
      const parsed = new URL(url, window.location.origin);
      if (!allowedProtocols.includes(parsed.protocol)) {
        console.warn(`SECURITY: Protocolo n\xE3o permitido: ${parsed.protocol}`);
        return null;
      }
      return parsed.href;
    } catch {
      if (url.startsWith("/") || url.startsWith("./") || url.startsWith("../")) {
        return url;
      }
      return null;
    }
  }
  function escapeAttr(str) {
    if (!str) return "";
    return String(str).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/'/g, "&#x27;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  function escapeJs(str) {
    if (!str) return "";
    return String(str).replace(/\\/g, "\\\\").replace(/'/g, "\\'").replace(/"/g, '\\"').replace(/\n/g, "\\n").replace(/\r/g, "\\r").replace(/\t/g, "\\t").replace(/<\/script/gi, "<\\/script");
  }
  window.SecurityUtils = {
    escapeHtml,
    sanitizeHtml,
    createElement,
    setInnerHTML,
    safeHtml,
    sanitizeUrl,
    escapeAttr,
    escapeJs
  };
  window.escapeHtml = escapeHtml;
  window.sanitizeHtml = sanitizeHtml;
  window.safeHtml = safeHtml;
  console.log("[SECURITY] security.ts loaded - XSS protection enabled");
})();
//# sourceMappingURL=security.js.map
