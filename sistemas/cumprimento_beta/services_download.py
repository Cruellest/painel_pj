# sistemas/cumprimento_beta/services_download.py
"""
Serviço de download de documentos do TJ-MS para o módulo beta.

Baseado no agente_tjms.py do gerador_pecas - usa chamadas SOAP diretas via aiohttp.
"""

import json
import logging
import base64
import aiohttp
import fitz
import xml.etree.ElementTree as ET
from typing import List, Set, Optional, Dict, Any
from datetime import datetime
from dataclasses import dataclass
from sqlalchemy.orm import Session

from services.tjms import get_config as _get_tjms_config
from admin.models import ConfiguracaoIA
from sistemas.cumprimento_beta.models import SessaoCumprimentoBeta, DocumentoBeta
from sistemas.cumprimento_beta.constants import (
    StatusSessao, StatusRelevancia, ConfigKeys, MAX_DOCS_POR_PROCESSO
)
from sistemas.cumprimento_beta.exceptions import TJMSError, ProcessoInvalidoError

# Silencia warnings do PyMuPDF
fitz.TOOLS.mupdf_warnings(False)

logger = logging.getLogger(__name__)

# Configuração TJ-MS
_tjms_config = _get_tjms_config()
URL_WSDL = _tjms_config.soap_url
WS_USER = _tjms_config.soap_user
WS_PASS = _tjms_config.soap_pass


@dataclass
class DocumentoTJMSTemp:
    """Documento temporário extraído do XML do TJ-MS"""
    id: str
    tipo_documento: Optional[str] = None
    codigo: Optional[int] = None
    descricao: Optional[str] = None
    data_juntada: Optional[datetime] = None
    conteudo_base64: Optional[str] = None
    texto_extraido: Optional[str] = None


def _limpar_numero_processo(numero: str) -> str:
    """Remove formatação do número do processo"""
    if '/' in numero:
        numero = numero.split('/')[0]
    return ''.join(c for c in numero if c.isdigit())


def _parse_datahora_tjms(s: Optional[str]) -> Optional[datetime]:
    """Parse de data/hora no formato do TJ-MS: YYYYMMDDHHMMSS"""
    if not s or len(s) < 8:
        return None
    try:
        if len(s) >= 14:
            return datetime.strptime(s[:14], "%Y%m%d%H%M%S")
        elif len(s) >= 8:
            return datetime.strptime(s[:8], "%Y%m%d")
    except:
        pass
    return None


def _first_text(elem: ET.Element, tag_suffix: str) -> Optional[str]:
    """Busca primeiro texto de elemento cujo nome termina com tag_suffix"""
    for e in elem.iter():
        tag_no_ns = e.tag.split('}')[-1].lower()
        if tag_no_ns.endswith(tag_suffix.lower()) and e.text:
            return e.text.strip()
    return None


def _extrair_texto_pdf(conteudo_base64: str) -> str:
    """Extrai texto de PDF em base64"""
    try:
        pdf_bytes = base64.b64decode(conteudo_base64)
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        texto = ""
        for page in doc:
            texto += page.get_text()
        doc.close()
        # Remove caracteres NUL que PostgreSQL não aceita
        texto = texto.replace('\x00', '')
        return texto.strip()
    except Exception as e:
        logger.warning(f"[BETA] Erro ao extrair texto do PDF: {e}")
        return ""


async def consultar_processo_async(
    session: aiohttp.ClientSession,
    numero_processo: str,
    timeout: int = 60
) -> str:
    """Consulta processo via SOAP (async)"""
    numero_limpo = _limpar_numero_processo(numero_processo)

    xml_data = f'''
    <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                      xmlns:ser="http://www.cnj.jus.br/servico-intercomunicacao-2.2.2/"
                      xmlns:tip="http://www.cnj.jus.br/tipos-servico-intercomunicacao-2.2.2">
        <soapenv:Header/>
        <soapenv:Body>
            <ser:consultarProcesso>
                <tip:idConsultante>{WS_USER}</tip:idConsultante>
                <tip:senhaConsultante>{WS_PASS}</tip:senhaConsultante>
                <tip:numeroProcesso>{numero_limpo}</tip:numeroProcesso>
                <tip:movimentos>true</tip:movimentos>
                <tip:incluirDocumentos>true</tip:incluirDocumentos>
            </ser:consultarProcesso>
        </soapenv:Body>
    </soapenv:Envelope>'''.strip()

    async with session.post(
        URL_WSDL,
        data=xml_data,
        headers={'Content-Type': 'text/xml; charset=utf-8'},
        timeout=aiohttp.ClientTimeout(total=timeout)
    ) as resp:
        resp.raise_for_status()
        return await resp.text()


