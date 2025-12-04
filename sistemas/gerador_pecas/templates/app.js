// app.js - Gerador de Peças Jurídicas
// Frontend JavaScript

const API_URL = '/gerador-pecas/api';

class GeradorPecasApp {
    constructor() {
        this.numeroCNJ = null;
        this.tipoPeca = null;
        this.conteudoJSON = null;
        this.urlDownload = null;
        this.geracaoId = null;
        this.notaSelecionada = null;
        
        this.initEventListeners();
        this.checkAuth();
    }
    
    async checkAuth() {
        const token = localStorage.getItem('access_token');
        
        if (!token) {
            window.location.href = '/login';
            return;
        }

        try {
            const response = await fetch('/auth/me', {
                headers: { 'Authorization': `Bearer ${token}` }
            });

            if (!response.ok) {
                throw new Error('Token inválido');
            }
        } catch (error) {
            localStorage.removeItem('access_token');
            window.location.href = '/login';
        }
    }
    
    initEventListeners() {
        // Form submit
        document.getElementById('form-processo').addEventListener('submit', (e) => {
            e.preventDefault();
            this.iniciarProcessamento();
        });
        
        // Modal pergunta
        document.getElementById('btn-cancelar-pergunta').addEventListener('click', () => {
            this.fecharModal('modal-pergunta');
        });
        
        document.getElementById('btn-enviar-resposta').addEventListener('click', () => {
            this.enviarResposta();
        });
        
        // Modal edição
        document.getElementById('btn-cancelar-edicao').addEventListener('click', () => {
            this.fecharModal('modal-edicao');
        });
        
        document.getElementById('btn-download').addEventListener('click', () => {
            this.download();
        });
        
        // Feedback
        document.querySelectorAll('.estrela').forEach(btn => {
            btn.addEventListener('click', (e) => {
                this.selecionarNota(parseInt(e.target.dataset.nota));
            });
        });
        
        document.getElementById('btn-pular-feedback').addEventListener('click', () => {
            this.fecharModal('modal-feedback');
            this.resetar();
        });
        
        document.getElementById('btn-enviar-feedback').addEventListener('click', () => {
            this.enviarFeedback();
        });
    }
    
