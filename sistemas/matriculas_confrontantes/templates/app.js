/**
 * Sistema de Análise Documental - Matrículas Confrontantes
 * JavaScript Application - Conectado ao Backend FastAPI
 */

// ============================================
// API Configuration
// ============================================

const API_BASE = '/matriculas/api';

// Função para obter token de autenticação
function getAuthToken() {
    return localStorage.getItem('access_token');
}

// Verifica se está autenticado, redireciona para login se não
function checkAuth() {
    const token = getAuthToken();
    if (!token) {
        window.location.href = '/login';
        return false;
    }
    return true;
}

// Função de logout
function logout() {
    localStorage.removeItem('access_token');
    window.location.href = '/login';
}

// Estado da aplicação
let appState = {
    files: [],
    folders: [],
    registros: [],
    logs: [],
    selectedFileId: null,
    selectedFileIds: [],  // Para seleção múltipla (análise em lote)
    documentDetails: null,
    currentAnaliseId: null,
    currentGrupoId: null,  // Para análise em lote
    config: {
        version: '1.0.0',
        model: 'google/gemini-3-flash-preview',
        hasApiKey: false
    },
    pollingIntervals: {}
};

// ============================================
// API Functions
// ============================================

async function api(endpoint, options = {}) {
    if (!checkAuth()) return null;

    const token = getAuthToken();

    try {
        const response = await fetch(`${API_BASE}${endpoint}`, {
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`,
                ...options.headers
            },
            ...options
        });

        if (response.status === 401) {
            // Token expirado ou inválido
            localStorage.removeItem('access_token');
            window.location.href = '/login';
            return null;
        }

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        return await response.json();
    } catch (error) {
        console.error(`API Error [${endpoint}]:`, error);
        throw error;
    }
}

async function loadFiles() {
    try {
        appState.files = await api('/files');
        renderFileList();
    } catch (error) {
        console.error('Erro ao carregar arquivos:', error);
        appState.files = [];
        renderFileList();
    }
}

async function loadAnalyses() {
    try {
        const response = await api('/analyses');
        console.log('[loadAnalyses] Resposta da API:', response);

        if (Array.isArray(response)) {
            appState.registros = response;
            console.log('[loadAnalyses] Análises carregadas:', appState.registros.length, appState.registros);
        } else if (response.error) {
            console.error('[loadAnalyses] Erro retornado pela API:', response.error);
            appState.registros = [];
        } else {
            console.warn('[loadAnalyses] Resposta inesperada:', response);
            appState.registros = [];
        }

        renderRecordsTable();
    } catch (error) {
        console.error('[loadAnalyses] Erro ao carregar análises:', error);
        appState.registros = [];
        renderRecordsTable();
    }
}

async function loadLogs() {
    try {
        appState.logs = await api('/logs');
        renderSystemLogs();
    } catch (error) {
        console.error('Erro ao carregar logs:', error);
    }
}

async function loadDocumentDetails(fileId) {
    appState.selectedFileId = fileId;

    // Carrega detalhes do arquivo
    const file = appState.files.find(f => String(f.id) === String(fileId));
    if (file) {
        // Atualiza nome do documento no visualizador
        const docNameEl = document.getElementById('current-doc-name');
        if (docNameEl) {
            docNameEl.textContent = file.name;
        }

        // Carrega PDF no visualizador
        loadPdfViewer(fileId, file.type);
    }

    // Verifica se tem resultado de análise
    try {
        const result = await api(`/resultado/${fileId}`);
        appState.documentDetails = result;
        renderExtractedDataPanel();
        // Se tem análise, mostra o relatório
        await generateAndShowReport();
    } catch (error) {
        // Não tem análise ainda
        appState.documentDetails = null;
        renderExtractedDataPanel();
    }
}

async function loadPdfViewer(fileId, fileType) {
    const viewer = document.getElementById('pdf-viewer');
    if (!viewer) return;

    const token = getAuthToken();

    // Verifica se o arquivo ainda existe (pode ter sido removido após análise)
    const file = appState.files.find(f => String(f.id) === String(fileId));

    if (!file) {
        // Arquivo já foi analisado e removido - mostra mensagem
        viewer.innerHTML = `
            <div class="text-center text-gray-400 py-20">
                <i class="fas fa-file-pdf text-6xl mb-4 text-gray-300"></i>
                <p class="text-lg">Documento já analisado</p>
                <p class="text-sm mt-2">O PDF foi removido após a análise.</p>
                <p class="text-xs mt-1 text-gray-500">Os dados extraídos estão disponíveis no relatório.</p>
            </div>
        `;
        return;
    }

    // Mostra loading enquanto carrega
    viewer.innerHTML = `
        <div class="text-center text-gray-400 py-20">
            <i class="fas fa-spinner fa-spin text-4xl mb-4"></i>
            <p class="text-lg">Carregando documento...</p>
        </div>
    `;

    try {
        // Busca o arquivo via fetch com Authorization header (mais seguro que token na URL)
        const response = await fetch(`${API_BASE}/files/${fileId}/view`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        // Cria blob URL a partir da resposta
        const blob = await response.blob();
        const blobUrl = URL.createObjectURL(blob);

        // Guarda referência para limpar depois
        if (viewer._currentBlobUrl) {
            URL.revokeObjectURL(viewer._currentBlobUrl);
        }
        viewer._currentBlobUrl = blobUrl;

        if (fileType === 'pdf') {
            // Usa object tag para PDFs com blob URL (evita problemas de CSP com iframe)
            viewer.innerHTML = `
                <div class="w-full h-full flex flex-col">
                    <object
                        data="${blobUrl}#view=FitH"
                        type="application/pdf"
                        class="w-full flex-1 border-0"
                        style="min-height: 600px;"
                    >
                        <div class="text-center text-gray-400 py-20">
                            <i class="fas fa-file-pdf text-6xl mb-4 text-red-400"></i>
                            <p class="text-lg mb-4">Não foi possível exibir o PDF no navegador</p>
                            <button onclick="openPdfInNewTab('${fileId}')"
                                class="px-6 py-3 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors">
                                <i class="fas fa-external-link-alt mr-2"></i>Abrir PDF em nova aba
                            </button>
                        </div>
                    </object>
                    <div class="bg-gray-100 px-4 py-2 border-t flex justify-end">
                        <button onclick="openPdfInNewTab('${fileId}')"
                            class="text-sm text-blue-600 hover:text-blue-800 flex items-center gap-1">
                            <i class="fas fa-external-link-alt"></i>Abrir em nova aba
                        </button>
                    </div>
                </div>
            `;
        } else {
            // Usa img para imagens com blob URL
            viewer.innerHTML = `
                <div class="flex items-center justify-center h-full w-full p-4">
                    <img
                        src="${blobUrl}"
                        class="w-full h-auto object-contain rounded-lg shadow-lg"
                        alt="Documento"
                        style="max-height: 100%;"
                    />
                </div>
            `;
        }
    } catch (error) {
        console.error('Erro ao carregar documento:', error);
        // Fallback: mostra botão para abrir em nova aba
        viewer.innerHTML = `
            <div class="text-center text-gray-400 py-20">
                <i class="fas fa-exclamation-triangle text-6xl mb-4 text-yellow-500"></i>
                <p class="text-lg mb-2">Erro ao carregar documento</p>
                <p class="text-sm text-gray-500 mb-4">${error.message || 'Tente novamente'}</p>
                <button onclick="openPdfInNewTab('${fileId}')"
                    class="px-6 py-3 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors">
                    <i class="fas fa-external-link-alt mr-2"></i>Abrir em nova aba
                </button>
            </div>
        `;
    }
}

// Função para abrir PDF em nova aba (fallback seguro)
async function openPdfInNewTab(fileId) {
    const token = getAuthToken();
    try {
        // Busca o arquivo via fetch com Authorization header
        const response = await fetch(`${API_BASE}/files/${fileId}/view`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        // Cria blob URL e abre em nova aba
        const blob = await response.blob();
        const blobUrl = URL.createObjectURL(blob);
        window.open(blobUrl, '_blank');

        // Limpa blob URL após alguns segundos (tempo suficiente para abrir)
        setTimeout(() => URL.revokeObjectURL(blobUrl), 60000);
    } catch (error) {
        console.error('Erro ao abrir PDF:', error);
        showToast('Erro ao abrir documento: ' + (error.message || 'Tente novamente'), 'error');
    }
}

async function loadConfig() {
    try {
        appState.config = await api('/config');
        updateAnalysisStatus();
    } catch (error) {
        console.error('Erro ao carregar configurações:', error);
    }
}

function updateConfigUI() {
    // Configuração de API movida para o painel admin
    updateAnalysisStatus();
}

async function uploadFile(file, replace = false) {
    if (!checkAuth()) return;

    const token = getAuthToken();
    const formData = new FormData();
    formData.append('file', file);

    try {
        const url = replace
            ? `${API_BASE}/files/upload?replace=true`
            : `${API_BASE}/files/upload`;

        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`
            },
            body: formData
        });

        if (response.status === 401) {
            localStorage.removeItem('access_token');
            window.location.href = '/login';
            return;
        }

        const result = await response.json();

        if (result.success) {
            await loadFiles();
            showToast(`Arquivo ${file.name} importado com sucesso!`, 'success');
        } else if (result.error === 'duplicate') {
            // Arquivo duplicado - perguntar se deseja substituir
            showDuplicateConfirmModal(file, result.message);
        } else {
            showToast(result.error || 'Erro ao importar arquivo', 'error');
        }
    } catch (error) {
        showToast('Erro de conexão ao importar arquivo', 'error');
    }
}

function showDuplicateConfirmModal(file, message) {
    const modal = document.createElement('div');
    modal.id = 'duplicate-confirm-modal';
    modal.className = 'fixed inset-0 z-50 flex items-center justify-center bg-black/50';

    modal.innerHTML = `
        <div class="bg-white rounded-xl shadow-2xl max-w-md w-full mx-4 overflow-hidden">
            <div class="bg-gradient-to-r from-yellow-500 to-orange-500 px-6 py-4">
                <div class="flex items-center gap-3">
                    <i class="fas fa-exclamation-triangle text-white text-2xl"></i>
                    <h3 class="text-lg font-semibold text-white">Arquivo Duplicado</h3>
                </div>
            </div>
            <div class="p-6">
                <p class="text-gray-700 mb-4">${message || 'Já existe um arquivo com este nome.'}</p>
                <p class="text-sm text-gray-500 mb-6">
                    Se substituir, a análise anterior será perdida.
                </p>
                <div class="flex gap-3">
                    <button onclick="confirmReplaceFile()" 
                        class="flex-1 px-4 py-2 bg-orange-500 text-white rounded-lg hover:bg-orange-600 transition-colors font-medium">
                        <i class="fas fa-sync-alt mr-2"></i>Substituir
                    </button>
                    <button onclick="cancelReplaceFile()" 
                        class="flex-1 px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 transition-colors font-medium">
                        Cancelar
                    </button>
                </div>
            </div>
        </div>
    `;

    // Guarda o arquivo para reenviar se confirmar
    window.pendingReplaceFile = file;

    document.body.appendChild(modal);
}