async def baixar_documentos_async(
    session: aiohttp.ClientSession,
    numero_processo: str,
    lista_ids: List[str],
    timeout: int = 180
) -> str:
    """Baixa conteúdo de documentos específicos via SOAP (async)"""
    numero_limpo = _limpar_numero_processo(numero_processo)

    # IMPORTANTE: Os IDs vão DIRETO no consultarProcesso, sem wrapper
    # (copiado exatamente do agente_tjms.py que funciona)
    xml_data = f'''
    <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                      xmlns:ser="http://www.cnj.jus.br/servico-intercomunicacao-2.2.2/"
                      xmlns:tip="http://www.cnj.jus.br/tipos-servico-intercomunicacao-2.2.2">
        <soapenv:Header/>
        <soapenv:Body>
            <ser:consultarProcesso>
                <tip:idConsultante>{WS_USER}</tip:idConsultante>
                <tip:senhaConsultante>{WS_PASS}</tip:senhaConsultante>
                <tip:numeroProcesso>{numero_limpo}</tip:numeroProcesso>
                {''.join(f'<tip:documento>{i}</tip:documento>' for i in lista_ids)}
            </ser:consultarProcesso>
        </soapenv:Body>
    </soapenv:Envelope>'''.strip()

    async with session.post(
        URL_WSDL,
        data=xml_data,
        headers={'Content-Type': 'text/xml; charset=utf-8'},
        timeout=aiohttp.ClientTimeout(total=timeout)
    ) as resp:
        resp.raise_for_status()
        return await resp.text()


def extrair_documentos_xml(xml_content: str) -> List[DocumentoTJMSTemp]:
    """Extrai lista de documentos do XML de resposta (copiado do agente_tjms.py)"""
    documentos = []

    try:
        root = ET.fromstring(xml_content)

        for elem in root.iter():
            tag_no_ns = elem.tag.split('}')[-1].lower() if '}' in elem.tag else elem.tag.lower()
            if tag_no_ns != 'documento':
                continue

            # IMPORTANTE: Os dados vêm nos ATRIBUTOS do elemento, não em elementos filhos
            doc_id = elem.attrib.get("idDocumento") or elem.attrib.get("id")
            if not doc_id:
                continue

            tipo = elem.attrib.get("tipoDocumento")
            descricao = elem.attrib.get("descricao")

            # Busca dataHora do atributo (formato YYYYMMDDHHMMSS)
            data_hora_attr = elem.attrib.get("dataHora")
            dt_txt = (
                data_hora_attr
                or _first_text(elem, "dataJuntada")
                or _first_text(elem, "dataHoraJuntada")
                or _first_text(elem, "dataInclusao")
                or elem.attrib.get("dataJuntada")
            )

            # Parse da data
            data_parsed = None
            if data_hora_attr:
                data_parsed = _parse_datahora_tjms(data_hora_attr)
            if not data_parsed and dt_txt:
                data_parsed = _parse_datahora_tjms(dt_txt)

            # Busca conteúdo base64 - primeiro no atributo, depois em elemento filho
            conteudo = elem.attrib.get("conteudo")
            if not conteudo:
                for child in elem:
                    child_tag = child.tag.split('}')[-1].lower()
                    if child_tag == 'conteudo' and child.text:
                        conteudo = child.text.strip()
                        break

            # Extrai código do tipo de documento
            codigo = None
            if tipo and tipo.isdigit():
                codigo = int(tipo)

            doc = DocumentoTJMSTemp(
                id=doc_id,
                tipo_documento=tipo,
                codigo=codigo,
                descricao=descricao,
                data_juntada=data_parsed,
                conteudo_base64=conteudo,
            )
            documentos.append(doc)

        # Remove duplicatas mantendo primeiro de cada ID
        seen = set()
        unique = []
        for d in documentos:
            if d.id not in seen:
                seen.add(d.id)
                unique.append(d)

        # Ordena por data (mais antigo primeiro)
        unique.sort(key=lambda d: d.data_juntada or datetime.min)

        return unique

    except ET.ParseError as e:
        logger.error(f"[BETA] Erro ao parsear XML: {e}")
        return []


