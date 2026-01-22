// app.js - Gerador de Peças Jurídicas
// Frontend JavaScript com Chat Interativo para Edição

const API_URL = '/gerador-pecas/api';
const ADMIN_API_URL = '/admin/api/prompts-modulos';

// =====================================================
// FEATURE FLAGS - Configuração de funcionalidades
// =====================================================
// Para ativar/desativar funcionalidades temporariamente
const FEATURE_FLAGS = {
    // Assuntos (Subcategorias de Conteúdo) - funcionalidade desabilitada
    SUBCATEGORIAS_ENABLED: false,
};
// =====================================================

class GeradorPecasApp {
    constructor() {
        this.numeroCNJ = null;
        this.tipoPeca = null;
        this.geracaoId = null;
        this.notaSelecionada = null;
        this.isNovaGeracao = false; // Flag para controlar se deve mostrar feedback

        // Dados para o editor interativo
        this.minutaMarkdown = null;
        this.historicoChat = [];
        this.isProcessingEdit = false;

        // Modo de entrada: 'cnj' ou 'pdf'
        this.modoEntrada = 'cnj';
        this.arquivosPdf = [];

        // Observação do usuário para a IA
        this.observacaoUsuario = null;

        // Grupo e subcategorias de prompts
        this.groupId = null;
        this.subcategoriaIds = [];
        this.gruposDisponiveis = [];
        this.subcategoriasDisponiveis = [];
        this.requiresGroupSelection = false;
        this.isAdmin = false;

        // Dados para histórico de versões
        this.versoesLista = [];
        this.versaoSelecionada = null;
        this.painelVersoesAberto = false;

        // Streaming de geração em tempo real
        this.streamingContent = '';
        this.isStreaming = false;

        // Flag de detecção automática de tipo de peça
        this.permiteAutoDetection = false; // Por padrão desabilitado (fail-safe)

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

            // Verifica se é admin
            const userData = await response.json();
            this.isAdmin = userData.role === 'admin';

            // Carrega histórico recente após autenticação
            this.carregarHistoricoRecente();

            // Carrega tipos de peça dinamicamente
            this.carregarTiposPeca();

            // Carrega grupos e subcategorias de prompts
            this.carregarGruposDisponiveis();
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

            // Armazena flag de detecção automática
            this.permiteAutoDetection = data.permite_auto === true;

            // Limpa todas as opções
            select.innerHTML = '';

            // Adiciona opção de auto-detecção apenas se permitido
            if (this.permiteAutoDetection) {
                const autoOption = document.createElement('option');
                autoOption.value = '';
                autoOption.textContent = '🤖 Detectar automaticamente (IA decide)';
                select.appendChild(autoOption);
            } else {
                // Opção placeholder que força seleção
                const placeholderOption = document.createElement('option');
                placeholderOption.value = '';
                placeholderOption.textContent = '-- Selecione o tipo de peça --';
                placeholderOption.disabled = true;
                placeholderOption.selected = true;
                select.appendChild(placeholderOption);
            }

            // Adiciona tipos do banco
            data.tipos.forEach(tipo => {
                const option = document.createElement('option');
                option.value = tipo.valor;
                option.textContent = tipo.label;
                select.appendChild(option);
            });

            // Atualiza texto de ajuda
            const helpText = select.parentElement.querySelector('p.text-xs');
            if (helpText) {
                if (this.permiteAutoDetection) {
                    helpText.textContent = 'A IA analisa os documentos e decide qual peça gerar, ou selecione manualmente';
                } else {
                    helpText.innerHTML = '<i class="fas fa-exclamation-circle text-amber-500 mr-1"></i>Seleção obrigatória do tipo de peça';
                }
            }
        } catch (error) {
            console.error('Erro ao carregar tipos de peça:', error);
        }
    }


    async carregarGruposDisponiveis() {
        const select = document.getElementById('grupo-principal');
        const hint = document.getElementById('grupo-hint');
        const grupoContainer = document.getElementById('grupo-container');

        if (!select) {
            return;
        }

        try {
            const response = await fetch(`${API_URL}/grupos-disponiveis`, {
                headers: { 'Authorization': `Bearer ${this.getToken()}` }
            });

            if (!response.ok) return;

            const data = await response.json();
            this.gruposDisponiveis = data.grupos || [];
            this.requiresGroupSelection = !!data.requires_selection;

            select.innerHTML = '';

            if (this.gruposDisponiveis.length === 0) {
                select.disabled = true;
                const option = document.createElement('option');
                option.value = '';
                option.textContent = 'Nenhum grupo disponível';
                select.appendChild(option);
                if (hint) {
                    hint.textContent = 'Nenhum grupo ativo disponível para o seu usuário.';
                }
                this.groupId = null;
                this.subcategoriaIds = [];
                this.subcategoriasDisponiveis = [];
                this.renderSubcategorias([]);
                return;
            }

            // Mostra seletor de grupo apenas quando há múltiplos grupos
            if (this.requiresGroupSelection) {
                if (grupoContainer) grupoContainer.classList.remove('hidden');
                const option = document.createElement('option');
                option.value = '';
                option.textContent = 'Selecione o grupo...';
                select.appendChild(option);
                select.disabled = false;

                const defaultGroup = this.gruposDisponiveis.find(
                    (grupo) => grupo.id === data.default_group_id
                );
                if (hint) {
                    hint.textContent = defaultGroup
                        ? `Grupo padrão: ${defaultGroup.nome}. Selecione o grupo para continuar.`
                        : 'Selecione o grupo de conteúdo antes de gerar a peça.';
                }
            } else {
                // Esconde o seletor quando há apenas 1 grupo
                if (grupoContainer) grupoContainer.classList.add('hidden');
                select.disabled = true;
            }

            this.gruposDisponiveis.forEach((grupo) => {
                const option = document.createElement('option');
                option.value = grupo.id;
                option.textContent = grupo.nome;
                select.appendChild(option);
            });

            if (!this.requiresGroupSelection && this.gruposDisponiveis.length === 1) {
                this.groupId = this.gruposDisponiveis[0].id;
                select.value = this.groupId;
                await this.carregarSubcategorias(this.groupId);
            } else {
                this.groupId = null;
                this.subcategoriaIds = [];
                this.subcategoriasDisponiveis = [];
                this.renderSubcategorias([]);
            }
        } catch (error) {
            console.error('Erro ao carregar grupos:', error);
        }
    }

    async carregarSubcategorias(groupId) {
        // Feature flag: Subcategorias
        if (!FEATURE_FLAGS.SUBCATEGORIAS_ENABLED) {
            this.subcategoriasDisponiveis = [];
            this.renderSubcategorias([]);
            return;
        }

        if (!groupId) {
            this.subcategoriasDisponiveis = [];
            this.renderSubcategorias([]);
            return;
        }

        try {
            const response = await fetch(`${ADMIN_API_URL}/grupos/${groupId}/subcategorias`, {
                headers: { 'Authorization': `Bearer ${this.getToken()}` }
            });

            if (!response.ok) {
                this.subcategoriasDisponiveis = [];
                this.renderSubcategorias([]);
                return;
            }

            const data = await response.json();
            this.subcategoriasDisponiveis = data || [];
            this.renderSubcategorias(this.subcategoriasDisponiveis);
        } catch (error) {
            console.error('Erro ao carregar subcategorias:', error);
            this.subcategoriasDisponiveis = [];
            this.renderSubcategorias([]);
        }
    }

    renderSubcategorias(subcategorias) {
        const container = document.getElementById('subcategoria-container');
        const options = document.getElementById('subcategoria-opcoes');
        const hint = document.getElementById('subcategoria-hint');

        if (!container || !options) {
            return;
        }

        // Feature flag: Subcategorias (liberado para todos os usuários)
        if (!FEATURE_FLAGS.SUBCATEGORIAS_ENABLED) {
            container.classList.add('hidden');
            this.subcategoriaIds = [];
            return;
        }

        if (!this.groupId) {
            container.classList.add('hidden');
            return;
        }

        container.classList.remove('hidden');
        options.innerHTML = '';
        this.subcategoriaIds = [];

        options.appendChild(this.criarOpcaoSubcategoria('all', 'Geral / Todos', true));

        if (subcategorias && subcategorias.length > 0) {
            if (hint) {
                hint.textContent = 'Selecione um ou mais assuntos para filtrar os prompts de conteúdo.';
            }
            subcategorias.forEach((subcategoria) => {
                options.appendChild(
                    this.criarOpcaoSubcategoria(subcategoria.id, subcategoria.nome, false)
                );
            });
        } else if (hint) {
            hint.textContent = 'Sem assuntos cadastrados. Usando Geral/Todos.';
        }

        options.querySelectorAll('input[name="subcategoria"]').forEach((input) => {
            input.addEventListener('change', (event) => this.handleSubcategoriaChange(event));
        });
    }

    criarOpcaoSubcategoria(valor, label, checked) {
        const wrapper = document.createElement('label');
        wrapper.className = 'inline-flex items-center gap-2 px-3 py-2 rounded-full border border-gray-200 text-sm text-gray-700 bg-white hover:border-primary-300 hover:bg-primary-50 cursor-pointer transition-all';

        const input = document.createElement('input');
        input.type = 'checkbox';
        input.name = 'subcategoria';
        input.value = String(valor);
        input.checked = checked;
        input.className = 'h-4 w-4 text-primary-600 rounded border-gray-300';

        const span = document.createElement('span');
        span.textContent = label;

        wrapper.appendChild(input);
        wrapper.appendChild(span);

        return wrapper;
    }

    handleGrupoChange(event) {
        const value = event.target.value;
        if (!value) {
            this.groupId = null;
            this.subcategoriaIds = [];
            this.subcategoriasDisponiveis = [];
            this.renderSubcategorias([]);
            return;
        }

        const parsed = parseInt(value, 10);
        this.groupId = Number.isNaN(parsed) ? null : parsed;
        this.subcategoriaIds = [];
        this.carregarSubcategorias(this.groupId);
    }

    handleSubcategoriaChange(event) {
        const input = event.target;
        const value = input.value;
        const container = document.getElementById('subcategoria-opcoes');
        const allInput = container ? container.querySelector('input[value="all"]') : null;

        if (value === 'all') {
            if (input.checked) {
                this.subcategoriaIds = [];
                if (container) {
                    container.querySelectorAll('input[name="subcategoria"]').forEach((checkbox) => {
                        if (checkbox.value !== 'all') {
                            checkbox.checked = false;
                        }
                    });
                }
            }
            return;
        }

        if (allInput) {
            allInput.checked = false;
        }

        const parsed = parseInt(value, 10);
        if (Number.isNaN(parsed)) {
            return;
        }

        if (input.checked) {
            if (!this.subcategoriaIds.includes(parsed)) {
                this.subcategoriaIds.push(parsed);
            }
        } else {
            this.subcategoriaIds = this.subcategoriaIds.filter((id) => id !== parsed);
            if (this.subcategoriaIds.length === 0 && allInput) {
                allInput.checked = true;
            }
        }
    }

    // ==========================================
    // CRUD Subcategorias
    // ==========================================

    abrirModalNovaSubcategoria() {
        if (!this.groupId) {
            this.showToast('Selecione um grupo primeiro', 'warning');
            return;
        }

        const modal = document.getElementById('modal-subcategoria');
        const form = document.getElementById('form-subcategoria');

        // Limpa o form
        document.getElementById('subcategoria-nome').value = '';
        document.getElementById('subcategoria-slug').value = '';
        document.getElementById('subcategoria-descricao').value = '';

        // Auto-gerar slug ao digitar nome
        const nomeInput = document.getElementById('subcategoria-nome');
        const slugInput = document.getElementById('subcategoria-slug');
        nomeInput.oninput = () => {
            slugInput.value = this.slugify(nomeInput.value);
        };

        // Handler do form
        form.onsubmit = async (e) => {
            e.preventDefault();
            await this.criarSubcategoria();
        };

        // Renderiza lista de subcategorias existentes
        this.renderListaSubcategoriasModal();

        modal.classList.remove('hidden');
    }

    fecharModalSubcategoria() {
        document.getElementById('modal-subcategoria').classList.add('hidden');
    }

    slugify(texto) {
        return texto
            .toLowerCase()
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '')
            .replace(/[^a-z0-9]+/g, '_')
            .replace(/^_|_$/g, '');
    }

    async criarSubcategoria() {
        const nome = document.getElementById('subcategoria-nome').value.trim();
        const slug = document.getElementById('subcategoria-slug').value.trim();
        const descricao = document.getElementById('subcategoria-descricao').value.trim();

        if (!nome || !slug) {
            this.showToast('Nome e slug sao obrigatorios', 'error');
            return;
        }

        try {
            const response = await fetch(`${ADMIN_API_URL}/grupos/${this.groupId}/subcategorias`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${this.getToken()}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ nome, slug, descricao: descricao || null })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Erro ao criar subcategoria');
            }

            this.showToast('Assunto criado com sucesso', 'success');

            // Limpa o form
            document.getElementById('subcategoria-nome').value = '';
            document.getElementById('subcategoria-slug').value = '';
            document.getElementById('subcategoria-descricao').value = '';

            // Atualiza as listas
            await this.carregarSubcategorias(this.groupId);
            this.renderListaSubcategoriasModal();
        } catch (error) {
            console.error('Erro ao criar subcategoria:', error);
            this.showToast(error.message, 'error');
        }
    }

    async deletarSubcategoria(id) {
        if (!confirm('Deseja realmente excluir este assunto?')) {
            return;
        }

        try {
            const response = await fetch(`${ADMIN_API_URL}/subcategorias/${id}`, {
                method: 'DELETE',
                headers: {
                    'Authorization': `Bearer ${this.getToken()}`
                }
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Erro ao excluir subcategoria');
            }

            this.showToast('Assunto excluído', 'success');

            // Atualiza as listas
            await this.carregarSubcategorias(this.groupId);
            this.renderListaSubcategoriasModal();
        } catch (error) {
            console.error('Erro ao excluir subcategoria:', error);
            this.showToast(error.message, 'error');
        }
    }

    renderListaSubcategoriasModal() {
        const container = document.getElementById('lista-subcategorias-modal');
        if (!container) return;

        if (!this.subcategoriasDisponiveis || this.subcategoriasDisponiveis.length === 0) {
            container.innerHTML = '<p class="text-gray-400 text-sm">Nenhum assunto cadastrado.</p>';
            return;
        }

        container.innerHTML = this.subcategoriasDisponiveis.map(sub => `
            <div class="flex items-center justify-between p-2 bg-gray-50 rounded-lg">
                <div>
                    <span class="text-sm font-medium text-gray-700">${sub.nome}</span>
                    <span class="text-xs text-gray-400 ml-2">(${sub.slug})</span>
                </div>
                <button type="button" onclick="app.deletarSubcategoria(${sub.id})"
                    class="p-1 text-red-400 hover:text-red-600 hover:bg-red-50 rounded transition-colors"
                    title="Excluir">
                    <i class="fas fa-trash-alt text-xs"></i>
                </button>
            </div>
        `).join('');
    }

    // ==========================================
    // Modo de Entrada (CNJ ou PDF)
    // ==========================================

    setModoEntrada(modo) {
        this.modoEntrada = modo;
        
        const btnCnj = document.getElementById('btn-modo-cnj');
        const btnPdf = document.getElementById('btn-modo-pdf');
        const modoCnj = document.getElementById('modo-cnj');
        const modoPdf = document.getElementById('modo-pdf');
        
        if (modo === 'cnj') {
            btnCnj.className = 'flex-1 py-2.5 px-4 rounded-lg font-medium transition-all bg-white shadow text-primary-700';
            btnPdf.className = 'flex-1 py-2.5 px-4 rounded-lg font-medium transition-all text-gray-500 hover:text-gray-700';
            modoCnj.classList.remove('hidden');
            modoPdf.classList.add('hidden');
        } else {
            btnPdf.className = 'flex-1 py-2.5 px-4 rounded-lg font-medium transition-all bg-white shadow text-primary-700';
            btnCnj.className = 'flex-1 py-2.5 px-4 rounded-lg font-medium transition-all text-gray-500 hover:text-gray-700';
            modoPdf.classList.remove('hidden');
            modoCnj.classList.add('hidden');
        }
    }

    handleFileSelect(event) {
        const files = Array.from(event.target.files);
        this.adicionarArquivos(files);
    }

    handleDrop(event) {
        event.preventDefault();
        event.currentTarget.classList.remove('border-primary-500', 'bg-primary-50');
        
        const files = Array.from(event.dataTransfer.files).filter(f => f.type === 'application/pdf');
        if (files.length === 0) {
            this.showToast('Apenas arquivos PDF são aceitos', 'error');
            return;
        }
        this.adicionarArquivos(files);
    }

    adicionarArquivos(files) {
        for (const file of files) {
            if (file.type !== 'application/pdf') {
                this.showToast(`Arquivo ignorado (não é PDF): ${file.name}`, 'warning');
                continue;
            }
            // Evita duplicatas
            if (!this.arquivosPdf.find(f => f.name === file.name && f.size === file.size)) {
                this.arquivosPdf.push(file);
            }
        }
        this.atualizarListaArquivos();
    }

    atualizarListaArquivos() {
        const container = document.getElementById('lista-arquivos');
        const lista = document.getElementById('arquivos-lista');
        
        if (this.arquivosPdf.length === 0) {
            container.classList.add('hidden');
            return;
        }
        
        container.classList.remove('hidden');
        lista.innerHTML = this.arquivosPdf.map((file, index) => `
            <div class="flex items-center gap-3 p-3 bg-gray-50 rounded-lg border border-gray-100">
                <div class="w-8 h-8 bg-red-100 rounded-lg flex items-center justify-center">
                    <i class="fas fa-file-pdf text-red-500 text-sm"></i>
                </div>
                <div class="flex-1 min-w-0">
                    <p class="text-sm font-medium text-gray-700 truncate">${this.escapeHtml(file.name)}</p>
                    <p class="text-xs text-gray-400">${this.formatarTamanho(file.size)}</p>
                </div>
                <button type="button" onclick="app.removerArquivo(${index})" 
                    class="p-1 text-gray-400 hover:text-red-500 transition-colors">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        `).join('');
    }

    removerArquivo(index) {
        this.arquivosPdf.splice(index, 1);
        this.atualizarListaArquivos();
    }

    limparArquivos() {
        this.arquivosPdf = [];
        this.atualizarListaArquivos();
        document.getElementById('input-pdfs').value = '';
    }

    formatarTamanho(bytes) {
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    }

    initEventListeners() {
        // Form submit
        document.getElementById('form-processo').addEventListener('submit', (e) => {
            e.preventDefault();
            this.iniciarProcessamento();
        });

        const grupoSelect = document.getElementById('grupo-principal');
        if (grupoSelect) {
            grupoSelect.addEventListener('change', (e) => {
                this.handleGrupoChange(e);
            });
        }

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
        this.tipoPeca = document.getElementById('tipo-peca').value || null;
        this.observacaoUsuario = document.getElementById('observacao-usuario').value.trim() || null;

        // Validação obrigatória do tipo de peça quando detecção automática está desabilitada
        if (!this.permiteAutoDetection && !this.tipoPeca) {
            this.mostrarErro('Selecione obrigatoriamente o tipo de peça.');
            // Foca no select para chamar atenção
            document.getElementById('tipo-peca').focus();
            return;
        }

        if (this.requiresGroupSelection && !this.groupId) {
            this.mostrarErro('Selecione o grupo de conteúdo antes de gerar a peça.');
            return;
        }

        if (!this.groupId) {
            this.mostrarErro('Nenhum grupo de conteúdo disponível para geração.');
            return;
        }

        // Reset estado de streaming para nova geração
        this.streamingContent = '';
        this.isStreaming = false;

        this.esconderErro();
        this.resetarStatusAgentes();
        this.mostrarLoading('Conectando ao servidor...', null);

        try {
            let response;

            if (this.modoEntrada === 'pdf') {
                // Modo PDF: envia arquivos anexados
                if (this.arquivosPdf.length === 0) {
                    throw new Error('Selecione pelo menos um arquivo PDF');
                }

                this.numeroCNJ = 'PDFs Anexados';

                const formData = new FormData();
                for (const file of this.arquivosPdf) {
                    formData.append('arquivos', file);
                }
                if (this.tipoPeca) {
                    formData.append('tipo_peca', this.tipoPeca);
                }
                if (this.observacaoUsuario) {
                    formData.append('observacao_usuario', this.observacaoUsuario);
                }
                if (this.groupId) {
                    formData.append('group_id', this.groupId);
                }
                response = await fetch(`${API_URL}/processar-pdfs-stream`, {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${this.getToken()}`
                    },
                    body: formData
                });
            } else {
                // Modo CNJ: busca no TJ-MS
                this.numeroCNJ = document.getElementById('numero-cnj').value;

                if (!this.numeroCNJ) {
                    throw new Error('Informe o número do processo');
                }

                response = await fetch(`${API_URL}/processar-stream`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${this.getToken()}`
                    },
                    body: JSON.stringify({
                        numero_cnj: this.numeroCNJ,
                        tipo_peca: this.tipoPeca,
                        observacao_usuario: this.observacaoUsuario,
                        group_id: this.groupId
                    })
                });
            }

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
            console.error('Erro na requisição:', error);
            // Trata erros de rede de forma mais amigável
            let mensagemErro = error.message;
            
            if (error.name === 'TypeError' && error.message === 'Failed to fetch') {
                mensagemErro = 'Não foi possível conectar ao servidor. Possíveis causas:\n• Conexão de internet instável\n• A solicitação é muito grande e demorou demais\n• O servidor está temporariamente indisponível\n\nTente novamente ou divida seu pedido em partes menores.';
            } else if (error.name === 'AbortError') {
                mensagemErro = 'A solicitação foi cancelada.';
            } else if (error.message.includes('network') || error.message.includes('Network')) {
                mensagemErro = 'Erro de conexão de rede. Verifique sua internet e tente novamente.';
            } else if (error.message.includes('timeout') || error.message.includes('Timeout')) {
                mensagemErro = 'A solicitação demorou mais que o esperado. Tente novamente ou use um pedido mais simples.';
            }
            
            this.mostrarErro(mensagemErro);
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

                // Conteúdo final (do streaming ou do evento)
                const conteudoFinal = this.isStreaming ? this.streamingContent : data.minuta_markdown;

                if (this.isStreaming) {
                    // Streaming já abriu o editor - apenas finaliza
                    this.finalizarEditorStreaming(data.geracao_id, data.tipo_peca, conteudoFinal);
                    this.esconderLoading();
                    this.showToast('Peça gerada com sucesso!', 'success');
                } else {
                    // Fallback: sem streaming, abre editor normalmente
                    this.finalizarStreaming();
                    setTimeout(() => {
                        this.esconderLoading();
                        this.showToast('Peça gerada com sucesso!', 'success');
                        this.exibirEditor({
                            status: 'sucesso',
                            geracao_id: data.geracao_id,
                            tipo_peca: data.tipo_peca,
                            minuta_markdown: conteudoFinal || data.minuta_markdown
                        });
                    }, 500);
                }
                break;

            case 'erro':
                this.finalizarStreaming();  // Limpa streaming em caso de erro
                this.esconderLoading();
                this.mostrarErro(data.mensagem);
                break;

            case 'info':
                document.getElementById('progresso-mensagem').textContent = data.mensagem;
                break;

            case 'geracao_chunk':
                // Streaming em tempo real: abre o editor e mostra texto sendo gerado
                console.log('🔥 CHUNK RECEBIDO:', data.content?.substring(0, 50));
                try {
                    if (!this.isStreaming) {
                        console.log('🚀 Iniciando streaming - abrindo editor');
                        this.isStreaming = true;
                        this.streamingContent = '';
                        this.abrirEditorStreaming();
                    }
                    this.streamingContent += data.content;
                    this.atualizarEditorStreaming();
                } catch (err) {
                    console.error('❌ Erro no streaming:', err);
                }
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

        // Reset estado de streaming
        this.streamingContent = '';
        this.isStreaming = false;

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

    exibirEditor(data, isNova = true) {
        this.tipoPeca = data.tipo_peca;
        this.geracaoId = data.geracao_id;
        this.isNovaGeracao = isNova;

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

        // Reset estado de versões
        this.versoesLista = [];
        this.versaoSelecionada = null;
        this.painelVersoesAberto = false;
        document.getElementById('painel-versoes').classList.add('hidden');
        document.getElementById('versao-detalhe').classList.add('hidden');
        document.getElementById('versoes-count').classList.add('hidden');

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

        // Carrega contagem de versões (em background)
        this.carregarContagemVersoes();
    }

    async carregarContagemVersoes() {
        if (!this.geracaoId) return;

        try {
            const response = await fetch(`${API_URL}/historico/${this.geracaoId}/versoes`, {
                headers: { 'Authorization': `Bearer ${this.getToken()}` }
            });

            if (!response.ok) return;

            const data = await response.json();

            // Atualiza contador
            const countEl = document.getElementById('versoes-count');
            if (data.total_versoes > 0) {
                countEl.textContent = data.total_versoes;
                countEl.classList.remove('hidden');
            }
        } catch (error) {
            console.error('Erro ao carregar contagem de versões:', error);
        }
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
            // Usa endpoint com streaming para melhor TTFT
            // Inclui tipo_peca para busca de argumentos relevantes
            const response = await fetch(`${API_URL}/editar-minuta-stream`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.getToken()}`
                },
                body: JSON.stringify({
                    minuta_atual: this.minutaMarkdown,
                    mensagem: mensagem,
                    historico: this.historicoChat,
                    tipo_peca: this.tipoPeca
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            // Processa stream SSE
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            let minutaCompleta = '';
            let primeiroChunk = true;

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';

                for (const line of lines) {
                    if (line.startsWith('event: ')) {
                        const eventType = line.substring(7).trim();
                        continue;
                    }
                    if (line.startsWith('data: ')) {
                        const data = line.substring(6);
                        if (data === '[DONE]') {
                            // Streaming finalizado
                            continue;
                        }
                        if (data.trim() === '' || data === ':heartbeat') {
                            continue;
                        }

                        try {
                            const parsed = JSON.parse(data);

                            if (parsed.error) {
                                throw new Error(parsed.error);
                            }

                            if (parsed.text) {
                                // Esconde indicador de digitação no primeiro chunk
                                if (primeiroChunk) {
                                    this.esconderTypingIndicator();
                                    primeiroChunk = false;
                                }

                                // Acumula texto
                                minutaCompleta += parsed.text;

                                // Atualiza preview em tempo real (a cada 500 chars para não sobrecarregar)
                                if (minutaCompleta.length % 500 < parsed.text.length) {
                                    this.minutaMarkdown = minutaCompleta;
                                    this.renderizarMinuta();
                                }
                            }
                        } catch (e) {
                            // Ignora linhas que não são JSON válido
                        }
                    }
                }
            }

            this.esconderTypingIndicator();

            // Verifica se recebeu conteúdo
            if (minutaCompleta) {
                // Atualiza a minuta final
                this.minutaMarkdown = minutaCompleta;
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
                this.adicionarMensagemChat('ai', 'Não foi possível processar a edição. Tente novamente.', false);
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

    abrirAutos() {
        if (!this.numeroCNJ || this.numeroCNJ === 'PDFs Anexados') {
            this.showToast('Autos disponíveis apenas para processos do TJ-MS', 'warning');
            return;
        }

        // Abre a página de autos em uma nova aba
        const token = this.getToken();
        const url = `/gerador-pecas/autos.html?cnj=${encodeURIComponent(this.numeroCNJ)}&token=${encodeURIComponent(token)}`;
        window.open(url, '_blank');
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
            this.isNovaGeracao = false; // Do histórico, não mostrar feedback

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

            // Reset estado de versões
            this.versoesLista = [];
            this.versaoSelecionada = null;
            this.painelVersoesAberto = false;
            document.getElementById('painel-versoes').classList.add('hidden');
            document.getElementById('versao-detalhe').classList.add('hidden');
            document.getElementById('versoes-count').classList.add('hidden');

            // Atualiza UI
            document.getElementById('editor-tipo-peca').textContent = this.formatarOpcao(data.tipo_peca);
            document.getElementById('editor-cnj').textContent = data.cnj ? `• ${data.cnj}` : '';
            this.renderizarMinuta();

            // Renderiza chat com histórico
            this.renderizarChatHistorico();

            this.abrirModal('modal-editor');

            // Carrega contagem de versões (em background)
            this.carregarContagemVersoes();

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
            // Obtém a última mensagem do usuário como descrição da alteração
            let descricaoAlteracao = null;
            if (this.historicoChat && this.historicoChat.length > 0) {
                for (let i = this.historicoChat.length - 1; i >= 0; i--) {
                    if (this.historicoChat[i].role === 'user') {
                        descricaoAlteracao = this.historicoChat[i].content;
                        break;
                    }
                }
            }

            const response = await fetch(`${API_URL}/historico/${this.geracaoId}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.getToken()}`
                },
                body: JSON.stringify({
                    minuta_markdown: this.minutaMarkdown,
                    historico_chat: this.historicoChat,
                    descricao_alteracao: descricaoAlteracao
                })
            });

            if (!response.ok) throw new Error('Erro ao salvar');

            const data = await response.json();

            // Atualiza status discretamente
            document.getElementById('minuta-status').textContent = 'Salvo automaticamente';

            // Se criou nova versão, atualiza contador e lista
            if (data.versao) {
                const countEl = document.getElementById('versoes-count');
                countEl.textContent = data.versao.numero_versao;
                countEl.classList.remove('hidden');

                // Se o painel de versões estiver aberto, recarrega a lista
                if (this.painelVersoesAberto) {
                    await this.carregarVersoes();
                }
            }

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
        const erroEl = document.getElementById('erro-mensagem');
        const toastEl = document.getElementById('toast-erro');
        
        // Preserva quebras de linha se houver
        erroEl.textContent = mensagem;
        toastEl.classList.remove('hidden');
        
        // Remove animação de pulse após 2 segundos
        setTimeout(() => {
            toastEl.classList.remove('animate-pulse');
        }, 2000);
        
        // Auto-hide após 15 segundos (aumentado para mensagens mais longas)
        if (this._erroTimeout) {
            clearTimeout(this._erroTimeout);
        }
        this._erroTimeout = setTimeout(() => {
            toastEl.classList.add('hidden');
            toastEl.classList.add('animate-pulse'); // Restaura para próximo uso
        }, 15000);
    }

    esconderErro() {
        const toastEl = document.getElementById('toast-erro');
        toastEl.classList.add('hidden');
        toastEl.classList.add('animate-pulse'); // Restaura para próximo uso
        if (this._erroTimeout) {
            clearTimeout(this._erroTimeout);
            this._erroTimeout = null;
        }
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
        document.getElementById('observacao-usuario').value = '';
        this.numeroCNJ = null;
        this.tipoPeca = null;
        this.geracaoId = null;
        this.notaSelecionada = null;
        this.isNovaGeracao = false;
        this.minutaMarkdown = null;
        this.historicoChat = [];
        this.observacaoUsuario = null;

        const grupoSelect = document.getElementById('grupo-principal');
        if (grupoSelect && grupoSelect.value) {
            const parsed = parseInt(grupoSelect.value, 10);
            this.groupId = Number.isNaN(parsed) ? null : parsed;
        } else {
            this.groupId = null;
        }
        this.subcategoriaIds = [];
        if (this.groupId) {
            this.renderSubcategorias(this.subcategoriasDisponiveis);
        } else {
            this.renderSubcategorias([]);
        }

        // Reset arquivos PDF
        this.arquivosPdf = [];
        this.atualizarListaArquivos();

        // Reset versões
        this.versoesLista = [];
        this.versaoSelecionada = null;
        this.painelVersoesAberto = false;

        // Reset estrelas
        document.querySelectorAll('.estrela').forEach(btn => {
            btn.classList.remove('text-yellow-400');
            btn.classList.add('text-gray-300');
        });
        document.getElementById('btn-enviar-feedback').disabled = true;
    }

    // ==========================================
    // Histórico de Versões
    // ==========================================

    toggleHistoricoVersoes() {
        const painel = document.getElementById('painel-versoes');

        if (this.painelVersoesAberto) {
            // Fechar painel
            painel.classList.add('hidden');
            this.painelVersoesAberto = false;
        } else {
            // Abrir painel e carregar versões
            painel.classList.remove('hidden');
            this.painelVersoesAberto = true;
            this.carregarVersoes();
        }
    }

    async carregarVersoes() {
        if (!this.geracaoId) return;

        const lista = document.getElementById('versoes-lista');
        lista.innerHTML = `
            <div class="text-center py-8 text-gray-400">
                <i class="fas fa-spinner fa-spin text-2xl mb-2"></i>
                <p class="text-sm">Carregando versões...</p>
            </div>
        `;

        try {
            const response = await fetch(`${API_URL}/historico/${this.geracaoId}/versoes`, {
                headers: { 'Authorization': `Bearer ${this.getToken()}` }
            });

            if (!response.ok) throw new Error('Erro ao carregar versões');

            const data = await response.json();
            this.versoesLista = data.versoes;

            // Atualiza contador
            const countEl = document.getElementById('versoes-count');
            if (data.total_versoes > 0) {
                countEl.textContent = data.total_versoes;
                countEl.classList.remove('hidden');
            } else {
                countEl.classList.add('hidden');
            }

            this.renderizarVersoes();

        } catch (error) {
            console.error('Erro ao carregar versões:', error);
            lista.innerHTML = `
                <div class="text-center py-8 text-gray-400">
                    <i class="fas fa-exclamation-circle text-2xl mb-2 text-red-400"></i>
                    <p class="text-sm">Erro ao carregar versões</p>
                </div>
            `;
        }
    }

    renderizarVersoes() {
        const lista = document.getElementById('versoes-lista');

        if (this.versoesLista.length === 0) {
            lista.innerHTML = `
                <div class="text-center py-8 text-gray-400">
                    <i class="fas fa-code-branch text-3xl mb-3 opacity-50"></i>
                    <p class="text-sm font-medium">Nenhuma versão registrada</p>
                    <p class="text-xs mt-1">As versões aparecerão aqui após edições</p>
                </div>
            `;
            return;
        }

        lista.innerHTML = this.versoesLista.map((versao, index) => {
            const isAtual = index === 0;
            const badgeClass = this.getBadgeClass(versao.origem);
            const badgeText = this.getBadgeText(versao.origem);
            const dataFormatada = versao.criado_em
                ? new Date(versao.criado_em).toLocaleString('pt-BR', {
                    day: '2-digit', month: '2-digit', year: '2-digit',
                    hour: '2-digit', minute: '2-digit'
                })
                : 'Data desconhecida';

            return `
                <div class="versao-item p-3 bg-white border ${isAtual ? 'border-indigo-300 bg-indigo-50' : 'border-gray-100'} rounded-xl cursor-pointer hover:border-indigo-300 hover:bg-indigo-50/50"
                     onclick="app.selecionarVersao(${versao.id})" data-versao-id="${versao.id}">
                    <div class="flex items-center justify-between mb-2">
                        <div class="flex items-center gap-2">
                            <span class="text-sm font-semibold text-gray-800">v${versao.numero_versao}</span>
                            ${isAtual ? '<span class="text-xs text-indigo-600 font-medium">(atual)</span>' : ''}
                        </div>
                        <span class="versao-badge ${badgeClass}">${badgeText}</span>
                    </div>
                    <p class="text-xs text-gray-500 mb-1">
                        <i class="fas fa-clock mr-1"></i>${dataFormatada}
                    </p>
                    ${versao.descricao_alteracao ? `
                        <p class="text-xs text-gray-600 truncate mt-1" title="${this.escapeHtml(versao.descricao_alteracao)}">
                            <i class="fas fa-comment mr-1 text-gray-400"></i>${this.escapeHtml(versao.descricao_alteracao.substring(0, 50))}${versao.descricao_alteracao.length > 50 ? '...' : ''}
                        </p>
                    ` : ''}
                    <p class="text-xs mt-1 ${versao.resumo_diff.includes('+') ? 'text-green-600' : 'text-gray-400'}">
                        ${versao.resumo_diff}
                    </p>
                </div>
            `;
        }).join('');
    }

    getBadgeClass(origem) {
        switch (origem) {
            case 'geracao_inicial':
                return 'versao-badge-inicial';
            case 'edicao_chat':
                return 'versao-badge-edicao';
            case 'edicao_manual':
                return 'versao-badge-restauracao';
            default:
                return 'versao-badge-inicial';
        }
    }

    getBadgeText(origem) {
        switch (origem) {
            case 'geracao_inicial':
                return 'Inicial';
            case 'edicao_chat':
                return 'Edição';
            case 'edicao_manual':
                return 'Restaurado';
            default:
                return origem;
        }
    }

    async selecionarVersao(versaoId) {
        this.versaoSelecionada = versaoId;

        // Atualiza visual da seleção
        document.querySelectorAll('.versao-item').forEach(el => {
            el.classList.remove('active');
        });
        const itemSelecionado = document.querySelector(`[data-versao-id="${versaoId}"]`);
        if (itemSelecionado) {
            itemSelecionado.classList.add('active');
        }

        // Carrega detalhes da versão
        try {
            const response = await fetch(`${API_URL}/historico/${this.geracaoId}/versoes/${versaoId}`, {
                headers: { 'Authorization': `Bearer ${this.getToken()}` }
            });

            if (!response.ok) throw new Error('Erro ao carregar versão');

            const versao = await response.json();
            this.mostrarDetalheVersao(versao);

        } catch (error) {
            console.error('Erro ao carregar detalhes da versão:', error);
            this.showToast('Erro ao carregar versão', 'error');
        }
    }

    mostrarDetalheVersao(versao) {
        const detalhePanel = document.getElementById('versao-detalhe');
        const diffContainer = document.getElementById('versao-diff');

        detalhePanel.classList.remove('hidden');

        if (versao.diff_anterior) {
            const diff = versao.diff_anterior;
            let diffHtml = '';

            // Mostra linhas adicionadas
            if (diff.linhas_adicionadas && diff.linhas_adicionadas.length > 0) {
                diffHtml += `<div class="mb-2"><span class="text-xs text-green-600 font-medium">+ Adicionadas (${diff.total_adicionadas}):</span></div>`;
                diff.linhas_adicionadas.slice(0, 10).forEach(linha => {
                    diffHtml += `<div class="diff-line diff-added">+ ${this.escapeHtml(linha.substring(0, 100))}</div>`;
                });
                if (diff.linhas_adicionadas.length > 10) {
                    diffHtml += `<div class="text-xs text-gray-400 mt-1">... e mais ${diff.linhas_adicionadas.length - 10} linha(s)</div>`;
                }
            }

            // Mostra linhas removidas
            if (diff.linhas_removidas && diff.linhas_removidas.length > 0) {
                diffHtml += `<div class="mt-3 mb-2"><span class="text-xs text-red-600 font-medium">- Removidas (${diff.total_removidas}):</span></div>`;
                diff.linhas_removidas.slice(0, 10).forEach(linha => {
                    diffHtml += `<div class="diff-line diff-removed">- ${this.escapeHtml(linha.substring(0, 100))}</div>`;
                });
                if (diff.linhas_removidas.length > 10) {
                    diffHtml += `<div class="text-xs text-gray-400 mt-1">... e mais ${diff.linhas_removidas.length - 10} linha(s)</div>`;
                }
            }

            if (!diffHtml) {
                diffHtml = '<p class="text-gray-400 text-center py-4">Versão inicial - sem alterações anteriores</p>';
            }

            diffContainer.innerHTML = diffHtml;
        } else {
            diffContainer.innerHTML = '<p class="text-gray-400 text-center py-4">Versão inicial - sem alterações anteriores</p>';
        }
    }

    fecharDetalheVersao() {
        document.getElementById('versao-detalhe').classList.add('hidden');
        this.versaoSelecionada = null;

        // Remove seleção visual
        document.querySelectorAll('.versao-item').forEach(el => {
            el.classList.remove('active');
        });
    }

    async verConteudoVersao() {
        if (!this.versaoSelecionada) return;

        try {
            const response = await fetch(`${API_URL}/historico/${this.geracaoId}/versoes/${this.versaoSelecionada}`, {
                headers: { 'Authorization': `Bearer ${this.getToken()}` }
            });

            if (!response.ok) throw new Error('Erro ao carregar versão');

            const versao = await response.json();

            // Preenche modal
            document.getElementById('modal-versao-titulo').textContent = `Versão ${versao.numero_versao}`;
            document.getElementById('modal-versao-data').textContent = versao.criado_em
                ? new Date(versao.criado_em).toLocaleString('pt-BR')
                : 'Data desconhecida';

            const conteudoEl = document.getElementById('modal-versao-conteudo');
            if (typeof marked !== 'undefined') {
                conteudoEl.innerHTML = marked.parse(versao.conteudo || '');
            } else {
                conteudoEl.innerHTML = versao.conteudo || '';
            }

            // Abre modal
            document.getElementById('modal-versao-completa').classList.remove('hidden');

        } catch (error) {
            console.error('Erro ao carregar conteúdo:', error);
            this.showToast('Erro ao carregar conteúdo da versão', 'error');
        }
    }

    fecharModalVersao() {
        document.getElementById('modal-versao-completa').classList.add('hidden');
    }

    async restaurarVersaoSelecionada() {
        if (!this.versaoSelecionada) {
            this.showToast('Selecione uma versão primeiro', 'warning');
            return;
        }

        if (!confirm('Tem certeza que deseja restaurar esta versão? O texto atual será salvo como uma nova versão antes da restauração.')) {
            return;
        }

        await this.restaurarVersao(this.versaoSelecionada);
    }

    async restaurarVersaoDoModal() {
        if (!this.versaoSelecionada) return;

        if (!confirm('Tem certeza que deseja restaurar esta versão? O texto atual será salvo como uma nova versão antes da restauração.')) {
            return;
        }

        this.fecharModalVersao();
        await this.restaurarVersao(this.versaoSelecionada);
    }

    async restaurarVersao(versaoId) {
        try {
            const response = await fetch(`${API_URL}/historico/${this.geracaoId}/versoes/${versaoId}/restaurar`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${this.getToken()}` }
            });

            if (!response.ok) throw new Error('Erro ao restaurar versão');

            const data = await response.json();

            // Atualiza a minuta com o conteúdo restaurado
            this.minutaMarkdown = data.conteudo;
            this.renderizarMinuta();

            // Recarrega lista de versões
            await this.carregarVersoes();

            // Fecha detalhe
            this.fecharDetalheVersao();

            this.showToast(`Versão restaurada! Nova versão: v${data.nova_versao.numero_versao}`, 'success');
            this.destacarMinuta();

        } catch (error) {
            console.error('Erro ao restaurar versão:', error);
            this.showToast('Erro ao restaurar versão', 'error');
        }
    }

    // ==========================================
    // Streaming de Geração em Tempo Real (no Editor)
    // ==========================================

    abrirEditorStreaming() {
        console.log('📝 abrirEditorStreaming() chamado');

        try {
            // Abre o editor imediatamente com estado de "gerando"
            this.esconderLoading();

            // Configura estado inicial
            this.minutaMarkdown = '';
            this.historicoChat = [];
            this.geracaoId = null;  // Será definido quando finalizar
            this.isNovaGeracao = true;

            // Reset estado de versões
            this.versoesLista = [];
            this.versaoSelecionada = null;
            this.painelVersoesAberto = false;

            // Esses elementos podem não existir - usar optional chaining
            document.getElementById('painel-versoes')?.classList.add('hidden');
            document.getElementById('versao-detalhe')?.classList.add('hidden');
            document.getElementById('versoes-count')?.classList.add('hidden');

            // Atualiza título com tipo da peça (ainda não sabemos)
            const editorTipoPeca = document.getElementById('editor-tipo-peca');
            if (editorTipoPeca) editorTipoPeca.textContent = 'Gerando...';

            const editorCnj = document.getElementById('editor-cnj');
            if (editorCnj) editorCnj.textContent = this.numeroCNJ ? `• ${this.numeroCNJ}` : '';

            // Mostra indicador de streaming no editor
            const container = document.getElementById('minuta-content');
            if (container) {
                container.innerHTML = `
                    <div class="flex items-center gap-2 text-primary-600 mb-4">
                        <div class="animate-spin h-4 w-4 border-2 border-primary-500 border-t-transparent rounded-full"></div>
                        <span class="text-sm font-medium">Gerando peça em tempo real...</span>
                    </div>
                    <div id="streaming-content" class="prose prose-sm max-w-none"></div>
                `;
            }

            // Status
            const minutaStatus = document.getElementById('minuta-status');
            if (minutaStatus) {
                minutaStatus.innerHTML = `
                    <span class="text-primary-600 animate-pulse">
                        <i class="fas fa-pen-fancy mr-1"></i> Escrevendo...
                    </span>
                `;
            }

            // Desabilita chat durante streaming
            const chatInput = document.getElementById('chat-input');
            if (chatInput) {
                chatInput.disabled = true;
                chatInput.placeholder = 'Aguarde a geração finalizar...';
            }

            // Reseta o chat (se existir o método)
            if (typeof this.resetarChat === 'function') {
                this.resetarChat();
            }

            // Abre o modal do editor
            console.log('📝 Abrindo modal-editor...');
            this.abrirModal('modal-editor');
            console.log('✅ Modal aberto com sucesso');

        } catch (err) {
            console.error('❌ Erro em abrirEditorStreaming:', err);
        }
    }

    atualizarEditorStreaming() {
        const contentEl = document.getElementById('streaming-content');

        if (contentEl && this.streamingContent) {
            // Renderiza markdown em tempo real
            if (typeof marked !== 'undefined') {
                marked.setOptions({ breaks: true, gfm: true });
                contentEl.innerHTML = marked.parse(this.streamingContent);
            } else {
                // Fallback simples
                contentEl.innerHTML = this.streamingContent
                    .replace(/## (.*)/g, '<h2 class="text-lg font-semibold mt-4 mb-2">$1</h2>')
                    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                    .replace(/\*(.*?)\*/g, '<em>$1</em>')
                    .replace(/\n/g, '<br>');
            }

            // Scroll automático para o final
            const container = document.getElementById('minuta-content');
            if (container) {
                container.scrollTop = container.scrollHeight;
            }
        }

        // Atualiza status com contagem
        const statusEl = document.getElementById('minuta-status');
        if (statusEl) {
            const chars = this.streamingContent.length;
            const tokens = Math.round(chars / 4);
            statusEl.innerHTML = `
                <span class="text-primary-600 animate-pulse">
                    <i class="fas fa-pen-fancy mr-1"></i>
                    Escrevendo... ${tokens.toLocaleString()} tokens
                </span>
            `;
        }
    }

    finalizarEditorStreaming(geracaoId, tipoPeca, conteudoFinal) {
        // Atualiza dados
        this.geracaoId = geracaoId;
        this.tipoPeca = tipoPeca;
        this.minutaMarkdown = conteudoFinal;

        // Atualiza título
        document.getElementById('editor-tipo-peca').textContent = this.formatarOpcao(tipoPeca);

        // Re-renderiza a minuta sem o indicador de streaming
        this.renderizarMinuta();

        // Atualiza status
        document.getElementById('minuta-status').textContent = 'Geração concluída';

        // Habilita chat
        const chatInput = document.getElementById('chat-input');
        if (chatInput) {
            chatInput.disabled = false;
            chatInput.placeholder = 'Digite uma solicitação de alteração...';
        }

        // Reseta estado de streaming
        this.isStreaming = false;
        this.streamingContent = '';

        // Carrega histórico e versões em background
        this.carregarHistoricoRecente();
        this.carregarContagemVersoes();

        // Efeito visual de conclusão
        this.destacarMinuta();
    }

    finalizarStreaming() {
        // Reseta estado (usado para limpeza em caso de erro)
        this.isStreaming = false;
        this.streamingContent = '';
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

    // Fecha painel de versões se estiver aberto
    if (app && app.painelVersoesAberto) {
        document.getElementById('painel-versoes').classList.add('hidden');
        app.painelVersoesAberto = false;
    }

    // Fecha detalhe de versão se estiver aberto
    document.getElementById('versao-detalhe').classList.add('hidden');

    // Abrir modal de feedback apenas se for nova geração
    if (app && app.isNovaGeracao) {
        document.getElementById('modal-feedback').classList.remove('hidden');
    }
}

// Inicializar app
let app;
document.addEventListener('DOMContentLoaded', () => {
    app = new GeradorPecasApp();
});
