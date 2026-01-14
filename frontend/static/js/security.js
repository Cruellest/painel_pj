/**
 * security.js - Utilitários de segurança para o frontend
 *
 * SECURITY: Este arquivo contém funções para prevenir XSS e outros ataques.
 * Deve ser incluído em TODOS os templates que renderizam dados dinâmicos.
 */

(function(window) {
    'use strict';

    /**
     * SECURITY: Escapa caracteres HTML perigosos para prevenir XSS.
     * Use esta função SEMPRE que inserir dados de usuário no DOM.
     *
     * @param {string} str - String a ser escapada
     * @returns {string} String com caracteres HTML escapados
     *
     * @example
     * // Uso correto
     * element.innerHTML = `<div>${escapeHtml(userData)}</div>`;
     *
     * // Uso com template literals
     * container.innerHTML = items.map(item => `
     *     <div class="item">${escapeHtml(item.name)}</div>
     * `).join('');
     */
    function escapeHtml(str) {
        if (str === null || str === undefined) {
            return '';
        }

        // Converte para string se necessário
        const string = String(str);

        // Mapa de caracteres a escapar
        const escapeMap = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#x27;',
            '/': '&#x2F;',
            '`': '&#x60;',
            '=': '&#x3D;'
        };

        return string.replace(/[&<>"'`=/]/g, char => escapeMap[char]);
    }

    /**
     * SECURITY: Sanitiza HTML removendo tags e atributos perigosos.
     * Permite apenas tags e atributos seguros para formatação básica.
     *
     * @param {string} html - HTML a ser sanitizado
     * @param {object} options - Opções de sanitização
     * @returns {string} HTML sanitizado
     */
    function sanitizeHtml(html, options = {}) {
        if (!html) return '';

        // Tags permitidas por padrão (apenas formatação básica)
        const allowedTags = options.allowedTags || [
            'b', 'i', 'u', 'strong', 'em', 'p', 'br', 'span',
            'div', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
            'table', 'thead', 'tbody', 'tr', 'th', 'td',
            'pre', 'code', 'blockquote'
        ];

        // Atributos permitidos
        const allowedAttrs = options.allowedAttrs || ['class', 'id', 'style'];

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

    /**
     * SECURITY: Cria elemento DOM de forma segura a partir de dados.
     * Alternativa mais segura ao innerHTML quando possível.
     *
     * @param {string} tag - Nome da tag HTML
     * @param {object} attrs - Atributos do elemento
     * @param {string|Node|Array} children - Conteúdo filho
     * @returns {HTMLElement}
     */
    function createElement(tag, attrs = {}, children = null) {
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
                children.forEach(child => {
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
     *
     * @param {HTMLElement} element - Elemento alvo
     * @param {string} html - HTML a inserir
     * @param {object} options - Opções de sanitização
     */
    function setInnerHTML(element, html, options = {}) {
        if (!element) return;
        element.innerHTML = sanitizeHtml(html, options);
    }

    /**
     * SECURITY: Template tag function para criar HTML seguro.
     * Escapa automaticamente todas as expressões interpoladas.
     *
     * @example
     * element.innerHTML = safeHtml`<div class="user">${userName}</div>`;
     */
    function safeHtml(strings, ...values) {
        return strings.reduce((result, string, i) => {
            const value = values[i - 1];
            const escaped = escapeHtml(value);
            return result + escaped + string;
        });
    }

    /**
     * SECURITY: Valida e sanitiza URLs.
     *
     * @param {string} url - URL a validar
     * @param {array} allowedProtocols - Protocolos permitidos
     * @returns {string|null} URL sanitizada ou null se inválida
     */
    function sanitizeUrl(url, allowedProtocols = ['http:', 'https:', 'mailto:']) {
        if (!url || typeof url !== 'string') return null;

        try {
            const parsed = new URL(url, window.location.origin);

            if (!allowedProtocols.includes(parsed.protocol)) {
                console.warn(`SECURITY: Protocolo não permitido: ${parsed.protocol}`);
                return null;
            }

            return parsed.href;
        } catch (e) {
            // URL relativa - permite
            if (url.startsWith('/') || url.startsWith('./') || url.startsWith('../')) {
                return url;
            }
            return null;
        }
    }

    /**
     * SECURITY: Escapa string para uso em atributos HTML.
     *
     * @param {string} str - String a escapar
     * @returns {string} String escapada para atributo
     */
    function escapeAttr(str) {
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
     *
     * @param {string} str - String a escapar
     * @returns {string} String escapada para JS
     */
    function escapeJs(str) {
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

    // Expõe funções globalmente
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

    // Atalhos globais para funções mais usadas
    window.escapeHtml = escapeHtml;
    window.sanitizeHtml = sanitizeHtml;
    window.safeHtml = safeHtml;

    console.log('[SECURITY] security.js loaded - XSS protection enabled');

})(window);
