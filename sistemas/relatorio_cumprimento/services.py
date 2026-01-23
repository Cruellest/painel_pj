# sistemas/relatorio_cumprimento/services.py
"""
Serviço orquestrador para geração de Relatório de Cumprimento de Sentença

Coordena o pipeline de processamento:
1. Consulta dados do processo de cumprimento
2. Identifica o processo principal (conhecimento)
3. Baixa documentos relevantes (petição inicial, sentenças, acórdãos)
4. Localiza informação de trânsito em julgado
5. Organiza e classifica documentos
6. Envia para IA gerar o relatório

Autor: LAB/PGE-MS
"""

import json
import time
from datetime import date, datetime
from typing import Dict, List, Optional, Any, Tuple, AsyncGenerator

from sqlalchemy.orm import Session

from .models import (
    CategoriaDocumento,
    StatusProcessamento,
    DocumentoClassificado,
    DadosProcesso,
    InfoTransitoJulgado,
    ResultadoColeta,
    ResultadoRelatorio,
    GeracaoRelatorioCumprimento,
    LogChamadaIARelatorioCumprimento,
    ResultadoDeteccaoAgravo
)

# Detector de Agravo de Instrumento
from .agravo_detector import (
    detect_and_validate_agravos,
    fetch_all_agravo_documents
)

# Reutiliza componentes existentes do pedido_calculo
from sistemas.pedido_calculo.xml_parser import XMLParser
from sistemas.pedido_calculo.document_downloader import DocumentDownloader

# Serviço de IA centralizado
from services.gemini_service import GeminiService

# Configurações do admin
from admin.models import PromptConfig, ConfiguracaoIA


SISTEMA = "relatorio_cumprimento"


def _get_config(db: Session, chave: str, default: str = None) -> str:
    """Busca configuração do sistema no banco"""
    config = db.query(ConfiguracaoIA).filter(
        ConfiguracaoIA.sistema == SISTEMA,
        ConfiguracaoIA.chave == chave
    ).first()
    return config.valor if config else default


def _get_prompt(db: Session, tipo: str) -> Optional[str]:
    """Busca prompt do sistema no banco"""
    prompt = db.query(PromptConfig).filter(
        PromptConfig.sistema == SISTEMA,
        PromptConfig.tipo == tipo,
        PromptConfig.is_active == True
    ).first()
    return prompt.conteudo if prompt else None


