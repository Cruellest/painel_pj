/**
 * Modulo de Curadoria de Argumentos - Modo Semi-Automatico
 *
 * Este modulo permite que usuarios:
 * 1. Visualizem os argumentos detectados automaticamente
 * 2. Adicionem/removam argumentos
 * 3. Reorganizem argumentos entre secoes via drag-and-drop
 * 4. Busquem argumentos adicionais (texto e semantico)
 * 5. Gerem a peca com os argumentos curados
 */

class CuradoriaModule {
    constructor() {
        this.dadosCuradoria = null;
        this.secoes = []; // Será carregado dinamicamente da API
        this.categoriasDisponiveis = []; // Categorias do grupo atual
        this.categoriasOrdem = []; // Ordem das categorias definida pelo usuário (para enviar ao backend)
        this.modulosOrdem = {}; // {secao: [id1, id2, ...]}
        this.modulosSelecionados = new Set();
        this.modulosManuais = new Set(); // IDs dos módulos adicionados manualmente pelo usuário
        this.draggedItem = null;
        this.draggedCategory = null; // Para drag de categoria inteira
        this.dragType = null; // 'modulo' ou 'categoria'
        this.buscarTimeout = null;
        // Novos: para lista de módulos disponíveis agrupados
        this.todosModulosDisponiveis = []; // Cache de todos os módulos do grupo
        this.modulosDisponiveisAgrupados = {}; // {categoria: [modulos...]}
        this.currentGroupId = null;
        this.secoesColapsadas = {}; // Estado das seções colapsáveis
    }