async function confirmReplaceFile() {
    const modal = document.getElementById('duplicate-confirm-modal');
    if (modal) modal.remove();

    if (window.pendingReplaceFile) {
        await uploadFile(window.pendingReplaceFile, true);
        window.pendingReplaceFile = null;
    }
}

function cancelReplaceFile() {
    const modal = document.getElementById('duplicate-confirm-modal');
    if (modal) modal.remove();
    window.pendingReplaceFile = null;
    showToast('Upload cancelado', 'info');
}

async function apiDeleteFile(fileId) {
    try {
        await api(`/files/${fileId}`, { method: 'DELETE' });

        // Se o arquivo deletado era o selecionado, limpa a seleção
        if (String(appState.selectedFileId) === String(fileId)) {
            appState.selectedFileId = null;
            appState.documentDetails = null;

            // Limpa o viewer
            const viewer = document.getElementById('pdf-viewer');
            if (viewer) {
                viewer.innerHTML = `
                    <div class="text-center text-gray-400 py-20">
                        <i class="fas fa-file-pdf text-6xl mb-4"></i>
                        <p class="text-lg">Visualização do Documento</p>
                        <p class="text-sm mt-2">Selecione um arquivo para visualizar</p>
                    </div>
                `;
            }

            // Limpa nome do documento
            const docNameEl = document.getElementById('current-doc-name');
            if (docNameEl) {
                docNameEl.textContent = 'Nenhum documento';
            }

            // Limpa relatório
            const reportView = document.getElementById('report-view');
            if (reportView) {
                reportView.innerHTML = `
                    <div class="text-center text-gray-400 py-12">
                        <i class="fas fa-file-alt text-5xl mb-4"></i>
                        <p class="text-lg">Relatório de Análise</p>
                        <p class="text-sm mt-2">Analise um documento para gerar o relatório automaticamente</p>
                    </div>
                `;
            }
        }

        // Recarrega tudo
        await loadFiles();
        await loadAnalyses();
        await loadLogs();

        updateAnalysisStatus();
        showToast('Arquivo excluído com sucesso', 'warning');
    } catch (error) {
        showToast('Erro ao excluir arquivo', 'error');
    }
}

async function apiToggleRecord(recordId) {
    try {
        await api(`/registros/${recordId}/toggle`, { method: 'POST' });
        await loadRegistros();
    } catch (error) {
        console.error('Erro ao expandir registro:', error);
    }
}

async function apiDeleteRecord(recordId) {
    try {
        await api(`/registros/${recordId}`, { method: 'DELETE' });
        await loadRegistros();
        await loadLogs();
        showToast('Registro excluído com sucesso', 'warning');
    } catch (error) {
        showToast('Erro ao excluir registro', 'error');
    }
}

async function apiClearLogs() {
    try {
        await api('/logs', { method: 'DELETE' });
        await loadLogs();
    } catch (error) {
        console.error('Erro ao limpar logs:', error);
    }
}

async function analisarDocumento(fileId, forceReanalysis = false) {
    // Validação da Matrícula Principal
    const matriculaInput = document.getElementById('matricula-principal-input');
    const matriculaPrincipal = matriculaInput ? matriculaInput.value.trim() : '';

    if (!matriculaPrincipal) {
        showToast('Por favor, informe a Matrícula Principal', 'warning');
        if (matriculaInput) matriculaInput.focus();
        return;
    }

    try {
        showToast('Verificando análise...', 'info');
        let url = forceReanalysis ? `/analisar/${fileId}?force=true` : `/analisar/${fileId}`;

        // Adiciona matrícula principal como query param
        url += (url.includes('?') ? '&' : '?') + `matricula_principal=${encodeURIComponent(matriculaPrincipal)}`;

        const result = await api(url, { method: 'POST' });

        if (result.success) {
            if (result.cached) {
                // Análise já existe, carrega direto
                showToast('Análise já realizada, carregando...', 'info');
                await loadAnalysisResult(fileId);
            } else {
                // Nova análise iniciada
                showToast('Iniciando análise do documento...', 'info');
                showProcessingModal(fileId);
                startAnalysisPolling(fileId);
            }
        } else {
            showToast(result.error || 'Erro ao iniciar análise', 'error');
        }
    } catch (error) {
        showToast('Erro ao analisar documento', 'error');
    }
}

async function loadAnalysisResult(fileId) {
    try {
        const result = await api(`/resultado/${fileId}`);
        appState.documentDetails = result;
        appState.currentAnaliseId = result.analise_id || null;
        await generateAndShowReport();
        await loadAnalyses();
        showToast('Análise carregada com sucesso!', 'success');
    } catch (error) {
        showToast('Erro ao carregar análise', 'error');
    }
}

function showProcessingModal(fileId) {
    // Remove modal existente se houver
    const existingModal = document.getElementById('processing-modal');
    if (existingModal) existingModal.remove();

    const file = appState.files.find(f => String(f.id) === String(fileId));

    const modal = document.createElement('div');
    modal.id = 'processing-modal';
    modal.className = 'fixed inset-0 z-50 flex items-center justify-center bg-black/50';
    modal.innerHTML = `
        <div class="bg-white rounded-xl shadow-2xl max-w-md w-full m-4 overflow-hidden">
            <div class="bg-gradient-to-r from-primary-500 to-accent-500 px-6 py-4">
                <h2 class="text-lg font-semibold text-white flex items-center gap-2">
                    <i class="fas fa-brain"></i>
                    Análise em Andamento
                </h2>
            </div>
            <div class="p-6">
                <div class="flex flex-col items-center text-center">
                    <div class="relative mb-6">
                        <div class="w-20 h-20 rounded-full border-4 border-primary-200 border-t-primary-500 animate-spin"></div>
                        <div class="absolute inset-0 flex items-center justify-center">
                            <i class="fas fa-file-pdf text-2xl text-primary-500"></i>
                        </div>
                    </div>
                    <h3 class="text-lg font-medium text-gray-800 mb-2">Processando Documento</h3>
                    <p class="text-sm text-gray-500 mb-1">${file?.name || 'Documento'}</p>
                    <p class="text-xs text-gray-400 mb-4" id="processing-status">Enviando para análise da IA...</p>
                    
                    <div class="w-full bg-gray-200 rounded-full h-2 mb-4">
                        <div class="bg-primary-500 h-2 rounded-full animate-pulse" style="width: 60%"></div>
                    </div>
                    
                    <p class="text-xs text-gray-400 mb-6">
                        <i class="fas fa-info-circle"></i>
                        Este processo pode levar alguns segundos dependendo do tamanho do documento
                    </p>
                </div>
                
                <button onclick="cancelAnalysis('${fileId}')" class="w-full px-4 py-3 text-sm text-red-600 bg-red-50 rounded-lg hover:bg-red-100 transition-colors flex items-center justify-center gap-2 font-medium">
                    <i class="fas fa-times-circle"></i>
                    Interromper Processamento
                </button>
            </div>
        </div>
    `;

    document.body.appendChild(modal);
}

function closeProcessingModal() {
    const modal = document.getElementById('processing-modal');
    if (modal) modal.remove();
}

async function cancelAnalysis(fileId) {
    // Para o polling
    if (appState.pollingIntervals[fileId]) {
        clearInterval(appState.pollingIntervals[fileId]);
        delete appState.pollingIntervals[fileId];
    }

    // Fecha o modal
    closeProcessingModal();

    // Atualiza status
    const statusEl = document.getElementById('analysis-status');
    if (statusEl) {
        statusEl.innerHTML = '<i class="fas fa-times-circle text-red-500"></i> Análise cancelada';
        statusEl.className = 'text-xs text-red-600 text-center';
    }

    showToast('Análise interrompida pelo usuário', 'warning');

    // Restaura status após 3 segundos
    setTimeout(() => {
        if (statusEl) {
            statusEl.innerHTML = '<i class="fas fa-info-circle text-gray-400"></i> Selecione um documento';
            statusEl.className = 'text-xs text-gray-600 text-center';
        }
    }, 3000);
}

function startAnalysisPolling(fileId) {
    // Limpa polling anterior se existir
    if (appState.pollingIntervals[fileId]) {
        clearInterval(appState.pollingIntervals[fileId]);
    }

    // Atualiza status visual
    const statusEl = document.getElementById('analysis-status');
    if (statusEl) {
        statusEl.innerHTML = '<i class="fas fa-spinner fa-spin text-blue-500"></i> Analisando...';
        statusEl.className = 'text-xs text-blue-600 text-center';
    }

    // Polling a cada 2 segundos
    appState.pollingIntervals[fileId] = setInterval(async () => {
        try {
            const status = await api(`/analisar/${fileId}/status`);
            console.log('[Polling] Status:', status);

            // Atualiza texto do modal
            const processingStatus = document.getElementById('processing-status');
            if (processingStatus) {
                processingStatus.textContent = 'Analisando com IA...';
            }

            if (!status.processing && status.has_result) {
                // Análise concluída
                clearInterval(appState.pollingIntervals[fileId]);
                delete appState.pollingIntervals[fileId];

                // Fecha modal de processamento
                closeProcessingModal();

                // Carrega resultado e atualiza UI
                try {
                    const resultado = await api(`/resultado/${fileId}`);
                    console.log('[Análise] Resultado:', resultado);

                    // Atualiza detalhes do documento
                    appState.documentDetails = resultado;
                    appState.currentAnaliseId = resultado.analise_id || null;

                    // Atualiza painel de dados extraídos
                    renderExtractedDataPanel();

                    // Atualiza lista de arquivos (marca como analisado)
                    await loadFiles();

                    // Atualiza tabela de análises
                    await loadAnalyses();

                    // Gera relatório automaticamente
                    await generateAndShowReport();

                    showToast('Análise concluída com sucesso!', 'success');
                    addLog('success', 'Análise concluída: ' + (resultado.matricula_principal || 'N/A'));

                    // Atualiza status
                    if (statusEl) {
                        statusEl.innerHTML = '<i class="fas fa-check-circle text-green-500"></i> Análise concluída';
                        statusEl.className = 'text-xs text-green-600 text-center';
                    }
                } catch (e) {
                    console.error('[Análise] Erro ao carregar resultado:', e);
                }

                await loadLogs();
            }
        } catch (error) {
            console.error('Erro no polling:', error);
        }
    }, 2000);

    // Timeout após 5 minutos
    setTimeout(() => {
        if (appState.pollingIntervals[fileId]) {
            clearInterval(appState.pollingIntervals[fileId]);
            delete appState.pollingIntervals[fileId];
            closeProcessingModal();
            showToast('Análise demorou muito. Verifique os logs.', 'warning');

            const statusEl = document.getElementById('analysis-status');
            if (statusEl) {
                statusEl.innerHTML = '<i class="fas fa-exclamation-triangle text-yellow-500"></i> Timeout na análise';
                statusEl.className = 'text-xs text-yellow-600 text-center mt-2';
            }
        }
    }, 300000);
}

