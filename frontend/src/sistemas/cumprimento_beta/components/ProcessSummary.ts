// frontend/src/sistemas/cumprimento_beta/components/ProcessSummary.ts
/**
 * ProcessSummary - Componente para exibir resumo do processo consolidado
 *
 * Features:
 * - Resumo human-readable (texto markdown renderizado)
 * - Cards de dados do processo (exequente, executado, valor, etc)
 * - Lista de sugestões de peças clicáveis
 * - JsonViewer integrado para dados completos
 * - Estados de loading/streaming
 *
 * @author LAB/PGE-MS
 */

import type { ConsolidationResponse, ProcessData, PieceSuggestion, JsonValue } from '../types';
import { JsonViewer, jsonViewerStyles } from './JsonViewer';

// Declaração do marked (biblioteca externa)
declare const marked: {
  parse: (markdown: string) => string;
};

export interface ProcessSummaryOptions {
  onSuggestionClick?: (suggestion: PieceSuggestion) => void;
  onCopyText?: () => void;
  showJsonViewer?: boolean;
}

export class ProcessSummary {
  private container: HTMLElement;
  private consolidation: ConsolidationResponse | null = null;
  private options: Required<ProcessSummaryOptions>;
  private isLoading: boolean = false;
  private streamingContent: string = '';
  private jsonViewer: JsonViewer | null = null;
  private activeTab: 'resumo' | 'dados' | 'json' = 'resumo';

  constructor(container: HTMLElement, options: ProcessSummaryOptions = {}) {
    this.container = container;
    this.options = {
      onSuggestionClick: options.onSuggestionClick ?? (() => {}),
      onCopyText: options.onCopyText ?? (() => {}),
      showJsonViewer: options.showJsonViewer ?? true,
    };
    this.injectStyles();
    this.render();
  }

  private injectStyles(): void {
    if (!document.getElementById('json-viewer-styles')) {
      const style = document.createElement('style');
      style.id = 'json-viewer-styles';
      style.textContent = jsonViewerStyles;
      document.head.appendChild(style);
    }
  }

