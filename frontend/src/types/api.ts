/**
 * Tipos para comunicação com a API do Portal PGE
 */

// ============================================
// Respostas genéricas
// ============================================

export interface ApiResponse<T = unknown> {
  success: boolean;
  data?: T;
  message?: string;
  error?: string;
  detail?: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
  has_next: boolean;
  has_prev: boolean;
}

// ============================================
// Autenticação
// ============================================

export interface Usuario {
  id: number;
  username: string;
  nome_completo: string;
  email: string;
  ativo: boolean;
  papel: 'admin' | 'procurador' | 'estagiario';
  data_criacao: string;
  ultimo_acesso?: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

// ============================================
// Processos
// ============================================

export interface Processo {
  numero_processo: string;
  numero_formatado: string;
  classe: string;
  classe_codigo: number;
  assunto: string;
  assunto_codigo: number;
  comarca: string;
  vara: string;
  data_ajuizamento: string;
  valor_causa: string;
  situacao: string;
  polo_ativo: Parte[];
  polo_passivo: Parte[];
  movimentacoes?: Movimentacao[];
}

export interface Parte {
  nome: string;
  documento?: string;
  tipo_pessoa: 'fisica' | 'juridica';
  tipo_parte: string;
  assistencia_judiciaria?: boolean;
  advogados?: Advogado[];
}

export interface Advogado {
  nome: string;
  oab: string;
}

export interface Movimentacao {
  data: string;
  descricao: string;
  complemento?: string;
}

// ============================================
// Histórico
// ============================================

export interface HistoricoItem {
  id: number;
  numero_processo?: string;
  numero_cnj?: string;
  numero_cnj_formatado?: string;
  cnj?: string;
  classe?: string;
  autor?: string;
  tipo_peca?: string;
  data_geracao?: string;
  criado_em?: string;
  status?: 'sucesso' | 'erro' | 'parcial';
}

// ============================================
// Feedback
// ============================================

export type AvaliacaoFeedback = 'correto' | 'parcial' | 'incorreto' | 'erro_ia';

export interface FeedbackRequest {
  consulta_id?: number;
  geracao_id?: number;
  avaliacao: AvaliacaoFeedback;
  nota?: number;
  comentario?: string | null;
}

export interface FeedbackResponse {
  success: boolean;
  has_feedback?: boolean;
  avaliacao?: AvaliacaoFeedback;
}

// ============================================
// Documentos
// ============================================

export interface DocumentoBaixado {
  id: string;
  tipo: string;
  processo?: 'origem' | 'cumprimento';
  numero_processo?: string;
}

// ============================================
// Toast types
// ============================================

export type ToastType = 'success' | 'error' | 'warning' | 'info';
