// BERT Training - Frontend Application
// Portal PGE-MS

// ==================== Auth ====================

function getToken() {
    return localStorage.getItem('access_token') || sessionStorage.getItem('access_token');
}

async function apiCall(endpoint, options = {}) {
    const token = getToken();
    if (!token) {
        window.location.href = '/login';
        return null;
    }

    const response = await fetch(`/bert-training${endpoint}`, {
        ...options,
        headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
            ...options.headers
        }
    });

    if (response.status === 401) {
        window.location.href = '/login';
        return null;
    }

    return response;
}

function logout() {
    localStorage.removeItem('access_token');
    sessionStorage.removeItem('access_token');
    window.location.href = '/login';
}

// ==================== Tabs ====================

function showTab(tabName) {
    // Hide all panels
    document.querySelectorAll('.tab-panel').forEach(panel => {
        panel.classList.add('hidden');
    });

    // Deactivate all tabs
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('tab-active');
        btn.classList.add('text-gray-500');
    });

    // Show selected panel
    document.getElementById(`panel-${tabName}`).classList.remove('hidden');

    // Activate selected tab
    const activeTab = document.getElementById(`tab-${tabName}`);
    activeTab.classList.add('tab-active');
    activeTab.classList.remove('text-gray-500');

    // Load data for tab
    if (tabName === 'datasets') loadDatasets();
    if (tabName === 'runs') loadRuns();
    if (tabName === 'new-run') loadDatasetsForSelect();
}

// ==================== Datasets ====================

async function loadDatasets() {
    const response = await apiCall('/api/datasets');
    if (!response) return;

    const datasets = await response.json();
    const container = document.getElementById('datasets-list');

    if (datasets.length === 0) {
        container.innerHTML = '<p class="text-gray-500">Nenhum dataset encontrado. Faca upload de um dataset Excel.</p>';
        return;
    }

    container.innerHTML = datasets.map(d => `
        <div class="border rounded-lg p-4 hover:bg-gray-50">
            <div class="flex justify-between items-start">
                <div>
                    <h3 class="font-medium">${d.filename}</h3>
                    <div class="text-sm text-gray-500 mt-1">
                        <span class="inline-block bg-gray-100 rounded px-2 py-0.5 mr-2">${d.task_type === 'text_classification' ? 'Classificacao' : 'NER'}</span>
                        <span>${d.total_rows} amostras</span>
                        <span class="mx-2">|</span>
                        <span>${d.total_labels || '?'} labels</span>
                    </div>
                    <div class="text-xs text-gray-400 mt-1">
                        Hash: ${d.sha256_hash.substring(0, 16)}... | ${new Date(d.uploaded_at).toLocaleDateString('pt-BR')}
                    </div>
                </div>
                <div class="flex space-x-2">
                    <button onclick="viewDataset(${d.id})" class="text-blue-600 hover:text-blue-800 text-sm">Ver</button>
                    <a href="/bert-training/api/datasets/${d.id}/download" class="text-green-600 hover:text-green-800 text-sm">Download</a>
                </div>
            </div>
        </div>
    `).join('');
}

