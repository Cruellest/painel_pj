// frontend/src/sistemas/cumprimento_beta/components/ProcessSteps.ts
/**
 * ProcessSteps - Componente para exibir etapas do processamento
 *
 * Features:
 * - Status visual por etapa (aguardando, processando, concluído, erro)
 * - Duração de cada etapa
 * - Detalhes de erro expansíveis
 * - Barra de progresso geral
 * - Aviso quando demora mais que o normal
 *
 * @author LAB/PGE-MS
 */

import type { ProcessStep, StepStatus } from '../types';

export interface ProcessStepsOptions {
  onRetry?: () => void;
  onShowDetails?: (step: ProcessStep) => void;
  warningThresholdMs?: number;
}

export class ProcessSteps {
  private container: HTMLElement;
  private steps: ProcessStep[] = [];
  private options: Required<ProcessStepsOptions>;
  private startTime: number = 0;
  private elapsedInterval: number | null = null;
  private showWarning: boolean = false;

  constructor(container: HTMLElement, options: ProcessStepsOptions = {}) {
    this.container = container;
    this.options = {
      onRetry: options.onRetry ?? (() => {}),
      onShowDetails: options.onShowDetails ?? (() => {}),
      warningThresholdMs: options.warningThresholdMs ?? 60000, // 1 minute
    };
    this.initializeSteps();
    this.render();
  }

  private initializeSteps(): void {
    this.steps = [
      {
        id: 'download',
        label: 'Baixando documentos',
        icon: 'fa-download',
        status: 'aguardando',
        message: 'Aguardando...',
      },
      {
        id: 'avaliacao',
        label: 'Avaliando relevância',
        icon: 'fa-filter',
        status: 'aguardando',
        message: 'Aguardando...',
      },
      {
        id: 'extracao',
        label: 'Extraindo informações',
        icon: 'fa-code',
        status: 'aguardando',
        message: 'Aguardando...',
      },
      {
        id: 'consolidacao',
        label: 'Consolidando',
        icon: 'fa-layer-group',
        status: 'aguardando',
        message: 'Aguardando...',
      },
    ];
  }

  private getStatusConfig(status: StepStatus): { bgClass: string; iconClass: string; badgeClass: string; badgeText: string } {
    const configs: Record<StepStatus, { bgClass: string; iconClass: string; badgeClass: string; badgeText: string }> = {
      aguardando: {
        bgClass: 'bg-gray-200',
        iconClass: 'text-gray-400',
        badgeClass: 'bg-gray-100 text-gray-500',
        badgeText: 'Aguardando',
      },
      processando: {
        bgClass: 'bg-purple-500 animate-pulse',
        iconClass: 'text-white',
        badgeClass: 'bg-purple-100 text-purple-700',
        badgeText: 'Processando',
      },
      concluido: {
        bgClass: 'bg-green-500',
        iconClass: 'text-white',
        badgeClass: 'bg-green-100 text-green-700',
        badgeText: 'Concluído',
      },
      erro: {
        bgClass: 'bg-red-500',
        iconClass: 'text-white',
        badgeClass: 'bg-red-100 text-red-700',
        badgeText: 'Erro',
      },
    };
    return configs[status];
  }

  private getProgress(): number {
    const completedSteps = this.steps.filter(s => s.status === 'concluido').length;
    const processingStep = this.steps.find(s => s.status === 'processando');

    if (processingStep) {
      const stepIndex = this.steps.indexOf(processingStep);
      return ((stepIndex + 0.5) / this.steps.length) * 100;
    }

    return (completedSteps / this.steps.length) * 100;
  }

  private formatDuration(ms: number): string {
    if (ms < 1000) return `${ms}ms`;
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
    const mins = Math.floor(ms / 60000);
    const secs = Math.floor((ms % 60000) / 1000);
    return `${mins}m ${secs}s`;
  }

  private getElapsedTime(): string {
    if (!this.startTime) return '';
    const elapsed = Date.now() - this.startTime;
    return this.formatDuration(elapsed);
  }