  private escapeHtml(str: string): string {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  private renderMarkdown(content: string): string {
    if (typeof marked !== 'undefined') {
      return marked.parse(content);
    }
    return `<pre>${this.escapeHtml(content)}</pre>`;
  }

  private getPriorityConfig(priority: 'alta' | 'media' | 'baixa'): { bgClass: string; textClass: string; label: string } {
    const configs: Record<string, { bgClass: string; textClass: string; label: string }> = {
      alta: { bgClass: 'bg-red-100', textClass: 'text-red-700', label: 'Alta' },
      media: { bgClass: 'bg-yellow-100', textClass: 'text-yellow-700', label: 'Média' },
      baixa: { bgClass: 'bg-gray-100', textClass: 'text-gray-700', label: 'Baixa' },
    };
    return configs[priority] || configs.baixa;
  }

  private renderDataCard(label: string, value: string | null | undefined, icon: string): string {
    if (!value) return '';
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

  private renderSuggestion(suggestion: PieceSuggestion, index: number): string {
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

  private renderLoadingState(): string {
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

  private renderStreamingContent(): string {
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

  private renderEmptyState(): string {
    return `
      <div class="summary-empty">
        <i class="fas fa-inbox"></i>
        <p>Nenhum resumo disponível</p>
        <span>Inicie o processamento de um processo para ver o resumo</span>
      </div>
    `;
  }

  private renderTabs(): string {
    return `
      <div class="summary-tabs">
        <button class="summary-tab ${this.activeTab === 'resumo' ? 'summary-tab-active' : ''}" data-tab="resumo">
          <i class="fas fa-file-alt"></i>
          Resumo
        </button>
        <button class="summary-tab ${this.activeTab === 'dados' ? 'summary-tab-active' : ''}" data-tab="dados">
          <i class="fas fa-table"></i>
          Dados
        </button>
        ${this.options.showJsonViewer ? `
          <button class="summary-tab ${this.activeTab === 'json' ? 'summary-tab-active' : ''}" data-tab="json">
            <i class="fas fa-code"></i>
            JSON
          </button>
        ` : ''}
      </div>
    `;
  }

  private renderResumoTab(): string {
    if (!this.consolidation) return '';

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
              Sugestões de Peças
            </h4>
            <div class="summary-suggestions-list">
              ${this.consolidation.sugestoes_pecas.map((s, i) => this.renderSuggestion(s, i)).join('')}
            </div>
          </div>
        ` : ''}
      </div>
    `;
  }

  private renderDadosTab(): string {
    const data = this.consolidation?.dados_processo;
    if (!data) {
      return `
        <div class="summary-empty-tab">
          <i class="fas fa-table"></i>
          <p>Dados estruturados não disponíveis</p>
        </div>
      `;
    }

    return `
      <div class="summary-data-grid">
        ${this.renderDataCard('Exequente', data.exequente, 'fa-user')}
        ${this.renderDataCard('Executado', data.executado, 'fa-user-tie')}
        ${this.renderDataCard('Valor da Execução', data.valor_execucao, 'fa-dollar-sign')}
        ${this.renderDataCard('Objeto', data.objeto, 'fa-gavel')}
        ${this.renderDataCard('Status', data.status, 'fa-info-circle')}
      </div>
    `;
  }

  private renderJsonTab(): string {
    return `<div id="summary-json-viewer" class="summary-json-container"></div>`;
  }

  private render(): void {
    // Handle special states
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

    // Render full content
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
            ${new Date(this.consolidation.created_at).toLocaleString('pt-BR')}
          </span>
        </div>

        <!-- Tabs -->
        ${this.renderTabs()}

        <!-- Tab Content -->
        <div class="summary-tab-content">
          ${this.activeTab === 'resumo' ? this.renderResumoTab() : ''}
          ${this.activeTab === 'dados' ? this.renderDadosTab() : ''}
          ${this.activeTab === 'json' ? this.renderJsonTab() : ''}
        </div>
      </div>
    `;

    this.attachEventListeners();

    // Initialize JsonViewer if on JSON tab
    if (this.activeTab === 'json' && this.options.showJsonViewer) {
      this.initJsonViewer();
    }
  }

  private initJsonViewer(): void {
    const viewerContainer = this.container.querySelector<HTMLElement>('#summary-json-viewer');
    if (viewerContainer && this.consolidation) {
      const jsonData: JsonValue = {
        resumo: this.consolidation.resumo_consolidado,
        dados_processo: this.consolidation.dados_processo,
        sugestoes_pecas: this.consolidation.sugestoes_pecas,
        total_jsons: this.consolidation.total_jsons_consolidados,
        modelo: this.consolidation.modelo_usado,
      };

      this.jsonViewer = new JsonViewer(viewerContainer, jsonData, {
        collapsed: false,
        searchEnabled: true,
        maxHeight: '400px',
      });
    }
  }

  private attachEventListeners(): void {
    // Tab switching
    this.container.querySelectorAll<HTMLButtonElement>('.summary-tab').forEach(tab => {
      tab.addEventListener('click', () => {
        this.activeTab = tab.dataset.tab as 'resumo' | 'dados' | 'json';
        this.render();
      });
    });

    // Copy action
    const copyBtn = this.container.querySelector<HTMLButtonElement>('[data-action="copy"]');
    copyBtn?.addEventListener('click', () => this.copyContent());

    // Suggestions
    this.container.querySelectorAll<HTMLButtonElement>('.summary-suggestion').forEach(btn => {
      btn.addEventListener('click', () => {
        const index = parseInt(btn.dataset.index ?? '0', 10);
        const suggestion = this.consolidation?.sugestoes_pecas?.[index];
        if (suggestion) {
          this.options.onSuggestionClick(suggestion);
        }
      });
    });
  }

  private async copyContent(): Promise<void> {
    if (!this.consolidation) return;

    try {
      await navigator.clipboard.writeText(this.consolidation.resumo_consolidado);
      this.showToast('Conteúdo copiado!');
      this.options.onCopyText();
    } catch {
      this.showToast('Erro ao copiar', 'error');
    }
  }

  private showToast(message: string, type: 'success' | 'error' = 'success'): void {
    const toast = document.createElement('div');
    toast.className = `summary-toast summary-toast-${type}`;
    toast.innerHTML = `
      <i class="fas ${type === 'success' ? 'fa-check-circle' : 'fa-exclamation-circle'}"></i>
      ${message}
    `;
    this.container.appendChild(toast);
    setTimeout(() => toast.remove(), 2000);
  }

  // Public methods
  public setLoading(loading: boolean): void {
    this.isLoading = loading;
    this.streamingContent = '';
    this.render();
  }

  public setStreamingContent(content: string): void {
    this.isLoading = false;
    this.streamingContent = content;
    this.render();
  }

  public appendStreamingContent(chunk: string): void {
    this.streamingContent += chunk;
    // Only re-render the streaming content, not the whole component
    const streamingEl = this.container.querySelector('.summary-markdown');
    if (streamingEl) {
      streamingEl.innerHTML = this.renderMarkdown(this.streamingContent);
      // Auto-scroll
      streamingEl.scrollTop = streamingEl.scrollHeight;
    } else {
      this.render();
    }
  }

  public setConsolidation(consolidation: ConsolidationResponse): void {
    this.consolidation = consolidation;
    this.isLoading = false;
    this.streamingContent = '';
    this.activeTab = 'resumo';
    this.render();
  }

  public clear(): void {
    this.consolidation = null;
    this.isLoading = false;
    this.streamingContent = '';
    this.jsonViewer?.destroy();
    this.jsonViewer = null;
    this.render();
  }

  public destroy(): void {
    this.jsonViewer?.destroy();
    this.container.innerHTML = '';
  }
}

// CSS Styles
export const processSummaryStyles = `
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
