# sistemas/prestacao_contas/services.py
"""
Orquestrador do Pipeline de Análise de Prestação de Contas

Coordena as 5 etapas do pipeline:
1. Extração do extrato da subconta (Playwright scrapper)
2. Consulta XML do processo (SOAP TJ-MS)
3. Identificação da petição de prestação de contas
4. Download de documentos anexos
5. Análise por IA

Autor: LAB/PGE-MS
"""

import asyncio
import logging
import os
import aiohttp
from datetime import datetime
from typing import Optional, AsyncGenerator, Dict, Any, List

from sqlalchemy.orm import Session

from sistemas.prestacao_contas.models import GeracaoAnalise, FeedbackPrestacao
from sistemas.prestacao_contas.schemas import EventoSSE, ResultadoAnalise as ResultadoAnaliseSchema
from sistemas.prestacao_contas.scrapper_subconta import extrair_extrato_subconta, StatusProcessamento
from sistemas.prestacao_contas.xml_parser import XMLParserPrestacao, parse_xml_processo, DocumentoProcesso
from sistemas.prestacao_contas.identificador_peticoes import (
    IdentificadorPeticoes,
    TipoDocumento,
    ResultadoIdentificacao,
)
from sistemas.prestacao_contas.agente_analise import AgenteAnalise, DadosAnalise, ResultadoAnalise
from sistemas.prestacao_contas.ia_logger import IALogger, create_logger

# Importa funções do pedido_calculo para reutilizar download de documentos
from sistemas.pedido_calculo.document_downloader import (
    consultar_processo_async,
    baixar_documentos_async,
    extrair_texto_pdf,
)

logger = logging.getLogger(__name__)


# =====================================================
# FUNÇÕES DE LOG FORMATADO
# =====================================================

def log_etapa(etapa: int, nome: str):
    """Log de início de etapa"""
    logger.info(f"\n{'='*60}")
    logger.info(f"📌 ETAPA {etapa}: {nome}")
    logger.info(f"{'='*60}")

def log_info(msg: str):
    """Log informativo"""
    logger.info(f"   ℹ️  {msg}")

def log_sucesso(msg: str):
    """Log de sucesso"""
    logger.info(f"   ✅ {msg}")

def log_aviso(msg: str):
    """Log de aviso"""
    logger.warning(f"   ⚠️  {msg}")

def log_erro(msg: str):
    """Log de erro"""
    logger.error(f"   ❌ {msg}")

def log_ia(msg: str):
    """Log específico de IA"""
    logger.info(f"   🤖 {msg}")


def converter_pdf_para_imagens(pdf_bytes: bytes, max_paginas: int = 10) -> List[str]:
    """
    Converte páginas de um PDF em imagens base64.

    Args:
        pdf_bytes: Bytes do PDF
        max_paginas: Máximo de páginas a converter

    Returns:
        Lista de imagens em base64 (formato data:image/jpeg;base64,...)
    """
    import base64
    import fitz  # PyMuPDF

    imagens = []
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            num_paginas = min(len(doc), max_paginas)

            for i in range(num_paginas):
                page = doc[i]
                # Renderiza página como imagem (zoom 2x para melhor qualidade)
                mat = fitz.Matrix(2, 2)
                pix = page.get_pixmap(matrix=mat)

                # Converte para JPEG base64
                img_bytes = pix.tobytes("jpeg", 85)
                img_base64 = base64.b64encode(img_bytes).decode('utf-8')
                imagens.append(f"data:image/jpeg;base64,{img_base64}")

    except Exception as e:
        logger.error(f"Erro ao converter PDF para imagens: {e}")

    return imagens


# =====================================================
# CONFIGURAÇÕES
# =====================================================

def _get_config(db: Session, chave: str, default: str) -> str:
    """Obtém configuração do banco de dados"""
    try:
        from admin.models import ConfiguracaoIA
        config = db.query(ConfiguracaoIA).filter(
            ConfiguracaoIA.sistema == "prestacao_contas",
            ConfiguracaoIA.chave == chave
        ).first()
        return config.valor if config else default
    except:
        return default


def _get_config_float(db: Session, chave: str, default: float) -> float:
    """Obtém configuração numérica do banco de dados"""
    valor = _get_config(db, chave, str(default))
    try:
        return float(valor)
    except:
        return default


# =====================================================
# ORQUESTRADOR PRINCIPAL
# =====================================================

