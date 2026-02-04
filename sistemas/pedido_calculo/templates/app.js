// Generated from TypeScript - DO NOT EDIT DIRECTLY
// Source: src\sistemas\pedido_calculo\app.ts
// Built at: 2026-01-30T21:41:45.507Z

"use strict";
(() => {
  // src/sistemas/pedido_calculo/app.ts
  var API_URL = "/pedido-calculo/api";
  var PedidoCalculoApp = class {
    constructor() {
      this.numeroCNJ = null;
      this.geracaoId = null;
      this.notaSelecionada = null;
      this.isNovaGeracao = false;
      // Dados para o editor interativo
      this.pedidoMarkdown = null;
      this.dadosBasicos = null;
      this.dadosExtracao = null;
      this.documentosBaixados = [];
      this.historicoChat = [];
      this.isProcessingEdit = false;
      // Streaming de geracao em tempo real
      this.streamingContent = "";
      this.isStreaming = false;
      this.initEventListeners();
      this.checkAuth();
    }
    async checkAuth() {
      const token = localStorage.getItem("access_token");
      if (!token) {
        window.location.href = "/login?next=/pedido-calculo";
        return;
      }
      try {
        const response = await fetch("/auth/me", {
          headers: { "Authorization": `Bearer ${token}` }
        });
        if (!response.ok) {
          throw new Error("Token invalido");
        }
        this.carregarHistoricoRecente();
      } catch {
        localStorage.removeItem("access_token");
        window.location.href = "/login?next=/pedido-calculo";
      }
    }
    initEventListeners() {
      document.getElementById("form-processo")?.addEventListener("submit", (e) => {
        e.preventDefault();
        this.iniciarProcessamento();
      });
      document.getElementById("btn-enviar-chat")?.addEventListener("click", () => {
        this.enviarMensagemChat();
      });
      document.getElementById("chat-input")?.addEventListener("keypress", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          this.enviarMensagemChat();
        }
      });
      document.getElementById("btn-copiar-minuta")?.addEventListener("click", () => {
        this.copiarMinuta();
      });
      document.querySelectorAll(".estrela").forEach((btn) => {
        btn.addEventListener("click", (e) => {
          const target = e.target;
          const nota = target.dataset.nota;
          if (nota) {
            this.selecionarNota(parseInt(nota, 10));
          }
        });
      });
      document.getElementById("btn-pular-feedback")?.addEventListener("click", () => {
        this.fecharModal("modal-feedback");
        this.resetar();
      });
      document.getElementById("btn-enviar-feedback")?.addEventListener("click", () => {
        this.enviarFeedback();
      });
    }
    async iniciarProcessamento(sobrescreverExistente = false) {
      const inputElement = document.getElementById("numero-cnj");
      this.numeroCNJ = inputElement?.value || null;
      if (!this.numeroCNJ) {
        this.showToast("Informe o numero do processo", "error");
        return;
      }
      if (!sobrescreverExistente) {
        try {
          const verificacao = await fetch(`${API_URL}/verificar-existente?numero_cnj=${encodeURIComponent(this.numeroCNJ)}`, {
            headers: {
              "Authorization": `Bearer ${this.getToken()}`
            }
          });
          if (verificacao.ok) {
            const dados = await verificacao.json();
            if (dados.existe) {
              const confirmar = await this.mostrarConfirmacaoSobrescrita(dados);
              if (confirmar === "cancelar") {
                return;
              } else if (confirmar === "ver" && dados.geracao_id) {
                this.carregarDoHistorico(dados.geracao_id);
                return;
              }
              sobrescreverExistente = true;
            }
          }
        } catch (error) {
          console.warn("Erro ao verificar existente:", error);
        }
      }
      this.esconderErro();
      this.resetarStatusAgentes();
      this.mostrarLoading("Conectando ao TJ-MS...", null);
      let streamFinalizadoCorretamente = false;
      try {
        const response = await fetch(`${API_URL}/processar-stream`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${this.getToken()}`
          },
          body: JSON.stringify({
            numero_cnj: this.numeroCNJ,
            sobrescrever_existente: sobrescreverExistente
          })
        });
        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.detail || "Erro ao processar");
        }
        const reader = response.body?.getReader();
        if (!reader) {
          throw new Error("Erro ao iniciar streaming");
        }
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
                if (data.tipo === "sucesso" || data.tipo === "erro") {
                  streamFinalizadoCorretamente = true;
                }
                this.processarEventoStream(data);
              } catch (e) {
                console.warn("Erro ao parsear evento SSE:", e);
              }
            }
          }
        }
        if (!streamFinalizadoCorretamente) {
          this.mostrarErro("Conexao interrompida com o servidor. Verifique a conexao e tente novamente.");
          this.esconderLoading();
        }
      } catch (error) {
        const err = error;
        let mensagemErro = err.message;
        if (err.message.includes("502") || err.message.includes("Proxy")) {
          mensagemErro = "Erro de conexao com o TJ-MS (502). O servidor pode estar temporariamente indisponivel. Tente novamente em alguns minutos.";
        } else if (err.message.includes("Failed to fetch") || err.message.includes("NetworkError")) {
          mensagemErro = "Erro de conexao com o servidor. Verifique sua internet e tente novamente.";
        }
        this.mostrarErro(mensagemErro);
        this.esconderLoading();
      }
    }
    processarEventoStream(data) {
      console.log("Evento SSE:", data);
      switch (data.tipo) {
        case "inicio":
          this.setProgressoMensagem(data.mensagem);
          break;
        case "agente":
          this.atualizarStatusAgente(data.agente, data.status);
          this.setProgressoMensagem(data.mensagem);
          if (data.status === "erro") {
            this.mostrarErro(data.mensagem);
            this.esconderLoading();
          }
          break;
        case "sucesso":
          this.setProgressoBarra("100%");
          this.atualizarStatusAgente(4, "concluido");
          const conteudoFinal = this.isStreaming ? this.streamingContent : data.pedido_markdown;
          if (this.isStreaming) {
            this.finalizarEditorStreaming(
              data.geracao_id,
              data.dados_basicos || null,
              data.dados_extracao || null,
              data.documentos_baixados || [],
              conteudoFinal || ""
            );
            this.esconderLoading();
            this.showToast("Pedido de calculo gerado com sucesso!", "success");
          } else {
            setTimeout(() => {
              this.esconderLoading();
              this.showToast("Pedido de calculo gerado com sucesso!", "success");
              this.exibirEditor({
                geracao_id: data.geracao_id,
                dados_basicos: data.dados_basicos,
                dados_extracao: data.dados_extracao,
                pedido_markdown: data.pedido_markdown,
                documentos_baixados: data.documentos_baixados
              });
            }, 500);
          }
          this.carregarHistoricoRecente();
          break;
        case "erro":
          this.finalizarStreaming();
          this.esconderLoading();
          this.mostrarErro(data.mensagem);
          break;
        case "info":
          this.setProgressoMensagem(data.mensagem);
          break;
        case "geracao_chunk":
          try {
            if (!this.isStreaming) {
              this.isStreaming = true;
              this.streamingContent = "";
              this.abrirEditorStreaming();
            }
            this.streamingContent += data.content;
            this.atualizarEditorStreaming();
          } catch (err) {
            console.error("Erro no streaming:", err);
          }
          break;
      }
    }
    setProgressoMensagem(mensagem) {
      const el = document.getElementById("progresso-mensagem");
      if (el) el.textContent = mensagem;
    }
    setProgressoBarra(width) {
      const el = document.getElementById("progresso-barra");
      if (el) el.style.width = width;
    }
    exibirEditor(data, isNova = true) {
      this.dadosBasicos = data.dados_basicos || {};
      this.dadosExtracao = data.dados_extracao || {};
      this.pedidoMarkdown = data.pedido_markdown || null;
      this.documentosBaixados = data.documentos_baixados || [];
      this.geracaoId = data.geracao_id;
      this.isNovaGeracao = isNova;
      const editorTipoPeca = document.getElementById("editor-tipo-peca");
      if (editorTipoPeca) editorTipoPeca.textContent = "Pedido de Calculo";
      const editorCnj = document.getElementById("editor-cnj");
      if (editorCnj) editorCnj.textContent = this.dadosBasicos?.numero_processo || this.numeroCNJ || "";
      this.renderizarMinuta();
      this.historicoChat = [];
      this.resetarChat();
      this.abrirModal("modal-editor");
    }
    renderizarMinuta() {
      const container = document.getElementById("minuta-content");
      if (container && this.pedidoMarkdown && typeof marked !== "undefined") {
        container.innerHTML = marked.parse(this.pedidoMarkdown);
      }
    }
    renderizarPedido() {
      const container = document.getElementById("pedido-content");
      if (container && this.pedidoMarkdown && typeof marked !== "undefined") {
        container.innerHTML = marked.parse(this.pedidoMarkdown);
      }
    }
    resetarChat() {
      const chatContainer = document.getElementById("chat-messages");
      if (!chatContainer) return;
      chatContainer.innerHTML = `
      <div class="flex gap-3">
        <div class="w-8 h-8 bg-gradient-to-br from-primary-500 to-primary-600 rounded-full flex items-center justify-center flex-shrink-0">
          <i class="fas fa-robot text-white text-xs"></i>
        </div>
        <div class="chat-bubble-ai px-4 py-3 max-w-[85%]">
          <p class="text-sm text-gray-700">
            Ola! Sou o assistente de edicao. Voce pode me pedir para fazer alteracoes no pedido de calculo, como:
          </p>
          <ul class="text-xs text-gray-500 mt-2 space-y-1">
            <li>- "Corrija o periodo da condenacao para 01/2022 a 12/2024"</li>
            <li>- "Adicione observacao sobre a EC 113/2021"</li>
            <li>- "Altere o indice de correcao para IPCA-E"</li>
          </ul>
        </div>
      </div>
    `;
    }
    async enviarMensagemChat() {
      if (this.isProcessingEdit) return;
      const input = document.getElementById("chat-input");
      if (!input) return;
      const mensagem = input.value.trim();
      if (!mensagem) return;
      input.value = "";
      this.isProcessingEdit = true;
      this.adicionarMensagemChat("user", mensagem);
      this.mostrarTypingIndicator();
      try {
        const response = await fetch(`${API_URL}/editar-pedido`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${this.getToken()}`
          },
          body: JSON.stringify({
            pedido_markdown: this.pedidoMarkdown,
            mensagem_usuario: mensagem,
            historico_chat: this.historicoChat,
            dados_basicos: this.dadosBasicos,
            dados_extracao: this.dadosExtracao
          })
        });
        this.esconderTypingIndicator();
        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.detail || "Erro ao processar");
        }
        const data = await response.json();
        if (data.status === "sucesso" && data.pedido_markdown) {
          this.pedidoMarkdown = data.pedido_markdown;
          this.renderizarMinuta();
          this.historicoChat.push({ role: "user", content: mensagem });
          this.historicoChat.push({ role: "assistant", content: "Pedido atualizado com sucesso." });
          this.adicionarMensagemChat("ai", "Pronto! Atualizei o pedido conforme solicitado. Veja as alteracoes na visualizacao ao lado.", true);
          this.destacarMinuta();
        } else {
          this.adicionarMensagemChat("ai", `Desculpe, encontrei um problema: ${data.mensagem || "Erro desconhecido"}`, false);
        }
      } catch (error) {
        const err = error;
        this.esconderTypingIndicator();
        this.adicionarMensagemChat("ai", `Erro ao processar: ${err.message}`, false);
      } finally {
        this.isProcessingEdit = false;
      }
    }
    adicionarMensagemChat(tipo, conteudo, sucesso = true) {
      const chatContainer = document.getElementById("chat-messages");
      if (!chatContainer) return;
      const msgDiv = document.createElement("div");
      msgDiv.className = tipo === "user" ? "flex gap-3 justify-end" : "flex gap-3";
      if (tipo === "user") {
        msgDiv.innerHTML = `
        <div class="chat-bubble-user px-4 py-3 max-w-[85%]">
          <p class="text-sm text-white">${escapeHtml(conteudo)}</p>
        </div>
        <div class="w-8 h-8 bg-gray-200 rounded-full flex items-center justify-center flex-shrink-0">
          <i class="fas fa-user text-gray-500 text-xs"></i>
        </div>
      `;
      } else {
        const iconClass = sucesso ? "fa-check-circle text-green-500" : "fa-exclamation-circle text-red-500";
        msgDiv.innerHTML = `
        <div class="w-8 h-8 bg-gradient-to-br from-primary-500 to-primary-600 rounded-full flex items-center justify-center flex-shrink-0">
          <i class="fas fa-robot text-white text-xs"></i>
        </div>
        <div class="chat-bubble-ai px-4 py-3 max-w-[85%]">
          <p class="text-sm text-gray-700">
            <i class="fas ${iconClass} mr-1"></i>
            ${escapeHtml(conteudo)}
          </p>
        </div>
      `;
      }
      chatContainer.appendChild(msgDiv);
      chatContainer.scrollTop = chatContainer.scrollHeight;
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
        await navigator.clipboard.writeText(this.pedidoMarkdown || "");
        this.showToast("Pedido copiado para a area de transferencia!", "success");
        const btn = document.getElementById("btn-copiar-minuta");
        if (btn) {
          const originalHTML = btn.innerHTML;
          btn.innerHTML = '<i class="fas fa-check"></i> Copiado!';
          setTimeout(() => btn.innerHTML = originalHTML, 2e3);
        }
      } catch {
        this.showToast("Erro ao copiar", "error");
      }
    }
    async downloadDocx() {
      if (!this.pedidoMarkdown) {
        this.showToast("Nenhum pedido para exportar", "error");
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
            "Authorization": `Bearer ${this.getToken()}`
          },
          body: JSON.stringify({
            markdown: this.pedidoMarkdown,
            numero_processo: this.numeroCNJ
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
          link.download = data.filename || "pedido_calculo.docx";
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
        const err = error;
        console.error("Erro ao baixar DOCX:", err);
        this.showToast(`Erro: ${err.message}`, "error");
        btn.innerHTML = originalHTML;
        btn.disabled = false;
      }
    }
    abrirAutos() {
      if (!this.numeroCNJ) {
        this.showToast("Numero do processo nao disponivel", "warning");
        return;
      }
      if (!this.documentosBaixados || this.documentosBaixados.length === 0) {
        this.showToast("Nenhum documento foi baixado para este processo", "warning");
        return;
      }
      this.abrirModalDocumentos();
    }
    abrirModalDocumentos() {
      let modal = document.getElementById("modal-documentos");
      if (!modal) {
        modal = document.createElement("div");
        modal.id = "modal-documentos";
        modal.className = "fixed inset-0 z-50 hidden";
        modal.innerHTML = `
        <div class="absolute inset-0 bg-black/50" onclick="app.fecharModalDocumentos()"></div>
        <div class="absolute inset-4 md:inset-10 lg:inset-20 bg-white rounded-2xl shadow-2xl flex flex-col">
          <div class="flex items-center justify-between px-6 py-4 border-b border-gray-100 bg-gradient-to-r from-primary-50 to-blue-50 rounded-t-2xl">
            <div>
              <h2 class="text-lg font-semibold text-gray-800">Documentos Analisados</h2>
              <p class="text-sm text-gray-500" id="modal-docs-info"></p>
            </div>
            <button onclick="app.fecharModalDocumentos()" class="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors">
              <i class="fas fa-times"></i>
            </button>
          </div>
          <div class="flex-1 flex overflow-hidden">
            <div class="w-64 border-r border-gray-200 overflow-y-auto bg-gray-50" id="lista-documentos"></div>
            <div class="flex-1 overflow-hidden" id="visualizador-documento">
              <div class="h-full flex items-center justify-center text-gray-400">
                <div class="text-center">
                  <i class="fas fa-file-pdf text-4xl mb-3 opacity-50"></i>
                  <p>Selecione um documento para visualizar</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      `;
        document.body.appendChild(modal);
      }
      const modalDocsInfo = document.getElementById("modal-docs-info");
      if (modalDocsInfo) {
        modalDocsInfo.textContent = `${this.documentosBaixados.length} documento(s) analisado(s) - Processo ${this.numeroCNJ}`;
      }
      const lista = document.getElementById("lista-documentos");
      if (!lista) return;
      const documentosVisiveis = this.documentosBaixados.filter((doc) => doc && doc.id);
      if (documentosVisiveis.length === 0) {
        lista.innerHTML = '<p class="text-xs text-gray-400 px-4 py-3">Nenhum documento valido para exibir.</p>';
      } else {
        lista.innerHTML = documentosVisiveis.map((doc, index) => {
          const isOrigem = doc.processo === "origem";
          const badge = isOrigem ? '<span class="ml-auto text-xs bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded">Origem</span>' : "";
          const numeroProcesso = doc.numero_processo || this.dadosBasicos?.numero_processo || this.numeroCNJ || "";
          return `
        <button
          onclick="app.visualizarDocumento('${escapeHtml(doc.id)}', ${index}, '${escapeHtml(numeroProcesso)}')"
          class="w-full text-left px-4 py-3 hover:bg-white border-b border-gray-200 transition-colors doc-item"
          data-index="${index}"
        >
          <div class="flex items-center gap-2">
            <i class="fas fa-file-pdf text-red-500"></i>
            <div class="min-w-0 flex-1">
              <p class="text-sm font-medium text-gray-800 truncate">${escapeHtml(doc.tipo || "Documento")}</p>
              <p class="text-xs text-gray-500 truncate">${escapeHtml(doc.id)}</p>
            </div>
            ${badge}
          </div>
        </button>
      `;
        }).join("");
      }
      modal.classList.remove("hidden");
    }
    fecharModalDocumentos() {
      const modal = document.getElementById("modal-documentos");
      if (modal) {
        modal.classList.add("hidden");
      }
    }
    async visualizarDocumento(idDocumento, index, numeroProcessoDoc) {
      document.querySelectorAll(".doc-item").forEach((el) => el.classList.remove("bg-white", "border-l-4", "border-primary-500"));
      document.querySelector(`.doc-item[data-index="${index}"]`)?.classList.add("bg-white", "border-l-4", "border-primary-500");
      const visualizador = document.getElementById("visualizador-documento");
      if (!visualizador) return;
      visualizador.innerHTML = `
      <div class="h-full flex items-center justify-center text-gray-400">
        <div class="text-center">
          <i class="fas fa-spinner fa-spin text-2xl mb-3"></i>
          <p>Carregando documento...</p>
        </div>
      </div>
    `;
      try {
        const token = this.getToken();
        const numeroProcesso = numeroProcessoDoc || this.dadosBasicos?.numero_processo || this.numeroCNJ;
        if (!numeroProcesso) {
          throw new Error("Numero do processo nao disponivel");
        }
        const response = await fetch(
          `${API_URL}/documento/${encodeURIComponent(numeroProcesso)}/${encodeURIComponent(idDocumento)}?token=${encodeURIComponent(token)}`
        );
        if (!response.ok) {
          let mensagem = "Documento nao encontrado";
          try {
            const erro = await response.json();
            if (erro && erro.detail) {
              mensagem = erro.detail;
            }
          } catch {
          }
          throw new Error(mensagem);
        }
        const data = await response.json();
        visualizador.innerHTML = `
        <iframe
          src="data:application/pdf;base64,${data.conteudo_base64}"
          class="w-full h-full border-0"
          title="Visualizacao do documento"
        ></iframe>
      `;
      } catch (error) {
        const err = error;
        visualizador.innerHTML = `
        <div class="h-full flex items-center justify-center text-red-400">
          <div class="text-center">
            <i class="fas fa-exclamation-circle text-2xl mb-3"></i>
            <p>Erro ao carregar documento</p>
            <p class="text-sm text-gray-400 mt-1">${escapeHtml(err.message)}</p>
          </div>
        </div>
      `;
      }
    }
    // ==========================================
    // Historico
    // ==========================================
    obterNumeroProcesso(item) {
      if (!item) return "";
      return item.numero_processo || item.numero_cnj_formatado || item.numero_cnj || item.cnj || item.dados_processo && item.dados_processo.numero_processo || "";
    }
    obterAutorProcesso(item) {
      if (!item) return "Pedido de Calculo";
      return item.autor || item.dados_processo && item.dados_processo.autor || "Pedido de Calculo";
    }
    formatarDataHistorico(item) {
      const dataStr = item && (item.criado_em || item.data);
      if (!dataStr) {
        return { dataTexto: "-", horaTexto: "-" };
      }
      const data = new Date(dataStr);
      if (Number.isNaN(data.getTime())) {
        return { dataTexto: "-", horaTexto: "-" };
      }
      return {
        dataTexto: data.toLocaleDateString("pt-BR"),
        horaTexto: data.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })
      };
    }
    async carregarHistoricoRecente() {
      const container = document.getElementById("historico-cards");
      if (!container) return;
      try {
        const response = await fetch(`${API_URL}/historico`, {
          headers: { "Authorization": `Bearer ${this.getToken()}` }
        });
        if (!response.ok) {
          container.innerHTML = `
          <div class="text-center py-8 text-gray-400">
            <i class="fas fa-calculator text-4xl mb-3 opacity-50"></i>
            <p class="text-sm">Nenhum pedido gerado ainda</p>
            <p class="text-xs mt-1">Use o formulario acima para gerar seu primeiro pedido</p>
          </div>
        `;
          return;
        }
        const historico = await response.json();
        if (!historico || historico.length === 0) {
          container.innerHTML = `
          <div class="text-center py-8 text-gray-400">
            <i class="fas fa-calculator text-4xl mb-3 opacity-50"></i>
            <p class="text-sm">Nenhum pedido gerado ainda</p>
            <p class="text-xs mt-1">Use o formulario acima para gerar seu primeiro pedido</p>
          </div>
        `;
          return;
        }
        historico.sort((a, b) => {
          const dataA = a.criado_em ? new Date(a.criado_em) : /* @__PURE__ */ new Date(0);
          const dataB = b.criado_em ? new Date(b.criado_em) : /* @__PURE__ */ new Date(0);
          return dataB.getTime() - dataA.getTime();
        });
        const recentes = historico.slice(0, 5);
        container.innerHTML = recentes.map((item) => {
          const numeroProcesso = this.obterNumeroProcesso(item) || "Processo";
          const autor = this.obterAutorProcesso(item);
          const { dataTexto, horaTexto } = this.formatarDataHistorico(item);
          return `
          <div class="flex items-center gap-4 p-4 border border-gray-100 rounded-xl hover:bg-amber-50 hover:border-amber-300 transition-all cursor-pointer group"
               onclick="app.abrirGeracao(${item.id})">
            <div class="w-12 h-12 bg-gradient-to-br from-amber-100 to-orange-100 rounded-xl flex items-center justify-center group-hover:from-amber-200 group-hover:to-orange-200 transition-colors">
              <i class="fas fa-calculator text-amber-600"></i>
            </div>
            <div class="flex-1 min-w-0">
              <p class="font-medium text-gray-800 truncate group-hover:text-amber-700">${escapeHtml(numeroProcesso)}</p>
              <p class="text-sm text-amber-600 font-medium">${escapeHtml(autor)}</p>
            </div>
            <div class="text-right flex-shrink-0">
              <p class="text-xs text-gray-400">${dataTexto}</p>
              <p class="text-xs text-gray-300">${horaTexto}</p>
            </div>
            <i class="fas fa-chevron-right text-gray-300 group-hover:text-amber-500 transition-colors"></i>
          </div>
        `;
        }).join("");
      } catch (error) {
        console.error("Erro ao carregar historico:", error);
        container.innerHTML = `
        <div class="text-center py-8 text-gray-400">
          <i class="fas fa-calculator text-4xl mb-3 opacity-50"></i>
          <p class="text-sm">Nenhum pedido gerado ainda</p>
        </div>
      `;
      }
    }
    async carregarHistoricoCompleto() {
      const container = document.getElementById("lista-historico");
      if (!container) return;
      try {
        container.innerHTML = `
        <div class="text-center py-8 text-gray-400">
          <i class="fas fa-spinner fa-spin text-2xl mb-2"></i>
          <p class="text-sm">Carregando historico...</p>
        </div>
      `;
        const response = await fetch(`${API_URL}/historico`, {
          headers: { "Authorization": `Bearer ${this.getToken()}` }
        });
        if (!response.ok) {
          throw new Error("Erro ao carregar historico");
        }
        const historico = await response.json();
        if (!historico || historico.length === 0) {
          container.innerHTML = `
          <div class="text-center py-8 text-gray-400">
            <i class="fas fa-calculator text-4xl mb-3 opacity-50"></i>
            <p class="text-sm">Nenhum pedido gerado ainda</p>
          </div>
        `;
          return;
        }
        historico.sort((a, b) => {
          const dataA = a.criado_em ? new Date(a.criado_em) : /* @__PURE__ */ new Date(0);
          const dataB = b.criado_em ? new Date(b.criado_em) : /* @__PURE__ */ new Date(0);
          return dataB.getTime() - dataA.getTime();
        });
        container.innerHTML = historico.map((item) => {
          const numeroProcesso = this.obterNumeroProcesso(item) || "Processo";
          const autor = this.obterAutorProcesso(item);
          const { dataTexto, horaTexto } = this.formatarDataHistorico(item);
          return `
          <div class="p-3 bg-gray-50 hover:bg-gray-100 rounded-lg cursor-pointer transition-colors mb-2"
              onclick="app.abrirGeracao(${item.id})">
            <div class="flex items-center justify-between mb-1">
              <span class="text-sm font-medium text-gray-800 truncate">${escapeHtml(numeroProcesso)}</span>
              <span class="text-xs text-gray-400">${dataTexto}</span>
            </div>
            <div class="flex items-center justify-between">
              <span class="text-xs text-gray-500 truncate">${escapeHtml(autor || "Autor nao identificado")}</span>
              <span class="text-xs text-gray-400">${horaTexto}</span>
            </div>
          </div>
        `;
        }).join("");
      } catch (error) {
        console.error("Erro ao carregar historico completo:", error);
        container.innerHTML = `
        <div class="text-center py-8 text-gray-400">
          <i class="fas fa-exclamation-circle text-2xl mb-2"></i>
          <p class="text-sm">Erro ao carregar historico</p>
          <button onclick="app.carregarHistoricoCompleto()" class="mt-2 text-xs text-primary-600 hover:text-primary-700">
            Tentar novamente
          </button>
        </div>
      `;
      }
    }
    async carregarDoHistorico(id) {
      await this.abrirGeracao(id);
    }
    async abrirGeracao(id) {
      try {
        const response = await fetch(`${API_URL}/historico/${id}`, {
          headers: { "Authorization": `Bearer ${this.getToken()}` }
        });
        if (!response.ok) throw new Error("Erro ao carregar");
        const data = await response.json();
        const dadosBasicos = data.dados_basicos || data.dados_processo || data.dados_agente1 && data.dados_agente1.dados_basicos || {};
        const dadosExtracao = data.dados_extracao || data.dados_agente2 || {};
        const numeroProcesso = this.obterNumeroProcesso(data) || dadosBasicos.numero_processo || "";
        this.numeroCNJ = numeroProcesso || this.numeroCNJ;
        this.pedidoMarkdown = data.conteudo_gerado || data.pedido_markdown || this.pedidoMarkdown;
        this.dadosBasicos = dadosBasicos;
        this.dadosExtracao = dadosExtracao;
        this.documentosBaixados = data.documentos_baixados || [];
        this.geracaoId = data.id;
        this.isNovaGeracao = false;
        const editorTipoPeca = document.getElementById("editor-tipo-peca");
        if (editorTipoPeca) editorTipoPeca.textContent = "Pedido de Calculo";
        const editorCnj = document.getElementById("editor-cnj");
        if (editorCnj) editorCnj.textContent = this.numeroCNJ || dadosBasicos.numero_processo || "";
        this.renderizarMinuta();
        this.historicoChat = data.historico_chat || [];
        this.renderizarChatHistorico();
        this.abrirModal("modal-editor");
      } catch {
        this.showToast("Erro ao abrir pedido", "error");
      }
    }
    renderizarChatHistorico() {
      this.resetarChat();
      for (let i = 0; i < this.historicoChat.length; i += 2) {
        if (this.historicoChat[i]) {
          this.adicionarMensagemChat("user", this.historicoChat[i].content);
        }
        if (this.historicoChat[i + 1]) {
          this.adicionarMensagemChat("ai", this.historicoChat[i + 1].content, true);
        }
      }
    }
    // ==========================================
    // UI Helpers
    // ==========================================
    getToken() {
      return localStorage.getItem("access_token") || "";
    }
    abrirModal(id) {
      document.getElementById(id)?.classList.remove("hidden");
    }
    fecharModal(id) {
      document.getElementById(id)?.classList.add("hidden");
    }
    mostrarLoading(mensagem, agente) {
      document.getElementById("modal-progresso")?.classList.remove("hidden");
      this.setProgressoMensagem(mensagem);
      if (agente !== null) {
        this.atualizarStatusAgente(agente, "ativo");
      }
    }
    esconderLoading() {
      document.getElementById("modal-progresso")?.classList.add("hidden");
    }
    atualizarStatusAgente(numero, status) {
      const statusEl = document.getElementById(`agente${numero}-status`);
      const iconEl = document.getElementById(`agente${numero}-icon`);
      const badgeEl = document.getElementById(`agente${numero}-badge`);
      if (!statusEl || !iconEl || !badgeEl) return;
      statusEl.classList.remove("bg-gray-50", "bg-blue-50", "bg-green-50", "bg-red-50");
      iconEl.classList.remove("bg-gray-200", "bg-blue-500", "bg-green-500", "bg-red-500");
      const progressos = { 1: 25, 2: 50, 3: 75, 4: 100 };
      if (status === "concluido" || status === "ativo") {
        this.setProgressoBarra(progressos[numero] + "%");
      }
      const iconI = iconEl.querySelector("i");
      switch (status) {
        case "ativo":
          statusEl.classList.add("bg-blue-50");
          iconEl.classList.add("bg-blue-500");
          if (iconI) iconI.className = "fas fa-spinner fa-spin text-white text-sm";
          badgeEl.className = "text-xs px-3 py-1 rounded-full bg-blue-100 text-blue-700 font-medium";
          badgeEl.textContent = "Processando";
          break;
        case "concluido":
          statusEl.classList.add("bg-green-50");
          iconEl.classList.add("bg-green-500");
          if (iconI) iconI.className = "fas fa-check text-white text-sm";
          badgeEl.className = "text-xs px-3 py-1 rounded-full bg-green-100 text-green-700 font-medium";
          badgeEl.textContent = "Concluido";
          break;
        case "erro":
          statusEl.classList.add("bg-red-50");
          iconEl.classList.add("bg-red-500");
          if (iconI) iconI.className = "fas fa-times text-white text-sm";
          badgeEl.className = "text-xs px-3 py-1 rounded-full bg-red-100 text-red-700 font-medium";
          badgeEl.textContent = "Erro";
          break;
        default:
          statusEl.classList.add("bg-gray-50");
          iconEl.classList.add("bg-gray-200");
          badgeEl.className = "text-xs px-3 py-1 rounded-full bg-gray-100 text-gray-500 font-medium";
          badgeEl.textContent = "Aguardando";
      }
    }
    resetarStatusAgentes() {
      for (let i = 1; i <= 4; i++) {
        this.atualizarStatusAgente(i, "aguardando");
      }
      this.setProgressoBarra("0%");
    }
    mostrarErro(mensagem) {
      const erroMensagem = document.getElementById("erro-mensagem");
      const toastErro = document.getElementById("toast-erro");
      if (erroMensagem) erroMensagem.textContent = mensagem;
      if (toastErro) {
        toastErro.classList.remove("hidden");
        setTimeout(() => {
          toastErro.classList.add("hidden");
        }, 5e3);
      }
    }
    esconderErro() {
      document.getElementById("toast-erro")?.classList.add("hidden");
    }
    showToast(mensagem, tipo = "success") {
      const toast = document.getElementById("toast");
      const icon = document.getElementById("toast-icon");
      const msg = document.getElementById("toast-message");
      if (!toast || !icon || !msg) return;
      msg.textContent = mensagem;
      if (tipo === "success") {
        icon.className = "fas fa-check-circle text-green-400";
      } else if (tipo === "error") {
        icon.className = "fas fa-exclamation-circle text-red-400";
      } else if (tipo === "warning") {
        icon.className = "fas fa-exclamation-triangle text-yellow-400";
      }
      toast.classList.remove("hidden");
      setTimeout(() => toast.classList.add("hidden"), 3e3);
    }
    async mostrarConfirmacaoSobrescrita(dados) {
      return new Promise((resolve) => {
        const modal = document.createElement("div");
        modal.id = "modal-confirmar-sobrescrita";
        modal.className = "fixed inset-0 bg-gray-900/30 backdrop-blur-sm flex items-center justify-center z-50";
        modal.innerHTML = `
        <div class="bg-white rounded-2xl p-6 max-w-md mx-4 shadow-2xl border border-gray-200">
          <div class="flex items-center gap-3 mb-4">
            <div class="w-12 h-12 bg-amber-100 rounded-xl flex items-center justify-center">
              <i class="fas fa-exclamation-triangle text-amber-500 text-xl"></i>
            </div>
            <div>
              <h3 class="text-lg font-semibold text-gray-800">Processo ja existe</h3>
              <p class="text-sm text-gray-500">Este processo consta no historico</p>
            </div>
          </div>
          <div class="bg-gray-50 rounded-xl p-4 mb-4 border border-gray-100">
            <div class="space-y-2 text-sm">
              <div class="flex justify-between">
                <span class="text-gray-500">Processo:</span>
                <span class="text-gray-800 font-medium">${escapeHtml(dados.numero_cnj_formatado || "N/A")}</span>
              </div>
              <div class="flex justify-between">
                <span class="text-gray-500">Autor:</span>
                <span class="text-gray-800">${escapeHtml(dados.autor || "N/A")}</span>
              </div>
              <div class="flex justify-between">
                <span class="text-gray-500">Gerado em:</span>
                <span class="text-gray-800">${escapeHtml(dados.criado_em || "N/A")}</span>
              </div>
            </div>
          </div>
          <p class="text-gray-600 text-sm mb-4">O que deseja fazer?</p>
          <div class="flex flex-col gap-2">
            <button id="btn-ver-existente" class="w-full px-4 py-2.5 bg-primary-600 hover:bg-primary-700 rounded-xl text-white font-medium transition-colors flex items-center justify-center gap-2 shadow-sm">
              <i class="fas fa-eye"></i> Ver pedido existente
            </button>
            <button id="btn-refazer" class="w-full px-4 py-2.5 bg-amber-500 hover:bg-amber-600 rounded-xl text-white font-medium transition-colors flex items-center justify-center gap-2 shadow-sm">
              <i class="fas fa-redo"></i> Refazer pedido
            </button>
            <button id="btn-cancelar-sobrescrita" class="w-full px-4 py-2.5 bg-gray-100 hover:bg-gray-200 rounded-xl text-gray-700 font-medium transition-colors flex items-center justify-center gap-2">
              <i class="fas fa-times"></i> Cancelar
            </button>
          </div>
        </div>
      `;
        document.body.appendChild(modal);
        document.getElementById("btn-ver-existente")?.addEventListener("click", () => {
          modal.remove();
          resolve("ver");
        });
        document.getElementById("btn-refazer")?.addEventListener("click", () => {
          modal.remove();
          resolve("refazer");
        });
        document.getElementById("btn-cancelar-sobrescrita")?.addEventListener("click", () => {
          modal.remove();
          resolve("cancelar");
        });
        modal.addEventListener("click", (e) => {
          if (e.target === modal) {
            modal.remove();
            resolve("cancelar");
          }
        });
      });
    }
    cancelarGeracao() {
      this.esconderLoading();
      this.showToast("Geracao cancelada", "warning");
    }
    selecionarNota(nota) {
      this.notaSelecionada = nota;
      document.querySelectorAll(".estrela").forEach((btn, index) => {
        btn.classList.toggle("text-yellow-400", index < nota);
        btn.classList.toggle("text-gray-300", index >= nota);
      });
      const btnEnviarFeedback = document.getElementById("btn-enviar-feedback");
      if (btnEnviarFeedback) btnEnviarFeedback.disabled = false;
    }
    async enviarFeedback() {
      if (!this.geracaoId) {
        this.fecharModal("modal-feedback");
        this.resetar();
        return;
      }
      const comentarioEl = document.getElementById("feedback-comentario");
      const comentario = comentarioEl?.value || "";
      try {
        await fetch(`${API_URL}/feedback`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${this.getToken()}`
          },
          body: JSON.stringify({
            geracao_id: this.geracaoId,
            avaliacao: this.notaSelecionada && this.notaSelecionada >= 4 ? "correto" : this.notaSelecionada && this.notaSelecionada >= 2 ? "parcial" : "incorreto",
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
    resetar() {
      const inputCnj = document.getElementById("numero-cnj");
      if (inputCnj) inputCnj.value = "";
      this.numeroCNJ = null;
      this.pedidoMarkdown = null;
      this.dadosBasicos = null;
      this.dadosExtracao = null;
      this.historicoChat = [];
      this.notaSelecionada = null;
      this.isNovaGeracao = false;
      this.streamingContent = "";
      this.isStreaming = false;
    }
    // ==========================================
    // Streaming de Geracao em Tempo Real
    // ==========================================
    abrirEditorStreaming() {
      try {
        this.esconderLoading();
        this.pedidoMarkdown = "";
        this.historicoChat = [];
        this.geracaoId = null;
        this.isNovaGeracao = true;
        const editorTipoPeca = document.getElementById("editor-tipo-peca");
        if (editorTipoPeca) editorTipoPeca.textContent = "Gerando...";
        const editorCnj = document.getElementById("editor-cnj");
        if (editorCnj) editorCnj.textContent = this.numeroCNJ ? `- ${this.numeroCNJ}` : "";
        const container = document.getElementById("pedido-content");
        if (container) {
          container.innerHTML = `
          <div class="flex items-center gap-2 text-primary-600 mb-4">
            <div class="animate-spin h-4 w-4 border-2 border-primary-500 border-t-transparent rounded-full"></div>
            <span class="text-sm font-medium">Gerando pedido em tempo real...</span>
          </div>
          <div id="streaming-content" class="prose prose-sm max-w-none"></div>
        `;
        }
        const status = document.getElementById("pedido-status");
        if (status) {
          status.innerHTML = `
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
        document.getElementById("modal-editor")?.classList.remove("hidden");
      } catch (err) {
        console.error("Erro em abrirEditorStreaming:", err);
      }
    }
    atualizarEditorStreaming() {
      const contentEl = document.getElementById("streaming-content");
      if (contentEl && this.streamingContent) {
        if (typeof marked !== "undefined") {
          marked.setOptions({ breaks: true, gfm: true });
          contentEl.innerHTML = marked.parse(this.streamingContent);
        } else {
          contentEl.innerHTML = this.streamingContent.replace(/## (.*)/g, '<h2 class="text-lg font-semibold mt-4 mb-2">$1</h2>').replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>").replace(/\*(.*?)\*/g, "<em>$1</em>").replace(/\n/g, "<br>");
        }
        const container = document.getElementById("pedido-content");
        if (container) {
          container.scrollTop = container.scrollHeight;
        }
      }
      const statusEl = document.getElementById("pedido-status");
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
    finalizarEditorStreaming(geracaoId, dadosBasicos, dadosExtracao, documentosBaixados, conteudoFinal) {
      this.geracaoId = geracaoId;
      this.dadosBasicos = dadosBasicos || {};
      this.dadosExtracao = dadosExtracao || {};
      this.documentosBaixados = documentosBaixados || [];
      this.pedidoMarkdown = conteudoFinal;
      const editorTipoPeca = document.getElementById("editor-tipo-peca");
      if (editorTipoPeca) editorTipoPeca.textContent = "Pedido de Calculo";
      this.renderizarPedido();
      const status = document.getElementById("pedido-status");
      if (status) status.textContent = "Geracao concluida";
      const chatInput = document.getElementById("chat-input");
      if (chatInput) {
        chatInput.disabled = false;
        chatInput.placeholder = "Digite uma solicitacao de alteracao...";
      }
      this.isStreaming = false;
      this.streamingContent = "";
    }
    finalizarStreaming() {
      this.isStreaming = false;
      this.streamingContent = "";
    }
  };
  function toggleHistorico() {
    const painel = document.getElementById("painel-historico");
    if (!painel) return;
    const estaFechado = painel.classList.contains("hidden");
    painel.classList.toggle("hidden");
    painel.classList.toggle("translate-x-full");
    if (estaFechado && app) {
      app.carregarHistoricoCompleto();
    }
  }
  function fecharModalEditor() {
    document.getElementById("modal-editor")?.classList.add("hidden");
    if (app && app.isNovaGeracao) {
      document.getElementById("modal-feedback")?.classList.remove("hidden");
    }
  }
  var app = new PedidoCalculoApp();
  window.app = app;
  window.toggleHistorico = toggleHistorico;
  window.fecharModalEditor = fecharModalEditor;
})();
//# sourceMappingURL=app.js.map