    /**
     * Inicializa o modo semi-automatico
     */
    async iniciarModoSemiAutomatico(numeroCnj, tipoPeca, groupId, subcategoriaIds) {
        try {
            this.currentGroupId = groupId;
            this.mostrarModalCuradoria();
            this.atualizarProgressoCuradoria('agente1', 'ativo', 'Coletando documentos do TJ-MS...');

            const response = await fetch('/gerador-pecas/api/curadoria/preview', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${app.getToken()}`
                },
                body: JSON.stringify({
                    numero_cnj: numeroCnj,
                    tipo_peca: tipoPeca,
                    group_id: groupId,
                    subcategoria_ids: subcategoriaIds
                })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Erro ao carregar preview');
            }

            const resultado = await response.json();

            if (!resultado.success) {
                throw new Error('Falha na deteccao de modulos');
            }

            this.dadosCuradoria = resultado.curadoria;
            this.atualizarProgressoCuradoria('agente1', 'concluido', 'Documentos coletados');
            this.atualizarProgressoCuradoria('agente2', 'concluido', `${resultado.curadoria.estatisticas.total_modulos} argumentos detectados`);

            // Inicializa estado
            this.inicializarEstado();

            // Carrega categorias disponíveis do grupo
            await this.carregarCategorias();

            // Carrega módulos disponíveis do grupo (não selecionados)
            await this.carregarModulosDisponiveis();

            // Renderiza interface de curadoria
            this.renderizarInterfaceCuradoria();

        } catch (error) {
            console.error('Erro no modo semi-automatico:', error);
            this.fecharModalCuradoria();
            app.mostrarErro(error.message);
        }
    }

    inicializarEstado() {
        this.modulosOrdem = {};
        this.modulosSelecionados = new Set();
        this.modulosManuais = new Set(); // Limpa módulos manuais ao inicializar
        this.categoriasOrdem = []; // Ordem das categorias

        for (const [secao, modulos] of Object.entries(this.dadosCuradoria.modulos_por_secao)) {
            this.modulosOrdem[secao] = modulos.map(m => m.id);
            this.categoriasOrdem.push(secao); // Adiciona categoria na ordem inicial
            modulos.forEach(m => {
                if (m.selecionado) {
                    this.modulosSelecionados.add(m.id);
                }
                // Módulos que já vieram marcados como manual do preview
                if (m.origem_ativacao === 'manual') {
                    this.modulosManuais.add(m.id);
                }
            });
        }
    }

    /**
     * Carrega categorias disponíveis da API para o grupo atual.
     * As categorias são usadas para agrupar módulos dinamicamente,
     * permitindo que novas categorias criadas no admin sejam reconhecidas automaticamente.
     */
    async carregarCategorias() {
        if (!this.currentGroupId) return;

        try {
            const response = await fetch(
                `/admin/api/prompts-modulos/categorias?group_id=${this.currentGroupId}&apenas_ativos=true`,
                { headers: { 'Authorization': `Bearer ${app.getToken()}` } }
            );

            if (!response.ok) {
                console.error('Erro ao carregar categorias:', response.status);
                // Fallback para categorias padrão
                this.categoriasDisponiveis = ['Preliminar', 'Mérito', 'Eventualidade', 'Honorários', 'Pedidos', 'Outros'];
                this.secoes = [...this.categoriasDisponiveis];
                return;
            }

            const categorias = await response.json();

            // Garante que "Outros" está sempre por último como fallback
            this.categoriasDisponiveis = categorias.filter(c => c && c !== 'Outros');
            this.categoriasDisponiveis.push('Outros');

            // Atualiza também o array de seções para a coluna esquerda
            this.secoes = [...this.categoriasDisponiveis];

        } catch (error) {
            console.error('Erro ao carregar categorias:', error);
            // Fallback para categorias padrão
            this.categoriasDisponiveis = ['Preliminar', 'Mérito', 'Eventualidade', 'Honorários', 'Pedidos', 'Outros'];
            this.secoes = [...this.categoriasDisponiveis];
        }
    }

    mostrarModalCuradoria() {
        let modal = document.getElementById('modal-curadoria');
        if (!modal) {
            modal = this.criarModalCuradoria();
            document.body.appendChild(modal);
        }
        modal.classList.remove('hidden');
    }

    fecharModalCuradoria() {
        const modal = document.getElementById('modal-curadoria');
        if (modal) {
            modal.classList.add('hidden');
        }
    }

    criarModalCuradoria() {
        const modal = document.createElement('div');
        modal.id = 'modal-curadoria';
        modal.className = 'fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50';

        modal.innerHTML = `
            <style>
                /* Estilos para drag and drop de categorias */
                [data-secao-container].category-drop-above {
                    border-top: 3px solid #f59e0b !important;
                    margin-top: -3px;
                }
                [data-secao-container].category-drop-below {
                    border-bottom: 3px solid #f59e0b !important;
                    margin-bottom: -3px;
                }
                [data-secao-container].opacity-50 {
                    opacity: 0.5;
                }
                /* Handle de drag */
                .cursor-grab:active {
                    cursor: grabbing;
                }
                /* Transição suave para reordenamento */
                #curadoria-secoes > div {
                    transition: transform 0.2s ease, opacity 0.2s ease;
                }
            </style>
            <div class="bg-white rounded-2xl max-w-7xl w-full mx-4 h-[90vh] flex flex-col shadow-2xl overflow-hidden">
                <!-- Header -->
                <div class="flex items-center justify-between px-6 py-4 border-b border-gray-100 bg-gradient-to-r from-amber-50 to-orange-50">
                    <div class="flex items-center gap-3">
                        <div class="w-10 h-10 bg-gradient-to-br from-amber-500 to-orange-500 rounded-xl flex items-center justify-center">
                            <i class="fas fa-hand-pointer text-white"></i>
                        </div>
                        <div>
                            <h2 class="text-lg font-bold text-gray-800">Modo Semi-Automatico</h2>
                            <p class="text-xs text-gray-500">Selecione e organize os argumentos antes de gerar</p>
                        </div>
                    </div>
                    <div class="flex items-center gap-2">
                        <button onclick="curadoria.fecharModalCuradoria()"
                            class="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                </div>

                <!-- Conteudo Principal -->
                <div class="flex-1 flex overflow-hidden">
                    <!-- Painel de Progresso (inicial) -->
                    <div id="curadoria-progresso" class="flex-1 flex items-center justify-center p-8">
                        <div class="max-w-md w-full space-y-4">
                            <div id="curadoria-agente1" class="flex items-center gap-3 p-4 rounded-xl bg-gray-50 border border-gray-100">
                                <div class="w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center">
                                    <i class="fas fa-download text-gray-400 text-sm"></i>
                                </div>
                                <div class="flex-1">
                                    <p class="text-sm font-medium text-gray-700">Agente 1: Coletor</p>
                                    <p class="text-xs text-gray-500">Aguardando...</p>
                                </div>
                                <span class="text-xs px-3 py-1 rounded-full bg-gray-100 text-gray-500 font-medium">Aguardando</span>
                            </div>
                            <div id="curadoria-agente2" class="flex items-center gap-3 p-4 rounded-xl bg-gray-50 border border-gray-100">
                                <div class="w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center">
                                    <i class="fas fa-brain text-gray-400 text-sm"></i>
                                </div>
                                <div class="flex-1">
                                    <p class="text-sm font-medium text-gray-700">Agente 2: Detector</p>
                                    <p class="text-xs text-gray-500">Aguardando...</p>
                                </div>
                                <span class="text-xs px-3 py-1 rounded-full bg-gray-100 text-gray-500 font-medium">Aguardando</span>
                            </div>
                        </div>
                    </div>

                    <!-- Interface de Curadoria (escondida inicialmente) -->
                    <div id="curadoria-interface" class="hidden flex-1 flex">
                        <!-- Painel Esquerdo: Argumentos por Secao -->
                        <div class="flex-1 flex flex-col border-r border-gray-200">
                            <div class="p-4 border-b border-gray-100 bg-gray-50">
                                <div class="flex items-center justify-between">
                                    <h3 class="font-semibold text-gray-800">
                                        <i class="fas fa-list-check mr-2 text-amber-500"></i>
                                        Argumentos Detectados
                                    </h3>
                                    <div class="flex items-center gap-2 text-xs">
                                        <span class="px-2 py-1 bg-green-100 text-green-700 rounded-full">
                                            <i class="fas fa-robot mr-1"></i>DET: <span id="count-det">0</span>
                                        </span>
                                        <span class="px-2 py-1 bg-blue-100 text-blue-700 rounded-full">
                                            <i class="fas fa-brain mr-1"></i>LLM: <span id="count-llm">0</span>
                                        </span>
                                    </div>
                                </div>
                            </div>
                            <div id="curadoria-secoes" class="flex-1 overflow-y-auto custom-scrollbar p-4 space-y-4">
                                <!-- Secoes serao renderizadas aqui -->
                            </div>
                        </div>

                        <!-- Painel Direito: Argumentos Disponíveis -->
                        <div class="w-96 flex flex-col bg-gray-50">
                            <!-- Filtro de Argumentos -->
                            <div class="p-4 border-b border-gray-200">
                                <h3 class="font-semibold text-gray-800 mb-3">
                                    <i class="fas fa-layer-group mr-2 text-primary-500"></i>
                                    Argumentos Disponíveis
                                </h3>
                                <div class="space-y-2">
                                    <input type="text" id="curadoria-busca-input"
                                        placeholder="Filtrar por título..."
                                        class="w-full px-3 py-2 border border-gray-200 rounded-lg focus:ring-2 focus:ring-primary-500 text-sm"
                                        oninput="curadoria.debounceBusca(this.value)">
                                </div>
                            </div>

                            <!-- Lista de Argumentos Agrupados -->
                            <div id="curadoria-busca-resultados" class="flex-1 overflow-y-auto custom-scrollbar p-4">
                                <p class="text-gray-400 text-sm text-center py-8">
                                    <i class="fas fa-spinner fa-spin mb-2 block text-2xl"></i>
                                    Carregando argumentos...
                                </p>
                            </div>

                            <!-- Resumo e Acoes -->
                            <div class="p-4 border-t border-gray-200 bg-white">
                                <div class="mb-4 p-3 bg-gray-50 rounded-lg">
                                    <div class="flex justify-between text-sm">
                                        <span class="text-gray-600">Total selecionados:</span>
                                        <span id="count-selecionados" class="font-bold text-primary-600">0</span>
                                    </div>
                                </div>
                                <button onclick="curadoria.gerarComCuradoria()"
                                    class="w-full bg-gradient-to-r from-amber-500 to-orange-500 text-white py-3 px-6 rounded-xl font-semibold hover:from-amber-600 hover:to-orange-600 transition-all flex items-center justify-center gap-2 shadow-lg shadow-amber-500/25">
                                    <i class="fas fa-wand-magic-sparkles"></i>
                                    Gerar com Selecionados
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;

        return modal;
    }

    atualizarProgressoCuradoria(agente, status, mensagem) {
        const el = document.getElementById(`curadoria-${agente}`);
        if (!el) return;

        const icon = el.querySelector('.fa-download, .fa-brain, .fa-check, .fa-spinner, .fa-times');
        const badge = el.querySelector('span:last-child');
        const descricao = el.querySelector('.text-xs.text-gray-500');

        if (descricao) descricao.textContent = mensagem;

        if (status === 'ativo') {
            if (icon) icon.className = 'fas fa-spinner fa-spin text-primary-500 text-sm';
            el.querySelector('.w-8').className = 'w-8 h-8 rounded-full bg-primary-100 flex items-center justify-center';
            if (badge) {
                badge.textContent = 'Processando';
                badge.className = 'text-xs px-3 py-1 rounded-full bg-primary-100 text-primary-600 font-medium';
            }
        } else if (status === 'concluido') {
            if (icon) icon.className = 'fas fa-check text-green-500 text-sm';
            el.querySelector('.w-8').className = 'w-8 h-8 rounded-full bg-green-100 flex items-center justify-center';
            if (badge) {
                badge.textContent = 'Concluido';
                badge.className = 'text-xs px-3 py-1 rounded-full bg-green-100 text-green-600 font-medium';
            }
        } else if (status === 'erro') {
            if (icon) icon.className = 'fas fa-times text-red-500 text-sm';
            el.querySelector('.w-8').className = 'w-8 h-8 rounded-full bg-red-100 flex items-center justify-center';
            if (badge) {
                badge.textContent = 'Erro';
                badge.className = 'text-xs px-3 py-1 rounded-full bg-red-100 text-red-600 font-medium';
            }
        }
    }

    renderizarInterfaceCuradoria() {
        document.getElementById('curadoria-progresso').classList.add('hidden');
        document.getElementById('curadoria-interface').classList.remove('hidden');

        // Atualiza contadores
        document.getElementById('count-det').textContent = this.dadosCuradoria.estatisticas.modulos_det;
        document.getElementById('count-llm').textContent = this.dadosCuradoria.estatisticas.modulos_llm;

        // Renderiza secoes usando categoriasOrdem para manter a ordem definida pelo usuário
        const container = document.getElementById('curadoria-secoes');
        container.innerHTML = '';

        // Usa categoriasOrdem se já foi definida, senão usa secoes do preview
        const ordemRenderizar = this.categoriasOrdem.length > 0 ? this.categoriasOrdem : this.secoes;

        for (const secao of ordemRenderizar) {
            const modulos = this.dadosCuradoria.modulos_por_secao[secao] || [];
            if (modulos.length === 0 && !this.modulosOrdem[secao]?.length) continue;

            const secaoEl = this.criarSecaoHTML(secao, modulos);
            container.appendChild(secaoEl);
        }

        this.atualizarContadorSelecionados();
        this.inicializarDragAndDrop();

        // Renderiza módulos disponíveis agrupados na coluna direita
        this.renderizarModulosAgrupados('');
    }

    criarSecaoHTML(secao, modulos) {
        const div = document.createElement('div');
        div.className = 'border border-gray-200 rounded-xl overflow-hidden bg-white transition-all duration-200';
        div.dataset.secao = secao;
        div.dataset.secaoContainer = secao; // Para drag de categoria

        const corSecao = {
            'Preliminar': 'blue',
            'Mérito': 'green',
            'Eventualidade': 'yellow',
            'Honorários': 'purple',
            'Pedidos': 'indigo',
            'Outros': 'gray'
        }[secao] || 'gray';

        // Escapa aspas no nome da seção para uso em atributos
        const secaoEscapada = secao.replace(/'/g, "\\'");

        div.innerHTML = `
            <div class="px-4 py-3 bg-${corSecao}-50 border-b border-${corSecao}-100 flex items-center justify-between">
                <div class="flex items-center gap-2 flex-1">
                    <!-- Handle para arrastar categoria -->
                    <div class="cursor-grab active:cursor-grabbing p-1 hover:bg-${corSecao}-100 rounded transition-colors"
                         draggable="true"
                         ondragstart="curadoria.onCategoryDragStart(event, '${secaoEscapada}')"
                         ondragend="curadoria.onDragEnd(event)"
                         title="Arrastar para reordenar categoria">
                        <i class="fas fa-grip-vertical text-${corSecao}-400"></i>
                    </div>
                    <h4 class="font-semibold text-${corSecao}-800 flex items-center gap-2 cursor-pointer flex-1"
                        onclick="curadoria.toggleSecao('${secaoEscapada}')">
                        <i class="fas fa-folder text-${corSecao}-500"></i>
                        ${secao}
                        <span class="text-xs font-normal text-${corSecao}-600">(${modulos.length})</span>
                    </h4>
                </div>
                <i class="fas fa-chevron-down text-${corSecao}-400 transition-transform cursor-pointer"
                   id="chevron-${secao}"
                   onclick="curadoria.toggleSecao('${secaoEscapada}')"></i>
            </div>
            <div id="modulos-${secao}" class="divide-y divide-gray-100" data-secao="${secao}">
                ${modulos.map(m => this.criarModuloHTML(m)).join('')}
            </div>
        `;

        return div;
    }

    criarModuloHTML(modulo) {
        const isSelected = this.modulosSelecionados.has(modulo.id);
        const origemClasse = modulo.origem_ativacao === 'deterministic'
            ? 'bg-green-100 text-green-700'
            : modulo.origem_ativacao === 'manual'
            ? 'bg-amber-100 text-amber-700'
            : 'bg-blue-100 text-blue-700';
        const origemTexto = modulo.origem_ativacao === 'deterministic'
            ? 'DET'
            : modulo.origem_ativacao === 'manual'
            ? 'MANUAL'
            : 'LLM';

        return `
            <div class="p-3 hover:bg-gray-50 transition-colors cursor-move ${isSelected ? '' : 'opacity-50'}"
                 draggable="true"
                 data-modulo-id="${modulo.id}"
                 ondragstart="curadoria.onDragStart(event)"
                 ondragend="curadoria.onDragEnd(event)">
                <div class="flex items-start gap-3">
                    <input type="checkbox" ${isSelected ? 'checked' : ''}
                        class="mt-1 w-4 h-4 text-primary-600 rounded focus:ring-primary-500"
                        onchange="curadoria.toggleModulo(${modulo.id}, this.checked)">
                    <div class="flex-1 min-w-0">
                        <div class="flex items-center gap-2 mb-1">
                            <span class="font-medium text-gray-800 text-sm break-words">${modulo.titulo}</span>
                            <span class="text-xs px-2 py-0.5 rounded-full ${origemClasse}">${origemTexto}</span>
                            ${modulo.validado ? '<i class="fas fa-check-circle text-green-500 text-xs" title="Validado"></i>' : ''}
                        </div>
                        ${modulo.subcategoria ? `<span class="text-xs text-gray-500">${modulo.subcategoria}</span>` : ''}
                        ${modulo.condicao_ativacao ? `
                            <p class="text-xs text-gray-400 mt-1 line-clamp-2">
                                <i class="fas fa-info-circle mr-1"></i>${modulo.condicao_ativacao}
                            </p>
                        ` : ''}
                    </div>
                    <button onclick="curadoria.mostrarDetalhesModulo(${modulo.id})"
                        class="p-1 text-gray-400 hover:text-primary-500 transition-colors"
                        title="Ver detalhes">
                        <i class="fas fa-eye text-xs"></i>
                    </button>
                </div>
            </div>
        `;
    }

    toggleSecao(secao) {
        const container = document.getElementById(`modulos-${secao}`);
        const chevron = document.getElementById(`chevron-${secao}`);

        if (container.classList.contains('hidden')) {
            container.classList.remove('hidden');
            chevron.style.transform = 'rotate(0deg)';
        } else {
            container.classList.add('hidden');
            chevron.style.transform = 'rotate(-90deg)';
        }
    }

    toggleModulo(moduloId, selecionado) {
        if (selecionado) {
            this.modulosSelecionados.add(moduloId);
        } else {
            this.modulosSelecionados.delete(moduloId);
        }

        // Atualiza visual
        const el = document.querySelector(`[data-modulo-id="${moduloId}"]`);
        if (el) {
            el.classList.toggle('opacity-50', !selecionado);
        }

        this.atualizarContadorSelecionados();
    }

    atualizarContadorSelecionados() {
        document.getElementById('count-selecionados').textContent = this.modulosSelecionados.size;
    }

    // ========== DRAG AND DROP ==========

    inicializarDragAndDrop() {
        const container = document.getElementById('curadoria-secoes');
        if (!container) return;

        // Event listeners para o container de seções (para drag de categorias)
        container.addEventListener('dragover', (e) => this.onDragOver(e));
        container.addEventListener('dragleave', (e) => this.onDragLeave(e));
        container.addEventListener('drop', (e) => this.onDrop(e));

        // Event listeners para cada container de módulos dentro das seções
        const modulosContainers = document.querySelectorAll('[id^="modulos-"]');
        modulosContainers.forEach(secao => {
            secao.addEventListener('dragover', (e) => this.onDragOver(e));
            secao.addEventListener('dragleave', (e) => this.onDragLeave(e));
            secao.addEventListener('drop', (e) => this.onDrop(e));
        });
    }

    // ========== DRAG DE MÓDULOS ==========

    onDragStart(event) {
        this.dragType = 'modulo';
        this.draggedItem = event.target.closest('[data-modulo-id]');
        this.draggedCategory = null;

        if (this.draggedItem) {
            this.draggedItem.classList.add('opacity-50', 'border-2', 'border-primary-500');
            event.dataTransfer.effectAllowed = 'move';
            event.dataTransfer.setData('text/plain', this.draggedItem.dataset.moduloId);
            event.dataTransfer.setData('application/x-drag-type', 'modulo');
        }
    }

    onDragEnd(event) {
        // Limpa estado do módulo arrastado
        if (this.draggedItem) {
            this.draggedItem.classList.remove('opacity-50', 'border-2', 'border-primary-500');
        }

        // Limpa estado da categoria arrastada
        if (this.draggedCategory) {
            this.draggedCategory.classList.remove('opacity-50', 'ring-2', 'ring-amber-500');
        }

        // Remove TODAS as classes de drop zone de todos os elementos
        document.querySelectorAll('.drag-over, .bg-primary-50, .bg-amber-50, .category-drop-above, .category-drop-below').forEach(el => {
            el.classList.remove('drag-over', 'bg-primary-50', 'bg-amber-50', 'category-drop-above', 'category-drop-below');
        });

        // Reset estado
        this.draggedItem = null;
        this.draggedCategory = null;
        this.dragType = null;
    }

    onDragLeave(event) {
        // Verifica se realmente saiu do elemento (e não entrou em filho)
        const relatedTarget = event.relatedTarget;
        const currentTarget = event.currentTarget;

        if (relatedTarget && currentTarget.contains(relatedTarget)) {
            return; // Ainda está dentro do container
        }

        // Remove classes de highlight deste container
        currentTarget.classList.remove('drag-over', 'bg-primary-50', 'bg-amber-50', 'category-drop-above', 'category-drop-below');
    }

    onDragOver(event) {
        event.preventDefault();
        event.dataTransfer.dropEffect = 'move';

        if (this.dragType === 'categoria') {
            this.onCategoryDragOver(event);
            return;
        }

        // Drag de módulo - encontra o container de módulos mais próximo
        const modulosContainer = event.target.closest('[id^="modulos-"]');
        if (modulosContainer) {
            // Remove highlight de outros containers primeiro
            document.querySelectorAll('[id^="modulos-"].drag-over').forEach(el => {
                if (el !== modulosContainer) {
                    el.classList.remove('drag-over', 'bg-primary-50');
                }
            });
            modulosContainer.classList.add('drag-over', 'bg-primary-50');
        }
    }

    onDrop(event) {
        event.preventDefault();

        if (this.dragType === 'categoria') {
            this.onCategoryDrop(event);
            return;
        }

        // Drop de módulo
        const container = event.target.closest('[id^="modulos-"]');
        if (!container || !this.draggedItem) {
            this.limparEstadoDrag();
            return;
        }

        const novaSecao = container.dataset.secao;
        const moduloId = parseInt(this.draggedItem.dataset.moduloId);

        // Remove da seção antiga
        for (const [secao, ids] of Object.entries(this.modulosOrdem)) {
            const idx = ids.indexOf(moduloId);
            if (idx > -1) {
                ids.splice(idx, 1);
                break;
            }
        }

        // Adiciona na nova seção
        if (!this.modulosOrdem[novaSecao]) {
            this.modulosOrdem[novaSecao] = [];
        }
        this.modulosOrdem[novaSecao].push(moduloId);

        // Move elemento no DOM
        container.appendChild(this.draggedItem);

        // Limpa estado
        this.limparEstadoDrag();
    }

    // ========== DRAG DE CATEGORIAS ==========

    onCategoryDragStart(event, secao) {
        event.stopPropagation();
        this.dragType = 'categoria';
        this.draggedCategory = event.target.closest('[data-secao-container]');
        this.draggedItem = null;

        if (this.draggedCategory) {
            this.draggedCategory.classList.add('opacity-50', 'ring-2', 'ring-amber-500');
            event.dataTransfer.effectAllowed = 'move';
            event.dataTransfer.setData('text/plain', secao);
            event.dataTransfer.setData('application/x-drag-type', 'categoria');
        }
    }

    onCategoryDragOver(event) {
        const targetContainer = event.target.closest('[data-secao-container]');
        if (!targetContainer || targetContainer === this.draggedCategory) {
            return;
        }

        // Remove highlight de outras seções
        document.querySelectorAll('[data-secao-container].category-drop-above, [data-secao-container].category-drop-below').forEach(el => {
            if (el !== targetContainer) {
                el.classList.remove('category-drop-above', 'category-drop-below', 'bg-amber-50');
            }
        });

        // Determina se soltar acima ou abaixo baseado na posição do mouse
        const rect = targetContainer.getBoundingClientRect();
        const midY = rect.top + rect.height / 2;

        if (event.clientY < midY) {
            targetContainer.classList.remove('category-drop-below');
            targetContainer.classList.add('category-drop-above', 'bg-amber-50');
        } else {
            targetContainer.classList.remove('category-drop-above');
            targetContainer.classList.add('category-drop-below', 'bg-amber-50');
        }
    }

    onCategoryDrop(event) {
        const targetContainer = event.target.closest('[data-secao-container]');
        if (!targetContainer || !this.draggedCategory || targetContainer === this.draggedCategory) {
            this.limparEstadoDrag();
            return;
        }

        const draggedSecao = this.draggedCategory.dataset.secaoContainer;
        const targetSecao = targetContainer.dataset.secaoContainer;

        // Encontra índices atuais
        const draggedIdx = this.categoriasOrdem.indexOf(draggedSecao);
        const targetIdx = this.categoriasOrdem.indexOf(targetSecao);

        if (draggedIdx === -1 || targetIdx === -1) {
            this.limparEstadoDrag();
            return;
        }

        // Remove da posição atual
        this.categoriasOrdem.splice(draggedIdx, 1);

        // Calcula nova posição
        const rect = targetContainer.getBoundingClientRect();
        const midY = event.clientY;
        const isAbove = midY < rect.top + rect.height / 2;

        // Ajusta índice considerando a remoção
        let newIdx = this.categoriasOrdem.indexOf(targetSecao);
        if (!isAbove) {
            newIdx += 1;
        }

        // Insere na nova posição
        this.categoriasOrdem.splice(newIdx, 0, draggedSecao);

        console.log(`[CURADORIA] Categoria '${draggedSecao}' movida. Nova ordem: ${this.categoriasOrdem.join(', ')}`);

        // Re-renderiza a interface com a nova ordem
        this.limparEstadoDrag();
        this.renderizarInterfaceCuradoria();
    }

    limparEstadoDrag() {
        // Remove classes de drag do módulo
        if (this.draggedItem) {
            this.draggedItem.classList.remove('opacity-50', 'border-2', 'border-primary-500');
        }

        // Remove classes de drag da categoria
        if (this.draggedCategory) {
            this.draggedCategory.classList.remove('opacity-50', 'ring-2', 'ring-amber-500');
        }

        // Remove TODAS as classes de drop zone
        document.querySelectorAll('.drag-over, .bg-primary-50, .bg-amber-50, .category-drop-above, .category-drop-below').forEach(el => {
            el.classList.remove('drag-over', 'bg-primary-50', 'bg-amber-50', 'category-drop-above', 'category-drop-below');
        });

        this.draggedItem = null;
        this.draggedCategory = null;
        this.dragType = null;
    }

    // ========== MÓDULOS DISPONÍVEIS E FILTRO ==========

    /**
     * Carrega todos os módulos de conteúdo do grupo atual
     */
    async carregarModulosDisponiveis() {
        if (!this.currentGroupId) return;

        try {
            const response = await fetch(`/admin/api/prompts-modulos?group_id=${this.currentGroupId}&tipo=conteudo&apenas_ativos=true`, {
                headers: {
                    'Authorization': `Bearer ${app.getToken()}`
                }
            });

            if (!response.ok) {
                console.error('Erro ao carregar módulos disponíveis:', response.status);
                return;
            }

            const data = await response.json();
            // API retorna { prompts: [...] } ou diretamente array
            this.todosModulosDisponiveis = data.prompts || data || [];
            this.agruparModulosDisponiveis();

        } catch (error) {
            console.error('Erro ao carregar módulos disponíveis:', error);
        }
    }

    /**
     * Agrupa módulos por categoria, excluindo os já selecionados.
     * Usa a categoria definida diretamente no módulo (conforme cadastro no admin).
     * Apenas módulos sem categoria (null/undefined/"") vão para "Outros".
     */
    agruparModulosDisponiveis() {
        this.modulosDisponiveisAgrupados = {};

        for (const modulo of this.todosModulosDisponiveis) {
            // Pula módulos já selecionados
            if (this.modulosSelecionados.has(modulo.id)) continue;

            // Usa a categoria diretamente do módulo, ou "Outros" se não definida
            const categoria = (modulo.categoria && modulo.categoria.trim()) ? modulo.categoria : 'Outros';

            if (!this.modulosDisponiveisAgrupados[categoria]) {
                this.modulosDisponiveisAgrupados[categoria] = [];
            }
            this.modulosDisponiveisAgrupados[categoria].push(modulo);
        }

        // Ordena por título dentro de cada categoria
        for (const categoria of Object.keys(this.modulosDisponiveisAgrupados)) {
            this.modulosDisponiveisAgrupados[categoria].sort((a, b) =>
                (a.titulo || '').localeCompare(b.titulo || '')
            );
        }
    }

    /**
     * Renderiza módulos disponíveis agrupados na coluna direita.
     * Usa categoriasDisponiveis carregadas da API para manter ordem consistente.
     * Categorias não previstas na API mas presentes nos módulos são incluídas
     * antes de "Outros".
     */
    renderizarModulosAgrupados(filtro = '') {
        const container = document.getElementById('curadoria-busca-resultados');
        if (!container) return;

        // Atualiza agrupamento (exclui selecionados)
        this.agruparModulosDisponiveis();

        const filtroLower = filtro.toLowerCase().trim();
        let html = '';
        let totalModulos = 0;

        // Usa categorias da API, mas também inclui categorias encontradas nos módulos
        const categoriasAgrupadas = Object.keys(this.modulosDisponiveisAgrupados);
        const ordemSecoes = [...this.categoriasDisponiveis];

        // Adiciona categorias que existem nos módulos mas não estão na lista da API
        for (const cat of categoriasAgrupadas) {
            if (!ordemSecoes.includes(cat) && cat !== 'Outros') {
                // Insere antes de "Outros"
                const outrosIdx = ordemSecoes.indexOf('Outros');
                if (outrosIdx > -1) {
                    ordemSecoes.splice(outrosIdx, 0, cat);
                } else {
                    ordemSecoes.push(cat);
                }
            }
        }

        // Garante "Outros" no final
        if (!ordemSecoes.includes('Outros')) {
            ordemSecoes.push('Outros');
        }

        for (const secao of ordemSecoes) {
            let modulos = this.modulosDisponiveisAgrupados[secao] || [];

            // Aplica filtro se houver
            if (filtroLower) {
                modulos = modulos.filter(m =>
                    (m.titulo || '').toLowerCase().includes(filtroLower) ||
                    (m.subcategoria || '').toLowerCase().includes(filtroLower) ||
                    (m.condicao_ativacao || '').toLowerCase().includes(filtroLower)
                );
            }

            if (modulos.length === 0) continue;

            totalModulos += modulos.length;
            const isColapsada = this.secoesColapsadas[secao] === true;

            // Escapa aspas no nome da seção para evitar problemas no onclick
            const secaoEscapada = secao.replace(/'/g, "\\'");

            html += `
                <div class="mb-3">
                    <button onclick="curadoria.toggleSecaoDisponivel('${secaoEscapada}')"
                        class="w-full flex items-center justify-between p-2 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors">
                        <span class="font-medium text-gray-700 text-sm">
                            <i class="fas fa-chevron-${isColapsada ? 'right' : 'down'} mr-2 text-xs text-gray-400"></i>
                            ${secao}
                        </span>
                        <span class="text-xs bg-gray-200 text-gray-600 px-2 py-0.5 rounded-full">${modulos.length}</span>
                    </button>
                    <div id="disponivel-${secao}" class="${isColapsada ? 'hidden' : ''} mt-2 space-y-1 pl-2">
                        ${modulos.map(m => this.criarModuloDisponivelHTML(m)).join('')}
                    </div>
                </div>
            `;
        }

        if (totalModulos === 0) {
            container.innerHTML = `
                <div class="text-center py-8">
                    <i class="fas fa-check-circle text-2xl text-green-300 mb-2"></i>
                    <p class="text-sm text-gray-500">${filtro ? 'Nenhum argumento encontrado' : 'Todos argumentos foram adicionados'}</p>
                </div>
            `;
        } else {
            container.innerHTML = html;

            // Adiciona data-arg-json nos elementos
            for (const secao of ordemSecoes) {
                const modulos = this.modulosDisponiveisAgrupados[secao] || [];
                for (const m of modulos) {
                    const el = container.querySelector(`[data-arg-id="${m.id}"]`);
                    if (el) el.dataset.argJson = JSON.stringify(m);
                }
            }
        }
    }

    /**
     * Cria HTML para um módulo disponível (na lista agrupada)
     */
    criarModuloDisponivelHTML(modulo) {
        return `
            <div class="p-2 bg-white border border-gray-200 rounded-lg hover:border-primary-300 transition-colors text-sm" data-arg-id="${modulo.id}">
                <div class="flex items-start justify-between gap-2">
                    <div class="flex-1 min-w-0">
                        <p class="font-medium text-gray-800 text-xs break-words">${modulo.titulo || modulo.nome || 'Sem título'}</p>
                        ${modulo.subcategoria ? `<p class="text-xs text-gray-400">${modulo.subcategoria}</p>` : ''}
                    </div>
                    <button onclick="curadoria.adicionarArgumento(JSON.parse(this.closest('[data-arg-id]').dataset.argJson))"
                        class="p-1.5 bg-primary-500 text-white rounded-lg hover:bg-primary-600 transition-colors flex-shrink-0"
                        title="Adicionar argumento">
                        <i class="fas fa-plus text-xs"></i>
                    </button>
                </div>
            </div>
        `;
    }

    /**
     * Toggle seção colapsável na lista de disponíveis
     */
    toggleSecaoDisponivel(secao) {
        this.secoesColapsadas[secao] = !this.secoesColapsadas[secao];
        const el = document.getElementById(`disponivel-${secao}`);
        if (el) {
            el.classList.toggle('hidden');
        }
        // Atualiza ícone
        const btn = document.querySelector(`button[onclick*="toggleSecaoDisponivel('${secao}')"] i`);
        if (btn) {
            btn.className = `fas fa-chevron-${this.secoesColapsadas[secao] ? 'right' : 'down'} mr-2 text-xs text-gray-400`;
        }
    }

    /**
     * Debounce para filtro local
     */
    debounceBusca(query) {
        clearTimeout(this.buscarTimeout);

        // Se query vazia, mostra todos
        if (!query || query.length < 1) {
            this.renderizarModulosAgrupados('');
            return;
        }

        this.buscarTimeout = setTimeout(() => {
            this.renderizarModulosAgrupados(query);
        }, 200);
    }

    adicionarArgumento(argumento) {
        // argumento pode ser um objeto completo (da busca) ou apenas id/secao (legado)
        const moduloId = typeof argumento === 'object' ? argumento.id : argumento;
        const secao = typeof argumento === 'object' ? (argumento.categoria || 'MERITO') : arguments[1];

        // Adiciona ao estado
        this.modulosSelecionados.add(moduloId);
        // Marca como manual - foi adicionado pelo usuário
        this.modulosManuais.add(moduloId);
        console.log(`[CURADORIA] Módulo manual adicionado: ID ${moduloId}, seção ${secao}`);
        if (!this.modulosOrdem[secao]) {
            this.modulosOrdem[secao] = [];
        }
        this.modulosOrdem[secao].push(moduloId);

        // Usa dados do argumento se disponíveis, senão cria placeholder
        const modulo = typeof argumento === 'object' ? {
            id: argumento.id,
            titulo: argumento.titulo || argumento.nome || 'Argumento',
            categoria: secao,
            subcategoria: argumento.subcategoria || null,
            condicao_ativacao: argumento.condicao_ativacao || argumento.descricao || null,
            origem_ativacao: 'manual',
            validado: true,
            selecionado: true
        } : {
            id: moduloId,
            titulo: 'Argumento Adicionado',
            categoria: secao,
            origem_ativacao: 'manual',
            validado: true,
            selecionado: true
        };

        // Adiciona aos dados de curadoria para persistência
        if (!this.dadosCuradoria.modulos_por_secao[secao]) {
            this.dadosCuradoria.modulos_por_secao[secao] = [];
        }
        this.dadosCuradoria.modulos_por_secao[secao].push(modulo);

        // Adiciona a secao no DOM
        let secaoEl = document.getElementById(`modulos-${secao}`);
        if (!secaoEl) {
            // Cria secao se nao existir
            const container = document.getElementById('curadoria-secoes');
            const novaSecao = this.criarSecaoHTML(secao, [modulo]);
            container.appendChild(novaSecao);
        } else {
            secaoEl.insertAdjacentHTML('beforeend', this.criarModuloHTML(modulo));
        }

        this.atualizarContadorSelecionados();

        // Remove do resultado de busca/lista de disponíveis
        const cardBusca = document.querySelector(`[data-arg-id="${moduloId}"]`);
        if (cardBusca) {
            cardBusca.remove();
        }
    }

    mostrarDetalhesModulo(moduloId) {
        // Busca modulo
        let modulo = null;
        for (const modulos of Object.values(this.dadosCuradoria.modulos_por_secao)) {
            modulo = modulos.find(m => m.id === moduloId);
            if (modulo) break;
        }

        if (!modulo) return;

        // Mostra modal com detalhes
        const modal = document.createElement('div');
        modal.className = 'fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-[60]';
        modal.onclick = (e) => { if (e.target === modal) modal.remove(); };

        modal.innerHTML = `
            <div class="bg-white rounded-2xl max-w-2xl w-full mx-4 max-h-[80vh] overflow-hidden shadow-2xl">
                <div class="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
                    <h3 class="font-bold text-gray-800">${modulo.titulo}</h3>
                    <button onclick="this.closest('.fixed').remove()" class="p-2 text-gray-500 hover:text-gray-700">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
                <div class="p-6 overflow-y-auto custom-scrollbar" style="max-height: calc(80vh - 120px);">
                    <div class="mb-4">
                        <span class="text-xs px-2 py-1 bg-gray-100 text-gray-600 rounded-full mr-2">${modulo.categoria}</span>
                        ${modulo.subcategoria ? `<span class="text-xs px-2 py-1 bg-gray-100 text-gray-600 rounded-full">${modulo.subcategoria}</span>` : ''}
                    </div>
                    ${modulo.condicao_ativacao ? `
                        <div class="mb-4 p-3 bg-blue-50 rounded-lg">
                            <p class="text-sm text-blue-800"><strong>Condicao de ativacao:</strong> ${modulo.condicao_ativacao}</p>
                        </div>
                    ` : ''}
                    <div class="prose prose-sm max-w-none">
                        <div class="markdown-body text-gray-700">${marked.parse(modulo.conteudo || '')}</div>
                    </div>
                </div>
            </div>
        `;

        document.body.appendChild(modal);
    }

    // ========== GERACAO ==========

    async gerarComCuradoria() {
        if (this.modulosSelecionados.size === 0) {
            alert('Selecione pelo menos um argumento para gerar a peca.');
            return;
        }

        this.fecharModalCuradoria();

        // Usa o fluxo padrao de geracao com os modulos curados
        const numeroCnj = document.getElementById('numero-cnj').value;
        const tipoPeca = document.getElementById('tipo-peca').value || this.dadosCuradoria.tipo_peca;
        const observacao = document.getElementById('observacao-usuario').value;
        const groupId = document.getElementById('grupo-principal')?.value;
        const subcategoriaIds = app.getSubcategoriasIds?.() || [];

        // Mostra modal de progresso padrao
        app.mostrarLoading('Gerando peça com argumentos curados...', 3);

        try {
            const response = await fetch('/gerador-pecas/api/curadoria/gerar-stream', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${app.getToken()}`
                },
                body: JSON.stringify({
                    numero_cnj: numeroCnj,
                    tipo_peca: tipoPeca,
                    modulos_ids_curados: Array.from(this.modulosSelecionados),
                    modulos_manuais_ids: Array.from(this.modulosManuais), // IDs dos módulos adicionados manualmente
                    modulos_ordem: this.modulosOrdem,
                    categorias_ordem: this.categoriasOrdem, // Ordem das categorias definida pelo usuário
                    observacao_usuario: observacao,
                    group_id: groupId ? parseInt(groupId) : null,
                    subcategoria_ids: subcategoriaIds,
                    resumo_consolidado: this.dadosCuradoria.resumo_consolidado,
                    dados_extracao: this.dadosCuradoria.dados_extracao
                })
            });

            // Processa stream SSE usando o metodo do app principal
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.slice(6));
                            // Usa o processador de eventos do app principal
                            app.processarEventoStream(data);
                        } catch (e) {
                            console.error('Erro ao processar evento SSE:', e, line);
                        }
                    }
                }
            }

        } catch (error) {
            console.error('Erro na geracao curada:', error);
            app.esconderLoading();
            app.mostrarErro(error.message);
        }
    }
}

// Instancia global - deve ser window.curadoria para ser acessível pelo app.ts
window.curadoria = new CuradoriaModule();
