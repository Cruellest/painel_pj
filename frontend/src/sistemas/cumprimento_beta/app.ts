// frontend/src/sistemas/cumprimento_beta/app.ts
/**
 * Aplicação principal do Cumprimento de Sentença Beta
 *
 * Orquestra todos os componentes e gerencia o estado da aplicação
 *
 * @author LAB/PGE-MS
 */

import type {
  AppState,
  SessionResponse,
  SessionStatus,
  ConsolidationResponse,
  PieceSuggestion,
  ChatMessageResponse,
  ProcessStep,
  SSEEvent,
} from './types';

import { api } from './api';
import {
  HistoryDrawer,
  historyDrawerStyles,
  ProcessSteps,
  processStepsStyles,
  ProcessSummary,
  processSummaryStyles,
  jsonViewerStyles,
} from './components';

// Declaração do marked (biblioteca externa)
declare const marked: {
  parse: (markdown: string) => string;
};

// ============================================
// Application Class
// ============================================

export class CumprimentoBetaApp {
  private state: AppState = {
    token: localStorage.getItem('access_token'),
    userName: '',
    sessaoId: null,
    status: 'idle',
    currentSession: null,
    consolidation: null,
    documents: [],
    chatHistory: [],
    generatedPieces: [],
    error: null,
  };

  // Components
  private historyDrawer: HistoryDrawer | null = null;
  private processSteps: ProcessSteps | null = null;
  private processSummary: ProcessSummary | null = null;

  // Polling
  private pollInterval: number | null = null;

  constructor() {
    this.injectStyles();
    this.init();
  }

