/**
 * Cliente API compartilhado para todos os sistemas do Portal PGE
 */

// Types importados para uso futuro
// import type { ApiResponse } from '../types/api';

// ============================================
// Autenticação
// ============================================

/**
 * Obtém o token de autenticação do localStorage
 */
export function getAuthToken(): string | null {
  return localStorage.getItem('access_token');
}

/**
 * Verifica se o usuário está autenticado
 * Redireciona para login se não estiver
 */
export function checkAuth(redirectPath?: string): boolean {
  const token = getAuthToken();
  if (!token) {
    const next = redirectPath || window.location.pathname;
    window.location.href = `/login?next=${encodeURIComponent(next)}`;
    return false;
  }
  return true;
}

/**
 * Remove token e redireciona para login
 */
export function logout(): void {
  localStorage.removeItem('access_token');
  window.location.href = '/login';
}

// ============================================
// Cliente API Base
// ============================================

export interface ApiRequestOptions extends RequestInit {
  responseType?: 'json' | 'blob' | 'text';
}

/**
 * Faz uma requisição autenticada para a API
 *
 * @param endpoint - Endpoint da API (ex: '/consultar')
 * @param options - Opções da requisição
 * @returns Dados da resposta ou null em caso de erro de autenticação
 */
export async function apiRequest<T = unknown>(
  baseUrl: string,
  endpoint: string,
  options: ApiRequestOptions = {}
): Promise<T | null> {
  if (!checkAuth()) return null;

  const token = getAuthToken();
  const { responseType = 'json', headers: customHeaders, ...restOptions } = options;

  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${token}`,
    ...customHeaders,
  };

  try {
    const response = await fetch(`${baseUrl}${endpoint}`, {
      headers,
      ...restOptions,
    });

    // Token expirado ou inválido
    if (response.status === 401) {
      logout();
      return null;
    }

    // Para downloads (blob)
    if (responseType === 'blob') {
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      return (await response.blob()) as T;
    }

    // Para texto puro
    if (responseType === 'text') {
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      return (await response.text()) as T;
    }

    // JSON (padrão)
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || data.message || `HTTP ${response.status}`);
    }

    return data as T;
  } catch (error) {
    console.error(`API Error [${endpoint}]:`, error);
    throw error;
  }
}

/**
 * Cria um cliente API para um sistema específico
 *
 * @param baseUrl - URL base do sistema (ex: '/assistencia/api')
 * @returns Funções de API configuradas
 */
export function createApiClient(baseUrl: string) {
  return {
    get: <T = unknown>(endpoint: string, options?: ApiRequestOptions) =>
      apiRequest<T>(baseUrl, endpoint, { ...options, method: 'GET' }),

    post: <T = unknown>(endpoint: string, body?: unknown, options?: ApiRequestOptions) =>
      apiRequest<T>(baseUrl, endpoint, {
        ...options,
        method: 'POST',
        body: body ? JSON.stringify(body) : undefined,
      }),

    put: <T = unknown>(endpoint: string, body?: unknown, options?: ApiRequestOptions) =>
      apiRequest<T>(baseUrl, endpoint, {
        ...options,
        method: 'PUT',
        body: body ? JSON.stringify(body) : undefined,
      }),

    delete: <T = unknown>(endpoint: string, options?: ApiRequestOptions) =>
      apiRequest<T>(baseUrl, endpoint, { ...options, method: 'DELETE' }),

    /**
     * Requisição com blob response (para downloads)
     */
    blob: (endpoint: string, options?: ApiRequestOptions) =>
      apiRequest<Blob>(baseUrl, endpoint, { ...options, responseType: 'blob' }),
  };
}

// ============================================
// Verificação de autenticação no servidor
// ============================================

/**
 * Verifica se o token é válido no servidor
 * Útil para verificação inicial da página
 */
export async function verifyAuthToken(): Promise<boolean> {
  const token = getAuthToken();
  if (!token) return false;

  try {
    const response = await fetch('/auth/me', {
      headers: { Authorization: `Bearer ${token}` },
    });

    if (!response.ok) {
      localStorage.removeItem('access_token');
      return false;
    }

    return true;
  } catch {
    return false;
  }
}