async function viewDataset(id) {
    const response = await apiCall(`/api/datasets/${id}`);
    if (!response) return;

    const dataset = await response.json();

    const content = `
        <div class="space-y-4">
            <div class="grid grid-cols-2 gap-4">
                <div><strong>Arquivo:</strong> ${dataset.filename}</div>
                <div><strong>Tipo:</strong> ${dataset.task_type}</div>
                <div><strong>Coluna Texto:</strong> ${dataset.text_column}</div>
                <div><strong>Coluna Label:</strong> ${dataset.label_column}</div>
                <div><strong>Total Linhas:</strong> ${dataset.total_rows}</div>
                <div><strong>Total Labels:</strong> ${dataset.total_labels}</div>
            </div>

            <div>
                <strong>Distribuicao de Labels:</strong>
                <div class="mt-2 max-h-40 overflow-y-auto">
                    ${Object.entries(dataset.label_distribution || {}).map(([label, count]) => `
                        <div class="flex justify-between text-sm py-1 border-b">
                            <span>${label}</span>
                            <span class="text-gray-500">${count}</span>
                        </div>
                    `).join('')}
                </div>
            </div>

            <div>
                <strong>Preview:</strong>
                <div class="mt-2 overflow-x-auto">
                    <table class="min-w-full text-sm">
                        <thead>
                            <tr class="bg-gray-100">
                                <th class="px-2 py-1 text-left">${dataset.text_column}</th>
                                <th class="px-2 py-1 text-left">${dataset.label_column}</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${(dataset.sample_preview || []).map(row => `
                                <tr class="border-b">
                                    <td class="px-2 py-1 max-w-md truncate">${String(row[dataset.text_column]).substring(0, 100)}...</td>
                                    <td class="px-2 py-1">${row[dataset.label_column]}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    `;

    document.getElementById('run-detail-title').textContent = 'Detalhes do Dataset';
    document.getElementById('run-detail-content').innerHTML = content;
    document.getElementById('run-detail-modal').classList.remove('hidden');
}

// ==================== Upload ====================

let currentPreviewData = null;

function showUploadModal() {
    document.getElementById('upload-modal').classList.remove('hidden');
    resetUploadModal();
}

function closeUploadModal() {
    document.getElementById('upload-modal').classList.add('hidden');
    resetUploadModal();
}

function resetUploadModal() {
    document.getElementById('upload-form').reset();
    document.getElementById('upload-preview').classList.add('hidden');
    document.getElementById('upload-preview-content').classList.add('hidden');
    document.getElementById('upload-validation').classList.add('hidden');
    document.getElementById('btn-validate').classList.add('hidden');
    document.getElementById('btn-upload').classList.add('hidden');
    currentPreviewData = null;
}

// Listener para quando o arquivo é selecionado
document.getElementById('upload-file').addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    // Mostra loading
    document.getElementById('upload-preview').classList.remove('hidden');
    document.getElementById('upload-preview-loading').classList.remove('hidden');
    document.getElementById('upload-preview-content').classList.add('hidden');

    // Chama API de preview
    const formData = new FormData();
    formData.append('file', file);

    const token = getToken();
    try {
        const response = await fetch('/bert-training/api/datasets/preview', {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` },
            body: formData
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Erro ao analisar arquivo');
        }

        const data = await response.json();
        currentPreviewData = data;

        // Mostra conteudo do preview
        document.getElementById('upload-preview-loading').classList.add('hidden');
        document.getElementById('upload-preview-content').classList.remove('hidden');

        // Info basica
        document.getElementById('preview-info').innerHTML = `
            <strong>${data.filename}</strong> -
            ${data.total_rows} linhas, ${data.total_columns} colunas
        `;

        // Popula selects de colunas
        const textSelect = document.getElementById('upload-text-col');
        const labelSelect = document.getElementById('upload-label-col');

        textSelect.innerHTML = '<option value="">Selecione a coluna de texto...</option>' +
            data.columns.map(col => `<option value="${col}">${col}</option>`).join('');

        labelSelect.innerHTML = '<option value="">Selecione a coluna de labels...</option>' +
            data.columns.map(col => `<option value="${col}">${col}</option>`).join('');

        // Sugere colunas candidatas
        if (data.text_candidates.length > 0) {
            textSelect.value = data.text_candidates[0];
            document.getElementById('text-col-hint').textContent = `Sugestao: ${data.text_candidates.join(', ')}`;
            document.getElementById('text-col-hint').classList.remove('hidden');
        }
        if (data.label_candidates.length > 0) {
            labelSelect.value = data.label_candidates[0];
            document.getElementById('label-col-hint').textContent = `Sugestao: ${data.label_candidates.join(', ')}`;
            document.getElementById('label-col-hint').classList.remove('hidden');
        }

        // Estatisticas das colunas
        document.getElementById('column-stats').innerHTML = data.column_stats.map(col => `
            <div class="border-b py-2">
                <div class="flex justify-between">
                    <span class="font-medium">${col.name}</span>
                    <span class="text-gray-500">${col.unique_values} valores unicos</span>
                </div>
                <div class="text-xs text-gray-400 mt-1">
                    ${col.null_count > 0 ? `<span class="text-yellow-600">${col.null_count} nulos</span> | ` : ''}
                    Exemplos: ${col.sample_values.join(', ')}
                </div>
                ${col.is_text_candidate ? '<span class="text-xs bg-blue-100 text-blue-700 px-1 rounded">texto</span>' : ''}
                ${col.is_label_candidate ? '<span class="text-xs bg-green-100 text-green-700 px-1 rounded">label</span>' : ''}
            </div>
        `).join('');

        // Preview dos dados
        if (data.preview_rows && data.preview_rows.length > 0) {
            const headers = Object.keys(data.preview_rows[0]);
            document.getElementById('data-preview').innerHTML = `
                <table class="min-w-full text-xs">
                    <thead>
                        <tr class="bg-gray-100">
                            ${headers.map(h => `<th class="px-2 py-1 text-left">${h}</th>`).join('')}
                        </tr>
                    </thead>
                    <tbody>
                        ${data.preview_rows.map(row => `
                            <tr class="border-b">
                                ${headers.map(h => `<td class="px-2 py-1 max-w-xs truncate">${String(row[h] || '').substring(0, 50)}</td>`).join('')}
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            `;
        }

        // Mostra botoes
        document.getElementById('btn-validate').classList.remove('hidden');
        document.getElementById('btn-upload').classList.remove('hidden');

    } catch (error) {
        document.getElementById('upload-preview-loading').innerHTML = `
            <div class="text-red-600">${error.message}</div>
        `;
    }
});

async function validateDataset() {
    const file = document.getElementById('upload-file').files[0];
    if (!file) {
        alert('Selecione um arquivo');
        return;
    }

    const textCol = document.getElementById('upload-text-col').value;
    const labelCol = document.getElementById('upload-label-col').value;

    if (!textCol || !labelCol) {
        alert('Selecione as colunas de texto e labels');
        return;
    }

    const formData = new FormData();
    formData.append('file', file);
    formData.append('task_type', document.getElementById('upload-task-type').value);
    formData.append('text_column', textCol);
    formData.append('label_column', labelCol);

    const token = getToken();
    const response = await fetch('/bert-training/api/datasets/validate', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: formData
    });

    const result = await response.json();
    const validationDiv = document.getElementById('upload-validation');
    validationDiv.classList.remove('hidden');

    if (result.is_valid) {
        validationDiv.innerHTML = `
            <div class="bg-green-50 border border-green-200 rounded p-3">
                <p class="text-green-800 font-medium">Validacao OK!</p>
                <p class="text-sm text-green-600">${result.total_rows} linhas validas</p>
                ${result.warnings.length > 0 ? `
                    <div class="mt-2 text-sm text-yellow-700">
                        <strong>Avisos:</strong>
                        <ul class="list-disc ml-4">${result.warnings.map(w => `<li>${w}</li>`).join('')}</ul>
                    </div>
                ` : ''}
            </div>
        `;
    } else {
        validationDiv.innerHTML = `
            <div class="bg-red-50 border border-red-200 rounded p-3">
                <p class="text-red-800 font-medium">Validacao Falhou</p>
                <ul class="text-sm text-red-600 list-disc ml-4">
                    ${result.errors.map(e => `<li>${e}</li>`).join('')}
                </ul>
            </div>
        `;
    }
}

document.getElementById('upload-form').addEventListener('submit', async (e) => {
    e.preventDefault();

    const file = document.getElementById('upload-file').files[0];
    if (!file) {
        alert('Selecione um arquivo');
        return;
    }

    const textCol = document.getElementById('upload-text-col').value;
    const labelCol = document.getElementById('upload-label-col').value;

    if (!textCol || !labelCol) {
        alert('Selecione as colunas de texto e labels');
        return;
    }

    const formData = new FormData();
    formData.append('file', file);
    formData.append('task_type', document.getElementById('upload-task-type').value);
    formData.append('text_column', textCol);
    formData.append('label_column', labelCol);

    const token = getToken();
    const response = await fetch('/bert-training/api/datasets/upload', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: formData
    });

    if (response.ok) {
        const result = await response.json();
        alert(result.is_duplicate ? 'Dataset ja existe!' : 'Dataset enviado com sucesso!');
        closeUploadModal();
        loadDatasets();
    } else {
        const error = await response.json();
        alert('Erro: ' + (error.detail || 'Falha no upload'));
    }
});

// ==================== Runs ====================

async function loadRuns() {
    const response = await apiCall('/api/runs');
    if (!response) return;

    const runs = await response.json();
    const container = document.getElementById('runs-list');

    if (runs.length === 0) {
        container.innerHTML = '<p class="text-gray-500">Nenhum run encontrado. Crie um novo run para iniciar.</p>';
        return;
    }

    container.innerHTML = runs.map(r => `
        <div class="border rounded-lg p-4 hover:bg-gray-50 cursor-pointer" onclick="viewRun(${r.id})">
            <div class="flex justify-between items-start">
                <div>
                    <h3 class="font-medium">${r.name}</h3>
                    <div class="text-sm text-gray-500 mt-1">
                        <span class="inline-block status-${r.status} rounded px-2 py-0.5 mr-2">${r.status}</span>
                        <span>${r.base_model}</span>
                    </div>
                    <div class="text-xs text-gray-400 mt-1">
                        Criado: ${new Date(r.created_at).toLocaleDateString('pt-BR')}
                        ${r.final_accuracy ? ` | Accuracy: ${(r.final_accuracy * 100).toFixed(1)}%` : ''}
                        ${r.final_macro_f1 ? ` | F1: ${(r.final_macro_f1 * 100).toFixed(1)}%` : ''}
                    </div>
                </div>
                <div class="text-blue-600">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/>
                    </svg>
                </div>
            </div>
        </div>
    `).join('');
}

async function viewRun(id) {
    const response = await apiCall(`/api/runs/${id}`);
    if (!response) return;

    const run = await response.json();

    const content = `
        <div class="space-y-6">
            <!-- Info basica -->
            <div class="grid grid-cols-2 gap-4 text-sm">
                <div><strong>Status:</strong> <span class="status-${run.status} px-2 py-0.5 rounded">${run.status}</span></div>
                <div><strong>Modelo:</strong> ${run.base_model}</div>
                <div><strong>Dataset:</strong> ${run.dataset_filename}</div>
                <div><strong>Seed:</strong> ${run.config_json.seed}</div>
            </div>

            ${run.error_message ? `
                <div class="bg-red-50 border border-red-200 rounded p-3 text-sm text-red-700">
                    <strong>Erro:</strong> ${run.error_message}
                </div>
            ` : ''}

            <!-- Metricas finais -->
            ${run.final_accuracy ? `
                <div class="bg-green-50 border border-green-200 rounded p-4">
                    <h4 class="font-medium text-green-800 mb-2">Metricas Finais</h4>
                    <div class="grid grid-cols-3 gap-4 text-center">
                        <div>
                            <div class="text-2xl font-bold text-green-600">${(run.final_accuracy * 100).toFixed(1)}%</div>
                            <div class="text-xs text-gray-500">Accuracy</div>
                        </div>
                        <div>
                            <div class="text-2xl font-bold text-green-600">${(run.final_macro_f1 * 100).toFixed(1)}%</div>
                            <div class="text-xs text-gray-500">Macro F1</div>
                        </div>
                        <div>
                            <div class="text-2xl font-bold text-green-600">${(run.final_weighted_f1 * 100).toFixed(1)}%</div>
                            <div class="text-xs text-gray-500">Weighted F1</div>
                        </div>
                    </div>
                </div>
            ` : ''}

            <!-- Grafico de metricas -->
            ${run.recent_metrics && run.recent_metrics.length > 0 ? `
                <div>
                    <h4 class="font-medium mb-2">Progresso do Treinamento</h4>
                    <canvas id="metrics-chart" height="200"></canvas>
                </div>
            ` : ''}

            <!-- Config -->
            <details class="border rounded-lg p-3">
                <summary class="cursor-pointer font-medium">Configuracao Completa</summary>
                <pre class="mt-2 text-xs bg-gray-100 p-2 rounded overflow-x-auto">${JSON.stringify(run.config_json, null, 2)}</pre>
            </details>

            <!-- Reprodutibilidade -->
            <div class="text-xs text-gray-500 space-y-1">
                <div><strong>Git Commit:</strong> ${run.git_commit_hash || 'N/A'}</div>
                <div><strong>Env Fingerprint:</strong> ${run.environment_fingerprint || 'N/A'}</div>
                <div><strong>Model Fingerprint:</strong> ${run.model_fingerprint || 'N/A'}</div>
            </div>

            <!-- Acoes -->
            <div class="flex space-x-2 pt-4 border-t">
                ${run.status === 'completed' ? `
                    <button onclick="reproduceRun(${run.id})" class="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700">
                        Reproduzir
                    </button>
                ` : ''}
                <button onclick="viewRunLogs(${run.id})" class="px-4 py-2 border rounded hover:bg-gray-50">
                    Ver Logs
                </button>
            </div>
        </div>
    `;

    document.getElementById('run-detail-title').textContent = run.name;
    document.getElementById('run-detail-content').innerHTML = content;
    document.getElementById('run-detail-modal').classList.remove('hidden');

    // Renderiza grafico se houver metricas
    if (run.recent_metrics && run.recent_metrics.length > 0) {
        renderMetricsChart(run.recent_metrics);
    }
}

function renderMetricsChart(metrics) {
    const ctx = document.getElementById('metrics-chart').getContext('2d');

    new Chart(ctx, {
        type: 'line',
        data: {
            labels: metrics.map(m => `Epoch ${m.epoch}`),
            datasets: [
                {
                    label: 'Train Loss',
                    data: metrics.map(m => m.train_loss),
                    borderColor: 'rgb(239, 68, 68)',
                    backgroundColor: 'rgba(239, 68, 68, 0.1)',
                    tension: 0.1
                },
                {
                    label: 'Val Loss',
                    data: metrics.map(m => m.val_loss),
                    borderColor: 'rgb(59, 130, 246)',
                    backgroundColor: 'rgba(59, 130, 246, 0.1)',
                    tension: 0.1
                },
                {
                    label: 'Val Accuracy',
                    data: metrics.map(m => m.val_accuracy),
                    borderColor: 'rgb(34, 197, 94)',
                    backgroundColor: 'rgba(34, 197, 94, 0.1)',
                    tension: 0.1,
                    yAxisID: 'y1'
                }
            ]
        },
        options: {
            responsive: true,
            interaction: { mode: 'index', intersect: false },
            scales: {
                y: { type: 'linear', display: true, position: 'left', title: { display: true, text: 'Loss' } },
                y1: { type: 'linear', display: true, position: 'right', title: { display: true, text: 'Accuracy' }, grid: { drawOnChartArea: false } }
            }
        }
    });
}

async function reproduceRun(id) {
    if (!confirm('Criar novo run com a mesma configuracao?')) return;

    const response = await apiCall(`/api/runs/${id}/reproduce`, { method: 'POST' });
    if (response && response.ok) {
        alert('Novo run criado e adicionado a fila!');
        closeRunDetail();
        loadRuns();
    } else {
        const error = await response.json();
        alert('Erro: ' + (error.detail || 'Falha ao reproduzir'));
    }
}

function viewRunLogs(runId) {
    alert('Funcionalidade de logs em tempo real sera implementada em breve!');
}

function closeRunDetail() {
    document.getElementById('run-detail-modal').classList.add('hidden');
}

// ==================== New Run ====================

// Cache de presets
let presetsCache = null;
let advancedModeEnabled = false;

async function loadDatasetsForSelect() {
    const response = await apiCall('/api/datasets');
    if (!response) return;

    const datasets = await response.json();
    const select = document.getElementById('run-dataset');

    select.innerHTML = '<option value="">Selecione um dataset...</option>' +
        datasets.map(d => `<option value="${d.id}">${d.filename} (${d.total_rows} amostras, ${d.total_labels} labels)</option>`).join('');

    // Carrega presets
    loadPresets();
}

async function loadPresets() {
    if (presetsCache) {
        renderPresets(presetsCache);
        return;
    }

    const response = await apiCall('/api/presets');
    if (!response) return;

    const data = await response.json();
    presetsCache = data.presets;
    renderPresets(presetsCache);
}

function renderPresets(presets) {
    const container = document.getElementById('presets-container');
    if (!container) return;

    // Icones para cada preset
    const icons = {
        'rapido': `<svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>`,
        'equilibrado': `<svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 6l3 1m0 0l-3 9a5.002 5.002 0 006.001 0M6 7l3 9M6 7l6-2m6 2l3-1m-3 1l-3 9a5.002 5.002 0 006.001 0M18 7l3 9m-3-9l-6-2m0-2v2m0 16V5m0 16H9m3 0h3"/></svg>`,
        'preciso': `<svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>`
    };

    container.innerHTML = presets.map(p => `
        <div class="preset-card border-2 rounded-lg p-4 cursor-pointer hover:border-blue-500 transition-all ${p.is_recommended ? 'border-blue-300 bg-blue-50' : 'border-gray-200'}"
             data-preset="${p.name}"
             onclick="selectPreset('${p.name}')">
            <div class="flex flex-col items-center text-center">
                <div class="text-blue-600 mb-2">
                    ${icons[p.name] || icons['equilibrado']}
                </div>
                <h3 class="font-bold text-lg">${p.display_name}</h3>
                ${p.is_recommended ? '<span class="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded mt-1">Recomendado</span>' : ''}
                <p class="text-sm text-gray-600 mt-2">${p.description}</p>
                <div class="text-xs text-gray-500 mt-3">
                    ${p.estimated_time_minutes_min ? `~${p.estimated_time_minutes_min}-${p.estimated_time_minutes_max} min` : ''}
                </div>
                <div class="text-xs text-gray-400 mt-1">
                    ${p.config.epochs} rodadas
                </div>
            </div>
        </div>
    `).join('');

    // Seleciona o recomendado por padrao
    const recommended = presets.find(p => p.is_recommended) || presets[1];
    if (recommended) {
        selectPreset(recommended.name);
    }
}

