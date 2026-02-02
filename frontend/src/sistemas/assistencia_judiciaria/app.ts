/**
 * Sistema de Assistência Judiciária - PGE-MS
 * Consulta de processos no TJ-MS com análise por IA
 *
 * Migrado de JavaScript para TypeScript
 */

import {
  createApiClient,
  checkAuth,
  logout as authLogout,
} from '../../shared/api';
import {
  showToast,
  showState,
  escapeHtml,
  markdownToHtml,
  formatDate,
} from '../../shared/ui';
import type {
  HistoricoItem,
  AvaliacaoFeedback,
  FeedbackResponse,
} from '../../types/api';

// ============================================
// Types
// ============================================

interface AppConfig {
  apiKey: string;
  model: string;
}

interface AppState {
  historico: HistoricoItem[];
  ultimoResultado: ConsultaResult | null;
  config: AppConfig;
}

interface ConsultaRequest {
  cnj: string;
  model: string;
  force: boolean;
}

interface ConsultaResult {
  consulta_id?: number;
  dados?: ProcessoDados;
  relatorio?: string;
  cached?: boolean;
  consultado_em?: string;
}

interface ProcessoDados {
  classe?: string;
  numero_processo?: string;
}

// ============================================
// Configuração
// ============================================

const API_BASE = '/assistencia/api';
const api = createApiClient(API_BASE);

const ESTADOS = ['inicial', 'loading', 'resultado', 'erro'];

// Estado da aplicação
const appState: AppState = {
  historico: [],
  ultimoResultado: null,
  config: {
    apiKey: '',
    model: 'google/gemini-3-flash-preview',
  },
};

// ============================================
// Funções de UI específicas
// ============================================

function mostrarEstado(estado: string): void {
  showState(estado, ESTADOS, 'estado-');
}

function voltarInicio(): void {
  mostrarEstado('inicial');
}

// ============================================
// Histórico
// ============================================

async function carregarHistorico(): Promise<void> {
  try {
    const historico = await api.get<HistoricoItem[]>('/historico');
    if (historico && Array.isArray(historico)) {
      appState.historico = historico;
      renderizarHistorico();
    }
  } catch (error) {
    console.error('Erro ao carregar histórico:', error);
  }
}

function renderizarHistorico(): void {
  const container = document.getElementById('historico-list');
  if (!container) return;

  if (!appState.historico || appState.historico.length === 0) {
    container.innerHTML =
      '<p class="text-sm text-gray-400 italic">Nenhuma consulta ainda</p>';
    return;
  }

  container.innerHTML = appState.historico
    .slice(0, 10)
    .map((item) => {
      const cnj = item.cnj || item.numero_cnj || '';
      const classe = item.classe || 'Processo';
      return `
      <div class="flex items-center justify-between p-2 rounded-lg hover:bg-gray-100 transition-colors group">
        <button onclick="consultarProcesso('${escapeHtml(cnj)}')"
          class="flex-1 text-left">
          <div class="font-mono text-xs text-gray-600 group-hover:text-primary-600">${escapeHtml(cnj)}</div>
          <div class="text-xs text-gray-400 truncate">${escapeHtml(classe)}</div>
        </button>
        <button onclick="excluirDoHistorico(${item.id}, event)"
          class="p-1 text-gray-300 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity"
          title="Remover do histórico">
          <i class="fas fa-times text-xs"></i>
        </button>
      </div>
    `;
    })
    .join('');
}

async function excluirDoHistorico(
  id: number,
  event: Event
): Promise<void> {
  event.stopPropagation();
  try {
    const result = await api.delete<{ success: boolean }>(`/historico/${id}`);
    if (result && result.success) {
      await carregarHistorico();
      showToast('Removido do histórico', 'info');
    }
  } catch {
    showToast('Erro ao remover do histórico', 'error');
  }
}

function adicionarHistorico(_cnj: string, _classe?: string): void {
  // O histórico é atualizado automaticamente pelo backend
  carregarHistorico();
}

// ============================================
// Consulta de Processo
// ============================================

