// Generated from TypeScript - DO NOT EDIT DIRECTLY
// Source: src\sistemas\assistencia_judiciaria\app.ts
// Built at: 2026-01-30T21:41:45.038Z

"use strict";
(() => {
  // src/shared/api.ts
  function getAuthToken() {
    return localStorage.getItem("access_token");
  }
  function checkAuth(redirectPath) {
    const token = getAuthToken();
    if (!token) {
      const next = redirectPath || window.location.pathname;
      window.location.href = `/login?next=${encodeURIComponent(next)}`;
      return false;
    }
    return true;
  }
  function logout() {
    localStorage.removeItem("access_token");
    window.location.href = "/login";
  }
  async function apiRequest(baseUrl, endpoint, options = {}) {
    if (!checkAuth()) return null;
    const token = getAuthToken();
    const { responseType = "json", headers: customHeaders, ...restOptions } = options;
    const headers = {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...customHeaders
    };
    try {
      const response = await fetch(`${baseUrl}${endpoint}`, {
        headers,
        ...restOptions
      });
      if (response.status === 401) {
        logout();
        return null;
      }
      if (responseType === "blob") {
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        return await response.blob();
      }
      if (responseType === "text") {
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        return await response.text();
      }
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || data.message || `HTTP ${response.status}`);
      }
      return data;
    } catch (error) {
      console.error(`API Error [${endpoint}]:`, error);
      throw error;
    }
  }
  function createApiClient(baseUrl) {
    return {
      get: (endpoint, options) => apiRequest(baseUrl, endpoint, { ...options, method: "GET" }),
      post: (endpoint, body, options) => apiRequest(baseUrl, endpoint, {
        ...options,
        method: "POST",
        body: body ? JSON.stringify(body) : void 0
      }),
      put: (endpoint, body, options) => apiRequest(baseUrl, endpoint, {
        ...options,
        method: "PUT",
        body: body ? JSON.stringify(body) : void 0
      }),
      delete: (endpoint, options) => apiRequest(baseUrl, endpoint, { ...options, method: "DELETE" }),
      /**
       * Requisição com blob response (para downloads)
       */
      blob: (endpoint, options) => apiRequest(baseUrl, endpoint, { ...options, responseType: "blob" })
    };
  }

  // src/shared/ui.ts
  var TOAST_COLORS = {
    success: "bg-green-500",
    error: "bg-red-500",
    warning: "bg-yellow-500",
    info: "bg-blue-500"
  };
  var TOAST_ICONS = {
    success: "fa-check-circle",
    error: "fa-exclamation-circle",
    warning: "fa-exclamation-triangle",
    info: "fa-info-circle"
  };
  function showToast(message, type = "info", duration = 5e3) {
    const container = document.getElementById("toast-container");
    if (!container) {
      console.warn("Toast container not found");
      return;
    }
    const toast = document.createElement("div");
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
  function showState(activeState, states, prefix = "estado-") {
    for (const state of states) {
      const el = document.getElementById(`${prefix}${state}`);
      if (el) {
        if (state === activeState) {
          el.classList.remove("hidden");
        } else {
          el.classList.add("hidden");
        }
      }
    }
  }
  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }
  function formatDate(dateStr) {
    try {
      const date = new Date(dateStr);
      if (isNaN(date.getTime())) return "-";
      return date.toLocaleDateString("pt-BR");
    } catch {
      return "-";
    }
  }
  function markdownToHtml(text) {
    if (!text) return "";
    return text.replace(/^### (.*$)/gim, "<h3>$1</h3>").replace(/^## (.*$)/gim, "<h2>$1</h2>").replace(/^# (.*$)/gim, "<h1>$1</h1>").replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>").replace(/\*([^*]+)\*/g, "<em>$1</em>").replace(/^- (.*$)/gim, "<li>$1</li>").replace(/(<li>.*<\/li>)/s, "<ul>$1</ul>").replace(/^> (.*$)/gim, "<blockquote>$1</blockquote>").replace(/\n\n/g, "</p><p>").replace(/\n/g, "<br>");
  }

  // src/sistemas/assistencia_judiciaria/app.ts
  var API_BASE = "/assistencia/api";
  var api = createApiClient(API_BASE);
  var ESTADOS = ["inicial", "loading", "resultado", "erro"];
  var appState = {
    historico: [],
    ultimoResultado: null,
    config: {
      apiKey: "",
      model: "google/gemini-3-flash-preview"
    }
  };
  function mostrarEstado(estado) {
    showState(estado, ESTADOS, "estado-");
  }
  function voltarInicio() {
    mostrarEstado("inicial");
  }
  async function carregarHistorico() {
    try {
      const historico = await api.get("/historico");
      if (historico && Array.isArray(historico)) {
        appState.historico = historico;
        renderizarHistorico();
      }
    } catch (error) {
      console.error("Erro ao carregar hist\xF3rico:", error);
    }
  }
  function renderizarHistorico() {
    const container = document.getElementById("historico-list");
    if (!container) return;
    if (!appState.historico || appState.historico.length === 0) {
      container.innerHTML = '<p class="text-sm text-gray-400 italic">Nenhuma consulta ainda</p>';
      return;
    }
    container.innerHTML = appState.historico.slice(0, 10).map((item) => {
      const cnj = item.cnj || item.numero_cnj || "";
      const classe = item.classe || "Processo";
      return `
      <div class="flex items-center justify-between p-2 rounded-lg hover:bg-gray-100 transition-colors group">
        <button onclick="consultarProcesso('${escapeHtml(cnj)}')"
          class="flex-1 text-left">
          <div class="font-mono text-xs text-gray-600 group-hover:text-primary-600">${escapeHtml(cnj)}</div>
          <div class="text-xs text-gray-400 truncate">${escapeHtml(classe)}</div>
        </button>
        <button onclick="excluirDoHistorico(${item.id}, event)"
          class="p-1 text-gray-300 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity"
          title="Remover do hist\xF3rico">
          <i class="fas fa-times text-xs"></i>
        </button>
      </div>
    `;
    }).join("");
  }
  async function excluirDoHistorico(id, event) {
    event.stopPropagation();
    try {
      const result = await api.delete(`/historico/${id}`);
      if (result && result.success) {
        await carregarHistorico();
        showToast("Removido do hist\xF3rico", "info");
      }
    } catch {
      showToast("Erro ao remover do hist\xF3rico", "error");
    }
  }
  function adicionarHistorico(_cnj, _classe) {
    carregarHistorico();
  }
  async function consultarProcesso(cnj, forceRefresh = false) {
    const inputCnj = document.getElementById("input-cnj");
    if (!cnj && inputCnj) {
      cnj = inputCnj.value.trim();
    }
    if (!cnj) {
      showToast("Digite o n\xFAmero do processo", "warning");
      return;
    }
    if (inputCnj) {
      inputCnj.value = cnj;
    }
    mostrarEstado("loading");
    try {
      const request = {
        cnj,
        model: appState.config.model,
        force: forceRefresh
      };
      const result = await api.post("/consultar", request);
      if (!result) return;
      appState.ultimoResultado = result;
      const dados = result.dados || {};
      const relatorio = result.relatorio || "";
      const resultadoCnj = document.getElementById("resultado-cnj");
      if (resultadoCnj) {
        resultadoCnj.textContent = cnj;
      }
      const cacheIndicator = document.getElementById("cache-indicator");
      if (cacheIndicator) {
        if (result.cached) {
          const dataConsulta = result.consultado_em ? formatDate(result.consultado_em) : "";
          cacheIndicator.innerHTML = `<i class="fas fa-database text-blue-500"></i> Dados em cache ${dataConsulta ? `(${dataConsulta})` : ""}`;
          cacheIndicator.classList.remove("hidden");
        } else {
          cacheIndicator.classList.add("hidden");
        }
      }
      const relatorioContainer = document.getElementById("resultado-relatorio");
      if (relatorioContainer) {
        if (relatorio) {
          if (typeof window.marked?.parse === "function") {
            relatorioContainer.innerHTML = window.marked.parse(relatorio);
          } else {
            relatorioContainer.innerHTML = markdownToHtml(relatorio);
          }
        } else {
          relatorioContainer.innerHTML = '<p class="text-gray-400 italic">Relat\xF3rio n\xE3o dispon\xEDvel</p>';
        }
      }
      adicionarHistorico(cnj, dados.classe);
      if (result.consulta_id) {
        verificarFeedbackExistente(result.consulta_id);
      }
      mostrarEstado("resultado");
      if (result.cached) {
        showToast("Consulta recuperada do cache", "info");
      } else {
        showToast("Processo consultado com sucesso!", "success");
      }
    } catch (error) {
      const erroMensagem = document.getElementById("erro-mensagem");
      if (erroMensagem) {
        erroMensagem.textContent = error.message || "Erro ao consultar processo";
      }
      mostrarEstado("erro");
      showToast("Erro na consulta", "error");
    }
  }
  function reconsultarProcesso() {
    const resultadoCnj = document.getElementById("resultado-cnj");
    const cnj = resultadoCnj?.textContent;
    if (cnj && confirm(
      "Deseja reconsultar este processo? Isso ir\xE1 buscar dados atualizados do TJ-MS e gerar um novo relat\xF3rio."
    )) {
      consultarProcesso(cnj, true);
    }
  }
  async function enviarFeedback(avaliacao) {
    if (!appState.ultimoResultado || !appState.ultimoResultado.consulta_id) {
      showToast("Nenhuma consulta para avaliar", "warning");
      return;
    }
    let comentario = null;
    if (avaliacao === "incorreto" || avaliacao === "parcial") {
      comentario = prompt(
        "Por favor, descreva brevemente o que estava incorreto (opcional):"
      );
    }
    try {
      const result = await api.post("/feedback", {
        consulta_id: appState.ultimoResultado.consulta_id,
        avaliacao,
        comentario
      });
      if (result && result.success) {
        const feedbackButtons = document.getElementById("feedback-buttons");
        const feedbackEnviado = document.getElementById("feedback-enviado");
        const feedbackEnviadoTipo = document.getElementById("feedback-enviado-tipo");
        if (feedbackButtons) feedbackButtons.classList.add("hidden");
        if (feedbackEnviado) feedbackEnviado.classList.remove("hidden");
        const tipoTexto = {
          correto: "An\xE1lise marcada como correta",
          parcial: "An\xE1lise marcada como parcialmente correta",
          incorreto: "An\xE1lise marcada como incorreta",
          erro_ia: "Reportado como erro da IA"
        };
        if (feedbackEnviadoTipo) {
          feedbackEnviadoTipo.textContent = tipoTexto[avaliacao] || "";
        }
        showToast("Feedback registrado!", "success");
      } else {
        showToast("Erro ao enviar feedback", "error");
      }
    } catch {
      showToast("Erro ao enviar feedback", "error");
    }
  }
  async function verificarFeedbackExistente(consultaId) {
    try {
      const result = await api.get(`/feedback/${consultaId}`);
      const feedbackButtons = document.getElementById("feedback-buttons");
      const feedbackEnviado = document.getElementById("feedback-enviado");
      const feedbackEnviadoTipo = document.getElementById("feedback-enviado-tipo");
      if (result && result.has_feedback) {
        if (feedbackButtons) feedbackButtons.classList.add("hidden");
        if (feedbackEnviado) feedbackEnviado.classList.remove("hidden");
        const tipoTexto = {
          correto: "An\xE1lise marcada como correta",
          parcial: "An\xE1lise marcada como parcialmente correta",
          incorreto: "An\xE1lise marcada como incorreta",
          erro_ia: "Reportado como erro da IA"
        };
        if (feedbackEnviadoTipo && result.avaliacao) {
          feedbackEnviadoTipo.textContent = tipoTexto[result.avaliacao] || "";
        }
      } else {
        if (feedbackButtons) feedbackButtons.classList.remove("hidden");
        if (feedbackEnviado) feedbackEnviado.classList.add("hidden");
      }
    } catch {
      const feedbackButtons = document.getElementById("feedback-buttons");
      const feedbackEnviado = document.getElementById("feedback-enviado");
      if (feedbackButtons) feedbackButtons.classList.remove("hidden");
      if (feedbackEnviado) feedbackEnviado.classList.add("hidden");
    }
  }
  function downloadDocumento(formato) {
    if (!appState.ultimoResultado) {
      showToast("Nenhum resultado para exportar", "warning");
      return;
    }
    const resultadoCnj = document.getElementById("resultado-cnj");
    const cnj = resultadoCnj?.textContent || "processo";
    const relatorio = appState.ultimoResultado.relatorio || "";
    const htmlContent = markdownToHtml(relatorio);
    if (formato === "docx") {
      const docContent = `
      <!DOCTYPE html>
      <html>
      <head>
        <meta charset="utf-8">
        <title>Relat\xF3rio - Assist\xEAncia Judici\xE1ria</title>
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
        <h1>An\xE1lise de Processo</h1>
        <p style="text-align: center; color: #666;">Processo: ${escapeHtml(cnj)}</p>
        <hr>
        <p>${htmlContent}</p>
      </body>
      </html>
    `;
      const blob = new Blob([docContent], {
        type: "application/vnd.ms-word;charset=utf-8"
      });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `relatorio_${cnj.replace(/\D/g, "")}.doc`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(link.href);
      showToast("Download do Word iniciado!", "success");
    } else if (formato === "pdf") {
      const printWindow = window.open("", "_blank");
      if (!printWindow) {
        showToast("Popup bloqueado. Habilite popups para este site.", "error");
        return;
      }
      printWindow.document.write(`
      <!DOCTYPE html>
      <html>
      <head>
        <meta charset="utf-8">
        <title>Relat\xF3rio - Assist\xEAncia Judici\xE1ria</title>
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
          <h1>An\xE1lise de Processo</h1>
          <p>Sistema de Assist\xEAncia Judici\xE1ria - PGE-MS</p>
          <p>Processo: ${escapeHtml(cnj)}</p>
        </div>
        <hr>
        <p>${htmlContent}</p>
        <div class="footer">
          <p>Documento gerado em ${(/* @__PURE__ */ new Date()).toLocaleDateString("pt-BR")} \xE0s ${(/* @__PURE__ */ new Date()).toLocaleTimeString("pt-BR")}</p>
          <p>Procuradoria-Geral do Estado de Mato Grosso do Sul</p>
        </div>
      </body>
      </html>
    `);
      printWindow.document.close();
      setTimeout(() => {
        printWindow.print();
      }, 500);
      showToast("Janela de impress\xE3o aberta!", "success");
    }
  }
  async function carregarSettings() {
    try {
      const config = await api.get("/settings");
      if (config) {
        appState.config.model = config.default_model || "google/gemini-3-flash-preview";
      }
    } catch (error) {
      console.error("Erro ao carregar settings:", error);
    }
  }
  function logout2() {
    logout();
  }
  function initApp() {
    if (!checkAuth("/assistencia-judiciaria")) return;
    const btnConsultar = document.getElementById("btn-consultar");
    if (btnConsultar) {
      btnConsultar.addEventListener("click", () => consultarProcesso());
    }
    const inputCnj = document.getElementById("input-cnj");
    if (inputCnj) {
      inputCnj.addEventListener("keypress", (e) => {
        if (e.key === "Enter") consultarProcesso();
      });
    }
    const btnDocx = document.getElementById("btn-download-docx");
    const btnPdf = document.getElementById("btn-download-pdf");
    if (btnDocx) {
      btnDocx.addEventListener("click", () => downloadDocumento("docx"));
    }
    if (btnPdf) {
      btnPdf.addEventListener("click", () => downloadDocumento("pdf"));
    }
    carregarHistorico();
    carregarSettings();
  }
  document.addEventListener("DOMContentLoaded", initApp);
  window.consultarProcesso = consultarProcesso;
  window.reconsultarProcesso = reconsultarProcesso;
  window.enviarFeedback = enviarFeedback;
  window.downloadDocumento = downloadDocumento;
  window.voltarInicio = voltarInicio;
  window.excluirDoHistorico = excluirDoHistorico;
  window.logout = logout2;
})();
//# sourceMappingURL=app.js.map