/**
 * Generate and show report automatically
 */
async function generateAndShowReport() {
    const reportView = document.getElementById('report-view');
    const reportActions = document.getElementById('report-actions');

    if (!reportView) return;

    // Mostra loading
    reportView.innerHTML = `
        <div class="text-center text-gray-400 py-12">
            <i class="fas fa-spinner fa-spin text-4xl mb-4 text-primary-500"></i>
            <p class="text-lg">Gerando Relatório...</p>
            <p class="text-sm mt-2">Aguarde enquanto a IA processa os dados</p>
        </div>
    `;

    try {
        const result = await api('/relatorio/gerar', { method: 'POST' });

        if (result.success) {
            // Armazena para download
            window.currentReportText = result.report;
            window.currentReportPayload = result.payload;

            // Renderiza relatório no div com seção de feedback
            reportView.innerHTML = `
                <div class="prose prose-sm max-w-none">
                    ${renderMarkdown(result.report)}
                </div>
                
                <!-- Seção de Feedback Inline -->
                <div id="feedback-section-inline" class="mt-6 bg-gradient-to-r from-blue-50 to-indigo-50 rounded-xl border border-blue-200 p-4">
                    <h4 class="font-semibold text-gray-700 mb-3 flex items-center gap-2">
                        <i class="fas fa-comment-dots text-blue-500"></i>
                        Avalie a Análise da IA
                    </h4>
                    <p class="text-sm text-gray-600 mb-4">Sua avaliação nos ajuda a melhorar o sistema.</p>
                    
                    <div id="feedback-buttons-inline" class="grid grid-cols-2 md:grid-cols-4 gap-3">
                        <button onclick="enviarFeedbackMatricula('correto')" 
                            class="px-4 py-3 bg-green-100 text-green-700 rounded-lg hover:bg-green-200 transition-colors flex flex-col items-center gap-1 border-2 border-transparent hover:border-green-400">
                            <i class="fas fa-check-circle text-xl"></i>
                            <span class="text-sm font-medium">Correta</span>
                        </button>
                        <button onclick="enviarFeedbackMatricula('parcial')" 
                            class="px-4 py-3 bg-yellow-100 text-yellow-700 rounded-lg hover:bg-yellow-200 transition-colors flex flex-col items-center gap-1 border-2 border-transparent hover:border-yellow-400">
                            <i class="fas fa-adjust text-xl"></i>
                            <span class="text-sm font-medium">Parcialmente</span>
                        </button>
                        <button onclick="enviarFeedbackMatricula('incorreto')" 
                            class="px-4 py-3 bg-red-100 text-red-700 rounded-lg hover:bg-red-200 transition-colors flex flex-col items-center gap-1 border-2 border-transparent hover:border-red-400">
                            <i class="fas fa-times-circle text-xl"></i>
                            <span class="text-sm font-medium">Incorreta</span>
                        </button>
                        <button onclick="enviarFeedbackMatricula('erro_ia')" 
                            class="px-4 py-3 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors flex flex-col items-center gap-1 border-2 border-transparent hover:border-gray-400">
                            <i class="fas fa-exclamation-triangle text-xl"></i>
                            <span class="text-sm font-medium">Erro/Não gerou</span>
                        </button>
                    </div>
                    
                    <div id="feedback-enviado-inline" class="hidden text-center py-4">
                        <i class="fas fa-check-circle text-green-500 text-3xl mb-2"></i>
                        <p class="text-green-700 font-medium">Obrigado pelo seu feedback!</p>
                        <p id="feedback-enviado-tipo-inline" class="text-sm text-gray-500"></p>
                    </div>
                </div>
            `;

            // Mostra botões de ação
            if (reportActions) {
                reportActions.style.display = 'flex';
            }

            // Verifica se já tem feedback
            if (appState.currentAnaliseId) {
                verificarFeedbackInline(appState.currentAnaliseId);
            }
        } else {
            reportView.innerHTML = `
                <div class="text-center text-red-400 py-12">
                    <i class="fas fa-exclamation-circle text-4xl mb-4"></i>
                    <p class="text-lg">Erro ao gerar relatório</p>
                    <p class="text-sm mt-2">${result.error || 'Tente novamente'}</p>
                </div>
            `;
        }
    } catch (error) {
        reportView.innerHTML = `
            <div class="text-center text-red-400 py-12">
                <i class="fas fa-exclamation-circle text-4xl mb-4"></i>
                <p class="text-lg">Erro de conexão</p>
                <p class="text-sm mt-2">Não foi possível gerar o relatório</p>
            </div>
        `;
    }
}

/**
 * Show analysis result modal - REMOVED, now using inline report
 */
function showAnalysisResultModal(resultado) {
    // Não mostra mais modal, relatório é exibido inline
    console.log('[Análise] Resultado processado:', resultado.matricula_principal);
}

async function gerarRelatorio() {
    // Gera relatório inline em vez de modal
    await generateAndShowReport();
}

function showReportModal(reportText, payloadJson) {
    // Cria modal para exibir relatório
    const modal = document.createElement('div');
    modal.id = 'report-modal';
    modal.className = 'fixed inset-0 z-50 flex items-center justify-center bg-black/50';
    modal.innerHTML = `
        <div class="bg-white rounded-xl shadow-2xl max-w-4xl w-full max-h-[90vh] overflow-hidden flex flex-col m-4">
            <div class="flex items-center justify-between px-6 py-4 border-b border-gray-100 bg-gradient-to-r from-green-50 to-blue-50">
                <div>
                    <h2 class="text-lg font-semibold text-gray-800">Relatório Completo</h2>
                    <p class="text-sm text-gray-500">Análise de Matrículas Confrontantes</p>
                </div>
                <button onclick="closeReportModal()" class="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors">
                    <i class="fas fa-times"></i>
                </button>
            </div>
            <div class="flex-1 overflow-y-auto p-6" id="report-content-wrapper">
                <div class="prose max-w-none" id="report-content"></div>
                
                <!-- Seção de Feedback -->
                <div id="feedback-section-matriculas" class="mt-6 bg-gradient-to-r from-blue-50 to-indigo-50 rounded-xl border border-blue-200 p-4">
                    <h4 class="font-semibold text-gray-700 mb-3 flex items-center gap-2">
                        <i class="fas fa-comment-dots text-blue-500"></i>
                        Avalie a Análise da IA
                    </h4>
                    <p class="text-sm text-gray-600 mb-4">Sua avaliação nos ajuda a melhorar o sistema.</p>
                    
                    <div id="feedback-buttons-matriculas" class="grid grid-cols-2 md:grid-cols-4 gap-3">
                        <button onclick="enviarFeedbackMatricula('correto')" 
                            class="px-4 py-3 bg-green-100 text-green-700 rounded-lg hover:bg-green-200 transition-colors flex flex-col items-center gap-1 border-2 border-transparent hover:border-green-400">
                            <i class="fas fa-check-circle text-xl"></i>
                            <span class="text-sm font-medium">Correta</span>
                        </button>
                        <button onclick="enviarFeedbackMatricula('parcial')" 
                            class="px-4 py-3 bg-yellow-100 text-yellow-700 rounded-lg hover:bg-yellow-200 transition-colors flex flex-col items-center gap-1 border-2 border-transparent hover:border-yellow-400">
                            <i class="fas fa-adjust text-xl"></i>
                            <span class="text-sm font-medium">Parcialmente</span>
                        </button>
                        <button onclick="enviarFeedbackMatricula('incorreto')" 
                            class="px-4 py-3 bg-red-100 text-red-700 rounded-lg hover:bg-red-200 transition-colors flex flex-col items-center gap-1 border-2 border-transparent hover:border-red-400">
                            <i class="fas fa-times-circle text-xl"></i>
                            <span class="text-sm font-medium">Incorreta</span>
                        </button>
                        <button onclick="enviarFeedbackMatricula('erro_ia')" 
                            class="px-4 py-3 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors flex flex-col items-center gap-1 border-2 border-transparent hover:border-gray-400">
                            <i class="fas fa-exclamation-triangle text-xl"></i>
                            <span class="text-sm font-medium">Erro/Não gerou</span>
                        </button>
                    </div>
                    
                    <div id="feedback-enviado-matriculas" class="hidden text-center py-4">
                        <i class="fas fa-check-circle text-green-500 text-3xl mb-2"></i>
                        <p class="text-green-700 font-medium">Obrigado pelo seu feedback!</p>
                        <p id="feedback-enviado-tipo-matriculas" class="text-sm text-gray-500"></p>
                    </div>
                </div>
            </div>
            <div class="px-6 py-4 border-t border-gray-100 bg-gray-50 flex justify-between">
                <div class="flex gap-2">
                    <button onclick="downloadReportDocx()" class="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors flex items-center gap-2">
                        <i class="fas fa-file-word"></i> Baixar DOCX
                    </button>
                    <button onclick="printReportPdf()" class="px-4 py-2 text-sm bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors flex items-center gap-2">
                        <i class="fas fa-file-pdf"></i> Imprimir PDF
                    </button>
                    <button onclick="copyReport()" class="px-4 py-2 text-sm bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors flex items-center gap-2">
                        <i class="fas fa-copy"></i> Copiar
                    </button>
                </div>
                <div class="flex gap-2">
                    <button onclick="showPayload()" class="px-4 py-2 text-sm bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors flex items-center gap-2">
                        <i class="fas fa-code"></i> Ver JSON
                    </button>
                </div>
                <button onclick="closeReportModal()" class="px-4 py-2 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors">
                    Fechar
                </button>
            </div>
        </div>
    `;

    document.body.appendChild(modal);

    // Renderiza markdown como HTML
    const contentEl = document.getElementById('report-content');
    contentEl.innerHTML = renderMarkdown(reportText);

    // Armazena payload para uso posterior
    window.currentReportPayload = payloadJson;
    window.currentReportText = reportText;

    // Verifica se já tem feedback
    if (appState.currentAnaliseId) {
        verificarFeedbackMatriculaExistente(appState.currentAnaliseId);
    }
}

