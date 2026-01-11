# sistemas/prestacao_contas/xml_parser.py
"""
Parser de XML do processo judicial (padrão MNI/CNJ) para Prestação de Contas

Extrai dados do XML retornado pela API SOAP do TJ-MS, identificando:
- Dados básicos do processo
- Petições específicas para análise de prestação de contas
- Documentos anexados no mesmo dia das petições

Autor: LAB/PGE-MS
"""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Any


# Códigos de petições que podem conter prestação de contas
# Lista ampliada para capturar todos os tipos de petição possíveis
CODIGOS_PETICAO_PRESTACAO = [
    "21", "25", "30", "93", "209", "215", "225", "238", "239", "240",
    "256", "270", "273", "277", "286", "306", "330", "333", "357",
    "500", "510", "579",
    "8303", "8305", "8315", "8320", "8323", "8326", "8327", "8330",
    "8331", "8333", "8334", "8336", "8338", "8350", "8356", "8361",
    "8365", "8367", "8368", "8373", "8380", "8387", "8388", "8390",
    "8392", "8393", "8395", "8397", "8399", "8423", "8425", "8426",
    "8428", "8438",
    "9500", "9511", "9615", "9635", "9875",
]

# Codigos de documentos que podem ser anexos (notas fiscais, comprovantes)
# Apenas os codigos especificos para notas fiscais e comprovantes
CODIGOS_DOCUMENTOS_ANEXOS = [
    "9870",  # Nota Fiscal
    "386",   # Nota Fiscal
    "9882",  # Comprovante
    "9908",  # Comprovante
    "9606",  # Comprovante
]


@dataclass
class DadosBasicosProcesso:
    """Dados básicos do processo"""
    numero_processo: str
    numero_formatado: str = ""
    classe: str = ""
    assunto: str = ""
    autor: str = ""
    reu: str = "Estado de Mato Grosso do Sul"
    comarca: str = ""
    vara: str = ""
    data_ajuizamento: Optional[date] = None
    valor_causa: Optional[float] = None


@dataclass
class DocumentoProcesso:
    """Documento do processo"""
    id: str
    tipo_codigo: str = ""
    tipo_descricao: str = ""
    data_juntada: Optional[datetime] = None
    movimento_descricao: str = ""
    movimento_complemento: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tipo_codigo": self.tipo_codigo,
            "tipo_descricao": self.tipo_descricao,
            "data_juntada": self.data_juntada.isoformat() if self.data_juntada else None,
            "movimento_descricao": self.movimento_descricao,
            "movimento_complemento": self.movimento_complemento,
        }


@dataclass
class ResultadoParseXML:
    """Resultado do parse do XML"""
    dados_basicos: DadosBasicosProcesso
    documentos: List[DocumentoProcesso] = field(default_factory=list)
    peticoes_candidatas: List[DocumentoProcesso] = field(default_factory=list)
    peticao_inicial: Optional[DocumentoProcesso] = None
    erro: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "dados_basicos": {
                "numero_processo": self.dados_basicos.numero_processo,
                "numero_formatado": self.dados_basicos.numero_formatado,
                "classe": self.dados_basicos.classe,
                "assunto": self.dados_basicos.assunto,
                "autor": self.dados_basicos.autor,
                "reu": self.dados_basicos.reu,
                "comarca": self.dados_basicos.comarca,
                "vara": self.dados_basicos.vara,
                "data_ajuizamento": self.dados_basicos.data_ajuizamento.isoformat() if self.dados_basicos.data_ajuizamento else None,
                "valor_causa": self.dados_basicos.valor_causa,
            },
            "total_documentos": len(self.documentos),
            "total_peticoes_candidatas": len(self.peticoes_candidatas),
            "peticao_inicial_id": self.peticao_inicial.id if self.peticao_inicial else None,
            "erro": self.erro,
        }


# =====================================================
# FUNÇÕES AUXILIARES
# =====================================================

def _parse_datahora_tjms(s: Optional[str]) -> Optional[datetime]:
    """Parse de data/hora no formato TJ-MS: YYYYMMDDHHMMSS"""
    if not s or len(s) < 8:
        return None
    try:
        if len(s) >= 14:
            return datetime.strptime(s[:14], "%Y%m%d%H%M%S")
        elif len(s) >= 8:
            return datetime.strptime(s[:8], "%Y%m%d")
    except ValueError:
        pass
    return None


def _parse_date_tjms(s: Optional[str]) -> Optional[date]:
    """Parse de data no formato TJ-MS para date"""
    dt = _parse_datahora_tjms(s)
    return dt.date() if dt else None


def _formatar_numero_processo(numero: str) -> str:
    """Formata número do processo para padrão CNJ: NNNNNNN-NN.NNNN.N.NN.NNNN"""
    numero_limpo = re.sub(r'\D', '', numero)
    if len(numero_limpo) == 20:
        return f"{numero_limpo[:7]}-{numero_limpo[7:9]}.{numero_limpo[9:13]}.{numero_limpo[13]}.{numero_limpo[14:16]}.{numero_limpo[16:]}"
    return numero


