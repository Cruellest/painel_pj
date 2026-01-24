/**
 * timezone.ts - Utilitários de timezone para o Portal PGE-MS
 *
 * POLÍTICA DE TIMEZONE DO SISTEMA:
 * - Backend grava em UTC
 * - Frontend exibe em America/Campo_Grande (UTC-4)
 *
 * IMPORTANTE: Incluir este arquivo em TODAS as páginas que exibem timestamps.
 *
 * Migrado de JavaScript para TypeScript
 */

export {};

// ============================================
// Constants
// ============================================

/** Timezone do sistema (Mato Grosso do Sul) */
const SYSTEM_TIMEZONE = 'America/Campo_Grande';

// ============================================
// Types
// ============================================

interface DateTimeFormatOptions {
  timeZone?: string;
  day?: '2-digit' | 'numeric';
  month?: '2-digit' | 'numeric' | 'short' | 'long';
  year?: '2-digit' | 'numeric';
  hour?: '2-digit' | 'numeric';
  minute?: '2-digit' | 'numeric';
  second?: '2-digit' | 'numeric';
}

// ============================================
// Formatting Functions
// ============================================

/**
 * Formata um timestamp ISO para data e hora no timezone local.
 * @param isoString - Timestamp no formato ISO 8601
 * @param options - Opções de formatação (opcional)
 * @returns Data/hora formatada (DD/MM/YYYY HH:MM:SS)
 */
function formatDateTime(
  isoString: string | null | undefined,
  options: DateTimeFormatOptions = {}
): string {
  if (!isoString) return '-';

  try {
    const defaultOptions: Intl.DateTimeFormatOptions = {
      timeZone: SYSTEM_TIMEZONE,
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    };
    return new Date(isoString).toLocaleString('pt-BR', { ...defaultOptions, ...options });
  } catch (e) {
    console.warn('Erro ao formatar data:', isoString, e);
    return isoString;
  }
}

/**
 * Formata apenas a data no timezone local.
 * @param isoString - Timestamp no formato ISO 8601
 * @returns Data formatada (DD/MM/YYYY)
 */
function formatDate(isoString: string | null | undefined): string {
  if (!isoString) return '-';

  try {
    return new Date(isoString).toLocaleDateString('pt-BR', {
      timeZone: SYSTEM_TIMEZONE,
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    });
  } catch (e) {
    console.warn('Erro ao formatar data:', isoString, e);
    return isoString;
  }
}

/**
 * Formata apenas a hora no timezone local.
 * @param isoString - Timestamp no formato ISO 8601
 * @returns Hora formatada (HH:MM:SS)
 */
function formatTime(isoString: string | null | undefined): string {
  if (!isoString) return '-';

  try {
    return new Date(isoString).toLocaleTimeString('pt-BR', {
      timeZone: SYSTEM_TIMEZONE,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch (e) {
    console.warn('Erro ao formatar hora:', isoString, e);
    return isoString;
  }
}

/**
 * Formata data e hora de forma curta (sem segundos).
 * @param isoString - Timestamp no formato ISO 8601
 * @returns Data/hora formatada (DD/MM/YYYY HH:MM)
 */
function formatDateTimeShort(isoString: string | null | undefined): string {
  if (!isoString) return '-';

  try {
    return new Date(isoString).toLocaleString('pt-BR', {
      timeZone: SYSTEM_TIMEZONE,
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch (e) {
    console.warn('Erro ao formatar data:', isoString, e);
    return isoString;
  }
}

/**
 * Formata data de forma relativa (há X minutos, há X horas, etc).
 * @param isoString - Timestamp no formato ISO 8601
 * @returns Tempo relativo
 */
function formatRelativeTime(isoString: string | null | undefined): string {
  if (!isoString) return '-';

  try {
    const date = new Date(isoString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMinutes = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMinutes < 1) return 'agora';
    if (diffMinutes < 60) return `há ${diffMinutes} min`;
    if (diffHours < 24) return `há ${diffHours}h`;
    if (diffDays < 7) return `há ${diffDays}d`;

    return formatDate(isoString);
  } catch {
    return formatDate(isoString);
  }
}

/**
 * Converte um timestamp ISO para objeto Date no timezone local.
 * @param isoString - Timestamp no formato ISO 8601
 * @returns Date object ou null se inválido
 */
function toLocalDate(isoString: string | null | undefined): Date | null {
  if (!isoString) return null;

  try {
    return new Date(isoString);
  } catch {
    return null;
  }
}

/**
 * Retorna o nome do timezone do sistema.
 */
function getSystemTimezone(): string {
  return SYSTEM_TIMEZONE;
}

// ============================================
// Global Exports
// ============================================

declare global {
  interface Window {
    formatDateTime: typeof formatDateTime;
    formatDate: typeof formatDate;
    formatTime: typeof formatTime;
    formatDateTimeShort: typeof formatDateTimeShort;
    formatRelativeTime: typeof formatRelativeTime;
    toLocalDate: typeof toLocalDate;
    getSystemTimezone: typeof getSystemTimezone;
    SYSTEM_TIMEZONE: string;
  }
}

// Exporta funções para uso global
window.formatDateTime = formatDateTime;
window.formatDate = formatDate;
window.formatTime = formatTime;
window.formatDateTimeShort = formatDateTimeShort;
window.formatRelativeTime = formatRelativeTime;
window.toLocalDate = toLocalDate;
window.getSystemTimezone = getSystemTimezone;
window.SYSTEM_TIMEZONE = SYSTEM_TIMEZONE;
