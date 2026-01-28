// Generated from TypeScript - DO NOT EDIT DIRECTLY
// Source: src\shared\timezone.ts
// Built at: 2026-01-28T12:56:50.180Z

"use strict";
(() => {
  // src/shared/timezone.ts
  var SYSTEM_TIMEZONE = "America/Campo_Grande";
  function formatDateTime(isoString, options = {}) {
    if (!isoString) return "-";
    try {
      const defaultOptions = {
        timeZone: SYSTEM_TIMEZONE,
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit"
      };
      return new Date(isoString).toLocaleString("pt-BR", { ...defaultOptions, ...options });
    } catch (e) {
      console.warn("Erro ao formatar data:", isoString, e);
      return isoString;
    }
  }
  function formatDate(isoString) {
    if (!isoString) return "-";
    try {
      return new Date(isoString).toLocaleDateString("pt-BR", {
        timeZone: SYSTEM_TIMEZONE,
        day: "2-digit",
        month: "2-digit",
        year: "numeric"
      });
    } catch (e) {
      console.warn("Erro ao formatar data:", isoString, e);
      return isoString;
    }
  }
  function formatTime(isoString) {
    if (!isoString) return "-";
    try {
      return new Date(isoString).toLocaleTimeString("pt-BR", {
        timeZone: SYSTEM_TIMEZONE,
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit"
      });
    } catch (e) {
      console.warn("Erro ao formatar hora:", isoString, e);
      return isoString;
    }
  }
  function formatDateTimeShort(isoString) {
    if (!isoString) return "-";
    try {
      return new Date(isoString).toLocaleString("pt-BR", {
        timeZone: SYSTEM_TIMEZONE,
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit"
      });
    } catch (e) {
      console.warn("Erro ao formatar data:", isoString, e);
      return isoString;
    }
  }
  function formatRelativeTime(isoString) {
    if (!isoString) return "-";
    try {
      const date = new Date(isoString);
      const now = /* @__PURE__ */ new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffMinutes = Math.floor(diffMs / 6e4);
      const diffHours = Math.floor(diffMs / 36e5);
      const diffDays = Math.floor(diffMs / 864e5);
      if (diffMinutes < 1) return "agora";
      if (diffMinutes < 60) return `h\xE1 ${diffMinutes} min`;
      if (diffHours < 24) return `h\xE1 ${diffHours}h`;
      if (diffDays < 7) return `h\xE1 ${diffDays}d`;
      return formatDate(isoString);
    } catch {
      return formatDate(isoString);
    }
  }
  function toLocalDate(isoString) {
    if (!isoString) return null;
    try {
      return new Date(isoString);
    } catch {
      return null;
    }
  }
  function getSystemTimezone() {
    return SYSTEM_TIMEZONE;
  }
  window.formatDateTime = formatDateTime;
  window.formatDate = formatDate;
  window.formatTime = formatTime;
  window.formatDateTimeShort = formatDateTimeShort;
  window.formatRelativeTime = formatRelativeTime;
  window.toLocalDate = toLocalDate;
  window.getSystemTimezone = getSystemTimezone;
  window.SYSTEM_TIMEZONE = SYSTEM_TIMEZONE;
})();
//# sourceMappingURL=timezone.js.map