async function consultarProcesso(
  cnj?: string,
  forceRefresh = false
): Promise<void> {
  const inputCnj = document.getElementById('input-cnj') as HTMLInputElement | null;

  if (!cnj && inputCnj) {
    cnj = inputCnj.value.trim();
  }

  if (!cnj) {
    showToast('Digite o número do processo', 'warning');
    return;
  }

  // Atualiza input
  if (inputCnj) {
    inputCnj.value = cnj;
  }

  mostrarEstado('loading');

  try {
    const request: ConsultaRequest = {
      cnj,
      model: appState.config.model,
      force: forceRefresh,
    };

    const result = await api.post<ConsultaResult>('/consultar', request);

    if (!result) return;

    appState.ultimoResultado = result;

    // Extrai dados
    const dados = result.dados || {};
    const relatorio = result.relatorio || '';

    // Preenche a UI
    const resultadoCnj = document.getElementById('resultado-cnj');
    if (resultadoCnj) {
      resultadoCnj.textContent = cnj;
    }

    // Mostra indicador de cache
    const cacheIndicator = document.getElementById('cache-indicator');
    if (cacheIndicator) {
      if (result.cached) {
        const dataConsulta = result.consultado_em
          ? formatDate(result.consultado_em)
          : '';
        cacheIndicator.innerHTML = `<i class="fas fa-database text-blue-500"></i> Dados em cache ${dataConsulta ? `(${dataConsulta})` : ''}`;
        cacheIndicator.classList.remove('hidden');
      } else {
        cacheIndicator.classList.add('hidden');
      }
    }

    // Relatório
    const relatorioContainer = document.getElementById('resultado-relatorio');
    if (relatorioContainer) {
      if (relatorio) {
        // Usa marked se disponível, senão fallback
        if (typeof (window as unknown as { marked?: { parse: (s: string) => string } }).marked?.parse === 'function') {
          relatorioContainer.innerHTML = (window as unknown as { marked: { parse: (s: string) => string } }).marked.parse(relatorio);
        } else {
          relatorioContainer.innerHTML = markdownToHtml(relatorio);
        }
      } else {
        relatorioContainer.innerHTML =
          '<p class="text-gray-400 italic">Relatório não disponível</p>';
      }
    }

    // Adiciona ao histórico
    adicionarHistorico(cnj, dados.classe);

    // Verifica se já tem feedback para esta consulta
    if (result.consulta_id) {
      verificarFeedbackExistente(result.consulta_id);
    }

    mostrarEstado('resultado');

    if (result.cached) {
      showToast('Consulta recuperada do cache', 'info');
    } else {
      showToast('Processo consultado com sucesso!', 'success');
    }
  } catch (error) {
    const erroMensagem = document.getElementById('erro-mensagem');
    if (erroMensagem) {
      erroMensagem.textContent =
        (error as Error).message || 'Erro ao consultar processo';
    }
    mostrarEstado('erro');
    showToast('Erro na consulta', 'error');
  }
}

function reconsultarProcesso(): void {
  const resultadoCnj = document.getElementById('resultado-cnj');
  const cnj = resultadoCnj?.textContent;
  if (
    cnj &&
    confirm(
      'Deseja reconsultar este processo? Isso irá buscar dados atualizados do TJ-MS e gerar um novo relatório.'
    )
  ) {
    consultarProcesso(cnj, true);
  }
}

// ============================================
// Feedback da Análise
// ============================================

async function enviarFeedback(avaliacao: AvaliacaoFeedback): Promise<void> {
  if (!appState.ultimoResultado || !appState.ultimoResultado.consulta_id) {
    showToast('Nenhuma consulta para avaliar', 'warning');
    return;
  }

  // Pede comentário para feedback negativo
  let comentario: string | null = null;
  if (avaliacao === 'incorreto' || avaliacao === 'parcial') {
    comentario = prompt(
      'Por favor, descreva brevemente o que estava incorreto (opcional):'
    );
  }

  try {
    const result = await api.post<{ success: boolean }>('/feedback', {
      consulta_id: appState.ultimoResultado.consulta_id,
      avaliacao,
      comentario,
    });

    if (result && result.success) {
      // Mostra feedback enviado
      const feedbackButtons = document.getElementById('feedback-buttons');
      const feedbackEnviado = document.getElementById('feedback-enviado');
      const feedbackEnviadoTipo = document.getElementById('feedback-enviado-tipo');

      if (feedbackButtons) feedbackButtons.classList.add('hidden');
      if (feedbackEnviado) feedbackEnviado.classList.remove('hidden');

      const tipoTexto: Record<AvaliacaoFeedback, string> = {
        correto: 'Análise marcada como correta',
        parcial: 'Análise marcada como parcialmente correta',
        incorreto: 'Análise marcada como incorreta',
        erro_ia: 'Reportado como erro da IA',
      };

      if (feedbackEnviadoTipo) {
        feedbackEnviadoTipo.textContent = tipoTexto[avaliacao] || '';
      }

      showToast('Feedback registrado!', 'success');
    } else {
      showToast('Erro ao enviar feedback', 'error');
    }
  } catch {
    showToast('Erro ao enviar feedback', 'error');
  }
}