  private renderStep(step: ProcessStep, index: number): string {
    const config = this.getStatusConfig(step.status);
    const isFirst = index === 0;
    const isLast = index === this.steps.length - 1;

    return `
      <div class="process-step ${step.status === 'erro' ? 'process-step-error' : ''}" data-step-id="${step.id}">
        <!-- Connector Line -->
        ${!isFirst ? `
          <div class="process-connector ${this.steps[index - 1].status === 'concluido' ? 'process-connector-active' : ''}"></div>
        ` : ''}

        <!-- Step Content -->
        <div class="process-step-content">
          <!-- Icon -->
          <div class="process-step-icon ${config.bgClass}">
            ${step.status === 'processando' ? `
              <i class="fas fa-spinner fa-spin ${config.iconClass}"></i>
            ` : step.status === 'concluido' ? `
              <i class="fas fa-check ${config.iconClass}"></i>
            ` : step.status === 'erro' ? `
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
            ` : ''}
          </div>

          <!-- Error Details Button -->
          ${step.status === 'erro' ? `
            <button class="process-step-details-btn" data-step-id="${step.id}">
              <i class="fas fa-info-circle"></i>
              Ver detalhes
            </button>
          ` : ''}
        </div>
      </div>
    `;
  }

  private render(): void {
    const progress = this.getProgress();
    const isProcessing = this.steps.some(s => s.status === 'processando');
    const hasError = this.steps.some(s => s.status === 'erro');
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
          ` : ''}
        </div>

        <!-- Progress Bar -->
        <div class="process-progress">
          <div class="process-progress-bar">
            <div
              class="process-progress-fill ${hasError ? 'process-progress-error' : ''}"
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
        ` : ''}

        <!-- Steps -->
        <div class="process-steps-list">
          ${this.steps.map((step, index) => this.renderStep(step, index)).join('')}
        </div>

        <!-- Error Actions -->
        ${hasError ? `
          <div class="process-error-actions">
            <button class="process-retry-btn" data-action="retry">
              <i class="fas fa-redo"></i>
              Tentar novamente
            </button>
          </div>
        ` : ''}
      </div>
    `;

    this.attachEventListeners();
  }

  private attachEventListeners(): void {
    // Retry buttons
    this.container.querySelectorAll<HTMLButtonElement>('[data-action="retry"]').forEach(btn => {
      btn.addEventListener('click', () => this.options.onRetry());
    });

    // Details buttons
    this.container.querySelectorAll<HTMLButtonElement>('.process-step-details-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const stepId = btn.dataset.stepId;
        const step = this.steps.find(s => s.id === stepId);
        if (step) {
          this.options.onShowDetails(step);
        }
      });
    });
  }

  public start(): void {
    this.startTime = Date.now();
    this.showWarning = false;

    // Start elapsed time update
    this.elapsedInterval = window.setInterval(() => {
      this.render();

      // Check for warning
      if (!this.showWarning && Date.now() - this.startTime > this.options.warningThresholdMs) {
        this.showWarning = true;
        this.render();
      }
    }, 1000);

    this.render();
  }

  public stop(): void {
    if (this.elapsedInterval) {
      clearInterval(this.elapsedInterval);
      this.elapsedInterval = null;
    }
  }

  public updateStep(stepId: string, updates: Partial<ProcessStep>): void {
    const step = this.steps.find(s => s.id === stepId);
    if (step) {
      Object.assign(step, updates);
      this.render();
    }
  }

  public setStepStatus(stepId: string, status: StepStatus, message?: string): void {
    this.updateStep(stepId, {
      status,
      message: message ?? this.getDefaultMessage(status),
    });
  }

  private getDefaultMessage(status: StepStatus): string {
    switch (status) {
      case 'aguardando': return 'Aguardando...';
      case 'processando': return 'Processando...';
      case 'concluido': return 'Concluído';
      case 'erro': return 'Erro no processamento';
    }
  }

  public reset(): void {
    this.stop();
    this.startTime = 0;
    this.showWarning = false;
    this.initializeSteps();
    this.render();
  }

  public complete(): void {
    this.stop();
    this.steps.forEach(step => {
      if (step.status !== 'erro') {
        step.status = 'concluido';
      }
    });
    this.render();
  }

  public destroy(): void {
    this.stop();
    this.container.innerHTML = '';
  }
}

// CSS Styles
export const processStepsStyles = `
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
