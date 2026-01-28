// frontend/src/sistemas/cumprimento_beta/components/HistoryDrawer.ts
/**
 * HistoryDrawer - Drawer lateral para histórico de sessões
 *
 * Features:
 * - Drawer recolhível (toggle)
 * - Busca por CNJ
 * - Filtro por status
 * - Lista de sessões com status visual
 * - Responsivo (fechado em mobile, aberto em desktop)
 *
 * @author LAB/PGE-MS
 */

import type { SessionResponse, SessionStatus, HistoryFilters } from '../types';

export interface HistoryDrawerOptions {
  defaultOpen?: boolean;
  onSessionSelect?: (sessionId: number) => void;
  onClose?: () => void;
}

export class HistoryDrawer {
  private container: HTMLElement;
  private sessions: SessionResponse[] = [];
  private options: Required<HistoryDrawerOptions>;
  private isOpen: boolean;
  private filters: HistoryFilters = {
    search: '',
    status: 'all',
  };
  private currentSessionId: number | null = null;

  constructor(container: HTMLElement, options: HistoryDrawerOptions = {}) {
    this.container = container;
    this.options = {
      defaultOpen: options.defaultOpen ?? window.innerWidth >= 1024,
      onSessionSelect: options.onSessionSelect ?? (() => {}),
      onClose: options.onClose ?? (() => {}),
    };
    this.isOpen = this.options.defaultOpen;
    this.render();
    this.setupResizeListener();
  }

  private setupResizeListener(): void {
    let timeout: number;
    window.addEventListener('resize', () => {
      clearTimeout(timeout);
      timeout = window.setTimeout(() => {
        // Auto-close on mobile, auto-open on desktop
        const shouldBeOpen = window.innerWidth >= 1024;
        if (this.isOpen !== shouldBeOpen) {
          this.isOpen = shouldBeOpen;
          this.render();
        }
      }, 150);
    });
  }