async function verificarFeedbackExistente(consultaId: number): Promise<void> {
  try {
    const result = await api.get<FeedbackResponse>(`/feedback/${consultaId}`);

    const feedbackButtons = document.getElementById('feedback-buttons');
    const feedbackEnviado = document.getElementById('feedback-enviado');
    const feedbackEnviadoTipo = document.getElementById('feedback-enviado-tipo');

    if (result && result.has_feedback) {
      // Já tem feedback, mostra o estado de enviado
      if (feedbackButtons) feedbackButtons.classList.add('hidden');
      if (feedbackEnviado) feedbackEnviado.classList.remove('hidden');

      const tipoTexto: Record<AvaliacaoFeedback, string> = {
        correto: 'Análise marcada como correta',
        parcial: 'Análise marcada como parcialmente correta',
        incorreto: 'Análise marcada como incorreta',
        erro_ia: 'Reportado como erro da IA',
      };

      if (feedbackEnviadoTipo && result.avaliacao) {
        feedbackEnviadoTipo.textContent = tipoTexto[result.avaliacao] || '';
      }
    } else {
      // Não tem feedback, mostra botões
      if (feedbackButtons) feedbackButtons.classList.remove('hidden');
      if (feedbackEnviado) feedbackEnviado.classList.add('hidden');
    }
  } catch {
    // Em caso de erro, mostra botões
    const feedbackButtons = document.getElementById('feedback-buttons');
    const feedbackEnviado = document.getElementById('feedback-enviado');
    if (feedbackButtons) feedbackButtons.classList.remove('hidden');
    if (feedbackEnviado) feedbackEnviado.classList.add('hidden');
  }
}

// ============================================
// Download de Documentos
// ============================================

