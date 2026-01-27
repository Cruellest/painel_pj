// Generated from TypeScript - DO NOT EDIT DIRECTLY
// Source: src\sistemas\gerador_pecas\app.ts
// Built at: 2026-01-24T19:56:06.920Z

"use strict";
(() => {
  // src/sistemas/gerador_pecas/app.ts
  var API_URL = "/gerador-pecas/api";
  var ADMIN_API_URL = "/admin/api/prompts-modulos";
  var FEATURE_FLAGS = {
    // Assuntos (Subcategorias de Conteudo) - funcionalidade desabilitada
    SUBCATEGORIAS_ENABLED: false
  };
  var GeradorPecasApp = class {
    constructor() {
      // State
      this.numeroCNJ = null;
      this.tipoPeca = null;
      this.geracaoId = null;
      this.notaSelecionada = null;
      this.isNovaGeracao = false;
      // Dados para o editor interativo
      this.minutaMarkdown = null;
      this.historicoChat = [];
      this.isProcessingEdit = false;
      // Modo de entrada: 'cnj' ou 'pdf'
      this.modoEntrada = "cnj";
      this.arquivosPdf = [];
      // Observacao do usuario para a IA
      this.observacaoUsuario = null;
      // Grupo e subcategorias de prompts
      this.groupId = null;
      this.subcategoriaIds = [];
      this.gruposDisponiveis = [];
      this.subcategoriasDisponiveis = [];
      this.requiresGroupSelection = false;
      this.isAdmin = false;
      // Dados para historico de versoes
      this.versoesLista = [];
      this.versaoSelecionada = null;
      this.painelVersoesAberto = false;
      // Streaming de geracao em tempo real
      this.streamingContent = "";
      this.isStreaming = false;
      // Flag de deteccao automatica de tipo de peca
      this.permiteAutoDetection = false;
      // Controlador para cancelar requisicoes
      this.abortController = null;
      // Timeout para erro
      this._erroTimeout = null;
      this.initEventListeners();
      this.checkAuth();
    }
    async checkAuth() {
      const token = localStorage.getItem("access_token");
      if (!token) {
        window.location.href = "/login";
        return;
      }
      try {
        const response = await fetch("/auth/me", {
          headers: { Authorization: `Bearer ${token}` }
        });
        if (!response.ok) {
          throw new Error("Token invalido");
        }
        const userData = await response.json();
        this.isAdmin = userData.role === "admin";
        this.carregarHistoricoRecente();
        this.carregarTiposPeca();
        this.carregarGruposDisponiveis();
      } catch (error) {
        localStorage.removeItem("access_token");
        window.location.href = "/login";
      }
    }
    async carregarTiposPeca() {
      try {
        const response = await fetch(`${API_URL}/tipos-peca`, {
          headers: { Authorization: `Bearer ${this.getToken()}` }
        });
        if (!response.ok) return;
        const data = await response.json();
        const select = document.getElementById("tipo-peca");
        if (!select) return;
        this.permiteAutoDetection = data.permite_auto === true;
        select.innerHTML = "";
        if (this.permiteAutoDetection) {
          const autoOption = document.createElement("option");
          autoOption.value = "";
          autoOption.textContent = "\u{1F916} Detectar automaticamente (IA decide)";
          select.appendChild(autoOption);
        } else {
          const placeholderOption = document.createElement("option");
          placeholderOption.value = "";
          placeholderOption.textContent = "-- Selecione o tipo de peca --";
          placeholderOption.disabled = true;
          placeholderOption.selected = true;
          select.appendChild(placeholderOption);
        }
        data.tipos.forEach((tipo) => {
          const option = document.createElement("option");
          option.value = tipo.valor;
          option.textContent = tipo.label;
          select.appendChild(option);
        });
        const helpText = select.parentElement?.querySelector("p.text-xs");
        if (helpText) {
          if (this.permiteAutoDetection) {
            helpText.textContent = "A IA analisa os documentos e decide qual peca gerar, ou selecione manualmente";
          } else {
            helpText.innerHTML = '<i class="fas fa-exclamation-circle text-amber-500 mr-1"></i>Selecao obrigatoria do tipo de peca';
          }
        }
      } catch (error) {
        console.error("Erro ao carregar tipos de peca:", error);
      }
    }
    async carregarGruposDisponiveis() {
      const select = document.getElementById("grupo-principal");
      const hint = document.getElementById("grupo-hint");
      const grupoContainer = document.getElementById("grupo-container");
      if (!select) {
        return;
      }
      try {
        const response = await fetch(`${API_URL}/grupos-disponiveis`, {
          headers: { Authorization: `Bearer ${this.getToken()}` }
        });
        if (!response.ok) return;
        const data = await response.json();
        this.gruposDisponiveis = data.grupos || [];
        this.requiresGroupSelection = !!data.requires_selection;
        select.innerHTML = "";
        if (this.gruposDisponiveis.length === 0) {
          select.disabled = true;
          const option = document.createElement("option");
          option.value = "";
          option.textContent = "Nenhum grupo disponivel";
          select.appendChild(option);
          if (hint) {
            hint.textContent = "Nenhum grupo ativo disponivel para o seu usuario.";
          }
          this.groupId = null;
          this.subcategoriaIds = [];
          this.subcategoriasDisponiveis = [];
          this.renderSubcategorias([]);
          return;
        }
        if (this.requiresGroupSelection) {
          if (grupoContainer) grupoContainer.classList.remove("hidden");
          const option = document.createElement("option");
          option.value = "";
          option.textContent = "Selecione o grupo...";
          select.appendChild(option);
          select.disabled = false;
          const defaultGroup = this.gruposDisponiveis.find(
            (grupo) => grupo.id === data.default_group_id
          );
          if (hint) {
            hint.textContent = defaultGroup ? `Grupo padrao: ${defaultGroup.nome}. Selecione o grupo para continuar.` : "Selecione o grupo de conteudo antes de gerar a peca.";
          }
        } else {
          if (grupoContainer) grupoContainer.classList.add("hidden");
          select.disabled = true;
        }
        this.gruposDisponiveis.forEach((grupo) => {
          const option = document.createElement("option");
          option.value = String(grupo.id);
          option.textContent = grupo.nome;
          select.appendChild(option);
        });
        if (!this.requiresGroupSelection && this.gruposDisponiveis.length === 1) {
          this.groupId = this.gruposDisponiveis[0].id;
          select.value = String(this.groupId);
          await this.carregarSubcategorias(this.groupId);
        } else {
          this.groupId = null;
          this.subcategoriaIds = [];
          this.subcategoriasDisponiveis = [];
          this.renderSubcategorias([]);
        }
      } catch (error) {
        console.error("Erro ao carregar grupos:", error);
      }
    }
    async carregarSubcategorias(groupId) {
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
          headers: { Authorization: `Bearer ${this.getToken()}` }
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
        console.error("Erro ao carregar subcategorias:", error);
        this.subcategoriasDisponiveis = [];
        this.renderSubcategorias([]);
      }
    }
    renderSubcategorias(subcategorias) {
      const container = document.getElementById("subcategoria-container");
      const options = document.getElementById("subcategoria-opcoes");
      const hint = document.getElementById("subcategoria-hint");
      if (!container || !options) {
        return;
      }
      if (!FEATURE_FLAGS.SUBCATEGORIAS_ENABLED) {
        container.classList.add("hidden");
        this.subcategoriaIds = [];
        return;
      }
      if (!this.groupId) {
        container.classList.add("hidden");
        return;
      }
      container.classList.remove("hidden");
      options.innerHTML = "";
      this.subcategoriaIds = [];
      options.appendChild(this.criarOpcaoSubcategoria("all", "Geral / Todos", true));
      if (subcategorias && subcategorias.length > 0) {
        if (hint) {
          hint.textContent = "Selecione um ou mais assuntos para filtrar os prompts de conteudo.";
        }
        subcategorias.forEach((subcategoria) => {
          options.appendChild(
            this.criarOpcaoSubcategoria(String(subcategoria.id), subcategoria.nome, false)
          );
        });
      } else if (hint) {
        hint.textContent = "Sem assuntos cadastrados. Usando Geral/Todos.";
      }
      options.querySelectorAll('input[name="subcategoria"]').forEach((input) => {
        input.addEventListener(
          "change",
          (event) => this.handleSubcategoriaChange(event)
        );
      });
    }
    criarOpcaoSubcategoria(valor, label, checked) {
      const wrapper = document.createElement("label");
      wrapper.className = "inline-flex items-center gap-2 px-3 py-2 rounded-full border border-gray-200 text-sm text-gray-700 bg-white hover:border-primary-300 hover:bg-primary-50 cursor-pointer transition-all";
      const input = document.createElement("input");
      input.type = "checkbox";
      input.name = "subcategoria";
      input.value = valor;
      input.checked = checked;
      input.className = "h-4 w-4 text-primary-600 rounded border-gray-300";
      const span = document.createElement("span");
      span.textContent = label;
      wrapper.appendChild(input);
      wrapper.appendChild(span);
      return wrapper;
    }
    handleGrupoChange(event) {
      const target = event.target;
      const value = target.value;
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
      const container = document.getElementById("subcategoria-opcoes");
      const allInput = container ? container.querySelector('input[value="all"]') : null;
      if (value === "all") {
        if (input.checked) {
          this.subcategoriaIds = [];
          if (container) {
            container.querySelectorAll('input[name="subcategoria"]').forEach((checkbox) => {
              if (checkbox.value !== "all") {
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
        this.showToast("Selecione um grupo primeiro", "warning");
        return;
      }
      const modal = document.getElementById("modal-subcategoria");
      const form = document.getElementById("form-subcategoria");
      const nomeInput = document.getElementById("subcategoria-nome");
      const slugInput = document.getElementById("subcategoria-slug");
      const descricaoInput = document.getElementById(
        "subcategoria-descricao"
      );
      if (nomeInput) nomeInput.value = "";
      if (slugInput) slugInput.value = "";
      if (descricaoInput) descricaoInput.value = "";
      if (nomeInput && slugInput) {
        nomeInput.oninput = () => {
          slugInput.value = this.slugify(nomeInput.value);
        };
      }
      if (form) {
        form.onsubmit = async (e) => {
          e.preventDefault();
          await this.criarSubcategoria();
        };
      }
      this.renderListaSubcategoriasModal();
      if (modal) modal.classList.remove("hidden");
    }
    fecharModalSubcategoria() {
      const modal = document.getElementById("modal-subcategoria");
      if (modal) modal.classList.add("hidden");
    }
    slugify(texto) {
      return texto.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
    }
    async criarSubcategoria() {
      const nomeInput = document.getElementById("subcategoria-nome");
      const slugInput = document.getElementById("subcategoria-slug");
      const descricaoInput = document.getElementById(
        "subcategoria-descricao"
      );
      const nome = nomeInput?.value.trim() || "";
      const slug = slugInput?.value.trim() || "";
      const descricao = descricaoInput?.value.trim() || "";
      if (!nome || !slug) {
        this.showToast("Nome e slug sao obrigatorios", "error");
        return;
      }
      try {
        const response = await fetch(`${ADMIN_API_URL}/grupos/${this.groupId}/subcategorias`, {
          method: "POST",
          headers: {
            Authorization: `Bearer ${this.getToken()}`,
            "Content-Type": "application/json"
          },
          body: JSON.stringify({ nome, slug, descricao: descricao || null })
        });
        if (!response.ok) {
          const error = await response.json();
          throw new Error(error.detail || "Erro ao criar subcategoria");
        }
        this.showToast("Assunto criado com sucesso", "success");
        if (nomeInput) nomeInput.value = "";
        if (slugInput) slugInput.value = "";
        if (descricaoInput) descricaoInput.value = "";
        await this.carregarSubcategorias(this.groupId);
        this.renderListaSubcategoriasModal();
      } catch (error) {
        console.error("Erro ao criar subcategoria:", error);
        this.showToast(error.message, "error");
      }
    }
    async deletarSubcategoria(id) {
      if (!confirm("Deseja realmente excluir este assunto?")) {
        return;
      }
      try {
        const response = await fetch(`${ADMIN_API_URL}/subcategorias/${id}`, {
          method: "DELETE",
          headers: {
            Authorization: `Bearer ${this.getToken()}`
          }
        });
        if (!response.ok) {
          const error = await response.json();
          throw new Error(error.detail || "Erro ao excluir subcategoria");
        }
        this.showToast("Assunto excluido", "success");
        await this.carregarSubcategorias(this.groupId);
        this.renderListaSubcategoriasModal();
      } catch (error) {
        console.error("Erro ao excluir subcategoria:", error);
        this.showToast(error.message, "error");
      }
    }
    renderListaSubcategoriasModal() {
      const container = document.getElementById("lista-subcategorias-modal");
      if (!container) return;
      if (!this.subcategoriasDisponiveis || this.subcategoriasDisponiveis.length === 0) {
        container.innerHTML = '<p class="text-gray-400 text-sm">Nenhum assunto cadastrado.</p>';
        return;
      }
      container.innerHTML = this.subcategoriasDisponiveis.map(
        (sub) => `
            <div class="flex items-center justify-between p-2 bg-gray-50 rounded-lg">
                <div>
                    <span class="text-sm font-medium text-gray-700">${this.escapeHtml(sub.nome)}</span>
                    <span class="text-xs text-gray-400 ml-2">(${this.escapeHtml(sub.slug)})</span>
                </div>
                <button type="button" onclick="app.deletarSubcategoria(${sub.id})"
                    class="p-1 text-red-400 hover:text-red-600 hover:bg-red-50 rounded transition-colors"
                    title="Excluir">
                    <i class="fas fa-trash-alt text-xs"></i>
                </button>
            </div>
        `
      ).join("");
    }
    // ==========================================
    // Modo de Entrada (CNJ ou PDF)
    // ==========================================
    setModoEntrada(modo) {
      this.modoEntrada = modo;
      const btnCnj = document.getElementById("btn-modo-cnj");
      const btnPdf = document.getElementById("btn-modo-pdf");
      const modoCnj = document.getElementById("modo-cnj");
      const modoPdf = document.getElementById("modo-pdf");
      if (modo === "cnj") {
        if (btnCnj)
          btnCnj.className = "flex-1 py-2.5 px-4 rounded-lg font-medium transition-all bg-white shadow text-primary-700";
        if (btnPdf)
          btnPdf.className = "flex-1 py-2.5 px-4 rounded-lg font-medium transition-all text-gray-500 hover:text-gray-700";
        if (modoCnj) modoCnj.classList.remove("hidden");
        if (modoPdf) modoPdf.classList.add("hidden");
      } else {
        if (btnPdf)
          btnPdf.className = "flex-1 py-2.5 px-4 rounded-lg font-medium transition-all bg-white shadow text-primary-700";
        if (btnCnj)
          btnCnj.className = "flex-1 py-2.5 px-4 rounded-lg font-medium transition-all text-gray-500 hover:text-gray-700";
        if (modoPdf) modoPdf.classList.remove("hidden");
        if (modoCnj) modoCnj.classList.add("hidden");
      }
    }
    handleFileSelect(event) {
      const target = event.target;
      const files = Array.from(target.files || []);
      this.adicionarArquivos(files);
    }
    handleDrop(event) {
      event.preventDefault();
      const target = event.currentTarget;
      target.classList.remove("border-primary-500", "bg-primary-50");
      const files = Array.from(event.dataTransfer?.files || []).filter(
        (f) => f.type === "application/pdf"
      );
      if (files.length === 0) {
        this.showToast("Apenas arquivos PDF sao aceitos", "error");
        return;
      }
      this.adicionarArquivos(files);
    }
    adicionarArquivos(files) {
      for (const file of files) {
        if (file.type !== "application/pdf") {
          this.showToast(`Arquivo ignorado (nao e PDF): ${file.name}`, "warning");
          continue;
        }
        if (!this.arquivosPdf.find((f) => f.name === file.name && f.size === file.size)) {
          this.arquivosPdf.push(file);
        }
      }
      this.atualizarListaArquivos();
    }
    atualizarListaArquivos() {
      const container = document.getElementById("lista-arquivos");
      const lista = document.getElementById("arquivos-lista");
      if (!container || !lista) return;
      if (this.arquivosPdf.length === 0) {
        container.classList.add("hidden");
        return;
      }
      container.classList.remove("hidden");
      lista.innerHTML = this.arquivosPdf.map(
        (file, index) => `
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
        `
      ).join("");
    }
    removerArquivo(index) {
      this.arquivosPdf.splice(index, 1);
      this.atualizarListaArquivos();
    }
    limparArquivos() {
      this.arquivosPdf = [];
      this.atualizarListaArquivos();
      const input = document.getElementById("input-pdfs");
      if (input) input.value = "";
    }
    formatarTamanho(bytes) {
      if (bytes < 1024) return bytes + " B";
      if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
      return (bytes / (1024 * 1024)).toFixed(1) + " MB";
    }
    initEventListeners() {
      const formProcesso = document.getElementById("form-processo");
      if (formProcesso) {
        formProcesso.addEventListener("submit", (e) => {
          e.preventDefault();
          this.iniciarProcessamento();
        });
      }
      const grupoSelect = document.getElementById("grupo-principal");
      if (grupoSelect) {
        grupoSelect.addEventListener("change", (e) => {
          this.handleGrupoChange(e);
        });
      }
      const btnCancelarPergunta = document.getElementById("btn-cancelar-pergunta");
      if (btnCancelarPergunta) {
        btnCancelarPergunta.addEventListener("click", () => {
          this.fecharModal("modal-pergunta");
        });
      }
      const btnEnviarResposta = document.getElementById("btn-enviar-resposta");
      if (btnEnviarResposta) {
        btnEnviarResposta.addEventListener("click", () => {
          this.enviarResposta();
        });
      }
      const btnEnviarChat = document.getElementById("btn-enviar-chat");
      if (btnEnviarChat) {
        btnEnviarChat.addEventListener("click", () => {
          this.enviarMensagemChat();
        });
      }
      const chatInput = document.getElementById("chat-input");
      if (chatInput) {
        chatInput.addEventListener("keypress", (e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            this.enviarMensagemChat();
          }
        });
      }
      const btnCopiarMinuta = document.getElementById("btn-copiar-minuta");
      if (btnCopiarMinuta) {
        btnCopiarMinuta.addEventListener("click", () => {
          this.copiarMinuta();
        });
      }
      document.querySelectorAll(".estrela").forEach((btn) => {
        btn.addEventListener("click", (e) => {
          const target = e.target;
          const nota = parseInt(target.dataset.nota || "0", 10);
          this.selecionarNota(nota);
        });
      });
      const btnPularFeedback = document.getElementById("btn-pular-feedback");
      if (btnPularFeedback) {
        btnPularFeedback.addEventListener("click", () => {
          this.fecharModal("modal-feedback");
          this.resetar();
        });
      }
      const btnEnviarFeedback = document.getElementById("btn-enviar-feedback");
      if (btnEnviarFeedback) {
        btnEnviarFeedback.addEventListener("click", () => {
          this.enviarFeedback();
        });
      }
    }
    async iniciarProcessamento() {
      const tipoPecaSelect = document.getElementById("tipo-peca");
      const observacaoInput = document.getElementById(
        "observacao-usuario"
      );
      this.tipoPeca = tipoPecaSelect?.value || null;
      this.observacaoUsuario = observacaoInput?.value.trim() || null;
      if (!this.permiteAutoDetection && !this.tipoPeca) {
        this.mostrarErro("Selecione obrigatoriamente o tipo de peca.");
        tipoPecaSelect?.focus();
        return;
      }
      if (this.requiresGroupSelection && !this.groupId) {
        this.mostrarErro("Selecione o grupo de conteudo antes de gerar a peca.");
        return;
      }
      if (!this.groupId) {
        this.mostrarErro("Nenhum grupo de conteudo disponivel para geracao.");
        return;
      }
      this.streamingContent = "";
      this.isStreaming = false;
      this.esconderErro();
      this.resetarStatusAgentes();
      this.mostrarLoading("Conectando ao servidor...", null);
      try {
        let response;
        if (this.modoEntrada === "pdf") {
          if (this.arquivosPdf.length === 0) {
            throw new Error("Selecione pelo menos um arquivo PDF");
          }
          this.numeroCNJ = "PDFs Anexados";
          const formData = new FormData();
          for (const file of this.arquivosPdf) {
            formData.append("arquivos", file);
          }
          if (this.tipoPeca) {
            formData.append("tipo_peca", this.tipoPeca);
          }
          if (this.observacaoUsuario) {
            formData.append("observacao_usuario", this.observacaoUsuario);
          }
          if (this.groupId) {
            formData.append("group_id", String(this.groupId));
          }
          response = await fetch(`${API_URL}/processar-pdfs-stream`, {
            method: "POST",
            headers: {
              Authorization: `Bearer ${this.getToken()}`
            },
            body: formData
          });
        } else {
          const numeroCnjInput = document.getElementById("numero-cnj");
          this.numeroCNJ = numeroCnjInput?.value || null;
          if (!this.numeroCNJ) {
            throw new Error("Informe o numero do processo");
          }
          response = await fetch(`${API_URL}/processar-stream`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${this.getToken()}`
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
          throw new Error(errorData.detail || "Erro ao processar");
        }
        const reader = response.body?.getReader();
        if (!reader) throw new Error("Stream nao disponivel");
        const decoder = new TextDecoder();
        let buffer = "";
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n\n");
          buffer = lines.pop() || "";
          for (const line of lines) {
            if (line.startsWith("data: ")) {
              try {
                const data = JSON.parse(line.slice(6));
                this.processarEventoStream(data);
              } catch (e) {
                console.warn("Erro ao parsear evento SSE:", e);
              }
            }
          }
        }
      } catch (error) {
        console.error("Erro na requisicao:", error);
        let mensagemErro = error.message;
        if (error.name === "TypeError" && error.message === "Failed to fetch") {
          mensagemErro = "Nao foi possivel conectar ao servidor. Possiveis causas:\n- Conexao de internet instavel\n- A solicitacao e muito grande e demorou demais\n- O servidor esta temporariamente indisponivel\n\nTente novamente ou divida seu pedido em partes menores.";
        } else if (error.name === "AbortError") {
          mensagemErro = "A solicitacao foi cancelada.";
        } else if (error.message.includes("network") || error.message.includes("Network")) {
          mensagemErro = "Erro de conexao de rede. Verifique sua internet e tente novamente.";
        } else if (error.message.includes("timeout") || error.message.includes("Timeout")) {
          mensagemErro = "A solicitacao demorou mais que o esperado. Tente novamente ou use um pedido mais simples.";
        }
        this.mostrarErro(mensagemErro);
        this.esconderLoading();
      }
    }
    processarEventoStream(data) {
      console.log("Evento SSE:", data);
      switch (data.tipo) {
        case "inicio":
          {
            const progressoMensagem = document.getElementById("progresso-mensagem");
            if (progressoMensagem) progressoMensagem.textContent = data.mensagem || "";
          }
          break;
        case "agente":
          {
            this.atualizarStatusAgente(data.agente || 1, data.status || "ativo");
            const progressoMensagem = document.getElementById("progresso-mensagem");
            if (progressoMensagem) progressoMensagem.textContent = data.mensagem || "";
            if (data.status === "erro") {
              this.mostrarErro(data.mensagem || "Erro desconhecido");
              this.esconderLoading();
            }
          }
          break;
        case "pergunta":
          this.esconderLoading();
          this.exibirPergunta(data);
          break;
        case "sucesso":
          {
            const progressoBarra = document.getElementById("progresso-barra");
            if (progressoBarra) progressoBarra.style.width = "100%";
            this.atualizarStatusAgente(3, "concluido");
            const conteudoFinal = this.isStreaming ? this.streamingContent : data.minuta_markdown || "";
            if (this.isStreaming) {
              this.finalizarEditorStreaming(
                data.geracao_id || null,
                data.tipo_peca || null,
                conteudoFinal
              );
              this.esconderLoading();
              this.showToast("Peca gerada com sucesso!", "success");
            } else {
              this.finalizarStreaming();
              setTimeout(() => {
                this.esconderLoading();
                this.showToast("Peca gerada com sucesso!", "success");
                this.exibirEditor(
                  {
                    status: "sucesso",
                    geracao_id: data.geracao_id || 0,
                    tipo_peca: data.tipo_peca || "",
                    minuta_markdown: conteudoFinal || data.minuta_markdown || ""
                  },
                  true
                );
              }, 500);
            }
          }
          break;
        case "erro":
          this.finalizarStreaming();
          this.esconderLoading();
          this.mostrarErro(data.mensagem || "Erro desconhecido");
          break;
        case "info":
          {
            const progressoMensagem = document.getElementById("progresso-mensagem");
            if (progressoMensagem) progressoMensagem.textContent = data.mensagem || "";
          }
          break;
        case "geracao_chunk":
          console.log("CHUNK RECEBIDO:", data.content?.substring(0, 50));
          try {
            if (!this.isStreaming) {
              console.log("Iniciando streaming - abrindo editor");
              this.isStreaming = true;
              this.streamingContent = "";
              this.abrirEditorStreaming();
            }
            this.streamingContent += data.content || "";
            this.atualizarEditorStreaming();
          } catch (err) {
            console.error("Erro no streaming:", err);
          }
          break;
        default:
          if (data.status === "pergunta") {
            this.esconderLoading();
            this.exibirPergunta(data);
          } else if (data.status === "sucesso") {
            this.esconderLoading();
            this.exibirEditor(
              {
                status: "sucesso",
                geracao_id: data.geracao_id || 0,
                tipo_peca: data.tipo_peca || "",
                minuta_markdown: data.minuta_markdown || ""
              },
              true
            );
          } else if (data.status === "erro") {
            this.esconderLoading();
            this.mostrarErro(data.mensagem || "Erro desconhecido");
          }
      }
    }
    exibirPergunta(data) {
      const perguntaTexto = document.getElementById("pergunta-texto");
      if (perguntaTexto) perguntaTexto.textContent = data.pergunta || "";
      const opcoesContainer = document.getElementById("opcoes-container");
      if (!opcoesContainer) return;
      opcoesContainer.innerHTML = "";
      if (data.opcoes && data.opcoes.length > 0) {
        data.opcoes.forEach((opcao) => {
          const btn = document.createElement("button");
          btn.className = "w-full px-4 py-3 text-left border border-gray-200 rounded-xl hover:bg-primary-50 hover:border-primary-500 transition-all shadow-sm";
          btn.textContent = this.formatarOpcao(opcao);
          btn.addEventListener("click", () => {
            this.tipoPeca = opcao;
            this.enviarResposta();
          });
          opcoesContainer.appendChild(btn);
        });
      }
      if (data.mensagem) {
        const p = document.createElement("p");
        p.className = "text-sm text-amber-700 mt-4 p-3 bg-amber-50 rounded-xl border border-amber-200";
        p.innerHTML = `<i class="fas fa-info-circle mr-1"></i> ${data.mensagem}`;
        opcoesContainer.appendChild(p);
      }
      this.abrirModal("modal-pergunta");
    }
    async enviarResposta() {
      const respostaInput = document.getElementById("resposta-usuario");
      const resposta = respostaInput?.value || this.tipoPeca;
      this.streamingContent = "";
      this.isStreaming = false;
      this.fecharModal("modal-pergunta");
      this.resetarStatusAgentes();
      this.atualizarStatusAgente(1, "concluido");
      this.mostrarLoading("Continuando processamento...", 2);
      try {
        const response = await fetch(`${API_URL}/processar-stream`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${this.getToken()}`
          },
          body: JSON.stringify({
            numero_cnj: this.numeroCNJ,
            tipo_peca: this.tipoPeca,
            resposta_usuario: resposta
          })
        });
        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.detail || "Erro ao processar");
        }
        const reader = response.body?.getReader();
        if (!reader) throw new Error("Stream nao disponivel");
        const decoder = new TextDecoder();
        let buffer = "";
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n\n");
          buffer = lines.pop() || "";
          for (const line of lines) {
            if (line.startsWith("data: ")) {
              try {
                const data = JSON.parse(line.slice(6));
                this.processarEventoStream(data);
              } catch (e) {
                console.warn("Erro ao parsear evento SSE:", e);
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
      let markdown = data.minuta_markdown || "*Conteudo nao disponivel*";
      if (typeof markdown === "string") {
        try {
          if (markdown.startsWith('"') && markdown.endsWith('"')) {
            markdown = JSON.parse(markdown);
          }
        } catch (e) {
        }
      }
      this.minutaMarkdown = markdown;
      this.historicoChat = [];
      this.versoesLista = [];
      this.versaoSelecionada = null;
      this.painelVersoesAberto = false;
      document.getElementById("painel-versoes")?.classList.add("hidden");
      document.getElementById("versao-detalhe")?.classList.add("hidden");
      document.getElementById("versoes-count")?.classList.add("hidden");
      const editorTipoPeca = document.getElementById("editor-tipo-peca");
      if (editorTipoPeca) editorTipoPeca.textContent = this.formatarOpcao(data.tipo_peca);
      const editorCnj = document.getElementById("editor-cnj");
      if (editorCnj) editorCnj.textContent = this.numeroCNJ ? `- ${this.numeroCNJ}` : "";
      this.renderizarMinuta();
      this.resetarChat();
      this.abrirModal("modal-editor");
      this.carregarHistoricoRecente();
      this.carregarContagemVersoes();
    }
    async carregarContagemVersoes() {
      if (!this.geracaoId) return;
      try {
        const response = await fetch(`${API_URL}/historico/${this.geracaoId}/versoes`, {
          headers: { Authorization: `Bearer ${this.getToken()}` }
        });
        if (!response.ok) return;
        const data = await response.json();
        const countEl = document.getElementById("versoes-count");
        if (countEl && data.total_versoes > 0) {
          countEl.textContent = String(data.total_versoes);
          countEl.classList.remove("hidden");
        }
      } catch (error) {
        console.error("Erro ao carregar contagem de versoes:", error);
      }
    }
    renderizarMinuta() {
      const container = document.getElementById("minuta-content");
      if (!container) return;
      console.log("Markdown a renderizar:", this.minutaMarkdown?.substring(0, 200));
      const marked = window.marked;
      if (marked) {
        marked.setOptions({
          breaks: true,
          gfm: true
        });
        container.innerHTML = marked.parse(this.minutaMarkdown || "");
      } else {
        container.innerHTML = (this.minutaMarkdown || "").replace(/## (.*)/g, "<h2>$1</h2>").replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>").replace(/\*(.*?)\*/g, "<em>$1</em>").replace(/\n/g, "<br>");
      }
      const minutaStatus = document.getElementById("minuta-status");
      if (minutaStatus) minutaStatus.textContent = "Atualizado agora";
    }
    resetarChat() {
      const chatContainer = document.getElementById("chat-messages");
      if (chatContainer) {
        chatContainer.innerHTML = `
            <div class="flex gap-3">
                <div class="w-8 h-8 bg-gradient-to-br from-primary-500 to-primary-600 rounded-full flex items-center justify-center flex-shrink-0">
                    <i class="fas fa-robot text-white text-xs"></i>
                </div>
                <div class="chat-bubble-ai px-4 py-3 max-w-[85%]">
                    <p class="text-sm text-gray-700">
                        Ola! Sou o assistente de edicao. Voce pode me pedir para fazer alteracoes na minuta, como:
                    </p>
                    <ul class="text-xs text-gray-500 mt-2 space-y-1">
                        <li>- "Adicione um argumento sobre prescricao"</li>
                        <li>- "Mude o tom do item II para ser mais assertivo"</li>
                        <li>- "Inclua jurisprudencia do STJ"</li>
                    </ul>
                </div>
            </div>
        `;
      }
      const chatInput = document.getElementById("chat-input");
      if (chatInput) chatInput.value = "";
    }
    async enviarMensagemChat() {
      const input = document.getElementById("chat-input");
      const mensagem = input?.value.trim();
      if (!mensagem || this.isProcessingEdit) return;
      if (input) input.value = "";
      this.isProcessingEdit = true;
      this.adicionarMensagemChat("user", mensagem);
      this.mostrarTypingIndicator();
      try {
        const response = await fetch(`${API_URL}/editar-minuta-stream`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${this.getToken()}`
          },
          body: JSON.stringify({
            minuta_atual: this.minutaMarkdown,
            mensagem,
            historico: this.historicoChat,
            tipo_peca: this.tipoPeca
          })
        });
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const reader = response.body?.getReader();
        if (!reader) throw new Error("Stream nao disponivel");
        const decoder = new TextDecoder();
        let buffer = "";
        let minutaCompleta = "";
        let primeiroChunk = true;
        let isPergunta = false;
        const minutaOriginal = this.minutaMarkdown; // Guarda minuta original
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";
          for (const line of lines) {
            if (line.startsWith("event: ")) {
              continue;
            }
            if (line.startsWith("data: ")) {
              const data = line.substring(6);
              if (data === "[DONE]") {
                continue;
              }
              if (data.trim() === "" || data === ":heartbeat") {
                continue;
              }
              try {
                const parsed = JSON.parse(data);
                if (parsed.error) {
                  throw new Error(parsed.error);
                }
                if (parsed.text) {
                  if (primeiroChunk) {
                    this.esconderTypingIndicator();
                    primeiroChunk = false;
                  }
                  minutaCompleta += parsed.text;
                  // Verifica se é pergunta nos primeiros caracteres
                  if (!isPergunta && minutaCompleta.length < 50) {
                    isPergunta = /^\s*\[PERGUNTA\]/i.test(minutaCompleta);
                  }
                  // Só atualiza visualização se NÃO for pergunta
                  if (!isPergunta && minutaCompleta.length % 500 < parsed.text.length) {
                    this.minutaMarkdown = minutaCompleta;
                    this.renderizarMinuta();
                  }
                }
              } catch (e) {
              }
            }
          }
        }
        this.esconderTypingIndicator();
        if (minutaCompleta) {
          // Verifica se a resposta é uma pergunta de clarificação
          // Detecta [PERGUNTA] no início (com possíveis espaços/quebras antes)
          const perguntaMatch = minutaCompleta.match(/^\s*\[PERGUNTA\]\s*/i);
          if (perguntaMatch || isPergunta) {
            // Restaura a minuta original (não foi alterada)
            this.minutaMarkdown = minutaOriginal;
            this.renderizarMinuta();
            // Remove o marcador [PERGUNTA] e mostra no chat
            const perguntaTexto = minutaCompleta.replace(/^\s*\[PERGUNTA\]\s*/i, "").trim();
            this.historicoChat.push({ role: "user", content: mensagem });
            this.historicoChat.push({ role: "assistant", content: perguntaTexto });
            this.adicionarMensagemChat("ai", perguntaTexto, true, null, true);
          } else {
            // Resposta normal - atualiza a minuta
            this.minutaMarkdown = minutaCompleta;
            this.renderizarMinuta();
            this.historicoChat.push({ role: "user", content: mensagem });
            this.historicoChat.push({ role: "assistant", content: "Minuta atualizada com sucesso." });
            this.adicionarMensagemChat(
              "ai",
              "Pronto! Atualizei a minuta conforme solicitado. Veja as alteracoes na visualizacao ao lado.",
              true
            );
            this.destacarMinuta();
            this.salvarMinutaAuto();
          }
        } else {
          this.adicionarMensagemChat(
            "ai",
            "Nao foi possivel processar a edicao. Tente novamente.",
            false
          );
        }
      } catch (error) {
        this.esconderTypingIndicator();
        this.adicionarMensagemChat("ai", `Erro ao processar: ${error.message}`, false);
      } finally {
        this.isProcessingEdit = false;
      }
    }
    // Renderiza markdown básico para HTML (negrito, itálico)
    renderMarkdownBasico(texto) {
      let html = this.escapeHtml(texto);
      // Negrito: **texto** -> <strong>texto</strong>
      html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
      // Itálico: *texto* -> <em>texto</em>
      html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');
      // Quebras de linha
      html = html.replace(/\n/g, '<br>');
      return html;
    }
    adicionarMensagemChat(tipo, conteudo, sucesso = true, indice = null, usarMarkdown = false) {
      const chatContainer = document.getElementById("chat-messages");
      if (!chatContainer) return;
      if (indice === null) {
        indice = this.historicoChat.length;
      }
      const msgDiv = document.createElement("div");
      msgDiv.className = tipo === "user" ? "flex gap-3 justify-end group" : "flex gap-3 group";
      msgDiv.dataset.chatIndex = String(indice);
      if (tipo === "user") {
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
        const iconClass = sucesso ? "fa-check-circle text-green-500" : "fa-exclamation-circle text-red-500";
        const conteudoHtml = usarMarkdown ? this.renderMarkdownBasico(conteudo) : this.escapeHtml(conteudo);
        msgDiv.innerHTML = `
                <div class="w-8 h-8 bg-gradient-to-br from-primary-500 to-primary-600 rounded-full flex items-center justify-center flex-shrink-0">
                    <i class="fas fa-robot text-white text-xs"></i>
                </div>
                <div class="chat-bubble-ai px-4 py-3 max-w-[85%]">
                    <div class="text-sm text-gray-700">
                        <i class="fas ${iconClass} mr-1"></i>
                        ${conteudoHtml}
                    </div>
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
      const startIdx = Math.floor(indice / 2) * 2;
      this.historicoChat.splice(startIdx, 2);
      this.renderizarChatHistorico();
      this.salvarMinutaAuto();
      this.showToast("Mensagem removida", "success");
    }
    limparTodoHistoricoChat() {
      if (this.historicoChat.length === 0) {
        this.showToast("Historico ja esta vazio", "warning");
        return;
      }
      if (!confirm("Tem certeza que deseja limpar todo o historico do chat?")) {
        return;
      }
      this.historicoChat = [];
      this.resetarChat();
      this.salvarMinutaAuto();
      this.showToast("Historico do chat limpo", "success");
    }
    mostrarTypingIndicator() {
      const chatContainer = document.getElementById("chat-messages");
      if (!chatContainer) return;
      const typingDiv = document.createElement("div");
      typingDiv.id = "typing-indicator";
      typingDiv.className = "flex gap-3";
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
      const indicator = document.getElementById("typing-indicator");
      if (indicator) indicator.remove();
    }
    destacarMinuta() {
      const container = document.getElementById("minuta-container");
      if (container) {
        container.classList.add("pulse-glow");
        setTimeout(() => container.classList.remove("pulse-glow"), 2e3);
      }
    }
    async copiarMinuta() {
      try {
        await navigator.clipboard.writeText(this.minutaMarkdown || "");
        this.showToast("Minuta copiada para a area de transferencia!", "success");
        const btn = document.getElementById("btn-copiar-minuta");
        if (btn) {
          const originalHTML = btn.innerHTML;
          btn.innerHTML = '<i class="fas fa-check"></i> Copiado!';
          setTimeout(() => {
            btn.innerHTML = originalHTML;
          }, 2e3);
        }
      } catch (error) {
        this.showToast("Erro ao copiar minuta", "error");
      }
    }
    async downloadDocx() {
      if (!this.minutaMarkdown) {
        this.showToast("Nenhuma minuta para exportar", "error");
        return;
      }
      const btn = document.getElementById("btn-download-docx");
      if (!btn) return;
      const originalHTML = btn.innerHTML;
      try {
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Gerando...';
        btn.disabled = true;
        const response = await fetch(`${API_URL}/exportar-docx`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${this.getToken()}`
          },
          body: JSON.stringify({
            markdown: this.minutaMarkdown,
            numero_cnj: this.numeroCNJ,
            tipo_peca: this.tipoPeca
          })
        });
        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.detail || "Erro ao gerar documento");
        }
        const data = await response.json();
        if (data.status === "sucesso" && data.url_download) {
          const downloadUrl = `${data.url_download}?token=${encodeURIComponent(this.getToken())}`;
          const link = document.createElement("a");
          link.href = downloadUrl;
          link.download = data.filename || "peca_juridica.docx";
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
          this.showToast("Download iniciado!", "success");
          btn.innerHTML = '<i class="fas fa-check"></i> Baixado!';
          setTimeout(() => {
            btn.innerHTML = originalHTML;
            btn.disabled = false;
          }, 2e3);
        } else {
          throw new Error(data.mensagem || "Erro desconhecido");
        }
      } catch (error) {
        console.error("Erro ao baixar DOCX:", error);
        this.showToast(`Erro: ${error.message}`, "error");
        btn.innerHTML = originalHTML;
        btn.disabled = false;
      }
    }
    abrirAutos() {
      if (!this.numeroCNJ || this.numeroCNJ === "PDFs Anexados") {
        this.showToast("Autos disponiveis apenas para processos do TJ-MS", "warning");
        return;
      }
      const token = this.getToken();
      const url = `/gerador-pecas/autos.html?cnj=${encodeURIComponent(this.numeroCNJ)}&token=${encodeURIComponent(token)}`;
      window.open(url, "_blank");
    }
    escapeHtml(text) {
      const div = document.createElement("div");
      div.textContent = text;
      return div.innerHTML;
    }
    // ==========================================
    // Historico
    // ==========================================
    async carregarHistoricoRecente() {
      const container = document.getElementById("historico-cards");
      if (!container) return;
      try {
        const response = await fetch(`${API_URL}/historico`, {
          headers: { Authorization: `Bearer ${this.getToken()}` }
        });
        if (!response.ok) throw new Error("Erro ao carregar");
        const historico = await response.json();
        if (historico.length === 0) {
          container.innerHTML = `
                    <div class="text-center py-8 text-gray-400">
                        <i class="fas fa-file-alt text-4xl mb-3 opacity-50"></i>
                        <p class="text-sm">Nenhuma peca gerada ainda</p>
                        <p class="text-xs mt-1">Use o formulario acima para gerar sua primeira peca</p>
                    </div>
                `;
          return;
        }
        const recentes = historico.slice(0, 5);
        container.innerHTML = recentes.map(
          (item) => `
                <div class="flex items-center gap-4 p-4 border border-gray-100 rounded-xl hover:bg-primary-50 hover:border-primary-300 transition-all cursor-pointer group"
                     onclick="app.abrirGeracao(${item.id})">
                    <div class="w-12 h-12 bg-gradient-to-br from-purple-100 to-indigo-100 rounded-xl flex items-center justify-center group-hover:from-purple-200 group-hover:to-indigo-200 transition-colors">
                        <i class="fas fa-file-alt text-purple-600"></i>
                    </div>
                    <div class="flex-1 min-w-0">
                        <p class="font-medium text-gray-800 truncate group-hover:text-primary-700">${this.escapeHtml(item.cnj)}</p>
                        <p class="text-sm text-primary-600 font-medium">${this.formatarOpcao(item.tipo_peca)}</p>
                    </div>
                    <div class="text-right flex-shrink-0">
                        <p class="text-xs text-gray-400">${new Date(item.data).toLocaleDateString("pt-BR")}</p>
                        <p class="text-xs text-gray-300">${new Date(item.data).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}</p>
                    </div>
                    <button onclick="event.stopPropagation(); app.deletarHistorico(${item.id})"
                        class="opacity-0 group-hover:opacity-100 p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-all"
                        title="Excluir do historico">
                        <i class="fas fa-trash-alt text-sm"></i>
                    </button>
                    <i class="fas fa-chevron-right text-gray-300 group-hover:text-primary-500 transition-colors"></i>
                </div>
            `
        ).join("");
        if (historico.length > 5) {
          container.innerHTML += `
                    <div class="text-center py-2">
                        <button onclick="toggleHistorico()" class="text-sm text-primary-600 hover:text-primary-700 font-medium">
                            Ver mais ${historico.length - 5} pecas <i class="fas fa-arrow-right ml-1"></i>
                        </button>
                    </div>
                `;
        }
      } catch (error) {
        container.innerHTML = `
                <div class="text-center py-4 text-red-500">
                    <i class="fas fa-exclamation-circle mr-2"></i>
                    Erro ao carregar historico
                </div>
            `;
      }
    }
    async carregarHistorico() {
      const lista = document.getElementById("lista-historico");
      if (!lista) return;
      try {
        const response = await fetch(`${API_URL}/historico`, {
          headers: { Authorization: `Bearer ${this.getToken()}` }
        });
        if (!response.ok) throw new Error("Erro ao carregar");
        const historico = await response.json();
        if (historico.length === 0) {
          lista.innerHTML = '<p class="text-gray-500 text-sm text-center py-8">Nenhuma geracao encontrada</p>';
          return;
        }
        lista.innerHTML = historico.map(
          (item) => `
                <div class="border border-gray-100 rounded-xl p-3 mb-2 hover:bg-primary-50 hover:border-primary-300 transition-all cursor-pointer shadow-sm group"
                     onclick="app.abrirGeracao(${item.id})">
                    <div class="flex items-center justify-between">
                        <div class="flex-1">
                            <p class="font-medium text-sm text-gray-800 group-hover:text-primary-700">${this.escapeHtml(item.cnj)}</p>
                            <p class="text-xs text-primary-600 font-medium">${this.formatarOpcao(item.tipo_peca)}</p>
                            <p class="text-xs text-gray-400 mt-1">${new Date(item.data).toLocaleDateString("pt-BR")}</p>
                        </div>
                        <button onclick="event.stopPropagation(); app.deletarHistorico(${item.id})"
                            class="opacity-0 group-hover:opacity-100 p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-all mr-2"
                            title="Excluir do historico">
                            <i class="fas fa-trash-alt text-sm"></i>
                        </button>
                        <i class="fas fa-chevron-right text-gray-300 group-hover:text-primary-500 transition-colors"></i>
                    </div>
                </div>
            `
        ).join("");
      } catch (error) {
        lista.innerHTML = '<p class="text-red-500 text-sm text-center py-8">Erro ao carregar historico</p>';
      }
    }
    async deletarHistorico(geracaoId) {
      if (!confirm("Tem certeza que deseja excluir esta peca do historico?")) {
        return;
      }
      try {
        const response = await fetch(`${API_URL}/historico/${geracaoId}`, {
          method: "DELETE",
          headers: { Authorization: `Bearer ${this.getToken()}` }
        });
        if (!response.ok) throw new Error("Erro ao excluir");
        this.showToast("Peca removida do historico", "success");
        this.carregarHistoricoRecente();
        this.carregarHistorico();
      } catch (error) {
        this.showToast(`Erro: ${error.message}`, "error");
      }
    }
    async limparTodoHistorico() {
      if (!confirm(
        "Tem certeza que deseja excluir TODO o historico de pecas geradas? Esta acao nao pode ser desfeita."
      )) {
        return;
      }
      try {
        const response = await fetch(`${API_URL}/historico`, {
          headers: { Authorization: `Bearer ${this.getToken()}` }
        });
        if (!response.ok) throw new Error("Erro ao carregar");
        const historico = await response.json();
        for (const item of historico) {
          await fetch(`${API_URL}/historico/${item.id}`, {
            method: "DELETE",
            headers: { Authorization: `Bearer ${this.getToken()}` }
          });
        }
        this.showToast("Todo historico foi excluido", "success");
        this.carregarHistoricoRecente();
        this.carregarHistorico();
      } catch (error) {
        this.showToast(`Erro: ${error.message}`, "error");
      }
    }
    async abrirGeracao(geracaoId) {
      try {
        const response = await fetch(`${API_URL}/historico/${geracaoId}`, {
          headers: { Authorization: `Bearer ${this.getToken()}` }
        });
        if (!response.ok) throw new Error("Erro ao carregar geracao");
        const data = await response.json();
        this.geracaoId = data.id;
        this.tipoPeca = data.tipo_peca;
        this.numeroCNJ = data.cnj;
        this.isNovaGeracao = false;
        let markdown = data.minuta_markdown || "*Conteudo nao disponivel*";
        if (typeof markdown === "string") {
          try {
            if (markdown.startsWith('"') && markdown.endsWith('"')) {
              markdown = JSON.parse(markdown);
            }
          } catch (e) {
          }
        }
        this.minutaMarkdown = markdown;
        this.historicoChat = data.historico_chat || [];
        this.versoesLista = [];
        this.versaoSelecionada = null;
        this.painelVersoesAberto = false;
        document.getElementById("painel-versoes")?.classList.add("hidden");
        document.getElementById("versao-detalhe")?.classList.add("hidden");
        document.getElementById("versoes-count")?.classList.add("hidden");
        const editorTipoPeca = document.getElementById("editor-tipo-peca");
        if (editorTipoPeca) editorTipoPeca.textContent = this.formatarOpcao(data.tipo_peca);
        const editorCnj = document.getElementById("editor-cnj");
        if (editorCnj) editorCnj.textContent = data.cnj ? `- ${data.cnj}` : "";
        this.renderizarMinuta();
        this.renderizarChatHistorico();
        this.abrirModal("modal-editor");
        this.carregarContagemVersoes();
        const painel = document.getElementById("painel-historico");
        if (painel && !painel.classList.contains("translate-x-full")) {
          toggleHistorico();
        }
        this.showToast("Peca carregada do historico", "success");
      } catch (error) {
        this.showToast(`Erro: ${error.message}`, "error");
      }
    }
    renderizarChatHistorico() {
      const chatContainer = document.getElementById("chat-messages");
      if (!chatContainer) return;
      let html = `
            <div class="flex gap-3">
                <div class="w-8 h-8 bg-gradient-to-br from-primary-500 to-primary-600 rounded-full flex items-center justify-center flex-shrink-0">
                    <i class="fas fa-robot text-white text-xs"></i>
                </div>
                <div class="chat-bubble-ai px-4 py-3 max-w-[85%]">
                    <p class="text-sm text-gray-700">
                        Ola! Sou o assistente de edicao. Voce pode me pedir para fazer alteracoes na minuta.
                    </p>
                </div>
            </div>
        `;
      if (this.historicoChat && this.historicoChat.length > 0) {
        for (let i = 0; i < this.historicoChat.length; i++) {
          const msg = this.historicoChat[i];
          if (msg.role === "user") {
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
      const chatInput = document.getElementById("chat-input");
      if (chatInput) chatInput.value = "";
    }
    async salvarMinutaAuto() {
      if (!this.geracaoId || !this.minutaMarkdown) return;
      try {
        let descricaoAlteracao = null;
        if (this.historicoChat && this.historicoChat.length > 0) {
          for (let i = this.historicoChat.length - 1; i >= 0; i--) {
            if (this.historicoChat[i].role === "user") {
              descricaoAlteracao = this.historicoChat[i].content;
              break;
            }
          }
        }
        const response = await fetch(`${API_URL}/historico/${this.geracaoId}`, {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${this.getToken()}`
          },
          body: JSON.stringify({
            minuta_markdown: this.minutaMarkdown,
            historico_chat: this.historicoChat,
            descricao_alteracao: descricaoAlteracao
          })
        });
        if (!response.ok) throw new Error("Erro ao salvar");
        const data = await response.json();
        const minutaStatus = document.getElementById("minuta-status");
        if (minutaStatus) minutaStatus.textContent = "Salvo automaticamente";
        if (data.versao) {
          const countEl = document.getElementById("versoes-count");
          if (countEl) {
            countEl.textContent = String(data.versao.numero_versao);
            countEl.classList.remove("hidden");
          }
          if (this.painelVersoesAberto) {
            await this.carregarVersoes();
          }
        }
      } catch (error) {
        console.error("Erro ao salvar automaticamente:", error);
      }
    }
    // ==========================================
    // Feedback
    // ==========================================
    selecionarNota(nota) {
      this.notaSelecionada = nota;
      document.querySelectorAll(".estrela").forEach((btn, idx) => {
        if (idx < nota) {
          btn.classList.add("text-yellow-400");
          btn.classList.remove("text-gray-300");
        } else {
          btn.classList.remove("text-yellow-400");
          btn.classList.add("text-gray-300");
        }
      });
      const btnEnviar = document.getElementById("btn-enviar-feedback");
      if (btnEnviar) btnEnviar.disabled = false;
    }
    async enviarFeedback() {
      if (!this.geracaoId) {
        this.fecharModal("modal-feedback");
        this.resetar();
        return;
      }
      const comentarioInput = document.getElementById(
        "feedback-comentario"
      );
      const comentario = comentarioInput?.value || "";
      try {
        await fetch(`${API_URL}/feedback`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${this.getToken()}`
          },
          body: JSON.stringify({
            geracao_id: this.geracaoId,
            avaliacao: (this.notaSelecionada || 0) >= 4 ? "correto" : (this.notaSelecionada || 0) >= 2 ? "parcial" : "incorreto",
            nota: this.notaSelecionada,
            comentario: comentario || null
          })
        });
        this.showToast("Feedback enviado! Obrigado!", "success");
      } catch (error) {
        console.error("Erro ao enviar feedback:", error);
      } finally {
        this.fecharModal("modal-feedback");
        this.resetar();
      }
    }
    // ==========================================
    // Utilitarios
    // ==========================================
    mostrarLoading(mensagem, agente) {
      const progressoMensagem = document.getElementById("progresso-mensagem");
      if (progressoMensagem) progressoMensagem.textContent = mensagem;
      const modalProgresso = document.getElementById("modal-progresso");
      if (modalProgresso) modalProgresso.classList.remove("hidden");
      const btnGerar = document.getElementById("btn-gerar");
      if (btnGerar) btnGerar.disabled = true;
      let progresso = 0;
      if (agente === 1) progresso = 10;
      else if (agente === 2) progresso = 40;
      else if (agente === 3) progresso = 70;
      const progressoBarra = document.getElementById("progresso-barra");
      if (progressoBarra) progressoBarra.style.width = `${progresso}%`;
      if (agente === 1) {
        this.atualizarStatusAgente(1, "ativo");
      } else if (agente === 2) {
        this.atualizarStatusAgente(1, "concluido");
        this.atualizarStatusAgente(2, "ativo");
      } else if (agente === 3) {
        this.atualizarStatusAgente(1, "concluido");
        this.atualizarStatusAgente(2, "concluido");
        this.atualizarStatusAgente(3, "ativo");
      }
    }
    atualizarStatusAgente(agente, status) {
      const badge = document.getElementById(`agente${agente}-badge`);
      const container = document.getElementById(`agente${agente}-status`);
      const iconDiv = document.getElementById(`agente${agente}-icon`);
      if (!badge || !container || !iconDiv) return;
      if (status === "ativo") {
        badge.textContent = "Processando...";
        badge.className = "text-xs px-3 py-1 rounded-full bg-blue-100 text-blue-700 font-medium animate-pulse";
        iconDiv.className = "w-8 h-8 rounded-full bg-blue-500 flex items-center justify-center";
        iconDiv.innerHTML = '<i class="fas fa-spinner fa-spin text-white text-sm"></i>';
        container.className = "flex items-center gap-3 p-3 rounded-xl bg-blue-50 border border-blue-200";
        let progresso = agente === 1 ? 20 : agente === 2 ? 50 : 80;
        const progressoBarra = document.getElementById("progresso-barra");
        if (progressoBarra) progressoBarra.style.width = `${progresso}%`;
      } else if (status === "concluido") {
        badge.textContent = "Concluido";
        badge.className = "text-xs px-3 py-1 rounded-full bg-green-100 text-green-700 font-medium";
        iconDiv.className = "w-8 h-8 rounded-full bg-green-500 flex items-center justify-center";
        iconDiv.innerHTML = '<i class="fas fa-check text-white text-sm"></i>';
        container.className = "flex items-center gap-3 p-3 rounded-xl bg-green-50 border border-green-200";
      } else if (status === "erro") {
        badge.textContent = "Erro";
        badge.className = "text-xs px-3 py-1 rounded-full bg-red-100 text-red-700 font-medium";
        iconDiv.className = "w-8 h-8 rounded-full bg-red-500 flex items-center justify-center";
        iconDiv.innerHTML = '<i class="fas fa-times text-white text-sm"></i>';
        container.className = "flex items-center gap-3 p-3 rounded-xl bg-red-50 border border-red-200";
      }
    }
    resetarStatusAgentes() {
      [1, 2, 3].forEach((agente) => {
        const badge = document.getElementById(`agente${agente}-badge`);
        const container = document.getElementById(`agente${agente}-status`);
        const iconDiv = document.getElementById(`agente${agente}-icon`);
        if (!badge || !container || !iconDiv) return;
        badge.textContent = "Aguardando";
        badge.className = "text-xs px-3 py-1 rounded-full bg-gray-100 text-gray-500 font-medium";
        iconDiv.className = "w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center";
        container.className = "flex items-center gap-3 p-3 rounded-xl bg-gray-50 border border-gray-100";
        const icons = ["fa-download", "fa-brain", "fa-file-alt"];
        iconDiv.innerHTML = `<i class="fas ${icons[agente - 1]} text-gray-400 text-sm"></i>`;
      });
      const progressoBarra = document.getElementById("progresso-barra");
      if (progressoBarra) progressoBarra.style.width = "0%";
    }
    esconderLoading() {
      const modalProgresso = document.getElementById("modal-progresso");
      if (modalProgresso) modalProgresso.classList.add("hidden");
      const btnGerar = document.getElementById("btn-gerar");
      if (btnGerar) btnGerar.disabled = false;
      this.resetarStatusAgentes();
    }
    cancelarGeracao() {
      if (this.abortController) {
        this.abortController.abort();
        this.abortController = null;
      }
      this.esconderLoading();
      this.showToast("Geracao cancelada", "warning");
    }
    mostrarErro(mensagem) {
      const erroEl = document.getElementById("erro-mensagem");
      const toastEl = document.getElementById("toast-erro");
      if (erroEl) erroEl.textContent = mensagem;
      if (toastEl) toastEl.classList.remove("hidden");
      setTimeout(() => {
        if (toastEl) toastEl.classList.remove("animate-pulse");
      }, 2e3);
      if (this._erroTimeout) {
        clearTimeout(this._erroTimeout);
      }
      this._erroTimeout = setTimeout(() => {
        if (toastEl) {
          toastEl.classList.add("hidden");
          toastEl.classList.add("animate-pulse");
        }
      }, 15e3);
    }
    esconderErro() {
      const toastEl = document.getElementById("toast-erro");
      if (toastEl) {
        toastEl.classList.add("hidden");
        toastEl.classList.add("animate-pulse");
      }
      if (this._erroTimeout) {
        clearTimeout(this._erroTimeout);
        this._erroTimeout = null;
      }
    }
    abrirModal(id) {
      const modal = document.getElementById(id);
      if (modal) modal.classList.remove("hidden");
    }
    fecharModal(id) {
      const modal = document.getElementById(id);
      if (modal) modal.classList.add("hidden");
    }
    formatarOpcao(opcao) {
      const labels = {
        contestacao: "Contestacao",
        recurso_apelacao: "Recurso de Apelacao",
        contrarrazoes: "Contrarrazoes de Recurso",
        parecer: "Parecer Juridico"
      };
      return labels[opcao || ""] || opcao || "Nao definido";
    }
    getToken() {
      return localStorage.getItem("access_token") || "";
    }
    showToast(message, type = "success") {
      const toast = document.getElementById("toast");
      const icon = document.getElementById("toast-icon");
      const msg = document.getElementById("toast-message");
      if (msg) msg.textContent = message;
      if (icon) {
        if (type === "success") {
          icon.className = "fas fa-check-circle text-green-400";
        } else if (type === "error") {
          icon.className = "fas fa-exclamation-circle text-red-400";
        } else if (type === "warning") {
          icon.className = "fas fa-exclamation-triangle text-yellow-400";
        }
      }
      if (toast) {
        toast.classList.remove("hidden");
        setTimeout(() => toast.classList.add("hidden"), 3e3);
      }
    }
    resetar() {
      const form = document.getElementById("form-processo");
      if (form) form.reset();
      const respostaUsuario = document.getElementById(
        "resposta-usuario"
      );
      if (respostaUsuario) respostaUsuario.value = "";
      const feedbackComentario = document.getElementById(
        "feedback-comentario"
      );
      if (feedbackComentario) feedbackComentario.value = "";
      const observacaoUsuario = document.getElementById(
        "observacao-usuario"
      );
      if (observacaoUsuario) observacaoUsuario.value = "";
      this.numeroCNJ = null;
      this.tipoPeca = null;
      this.geracaoId = null;
      this.notaSelecionada = null;
      this.isNovaGeracao = false;
      this.minutaMarkdown = null;
      this.historicoChat = [];
      this.observacaoUsuario = null;
      const grupoSelect = document.getElementById("grupo-principal");
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
      this.arquivosPdf = [];
      this.atualizarListaArquivos();
      this.versoesLista = [];
      this.versaoSelecionada = null;
      this.painelVersoesAberto = false;
      document.querySelectorAll(".estrela").forEach((btn) => {
        btn.classList.remove("text-yellow-400");
        btn.classList.add("text-gray-300");
      });
      const btnEnviarFeedback = document.getElementById(
        "btn-enviar-feedback"
      );
      if (btnEnviarFeedback) btnEnviarFeedback.disabled = true;
    }
    // ==========================================
    // Historico de Versoes
    // ==========================================
    toggleHistoricoVersoes() {
      const painel = document.getElementById("painel-versoes");
      if (!painel) return;
      if (this.painelVersoesAberto) {
        painel.classList.add("hidden");
        this.painelVersoesAberto = false;
      } else {
        painel.classList.remove("hidden");
        this.painelVersoesAberto = true;
        this.carregarVersoes();
      }
    }
    async carregarVersoes() {
      if (!this.geracaoId) return;
      const lista = document.getElementById("versoes-lista");
      if (!lista) return;
      lista.innerHTML = `
            <div class="text-center py-8 text-gray-400">
                <i class="fas fa-spinner fa-spin text-2xl mb-2"></i>
                <p class="text-sm">Carregando versoes...</p>
            </div>
        `;
      try {
        const response = await fetch(`${API_URL}/historico/${this.geracaoId}/versoes`, {
          headers: { Authorization: `Bearer ${this.getToken()}` }
        });
        if (!response.ok) throw new Error("Erro ao carregar versoes");
        const data = await response.json();
        this.versoesLista = data.versoes;
        const countEl = document.getElementById("versoes-count");
        if (countEl) {
          if (data.total_versoes > 0) {
            countEl.textContent = String(data.total_versoes);
            countEl.classList.remove("hidden");
          } else {
            countEl.classList.add("hidden");
          }
        }
        this.renderizarVersoes();
      } catch (error) {
        console.error("Erro ao carregar versoes:", error);
        lista.innerHTML = `
                <div class="text-center py-8 text-gray-400">
                    <i class="fas fa-exclamation-circle text-2xl mb-2 text-red-400"></i>
                    <p class="text-sm">Erro ao carregar versoes</p>
                </div>
            `;
      }
    }
    renderizarVersoes() {
      const lista = document.getElementById("versoes-lista");
      if (!lista) return;
      if (this.versoesLista.length === 0) {
        lista.innerHTML = `
                <div class="text-center py-8 text-gray-400">
                    <i class="fas fa-code-branch text-3xl mb-3 opacity-50"></i>
                    <p class="text-sm font-medium">Nenhuma versao registrada</p>
                    <p class="text-xs mt-1">As versoes aparecerao aqui apos edicoes</p>
                </div>
            `;
        return;
      }
      lista.innerHTML = this.versoesLista.map((versao, index) => {
        const isAtual = index === 0;
        const badgeClass = this.getBadgeClass(versao.origem);
        const badgeText = this.getBadgeText(versao.origem);
        const dataFormatada = versao.criado_em ? new Date(versao.criado_em).toLocaleString("pt-BR", {
          day: "2-digit",
          month: "2-digit",
          year: "2-digit",
          hour: "2-digit",
          minute: "2-digit"
        }) : "Data desconhecida";
        return `
                <div class="versao-item p-3 bg-white border ${isAtual ? "border-indigo-300 bg-indigo-50" : "border-gray-100"} rounded-xl cursor-pointer hover:border-indigo-300 hover:bg-indigo-50/50"
                     onclick="app.selecionarVersao(${versao.id})" data-versao-id="${versao.id}">
                    <div class="flex items-center justify-between mb-2">
                        <div class="flex items-center gap-2">
                            <span class="text-sm font-semibold text-gray-800">v${versao.numero_versao}</span>
                            ${isAtual ? '<span class="text-xs text-indigo-600 font-medium">(atual)</span>' : ""}
                        </div>
                        <span class="versao-badge ${badgeClass}">${badgeText}</span>
                    </div>
                    <p class="text-xs text-gray-500 mb-1">
                        <i class="fas fa-clock mr-1"></i>${dataFormatada}
                    </p>
                    ${versao.descricao_alteracao ? `
                        <p class="text-xs text-gray-600 truncate mt-1" title="${this.escapeHtml(versao.descricao_alteracao)}">
                            <i class="fas fa-comment mr-1 text-gray-400"></i>${this.escapeHtml(versao.descricao_alteracao.substring(0, 50))}${versao.descricao_alteracao.length > 50 ? "..." : ""}
                        </p>
                    ` : ""}
                    <p class="text-xs mt-1 ${versao.resumo_diff.includes("+") ? "text-green-600" : "text-gray-400"}">
                        ${versao.resumo_diff}
                    </p>
                </div>
            `;
      }).join("");
    }
    getBadgeClass(origem) {
      switch (origem) {
        case "geracao_inicial":
          return "versao-badge-inicial";
        case "edicao_chat":
          return "versao-badge-edicao";
        case "edicao_manual":
          return "versao-badge-restauracao";
        default:
          return "versao-badge-inicial";
      }
    }
    getBadgeText(origem) {
      switch (origem) {
        case "geracao_inicial":
          return "Inicial";
        case "edicao_chat":
          return "Edicao";
        case "edicao_manual":
          return "Restaurado";
        default:
          return origem;
      }
    }
    async selecionarVersao(versaoId) {
      this.versaoSelecionada = versaoId;
      document.querySelectorAll(".versao-item").forEach((el) => {
        el.classList.remove("active");
      });
      const itemSelecionado = document.querySelector(`[data-versao-id="${versaoId}"]`);
      if (itemSelecionado) {
        itemSelecionado.classList.add("active");
      }
      try {
        const response = await fetch(
          `${API_URL}/historico/${this.geracaoId}/versoes/${versaoId}`,
          {
            headers: { Authorization: `Bearer ${this.getToken()}` }
          }
        );
        if (!response.ok) throw new Error("Erro ao carregar versao");
        const versao = await response.json();
        this.mostrarDetalheVersao(versao);
      } catch (error) {
        console.error("Erro ao carregar detalhes da versao:", error);
        this.showToast("Erro ao carregar versao", "error");
      }
    }
    mostrarDetalheVersao(versao) {
      const detalhePanel = document.getElementById("versao-detalhe");
      const diffContainer = document.getElementById("versao-diff");
      if (!detalhePanel || !diffContainer) return;
      detalhePanel.classList.remove("hidden");
      if (versao.diff_anterior) {
        const diff = versao.diff_anterior;
        let diffHtml = "";
        if (diff.linhas_adicionadas && diff.linhas_adicionadas.length > 0) {
          diffHtml += `<div class="mb-2"><span class="text-xs text-green-600 font-medium">+ Adicionadas (${diff.total_adicionadas}):</span></div>`;
          diff.linhas_adicionadas.slice(0, 10).forEach((linha) => {
            diffHtml += `<div class="diff-line diff-added">+ ${this.escapeHtml(linha.substring(0, 100))}</div>`;
          });
          if (diff.linhas_adicionadas.length > 10) {
            diffHtml += `<div class="text-xs text-gray-400 mt-1">... e mais ${diff.linhas_adicionadas.length - 10} linha(s)</div>`;
          }
        }
        if (diff.linhas_removidas && diff.linhas_removidas.length > 0) {
          diffHtml += `<div class="mt-3 mb-2"><span class="text-xs text-red-600 font-medium">- Removidas (${diff.total_removidas}):</span></div>`;
          diff.linhas_removidas.slice(0, 10).forEach((linha) => {
            diffHtml += `<div class="diff-line diff-removed">- ${this.escapeHtml(linha.substring(0, 100))}</div>`;
          });
          if (diff.linhas_removidas.length > 10) {
            diffHtml += `<div class="text-xs text-gray-400 mt-1">... e mais ${diff.linhas_removidas.length - 10} linha(s)</div>`;
          }
        }
        if (!diffHtml) {
          diffHtml = '<p class="text-gray-400 text-center py-4">Versao inicial - sem alteracoes anteriores</p>';
        }
        diffContainer.innerHTML = diffHtml;
      } else {
        diffContainer.innerHTML = '<p class="text-gray-400 text-center py-4">Versao inicial - sem alteracoes anteriores</p>';
      }
    }
    fecharDetalheVersao() {
      const detalhe = document.getElementById("versao-detalhe");
      if (detalhe) detalhe.classList.add("hidden");
      this.versaoSelecionada = null;
      document.querySelectorAll(".versao-item").forEach((el) => {
        el.classList.remove("active");
      });
    }
    async verConteudoVersao() {
      if (!this.versaoSelecionada) return;
      try {
        const response = await fetch(
          `${API_URL}/historico/${this.geracaoId}/versoes/${this.versaoSelecionada}`,
          {
            headers: { Authorization: `Bearer ${this.getToken()}` }
          }
        );
        if (!response.ok) throw new Error("Erro ao carregar versao");
        const versao = await response.json();
        const tituloEl = document.getElementById("modal-versao-titulo");
        if (tituloEl) tituloEl.textContent = `Versao ${versao.numero_versao}`;
        const dataEl = document.getElementById("modal-versao-data");
        if (dataEl)
          dataEl.textContent = versao.criado_em ? new Date(versao.criado_em).toLocaleString("pt-BR") : "Data desconhecida";
        const conteudoEl = document.getElementById("modal-versao-conteudo");
        if (conteudoEl) {
          const marked = window.marked;
          if (marked) {
            conteudoEl.innerHTML = marked.parse(versao.conteudo || "");
          } else {
            conteudoEl.innerHTML = versao.conteudo || "";
          }
        }
        const modal = document.getElementById("modal-versao-completa");
        if (modal) modal.classList.remove("hidden");
      } catch (error) {
        console.error("Erro ao carregar conteudo:", error);
        this.showToast("Erro ao carregar conteudo da versao", "error");
      }
    }
    fecharModalVersao() {
      const modal = document.getElementById("modal-versao-completa");
      if (modal) modal.classList.add("hidden");
    }
    async restaurarVersaoSelecionada() {
      if (!this.versaoSelecionada) {
        this.showToast("Selecione uma versao primeiro", "warning");
        return;
      }
      if (!confirm(
        "Tem certeza que deseja restaurar esta versao? O texto atual sera salvo como uma nova versao antes da restauracao."
      )) {
        return;
      }
      await this.restaurarVersao(this.versaoSelecionada);
    }
    async restaurarVersaoDoModal() {
      if (!this.versaoSelecionada) return;
      if (!confirm(
        "Tem certeza que deseja restaurar esta versao? O texto atual sera salvo como uma nova versao antes da restauracao."
      )) {
        return;
      }
      this.fecharModalVersao();
      await this.restaurarVersao(this.versaoSelecionada);
    }
    async restaurarVersao(versaoId) {
      try {
        const response = await fetch(
          `${API_URL}/historico/${this.geracaoId}/versoes/${versaoId}/restaurar`,
          {
            method: "POST",
            headers: { Authorization: `Bearer ${this.getToken()}` }
          }
        );
        if (!response.ok) throw new Error("Erro ao restaurar versao");
        const data = await response.json();
        this.minutaMarkdown = data.conteudo;
        this.renderizarMinuta();
        await this.carregarVersoes();
        this.fecharDetalheVersao();
        this.showToast(`Versao restaurada! Nova versao: v${data.nova_versao.numero_versao}`, "success");
        this.destacarMinuta();
      } catch (error) {
        console.error("Erro ao restaurar versao:", error);
        this.showToast("Erro ao restaurar versao", "error");
      }
    }
    // ==========================================
    // Streaming de Geracao em Tempo Real (no Editor)
    // ==========================================
    abrirEditorStreaming() {
      console.log("abrirEditorStreaming() chamado");
      try {
        this.esconderLoading();
        this.minutaMarkdown = "";
        this.historicoChat = [];
        this.geracaoId = null;
        this.isNovaGeracao = true;
        this.versoesLista = [];
        this.versaoSelecionada = null;
        this.painelVersoesAberto = false;
        document.getElementById("painel-versoes")?.classList.add("hidden");
        document.getElementById("versao-detalhe")?.classList.add("hidden");
        document.getElementById("versoes-count")?.classList.add("hidden");
        const editorTipoPeca = document.getElementById("editor-tipo-peca");
        if (editorTipoPeca) editorTipoPeca.textContent = "Gerando...";
        const editorCnj = document.getElementById("editor-cnj");
        if (editorCnj) editorCnj.textContent = this.numeroCNJ ? `- ${this.numeroCNJ}` : "";
        const container = document.getElementById("minuta-content");
        if (container) {
          container.innerHTML = `
                    <div class="flex items-center gap-2 text-primary-600 mb-4">
                        <div class="animate-spin h-4 w-4 border-2 border-primary-500 border-t-transparent rounded-full"></div>
                        <span class="text-sm font-medium">Gerando peca em tempo real...</span>
                    </div>
                    <div id="streaming-content" class="prose prose-sm max-w-none"></div>
                `;
        }
        const minutaStatus = document.getElementById("minuta-status");
        if (minutaStatus) {
          minutaStatus.innerHTML = `
                    <span class="text-primary-600 animate-pulse">
                        <i class="fas fa-pen-fancy mr-1"></i> Escrevendo...
                    </span>
                `;
        }
        const chatInput = document.getElementById("chat-input");
        if (chatInput) {
          chatInput.disabled = true;
          chatInput.placeholder = "Aguarde a geracao finalizar...";
        }
        if (typeof this.resetarChat === "function") {
          this.resetarChat();
        }
        console.log("Abrindo modal-editor...");
        this.abrirModal("modal-editor");
        console.log("Modal aberto com sucesso");
      } catch (err) {
        console.error("Erro em abrirEditorStreaming:", err);
      }
    }
    atualizarEditorStreaming() {
      const contentEl = document.getElementById("streaming-content");
      if (contentEl && this.streamingContent) {
        const marked = window.marked;
        if (marked) {
          marked.setOptions({ breaks: true, gfm: true });
          contentEl.innerHTML = marked.parse(this.streamingContent);
        } else {
          contentEl.innerHTML = this.streamingContent.replace(/## (.*)/g, '<h2 class="text-lg font-semibold mt-4 mb-2">$1</h2>').replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>").replace(/\*(.*?)\*/g, "<em>$1</em>").replace(/\n/g, "<br>");
        }
        const container = document.getElementById("minuta-content");
        if (container) {
          container.scrollTop = container.scrollHeight;
        }
      }
      const statusEl = document.getElementById("minuta-status");
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
      this.geracaoId = geracaoId;
      this.tipoPeca = tipoPeca;
      this.minutaMarkdown = conteudoFinal;
      const editorTipoPeca = document.getElementById("editor-tipo-peca");
      if (editorTipoPeca) editorTipoPeca.textContent = this.formatarOpcao(tipoPeca);
      this.renderizarMinuta();
      const minutaStatus = document.getElementById("minuta-status");
      if (minutaStatus) minutaStatus.textContent = "Geracao concluida";
      const chatInput = document.getElementById("chat-input");
      if (chatInput) {
        chatInput.disabled = false;
        chatInput.placeholder = "Digite uma solicitacao de alteracao...";
      }
      this.isStreaming = false;
      this.streamingContent = "";
      this.carregarHistoricoRecente();
      this.carregarContagemVersoes();
      this.destacarMinuta();
    }
    finalizarStreaming() {
      this.isStreaming = false;
      this.streamingContent = "";
    }
  };
  function toggleHistorico() {
    const painel = document.getElementById("painel-historico");
    if (!painel) return;
    if (painel.classList.contains("translate-x-full")) {
      painel.classList.remove("translate-x-full", "hidden");
      painel.classList.add("translate-x-0");
      app.carregarHistorico();
    } else {
      painel.classList.add("translate-x-full");
      painel.classList.remove("translate-x-0");
    }
  }
  function fecharModalEditor() {
    const modalEditor = document.getElementById("modal-editor");
    if (modalEditor) modalEditor.classList.add("hidden");
    if (app && app.painelVersoesAberto) {
      const painelVersoes = document.getElementById("painel-versoes");
      if (painelVersoes) painelVersoes.classList.add("hidden");
      app.painelVersoesAberto = false;
    }
    const versaoDetalhe = document.getElementById("versao-detalhe");
    if (versaoDetalhe) versaoDetalhe.classList.add("hidden");
    if (app && app.isNovaGeracao) {
      const modalFeedback = document.getElementById("modal-feedback");
      if (modalFeedback) modalFeedback.classList.remove("hidden");
    }
  }
  var app;
  document.addEventListener("DOMContentLoaded", () => {
    app = new GeradorPecasApp();
    window.app = app;  // Expor globalmente para handlers onclick
  });
  window.toggleHistorico = toggleHistorico;
  window.fecharModalEditor = fecharModalEditor;
})();
//# sourceMappingURL=app.js.map