class OrquestradorPrestacaoContas:
    """
    Orquestra o pipeline completo de análise de prestação de contas.
    """

    def __init__(self, db: Session, usuario_id: Optional[int] = None):
        self.db = db
        self.usuario_id = usuario_id
        self.ia_logger = create_logger()

        # Configurações
        self.modelo_identificacao = _get_config(db, "modelo_identificacao", "gemini-2.0-flash-lite")
        self.modelo_analise = _get_config(db, "modelo_analise", "gemini-3-flash-preview")
        self.temperatura_identificacao = _get_config_float(db, "temperatura_identificacao", 0.1)
        self.temperatura_analise = _get_config_float(db, "temperatura_analise", 0.3)

    async def processar_completo(
        self,
        numero_cnj: str,
        sobrescrever: bool = False
    ) -> AsyncGenerator[EventoSSE, None]:
        """
        Executa o pipeline completo com streaming de eventos.

        Args:
            numero_cnj: Número CNJ do processo
            sobrescrever: Se True, refaz análise mesmo se já existir

        Yields:
            EventoSSE com progresso do processamento
        """
        inicio = datetime.utcnow()

        # Normaliza o número CNJ (remove formatação para consistência)
        numero_cnj_limpo = numero_cnj.replace(".", "").replace("-", "").replace("/", "").strip()

        # Se sobrescrever, deleta registros anteriores do mesmo processo
        if sobrescrever:
            registros_antigos = self.db.query(GeracaoAnalise).filter(
                GeracaoAnalise.numero_cnj == numero_cnj_limpo,
                GeracaoAnalise.usuario_id == self.usuario_id
            ).all()
            for registro in registros_antigos:
                # Deleta feedbacks associados
                self.db.query(FeedbackPrestacao).filter(
                    FeedbackPrestacao.geracao_id == registro.id
                ).delete()
                self.db.delete(registro)
            self.db.commit()
            log_info(f"Deletados {len(registros_antigos)} registros anteriores do processo")

        # Cria registro de geração
        geracao = GeracaoAnalise(
            numero_cnj=numero_cnj_limpo,
            usuario_id=self.usuario_id,
            status="processando",
        )
        self.db.add(geracao)
        self.db.commit()
        self.db.refresh(geracao)

        try:
            logger.info(f"\n{'#'*60}")
            logger.info(f"# PRESTAÇÃO DE CONTAS - {numero_cnj}")
            logger.info(f"{'#'*60}")
            yield EventoSSE(tipo="inicio", mensagem="Iniciando análise de prestação de contas")

            # =====================================================
            # ETAPA 1: EXTRATO DA SUBCONTA
            # =====================================================
            log_etapa(1, "EXTRATO DA SUBCONTA")
            yield EventoSSE(
                tipo="etapa",
                etapa=1,
                etapa_nome="Extrato da Subconta",
                mensagem="Baixando extrato da subconta...",
                progresso=10
            )

            resultado_subconta = await extrair_extrato_subconta(numero_cnj)

            if resultado_subconta.status == StatusProcessamento.OK:
                geracao.extrato_subconta_texto = resultado_subconta.texto_extraido
                # Salva PDF em base64 para visualização
                if resultado_subconta.pdf_bytes:
                    import base64 as b64
                    geracao.extrato_subconta_pdf_base64 = b64.b64encode(resultado_subconta.pdf_bytes).decode('utf-8')
                log_sucesso(f"Extrato baixado ({len(resultado_subconta.texto_extraido or '')} caracteres)")
                yield EventoSSE(
                    tipo="progresso",
                    etapa=1,
                    mensagem="Extrato da subconta baixado com sucesso",
                    progresso=20
                )
            elif resultado_subconta.status == StatusProcessamento.SEM_SUBCONTA:
                log_aviso("Processo não possui subconta registrada")
                yield EventoSSE(
                    tipo="aviso",
                    etapa=1,
                    mensagem="Processo não possui subconta registrada"
                )
            else:
                log_erro(f"Erro ao baixar subconta: {resultado_subconta.erro}")
                yield EventoSSE(
                    tipo="aviso",
                    etapa=1,
                    mensagem=f"Erro ao baixar subconta: {resultado_subconta.erro}"
                )

            # =====================================================
            # ETAPA 2: XML DO PROCESSO
            # =====================================================
            log_etapa(2, "CONSULTA XML TJ-MS")
            yield EventoSSE(
                tipo="etapa",
                etapa=2,
                etapa_nome="Consulta XML TJ-MS",
                mensagem="Consultando dados do processo no TJ-MS...",
                progresso=25
            )

            async with aiohttp.ClientSession() as session:
                xml_response = await consultar_processo_async(session, numero_cnj)

            resultado_xml = parse_xml_processo(xml_response)

            if resultado_xml.erro:
                log_erro(f"Erro ao consultar processo: {resultado_xml.erro}")
                geracao.status = "erro"
                geracao.erro = resultado_xml.erro
                self.db.commit()

                yield EventoSSE(
                    tipo="erro",
                    etapa=2,
                    mensagem=f"Erro ao consultar processo: {resultado_xml.erro}"
                )
                yield EventoSSE(
                    tipo="fim",
                    mensagem="Processamento finalizado com erro"
                )
                return

            geracao.numero_cnj_formatado = resultado_xml.dados_basicos.numero_formatado
            geracao.dados_processo_xml = resultado_xml.to_dict()
            log_sucesso(f"Processo encontrado: {resultado_xml.dados_basicos.autor}")
            log_info(f"Total de documentos no processo: {len(resultado_xml.peticoes_candidatas)} petições candidatas")

            # DEBUG: Mostra as primeiras 15 petições candidatas
            logger.warning(f"{'='*60}")
            logger.warning(f"PETICOES CANDIDATAS (primeiras 15 de {len(resultado_xml.peticoes_candidatas)}):")
            for i, pet in enumerate(resultado_xml.peticoes_candidatas[:15]):
                logger.warning(f"  {i+1}. ID={pet.id} | Codigo={pet.tipo_codigo} | {pet.tipo_descricao[:50] if pet.tipo_descricao else 'Sem desc'}")
            logger.warning(f"{'='*60}")

            yield EventoSSE(
                tipo="progresso",
                etapa=2,
                mensagem=f"Processo encontrado: {resultado_xml.dados_basicos.autor}",
                progresso=35,
                dados={"autor": resultado_xml.dados_basicos.autor}
            )

            # =====================================================
            # ETAPA 3: CLASSIFICAR DOCUMENTOS DO PROCESSO
            # =====================================================
            log_etapa(3, "CLASSIFICAÇÃO DE DOCUMENTOS (LLM)")
            log_ia(f"Modelo: {self.modelo_identificacao} | Temperatura: {self.temperatura_identificacao}")

            # Pega as últimas 10 petições para análise
            MAX_PETICOES = 10
            peticoes_para_analisar = resultado_xml.peticoes_candidatas[:MAX_PETICOES]
            log_info(f"Serão analisadas as últimas {len(peticoes_para_analisar)} petições")

            yield EventoSSE(
                tipo="etapa",
                etapa=3,
                etapa_nome="Classificar Documentos",
                mensagem=f"Analisando {len(peticoes_para_analisar)} petições...",
                progresso=40
            )

            identificador = IdentificadorPeticoes(
                modelo_llm=self.modelo_identificacao,
                temperatura_llm=self.temperatura_identificacao,
                db=self.db
            )

            # Estruturas para armazenar documentos classificados
            documentos_classificados = []  # Lista de {doc, resultado_id, texto, bytes}
            peticao_prestacao = None
            peticao_prestacao_doc = None
            peticoes_relevantes = []  # Petições que irão como texto
            docs_para_baixar_anexos = []  # Documentos que mencionam anexos

            # FASE 1: Baixar documentos sequencialmente
            log_info("Baixando documentos...")
            documentos_baixados = []  # Lista de {doc, bytes, texto}

            # DEBUG: Log dos documentos que serão baixados
            logger.warning(f"DOCUMENTOS A BAIXAR ({len(peticoes_para_analisar)}):")
            for i, p in enumerate(peticoes_para_analisar):
                logger.warning(f"  {i+1}. ID={p.id} | Codigo={p.tipo_codigo} | {p.tipo_descricao[:40] if p.tipo_descricao else 'Sem desc'}")

            async with aiohttp.ClientSession() as session:
                for i, peticao in enumerate(peticoes_para_analisar):
                    yield EventoSSE(
                        tipo="info",
                        etapa=3,
                        mensagem=f"Baixando documento {i+1}/{len(peticoes_para_analisar)}..."
                    )

                    try:
                        xml_docs = await baixar_documentos_async(session, numero_cnj, [peticao.id])

                        import base64
                        import xml.etree.ElementTree as ET
                        root = ET.fromstring(xml_docs)
                        conteudo_bytes = None
                        for elem in root.iter():
                            if 'conteudo' in elem.tag.lower() and elem.text:
                                conteudo_bytes = base64.b64decode(elem.text)
                                break

                        if conteudo_bytes:
                            texto = extrair_texto_pdf(conteudo_bytes)
                            documentos_baixados.append({
                                "doc": peticao,
                                "bytes": conteudo_bytes,
                                "texto": texto
                            })
                            log_info(f"Documento {peticao.id} baixado ({len(texto)} caracteres)")
                    except Exception as e:
                        log_erro(f"Erro ao baixar documento {peticao.id}: {e}")
                        continue

            log_sucesso(f"{len(documentos_baixados)} documentos baixados com sucesso")

            if not documentos_baixados:
                log_erro("Nenhum documento pôde ser baixado")
                geracao.status = "erro"
                geracao.erro = "Nenhum documento pôde ser baixado do processo"
                self.db.commit()

                yield EventoSSE(
                    tipo="erro",
                    etapa=3,
                    mensagem="Nenhum documento pôde ser baixado do processo"
                )
                yield EventoSSE(
                    tipo="fim",
                    mensagem="Processamento finalizado com erro"
                )
                return

            # FASE 2: Classificar todos via LLM (PARALELIZADO)
            log_info(f"Classificando {len(documentos_baixados)} documentos via IA em paralelo...")
            yield EventoSSE(
                tipo="info",
                etapa=3,
                mensagem=f"Classificando {len(documentos_baixados)} documentos via IA em paralelo..."
            )

            async def classificar_documento(doc_info):
                """Classifica um documento via LLM"""
                try:
                    resultado_id = await identificador.identificar_async(doc_info["texto"])
                    return {
                        "doc": doc_info["doc"],
                        "resultado": resultado_id,
                        "texto": doc_info["texto"],
                        "bytes": doc_info["bytes"],
                    }
                except Exception as e:
                    log_erro(f"Erro ao classificar documento {doc_info['doc'].id}: {e}")
                    return None

            # Classifica todos os documentos em paralelo
            tarefas_classificacao = [classificar_documento(d) for d in documentos_baixados]
            resultados_classificacao = await asyncio.gather(*tarefas_classificacao)
            documentos_classificados = [r for r in resultados_classificacao if r is not None]

            # Processa resultados da classificação
            log_info(f"Processando {len(documentos_classificados)} documentos classificados...")
            print(f"[DEBUG] PROCESSANDO {len(documentos_classificados)} DOCS CLASSIFICADOS", flush=True)

            for doc_class in documentos_classificados:
                resultado_id = doc_class["resultado"]
                peticao = doc_class["doc"]

                print(f"[DEBUG] Doc {peticao.id}: {resultado_id.tipo_documento.value}", flush=True)
                log_ia(f"Doc {peticao.id}: {resultado_id.tipo_documento.value} | Confiança: {resultado_id.confianca:.0%}")
                if resultado_id.resumo:
                    log_ia(f"  Resumo: {resultado_id.resumo}")
                if resultado_id.menciona_anexos:
                    log_ia(f"  📎 Menciona anexos: {resultado_id.descricao_anexos}")

                # Processa conforme tipo
                if resultado_id.tipo_documento == TipoDocumento.PETICAO_PRESTACAO:
                    if not peticao_prestacao:  # Pega a primeira
                        peticao_prestacao = doc_class["texto"]
                        peticao_prestacao_doc = peticao
                        log_sucesso(f"✨ PETIÇÃO DE PRESTAÇÃO ENCONTRADA! (ID: {peticao.id})")
                        yield EventoSSE(
                            tipo="info",
                            etapa=3,
                            mensagem=f"Petição de prestação encontrada! (confiança: {resultado_id.confianca:.0%})"
                        )
                    else:
                        # Se já tem uma prestação, adiciona como relevante para não perder
                        peticoes_relevantes.append(doc_class)
                        logger.warning(f">>> ADICIONANDO peticoes_relevantes: PETICAO_PRESTACAO adicional (ID: {peticao.id})")
                        log_info(f"Petição de prestação adicional -> adicionada como relevante")

                elif resultado_id.tipo_documento == TipoDocumento.PETICAO_RELEVANTE:
                    peticoes_relevantes.append(doc_class)
                    logger.warning(f">>> ADICIONANDO peticoes_relevantes: PETICAO_RELEVANTE (ID: {peticao.id}, {resultado_id.resumo})")
                    log_sucesso(f"✅ Petição RELEVANTE: {resultado_id.resumo}")

                elif resultado_id.tipo_documento in [TipoDocumento.NOTA_FISCAL, TipoDocumento.COMPROVANTE]:
                    # Notas fiscais e comprovantes encontrados nas petições (raro, mas possível)
                    log_info(f"Documento fiscal/comprovante identificado: {resultado_id.resumo}")

                elif resultado_id.tipo_documento == TipoDocumento.IRRELEVANTE:
                    log_info(f"❌ Documento IRRELEVANTE: {resultado_id.resumo}")

                # Se menciona anexos, marca para baixar docs do mesmo dia
                if resultado_id.menciona_anexos and peticao.data_juntada:
                    docs_para_baixar_anexos.append(peticao)

            # Verifica se encontrou prestação de contas
            if not peticao_prestacao:
                log_aviso("Petição de prestação de contas não encontrada")
                geracao.status = "erro"
                geracao.erro = "Petição de prestação de contas não encontrada no processo"
                self.db.commit()

                yield EventoSSE(
                    tipo="erro",
                    etapa=3,
                    mensagem="Petição de prestação de contas não encontrada no processo"
                )
                yield EventoSSE(
                    tipo="fim",
                    mensagem="Processamento finalizado com erro"
                )
                return

            # Salva dados da prestação encontrada
            geracao.peticao_prestacao_id = peticao_prestacao_doc.id
            geracao.peticao_prestacao_data = peticao_prestacao_doc.data_juntada
            geracao.peticao_prestacao_texto = peticao_prestacao

            # Log resumo da classificação
            total_relevantes = sum(1 for d in documentos_classificados if d["resultado"].e_relevante)
            total_irrelevantes = sum(1 for d in documentos_classificados if not d["resultado"].e_relevante)
            log_sucesso(f"Classificação concluída: {total_relevantes} relevantes, {total_irrelevantes} descartados")
            log_info(f"  -> Petição de prestação: {'SIM' if peticao_prestacao else 'NÃO'}")

            # DEBUG: Mostrar petições relevantes encontradas
            logger.warning(f"{'='*60}")
            logger.warning(f"DEBUG ETAPA 3: peticoes_relevantes tem {len(peticoes_relevantes)} itens")
            for i, pr in enumerate(peticoes_relevantes, 1):
                logger.warning(f"  {i}. {pr['resultado'].tipo_documento.value}: {pr['resultado'].resumo}")
            logger.warning(f"{'='*60}")

            log_info(f"  -> Petições relevantes para contexto: {len(peticoes_relevantes)}")
            if peticoes_relevantes:
                for i, pr in enumerate(peticoes_relevantes, 1):
                    log_info(f"     {i}. {pr['resultado'].resumo or pr['doc'].id}")

            yield EventoSSE(
                tipo="progresso",
                etapa=3,
                mensagem=f"Classificação: {total_relevantes} relevantes, {total_irrelevantes} descartados",
                progresso=55
            )

            # =====================================================
            # ETAPA 4: BAIXAR DOCUMENTOS ANEXOS
            # =====================================================
            log_etapa(4, "DOWNLOAD DE DOCUMENTOS ANEXOS")
            yield EventoSSE(
                tipo="etapa",
                etapa=4,
                etapa_nome="Baixar Documentos",
                mensagem="Baixando documentos anexos...",
                progresso=60
            )

            documentos_anexos = []  # Imagens (notas fiscais, comprovantes)
            peticoes_contexto = []  # Textos de petições relevantes para contexto

            # Baixa petição inicial
            if resultado_xml.peticao_inicial:
                log_info(f"Baixando petição inicial (ID: {resultado_xml.peticao_inicial.id})...")
                yield EventoSSE(
                    tipo="info",
                    etapa=4,
                    mensagem="Baixando petição inicial..."
                )
                try:
                    async with aiohttp.ClientSession() as session:
                        xml_docs = await baixar_documentos_async(
                            session, numero_cnj, [resultado_xml.peticao_inicial.id]
                        )
                        import base64
                        import xml.etree.ElementTree as ET
                        root = ET.fromstring(xml_docs)
                        for elem in root.iter():
                            if 'conteudo' in elem.tag.lower() and elem.text:
                                conteudo = base64.b64decode(elem.text)
                                geracao.peticao_inicial_id = resultado_xml.peticao_inicial.id
                                geracao.peticao_inicial_texto = extrair_texto_pdf(conteudo)
                                log_sucesso(f"Petição inicial baixada ({len(geracao.peticao_inicial_texto)} caracteres)")
                                break
                except Exception as e:
                    log_erro(f"Erro ao baixar petição inicial: {e}")

            # Adiciona petições relevantes como contexto em texto
            logger.warning(f"{'='*60}")
            logger.warning(f"DEBUG ETAPA 4: peticoes_relevantes = {len(peticoes_relevantes)} itens")
            logger.warning(f"{'='*60}")

            logger.warning(f"Adicionando {len(peticoes_relevantes)} petições relevantes ao contexto...")
            for doc_class in peticoes_relevantes:
                peticoes_contexto.append({
                    "id": doc_class["doc"].id,
                    "tipo": doc_class["resultado"].resumo or "Petição relevante",
                    "texto": doc_class["texto"]
                })
                logger.warning(f"  📄 Contexto adicionado: {doc_class['resultado'].resumo} (ID: {doc_class['doc'].id}, {len(doc_class['texto'])} chars)")

            logger.warning(f"{'='*60}")
            logger.warning(f"TOTAL peticoes_contexto: {len(peticoes_contexto)} itens")
            logger.warning(f"{'='*60}")

            if peticoes_contexto:
                yield EventoSSE(
                    tipo="info",
                    etapa=4,
                    mensagem=f"{len(peticoes_contexto)} petições relevantes adicionadas ao contexto"
                )

            # Prepara parser para buscar documentos anexos
            parser = XMLParserPrestacao(xml_response)
            parser._parse_estrutura()
            parser._extrair_documentos()

            # Coleta IDs de documentos já processados (para não duplicar)
            ids_ja_processados = {d["doc"].id for d in documentos_classificados}

            # Baixa documentos anexos das petições que mencionam anexos
            # Usa intervalo de 2 minutos para encontrar anexos juntados junto com a petição
            for peticao_com_anexos in docs_para_baixar_anexos:
                if peticao_com_anexos.data_juntada:
                    # Busca documentos juntados no mesmo horário (intervalo de 2 minutos)
                    docs_proximos = parser.get_documentos_proximos(
                        peticao_com_anexos.data_juntada,
                        excluir_id=peticao_com_anexos.id,
                        intervalo_minutos=2
                    )

                    # Filtra apenas documentos não processados
                    docs_novos = [d for d in docs_proximos if d.id not in ids_ja_processados]

                    if docs_novos:
                        hora_ref = peticao_com_anexos.data_juntada.strftime('%d/%m/%Y %H:%M')
                        log_info(f"Encontrados {len(docs_novos)} anexos próximos a {hora_ref}")
                        yield EventoSSE(
                            tipo="info",
                            etapa=4,
                            mensagem=f"Baixando {len(docs_novos)} documentos anexos..."
                        )

                        ids_docs = [d.id for d in docs_novos]
                        try:
                            async with aiohttp.ClientSession() as session:
                                xml_docs = await baixar_documentos_async(session, numero_cnj, ids_docs)

                                import base64
                                import xml.etree.ElementTree as ET
                                root = ET.fromstring(xml_docs)

                                # Extrai bytes de cada documento
                                doc_bytes_map = {}
                                for elem in root.iter():
                                    if 'documento' in elem.tag.lower():
                                        doc_id = elem.attrib.get('idDocumento', '')
                                        for child in elem:
                                            if 'conteudo' in child.tag.lower() and child.text:
                                                try:
                                                    doc_bytes_map[doc_id] = base64.b64decode(child.text)
                                                except:
                                                    pass

                                # Todos os anexos são enviados como imagem (sem classificação)
                                for doc in docs_novos:
                                    if doc.id in doc_bytes_map:
                                        doc_bytes = doc_bytes_map[doc.id]
                                        ids_ja_processados.add(doc.id)

                                        # Converte para imagem
                                        imagens = converter_pdf_para_imagens(doc_bytes)
                                        if imagens:
                                            documentos_anexos.append({
                                                "id": doc.id,
                                                "tipo": doc.tipo_descricao or doc.tipo_codigo or "Anexo",
                                                "imagens": imagens
                                            })
                                            log_sucesso(f"Anexo convertido para imagem: {doc.tipo_descricao or doc.tipo_codigo} ({len(imagens)} páginas)")
                                            yield EventoSSE(
                                                tipo="info",
                                                etapa=4,
                                                mensagem=f"Anexo '{doc.tipo_descricao or doc.tipo_codigo}' ({len(imagens)} páginas)"
                                            )

                        except Exception as e:
                            log_erro(f"Erro ao baixar documentos anexos: {e}")

            geracao.documentos_anexos = documentos_anexos

            # Salva petições relevantes para visualização posterior
            geracao.peticoes_relevantes = [
                {
                    "id": pr["doc"].id,
                    "tipo": pr["resultado"].resumo or "Petição relevante",
                    "data": pr["doc"].data_juntada.isoformat() if pr["doc"].data_juntada else None
                }
                for pr in peticoes_relevantes
            ]

            geracao.prompt_identificacao = f"Documentos classificados: {len(documentos_classificados)}, Relevantes: {total_relevantes}"

            # Conta totais
            total_imagens = sum(len(d.get('imagens', [])) for d in documentos_anexos)
            log_sucesso(f"Total: {len(documentos_anexos)} docs como imagem ({total_imagens} páginas), {len(peticoes_contexto)} docs como texto")

            yield EventoSSE(
                tipo="progresso",
                etapa=4,
                mensagem=f"{len(documentos_anexos)} documentos como imagem, {len(peticoes_contexto)} como texto",
                progresso=75
            )

            # =====================================================
            # ETAPA 5: ANÁLISE POR IA
            # =====================================================
            log_etapa(5, "ANÁLISE FINAL (LLM)")
            log_ia(f"Modelo: {self.modelo_analise} | Temperatura: {self.temperatura_analise}")
            yield EventoSSE(
                tipo="etapa",
                etapa=5,
                etapa_nome="Análise IA",
                mensagem="Analisando prestação de contas com IA...",
                progresso=80
            )

            dados_analise = DadosAnalise(
                extrato_subconta=geracao.extrato_subconta_texto or "",
                peticao_inicial=geracao.peticao_inicial_texto or "",
                peticao_prestacao=geracao.peticao_prestacao_texto or "",
                documentos_anexos=documentos_anexos,
                peticoes_contexto=peticoes_contexto,
            )

            # Log dos dados enviados
            log_ia(f"Dados para análise:")
            log_ia(f"  - Extrato subconta: {len(geracao.extrato_subconta_texto or '')} caracteres")
            log_ia(f"  - Petição inicial: {len(geracao.peticao_inicial_texto or '')} caracteres")
            log_ia(f"  - Petição prestação: {len(geracao.peticao_prestacao_texto or '')} caracteres")
            log_ia(f"  - Petições de contexto: {len(peticoes_contexto)} documentos")
            log_ia(f"  - Documentos anexos: {len(documentos_anexos)} docs, {total_imagens} imagens")

            agente = AgenteAnalise(
                modelo=self.modelo_analise,
                temperatura=self.temperatura_analise,
                ia_logger=self.ia_logger,
                db=self.db,
            )

            log_ia("Enviando para análise...")
            resultado = await agente.analisar(dados_analise)

            # Log do resultado
            log_sucesso(f"Análise concluída!")
            log_ia(f"  📋 PARECER: {resultado.parecer.upper()}")
            if resultado.valor_bloqueado:
                log_ia(f"  💰 Valor bloqueado: R$ {resultado.valor_bloqueado:,.2f}")
            if resultado.valor_utilizado:
                log_ia(f"  💸 Valor utilizado: R$ {resultado.valor_utilizado:,.2f}")
            if resultado.valor_devolvido:
                log_ia(f"  🔄 Valor devolvido: R$ {resultado.valor_devolvido:,.2f}")
            if resultado.medicamento_pedido:
                log_ia(f"  💊 Medicamento pedido: {resultado.medicamento_pedido}")
            if resultado.medicamento_comprado:
                log_ia(f"  💊 Medicamento comprado: {resultado.medicamento_comprado}")
            if resultado.irregularidades:
                log_ia(f"  ⚠️  Irregularidades: {len(resultado.irregularidades)}")
            if resultado.perguntas:
                log_ia(f"  ❓ Perguntas ao usuário: {len(resultado.perguntas)}")

            # Salva resultado
            geracao.parecer = resultado.parecer
            geracao.fundamentacao = resultado.fundamentacao
            geracao.irregularidades = resultado.irregularidades
            geracao.perguntas_usuario = resultado.perguntas
            geracao.valor_bloqueado = resultado.valor_bloqueado
            geracao.valor_utilizado = resultado.valor_utilizado
            geracao.valor_devolvido = resultado.valor_devolvido
            geracao.medicamento_pedido = resultado.medicamento_pedido
            geracao.medicamento_comprado = resultado.medicamento_comprado
            geracao.modelo_usado = resultado.modelo_usado
            geracao.prompt_analise = self.ia_logger.logs[-1].prompt_enviado if self.ia_logger.logs else None
            geracao.resposta_ia_bruta = self.ia_logger.logs[-1].resposta_ia if self.ia_logger.logs else None

            # Calcula tempo de processamento
            fim = datetime.utcnow()
            geracao.tempo_processamento_ms = int((fim - inicio).total_seconds() * 1000)
            geracao.status = "concluido"

            self.db.commit()

            # Salva logs de IA
            self.ia_logger.salvar_logs(self.db, geracao.id)

            log_info(f"Tempo total de processamento: {geracao.tempo_processamento_ms/1000:.1f}s")
            logger.info(f"\n{'#'*60}")
            logger.info(f"# FIM - PARECER: {resultado.parecer.upper()}")
            logger.info(f"{'#'*60}\n")

            yield EventoSSE(
                tipo="sucesso",
                etapa=5,
                mensagem="Análise concluída!",
                progresso=100
            )

            yield EventoSSE(
                tipo="resultado",
                mensagem="Processamento finalizado",
                dados={
                    "geracao_id": geracao.id,
                    "parecer": resultado.parecer,
                    "fundamentacao": resultado.fundamentacao,
                    "valor_bloqueado": resultado.valor_bloqueado,
                    "valor_utilizado": resultado.valor_utilizado,
                    "valor_devolvido": resultado.valor_devolvido,
                    "medicamento_pedido": resultado.medicamento_pedido,
                    "medicamento_comprado": resultado.medicamento_comprado,
                    "irregularidades": resultado.irregularidades,
                    "perguntas": resultado.perguntas,
                }
            )

        except Exception as e:
            logger.exception(f"Erro no processamento: {e}")
            geracao.status = "erro"
            geracao.erro = str(e)
            self.db.commit()

            yield EventoSSE(
                tipo="erro",
                mensagem=f"Erro no processamento: {str(e)}"
            )
            yield EventoSSE(
                tipo="fim",
                mensagem="Processamento finalizado com erro"
            )

    async def responder_duvida(
        self,
        geracao_id: int,
        respostas: Dict[str, str]
    ) -> ResultadoAnalise:
        """
        Processa respostas do usuário às perguntas de dúvida e reavalia.

        Args:
            geracao_id: ID da geração
            respostas: Dict com pergunta -> resposta

        Returns:
            ResultadoAnalise atualizado
        """
        geracao = self.db.query(GeracaoAnalise).filter(
            GeracaoAnalise.id == geracao_id
        ).first()

        if not geracao:
            raise ValueError("Geração não encontrada")

        # Monta dados originais
        dados = DadosAnalise(
            extrato_subconta=geracao.extrato_subconta_texto or "",
            peticao_inicial=geracao.peticao_inicial_texto or "",
            peticao_prestacao=geracao.peticao_prestacao_texto or "",
            documentos_anexos=geracao.documentos_anexos or [],
        )

        # Reavalia
        agente = AgenteAnalise(
            modelo=self.modelo_analise,
            temperatura=self.temperatura_analise,
            ia_logger=self.ia_logger,
            db=self.db,
        )

        resultado = await agente.reanalisar_com_respostas(dados, respostas)

        # Atualiza geração
        geracao.parecer = resultado.parecer
        geracao.fundamentacao = resultado.fundamentacao
        geracao.irregularidades = resultado.irregularidades
        geracao.perguntas_usuario = resultado.perguntas
        geracao.respostas_usuario = respostas
        geracao.valor_bloqueado = resultado.valor_bloqueado
        geracao.valor_utilizado = resultado.valor_utilizado
        geracao.valor_devolvido = resultado.valor_devolvido

        self.db.commit()

        # Salva logs
        self.ia_logger.salvar_logs(self.db, geracao.id)

        return resultado