def _get_tag_name(elem: ET.Element) -> str:
    """Retorna nome da tag sem namespace"""
    return elem.tag.split('}')[-1].lower() if '}' in elem.tag else elem.tag.lower()


def _get_elem_text(elem: ET.Element, path: str) -> str:
    """Obtém texto de elemento filho"""
    for child in elem:
        if _get_tag_name(child) == path.lower():
            return child.text or ""
    return ""


def _get_elem_attrib(elem: ET.Element, path: str, attrib: str) -> str:
    """Obtém atributo de elemento filho"""
    for child in elem:
        if _get_tag_name(child) == path.lower():
            return child.attrib.get(attrib, "")
    return ""


# =====================================================
# PARSER PRINCIPAL
# =====================================================

class XMLParserPrestacao:
    """Parser do XML do processo para análise de prestação de contas"""

    def __init__(self, xml_text: str):
        """
        Inicializa o parser.

        Args:
            xml_text: XML completo do processo
        """
        self.xml_text = xml_text
        self.root = ET.fromstring(xml_text)
        self._dados_basicos_elem = None
        self._movimentos = []
        self._documentos: List[DocumentoProcesso] = []
        self._doc_movimento_map: Dict[str, Dict[str, str]] = {}

    def parse(self) -> ResultadoParseXML:
        """
        Faz o parse completo do XML.

        Returns:
            ResultadoParseXML com dados extraídos
        """
        try:
            self._parse_estrutura()
            dados_basicos = self._extrair_dados_basicos()
            self._extrair_documentos()

            # Filtra petições candidatas (códigos de petição, ordenadas por data desc)
            peticoes = [
                doc for doc in self._documentos
                if doc.tipo_codigo in CODIGOS_PETICAO_PRESTACAO
            ]
            # Ordena por data de juntada (mais recente primeiro)
            peticoes.sort(
                key=lambda d: d.data_juntada or datetime.min,
                reverse=True
            )

            # Identifica petição inicial (primeira em ordem cronológica)
            peticao_inicial = self._identificar_peticao_inicial()

            return ResultadoParseXML(
                dados_basicos=dados_basicos,
                documentos=self._documentos,
                peticoes_candidatas=peticoes,
                peticao_inicial=peticao_inicial,
            )

        except Exception as e:
            return ResultadoParseXML(
                dados_basicos=DadosBasicosProcesso(numero_processo=""),
                erro=f"Erro ao fazer parse do XML: {str(e)}",
            )

    def _parse_estrutura(self):
        """Parse inicial para identificar estrutura do XML"""
        for elem in self.root.iter():
            tag = _get_tag_name(elem)

            if tag == 'dadosbasicos':
                self._dados_basicos_elem = elem
            elif tag == 'movimento':
                self._movimentos.append(elem)
                # Extrai info do movimento para mapear aos documentos filhos
                mov_complemento = ""
                mov_descricao = ""
                mov_data = None

                for child in elem:
                    child_tag = _get_tag_name(child)
                    if child_tag == 'complemento' and child.text:
                        mov_complemento = child.text
                    elif child_tag == 'movimentolocal':
                        mov_descricao = child.attrib.get('descricao', '')
                    elif child_tag == 'datahora':
                        mov_data = _parse_datahora_tjms(child.text)

                # Mapeia documentos deste movimento
                for child in elem:
                    if _get_tag_name(child) == 'documento':
                        doc_id = child.attrib.get('idDocumento', '')
                        if doc_id:
                            self._doc_movimento_map[doc_id] = {
                                'complemento': mov_complemento,
                                'descricao': mov_descricao,
                                'data': mov_data,
                            }

    def _extrair_dados_basicos(self) -> DadosBasicosProcesso:
        """Extrai dados básicos do processo"""
        if self._dados_basicos_elem is None:
            return DadosBasicosProcesso(numero_processo="")

        elem = self._dados_basicos_elem

        # Número do processo
        numero = elem.attrib.get('numero', '')
        numero_formatado = _formatar_numero_processo(numero)

        # Classe processual
        classe = ""
        for child in elem:
            if _get_tag_name(child) == 'classeprocessual':
                classe = child.attrib.get('descricao', '')
                break

        # Assunto
        assunto = ""
        for child in elem:
            if _get_tag_name(child) == 'assunto':
                assunto_elem = child
                for sub in assunto_elem:
                    if _get_tag_name(sub) == 'principal':
                        assunto = sub.attrib.get('descricao', '')
                        break
                break

        # Partes
        autor = ""
        reu = "Estado de Mato Grosso do Sul"
        for child in elem:
            if _get_tag_name(child) == 'polo':
                polo_tipo = child.attrib.get('polo', '').upper()
                for parte in child:
                    if _get_tag_name(parte) == 'parte':
                        for pessoa in parte:
                            if _get_tag_name(pessoa) == 'pessoa':
                                nome = pessoa.attrib.get('nome', '')
                                if polo_tipo == 'AT' and not autor:
                                    autor = nome
                                elif polo_tipo == 'PA' and nome:
                                    reu = nome

        # Órgão julgador (vara)
        vara = ""
        comarca = ""
        for child in elem:
            if _get_tag_name(child) == 'orgaojulgador':
                vara = child.attrib.get('nomeOrgao', '')
                # Tenta extrair comarca do nome do órgão
                if ' - ' in vara:
                    partes = vara.split(' - ')
                    comarca = partes[-1] if len(partes) > 1 else ""
                break

        # Data de ajuizamento
        data_ajuizamento = None
        data_str = elem.attrib.get('dataAjuizamento', '')
        if data_str:
            data_ajuizamento = _parse_date_tjms(data_str)

        # Valor da causa
        valor_causa = None
        valor_str = elem.attrib.get('valorCausa', '')
        if valor_str:
            try:
                valor_causa = float(valor_str.replace(',', '.'))
            except ValueError:
                pass

        return DadosBasicosProcesso(
            numero_processo=numero,
            numero_formatado=numero_formatado,
            classe=classe,
            assunto=assunto,
            autor=autor,
            reu=reu,
            comarca=comarca,
            vara=vara,
            data_ajuizamento=data_ajuizamento,
            valor_causa=valor_causa,
        )

    def _extrair_documentos(self):
        """Extrai lista de documentos do processo"""
        for elem in self.root.iter():
            if _get_tag_name(elem) == 'documento':
                doc_id = elem.attrib.get('idDocumento', '')
                if not doc_id:
                    continue

                tipo_codigo = elem.attrib.get('tipoDocumento', '')
                tipo_descricao = elem.attrib.get('descricao', '')

                # Data de juntada
                data_juntada = None
                data_str = elem.attrib.get('dataHora', '')
                if data_str:
                    data_juntada = _parse_datahora_tjms(data_str)

                # Info do movimento pai
                mov_info = self._doc_movimento_map.get(doc_id, {})

                doc = DocumentoProcesso(
                    id=doc_id,
                    tipo_codigo=tipo_codigo,
                    tipo_descricao=tipo_descricao,
                    data_juntada=data_juntada or mov_info.get('data'),
                    movimento_descricao=mov_info.get('descricao', ''),
                    movimento_complemento=mov_info.get('complemento', ''),
                )
                self._documentos.append(doc)

    def _identificar_peticao_inicial(self) -> Optional[DocumentoProcesso]:
        """Identifica a petição inicial (primeira do processo)"""
        # Filtra documentos que podem ser petição inicial
        candidatas = [
            doc for doc in self._documentos
            if doc.tipo_codigo in ["21", "9500", "9501"]  # Petição Inicial, Petição
        ]

        if not candidatas:
            return None

        # Ordena por data (mais antiga primeiro)
        candidatas.sort(key=lambda d: d.data_juntada or datetime.max)

        return candidatas[0] if candidatas else None

    def get_documentos_mesmo_dia(
        self,
        data_referencia: datetime,
        excluir_id: str = None
    ) -> List[DocumentoProcesso]:
        """
        Retorna TODOS os documentos juntados no mesmo dia da data de referência.
        Útil para encontrar notas fiscais e comprovantes anexados junto com a prestação.

        Args:
            data_referencia: Data da petição de prestação de contas
            excluir_id: ID do documento a excluir (ex: a própria petição)

        Returns:
            Lista de documentos do mesmo dia (exceto o documento excluído)
        """
        if not data_referencia:
            return []

        data_ref = data_referencia.date()
        return [
            doc for doc in self._documentos
            if doc.data_juntada and doc.data_juntada.date() == data_ref
            and doc.id != excluir_id  # Exclui a própria petição de prestação
        ]

    def get_documentos_proximos(
        self,
        data_referencia: datetime,
        excluir_id: str = None,
        intervalo_minutos: int = 2
    ) -> List[DocumentoProcesso]:
        """
        Retorna documentos juntados próximos ao horário de referência.
        Útil para encontrar anexos (notas fiscais, comprovantes) juntados
        junto com uma petição.

        Args:
            data_referencia: Data/hora da petição
            excluir_id: ID do documento a excluir (ex: a própria petição)
            intervalo_minutos: Intervalo em minutos para considerar (padrão: 2)

        Returns:
            Lista de documentos dentro do intervalo (exceto o documento excluído)
        """
        if not data_referencia:
            return []

        # Define janela de tempo
        inicio = data_referencia - timedelta(minutes=intervalo_minutos)
        fim = data_referencia + timedelta(minutes=intervalo_minutos)

        return [
            doc for doc in self._documentos
            if doc.data_juntada
            and inicio <= doc.data_juntada <= fim
            and doc.id != excluir_id
        ]


def parse_xml_processo(xml_text: str) -> ResultadoParseXML:
    """
    Função de conveniência para parse do XML.

    Args:
        xml_text: XML completo do processo

    Returns:
        ResultadoParseXML com dados extraídos
    """
    parser = XMLParserPrestacao(xml_text)
    return parser.parse()
