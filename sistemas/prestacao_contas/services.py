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
from sistemas.prestacao_contas.identificador_peticoes import IdentificadorPeticoes
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
            print(f"[Prestacao] Deletados {len(registros_antigos)} registros anteriores")

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
            print(f"[Prestacao] Iniciando análise para {numero_cnj}")
            yield EventoSSE(tipo="inicio", mensagem="Iniciando análise de prestação de contas")

            # =====================================================
            # ETAPA 1: EXTRATO DA SUBCONTA
            # =====================================================
            print("[Prestacao] Etapa 1: Subconta")
            yield EventoSSE(
                tipo="etapa",
                etapa=1,
                etapa_nome="Extrato da Subconta",
                mensagem="Baixando extrato da subconta...",
                progresso=10
            )

            print("[Prestacao] Chamando extrair_extrato_subconta...")
            resultado_subconta = await extrair_extrato_subconta(numero_cnj)
            print(f"[Prestacao] Subconta resultado: {resultado_subconta.status}")

            if resultado_subconta.status == StatusProcessamento.OK:
                geracao.extrato_subconta_texto = resultado_subconta.texto_extraido
                yield EventoSSE(
                    tipo="progresso",
                    etapa=1,
                    mensagem="Extrato da subconta baixado com sucesso",
                    progresso=20
                )
            elif resultado_subconta.status == StatusProcessamento.SEM_SUBCONTA:
                yield EventoSSE(
                    tipo="aviso",
                    etapa=1,
                    mensagem="Processo não possui subconta registrada"
                )
            else:
                yield EventoSSE(
                    tipo="aviso",
                    etapa=1,
                    mensagem=f"Erro ao baixar subconta: {resultado_subconta.erro}"
                )

            # =====================================================
            # ETAPA 2: XML DO PROCESSO
            # =====================================================
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
                yield EventoSSE(
                    tipo="erro",
                    etapa=2,
                    mensagem=f"Erro ao consultar processo: {resultado_xml.erro}"
                )
                geracao.status = "erro"
                geracao.erro = resultado_xml.erro
                self.db.commit()
                return

            geracao.numero_cnj_formatado = resultado_xml.dados_basicos.numero_formatado
            geracao.dados_processo_xml = resultado_xml.to_dict()

            yield EventoSSE(
                tipo="progresso",
                etapa=2,
                mensagem=f"Processo encontrado: {resultado_xml.dados_basicos.autor}",
                progresso=35,
                dados={"autor": resultado_xml.dados_basicos.autor}
            )

            # =====================================================
            # ETAPA 3: IDENTIFICAR PETIÇÃO DE PRESTAÇÃO DE CONTAS
            # =====================================================
            yield EventoSSE(
                tipo="etapa",
                etapa=3,
                etapa_nome="Identificar Prestação",
                mensagem=f"Analisando {len(resultado_xml.peticoes_candidatas)} petições...",
                progresso=40
            )

            peticao_prestacao = None
            peticao_prestacao_doc = None
            identificador = IdentificadorPeticoes(
                usar_llm=True,
                modelo_llm=self.modelo_identificacao,
                temperatura_llm=self.temperatura_identificacao
            )

            async with aiohttp.ClientSession() as session:
                for i, peticao in enumerate(resultado_xml.peticoes_candidatas):
                    yield EventoSSE(
                        tipo="info",
                        etapa=3,
                        mensagem=f"Analisando petição {i+1}/{len(resultado_xml.peticoes_candidatas)}..."
                    )

                    # Baixa PDF da petição
                    try:
                        xml_docs = await baixar_documentos_async(session, numero_cnj, [peticao.id])
                        # Extrai conteúdo base64
                        import base64
                        import xml.etree.ElementTree as ET
                        root = ET.fromstring(xml_docs)
                        conteudo = None
                        for elem in root.iter():
                            if 'conteudo' in elem.tag.lower() and elem.text:
                                conteudo = base64.b64decode(elem.text)
                                break

                        if conteudo:
                            texto = extrair_texto_pdf(conteudo)

                            # Identifica se é prestação de contas
                            resultado_id = identificador.identificar(texto)

                            if resultado_id.e_prestacao_contas and resultado_id.confianca > 0.5:
                                peticao_prestacao = texto
                                peticao_prestacao_doc = peticao
                                geracao.prompt_identificacao = f"Método: {resultado_id.metodo}, Confiança: {resultado_id.confianca}"
                                yield EventoSSE(
                                    tipo="info",
                                    etapa=3,
                                    mensagem=f"Petição de prestação de contas encontrada! (confiança: {resultado_id.confianca:.0%})"
                                )
                                break

                    except Exception as e:
                        logger.error(f"Erro ao analisar petição {peticao.id}: {e}")
                        continue

            if not peticao_prestacao:
                yield EventoSSE(
                    tipo="aviso",
                    etapa=3,
                    mensagem="Petição de prestação de contas não encontrada"
                )
                geracao.status = "erro"
                geracao.erro = "Petição de prestação de contas não encontrada no processo"
                self.db.commit()
                return

            geracao.peticao_prestacao_id = peticao_prestacao_doc.id
            geracao.peticao_prestacao_data = peticao_prestacao_doc.data_juntada
            geracao.peticao_prestacao_texto = peticao_prestacao

            yield EventoSSE(
                tipo="progresso",
                etapa=3,
                mensagem="Petição de prestação de contas identificada",
                progresso=55
            )

            # =====================================================
            # ETAPA 4: BAIXAR DOCUMENTOS ANEXOS
            # =====================================================
            yield EventoSSE(
                tipo="etapa",
                etapa=4,
                etapa_nome="Baixar Documentos",
                mensagem="Baixando documentos anexos...",
                progresso=60
            )

            documentos_anexos = []

            # Baixa petição inicial
            if resultado_xml.peticao_inicial:
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
                                break
                except Exception as e:
                    logger.error(f"Erro ao baixar petição inicial: {e}")

            # Baixa documentos do mesmo dia da prestação
            parser = XMLParserPrestacao(xml_response)
            parser._parse_estrutura()
            parser._extrair_documentos()

            if peticao_prestacao_doc and peticao_prestacao_doc.data_juntada:
                docs_mesmo_dia = parser.get_documentos_mesmo_dia(peticao_prestacao_doc.data_juntada)
                yield EventoSSE(
                    tipo="info",
                    etapa=4,
                    mensagem=f"Encontrados {len(docs_mesmo_dia)} documentos anexos"
                )

                if docs_mesmo_dia:
                    ids_docs = [d.id for d in docs_mesmo_dia]
                    try:
                        async with aiohttp.ClientSession() as session:
                            xml_docs = await baixar_documentos_async(session, numero_cnj, ids_docs)

                            import base64
                            import xml.etree.ElementTree as ET
                            root = ET.fromstring(xml_docs)

                            doc_textos = {}
                            for elem in root.iter():
                                if 'documento' in elem.tag.lower():
                                    doc_id = elem.attrib.get('idDocumento', '')
                                    for child in elem:
                                        if 'conteudo' in child.tag.lower() and child.text:
                                            try:
                                                conteudo = base64.b64decode(child.text)
                                                doc_textos[doc_id] = extrair_texto_pdf(conteudo)
                                            except:
                                                pass

                            for doc in docs_mesmo_dia:
                                if doc.id in doc_textos:
                                    documentos_anexos.append({
                                        "id": doc.id,
                                        "tipo": doc.tipo_descricao or doc.tipo_codigo,
                                        "texto": doc_textos[doc.id]
                                    })

                    except Exception as e:
                        logger.error(f"Erro ao baixar documentos anexos: {e}")

            geracao.documentos_anexos = documentos_anexos

            yield EventoSSE(
                tipo="progresso",
                etapa=4,
                mensagem=f"{len(documentos_anexos)} documentos baixados",
                progresso=75
            )

            # =====================================================
            # ETAPA 5: ANÁLISE POR IA
            # =====================================================
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
            )

            agente = AgenteAnalise(
                modelo=self.modelo_analise,
                temperatura=self.temperatura_analise,
                ia_logger=self.ia_logger,
            )

            resultado = await agente.analisar(dados_analise)

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