function selectPreset(presetName) {
    // Atualiza visual
    document.querySelectorAll('.preset-card').forEach(card => {
        card.classList.remove('border-blue-500', 'bg-blue-100');
        if (card.dataset.preset === presetName) {
            card.classList.add('border-blue-500', 'bg-blue-100');
        }
    });

    // Armazena preset selecionado
    document.getElementById('selected-preset').value = presetName;

    // Se preset rapido, mostra aviso
    const warningDiv = document.getElementById('preset-warning');
    if (presetName === 'rapido') {
        warningDiv.innerHTML = `
            <div class="bg-yellow-50 border border-yellow-200 rounded p-3 text-sm text-yellow-700">
                <strong>Modo Rapido:</strong> Ideal para testar se o dataset esta correto.
                Os resultados podem nao ser muito precisos.
            </div>
        `;
        warningDiv.classList.remove('hidden');
    } else if (presetName === 'preciso') {
        warningDiv.innerHTML = `
            <div class="bg-blue-50 border border-blue-200 rounded p-3 text-sm text-blue-700">
                <strong>Modo Preciso:</strong> Pode demorar varias horas, mas oferece os melhores resultados.
            </div>
        `;
        warningDiv.classList.remove('hidden');
    } else {
        warningDiv.classList.add('hidden');
    }
}

