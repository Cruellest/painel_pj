// frontend/src/sistemas/cumprimento_beta/types.ts
/**
 * Tipos TypeScript para o módulo Cumprimento de Sentença Beta
 *
 * @author LAB/PGE-MS
 */

// ============================================
// Status e Enums
// ============================================

export type SessionStatus =
  | 'iniciado'
  | 'baixando_docs'
  | 'avaliando_relevancia'
  | 'extraindo_json'
  | 'consolidando'
  | 'chatbot'
  | 'gerando_peca'
  | 'finalizado'
  | 'erro';

export type RelevanceStatus = 'pendente' | 'relevante' | 'irrelevante' | 'ignorado';

export type StepStatus = 'aguardando' | 'processando' | 'concluido' | 'erro';

export type MessageRole = 'user' | 'assistant' | 'system';

// ============================================
// API Response Types
// ============================================

export interface SessionResponse {
  id: number;
  numero_processo: string;
  numero_processo_formatado: string;
  status: SessionStatus;
  total_documentos: number;
  documentos_processados: number;
  documentos_relevantes: number;
  documentos_irrelevantes: number;
  documentos_ignorados: number;
  erro_mensagem: string | null;
  created_at: string;
  updated_at: string;
  finalizado_em: string | null;
  tem_consolidacao: boolean;
  total_conversas: number;
  total_pecas: number;
}

export interface SessionListResponse {
  sessoes: SessionResponse[];
  total: number;
  pagina: number;
  por_pagina: number;
}

export interface CreateSessionRequest {
  numero_processo: string;
}

export interface CreateSessionResponse {
  sessao_id: number;
  numero_processo: string;
  numero_processo_formatado: string;
  status: SessionStatus;
  created_at: string;
}

export interface DocumentResponse {
  id: number;
  documento_id_tjms: string;
  codigo_documento: string;
  descricao_documento: string | null;
  data_documento: string | null;
  status_relevancia: RelevanceStatus;
  motivo_irrelevancia: string | null;
  tem_json: boolean;
}

export interface ConsolidationResponse {
  id: number;
  sessao_id: number;
  resumo_consolidado: string;
  sugestoes_pecas: PieceSuggestion[];
  dados_processo: ProcessData | null;
  total_jsons_consolidados: number;
  modelo_usado: string;
  created_at: string;
}

export interface ProcessData {
  exequente?: string;
  executado?: string;
  valor_execucao?: string;
  objeto?: string;
  status?: string;
  [key: string]: unknown;
}

export interface PieceSuggestion {
  tipo: string;
  descricao: string;
  prioridade: 'alta' | 'media' | 'baixa';
}

export interface ChatMessageRequest {
  conteudo: string;
}

export interface ChatMessageResponse {
  id: number;
  role: MessageRole;
  conteudo: string;
  modelo_usado: string | null;
  usou_busca_vetorial: boolean;
  created_at: string;
}

export interface ChatHistoryResponse {
  sessao_id: number;
  mensagens: ChatMessageResponse[];
  total: number;
}

export interface GeneratePieceRequest {
  tipo_peca: string;
  instrucoes_adicionais?: string;
}

export interface GeneratedPieceResponse {
  id: number;
  sessao_id: number;
  tipo_peca: string;
  titulo: string;
  conteudo_markdown: string;
  download_url: string | null;
  modelo_usado: string;
  created_at: string;
}

// ============================================
// SSE Event Types
// ============================================

export interface SSEEventInicio {
  event: 'inicio';
  data: {
    sessao_id: number;
    total_jsons?: number;
  };
}

export interface SSEEventChunk {
  event: 'chunk';
  data: {
    texto: string;
  };
}

export interface SSEEventConcluido {
  event: 'concluido';
  data: {
    consolidacao_id: number | null;
    sugestoes: PieceSuggestion[];
  };
}

export interface SSEEventErro {
  event: 'erro';
  data: {
    mensagem: string;
  };
}

export type SSEEvent = SSEEventInicio | SSEEventChunk | SSEEventConcluido | SSEEventErro;

// ============================================
// Application State Types
// ============================================

export interface AppState {
  token: string | null;
  userName: string;
  sessaoId: number | null;
  status: 'idle' | 'processando' | 'consolidando' | 'chatbot' | 'finalizado' | 'erro';
  currentSession: SessionResponse | null;
  consolidation: ConsolidationResponse | null;
  documents: DocumentResponse[];
  chatHistory: ChatMessageResponse[];
  generatedPieces: GeneratedPieceResponse[];
  error: string | null;
}

export interface ProcessStep {
  id: string;
  label: string;
  icon: string;
  status: StepStatus;
  message: string;
  duration?: number;
}

// ============================================
// Component Props Types
// ============================================

export interface HistoryDrawerProps {
  sessions: SessionResponse[];
  isOpen: boolean;
  onClose: () => void;
  onSelectSession: (sessionId: number) => void;
  currentSessionId: number | null;
  searchQuery: string;
  onSearchChange: (query: string) => void;
  statusFilter: SessionStatus | 'all';
  onStatusFilterChange: (status: SessionStatus | 'all') => void;
}

export interface ProcessStepsProps {
  steps: ProcessStep[];
  currentStep: number;
  totalProgress: number;
}

export interface ProcessSummaryProps {
  consolidation: ConsolidationResponse | null;
  processData: ProcessData | null;
  suggestions: PieceSuggestion[];
  onSuggestionClick: (suggestion: PieceSuggestion) => void;
  isLoading: boolean;
  streamingContent: string;
}

export interface JsonViewerProps {
  data: unknown;
  title?: string;
  collapsed?: boolean;
  searchEnabled?: boolean;
  maxHeight?: string;
}

export interface JsonViewerState {
  expandedPaths: Set<string>;
  searchQuery: string;
  matchingPaths: Set<string>;
}

// ============================================
// Utility Types
// ============================================

export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonArray | JsonObject;
export interface JsonArray extends Array<JsonValue> {}
export interface JsonObject { [key: string]: JsonValue; }

export interface ApiError {
  detail: string;
  status?: number;
}

// ============================================
// History Filter Types
// ============================================

export interface HistoryFilters {
  search: string;
  status: SessionStatus | 'all';
  dateRange?: {
    start: Date;
    end: Date;
  };
}
