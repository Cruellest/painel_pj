/**
 * Sistema de Assistência Judiciária - PGE-MS
 * Consulta de processos no TJ-MS com análise por IA
 */

// ============================================
// Configuração da API
// ============================================

const API_BASE = '/assistencia/api';

// Autenticação
function getAuthToken() {
    return localStorage.getItem('access_token');
}

function checkAuth() {
    const token = getAuthToken();
    if (!token) {
        window.location.href = '/login';
        return false;
    }
    return true;
}

function logout() {
    localStorage.removeItem('access_token');
    window.location.href = '/login';
}

// Estado da aplicação
let appState = {
    historico: [],
    ultimoResultado: null,
    config: {
        apiKey: '',
        model: 'google/gemini-2.5-flash'
    }
};

// ============================================
// Funções de API
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
            localStorage.removeItem('access_token');
            window.location.href = '/login';
            return null;
        }

        // Para downloads (blob)
        if (options.responseType === 'blob') {
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            return await response.blob();
        }

        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.detail || `HTTP ${response.status}`);
        }

        return data;
    } catch (error) {
        console.error(`API Error [${endpoint}]:`, error);
        throw error;
    }
}

// ============================================
// Funções de UI
// ============================================

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    
    const colors = {
        success: 'bg-green-500',
        error: 'bg-red-500',
        warning: 'bg-yellow-500',
        info: 'bg-blue-500'
    };
    
    const icons = {
        success: 'fa-check-circle',
        error: 'fa-exclamation-circle',
        warning: 'fa-exclamation-triangle',
        info: 'fa-info-circle'
    };
    
    toast.className = `toast ${colors[type]} text-white px-4 py-3 rounded-lg shadow-lg flex items-center gap-2 min-w-[280px]`;
    toast.innerHTML = `
        <i class="fas ${icons[type]}"></i>
        <span class="flex-1">${message}</span>
        <button onclick="this.parentElement.remove()" class="text-white/80 hover:text-white">
            <i class="fas fa-times"></i>
        </button>
    `;
    
    container.appendChild(toast);
    
    setTimeout(() => toast.remove(), 5000);
}

function mostrarEstado(estado) {
    document.getElementById('estado-inicial').classList.add('hidden');
    document.getElementById('estado-loading').classList.add('hidden');
    document.getElementById('estado-resultado').classList.add('hidden');
    document.getElementById('estado-erro').classList.add('hidden');
    
    document.getElementById(`estado-${estado}`).classList.remove('hidden');
}

function voltarInicio() {
    mostrarEstado('inicial');
}

// ============================================
// Histórico
// ============================================

async function carregarHistorico() {
    try {
        const historico = await api('/historico');
        if (historico && Array.isArray(historico)) {
            appState.historico = historico;
            renderizarHistorico();
        }
    } catch (error) {
        console.error('Erro ao carregar histórico:', error);
    }
}

function renderizarHistorico() {
    const container = document.getElementById('historico-list');
    
    if (!appState.historico || appState.historico.length === 0) {
        container.innerHTML = '<p class="text-sm text-gray-400 italic">Nenhuma consulta ainda</p>';
        return;
    }
    
    container.innerHTML = appState.historico.slice(0, 10).map(item => `
        <div class="flex items-center justify-between p-2 rounded-lg hover:bg-gray-100 transition-colors group">
            <button onclick="consultarProcesso('${item.cnj}')" 
                class="flex-1 text-left">
                <div class="font-mono text-xs text-gray-600 group-hover:text-primary-600">${item.cnj}</div>
                <div class="text-xs text-gray-400 truncate">${item.classe || 'Processo'}</div>
            </button>
            <button onclick="excluirDoHistorico(${item.id}, event)" 
                class="p-1 text-gray-300 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity"
                title="Remover do histórico">
                <i class="fas fa-times text-xs"></i>
            </button>
        </div>
    `).join('');
}

async function excluirDoHistorico(id, event) {
    event.stopPropagation();
    try {
        const result = await api(`/historico/${id}`, { method: 'DELETE' });
        if (result && result.success) {
            await carregarHistorico();
            showToast('Removido do histórico', 'info');
        }
    } catch (error) {
        showToast('Erro ao remover do histórico', 'error');
    }
}

function adicionarHistorico(cnj, classe) {
    // Não precisa mais fazer nada aqui, o histórico é atualizado automaticamente
    // quando a consulta é salva no banco pelo backend
    carregarHistorico();
}