function toggleAdvancedMode() {
    advancedModeEnabled = !advancedModeEnabled;
    const advancedSection = document.getElementById('advanced-params');
    const toggleBtn = document.getElementById('toggle-advanced-btn');

    if (advancedModeEnabled) {
        advancedSection.classList.remove('hidden');
        toggleBtn.textContent = 'Ocultar configuracoes avancadas';
    } else {
        advancedSection.classList.add('hidden');
        toggleBtn.textContent = 'Configurar manualmente (avancado)';
    }
}

document.getElementById('new-run-form').addEventListener('submit', async (e) => {
    e.preventDefault();

    const presetName = document.getElementById('selected-preset').value;

    // Monta dados baseado no modo
    let data = {
        name: document.getElementById('run-name').value,
        description: document.getElementById('run-description').value || null,
        dataset_id: parseInt(document.getElementById('run-dataset').value),
        base_model: document.getElementById('run-model').value,
        preset_name: presetName
    };

    // Se modo avancado esta ativo, adiciona hyperparameters
    if (advancedModeEnabled) {
        data.hyperparameters = {
            learning_rate: parseFloat(document.getElementById('run-lr').value),
            batch_size: parseInt(document.getElementById('run-batch').value),
            epochs: parseInt(document.getElementById('run-epochs').value),
            max_length: parseInt(document.getElementById('run-maxlen').value),
            train_split: parseFloat(document.getElementById('run-split').value),
            early_stopping_patience: parseInt(document.getElementById('run-patience').value),
            seed: parseInt(document.getElementById('run-seed').value),
            warmup_steps: parseInt(document.getElementById('run-warmup').value),
            weight_decay: parseFloat(document.getElementById('run-weight-decay').value),
            gradient_accumulation_steps: parseInt(document.getElementById('run-grad-accum').value),
            truncation_side: document.getElementById('run-truncation').value,
            use_class_weights: document.getElementById('run-class-weights').checked
        };
    }

    const response = await apiCall('/api/runs', {
        method: 'POST',
        body: JSON.stringify(data)
    });

    if (response && response.ok) {
        const result = await response.json();
        alert(`Treinamento "${result.name}" iniciado!\n\nPreset: ${result.preset_name || 'customizado'}\n\nAcompanhe o progresso na aba "Runs".`);
        document.getElementById('new-run-form').reset();
        showTab('runs');
    } else {
        const error = await response.json();
        alert('Erro: ' + (error.detail || 'Falha ao criar run'));
    }
});