function downloadDocumento(formato: 'docx' | 'pdf'): void {
  if (!appState.ultimoResultado) {
    showToast('Nenhum resultado para exportar', 'warning');
    return;
  }

  const resultadoCnj = document.getElementById('resultado-cnj');
  const cnj = resultadoCnj?.textContent || 'processo';
  const relatorio = appState.ultimoResultado.relatorio || '';
  const htmlContent = markdownToHtml(relatorio);

  if (formato === 'docx') {
    // Gera DOCX via HTML
    const docContent = `
      <!DOCTYPE html>
      <html>
      <head>
        <meta charset="utf-8">
        <title>Relatório - Assistência Judiciária</title>
        <style>
          body { font-family: 'Calibri', sans-serif; font-size: 12pt; line-height: 1.5; margin: 2cm; }
          h1 { font-size: 18pt; color: #1e3a5f; border-bottom: 2px solid #1e3a5f; padding-bottom: 10px; text-align: center; }
          h2 { font-size: 14pt; color: #2563eb; margin-top: 20px; }
          h3 { font-size: 12pt; color: #374151; }
          p { margin: 10px 0; text-align: justify; }
          ul, ol { margin: 10px 0; padding-left: 30px; }
          li { margin: 5px 0; }
          strong { color: #1f2937; }
          blockquote { margin: 10px 20px; padding: 10px; background: #f5f5f5; border-left: 3px solid #2563eb; font-style: italic; }
        </style>
      </head>
      <body>
        <h1>Análise de Processo</h1>
        <p style="text-align: center; color: #666;">Processo: ${escapeHtml(cnj)}</p>
        <hr>
        <p>${htmlContent}</p>
      </body>
      </html>
    `;

    const blob = new Blob([docContent], {
      type: 'application/vnd.ms-word;charset=utf-8',
    });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `relatorio_${cnj.replace(/\D/g, '')}.doc`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(link.href);

    showToast('Download do Word iniciado!', 'success');
  } else if (formato === 'pdf') {
    // Abre janela de impressão para PDF
    const printWindow = window.open('', '_blank');
    if (!printWindow) {
      showToast('Popup bloqueado. Habilite popups para este site.', 'error');
      return;
    }

    printWindow.document.write(`
      <!DOCTYPE html>
      <html>
      <head>
        <meta charset="utf-8">
        <title>Relatório - Assistência Judiciária</title>
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
          blockquote { margin: 10px 20px; padding: 10px; background: #f5f5f5; border-left: 3px solid #2563eb; font-style: italic; }
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
          <h1>Análise de Processo</h1>
          <p>Sistema de Assistência Judiciária - PGE-MS</p>
          <p>Processo: ${escapeHtml(cnj)}</p>
        </div>
        <hr>
        <p>${htmlContent}</p>
        <div class="footer">
          <p>Documento gerado em ${new Date().toLocaleDateString('pt-BR')} às ${new Date().toLocaleTimeString('pt-BR')}</p>
          <p>Procuradoria-Geral do Estado de Mato Grosso do Sul</p>
        </div>
      </body>
      </html>
    `);
    printWindow.document.close();

    setTimeout(() => {
      printWindow.print();
    }, 500);

    showToast('Janela de impressão aberta!', 'success');
  }
}

// ============================================
// Configurações
// ============================================

async function carregarSettings(): Promise<void> {
  try {
    const config = await api.get<{ default_model?: string }>('/settings');
    if (config) {
      appState.config.model =
        config.default_model || 'google/gemini-3-flash-preview';
    }
  } catch (error) {
    console.error('Erro ao carregar settings:', error);
  }
}

// ============================================
// Logout
// ============================================

function logout(): void {
  authLogout();
}

// ============================================
// Inicialização
// ============================================

function initApp(): void {
  // Verifica autenticação
  if (!checkAuth('/assistencia-judiciaria')) return;

  // Botão consultar
  const btnConsultar = document.getElementById('btn-consultar');
  if (btnConsultar) {
    btnConsultar.addEventListener('click', () => consultarProcesso());
  }

  // Enter no input
  const inputCnj = document.getElementById('input-cnj');
  if (inputCnj) {
    inputCnj.addEventListener('keypress', (e) => {
      if ((e as KeyboardEvent).key === 'Enter') consultarProcesso();
    });
  }

  // Downloads
  const btnDocx = document.getElementById('btn-download-docx');
  const btnPdf = document.getElementById('btn-download-pdf');
  if (btnDocx) {
    btnDocx.addEventListener('click', () => downloadDocumento('docx'));
  }
  if (btnPdf) {
    btnPdf.addEventListener('click', () => downloadDocumento('pdf'));
  }

  // Carrega estado inicial
  carregarHistorico();
  carregarSettings();
}

// Inicializa quando o DOM estiver pronto
document.addEventListener('DOMContentLoaded', initApp);

// ============================================
// Exporta funções para uso global (onclick no HTML)
// ============================================

// Declara o tipo da janela com as funções globais
declare global {
  interface Window {
    consultarProcesso: typeof consultarProcesso;
    reconsultarProcesso: typeof reconsultarProcesso;
    enviarFeedback: typeof enviarFeedback;
    downloadDocumento: typeof downloadDocumento;
    voltarInicio: typeof voltarInicio;
    excluirDoHistorico: typeof excluirDoHistorico;
    logout: typeof logout;
  }
}

// Exponha funções globalmente
window.consultarProcesso = consultarProcesso;
window.reconsultarProcesso = reconsultarProcesso;
window.enviarFeedback = enviarFeedback;
window.downloadDocumento = downloadDocumento;
window.voltarInicio = voltarInicio;
window.excluirDoHistorico = excluirDoHistorico;
window.logout = logout;
