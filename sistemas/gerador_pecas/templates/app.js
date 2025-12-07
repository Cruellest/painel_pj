// app.js - Gerador de Peças Jurídicas
// Frontend JavaScript com Chat Interativo para Edição

const API_URL = '/gerador-pecas/api';

class GeradorPecasApp {
    constructor() {
        this.numeroCNJ = null;
        this.tipoPeca = null;
        this.geracaoId = null;
        this.notaSelecionada = null;

        // Dados para o editor interativo
        this.minutaMarkdown = null;
        this.historicoChat = [];
        this.isProcessingEdit = false;

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
            
            // Carrega histórico recente após autenticação
            this.carregarHistoricoRecente();
            
            // Carrega tipos de peça dinamicamente
            this.carregarTiposPeca();
        } catch (error) {
            localStorage.removeItem('access_token');
            window.location.href = '/login';
        }
    }

    async carregarTiposPeca() {
        try {
            const response = await fetch(`${API_URL}/tipos-peca`, {
                headers: { 'Authorization': `Bearer ${this.getToken()}` }
            });

            if (!response.ok) return;

            const data = await response.json();
            const select = document.getElementById('tipo-peca');
            
            // Limpa opções existentes (exceto a primeira)
            while (select.options.length > 1) {
                select.remove(1);
            }
            
            // Adiciona tipos do banco
            data.tipos.forEach(tipo => {
                const option = document.createElement('option');
                option.value = tipo.valor;
                option.textContent = tipo.label;
                select.appendChild(option);
            });
        } catch (error) {
            console.error('Erro ao carregar tipos de peça:', error);
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

        // Novo: Chat de edição
        document.getElementById('btn-enviar-chat').addEventListener('click', () => {
            this.enviarMensagemChat();
        });

        document.getElementById('chat-input').addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.enviarMensagemChat();
            }
        });

        // Novo: Botão de copiar minuta
        document.getElementById('btn-copiar-minuta').addEventListener('click', () => {
            this.copiarMinuta();
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
        this.resetarStatusAgentes();
        this.mostrarLoading('Conectando ao servidor...', null);

        try {
            // Usa SSE para streaming em tempo real
            const response = await fetch(`${API_URL}/processar-stream`, {
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

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Erro ao processar');
            }

            // Processa o stream SSE
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n\n');
                buffer = lines.pop() || '';

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.slice(6));
                            this.processarEventoStream(data);
                        } catch (e) {
                            console.warn('Erro ao parsear evento SSE:', e);
                        }
                    }
                }
            }

        } catch (error) {
            this.mostrarErro(error.message);
            this.esconderLoading();
        }
    }

    processarEventoStream(data) {
        console.log('📡 Evento SSE:', data);

        switch (data.tipo) {
            case 'inicio':
                document.getElementById('progresso-mensagem').textContent = data.mensagem;
                break;

            case 'agente':
                this.atualizarStatusAgente(data.agente, data.status);
                document.getElementById('progresso-mensagem').textContent = data.mensagem;
                
                if (data.status === 'erro') {
                    this.mostrarErro(data.mensagem);
                    this.esconderLoading();
                }
                break;

            case 'pergunta':
                this.esconderLoading();
                this.exibirPergunta(data);
                break;

            case 'sucesso':
                // Atualiza progresso para 100%
                document.getElementById('progresso-barra').style.width = '100%';
                this.atualizarStatusAgente(3, 'concluido');
                
                setTimeout(() => {
                    this.esconderLoading();
                    this.showToast('Peça gerada com sucesso!', 'success');
                    this.exibirEditor({
                        status: 'sucesso',
                        geracao_id: data.geracao_id,
                        tipo_peca: data.tipo_peca,
                        minuta_markdown: data.minuta_markdown
                    });
                }, 500);
                break;

            case 'erro':
                this.esconderLoading();
                this.mostrarErro(data.mensagem);
                break;

            case 'info':
                document.getElementById('progresso-mensagem').textContent = data.mensagem;
                break;

            default:
                // Fallback para respostas diretas (modo legado)
                if (data.status === 'pergunta') {
                    this.esconderLoading();
                    this.exibirPergunta(data);
                } else if (data.status === 'sucesso') {
                    this.esconderLoading();
                    this.exibirEditor(data);
                } else if (data.status === 'erro') {
                    this.esconderLoading();
                    this.mostrarErro(data.mensagem);
                }
        }
    }

    exibirPergunta(data) {
        document.getElementById('pergunta-texto').textContent = data.pergunta;

        const opcoesContainer = document.getElementById('opcoes-container');
        opcoesContainer.innerHTML = '';

        if (data.opcoes && data.opcoes.length > 0) {
            data.opcoes.forEach(opcao => {
                const btn = document.createElement('button');
                btn.className = 'w-full px-4 py-3 text-left border border-gray-200 rounded-xl hover:bg-primary-50 hover:border-primary-500 transition-all shadow-sm';
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
            p.className = 'text-sm text-amber-700 mt-4 p-3 bg-amber-50 rounded-xl border border-amber-200';
            p.innerHTML = `<i class="fas fa-info-circle mr-1"></i> ${data.mensagem}`;
            opcoesContainer.appendChild(p);
        }

        this.abrirModal('modal-pergunta');
    }

    async enviarResposta() {
        const resposta = document.getElementById('resposta-usuario').value || this.tipoPeca;

        this.fecharModal('modal-pergunta');
        this.resetarStatusAgentes();
        this.atualizarStatusAgente(1, 'concluido');
        this.mostrarLoading('Continuando processamento...', 2);

        try {
            // Usa SSE para streaming em tempo real
            const response = await fetch(`${API_URL}/processar-stream`, {
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

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Erro ao processar');
            }

            // Processa o stream SSE
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n\n');
                buffer = lines.pop() || '';

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.slice(6));
                            this.processarEventoStream(data);
                        } catch (e) {
                            console.warn('Erro ao parsear evento SSE:', e);
                        }
                    }
                }
            }

        } catch (error) {
            this.mostrarErro(error.message);
            this.esconderLoading();
        }
    }

    // ==========================================
    // NOVO: Editor Interativo com Chat
    // ==========================================

    exibirEditor(data) {
        this.tipoPeca = data.tipo_peca;
        this.geracaoId = data.geracao_id;
        
        // Garante que o markdown é uma string limpa
        let markdown = data.minuta_markdown || '*Conteúdo não disponível*';
        
        // Se vier como string JSON escapada, desescapa
        if (typeof markdown === 'string') {
            // Remove possíveis escapes extras de JSON
            try {
                // Tenta parsear caso seja JSON string aninhada
                if (markdown.startsWith('"') && markdown.endsWith('"')) {
                    markdown = JSON.parse(markdown);
                }
            } catch (e) {
                // Mantém como está se não for JSON
            }
        }
        
        this.minutaMarkdown = markdown;
        this.historicoChat = [];

        // Atualiza título com tipo da peça e CNJ
        document.getElementById('editor-tipo-peca').textContent = this.formatarOpcao(data.tipo_peca);
        document.getElementById('editor-cnj').textContent = this.numeroCNJ ? `• ${this.numeroCNJ}` : '';

        // Renderiza a minuta em markdown
        this.renderizarMinuta();

        // Reseta o chat
        this.resetarChat();

        // Abre o modal do editor
        this.abrirModal('modal-editor');
        
        // Atualiza histórico recente
        this.carregarHistoricoRecente();
    }

    renderizarMinuta() {
        const container = document.getElementById('minuta-content');
        
        // Debug
        console.log('📄 Markdown a renderizar:', this.minutaMarkdown?.substring(0, 200));

        // Usa marked.js para renderizar o markdown
        if (typeof marked !== 'undefined') {
            // Configura o marked para quebras de linha
            marked.setOptions({
                breaks: true,  // Converte \n em <br>
                gfm: true      // GitHub Flavored Markdown
            });
            container.innerHTML = marked.parse(this.minutaMarkdown || '');
        } else {
            // Fallback simples se marked não estiver disponível
            container.innerHTML = this.minutaMarkdown
                .replace(/## (.*)/g, '<h2>$1</h2>')
                .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                .replace(/\*(.*?)\*/g, '<em>$1</em>')
                .replace(/\n/g, '<br>');
        }

        // Atualiza status
        document.getElementById('minuta-status').textContent = 'Atualizado agora';
    }

    resetarChat() {
        const chatContainer = document.getElementById('chat-messages');
        chatContainer.innerHTML = `
            <div class="flex gap-3">
                <div class="w-8 h-8 bg-gradient-to-br from-primary-500 to-primary-600 rounded-full flex items-center justify-center flex-shrink-0">
                    <i class="fas fa-robot text-white text-xs"></i>
                </div>
                <div class="chat-bubble-ai px-4 py-3 max-w-[85%]">
                    <p class="text-sm text-gray-700">
                        Olá! Sou o assistente de edição. Você pode me pedir para fazer alterações na minuta, como:
                    </p>
                    <ul class="text-xs text-gray-500 mt-2 space-y-1">
                        <li>• "Adicione um argumento sobre prescrição"</li>
                        <li>• "Mude o tom do item II para ser mais assertivo"</li>
                        <li>• "Inclua jurisprudência do STJ"</li>
                    </ul>
                </div>
            </div>
        `;
        document.getElementById('chat-input').value = '';
    }

    async enviarMensagemChat() {
        const input = document.getElementById('chat-input');
        const mensagem = input.value.trim();

        if (!mensagem || this.isProcessingEdit) return;

        input.value = '';
        this.isProcessingEdit = true;

        // Adiciona mensagem do usuário
        this.adicionarMensagemChat('user', mensagem);

        // Mostra indicador de digitação
        this.mostrarTypingIndicator();

        try {
            const response = await fetch(`${API_URL}/editar-minuta`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.getToken()}`
                },
                body: JSON.stringify({
                    minuta_atual: this.minutaMarkdown,
                    mensagem: mensagem,
                    historico: this.historicoChat
                })
            });

            const data = await response.json();

            this.esconderTypingIndicator();

            if (data.status === 'sucesso') {
                // Atualiza a minuta
                this.minutaMarkdown = data.minuta_markdown;
                this.renderizarMinuta();

                // Adiciona histórico
                this.historicoChat.push({ role: 'user', content: mensagem });
                this.historicoChat.push({ role: 'assistant', content: 'Minuta atualizada com sucesso.' });

                // Adiciona confirmação no chat
                this.adicionarMensagemChat('ai', 'Pronto! Atualizei a minuta conforme solicitado. Veja as alterações na visualização ao lado.', true);

                // Destaca visualmente a minuta
                this.destacarMinuta();

                // Salvamento automático
                this.salvarMinutaAuto();

            } else {
                this.adicionarMensagemChat('ai', `Desculpe, encontrei um problema: ${data.mensagem}`, false);
            }

        } catch (error) {
            this.esconderTypingIndicator();
            this.adicionarMensagemChat('ai', `Erro ao processar: ${error.message}`, false);
        } finally {
            this.isProcessingEdit = false;
        }
    }

    adicionarMensagemChat(tipo, conteudo, sucesso = true, indice = null) {
        const chatContainer = document.getElementById('chat-messages');
        
        // Calcula índice se não fornecido
        if (indice === null) {
            indice = this.historicoChat.length;
        }

        const msgDiv = document.createElement('div');
        msgDiv.className = tipo === 'user' ? 'flex gap-3 justify-end group' : 'flex gap-3 group';
        msgDiv.dataset.chatIndex = indice;

        if (tipo === 'user') {
            msgDiv.innerHTML = `
                <button onclick="app.deletarMensagemChat(${indice})" 
                    class="opacity-0 group-hover:opacity-100 p-1 text-gray-300 hover:text-red-500 transition-all self-center"
                    title="Remover mensagem">
                    <i class="fas fa-times text-xs"></i>
                </button>
                <div class="chat-bubble-user px-4 py-3 max-w-[85%]">
                    <p class="text-sm text-white">${this.escapeHtml(conteudo)}</p>
                </div>
                <div class="w-8 h-8 bg-gray-200 rounded-full flex items-center justify-center flex-shrink-0">
                    <i class="fas fa-user text-gray-500 text-xs"></i>
                </div>
            `;
        } else {
            const iconClass = sucesso ? 'fa-check-circle text-green-500' : 'fa-exclamation-circle text-red-500';
            msgDiv.innerHTML = `
                <div class="w-8 h-8 bg-gradient-to-br from-primary-500 to-primary-600 rounded-full flex items-center justify-center flex-shrink-0">
                    <i class="fas fa-robot text-white text-xs"></i>
                </div>
                <div class="chat-bubble-ai px-4 py-3 max-w-[85%]">
                    <p class="text-sm text-gray-700">
                        ${sucesso ? `<i class="fas ${iconClass} mr-1"></i>` : `<i class="fas ${iconClass} mr-1"></i>`}
                        ${this.escapeHtml(conteudo)}
                    </p>
                </div>
                <button onclick="app.deletarMensagemChat(${indice})" 
                    class="opacity-0 group-hover:opacity-100 p-1 text-gray-300 hover:text-red-500 transition-all self-center"
                    title="Remover mensagem">
                    <i class="fas fa-times text-xs"></i>
                </button>
            `;
        }

        chatContainer.appendChild(msgDiv);
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    deletarMensagemChat(indice) {
        // Remove do histórico (remove par user+assistant)
        const startIdx = Math.floor(indice / 2) * 2;
        this.historicoChat.splice(startIdx, 2);
        
        // Re-renderiza o chat
        this.renderizarChatHistorico();
        
        // Salva automaticamente
        this.salvarMinutaAuto();
        
        this.showToast('Mensagem removida', 'success');
    }

    limparTodoHistoricoChat() {
        if (this.historicoChat.length === 0) {
            this.showToast('Histórico já está vazio', 'warning');
            return;
        }
        
        if (!confirm('Tem certeza que deseja limpar todo o histórico do chat?')) {
            return;
        }
        
        this.historicoChat = [];
        this.resetarChat();
        
        // Salva automaticamente
        this.salvarMinutaAuto();
        
        this.showToast('Histórico do chat limpo', 'success');
    }

    mostrarTypingIndicator() {
        const chatContainer = document.getElementById('chat-messages');
        const typingDiv = document.createElement('div');
        typingDiv.id = 'typing-indicator';
        typingDiv.className = 'flex gap-3';
        typingDiv.innerHTML = `
            <div class="w-8 h-8 bg-gradient-to-br from-primary-500 to-primary-600 rounded-full flex items-center justify-center flex-shrink-0">
                <i class="fas fa-robot text-white text-xs"></i>
            </div>
            <div class="chat-bubble-ai typing-indicator">
                <span></span>
                <span></span>
                <span></span>
            </div>
        `;
        chatContainer.appendChild(typingDiv);
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    esconderTypingIndicator() {
        const indicator = document.getElementById('typing-indicator');
        if (indicator) indicator.remove();
    }

    destacarMinuta() {
        const container = document.getElementById('minuta-container');
        container.classList.add('pulse-glow');
        setTimeout(() => container.classList.remove('pulse-glow'), 2000);
    }

    async copiarMinuta() {
        try {
            // Copia o texto markdown
            await navigator.clipboard.writeText(this.minutaMarkdown);
            this.showToast('Minuta copiada para a área de transferência!', 'success');

            // Feedback visual no botão
            const btn = document.getElementById('btn-copiar-minuta');
            const originalHTML = btn.innerHTML;
            btn.innerHTML = '<i class="fas fa-check"></i> Copiado!';
            setTimeout(() => btn.innerHTML = originalHTML, 2000);

        } catch (error) {
            this.showToast('Erro ao copiar minuta', 'error');
        }
    }

    async downloadDocx() {
        if (!this.minutaMarkdown) {
            this.showToast('Nenhuma minuta para exportar', 'error');
            return;
        }

        const btn = document.getElementById('btn-download-docx');
        const originalHTML = btn.innerHTML;

        try {
            // Mostra loading no botão
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Gerando...';
            btn.disabled = true;

            // Chama API para converter markdown para DOCX
            const response = await fetch(`${API_URL}/exportar-docx`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.getToken()}`
                },
                body: JSON.stringify({
                    markdown: this.minutaMarkdown,
                    numero_cnj: this.numeroCNJ,
                    tipo_peca: this.tipoPeca
                })
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Erro ao gerar documento');
            }

            const data = await response.json();

            if (data.status === 'sucesso' && data.url_download) {
                // Faz download do arquivo
                const downloadUrl = `${data.url_download}?token=${encodeURIComponent(this.getToken())}`;
                
                // Cria link temporário para download
                const link = document.createElement('a');
                link.href = downloadUrl;
                link.download = data.filename || 'peca_juridica.docx';
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);

                this.showToast('Download iniciado!', 'success');

                // Feedback visual de sucesso
                btn.innerHTML = '<i class="fas fa-check"></i> Baixado!';
                setTimeout(() => {
                    btn.innerHTML = originalHTML;
                    btn.disabled = false;
                }, 2000);
            } else {
                throw new Error(data.mensagem || 'Erro desconhecido');
            }

        } catch (error) {
            console.error('Erro ao baixar DOCX:', error);
            this.showToast(`Erro: ${error.message}`, 'error');
            btn.innerHTML = originalHTML;
            btn.disabled = false;
        }
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // ==========================================
    // Histórico
    // ==========================================

    async carregarHistoricoRecente() {
        const container = document.getElementById('historico-cards');
        
        try {
            const response = await fetch(`${API_URL}/historico`, {
                headers: { 'Authorization': `Bearer ${this.getToken()}` }
            });

            if (!response.ok) throw new Error('Erro ao carregar');

            const historico = await response.json();

            if (historico.length === 0) {
                container.innerHTML = `
                    <div class="text-center py-8 text-gray-400">
                        <i class="fas fa-file-alt text-4xl mb-3 opacity-50"></i>
                        <p class="text-sm">Nenhuma peça gerada ainda</p>
                        <p class="text-xs mt-1">Use o formulário acima para gerar sua primeira peça</p>
                    </div>
                `;
                return;
            }

            // Mostra apenas os 5 mais recentes na tela inicial
            const recentes = historico.slice(0, 5);

            container.innerHTML = recentes.map(item => `
                <div class="flex items-center gap-4 p-4 border border-gray-100 rounded-xl hover:bg-primary-50 hover:border-primary-300 transition-all cursor-pointer group"
                     onclick="app.abrirGeracao(${item.id})">
                    <div class="w-12 h-12 bg-gradient-to-br from-purple-100 to-indigo-100 rounded-xl flex items-center justify-center group-hover:from-purple-200 group-hover:to-indigo-200 transition-colors">
                        <i class="fas fa-file-alt text-purple-600"></i>
                    </div>
                    <div class="flex-1 min-w-0">
                        <p class="font-medium text-gray-800 truncate group-hover:text-primary-700">${item.cnj}</p>
                        <p class="text-sm text-primary-600 font-medium">${this.formatarOpcao(item.tipo_peca)}</p>
                    </div>
                    <div class="text-right flex-shrink-0">
                        <p class="text-xs text-gray-400">${new Date(item.data).toLocaleDateString('pt-BR')}</p>
                        <p class="text-xs text-gray-300">${new Date(item.data).toLocaleTimeString('pt-BR', {hour: '2-digit', minute: '2-digit'})}</p>
                    </div>
                    <button onclick="event.stopPropagation(); app.deletarHistorico(${item.id})"
                        class="opacity-0 group-hover:opacity-100 p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-all"
                        title="Excluir do histórico">
                        <i class="fas fa-trash-alt text-sm"></i>
                    </button>
                    <i class="fas fa-chevron-right text-gray-300 group-hover:text-primary-500 transition-colors"></i>
                </div>
            `).join('');

            // Se tem mais que 5, mostra indicador
            if (historico.length > 5) {
                container.innerHTML += `
                    <div class="text-center py-2">
                        <button onclick="toggleHistorico()" class="text-sm text-primary-600 hover:text-primary-700 font-medium">
                            Ver mais ${historico.length - 5} peças <i class="fas fa-arrow-right ml-1"></i>
                        </button>
                    </div>
                `;
            }

        } catch (error) {
            container.innerHTML = `
                <div class="text-center py-4 text-red-500">
                    <i class="fas fa-exclamation-circle mr-2"></i>
                    Erro ao carregar histórico
                </div>
            `;
        }
    }

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
                <div class="border border-gray-100 rounded-xl p-3 mb-2 hover:bg-primary-50 hover:border-primary-300 transition-all cursor-pointer shadow-sm group"
                     onclick="app.abrirGeracao(${item.id})">
                    <div class="flex items-center justify-between">
                        <div class="flex-1">
                            <p class="font-medium text-sm text-gray-800 group-hover:text-primary-700">${item.cnj}</p>
                            <p class="text-xs text-primary-600 font-medium">${this.formatarOpcao(item.tipo_peca)}</p>
                            <p class="text-xs text-gray-400 mt-1">${new Date(item.data).toLocaleDateString('pt-BR')}</p>
                        </div>
                        <button onclick="event.stopPropagation(); app.deletarHistorico(${item.id})"
                            class="opacity-0 group-hover:opacity-100 p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-all mr-2"
                            title="Excluir do histórico">
                            <i class="fas fa-trash-alt text-sm"></i>
                        </button>
                        <i class="fas fa-chevron-right text-gray-300 group-hover:text-primary-500 transition-colors"></i>
                    </div>
                </div>
            `).join('');

        } catch (error) {
            lista.innerHTML = '<p class="text-red-500 text-sm text-center py-8">Erro ao carregar histórico</p>';
        }
    }

    async deletarHistorico(geracaoId) {
        if (!confirm('Tem certeza que deseja excluir esta peça do histórico?')) {
            return;
        }

        try {
            const response = await fetch(`${API_URL}/historico/${geracaoId}`, {
                method: 'DELETE',
                headers: { 'Authorization': `Bearer ${this.getToken()}` }
            });

            if (!response.ok) throw new Error('Erro ao excluir');

            this.showToast('Peça removida do histórico', 'success');
            
            // Recarrega os históricos
            this.carregarHistoricoRecente();
            this.carregarHistorico();

        } catch (error) {
            this.showToast(`Erro: ${error.message}`, 'error');
        }
    }

    async limparTodoHistorico() {
        if (!confirm('Tem certeza que deseja excluir TODO o histórico de peças geradas? Esta ação não pode ser desfeita.')) {
            return;
        }

        try {
            const response = await fetch(`${API_URL}/historico`, {
                headers: { 'Authorization': `Bearer ${this.getToken()}` }
            });

            if (!response.ok) throw new Error('Erro ao carregar');

            const historico = await response.json();

            // Deleta cada item
            for (const item of historico) {
                await fetch(`${API_URL}/historico/${item.id}`, {
                    method: 'DELETE',
                    headers: { 'Authorization': `Bearer ${this.getToken()}` }
                });
            }

            this.showToast('Todo histórico foi excluído', 'success');
            
            // Recarrega os históricos
            this.carregarHistoricoRecente();
            this.carregarHistorico();

        } catch (error) {
            this.showToast(`Erro: ${error.message}`, 'error');
        }
    }

    async abrirGeracao(geracaoId) {
        try {
            const response = await fetch(`${API_URL}/historico/${geracaoId}`, {
                headers: { 'Authorization': `Bearer ${this.getToken()}` }
            });

            if (!response.ok) throw new Error('Erro ao carregar geração');

            const data = await response.json();

            // Carrega no editor
            this.geracaoId = data.id;
            this.tipoPeca = data.tipo_peca;
            this.numeroCNJ = data.cnj;

            // Processa o markdown
            let markdown = data.minuta_markdown || '*Conteúdo não disponível*';
            
            // Se vier como string JSON escapada, desescapa
            if (typeof markdown === 'string') {
                try {
                    if (markdown.startsWith('"') && markdown.endsWith('"')) {
                        markdown = JSON.parse(markdown);
                    }
                } catch (e) {
                    // Mantém como está
                }
            }
            
            this.minutaMarkdown = markdown;
            
            // Carrega histórico de chat se existir
            this.historicoChat = data.historico_chat || [];

            // Atualiza UI
            document.getElementById('editor-tipo-peca').textContent = this.formatarOpcao(data.tipo_peca);
            document.getElementById('editor-cnj').textContent = data.cnj ? `• ${data.cnj}` : '';
            this.renderizarMinuta();
            
            // Renderiza chat com histórico
            this.renderizarChatHistorico();
            
            this.abrirModal('modal-editor');

            // Fecha painel de histórico (se estiver aberto)
            const painel = document.getElementById('painel-historico');
            if (!painel.classList.contains('translate-x-full')) {
                toggleHistorico();
            }

            this.showToast('Peça carregada do histórico', 'success');

        } catch (error) {
            this.showToast(`Erro: ${error.message}`, 'error');
        }
    }
    
    renderizarChatHistorico() {
        const chatContainer = document.getElementById('chat-messages');
        
        // Mensagem inicial do assistente
        let html = `
            <div class="flex gap-3">
                <div class="w-8 h-8 bg-gradient-to-br from-primary-500 to-primary-600 rounded-full flex items-center justify-center flex-shrink-0">
                    <i class="fas fa-robot text-white text-xs"></i>
                </div>
                <div class="chat-bubble-ai px-4 py-3 max-w-[85%]">
                    <p class="text-sm text-gray-700">
                        Olá! Sou o assistente de edição. Você pode me pedir para fazer alterações na minuta.
                    </p>
                </div>
            </div>
        `;
        
        // Renderiza histórico se existir
        if (this.historicoChat && this.historicoChat.length > 0) {
            for (let i = 0; i < this.historicoChat.length; i++) {
                const msg = this.historicoChat[i];
                if (msg.role === 'user') {
                    html += `
                        <div class="flex gap-3 justify-end group" data-chat-index="${i}">
                            <button onclick="app.deletarMensagemChat(${i})" 
                                class="opacity-0 group-hover:opacity-100 p-1 text-gray-300 hover:text-red-500 transition-all self-center"
                                title="Remover mensagem">
                                <i class="fas fa-times text-xs"></i>
                            </button>
                            <div class="chat-bubble-user px-4 py-3 max-w-[85%]">
                                <p class="text-sm text-white">${this.escapeHtml(msg.content)}</p>
                            </div>
                            <div class="w-8 h-8 bg-gray-200 rounded-full flex items-center justify-center flex-shrink-0">
                                <i class="fas fa-user text-gray-500 text-xs"></i>
                            </div>
                        </div>
                    `;
                } else {
                    html += `
                        <div class="flex gap-3 group" data-chat-index="${i}">
                            <div class="w-8 h-8 bg-gradient-to-br from-primary-500 to-primary-600 rounded-full flex items-center justify-center flex-shrink-0">
                                <i class="fas fa-robot text-white text-xs"></i>
                            </div>
                            <div class="chat-bubble-ai px-4 py-3 max-w-[85%]">
                                <p class="text-sm text-gray-700">
                                    <i class="fas fa-check-circle text-green-500 mr-1"></i>
                                    ${this.escapeHtml(msg.content)}
                                </p>
                            </div>
                            <button onclick="app.deletarMensagemChat(${i})" 
                                class="opacity-0 group-hover:opacity-100 p-1 text-gray-300 hover:text-red-500 transition-all self-center"
                                title="Remover mensagem">
                                <i class="fas fa-times text-xs"></i>
                            </button>
                        </div>
                    `;
                }
            }
        }
        
        chatContainer.innerHTML = html;
        chatContainer.scrollTop = chatContainer.scrollHeight;
        document.getElementById('chat-input').value = '';
    }

    async salvarMinutaAuto() {
        if (!this.geracaoId || !this.minutaMarkdown) return;

        try {
            const response = await fetch(`${API_URL}/historico/${this.geracaoId}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.getToken()}`
                },
                body: JSON.stringify({
                    minuta_markdown: this.minutaMarkdown,
                    historico_chat: this.historicoChat
                })
            });

            if (!response.ok) throw new Error('Erro ao salvar');

            // Atualiza status discretamente
            document.getElementById('minuta-status').textContent = 'Salvo automaticamente';

        } catch (error) {
            console.error('Erro ao salvar automaticamente:', error);
        }
    }

    // ==========================================
    // Feedback
    // ==========================================

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

    // ==========================================
    // Utilitários
    // ==========================================

    // Controlador para cancelar requisições
    abortController = null;

    mostrarLoading(mensagem, agente = null) {
        document.getElementById('progresso-mensagem').textContent = mensagem;
        document.getElementById('modal-progresso').classList.remove('hidden');
        document.getElementById('btn-gerar').disabled = true;

        // Atualiza barra de progresso
        let progresso = 0;
        if (agente === 1) progresso = 10;
        else if (agente === 2) progresso = 40;
        else if (agente === 3) progresso = 70;
        document.getElementById('progresso-barra').style.width = `${progresso}%`;

        // Atualiza status dos agentes
        if (agente === 1) {
            this.atualizarStatusAgente(1, 'ativo');
        } else if (agente === 2) {
            this.atualizarStatusAgente(1, 'concluido');
            this.atualizarStatusAgente(2, 'ativo');
        } else if (agente === 3) {
            this.atualizarStatusAgente(1, 'concluido');
            this.atualizarStatusAgente(2, 'concluido');
            this.atualizarStatusAgente(3, 'ativo');
        }
    }

    atualizarStatusAgente(agente, status) {
        const badge = document.getElementById(`agente${agente}-badge`);
        const container = document.getElementById(`agente${agente}-status`);
        const iconDiv = document.getElementById(`agente${agente}-icon`);

        if (status === 'ativo') {
            badge.textContent = 'Processando...';
            badge.className = 'text-xs px-3 py-1 rounded-full bg-blue-100 text-blue-700 font-medium animate-pulse';
            iconDiv.className = 'w-8 h-8 rounded-full bg-blue-500 flex items-center justify-center';
            iconDiv.innerHTML = '<i class="fas fa-spinner fa-spin text-white text-sm"></i>';
            container.className = 'flex items-center gap-3 p-3 rounded-xl bg-blue-50 border border-blue-200';
            
            // Atualiza progresso
            let progresso = agente === 1 ? 20 : agente === 2 ? 50 : 80;
            document.getElementById('progresso-barra').style.width = `${progresso}%`;
        } else if (status === 'concluido') {
            badge.textContent = 'Concluído ✓';
            badge.className = 'text-xs px-3 py-1 rounded-full bg-green-100 text-green-700 font-medium';
            iconDiv.className = 'w-8 h-8 rounded-full bg-green-500 flex items-center justify-center';
            iconDiv.innerHTML = '<i class="fas fa-check text-white text-sm"></i>';
            container.className = 'flex items-center gap-3 p-3 rounded-xl bg-green-50 border border-green-200';
        } else if (status === 'erro') {
            badge.textContent = 'Erro';
            badge.className = 'text-xs px-3 py-1 rounded-full bg-red-100 text-red-700 font-medium';
            iconDiv.className = 'w-8 h-8 rounded-full bg-red-500 flex items-center justify-center';
            iconDiv.innerHTML = '<i class="fas fa-times text-white text-sm"></i>';
            container.className = 'flex items-center gap-3 p-3 rounded-xl bg-red-50 border border-red-200';
        }
    }

    resetarStatusAgentes() {
        [1, 2, 3].forEach(agente => {
            const badge = document.getElementById(`agente${agente}-badge`);
            const container = document.getElementById(`agente${agente}-status`);
            const iconDiv = document.getElementById(`agente${agente}-icon`);

            badge.textContent = 'Aguardando';
            badge.className = 'text-xs px-3 py-1 rounded-full bg-gray-100 text-gray-500 font-medium';
            iconDiv.className = 'w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center';
            container.className = 'flex items-center gap-3 p-3 rounded-xl bg-gray-50 border border-gray-100';

            const icons = ['fa-download', 'fa-brain', 'fa-file-alt'];
            iconDiv.innerHTML = `<i class="fas ${icons[agente - 1]} text-gray-400 text-sm"></i>`;
        });
        
        document.getElementById('progresso-barra').style.width = '0%';
    }

    esconderLoading() {
        document.getElementById('modal-progresso').classList.add('hidden');
        document.getElementById('btn-gerar').disabled = false;
        this.resetarStatusAgentes();
    }

    cancelarGeracao() {
        if (this.abortController) {
            this.abortController.abort();
            this.abortController = null;
        }
        this.esconderLoading();
        this.showToast('Geração cancelada', 'warning');
    }

    mostrarErro(mensagem) {
        document.getElementById('erro-mensagem').textContent = mensagem;
        document.getElementById('toast-erro').classList.remove('hidden');
        
        // Auto-hide após 10 segundos
        setTimeout(() => {
            document.getElementById('toast-erro').classList.add('hidden');
        }, 10000);
    }

    esconderErro() {
        document.getElementById('toast-erro').classList.add('hidden');
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
        this.geracaoId = null;
        this.notaSelecionada = null;
        this.minutaMarkdown = null;
        this.historicoChat = [];

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

function fecharModalEditor() {
    document.getElementById('modal-editor').classList.add('hidden');
    // Opcionalmente abrir modal de feedback
    // document.getElementById('modal-feedback').classList.remove('hidden');
}

// Inicializar app
let app;
document.addEventListener('DOMContentLoaded', () => {
    app = new GeradorPecasApp();
});