class RelatorioCumprimentoService:
    """
    Serviço principal para geração de Relatório de Cumprimento de Sentença.

    Orquestra todo o pipeline de processamento.
    """

    def __init__(self, db: Session, logger=None):
        """
        Inicializa o serviço.

        Args:
            db: Sessão do banco de dados para buscar configurações
            logger: Logger opcional para debug de chamadas de IA
        """
        self.db = db
        self.logger = logger

        # Carrega configurações do banco
        self.modelo = _get_config(db, "modelo_analise", "gemini-3-flash-preview")
        self.temperatura = float(_get_config(db, "temperatura_analise", "0.2"))
        self.thinking_level = _get_config(db, "thinking_level", "low")

        # Serviço de IA
        self.gemini = GeminiService()

    async def consultar_processo(self, numero_cnj: str) -> Tuple[Dict[str, Any], Optional[str]]:
        """
        Consulta dados do processo no TJ-MS.

        Args:
            numero_cnj: Número CNJ do processo

        Returns:
            Tupla (dados do XML parseados, erro opcional)
        """
        try:
            async with DocumentDownloader() as downloader:
                xml_texto = await downloader.consultar_processo(numero_cnj)

            parser = XMLParser(xml_texto)
            dados_basicos = parser.extrair_dados_basicos()
            movimentos = parser.extrair_movimentos_relevantes()
            documentos_info = parser.identificar_documentos_para_download()

            return {
                "dados_basicos": dados_basicos,
                "movimentos": movimentos,
                "documentos_info": documentos_info,
                "xml_texto": xml_texto
            }, None

        except Exception as e:
            return {}, f"Erro ao consultar processo: {str(e)}"

    async def identificar_processo_principal(
        self,
        xml_texto: str,
        documentos_info: Any
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Identifica o número do processo principal (conhecimento).

        Usa a mesma lógica do sistema de pedido de cálculo.

        Args:
            xml_texto: XML do processo de cumprimento
            documentos_info: Informações de documentos do parser

        Returns:
            Tupla (número do processo principal, erro opcional)
        """
        try:
            # Se já é cumprimento autônomo, o número está no documentos_info
            if documentos_info.is_cumprimento_autonomo and documentos_info.numero_processo_origem:
                return documentos_info.numero_processo_origem, None

            # Se não é cumprimento autônomo, o processo de cumprimento é no mesmo processo
            # Nesse caso, retorna None (os documentos estão no mesmo processo)
            return None, None

        except Exception as e:
            return None, f"Erro ao identificar processo principal: {str(e)}"

    async def baixar_documentos(
        self,
        numero_cumprimento: str,
        numero_principal: Optional[str],
        documentos_info: Any
    ) -> Tuple[List[DocumentoClassificado], Optional[str]]:
        """
        Baixa e classifica documentos do processo.

        Args:
            numero_cumprimento: Número do processo de cumprimento
            numero_principal: Número do processo principal (se diferente)
            documentos_info: Informações de documentos do parser

        Returns:
            Tupla (lista de documentos classificados, erro opcional)
        """
        documentos = []

        try:
            async with DocumentDownloader() as downloader:
                # Coleta IDs para baixar do cumprimento
                ids_cumprimento = []
                if documentos_info.id_peticao_inicial:
                    ids_cumprimento.append(documentos_info.id_peticao_inicial)

                # Baixa documentos do cumprimento
                if ids_cumprimento:
                    textos_cumprimento = await downloader.baixar_e_extrair_textos(
                        numero_cumprimento, ids_cumprimento
                    )

                    # Processa petição inicial
                    if documentos_info.id_peticao_inicial and documentos_info.id_peticao_inicial in textos_cumprimento:
                        doc = DocumentoClassificado(
                            id_documento=documentos_info.id_peticao_inicial,
                            categoria=CategoriaDocumento.PETICAO_INICIAL_CUMPRIMENTO,
                            nome_original="Petição Inicial",
                            nome_padronizado="01_peticao_inicial_cumprimento.pdf",
                            processo_origem="cumprimento",
                            conteudo_texto=textos_cumprimento[documentos_info.id_peticao_inicial]
                        )
                        documentos.append(doc)

                # 2. Prepara IDs de sentenças, acórdãos e decisões
                processo_docs = numero_principal or numero_cumprimento
                ids_sentencas = list(documentos_info.sentencas) if documentos_info.sentencas else []
                ids_acordaos = list(documentos_info.acordaos) if documentos_info.acordaos else []
                ids_decisoes = list(documentos_info.decisoes) if hasattr(documentos_info, 'decisoes') and documentos_info.decisoes else []
                id_transito = documentos_info.certidao_transito if hasattr(documentos_info, 'certidao_transito') else None

                # Se tem processo principal, busca documentos de lá
                docs_principal = None
                if numero_principal:
                    xml_principal = await downloader.consultar_processo(numero_principal)
                    parser_principal = XMLParser(xml_principal)
                    docs_principal = parser_principal.identificar_documentos_para_download(
                        forcar_busca_sentencas=True
                    )
                    ids_sentencas = list(docs_principal.sentencas) if docs_principal.sentencas else []
                    ids_acordaos = list(docs_principal.acordaos) if docs_principal.acordaos else []
                    ids_decisoes = list(docs_principal.decisoes) if hasattr(docs_principal, 'decisoes') and docs_principal.decisoes else []
                    id_transito = docs_principal.certidao_transito if hasattr(docs_principal, 'certidao_transito') else None

                # Coleta todos os IDs do processo principal/cumprimento
                ids_principais = []
                ids_principais.extend(ids_sentencas)
                ids_principais.extend(ids_acordaos)
                ids_principais.extend(ids_decisoes)
                if id_transito:
                    ids_principais.append(id_transito)

                # Baixa todos em paralelo
                if ids_principais:
                    textos_principais = await downloader.baixar_e_extrair_textos(
                        processo_docs, ids_principais
                    )

                    # Processa sentenças
                    for i, id_sentenca in enumerate(ids_sentencas, 1):
                        if id_sentenca in textos_principais:
                            doc = DocumentoClassificado(
                                id_documento=id_sentenca,
                                categoria=CategoriaDocumento.SENTENCA,
                                nome_original=f"Sentença {i}",
                                nome_padronizado=f"02_sentenca_{i:02d}.pdf",
                                processo_origem="principal" if numero_principal else "cumprimento",
                                conteudo_texto=textos_principais[id_sentenca]
                            )
                            documentos.append(doc)

                    # Processa acórdãos
                    for i, id_acordao in enumerate(ids_acordaos, 1):
                        if id_acordao in textos_principais:
                            doc = DocumentoClassificado(
                                id_documento=id_acordao,
                                categoria=CategoriaDocumento.ACORDAO,
                                nome_original=f"Acórdão {i}",
                                nome_padronizado=f"03_acordao_{i:02d}.pdf",
                                processo_origem="principal" if numero_principal else "cumprimento",
                                conteudo_texto=textos_principais[id_acordao]
                            )
                            documentos.append(doc)

                    # Processa decisões interlocutórias
                    for i, id_decisao in enumerate(ids_decisoes, 1):
                        if id_decisao in textos_principais:
                            doc = DocumentoClassificado(
                                id_documento=id_decisao,
                                categoria=CategoriaDocumento.DECISAO,
                                nome_original=f"Decisão {i}",
                                nome_padronizado=f"04_decisao_{i:02d}.pdf",
                                processo_origem="principal" if numero_principal else "cumprimento",
                                conteudo_texto=textos_principais[id_decisao]
                            )
                            documentos.append(doc)

                    # Processa certidão de trânsito
                    if id_transito and id_transito in textos_principais:
                        doc = DocumentoClassificado(
                            id_documento=id_transito,
                            categoria=CategoriaDocumento.CERTIDAO_TRANSITO,
                            nome_original="Certidão de Trânsito em Julgado",
                            nome_padronizado="05_certidao_transito.pdf",
                            processo_origem="principal" if numero_principal else "cumprimento",
                            conteudo_texto=textos_principais[id_transito]
                        )
                        documentos.append(doc)

            return documentos, None

        except Exception as e:
            import traceback
            traceback.print_exc()
            return documentos, f"Erro ao baixar documentos: {str(e)}"

    def localizar_transito_julgado(
        self,
        movimentos: Any,
        documentos: List[DocumentoClassificado]
    ) -> InfoTransitoJulgado:
        """
        Localiza informação de trânsito em julgado.

        Args:
            movimentos: Movimentos relevantes extraídos do XML
            documentos: Documentos baixados

        Returns:
            Informação sobre trânsito em julgado
        """
        info = InfoTransitoJulgado()

        # 1. Verifica movimentos
        if movimentos and movimentos.transito_julgado:
            info.localizado = True
            info.data_transito = movimentos.transito_julgado
            info.fonte = "movimento"
            return info

        # 2. Verifica se tem certidão de trânsito
        for doc in documentos:
            if doc.categoria == CategoriaDocumento.CERTIDAO_TRANSITO:
                info.localizado = True
                info.fonte = "certidao"
                info.id_documento = doc.id_documento
                # A data será extraída pela IA
                return info

        # Não localizado
        info.observacao = "Não foi possível identificar informação de trânsito em julgado"
        return info

    async def detectar_agravos_processo_origem(
        self,
        xml_processo_origem: str,
        request_id: Optional[str] = None
    ) -> Tuple[ResultadoDeteccaoAgravo, List[DocumentoClassificado]]:
        """
        Detecta e baixa documentos de Agravos de Instrumento do processo de origem.

        Esta verificação é realizada apenas quando:
        - O cumprimento de sentença é autônomo
        - O processo de origem foi corretamente identificado

        O fluxo:
        1. Extrai candidatos a agravo do XML do processo de origem
        2. Para cada candidato, baixa o XML e valida comparando partes
        3. Para agravos validados, baixa decisões e acórdãos

        Args:
            xml_processo_origem: XML completo do processo de origem (conhecimento)
            request_id: ID da requisição para logs estruturados

        Returns:
            Tupla (ResultadoDeteccaoAgravo, Lista de DocumentoClassificado dos agravos)
        """
        import logging
        logger = logging.getLogger(__name__)
        log_prefix = f"[{request_id}] " if request_id else ""

        documentos_agravos = []

        try:
            # 1. Detecta e valida agravos
            logger.info(f"{log_prefix}Iniciando detecção de Agravo de Instrumento no processo de origem")

            resultado_deteccao = await detect_and_validate_agravos(
                xml_processo_origem,
                request_id
            )

            if resultado_deteccao.erro:
                logger.error(f"{log_prefix}Erro na detecção de agravos: {resultado_deteccao.erro}")
                return resultado_deteccao, []

            # Log estruturado
            logger.info(
                f"{log_prefix}AGRAVO_SUMMARY | "
                f"processo_origem=true | "
                f"candidatos={len(resultado_deteccao.candidatos_detectados)} | "
                f"validados={len(resultado_deteccao.agravos_validados)} | "
                f"rejeitados={len(resultado_deteccao.agravos_rejeitados)}"
            )

            # 2. Se não há agravos validados, retorna
            if not resultado_deteccao.agravos_validados:
                logger.info(f"{log_prefix}Nenhum agravo validado - prosseguindo sem documentos de agravo")
                return resultado_deteccao, []

            # 3. Baixa documentos dos agravos validados
            logger.info(
                f"{log_prefix}Baixando documentos de {len(resultado_deteccao.agravos_validados)} agravo(s) validado(s)"
            )

            documentos_agravos = await fetch_all_agravo_documents(
                resultado_deteccao.agravos_validados,
                request_id
            )

            # Log final
            qtd_decisoes = sum(1 for d in documentos_agravos if d.categoria == CategoriaDocumento.DECISAO_AGRAVO)
            qtd_acordaos = sum(1 for d in documentos_agravos if d.categoria == CategoriaDocumento.ACORDAO_AGRAVO)

            logger.info(
                f"{log_prefix}AGRAVO_DOCUMENTS | "
                f"total={len(documentos_agravos)} | "
                f"decisoes={qtd_decisoes} | "
                f"acordaos={qtd_acordaos}"
            )

            return resultado_deteccao, documentos_agravos

        except Exception as e:
            import traceback
            traceback.print_exc()
            logger.error(f"{log_prefix}Erro ao detectar agravos: {e}")
            resultado_deteccao = ResultadoDeteccaoAgravo(erro=str(e))
            return resultado_deteccao, []

    async def gerar_relatorio(
        self,
        dados_cumprimento: DadosProcesso,
        dados_principal: Optional[DadosProcesso],
        documentos: List[DocumentoClassificado],
        transito_julgado: InfoTransitoJulgado,
        geracao_id: Optional[int] = None
    ) -> Tuple[str, Optional[str]]:
        """
        Gera o relatório usando IA.

        Args:
            dados_cumprimento: Dados do processo de cumprimento
            dados_principal: Dados do processo principal (se diferente)
            documentos: Documentos baixados e classificados
            transito_julgado: Info sobre trânsito em julgado
            geracao_id: ID da geração para logging

        Returns:
            Tupla (markdown do relatório, erro opcional)
        """
        try:
            # Busca prompt do banco
            prompt_template = _get_prompt(self.db, "geracao_relatorio")
            if not prompt_template:
                return "", "Prompt de geração não configurado. Configure em /admin/prompts-config"

            # Monta contexto dos documentos
            docs_texto = ""
            for doc in documentos:
                docs_texto += f"\n\n### {doc.categoria.value.upper()}: {doc.nome_original}\n"
                docs_texto += f"Processo de origem: {doc.processo_origem}\n"
                docs_texto += f"---\n{doc.conteudo_texto or '[Conteúdo não disponível]'}\n"

            # Monta dados básicos
            dados_json = json.dumps({
                "processo_cumprimento": dados_cumprimento.to_dict(),
                "processo_principal": dados_principal.to_dict() if dados_principal else None,
                "transito_julgado": transito_julgado.to_dict(),
                "data_atual": date.today().strftime("%d/%m/%Y")
            }, ensure_ascii=False, indent=2)

            # Formata prompt
            prompt = prompt_template.format(
                dados_json=dados_json,
                documentos=docs_texto,
                data_atual=date.today().strftime("%d/%m/%Y")
            )

            # Log da chamada
            inicio = time.time()
            log = None
            if geracao_id:
                log = LogChamadaIARelatorioCumprimento(
                    geracao_id=geracao_id,
                    etapa="geracao_relatorio",
                    descricao="Geração do relatório inicial",
                    prompt_enviado=prompt[:5000],  # Trunca para log
                    documentos_enviados=[d.to_dict() for d in documentos],
                    modelo_usado=self.modelo,
                    temperatura_usada=str(self.temperatura),
                    thinking_level_usado=self.thinking_level
                )
                self.db.add(log)
                self.db.commit()

            # Chama IA
            resposta = await self.gemini.generate(
                prompt=prompt,
                model=self.modelo,
                temperature=self.temperatura,
                thinking_level=self.thinking_level
            )

            tempo_ms = int((time.time() - inicio) * 1000)

            # Atualiza log
            if log:
                log.resposta_ia = resposta[:10000] if resposta else None
                log.tempo_ms = tempo_ms
                log.sucesso = bool(resposta)
                self.db.commit()

            if not resposta:
                return "", "IA não retornou resposta"

            return resposta, None

        except Exception as e:
            import traceback
            traceback.print_exc()
            if log:
                log.sucesso = False
                log.erro = str(e)
                self.db.commit()
            return "", f"Erro ao gerar relatório: {str(e)}"

    async def gerar_relatorio_stream(
        self,
        dados_cumprimento: DadosProcesso,
        dados_principal: Optional[DadosProcesso],
        documentos: List[DocumentoClassificado],
        transito_julgado: InfoTransitoJulgado,
        geracao_id: Optional[int] = None,
        request_id: Optional[str] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Versão streaming da geração de relatório.

        Args:
            dados_cumprimento: Dados do processo de cumprimento
            dados_principal: Dados do processo principal (se diferente)
            documentos: Documentos baixados e classificados
            transito_julgado: Info sobre trânsito em julgado
            geracao_id: ID da geração para logging
            request_id: ID da requisição para correlação de logs

        Yields:
            dict com tipo='chunk'|'done'|'error'
        """
        import logging
        logger = logging.getLogger(__name__)
        log_prefix = f"[{request_id}] " if request_id else ""
        inicio = time.time()
        log = None

        try:
            logger.info(
                f"{log_prefix}RELATORIO_STREAM_START | "
                f"geracao_id={geracao_id} | "
                f"processo={dados_cumprimento.numero_processo} | "
                f"modelo={self.modelo} | "
                f"docs={len(documentos)}"
            )

            # Busca prompt do banco
            prompt_template = _get_prompt(self.db, "geracao_relatorio")
            if not prompt_template:
                logger.error(f"{log_prefix}Prompt de geração não configurado")
                yield {"tipo": "error", "error": "Prompt de geração não configurado. Configure em /admin/prompts-config"}
                return

            # Monta contexto dos documentos
            docs_texto = ""
            for doc in documentos:
                docs_texto += f"\n\n### {doc.categoria.value.upper()}: {doc.nome_original}\n"
                docs_texto += f"Processo de origem: {doc.processo_origem}\n"
                docs_texto += f"---\n{doc.conteudo_texto or '[Conteúdo não disponível]'}\n"

            # Monta dados básicos
            dados_json = json.dumps({
                "processo_cumprimento": dados_cumprimento.to_dict(),
                "processo_principal": dados_principal.to_dict() if dados_principal else None,
                "transito_julgado": transito_julgado.to_dict(),
                "data_atual": date.today().strftime("%d/%m/%Y")
            }, ensure_ascii=False, indent=2)

            # Formata prompt
            prompt = prompt_template.format(
                dados_json=dados_json,
                documentos=docs_texto,
                data_atual=date.today().strftime("%d/%m/%Y")
            )

            # Cria log de chamada IA no banco (CRÍTICO para /admin/performance)
            if geracao_id:
                log = LogChamadaIARelatorioCumprimento(
                    geracao_id=geracao_id,
                    etapa="geracao_relatorio_stream",
                    descricao="Geração do relatório via streaming SSE",
                    prompt_enviado=prompt[:5000],  # Trunca para log
                    documentos_enviados=[d.to_dict() for d in documentos],
                    modelo_usado=self.modelo,
                    temperatura_usada=str(self.temperatura),
                    thinking_level_usado=self.thinking_level
                )
                self.db.add(log)
                self.db.commit()
                logger.info(f"{log_prefix}Log de chamada IA criado: id={log.id}")

            # Streaming com contexto para logging correto
            conteudo_completo = ""
            context = {
                "sistema": SISTEMA,
                "modulo": "geracao_relatorio_stream",
                "request_id": request_id
            }

            logger.info(
                f"{log_prefix}GEMINI_STREAM_CALL | "
                f"modelo={self.modelo} | "
                f"prompt_len={len(prompt)} | "
                f"temperatura={self.temperatura} | "
                f"thinking_level={self.thinking_level}"
            )

            chunks_recebidos = 0
            async for chunk in self.gemini.generate_stream(
                prompt=prompt,
                model=self.modelo,
                temperature=self.temperatura,
                thinking_level=self.thinking_level,
                context=context
            ):
                chunks_recebidos += 1
                conteudo_completo += chunk
                yield {"tipo": "chunk", "chunk": chunk}

                # Log a cada 10 chunks para não poluir
                if chunks_recebidos % 10 == 0:
                    logger.info(f"{log_prefix}GEMINI_CHUNKS | count={chunks_recebidos} | total_len={len(conteudo_completo)}")

            logger.info(
                f"{log_prefix}GEMINI_STREAM_DONE | "
                f"chunks_total={chunks_recebidos} | "
                f"conteudo_len={len(conteudo_completo)}"
            )

            tempo_ms = int((time.time() - inicio) * 1000)

            # Valida que conteúdo não está vazio
            conteudo_limpo = (conteudo_completo or "").strip()
            if not conteudo_limpo:
                logger.error(
                    f"{log_prefix}RELATORIO_STREAM_EMPTY | "
                    f"geracao_id={geracao_id} | "
                    f"tempo_ms={tempo_ms} | "
                    f"conteudo_raw_len={len(conteudo_completo or '')}"
                )
                if log:
                    log.sucesso = False
                    log.erro = "Conteúdo gerado vazio"
                    log.tempo_ms = tempo_ms
                    self.db.commit()
                yield {"tipo": "error", "error": "A IA retornou conteúdo vazio. Tente novamente ou verifique os documentos do processo."}
                return

            # Atualiza log com sucesso
            if log:
                log.resposta_ia = conteudo_completo[:10000] if conteudo_completo else None
                log.tempo_ms = tempo_ms
                log.sucesso = True
                self.db.commit()

            logger.info(
                f"{log_prefix}RELATORIO_STREAM_DONE | "
                f"geracao_id={geracao_id} | "
                f"tempo_ms={tempo_ms} | "
                f"conteudo_len={len(conteudo_completo)}"
            )

            yield {"tipo": "done", "conteudo": conteudo_completo}

        except Exception as e:
            import traceback
            traceback.print_exc()
            tempo_ms = int((time.time() - inicio) * 1000)
            logger.error(
                f"{log_prefix}RELATORIO_STREAM_ERROR | "
                f"geracao_id={geracao_id} | "
                f"tempo_ms={tempo_ms} | "
                f"error={str(e)}"
            )
            if log:
                log.sucesso = False
                log.erro = str(e)
                log.tempo_ms = tempo_ms
                self.db.commit()
            yield {"tipo": "error", "error": str(e)}

    async def processar_completo(
        self,
        numero_cumprimento: str,
        callback_progresso: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Executa pipeline completo de processamento.

        Args:
            numero_cumprimento: Número CNJ do processo de cumprimento
            callback_progresso: Função opcional para reportar progresso

        Returns:
            Dict com resultado completo
        """
        resultado = {
            "sucesso": False,
            "erro": None,
            "dados_cumprimento": None,
            "dados_principal": None,
            "numero_principal": None,
            "documentos": [],
            "transito_julgado": None,
            "relatorio_markdown": None,
            "geracao_id": None
        }

        inicio = time.time()

        try:
            # Cria registro de geração
            geracao = GeracaoRelatorioCumprimento(
                numero_cumprimento=numero_cumprimento,
                status=StatusProcessamento.INICIADO.value,
                modelo_usado=self.modelo,
                temperatura_usada=str(self.temperatura),
                thinking_level_usado=self.thinking_level
            )
            self.db.add(geracao)
            self.db.commit()
            resultado["geracao_id"] = geracao.id

            # Etapa 1: Consulta processo de cumprimento
            if callback_progresso:
                callback_progresso(1, "Consultando processo de cumprimento...")

            geracao.status = StatusProcessamento.BAIXANDO_DOCUMENTOS.value
            self.db.commit()

            dados_consulta, erro = await self.consultar_processo(numero_cumprimento)
            if erro:
                geracao.status = StatusProcessamento.ERRO.value
                geracao.erro_mensagem = erro
                self.db.commit()
                resultado["erro"] = erro
                return resultado

            dados_basicos = dados_consulta["dados_basicos"]
            movimentos = dados_consulta["movimentos"]
            documentos_info = dados_consulta["documentos_info"]

            dados_cumprimento = DadosProcesso(
                numero_processo=numero_cumprimento,
                numero_processo_formatado=dados_basicos.numero_processo,
                autor=dados_basicos.autor,
                cpf_cnpj_autor=dados_basicos.cpf_autor,
                comarca=dados_basicos.comarca,
                vara=dados_basicos.vara,
                data_ajuizamento=dados_basicos.data_ajuizamento,
                valor_causa=dados_basicos.valor_causa
            )
            resultado["dados_cumprimento"] = dados_cumprimento.to_dict()

            geracao.numero_cumprimento_formatado = dados_basicos.numero_processo
            geracao.dados_processo_cumprimento = dados_cumprimento.to_dict()
            self.db.commit()

            # Etapa 2: Identifica processo principal
            if callback_progresso:
                callback_progresso(2, "Identificando processo principal...")

            numero_principal, erro = await self.identificar_processo_principal(
                dados_consulta["xml_texto"],
                documentos_info
            )

            if numero_principal:
                resultado["numero_principal"] = numero_principal
                geracao.numero_principal = numero_principal

                # Consulta dados do processo principal
                dados_principal_consulta, _ = await self.consultar_processo(numero_principal)
                if dados_principal_consulta:
                    dados_basicos_principal = dados_principal_consulta["dados_basicos"]
                    movimentos = dados_principal_consulta["movimentos"]  # Usa movimentos do principal

                    dados_principal = DadosProcesso(
                        numero_processo=numero_principal,
                        numero_processo_formatado=dados_basicos_principal.numero_processo,
                        autor=dados_basicos_principal.autor,
                        cpf_cnpj_autor=dados_basicos_principal.cpf_autor,
                        comarca=dados_basicos_principal.comarca,
                        vara=dados_basicos_principal.vara,
                        data_ajuizamento=dados_basicos_principal.data_ajuizamento,
                        valor_causa=dados_basicos_principal.valor_causa
                    )
                    resultado["dados_principal"] = dados_principal.to_dict()
                    geracao.numero_principal_formatado = dados_basicos_principal.numero_processo
                    geracao.dados_processo_principal = dados_principal.to_dict()
            else:
                dados_principal = None

            self.db.commit()

            # Etapa 3: Baixa documentos
            if callback_progresso:
                callback_progresso(3, "Baixando documentos do TJ-MS...")

            documentos, erro = await self.baixar_documentos(
                numero_cumprimento,
                numero_principal,
                documentos_info
            )

            if erro and not documentos:
                geracao.status = StatusProcessamento.ERRO.value
                geracao.erro_mensagem = erro
                self.db.commit()
                resultado["erro"] = erro
                return resultado

            resultado["documentos"] = [d.to_dict() for d in documentos]
            geracao.documentos_baixados = resultado["documentos"]
            self.db.commit()

            # Etapa 4: Localiza trânsito em julgado
            if callback_progresso:
                callback_progresso(4, "Localizando trânsito em julgado...")

            transito_julgado = self.localizar_transito_julgado(movimentos, documentos)
            resultado["transito_julgado"] = transito_julgado.to_dict()

            geracao.transito_julgado_localizado = transito_julgado.localizado
            if transito_julgado.data_transito:
                geracao.data_transito_julgado = transito_julgado.data_transito.strftime("%d/%m/%Y")
            self.db.commit()

            # Etapa 5: Gera relatório
            if callback_progresso:
                callback_progresso(5, "Gerando relatório com IA...")

            geracao.status = StatusProcessamento.GERANDO_RELATORIO.value
            self.db.commit()

            relatorio, erro = await self.gerar_relatorio(
                dados_cumprimento,
                dados_principal,
                documentos,
                transito_julgado,
                geracao_id=geracao.id
            )

            if erro:
                geracao.status = StatusProcessamento.ERRO.value
                geracao.erro_mensagem = erro
                self.db.commit()
                resultado["erro"] = erro
                return resultado

            resultado["relatorio_markdown"] = relatorio
            resultado["sucesso"] = True

            # Finaliza
            tempo_total = int(time.time() - inicio)
            geracao.conteudo_gerado = relatorio
            geracao.status = StatusProcessamento.CONCLUIDO.value
            geracao.tempo_processamento = tempo_total
            geracao.dados_basicos = {
                "cumprimento": dados_cumprimento.to_dict(),
                "principal": dados_principal.to_dict() if dados_principal else None
            }
            self.db.commit()

            return resultado

        except Exception as e:
            import traceback
            traceback.print_exc()
            resultado["erro"] = f"Erro no processamento: {str(e)}"
            if "geracao" in locals():
                geracao.status = StatusProcessamento.ERRO.value
                geracao.erro_mensagem = str(e)
                self.db.commit()
            return resultado

    async def editar_relatorio(
        self,
        geracao_id: int,
        mensagem_usuario: str
    ) -> Tuple[str, Optional[str]]:
        """
        Edita o relatório via chat com o usuário.

        Args:
            geracao_id: ID da geração a editar
            mensagem_usuario: Mensagem do usuário com a alteração desejada

        Returns:
            Tupla (novo markdown, erro opcional)
        """
        try:
            geracao = self.db.query(GeracaoRelatorioCumprimento).filter(
                GeracaoRelatorioCumprimento.id == geracao_id
            ).first()

            if not geracao:
                return "", "Geração não encontrada"

            # Busca prompt de edição
            prompt_template = _get_prompt(self.db, "edicao_relatorio")
            if not prompt_template:
                return "", "Prompt de edição não configurado"

            # Formata prompt
            prompt = prompt_template.format(
                mensagem_usuario=mensagem_usuario,
                relatorio_markdown=geracao.conteudo_gerado,
                dados_processo=json.dumps(geracao.dados_basicos, ensure_ascii=False)
            )

            # Chama IA
            modelo_edicao = _get_config(self.db, "modelo_edicao", self.modelo)
            resposta = await self.gemini.generate(
                prompt=prompt,
                model=modelo_edicao,
                temperature=0.3
            )

            if not resposta:
                return "", "IA não retornou resposta"

            # Atualiza geração
            geracao.conteudo_gerado = resposta

            # Atualiza histórico de chat
            historico = geracao.historico_chat or []
            historico.append({
                "tipo": "usuario",
                "mensagem": mensagem_usuario,
                "timestamp": datetime.now().isoformat()
            })
            historico.append({
                "tipo": "assistente",
                "mensagem": "Relatório atualizado conforme solicitado.",
                "timestamp": datetime.now().isoformat()
            })
            geracao.historico_chat = historico
            self.db.commit()

            return resposta, None

        except Exception as e:
            return "", f"Erro ao editar: {str(e)}"
