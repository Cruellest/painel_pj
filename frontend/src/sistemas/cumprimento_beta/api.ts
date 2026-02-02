// frontend/src/sistemas/cumprimento_beta/api.ts
/**
 * API Client para o módulo Cumprimento de Sentença Beta
 *
 * Encapsula todas as chamadas HTTP para o backend
 *
 * @author LAB/PGE-MS
 */

import type {
  SessionResponse,
  SessionListResponse,
  CreateSessionRequest,
  CreateSessionResponse,
  DocumentResponse,
  ConsolidationResponse,
  ChatMessageRequest,
  ChatMessageResponse,
  ChatHistoryResponse,
  GeneratePieceRequest,
  GeneratedPieceResponse,
  SSEEvent,
  ApiError,
} from './types';

const API_BASE = '/api/cumprimento-beta';

class CumprimentoBetaApi {
  private getToken(): string | null {
    return localStorage.getItem('access_token');
  }

  private getHeaders(): HeadersInit {
    const token = this.getToken();
    return {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    };
  }

  private async handleResponse<T>(response: Response): Promise<T> {
    if (!response.ok) {
      let error: ApiError;
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

  async checkAccess(): Promise<{ pode_acessar: boolean; motivo?: string }> {
    const response = await fetch(`${API_BASE}/acesso`, {
      headers: this.getHeaders(),
    });
    return this.handleResponse(response);
  }

  async getCurrentUser(): Promise<{ id: number; full_name: string; email: string }> {
    const response = await fetch('/auth/me', {
      headers: this.getHeaders(),
    });
    return this.handleResponse(response);
  }

  // ==========================================
  // Sessions
  // ==========================================

  async createSession(request: CreateSessionRequest): Promise<CreateSessionResponse> {
    const response = await fetch(`${API_BASE}/sessoes`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify(request),
    });
    return this.handleResponse(response);
  }

  async listSessions(pagina: number = 1, porPagina: number = 10): Promise<SessionListResponse> {
    const response = await fetch(
      `${API_BASE}/sessoes?pagina=${pagina}&por_pagina=${porPagina}`,
      { headers: this.getHeaders() }
    );
    return this.handleResponse(response);
  }

  async getSession(sessaoId: number): Promise<SessionResponse> {
    const response = await fetch(`${API_BASE}/sessoes/${sessaoId}`, {
      headers: this.getHeaders(),
    });
    return this.handleResponse(response);
  }

  async startProcessing(sessaoId: number): Promise<{ mensagem: string; sessao_id: number; status: string }> {
    const response = await fetch(`${API_BASE}/sessoes/${sessaoId}/processar`, {
      method: 'POST',
      headers: this.getHeaders(),
    });
    return this.handleResponse(response);
  }

  // ==========================================
  // Documents
  // ==========================================

  async listDocuments(sessaoId: number, status?: string): Promise<DocumentResponse[]> {
    const url = status
      ? `${API_BASE}/sessoes/${sessaoId}/documentos?status=${status}`
      : `${API_BASE}/sessoes/${sessaoId}/documentos`;
    const response = await fetch(url, {
      headers: this.getHeaders(),
    });
    return this.handleResponse(response);
  }

  // ==========================================
  // Consolidation
  // ==========================================

  async getConsolidation(sessaoId: number): Promise<ConsolidationResponse> {
    const response = await fetch(`${API_BASE}/sessoes/${sessaoId}/consolidacao`, {
      headers: this.getHeaders(),
    });
    return this.handleResponse(response);
  }

  async startConsolidation(sessaoId: number): Promise<Response> {
    return fetch(`${API_BASE}/sessoes/${sessaoId}/consolidar?streaming=true`, {
      method: 'POST',
      headers: this.getHeaders(),
    });
  }

  async *streamConsolidation(sessaoId: number): AsyncGenerator<SSEEvent, void, unknown> {
    const response = await this.startConsolidation(sessaoId);

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Erro desconhecido' }));
      throw new Error(error.detail);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('Erro ao iniciar streaming');
    }

    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const event: SSEEvent = JSON.parse(line.slice(6));
            yield event;
          } catch {
            console.warn('Erro ao parsear SSE:', line);
          }
        }
      }
    }
  }

  // ==========================================
  // Chat
  // ==========================================

  async sendChatMessage(sessaoId: number, request: ChatMessageRequest): Promise<Response> {
    return fetch(`${API_BASE}/sessoes/${sessaoId}/chat?streaming=true`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify(request),
    });
  }

  async *streamChat(sessaoId: number, message: string): AsyncGenerator<string, void, unknown> {
    const response = await this.sendChatMessage(sessaoId, { conteudo: message });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Erro desconhecido' }));
      throw new Error(error.detail);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('Erro ao iniciar streaming');
    }

    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6));
            if (data.chunk) {
              yield data.chunk;
            }
          } catch {
            console.warn('Erro ao parsear SSE:', line);
          }
        }
      }
    }
  }

  async getChatHistory(sessaoId: number): Promise<ChatHistoryResponse> {
    const response = await fetch(`${API_BASE}/sessoes/${sessaoId}/conversas`, {
      headers: this.getHeaders(),
    });
    return this.handleResponse(response);
  }

  // ==========================================
  // Pieces
  // ==========================================

  async generatePiece(sessaoId: number, request: GeneratePieceRequest): Promise<GeneratedPieceResponse> {
    const response = await fetch(`${API_BASE}/sessoes/${sessaoId}/gerar-peca`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify(request),
    });
    return this.handleResponse(response);
  }

  async listPieces(sessaoId: number): Promise<GeneratedPieceResponse[]> {
    const response = await fetch(`${API_BASE}/sessoes/${sessaoId}/pecas`, {
      headers: this.getHeaders(),
    });
    return this.handleResponse(response);
  }

  getDownloadUrl(sessaoId: number, pecaId: number): string {
    const token = this.getToken();
    return `${API_BASE}/sessoes/${sessaoId}/pecas/${pecaId}/download?token=${encodeURIComponent(token ?? '')}`;
  }
}

// Singleton instance
export const api = new CumprimentoBetaApi();
