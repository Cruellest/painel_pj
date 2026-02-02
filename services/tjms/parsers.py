# services/tjms/parsers.py
"""
Parsers XML para respostas do TJ-MS.

Extrai dados estruturados do XML SOAP retornado pelo MNI.
"""

import re
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
import xml.etree.ElementTree as ET

from utils.security import safe_parse_xml
from .models import ProcessoTJMS, Parte, Movimento, DocumentoMetadata

logger = logging.getLogger(__name__)

# Namespaces usados pelo TJ-MS
# NOTA: TJ-MS usa intercomunicacao-2.2.2 para documentos, não tipos-servico
NS = {
    "soap": "http://schemas.xmlsoap.org/soap/envelope/",
    "ns2": "http://www.cnj.jus.br/intercomunicacao-2.2.2",
    "ns3": "http://www.cnj.jus.br/servico-intercomunicacao-2.2.2/",
    # Namespace alternativo (tipos) - alguns endpoints usam este
    "tip": "http://www.cnj.jus.br/tipos-servico-intercomunicacao-2.2.2",
}


class XMLParserTJMS:
    """
    Parser para XML de resposta do TJ-MS (MNI/SOAP).

    Extrai dados estruturados de um XML de processo.
    """

    def __init__(self, xml_text: str):
        """
        Inicializa o parser.

        Args:
            xml_text: XML completo da resposta SOAP
        """
        self.xml_text = xml_text
        self._root: Optional[ET.Element] = None

    def parse(self) -> ProcessoTJMS:
        """
        Parseia o XML e retorna ProcessoTJMS estruturado.

        Returns:
            ProcessoTJMS com todos os dados extraidos
        """
        # Parse seguro (previne XXE)
        self._root = safe_parse_xml(self.xml_text)

        # Extrai numero do processo
        numero = self._extrair_numero_processo()

        processo = ProcessoTJMS(
            numero=numero,
            xml_raw=self.xml_text,
        )

        # Extrai dados basicos
        self._extrair_dados_basicos(processo)

        # Extrai partes
        self._extrair_partes(processo)

        # Extrai movimentos
        self._extrair_movimentos(processo)

        # Extrai documentos
        self._extrair_documentos(processo)

        # Detecta processo de origem (cumprimento autonomo)
        self._detectar_processo_origem(processo)

        return processo

    def _extrair_numero_processo(self) -> str:
        """Extrai numero do processo do XML."""
        # Tenta diferentes locais
        for xpath in [
            ".//ns2:dadosBasicos",
            ".//dadosBasicos",
        ]:
            elem = self._root.find(xpath, NS)
            if elem is not None:
                numero = elem.attrib.get("numero", "")
                if numero:
                    return "".join(c for c in numero if c.isdigit())

        # Fallback: busca em qualquer lugar
        match = re.search(r'numero="(\d{20})"', self.xml_text)
        if match:
            return match.group(1)

        return ""

    def _extrair_dados_basicos(self, processo: ProcessoTJMS) -> None:
        """Extrai dados basicos do processo."""
        dados_basicos = self._root.find(".//ns2:dadosBasicos", NS)
        if dados_basicos is None:
            dados_basicos = self._root.find(".//dadosBasicos", NS)

        if dados_basicos is None:
            logger.warning("dadosBasicos nao encontrado no XML")
            return

        # Classe processual
        processo.classe_processual = dados_basicos.attrib.get("classeProcessual")
        classe_codigo = dados_basicos.attrib.get("codigoLocalidade")
        if classe_codigo and classe_codigo.isdigit():
            processo.classe_codigo = int(classe_codigo)

        # Competencia
        processo.competencia = dados_basicos.attrib.get("competencia")

        # Orgao julgador
        orgao = dados_basicos.find("ns2:orgaoJulgador", NS)
        if orgao is not None:
            processo.orgao_julgador = orgao.attrib.get("nomeOrgao")
            processo.comarca = orgao.attrib.get("codigoMunicipioIBGE")
            # Tenta extrair vara do nome
            nome_orgao = orgao.attrib.get("nomeOrgao", "")
            if "vara" in nome_orgao.lower():
                processo.vara = nome_orgao

        # Valor da causa
        valor_elem = dados_basicos.find("ns2:valorCausa", NS)
        if valor_elem is not None and valor_elem.text:
            processo.valor_causa = valor_elem.text.strip()

        # Data de ajuizamento
        data_elem = dados_basicos.find("ns2:dataAjuizamento", NS)
        if data_elem is not None and data_elem.text:
            processo.data_ajuizamento = self._parse_data(data_elem.text)

    def _extrair_partes(self, processo: ProcessoTJMS) -> None:
        """Extrai partes processuais (polo ativo e passivo)."""
        for polo_node in self._root.findall(".//ns2:polo", NS):
            polo_tipo = polo_node.attrib.get("polo", "")

            for parte_node in polo_node.findall("ns2:parte", NS):
                parte = self._parse_parte(parte_node, polo_tipo)
                if parte:
                    if polo_tipo == "AT":
                        processo.polo_ativo.append(parte)
                    elif polo_tipo == "PA":
                        processo.polo_passivo.append(parte)

    def _parse_parte(self, parte_node: ET.Element, polo: str) -> Optional[Parte]:
        """Parseia uma parte processual."""
        pessoa = parte_node.find("ns2:pessoa", NS)
        if pessoa is None:
            return None

        nome = pessoa.attrib.get("nome", "").strip()
        if not nome:
            return None

        # Tipo de pessoa
        tipo_pessoa = pessoa.attrib.get("tipoPessoa", "")
        if tipo_pessoa == "F":
            tipo_pessoa = "fisica"
        elif tipo_pessoa == "J":
            tipo_pessoa = "juridica"

        # Documento
        documento = None
        doc_elem = pessoa.find("ns2:documento", NS)
        if doc_elem is not None:
            documento = doc_elem.attrib.get("codigoDocumento", "")

        # Assistencia judiciaria
        assistencia = parte_node.attrib.get("assistenciaJudiciaria", "").lower() == "true"

        # Tipo de representante
        tipo_rep = None
        for adv in parte_node.findall("ns2:advogado", NS):
            tipo_rep = adv.attrib.get("tipoRepresentante", tipo_rep)

        return Parte(
            nome=nome,
            polo=polo,
            tipo_pessoa=tipo_pessoa,
            documento=documento,
            assistencia_judiciaria=assistencia,
            tipo_representante=tipo_rep,
        )

    def _extrair_movimentos(self, processo: ProcessoTJMS) -> None:
        """Extrai movimentos processuais."""
        for mov_node in self._root.findall(".//ns2:movimento", NS):
            movimento = self._parse_movimento(mov_node)
            if movimento:
                processo.movimentos.append(movimento)

        # Ordena por data (mais recente primeiro)
        processo.movimentos.sort(
            key=lambda m: m.data_hora or datetime.min,
            reverse=True
        )

    def _parse_movimento(self, mov_node: ET.Element) -> Optional[Movimento]:
        """Parseia um movimento processual."""
        # Data/hora
        data_hora = None
        data_str = mov_node.attrib.get("dataHora", "")
        if data_str:
            data_hora = self._parse_data(data_str)

        # Movimento nacional (codigo pai)
        codigo_nacional = None
        mov_nacional = mov_node.find("ns2:movimentoNacional", NS)
        if mov_nacional is not None:
            codigo_str = mov_nacional.attrib.get("codigoNacional", "")
            if codigo_str and codigo_str.isdigit():
                codigo_nacional = int(codigo_str)

        # Movimento local
        codigo_local = None
        descricao = ""
        mov_local = mov_node.find("ns2:movimentoLocal", NS)
        if mov_local is not None:
            codigo_local = mov_local.attrib.get("codigoMovimento", "")
            descricao = mov_local.text or ""

        # Se nao tem descricao do local, pega do nacional
        if not descricao and mov_nacional is not None:
            descricao = mov_nacional.text or ""

        # Complementos
        complementos = []
        for comp in mov_node.findall(".//ns2:complemento", NS):
            if comp.text:
                complementos.append(comp.text.strip())
        complemento = " | ".join(complementos) if complementos else None

        return Movimento(
            codigo_nacional=codigo_nacional,
            codigo_local=codigo_local,
            descricao=descricao.strip(),
            data_hora=data_hora,
            complemento=complemento,
        )

    def _extrair_documentos(self, processo: ProcessoTJMS) -> None:
        """Extrai metadados de documentos."""
        for doc_node in self._root.findall(".//ns2:documento", NS):
            doc = self._parse_documento(doc_node)
            if doc:
                processo.documentos.append(doc)

        # Ordena por data (mais recente primeiro)
        processo.documentos.sort(
            key=lambda d: d.data_juntada or datetime.min,
            reverse=True
        )

    def _parse_documento(self, doc_node: ET.Element) -> Optional[DocumentoMetadata]:
        """Parseia metadados de um documento."""
        doc_id = doc_node.attrib.get("idDocumento", "")
        if not doc_id:
            return None

        # Tipo do documento
        tipo_codigo = None
        tipo_descricao = None
        tipo_str = doc_node.attrib.get("tipoDocumento", "")
        if tipo_str and tipo_str.isdigit():
            tipo_codigo = int(tipo_str)

        # Descricao
        descricao = doc_node.attrib.get("descricao", "")

        # Data de juntada
        data_juntada = None
        data_str = doc_node.attrib.get("dataHora", "")
        if data_str:
            data_juntada = self._parse_data(data_str)

        # Mimetype
        mimetype = doc_node.attrib.get("mimetype", "application/pdf")

        # Nivel de sigilo
        nivel_sigilo = 0
        sigilo_str = doc_node.attrib.get("nivelSigilo", "0")
        if sigilo_str.isdigit():
            nivel_sigilo = int(sigilo_str)

        return DocumentoMetadata(
            id=doc_id,
            tipo_codigo=tipo_codigo,
            tipo_descricao=tipo_descricao,
            descricao=descricao,
            data_juntada=data_juntada,
            mimetype=mimetype,
            nivel_sigilo=nivel_sigilo,
        )

    def _detectar_processo_origem(self, processo: ProcessoTJMS) -> None:
        """Detecta se e cumprimento autonomo e extrai processo de origem."""
        # Verifica se e cumprimento de sentenca (classe 156 ou 229)
        classes_cumprimento = {"156", "229", "12078"}
        if processo.classe_processual not in classes_cumprimento:
            return

        # Busca processo vinculado
        for vinculo in self._root.findall(".//ns2:processoVinculado", NS):
            tipo_vinculo = vinculo.attrib.get("tipoVinculo", "")
            numero_vinculo = vinculo.attrib.get("numeroProcesso", "")

            # Vinculo tipo "OR" = processo de origem
            if tipo_vinculo == "OR" and numero_vinculo:
                processo.processo_origem = "".join(c for c in numero_vinculo if c.isdigit())
                processo.is_cumprimento_autonomo = True
                return

        # Fallback: busca em movimentos/complementos
        for mov in processo.movimentos:
            if mov.complemento:
                match = re.search(r'processo.*?(\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4})', mov.complemento, re.I)
                if match:
                    processo.processo_origem = "".join(c for c in match.group(1) if c.isdigit())
                    processo.is_cumprimento_autonomo = True
                    return

    def _parse_data(self, data_str: str) -> Optional[datetime]:
        """Parseia string de data em varios formatos."""
        if not data_str:
            return None

        # Formato: YYYYMMDDHHMMSS
        if re.match(r'^\d{14}$', data_str):
            try:
                return datetime.strptime(data_str, "%Y%m%d%H%M%S")
            except ValueError:
                pass

        # Formato: YYYY-MM-DD HH:MM:SS
        if re.match(r'^\d{4}-\d{2}-\d{2}', data_str):
            try:
                return datetime.fromisoformat(data_str.replace("Z", "+00:00"))
            except ValueError:
                pass

        # Formato: DD/MM/YYYY
        if re.match(r'^\d{2}/\d{2}/\d{4}', data_str):
            try:
                return datetime.strptime(data_str[:10], "%d/%m/%Y")
            except ValueError:
                pass

        logger.warning(f"Formato de data nao reconhecido: {data_str}")
        return None

    def extrair_documentos_por_tipo(
        self,
        tipos_permitidos: Optional[List[int]] = None,
        tipos_excluidos: Optional[List[int]] = None
    ) -> List[DocumentoMetadata]:
        """
        Extrai documentos filtrados por tipo.

        Args:
            tipos_permitidos: Lista de codigos permitidos (whitelist)
            tipos_excluidos: Lista de codigos excluidos (blacklist)

        Returns:
            Lista de DocumentoMetadata filtrados
        """
        processo = self.parse()
        documentos = processo.documentos

        if tipos_permitidos is not None:
            documentos = [d for d in documentos if d.tipo_codigo in tipos_permitidos]
        elif tipos_excluidos is not None:
            documentos = [d for d in documentos if d.tipo_codigo not in tipos_excluidos]

        return documentos


def extrair_conteudo_documento(xml_text: str, doc_id: str) -> Optional[bytes]:
    """
    Extrai conteudo binario (base64) de um documento do XML.

    Args:
        xml_text: XML da resposta SOAP
        doc_id: ID do documento

    Returns:
        bytes do documento decodificado ou None
    """
    import base64

    root = safe_parse_xml(xml_text)

    for doc in root.findall(".//ns2:documento", NS):
        if doc.attrib.get("idDocumento") == doc_id:
            conteudo = doc.find("ns2:conteudo", NS)
            if conteudo is not None and conteudo.text:
                try:
                    return base64.b64decode(conteudo.text)
                except Exception as e:
                    logger.error(f"Erro ao decodificar documento {doc_id}: {e}")
                    return None

    return None