// ============================================
// Consulta de Processo
// ============================================

async function consultarProcesso(cnj, forceRefresh = false) {
    if (!cnj) {
        cnj = document.getElementById('input-cnj').value.trim();
    }
    
    if (!cnj) {
        showToast('Digite o número do processo', 'warning');
        return;
    }
    
    // Atualiza input
    document.getElementById('input-cnj').value = cnj;
    
    mostrarEstado('loading');
    
    try {
        const result = await api('/consultar', {
            method: 'POST',
            body: JSON.stringify({ 
                cnj: cnj,
                model: appState.config.model,
                force: forceRefresh
            })
        });
        
        if (!result) return;
        
        appState.ultimoResultado = result;
        
        // Extrai dados
        const dados = result.dados || {};
        const relatorio = result.relatorio || '';
        
        // Preenche a UI
        document.getElementById('resultado-cnj').textContent = cnj;
        
        // Mostra indicador de cache
        const cacheIndicator = document.getElementById('cache-indicator');
        if (cacheIndicator) {
            if (result.cached) {
                const dataConsulta = result.consultado_em ? new Date(result.consultado_em).toLocaleDateString('pt-BR') : '';
                cacheIndicator.innerHTML = `<i class="fas fa-database text-blue-500"></i> Dados em cache ${dataConsulta ? `(${dataConsulta})` : ''}`;
                cacheIndicator.classList.remove('hidden');
            } else {
                cacheIndicator.classList.add('hidden');
            }
        }
        
        // Relatório
        const relatorioContainer = document.getElementById('resultado-relatorio');
        if (relatorio) {
            relatorioContainer.innerHTML = marked.parse(relatorio);
        } else {
            relatorioContainer.innerHTML = '<p class="text-gray-400 italic">Relatório não disponível</p>';
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
        document.getElementById('erro-mensagem').textContent = error.message || 'Erro ao consultar processo';
        mostrarEstado('erro');
        showToast('Erro na consulta', 'error');
    }
}

function reconsultarProcesso() {
    const cnj = document.getElementById('resultado-cnj').textContent;
    if (cnj && confirm('Deseja reconsultar este processo? Isso irá buscar dados atualizados do TJ-MS e gerar um novo relatório.')) {
        consultarProcesso(cnj, true);
    }
}

// ============================================
// Feedback da Análise
// ============================================

async function enviarFeedback(avaliacao) {
    if (!appState.ultimoResultado || !appState.ultimoResultado.consulta_id) {
        showToast('Nenhuma consulta para avaliar', 'warning');
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
                consulta_id: appState.ultimoResultado.consulta_id,
                avaliacao: avaliacao,
                comentario: comentario
            })
        });
        
        if (result && result.success) {
            // Mostra feedback enviado
            document.getElementById('feedback-buttons').classList.add('hidden');
            document.getElementById('feedback-enviado').classList.remove('hidden');
            
            const tipoTexto = {
                'correto': 'Análise marcada como correta',
                'parcial': 'Análise marcada como parcialmente correta',
                'incorreto': 'Análise marcada como incorreta',
                'erro_ia': 'Reportado como erro da IA'
            };
            document.getElementById('feedback-enviado-tipo').textContent = tipoTexto[avaliacao] || '';
            
            showToast('Feedback registrado!', 'success');
        } else {
            showToast('Erro ao enviar feedback', 'error');
        }
    } catch (error) {
        showToast('Erro ao enviar feedback', 'error');
    }
}

async function verificarFeedbackExistente(consultaId) {
    try {
        const result = await api(`/feedback/${consultaId}`);
        
        if (result && result.has_feedback) {
            // Já tem feedback, mostra o estado de enviado
            document.getElementById('feedback-buttons').classList.add('hidden');
            document.getElementById('feedback-enviado').classList.remove('hidden');
            
            const tipoTexto = {
                'correto': 'Análise marcada como correta',
                'parcial': 'Análise marcada como parcialmente correta',
                'incorreto': 'Análise marcada como incorreta',
                'erro_ia': 'Reportado como erro da IA'
            };
            document.getElementById('feedback-enviado-tipo').textContent = tipoTexto[result.avaliacao] || '';
        } else {
            // Não tem feedback, mostra botões
            document.getElementById('feedback-buttons').classList.remove('hidden');
            document.getElementById('feedback-enviado').classList.add('hidden');
        }
    } catch (error) {
        // Em caso de erro, mostra botões
        document.getElementById('feedback-buttons').classList.remove('hidden');
        document.getElementById('feedback-enviado').classList.add('hidden');
    }
}

