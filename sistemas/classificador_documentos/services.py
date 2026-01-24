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
from datetime import datetime
from typing import Optional, List, Dict, Any, AsyncGenerator, Tuple
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

    def criar_prompt(self, nome: str, conteudo: str, descricao: str = None, usuario_id: int = None) -> PromptClassificacao:
        """Cria um novo prompt"""
        prompt = PromptClassificacao(
            nome=nome,
            conteudo=conteudo,
            descricao=descricao,
            usuario_id=usuario_id
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
        projeto = self.obter_projeto(projeto_id)
        if not projeto:
            yield {"tipo": "erro", "mensagem": "Projeto não encontrado"}
            return

        # Carrega prompt
        prompt_texto = None
        if projeto.prompt_id:
            prompt = self.obter_prompt(projeto.prompt_id)
            if prompt:
                prompt_texto = prompt.conteudo

        if not prompt_texto:
            yield {"tipo": "erro", "mensagem": "Prompt não configurado para o projeto"}
            return

        # Carrega códigos
        if codigos_ids:
            codigos = self.db.query(CodigoDocumentoProjeto).filter(
                CodigoDocumentoProjeto.id.in_(codigos_ids),
                CodigoDocumentoProjeto.projeto_id == projeto_id
            ).all()
        else:
            codigos = self.listar_codigos(projeto_id)

        if not codigos:
            yield {"tipo": "erro", "mensagem": "Nenhum código de documento configurado"}
            return

        # Cria execução
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
            iniciado_em=get_utc_now()
        )
        self.db.add(execucao)
        self.db.commit()

        yield {
            "tipo": "inicio",
            "mensagem": f"Iniciando classificação de {len(codigos)} documentos",
            "execucao_id": execucao.id
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

            self.db.commit()

            yield {
                "tipo": "progresso",
                "mensagem": f"Processado: {resultado.codigo_documento}",
                "processados": execucao.arquivos_processados,
                "total": execucao.total_arquivos,
                "sucesso": resultado.sucesso,
                "resultado": resultado.to_dict()
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
            "erros": execucao.arquivos_erro
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
            # 1. Baixa documento do TJ-MS
            if codigo.fonte == FonteDocumento.TJMS.value and codigo.numero_processo:
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

                pdf_bytes = doc.conteudo_bytes
            else:
                # Documento não é do TJ-MS ou não tem processo - erro
                resultado_db.status = StatusArquivo.ERRO.value
                resultado_db.erro_mensagem = "Documento sem processo associado"
                self.db.commit()
                return ResultadoClassificacaoDTO(
                    codigo_documento=codigo.codigo,
                    erro="Documento sem processo associado"
                )

            # 2. Extrai texto (com OCR fallback)
            extraction = self.extractor.extrair_texto(pdf_bytes)

            if not extraction.texto or len(extraction.texto.strip()) < 50:
                resultado_db.status = StatusArquivo.ERRO.value
                resultado_db.erro_mensagem = "Texto extraído vazio ou muito curto"
                self.db.commit()
                return ResultadoClassificacaoDTO(
                    codigo_documento=codigo.codigo,
                    numero_processo=codigo.numero_processo,
                    erro="Texto extraído vazio"
                )

            resultado_db.texto_extraido_via = "ocr" if extraction.via_ocr else "pdf"
            resultado_db.tokens_extraidos = extraction.tokens_total

            # 3. Extrai chunk para classificação
            if projeto.modo_processamento == "chunk":
                chunk = self.extractor.extrair_chunk(
                    extraction.texto,
                    projeto.tamanho_chunk,
                    projeto.posicao_chunk
                )
            else:
                chunk = extraction.texto

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

            if not openrouter_result.sucesso:
                resultado_db.status = StatusArquivo.ERRO.value
                resultado_db.erro_mensagem = openrouter_result.erro
                self.db.commit()
                return ResultadoClassificacaoDTO(
                    codigo_documento=codigo.codigo,
                    numero_processo=codigo.numero_processo,
                    erro=openrouter_result.erro,
                    texto_via="ocr" if extraction.via_ocr else "pdf",
                    tokens_usados=extraction.tokens_total
                )

            # 5. Salva resultado
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
                categoria=resultado.get("categoria"),
                subcategoria=resultado.get("subcategoria"),
                confianca=resultado.get("confianca"),
                justificativa=resultado.get("justificativa_breve"),
                sucesso=True,
                texto_via="ocr" if extraction.via_ocr else "pdf",
                tokens_usados=extraction.tokens_total,
                chunk_usado=chunk[:500],
                resultado_completo=resultado
            )

        except Exception as e:
            logger.exception(f"Erro ao processar código {codigo.codigo}: {e}")
            resultado_db.status = StatusArquivo.ERRO.value
            resultado_db.erro_mensagem = str(e)
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
