# sistemas/classificador_documentos/services.py
"""
Serviço principal de classificação de documentos.

Orquestra o pipeline completo:
1. Download de documentos do TJ-MS (ou recebe upload)
2. Extração de texto (com OCR fallback)
3. Normalização com text_normalizer
4. Classificação via OpenRouter
5. Persistência de resultados

Autor: LAB/PGE-MS
"""

import logging
import asyncio
import time
import traceback
from datetime import datetime
from typing import Optional, List, Dict, Any, AsyncGenerator, Tuple, Set
from sqlalchemy.orm import Session

from utils.timezone import get_utc_now

from .models import (
    ProjetoClassificacao,
    CodigoDocumentoProjeto,
    ExecucaoClassificacao,
    ResultadoClassificacao,
    PromptClassificacao,
    LogClassificacaoIA,
    StatusExecucao,
    StatusArquivo,
    FonteDocumento,
    DocumentoParaClassificar,
    ResultadoClassificacaoDTO
)
from .services_openrouter import get_openrouter_service, OpenRouterResult
from .services_extraction import get_text_extractor, ExtractionResult
from .services_tjms import get_tjms_service, DocumentoTJMS

logger = logging.getLogger(__name__)


class ClassificadorService:
    """
    Serviço principal para classificação de documentos.

    Uso:
        service = ClassificadorService(db)

        # Executar projeto
        async for evento in service.executar_projeto(projeto_id):
            print(evento)

        # Classificar documento avulso
        resultado = await service.classificar_documento(pdf_bytes, "doc.pdf", prompt)
    """

    def __init__(self, db: Session):
        self.db = db
        self.openrouter = get_openrouter_service()
        self.extractor = get_text_extractor()
        self.tjms = get_tjms_service()

    # ============================================
    # CRUD de Prompts
    # ============================================

    def listar_prompts(self, apenas_ativos: bool = True) -> List[PromptClassificacao]:
        """Lista prompts de classificação"""
        query = self.db.query(PromptClassificacao)
        if apenas_ativos:
            query = query.filter(PromptClassificacao.ativo == True)
        return query.order_by(PromptClassificacao.nome).all()

    def obter_prompt(self, prompt_id: int) -> Optional[PromptClassificacao]:
        """Obtém um prompt por ID"""
        return self.db.query(PromptClassificacao).filter(
            PromptClassificacao.id == prompt_id
        ).first()

    def criar_prompt(self, nome: str, conteudo: str, descricao: str = None, usuario_id: int = None, codigos_documento: str = None) -> PromptClassificacao:
        """Cria um novo prompt"""
        prompt = PromptClassificacao(
            nome=nome,
            conteudo=conteudo,
            descricao=descricao,
            usuario_id=usuario_id,
            codigos_documento=codigos_documento
        )
        self.db.add(prompt)
        self.db.commit()
        self.db.refresh(prompt)
        return prompt

    def atualizar_prompt(self, prompt_id: int, **kwargs) -> Optional[PromptClassificacao]:
        """Atualiza um prompt existente"""
        prompt = self.obter_prompt(prompt_id)
        if not prompt:
            return None

        for key, value in kwargs.items():
            if hasattr(prompt, key) and value is not None:
                setattr(prompt, key, value)

        self.db.commit()
        self.db.refresh(prompt)
        return prompt

    # ============================================
    # CRUD de Projetos
    # ============================================

    def listar_projetos(self, usuario_id: int, apenas_ativos: bool = True) -> List[ProjetoClassificacao]:
        """Lista projetos do usuário"""
        query = self.db.query(ProjetoClassificacao).filter(
            ProjetoClassificacao.usuario_id == usuario_id
        )
        if apenas_ativos:
            query = query.filter(ProjetoClassificacao.ativo == True)
        return query.order_by(ProjetoClassificacao.criado_em.desc()).all()

    def obter_projeto(self, projeto_id: int) -> Optional[ProjetoClassificacao]:
        """Obtém um projeto por ID"""
        return self.db.query(ProjetoClassificacao).filter(
            ProjetoClassificacao.id == projeto_id
        ).first()

    def criar_projeto(
        self,
        nome: str,
        usuario_id: int,
        descricao: str = None,
        prompt_id: int = None,
        modelo: str = "google/gemini-2.5-flash-lite",
        **kwargs
    ) -> ProjetoClassificacao:
        """Cria um novo projeto"""
        projeto = ProjetoClassificacao(
            nome=nome,
            usuario_id=usuario_id,
            descricao=descricao,
            prompt_id=prompt_id,
            modelo=modelo,
            **kwargs
        )
        self.db.add(projeto)
        self.db.commit()
        self.db.refresh(projeto)
        return projeto

    def atualizar_projeto(self, projeto_id: int, **kwargs) -> Optional[ProjetoClassificacao]:
        """Atualiza um projeto existente"""
        projeto = self.obter_projeto(projeto_id)
        if not projeto:
            return None

        for key, value in kwargs.items():
            if hasattr(projeto, key) and value is not None:
                setattr(projeto, key, value)

        self.db.commit()
        self.db.refresh(projeto)
        return projeto

    # ============================================
    # CRUD de Códigos de Documentos
    # ============================================

    def adicionar_codigos(
        self,
        projeto_id: int,
        codigos: List[str],
        numero_processo: str = None,
        fonte: str = "tjms"
    ) -> List[CodigoDocumentoProjeto]:
        """Adiciona códigos de documentos a um projeto"""
        novos_codigos = []
        for codigo in codigos:
            codigo_limpo = codigo.strip()
            if not codigo_limpo:
                continue

            # Verifica se já existe
            existente = self.db.query(CodigoDocumentoProjeto).filter(
                CodigoDocumentoProjeto.projeto_id == projeto_id,
                CodigoDocumentoProjeto.codigo == codigo_limpo
            ).first()

            if not existente:
                novo = CodigoDocumentoProjeto(
                    projeto_id=projeto_id,
                    codigo=codigo_limpo,
                    numero_processo=numero_processo,
                    fonte=fonte
                )
                self.db.add(novo)
                novos_codigos.append(novo)

        self.db.commit()
        return novos_codigos

    def remover_codigo(self, codigo_id: int) -> bool:
        """Remove um código de documento"""
        codigo = self.db.query(CodigoDocumentoProjeto).filter(
            CodigoDocumentoProjeto.id == codigo_id
        ).first()
        if codigo:
            self.db.delete(codigo)
            self.db.commit()
            return True
        return False

    def listar_codigos(self, projeto_id: int, apenas_ativos: bool = True) -> List[CodigoDocumentoProjeto]:
        """Lista códigos de um projeto"""
        query = self.db.query(CodigoDocumentoProjeto).filter(
            CodigoDocumentoProjeto.projeto_id == projeto_id
        )
        if apenas_ativos:
            query = query.filter(CodigoDocumentoProjeto.ativo == True)
        return query.all()

    # ============================================
    # Execução de Classificação
    # ============================================

    async def executar_projeto(
        self,
        projeto_id: int,
        usuario_id: int,
        codigos_ids: List[int] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Executa classificação de um projeto com streaming de eventos.

        Args:
            projeto_id: ID do projeto
            usuario_id: ID do usuário
            codigos_ids: IDs específicos de códigos (None = todos ativos)

        Yields:
            Eventos de progresso: {tipo, mensagem, dados}
        """
        logger.info(f"[CLASSIFICADOR] Iniciando execução do projeto {projeto_id} para usuário {usuario_id}")

        projeto = self.obter_projeto(projeto_id)
        if not projeto:
            logger.warning(f"[CLASSIFICADOR] Projeto {projeto_id} não encontrado")
            yield {"tipo": "erro", "mensagem": "Projeto não encontrado"}
            return

        logger.info(f"[CLASSIFICADOR] Projeto encontrado: {projeto.nome}, modelo: {projeto.modelo}")

        # Carrega prompt
        prompt_texto = None
        if projeto.prompt_id:
            prompt = self.obter_prompt(projeto.prompt_id)
            if prompt:
                prompt_texto = prompt.conteudo
                logger.info(f"[CLASSIFICADOR] Prompt carregado: {prompt.nome} ({len(prompt_texto)} chars)")

        if not prompt_texto:
            logger.warning(f"[CLASSIFICADOR] Prompt não configurado para projeto {projeto_id}")
            yield {"tipo": "erro", "mensagem": "Prompt não configurado para o projeto"}
            return

        # Carrega códigos
        if codigos_ids:
            codigos = self.db.query(CodigoDocumentoProjeto).filter(
                CodigoDocumentoProjeto.id.in_(codigos_ids),
                CodigoDocumentoProjeto.projeto_id == projeto_id
            ).all()
            logger.info(f"[CLASSIFICADOR] Carregados {len(codigos)} códigos específicos (de {len(codigos_ids)} solicitados)")
        else:
            codigos = self.listar_codigos(projeto_id)
            logger.info(f"[CLASSIFICADOR] Carregados {len(codigos)} códigos do projeto")

        if not codigos:
            logger.warning(f"[CLASSIFICADOR] Nenhum código encontrado para projeto {projeto_id}")
            yield {"tipo": "erro", "mensagem": "Nenhum código de documento configurado. Faça upload de arquivos primeiro."}
            return

        # Cria execução (ADR-0010: com campos de heartbeat e rota)
        agora = get_utc_now()
        execucao = ExecucaoClassificacao(
            projeto_id=projeto_id,
            status=StatusExecucao.EM_ANDAMENTO.value,
            total_arquivos=len(codigos),
            modelo_usado=projeto.modelo,
            prompt_usado=prompt_texto,
            config_usada={
                "modo_processamento": projeto.modo_processamento,
                "posicao_chunk": projeto.posicao_chunk,
                "tamanho_chunk": projeto.tamanho_chunk,
                "max_concurrent": projeto.max_concurrent
            },
            usuario_id=usuario_id,
            iniciado_em=agora,
            ultimo_heartbeat=agora,  # ADR-0010: heartbeat inicial
            rota_origem="/classificador/"  # ADR-0010: rota de origem
        )
        self.db.add(execucao)
        self.db.commit()

        yield {
            "tipo": "inicio",
            "mensagem": f"Iniciando classificação de {len(codigos)} documentos",
            "execucao_id": execucao.id,
            "rota_origem": execucao.rota_origem
        }

        # Processa documentos com paralelismo controlado
        semaforo = asyncio.Semaphore(projeto.max_concurrent)
        tarefas = []

        for codigo in codigos:
            tarefa = self._processar_codigo_com_semaforo(
                semaforo,
                execucao,
                codigo,
                projeto,
                prompt_texto
            )
            tarefas.append(tarefa)

        # Processa e emite eventos de progresso
        for tarefa in asyncio.as_completed(tarefas):
            resultado = await tarefa

            execucao.arquivos_processados += 1
            if resultado.sucesso:
                execucao.arquivos_sucesso += 1
            else:
                execucao.arquivos_erro += 1

            # ADR-0010: Atualiza heartbeat a cada documento processado
            execucao.ultimo_heartbeat = get_utc_now()
            execucao.ultimo_codigo_processado = resultado.codigo_documento

            self.db.commit()

            yield {
                "tipo": "progresso",
                "mensagem": f"Processado: {resultado.codigo_documento}",
                "processados": execucao.arquivos_processados,
                "total": execucao.total_arquivos,
                "sucesso": resultado.sucesso,
                "resultado": resultado.to_dict(),
                "ultimo_heartbeat": execucao.ultimo_heartbeat.isoformat()
            }

        # Finaliza execução
        execucao.status = StatusExecucao.CONCLUIDO.value
        execucao.finalizado_em = get_utc_now()
        self.db.commit()

        yield {
            "tipo": "concluido",
            "mensagem": f"Classificação concluída: {execucao.arquivos_sucesso} sucessos, {execucao.arquivos_erro} erros",
            "execucao_id": execucao.id,
            "sucesso": execucao.arquivos_sucesso,
            "erros": execucao.arquivos_erro,
            "rota_origem": execucao.rota_origem
        }

    async def _processar_codigo_com_semaforo(
        self,
        semaforo: asyncio.Semaphore,
        execucao: ExecucaoClassificacao,
        codigo: CodigoDocumentoProjeto,
        projeto: ProjetoClassificacao,
        prompt_texto: str
    ) -> ResultadoClassificacaoDTO:
        """Processa um código com controle de concorrência"""
        async with semaforo:
            return await self._processar_codigo(
                execucao, codigo, projeto, prompt_texto
            )

    async def _processar_codigo(
        self,
        execucao: ExecucaoClassificacao,
        codigo: CodigoDocumentoProjeto,
        projeto: ProjetoClassificacao,
        prompt_texto: str
    ) -> ResultadoClassificacaoDTO:
        """Processa um único código de documento"""
        logger.info(f"[CLASSIFICADOR] Processando código {codigo.codigo} (fonte: {codigo.fonte}, arquivo: {codigo.arquivo_nome})")

        # Cria registro de resultado
        resultado_db = ResultadoClassificacao(
            execucao_id=execucao.id,
            codigo_documento=codigo.codigo,
            numero_processo=codigo.numero_processo,
            status=StatusArquivo.PROCESSANDO.value,
            fonte=codigo.fonte
        )
        self.db.add(resultado_db)
        self.db.commit()

        try:
            texto_documento = None
            via_ocr = False

            # 1. Obtém texto do documento baseado na fonte
            if codigo.fonte == FonteDocumento.UPLOAD.value:
                logger.debug(f"[CLASSIFICADOR] Fonte UPLOAD - usando texto extraído cached")
                # Upload: usa texto já extraído no momento do upload
                if codigo.texto_extraido and len(codigo.texto_extraido.strip()) >= 50:
                    texto_documento = codigo.texto_extraido
                    via_ocr = False  # Já foi extraído antes
                else:
                    resultado_db.status = StatusArquivo.ERRO.value
                    resultado_db.erro_mensagem = "Texto do upload vazio ou muito curto"
                    self.db.commit()
                    return ResultadoClassificacaoDTO(
                        codigo_documento=codigo.codigo,
                        nome_arquivo=codigo.arquivo_nome,
                        erro="Texto do upload vazio ou muito curto"
                    )

            elif codigo.fonte == FonteDocumento.TJMS.value and codigo.numero_processo:
                # TJ-MS: baixa documento e extrai texto
                doc = await self.tjms.baixar_documento(
                    codigo.numero_processo,
                    codigo.codigo
                )
                if doc.erro:
                    resultado_db.status = StatusArquivo.ERRO.value
                    resultado_db.erro_mensagem = f"Erro ao baixar: {doc.erro}"
                    self.db.commit()
                    return ResultadoClassificacaoDTO(
                        codigo_documento=codigo.codigo,
                        numero_processo=codigo.numero_processo,
                        erro=doc.erro
                    )

                # Extrai texto do PDF baixado
                extraction = self.extractor.extrair_texto(doc.conteudo_bytes)

                if not extraction.texto or len(extraction.texto.strip()) < 50:
                    resultado_db.status = StatusArquivo.ERRO.value
                    resultado_db.erro_mensagem = "Texto extraído vazio ou muito curto"
                    self.db.commit()
                    return ResultadoClassificacaoDTO(
                        codigo_documento=codigo.codigo,
                        numero_processo=codigo.numero_processo,
                        erro="Texto extraído vazio"
                    )

                texto_documento = extraction.texto
                via_ocr = extraction.via_ocr
                resultado_db.tokens_extraidos = extraction.tokens_total

            else:
                # Fonte desconhecida ou sem dados necessários
                resultado_db.status = StatusArquivo.ERRO.value
                resultado_db.erro_mensagem = "Documento sem fonte válida ou processo associado"
                self.db.commit()
                return ResultadoClassificacaoDTO(
                    codigo_documento=codigo.codigo,
                    erro="Documento sem fonte válida"
                )

            resultado_db.texto_extraido_via = "ocr" if via_ocr else "pdf"

            # 2. Extrai chunk para classificação
            if projeto.modo_processamento == "chunk":
                chunk = self.extractor.extrair_chunk(
                    texto_documento,
                    projeto.tamanho_chunk,
                    projeto.posicao_chunk
                )
            else:
                chunk = texto_documento

            resultado_db.chunk_usado = chunk[:5000]  # Limita para auditoria

            # 4. Classifica com OpenRouter
            openrouter_result = await self.openrouter.classificar(
                modelo=projeto.modelo,
                prompt_sistema=prompt_texto,
                nome_arquivo=codigo.codigo,
                chunk_texto=chunk
            )

            # Log da chamada IA
            log_ia = LogClassificacaoIA(
                resultado_id=resultado_db.id,
                execucao_id=execucao.id,
                codigo_documento=codigo.codigo,
                prompt_enviado=prompt_texto[:2000],
                chunk_enviado=chunk[:2000],
                resposta_bruta=openrouter_result.resposta_bruta,
                resposta_parseada=openrouter_result.resultado,
                modelo_usado=projeto.modelo,
                tokens_entrada=openrouter_result.tokens_entrada,
                tokens_saida=openrouter_result.tokens_saida,
                tempo_ms=openrouter_result.tempo_ms,
                sucesso=openrouter_result.sucesso,
                erro=openrouter_result.erro
            )
            self.db.add(log_ia)

            # Estima tokens (aproximadamente 4 chars por token)
            tokens_estimados = resultado_db.tokens_extraidos or len(texto_documento) // 4

            if not openrouter_result.sucesso:
                resultado_db.status = StatusArquivo.ERRO.value
                resultado_db.erro_mensagem = openrouter_result.erro
                self.db.commit()
                return ResultadoClassificacaoDTO(
                    codigo_documento=codigo.codigo,
                    numero_processo=codigo.numero_processo,
                    nome_arquivo=codigo.arquivo_nome,
                    erro=openrouter_result.erro,
                    texto_via="ocr" if via_ocr else "pdf",
                    tokens_usados=tokens_estimados
                )

            # 3. Salva resultado
            resultado = openrouter_result.resultado
            resultado_db.categoria = resultado.get("categoria")
            resultado_db.subcategoria = resultado.get("subcategoria")
            resultado_db.confianca = resultado.get("confianca")
            resultado_db.justificativa = resultado.get("justificativa_breve")
            resultado_db.resultado_json = resultado
            resultado_db.status = StatusArquivo.CONCLUIDO.value
            resultado_db.processado_em = get_utc_now()

            self.db.commit()

            return ResultadoClassificacaoDTO(
                codigo_documento=codigo.codigo,
                numero_processo=codigo.numero_processo,
                nome_arquivo=codigo.arquivo_nome,
                categoria=resultado.get("categoria"),
                subcategoria=resultado.get("subcategoria"),
                confianca=resultado.get("confianca"),
                justificativa=resultado.get("justificativa_breve"),
                sucesso=True,
                texto_via="ocr" if via_ocr else "pdf",
                tokens_usados=tokens_estimados,
                chunk_usado=chunk[:500],
                resultado_completo=resultado
            )

        except Exception as e:
            logger.exception(f"Erro ao processar código {codigo.codigo}: {e}")
            resultado_db.status = StatusArquivo.ERRO.value
            resultado_db.erro_mensagem = str(e)
            # ADR-0010: Captura stack trace para debug
            resultado_db.erro_stack = traceback.format_exc()
            resultado_db.ultimo_erro_em = get_utc_now()
            resultado_db.tentativas = (resultado_db.tentativas or 0) + 1
            self.db.commit()

            return ResultadoClassificacaoDTO(
                codigo_documento=codigo.codigo,
                numero_processo=codigo.numero_processo,
                erro=str(e)
            )

    async def classificar_documento_avulso(
        self,
        pdf_bytes: bytes,
        nome_arquivo: str,
        prompt_texto: str,
        modelo: str = "google/gemini-2.5-flash-lite",
        modo_processamento: str = "chunk",
        posicao_chunk: str = "fim",
        tamanho_chunk: int = 512
    ) -> ResultadoClassificacaoDTO:
        """
        Classifica um documento avulso (upload manual).

        Args:
            pdf_bytes: Bytes do PDF
            nome_arquivo: Nome do arquivo
            prompt_texto: Texto do prompt
            modelo: Modelo LLM
            modo_processamento: "chunk" ou "completo"
            posicao_chunk: "inicio" ou "fim"
            tamanho_chunk: Número de tokens do chunk

        Returns:
            ResultadoClassificacaoDTO
        """
        # Extrai texto
        extraction = self.extractor.extrair_texto(pdf_bytes)

        if not extraction.texto or len(extraction.texto.strip()) < 50:
            return ResultadoClassificacaoDTO(
                codigo_documento=nome_arquivo,
                erro="Texto extraído vazio ou muito curto"
            )

        # Extrai chunk
        if modo_processamento == "chunk":
            chunk = self.extractor.extrair_chunk(
                extraction.texto,
                tamanho_chunk,
                posicao_chunk
            )
        else:
            chunk = extraction.texto

        # Classifica
        result = await self.openrouter.classificar(
            modelo=modelo,
            prompt_sistema=prompt_texto,
            nome_arquivo=nome_arquivo,
            chunk_texto=chunk
        )

        if not result.sucesso:
            return ResultadoClassificacaoDTO(
                codigo_documento=nome_arquivo,
                erro=result.erro,
                texto_via="ocr" if extraction.via_ocr else "pdf",
                tokens_usados=extraction.tokens_total
            )

        return ResultadoClassificacaoDTO(
            codigo_documento=nome_arquivo,
            categoria=result.resultado.get("categoria"),
            subcategoria=result.resultado.get("subcategoria"),
            confianca=result.resultado.get("confianca"),
            justificativa=result.resultado.get("justificativa_breve"),
            sucesso=True,
            texto_via="ocr" if extraction.via_ocr else "pdf",
            tokens_usados=extraction.tokens_total,
            chunk_usado=chunk[:500],
            resultado_completo=result.resultado
        )

    # ============================================
    # Consultas
    # ============================================

    def listar_execucoes(self, projeto_id: int) -> List[ExecucaoClassificacao]:
        """Lista execuções de um projeto"""
        return self.db.query(ExecucaoClassificacao).filter(
            ExecucaoClassificacao.projeto_id == projeto_id
        ).order_by(ExecucaoClassificacao.criado_em.desc()).all()

    def obter_execucao(self, execucao_id: int) -> Optional[ExecucaoClassificacao]:
        """Obtém uma execução por ID"""
        return self.db.query(ExecucaoClassificacao).filter(
            ExecucaoClassificacao.id == execucao_id
        ).first()

    def listar_resultados(
        self,
        execucao_id: int,
        categoria: str = None,
        confianca: str = None,
        apenas_erros: bool = False
    ) -> List[ResultadoClassificacao]:
        """Lista resultados de uma execução com filtros"""
        query = self.db.query(ResultadoClassificacao).filter(
            ResultadoClassificacao.execucao_id == execucao_id
        )

        if categoria:
            query = query.filter(ResultadoClassificacao.categoria == categoria)
        if confianca:
            query = query.filter(ResultadoClassificacao.confianca == confianca)
        if apenas_erros:
            query = query.filter(ResultadoClassificacao.status == StatusArquivo.ERRO.value)

        return query.order_by(ResultadoClassificacao.criado_em).all()

    # ============================================
    # Retomada e Recuperação (ADR-0010)
    # ============================================

    async def retomar_execucao(
        self,
        execucao_id: int,
        usuario_id: int
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Retoma uma execução travada ou com erro de onde parou.

        Comportamento idempotente:
        - Pula documentos já processados com sucesso
        - Reprocessa apenas documentos pendentes ou com erro

        Args:
            execucao_id: ID da execução a retomar
            usuario_id: ID do usuário

        Yields:
            Eventos de progresso: {tipo, mensagem, dados}
        """
        logger.info(f"[CLASSIFICADOR] Retomando execução {execucao_id}")

        execucao = self.obter_execucao(execucao_id)
        if not execucao:
            yield {"tipo": "erro", "mensagem": "Execução não encontrada"}
            return

        # Valida se pode retomar
        if execucao.status not in [StatusExecucao.TRAVADO.value, StatusExecucao.ERRO.value]:
            yield {
                "tipo": "erro",
                "mensagem": f"Execução com status '{execucao.status}' não pode ser retomada. "
                           f"Apenas execuções TRAVADO ou ERRO podem ser retomadas."
            }
            return

        if not execucao.pode_retomar:
            yield {
                "tipo": "erro",
                "mensagem": f"Limite de retomadas atingido ({execucao.tentativas_retry}/{execucao.max_retries})"
            }
            return

        projeto = self.obter_projeto(execucao.projeto_id)
        if not projeto:
            yield {"tipo": "erro", "mensagem": "Projeto não encontrado"}
            return

        # Carrega prompt
        prompt_texto = execucao.prompt_usado
        if not prompt_texto:
            yield {"tipo": "erro", "mensagem": "Prompt da execução não encontrado"}
            return

        # Identifica códigos que precisam ser processados
        codigos_processados_sucesso: Set[str] = set()
        resultados_existentes = self.db.query(ResultadoClassificacao).filter(
            ResultadoClassificacao.execucao_id == execucao_id
        ).all()

        for r in resultados_existentes:
            if r.status == StatusArquivo.CONCLUIDO.value:
                codigos_processados_sucesso.add(r.codigo_documento)

        # Busca códigos do projeto que ainda precisam ser processados
        todos_codigos = self.listar_codigos(projeto.id)
        codigos_a_processar = [
            c for c in todos_codigos
            if c.codigo not in codigos_processados_sucesso
        ]

        if not codigos_a_processar:
            yield {
                "tipo": "concluido",
                "mensagem": "Todos os documentos já foram processados com sucesso",
                "execucao_id": execucao_id
            }
            return

        # Atualiza execução para retomada
        agora = get_utc_now()
        execucao.status = StatusExecucao.EM_ANDAMENTO.value
        execucao.tentativas_retry += 1
        execucao.ultimo_heartbeat = agora
        execucao.erro_mensagem = None
        self.db.commit()

        yield {
            "tipo": "retomada",
            "mensagem": f"Retomando execução: {len(codigos_a_processar)} documentos pendentes "
                       f"(tentativa {execucao.tentativas_retry}/{execucao.max_retries})",
            "execucao_id": execucao.id,
            "ja_processados": len(codigos_processados_sucesso),
            "pendentes": len(codigos_a_processar),
            "rota_origem": execucao.rota_origem
        }

        # Processa documentos pendentes
        semaforo = asyncio.Semaphore(projeto.max_concurrent)
        tarefas = []

        for codigo in codigos_a_processar:
            tarefa = self._processar_codigo_com_semaforo(
                semaforo,
                execucao,
                codigo,
                projeto,
                prompt_texto
            )
            tarefas.append(tarefa)

        # Processa e emite eventos de progresso
        for tarefa in asyncio.as_completed(tarefas):
            resultado = await tarefa

            execucao.arquivos_processados += 1
            if resultado.sucesso:
                execucao.arquivos_sucesso += 1
            else:
                execucao.arquivos_erro += 1

            # Atualiza heartbeat
            execucao.ultimo_heartbeat = get_utc_now()
            execucao.ultimo_codigo_processado = resultado.codigo_documento

            self.db.commit()

            yield {
                "tipo": "progresso",
                "mensagem": f"Processado: {resultado.codigo_documento}",
                "processados": execucao.arquivos_processados,
                "total": execucao.total_arquivos,
                "sucesso": resultado.sucesso,
                "resultado": resultado.to_dict(),
                "ultimo_heartbeat": execucao.ultimo_heartbeat.isoformat()
            }

        # Finaliza execução
        execucao.status = StatusExecucao.CONCLUIDO.value
        execucao.finalizado_em = get_utc_now()
        self.db.commit()

        yield {
            "tipo": "concluido",
            "mensagem": f"Retomada concluída: {execucao.arquivos_sucesso} sucessos, {execucao.arquivos_erro} erros",
            "execucao_id": execucao.id,
            "sucesso": execucao.arquivos_sucesso,
            "erros": execucao.arquivos_erro,
            "rota_origem": execucao.rota_origem
        }

    async def reprocessar_erros(
        self,
        execucao_id: int,
        usuario_id: int
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Reprocessa apenas os documentos que tiveram erro.

        Args:
            execucao_id: ID da execução
            usuario_id: ID do usuário

        Yields:
            Eventos de progresso: {tipo, mensagem, dados}
        """
        logger.info(f"[CLASSIFICADOR] Reprocessando erros da execução {execucao_id}")

        execucao = self.obter_execucao(execucao_id)
        if not execucao:
            yield {"tipo": "erro", "mensagem": "Execução não encontrada"}
            return

        projeto = self.obter_projeto(execucao.projeto_id)
        if not projeto:
            yield {"tipo": "erro", "mensagem": "Projeto não encontrado"}
            return

        prompt_texto = execucao.prompt_usado
        if not prompt_texto:
            yield {"tipo": "erro", "mensagem": "Prompt da execução não encontrado"}
            return

        # Busca resultados com erro que podem ser reprocessados
        resultados_erro = self.db.query(ResultadoClassificacao).filter(
            ResultadoClassificacao.execucao_id == execucao_id,
            ResultadoClassificacao.status == StatusArquivo.ERRO.value
        ).all()

        # Filtra apenas os que podem ser reprocessados (< max tentativas)
        codigos_reprocessar = []
        for r in resultados_erro:
            if r.pode_reprocessar:
                # Busca o código correspondente
                codigo = self.db.query(CodigoDocumentoProjeto).filter(
                    CodigoDocumentoProjeto.projeto_id == projeto.id,
                    CodigoDocumentoProjeto.codigo == r.codigo_documento
                ).first()
                if codigo:
                    codigos_reprocessar.append((codigo, r))

        if not codigos_reprocessar:
            yield {
                "tipo": "erro",
                "mensagem": "Nenhum documento com erro pode ser reprocessado "
                           "(limite de tentativas atingido ou todos processados com sucesso)"
            }
            return

        # Atualiza execução
        agora = get_utc_now()
        execucao.status = StatusExecucao.EM_ANDAMENTO.value
        execucao.ultimo_heartbeat = agora
        self.db.commit()

        yield {
            "tipo": "reprocessamento",
            "mensagem": f"Reprocessando {len(codigos_reprocessar)} documentos com erro",
            "execucao_id": execucao.id,
            "total_erros": len(resultados_erro),
            "reprocessaveis": len(codigos_reprocessar),
            "rota_origem": execucao.rota_origem
        }

        # Reseta status dos resultados que serão reprocessados
        for codigo, resultado_antigo in codigos_reprocessar:
            resultado_antigo.status = StatusArquivo.PENDENTE.value
            self.db.commit()

        # Processa documentos
        semaforo = asyncio.Semaphore(projeto.max_concurrent)
        sucesso_count = 0
        erro_count = 0

        for codigo, resultado_antigo in codigos_reprocessar:
            async with semaforo:
                resultado = await self._processar_codigo(
                    execucao, codigo, projeto, prompt_texto
                )

                if resultado.sucesso:
                    sucesso_count += 1
                    execucao.arquivos_erro -= 1
                    execucao.arquivos_sucesso += 1
                else:
                    erro_count += 1

                execucao.ultimo_heartbeat = get_utc_now()
                execucao.ultimo_codigo_processado = resultado.codigo_documento
                self.db.commit()

                yield {
                    "tipo": "progresso",
                    "mensagem": f"Reprocessado: {resultado.codigo_documento}",
                    "sucesso": resultado.sucesso,
                    "resultado": resultado.to_dict(),
                    "ultimo_heartbeat": execucao.ultimo_heartbeat.isoformat()
                }

        # Finaliza
        execucao.status = StatusExecucao.CONCLUIDO.value
        execucao.finalizado_em = get_utc_now()
        self.db.commit()

        yield {
            "tipo": "concluido",
            "mensagem": f"Reprocessamento concluído: {sucesso_count} recuperados, {erro_count} ainda com erro",
            "execucao_id": execucao.id,
            "recuperados": sucesso_count,
            "ainda_com_erro": erro_count,
            "rota_origem": execucao.rota_origem
        }