function closeReportModal() {
    const modal = document.getElementById('report-modal');
    if (modal) modal.remove();
}

function copyReport() {
    if (window.currentReportText) {
        navigator.clipboard.writeText(window.currentReportText);
        showToast('Relatório copiado!', 'success');
    }
}

async function downloadReportDocx(analiseId = null) {
    // Usa o ID passado, ou o ID da análise atual, ou nenhum (pega a última)
    const idToUse = analiseId || appState.currentAnaliseId;

    try {
        showToast('Gerando documento DOCX...', 'info');

        // Monta URL com parâmetro de análise se disponível
        let url = `${API_BASE}/relatorio/download`;
        if (idToUse) {
            url += `?analise_id=${idToUse}`;
        }

        // Chama o endpoint do backend que gera DOCX com template institucional
        const response = await fetch(url, {
            method: 'GET',
            headers: {
                'Authorization': `Bearer ${window.authToken}`
            }
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Erro desconhecido' }));
            throw new Error(error.detail || 'Erro ao gerar DOCX');
        }

        // Obtém o blob do arquivo
        const blob = await response.blob();

        // Extrai nome do arquivo do header Content-Disposition, se disponível
        const contentDisposition = response.headers.get('Content-Disposition');
        let filename = 'relatorio_matriculas_confrontantes.docx';
        if (contentDisposition) {
            const match = contentDisposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
            if (match && match[1]) {
                filename = match[1].replace(/['"]/g, '');
            }
        }

        // Cria link e dispara download
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(link.href);

        showToast('Download concluído!', 'success');
    } catch (error) {
        console.error('Erro ao baixar DOCX:', error);
        showToast(`Erro ao gerar DOCX: ${error.message}`, 'error');
    }
}

function printReportPdf() {
    if (!window.currentReportText) {
        showToast('Nenhum relatório para imprimir', 'warning');
        return;
    }

    // Cria janela de impressão
    const printWindow = window.open('', '_blank');
    printWindow.document.write(`
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Relatório de Análise - Matrículas Confrontantes</title>
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
                <h1>Relatório de Análise</h1>
                <p>Sistema de Matrículas Confrontantes</p>
                <p>Data: ${new Date().toLocaleDateString('pt-BR')}</p>
            </div>
            ${renderMarkdown(window.currentReportText)}
            <div class="footer">
                Documento gerado automaticamente pelo Sistema de Análise de Matrículas Confrontantes - PGE-MS
            </div>
        </body>
        </html>
    `);
    printWindow.document.close();

    // Espera carregar e imprime
    printWindow.onload = () => {
        printWindow.print();
    };

    showToast('Abrindo impressão...', 'info');
}

function showPayload() {
    if (window.currentReportPayload) {
        const payloadModal = document.createElement('div');
        payloadModal.id = 'payload-modal';
        payloadModal.className = 'fixed inset-0 z-[60] flex items-center justify-center bg-black/50';
        payloadModal.innerHTML = `
            <div class="bg-white rounded-xl shadow-2xl max-w-3xl w-full max-h-[80vh] overflow-hidden flex flex-col m-4">
                <div class="flex items-center justify-between px-6 py-4 border-b border-gray-100">
                    <h2 class="text-lg font-semibold text-gray-800">Dados Estruturados (JSON)</h2>
                    <button onclick="document.getElementById('payload-modal').remove()" class="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
                <div class="flex-1 overflow-y-auto p-6">
                    <pre class="text-xs bg-gray-50 p-4 rounded-lg overflow-x-auto">${window.currentReportPayload}</pre>
                </div>
            </div>
        `;
        document.body.appendChild(payloadModal);
    }
}

// ============================================
// Feedback Functions
// ============================================

async function enviarFeedbackMatricula(avaliacao) {
    if (!appState.currentAnaliseId) {
        showToast('Nenhuma análise para avaliar', 'warning');
        return;
    }

    // Pede comentário para feedback negativo
    let comentario = null;
    if (avaliacao === 'incorreto' || avaliacao === 'parcial') {
        comentario = prompt('Por favor, descreva brevemente o que estava incorreto (opcional):');
    }

    try {
        const result = await api('/feedback', {
            method: 'POST',
            body: JSON.stringify({
                analise_id: appState.currentAnaliseId,
                avaliacao: avaliacao,
                comentario: comentario
            })
        });

        if (result && result.success) {
            const tipoTexto = {
                'correto': 'Análise marcada como correta',
                'parcial': 'Análise marcada como parcialmente correta',
                'incorreto': 'Análise marcada como incorreta',
                'erro_ia': 'Reportado como erro da IA'
            };

            // Atualiza feedback no modal (se existir)
            const buttonsModal = document.getElementById('feedback-buttons-matriculas');
            const enviadoModal = document.getElementById('feedback-enviado-matriculas');
            if (buttonsModal) buttonsModal.classList.add('hidden');
            if (enviadoModal) enviadoModal.classList.remove('hidden');
            const tipoElModal = document.getElementById('feedback-enviado-tipo-matriculas');
            if (tipoElModal) tipoElModal.textContent = tipoTexto[avaliacao] || '';

            // Atualiza feedback inline (se existir)
            const buttonsInline = document.getElementById('feedback-buttons-inline');
            const enviadoInline = document.getElementById('feedback-enviado-inline');
            if (buttonsInline) buttonsInline.classList.add('hidden');
            if (enviadoInline) enviadoInline.classList.remove('hidden');
            const tipoElInline = document.getElementById('feedback-enviado-tipo-inline');
            if (tipoElInline) tipoElInline.textContent = tipoTexto[avaliacao] || '';

            showToast('Feedback registrado!', 'success');
        } else {
            showToast('Erro ao enviar feedback', 'error');
        }
    } catch (error) {
        showToast('Erro ao enviar feedback', 'error');
    }
}

async function verificarFeedbackMatriculaExistente(analiseId) {
    try {
        const result = await api(`/feedback/${analiseId}`);

        const buttons = document.getElementById('feedback-buttons-matriculas');
        const enviado = document.getElementById('feedback-enviado-matriculas');

        if (result && result.has_feedback) {
            // Já tem feedback, mostra o estado de enviado
            if (buttons) buttons.classList.add('hidden');
            if (enviado) enviado.classList.remove('hidden');

            const tipoTexto = {
                'correto': 'Análise marcada como correta',
                'parcial': 'Análise marcada como parcialmente correta',
                'incorreto': 'Análise marcada como incorreta',
                'erro_ia': 'Reportado como erro da IA'
            };
            const tipoEl = document.getElementById('feedback-enviado-tipo-matriculas');
            if (tipoEl) tipoEl.textContent = tipoTexto[result.avaliacao] || '';
        } else {
            // Não tem feedback, mostra botões
            if (buttons) buttons.classList.remove('hidden');
            if (enviado) enviado.classList.add('hidden');
        }
    } catch (error) {
        // Em caso de erro, mostra botões
        const buttons = document.getElementById('feedback-buttons-matriculas');
        const enviado = document.getElementById('feedback-enviado-matriculas');
        if (buttons) buttons.classList.remove('hidden');
        if (enviado) enviado.classList.add('hidden');
    }
}

async function verificarFeedbackInline(analiseId) {
    try {
        const result = await api(`/feedback/${analiseId}`);

        const buttons = document.getElementById('feedback-buttons-inline');
        const enviado = document.getElementById('feedback-enviado-inline');

        if (result && result.has_feedback) {
            // Já tem feedback, mostra o estado de enviado
            if (buttons) buttons.classList.add('hidden');
            if (enviado) enviado.classList.remove('hidden');

            const tipoTexto = {
                'correto': 'Análise marcada como correta',
                'parcial': 'Análise marcada como parcialmente correta',
                'incorreto': 'Análise marcada como incorreta',
                'erro_ia': 'Reportado como erro da IA'
            };
            const tipoEl = document.getElementById('feedback-enviado-tipo-inline');
            if (tipoEl) tipoEl.textContent = tipoTexto[result.avaliacao] || '';
        } else {
            // Não tem feedback, mostra botões
            if (buttons) buttons.classList.remove('hidden');
            if (enviado) enviado.classList.add('hidden');
        }
    } catch (error) {
        // Em caso de erro, mostra botões
        const buttons = document.getElementById('feedback-buttons-inline');
        const enviado = document.getElementById('feedback-enviado-inline');
        if (buttons) buttons.classList.remove('hidden');
        if (enviado) enviado.classList.add('hidden');
    }
}

function renderMarkdown(text) {
    // Renderização simples de markdown para HTML
    return text
        .replace(/^### (.*$)/gim, '<h3 class="text-lg font-semibold mt-4 mb-2">$1</h3>')
        .replace(/^## (.*$)/gim, '<h2 class="text-xl font-bold mt-6 mb-3 text-primary-700">$1</h2>')
        .replace(/^# (.*$)/gim, '<h1 class="text-2xl font-bold mt-6 mb-4 text-primary-800">$1</h1>')
        .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
        .replace(/\*([^*]+)\*/g, '<em>$1</em>')
        .replace(/^- (.*$)/gim, '<li class="ml-4">$1</li>')
        .replace(/^• (.*$)/gim, '<li class="ml-4">$1</li>')
        .replace(/\n/gim, '<br>');
}

async function setApiKey() {
    // Configurações de API movidas para o painel admin
    showToast('Configurações de API devem ser feitas pelo administrador', 'info');
}

// ============================================
// Render Functions
// ============================================

/**
 * Render file list in left panel
 */
function renderFileList() {
    const container = document.getElementById('file-list');
    const files = appState.files;

    if (!files || files.length === 0) {
        container.innerHTML = `
            <div class="text-center py-8 text-gray-400">
                <i class="fas fa-folder-open text-4xl mb-2"></i>
                <p class="text-sm">Nenhum arquivo importado</p>
                <p class="text-xs mt-1">Clique em "Importar Documentos"</p>
            </div>
        `;
        return;
    }

    container.innerHTML = files.map(file => {
        const isSelected = appState.selectedFileIds.includes(String(file.id));
        const isMultiSelect = appState.selectedFileIds.length > 1;
        return `
        <div class="file-item group p-3 rounded-lg cursor-pointer transition-all ${isSelected ? (isMultiSelect ? 'bg-purple-50 border border-purple-200' : 'bg-primary-50 border border-primary-200') : 'hover:bg-gray-50 border border-transparent'}" 
             onclick="selectFile('${file.id}', event)">
            <div class="flex items-start gap-3">
                <div class="flex-shrink-0 w-10 h-10 rounded-lg ${file.type === 'pdf' ? 'bg-red-100' : 'bg-blue-100'} flex items-center justify-center relative">
                    <i class="fas ${file.type === 'pdf' ? 'fa-file-pdf text-red-500' : 'fa-image text-blue-500'}"></i>
                    ${file.analyzed ? '<span class="absolute -top-1 -right-1 w-4 h-4 bg-green-500 rounded-full flex items-center justify-center"><i class="fas fa-check text-white text-xs"></i></span>' : ''}
                    ${isSelected && isMultiSelect ? '<span class="absolute -bottom-1 -left-1 w-5 h-5 bg-purple-500 rounded-full flex items-center justify-center text-white text-xs font-bold">' + (appState.selectedFileIds.indexOf(String(file.id)) + 1) + '</span>' : ''}
                </div>
                <div class="flex-1 min-w-0">
                    <p class="text-sm font-medium text-gray-800 truncate">${file.name}</p>
                    <p class="text-xs text-gray-500">${file.size} • ${file.date}</p>
                    ${file.analyzed ? '<span class="text-xs text-green-600"><i class="fas fa-check-circle"></i> Analisado</span>' : ''}
                </div>
                <div class="flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button class="p-1 text-gray-400 hover:text-red-500 transition-colors" onclick="event.stopPropagation(); deleteFile('${file.id}')" title="Excluir">
                        <i class="fas fa-trash-alt text-xs"></i>
                    </button>
                </div>
            </div>
        </div>
    `}).join('');
}

/**
 * Render folder tree
 */
function renderFolderTree() {
    const container = document.getElementById('folder-tree');
    const folders = appState.folders.length > 0 ? appState.folders : [
        {
            name: 'Documentos',
            icon: 'folder',
            expanded: true,
            children: [
                { name: 'Matrículas', icon: 'folder', children: [] },
                { name: 'Certidões', icon: 'folder', children: [] },
                { name: 'Laudos', icon: 'folder', children: [] },
            ]
        },
        { name: 'Lixeira', icon: 'trash', children: [] }
    ];

    function renderFolder(folder, level = 0) {
        const hasChildren = folder.children && folder.children.length > 0;
        const paddingLeft = level * 12;

        let html = `
            <div class="folder-item">
                <div class="flex items-center gap-2 py-1.5 px-2 rounded hover:bg-gray-100 cursor-pointer transition-colors" style="padding-left: ${paddingLeft}px">
                    ${hasChildren ? `<i class="fas fa-chevron-${folder.expanded ? 'down' : 'right'} text-xs text-gray-400 w-3"></i>` : '<span class="w-3"></span>'}
                    <i class="fas fa-${folder.icon === 'trash' ? 'trash' : 'folder'} ${folder.icon === 'trash' ? 'text-gray-400' : 'text-yellow-500'} text-sm"></i>
                    <span class="text-gray-700">${folder.name}</span>
                </div>
        `;

        if (hasChildren && folder.expanded) {
            html += `<div class="tree-line">`;
            folder.children.forEach(child => {
                html += renderFolder(child, level + 1);
            });
            html += `</div>`;
        }

        html += `</div>`;
        return html;
    }

    container.innerHTML = folders.map(folder => renderFolder(folder)).join('');
}

/**
 * Render extracted data panel (replaces old records table)
 */
function renderExtractedDataPanel() {
    const container = document.getElementById('extracted-data-panel');
    if (!container) return;

    const data = appState.documentDetails;

    if (!data || !data.matriculas_encontradas) {
        container.innerHTML = `
            <div class="text-center text-gray-400 py-8">
                <i class="fas fa-file-alt text-3xl mb-2"></i>
                <p class="text-sm">Selecione e analise um documento para ver os dados extraídos</p>
            </div>
        `;
        return;
    }

    // Renderiza matrículas encontradas
    const matriculasHtml = (data.matriculas_encontradas || []).map(mat => `
        <tr class="border-b border-gray-100 hover:bg-gray-50 text-xs">
            <td class="px-2 py-1.5 font-medium text-primary-600">${mat.numero || 'N/A'}</td>
            <td class="px-2 py-1.5">${mat.lote || '-'}</td>
            <td class="px-2 py-1.5">${mat.quadra || '-'}</td>
            <td class="px-2 py-1.5 truncate max-w-[150px]" title="${(mat.proprietarios || []).join(', ')}">${(mat.proprietarios || []).join(', ') || 'N/A'}</td>
        </tr>
    `).join('') || '<tr><td colspan="4" class="px-2 py-3 text-center text-gray-400 text-xs">Nenhuma matrícula</td></tr>';

    // Renderiza lotes confrontantes
    const lotesHtml = (data.lotes_confrontantes || []).map(lote => `
        <tr class="border-b border-gray-100 hover:bg-gray-50 text-xs">
            <td class="px-2 py-1.5">${lote.identificador || 'N/A'}</td>
            <td class="px-2 py-1.5">${lote.direcao ? lote.direcao.toUpperCase() : '-'}</td>
            <td class="px-2 py-1.5">${lote.tipo || '-'}</td>
            <td class="px-2 py-1.5">${lote.matricula_anexada || '-'}</td>
        </tr>
    `).join('') || '<tr><td colspan="4" class="px-2 py-3 text-center text-gray-400 text-xs">Nenhum confrontante</td></tr>';

    const confidence = data.confidence ? Math.round(data.confidence <= 1 ? data.confidence * 100 : data.confidence) : 0;
    const confColor = confidence >= 80 ? 'text-green-600' : confidence >= 60 ? 'text-yellow-600' : 'text-red-600';
    const confBg = confidence >= 80 ? 'bg-green-500' : confidence >= 60 ? 'bg-yellow-500' : 'bg-red-500';

    container.innerHTML = `
        <div class="space-y-3">
            <!-- Resumo compacto -->
            <div class="flex items-center gap-4 text-xs">
                <div class="flex items-center gap-2">
                    <span class="text-gray-500">Matrícula:</span>
                    <span class="font-semibold text-primary-700">${data.matricula_principal || 'N/A'}</span>
                </div>
                <div class="flex items-center gap-2">
                    <span class="text-gray-500">Confiança:</span>
                    <div class="flex items-center gap-1">
                        <div class="w-12 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                            <div class="h-full ${confBg} rounded-full" style="width: ${confidence}%"></div>
                        </div>
                        <span class="${confColor} font-medium">${confidence}%</span>
                    </div>
                </div>
                <div class="flex items-center gap-2">
                    <span class="text-gray-500">Confrontação:</span>
                    <span class="font-medium ${data.confrontacao_completa ? 'text-green-600' : data.confrontacao_completa === false ? 'text-red-600' : 'text-gray-400'}">
                        ${data.confrontacao_completa === true ? '✓ Completa' : data.confrontacao_completa === false ? '✗ Incompleta' : 'N/A'}
                    </span>
                </div>
            </div>
            
            <!-- Tabelas lado a lado -->
            <div class="grid grid-cols-2 gap-3">
                <!-- Matrículas -->
                <div class="bg-gray-50 rounded-lg overflow-hidden">
                    <div class="px-2 py-1.5 bg-gray-100 border-b border-gray-200">
                        <h4 class="font-medium text-gray-700 text-xs flex items-center gap-1">
                            <i class="fas fa-file-alt text-primary-500"></i>
                            Matrículas (${(data.matriculas_encontradas || []).length})
                        </h4>
                    </div>
                    <div class="max-h-32 overflow-auto">
                        <table class="w-full">
                            <thead class="bg-gray-100 text-gray-600 text-xs sticky top-0">
                                <tr>
                                    <th class="px-2 py-1 text-left font-medium">Nº</th>
                                    <th class="px-2 py-1 text-left font-medium">Lote</th>
                                    <th class="px-2 py-1 text-left font-medium">Quadra</th>
                                    <th class="px-2 py-1 text-left font-medium">Proprietários</th>
                                </tr>
                            </thead>
                            <tbody>${matriculasHtml}</tbody>
                        </table>
                    </div>
                </div>
                
                <!-- Confrontantes -->
                <div class="bg-gray-50 rounded-lg overflow-hidden">
                    <div class="px-2 py-1.5 bg-gray-100 border-b border-gray-200">
                        <h4 class="font-medium text-gray-700 text-xs flex items-center gap-1">
                            <i class="fas fa-map-marked-alt text-green-500"></i>
                            Confrontantes (${(data.lotes_confrontantes || []).length})
                        </h4>
                    </div>
                    <div class="max-h-32 overflow-auto">
                        <table class="w-full">
                            <thead class="bg-gray-100 text-gray-600 text-xs sticky top-0">
                                <tr>
                                    <th class="px-2 py-1 text-left font-medium">Identificador</th>
                                    <th class="px-2 py-1 text-left font-medium">Direção</th>
                                    <th class="px-2 py-1 text-left font-medium">Tipo</th>
                                    <th class="px-2 py-1 text-left font-medium">Matrícula</th>
                                </tr>
                            </thead>
                            <tbody>${lotesHtml}</tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    `;
}

// Mantém função antiga como alias para compatibilidade
function renderRecordsTable() {
    renderExtractedDataPanel();
}

function getConfiancaBarSmall(value) {
    let color = 'bg-green-500';
    if (value < 80) color = 'bg-yellow-500';
    if (value < 60) color = 'bg-red-500';
    return `
        <div class="flex items-center gap-1">
            <div class="w-10 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                <div class="h-full ${color} rounded-full" style="width: ${value}%"></div>
            </div>
            <span class="text-xs text-gray-500">${value}%</span>
        </div>
    `;
}

/**
 * Render PDF thumbnails
 */
function renderPdfThumbnails() {
    const container = document.getElementById('pdf-thumbnails');
    const pages = [1, 2, 3, 4, 5];

    container.innerHTML = pages.map((page, index) => `
        <div class="thumbnail cursor-pointer rounded overflow-hidden border-2 ${index === 0 ? 'border-primary-500' : 'border-transparent hover:border-gray-400'} transition-colors">
            <div class="bg-white aspect-[8.5/11] flex items-center justify-center">
                <span class="text-xs text-gray-400">${page}</span>
            </div>
        </div>
    `).join('');
}

/**
 * Render document details panel - simplified, not used anymore
 */
function renderDocumentDetails(result = null) {
    // Função mantida para compatibilidade mas não é mais usada
    // Relatório é gerado automaticamente no campo report-view
}

/**
 * Render system logs
 */
function renderSystemLogs() {
    const container = document.getElementById('system-logs');
    if (!container) return; // Painel de logs foi removido da UI

    const logs = appState.logs || [];

    if (logs.length === 0) {
        container.innerHTML = '<div class="text-gray-500 py-2">Nenhum log registrado</div>';
        return;
    }

    const statusIcons = {
        'success': '<span class="w-2 h-2 rounded-full bg-green-500 inline-block"></span>',
        'info': '<span class="w-2 h-2 rounded-full bg-blue-500 inline-block"></span>',
        'warning': '<span class="w-2 h-2 rounded-full bg-yellow-500 inline-block"></span>',
        'error': '<span class="w-2 h-2 rounded-full bg-red-500 inline-block"></span>'
    };

    const statusColors = {
        'success': 'text-green-400',
        'info': 'text-blue-400',
        'warning': 'text-yellow-400',
        'error': 'text-red-400'
    };

    container.innerHTML = logs.map(log => `
        <div class="log-entry flex items-start gap-3 py-1 ${statusColors[log.status] || 'text-gray-400'}">
            <span class="text-gray-500 flex-shrink-0">[${log.time}]</span>
            ${statusIcons[log.status] || statusIcons.info}
            <span class="${log.status === 'error' ? 'text-red-400' : 'text-gray-300'}">${log.message}</span>
        </div>
    `).join('');
}

// ============================================
// Event Handlers
// ============================================

/**
 * Select a file (supports multi-select with Ctrl+Click)
 */
async function selectFile(id, event) {
    // Garante que id seja string para comparação consistente
    const fileId = String(id);

    // Verifica se é seleção múltipla (Ctrl+Click)
    if (event && event.ctrlKey) {
        const index = appState.selectedFileIds.indexOf(fileId);
        if (index === -1) {
            // Adiciona à seleção
            appState.selectedFileIds.push(fileId);
        } else {
            // Remove da seleção
            appState.selectedFileIds.splice(index, 1);
        }
        // Atualiza selectedFileId para o último selecionado
        if (appState.selectedFileIds.length > 0) {
            appState.selectedFileId = appState.selectedFileIds[appState.selectedFileIds.length - 1];
        } else {
            appState.selectedFileId = null;
        }
    } else {
        // Seleção simples - limpa múltipla seleção
        appState.selectedFileIds = [fileId];
        appState.selectedFileId = fileId;
    }

    // Atualiza estado de seleção nos arquivos
    appState.files.forEach(file => {
        file.selected = appState.selectedFileIds.includes(String(file.id));
    });

    renderFileList();
    updateBatchAnalyzeButton();

    // Carrega detalhes apenas do último arquivo selecionado
    if (appState.selectedFileId) {
        await loadDocumentDetails(appState.selectedFileId);
    }

    updateAnalysisStatus();

    if (appState.selectedFileIds.length > 1) {
        addLog('info', `${appState.selectedFileIds.length} arquivos selecionados para análise em lote`);
    } else {
        addLog('info', `Arquivo selecionado: ${appState.files.find(f => String(f.id) === fileId)?.name || fileId}`);
    }
}

/**
 * Update batch analyze button state
 */
function updateBatchAnalyzeButton() {
    const batchBtn = document.getElementById('btn-analyze-batch');
    if (batchBtn) {
        if (appState.selectedFileIds.length >= 2) {
            batchBtn.disabled = false;
            batchBtn.innerHTML = `<i class="fas fa-layer-group"></i> Analisar ${appState.selectedFileIds.length} arquivos`;
        } else {
            batchBtn.disabled = true;
            batchBtn.innerHTML = `<i class="fas fa-layer-group"></i> Análise em Lote`;
        }
    }
}

/**
 * Analyze multiple documents together
 */
async function analisarEmLote(fileIds) {
    if (!fileIds || fileIds.length < 2) {
        showToast('Selecione pelo menos 2 documentos', 'warning');
        return;
    }

    // Validação da Matrícula Principal
    const matriculaInput = document.getElementById('matricula-principal-input');
    const matriculaPrincipal = matriculaInput ? matriculaInput.value.trim() : '';

    if (!matriculaPrincipal) {
        showToast('Por favor, informe a Matrícula Principal', 'warning');
        if (matriculaInput) matriculaInput.focus();
        return;
    }

    try {
        showToast(`Iniciando análise de ${fileIds.length} documentos...`, 'info');
        addLog('info', `Iniciando análise em lote de ${fileIds.length} documentos`);

        const result = await api('/analisar-lote', {
            method: 'POST',
            body: JSON.stringify({
                file_ids: fileIds,
                nome_grupo: `Análise de ${fileIds.length} matrículas`,
                matricula_principal: matriculaPrincipal
            })
        });

        if (result?.success) {
            appState.currentGrupoId = result.grupo_id;
            showToast('Análise em lote iniciada!', 'success');

            // Inicia polling do status do grupo
            startBatchPolling(result.grupo_id);
        } else {
            showToast(result?.detail || 'Erro ao iniciar análise em lote', 'error');
        }
    } catch (error) {
        console.error('Erro na análise em lote:', error);
        showToast('Erro ao iniciar análise em lote', 'error');
    }
}

/**
 * Poll batch analysis status
 */
function startBatchPolling(grupoId) {
    const statusEl = document.getElementById('analysis-status');

    const pollInterval = setInterval(async () => {
        try {
            const status = await api(`/grupo/${grupoId}/status`);

            if (status.status === 'concluido') {
                clearInterval(pollInterval);
                showToast('Análise em lote concluída!', 'success');
                addLog('success', `Análise em lote concluída: ${status.total_arquivos} arquivos`);

                if (statusEl) {
                    statusEl.innerHTML = '<i class="fas fa-check-circle text-green-500"></i> Análise em lote concluída';
                }

                // Carrega resultado do grupo
                const resultado = await api(`/grupo/${grupoId}/resultado`);
                appState.documentDetails = resultado;
                appState.currentAnaliseId = resultado.analise_id || null;

                // Atualiza painel de dados extraídos
                renderExtractedDataPanel();

                // Gera relatório
                await generateAndShowReport();

                // Recarrega lista de arquivos
                await loadFiles();
                await loadAnalyses();

            } else if (status.status === 'erro') {
                clearInterval(pollInterval);
                showToast('Erro na análise em lote', 'error');
                addLog('error', 'Erro na análise em lote');

                if (statusEl) {
                    statusEl.innerHTML = '<i class="fas fa-exclamation-circle text-red-500"></i> Erro na análise';
                }

            } else {
                // Ainda processando
                if (statusEl) {
                    statusEl.innerHTML = '<i class="fas fa-spinner fa-spin text-purple-500"></i> Analisando ' + status.total_arquivos + ' arquivos...';
                }
            }
        } catch (error) {
            console.error('Erro ao verificar status do lote:', error);
        }
    }, 3000); // Poll a cada 3 segundos

    // Guarda referência para poder cancelar
    appState.pollingIntervals['batch_' + grupoId] = pollInterval;
}

/**
 * Delete a file
 */
async function deleteFile(id) {
    const fileId = String(id);
    const file = appState.files.find(f => String(f.id) === fileId);
    if (file && confirm(`Deseja excluir o arquivo "${file.name}"?`)) {
        await apiDeleteFile(fileId);
    }
}

/**
 * View analysis details from table
 */
async function viewAnalysis(id) {
    try {
        const result = await api(`/resultado/${id}`);
        appState.documentDetails = result;
        appState.currentAnaliseId = result.analise_id || null;

        // Gera relatório automaticamente para esta análise
        await generateAndShowReport();

        showToast('Análise carregada', 'info');
    } catch (error) {
        showToast('Erro ao carregar análise', 'error');
    }
}

function showResultModal(result) {
    const modal = document.createElement('div');
    modal.id = 'result-modal';
    modal.className = 'fixed inset-0 z-50 flex items-center justify-center bg-black/50';
    modal.innerHTML = `
        <div class="bg-white rounded-xl shadow-2xl max-w-4xl w-full max-h-[90vh] overflow-hidden flex flex-col m-4">
            <div class="flex items-center justify-between px-6 py-4 border-b border-gray-100">
                <h2 class="text-lg font-semibold text-gray-800">Detalhes da Análise - Matrícula ${result.matricula_principal || 'N/A'}</h2>
                <button onclick="document.getElementById('result-modal').remove()" class="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors">
                    <i class="fas fa-times"></i>
                </button>
            </div>
            <div class="flex-1 overflow-y-auto p-6">
                <div class="space-y-4">
                    <div class="bg-gray-50 p-4 rounded-lg">
                        <h3 class="font-semibold text-gray-800 mb-2">Resumo</h3>
                        <p class="text-sm text-gray-600">${result.reasoning || 'Sem resumo disponível'}</p>
                    </div>
                    
                    <div class="grid grid-cols-2 gap-4">
                        <div class="bg-primary-50 p-4 rounded-lg">
                            <p class="text-sm text-gray-600">Confiança</p>
                            <p class="text-2xl font-bold text-primary-700">${result.confidence ? Math.round(result.confidence <= 1 ? result.confidence * 100 : result.confidence) : 0}%</p>
                        </div>
                        <div class="bg-green-50 p-4 rounded-lg">
                            <p class="text-sm text-gray-600">Confrontantes</p>
                            <p class="text-2xl font-bold text-green-700">${result.lotes_confrontantes?.length || 0}</p>
                        </div>
                    </div>
                    
                    <div class="bg-gray-50 p-4 rounded-lg">
                        <h3 class="font-semibold text-gray-800 mb-2">Matrículas Encontradas</h3>
                        <div class="space-y-2">
                            ${(result.matriculas_encontradas || []).map(mat => `
                                <div class="bg-white p-3 rounded border border-gray-200">
                                    <p class="font-medium text-primary-600">Matrícula ${mat.numero}</p>
                                    <p class="text-sm text-gray-600">Proprietários: ${(mat.proprietarios || []).join(', ') || 'N/A'}</p>
                                    ${mat.lote ? `<p class="text-sm text-gray-500">Lote ${mat.lote}${mat.quadra ? `, Quadra ${mat.quadra}` : ''}</p>` : ''}
                                </div>
                            `).join('')}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
}

/**
 * Show raw extracted data in a modal with tables
 */
function showRawDataModal() {
    const data = appState.documentDetails;
    if (!data) {
        showToast('Nenhum dado disponível', 'warning');
        return;
    }

    const modal = document.createElement('div');
    modal.id = 'raw-data-modal';
    modal.className = 'fixed inset-0 z-50 flex items-center justify-center bg-black/50';

    // Renderiza matrículas encontradas
    const matriculasHtml = (data.matriculas_encontradas || []).map(mat => `
        <tr class="border-b border-gray-100 hover:bg-gray-50">
            <td class="px-3 py-2 font-medium text-primary-600">${mat.numero || 'N/A'}</td>
            <td class="px-3 py-2">${mat.lote || 'N/A'}</td>
            <td class="px-3 py-2">${mat.quadra || 'N/A'}</td>
            <td class="px-3 py-2">${(mat.proprietarios || []).join(', ') || 'N/A'}</td>
            <td class="px-3 py-2 text-xs text-gray-500 max-w-xs truncate" title="${mat.descricao || ''}">${mat.descricao || 'N/A'}</td>
        </tr>
    `).join('') || '<tr><td colspan="5" class="px-3 py-4 text-center text-gray-400">Nenhuma matrícula encontrada</td></tr>';

    // Renderiza lotes confrontantes
    const lotesHtml = (data.lotes_confrontantes || []).map(lote => `
        <tr class="border-b border-gray-100 hover:bg-gray-50">
            <td class="px-3 py-2">${lote.identificador || 'N/A'}</td>
            <td class="px-3 py-2">${lote.direcao ? lote.direcao.toUpperCase() : 'N/A'}</td>
            <td class="px-3 py-2">${lote.tipo || 'N/A'}</td>
            <td class="px-3 py-2">${lote.matricula_anexada || 'N/A'}</td>
            <td class="px-3 py-2">${(lote.proprietarios || []).join(', ') || 'N/A'}</td>
        </tr>
    `).join('') || '<tr><td colspan="5" class="px-3 py-4 text-center text-gray-400">Nenhum lote confrontante</td></tr>';

    // Renderiza proprietários identificados
    const proprietariosHtml = Object.entries(data.proprietarios_identificados || {}).map(([matricula, props]) => `
        <tr class="border-b border-gray-100 hover:bg-gray-50">
            <td class="px-3 py-2 font-medium text-primary-600">${matricula}</td>
            <td class="px-3 py-2">${(props || []).join(', ') || 'N/A'}</td>
        </tr>
    `).join('') || '<tr><td colspan="2" class="px-3 py-4 text-center text-gray-400">Nenhum proprietário identificado</td></tr>';

    // Renderiza matrículas confrontantes
    const matConfrontantesHtml = (data.matriculas_confrontantes || []).length > 0
        ? data.matriculas_confrontantes.map(m => `<span class="inline-block bg-green-100 text-green-700 px-2 py-1 rounded text-xs mr-1 mb-1">${m}</span>`).join('')
        : '<span class="text-gray-400">Nenhuma</span>';

    // Renderiza matrículas não confrontantes
    const matNaoConfrontantesHtml = (data.matriculas_nao_confrontantes || []).length > 0
        ? data.matriculas_nao_confrontantes.map(m => `<span class="inline-block bg-red-100 text-red-700 px-2 py-1 rounded text-xs mr-1 mb-1">${m}</span>`).join('')
        : '<span class="text-gray-400">Nenhuma</span>';

    // Renderiza lotes sem matrícula
    const lotesSemMatHtml = (data.lotes_sem_matricula || []).length > 0
        ? data.lotes_sem_matricula.map(l => `<span class="inline-block bg-yellow-100 text-yellow-700 px-2 py-1 rounded text-xs mr-1 mb-1">${l}</span>`).join('')
        : '<span class="text-gray-400">Nenhum</span>';

    modal.innerHTML = `
        <div class="bg-white rounded-xl shadow-2xl max-w-6xl w-full max-h-[90vh] overflow-hidden flex flex-col m-4">
            <div class="flex items-center justify-between px-6 py-4 border-b border-gray-100 bg-purple-50">
                <h2 class="text-lg font-semibold text-gray-800 flex items-center gap-2">
                    <i class="fas fa-table text-purple-500"></i>
                    Dados Brutos Extraídos - Matrícula ${data.matricula_principal || 'N/A'}
                </h2>
                <button onclick="document.getElementById('raw-data-modal').remove()" class="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors">
                    <i class="fas fa-times"></i>
                </button>
            </div>
            <div class="flex-1 overflow-y-auto p-6 space-y-6">
                <!-- Resumo -->
                <div class="grid grid-cols-4 gap-4">
                    <div class="bg-primary-50 p-4 rounded-lg text-center">
                        <p class="text-xs text-gray-600">Confiança</p>
                        <p class="text-2xl font-bold text-primary-700">${data.confidence ? Math.round(data.confidence <= 1 ? data.confidence * 100 : data.confidence) : 0}%</p>
                    </div>
                    <div class="bg-green-50 p-4 rounded-lg text-center">
                        <p class="text-xs text-gray-600">Matrículas</p>
                        <p class="text-2xl font-bold text-green-700">${(data.matriculas_encontradas || []).length}</p>
                    </div>
                    <div class="bg-blue-50 p-4 rounded-lg text-center">
                        <p class="text-xs text-gray-600">Confrontantes</p>
                        <p class="text-2xl font-bold text-blue-700">${(data.lotes_confrontantes || []).length}</p>
                    </div>
                    <div class="bg-purple-50 p-4 rounded-lg text-center">
                        <p class="text-xs text-gray-600">Confrontação</p>
                        <p class="text-lg font-bold ${data.confrontacao_completa ? 'text-green-600' : data.confrontacao_completa === false ? 'text-red-600' : 'text-gray-400'}">
                            ${data.confrontacao_completa === true ? 'Completa' : data.confrontacao_completa === false ? 'Incompleta' : 'N/A'}
                        </p>
                    </div>
                </div>

                <!-- Matrículas Encontradas -->
                <div class="bg-gray-50 rounded-lg overflow-hidden">
                    <div class="px-4 py-3 bg-gray-100 border-b border-gray-200">
                        <h3 class="font-semibold text-gray-800 flex items-center gap-2">
                            <i class="fas fa-file-alt text-primary-500"></i>
                            Matrículas Encontradas
                        </h3>
                    </div>
                    <div class="overflow-x-auto">
                        <table class="w-full text-sm">
                            <thead class="bg-gray-100 text-gray-600">
                                <tr>
                                    <th class="px-3 py-2 text-left font-medium">Número</th>
                                    <th class="px-3 py-2 text-left font-medium">Lote</th>
                                    <th class="px-3 py-2 text-left font-medium">Quadra</th>
                                    <th class="px-3 py-2 text-left font-medium">Proprietários</th>
                                    <th class="px-3 py-2 text-left font-medium">Descrição</th>
                                </tr>
                            </thead>
                            <tbody>${matriculasHtml}</tbody>
                        </table>
                    </div>
                </div>

                <!-- Lotes Confrontantes -->
                <div class="bg-gray-50 rounded-lg overflow-hidden">
                    <div class="px-4 py-3 bg-gray-100 border-b border-gray-200">
                        <h3 class="font-semibold text-gray-800 flex items-center gap-2">
                            <i class="fas fa-map-marked-alt text-green-500"></i>
                            Lotes Confrontantes
                        </h3>
                    </div>
                    <div class="overflow-x-auto">
                        <table class="w-full text-sm">
                            <thead class="bg-gray-100 text-gray-600">
                                <tr>
                                    <th class="px-3 py-2 text-left font-medium">Identificador</th>
                                    <th class="px-3 py-2 text-left font-medium">Direção</th>
                                    <th class="px-3 py-2 text-left font-medium">Tipo</th>
                                    <th class="px-3 py-2 text-left font-medium">Matrícula</th>
                                    <th class="px-3 py-2 text-left font-medium">Proprietários</th>
                                </tr>
                            </thead>
                            <tbody>${lotesHtml}</tbody>
                        </table>
                    </div>
                </div>

                <!-- Proprietários Identificados -->
                <div class="bg-gray-50 rounded-lg overflow-hidden">
                    <div class="px-4 py-3 bg-gray-100 border-b border-gray-200">
                        <h3 class="font-semibold text-gray-800 flex items-center gap-2">
                            <i class="fas fa-users text-blue-500"></i>
                            Proprietários por Matrícula
                        </h3>
                    </div>
                    <div class="overflow-x-auto">
                        <table class="w-full text-sm">
                            <thead class="bg-gray-100 text-gray-600">
                                <tr>
                                    <th class="px-3 py-2 text-left font-medium">Matrícula</th>
                                    <th class="px-3 py-2 text-left font-medium">Proprietários</th>
                                </tr>
                            </thead>
                            <tbody>${proprietariosHtml}</tbody>
                        </table>
                    </div>
                </div>

                <!-- Classificações -->
                <div class="grid grid-cols-3 gap-4">
                    <div class="bg-gray-50 rounded-lg p-4">
                        <h4 class="font-medium text-gray-800 mb-2 flex items-center gap-2">
                            <i class="fas fa-check-circle text-green-500"></i>
                            Matrículas Confrontantes
                        </h4>
                        <div class="flex flex-wrap">${matConfrontantesHtml}</div>
                    </div>
                    <div class="bg-gray-50 rounded-lg p-4">
                        <h4 class="font-medium text-gray-800 mb-2 flex items-center gap-2">
                            <i class="fas fa-times-circle text-red-500"></i>
                            Não Confrontantes
                        </h4>
                        <div class="flex flex-wrap">${matNaoConfrontantesHtml}</div>
                    </div>
                    <div class="bg-gray-50 rounded-lg p-4">
                        <h4 class="font-medium text-gray-800 mb-2 flex items-center gap-2">
                            <i class="fas fa-question-circle text-yellow-500"></i>
                            Lotes sem Matrícula
                        </h4>
                        <div class="flex flex-wrap">${lotesSemMatHtml}</div>
                    </div>
                </div>

                <!-- Reasoning -->
                ${data.reasoning ? `
                <div class="bg-blue-50 rounded-lg p-4">
                    <h4 class="font-medium text-gray-800 mb-2 flex items-center gap-2">
                        <i class="fas fa-brain text-blue-500"></i>
                        Raciocínio da IA
                    </h4>
                    <p class="text-sm text-gray-600">${data.reasoning}</p>
                </div>
                ` : ''}
            </div>
            <div class="px-6 py-4 border-t border-gray-100 bg-gray-50 flex justify-end">
                <button onclick="document.getElementById('raw-data-modal').remove()" class="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 transition-colors">
                    Fechar
                </button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
}

function editRecord(id) {
    showToast('Função de edição em desenvolvimento', 'info');
}

async function deleteRecord(id) {
    if (confirm('Deseja excluir este registro?')) {
        await apiDeleteRecord(id);
    }
}

/**
 * Add a new log entry (local)
 */
function addLog(status, message) {
    const now = new Date();
    const time = now.toTimeString().split(' ')[0];
    appState.logs.unshift({ time, status, message });
    if (appState.logs.length > 50) appState.logs.pop();
    renderSystemLogs();
}

/**
 * Toggle logs visibility
 */
function setupLogToggle() {
    const toggleBtn = document.getElementById('toggle-logs');
    const logsContainer = document.getElementById('system-logs');

    // Painel de logs foi removido da UI
    if (!toggleBtn || !logsContainer) return;

    let collapsed = false;

    toggleBtn.addEventListener('click', () => {
        collapsed = !collapsed;
        logsContainer.style.height = collapsed ? '0' : '6rem';
        logsContainer.style.padding = collapsed ? '0 1rem' : '0.5rem 1rem';
        toggleBtn.innerHTML = `<i class="fas fa-chevron-${collapsed ? 'up' : 'down'}"></i>`;
    });
}

/**
 * Setup file upload handlers
 */
function setupFileUpload() {
    // Botão de importar na barra lateral
    const importBtn = document.getElementById('btn-import');
    if (importBtn) {
        importBtn.addEventListener('click', triggerFileUpload);
        console.log('[Setup] Botão importar configurado');
    } else {
        console.warn('[Setup] Botão importar não encontrado');
    }

    // Criar input de arquivo oculto
    const fileInput = document.createElement('input');
    fileInput.type = 'file';
    fileInput.id = 'file-input';
    fileInput.accept = '.pdf,.png,.jpg,.jpeg,.tif,.tiff,.bmp,.webp';
    fileInput.multiple = true;
    fileInput.style.display = 'none';
    fileInput.addEventListener('change', handleFileSelect);
    document.body.appendChild(fileInput);
    console.log('[Setup] Input de arquivo criado');
}

function triggerFileUpload() {
    document.getElementById('file-input')?.click();
}

async function handleFileSelect(event) {
    const files = event.target.files;
    if (!files || files.length === 0) return;

    for (const file of files) {
        await uploadFile(file);
    }

    event.target.value = ''; // Reset input
}

/**
 * Setup settings button - não usado mais (config pelo admin)
 */
function setupSettings() {
    // Configurações movidas para o painel admin
}

/**
 * Setup AI Analysis buttons
 */
function setupAIActions() {
    // Botão de analisar documento
    const analyzeBtn = document.getElementById('btn-analyze');
    if (analyzeBtn) {
        analyzeBtn.addEventListener('click', () => {
            if (appState.selectedFileId) {
                analisarDocumento(appState.selectedFileId);
            } else {
                showToast('Selecione um documento primeiro', 'warning');
            }
        });
        console.log('[Setup] Botão analisar configurado');
    }

    // Botão de reanalisar documento (forçar nova análise)
    const reanalyzeBtn = document.getElementById('btn-reanalyze');
    if (reanalyzeBtn) {
        reanalyzeBtn.addEventListener('click', () => {
            if (appState.selectedFileId) {
                if (confirm('Deseja refazer a análise deste documento? A análise anterior será substituída.')) {
                    analisarDocumento(appState.selectedFileId, true);
                }
            } else {
                showToast('Selecione um documento primeiro', 'warning');
            }
        });
        console.log('[Setup] Botão reanalisar configurado');
    }

    // Botão de análise em lote
    const batchAnalyzeBtn = document.getElementById('btn-analyze-batch');
    if (batchAnalyzeBtn) {
        batchAnalyzeBtn.addEventListener('click', () => {
            if (appState.selectedFileIds.length >= 2) {
                analisarEmLote(appState.selectedFileIds);
            } else {
                showToast('Selecione pelo menos 2 documentos (Ctrl+Click)', 'warning');
            }
        });
        console.log('[Setup] Botão análise em lote configurado');
    }

    // Botão de excluir arquivo
    const deleteBtn = document.getElementById('btn-delete-file');
    if (deleteBtn) {
        deleteBtn.addEventListener('click', () => {
            if (appState.selectedFileId) {
                deleteFile(appState.selectedFileId);
            } else {
                showToast('Selecione um documento primeiro', 'warning');
            }
        });
    }

    // Atualiza status inicial
    updateAnalysisStatus();
}

/**
 * Update analysis status text
 */
function updateAnalysisStatus() {
    const statusEl = document.getElementById('analysis-status');
    if (!statusEl) return;

    if (!appState.selectedFileId) {
        statusEl.innerHTML = 'Selecione um documento para analisar';
        statusEl.className = 'text-xs text-gray-500 text-center mt-2';
    } else {
        const file = appState.files.find(f => String(f.id) === String(appState.selectedFileId));
        if (file?.analyzed) {
            statusEl.innerHTML = '<i class="fas fa-check-circle text-green-500"></i> Documento analisado';
            statusEl.className = 'text-xs text-green-600 text-center mt-2';
        } else {
            statusEl.innerHTML = '<i class="fas fa-info-circle text-blue-500"></i> Pronto para analisar';
            statusEl.className = 'text-xs text-blue-600 text-center mt-2';
        }
    }
}

/**
 * Update API status in header - não usado mais
 */
function updateApiStatus() {
    // Configuração de API movida para o painel admin
}

function showSettingsModal() {
    // Configurações movidas para o painel admin
    showToast('Configurações de API devem ser feitas pelo administrador', 'info');
}

async function saveApiKeyFromModal() {
    // Não é mais usado - API key é configurada pelo admin
    showToast('Configurações de API devem ser feitas pelo administrador', 'info');
}

// ============================================
// Initialization
// ============================================

document.addEventListener('DOMContentLoaded', async () => {
    console.log('[Init] Iniciando aplicação...');

    // Carrega dados do servidor
    try {
        await Promise.all([
            loadConfig(),
            loadFiles(),
            loadAnalyses(),
            loadLogs()
        ]);
        console.log('[Init] Dados carregados do servidor');
    } catch (error) {
        console.error('[Init] Erro ao carregar dados:', error);
    }

    // Renderiza interface
    renderFileList();
    renderRecordsTable();
    renderDocumentDetails();
    renderSystemLogs();

    // Setup handlers
    setupLogToggle();
    setupFileUpload();
    setupSettings();
    setupAIActions();

    // Atualiza status
    updateAnalysisStatus();

    // Welcome log
    addLog('success', 'Interface web carregada com sucesso');
    console.log('[Init] Aplicação iniciada');
});

// ============================================
// Help Modal - Análise em Lote
// ============================================

function showBatchHelpModal() {
    const modal = document.createElement('div');
    modal.id = 'batch-help-modal';
    modal.className = 'fixed inset-0 z-50 flex items-center justify-center bg-black/50';
    modal.onclick = (e) => { if (e.target === modal) modal.remove(); };

    modal.innerHTML = `
        <div class="bg-white rounded-xl shadow-2xl max-w-md w-full mx-4 overflow-hidden">
            <div class="bg-gradient-to-r from-purple-500 to-purple-600 px-6 py-4">
                <div class="flex items-center justify-between">
                    <h3 class="text-lg font-semibold text-white flex items-center gap-2">
                        <i class="fas fa-layer-group"></i>
                        Análise em Lote
                    </h3>
                    <button onclick="document.getElementById('batch-help-modal').remove()" 
                        class="text-white/80 hover:text-white transition-colors">
                        <i class="fas fa-times text-xl"></i>
                    </button>
                </div>
            </div>
            <div class="p-6 space-y-4">
                <div class="flex items-start gap-3">
                    <div class="w-8 h-8 bg-purple-100 rounded-full flex items-center justify-center flex-shrink-0">
                        <i class="fas fa-question text-purple-600"></i>
                    </div>
                    <div>
                        <h4 class="font-semibold text-gray-800">Quando usar?</h4>
                        <p class="text-sm text-gray-600 mt-1">
                            Use quando tiver <strong>múltiplas matrículas</strong> que fazem parte do 
                            <strong>mesmo processo de usucapião</strong>.
                        </p>
                    </div>
                </div>
                
                <div class="flex items-start gap-3">
                    <div class="w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center flex-shrink-0">
                        <i class="fas fa-file-alt text-blue-600"></i>
                    </div>
                    <div>
                        <h4 class="font-semibold text-gray-800">Exemplo</h4>
                        <p class="text-sm text-gray-600 mt-1">
                            A matrícula principal do imóvel + matrículas dos confrontantes anexadas ao processo.
                        </p>
                    </div>
                </div>
                
                <div class="flex items-start gap-3">
                    <div class="w-8 h-8 bg-green-100 rounded-full flex items-center justify-center flex-shrink-0">
                        <i class="fas fa-brain text-green-600"></i>
                    </div>
                    <div>
                        <h4 class="font-semibold text-gray-800">O que a IA faz?</h4>
                        <p class="text-sm text-gray-600 mt-1">
                            Analisa todos os documentos em conjunto, cruzando informações para identificar 
                            a matrícula principal e validar as confrontações.
                        </p>
                    </div>
                </div>
                
                <div class="bg-gray-50 rounded-lg p-4 mt-4">
                    <h4 class="font-semibold text-gray-800 text-sm mb-2">
                        <i class="fas fa-keyboard text-gray-500"></i> Como selecionar múltiplos arquivos:
                    </h4>
                    <p class="text-sm text-gray-600">
                        Segure <kbd class="px-2 py-1 bg-gray-200 rounded text-xs font-mono">Ctrl</kbd> 
                        e clique nos arquivos desejados.
                    </p>
                </div>
            </div>
            <div class="px-6 py-4 bg-gray-50 border-t">
                <button onclick="document.getElementById('batch-help-modal').remove()" 
                    class="w-full px-4 py-2 bg-purple-500 text-white rounded-lg hover:bg-purple-600 transition-colors font-medium">
                    Entendi
                </button>
            </div>
        </div>
    `;

    document.body.appendChild(modal);
}
