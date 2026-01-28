// Generated from TypeScript - DO NOT EDIT DIRECTLY
// Source: src\sistemas\cumprimento_beta\index.ts
// Built at: 2026-01-28T13:55:56.123Z

"use strict";
(() => {
  // src/sistemas/cumprimento_beta/api.ts
  var API_BASE = "/api/cumprimento-beta";
  var CumprimentoBetaApi = class {
    getToken() {
      return localStorage.getItem("access_token");
    }
    getHeaders() {
      const token = this.getToken();
      return {
        "Content-Type": "application/json",
        ...token ? { Authorization: `Bearer ${token}` } : {}
      };
    }
    async handleResponse(response) {
      if (!response.ok) {
        let error;
        try {
          error = await response.json();
        } catch {
          error = { detail: `Erro ${response.status}: ${response.statusText}` };
        }
        throw new Error(error.detail);
      }
      return response.json();
    }
    // ==========================================
    // Auth
    // ==========================================
    async checkAccess() {
      const response = await fetch(`${API_BASE}/acesso`, {
        headers: this.getHeaders()
      });
      return this.handleResponse(response);
    }
    async getCurrentUser() {
      const response = await fetch("/auth/me", {
        headers: this.getHeaders()
      });
      return this.handleResponse(response);
    }
    // ==========================================
    // Sessions
    // ==========================================
    async createSession(request) {
      const response = await fetch(`${API_BASE}/sessoes`, {
        method: "POST",
        headers: this.getHeaders(),
        body: JSON.stringify(request)
      });
      return this.handleResponse(response);
    }
    async listSessions(pagina = 1, porPagina = 10) {
      const response = await fetch(
        `${API_BASE}/sessoes?pagina=${pagina}&por_pagina=${porPagina}`,
        { headers: this.getHeaders() }
      );
      return this.handleResponse(response);
    }
    async getSession(sessaoId) {
      const response = await fetch(`${API_BASE}/sessoes/${sessaoId}`, {
        headers: this.getHeaders()
      });
      return this.handleResponse(response);
    }
    async startProcessing(sessaoId) {
      const response = await fetch(`${API_BASE}/sessoes/${sessaoId}/processar`, {
        method: "POST",
        headers: this.getHeaders()
      });
      return this.handleResponse(response);
    }
    // ==========================================
    // Documents
    // ==========================================
    async listDocuments(sessaoId, status) {
      const url = status ? `${API_BASE}/sessoes/${sessaoId}/documentos?status=${status}` : `${API_BASE}/sessoes/${sessaoId}/documentos`;
      const response = await fetch(url, {
        headers: this.getHeaders()
      });
      return this.handleResponse(response);
    }
    // ==========================================
    // Consolidation
    // ==========================================
    async getConsolidation(sessaoId) {
      const response = await fetch(`${API_BASE}/sessoes/${sessaoId}/consolidacao`, {
        headers: this.getHeaders()
      });
      return this.handleResponse(response);
    }
    async startConsolidation(sessaoId) {
      return fetch(`${API_BASE}/sessoes/${sessaoId}/consolidar?streaming=true`, {
        method: "POST",
        headers: this.getHeaders()
      });
    }
    async *streamConsolidation(sessaoId) {
      const response = await this.startConsolidation(sessaoId);
      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: "Erro desconhecido" }));
        throw new Error(error.detail);
      }
      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error("Erro ao iniciar streaming");
      }
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const event = JSON.parse(line.slice(6));
              yield event;
            } catch {
              console.warn("Erro ao parsear SSE:", line);
            }
          }
        }
      }
    }
    // ==========================================
    // Chat
    // ==========================================
    async sendChatMessage(sessaoId, request) {
      return fetch(`${API_BASE}/sessoes/${sessaoId}/chat?streaming=true`, {
        method: "POST",
        headers: this.getHeaders(),
        body: JSON.stringify(request)
      });
    }
    async *streamChat(sessaoId, message) {
      const response = await this.sendChatMessage(sessaoId, { conteudo: message });
      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: "Erro desconhecido" }));
        throw new Error(error.detail);
      }
      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error("Erro ao iniciar streaming");
      }
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.chunk) {
                yield data.chunk;
              }
            } catch {
              console.warn("Erro ao parsear SSE:", line);
            }
          }
        }
      }
    }
    async getChatHistory(sessaoId) {
      const response = await fetch(`${API_BASE}/sessoes/${sessaoId}/conversas`, {
        headers: this.getHeaders()
      });
      return this.handleResponse(response);
    }
    // ==========================================
    // Pieces
    // ==========================================
    async generatePiece(sessaoId, request) {
      const response = await fetch(`${API_BASE}/sessoes/${sessaoId}/gerar-peca`, {
        method: "POST",
        headers: this.getHeaders(),
        body: JSON.stringify(request)
      });
      return this.handleResponse(response);
    }
    async listPieces(sessaoId) {
      const response = await fetch(`${API_BASE}/sessoes/${sessaoId}/pecas`, {
        headers: this.getHeaders()
      });
      return this.handleResponse(response);
    }
    getDownloadUrl(sessaoId, pecaId) {
      const token = this.getToken();
      return `${API_BASE}/sessoes/${sessaoId}/pecas/${pecaId}/download?token=${encodeURIComponent(token ?? "")}`;
    }
  };
  var api = new CumprimentoBetaApi();

  // src/sistemas/cumprimento_beta/components/JsonViewer.ts
  var JsonViewer = class {
    constructor(container, data, options = {}) {
      this.nodeStates = /* @__PURE__ */ new Map();
      this.searchQuery = "";
      this.matchingPaths = /* @__PURE__ */ new Set();
      this.container = container;
      this.data = data;
      this.options = {
        collapsed: options.collapsed ?? false,
        searchEnabled: options.searchEnabled ?? true,
        maxHeight: options.maxHeight ?? "500px",
        theme: options.theme ?? "light",
        rootName: options.rootName ?? "root"
      };
      this.initializeNodeStates(data, "");
      this.render();
    }
    initializeNodeStates(value, path) {
      if (this.isObject(value)) {
        this.nodeStates.set(path, { expanded: !this.options.collapsed, matches: false });
        Object.entries(value).forEach(([key, val]) => {
          this.initializeNodeStates(val, path ? `${path}.${key}` : key);
        });
      } else if (this.isArray(value)) {
        this.nodeStates.set(path, { expanded: !this.options.collapsed, matches: false });
        value.forEach((val, index) => {
          this.initializeNodeStates(val, path ? `${path}[${index}]` : `[${index}]`);
        });
      }
    }
    isObject(value) {
      return typeof value === "object" && value !== null && !Array.isArray(value);
    }
    isArray(value) {
      return Array.isArray(value);
    }
    escapeHtml(str) {
      const div = document.createElement("div");
      div.textContent = str;
      return div.innerHTML;
    }
    getTypeClass(value) {
      if (value === null) return "json-null";
      if (typeof value === "string") return "json-string";
      if (typeof value === "number") return "json-number";
      if (typeof value === "boolean") return "json-boolean";
      if (this.isArray(value)) return "json-array";
      if (this.isObject(value)) return "json-object";
      return "";
    }
    formatValue(value) {
      if (value === null) return '<span class="json-null">null</span>';
      if (typeof value === "string") {
        const escaped = this.escapeHtml(value);
        const highlighted = this.highlightSearch(escaped);
        return `<span class="json-string">"${highlighted}"</span>`;
      }
      if (typeof value === "number") return `<span class="json-number">${value}</span>`;
      if (typeof value === "boolean") return `<span class="json-boolean">${value}</span>`;
      return "";
    }
    highlightSearch(text) {
      if (!this.searchQuery) return text;
      const regex = new RegExp(`(${this.escapeRegex(this.searchQuery)})`, "gi");
      return text.replace(regex, '<mark class="json-highlight">$1</mark>');
    }
    escapeRegex(str) {
      return str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    }
    renderNode(key, value, path, indent) {
      const isExpandable = this.isObject(value) || this.isArray(value);
      const state = this.nodeStates.get(path);
      const isExpanded = state?.expanded ?? true;
      const matches = this.matchingPaths.has(path);
      const matchClass = matches ? "json-match" : "";
      const keyHtml = key ? `<span class="json-key ${matchClass}">${this.highlightSearch(this.escapeHtml(key))}</span>: ` : "";
      const indentStyle = `padding-left: ${indent * 20}px`;
      if (!isExpandable) {
        return `<div class="json-line" style="${indentStyle}">${keyHtml}${this.formatValue(value)}</div>`;
      }
      const isArray = this.isArray(value);
      const entries = isArray ? value : Object.entries(value);
      const count = isArray ? value.length : Object.keys(value).length;
      const bracket = isArray ? ["[", "]"] : ["{", "}"];
      const typeLabel = isArray ? `Array(${count})` : `Object`;
      const toggleIcon = isExpanded ? "fa-chevron-down" : "fa-chevron-right";
      const collapsedPreview = !isExpanded ? `<span class="json-preview">${bracket[0]}...${bracket[1]} <span class="json-count">${count} items</span></span>` : "";
      let html = `
      <div class="json-line json-expandable ${matchClass}" style="${indentStyle}">
        <button class="json-toggle" data-path="${path}" aria-label="${isExpanded ? "Recolher" : "Expandir"}">
          <i class="fas ${toggleIcon}"></i>
        </button>
        ${keyHtml}<span class="json-type-label">${typeLabel}</span> ${bracket[0]}${collapsedPreview}
      </div>
    `;
      if (isExpanded) {
        if (isArray) {
          value.forEach((item, index) => {
            const childPath = path ? `${path}[${index}]` : `[${index}]`;
            html += this.renderNode(String(index), item, childPath, indent + 1);
          });
        } else {
          Object.entries(value).forEach(([k, v]) => {
            const childPath = path ? `${path}.${k}` : k;
            html += this.renderNode(k, v, childPath, indent + 1);
          });
        }
        html += `<div class="json-line" style="${indentStyle}">${bracket[1]}</div>`;
      }
      return html;
    }
    renderToolbar() {
      return `
      <div class="json-toolbar">
        ${this.options.searchEnabled ? `
          <div class="json-search">
            <i class="fas fa-search"></i>
            <input type="text" class="json-search-input" placeholder="Buscar..." value="${this.escapeHtml(this.searchQuery)}">
            ${this.searchQuery ? `<span class="json-search-count">${this.matchingPaths.size} encontrado(s)</span>` : ""}
          </div>
        ` : ""}
        <div class="json-actions">
          <button class="json-btn" data-action="expand-all" title="Expandir tudo">
            <i class="fas fa-plus-square"></i>
          </button>
          <button class="json-btn" data-action="collapse-all" title="Recolher tudo">
            <i class="fas fa-minus-square"></i>
          </button>
          <button class="json-btn" data-action="copy" title="Copiar JSON">
            <i class="fas fa-copy"></i>
          </button>
          <button class="json-btn" data-action="download" title="Baixar JSON">
            <i class="fas fa-download"></i>
          </button>
        </div>
      </div>
    `;
    }
    render() {
      const treeHtml = this.renderNode("", this.data, "", 0);
      this.container.innerHTML = `
      <div class="json-viewer ${this.options.theme}">
        ${this.renderToolbar()}
        <div class="json-tree" style="max-height: ${this.options.maxHeight}; overflow: auto;">
          ${treeHtml}
        </div>
      </div>
    `;
      this.attachEventListeners();
    }
    attachEventListeners() {
      this.container.querySelectorAll(".json-toggle").forEach((btn) => {
        btn.addEventListener("click", () => {
          const path = btn.dataset.path ?? "";
          this.toggleNode(path);
        });
      });
      const searchInput = this.container.querySelector(".json-search-input");
      if (searchInput) {
        searchInput.addEventListener("input", (e) => {
          this.search(e.target.value);
        });
      }
      this.container.querySelectorAll(".json-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          const action = btn.dataset.action;
          switch (action) {
            case "expand-all":
              this.expandAll();
              break;
            case "collapse-all":
              this.collapseAll();
              break;
            case "copy":
              this.copyToClipboard();
              break;
            case "download":
              this.downloadJson();
              break;
          }
        });
      });
    }
    toggleNode(path) {
      const state = this.nodeStates.get(path);
      if (state) {
        state.expanded = !state.expanded;
        this.render();
      }
    }
    expandAll() {
      this.nodeStates.forEach((state) => {
        state.expanded = true;
      });
      this.render();
    }
    collapseAll() {
      this.nodeStates.forEach((state) => {
        state.expanded = false;
      });
      this.render();
    }
    search(query) {
      this.searchQuery = query.toLowerCase();
      this.matchingPaths.clear();
      if (this.searchQuery) {
        this.findMatches(this.data, "");
        this.matchingPaths.forEach((path) => {
          this.expandPath(path);
        });
      }
      this.render();
    }
    findMatches(value, path) {
      if (value === null) return;
      if (typeof value === "string" && value.toLowerCase().includes(this.searchQuery)) {
        this.matchingPaths.add(path);
      } else if (typeof value === "number" && String(value).includes(this.searchQuery)) {
        this.matchingPaths.add(path);
      } else if (this.isObject(value)) {
        Object.entries(value).forEach(([key, val]) => {
          const childPath = path ? `${path}.${key}` : key;
          if (key.toLowerCase().includes(this.searchQuery)) {
            this.matchingPaths.add(childPath);
          }
          this.findMatches(val, childPath);
        });
      } else if (this.isArray(value)) {
        value.forEach((val, index) => {
          const childPath = path ? `${path}[${index}]` : `[${index}]`;
          this.findMatches(val, childPath);
        });
      }
    }
    expandPath(path) {
      const parts = path.split(/\.|\[/).filter(Boolean);
      let currentPath = "";
      parts.forEach((part, index) => {
        if (index > 0) {
          currentPath += part.startsWith("[") ? part : `.${part}`;
        } else {
          currentPath = part.replace("]", "");
        }
        const state = this.nodeStates.get(currentPath.replace(/\]/g, ""));
        if (state) {
          state.expanded = true;
        }
      });
    }
    async copyToClipboard() {
      try {
        await navigator.clipboard.writeText(JSON.stringify(this.data, null, 2));
        this.showToast("JSON copiado!");
      } catch {
        this.showToast("Erro ao copiar", "error");
      }
    }
    downloadJson() {
      const blob = new Blob([JSON.stringify(this.data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "dados.json";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      this.showToast("JSON baixado!");
    }
    showToast(message, type = "success") {
      const toast = document.createElement("div");
      toast.className = `json-toast json-toast-${type}`;
      toast.textContent = message;
      this.container.appendChild(toast);
      setTimeout(() => toast.remove(), 2e3);
    }
    update(data) {
      this.data = data;
      this.nodeStates.clear();
      this.initializeNodeStates(data, "");
      this.render();
    }
    destroy() {
      this.container.innerHTML = "";
    }
  };
  var jsonViewerStyles = `
  .json-viewer {
    font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
    font-size: 13px;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    overflow: hidden;
  }

  .json-viewer.dark {
    background: #1e293b;
    border-color: #334155;
  }

  .json-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 12px;
    background: #f1f5f9;
    border-bottom: 1px solid #e2e8f0;
    gap: 12px;
  }

  .dark .json-toolbar {
    background: #0f172a;
    border-color: #334155;
  }

  .json-search {
    display: flex;
    align-items: center;
    gap: 8px;
    flex: 1;
    max-width: 300px;
  }

  .json-search i {
    color: #94a3b8;
  }

  .json-search-input {
    flex: 1;
    padding: 6px 10px;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    font-size: 12px;
    outline: none;
  }

  .json-search-input:focus {
    border-color: #3b82f6;
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
  }

  .json-search-count {
    font-size: 11px;
    color: #64748b;
  }

  .json-actions {
    display: flex;
    gap: 4px;
  }

  .json-btn {
    padding: 6px 10px;
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    cursor: pointer;
    color: #64748b;
    transition: all 0.15s;
  }

  .json-btn:hover {
    background: #f1f5f9;
    color: #334155;
    border-color: #cbd5e1;
  }

  .json-tree {
    padding: 12px;
  }

  .json-line {
    line-height: 1.6;
    white-space: nowrap;
  }

  .json-expandable {
    cursor: pointer;
  }

  .json-toggle {
    background: none;
    border: none;
    padding: 0 4px;
    cursor: pointer;
    color: #64748b;
    font-size: 10px;
    width: 16px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }

  .json-toggle:hover {
    color: #3b82f6;
  }

  .json-key {
    color: #0f172a;
    font-weight: 500;
  }

  .dark .json-key {
    color: #e2e8f0;
  }

  .json-string {
    color: #16a34a;
  }

  .json-number {
    color: #2563eb;
  }

  .json-boolean {
    color: #dc2626;
  }

  .json-null {
    color: #9333ea;
    font-style: italic;
  }

  .json-type-label {
    color: #94a3b8;
    font-size: 11px;
    font-style: italic;
  }

  .json-preview {
    color: #94a3b8;
  }

  .json-count {
    font-size: 11px;
  }

  .json-highlight {
    background: #fef08a;
    padding: 0 2px;
    border-radius: 2px;
  }

  .json-match {
    background: rgba(59, 130, 246, 0.1);
    border-radius: 2px;
  }

  .json-toast {
    position: absolute;
    bottom: 12px;
    right: 12px;
    padding: 8px 16px;
    background: #22c55e;
    color: white;
    border-radius: 6px;
    font-size: 12px;
    animation: toast-in 0.2s ease-out;
  }

  .json-toast-error {
    background: #ef4444;
  }

  @keyframes toast-in {
    from {
      opacity: 0;
      transform: translateY(10px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }
`;

  // src/sistemas/cumprimento_beta/components/HistoryDrawer.ts
  var HistoryDrawer = class {
    constructor(container, options = {}) {
      this.sessions = [];
      this.filters = {
        search: "",
        status: "all"
      };
      this.currentSessionId = null;
      this.container = container;
      this.options = {
        defaultOpen: options.defaultOpen ?? window.innerWidth >= 1024,
        onSessionSelect: options.onSessionSelect ?? (() => {
        }),
        onClose: options.onClose ?? (() => {
        })
      };
      this.isOpen = this.options.defaultOpen;
      this.render();
      this.setupResizeListener();
    }
    setupResizeListener() {
      let timeout;
      window.addEventListener("resize", () => {
        clearTimeout(timeout);
        timeout = window.setTimeout(() => {
          const shouldBeOpen = window.innerWidth >= 1024;
          if (this.isOpen !== shouldBeOpen) {
            this.isOpen = shouldBeOpen;
            this.render();
          }
        }, 150);
      });
    }
    escapeHtml(str) {
      const div = document.createElement("div");
      div.textContent = str;
      return div.innerHTML;
    }
    getStatusConfig(status) {
      const configs = {
        iniciado: { icon: "fa-play", color: "blue", label: "Iniciado" },
        baixando_docs: { icon: "fa-download", color: "blue", label: "Baixando" },
        avaliando_relevancia: { icon: "fa-filter", color: "yellow", label: "Avaliando" },
        extraindo_json: { icon: "fa-code", color: "yellow", label: "Extraindo" },
        consolidando: { icon: "fa-layer-group", color: "yellow", label: "Consolidando" },
        chatbot: { icon: "fa-check", color: "green", label: "Conclu\xEDdo" },
        gerando_peca: { icon: "fa-file-alt", color: "purple", label: "Gerando Pe\xE7a" },
        finalizado: { icon: "fa-check-circle", color: "green", label: "Finalizado" },
        erro: { icon: "fa-times-circle", color: "red", label: "Erro" }
      };
      return configs[status] || configs.iniciado;
    }
    formatDate(dateStr) {
      const date = new Date(dateStr);
      const now = /* @__PURE__ */ new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffMins = Math.floor(diffMs / 6e4);
      const diffHours = Math.floor(diffMs / 36e5);
      const diffDays = Math.floor(diffMs / 864e5);
      if (diffMins < 1) return "Agora";
      if (diffMins < 60) return `${diffMins}min atr\xE1s`;
      if (diffHours < 24) return `${diffHours}h atr\xE1s`;
      if (diffDays < 7) return `${diffDays}d atr\xE1s`;
      return date.toLocaleDateString("pt-BR", {
        day: "2-digit",
        month: "2-digit",
        year: "2-digit"
      });
    }
    getFilteredSessions() {
      return this.sessions.filter((session) => {
        if (this.filters.search) {
          const searchLower = this.filters.search.toLowerCase();
          const matchesCnj = session.numero_processo.includes(this.filters.search) || session.numero_processo_formatado.toLowerCase().includes(searchLower);
          if (!matchesCnj) return false;
        }
        if (this.filters.status !== "all" && session.status !== this.filters.status) {
          return false;
        }
        return true;
      });
    }
    renderSessionItem(session) {
      const statusConfig = this.getStatusConfig(session.status);
      const isSelected = session.id === this.currentSessionId;
      return `
      <button
        class="history-item ${isSelected ? "history-item-selected" : ""}"
        data-session-id="${session.id}"
        aria-label="Sess\xE3o ${session.numero_processo_formatado}"
      >
        <div class="history-item-main">
          <div class="history-item-cnj">${this.escapeHtml(session.numero_processo_formatado)}</div>
          <div class="history-item-meta">
            <span class="history-item-date">${this.formatDate(session.created_at)}</span>
            ${session.documentos_relevantes > 0 ? `
              <span class="history-item-docs">
                <i class="fas fa-file-alt"></i> ${session.documentos_relevantes}
              </span>
            ` : ""}
          </div>
        </div>
        <div class="history-item-status history-status-${statusConfig.color}">
          <i class="fas ${statusConfig.icon}"></i>
          <span>${statusConfig.label}</span>
        </div>
      </button>
    `;
    }
    renderStatusFilterOptions() {
      const statuses = [
        { value: "all", label: "Todos" },
        { value: "chatbot", label: "Conclu\xEDdos" },
        { value: "consolidando", label: "Em Progresso" },
        { value: "erro", label: "Com Erro" }
      ];
      return statuses.map((s) => `
      <option value="${s.value}" ${this.filters.status === s.value ? "selected" : ""}>
        ${s.label}
      </option>
    `).join("");
    }
    render() {
      const filteredSessions = this.getFilteredSessions();
      this.container.innerHTML = `
      <!-- Toggle Button (always visible) -->
      <button class="history-toggle" aria-label="${this.isOpen ? "Fechar" : "Abrir"} hist\xF3rico">
        <i class="fas fa-history"></i>
        <span class="history-toggle-label">Hist\xF3rico</span>
        <span class="history-toggle-count">${this.sessions.length}</span>
      </button>

      <!-- Drawer Panel -->
      <div class="history-drawer ${this.isOpen ? "history-drawer-open" : ""}">
        <!-- Overlay for mobile -->
        <div class="history-overlay"></div>

        <!-- Drawer Content -->
        <div class="history-panel">
          <!-- Header -->
          <div class="history-header">
            <h3 class="history-title">
              <i class="fas fa-history"></i>
              Hist\xF3rico
            </h3>
            <button class="history-close" aria-label="Fechar hist\xF3rico">
              <i class="fas fa-times"></i>
            </button>
          </div>

          <!-- Filters -->
          <div class="history-filters">
            <div class="history-search">
              <i class="fas fa-search"></i>
              <input
                type="text"
                class="history-search-input"
                placeholder="Buscar por CNJ..."
                value="${this.escapeHtml(this.filters.search)}"
              >
              ${this.filters.search ? `
                <button class="history-search-clear" aria-label="Limpar busca">
                  <i class="fas fa-times-circle"></i>
                </button>
              ` : ""}
            </div>
            <select class="history-filter-select">
              ${this.renderStatusFilterOptions()}
            </select>
          </div>

          <!-- Sessions List -->
          <div class="history-list">
            ${filteredSessions.length > 0 ? `
              ${filteredSessions.map((s) => this.renderSessionItem(s)).join("")}
            ` : `
              <div class="history-empty">
                ${this.sessions.length === 0 ? `
                  <i class="fas fa-inbox"></i>
                  <p>Nenhuma sess\xE3o ainda</p>
                  <span>Inicie uma nova an\xE1lise</span>
                ` : `
                  <i class="fas fa-search"></i>
                  <p>Nenhum resultado</p>
                  <span>Tente outros filtros</span>
                `}
              </div>
            `}
          </div>
        </div>
      </div>
    `;
      this.attachEventListeners();
    }
    attachEventListeners() {
      const toggleBtn = this.container.querySelector(".history-toggle");
      toggleBtn?.addEventListener("click", () => this.toggle());
      const closeBtn = this.container.querySelector(".history-close");
      closeBtn?.addEventListener("click", () => this.close());
      const overlay = this.container.querySelector(".history-overlay");
      overlay?.addEventListener("click", () => this.close());
      const searchInput = this.container.querySelector(".history-search-input");
      searchInput?.addEventListener("input", (e) => {
        this.filters.search = e.target.value;
        this.render();
      });
      const clearBtn = this.container.querySelector(".history-search-clear");
      clearBtn?.addEventListener("click", () => {
        this.filters.search = "";
        this.render();
      });
      const filterSelect = this.container.querySelector(".history-filter-select");
      filterSelect?.addEventListener("change", (e) => {
        this.filters.status = e.target.value;
        this.render();
      });
      this.container.querySelectorAll(".history-item").forEach((btn) => {
        btn.addEventListener("click", () => {
          const sessionId = parseInt(btn.dataset.sessionId ?? "0", 10);
          if (sessionId) {
            this.selectSession(sessionId);
          }
        });
      });
    }
    toggle() {
      this.isOpen = !this.isOpen;
      this.render();
    }
    open() {
      this.isOpen = true;
      this.render();
    }
    close() {
      this.isOpen = false;
      this.render();
      this.options.onClose();
    }
    setSessions(sessions) {
      this.sessions = sessions;
      this.render();
    }
    setCurrentSession(sessionId) {
      this.currentSessionId = sessionId;
      this.render();
    }
    selectSession(sessionId) {
      this.currentSessionId = sessionId;
      this.options.onSessionSelect(sessionId);
      if (window.innerWidth < 1024) {
        this.close();
      } else {
        this.render();
      }
    }
    destroy() {
      this.container.innerHTML = "";
    }
  };
  var historyDrawerStyles = `
  .history-toggle {
    position: fixed;
    left: 16px;
    top: 80px;
    z-index: 40;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 16px;
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
    cursor: pointer;
    transition: all 0.2s;
  }

  .history-toggle:hover {
    background: #f8fafc;
    box-shadow: 0 6px 16px rgba(0, 0, 0, 0.12);
  }

  .history-toggle i {
    color: #a855f7;
  }

  .history-toggle-label {
    font-size: 14px;
    font-weight: 500;
    color: #334155;
  }

  .history-toggle-count {
    background: #a855f7;
    color: white;
    font-size: 11px;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 10px;
  }

  @media (max-width: 1023px) {
    .history-toggle-label {
      display: none;
    }
  }

  .history-drawer {
    position: fixed;
    inset: 0;
    z-index: 45;
    pointer-events: none;
  }

  .history-drawer-open {
    pointer-events: auto;
  }

  .history-overlay {
    position: absolute;
    inset: 0;
    background: rgba(0, 0, 0, 0.4);
    opacity: 0;
    transition: opacity 0.3s;
  }

  .history-drawer-open .history-overlay {
    opacity: 1;
  }

  @media (min-width: 1024px) {
    .history-overlay {
      display: none;
    }
  }

  .history-panel {
    position: absolute;
    left: 0;
    top: 64px;
    bottom: 0;
    width: 320px;
    max-width: calc(100vw - 48px);
    background: white;
    border-right: 1px solid #e2e8f0;
    display: flex;
    flex-direction: column;
    transform: translateX(-100%);
    transition: transform 0.3s ease;
    box-shadow: 4px 0 24px rgba(0, 0, 0, 0.1);
  }

  .history-drawer-open .history-panel {
    transform: translateX(0);
  }

  .history-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px;
    border-bottom: 1px solid #e2e8f0;
    background: linear-gradient(to right, #faf5ff, #f8fafc);
  }

  .history-title {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 16px;
    font-weight: 600;
    color: #1e293b;
    margin: 0;
  }

  .history-title i {
    color: #a855f7;
  }

  .history-close {
    padding: 8px;
    background: none;
    border: none;
    color: #64748b;
    cursor: pointer;
    border-radius: 8px;
    transition: all 0.15s;
  }

  .history-close:hover {
    background: #f1f5f9;
    color: #334155;
  }

  .history-filters {
    padding: 12px 16px;
    border-bottom: 1px solid #e2e8f0;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .history-search {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    transition: all 0.15s;
  }

  .history-search:focus-within {
    border-color: #a855f7;
    box-shadow: 0 0 0 3px rgba(168, 85, 247, 0.1);
  }

  .history-search i {
    color: #94a3b8;
  }

  .history-search-input {
    flex: 1;
    border: none;
    background: none;
    outline: none;
    font-size: 14px;
    color: #1e293b;
  }

  .history-search-input::placeholder {
    color: #94a3b8;
  }

  .history-search-clear {
    padding: 4px;
    background: none;
    border: none;
    color: #94a3b8;
    cursor: pointer;
  }

  .history-search-clear:hover {
    color: #64748b;
  }

  .history-filter-select {
    padding: 8px 12px;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    background: white;
    font-size: 14px;
    color: #334155;
    cursor: pointer;
    outline: none;
  }

  .history-filter-select:focus {
    border-color: #a855f7;
  }

  .history-list {
    flex: 1;
    overflow-y: auto;
    padding: 8px;
  }

  .history-item {
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px;
    margin-bottom: 6px;
    background: #f8fafc;
    border: 1px solid transparent;
    border-radius: 10px;
    cursor: pointer;
    text-align: left;
    transition: all 0.15s;
  }

  .history-item:hover {
    background: #f1f5f9;
    border-color: #e2e8f0;
  }

  .history-item-selected {
    background: #faf5ff;
    border-color: #a855f7;
  }

  .history-item-main {
    flex: 1;
    min-width: 0;
  }

  .history-item-cnj {
    font-size: 13px;
    font-weight: 500;
    color: #1e293b;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .history-item-meta {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 4px;
  }

  .history-item-date {
    font-size: 11px;
    color: #64748b;
  }

  .history-item-docs {
    font-size: 11px;
    color: #64748b;
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .history-item-status {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 4px 8px;
    border-radius: 6px;
    font-size: 11px;
    font-weight: 500;
    flex-shrink: 0;
  }

  .history-status-green {
    background: #dcfce7;
    color: #16a34a;
  }

  .history-status-yellow {
    background: #fef9c3;
    color: #ca8a04;
  }

  .history-status-blue {
    background: #dbeafe;
    color: #2563eb;
  }

  .history-status-red {
    background: #fee2e2;
    color: #dc2626;
  }

  .history-status-purple {
    background: #f3e8ff;
    color: #9333ea;
  }

  .history-empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 48px 24px;
    text-align: center;
    color: #94a3b8;
  }

  .history-empty i {
    font-size: 32px;
    margin-bottom: 12px;
  }

  .history-empty p {
    font-size: 14px;
    font-weight: 500;
    color: #64748b;
    margin: 0;
  }

  .history-empty span {
    font-size: 12px;
    margin-top: 4px;
  }
`;

  // src/sistemas/cumprimento_beta/components/ProcessSteps.ts
  var ProcessSteps = class {
    constructor(container, options = {}) {
      this.steps = [];
      this.startTime = 0;
      this.elapsedInterval = null;
      this.showWarning = false;
      this.container = container;
      this.options = {
        onRetry: options.onRetry ?? (() => {
        }),
        onShowDetails: options.onShowDetails ?? (() => {
        }),
        warningThresholdMs: options.warningThresholdMs ?? 6e4
        // 1 minute
      };
      this.initializeSteps();
      this.render();
    }
    initializeSteps() {
      this.steps = [
        {
          id: "download",
          label: "Baixando documentos",
          icon: "fa-download",
          status: "aguardando",
          message: "Aguardando..."
        },
        {
          id: "avaliacao",
          label: "Avaliando relev\xE2ncia",
          icon: "fa-filter",
          status: "aguardando",
          message: "Aguardando..."
        },
        {
          id: "extracao",
          label: "Extraindo informa\xE7\xF5es",
          icon: "fa-code",
          status: "aguardando",
          message: "Aguardando..."
        },
        {
          id: "consolidacao",
          label: "Consolidando",
          icon: "fa-layer-group",
          status: "aguardando",
          message: "Aguardando..."
        }
      ];
    }
    getStatusConfig(status) {
      const configs = {
        aguardando: {
          bgClass: "bg-gray-200",
          iconClass: "text-gray-400",
          badgeClass: "bg-gray-100 text-gray-500",
          badgeText: "Aguardando"
        },
        processando: {
          bgClass: "bg-purple-500 animate-pulse",
          iconClass: "text-white",
          badgeClass: "bg-purple-100 text-purple-700",
          badgeText: "Processando"
        },
        concluido: {
          bgClass: "bg-green-500",
          iconClass: "text-white",
          badgeClass: "bg-green-100 text-green-700",
          badgeText: "Conclu\xEDdo"
        },
        erro: {
          bgClass: "bg-red-500",
          iconClass: "text-white",
          badgeClass: "bg-red-100 text-red-700",
          badgeText: "Erro"
        }
      };
      return configs[status];
    }
    getProgress() {
      const completedSteps = this.steps.filter((s) => s.status === "concluido").length;
      const processingStep = this.steps.find((s) => s.status === "processando");
      if (processingStep) {
        const stepIndex = this.steps.indexOf(processingStep);
        return (stepIndex + 0.5) / this.steps.length * 100;
      }
      return completedSteps / this.steps.length * 100;
    }
    formatDuration(ms) {
      if (ms < 1e3) return `${ms}ms`;
      if (ms < 6e4) return `${(ms / 1e3).toFixed(1)}s`;
      const mins = Math.floor(ms / 6e4);
      const secs = Math.floor(ms % 6e4 / 1e3);
      return `${mins}m ${secs}s`;
    }
    getElapsedTime() {
      if (!this.startTime) return "";
      const elapsed = Date.now() - this.startTime;
      return this.formatDuration(elapsed);
    }
    renderStep(step, index) {
      const config = this.getStatusConfig(step.status);
      const isFirst = index === 0;
      const isLast = index === this.steps.length - 1;
      return `
      <div class="process-step ${step.status === "erro" ? "process-step-error" : ""}" data-step-id="${step.id}">
        <!-- Connector Line -->
        ${!isFirst ? `
          <div class="process-connector ${this.steps[index - 1].status === "concluido" ? "process-connector-active" : ""}"></div>
        ` : ""}

        <!-- Step Content -->
        <div class="process-step-content">
          <!-- Icon -->
          <div class="process-step-icon ${config.bgClass}">
            ${step.status === "processando" ? `
              <i class="fas fa-spinner fa-spin ${config.iconClass}"></i>
            ` : step.status === "concluido" ? `
              <i class="fas fa-check ${config.iconClass}"></i>
            ` : step.status === "erro" ? `
              <i class="fas fa-times ${config.iconClass}"></i>
            ` : `
              <i class="fas ${step.icon} ${config.iconClass}"></i>
            `}
          </div>

          <!-- Info -->
          <div class="process-step-info">
            <div class="process-step-header">
              <span class="process-step-label">${step.label}</span>
              <span class="process-step-badge ${config.badgeClass}">${config.badgeText}</span>
            </div>
            <p class="process-step-message">${step.message}</p>
            ${step.duration ? `
              <span class="process-step-duration">
                <i class="fas fa-clock"></i> ${this.formatDuration(step.duration)}
              </span>
            ` : ""}
          </div>

          <!-- Error Details Button -->
          ${step.status === "erro" ? `
            <button class="process-step-details-btn" data-step-id="${step.id}">
              <i class="fas fa-info-circle"></i>
              Ver detalhes
            </button>
          ` : ""}
        </div>
      </div>
    `;
    }
    render() {
      const progress = this.getProgress();
      const isProcessing = this.steps.some((s) => s.status === "processando");
      const hasError = this.steps.some((s) => s.status === "erro");
      const elapsed = this.getElapsedTime();
      this.container.innerHTML = `
      <div class="process-steps-container">
        <!-- Header -->
        <div class="process-steps-header">
          <h3 class="process-steps-title">
            <i class="fas fa-tasks"></i>
            Processamento
          </h3>
          ${elapsed ? `
            <span class="process-steps-elapsed">
              <i class="fas fa-stopwatch"></i>
              ${elapsed}
            </span>
          ` : ""}
        </div>

        <!-- Progress Bar -->
        <div class="process-progress">
          <div class="process-progress-bar">
            <div
              class="process-progress-fill ${hasError ? "process-progress-error" : ""}"
              style="width: ${progress}%"
            ></div>
          </div>
          <span class="process-progress-text">${Math.round(progress)}%</span>
        </div>

        <!-- Warning -->
        ${this.showWarning && isProcessing ? `
          <div class="process-warning">
            <i class="fas fa-exclamation-triangle"></i>
            <span>Demorando mais que o normal...</span>
            <button class="process-warning-btn" data-action="retry">
              <i class="fas fa-redo"></i>
              Recarregar
            </button>
          </div>
        ` : ""}

        <!-- Steps -->
        <div class="process-steps-list">
          ${this.steps.map((step, index) => this.renderStep(step, index)).join("")}
        </div>

        <!-- Error Actions -->
        ${hasError ? `
          <div class="process-error-actions">
            <button class="process-retry-btn" data-action="retry">
              <i class="fas fa-redo"></i>
              Tentar novamente
            </button>
          </div>
        ` : ""}
      </div>
    `;
      this.attachEventListeners();
    }
    attachEventListeners() {
      this.container.querySelectorAll('[data-action="retry"]').forEach((btn) => {
        btn.addEventListener("click", () => this.options.onRetry());
      });
      this.container.querySelectorAll(".process-step-details-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          const stepId = btn.dataset.stepId;
          const step = this.steps.find((s) => s.id === stepId);
          if (step) {
            this.options.onShowDetails(step);
          }
        });
      });
    }
    start() {
      this.startTime = Date.now();
      this.showWarning = false;
      this.elapsedInterval = window.setInterval(() => {
        this.render();
        if (!this.showWarning && Date.now() - this.startTime > this.options.warningThresholdMs) {
          this.showWarning = true;
          this.render();
        }
      }, 1e3);
      this.render();
    }
    stop() {
      if (this.elapsedInterval) {
        clearInterval(this.elapsedInterval);
        this.elapsedInterval = null;
      }
    }
    updateStep(stepId, updates) {
      const step = this.steps.find((s) => s.id === stepId);
      if (step) {
        Object.assign(step, updates);
        this.render();
      }
    }
    setStepStatus(stepId, status, message) {
      this.updateStep(stepId, {
        status,
        message: message ?? this.getDefaultMessage(status)
      });
    }
    getDefaultMessage(status) {
      switch (status) {
        case "aguardando":
          return "Aguardando...";
        case "processando":
          return "Processando...";
        case "concluido":
          return "Conclu\xEDdo";
        case "erro":
          return "Erro no processamento";
      }
    }
    reset() {
      this.stop();
      this.startTime = 0;
      this.showWarning = false;
      this.initializeSteps();
      this.render();
    }
    complete() {
      this.stop();
      this.steps.forEach((step) => {
        if (step.status !== "erro") {
          step.status = "concluido";
        }
      });
      this.render();
    }
    destroy() {
      this.stop();
      this.container.innerHTML = "";
    }
  };
  var processStepsStyles = `
  .process-steps-container {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 16px;
    padding: 20px;
  }

  .process-steps-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 16px;
  }

  .process-steps-title {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 16px;
    font-weight: 600;
    color: #1e293b;
    margin: 0;
  }

  .process-steps-title i {
    color: #a855f7;
  }

  .process-steps-elapsed {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    color: #64748b;
  }

  .process-progress {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 20px;
  }

  .process-progress-bar {
    flex: 1;
    height: 8px;
    background: #e2e8f0;
    border-radius: 4px;
    overflow: hidden;
  }

  .process-progress-fill {
    height: 100%;
    background: linear-gradient(90deg, #a855f7, #7c3aed);
    border-radius: 4px;
    transition: width 0.5s ease;
  }

  .process-progress-error {
    background: linear-gradient(90deg, #ef4444, #dc2626);
  }

  .process-progress-text {
    font-size: 13px;
    font-weight: 600;
    color: #64748b;
    min-width: 40px;
    text-align: right;
  }

  .process-warning {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 14px;
    background: #fef3c7;
    border: 1px solid #fcd34d;
    border-radius: 10px;
    margin-bottom: 16px;
    font-size: 13px;
    color: #92400e;
  }

  .process-warning i {
    color: #f59e0b;
  }

  .process-warning-btn {
    margin-left: auto;
    padding: 6px 12px;
    background: white;
    border: 1px solid #fcd34d;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 500;
    color: #92400e;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 6px;
    transition: all 0.15s;
  }

  .process-warning-btn:hover {
    background: #fef9c3;
  }

  .process-steps-list {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .process-step {
    position: relative;
  }

  .process-connector {
    position: absolute;
    left: 17px;
    top: -12px;
    width: 2px;
    height: 12px;
    background: #e2e8f0;
  }

  .process-connector-active {
    background: #22c55e;
  }

  .process-step-content {
    display: flex;
    align-items: flex-start;
    gap: 12px;
    padding: 12px;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    transition: all 0.2s;
  }

  .process-step-error .process-step-content {
    background: #fef2f2;
    border-color: #fecaca;
  }

  .process-step-icon {
    width: 36px;
    height: 36px;
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }

  .process-step-info {
    flex: 1;
    min-width: 0;
  }

  .process-step-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 4px;
  }

  .process-step-label {
    font-size: 14px;
    font-weight: 500;
    color: #1e293b;
  }

  .process-step-badge {
    padding: 2px 8px;
    border-radius: 6px;
    font-size: 11px;
    font-weight: 500;
  }

  .process-step-message {
    font-size: 13px;
    color: #64748b;
    margin: 0;
  }

  .process-step-duration {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 11px;
    color: #94a3b8;
    margin-top: 4px;
  }

  .process-step-details-btn {
    padding: 6px 10px;
    background: white;
    border: 1px solid #fecaca;
    border-radius: 6px;
    font-size: 12px;
    color: #dc2626;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 6px;
    transition: all 0.15s;
    flex-shrink: 0;
  }

  .process-step-details-btn:hover {
    background: #fee2e2;
  }

  .process-error-actions {
    display: flex;
    justify-content: center;
    margin-top: 16px;
  }

  .process-retry-btn {
    padding: 10px 20px;
    background: #a855f7;
    border: none;
    border-radius: 10px;
    font-size: 14px;
    font-weight: 500;
    color: white;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 8px;
    transition: all 0.2s;
  }

  .process-retry-btn:hover {
    background: #9333ea;
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.7; }
  }

  .animate-pulse {
    animation: pulse 2s ease-in-out infinite;
  }
`;

  // src/sistemas/cumprimento_beta/components/ProcessSummary.ts
  var ProcessSummary = class {
    constructor(container, options = {}) {
      this.consolidation = null;
      this.isLoading = false;
      this.streamingContent = "";
      this.jsonViewer = null;
      this.activeTab = "resumo";
      this.container = container;
      this.options = {
        onSuggestionClick: options.onSuggestionClick ?? (() => {
        }),
        onCopyText: options.onCopyText ?? (() => {
        }),
        showJsonViewer: options.showJsonViewer ?? true
      };
      this.injectStyles();
      this.render();
    }
    injectStyles() {
      if (!document.getElementById("json-viewer-styles")) {
        const style = document.createElement("style");
        style.id = "json-viewer-styles";
        style.textContent = jsonViewerStyles;
        document.head.appendChild(style);
      }
    }
    escapeHtml(str) {
      const div = document.createElement("div");
      div.textContent = str;
      return div.innerHTML;
    }
    renderMarkdown(content) {
      if (typeof marked !== "undefined") {
        return marked.parse(content);
      }
      return `<pre>${this.escapeHtml(content)}</pre>`;
    }
    getPriorityConfig(priority) {
      const configs = {
        alta: { bgClass: "bg-red-100", textClass: "text-red-700", label: "Alta" },
        media: { bgClass: "bg-yellow-100", textClass: "text-yellow-700", label: "M\xE9dia" },
        baixa: { bgClass: "bg-gray-100", textClass: "text-gray-700", label: "Baixa" }
      };
      return configs[priority] || configs.baixa;
    }
    renderDataCard(label, value, icon) {
      if (!value) return "";
      return `
      <div class="summary-data-card">
        <div class="summary-data-icon">
          <i class="fas ${icon}"></i>
        </div>
        <div class="summary-data-content">
          <span class="summary-data-label">${label}</span>
          <span class="summary-data-value">${this.escapeHtml(value)}</span>
        </div>
      </div>
    `;
    }
    renderSuggestion(suggestion, index) {
      const priorityConfig = this.getPriorityConfig(suggestion.prioridade);
      return `
      <button class="summary-suggestion" data-index="${index}">
        <div class="summary-suggestion-main">
          <span class="summary-suggestion-type">${this.escapeHtml(suggestion.tipo)}</span>
          <span class="summary-suggestion-priority ${priorityConfig.bgClass} ${priorityConfig.textClass}">
            ${priorityConfig.label}
          </span>
        </div>
        <p class="summary-suggestion-desc">${this.escapeHtml(suggestion.descricao)}</p>
        <div class="summary-suggestion-action">
          <i class="fas fa-arrow-right"></i>
        </div>
      </button>
    `;
    }
    renderLoadingState() {
      return `
      <div class="summary-loading">
        <div class="summary-loading-spinner">
          <i class="fas fa-spinner fa-spin"></i>
        </div>
        <p class="summary-loading-text">Gerando resumo consolidado...</p>
        <div class="summary-loading-skeleton">
          <div class="skeleton-line skeleton-line-long"></div>
          <div class="skeleton-line skeleton-line-medium"></div>
          <div class="skeleton-line skeleton-line-short"></div>
        </div>
      </div>
    `;
    }
    renderStreamingContent() {
      return `
      <div class="summary-streaming">
        <div class="summary-streaming-indicator">
          <i class="fas fa-pen-nib animate-bounce"></i>
          <span>Gerando...</span>
        </div>
        <div class="summary-markdown markdown-body">
          ${this.renderMarkdown(this.streamingContent)}
        </div>
      </div>
    `;
    }
    renderEmptyState() {
      return `
      <div class="summary-empty">
        <i class="fas fa-inbox"></i>
        <p>Nenhum resumo dispon\xEDvel</p>
        <span>Inicie o processamento de um processo para ver o resumo</span>
      </div>
    `;
    }
    renderTabs() {
      return `
      <div class="summary-tabs">
        <button class="summary-tab ${this.activeTab === "resumo" ? "summary-tab-active" : ""}" data-tab="resumo">
          <i class="fas fa-file-alt"></i>
          Resumo
        </button>
        <button class="summary-tab ${this.activeTab === "dados" ? "summary-tab-active" : ""}" data-tab="dados">
          <i class="fas fa-table"></i>
          Dados
        </button>
        ${this.options.showJsonViewer ? `
          <button class="summary-tab ${this.activeTab === "json" ? "summary-tab-active" : ""}" data-tab="json">
            <i class="fas fa-code"></i>
            JSON
          </button>
        ` : ""}
      </div>
    `;
    }
    renderResumoTab() {
      if (!this.consolidation) return "";
      return `
      <div class="summary-content-section">
        <!-- Actions Bar -->
        <div class="summary-actions">
          <button class="summary-action-btn" data-action="copy">
            <i class="fas fa-copy"></i>
            Copiar
          </button>
        </div>

        <!-- Markdown Content -->
        <div class="summary-markdown markdown-body">
          ${this.renderMarkdown(this.consolidation.resumo_consolidado)}
        </div>

        <!-- Suggestions -->
        ${this.consolidation.sugestoes_pecas?.length > 0 ? `
          <div class="summary-suggestions">
            <h4 class="summary-suggestions-title">
              <i class="fas fa-lightbulb"></i>
              Sugest\xF5es de Pe\xE7as
            </h4>
            <div class="summary-suggestions-list">
              ${this.consolidation.sugestoes_pecas.map((s, i) => this.renderSuggestion(s, i)).join("")}
            </div>
          </div>
        ` : ""}
      </div>
    `;
    }
    renderDadosTab() {
      const data = this.consolidation?.dados_processo;
      if (!data) {
        return `
        <div class="summary-empty-tab">
          <i class="fas fa-table"></i>
          <p>Dados estruturados n\xE3o dispon\xEDveis</p>
        </div>
      `;
      }
      return `
      <div class="summary-data-grid">
        ${this.renderDataCard("Exequente", data.exequente, "fa-user")}
        ${this.renderDataCard("Executado", data.executado, "fa-user-tie")}
        ${this.renderDataCard("Valor da Execu\xE7\xE3o", data.valor_execucao, "fa-dollar-sign")}
        ${this.renderDataCard("Objeto", data.objeto, "fa-gavel")}
        ${this.renderDataCard("Status", data.status, "fa-info-circle")}
      </div>
    `;
    }
    renderJsonTab() {
      return `<div id="summary-json-viewer" class="summary-json-container"></div>`;
    }
    render() {
      if (this.isLoading) {
        this.container.innerHTML = this.renderLoadingState();
        return;
      }
      if (this.streamingContent) {
        this.container.innerHTML = this.renderStreamingContent();
        return;
      }
      if (!this.consolidation) {
        this.container.innerHTML = this.renderEmptyState();
        return;
      }
      this.container.innerHTML = `
      <div class="summary-container">
        <!-- Header -->
        <div class="summary-header">
          <h3 class="summary-title">
            <i class="fas fa-file-lines"></i>
            Resumo do Processo
          </h3>
          <span class="summary-meta">
            <i class="fas fa-clock"></i>
            ${new Date(this.consolidation.created_at).toLocaleString("pt-BR")}
          </span>
        </div>

        <!-- Tabs -->
        ${this.renderTabs()}

        <!-- Tab Content -->
        <div class="summary-tab-content">
          ${this.activeTab === "resumo" ? this.renderResumoTab() : ""}
          ${this.activeTab === "dados" ? this.renderDadosTab() : ""}
          ${this.activeTab === "json" ? this.renderJsonTab() : ""}
        </div>
      </div>
    `;
      this.attachEventListeners();
      if (this.activeTab === "json" && this.options.showJsonViewer) {
        this.initJsonViewer();
      }
    }
    initJsonViewer() {
      const viewerContainer = this.container.querySelector("#summary-json-viewer");
      if (viewerContainer && this.consolidation) {
        const jsonData = {
          resumo: this.consolidation.resumo_consolidado,
          dados_processo: this.consolidation.dados_processo,
          sugestoes_pecas: this.consolidation.sugestoes_pecas,
          total_jsons: this.consolidation.total_jsons_consolidados,
          modelo: this.consolidation.modelo_usado
        };
        this.jsonViewer = new JsonViewer(viewerContainer, jsonData, {
          collapsed: false,
          searchEnabled: true,
          maxHeight: "400px"
        });
      }
    }
    attachEventListeners() {
      this.container.querySelectorAll(".summary-tab").forEach((tab) => {
        tab.addEventListener("click", () => {
          this.activeTab = tab.dataset.tab;
          this.render();
        });
      });
      const copyBtn = this.container.querySelector('[data-action="copy"]');
      copyBtn?.addEventListener("click", () => this.copyContent());
      this.container.querySelectorAll(".summary-suggestion").forEach((btn) => {
        btn.addEventListener("click", () => {
          const index = parseInt(btn.dataset.index ?? "0", 10);
          const suggestion = this.consolidation?.sugestoes_pecas?.[index];
          if (suggestion) {
            this.options.onSuggestionClick(suggestion);
          }
        });
      });
    }
    async copyContent() {
      if (!this.consolidation) return;
      try {
        await navigator.clipboard.writeText(this.consolidation.resumo_consolidado);
        this.showToast("Conte\xFAdo copiado!");
        this.options.onCopyText();
      } catch {
        this.showToast("Erro ao copiar", "error");
      }
    }
    showToast(message, type = "success") {
      const toast = document.createElement("div");
      toast.className = `summary-toast summary-toast-${type}`;
      toast.innerHTML = `
      <i class="fas ${type === "success" ? "fa-check-circle" : "fa-exclamation-circle"}"></i>
      ${message}
    `;
      this.container.appendChild(toast);
      setTimeout(() => toast.remove(), 2e3);
    }
    // Public methods
    setLoading(loading) {
      this.isLoading = loading;
      this.streamingContent = "";
      this.render();
    }
    setStreamingContent(content) {
      this.isLoading = false;
      this.streamingContent = content;
      this.render();
    }
    appendStreamingContent(chunk) {
      this.streamingContent += chunk;
      const streamingEl = this.container.querySelector(".summary-markdown");
      if (streamingEl) {
        streamingEl.innerHTML = this.renderMarkdown(this.streamingContent);
        streamingEl.scrollTop = streamingEl.scrollHeight;
      } else {
        this.render();
      }
    }
    setConsolidation(consolidation) {
      this.consolidation = consolidation;
      this.isLoading = false;
      this.streamingContent = "";
      this.activeTab = "resumo";
      this.render();
    }
    clear() {
      this.consolidation = null;
      this.isLoading = false;
      this.streamingContent = "";
      this.jsonViewer?.destroy();
      this.jsonViewer = null;
      this.render();
    }
    destroy() {
      this.jsonViewer?.destroy();
      this.container.innerHTML = "";
    }
  };
  var processSummaryStyles = `
  .summary-container {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 16px;
    overflow: hidden;
  }

  .summary-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 20px;
    background: linear-gradient(to right, #faf5ff, #f8fafc);
    border-bottom: 1px solid #e2e8f0;
  }

  .summary-title {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 16px;
    font-weight: 600;
    color: #1e293b;
    margin: 0;
  }

  .summary-title i {
    color: #a855f7;
  }

  .summary-meta {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: #64748b;
  }

  .summary-tabs {
    display: flex;
    border-bottom: 1px solid #e2e8f0;
  }

  .summary-tab {
    flex: 1;
    padding: 12px;
    background: none;
    border: none;
    border-bottom: 2px solid transparent;
    font-size: 14px;
    font-weight: 500;
    color: #64748b;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    transition: all 0.2s;
  }

  .summary-tab:hover {
    color: #a855f7;
    background: #faf5ff;
  }

  .summary-tab-active {
    color: #a855f7;
    border-bottom-color: #a855f7;
  }

  .summary-tab-content {
    padding: 20px;
  }

  .summary-content-section {
    display: flex;
    flex-direction: column;
    gap: 20px;
  }

  .summary-actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
  }

  .summary-action-btn {
    padding: 8px 16px;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    font-size: 13px;
    color: #64748b;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 6px;
    transition: all 0.15s;
  }

  .summary-action-btn:hover {
    background: #f1f5f9;
    color: #334155;
  }

  .summary-markdown {
    font-size: 14px;
    line-height: 1.7;
    color: #374151;
  }

  .summary-markdown h1, .summary-markdown h2, .summary-markdown h3 {
    color: #1e293b;
    margin-top: 1.5em;
    margin-bottom: 0.5em;
  }

  .summary-markdown p {
    margin-bottom: 1em;
  }

  .summary-markdown ul, .summary-markdown ol {
    padding-left: 1.5em;
    margin-bottom: 1em;
  }

  .summary-suggestions {
    border-top: 1px solid #e2e8f0;
    padding-top: 20px;
  }

  .summary-suggestions-title {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 15px;
    font-weight: 600;
    color: #1e293b;
    margin: 0 0 12px 0;
  }

  .summary-suggestions-title i {
    color: #f59e0b;
  }

  .summary-suggestions-list {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 12px;
  }

  .summary-suggestion {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 14px;
    background: #faf5ff;
    border: 1px solid #e9d5ff;
    border-radius: 12px;
    text-align: left;
    cursor: pointer;
    transition: all 0.2s;
  }

  .summary-suggestion:hover {
    border-color: #a855f7;
    box-shadow: 0 4px 12px rgba(168, 85, 247, 0.15);
  }

  .summary-suggestion-main {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .summary-suggestion-type {
    font-size: 14px;
    font-weight: 600;
    color: #7c3aed;
  }

  .summary-suggestion-priority {
    padding: 2px 8px;
    border-radius: 6px;
    font-size: 11px;
    font-weight: 500;
  }

  .summary-suggestion-desc {
    font-size: 13px;
    color: #64748b;
    margin: 0;
    line-height: 1.4;
  }

  .summary-suggestion-action {
    align-self: flex-end;
    color: #a855f7;
    font-size: 12px;
  }

  .summary-data-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 12px;
  }

  .summary-data-card {
    display: flex;
    align-items: flex-start;
    gap: 12px;
    padding: 14px;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
  }

  .summary-data-icon {
    width: 36px;
    height: 36px;
    background: #a855f7;
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: white;
    flex-shrink: 0;
  }

  .summary-data-content {
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-width: 0;
  }

  .summary-data-label {
    font-size: 12px;
    color: #64748b;
  }

  .summary-data-value {
    font-size: 14px;
    font-weight: 500;
    color: #1e293b;
    word-break: break-word;
  }

  .summary-json-container {
    min-height: 300px;
  }

  .summary-loading {
    padding: 48px 24px;
    text-align: center;
  }

  .summary-loading-spinner {
    font-size: 32px;
    color: #a855f7;
    margin-bottom: 16px;
  }

  .summary-loading-text {
    font-size: 14px;
    color: #64748b;
    margin: 0 0 24px 0;
  }

  .summary-loading-skeleton {
    max-width: 400px;
    margin: 0 auto;
  }

  .skeleton-line {
    height: 12px;
    background: linear-gradient(90deg, #f1f5f9 25%, #e2e8f0 50%, #f1f5f9 75%);
    background-size: 200% 100%;
    animation: skeleton-shimmer 1.5s infinite;
    border-radius: 6px;
    margin-bottom: 12px;
  }

  .skeleton-line-long { width: 100%; }
  .skeleton-line-medium { width: 75%; }
  .skeleton-line-short { width: 50%; }

  @keyframes skeleton-shimmer {
    0% { background-position: -200% 0; }
    100% { background-position: 200% 0; }
  }

  .summary-streaming {
    padding: 20px;
  }

  .summary-streaming-indicator {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 6px 12px;
    background: #faf5ff;
    border-radius: 20px;
    font-size: 12px;
    color: #a855f7;
    margin-bottom: 16px;
  }

  @keyframes bounce {
    0%, 100% { transform: translateY(0); }
    50% { transform: translateY(-3px); }
  }

  .animate-bounce {
    animation: bounce 1s infinite;
  }

  .summary-empty, .summary-empty-tab {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 48px 24px;
    text-align: center;
    color: #94a3b8;
  }

  .summary-empty i, .summary-empty-tab i {
    font-size: 48px;
    margin-bottom: 16px;
  }

  .summary-empty p, .summary-empty-tab p {
    font-size: 16px;
    font-weight: 500;
    color: #64748b;
    margin: 0;
  }

  .summary-empty span {
    font-size: 13px;
    margin-top: 8px;
  }

  .summary-toast {
    position: fixed;
    bottom: 24px;
    right: 24px;
    padding: 12px 20px;
    background: #22c55e;
    color: white;
    border-radius: 10px;
    font-size: 14px;
    display: flex;
    align-items: center;
    gap: 8px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    animation: toast-slide-in 0.3s ease;
    z-index: 100;
  }

  .summary-toast-error {
    background: #ef4444;
  }

  @keyframes toast-slide-in {
    from {
      opacity: 0;
      transform: translateY(20px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }
`;

  // src/sistemas/cumprimento_beta/app.ts
  var CumprimentoBetaApp = class {
    constructor() {
      this.state = {
        token: localStorage.getItem("access_token"),
        userName: "",
        sessaoId: null,
        status: "idle",
        currentSession: null,
        consolidation: null,
        documents: [],
        chatHistory: [],
        generatedPieces: [],
        error: null
      };
      // Components
      this.historyDrawer = null;
      this.processSteps = null;
      this.processSummary = null;
      // Polling
      this.pollInterval = null;
      this.injectStyles();
      this.init();
    }
    injectStyles() {
      const styleId = "cumprimento-beta-styles";
      if (document.getElementById(styleId)) return;
      const style = document.createElement("style");
      style.id = styleId;
      style.textContent = `
      ${historyDrawerStyles}
      ${processStepsStyles}
      ${processSummaryStyles}
      ${jsonViewerStyles}
      ${this.getAppStyles()}
    `;
      document.head.appendChild(style);
    }
    getAppStyles() {
      return `
      .beta-app {
        min-height: 100vh;
        background: #f8fafc;
      }

      .beta-header {
        background: white;
        border-bottom: 1px solid #e2e8f0;
        padding: 0 24px;
        height: 64px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        position: sticky;
        top: 0;
        z-index: 50;
      }

      .beta-header-left {
        display: flex;
        align-items: center;
        gap: 16px;
      }

      .beta-header-back {
        color: #64748b;
        text-decoration: none;
        padding: 8px;
        border-radius: 8px;
        transition: all 0.15s;
      }

      .beta-header-back:hover {
        background: #f1f5f9;
        color: #334155;
      }

      .beta-header-logo {
        height: 40px;
      }

      .beta-header-title {
        display: flex;
        flex-direction: column;
      }

      .beta-header-title h1 {
        font-size: 16px;
        font-weight: 600;
        color: #1e293b;
        margin: 0;
      }

      .beta-badge {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        padding: 2px 8px;
        background: #f3e8ff;
        color: #7c3aed;
        font-size: 11px;
        font-weight: 500;
        border-radius: 4px;
        margin-top: 2px;
      }

      .beta-header-right {
        display: flex;
        align-items: center;
        gap: 16px;
      }

      .beta-user-name {
        font-size: 14px;
        color: #64748b;
      }

      .beta-main {
        max-width: 1200px;
        margin: 0 auto;
        padding: 24px;
        padding-left: 340px;
        transition: padding-left 0.3s;
      }

      @media (max-width: 1023px) {
        .beta-main {
          padding-left: 24px;
        }
      }

      .beta-section {
        margin-bottom: 24px;
      }

      .beta-card {
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 16px;
        padding: 24px;
      }

      .beta-input-section {
        display: flex;
        gap: 16px;
        align-items: flex-end;
      }

      .beta-input-group {
        flex: 1;
      }

      .beta-input-label {
        display: block;
        font-size: 14px;
        font-weight: 500;
        color: #374151;
        margin-bottom: 8px;
      }

      .beta-input {
        width: 100%;
        padding: 12px 16px;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        font-size: 15px;
        outline: none;
        transition: all 0.15s;
      }

      .beta-input:focus {
        border-color: #a855f7;
        box-shadow: 0 0 0 3px rgba(168, 85, 247, 0.1);
      }

      .beta-input::placeholder {
        color: #94a3b8;
      }

      .beta-input-hint {
        font-size: 12px;
        color: #94a3b8;
        margin-top: 6px;
      }

      .beta-btn {
        padding: 12px 24px;
        background: linear-gradient(135deg, #a855f7, #7c3aed);
        border: none;
        border-radius: 10px;
        color: white;
        font-size: 15px;
        font-weight: 500;
        cursor: pointer;
        display: flex;
        align-items: center;
        gap: 8px;
        transition: all 0.2s;
        white-space: nowrap;
      }

      .beta-btn:hover:not(:disabled) {
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(168, 85, 247, 0.3);
      }

      .beta-btn:disabled {
        opacity: 0.6;
        cursor: not-allowed;
      }

      .beta-chat-container {
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 16px;
        display: flex;
        flex-direction: column;
        overflow: hidden;
      }

      .beta-chat-header {
        padding: 16px 20px;
        border-bottom: 1px solid #e2e8f0;
        background: linear-gradient(to right, #faf5ff, #f8fafc);
      }

      .beta-chat-title {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 16px;
        font-weight: 600;
        color: #1e293b;
        margin: 0;
      }

      .beta-chat-title i {
        color: #a855f7;
      }

      .beta-chat-messages {
        flex: 1;
        padding: 20px;
        max-height: 400px;
        overflow-y: auto;
        display: flex;
        flex-direction: column;
        gap: 16px;
      }

      .beta-chat-message {
        display: flex;
        gap: 12px;
        max-width: 85%;
      }

      .beta-chat-message-user {
        align-self: flex-end;
        flex-direction: row-reverse;
      }

      .beta-chat-avatar {
        width: 36px;
        height: 36px;
        border-radius: 10px;
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
      }

      .beta-chat-avatar-ai {
        background: linear-gradient(135deg, #a855f7, #7c3aed);
        color: white;
      }

      .beta-chat-avatar-user {
        background: #f1f5f9;
        color: #64748b;
      }

      .beta-chat-bubble {
        padding: 12px 16px;
        border-radius: 16px;
        font-size: 14px;
        line-height: 1.5;
      }

      .beta-chat-bubble-ai {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        color: #374151;
        border-radius: 16px 16px 16px 4px;
      }

      .beta-chat-bubble-user {
        background: linear-gradient(135deg, #a855f7, #7c3aed);
        color: white;
        border-radius: 16px 16px 4px 16px;
      }

      .beta-chat-input-area {
        padding: 16px 20px;
        border-top: 1px solid #e2e8f0;
        display: flex;
        gap: 12px;
      }

      .beta-chat-input {
        flex: 1;
        padding: 12px 16px;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        font-size: 14px;
        outline: none;
        resize: none;
      }

      .beta-chat-input:focus {
        border-color: #a855f7;
      }

      .beta-chat-send {
        padding: 12px 20px;
        background: #a855f7;
        border: none;
        border-radius: 10px;
        color: white;
        cursor: pointer;
        display: flex;
        align-items: center;
        gap: 8px;
        transition: all 0.15s;
      }

      .beta-chat-send:hover:not(:disabled) {
        background: #9333ea;
      }

      .beta-chat-send:disabled {
        opacity: 0.6;
        cursor: not-allowed;
      }

      .beta-typing-indicator {
        display: flex;
        gap: 4px;
        padding: 12px 16px;
      }

      .beta-typing-indicator span {
        width: 8px;
        height: 8px;
        background: #94a3b8;
        border-radius: 50%;
        animation: typing 1.4s infinite;
      }

      .beta-typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
      .beta-typing-indicator span:nth-child(3) { animation-delay: 0.4s; }

      @keyframes typing {
        0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
        30% { transform: translateY(-4px); opacity: 1; }
      }

      .beta-error {
        background: #fef2f2;
        border: 1px solid #fecaca;
        border-radius: 12px;
        padding: 16px 20px;
        display: flex;
        align-items: flex-start;
        gap: 12px;
      }

      .beta-error-icon {
        width: 40px;
        height: 40px;
        background: #fee2e2;
        border-radius: 10px;
        display: flex;
        align-items: center;
        justify-content: center;
        color: #dc2626;
        flex-shrink: 0;
      }

      .beta-error-content h4 {
        font-size: 15px;
        font-weight: 600;
        color: #991b1b;
        margin: 0 0 4px 0;
      }

      .beta-error-content p {
        font-size: 14px;
        color: #b91c1c;
        margin: 0;
      }

      .beta-error-btn {
        margin-top: 12px;
        padding: 8px 16px;
        background: #dc2626;
        border: none;
        border-radius: 8px;
        color: white;
        font-size: 13px;
        cursor: pointer;
        display: inline-flex;
        align-items: center;
        gap: 6px;
      }

      .beta-error-btn:hover {
        background: #b91c1c;
      }

      .beta-hidden {
        display: none !important;
      }
    `;
    }
    async init() {
      if (!this.state.token) {
        window.location.href = "/login?next=/cumprimento-beta";
        return;
      }
      try {
        const access = await api.checkAccess();
        if (!access.pode_acessar) {
          this.showError(access.motivo ?? "Acesso negado");
          return;
        }
        const user = await api.getCurrentUser();
        this.state.userName = user.full_name;
        this.render();
        this.initComponents();
        await this.loadHistory();
      } catch (error) {
        const err = error;
        if (err.message.includes("401") || err.message.includes("Token")) {
          localStorage.removeItem("access_token");
          window.location.href = "/login?next=/cumprimento-beta";
          return;
        }
        this.showError(err.message);
      }
    }
    render() {
      const appContainer = document.getElementById("app") ?? document.body;
      appContainer.innerHTML = `
      <div class="beta-app">
        <!-- Header -->
        <header class="beta-header">
          <div class="beta-header-left">
            <a href="/dashboard" class="beta-header-back">
              <i class="fas fa-arrow-left"></i>
            </a>
            <img src="/logo/logo-pge.png" alt="PGE-MS" class="beta-header-logo">
            <div class="beta-header-title">
              <h1>Cumprimento de Senten\xE7a</h1>
              <span class="beta-badge">
                <i class="fas fa-flask"></i> Beta
              </span>
            </div>
          </div>
          <div class="beta-header-right">
            <span class="beta-user-name">${this.escapeHtml(this.state.userName)}</span>
            <a href="/gerador-pecas/" class="beta-header-back">
              <i class="fas fa-file-alt"></i>
            </a>
          </div>
        </header>

        <!-- History Drawer Container -->
        <div id="history-drawer-container"></div>

        <!-- Main Content -->
        <main class="beta-main">
          <!-- Input Section -->
          <section class="beta-section beta-card">
            <div class="beta-input-section">
              <div class="beta-input-group">
                <label class="beta-input-label" for="numero-processo">
                  N\xFAmero do Processo (CNJ)
                </label>
                <input
                  type="text"
                  id="numero-processo"
                  class="beta-input"
                  placeholder="0000000-00.0000.0.00.0000"
                >
                <p class="beta-input-hint">Formato: NNNNNNN-DD.AAAA.J.TR.OOOO</p>
              </div>
              <button id="btn-iniciar" class="beta-btn">
                <i class="fas fa-play"></i>
                Iniciar
              </button>
            </div>
          </section>

          <!-- Error Section -->
          <section id="error-section" class="beta-section beta-hidden">
            <div class="beta-error">
              <div class="beta-error-icon">
                <i class="fas fa-exclamation-triangle"></i>
              </div>
              <div class="beta-error-content">
                <h4>Erro no Processamento</h4>
                <p id="error-message"></p>
                <button id="btn-retry" class="beta-error-btn">
                  <i class="fas fa-redo"></i>
                  Tentar Novamente
                </button>
              </div>
            </div>
          </section>

          <!-- Processing Section -->
          <section id="processing-section" class="beta-section beta-hidden">
            <div id="process-steps-container"></div>
          </section>

          <!-- Summary Section -->
          <section id="summary-section" class="beta-section beta-hidden">
            <div id="process-summary-container"></div>
          </section>

          <!-- Chat Section -->
          <section id="chat-section" class="beta-section beta-hidden">
            <div class="beta-chat-container">
              <div class="beta-chat-header">
                <h3 class="beta-chat-title">
                  <i class="fas fa-comments"></i>
                  Chat com IA
                </h3>
              </div>
              <div id="chat-messages" class="beta-chat-messages">
                <!-- Messages will be added here -->
              </div>
              <div class="beta-chat-input-area">
                <input
                  type="text"
                  id="chat-input"
                  class="beta-chat-input"
                  placeholder="Digite sua mensagem..."
                >
                <button id="btn-send-chat" class="beta-chat-send">
                  <i class="fas fa-paper-plane"></i>
                </button>
              </div>
            </div>
          </section>
        </main>
      </div>
    `;
      this.attachEventListeners();
    }
    initComponents() {
      const historyContainer = document.getElementById("history-drawer-container");
      if (historyContainer) {
        this.historyDrawer = new HistoryDrawer(historyContainer, {
          onSessionSelect: (id) => this.loadSession(id)
        });
      }
      const stepsContainer = document.getElementById("process-steps-container");
      if (stepsContainer) {
        this.processSteps = new ProcessSteps(stepsContainer, {
          onRetry: () => this.retry(),
          warningThresholdMs: 12e4
          // 2 minutes
        });
      }
      const summaryContainer = document.getElementById("process-summary-container");
      if (summaryContainer) {
        this.processSummary = new ProcessSummary(summaryContainer, {
          onSuggestionClick: (s) => this.handleSuggestionClick(s)
        });
      }
    }
    attachEventListeners() {
      document.getElementById("btn-iniciar")?.addEventListener("click", () => {
        this.startNewSession();
      });
      document.getElementById("numero-processo")?.addEventListener("keypress", (e) => {
        if (e.key === "Enter") {
          this.startNewSession();
        }
      });
      document.getElementById("btn-retry")?.addEventListener("click", () => {
        this.retry();
      });
      document.getElementById("btn-send-chat")?.addEventListener("click", () => {
        this.sendChatMessage();
      });
      document.getElementById("chat-input")?.addEventListener("keypress", (e) => {
        if (e.key === "Enter") {
          this.sendChatMessage();
        }
      });
    }
    escapeHtml(str) {
      const div = document.createElement("div");
      div.textContent = str;
      return div.innerHTML;
    }
    // ==========================================
    // Session Management
    // ==========================================
    async loadHistory() {
      try {
        const response = await api.listSessions(1, 50);
        this.historyDrawer?.setSessions(response.sessoes);
      } catch (error) {
        console.error("Erro ao carregar hist\xF3rico:", error);
      }
    }
    async startNewSession() {
      const input = document.getElementById("numero-processo");
      const numeroProcesso = input?.value.trim();
      if (!numeroProcesso) {
        this.showToast("Informe o n\xFAmero do processo", "warning");
        return;
      }
      this.hideError();
      this.showSection("processing");
      try {
        const session = await api.createSession({ numero_processo: numeroProcesso });
        this.state.sessaoId = session.sessao_id;
        await api.startProcessing(session.sessao_id);
        this.processSteps?.start();
        this.startPolling();
        await this.loadHistory();
        this.historyDrawer?.setCurrentSession(session.sessao_id);
      } catch (error) {
        const err = error;
        this.showError(err.message);
        this.processSteps?.stop();
      }
    }
    async loadSession(sessionId) {
      this.state.sessaoId = sessionId;
      this.hideError();
      try {
        const session = await api.getSession(sessionId);
        this.state.currentSession = session;
        this.historyDrawer?.setCurrentSession(sessionId);
        const input = document.getElementById("numero-processo");
        if (input) {
          input.value = session.numero_processo_formatado;
        }
        if (session.status === "chatbot" || session.status === "finalizado") {
          await this.loadCompletedSession(session);
        } else if (session.status === "erro") {
          this.showError(session.erro_mensagem ?? "Erro no processamento");
        } else if (session.status === "consolidando" && !session.tem_consolidacao) {
          this.showSection("processing");
          this.processSteps?.start();
          await this.runConsolidation();
        } else {
          this.showSection("processing");
          this.processSteps?.start();
          this.startPolling();
        }
      } catch (error) {
        const err = error;
        this.showError(err.message);
      }
    }
    async loadCompletedSession(session) {
      this.showSection("summary");
      this.showSection("chat");
      try {
        const consolidation = await api.getConsolidation(session.id);
        this.state.consolidation = consolidation;
        this.processSummary?.setConsolidation(consolidation);
        const chatHistory = await api.getChatHistory(session.id);
        this.state.chatHistory = chatHistory.mensagens;
        this.renderChatHistory();
      } catch (error) {
        console.error("Erro ao carregar sess\xE3o:", error);
        this.processSummary?.clear();
      }
    }
    // ==========================================
    // Polling
    // ==========================================
    startPolling() {
      this.stopPolling();
      this.pollInterval = window.setInterval(() => this.pollStatus(), 2e3);
    }
    stopPolling() {
      if (this.pollInterval) {
        clearInterval(this.pollInterval);
        this.pollInterval = null;
      }
    }
    async pollStatus() {
      if (!this.state.sessaoId) return;
      try {
        const session = await api.getSession(this.state.sessaoId);
        this.state.currentSession = session;
        this.updateProcessingUI(session);
        if (session.status === "consolidando") {
          if (!session.tem_consolidacao) {
            this.stopPolling();
            await this.runConsolidation();
          }
        } else if (session.status === "chatbot" || session.status === "finalizado") {
          this.stopPolling();
          this.processSteps?.complete();
          await this.loadCompletedSession(session);
        } else if (session.status === "erro") {
          this.stopPolling();
          this.processSteps?.stop();
          this.showError(session.erro_mensagem ?? "Erro no processamento");
        }
      } catch (error) {
        console.error("Erro no polling:", error);
      }
    }
    updateProcessingUI(session) {
      const statusMap = {
        iniciado: "download",
        baixando_docs: "download",
        avaliando_relevancia: "avaliacao",
        extraindo_json: "extracao",
        consolidando: "consolidacao",
        chatbot: "consolidacao",
        gerando_peca: "consolidacao",
        finalizado: "consolidacao",
        erro: "download"
      };
      const currentStep = statusMap[session.status];
      if (session.status === "baixando_docs") {
        this.processSteps?.setStepStatus(
          "download",
          "processando",
          `${session.documentos_processados}/${session.total_documentos} documentos`
        );
      } else if (session.status === "avaliando_relevancia" || session.status === "extraindo_json") {
        this.processSteps?.setStepStatus(
          "download",
          "concluido",
          `${session.total_documentos} documentos baixados`
        );
        this.processSteps?.setStepStatus(
          "avaliacao",
          "processando",
          `${session.documentos_relevantes} relevantes de ${session.documentos_processados}`
        );
        if (session.status === "extraindo_json") {
          this.processSteps?.setStepStatus("extracao", "processando", "Extraindo informa\xE7\xF5es...");
        }
      } else if (session.status === "consolidando") {
        this.processSteps?.setStepStatus("download", "concluido");
        this.processSteps?.setStepStatus("avaliacao", "concluido");
        this.processSteps?.setStepStatus("extracao", "concluido");
        this.processSteps?.setStepStatus("consolidacao", "processando", "Consolidando...");
      }
    }
    // ==========================================
    // Consolidation
    // ==========================================
    async runConsolidation() {
      if (!this.state.sessaoId) return;
      this.showSection("summary");
      this.processSummary?.setLoading(true);
      this.processSteps?.setStepStatus("consolidacao", "processando", "Gerando resumo...");
      try {
        for await (const event of api.streamConsolidation(this.state.sessaoId)) {
          this.handleConsolidationEvent(event);
        }
      } catch (error) {
        const err = error;
        this.showError(err.message);
        this.processSteps?.setStepStatus("consolidacao", "erro", err.message);
      }
    }
    handleConsolidationEvent(event) {
      switch (event.event) {
        case "inicio":
          this.processSummary?.setStreamingContent("");
          break;
        case "chunk":
          this.processSummary?.appendStreamingContent(event.data.texto);
          break;
        case "concluido":
          this.processSteps?.setStepStatus("consolidacao", "concluido");
          this.processSteps?.stop();
          this.showSection("chat");
          if (this.state.sessaoId) {
            api.getConsolidation(this.state.sessaoId).then((consolidation) => {
              this.state.consolidation = consolidation;
              this.processSummary?.setConsolidation(consolidation);
            });
          }
          this.addChatMessage(
            "assistant",
            "Ol\xE1! Analisei o processo de cumprimento de senten\xE7a. Como posso ajudar? Voc\xEA pode escolher uma das sugest\xF5es acima ou fazer qualquer pergunta sobre o processo."
          );
          break;
        case "erro":
          this.showError(event.data.mensagem);
          this.processSteps?.setStepStatus("consolidacao", "erro", event.data.mensagem);
          break;
      }
    }
    // ==========================================
    // Chat
    // ==========================================
    renderChatHistory() {
      const container = document.getElementById("chat-messages");
      if (!container) return;
      container.innerHTML = "";
      for (const msg of this.state.chatHistory) {
        this.addChatMessage(msg.role === "user" ? "user" : "assistant", msg.conteudo);
      }
      container.scrollTop = container.scrollHeight;
    }
    addChatMessage(role, content) {
      const container = document.getElementById("chat-messages");
      if (!container) return;
      const messageEl = document.createElement("div");
      messageEl.className = `beta-chat-message ${role === "user" ? "beta-chat-message-user" : ""}`;
      const parsedContent = typeof marked !== "undefined" ? marked.parse(content) : this.escapeHtml(content);
      messageEl.innerHTML = `
      <div class="beta-chat-avatar ${role === "user" ? "beta-chat-avatar-user" : "beta-chat-avatar-ai"}">
        <i class="fas ${role === "user" ? "fa-user" : "fa-robot"}"></i>
      </div>
      <div class="beta-chat-bubble ${role === "user" ? "beta-chat-bubble-user" : "beta-chat-bubble-ai"}">
        ${parsedContent}
      </div>
    `;
      container.appendChild(messageEl);
      container.scrollTop = container.scrollHeight;
    }
    addTypingIndicator() {
      const container = document.getElementById("chat-messages");
      if (!container) return document.createElement("div");
      const indicator = document.createElement("div");
      indicator.id = "typing-indicator";
      indicator.className = "beta-chat-message";
      indicator.innerHTML = `
      <div class="beta-chat-avatar beta-chat-avatar-ai">
        <i class="fas fa-robot"></i>
      </div>
      <div class="beta-chat-bubble beta-chat-bubble-ai">
        <div class="beta-typing-indicator">
          <span></span><span></span><span></span>
        </div>
      </div>
    `;
      container.appendChild(indicator);
      container.scrollTop = container.scrollHeight;
      return indicator;
    }
    removeTypingIndicator() {
      document.getElementById("typing-indicator")?.remove();
    }
    async sendChatMessage() {
      const input = document.getElementById("chat-input");
      const message = input?.value.trim();
      if (!message || !this.state.sessaoId) return;
      input.value = "";
      this.addChatMessage("user", message);
      this.addTypingIndicator();
      try {
        let response = "";
        const messageEl = document.createElement("div");
        messageEl.className = "beta-chat-message";
        messageEl.innerHTML = `
        <div class="beta-chat-avatar beta-chat-avatar-ai">
          <i class="fas fa-robot"></i>
        </div>
        <div class="beta-chat-bubble beta-chat-bubble-ai message-content"></div>
      `;
        this.removeTypingIndicator();
        document.getElementById("chat-messages")?.appendChild(messageEl);
        const contentEl = messageEl.querySelector(".message-content");
        for await (const chunk of api.streamChat(this.state.sessaoId, message)) {
          response += chunk;
          if (contentEl && typeof marked !== "undefined") {
            contentEl.innerHTML = marked.parse(response);
          }
          const container = document.getElementById("chat-messages");
          if (container) {
            container.scrollTop = container.scrollHeight;
          }
        }
      } catch (error) {
        this.removeTypingIndicator();
        const err = error;
        this.addChatMessage("assistant", `Erro: ${err.message}`);
      }
    }
    handleSuggestionClick(suggestion) {
      const input = document.getElementById("chat-input");
      if (input) {
        input.value = `Gere uma ${suggestion.tipo} para este processo`;
        input.focus();
      }
    }
    // ==========================================
    // UI Helpers
    // ==========================================
    showSection(section) {
      const sectionId = `${section}-section`;
      document.getElementById(sectionId)?.classList.remove("beta-hidden");
    }
    hideSection(section) {
      const sectionId = `${section}-section`;
      document.getElementById(sectionId)?.classList.add("beta-hidden");
    }
    showError(message) {
      const section = document.getElementById("error-section");
      const messageEl = document.getElementById("error-message");
      if (section) section.classList.remove("beta-hidden");
      if (messageEl) messageEl.textContent = message;
      this.state.error = message;
      this.hideSection("processing");
    }
    hideError() {
      document.getElementById("error-section")?.classList.add("beta-hidden");
      this.state.error = null;
    }
    retry() {
      this.hideError();
      this.processSteps?.reset();
      if (this.state.sessaoId) {
        this.loadSession(this.state.sessaoId);
      }
    }
    showToast(message, type = "success") {
      const toast = document.createElement("div");
      toast.className = `summary-toast summary-toast-${type}`;
      toast.innerHTML = `
      <i class="fas ${type === "success" ? "fa-check-circle" : type === "warning" ? "fa-exclamation-triangle" : "fa-exclamation-circle"}"></i>
      ${message}
    `;
      document.body.appendChild(toast);
      setTimeout(() => toast.remove(), 3e3);
    }
  };
  var app = new CumprimentoBetaApp();
  window.cumprimentoBetaApp = app;
})();
//# sourceMappingURL=index.js.map