// ==================== Queue Status ====================

async function updateQueueStatus() {
    try {
        const response = await apiCall('/api/queue/status');
        if (response && response.ok) {
            const status = await response.json();
            document.getElementById('queue-status').textContent =
                `Fila: ${status.pending} pendente(s), ${status.training} treinando`;
        }
    } catch (e) {
        console.error('Erro ao atualizar status da fila:', e);
    }
}

// ==================== Onboarding ====================

function showOnboarding() {
    document.getElementById('onboarding-modal').classList.remove('hidden');
}

function closeOnboarding() {
    const dontShowAgain = document.getElementById('dont-show-again').checked;
    if (dontShowAgain) {
        localStorage.setItem('bert_onboarding_done', 'true');
    }
    document.getElementById('onboarding-modal').classList.add('hidden');
}

function checkOnboarding() {
    const onboardingDone = localStorage.getItem('bert_onboarding_done');
    if (!onboardingDone) {
        showOnboarding();
    }
}


// ==================== Init ====================

document.addEventListener('DOMContentLoaded', async () => {
    const token = getToken();
    if (!token) {
        window.location.href = '/login';
        return;
    }

    // Verifica se deve mostrar onboarding
    checkOnboarding();

    // Carrega dados iniciais
    loadDatasets();
    updateQueueStatus();

    // Atualiza status da fila periodicamente
    setInterval(updateQueueStatus, 30000);
});