// ============================================
// Download de Documentos
// ============================================

async function downloadDocumento(formato) {
    if (!appState.ultimoResultado) {
        showToast('Nenhum resultado para exportar', 'warning');
        return;
    }
    
    const cnj = document.getElementById('resultado-cnj').textContent;
    const relatorio = appState.ultimoResultado.relatorio || '';
    
    showToast(`Gerando ${formato.toUpperCase()}...`, 'info');
    
    try {
        const response = await fetch(`${API_BASE}/generate-doc`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${getAuthToken()}`
            },
            body: JSON.stringify({
                markdown_text: relatorio,
                cnj: cnj,
                format: formato
            })
        });
        
        if (!response.ok) {
            throw new Error('Erro ao gerar documento');
        }
        
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `relatorio_${cnj.replace(/\D/g, '')}.${formato}`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        a.remove();
        
        showToast(`${formato.toUpperCase()} baixado com sucesso!`, 'success');
        
    } catch (error) {
        showToast(`Erro ao gerar ${formato.toUpperCase()}`, 'error');
    }
}

// ============================================
// Configurações
// ============================================

function abrirSettings() {
    document.getElementById('modal-settings').classList.remove('hidden');
    carregarSettings();
}

function fecharSettings() {
    document.getElementById('modal-settings').classList.add('hidden');
}

async function carregarSettings() {
    try {
        const config = await api('/settings');
        if (config) {
            document.getElementById('input-apikey').value = config.openrouter_api_key || '';
            document.getElementById('select-model').value = config.default_model || 'google/gemini-2.5-flash';
            appState.config.model = config.default_model || 'google/gemini-2.5-flash';
        }
    } catch (error) {
        console.error('Erro ao carregar settings:', error);
    }
}

async function salvarSettings() {
    const apiKey = document.getElementById('input-apikey').value.trim();
    const model = document.getElementById('select-model').value;
    
    try {
        await api('/settings', {
            method: 'POST',
            body: JSON.stringify({
                openrouter_api_key: apiKey,
                default_model: model
            })
        });
        
        appState.config.model = model;
        fecharSettings();
        showToast('Configurações salvas!', 'success');
        atualizarStatusAPI();
        
    } catch (error) {
        showToast('Erro ao salvar configurações', 'error');
    }
}

async function atualizarStatusAPI() {
    try {
        const config = await api('/settings');
        const statusEl = document.getElementById('api-status');
        
        if (config && config.openrouter_api_key && config.openrouter_api_key.length > 10) {
            statusEl.innerHTML = `
                <span class="w-2 h-2 rounded-full bg-green-500"></span>
                <span class="text-green-600">API Configurada</span>
            `;
        } else {
            statusEl.innerHTML = `
                <span class="w-2 h-2 rounded-full bg-yellow-500"></span>
                <span class="text-yellow-600">API não configurada</span>
            `;
        }
    } catch (error) {
        document.getElementById('api-status').innerHTML = `
            <span class="w-2 h-2 rounded-full bg-red-500"></span>
            <span class="text-red-600">Erro de conexão</span>
        `;
    }
}

// ============================================
// Event Listeners
// ============================================

document.addEventListener('DOMContentLoaded', () => {
    // Verifica autenticação
    if (!checkAuth()) return;
    
    // Botão consultar
    document.getElementById('btn-consultar').addEventListener('click', () => consultarProcesso());
    
    // Enter no input
    document.getElementById('input-cnj').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') consultarProcesso();
    });
    
    // Botão configurações
    document.getElementById('btn-settings').addEventListener('click', abrirSettings);
    
    // Downloads
    document.getElementById('btn-download-docx').addEventListener('click', () => downloadDocumento('docx'));
    document.getElementById('btn-download-pdf').addEventListener('click', () => downloadDocumento('pdf'));
    
    // Fechar modal clicando fora
    document.getElementById('modal-settings').addEventListener('click', (e) => {
        if (e.target.id === 'modal-settings') fecharSettings();
    });
    
    // Carrega estado inicial do banco de dados
    carregarHistorico();
    atualizarStatusAPI();
});
