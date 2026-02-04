/**
 * Utilitários de UI compartilhados
 */

import type { ToastType } from '../types/api';

// ============================================
// Toast Notifications
// ============================================

const TOAST_COLORS: Record<ToastType, string> = {
  success: 'bg-green-500',
  error: 'bg-red-500',
  warning: 'bg-yellow-500',
  info: 'bg-blue-500',
};

const TOAST_ICONS: Record<ToastType, string> = {
  success: 'fa-check-circle',
  error: 'fa-exclamation-circle',
  warning: 'fa-exclamation-triangle',
  info: 'fa-info-circle',
};

/**
 * Exibe uma notificação toast
 *
 * @param message - Mensagem a exibir
 * @param type - Tipo do toast (success, error, warning, info)
 * @param duration - Duração em ms (padrão: 5000)
 */
export function showToast(
  message: string,
  type: ToastType = 'info',
  duration = 5000
): void {
  const container = document.getElementById('toast-container');
  if (!container) {
    console.warn('Toast container not found');
    return;
  }

  const toast = document.createElement('div');
  toast.className = `toast ${TOAST_COLORS[type]} text-white px-4 py-3 rounded-lg shadow-lg flex items-center gap-2 min-w-[280px]`;
  toast.innerHTML = `
    <i class="fas ${TOAST_ICONS[type]}"></i>
    <span class="flex-1">${escapeHtml(message)}</span>
    <button onclick="this.parentElement.remove()" class="text-white/80 hover:text-white">
      <i class="fas fa-times"></i>
    </button>
  `;

  container.appendChild(toast);

  setTimeout(() => toast.remove(), duration);
}

// ============================================
// Estado de elementos
// ============================================

/**
 * Mostra um elemento pelo ID
 */
export function showElement(id: string): void {
  const el = document.getElementById(id);
  if (el) el.classList.remove('hidden');
}

/**
 * Esconde um elemento pelo ID
 */
export function hideElement(id: string): void {
  const el = document.getElementById(id);
  if (el) el.classList.add('hidden');
}

/**
 * Alterna visibilidade de um elemento
 */
export function toggleElement(id: string): void {
  const el = document.getElementById(id);
  if (el) el.classList.toggle('hidden');
}

/**
 * Mostra apenas um estado entre vários
 * Útil para máquinas de estado de UI (loading, resultado, erro, etc.)
 *
 * @param activeState - Estado a mostrar
 * @param states - Lista de estados possíveis
 * @param prefix - Prefixo dos IDs (ex: 'estado-' para 'estado-loading')
 */
export function showState(
  activeState: string,
  states: string[],
  prefix = 'estado-'
): void {
  for (const state of states) {
    const el = document.getElementById(`${prefix}${state}`);
    if (el) {
      if (state === activeState) {
        el.classList.remove('hidden');
      } else {
        el.classList.add('hidden');
      }
    }
  }
}

// ============================================
// Modais
// ============================================

/**
 * Abre um modal pelo ID
 */
export function openModal(id: string): void {
  showElement(id);
}

/**
 * Fecha um modal pelo ID
 */
export function closeModal(id: string): void {
  hideElement(id);
}

// ============================================
// Helpers de DOM
// ============================================

/**
 * Escapa HTML para prevenir XSS
 */
export function escapeHtml(text: string): string {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

/**
 * Define o texto de um elemento
 */
export function setText(id: string, text: string): void {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

/**
 * Define o HTML de um elemento (usar com cuidado - sanitizar input)
 */
export function setHtml(id: string, html: string): void {
  const el = document.getElementById(id);
  if (el) el.innerHTML = html;
}

/**
 * Obtém o valor de um input
 */
export function getInputValue(id: string): string {
  const el = document.getElementById(id) as HTMLInputElement | null;
  return el?.value?.trim() ?? '';
}

/**
 * Define o valor de um input
 */
export function setInputValue(id: string, value: string): void {
  const el = document.getElementById(id) as HTMLInputElement | null;
  if (el) el.value = value;
}

// ============================================
// Formatação
// ============================================

/**
 * Formata data para pt-BR
 */
export function formatDate(dateStr: string): string {
  try {
    const date = new Date(dateStr);
    if (isNaN(date.getTime())) return '-';
    return date.toLocaleDateString('pt-BR');
  } catch {
    return '-';
  }
}

/**
 * Formata data e hora para pt-BR
 */
export function formatDateTime(dateStr: string): { data: string; hora: string } {
  try {
    const date = new Date(dateStr);
    if (isNaN(date.getTime())) return { data: '-', hora: '-' };
    return {
      data: date.toLocaleDateString('pt-BR'),
      hora: date.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }),
    };
  } catch {
    return { data: '-', hora: '-' };
  }
}

// ============================================
// Markdown básico para HTML
// ============================================

/**
 * Converte markdown básico para HTML
 * Útil para exportação de documentos
 */
export function markdownToHtml(text: string): string {
  if (!text) return '';
  return text
    .replace(/^### (.*$)/gim, '<h3>$1</h3>')
    .replace(/^## (.*$)/gim, '<h2>$1</h2>')
    .replace(/^# (.*$)/gim, '<h1>$1</h1>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
    .replace(/^- (.*$)/gim, '<li>$1</li>')
    .replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>')
    .replace(/^> (.*$)/gim, '<blockquote>$1</blockquote>')
    .replace(/\n\n/g, '</p><p>')
    .replace(/\n/g, '<br>');
}

// ============================================
// Debounce/Throttle
// ============================================

/**
 * Debounce uma função
 */
export function debounce<T extends (...args: unknown[]) => unknown>(
  fn: T,
  delay: number
): (...args: Parameters<T>) => void {
  let timeoutId: ReturnType<typeof setTimeout>;
  return (...args: Parameters<T>) => {
    clearTimeout(timeoutId);
    timeoutId = setTimeout(() => fn(...args), delay);
  };
}

/**
 * Throttle uma função
 */
export function throttle<T extends (...args: unknown[]) => unknown>(
  fn: T,
  limit: number
): (...args: Parameters<T>) => void {
  let inThrottle = false;
  return (...args: Parameters<T>) => {
    if (!inThrottle) {
      fn(...args);
      inThrottle = true;
      setTimeout(() => (inThrottle = false), limit);
    }
  };
}