class DownloadService:
    """Serviço para download de documentos do TJ-MS"""

    def __init__(self, db: Session):
        self.db = db
        self._codigos_ignorados: Set[int] = set()
        self._carregar_codigos_ignorados()

    def _carregar_codigos_ignorados(self) -> None:
        """Carrega lista de códigos a ignorar do admin"""
        try:
            config = self.db.query(ConfiguracaoIA).filter(
                ConfiguracaoIA.sistema == "cumprimento_beta",
                ConfiguracaoIA.chave == ConfigKeys.CODIGOS_IGNORAR
            ).first()

            if config and config.valor:
                codigos_lista = json.loads(config.valor)
                if isinstance(codigos_lista, list):
                    self._codigos_ignorados = set(int(c) for c in codigos_lista if c)
                    logger.info(f"[BETA] Códigos ignorados carregados: {sorted(self._codigos_ignorados)}")

        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.warning(f"[BETA] Erro ao carregar códigos ignorados: {e}")

    def codigo_deve_ser_ignorado(self, codigo: int) -> bool:
        """Verifica se um código de documento deve ser ignorado"""
        return codigo in self._codigos_ignorados

    async def baixar_documentos_processo(
        self,
        sessao: SessaoCumprimentoBeta,
        on_progress: Optional[callable] = None
    ) -> List[DocumentoBeta]:
        """
        Baixa todos os documentos de um processo do TJ-MS.

        Args:
            sessao: Sessão do beta
            on_progress: Callback para progresso (opcional)

        Returns:
            Lista de DocumentoBeta criados

        Raises:
            TJMSError: Se falhar comunicação com TJ-MS
            ProcessoInvalidoError: Se processo não encontrado
        """
        numero_processo = sessao.numero_processo
        logger.info(f"[BETA] Iniciando download de documentos do processo {numero_processo}")

        # Atualiza status da sessão
        sessao.status = StatusSessao.BAIXANDO_DOCS
        self.db.commit()

        try:
            async with aiohttp.ClientSession() as http_session:
                # 1. Consulta processo para obter lista de documentos
                logger.info(f"[BETA] Consultando processo {numero_processo}")
                xml_processo = await consultar_processo_async(http_session, numero_processo)

                # Extrai lista de documentos do XML
                documentos_tjms = extrair_documentos_xml(xml_processo)

                if not documentos_tjms:
                    logger.warning(f"[BETA] Nenhum documento encontrado para processo {numero_processo}")
                    return []

                logger.info(f"[BETA] Encontrados {len(documentos_tjms)} documentos")

                # Limita quantidade
                if len(documentos_tjms) > MAX_DOCS_POR_PROCESSO:
                    logger.warning(
                        f"[BETA] Processo tem {len(documentos_tjms)} documentos, "
                        f"limitando a {MAX_DOCS_POR_PROCESSO}"
                    )
                    documentos_tjms = documentos_tjms[:MAX_DOCS_POR_PROCESSO]

                sessao.total_documentos = len(documentos_tjms)
                self.db.commit()

                documentos_criados = []
                docs_para_baixar = []

                # Primeira passada: cria registros e identifica quais baixar
                for idx, doc_tjms in enumerate(documentos_tjms):
                    doc_beta = DocumentoBeta(
                        sessao_id=sessao.id,
                        documento_id_tjms=str(doc_tjms.id),
                        codigo_documento=doc_tjms.codigo or 0,
                        descricao_documento=doc_tjms.descricao,
                        data_documento=doc_tjms.data_juntada,
                    )

                    # Verifica se código deve ser ignorado
                    if self.codigo_deve_ser_ignorado(doc_beta.codigo_documento):
                        doc_beta.status_relevancia = StatusRelevancia.IGNORADO
                        doc_beta.motivo_irrelevancia = "Código na lista de ignorados"
                        sessao.documentos_ignorados = (sessao.documentos_ignorados or 0) + 1
                        logger.debug(
                            f"[BETA] Documento {doc_tjms.id} ignorado (código {doc_beta.codigo_documento})"
                        )
                    else:
                        # Marca para baixar conteúdo
                        docs_para_baixar.append((doc_beta, doc_tjms.id))

                    self.db.add(doc_beta)
                    documentos_criados.append(doc_beta)

                self.db.commit()

                # 2. Baixa conteúdo dos documentos não ignorados
                if docs_para_baixar:
                    logger.info(f"[BETA] Baixando conteúdo de {len(docs_para_baixar)} documentos")

                    ids_para_baixar = [doc_id for _, doc_id in docs_para_baixar]

                    # Baixa em batches de 5
                    batch_size = 5
                    for i in range(0, len(ids_para_baixar), batch_size):
                        batch_ids = ids_para_baixar[i:i + batch_size]

                        if on_progress:
                            await on_progress(
                                etapa="baixando_docs",
                                atual=min(i + batch_size, len(ids_para_baixar)),
                                total=len(ids_para_baixar),
                                mensagem=f"Baixando documentos {min(i + batch_size, len(ids_para_baixar))}/{len(ids_para_baixar)}"
                            )

                        try:
                            xml_docs = await baixar_documentos_async(
                                http_session, numero_processo, batch_ids
                            )
                            docs_baixados = extrair_documentos_xml(xml_docs)

                            # Mapeia por ID
                            docs_map = {d.id: d for d in docs_baixados}

                            # Atualiza os DocumentoBeta com o conteúdo
                            for doc_beta, doc_id in docs_para_baixar:
                                if doc_id in docs_map:
                                    doc_tjms = docs_map[doc_id]
                                    if doc_tjms.conteudo_base64:
                                        texto = _extrair_texto_pdf(doc_tjms.conteudo_base64)
                                        doc_beta.conteudo_texto = texto
                                        doc_beta.tamanho_bytes = len(texto.encode('utf-8')) if texto else 0

                        except Exception as e:
                            logger.warning(f"[BETA] Erro ao baixar batch: {e}")

                        self.db.commit()
                        sessao.documentos_processados = min(i + batch_size, len(ids_para_baixar))
                        self.db.commit()

                logger.info(
                    f"[BETA] Download concluído: {len(documentos_criados)} documentos, "
                    f"{sessao.documentos_ignorados or 0} ignorados"
                )

                return documentos_criados

        except aiohttp.ClientError as e:
            logger.error(f"[BETA] Erro de conexão com TJ-MS: {e}")
            sessao.status = StatusSessao.ERRO
            sessao.erro_mensagem = f"Erro de conexão com TJ-MS: {str(e)}"
            self.db.commit()
            raise TJMSError(f"Falha na conexão com TJ-MS: {e}")
        except Exception as e:
            logger.error(f"[BETA] Erro no download de documentos: {e}")
            sessao.status = StatusSessao.ERRO
            sessao.erro_mensagem = f"Erro ao baixar documentos: {str(e)}"
            self.db.commit()
            raise TJMSError(f"Falha ao baixar documentos do TJ-MS: {e}")


async def baixar_documentos_sessao(
    db: Session,
    sessao: SessaoCumprimentoBeta,
    on_progress: Optional[callable] = None
) -> List[DocumentoBeta]:
    """
    Função auxiliar para baixar documentos de uma sessão.

    Args:
        db: Sessão do banco de dados
        sessao: Sessão do beta
        on_progress: Callback para progresso

    Returns:
        Lista de DocumentoBeta criados
    """
    service = DownloadService(db)
    return await service.baixar_documentos_processo(sessao, on_progress)
