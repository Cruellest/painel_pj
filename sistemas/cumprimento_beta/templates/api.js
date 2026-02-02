// Generated from TypeScript - DO NOT EDIT DIRECTLY
// Source: src\sistemas\cumprimento_beta\api.ts
// Built at: 2026-01-30T21:41:45.549Z

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
})();
//# sourceMappingURL=api.js.map
