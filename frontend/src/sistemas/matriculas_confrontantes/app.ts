/**
 * Sistema de Analise Documental - Matriculas Confrontantes
 * TypeScript Application - Conectado ao Backend FastAPI
 */

export {};

// ============================================
// Types
// ============================================

interface FileItem {
  id: string | number;
  name: string;
  type: 'pdf' | 'image';
  size: string;
  date: string;
  analyzed?: boolean;
  selected?: boolean;
}

interface FolderItem {
  name: string;
  icon: string;
  expanded?: boolean;
  children?: FolderItem[];
}

interface LogEntry {
  time: string;
  status: 'success' | 'info' | 'warning' | 'error';
  message: string;
}

interface MatriculaEncontrada {
  numero?: string;
  lote?: string;
  quadra?: string;
  proprietarios?: string[];
  descricao?: string;
}

interface LoteConfrontante {
  identificador?: string;
  direcao?: string;
  tipo?: string;
  matricula_anexada?: string;
  proprietarios?: string[];
}

interface DocumentDetails {
  analise_id?: number;
  matricula_principal?: string;
  confidence?: number;
  confrontacao_completa?: boolean | null;
  matriculas_encontradas?: MatriculaEncontrada[];
  lotes_confrontantes?: LoteConfrontante[];
  proprietarios_identificados?: Record<string, string[]>;
  matriculas_confrontantes?: string[];
  matriculas_nao_confrontantes?: string[];
  lotes_sem_matricula?: string[];
  reasoning?: string;
}

interface AnalysisRecord {
  id: number;
  [key: string]: unknown;
}

interface AppConfig {
  version: string;
  model: string;
  hasApiKey: boolean;
}

interface AppState {
  files: FileItem[];
  folders: FolderItem[];
  registros: AnalysisRecord[];
  logs: LogEntry[];
  selectedFileId: string | null;
  selectedFileIds: string[];
  documentDetails: DocumentDetails | null;
  currentAnaliseId: number | null;
  currentGrupoId: number | null;
  config: AppConfig;
  pollingIntervals: Record<string, ReturnType<typeof setInterval>>;
}

interface AnalysisStatusResponse {
  processing: boolean;
  has_result: boolean;
}

interface BatchStatusResponse {
  status: 'concluido' | 'erro' | 'processando';
  total_arquivos?: number;
}

interface ReportResponse {
  success: boolean;
  report?: string;
  payload?: string;
  error?: string;
}

interface FeedbackResponse {
  success?: boolean;
  has_feedback?: boolean;
  avaliacao?: string;
}

// ============================================
// Utility Functions
// ============================================

/**
 * Escapa caracteres HTML para prevenir XSS
 */
function escapeHtml(text: string | null | undefined): string {
  if (!text) return '';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// ============================================
// API Configuration
// ============================================

const API_BASE = '/matriculas/api';

// Funcao para obter token de autenticacao
function getAuthToken(): string | null {
  return localStorage.getItem('access_token');
}

// Verifica se esta autenticado, redireciona para login se nao
function checkAuth(): boolean {
  const token = getAuthToken();
  if (!token) {
    window.location.href = '/login';
    return false;
  }
  return true;
}

// Funcao de logout
function logout(): void {
  localStorage.removeItem('access_token');
  window.location.href = '/login';
}

// Estado da aplicacao
const appState: AppState = {
  files: [],
  folders: [],
  registros: [],
  logs: [],
  selectedFileId: null,
  selectedFileIds: [],
  documentDetails: null,
  currentAnaliseId: null,
  currentGrupoId: null,
  config: {
    version: '1.0.0',
    model: 'google/gemini-3-flash-preview',
    hasApiKey: false
  },
  pollingIntervals: {}
};

// ============================================
// API Functions
// ============================================

async function api<T = unknown>(endpoint: string, options: RequestInit = {}): Promise<T | null> {
  if (!checkAuth()) return null;

  const token = getAuthToken();

  try {
    const response = await fetch(`${API_BASE}${endpoint}`, {
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
        ...options.headers
      },
      ...options
    });

    if (response.status === 401) {
      localStorage.removeItem('access_token');
      window.location.href = '/login';
      return null;
    }

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    console.error(`API Error [${endpoint}]:`, error);
    throw error;
  }
}

async function loadFiles(): Promise<void> {
  try {
    const files = await api<FileItem[]>('/files');
    appState.files = files || [];
    renderFileList();
  } catch {
    appState.files = [];
    renderFileList();
  }
}

async function loadAnalyses(): Promise<void> {
  try {
    const response = await api<AnalysisRecord[] | { error: string }>('/analyses');
    console.log('[loadAnalyses] Resposta da API:', response);

    if (Array.isArray(response)) {
      appState.registros = response;
      console.log('[loadAnalyses] Analises carregadas:', appState.registros.length);
    } else if (response && 'error' in response) {
      console.error('[loadAnalyses] Erro retornado pela API:', response.error);
      appState.registros = [];
    } else {
      console.warn('[loadAnalyses] Resposta inesperada:', response);
      appState.registros = [];
    }

    renderRecordsTable();
  } catch {
    appState.registros = [];
    renderRecordsTable();
  }
}

async function loadLogs(): Promise<void> {
  try {
    const logs = await api<LogEntry[]>('/logs');
    appState.logs = logs || [];
    renderSystemLogs();
  } catch {
    console.error('Erro ao carregar logs');
  }
}

async function loadDocumentDetails(fileId: string): Promise<void> {
  appState.selectedFileId = fileId;

  const file = appState.files.find(f => String(f.id) === String(fileId));
  if (file) {
    const docNameEl = document.getElementById('current-doc-name');
    if (docNameEl) {
      docNameEl.textContent = file.name;
    }

    loadPdfViewer(fileId, file.type);
  }

  try {
    const result = await api<DocumentDetails>(`/resultado/${fileId}`);
    appState.documentDetails = result;
    renderExtractedDataPanel();
    await generateAndShowReport();
  } catch {
    appState.documentDetails = null;
    renderExtractedDataPanel();
  }
}

interface ViewerElement extends HTMLElement {
  _currentBlobUrl?: string;
}