  private escapeHtml(str: string): string {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  private getStatusConfig(status: SessionStatus): { icon: string; color: string; label: string } {
    const configs: Record<SessionStatus, { icon: string; color: string; label: string }> = {
      iniciado: { icon: 'fa-play', color: 'blue', label: 'Iniciado' },
      baixando_docs: { icon: 'fa-download', color: 'blue', label: 'Baixando' },
      avaliando_relevancia: { icon: 'fa-filter', color: 'yellow', label: 'Avaliando' },
      extraindo_json: { icon: 'fa-code', color: 'yellow', label: 'Extraindo' },
      consolidando: { icon: 'fa-layer-group', color: 'yellow', label: 'Consolidando' },
      chatbot: { icon: 'fa-check', color: 'green', label: 'Concluído' },
      gerando_peca: { icon: 'fa-file-alt', color: 'purple', label: 'Gerando Peça' },
      finalizado: { icon: 'fa-check-circle', color: 'green', label: 'Finalizado' },
      erro: { icon: 'fa-times-circle', color: 'red', label: 'Erro' },
    };
    return configs[status] || configs.iniciado;
  }

  private formatDate(dateStr: string): string {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Agora';
    if (diffMins < 60) return `${diffMins}min atrás`;
    if (diffHours < 24) return `${diffHours}h atrás`;
    if (diffDays < 7) return `${diffDays}d atrás`;

    return date.toLocaleDateString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      year: '2-digit',
    });
  }

  private getFilteredSessions(): SessionResponse[] {
    return this.sessions.filter(session => {
      // Search filter
      if (this.filters.search) {
        const searchLower = this.filters.search.toLowerCase();
        const matchesCnj = session.numero_processo.includes(this.filters.search) ||
                          session.numero_processo_formatado.toLowerCase().includes(searchLower);
        if (!matchesCnj) return false;
      }

      // Status filter
      if (this.filters.status !== 'all' && session.status !== this.filters.status) {
        return false;
      }

      return true;
    });
  }

  private renderSessionItem(session: SessionResponse): string {
    const statusConfig = this.getStatusConfig(session.status);
    const isSelected = session.id === this.currentSessionId;

    return `
      <button
        class="history-item ${isSelected ? 'history-item-selected' : ''}"
        data-session-id="${session.id}"
        aria-label="Sessão ${session.numero_processo_formatado}"
      >
        <div class="history-item-main">
          <div class="history-item-cnj">${this.escapeHtml(session.numero_processo_formatado)}</div>
          <div class="history-item-meta">
            <span class="history-item-date">${this.formatDate(session.created_at)}</span>
            ${session.documentos_relevantes > 0 ? `
              <span class="history-item-docs">
                <i class="fas fa-file-alt"></i> ${session.documentos_relevantes}
              </span>
            ` : ''}
          </div>
        </div>
        <div class="history-item-status history-status-${statusConfig.color}">
          <i class="fas ${statusConfig.icon}"></i>
          <span>${statusConfig.label}</span>
        </div>
      </button>
    `;
  }

  private renderStatusFilterOptions(): string {
    const statuses: Array<{ value: SessionStatus | 'all'; label: string }> = [
      { value: 'all', label: 'Todos' },
      { value: 'chatbot', label: 'Concluídos' },
      { value: 'consolidando', label: 'Em Progresso' },
      { value: 'erro', label: 'Com Erro' },
    ];

    return statuses.map(s => `
      <option value="${s.value}" ${this.filters.status === s.value ? 'selected' : ''}>
        ${s.label}
      </option>
    `).join('');
  }

  private render(): void {
    const filteredSessions = this.getFilteredSessions();

    this.container.innerHTML = `
      <!-- Toggle Button (always visible) -->
      <button class="history-toggle" aria-label="${this.isOpen ? 'Fechar' : 'Abrir'} histórico">
        <i class="fas fa-history"></i>
        <span class="history-toggle-label">Histórico</span>
        <span class="history-toggle-count">${this.sessions.length}</span>
      </button>

      <!-- Drawer Panel -->
      <div class="history-drawer ${this.isOpen ? 'history-drawer-open' : ''}">
        <!-- Overlay for mobile -->
        <div class="history-overlay"></div>

        <!-- Drawer Content -->
        <div class="history-panel">
          <!-- Header -->
          <div class="history-header">
            <h3 class="history-title">
              <i class="fas fa-history"></i>
              Histórico
            </h3>
            <button class="history-close" aria-label="Fechar histórico">
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
              ` : ''}
            </div>
            <select class="history-filter-select">
              ${this.renderStatusFilterOptions()}
            </select>
          </div>

          <!-- Sessions List -->
          <div class="history-list">
            ${filteredSessions.length > 0 ? `
              ${filteredSessions.map(s => this.renderSessionItem(s)).join('')}
            ` : `
              <div class="history-empty">
                ${this.sessions.length === 0 ? `
                  <i class="fas fa-inbox"></i>
                  <p>Nenhuma sessão ainda</p>
                  <span>Inicie uma nova análise</span>
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

  private attachEventListeners(): void {
    // Toggle button
    const toggleBtn = this.container.querySelector('.history-toggle');
    toggleBtn?.addEventListener('click', () => this.toggle());

    // Close button
    const closeBtn = this.container.querySelector('.history-close');
    closeBtn?.addEventListener('click', () => this.close());

    // Overlay click
    const overlay = this.container.querySelector('.history-overlay');
    overlay?.addEventListener('click', () => this.close());

    // Search input
    const searchInput = this.container.querySelector<HTMLInputElement>('.history-search-input');
    searchInput?.addEventListener('input', (e) => {
      this.filters.search = (e.target as HTMLInputElement).value;
      this.render();
    });

    // Clear search
    const clearBtn = this.container.querySelector('.history-search-clear');
    clearBtn?.addEventListener('click', () => {
      this.filters.search = '';
      this.render();
    });

    // Status filter
    const filterSelect = this.container.querySelector<HTMLSelectElement>('.history-filter-select');
    filterSelect?.addEventListener('change', (e) => {
      this.filters.status = (e.target as HTMLSelectElement).value as SessionStatus | 'all';
      this.render();
    });

    // Session items
    this.container.querySelectorAll<HTMLButtonElement>('.history-item').forEach(btn => {
      btn.addEventListener('click', () => {
        const sessionId = parseInt(btn.dataset.sessionId ?? '0', 10);
        if (sessionId) {
          this.selectSession(sessionId);
        }
      });
    });
  }

  public toggle(): void {
    this.isOpen = !this.isOpen;
    this.render();
  }

  public open(): void {
    this.isOpen = true;
    this.render();
  }

  public close(): void {
    this.isOpen = false;
    this.render();
    this.options.onClose();
  }

  public setSessions(sessions: SessionResponse[]): void {
    this.sessions = sessions;
    this.render();
  }

  public setCurrentSession(sessionId: number | null): void {
    this.currentSessionId = sessionId;
    this.render();
  }

  private selectSession(sessionId: number): void {
    this.currentSessionId = sessionId;
    this.options.onSessionSelect(sessionId);
    // Close drawer on mobile after selection
    if (window.innerWidth < 1024) {
      this.close();
    } else {
      this.render();
    }
  }

  public destroy(): void {
    this.container.innerHTML = '';
  }
}

// CSS Styles
export const historyDrawerStyles = `
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
