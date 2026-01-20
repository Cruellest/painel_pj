/**
 * timezone.js - Utilitários de timezone para o Portal PGE-MS
 *
 * POLÍTICA DE TIMEZONE DO SISTEMA:
 * - Backend grava em UTC
 * - Frontend exibe em America/Campo_Grande (UTC-4)
 *
 * IMPORTANTE: Incluir este arquivo em TODAS as páginas que exibem timestamps.
 *
 * USO:
 *   formatDateTime('2026-01-20T18:30:00Z')  // "20/01/2026 14:30:00"
 *   formatDate('2026-01-20T18:30:00Z')      // "20/01/2026"
 *   formatTime('2026-01-20T18:30:00Z')      // "14:30:00"
 */

// Timezone do sistema (Mato Grosso do Sul)
const SYSTEM_TIMEZONE = 'America/Campo_Grande';

/**
 * Formata um timestamp ISO para data e hora no timezone local.
 * @param {string} isoString - Timestamp no formato ISO 8601
 * @param {object} options - Opções de formatação (opcional)
 * @returns {string} - Data/hora formatada (DD/MM/YYYY HH:MM:SS)
 */
function formatDateTime(isoString, options = {}) {
    if (!isoString) return '-';

    try {
        const defaultOptions = {
            timeZone: SYSTEM_TIMEZONE,
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        };
        return new Date(isoString).toLocaleString('pt-BR', { ...defaultOptions, ...options });
    } catch (e) {
        console.warn('Erro ao formatar data:', isoString, e);
        return isoString;
    }
}

/**
 * Formata apenas a data no timezone local.
 * @param {string} isoString - Timestamp no formato ISO 8601
 * @returns {string} - Data formatada (DD/MM/YYYY)
 */
function formatDate(isoString) {
    if (!isoString) return '-';

    try {
        return new Date(isoString).toLocaleDateString('pt-BR', {
            timeZone: SYSTEM_TIMEZONE,
            day: '2-digit',
            month: '2-digit',
            year: 'numeric'
        });
    } catch (e) {
        console.warn('Erro ao formatar data:', isoString, e);
        return isoString;
    }
}

/**
 * Formata apenas a hora no timezone local.
 * @param {string} isoString - Timestamp no formato ISO 8601
 * @returns {string} - Hora formatada (HH:MM:SS)
 */
function formatTime(isoString) {
    if (!isoString) return '-';

    try {
        return new Date(isoString).toLocaleTimeString('pt-BR', {
            timeZone: SYSTEM_TIMEZONE,
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
    } catch (e) {
        console.warn('Erro ao formatar hora:', isoString, e);
        return isoString;
    }
}

/**
 * Formata data e hora de forma curta (sem segundos).
 * @param {string} isoString - Timestamp no formato ISO 8601
 * @returns {string} - Data/hora formatada (DD/MM/YYYY HH:MM)
 */
function formatDateTimeShort(isoString) {
    if (!isoString) return '-';

    try {
        return new Date(isoString).toLocaleString('pt-BR', {
            timeZone: SYSTEM_TIMEZONE,
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    } catch (e) {
        console.warn('Erro ao formatar data:', isoString, e);
        return isoString;
    }
}

/**
 * Formata data de forma relativa (há X minutos, há X horas, etc).
 * @param {string} isoString - Timestamp no formato ISO 8601
 * @returns {string} - Tempo relativo
 */
function formatRelativeTime(isoString) {
    if (!isoString) return '-';

    try {
        const date = new Date(isoString);
        const now = new Date();
        const diffMs = now - date;
        const diffMinutes = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMs / 3600000);
        const diffDays = Math.floor(diffMs / 86400000);

        if (diffMinutes < 1) return 'agora';
        if (diffMinutes < 60) return `há ${diffMinutes} min`;
        if (diffHours < 24) return `há ${diffHours}h`;
        if (diffDays < 7) return `há ${diffDays}d`;

        return formatDate(isoString);
    } catch (e) {
        return formatDate(isoString);
    }
}

/**
 * Converte um timestamp ISO para objeto Date no timezone local.
 * @param {string} isoString - Timestamp no formato ISO 8601
 * @returns {Date|null} - Date object ou null se inválido
 */
function toLocalDate(isoString) {
    if (!isoString) return null;

    try {
        return new Date(isoString);
    } catch (e) {
        return null;
    }
}

/**
 * Retorna o nome do timezone do sistema.
 * @returns {string} - Nome do timezone
 */
function getSystemTimezone() {
    return SYSTEM_TIMEZONE;
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
