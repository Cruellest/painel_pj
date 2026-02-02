// Generated from TypeScript - DO NOT EDIT DIRECTLY
// Source: src\sistemas\bert_training\app.ts
// Built at: 2026-01-30T21:41:45.398Z

"use strict";
(() => {
  // src/sistemas/bert_training/app.ts
  var WORKER_URL = "http://127.0.0.1:8765";
  function getToken() {
    return localStorage.getItem("access_token") || sessionStorage.getItem("access_token");
  }
  async function apiCall(endpoint, options = {}) {
    const token = getToken();
    if (!token) {
      window.location.href = "/login";
      return null;
    }
    const response = await fetch(`/bert-training${endpoint}`, {
      ...options,
      headers: {
        "Authorization": `Bearer ${token}`,
        "Content-Type": "application/json",
        ...options.headers
      }
    });
    if (response.status === 401) {
      window.location.href = "/login";
      return null;
    }
    return response;
  }
  var currentTab = "novo";
  var allRuns = [];
  var currentFilter = "all";
  var activeTrainingRunId = null;
  var presetsCache = null;
  var workerConnected = false;
  var completedModels = [];
  function showTab(tabName) {
    currentTab = tabName;
    document.querySelectorAll(".tab-panel").forEach((panel) => {
      panel.classList.add("hidden");
    });
    document.querySelectorAll(".tab-btn").forEach((btn) => {
      btn.classList.remove("active");
    });
    document.getElementById(`panel-${tabName}`)?.classList.remove("hidden");
    document.getElementById(`tab-${tabName}`)?.classList.add("active");
    if (tabName === "novo") {
      loadDatasets();
      loadDatasetsForSelect();
    }
    if (tabName === "acompanhar") {
      loadRuns();
      checkActiveTraining();
    }
    if (tabName === "testar") {
      checkWorkerConnection();
      loadCompletedModels();
      loadTestHistory();
    }
  }
  async function loadDatasets() {
    const response = await apiCall("/api/datasets");
    if (!response) return;
    const datasets = await response.json();
    const container = document.getElementById("datasets-list");
    if (!container) return;
    if (datasets.length === 0) {
      container.innerHTML = '<p class="text-gray-500 text-center py-4">Nenhuma planilha enviada ainda.</p>';
      return;
    }
    container.innerHTML = datasets.map(
      (d) => `
    <div class="flex items-center justify-between p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors">
      <div class="flex items-center gap-3">
        <i class="fas fa-file-excel text-green-600"></i>
        <div>
          <p class="font-medium text-gray-800 text-sm">${escapeHtml(d.filename)}</p>
          <p class="text-xs text-gray-500">${d.total_rows} exemplos | ${d.total_labels || "?"} categorias</p>
        </div>
      </div>
      <div class="flex gap-2">
        <button onclick="viewDataset(${d.id})" class="text-blue-600 hover:text-blue-800 text-sm px-2">
          <i class="fas fa-eye"></i>
        </button>
      </div>
    </div>
  `
    ).join("");
  }
  async function viewDataset(id) {
    const response = await apiCall(`/api/datasets/${id}`);
    if (!response) return;
    const dataset = await response.json();
    const content = `
    <div class="space-y-4">
      <div class="grid grid-cols-2 gap-4 text-sm">
        <div><strong>Arquivo:</strong> ${escapeHtml(dataset.filename)}</div>
        <div><strong>Tipo:</strong> ${dataset.task_type === "text_classification" ? "Classificacao de Texto" : "NER"}</div>
        <div><strong>Coluna Texto:</strong> ${escapeHtml(dataset.text_column)}</div>
        <div><strong>Coluna Label:</strong> ${escapeHtml(dataset.label_column)}</div>
        <div><strong>Total Linhas:</strong> ${dataset.total_rows}</div>
        <div><strong>Total Categorias:</strong> ${dataset.total_labels}</div>
      </div>

      <div>
        <strong class="text-sm">Distribuicao de Categorias:</strong>
        <div class="mt-2 max-h-40 overflow-y-auto">
          ${Object.entries(dataset.label_distribution || {}).map(
      ([label, count]) => `
            <div class="flex justify-between text-sm py-1 border-b">
              <span>${escapeHtml(label)}</span>
              <span class="text-gray-500">${count}</span>
            </div>
          `
    ).join("")}
        </div>
      </div>
    </div>
  `;
    const titleEl = document.getElementById("run-detail-title");
    const contentEl = document.getElementById("run-detail-content");
    const modalEl = document.getElementById("run-detail-modal");
    if (titleEl) titleEl.textContent = "Detalhes do Dataset";
    if (contentEl) contentEl.innerHTML = content;
    modalEl?.classList.remove("hidden");
  }
  function showUploadModal() {
    document.getElementById("upload-modal")?.classList.remove("hidden");
    resetUploadModal();
  }
  function closeUploadModal() {
    document.getElementById("upload-modal")?.classList.add("hidden");
    resetUploadModal();
  }
  function resetUploadModal() {
    const form = document.getElementById("upload-form");
    form?.reset();
    document.getElementById("upload-preview")?.classList.add("hidden");
    document.getElementById("upload-preview-content")?.classList.add("hidden");
    document.getElementById("upload-validation")?.classList.add("hidden");
    document.getElementById("btn-validate")?.classList.add("hidden");
    document.getElementById("btn-upload")?.classList.add("hidden");
  }
  async function handleFileChange(e) {
    const target = e.target;
    const file = target.files?.[0];
    if (!file) return;
    document.getElementById("upload-preview")?.classList.remove("hidden");
    document.getElementById("upload-preview-loading")?.classList.remove("hidden");
    document.getElementById("upload-preview-content")?.classList.add("hidden");
    const formData = new FormData();
    formData.append("file", file);
    const token = getToken();
    try {
      const response = await fetch("/bert-training/api/datasets/preview", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData
      });
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Erro ao analisar arquivo");
      }
      const data = await response.json();
      document.getElementById("upload-preview-loading")?.classList.add("hidden");
      document.getElementById("upload-preview-content")?.classList.remove("hidden");
      const previewInfo = document.getElementById("preview-info");
      if (previewInfo) {
        previewInfo.innerHTML = `<strong>${escapeHtml(data.filename)}</strong> - ${data.total_rows} linhas, ${data.total_columns} colunas`;
      }
      const textSelect = document.getElementById("upload-text-col");
      const labelSelect = document.getElementById("upload-label-col");
      if (textSelect) {
        textSelect.innerHTML = '<option value="">Selecione a coluna de texto...</option>' + data.columns.map((col) => `<option value="${escapeHtml(col)}">${escapeHtml(col)}</option>`).join("");
      }
      if (labelSelect) {
        labelSelect.innerHTML = '<option value="">Selecione a coluna de categorias...</option>' + data.columns.map((col) => `<option value="${escapeHtml(col)}">${escapeHtml(col)}</option>`).join("");
      }
      if (data.text_candidates.length > 0 && textSelect) {
        textSelect.value = data.text_candidates[0];
        const hint = document.getElementById("text-col-hint");
        if (hint) {
          hint.textContent = `Sugestao: ${data.text_candidates.join(", ")}`;
          hint.classList.remove("hidden");
        }
      }
      if (data.label_candidates.length > 0 && labelSelect) {
        labelSelect.value = data.label_candidates[0];
        const hint = document.getElementById("label-col-hint");
        if (hint) {
          hint.textContent = `Sugestao: ${data.label_candidates.join(", ")}`;
          hint.classList.remove("hidden");
        }
      }
      const columnStatsEl = document.getElementById("column-stats");
      if (columnStatsEl) {
        columnStatsEl.innerHTML = data.column_stats.map(
          (col) => `
        <div class="border-b py-2">
          <div class="flex justify-between">
            <span class="font-medium">${escapeHtml(col.name)}</span>
            <span class="text-gray-500">${col.unique_values} valores unicos</span>
          </div>
          <div class="text-xs text-gray-400 mt-1">
            ${col.null_count > 0 ? `<span class="text-yellow-600">${col.null_count} nulos</span> | ` : ""}
            Exemplos: ${col.sample_values.slice(0, 3).map((v) => escapeHtml(v)).join(", ")}
          </div>
        </div>
      `
        ).join("");
      }
      if (data.preview_rows && data.preview_rows.length > 0) {
        const headers = Object.keys(data.preview_rows[0]);
        const dataPreviewEl = document.getElementById("data-preview");
        if (dataPreviewEl) {
          dataPreviewEl.innerHTML = `
          <table class="min-w-full text-xs">
            <thead>
              <tr class="bg-gray-100">
                ${headers.map((h) => `<th class="px-2 py-1 text-left">${escapeHtml(h)}</th>`).join("")}
              </tr>
            </thead>
            <tbody>
              ${data.preview_rows.slice(0, 5).map(
            (row) => `
                <tr class="border-b">
                  ${headers.map((h) => `<td class="px-2 py-1 max-w-xs truncate">${escapeHtml(String(row[h] || "").substring(0, 50))}</td>`).join("")}
                </tr>
              `
          ).join("")}
            </tbody>
          </table>
        `;
        }
      }
      document.getElementById("btn-validate")?.classList.remove("hidden");
      document.getElementById("btn-upload")?.classList.remove("hidden");
    } catch (error) {
      const loadingEl = document.getElementById("upload-preview-loading");
      if (loadingEl) {
        loadingEl.innerHTML = `<div class="text-red-600"><i class="fas fa-exclamation-circle mr-2"></i>${escapeHtml(error.message)}</div>`;
      }
    }
  }
  async function validateDataset() {
    const fileInput = document.getElementById("upload-file");
    const file = fileInput?.files?.[0];
    if (!file) {
      alert("Selecione um arquivo");
      return;
    }
    const textCol = document.getElementById("upload-text-col")?.value;
    const labelCol = document.getElementById("upload-label-col")?.value;
    if (!textCol || !labelCol) {
      alert("Selecione as colunas de texto e categorias");
      return;
    }
    const formData = new FormData();
    formData.append("file", file);
    formData.append("task_type", document.getElementById("upload-task-type")?.value || "text_classification");
    formData.append("text_column", textCol);
    formData.append("label_column", labelCol);
    const token = getToken();
    const response = await fetch("/bert-training/api/datasets/validate", {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: formData
    });
    const result = await response.json();
    const validationDiv = document.getElementById("upload-validation");
    if (!validationDiv) return;
    validationDiv.classList.remove("hidden");
    if (result.is_valid) {
      validationDiv.innerHTML = `
      <div class="bg-green-50 border border-green-200 rounded p-3">
        <p class="text-green-800 font-medium"><i class="fas fa-check-circle mr-2"></i>Validacao OK!</p>
        <p class="text-sm text-green-600">${result.total_rows} linhas validas</p>
      </div>
    `;
    } else {
      validationDiv.innerHTML = `
      <div class="bg-red-50 border border-red-200 rounded p-3">
        <p class="text-red-800 font-medium"><i class="fas fa-times-circle mr-2"></i>Problemas encontrados</p>
        <ul class="text-sm text-red-600 list-disc ml-4">
          ${result.errors.map((e) => `<li>${escapeHtml(e)}</li>`).join("")}
        </ul>
      </div>
    `;
    }
  }
  async function handleUploadSubmit(e) {
    e.preventDefault();
    const fileInput = document.getElementById("upload-file");
    const file = fileInput?.files?.[0];
    if (!file) {
      alert("Selecione um arquivo");
      return;
    }
    const textCol = document.getElementById("upload-text-col")?.value;
    const labelCol = document.getElementById("upload-label-col")?.value;
    if (!textCol || !labelCol) {
      alert("Selecione as colunas de texto e categorias");
      return;
    }
    const formData = new FormData();
    formData.append("file", file);
    formData.append("task_type", document.getElementById("upload-task-type")?.value || "text_classification");
    formData.append("text_column", textCol);
    formData.append("label_column", labelCol);
    const token = getToken();
    const response = await fetch("/bert-training/api/datasets/upload", {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: formData
    });
    if (response.ok) {
      const result = await response.json();
      alert(result.is_duplicate ? "Planilha ja existe!" : "Planilha enviada com sucesso!");
      closeUploadModal();
      loadDatasets();
      loadDatasetsForSelect();
    } else {
      const error = await response.json();
      alert("Erro: " + (error.detail || "Falha no upload"));
    }
  }
  async function loadRuns() {
    const response = await apiCall("/api/runs");
    if (!response) return;
    const runs = await response.json();
    allRuns = runs;
    const trainingCount = runs.filter((r) => r.status === "training").length;
    const badge = document.getElementById("badge-training");
    if (badge) {
      if (trainingCount > 0) {
        badge.textContent = String(trainingCount);
        badge.classList.remove("hidden");
      } else {
        badge.classList.add("hidden");
      }
    }
    renderRunsList(runs);
  }
  function filterRuns(status) {
    currentFilter = status;
    document.querySelectorAll("[data-filter]").forEach((btn) => {
      const el = btn;
      el.classList.remove("bg-blue-100", "text-blue-700");
      el.classList.add("bg-gray-100", "text-gray-600");
      if (el.dataset.filter === status) {
        el.classList.remove("bg-gray-100", "text-gray-600");
        el.classList.add("bg-blue-100", "text-blue-700");
      }
    });
    let filteredRuns = allRuns;
    if (status !== "all") {
      filteredRuns = allRuns.filter((r) => r.status === status);
    }
    renderRunsList(filteredRuns);
  }
  function renderRunsList(runs) {
    const container = document.getElementById("runs-list");
    if (!container) return;
    if (runs.length === 0) {
      const emptyMsg = currentFilter === "all" ? "Nenhum treinamento encontrado." : `Nenhum treinamento "${formatStatus(currentFilter)}".`;
      container.innerHTML = `<p class="text-gray-400 text-center py-8">${emptyMsg}</p>`;
      return;
    }
    container.innerHTML = runs.map(
      (r) => `
    <div class="border rounded-lg p-4 hover:bg-gray-50 cursor-pointer transition-colors" onclick="viewRun(${r.id})">
      <div class="flex justify-between items-start">
        <div class="flex-1">
          <h3 class="font-medium text-gray-900">${escapeHtml(r.name)}</h3>
          <div class="flex items-center gap-2 mt-1">
            <span class="inline-block status-${r.status} rounded px-2 py-0.5 text-xs font-medium">${formatStatus(r.status)}</span>
            <span class="text-xs text-gray-500">${escapeHtml(r.base_model.split("/").pop() || "")}</span>
          </div>
          <div class="text-xs text-gray-400 mt-1">
            ${new Date(r.created_at).toLocaleDateString("pt-BR")}
            ${r.final_accuracy ? ` | Precisao: ${(r.final_accuracy * 100).toFixed(1)}%` : ""}
          </div>
        </div>
        <div class="text-gray-400 ml-2">
          <i class="fas fa-chevron-right"></i>
        </div>
      </div>
    </div>
  `
    ).join("");
  }
  function formatStatus(status) {
    const statusMap = {
      pending: "Na fila",
      training: "Treinando",
      completed: "Concluido",
      failed: "Falhou",
      cancelled: "Cancelado"
    };
    return statusMap[status] || status;
  }
  async function viewRun(id) {
    const response = await apiCall(`/api/runs/${id}`);
    if (!response) return;
    const run = await response.json();
    const content = `
    <div class="space-y-6">
      <div class="grid grid-cols-2 gap-4 text-sm">
        <div><strong>Status:</strong> <span class="status-${run.status} px-2 py-0.5 rounded">${formatStatus(run.status)}</span></div>
        <div><strong>Modelo:</strong> ${escapeHtml(run.base_model)}</div>
        <div><strong>Dataset:</strong> ${escapeHtml(run.dataset_filename)}</div>
        <div><strong>Seed:</strong> ${run.config_json?.seed || 42}</div>
      </div>

      ${run.error_message ? `
        <div class="bg-red-50 border border-red-200 rounded p-3 text-sm text-red-700">
          <strong>Erro:</strong> ${escapeHtml(run.error_message)}
        </div>
      ` : ""}

      ${run.final_accuracy ? `
        <div class="bg-green-50 border border-green-200 rounded p-4">
          <h4 class="font-medium text-green-800 mb-2">Metricas Finais</h4>
          <div class="grid grid-cols-3 gap-4 text-center">
            <div>
              <div class="text-2xl font-bold text-green-600">${(run.final_accuracy * 100).toFixed(1)}%</div>
              <div class="text-xs text-gray-500">Precisao</div>
            </div>
            <div>
              <div class="text-2xl font-bold text-green-600">${((run.final_macro_f1 || 0) * 100).toFixed(1)}%</div>
              <div class="text-xs text-gray-500">F1 Macro</div>
            </div>
            <div>
              <div class="text-2xl font-bold text-green-600">${((run.final_weighted_f1 || 0) * 100).toFixed(1)}%</div>
              <div class="text-xs text-gray-500">F1 Ponderado</div>
            </div>
          </div>
        </div>
      ` : ""}

      ${run.recent_metrics && run.recent_metrics.length > 0 ? `
        <div>
          <h4 class="font-medium mb-2">Progresso</h4>
          <canvas id="metrics-chart" height="200"></canvas>
        </div>
      ` : ""}

      <details class="border rounded-lg p-3">
        <summary class="cursor-pointer font-medium text-sm">Configuracao Completa</summary>
        <pre class="mt-2 text-xs bg-gray-100 p-2 rounded overflow-x-auto">${escapeHtml(JSON.stringify(run.config_json, null, 2))}</pre>
      </details>
    </div>
  `;
    const titleEl = document.getElementById("run-detail-title");
    const contentEl = document.getElementById("run-detail-content");
    const modalEl = document.getElementById("run-detail-modal");
    if (titleEl) titleEl.textContent = run.name;
    if (contentEl) contentEl.innerHTML = content;
    modalEl?.classList.remove("hidden");
    if (run.recent_metrics && run.recent_metrics.length > 0) {
      renderMetricsChart(run.recent_metrics);
    }
  }
  function renderMetricsChart(metrics) {
    const canvas = document.getElementById("metrics-chart");
    const ctx = canvas?.getContext("2d");
    if (!ctx) return;
    new Chart(ctx, {
      type: "line",
      data: {
        labels: metrics.map((m) => `Rodada ${m.epoch}`),
        datasets: [
          {
            label: "Loss Treino",
            data: metrics.map((m) => m.train_loss),
            borderColor: "rgb(239, 68, 68)",
            tension: 0.1
          },
          {
            label: "Loss Validacao",
            data: metrics.map((m) => m.val_loss),
            borderColor: "rgb(59, 130, 246)",
            tension: 0.1
          },
          {
            label: "Precisao",
            data: metrics.map((m) => m.val_accuracy),
            borderColor: "rgb(34, 197, 94)",
            tension: 0.1,
            yAxisID: "y1"
          }
        ]
      },
      options: {
        responsive: true,
        scales: {
          y: { type: "linear", display: true, position: "left", title: { display: true, text: "Loss" } },
          y1: { type: "linear", display: true, position: "right", title: { display: true, text: "Precisao" }, grid: { drawOnChartArea: false } }
        }
      }
    });
  }
  function closeRunDetail() {
    document.getElementById("run-detail-modal")?.classList.add("hidden");
  }
  function checkActiveTraining() {
    const trainingRuns = allRuns.filter((r) => r.status === "training");
    if (trainingRuns.length > 0) {
      activeTrainingRunId = trainingRuns[0].id;
      document.getElementById("active-training-card")?.classList.remove("hidden");
      updateActiveTrainingStatus();
    } else {
      document.getElementById("active-training-card")?.classList.add("hidden");
      activeTrainingRunId = null;
    }
  }
  async function updateActiveTrainingStatus() {
    if (!activeTrainingRunId) return;
    try {
      const response = await apiCall(`/api/runs/${activeTrainingRunId}/progress`);
      if (!response || !response.ok) return;
      const progress = await response.json();
      const nameEl = document.getElementById("active-training-name");
      const statusEl = document.getElementById("active-training-status");
      const progressLabelEl = document.getElementById("active-training-progress-label");
      const progressBarEl = document.getElementById("active-training-progress-bar");
      const timeEl = document.getElementById("active-training-time-remaining");
      if (nameEl) nameEl.textContent = progress.run_name || "Treinamento";
      if (statusEl) statusEl.textContent = `Rodada ${progress.current_epoch || 0} de ${progress.total_epochs || "?"}`;
      if (progressLabelEl) progressLabelEl.textContent = `${(progress.progress_percent || 0).toFixed(0)}%`;
      if (progressBarEl) progressBarEl.style.width = `${progress.progress_percent || 0}%`;
      if (progress.estimated_remaining_label && timeEl) {
        timeEl.textContent = progress.estimated_remaining_label;
      }
      if (progress.latest_metrics) {
        const m = progress.latest_metrics;
        const lossEl = document.getElementById("metric-loss");
        const accEl = document.getElementById("metric-accuracy");
        const f1El = document.getElementById("metric-f1");
        const epochEl = document.getElementById("metric-epoch");
        if (lossEl) lossEl.textContent = m.val_loss?.toFixed(4) || "-";
        if (accEl) accEl.textContent = m.val_accuracy ? `${(m.val_accuracy * 100).toFixed(1)}%` : "-";
        if (f1El) f1El.textContent = m.val_macro_f1 ? `${(m.val_macro_f1 * 100).toFixed(1)}%` : "-";
        if (epochEl) epochEl.textContent = `${progress.current_epoch || 0}/${progress.total_epochs || "?"}`;
      }
    } catch (e) {
      console.error("Erro ao atualizar progresso:", e);
    }
  }
  function cancelTraining() {
    if (!activeTrainingRunId) return;
    if (!confirm("Tem certeza que deseja cancelar o treinamento?")) return;
    alert("Funcionalidade de cancelamento sera implementada em breve.");
  }
  async function loadDatasetsForSelect() {
    const response = await apiCall("/api/datasets");
    if (!response) return;
    const datasets = await response.json();
    const select = document.getElementById("run-dataset");
    if (!select) return;
    select.innerHTML = '<option value="">Selecione uma planilha...</option>' + datasets.map((d) => `<option value="${d.id}">${escapeHtml(d.filename)} (${d.total_rows} exemplos)</option>`).join("");
    loadPresets();
  }
  async function loadPresets() {
    if (presetsCache) {
      renderPresets(presetsCache);
      return;
    }
    const response = await apiCall("/api/presets");
    if (!response) return;
    const data = await response.json();
    presetsCache = data.presets;
    if (presetsCache) {
      renderPresets(presetsCache);
    }
  }
  function renderPresets(presets) {
    const container = document.getElementById("presets-container");
    if (!container) return;
    const icons = {
      rapido: "fa-bolt",
      equilibrado: "fa-balance-scale",
      preciso: "fa-bullseye"
    };
    container.innerHTML = presets.map(
      (p) => `
    <div class="preset-card border-2 rounded-lg p-4 cursor-pointer hover:border-blue-500 transition-all ${p.is_recommended ? "border-blue-300 bg-blue-50" : "border-gray-200"}"
         data-preset="${p.name}"
         onclick="selectPreset('${p.name}')">
      <div class="flex flex-col items-center text-center">
        <i class="fas ${icons[p.name] || "fa-cog"} text-2xl text-blue-600 mb-2"></i>
        <h3 class="font-bold">${escapeHtml(p.display_name)}</h3>
        ${p.is_recommended ? '<span class="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded mt-1">Recomendado</span>' : ""}
        <p class="text-xs text-gray-600 mt-2">${escapeHtml(p.description)}</p>
        <div class="text-xs text-gray-400 mt-2">
          ~${p.estimated_time_minutes_min}-${p.estimated_time_minutes_max} min
        </div>
      </div>
    </div>
  `
    ).join("");
    const recommended = presets.find((p) => p.is_recommended) || presets[1];
    if (recommended) selectPreset(recommended.name);
  }
  function selectPreset(presetName) {
    document.querySelectorAll(".preset-card").forEach((card) => {
      const el = card;
      el.classList.remove("border-blue-500", "bg-blue-100");
      if (el.dataset.preset === presetName) {
        el.classList.add("border-blue-500", "bg-blue-100");
      }
    });
    const hiddenInput = document.getElementById("selected-preset");
    if (hiddenInput) hiddenInput.value = presetName;
    const warningDiv = document.getElementById("preset-warning");
    if (!warningDiv) return;
    if (presetName === "rapido") {
      warningDiv.innerHTML = `
      <div class="bg-yellow-50 border border-yellow-200 rounded p-3 text-sm text-yellow-700">
        <i class="fas fa-info-circle mr-2"></i>Modo rapido: ideal para testar se a planilha esta correta.
      </div>
    `;
      warningDiv.classList.remove("hidden");
    } else if (presetName === "preciso") {
      warningDiv.innerHTML = `
      <div class="bg-blue-50 border border-blue-200 rounded p-3 text-sm text-blue-700">
        <i class="fas fa-clock mr-2"></i>Modo preciso: pode demorar varias horas.
      </div>
    `;
      warningDiv.classList.remove("hidden");
    } else {
      warningDiv.classList.add("hidden");
    }
  }
  async function handleNewRunSubmit(e) {
    e.preventDefault();
    const presetName = document.getElementById("selected-preset")?.value || "";
    const data = {
      name: document.getElementById("run-name")?.value,
      description: document.getElementById("run-description")?.value || null,
      dataset_id: parseInt(document.getElementById("run-dataset")?.value || "0"),
      base_model: document.getElementById("run-model")?.value,
      preset_name: presetName
    };
    const hyperparameters = {};
    let hasOverrides = false;
    const epochsVal = document.getElementById("run-epochs")?.value;
    if (epochsVal) {
      hyperparameters.epochs = parseInt(epochsVal);
      hasOverrides = true;
    }
    const lrVal = document.getElementById("run-lr")?.value;
    if (lrVal) {
      hyperparameters.learning_rate = parseFloat(lrVal);
      hasOverrides = true;
    }
    const batchVal = document.getElementById("run-batch")?.value;
    if (batchVal) {
      hyperparameters.batch_size = parseInt(batchVal);
      hasOverrides = true;
    }
    const maxlenVal = document.getElementById("run-maxlen")?.value;
    if (maxlenVal) {
      hyperparameters.max_length = parseInt(maxlenVal);
      hasOverrides = true;
    }
    const splitVal = document.getElementById("run-split")?.value;
    if (splitVal) {
      hyperparameters.train_split = parseFloat(splitVal);
      hasOverrides = true;
    }
    const patienceVal = document.getElementById("run-patience")?.value;
    if (patienceVal) {
      hyperparameters.early_stopping_patience = parseInt(patienceVal);
      hasOverrides = true;
    }
    const seedVal = document.getElementById("run-seed")?.value;
    if (seedVal && seedVal !== "42") {
      hyperparameters.seed = parseInt(seedVal);
      hasOverrides = true;
    }
    const classWeightsEl = document.getElementById("run-class-weights");
    if (classWeightsEl && !classWeightsEl.checked) {
      hyperparameters.use_class_weights = false;
      hasOverrides = true;
    }
    if (hasOverrides) {
      data.hyperparameters = hyperparameters;
    }
    const response = await apiCall("/api/runs", {
      method: "POST",
      body: JSON.stringify(data)
    });
    if (response && response.ok) {
      const result = await response.json();
      alert(`Treinamento "${result.name}" iniciado!

Acompanhe na aba "Acompanhar".`);
      const form = document.getElementById("new-run-form");
      form?.reset();
      showTab("acompanhar");
    } else if (response) {
      const error = await response.json();
      alert("Erro: " + (error.detail || "Falha ao criar treinamento"));
    }
  }
  async function checkWorkerConnection() {
    const statusIcon = document.getElementById("worker-status-icon");
    const statusText = document.getElementById("worker-status-text");
    try {
      const response = await fetch(`${WORKER_URL}/health`, { method: "GET" });
      if (response.ok) {
        const data = await response.json();
        workerConnected = true;
        statusIcon?.classList.remove("bg-gray-300", "bg-red-500");
        statusIcon?.classList.add("bg-green-500");
        if (statusText) {
          statusText.textContent = `Conectado ao worker local ${data.cuda_available ? "(GPU disponivel)" : "(somente CPU)"}`;
        }
        loadLocalModels();
      } else {
        throw new Error("Worker nao respondeu");
      }
    } catch {
      workerConnected = false;
      statusIcon?.classList.remove("bg-gray-300", "bg-green-500");
      statusIcon?.classList.add("bg-red-500");
      if (statusText) {
        statusText.textContent = "Worker local nao conectado. Inicie o servidor de inferencia.";
      }
    }
  }
  async function loadCompletedModels() {
    const response = await apiCall("/api/models/completed");
    if (!response) return;
    completedModels = await response.json();
    updateModelSelect();
  }
  async function loadLocalModels() {
    if (!workerConnected) return;
    try {
      const response = await fetch(`${WORKER_URL}/models`);
      if (!response.ok) return;
      const data = await response.json();
      const localModels = data.models || [];
      completedModels.forEach((model) => {
        const local = localModels.find((l) => l.run_id === model.id);
        model.available_locally = !!local;
        if (local) {
          model.local_path = local.name;
        }
      });
      updateModelSelect();
    } catch (e) {
      console.error("Erro ao carregar modelos locais:", e);
    }
  }
  function updateModelSelect() {
    const select = document.getElementById("test-model-select");
    if (!select) return;
    select.innerHTML = '<option value="">Selecione um modelo...</option>' + completedModels.map((m) => {
      const accuracy = m.accuracy ? ` | ${(m.accuracy * 100).toFixed(1)}%` : "";
      const local = m.available_locally ? " [LOCAL]" : " [nao disponivel localmente]";
      return `<option value="${m.id}" data-local="${m.local_path || ""}" ${!m.available_locally ? "disabled" : ""}>
          ${escapeHtml(m.name)}${accuracy}${local}
        </option>`;
    }).join("");
  }
  function setTestMode(mode) {
    const textBtn = document.getElementById("test-mode-text");
    const pdfBtn = document.getElementById("test-mode-pdf");
    textBtn?.classList.toggle("border-purple-500", mode === "text");
    textBtn?.classList.toggle("text-purple-600", mode === "text");
    textBtn?.classList.toggle("border-transparent", mode !== "text");
    textBtn?.classList.toggle("text-gray-500", mode !== "text");
    pdfBtn?.classList.toggle("border-purple-500", mode === "pdf");
    pdfBtn?.classList.toggle("text-purple-600", mode === "pdf");
    pdfBtn?.classList.toggle("border-transparent", mode !== "pdf");
    pdfBtn?.classList.toggle("text-gray-500", mode !== "pdf");
    document.getElementById("test-input-text")?.classList.toggle("hidden", mode !== "text");
    document.getElementById("test-input-pdf")?.classList.toggle("hidden", mode !== "pdf");
  }
  function handlePdfInputChange(e) {
    const target = e.target;
    const file = target.files?.[0];
    if (file) {
      const filenameEl = document.getElementById("test-pdf-filename");
      if (filenameEl) filenameEl.textContent = file.name;
    }
  }
  async function classifyText() {
    if (!workerConnected) {
      alert("Worker local nao conectado. Inicie o servidor de inferencia primeiro.");
      return;
    }
    const select = document.getElementById("test-model-select");
    const modelId = select?.value;
    const localPath = select?.options[select.selectedIndex]?.dataset?.local;
    if (!modelId || !localPath) {
      alert("Selecione um modelo disponivel localmente.");
      return;
    }
    const text = document.getElementById("test-text-input")?.value.trim();
    if (!text) {
      alert("Digite ou cole um texto para classificar.");
      return;
    }
    const btn = document.getElementById("btn-classify-text");
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i> Classificando...';
    }
    try {
      const response = await fetch(`${WORKER_URL}/predict`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model: localPath, text })
      });
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || "Erro na classificacao");
      }
      const result = await response.json();
      showTestResult(result);
      saveTestHistory(parseInt(modelId), "text", text, null, result);
    } catch (e) {
      alert("Erro: " + e.message);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-magic mr-2"></i> Classificar';
      }
    }
  }
  async function classifyPdf() {
    if (!workerConnected) {
      alert("Worker local nao conectado. Inicie o servidor de inferencia primeiro.");
      return;
    }
    const select = document.getElementById("test-model-select");
    const modelId = select?.value;
    const localPath = select?.options[select.selectedIndex]?.dataset?.local;
    if (!modelId || !localPath) {
      alert("Selecione um modelo disponivel localmente.");
      return;
    }
    const fileInput = document.getElementById("test-pdf-input");
    const file = fileInput?.files?.[0];
    if (!file) {
      alert("Selecione um arquivo PDF.");
      return;
    }
    const btn = document.getElementById("btn-classify-pdf");
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i> Classificando...';
    }
    try {
      const formData = new FormData();
      formData.append("model", localPath);
      formData.append("file", file);
      const response = await fetch(`${WORKER_URL}/predict/pdf`, {
        method: "POST",
        body: formData
      });
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || "Erro na classificacao");
      }
      const result = await response.json();
      showTestResult(result);
      saveTestHistory(parseInt(modelId), "pdf", `[PDF: ${file.name}]`, file.name, result);
    } catch (e) {
      alert("Erro: " + e.message);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-magic mr-2"></i> Classificar PDF';
      }
    }
  }
  function showTestResult(result) {
    document.getElementById("test-result")?.classList.remove("hidden");
    const categoryEl = document.getElementById("test-result-category");
    const confidenceEl = document.getElementById("test-result-confidence");
    if (categoryEl) categoryEl.textContent = result.predicted_label;
    if (confidenceEl) confidenceEl.textContent = `${(result.confidence * 100).toFixed(1)}%`;
  }
  async function saveTestHistory(runId, inputType, inputText, filename, result) {
    const formData = new FormData();
    formData.append("run_id", String(runId));
    formData.append("input_type", inputType);
    formData.append("input_text", inputText.substring(0, 5e3));
    formData.append("predicted_label", result.predicted_label);
    formData.append("confidence", String(result.confidence));
    if (filename) formData.append("input_filename", filename);
    const token = getToken();
    await fetch("/bert-training/api/tests", {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: formData
    });
    loadTestHistory();
  }
  async function loadTestHistory() {
    const response = await apiCall("/api/tests?limit=20");
    if (!response) return;
    const tests = await response.json();
    const container = document.getElementById("test-history-list");
    if (!container) return;
    if (tests.length === 0) {
      container.innerHTML = '<p class="text-center py-4 text-gray-400 text-sm">Nenhum teste realizado ainda.</p>';
      return;
    }
    container.innerHTML = tests.map(
      (t) => `
    <div class="flex items-center justify-between p-3 bg-gray-50 rounded-lg text-sm">
      <div class="flex-1 min-w-0">
        <div class="flex items-center gap-2">
          <i class="fas ${t.input_type === "pdf" ? "fa-file-pdf text-red-500" : "fa-font text-blue-500"}"></i>
          <span class="font-medium text-gray-800">${escapeHtml(t.predicted_label)}</span>
          <span class="text-gray-400">${(t.confidence * 100).toFixed(0)}%</span>
        </div>
        <p class="text-xs text-gray-500 truncate mt-1">${escapeHtml(t.input_filename || t.input_text)}</p>
      </div>
      <button onclick="deleteTest(${t.id})" class="text-red-500 hover:text-red-700 ml-2">
        <i class="fas fa-trash"></i>
      </button>
    </div>
  `
    ).join("");
  }
  async function deleteTest(id) {
    if (!confirm("Deletar este teste?")) return;
    await apiCall(`/api/tests/${id}`, { method: "DELETE" });
    loadTestHistory();
  }
  async function clearTestHistory() {
    if (!confirm("Limpar todo o historico de testes?")) return;
    await apiCall("/api/tests", { method: "DELETE" });
    loadTestHistory();
  }
  function showOnboarding() {
    document.getElementById("onboarding-modal")?.classList.remove("hidden");
  }
  function closeOnboarding() {
    const dontShowAgain = document.getElementById("dont-show-again")?.checked;
    if (dontShowAgain) {
      localStorage.setItem("bert_onboarding_done", "true");
    }
    document.getElementById("onboarding-modal")?.classList.add("hidden");
  }
  function checkOnboarding() {
    const onboardingDone = localStorage.getItem("bert_onboarding_done");
    if (!onboardingDone) {
      showOnboarding();
    }
  }
  function escapeHtml(str) {
    if (str === null || str === void 0) return "";
    return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#x27;");
  }
  document.addEventListener("DOMContentLoaded", async () => {
    const token = getToken();
    if (!token) {
      window.location.href = "/login";
      return;
    }
    checkOnboarding();
    loadDatasets();
    loadDatasetsForSelect();
    loadRuns();
    document.getElementById("upload-file")?.addEventListener("change", handleFileChange);
    document.getElementById("upload-form")?.addEventListener("submit", handleUploadSubmit);
    document.getElementById("new-run-form")?.addEventListener("submit", handleNewRunSubmit);
    document.getElementById("test-pdf-input")?.addEventListener("change", handlePdfInputChange);
    setInterval(() => {
      if (currentTab === "acompanhar") {
        loadRuns();
        if (activeTrainingRunId) {
          updateActiveTrainingStatus();
        }
      }
    }, 15e3);
  });
  window.showTab = showTab;
  window.viewDataset = viewDataset;
  window.showUploadModal = showUploadModal;
  window.closeUploadModal = closeUploadModal;
  window.validateDataset = validateDataset;
  window.filterRuns = filterRuns;
  window.viewRun = viewRun;
  window.closeRunDetail = closeRunDetail;
  window.cancelTraining = cancelTraining;
  window.selectPreset = selectPreset;
  window.setTestMode = setTestMode;
  window.classifyText = classifyText;
  window.classifyPdf = classifyPdf;
  window.deleteTest = deleteTest;
  window.clearTestHistory = clearTestHistory;
  window.showOnboarding = showOnboarding;
  window.closeOnboarding = closeOnboarding;
})();
//# sourceMappingURL=app.js.map
