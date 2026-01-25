// Generated from TypeScript - DO NOT EDIT DIRECTLY
// Source: src\sistemas\relatorio_cumprimento\app.ts
// Built at: 2026-01-24T19:56:06.876Z

"use strict";
(() => {
  // src/sistemas/relatorio_cumprimento/app.ts
  var API_URL = "/relatorio-cumprimento/api";
  var RelatorioCumprimentoApp = class {
    constructor() {
      this.numeroCNJ = null;
      this.geracaoId = null;
      this.notaSelecionada = null;
      this.isNovaGeracao = false;
      // Dados para o editor interativo
      this.relatorioMarkdown = null;
      this.dadosCumprimento = null;
      this.dadosPrincipal = null;
      this.documentosBaixados = [];
      this.transitoJulgado = null;
      this.historicoChat = [];
      this.isProcessingEdit = false;
      // Streaming de geracao em tempo real
      this.streamingContent = "";
      this.isStreaming = false;
      // Request ID para diagnóstico
      this.lastRequestId = null;
      this.initEventListeners();
      this.checkAuth();
    }
    async checkAuth() {
      const token = localStorage.getItem("access_token");
      if (!token) {
        window.location.href = "/login?next=/relatorio-cumprimento";
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
        window.location.href = "/login?next=/relatorio-cumprimento";
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
    getToken() {
      return localStorage.getItem("access_token");
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
      this.resetarStatusEtapas();
      this.mostrarLoading("Conectando ao TJ-MS...");
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
          this.mostrarErro("Conexao interrompida com o servidor.");
          this.esconderLoading();
        }
      } catch (error) {
        const err = error;
        let mensagemErro = err.message;
        if (err.message.includes("502") || err.message.includes("Proxy")) {
          mensagemErro = "Erro de conexao com o TJ-MS (502). Tente novamente em alguns minutos.";
        } else if (err.message.includes("Failed to fetch") || err.message.includes("NetworkError")) {
          mensagemErro = "Erro de conexao com o servidor. Verifique sua internet.";
        }
        this.mostrarErro(mensagemErro);
        this.esconderLoading();
      }
    }
    processarEventoStream(data) {
      const logData = { ...data };
      if ("relatorio_markdown" in logData && typeof logData.relatorio_markdown === "string") {
        logData.relatorio_markdown = `[${logData.relatorio_markdown.length} chars]`;
      }
      console.log("[RelatorioCumprimento] Evento SSE:", logData);
      switch (data.tipo) {
        case "inicio":
          this.setProgressoMensagem(data.mensagem);
          break;
        case "etapa":
          this.atualizarStatusEtapa(data.etapa, data.status);
          this.setProgressoMensagem(data.mensagem);
          if (data.status === "erro") {
            this.mostrarErro(data.mensagem);
            this.esconderLoading();
          }
          break;
        case "sucesso":
          this.setProgressoBarra("100%");
          this.atualizarStatusEtapa(5, "concluido");
          this.lastRequestId = data.request_id || null;
          const conteudoFinal = this.isStreaming ? this.streamingContent : data.relatorio_markdown;
          const conteudoLimpo = (conteudoFinal || "").trim();
          if (!conteudoLimpo) {
            console.error("[RelatorioCumprimento] ERRO: Conteudo vazio recebido!", {
              request_id: data.request_id,
              geracao_id: data.geracao_id,
              streaming_len: this.streamingContent?.length,
              markdown_len: data.relatorio_markdown?.length
            });
            this.finalizarStreaming();
            this.esconderLoading();
            this.mostrarErro(`Relatorio gerado esta vazio. Por favor, tente novamente. (request_id: ${data.request_id || "N/A"})`);
            return;
          }
          console.log("[RelatorioCumprimento] Sucesso:", {
            request_id: data.request_id,
            geracao_id: data.geracao_id,
            conteudo_len: conteudoLimpo.length
          });
          if (this.isStreaming) {
            this.finalizarEditorStreaming(
              data.geracao_id,
              data.dados_cumprimento || null,
              data.dados_principal || null,
              data.documentos_baixados || [],
              data.transito_julgado || null,
              conteudoFinal || ""
            );
            this.esconderLoading();
            this.showToast("Relatorio gerado com sucesso!", "success");
          } else {
            setTimeout(() => {
              this.esconderLoading();
              this.showToast("Relatorio gerado com sucesso!", "success");
              this.exibirEditor({
                geracao_id: data.geracao_id,
                dados_cumprimento: data.dados_cumprimento,
                dados_principal: data.dados_principal,
                relatorio_markdown: data.relatorio_markdown,
                documentos_baixados: data.documentos_baixados,
                transito_julgado: data.transito_julgado
              });
            }, 500);
          }
          this.carregarHistoricoRecente();
          break;
        case "erro":
          console.error("[RelatorioCumprimento] Erro recebido:", data.mensagem);
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
              console.log("[RelatorioCumprimento] Iniciando streaming...");
            }
            this.streamingContent += data.content;
            this.atualizarEditorStreaming();
          } catch (err) {
            console.error("[RelatorioCumprimento] Erro no streaming:", err);
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
    atualizarStatusEtapa(etapa, status) {
      const statusEl = document.getElementById(`etapa${etapa}-status`);
      const iconEl = document.getElementById(`etapa${etapa}-icon`);
      const badgeEl = document.getElementById(`etapa${etapa}-badge`);
      if (!statusEl || !iconEl || !badgeEl) return;
      statusEl.classList.remove("bg-gray-50", "bg-green-50", "bg-yellow-50", "border-gray-100", "border-green-200", "border-yellow-200");
      const iconI = iconEl.querySelector("i");
      if (status === "ativo") {
        statusEl.classList.add("bg-yellow-50", "border-yellow-200");
        iconEl.classList.remove("bg-gray-200", "bg-green-500");
        iconEl.classList.add("bg-yellow-500", "pulse-glow");
        iconI?.classList.remove("text-gray-400", "text-white");
        iconI?.classList.add("text-white");
        badgeEl.textContent = "Processando";
        badgeEl.classList.remove("bg-gray-100", "text-gray-500", "bg-green-100", "text-green-700");
        badgeEl.classList.add("bg-yellow-100", "text-yellow-700");
        const progresso = (etapa - 1) / 5 * 100;
        this.setProgressoBarra(`${progresso}%`);
      } else if (status === "concluido") {
        statusEl.classList.add("bg-green-50", "border-green-200");
        iconEl.classList.remove("bg-gray-200", "bg-yellow-500", "pulse-glow");
        iconEl.classList.add("bg-green-500");
        iconI?.classList.remove("text-gray-400");
        iconI?.classList.add("text-white");
        badgeEl.textContent = "Concluido";
        badgeEl.classList.remove("bg-gray-100", "text-gray-500", "bg-yellow-100", "text-yellow-700");
        badgeEl.classList.add("bg-green-100", "text-green-700");
        const progresso = etapa / 5 * 100;
        this.setProgressoBarra(`${progresso}%`);
      }
    }
    resetarStatusEtapas() {
      for (let i = 1; i <= 5; i++) {
        const statusEl = document.getElementById(`etapa${i}-status`);
        const iconEl = document.getElementById(`etapa${i}-icon`);
        const badgeEl = document.getElementById(`etapa${i}-badge`);
        if (!statusEl || !iconEl || !badgeEl) continue;
        statusEl.classList.remove("bg-green-50", "bg-yellow-50", "border-green-200", "border-yellow-200");
        statusEl.classList.add("bg-gray-50", "border-gray-100");
        iconEl.classList.remove("bg-green-500", "bg-yellow-500", "pulse-glow");
        iconEl.classList.add("bg-gray-200");
        const iconI = iconEl.querySelector("i");
        iconI?.classList.remove("text-white");
        iconI?.classList.add("text-gray-400");
        badgeEl.textContent = "Aguardando";
        badgeEl.classList.remove("bg-green-100", "text-green-700", "bg-yellow-100", "text-yellow-700");
        badgeEl.classList.add("bg-gray-100", "text-gray-500");
      }
      this.setProgressoBarra("0%");
    }
    exibirEditor(data, isNova = true) {
      this.dadosCumprimento = data.dados_cumprimento || {};
      this.dadosPrincipal = data.dados_principal || null;
      this.relatorioMarkdown = data.relatorio_markdown || null;
      this.documentosBaixados = data.documentos_baixados || [];
      this.transitoJulgado = data.transito_julgado || {};
      this.geracaoId = data.geracao_id;
      this.isNovaGeracao = isNova;
      const editorCnj = document.getElementById("editor-cnj");
      if (editorCnj) {
        editorCnj.textContent = this.dadosCumprimento?.numero_processo_formatado || this.numeroCNJ || "";
      }
      this.renderizarMinuta();
      this.historicoChat = [];
      this.resetarChat();
      this.abrirModal("modal-editor");
    }
    abrirEditorStreaming() {
      const editorCnj = document.getElementById("editor-cnj");
      if (editorCnj) {
        editorCnj.textContent = this.numeroCNJ || "Gerando...";
      }
      const minutaContent = document.getElementById("minuta-content");
      if (minutaContent) {
        minutaContent.innerHTML = '<div class="animate-pulse"><div class="h-4 bg-gray-200 rounded w-3/4 mb-4"></div><div class="h-4 bg-gray-200 rounded w-1/2"></div></div>';
      }
      this.abrirModal("modal-editor");
    }
    atualizarEditorStreaming() {
      const content = document.getElementById("minuta-content");
      if (content && typeof marked !== "undefined") {
        content.innerHTML = marked.parse(this.streamingContent);
      }
      const container = document.getElementById("minuta-container");
      if (container) {
        container.scrollTop = container.scrollHeight;
      }
    }
    finalizarEditorStreaming(geracaoId, dadosCumprimento, dadosPrincipal, documentosBaixados, transitoJulgado, conteudoFinal) {
      this.geracaoId = geracaoId;
      this.dadosCumprimento = dadosCumprimento || {};
      this.dadosPrincipal = dadosPrincipal || null;
      this.documentosBaixados = documentosBaixados || [];
      this.transitoJulgado = transitoJulgado || {};
      this.relatorioMarkdown = conteudoFinal;
      this.isNovaGeracao = true;
      const editorCnj = document.getElementById("editor-cnj");
      if (editorCnj) {
        editorCnj.textContent = this.dadosCumprimento?.numero_processo_formatado || this.numeroCNJ || "";
      }
      this.finalizarStreaming();
      this.renderizarMinuta();
    }
    finalizarStreaming() {
      this.isStreaming = false;
      this.streamingContent = "";
    }
    renderizarMinuta() {
      const content = document.getElementById("minuta-content");
      if (!content) return;
      const conteudo = (this.relatorioMarkdown || "").trim();
      if (!conteudo) {
        content.innerHTML = `
        <div class="flex flex-col items-center justify-center h-64 text-gray-400">
          <i class="fas fa-exclamation-triangle text-4xl mb-4 text-yellow-500"></i>
          <p class="text-lg font-medium text-gray-600">Relatorio vazio</p>
          <p class="text-sm mt-2">O conteudo do relatorio nao foi gerado corretamente.</p>
          <p class="text-xs mt-1 text-gray-400">request_id: ${this.lastRequestId || "N/A"}</p>
          <button onclick="app.fecharModal('modal-editor'); app.iniciarProcessamento(true);"
                  class="mt-4 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors">
            <i class="fas fa-redo mr-2"></i>Gerar novamente
          </button>
        </div>
      `;
        const minutaStatus2 = document.getElementById("minuta-status");
        if (minutaStatus2) minutaStatus2.textContent = "Erro na geracao";
        console.error("[RelatorioCumprimento] renderizarMinuta: conteudo vazio!");
        return;
      }
      if (typeof marked !== "undefined") {
        content.innerHTML = marked.parse(conteudo);
      } else {
        content.innerHTML = conteudo;
      }
      const minutaStatus = document.getElementById("minuta-status");
      if (minutaStatus) minutaStatus.textContent = "Atualizado agora";
      console.log("[RelatorioCumprimento] renderizarMinuta: OK, len=" + conteudo.length);
    }
    resetarChat() {
      const chatMessages = document.getElementById("chat-messages");
      if (!chatMessages) return;
      chatMessages.innerHTML = `
      <div class="flex gap-3">
        <div class="w-8 h-8 bg-gradient-to-br from-primary-500 to-primary-600 rounded-full flex items-center justify-center flex-shrink-0">
          <i class="fas fa-robot text-white text-xs"></i>
        </div>
        <div class="chat-bubble-ai px-4 py-3 max-w-[85%]">
          <p class="text-sm text-gray-700">
            Ola! Sou o assistente de edicao. Voce pode me pedir para fazer alteracoes no relatorio, como:
          </p>
          <ul class="text-xs text-gray-500 mt-2 space-y-1">
            <li>- "Corrija a data do transito em julgado"</li>
            <li>- "Adicione mais detalhes sobre a condenacao"</li>
            <li>- "Inclua observacao sobre pendencias"</li>
          </ul>
        </div>
      </div>
    `;
    }
    async enviarMensagemChat() {
      const input = document.getElementById("chat-input");
      if (!input) return;
      const mensagem = input.value.trim();
      if (!mensagem || this.isProcessingEdit) return;
      this.isProcessingEdit = true;
      input.value = "";
      input.disabled = true;
      const btnEnviar = document.getElementById("btn-enviar-chat");
      if (btnEnviar) btnEnviar.disabled = true;
      this.adicionarMensagemChat(mensagem, "usuario");
      this.adicionarIndicadorDigitando();
      try {
        const response = await fetch(`${API_URL}/editar`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${this.getToken()}`
          },
          body: JSON.stringify({
            geracao_id: this.geracaoId,
            mensagem_usuario: mensagem
          })
        });
        const data = await response.json();
        this.removerIndicadorDigitando();
        if (data.status === "sucesso" && data.relatorio_markdown) {
          this.relatorioMarkdown = data.relatorio_markdown;
          this.renderizarMinuta();
          this.adicionarMensagemChat("Relatorio atualizado conforme solicitado.", "assistente");
          this.showToast("Relatorio atualizado!", "success");
        } else {
          this.adicionarMensagemChat(`Nao consegui fazer a alteracao: ${data.mensagem || "Erro desconhecido"}`, "assistente");
        }
      } catch {
        this.removerIndicadorDigitando();
        this.adicionarMensagemChat("Erro ao processar sua solicitacao. Tente novamente.", "assistente");
      }
      this.isProcessingEdit = false;
      input.disabled = false;
      if (btnEnviar) btnEnviar.disabled = false;
      input.focus();
    }
    adicionarMensagemChat(mensagem, tipo) {
      const chatMessages = document.getElementById("chat-messages");
      if (!chatMessages) return;
      const div = document.createElement("div");
      div.className = "flex gap-3" + (tipo === "usuario" ? " justify-end" : "");
      if (tipo === "usuario") {
        div.innerHTML = `
        <div class="chat-bubble-user px-4 py-3 max-w-[85%]">
          <p class="text-sm text-white">${escapeHtml(mensagem)}</p>
        </div>
      `;
      } else {
        div.innerHTML = `
        <div class="w-8 h-8 bg-gradient-to-br from-primary-500 to-primary-600 rounded-full flex items-center justify-center flex-shrink-0">
          <i class="fas fa-robot text-white text-xs"></i>
        </div>
        <div class="chat-bubble-ai px-4 py-3 max-w-[85%]">
          <p class="text-sm text-gray-700">${escapeHtml(mensagem)}</p>
        </div>
      `;
      }
      chatMessages.appendChild(div);
      chatMessages.scrollTop = chatMessages.scrollHeight;
    }
    adicionarIndicadorDigitando() {
      const chatMessages = document.getElementById("chat-messages");
      if (!chatMessages) return;
      const div = document.createElement("div");
      div.id = "typing-indicator";
      div.className = "flex gap-3";
      div.innerHTML = `
      <div class="w-8 h-8 bg-gradient-to-br from-primary-500 to-primary-600 rounded-full flex items-center justify-center flex-shrink-0">
        <i class="fas fa-robot text-white text-xs"></i>
      </div>
      <div class="chat-bubble-ai">
        <div class="typing-indicator">
          <span></span>
          <span></span>
          <span></span>
        </div>
      </div>
    `;
      chatMessages.appendChild(div);
      chatMessages.scrollTop = chatMessages.scrollHeight;
    }
    removerIndicadorDigitando() {
      const indicator = document.getElementById("typing-indicator");
      if (indicator) indicator.remove();
    }
    async copiarMinuta() {
      try {
        await navigator.clipboard.writeText(this.relatorioMarkdown || "");
        this.showToast("Texto copiado!", "success");
      } catch {
        this.showToast("Erro ao copiar", "error");
      }
    }
    async downloadDocx() {
      try {
        this.showToast("Gerando DOCX...", "info");
        const response = await fetch(`${API_URL}/exportar-docx`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${this.getToken()}`
          },
          body: JSON.stringify({
            markdown: this.relatorioMarkdown,
            numero_processo: this.numeroCNJ
          })
        });
        const data = await response.json();
        if (data.status === "sucesso" && data.url_download) {
          const token = this.getToken();
          window.open(`${data.url_download}?token=${token}`, "_blank");
          this.showToast("DOCX gerado!", "success");
        } else {
          this.showToast("Erro ao gerar DOCX", "error");
        }
      } catch {
        this.showToast("Erro ao gerar DOCX", "error");
      }
    }
    async downloadPdf() {
      try {
        this.showToast("Gerando PDF...", "info");
        const response = await fetch(`${API_URL}/exportar-pdf`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${this.getToken()}`
          },
          body: JSON.stringify({
            markdown: this.relatorioMarkdown,
            numero_processo: this.numeroCNJ
          })
        });
        const data = await response.json();
        if (data.status === "sucesso" && data.url_download) {
          const token = this.getToken();
          window.open(`${data.url_download}?token=${token}`, "_blank");
          this.showToast("PDF gerado!", "success");
        } else {
          this.showToast("Erro ao gerar PDF", "error");
        }
      } catch {
        this.showToast("Erro ao gerar PDF", "error");
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
        modal.className = "fixed inset-0 z-[60] hidden";
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
            <div class="w-72 border-r border-gray-200 overflow-y-auto bg-gray-50" id="lista-documentos"></div>
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
      const numeroCumprimento = this.dadosCumprimento?.numero_processo_formatado || this.numeroCNJ;
      const modalDocsInfo = document.getElementById("modal-docs-info");
      if (modalDocsInfo) {
        modalDocsInfo.textContent = `${this.documentosBaixados.length} documento(s) analisado(s) - Processo ${numeroCumprimento}`;
      }
      const lista = document.getElementById("lista-documentos");
      if (!lista) return;
      const documentosVisiveis = this.documentosBaixados.filter((doc) => doc && doc.id_documento);
      if (documentosVisiveis.length === 0) {
        lista.innerHTML = '<p class="text-xs text-gray-400 px-4 py-3">Nenhum documento valido para exibir.</p>';
      } else {
        lista.innerHTML = documentosVisiveis.map((doc, index) => {
          let badge = "";
          const categoria = doc.categoria || "";
          if (categoria.includes("sentenca")) {
            badge = '<span class="ml-auto text-xs bg-purple-100 text-purple-700 px-1.5 py-0.5 rounded">Sentenca</span>';
          } else if (categoria.includes("acordao")) {
            badge = '<span class="ml-auto text-xs bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded">Acordao</span>';
          } else if (categoria.includes("decisao")) {
            badge = '<span class="ml-auto text-xs bg-orange-100 text-orange-700 px-1.5 py-0.5 rounded">Decisao</span>';
          } else if (categoria.includes("peticao")) {
            badge = '<span class="ml-auto text-xs bg-green-100 text-green-700 px-1.5 py-0.5 rounded">Peticao</span>';
          } else if (categoria.includes("transito")) {
            badge = '<span class="ml-auto text-xs bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded">Transito</span>';
          }
          let numeroProcesso = this.numeroCNJ || "";
          if (doc.processo_origem === "principal" && this.dadosPrincipal?.numero_processo) {
            numeroProcesso = this.dadosPrincipal.numero_processo;
          } else if (this.dadosCumprimento?.numero_processo) {
            numeroProcesso = this.dadosCumprimento.numero_processo;
          }
          const nomeDoc = doc.nome || doc.nome_padronizado || doc.tipo_documento || `Documento ${index + 1}`;
          return `
        <button
          onclick="app.visualizarDocumento('${escapeHtml(doc.id_documento)}', ${index}, '${escapeHtml(numeroProcesso)}')"
          class="w-full text-left px-4 py-3 hover:bg-white border-b border-gray-200 transition-colors doc-item"
          data-index="${index}"
        >
          <div class="flex items-center gap-2">
            <i class="fas fa-file-pdf text-red-500"></i>
            <div class="min-w-0 flex-1">
              <p class="text-sm font-medium text-gray-800 truncate">${escapeHtml(nomeDoc)}</p>
              <p class="text-xs text-gray-500 truncate">${escapeHtml(doc.id_documento)}</p>
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
        const numeroProcesso = numeroProcessoDoc || this.dadosCumprimento?.numero_processo || this.numeroCNJ;
        if (!numeroProcesso) {
          throw new Error("Numero do processo nao disponivel");
        }
        const response = await fetch(
          `${API_URL}/documento/${encodeURIComponent(numeroProcesso)}/${encodeURIComponent(idDocumento)}?token=${encodeURIComponent(token || "")}`
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
        const byteCharacters = atob(data.conteudo_base64);
        const byteNumbers = new Array(byteCharacters.length);
        for (let i = 0; i < byteCharacters.length; i++) {
          byteNumbers[i] = byteCharacters.charCodeAt(i);
        }
        const byteArray = new Uint8Array(byteNumbers);
        const blob = new Blob([byteArray], { type: "application/pdf" });
        const blobUrl = URL.createObjectURL(blob);
        visualizador.innerHTML = `
        <iframe
          src="${blobUrl}"
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
    async carregarHistoricoRecente() {
      const containerCards = document.getElementById("historico-cards");
      const containerLista = document.getElementById("lista-historico");
      try {
        const response = await fetch(`${API_URL}/historico`, {
          headers: {
            "Authorization": `Bearer ${this.getToken()}`
          }
        });
        if (response.ok) {
          const historico = await response.json();
          this.renderizarHistoricoCards(historico.slice(0, 5));
          this.renderizarListaHistorico(historico);
        } else {
          // Erro na API - mostrar mensagem vazia
          if (containerCards) {
            containerCards.innerHTML = '<p class="text-gray-500 text-sm text-center py-4">Nenhum relatorio gerado ainda</p>';
          }
          if (containerLista) {
            containerLista.innerHTML = '<p class="text-gray-500 text-sm text-center py-8">Nenhum relatorio no historico</p>';
          }
        }
      } catch (error) {
        console.error("Erro ao carregar historico:", error);
        // Erro de rede - mostrar mensagem
        if (containerCards) {
          containerCards.innerHTML = '<p class="text-gray-500 text-sm text-center py-4">Nenhum relatorio gerado ainda</p>';
        }
        if (containerLista) {
          containerLista.innerHTML = '<p class="text-gray-500 text-sm text-center py-8">Nenhum relatorio no historico</p>';
        }
      }
    }
    renderizarHistoricoCards(historico) {
      const container = document.getElementById("historico-cards");
      if (!container) return;
      if (historico.length === 0) {
        container.innerHTML = '<p class="text-gray-500 text-sm text-center py-4">Nenhum relatorio gerado ainda</p>';
        return;
      }
      container.innerHTML = historico.map((h) => `
      <div class="flex items-center justify-between p-3 bg-gray-50 rounded-xl hover:bg-gray-100 transition-colors cursor-pointer"
           onclick="app.carregarDoHistorico(${h.id})">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 bg-primary-100 rounded-lg flex items-center justify-center">
            <i class="fas fa-file-lines text-primary-600"></i>
          </div>
          <div>
            <p class="font-medium text-gray-800 text-sm">${escapeHtml(h.numero_cumprimento_formatado || h.numero_cumprimento)}</p>
            <p class="text-xs text-gray-500">${escapeHtml(h.dados_basicos?.cumprimento?.autor || "Autor nao identificado")}</p>
          </div>
        </div>
        <div class="text-right">
          <p class="text-xs text-gray-500">${this.formatarData(h.criado_em)}</p>
          ${h.transito_julgado_localizado ? '<span class="text-xs text-green-600"><i class="fas fa-check"></i> Transito</span>' : '<span class="text-xs text-yellow-600"><i class="fas fa-exclamation"></i> Sem transito</span>'}
        </div>
      </div>
    `).join("");
    }
    renderizarListaHistorico(historico) {
      const container = document.getElementById("lista-historico");
      if (!container) return;
      if (historico.length === 0) {
        container.innerHTML = '<p class="text-gray-500 text-sm text-center py-8">Nenhum relatorio no historico</p>';
        return;
      }
      container.innerHTML = historico.map((h) => `
      <div class="p-3 border border-gray-100 rounded-xl mb-3 hover:border-primary-200 hover:bg-primary-50/30 transition-colors cursor-pointer"
           onclick="app.carregarDoHistorico(${h.id})">
        <p class="font-medium text-gray-800 text-sm">${escapeHtml(h.numero_cumprimento_formatado || h.numero_cumprimento)}</p>
        <p class="text-xs text-gray-500 mt-1">${escapeHtml(h.dados_basicos?.cumprimento?.autor || "Autor nao identificado")}</p>
        <div class="flex items-center gap-2 mt-2">
          <span class="text-xs text-gray-400">${this.formatarData(h.criado_em)}</span>
          ${h.tempo_processamento ? `<span class="text-xs text-gray-400">- ${h.tempo_processamento}s</span>` : ""}
        </div>
      </div>
    `).join("");
    }
    async carregarDoHistorico(id) {
      try {
        const response = await fetch(`${API_URL}/historico/${id}`, {
          headers: {
            "Authorization": `Bearer ${this.getToken()}`
          }
        });
        if (response.ok) {
          const dados = await response.json();
          this.numeroCNJ = dados.numero_cumprimento;
          this.exibirEditor({
            geracao_id: dados.id,
            dados_cumprimento: dados.dados_processo_cumprimento,
            dados_principal: dados.dados_processo_principal,
            relatorio_markdown: dados.conteudo_gerado,
            documentos_baixados: dados.documentos_baixados,
            transito_julgado: {
              localizado: dados.transito_julgado_localizado,
              data_transito: dados.data_transito_julgado
            }
          }, false);
          this.fecharModal("painel-historico");
        }
      } catch {
        this.showToast("Erro ao carregar relatorio", "error");
      }
    }
    formatarData(dataISO) {
      if (!dataISO) return "";
      const data = new Date(dataISO);
      return data.toLocaleDateString("pt-BR", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit"
      });
    }
    mostrarConfirmacaoSobrescrita(dados) {
      return new Promise((resolve) => {
        const modal = document.createElement("div");
        modal.className = "fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50";
        modal.innerHTML = `
        <div class="bg-white rounded-2xl p-6 max-w-md w-full mx-4 shadow-2xl">
          <h3 class="text-lg font-bold text-gray-800 mb-2">Processo ja existe</h3>
          <p class="text-gray-600 mb-4">
            Voce ja gerou um relatorio para este processo em ${dados.criado_em || "data desconhecida"}.
          </p>
          <div class="flex gap-3">
            <button class="flex-1 px-4 py-2 bg-gray-100 text-gray-700 rounded-xl hover:bg-gray-200 transition-colors" data-action="cancelar">
              Cancelar
            </button>
            <button class="flex-1 px-4 py-2 bg-blue-100 text-blue-700 rounded-xl hover:bg-blue-200 transition-colors" data-action="ver">
              Ver existente
            </button>
            <button class="flex-1 px-4 py-2 bg-primary-600 text-white rounded-xl hover:bg-primary-700 transition-colors" data-action="refazer">
              Refazer
            </button>
          </div>
        </div>
      `;
        modal.querySelectorAll("button[data-action]").forEach((btn) => {
          btn.addEventListener("click", () => {
            const action = btn.dataset.action;
            modal.remove();
            resolve(action);
          });
        });
        document.body.appendChild(modal);
      });
    }
    cancelarGeracao() {
      this.esconderLoading();
      this.showToast("Geracao cancelada", "info");
    }
    // Feedback
    selecionarNota(nota) {
      this.notaSelecionada = nota;
      document.querySelectorAll(".estrela").forEach((btn, i) => {
        btn.classList.toggle("text-primary-400", i < nota);
        btn.classList.toggle("text-gray-300", i >= nota);
      });
      const btnEnviarFeedback = document.getElementById("btn-enviar-feedback");
      if (btnEnviarFeedback) btnEnviarFeedback.disabled = false;
    }
    async enviarFeedback() {
      if (!this.notaSelecionada || !this.geracaoId) return;
      try {
        const comentarioEl = document.getElementById("feedback-comentario");
        const comentario = comentarioEl?.value || "";
        await fetch(`${API_URL}/feedback`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${this.getToken()}`
          },
          body: JSON.stringify({
            geracao_id: this.geracaoId,
            avaliacao: this.notaSelecionada >= 4 ? "correto" : this.notaSelecionada >= 2 ? "parcial" : "incorreto",
            nota: this.notaSelecionada,
            comentario
          })
        });
        this.showToast("Obrigado pelo feedback!", "success");
        this.fecharModal("modal-feedback");
        this.resetar();
      } catch {
        this.showToast("Erro ao enviar feedback", "error");
      }
    }
    // Utilitarios
    mostrarLoading(mensagem) {
      this.setProgressoMensagem(mensagem);
      this.abrirModal("modal-progresso");
    }
    esconderLoading() {
      this.fecharModal("modal-progresso");
    }
    mostrarErro(mensagem) {
      const erroMensagem = document.getElementById("erro-mensagem");
      const toastErro = document.getElementById("toast-erro");
      if (erroMensagem) erroMensagem.textContent = mensagem;
      if (toastErro) {
        toastErro.classList.remove("hidden");
        setTimeout(() => {
          toastErro.classList.add("hidden");
        }, 8e3);
      }
    }
    esconderErro() {
      const toastErro = document.getElementById("toast-erro");
      if (toastErro) toastErro.classList.add("hidden");
    }
    abrirModal(id) {
      document.getElementById(id)?.classList.remove("hidden");
    }
    fecharModal(id) {
      document.getElementById(id)?.classList.add("hidden");
    }
    showToast(message, type = "info") {
      const toast = document.getElementById("toast");
      const icon = document.getElementById("toast-icon");
      const msg = document.getElementById("toast-message");
      if (!toast || !icon || !msg) return;
      msg.textContent = message;
      icon.className = "fas " + (type === "success" ? "fa-check-circle text-green-400" : type === "error" ? "fa-exclamation-circle text-red-400" : type === "warning" ? "fa-exclamation-triangle text-yellow-400" : "fa-info-circle text-blue-400");
      toast.classList.remove("hidden");
      setTimeout(() => toast.classList.add("hidden"), 3e3);
    }
    resetar() {
      const inputCnj = document.getElementById("numero-cnj");
      if (inputCnj) inputCnj.value = "";
      this.numeroCNJ = null;
      this.geracaoId = null;
      this.relatorioMarkdown = null;
      this.notaSelecionada = null;
    }
  };
  function toggleHistorico() {
    const painel = document.getElementById("painel-historico");
    if (painel) {
      painel.classList.toggle("hidden");
      painel.classList.toggle("translate-x-full");
    }
  }
  function fecharModalEditor() {
    app.fecharModal("modal-editor");
    if (app.isNovaGeracao) {
      app.abrirModal("modal-feedback");
    }
  }
  var app = new RelatorioCumprimentoApp();
  window.app = app;
  window.toggleHistorico = toggleHistorico;
  window.fecharModalEditor = fecharModalEditor;
})();
//# sourceMappingURL=app.js.map