async function loadPdfViewer(fileId: string, fileType: string): Promise<void> {
  const viewer = document.getElementById('pdf-viewer') as ViewerElement | null;
  if (!viewer) return;

  const token = getAuthToken();
  const file = appState.files.find(f => String(f.id) === String(fileId));

  if (!file) {
    viewer.innerHTML = `
      <div class="text-center text-gray-400 py-20">
        <i class="fas fa-file-pdf text-6xl mb-4 text-gray-300"></i>
        <p class="text-lg">Documento ja analisado</p>
        <p class="text-sm mt-2">O PDF foi removido apos a analise.</p>
        <p class="text-xs mt-1 text-gray-500">Os dados extraidos estao disponiveis no relatorio.</p>
      </div>
    `;
    return;
  }

  viewer.innerHTML = `
    <div class="text-center text-gray-400 py-20">
      <i class="fas fa-spinner fa-spin text-4xl mb-4"></i>
      <p class="text-lg">Carregando documento...</p>
    </div>
  `;

  try {
    const response = await fetch(`${API_BASE}/files/${fileId}/view`, {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const blob = await response.blob();
    const blobUrl = URL.createObjectURL(blob);

    if (viewer._currentBlobUrl) {
      URL.revokeObjectURL(viewer._currentBlobUrl);
    }
    viewer._currentBlobUrl = blobUrl;

    if (fileType === 'pdf') {
      viewer.innerHTML = `
        <div class="w-full h-full flex flex-col">
          <object
            data="${blobUrl}#view=FitH"
            type="application/pdf"
            class="w-full flex-1 border-0"
            style="min-height: 600px;"
          >
            <div class="text-center text-gray-400 py-20">
              <i class="fas fa-file-pdf text-6xl mb-4 text-red-400"></i>
              <p class="text-lg mb-4">Nao foi possivel exibir o PDF no navegador</p>
              <button onclick="openPdfInNewTab('${fileId}')"
                class="px-6 py-3 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors">
                <i class="fas fa-external-link-alt mr-2"></i>Abrir PDF em nova aba
              </button>
            </div>
          </object>
          <div class="bg-gray-100 px-4 py-2 border-t flex justify-end">
            <button onclick="openPdfInNewTab('${fileId}')"
              class="text-sm text-blue-600 hover:text-blue-800 flex items-center gap-1">
              <i class="fas fa-external-link-alt"></i>Abrir em nova aba
            </button>
          </div>
        </div>
      `;
    } else {
      viewer.innerHTML = `
        <div class="flex items-center justify-center h-full w-full p-4">
          <img
            src="${blobUrl}"
            class="w-full h-auto object-contain rounded-lg shadow-lg"
            alt="Documento"
            style="max-height: 100%;"
          />
        </div>
      `;
    }
  } catch (error) {
    const err = error as Error;
    viewer.innerHTML = `
      <div class="text-center text-gray-400 py-20">
        <i class="fas fa-exclamation-triangle text-6xl mb-4 text-yellow-500"></i>
        <p class="text-lg mb-2">Erro ao carregar documento</p>
        <p class="text-sm text-gray-500 mb-4">${err.message || 'Tente novamente'}</p>
        <button onclick="openPdfInNewTab('${fileId}')"
          class="px-6 py-3 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors">
          <i class="fas fa-external-link-alt mr-2"></i>Abrir em nova aba
        </button>
      </div>
    `;
  }
}

async function openPdfInNewTab(fileId: string): Promise<void> {
  const token = getAuthToken();
  try {
    const response = await fetch(`${API_BASE}/files/${fileId}/view`, {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const blob = await response.blob();
    const blobUrl = URL.createObjectURL(blob);
    window.open(blobUrl, '_blank');

    setTimeout(() => URL.revokeObjectURL(blobUrl), 60000);
  } catch (error) {
    const err = error as Error;
    showToast('Erro ao abrir documento: ' + (err.message || 'Tente novamente'), 'error');
  }
}

async function loadConfig(): Promise<void> {
  try {
    const config = await api<AppConfig>('/config');
    if (config) {
      appState.config = config;
    }
    updateAnalysisStatus();
  } catch {
    console.error('Erro ao carregar configuracoes');
  }
}

function updateConfigUI(): void {
  updateAnalysisStatus();
}

async function uploadFile(file: File, replace: boolean = false): Promise<void> {
  console.log('[uploadFile] Iniciando upload:', file.name);

  if (!checkAuth()) {
    console.log('[uploadFile] Falha na autenticação');
    return;
  }

  const token = getAuthToken();
  const formData = new FormData();
  formData.append('file', file);

  try {
    const url = replace
      ? `${API_BASE}/files/upload?replace=true`
      : `${API_BASE}/files/upload`;

    console.log('[uploadFile] Enviando para:', url);

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`
      },
      body: formData
    });

    console.log('[uploadFile] Response status:', response.status);

    if (response.status === 401) {
      localStorage.removeItem('access_token');
      window.location.href = '/login';
      return;
    }

    const result = await response.json();
    console.log('[uploadFile] Resultado:', result);

    if (result.success) {
      await loadFiles();
      showToast(`Arquivo ${file.name} importado com sucesso!`, 'success');
    } else if (result.error === 'duplicate') {
      showDuplicateConfirmModal(file, result.message);
    } else {
      showToast(result.error || 'Erro ao importar arquivo', 'error');
    }
  } catch (error) {
    console.error('[uploadFile] Erro:', error);
    showToast('Erro de conexao ao importar arquivo', 'error');
  }
}

function showDuplicateConfirmModal(file: File, message: string): void {
  const modal = document.createElement('div');
  modal.id = 'duplicate-confirm-modal';
  modal.className = 'fixed inset-0 z-50 flex items-center justify-center bg-black/50';

  modal.innerHTML = `
    <div class="bg-white rounded-xl shadow-2xl max-w-md w-full mx-4 overflow-hidden">
      <div class="bg-gradient-to-r from-yellow-500 to-orange-500 px-6 py-4">
        <div class="flex items-center gap-3">
          <i class="fas fa-exclamation-triangle text-white text-2xl"></i>
          <h3 class="text-lg font-semibold text-white">Arquivo Duplicado</h3>
        </div>
      </div>
      <div class="p-6">
        <p class="text-gray-700 mb-4">${message || 'Ja existe um arquivo com este nome.'}</p>
        <p class="text-sm text-gray-500 mb-6">
          Se substituir, a analise anterior sera perdida.
        </p>
        <div class="flex gap-3">
          <button onclick="confirmReplaceFile()"
            class="flex-1 px-4 py-2 bg-orange-500 text-white rounded-lg hover:bg-orange-600 transition-colors font-medium">
            <i class="fas fa-sync-alt mr-2"></i>Substituir
          </button>
          <button onclick="cancelReplaceFile()"
            class="flex-1 px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 transition-colors font-medium">
            Cancelar
          </button>
        </div>
      </div>
    </div>
  `;

  (window as WindowWithPendingFile).pendingReplaceFile = file;
  document.body.appendChild(modal);
}

interface WindowWithPendingFile extends Window {
  pendingReplaceFile?: File;
  currentReportText?: string;
  currentReportPayload?: string;
  authToken?: string;
}

async function confirmReplaceFile(): Promise<void> {
  const modal = document.getElementById('duplicate-confirm-modal');
  if (modal) modal.remove();

  const win = window as WindowWithPendingFile;
  if (win.pendingReplaceFile) {
    await uploadFile(win.pendingReplaceFile, true);
    win.pendingReplaceFile = undefined;
  }
}

function cancelReplaceFile(): void {
  const modal = document.getElementById('duplicate-confirm-modal');
  if (modal) modal.remove();
  (window as WindowWithPendingFile).pendingReplaceFile = undefined;
  showToast('Upload cancelado', 'info');
}

async function apiDeleteFile(fileId: string): Promise<void> {
  try {
    await api(`/files/${fileId}`, { method: 'DELETE' });

    if (String(appState.selectedFileId) === String(fileId)) {
      appState.selectedFileId = null;
      appState.documentDetails = null;

      const viewer = document.getElementById('pdf-viewer');
      if (viewer) {
        viewer.innerHTML = `
          <div class="text-center text-gray-400 py-20">
            <i class="fas fa-file-pdf text-6xl mb-4"></i>
            <p class="text-lg">Visualizacao do Documento</p>
            <p class="text-sm mt-2">Selecione um arquivo para visualizar</p>
          </div>
        `;
      }

      const docNameEl = document.getElementById('current-doc-name');
      if (docNameEl) {
        docNameEl.textContent = 'Nenhum documento';
      }

      const reportView = document.getElementById('report-view');
      if (reportView) {
        reportView.innerHTML = `
          <div class="text-center text-gray-400 py-12">
            <i class="fas fa-file-alt text-5xl mb-4"></i>
            <p class="text-lg">Relatorio de Analise</p>
            <p class="text-sm mt-2">Analise um documento para gerar o relatorio automaticamente</p>
          </div>
        `;
      }
    }

    await loadFiles();
    await loadAnalyses();
    await loadLogs();

    updateAnalysisStatus();
    showToast('Arquivo excluido com sucesso', 'warning');
  } catch {
    showToast('Erro ao excluir arquivo', 'error');
  }
}

async function apiDeleteRecord(recordId: string): Promise<void> {
  try {
    await api(`/registros/${recordId}`, { method: 'DELETE' });
    await loadAnalyses();
    await loadLogs();
    showToast('Registro excluido com sucesso', 'warning');
  } catch {
    showToast('Erro ao excluir registro', 'error');
  }
}

async function apiClearLogs(): Promise<void> {
  try {
    await api('/logs', { method: 'DELETE' });
    await loadLogs();
  } catch {
    console.error('Erro ao limpar logs');
  }
}

async function analisarDocumento(fileId: string, forceReanalysis: boolean = false): Promise<void> {
  const matriculaInput = document.getElementById('matricula-principal-input') as HTMLInputElement | null;
  const matriculaPrincipal = matriculaInput ? matriculaInput.value.trim() : '';

  if (!matriculaPrincipal) {
    showToast('Por favor, informe a Matricula Principal', 'warning');
    if (matriculaInput) matriculaInput.focus();
    return;
  }

  try {
    showToast('Verificando analise...', 'info');
    let url = forceReanalysis ? `/analisar/${fileId}?force=true` : `/analisar/${fileId}`;
    url += (url.includes('?') ? '&' : '?') + `matricula_principal=${encodeURIComponent(matriculaPrincipal)}`;

    const result = await api<{ success: boolean; cached?: boolean; error?: string }>(url, { method: 'POST' });

    if (result?.success) {
      if (result.cached) {
        showToast('Analise ja realizada, carregando...', 'info');
        await loadAnalysisResult(fileId);
      } else {
        showToast('Iniciando analise do documento...', 'info');
        showProcessingModal(fileId);
        startAnalysisPolling(fileId);
      }
    } else {
      showToast(result?.error || 'Erro ao iniciar analise', 'error');
    }
  } catch {
    showToast('Erro ao analisar documento', 'error');
  }
}

async function loadAnalysisResult(fileId: string): Promise<void> {
  try {
    const result = await api<DocumentDetails>(`/resultado/${fileId}`);
    if (result) {
      appState.documentDetails = result;
      appState.currentAnaliseId = result.analise_id || null;
      await generateAndShowReport();
      await loadAnalyses();
      showToast('Analise carregada com sucesso!', 'success');
    }
  } catch {
    showToast('Erro ao carregar analise', 'error');
  }
}

function showProcessingModal(fileId: string): void {
  const existingModal = document.getElementById('processing-modal');
  if (existingModal) existingModal.remove();

  const file = appState.files.find(f => String(f.id) === String(fileId));

  const modal = document.createElement('div');
  modal.id = 'processing-modal';
  modal.className = 'fixed inset-0 z-50 flex items-center justify-center bg-black/50';
  modal.innerHTML = `
    <div class="bg-white rounded-xl shadow-2xl max-w-md w-full m-4 overflow-hidden">
      <div class="bg-gradient-to-r from-primary-500 to-accent-500 px-6 py-4">
        <h2 class="text-lg font-semibold text-white flex items-center gap-2">
          <i class="fas fa-brain"></i>
          Analise em Andamento
        </h2>
      </div>
      <div class="p-6">
        <div class="flex flex-col items-center text-center">
          <div class="relative mb-6">
            <div class="w-20 h-20 rounded-full border-4 border-primary-200 border-t-primary-500 animate-spin"></div>
            <div class="absolute inset-0 flex items-center justify-center">
              <i class="fas fa-file-pdf text-2xl text-primary-500"></i>
            </div>
          </div>
          <h3 class="text-lg font-medium text-gray-800 mb-2">Processando Documento</h3>
          <p class="text-sm text-gray-500 mb-1">${file?.name || 'Documento'}</p>
          <p class="text-xs text-gray-400 mb-4" id="processing-status">Enviando para analise da IA...</p>

          <div class="w-full bg-gray-200 rounded-full h-2 mb-4">
            <div class="bg-primary-500 h-2 rounded-full animate-pulse" style="width: 60%"></div>
          </div>

          <p class="text-xs text-gray-400 mb-6">
            <i class="fas fa-info-circle"></i>
            Este processo pode levar alguns segundos dependendo do tamanho do documento
          </p>
        </div>

        <button onclick="cancelAnalysis('${fileId}')" class="w-full px-4 py-3 text-sm text-red-600 bg-red-50 rounded-lg hover:bg-red-100 transition-colors flex items-center justify-center gap-2 font-medium">
          <i class="fas fa-times-circle"></i>
          Interromper Processamento
        </button>
      </div>
    </div>
  `;

  document.body.appendChild(modal);
}

function closeProcessingModal(): void {
  const modal = document.getElementById('processing-modal');
  if (modal) modal.remove();
}

function cancelAnalysis(fileId: string): void {
  if (appState.pollingIntervals[fileId]) {
    clearInterval(appState.pollingIntervals[fileId]);
    delete appState.pollingIntervals[fileId];
  }

  closeProcessingModal();

  const statusEl = document.getElementById('analysis-status');
  if (statusEl) {
    statusEl.innerHTML = '<i class="fas fa-times-circle text-red-500"></i> Analise cancelada';
    statusEl.className = 'text-xs text-red-600 text-center';
  }

  showToast('Analise interrompida pelo usuario', 'warning');

  setTimeout(() => {
    if (statusEl) {
      statusEl.innerHTML = '<i class="fas fa-info-circle text-gray-400"></i> Selecione um documento';
      statusEl.className = 'text-xs text-gray-600 text-center';
    }
  }, 3000);
}

function startAnalysisPolling(fileId: string): void {
  if (appState.pollingIntervals[fileId]) {
    clearInterval(appState.pollingIntervals[fileId]);
  }

  const statusEl = document.getElementById('analysis-status');
  if (statusEl) {
    statusEl.innerHTML = '<i class="fas fa-spinner fa-spin text-blue-500"></i> Analisando...';
    statusEl.className = 'text-xs text-blue-600 text-center';
  }

  appState.pollingIntervals[fileId] = setInterval(async () => {
    try {
      const status = await api<AnalysisStatusResponse>(`/analisar/${fileId}/status`);
      console.log('[Polling] Status:', status);

      const processingStatus = document.getElementById('processing-status');
      if (processingStatus) {
        processingStatus.textContent = 'Analisando com IA...';
      }

      if (status && !status.processing && status.has_result) {
        clearInterval(appState.pollingIntervals[fileId]);
        delete appState.pollingIntervals[fileId];

        closeProcessingModal();

        try {
          const resultado = await api<DocumentDetails>(`/resultado/${fileId}`);
          console.log('[Analise] Resultado:', resultado);

          if (resultado) {
            appState.documentDetails = resultado;
            appState.currentAnaliseId = resultado.analise_id || null;

            renderExtractedDataPanel();
            await loadFiles();
            await loadAnalyses();
            await generateAndShowReport();

            showToast('Analise concluida com sucesso!', 'success');
            addLog('success', 'Analise concluida: ' + (resultado.matricula_principal || 'N/A'));

            if (statusEl) {
              statusEl.innerHTML = '<i class="fas fa-check-circle text-green-500"></i> Analise concluida';
              statusEl.className = 'text-xs text-green-600 text-center';
            }
          }
        } catch (e) {
          console.error('[Analise] Erro ao carregar resultado:', e);
        }

        await loadLogs();
      }
    } catch (error) {
      console.error('Erro no polling:', error);
    }
  }, 2000);

  setTimeout(() => {
    if (appState.pollingIntervals[fileId]) {
      clearInterval(appState.pollingIntervals[fileId]);
      delete appState.pollingIntervals[fileId];
      closeProcessingModal();
      showToast('Analise demorou muito. Verifique os logs.', 'warning');

      const statusEl = document.getElementById('analysis-status');
      if (statusEl) {
        statusEl.innerHTML = '<i class="fas fa-exclamation-triangle text-yellow-500"></i> Timeout na analise';
        statusEl.className = 'text-xs text-yellow-600 text-center mt-2';
      }
    }
  }, 300000);
}

async function generateAndShowReport(): Promise<void> {
  const reportView = document.getElementById('report-view');

  if (!reportView) return;

  reportView.innerHTML = `
    <div class="text-center text-gray-400 py-12">
      <i class="fas fa-spinner fa-spin text-4xl mb-4 text-primary-500"></i>
      <p class="text-lg">Gerando Relatorio...</p>
      <p class="text-sm mt-2">Aguarde enquanto a IA processa os dados</p>
    </div>
  `;

  try {
    const result = await api<ReportResponse>('/relatorio/gerar', { method: 'POST' });

    if (result?.success && result.report) {
      const win = window as WindowWithPendingFile;
      win.currentReportText = result.report;
      win.currentReportPayload = result.payload;

      reportView.innerHTML = `
        <div class="prose prose-sm max-w-none">
          ${renderMarkdown(result.report)}
        </div>

        <!-- Secao de Feedback Inline -->
        <div id="feedback-section-inline" class="mt-6 bg-gradient-to-r from-blue-50 to-indigo-50 rounded-xl border border-blue-200 p-4">
          <h4 class="font-semibold text-gray-700 mb-3 flex items-center gap-2">
            <i class="fas fa-comment-dots text-blue-500"></i>
            Avalie a Analise da IA
          </h4>
          <p class="text-sm text-gray-600 mb-4">Sua avaliacao nos ajuda a melhorar o sistema.</p>

          <div id="feedback-buttons-inline" class="grid grid-cols-2 md:grid-cols-4 gap-3">
            <button onclick="enviarFeedbackMatricula('correto')"
              class="px-4 py-3 bg-green-100 text-green-700 rounded-lg hover:bg-green-200 transition-colors flex flex-col items-center gap-1 border-2 border-transparent hover:border-green-400">
              <i class="fas fa-check-circle text-xl"></i>
              <span class="text-sm font-medium">Correta</span>
            </button>
            <button onclick="enviarFeedbackMatricula('parcial')"
              class="px-4 py-3 bg-yellow-100 text-yellow-700 rounded-lg hover:bg-yellow-200 transition-colors flex flex-col items-center gap-1 border-2 border-transparent hover:border-yellow-400">
              <i class="fas fa-adjust text-xl"></i>
              <span class="text-sm font-medium">Parcialmente</span>
            </button>
            <button onclick="enviarFeedbackMatricula('incorreto')"
              class="px-4 py-3 bg-red-100 text-red-700 rounded-lg hover:bg-red-200 transition-colors flex flex-col items-center gap-1 border-2 border-transparent hover:border-red-400">
              <i class="fas fa-times-circle text-xl"></i>
              <span class="text-sm font-medium">Incorreta</span>
            </button>
            <button onclick="enviarFeedbackMatricula('erro_ia')"
              class="px-4 py-3 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors flex flex-col items-center gap-1 border-2 border-transparent hover:border-gray-400">
              <i class="fas fa-exclamation-triangle text-xl"></i>
              <span class="text-sm font-medium">Erro/Nao gerou</span>
            </button>
          </div>

          <div id="feedback-enviado-inline" class="hidden text-center py-4">
            <i class="fas fa-check-circle text-green-500 text-3xl mb-2"></i>
            <p class="text-green-700 font-medium">Obrigado pelo seu feedback!</p>
            <p id="feedback-enviado-tipo-inline" class="text-sm text-gray-500"></p>
          </div>
        </div>
      `;

      const reportActions = document.getElementById('report-actions');
      if (reportActions) {
        (reportActions as HTMLElement).style.display = 'flex';
      }

      if (appState.currentAnaliseId) {
        verificarFeedbackInline(appState.currentAnaliseId);
      }
    } else {
      reportView.innerHTML = `
        <div class="text-center text-red-400 py-12">
          <i class="fas fa-exclamation-circle text-4xl mb-4"></i>
          <p class="text-lg">Erro ao gerar relatorio</p>
          <p class="text-sm mt-2">${result?.error || 'Tente novamente'}</p>
        </div>
      `;
    }
  } catch {
    reportView.innerHTML = `
      <div class="text-center text-red-400 py-12">
        <i class="fas fa-exclamation-circle text-4xl mb-4"></i>
        <p class="text-lg">Erro de conexao</p>
        <p class="text-sm mt-2">Nao foi possivel gerar o relatorio</p>
      </div>
    `;
  }
}

function showAnalysisResultModal(resultado: DocumentDetails): void {
  console.log('[Analise] Resultado processado:', resultado.matricula_principal);
}

async function gerarRelatorio(): Promise<void> {
  await generateAndShowReport();
}

function copyReport(): void {
  const win = window as WindowWithPendingFile;
  if (win.currentReportText) {
    navigator.clipboard.writeText(win.currentReportText);
    showToast('Relatorio copiado!', 'success');
  }
}

async function downloadReportDocx(analiseId: number | null = null): Promise<void> {
  const idToUse = analiseId || appState.currentAnaliseId;

  try {
    showToast('Gerando documento DOCX...', 'info');

    let url = `${API_BASE}/relatorio/download`;
    if (idToUse) {
      url += `?analise_id=${idToUse}`;
    }

    const win = window as WindowWithPendingFile;
    const response = await fetch(url, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${win.authToken || getAuthToken()}`
      }
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Erro desconhecido' }));
      throw new Error(error.detail || 'Erro ao gerar DOCX');
    }

    const blob = await response.blob();

    const contentDisposition = response.headers.get('Content-Disposition');
    let filename = 'relatorio_matriculas_confrontantes.docx';
    if (contentDisposition) {
      const match = contentDisposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
      if (match && match[1]) {
        filename = match[1].replace(/['"]/g, '');
      }
    }

    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(link.href);

    showToast('Download concluido!', 'success');
  } catch (error) {
    const err = error as Error;
    console.error('Erro ao baixar DOCX:', err);
    showToast(`Erro ao gerar DOCX: ${err.message}`, 'error');
  }
}

function printReportPdf(): void {
  const win = window as WindowWithPendingFile;
  if (!win.currentReportText) {
    showToast('Nenhum relatorio para imprimir', 'warning');
    return;
  }

  const printWindow = window.open('', '_blank');
  if (!printWindow) {
    showToast('Bloqueador de popup ativo', 'error');
    return;
  }

  printWindow.document.write(`
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <title>Relatorio de Analise - Matriculas Confrontantes</title>
      <style>
        @media print {
          @page { margin: 2cm; }
        }
        body {
          font-family: 'Times New Roman', serif;
          font-size: 12pt;
          line-height: 1.6;
          max-width: 21cm;
          margin: 0 auto;
          padding: 20px;
        }
        h1 {
          font-size: 18pt;
          color: #1e3a5f;
          border-bottom: 2px solid #1e3a5f;
          padding-bottom: 10px;
          text-align: center;
        }
        h2 { font-size: 14pt; color: #2563eb; margin-top: 20px; }
        h3 { font-size: 12pt; color: #374151; }
        p { margin: 10px 0; text-align: justify; }
        ul, ol { margin: 10px 0; padding-left: 30px; }
        li { margin: 5px 0; }
        strong { color: #1f2937; }
        .header { text-align: center; margin-bottom: 30px; }
        .footer {
          margin-top: 40px;
          padding-top: 20px;
          border-top: 1px solid #ccc;
          font-size: 10pt;
          color: #666;
          text-align: center;
        }
      </style>
    </head>
    <body>
      <div class="header">
        <h1>Relatorio de Analise</h1>
        <p>Sistema de Matriculas Confrontantes</p>
        <p>Data: ${new Date().toLocaleDateString('pt-BR')}</p>
      </div>
      ${renderMarkdown(win.currentReportText)}
      <div class="footer">
        Documento gerado automaticamente pelo Sistema de Analise de Matriculas Confrontantes - PGE-MS
      </div>
    </body>
    </html>
  `);
  printWindow.document.close();

  printWindow.onload = () => {
    printWindow.print();
  };

  showToast('Abrindo impressao...', 'info');
}

function showPayload(): void {
  const win = window as WindowWithPendingFile;
  if (win.currentReportPayload) {
    const payloadModal = document.createElement('div');
    payloadModal.id = 'payload-modal';
    payloadModal.className = 'fixed inset-0 z-[60] flex items-center justify-center bg-black/50';
    payloadModal.innerHTML = `
      <div class="bg-white rounded-xl shadow-2xl max-w-3xl w-full max-h-[80vh] overflow-hidden flex flex-col m-4">
        <div class="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <h2 class="text-lg font-semibold text-gray-800">Dados Estruturados (JSON)</h2>
          <button onclick="document.getElementById('payload-modal').remove()" class="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors">
            <i class="fas fa-times"></i>
          </button>
        </div>
        <div class="flex-1 overflow-y-auto p-6">
          <pre class="text-xs bg-gray-50 p-4 rounded-lg overflow-x-auto">${escapeHtml(win.currentReportPayload)}</pre>
        </div>
      </div>
    `;
    document.body.appendChild(payloadModal);
  }
}

// ============================================
// Feedback Functions
// ============================================

async function enviarFeedbackMatricula(avaliacao: string): Promise<void> {
  if (!appState.currentAnaliseId) {
    showToast('Nenhuma analise para avaliar', 'warning');
    return;
  }

  let comentario: string | null = null;
  if (avaliacao === 'incorreto' || avaliacao === 'parcial') {
    comentario = prompt('Por favor, descreva brevemente o que estava incorreto (opcional):');
  }

  try {
    const result = await api<{ success: boolean }>('/feedback', {
      method: 'POST',
      body: JSON.stringify({
        analise_id: appState.currentAnaliseId,
        avaliacao: avaliacao,
        comentario: comentario
      })
    });

    if (result && result.success) {
      const tipoTexto: Record<string, string> = {
        'correto': 'Analise marcada como correta',
        'parcial': 'Analise marcada como parcialmente correta',
        'incorreto': 'Analise marcada como incorreta',
        'erro_ia': 'Reportado como erro da IA'
      };

      const buttonsModal = document.getElementById('feedback-buttons-matriculas');
      const enviadoModal = document.getElementById('feedback-enviado-matriculas');
      if (buttonsModal) buttonsModal.classList.add('hidden');
      if (enviadoModal) enviadoModal.classList.remove('hidden');
      const tipoElModal = document.getElementById('feedback-enviado-tipo-matriculas');
      if (tipoElModal) tipoElModal.textContent = tipoTexto[avaliacao] || '';

      const buttonsInline = document.getElementById('feedback-buttons-inline');
      const enviadoInline = document.getElementById('feedback-enviado-inline');
      if (buttonsInline) buttonsInline.classList.add('hidden');
      if (enviadoInline) enviadoInline.classList.remove('hidden');
      const tipoElInline = document.getElementById('feedback-enviado-tipo-inline');
      if (tipoElInline) tipoElInline.textContent = tipoTexto[avaliacao] || '';

      showToast('Feedback registrado!', 'success');
    } else {
      showToast('Erro ao enviar feedback', 'error');
    }
  } catch {
    showToast('Erro ao enviar feedback', 'error');
  }
}

async function verificarFeedbackInline(analiseId: number): Promise<void> {
  try {
    const result = await api<FeedbackResponse>(`/feedback/${analiseId}`);

    const buttons = document.getElementById('feedback-buttons-inline');
    const enviado = document.getElementById('feedback-enviado-inline');

    if (result && result.has_feedback) {
      if (buttons) buttons.classList.add('hidden');
      if (enviado) enviado.classList.remove('hidden');

      const tipoTexto: Record<string, string> = {
        'correto': 'Analise marcada como correta',
        'parcial': 'Analise marcada como parcialmente correta',
        'incorreto': 'Analise marcada como incorreta',
        'erro_ia': 'Reportado como erro da IA'
      };
      const tipoEl = document.getElementById('feedback-enviado-tipo-inline');
      if (tipoEl && result.avaliacao) tipoEl.textContent = tipoTexto[result.avaliacao] || '';
    } else {
      if (buttons) buttons.classList.remove('hidden');
      if (enviado) enviado.classList.add('hidden');
    }
  } catch {
    const buttons = document.getElementById('feedback-buttons-inline');
    const enviado = document.getElementById('feedback-enviado-inline');
    if (buttons) buttons.classList.remove('hidden');
    if (enviado) enviado.classList.add('hidden');
  }
}

function renderMarkdown(text: string): string {
  return text
    .replace(/^### (.*$)/gim, '<h3 class="text-lg font-semibold mt-4 mb-2">$1</h3>')
    .replace(/^## (.*$)/gim, '<h2 class="text-xl font-bold mt-6 mb-3 text-primary-700">$1</h2>')
    .replace(/^# (.*$)/gim, '<h1 class="text-2xl font-bold mt-6 mb-4 text-primary-800">$1</h1>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
    .replace(/^- (.*$)/gim, '<li class="ml-4">$1</li>')
    .replace(/^• (.*$)/gim, '<li class="ml-4">$1</li>')
    .replace(/\n/gim, '<br>');
}

// ============================================
// Render Functions
// ============================================

function renderFileList(): void {
  const container = document.getElementById('file-list');
  if (!container) return;

  const files = appState.files;

  if (!files || files.length === 0) {
    container.innerHTML = `
      <div class="text-center py-8 text-gray-400">
        <i class="fas fa-folder-open text-4xl mb-2"></i>
        <p class="text-sm">Nenhum arquivo importado</p>
        <p class="text-xs mt-1">Clique em "Importar Documentos"</p>
      </div>
    `;
    return;
  }

  container.innerHTML = files.map(file => {
    const isSelected = appState.selectedFileIds.includes(String(file.id));
    const isMultiSelect = appState.selectedFileIds.length > 1;
    return `
    <div class="file-item group p-3 rounded-lg cursor-pointer transition-all ${isSelected ? (isMultiSelect ? 'bg-purple-50 border border-purple-200' : 'bg-primary-50 border border-primary-200') : 'hover:bg-gray-50 border border-transparent'}"
         onclick="selectFile('${file.id}', event)">
      <div class="flex items-start gap-3">
        <div class="flex-shrink-0 w-10 h-10 rounded-lg ${file.type === 'pdf' ? 'bg-red-100' : 'bg-blue-100'} flex items-center justify-center relative">
          <i class="fas ${file.type === 'pdf' ? 'fa-file-pdf text-red-500' : 'fa-image text-blue-500'}"></i>
          ${file.analyzed ? '<span class="absolute -top-1 -right-1 w-4 h-4 bg-green-500 rounded-full flex items-center justify-center"><i class="fas fa-check text-white text-xs"></i></span>' : ''}
          ${isSelected && isMultiSelect ? '<span class="absolute -bottom-1 -left-1 w-5 h-5 bg-purple-500 rounded-full flex items-center justify-center text-white text-xs font-bold">' + (appState.selectedFileIds.indexOf(String(file.id)) + 1) + '</span>' : ''}
        </div>
        <div class="flex-1 min-w-0">
          <p class="text-sm font-medium text-gray-800 truncate">${escapeHtml(file.name)}</p>
          <p class="text-xs text-gray-500">${escapeHtml(file.size)} - ${escapeHtml(file.date)}</p>
          ${file.analyzed ? '<span class="text-xs text-green-600"><i class="fas fa-check-circle"></i> Analisado</span>' : ''}
        </div>
        <div class="flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
          <button class="p-1 text-gray-400 hover:text-red-500 transition-colors" onclick="event.stopPropagation(); deleteFile('${file.id}')" title="Excluir">
            <i class="fas fa-trash-alt text-xs"></i>
          </button>
        </div>
      </div>
    </div>
  `;
  }).join('');
}

function renderExtractedDataPanel(): void {
  const container = document.getElementById('extracted-data-panel');
  if (!container) return;

  const data = appState.documentDetails;

  if (!data || !data.matriculas_encontradas) {
    container.innerHTML = `
      <div class="text-center text-gray-400 py-8">
        <i class="fas fa-file-alt text-3xl mb-2"></i>
        <p class="text-sm">Selecione e analise um documento para ver os dados extraidos</p>
      </div>
    `;
    return;
  }

  const matriculasHtml = (data.matriculas_encontradas || []).map(mat => `
    <tr class="border-b border-gray-100 hover:bg-gray-50 text-xs">
      <td class="px-2 py-1.5 font-medium text-primary-600">${escapeHtml(mat.numero || 'N/A')}</td>
      <td class="px-2 py-1.5">${escapeHtml(mat.lote || '-')}</td>
      <td class="px-2 py-1.5">${escapeHtml(mat.quadra || '-')}</td>
      <td class="px-2 py-1.5 truncate max-w-[150px]" title="${escapeHtml((mat.proprietarios || []).join(', '))}">${escapeHtml((mat.proprietarios || []).join(', ') || 'N/A')}</td>
    </tr>
  `).join('') || '<tr><td colspan="4" class="px-2 py-3 text-center text-gray-400 text-xs">Nenhuma matricula</td></tr>';

  const lotesHtml = (data.lotes_confrontantes || []).map(lote => `
    <tr class="border-b border-gray-100 hover:bg-gray-50 text-xs">
      <td class="px-2 py-1.5">${escapeHtml(lote.identificador || 'N/A')}</td>
      <td class="px-2 py-1.5">${escapeHtml(lote.direcao ? lote.direcao.toUpperCase() : '-')}</td>
      <td class="px-2 py-1.5">${escapeHtml(lote.tipo || '-')}</td>
      <td class="px-2 py-1.5">${escapeHtml(lote.matricula_anexada || '-')}</td>
    </tr>
  `).join('') || '<tr><td colspan="4" class="px-2 py-3 text-center text-gray-400 text-xs">Nenhum confrontante</td></tr>';

  const confidence = data.confidence ? Math.round(data.confidence <= 1 ? data.confidence * 100 : data.confidence) : 0;
  const confColor = confidence >= 80 ? 'text-green-600' : confidence >= 60 ? 'text-yellow-600' : 'text-red-600';
  const confBg = confidence >= 80 ? 'bg-green-500' : confidence >= 60 ? 'bg-yellow-500' : 'bg-red-500';

  container.innerHTML = `
    <div class="space-y-3">
      <!-- Resumo compacto -->
      <div class="flex items-center gap-4 text-xs">
        <div class="flex items-center gap-2">
          <span class="text-gray-500">Matricula:</span>
          <span class="font-semibold text-primary-700">${escapeHtml(data.matricula_principal || 'N/A')}</span>
        </div>
        <div class="flex items-center gap-2">
          <span class="text-gray-500">Confianca:</span>
          <div class="flex items-center gap-1">
            <div class="w-12 h-1.5 bg-gray-200 rounded-full overflow-hidden">
              <div class="h-full ${confBg} rounded-full" style="width: ${confidence}%"></div>
            </div>
            <span class="${confColor} font-medium">${confidence}%</span>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <span class="text-gray-500">Confrontacao:</span>
          <span class="font-medium ${data.confrontacao_completa ? 'text-green-600' : data.confrontacao_completa === false ? 'text-red-600' : 'text-gray-400'}">
            ${data.confrontacao_completa === true ? '✓ Completa' : data.confrontacao_completa === false ? '✗ Incompleta' : 'N/A'}
          </span>
        </div>
      </div>

      <!-- Tabelas lado a lado -->
      <div class="grid grid-cols-2 gap-3">
        <!-- Matriculas -->
        <div class="bg-gray-50 rounded-lg overflow-hidden">
          <div class="px-2 py-1.5 bg-gray-100 border-b border-gray-200">
            <h4 class="font-medium text-gray-700 text-xs flex items-center gap-1">
              <i class="fas fa-file-alt text-primary-500"></i>
              Matriculas (${(data.matriculas_encontradas || []).length})
            </h4>
          </div>
          <div class="max-h-32 overflow-auto">
            <table class="w-full">
              <thead class="bg-gray-100 text-gray-600 text-xs sticky top-0">
                <tr>
                  <th class="px-2 py-1 text-left font-medium">N</th>
                  <th class="px-2 py-1 text-left font-medium">Lote</th>
                  <th class="px-2 py-1 text-left font-medium">Quadra</th>
                  <th class="px-2 py-1 text-left font-medium">Proprietarios</th>
                </tr>
              </thead>
              <tbody>${matriculasHtml}</tbody>
            </table>
          </div>
        </div>

        <!-- Confrontantes -->
        <div class="bg-gray-50 rounded-lg overflow-hidden">
          <div class="px-2 py-1.5 bg-gray-100 border-b border-gray-200">
            <h4 class="font-medium text-gray-700 text-xs flex items-center gap-1">
              <i class="fas fa-map-marked-alt text-green-500"></i>
              Confrontantes (${(data.lotes_confrontantes || []).length})
            </h4>
          </div>
          <div class="max-h-32 overflow-auto">
            <table class="w-full">
              <thead class="bg-gray-100 text-gray-600 text-xs sticky top-0">
                <tr>
                  <th class="px-2 py-1 text-left font-medium">Identificador</th>
                  <th class="px-2 py-1 text-left font-medium">Direcao</th>
                  <th class="px-2 py-1 text-left font-medium">Tipo</th>
                  <th class="px-2 py-1 text-left font-medium">Matricula</th>
                </tr>
              </thead>
              <tbody>${lotesHtml}</tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  `;
}

function renderRecordsTable(): void {
  renderExtractedDataPanel();
}

function renderSystemLogs(): void {
  const container = document.getElementById('system-logs');
  if (!container) return;

  const logs = appState.logs || [];

  if (logs.length === 0) {
    container.innerHTML = '<div class="text-gray-500 py-2">Nenhum log registrado</div>';
    return;
  }

  const statusIcons: Record<string, string> = {
    'success': '<span class="w-2 h-2 rounded-full bg-green-500 inline-block"></span>',
    'info': '<span class="w-2 h-2 rounded-full bg-blue-500 inline-block"></span>',
    'warning': '<span class="w-2 h-2 rounded-full bg-yellow-500 inline-block"></span>',
    'error': '<span class="w-2 h-2 rounded-full bg-red-500 inline-block"></span>'
  };

  const statusColors: Record<string, string> = {
    'success': 'text-green-400',
    'info': 'text-blue-400',
    'warning': 'text-yellow-400',
    'error': 'text-red-400'
  };

  container.innerHTML = logs.map(log => `
    <div class="log-entry flex items-start gap-3 py-1 ${statusColors[log.status] || 'text-gray-400'}">
      <span class="text-gray-500 flex-shrink-0">[${log.time}]</span>
      ${statusIcons[log.status] || statusIcons.info}
      <span class="${log.status === 'error' ? 'text-red-400' : 'text-gray-300'}">${escapeHtml(log.message)}</span>
    </div>
  `).join('');
}

// ============================================
// Event Handlers
// ============================================

async function selectFile(id: string, event: MouseEvent): Promise<void> {
  const fileId = String(id);

  if (event && event.ctrlKey) {
    const index = appState.selectedFileIds.indexOf(fileId);
    if (index === -1) {
      appState.selectedFileIds.push(fileId);
    } else {
      appState.selectedFileIds.splice(index, 1);
    }
    if (appState.selectedFileIds.length > 0) {
      appState.selectedFileId = appState.selectedFileIds[appState.selectedFileIds.length - 1];
    } else {
      appState.selectedFileId = null;
    }
  } else {
    appState.selectedFileIds = [fileId];
    appState.selectedFileId = fileId;
  }

  appState.files.forEach(file => {
    file.selected = appState.selectedFileIds.includes(String(file.id));
  });

  renderFileList();
  updateBatchAnalyzeButton();

  if (appState.selectedFileId) {
    await loadDocumentDetails(appState.selectedFileId);
  }

  updateAnalysisStatus();

  if (appState.selectedFileIds.length > 1) {
    addLog('info', `${appState.selectedFileIds.length} arquivos selecionados para analise em lote`);
  } else {
    addLog('info', `Arquivo selecionado: ${appState.files.find(f => String(f.id) === fileId)?.name || fileId}`);
  }
}

function updateBatchAnalyzeButton(): void {
  const batchBtn = document.getElementById('btn-analyze-batch');
  if (batchBtn) {
    if (appState.selectedFileIds.length >= 2) {
      (batchBtn as HTMLButtonElement).disabled = false;
      batchBtn.innerHTML = `<i class="fas fa-layer-group"></i> Analisar ${appState.selectedFileIds.length} arquivos`;
    } else {
      (batchBtn as HTMLButtonElement).disabled = true;
      batchBtn.innerHTML = `<i class="fas fa-layer-group"></i> Analise em Lote`;
    }
  }
}

async function analisarEmLote(fileIds: string[]): Promise<void> {
  if (!fileIds || fileIds.length < 2) {
    showToast('Selecione pelo menos 2 documentos', 'warning');
    return;
  }

  const matriculaInput = document.getElementById('matricula-principal-input') as HTMLInputElement | null;
  const matriculaPrincipal = matriculaInput ? matriculaInput.value.trim() : '';

  if (!matriculaPrincipal) {
    showToast('Por favor, informe a Matricula Principal', 'warning');
    if (matriculaInput) matriculaInput.focus();
    return;
  }

  try {
    showToast(`Iniciando analise de ${fileIds.length} documentos...`, 'info');
    addLog('info', `Iniciando analise em lote de ${fileIds.length} documentos`);

    const result = await api<{ success: boolean; grupo_id?: number; detail?: string }>('/analisar-lote', {
      method: 'POST',
      body: JSON.stringify({
        file_ids: fileIds,
        nome_grupo: `Analise de ${fileIds.length} matriculas`,
        matricula_principal: matriculaPrincipal
      })
    });

    if (result?.success && result.grupo_id) {
      appState.currentGrupoId = result.grupo_id;
      showToast('Analise em lote iniciada!', 'success');
      startBatchPolling(result.grupo_id);
    } else {
      showToast(result?.detail || 'Erro ao iniciar analise em lote', 'error');
    }
  } catch {
    showToast('Erro ao iniciar analise em lote', 'error');
  }
}

function startBatchPolling(grupoId: number): void {
  const statusEl = document.getElementById('analysis-status');

  const pollInterval = setInterval(async () => {
    try {
      const status = await api<BatchStatusResponse>(`/grupo/${grupoId}/status`);

      if (status?.status === 'concluido') {
        clearInterval(pollInterval);
        showToast('Analise em lote concluida!', 'success');
        addLog('success', `Analise em lote concluida: ${status.total_arquivos} arquivos`);

        if (statusEl) {
          statusEl.innerHTML = '<i class="fas fa-check-circle text-green-500"></i> Analise em lote concluida';
        }

        const resultado = await api<DocumentDetails>(`/grupo/${grupoId}/resultado`);
        if (resultado) {
          appState.documentDetails = resultado;
          appState.currentAnaliseId = resultado.analise_id || null;

          renderExtractedDataPanel();
          await generateAndShowReport();
          await loadFiles();
          await loadAnalyses();
        }

      } else if (status?.status === 'erro') {
        clearInterval(pollInterval);
        showToast('Erro na analise em lote', 'error');
        addLog('error', 'Erro na analise em lote');

        if (statusEl) {
          statusEl.innerHTML = '<i class="fas fa-exclamation-circle text-red-500"></i> Erro na analise';
        }

      } else {
        if (statusEl) {
          statusEl.innerHTML = '<i class="fas fa-spinner fa-spin text-purple-500"></i> Analisando ' + (status?.total_arquivos || 0) + ' arquivos...';
        }
      }
    } catch (error) {
      console.error('Erro ao verificar status do lote:', error);
    }
  }, 3000);

  appState.pollingIntervals['batch_' + grupoId] = pollInterval;
}

async function deleteFile(id: string): Promise<void> {
  const fileId = String(id);
  const file = appState.files.find(f => String(f.id) === fileId);
  if (file && confirm(`Deseja excluir o arquivo "${file.name}"?`)) {
    await apiDeleteFile(fileId);
  }
}

async function viewAnalysis(id: string): Promise<void> {
  try {
    const result = await api<DocumentDetails>(`/resultado/${id}`);
    if (result) {
      appState.documentDetails = result;
      appState.currentAnaliseId = result.analise_id || null;
      await generateAndShowReport();
      showToast('Analise carregada', 'info');
    }
  } catch {
    showToast('Erro ao carregar analise', 'error');
  }
}

function addLog(status: 'success' | 'info' | 'warning' | 'error', message: string): void {
  const now = new Date();
  const time = now.toTimeString().split(' ')[0];
  appState.logs.unshift({ time, status, message });
  if (appState.logs.length > 50) appState.logs.pop();
  renderSystemLogs();
}

function setupFileUpload(): void {
  const importBtn = document.getElementById('btn-import');
  if (importBtn) {
    importBtn.addEventListener('click', triggerFileUpload);
  }

  const fileInput = document.createElement('input');
  fileInput.type = 'file';
  fileInput.id = 'file-input';
  fileInput.accept = '.pdf,.png,.jpg,.jpeg,.tif,.tiff,.bmp,.webp';
  fileInput.multiple = true;
  fileInput.style.display = 'none';
  fileInput.addEventListener('change', handleFileSelect);
  document.body.appendChild(fileInput);
}

function triggerFileUpload(): void {
  console.log('[triggerFileUpload] Botão importar clicado');
  const fileInput = document.getElementById('file-input') as HTMLInputElement;
  console.log('[triggerFileUpload] Input encontrado:', !!fileInput);
  if (fileInput) {
    fileInput.click();
  } else {
    console.error('[triggerFileUpload] Input file não encontrado no DOM!');
  }
}

async function handleFileSelect(event: Event): Promise<void> {
  console.log('[handleFileSelect] Evento disparado', event);
  const target = event.target as HTMLInputElement;
  const files = target.files;
  console.log('[handleFileSelect] Arquivos selecionados:', files?.length || 0);

  if (!files || files.length === 0) {
    console.log('[handleFileSelect] Nenhum arquivo selecionado, retornando');
    return;
  }

  for (const file of Array.from(files)) {
    console.log('[handleFileSelect] Iniciando upload de:', file.name, file.type, file.size);
    await uploadFile(file);
  }

  target.value = '';
}

function setupAIActions(): void {
  const analyzeBtn = document.getElementById('btn-analyze');
  if (analyzeBtn) {
    analyzeBtn.addEventListener('click', () => {
      if (appState.selectedFileId) {
        analisarDocumento(appState.selectedFileId);
      } else {
        showToast('Selecione um documento primeiro', 'warning');
      }
    });
  }

  const reanalyzeBtn = document.getElementById('btn-reanalyze');
  if (reanalyzeBtn) {
    reanalyzeBtn.addEventListener('click', () => {
      if (appState.selectedFileId) {
        if (confirm('Deseja refazer a analise deste documento? A analise anterior sera substituida.')) {
          analisarDocumento(appState.selectedFileId, true);
        }
      } else {
        showToast('Selecione um documento primeiro', 'warning');
      }
    });
  }

  const batchAnalyzeBtn = document.getElementById('btn-analyze-batch');
  if (batchAnalyzeBtn) {
    batchAnalyzeBtn.addEventListener('click', () => {
      if (appState.selectedFileIds.length >= 2) {
        analisarEmLote(appState.selectedFileIds);
      } else {
        showToast('Selecione pelo menos 2 documentos (Ctrl+Click)', 'warning');
      }
    });
  }

  const deleteBtn = document.getElementById('btn-delete-file');
  if (deleteBtn) {
    deleteBtn.addEventListener('click', () => {
      if (appState.selectedFileId) {
        deleteFile(appState.selectedFileId);
      } else {
        showToast('Selecione um documento primeiro', 'warning');
      }
    });
  }

  updateAnalysisStatus();
}

function updateAnalysisStatus(): void {
  const statusEl = document.getElementById('analysis-status');
  if (!statusEl) return;

  if (!appState.selectedFileId) {
    statusEl.innerHTML = 'Selecione um documento para analisar';
    statusEl.className = 'text-xs text-gray-500 text-center mt-2';
  } else {
    const file = appState.files.find(f => String(f.id) === String(appState.selectedFileId));
    if (file?.analyzed) {
      statusEl.innerHTML = '<i class="fas fa-check-circle text-green-500"></i> Documento analisado';
      statusEl.className = 'text-xs text-green-600 text-center mt-2';
    } else {
      statusEl.innerHTML = '<i class="fas fa-info-circle text-blue-500"></i> Pronto para analisar';
      statusEl.className = 'text-xs text-blue-600 text-center mt-2';
    }
  }
}

function showBatchHelpModal(): void {
  const modal = document.createElement('div');
  modal.id = 'batch-help-modal';
  modal.className = 'fixed inset-0 z-50 flex items-center justify-center bg-black/50';
  modal.onclick = (e) => { if (e.target === modal) modal.remove(); };

  modal.innerHTML = `
    <div class="bg-white rounded-xl shadow-2xl max-w-md w-full mx-4 overflow-hidden">
      <div class="bg-gradient-to-r from-purple-500 to-purple-600 px-6 py-4">
        <div class="flex items-center justify-between">
          <h3 class="text-lg font-semibold text-white flex items-center gap-2">
            <i class="fas fa-layer-group"></i>
            Analise em Lote
          </h3>
          <button onclick="document.getElementById('batch-help-modal').remove()"
            class="text-white/80 hover:text-white transition-colors">
            <i class="fas fa-times text-xl"></i>
          </button>
        </div>
      </div>
      <div class="p-6 space-y-4">
        <div class="flex items-start gap-3">
          <div class="w-8 h-8 bg-purple-100 rounded-full flex items-center justify-center flex-shrink-0">
            <i class="fas fa-question text-purple-600"></i>
          </div>
          <div>
            <h4 class="font-semibold text-gray-800">Quando usar?</h4>
            <p class="text-sm text-gray-600 mt-1">
              Use quando tiver <strong>multiplas matriculas</strong> que fazem parte do
              <strong>mesmo processo de usucapiao</strong>.
            </p>
          </div>
        </div>

        <div class="flex items-start gap-3">
          <div class="w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center flex-shrink-0">
            <i class="fas fa-file-alt text-blue-600"></i>
          </div>
          <div>
            <h4 class="font-semibold text-gray-800">Exemplo</h4>
            <p class="text-sm text-gray-600 mt-1">
              A matricula principal do imovel + matriculas dos confrontantes anexadas ao processo.
            </p>
          </div>
        </div>

        <div class="flex items-start gap-3">
          <div class="w-8 h-8 bg-green-100 rounded-full flex items-center justify-center flex-shrink-0">
            <i class="fas fa-brain text-green-600"></i>
          </div>
          <div>
            <h4 class="font-semibold text-gray-800">O que a IA faz?</h4>
            <p class="text-sm text-gray-600 mt-1">
              Analisa todos os documentos em conjunto, cruzando informacoes para identificar
              a matricula principal e validar as confrontacoes.
            </p>
          </div>
        </div>

        <div class="bg-gray-50 rounded-lg p-4 mt-4">
          <h4 class="font-semibold text-gray-800 text-sm mb-2">
            <i class="fas fa-keyboard text-gray-500"></i> Como selecionar multiplos arquivos:
          </h4>
          <p class="text-sm text-gray-600">
            Segure <kbd class="px-2 py-1 bg-gray-200 rounded text-xs font-mono">Ctrl</kbd>
            e clique nos arquivos desejados.
          </p>
        </div>
      </div>
      <div class="px-6 py-4 bg-gray-50 border-t">
        <button onclick="document.getElementById('batch-help-modal').remove()"
          class="w-full px-4 py-2 bg-purple-500 text-white rounded-lg hover:bg-purple-600 transition-colors font-medium">
          Entendi
        </button>
      </div>
    </div>
  `;

  document.body.appendChild(modal);
}

// ============================================
// Toast Notification
// ============================================

function showToast(message: string, type: 'success' | 'error' | 'warning' | 'info' = 'info'): void {
  const existingToast = document.getElementById('toast-notification');
  if (existingToast) existingToast.remove();

  const toast = document.createElement('div');
  toast.id = 'toast-notification';
  toast.className = `fixed bottom-4 right-4 z-50 px-6 py-3 rounded-lg shadow-lg transition-all duration-300 flex items-center gap-2 ${
    type === 'success' ? 'bg-green-500 text-white' :
    type === 'error' ? 'bg-red-500 text-white' :
    type === 'warning' ? 'bg-yellow-500 text-white' :
    'bg-blue-500 text-white'
  }`;

  const icons: Record<string, string> = {
    success: 'fa-check-circle',
    error: 'fa-exclamation-circle',
    warning: 'fa-exclamation-triangle',
    info: 'fa-info-circle'
  };

  toast.innerHTML = `
    <i class="fas ${icons[type]}"></i>
    <span>${escapeHtml(message)}</span>
  `;

  document.body.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

// ============================================
// Initialization
// ============================================

document.addEventListener('DOMContentLoaded', async () => {
  console.log('[Init] Iniciando aplicacao...');

  try {
    await Promise.all([
      loadConfig(),
      loadFiles(),
      loadAnalyses(),
      loadLogs()
    ]);
    console.log('[Init] Dados carregados do servidor');
  } catch (error) {
    console.error('[Init] Erro ao carregar dados:', error);
  }

  renderFileList();
  renderRecordsTable();
  renderSystemLogs();

  setupFileUpload();
  setupAIActions();

  updateAnalysisStatus();

  addLog('success', 'Interface web carregada com sucesso');
  console.log('[Init] Aplicacao iniciada');
});

// ============================================
// Global Exports
// ============================================

declare global {
  interface Window {
    selectFile: typeof selectFile;
    deleteFile: typeof deleteFile;
    analisarDocumento: typeof analisarDocumento;
    analisarEmLote: typeof analisarEmLote;
    openPdfInNewTab: typeof openPdfInNewTab;
    confirmReplaceFile: typeof confirmReplaceFile;
    cancelReplaceFile: typeof cancelReplaceFile;
    enviarFeedbackMatricula: typeof enviarFeedbackMatricula;
    downloadReportDocx: typeof downloadReportDocx;
    printReportPdf: typeof printReportPdf;
    copyReport: typeof copyReport;
    showPayload: typeof showPayload;
    showBatchHelpModal: typeof showBatchHelpModal;
    cancelAnalysis: typeof cancelAnalysis;
    viewAnalysis: typeof viewAnalysis;
    logout: typeof logout;
    triggerFileUpload: typeof triggerFileUpload;
    showToast: typeof showToast;
    gerarRelatorio: typeof gerarRelatorio;
  }
}

window.selectFile = selectFile;
window.deleteFile = deleteFile;
window.analisarDocumento = analisarDocumento;
window.analisarEmLote = analisarEmLote;
window.openPdfInNewTab = openPdfInNewTab;
window.confirmReplaceFile = confirmReplaceFile;
window.cancelReplaceFile = cancelReplaceFile;
window.enviarFeedbackMatricula = enviarFeedbackMatricula;
window.downloadReportDocx = downloadReportDocx;
window.printReportPdf = printReportPdf;
window.copyReport = copyReport;
window.showPayload = showPayload;
window.showBatchHelpModal = showBatchHelpModal;
window.cancelAnalysis = cancelAnalysis;
window.viewAnalysis = viewAnalysis;
window.logout = logout;
window.triggerFileUpload = triggerFileUpload;
window.showToast = showToast;
window.gerarRelatorio = gerarRelatorio;