    async iniciarProcessamento() {
        this.numeroCNJ = document.getElementById('numero-cnj').value;
        this.tipoPeca = document.getElementById('tipo-peca').value || null;
        
        this.esconderErro();
        this.mostrarLoading('Consultando processo no TJ-MS...');
        
        try {
            const response = await fetch(`${API_URL}/processar`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.getToken()}`
                },
                body: JSON.stringify({
                    numero_cnj: this.numeroCNJ,
                    tipo_peca: this.tipoPeca
                })
            });
            
            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.detail || 'Erro ao processar');
            }
            
            if (data.status === 'pergunta') {
                this.exibirPergunta(data);
            } else if (data.status === 'sucesso') {
                this.exibirPreview(data);
            } else if (data.status === 'erro') {
                this.mostrarErro(data.mensagem);
            }
            
        } catch (error) {
            this.mostrarErro(error.message);
        } finally {
            this.esconderLoading();
        }
    }
    
    exibirPergunta(data) {
        document.getElementById('pergunta-texto').textContent = data.pergunta;
        
        const opcoesContainer = document.getElementById('opcoes-container');
        opcoesContainer.innerHTML = '';
        
        if (data.opcoes && data.opcoes.length > 0) {
            data.opcoes.forEach(opcao => {
                const btn = document.createElement('button');
                btn.className = 'w-full px-4 py-3 text-left border border-gray-300 rounded-xl hover:bg-primary-50 hover:border-primary-500 transition-colors';
                btn.textContent = this.formatarOpcao(opcao);
                btn.addEventListener('click', () => {
                    this.tipoPeca = opcao;
                    this.enviarResposta();
                });
                opcoesContainer.appendChild(btn);
            });
        }
        
        // Mostra mensagem informativa se houver
        if (data.mensagem) {
            const p = document.createElement('p');
            p.className = 'text-sm text-yellow-600 mt-4 p-3 bg-yellow-50 rounded-lg';
            p.innerHTML = `<i class="fas fa-info-circle mr-1"></i> ${data.mensagem}`;
            opcoesContainer.appendChild(p);
        }
        
        this.abrirModal('modal-pergunta');
    }
    
    async enviarResposta() {
        const resposta = document.getElementById('resposta-usuario').value || this.tipoPeca;
        
        this.fecharModal('modal-pergunta');
        this.mostrarLoading('Gerando documento...');
        
        try {
            const response = await fetch(`${API_URL}/processar`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.getToken()}`
                },
                body: JSON.stringify({
                    numero_cnj: this.numeroCNJ,
                    tipo_peca: this.tipoPeca,
                    resposta_usuario: resposta
                })
            });
            
            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.detail || 'Erro ao processar');
            }
            
            if (data.status === 'sucesso') {
                this.exibirPreview(data);
            } else if (data.status === 'erro') {
                this.mostrarErro(data.mensagem);
            }
            
        } catch (error) {
            this.mostrarErro(error.message);
        } finally {
            this.esconderLoading();
        }
    }
    
    exibirPreview(data) {
        this.urlDownload = data.url_download;
        this.conteudoJSON = data.conteudo_json;
        this.tipoPeca = data.tipo_peca;
        this.geracaoId = data.geracao_id;
        
        // Renderizar preview
        const previewContainer = document.getElementById('preview-container');
        previewContainer.innerHTML = this.renderizarPreview(data.conteudo_json);
        
        this.abrirModal('modal-edicao');
    }
    
    renderizarPreview(conteudo) {
        let html = '';
        
        // Cabeçalho
        if (conteudo.cabecalho) {
            const align = conteudo.cabecalho.alinhamento === 'direita' ? 'text-right' : 
                         conteudo.cabecalho.alinhamento === 'centro' ? 'text-center' : 'text-left';
            html += `<div class="${align} mb-6 font-bold">${conteudo.cabecalho.texto}</div>`;
        }
        
        // Qualificação
        if (conteudo.qualificacao) {
            html += `<p class="mb-6 text-justify" style="text-indent: 1.25cm;">${conteudo.qualificacao.texto.replace(/\n/g, '<br>')}</p>`;
        }
        
        // Seções
        if (conteudo.secoes) {
            conteudo.secoes.forEach(secao => {
                html += `<h2 class="text-center font-bold my-6">${secao.titulo}</h2>`;
                
                if (secao.paragrafos) {
                    secao.paragrafos.forEach((p, i) => {
                        if (p.tipo === 'citacao') {
                            html += `<blockquote class="border-l-4 border-gray-300 pl-4 italic my-4 text-sm ml-12 mr-12">${p.texto}</blockquote>`;
                            if (p.fonte) {
                                html += `<p class="text-xs text-right text-gray-600 mr-12 mb-4">${p.fonte}</p>`;
                            }
                        } else {
                            html += `<p class="mb-3 text-justify" style="text-indent: 1.25cm;">${p.texto}</p>`;
                        }
                    });
                }
            });
        }
        
        // Fecho
        if (conteudo.fecho) {
            html += `<div class="text-right mt-8">${conteudo.fecho.local_data}</div>`;
            html += `<div class="text-center mt-12 whitespace-pre-line">${conteudo.fecho.assinatura.replace(/\\n/g, '\n')}</div>`;
        }
        
        return html;
    }
    
    async download() {
        this.fecharModal('modal-edicao');
        
        // Iniciar download
        const link = document.createElement('a');
        link.href = this.urlDownload;
        link.download = `peca_${this.numeroCNJ.replace(/[\/\-\.]/g, '_')}.docx`;
        
        // Adiciona token via query param para autenticação
        const token = this.getToken();
        link.href = `${this.urlDownload}?token=${token}`;
        
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        
        // Mostrar toast de sucesso
        this.showToast('Download iniciado!', 'success');
        
        // Aguardar e abrir modal de feedback
        setTimeout(() => {
            this.abrirModal('modal-feedback');
        }, 1500);
    }
    
    selecionarNota(nota) {
        this.notaSelecionada = nota;
        
        document.querySelectorAll('.estrela').forEach((btn, idx) => {
            if (idx < nota) {
                btn.classList.add('text-yellow-400');
                btn.classList.remove('text-gray-300');
            } else {
                btn.classList.remove('text-yellow-400');
                btn.classList.add('text-gray-300');
            }
        });
        
        document.getElementById('btn-enviar-feedback').disabled = false;
    }
    
    async enviarFeedback() {
        if (!this.geracaoId) {
            this.fecharModal('modal-feedback');
            this.resetar();
            return;
        }
        
        const comentario = document.getElementById('feedback-comentario').value;
        
        try {
            await fetch(`${API_URL}/feedback`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.getToken()}`
                },
                body: JSON.stringify({
                    geracao_id: this.geracaoId,
                    avaliacao: this.notaSelecionada >= 4 ? 'correto' : this.notaSelecionada >= 2 ? 'parcial' : 'incorreto',
                    nota: this.notaSelecionada,
                    comentario: comentario || null
                })
            });
            
            this.showToast('Feedback enviado! Obrigado!', 'success');
            
        } catch (error) {
            console.error('Erro ao enviar feedback:', error);
        } finally {
            this.fecharModal('modal-feedback');
            this.resetar();
        }
    }
    
    // Histórico
    async carregarHistorico() {
        const lista = document.getElementById('lista-historico');
        
        try {
            const response = await fetch(`${API_URL}/historico`, {
                headers: { 'Authorization': `Bearer ${this.getToken()}` }
            });
            
            if (!response.ok) throw new Error('Erro ao carregar');
            
            const historico = await response.json();
            
            if (historico.length === 0) {
                lista.innerHTML = '<p class="text-gray-500 text-sm text-center py-8">Nenhuma geração encontrada</p>';
                return;
            }
            
            lista.innerHTML = historico.map(item => `
                <div class="border border-gray-200 rounded-lg p-3 mb-2 hover:bg-gray-50">
                    <p class="font-medium text-sm text-gray-800">${item.cnj}</p>
                    <p class="text-xs text-gray-500">${this.formatarOpcao(item.tipo_peca)}</p>
                    <p class="text-xs text-gray-400">${new Date(item.data).toLocaleDateString('pt-BR')}</p>
                </div>
            `).join('');
            
        } catch (error) {
            lista.innerHTML = '<p class="text-red-500 text-sm text-center py-8">Erro ao carregar histórico</p>';
        }
    }
    
    // Utilitários
    mostrarLoading(mensagem) {
        document.getElementById('loading-message').textContent = mensagem;
        document.getElementById('loading').classList.remove('hidden');
        document.getElementById('btn-gerar').disabled = true;
    }
    
    esconderLoading() {
        document.getElementById('loading').classList.add('hidden');
        document.getElementById('btn-gerar').disabled = false;
    }
    
    mostrarErro(mensagem) {
        document.getElementById('erro-mensagem').textContent = mensagem;
        document.getElementById('resultado-erro').classList.remove('hidden');
    }
    
    esconderErro() {
        document.getElementById('resultado-erro').classList.add('hidden');
    }
    
    abrirModal(id) {
        document.getElementById(id).classList.remove('hidden');
    }
    
    fecharModal(id) {
        document.getElementById(id).classList.add('hidden');
    }
    
    formatarOpcao(opcao) {
        const labels = {
            'contestacao': 'Contestação',
            'recurso_apelacao': 'Recurso de Apelação',
            'contrarrazoes': 'Contrarrazões de Recurso',
            'parecer': 'Parecer Jurídico'
        };
        return labels[opcao] || opcao || 'Não definido';
    }
    
    getToken() {
        return localStorage.getItem('access_token');
    }
    
    showToast(message, type = 'success') {
        const toast = document.getElementById('toast');
        const icon = document.getElementById('toast-icon');
        const msg = document.getElementById('toast-message');

        msg.textContent = message;
        
        if (type === 'success') {
            icon.className = 'fas fa-check-circle text-green-400';
        } else if (type === 'error') {
            icon.className = 'fas fa-exclamation-circle text-red-400';
        }

        toast.classList.remove('hidden');
        setTimeout(() => toast.classList.add('hidden'), 3000);
    }
    
    resetar() {
        document.getElementById('form-processo').reset();
        document.getElementById('resposta-usuario').value = '';
        document.getElementById('feedback-comentario').value = '';
        this.numeroCNJ = null;
        this.tipoPeca = null;
        this.conteudoJSON = null;
        this.urlDownload = null;
        this.geracaoId = null;
        this.notaSelecionada = null;
        
        // Reset estrelas
        document.querySelectorAll('.estrela').forEach(btn => {
            btn.classList.remove('text-yellow-400');
            btn.classList.add('text-gray-300');
        });
        document.getElementById('btn-enviar-feedback').disabled = true;
    }
}

// Toggle do painel de histórico
function toggleHistorico() {
    const painel = document.getElementById('painel-historico');
    
    if (painel.classList.contains('translate-x-full')) {
        painel.classList.remove('translate-x-full', 'hidden');
        painel.classList.add('translate-x-0');
        app.carregarHistorico();
    } else {
        painel.classList.add('translate-x-full');
        painel.classList.remove('translate-x-0');
    }
}

function fecharModalEdicao() {
    document.getElementById('modal-edicao').classList.add('hidden');
}

// Inicializar app
let app;
document.addEventListener('DOMContentLoaded', () => {
    app = new GeradorPecasApp();
});