  private injectStyles(): void {
    const styleId = 'cumprimento-beta-styles';
    if (document.getElementById(styleId)) return;

    const style = document.createElement('style');
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

  private getAppStyles(): string {
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

  private async init(): Promise<void> {
    if (!this.state.token) {
      window.location.href = '/login?next=/cumprimento-beta';
      return;
    }

    try {
      // Check access
      const access = await api.checkAccess();
      if (!access.pode_acessar) {
        this.showError(access.motivo ?? 'Acesso negado');
        return;
      }

      // Get user info
      const user = await api.getCurrentUser();
      this.state.userName = user.full_name;

      // Render app
      this.render();

      // Initialize components
      this.initComponents();

      // Load history
      await this.loadHistory();

    } catch (error) {
      const err = error as Error;
      if (err.message.includes('401') || err.message.includes('Token')) {
        localStorage.removeItem('access_token');
        window.location.href = '/login?next=/cumprimento-beta';
        return;
      }
      this.showError(err.message);
    }
  }

  private render(): void {
    const appContainer = document.getElementById('app') ?? document.body;
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
              <h1>Cumprimento de Sentença</h1>
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
                  Número do Processo (CNJ)
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

  private initComponents(): void {
    // History Drawer
    const historyContainer = document.getElementById('history-drawer-container');
    if (historyContainer) {
      this.historyDrawer = new HistoryDrawer(historyContainer, {
        onSessionSelect: (id) => this.loadSession(id),
      });
    }

    // Process Steps
    const stepsContainer = document.getElementById('process-steps-container');
    if (stepsContainer) {
      this.processSteps = new ProcessSteps(stepsContainer, {
        onRetry: () => this.retry(),
        warningThresholdMs: 120000, // 2 minutes
      });
    }

    // Process Summary
    const summaryContainer = document.getElementById('process-summary-container');
    if (summaryContainer) {
      this.processSummary = new ProcessSummary(summaryContainer, {
        onSuggestionClick: (s) => this.handleSuggestionClick(s),
      });
    }
  }

  private attachEventListeners(): void {
    // Start button
    document.getElementById('btn-iniciar')?.addEventListener('click', () => {
      this.startNewSession();
    });

    // Enter key on input
    document.getElementById('numero-processo')?.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') {
        this.startNewSession();
      }
    });

    // Retry button
    document.getElementById('btn-retry')?.addEventListener('click', () => {
      this.retry();
    });

    // Chat send button
    document.getElementById('btn-send-chat')?.addEventListener('click', () => {
      this.sendChatMessage();
    });

    // Chat input enter key
    document.getElementById('chat-input')?.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') {
        this.sendChatMessage();
      }
    });
  }

  private escapeHtml(str: string): string {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  // ==========================================
  // Session Management
  // ==========================================

  private async loadHistory(): Promise<void> {
    try {
      const response = await api.listSessions(1, 50);
      this.historyDrawer?.setSessions(response.sessoes);
    } catch (error) {
      console.error('Erro ao carregar histórico:', error);
    }
  }

  private async startNewSession(): Promise<void> {
    const input = document.getElementById('numero-processo') as HTMLInputElement;
    const numeroProcesso = input?.value.trim();

    if (!numeroProcesso) {
      this.showToast('Informe o número do processo', 'warning');
      return;
    }

    this.hideError();
    this.showSection('processing');

    try {
      // Create session
      const session = await api.createSession({ numero_processo: numeroProcesso });
      this.state.sessaoId = session.sessao_id;

      // Start processing
      await api.startProcessing(session.sessao_id);
      this.processSteps?.start();

      // Start polling
      this.startPolling();

      // Update history
      await this.loadHistory();
      this.historyDrawer?.setCurrentSession(session.sessao_id);

    } catch (error) {
      const err = error as Error;
      this.showError(err.message);
      this.processSteps?.stop();
    }
  }

  private async loadSession(sessionId: number): Promise<void> {
    this.state.sessaoId = sessionId;
    this.hideError();

    try {
      const session = await api.getSession(sessionId);
      this.state.currentSession = session;
      this.historyDrawer?.setCurrentSession(sessionId);

      // Update input
      const input = document.getElementById('numero-processo') as HTMLInputElement;
      if (input) {
        input.value = session.numero_processo_formatado;
      }

      // Handle based on status
      if (session.status === 'chatbot' || session.status === 'finalizado') {
        await this.loadCompletedSession(session);
      } else if (session.status === 'erro') {
        this.showError(session.erro_mensagem ?? 'Erro no processamento');
      } else if (session.status === 'consolidando' && !session.tem_consolidacao) {
        // Needs consolidation
        this.showSection('processing');
        this.processSteps?.start();
        await this.runConsolidation();
      } else {
        // Still processing
        this.showSection('processing');
        this.processSteps?.start();
        this.startPolling();
      }

    } catch (error) {
      const err = error as Error;
      this.showError(err.message);
    }
  }

  private async loadCompletedSession(session: SessionResponse): Promise<void> {
    this.showSection('summary');
    this.showSection('chat');

    try {
      const consolidation = await api.getConsolidation(session.id);
      this.state.consolidation = consolidation;
      this.processSummary?.setConsolidation(consolidation);

      // Load chat history
      const chatHistory = await api.getChatHistory(session.id);
      this.state.chatHistory = chatHistory.mensagens;
      this.renderChatHistory();

    } catch (error) {
      console.error('Erro ao carregar sessão:', error);
      this.processSummary?.clear();
    }
  }

  // ==========================================
  // Polling
  // ==========================================

  private startPolling(): void {
    this.stopPolling();
    this.pollInterval = window.setInterval(() => this.pollStatus(), 2000);
  }

  private stopPolling(): void {
    if (this.pollInterval) {
      clearInterval(this.pollInterval);
      this.pollInterval = null;
    }
  }

  private async pollStatus(): Promise<void> {
    if (!this.state.sessaoId) return;

    try {
      const session = await api.getSession(this.state.sessaoId);
      this.state.currentSession = session;
      this.updateProcessingUI(session);

      if (session.status === 'consolidando') {
        if (!session.tem_consolidacao) {
          this.stopPolling();
          await this.runConsolidation();
        }
      } else if (session.status === 'chatbot' || session.status === 'finalizado') {
        this.stopPolling();
        this.processSteps?.complete();
        await this.loadCompletedSession(session);
      } else if (session.status === 'erro') {
        this.stopPolling();
        this.processSteps?.stop();
        this.showError(session.erro_mensagem ?? 'Erro no processamento');
      }

    } catch (error) {
      console.error('Erro no polling:', error);
    }
  }

  private updateProcessingUI(session: SessionResponse): void {
    const statusMap: Record<SessionStatus, string> = {
      iniciado: 'download',
      baixando_docs: 'download',
      avaliando_relevancia: 'avaliacao',
      extraindo_json: 'extracao',
      consolidando: 'consolidacao',
      chatbot: 'consolidacao',
      gerando_peca: 'consolidacao',
      finalizado: 'consolidacao',
      erro: 'download',
    };

    const currentStep = statusMap[session.status];

    // Update steps based on status
    if (session.status === 'baixando_docs') {
      this.processSteps?.setStepStatus('download', 'processando',
        `${session.documentos_processados}/${session.total_documentos} documentos`);
    } else if (session.status === 'avaliando_relevancia' || session.status === 'extraindo_json') {
      this.processSteps?.setStepStatus('download', 'concluido',
        `${session.total_documentos} documentos baixados`);
      this.processSteps?.setStepStatus('avaliacao', 'processando',
        `${session.documentos_relevantes} relevantes de ${session.documentos_processados}`);
      if (session.status === 'extraindo_json') {
        this.processSteps?.setStepStatus('extracao', 'processando', 'Extraindo informações...');
      }
    } else if (session.status === 'consolidando') {
      this.processSteps?.setStepStatus('download', 'concluido');
      this.processSteps?.setStepStatus('avaliacao', 'concluido');
      this.processSteps?.setStepStatus('extracao', 'concluido');
      this.processSteps?.setStepStatus('consolidacao', 'processando', 'Consolidando...');
    }
  }

  // ==========================================
  // Consolidation
  // ==========================================

  private async runConsolidation(): Promise<void> {
    if (!this.state.sessaoId) return;

    this.showSection('summary');
    this.processSummary?.setLoading(true);
    this.processSteps?.setStepStatus('consolidacao', 'processando', 'Gerando resumo...');

    try {
      for await (const event of api.streamConsolidation(this.state.sessaoId)) {
        this.handleConsolidationEvent(event);
      }
    } catch (error) {
      const err = error as Error;
      this.showError(err.message);
      this.processSteps?.setStepStatus('consolidacao', 'erro', err.message);
    }
  }

  private handleConsolidationEvent(event: SSEEvent): void {
    switch (event.event) {
      case 'inicio':
        this.processSummary?.setStreamingContent('');
        break;

      case 'chunk':
        this.processSummary?.appendStreamingContent(event.data.texto);
        break;

      case 'concluido':
        this.processSteps?.setStepStatus('consolidacao', 'concluido');
        this.processSteps?.stop();
        this.showSection('chat');

        // Load full consolidation
        if (this.state.sessaoId) {
          api.getConsolidation(this.state.sessaoId).then(consolidation => {
            this.state.consolidation = consolidation;
            this.processSummary?.setConsolidation(consolidation);
          });
        }

        // Add initial chat message
        this.addChatMessage('assistant',
          'Olá! Analisei o processo de cumprimento de sentença. Como posso ajudar? Você pode escolher uma das sugestões acima ou fazer qualquer pergunta sobre o processo.');
        break;

      case 'erro':
        this.showError(event.data.mensagem);
        this.processSteps?.setStepStatus('consolidacao', 'erro', event.data.mensagem);
        break;
    }
  }

  // ==========================================
  // Chat
  // ==========================================

  private renderChatHistory(): void {
    const container = document.getElementById('chat-messages');
    if (!container) return;

    container.innerHTML = '';

    for (const msg of this.state.chatHistory) {
      this.addChatMessage(msg.role === 'user' ? 'user' : 'assistant', msg.conteudo);
    }

    // Scroll to bottom
    container.scrollTop = container.scrollHeight;
  }

  private addChatMessage(role: 'user' | 'assistant', content: string): void {
    const container = document.getElementById('chat-messages');
    if (!container) return;

    const messageEl = document.createElement('div');
    messageEl.className = `beta-chat-message ${role === 'user' ? 'beta-chat-message-user' : ''}`;

    const parsedContent = typeof marked !== 'undefined' ? marked.parse(content) : this.escapeHtml(content);

    messageEl.innerHTML = `
      <div class="beta-chat-avatar ${role === 'user' ? 'beta-chat-avatar-user' : 'beta-chat-avatar-ai'}">
        <i class="fas ${role === 'user' ? 'fa-user' : 'fa-robot'}"></i>
      </div>
      <div class="beta-chat-bubble ${role === 'user' ? 'beta-chat-bubble-user' : 'beta-chat-bubble-ai'}">
        ${parsedContent}
      </div>
    `;

    container.appendChild(messageEl);
    container.scrollTop = container.scrollHeight;
  }

  private addTypingIndicator(): HTMLElement {
    const container = document.getElementById('chat-messages');
    if (!container) return document.createElement('div');

    const indicator = document.createElement('div');
    indicator.id = 'typing-indicator';
    indicator.className = 'beta-chat-message';
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

  private removeTypingIndicator(): void {
    document.getElementById('typing-indicator')?.remove();
  }

  private async sendChatMessage(): Promise<void> {
    const input = document.getElementById('chat-input') as HTMLInputElement;
    const message = input?.value.trim();

    if (!message || !this.state.sessaoId) return;

    input.value = '';
    this.addChatMessage('user', message);
    this.addTypingIndicator();

    try {
      let response = '';
      const messageEl = document.createElement('div');
      messageEl.className = 'beta-chat-message';
      messageEl.innerHTML = `
        <div class="beta-chat-avatar beta-chat-avatar-ai">
          <i class="fas fa-robot"></i>
        </div>
        <div class="beta-chat-bubble beta-chat-bubble-ai message-content"></div>
      `;

      this.removeTypingIndicator();
      document.getElementById('chat-messages')?.appendChild(messageEl);

      const contentEl = messageEl.querySelector('.message-content');

      for await (const chunk of api.streamChat(this.state.sessaoId, message)) {
        response += chunk;
        if (contentEl && typeof marked !== 'undefined') {
          contentEl.innerHTML = marked.parse(response);
        }
        const container = document.getElementById('chat-messages');
        if (container) {
          container.scrollTop = container.scrollHeight;
        }
      }

    } catch (error) {
      this.removeTypingIndicator();
      const err = error as Error;
      this.addChatMessage('assistant', `Erro: ${err.message}`);
    }
  }

  private handleSuggestionClick(suggestion: PieceSuggestion): void {
    const input = document.getElementById('chat-input') as HTMLInputElement;
    if (input) {
      input.value = `Gere uma ${suggestion.tipo} para este processo`;
      input.focus();
    }
  }

  // ==========================================
  // UI Helpers
  // ==========================================

  private showSection(section: 'processing' | 'summary' | 'chat'): void {
    const sectionId = `${section}-section`;
    document.getElementById(sectionId)?.classList.remove('beta-hidden');
  }

  private hideSection(section: 'processing' | 'summary' | 'chat'): void {
    const sectionId = `${section}-section`;
    document.getElementById(sectionId)?.classList.add('beta-hidden');
  }

  private showError(message: string): void {
    const section = document.getElementById('error-section');
    const messageEl = document.getElementById('error-message');

    if (section) section.classList.remove('beta-hidden');
    if (messageEl) messageEl.textContent = message;

    this.state.error = message;
    this.hideSection('processing');
  }

  private hideError(): void {
    document.getElementById('error-section')?.classList.add('beta-hidden');
    this.state.error = null;
  }

  private retry(): void {
    this.hideError();
    this.processSteps?.reset();

    if (this.state.sessaoId) {
      this.loadSession(this.state.sessaoId);
    }
  }

  private showToast(message: string, type: 'success' | 'warning' | 'error' = 'success'): void {
    const toast = document.createElement('div');
    toast.className = `summary-toast summary-toast-${type}`;
    toast.innerHTML = `
      <i class="fas ${type === 'success' ? 'fa-check-circle' : type === 'warning' ? 'fa-exclamation-triangle' : 'fa-exclamation-circle'}"></i>
      ${message}
    `;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
  }
}

// ============================================
// Initialize Application
// ============================================

const app = new CumprimentoBetaApp();

// Global exports
declare global {
  interface Window {
    cumprimentoBetaApp: CumprimentoBetaApp;
  }
}

window.cumprimentoBetaApp = app;
