"""
Agente de IA para análise de documentos do TJ-MS
================================================

Este agente:
1. Consulta processos via API SOAP do TJ-MS
2. Baixa TODOS os documentos exceto categorias administrativas (certidões, ofícios, atas, etc)
3. Processa TODOS os documentos em paralelo para reduzir latência
4. Gera resumos de cada documento via OpenRouter (Gemini 2.5 Flash Lite)
5. Produz resumo consolidado e relatório final para subsidiar peças jurídicas

Autor: LAB/PGE-MS
"""

import os
import re
import sys
import base64
import asyncio
import aiohttp
import xml.etree.ElementTree as ET
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import json
from pathlib import Path

# PDF
import fitz  # PyMuPDF
import pymupdf4llm

from dotenv import load_dotenv
load_dotenv()


def _normalizar_texto_pdf(texto: str) -> str:
    """
    Normaliza texto extraído de PDF removendo quebras excessivas e espaços.
    """
    if not texto:
        return ""
    
    # Remove caracteres de controle exceto \n
    texto = re.sub(r'[\x00-\x09\x0b\x0c\x0e-\x1f]', '', texto)
    
    # Substitui múltiplos espaços por um só
    texto = re.sub(r'[ \t]+', ' ', texto)
    
    # Remove espaços no início e fim de cada linha
    linhas = [linha.strip() for linha in texto.split('\n')]
    
    # Junta linhas que foram quebradas no meio de frases
    resultado = []
    buffer = ""
    
    for linha in linhas:
        if not linha:
            if buffer:
                resultado.append(buffer)
                buffer = ""
            continue
        
        if buffer:
            ultima_char = buffer[-1] if buffer else ''
            primeira_char = linha[0] if linha else ''
            
            if ultima_char not in '.!?;:' and primeira_char.islower():
                buffer += ' ' + linha
            elif ultima_char == '-':
                buffer = buffer[:-1] + linha
            else:
                resultado.append(buffer)
                buffer = linha
        else:
            buffer = linha
    
    if buffer:
        resultado.append(buffer)
    
    texto_final = '\n\n'.join(resultado)
    texto_final = re.sub(r'\n{3,}', '\n\n', texto_final)
    
    return texto_final.strip()


# =========================
# Configurações
# =========================
URL_WSDL = os.getenv('URL_WSDL') or os.getenv('TJ_WSDL_URL') or os.getenv('TJ_URL_WSDL')
WS_USER = os.getenv('WS_USER') or os.getenv('TJ_WS_USER')
WS_PASS = os.getenv('WS_PASS') or os.getenv('TJ_WS_PASS')

# Validação das configurações
if not URL_WSDL:
    print("⚠️ URL_WSDL não configurada - defina TJ_WSDL_URL no .env")
if not WS_USER or not WS_PASS:
    print("⚠️ Credenciais TJ-MS não configuradas - defina TJ_WS_USER e TJ_WS_PASS no .env")

# Modelo padrão (sem prefixo google/)
MODELO_PADRAO = "gemini-3-flash-preview"

# =========================
# Categorias de documentos excluídas
# =========================
# Lista de categorias que NÃO devem ser baixadas/analisadas
CATEGORIAS_EXCLUIDAS = [
    10,    # Certidão diversa
    2,     # Certidão
    13,    # Ofício
    9508,  # Ofício expedido
    7,     # Ato ordinatório
    8449,  # Comunicação
    8450,  # Comunicação interna
    5,     # Ata
    9614,  # Termo
    9999,  # Outros
    192,   # Alvará
    53,    # Ato ordinatório praticado
    8433,  # Certidão de trânsito em julgado
    8494,  # Alvará diversos
    8500,  # Outros documentos
    9558,  # Termos diversos
]

# =========================
# Documentos que devem ir INTEGRAIS para a IA (sem resumo JSON)
# =========================
# Para desativar esta funcionalidade, basta comentar ou esvaziar esta lista
CODIGOS_TEXTO_INTEGRAL = {
    207,   # Parecer do CATES - Câmara Técnica em Saúde
    8451,  # Parecer do NAT - Núcleo de Apoio Técnico
    9636,  # Parecer NAT
    59,    # Nota Técnica NATJus
    8490,  # Nota Técnica NATJus
    8369,  # Laudo Pericial (pode incluir pareceres técnicos)
}


def documento_permitido(
    tipo_documento: int, 
    codigos_permitidos: set = None
) -> bool:
    """
    Verifica se o tipo de documento é permitido para análise.
    
    Args:
        tipo_documento: Código do documento TJ-MS
        codigos_permitidos: Conjunto de códigos permitidos (se configurado no banco).
                           Se None, usa filtro legado (CATEGORIAS_EXCLUIDAS).
    
    Returns:
        True se o documento deve ser analisado
    """
    if codigos_permitidos is not None:
        # Modo novo: usa lista de códigos permitidos do banco
        return tipo_documento in codigos_permitidos
    else:
        # Modo legado: usa lista de exclusão hardcoded
        return tipo_documento not in CATEGORIAS_EXCLUIDAS


# Mapa de categorias (código → descrição) - mantido para compatibilidade
CATEGORIAS_MAP = {
    "1": "Mandado",
    "2": "Certidão",
    "6": "Despacho",
    "8": "Sentença",
    "15": "Decisões Interlocutórias",
    "30": "Peças do MP",
    "34": "Acórdãos",
    "44": "Decisões Monocráticas",
    "53": "Ato Ordinatório",
    "137": "Decisão Interlocutória",
    "500": "Petição Inicial",
    "510": "Petição Intermediária",
    "8305": "Contrarrazões de Apelação",
    "8320": "Contestação",
    "8333": "Manifestação do Ministério Público",
    "8335": "Recurso de Apelação",
    "8338": "Manifestação do Procurador da Fazenda Pública Estadual",
    "8369": "Laudo Pericial",
    "9500": "Petição",
}


# =========================
# Dataclasses
# =========================
@dataclass
class DocumentoTJMS:
    """Representa um documento do processo"""
    id: str
    tipo_documento: Optional[str] = None
    categoria: Optional[str] = None
    data_juntada: Optional[datetime] = None
    data_texto: Optional[str] = None
    descricao: Optional[str] = None  # Descrição do documento (ex: "Petição", "Contestação")
    descricao_ia: Optional[str] = None  # Descrição identificada pela IA (mais precisa)
    ordem: Optional[int] = None
    conteudo_base64: Optional[str] = None
    texto_extraido: Optional[str] = None
    resumo: Optional[str] = None
    erro: Optional[str] = None
    irrelevante: bool = False  # Marcado pela IA como totalmente irrelevante
    processo_origem: bool = False  # True se é documento do processo de origem (1º grau)
    numero_processo: Optional[str] = None  # Número do processo ao qual pertence
    ids_agrupados: List[str] = field(default_factory=list)  # IDs de documentos agrupados

    @property
    def categoria_nome(self) -> str:
        """Retorna o nome da categoria do documento"""
        # Prioriza a descrição do XML se disponível
        if self.descricao:
            return self.descricao
        if self.tipo_documento:
            return CATEGORIAS_MAP.get(self.tipo_documento, f"Tipo {self.tipo_documento}")
        return "Desconhecido"
    
    @property
    def nome_exibicao(self) -> str:
        """Retorna o nome para exibição - prioriza identificação da IA"""
        if self.descricao_ia:
            return self.descricao_ia
        return self.categoria_nome

    @property
    def data_formatada(self) -> str:
        """Retorna a data formatada para exibição"""
        if self.data_juntada:
            return self.data_juntada.strftime('%d/%m/%Y %H:%M')
        return self.data_texto or 'N/A'

    @property
    def tag_origem(self) -> str:
        """Retorna tag indicando se é do processo principal ou de origem"""
        if self.processo_origem:
            return "[ORIGEM]"
        return ""


def _verificar_irrelevante(resumo: str) -> tuple[bool, str]:
    """
    Verifica se a IA marcou o documento como irrelevante.
    Retorna (é_irrelevante, resumo_limpo_ou_motivo)
    """
    if not resumo:
        return False, resumo

    resumo_strip = resumo.strip()

    # Verifica se começa com [IRRELEVANTE]
    if resumo_strip.startswith("**[IRRELEVANTE]**") or resumo_strip.startswith("[IRRELEVANTE]"):
        # Extrai o motivo
        motivo = resumo_strip.replace("**[IRRELEVANTE]**", "").replace("[IRRELEVANTE]", "").strip()
        return True, motivo if motivo else "Documento irrelevante"

    return False, resumo


def _extrair_tipo_documento_ia(resumo: str) -> Optional[str]:
    """
    Extrai o tipo de documento identificado pela IA do resumo.
    Procura por padrão: **[TIPO: Nome do Documento]**
    """
    if not resumo:
        return None
    
    import re
    
    # Padrão: **[TIPO: ...]** ou [TIPO: ...]
    padrao = r'\*?\*?\[TIPO:\s*([^\]]+)\]\*?\*?'
    match = re.search(padrao, resumo, re.IGNORECASE)
    
    if match:
        tipo = match.group(1).strip()
        # Limpa asteriscos extras
        tipo = tipo.replace('**', '').replace('*', '').strip()
        return tipo
    
    return None


def _extrair_processo_origem(resumo: str) -> Optional[str]:
    """
    Extrai número do processo de origem de um resumo de Agravo de Instrumento.
    Procura por padrões como: processo de origem nº XXXX, autos originários nº XXXX, etc.
    """
    import re

    if not resumo:
        return None

    # Padrões comuns para número de processo CNJ
    # Formato: NNNNNNN-NN.NNNN.N.NN.NNNN
    padrao_cnj = r'\b(\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4})\b'

    # Procura menções a processo de origem
    texto_lower = resumo.lower()

    # Indicadores de processo de origem
    indicadores = [
        'processo de origem',
        'autos de origem',
        'autos originários',
        'ação originária',
        'processo originário',
        'feito de origem',
        '1º grau',
        'primeiro grau',
        'origem:',
        'processo nº'
    ]

    # Encontra todos os números de processo no texto
    processos = re.findall(padrao_cnj, resumo)

    if not processos:
        return None

    # Se há indicador de origem, tenta pegar o processo mais próximo
    for indicador in indicadores:
        if indicador in texto_lower:
            # Pega o primeiro processo encontrado (geralmente é o de origem)
            # Em agravos, o primeiro número mencionado costuma ser o de origem
            return processos[0] if processos else None

    # Se encontrou mais de um processo, o primeiro geralmente é o de origem
    if len(processos) > 1:
        return processos[0]

    return None


@dataclass
class ParteProcesso:
    """Representa uma parte do processo (autor ou réu)"""
    nome: str
    tipo_pessoa: str = "fisica"  # fisica ou juridica
    polo: str = "AT"  # AT (polo ativo) ou PA (polo passivo)
    representante: Optional[str] = None  # Nome do advogado/defensor/procurador
    tipo_representante: Optional[str] = None  # 'advogado', 'defensoria', 'ministerio_publico', 'procuradoria'
    assistencia_judiciaria: bool = False


@dataclass
class DadosProcesso:
    """Dados extraídos do XML do processo (sem IA)"""
    numero_processo: str
    polo_ativo: List[ParteProcesso] = field(default_factory=list)
    polo_passivo: List[ParteProcesso] = field(default_factory=list)
    valor_causa: Optional[str] = None
    classe_processual: Optional[str] = None
    data_ajuizamento: Optional[datetime] = None
    orgao_julgador: Optional[str] = None
    
    def to_json(self) -> dict:
        """Converte para dicionário JSON-serializável"""
        return {
            "numero_processo": self.numero_processo,
            "polo_ativo": [
                {
                    "nome": p.nome,
                    "tipo_pessoa": p.tipo_pessoa,
                    "representante": p.representante,
                    "tipo_representante": p.tipo_representante,
                    "assistencia_judiciaria": p.assistencia_judiciaria
                }
                for p in self.polo_ativo
            ],
            "polo_passivo": [
                {
                    "nome": p.nome,
                    "tipo_pessoa": p.tipo_pessoa,
                    "representante": p.representante,
                    "tipo_representante": p.tipo_representante,
                    "assistencia_judiciaria": p.assistencia_judiciaria
                }
                for p in self.polo_passivo
            ],
            "valor_causa": self.valor_causa,
            "classe_processual": self.classe_processual,
            "data_ajuizamento": self.data_ajuizamento.strftime("%d/%m/%Y") if self.data_ajuizamento else None,
            "orgao_julgador": self.orgao_julgador
        }


@dataclass
class ResultadoAnalise:
    """Resultado da análise completa do processo"""
    numero_processo: str
    data_analise: datetime = field(default_factory=datetime.now)
    documentos: List[DocumentoTJMS] = field(default_factory=list)
    relatorio_final: Optional[str] = None
    erro_geral: Optional[str] = None
    processo_origem: Optional[str] = None  # Número do processo de origem (se for AI)
    is_agravo: bool = False  # True se é Agravo de Instrumento
    dados_processo: Optional[DadosProcesso] = None  # Dados extraídos do XML (partes, valor, etc)

    def documentos_com_resumo(self) -> List[DocumentoTJMS]:
        """Retorna documentos com resumo (excluindo irrelevantes)"""
        return [d for d in self.documentos if d.resumo and not d.irrelevante]

    def documentos_irrelevantes(self) -> List[DocumentoTJMS]:
        """Retorna documentos marcados como irrelevantes"""
        return [d for d in self.documentos if d.irrelevante]

    def documentos_com_erro(self) -> List[DocumentoTJMS]:
        return [d for d in self.documentos if d.erro]

    def documentos_processo_principal(self) -> List[DocumentoTJMS]:
        """Retorna documentos do processo principal (AI)"""
        return [d for d in self.documentos if not d.processo_origem and d.resumo and not d.irrelevante]

    def documentos_processo_origem(self) -> List[DocumentoTJMS]:
        """Retorna documentos do processo de origem (1º grau)"""
        return [d for d in self.documentos if d.processo_origem and d.resumo and not d.irrelevante]


# =========================
# Funções SOAP TJ-MS
# =========================
def _parse_iso_date(s: Optional[str]) -> Optional[datetime]:
    """Parse de datas em vários formatos"""
    if not s:
        return None
    s = s.strip().replace("Z", "+0000")
    fmts = [
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in fmts:
        try:
            return datetime.strptime(s, fmt)
        except:
            continue
    return None


def _parse_datahora_tjms(s: Optional[str]) -> Optional[datetime]:
    """Parse de data/hora no formato do TJ-MS: YYYYMMDDHHMMSS (ex: 20251120125020)"""
    if not s or len(s) < 8:
        return None
    try:
        # Formato: YYYYMMDDHHMMSS
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


def _limpar_numero_processo(numero: str) -> str:
    """
    Remove formatação do número do processo, deixando apenas 20 dígitos.
    
    Também remove sufixos após barra (ex: 0804330-09.2024.8.12.0017/50003 -> 0804330-09.2024.8.12.0017)
    """
    # Remove sufixo após barra (ex: /50003)
    if '/' in numero:
        numero = numero.split('/')[0]
    return ''.join(c for c in numero if c.isdigit())


async def consultar_processo_async(
    session: aiohttp.ClientSession,
    numero_processo: str,
    timeout: int = 60
) -> str:
    """Consulta processo via SOAP (async)"""
    # Limpar formatação do número
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
    # Limpar formatação do número
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


def extrair_documentos_xml(xml_text: str) -> List[DocumentoTJMS]:
    """Extrai lista de documentos do XML de resposta"""
    root = ET.fromstring(xml_text)
    docs = []

    for elem in root.iter():
        tag_no_ns = elem.tag.split('}')[-1].lower() if '}' in elem.tag else elem.tag.lower()
        if tag_no_ns != 'documento':
            continue

        doc_id = elem.attrib.get("idDocumento") or elem.attrib.get("id")
        if not doc_id:
            continue

        tipo = elem.attrib.get("tipoDocumento")
        descricao = elem.attrib.get("descricao")  # Ex: "Petição", "Contestação"

        # Busca dataHora do atributo (formato YYYYMMDDHHMMSS)
        data_hora_attr = elem.attrib.get("dataHora")

        # Busca data de juntada em outros formatos como fallback
        dt_txt = (
            data_hora_attr
            or _first_text(elem, "dataJuntada")
            or _first_text(elem, "dataHoraJuntada")
            or _first_text(elem, "dataInclusao")
            or elem.attrib.get("dataJuntada")
        )

        # Parse da data - tenta formato TJ-MS primeiro, depois ISO
        data_parsed = None
        if data_hora_attr:
            data_parsed = _parse_datahora_tjms(data_hora_attr)
        if not data_parsed and dt_txt:
            data_parsed = _parse_iso_date(dt_txt) or _parse_datahora_tjms(dt_txt)

        # Busca conteúdo base64
        conteudo = elem.attrib.get("conteudo")
        if not conteudo:
            for child in elem:
                child_tag = child.tag.split('}')[-1].lower()
                if child_tag == 'conteudo' and child.text:
                    conteudo = child.text.strip()
                    break

        doc = DocumentoTJMS(
            id=doc_id,
            tipo_documento=tipo,
            descricao=descricao,
            data_texto=dt_txt,
            data_juntada=data_parsed,
            conteudo_base64=conteudo
        )
        docs.append(doc)

    # Remove duplicatas mantendo primeiro de cada ID
    seen = set()
    unique = []
    for d in docs:
        if d.id not in seen:
            seen.add(d.id)
            unique.append(d)

    # Ordena por data (mais antigo primeiro)
    unique.sort(key=lambda d: d.data_juntada or datetime.min)

    return unique


def extrair_dados_processo_xml(xml_text: str) -> Optional[DadosProcesso]:
    """
    Extrai dados do processo do XML (partes, valor da causa, etc) SEM usar IA.
    
    Retorna:
        DadosProcesso com polo ativo, polo passivo e demais dados
    """
    try:
        root = ET.fromstring(xml_text)
        
        # Busca o elemento dadosBasicos
        dados_basicos = None
        for elem in root.iter():
            tag_no_ns = elem.tag.split('}')[-1].lower() if '}' in elem.tag else elem.tag.lower()
            if tag_no_ns == 'dadosbasicos':
                dados_basicos = elem
                break
        
        if dados_basicos is None:
            return None
        
        # Extrai número do processo
        numero_processo = dados_basicos.attrib.get('numero', '')
        
        # Extrai valor da causa
        valor_causa = None
        for elem in dados_basicos.iter():
            tag_no_ns = elem.tag.split('}')[-1].lower() if '}' in elem.tag else elem.tag.lower()
            if tag_no_ns == 'valorcausa' and elem.text:
                valor_causa = elem.text.strip()
                break
        
        # Extrai classe processual
        classe_processual = dados_basicos.attrib.get('classeProcessual')
        
        # Extrai data de ajuizamento
        data_ajuizamento = None
        data_str = dados_basicos.attrib.get('dataAjuizamento')
        if data_str:
            data_ajuizamento = _parse_datahora_tjms(data_str)
        
        # Extrai órgão julgador
        orgao_julgador = None
        for elem in dados_basicos.iter():
            tag_no_ns = elem.tag.split('}')[-1].lower() if '}' in elem.tag else elem.tag.lower()
            if tag_no_ns == 'orgaojulgador':
                orgao_julgador = elem.attrib.get('nomeOrgao')
                break
        
        # Extrai polos
        polo_ativo = []
        polo_passivo = []
        
        for polo_elem in dados_basicos.iter():
            tag_no_ns = polo_elem.tag.split('}')[-1].lower() if '}' in polo_elem.tag else polo_elem.tag.lower()
            if tag_no_ns != 'polo':
                continue
            
            tipo_polo = polo_elem.attrib.get('polo', '')
            partes_list = polo_ativo if tipo_polo == 'AT' else polo_passivo if tipo_polo == 'PA' else []
            
            # Processa cada parte do polo
            for parte_elem in polo_elem.iter():
                parte_tag = parte_elem.tag.split('}')[-1].lower() if '}' in parte_elem.tag else parte_elem.tag.lower()
                if parte_tag != 'parte':
                    continue
                
                assistencia = parte_elem.attrib.get('assistenciaJudiciaria', 'false').lower() == 'true'
                
                # Busca pessoa principal (a parte)
                pessoa_principal = None
                for pessoa_elem in parte_elem:
                    pessoa_tag = pessoa_elem.tag.split('}')[-1].lower() if '}' in pessoa_elem.tag else pessoa_elem.tag.lower()
                    if pessoa_tag == 'pessoa':
                        pessoa_principal = pessoa_elem
                        break
                
                if pessoa_principal is None:
                    continue
                
                nome_parte = pessoa_principal.attrib.get('nome', '')
                tipo_pessoa = pessoa_principal.attrib.get('tipoPessoa', 'fisica')
                
                # Busca representante (advogado, defensoria, MP)
                representante_nome = None
                tipo_representante = None
                
                # Primeiro procura advogado direto
                for adv_elem in parte_elem.iter():
                    adv_tag = adv_elem.tag.split('}')[-1].lower() if '}' in adv_elem.tag else adv_elem.tag.lower()
                    if adv_tag == 'advogado':
                        representante_nome = adv_elem.attrib.get('nome')
                        tipo_representante = 'advogado'
                        break
                
                # Se não tem advogado, procura pessoaProcessualRelacionada
                if not representante_nome:
                    for rel_elem in parte_elem.iter():
                        rel_tag = rel_elem.tag.split('}')[-1].lower() if '}' in rel_elem.tag else rel_elem.tag.lower()
                        if rel_tag == 'pessoaprocessualrelacionada':
                            # Busca pessoa dentro de pessoaProcessualRelacionada
                            for pessoa_rel in rel_elem:
                                pessoa_rel_tag = pessoa_rel.tag.split('}')[-1].lower() if '}' in pessoa_rel.tag else pessoa_rel.tag.lower()
                                if pessoa_rel_tag == 'pessoa':
                                    nome_rel = pessoa_rel.attrib.get('nome', '').lower()
                                    representante_nome = pessoa_rel.attrib.get('nome')
                                    
                                    # Identifica o tipo de representante
                                    if 'defensoria' in nome_rel:
                                        tipo_representante = 'defensoria'
                                    elif 'ministério público' in nome_rel or 'ministerio publico' in nome_rel or 'promotor' in nome_rel:
                                        tipo_representante = 'ministerio_publico'
                                    elif 'procuradoria' in nome_rel:
                                        tipo_representante = 'procuradoria'
                                    else:
                                        tipo_representante = 'outro'
                                    break
                            break
                
                # Cria a parte
                parte = ParteProcesso(
                    nome=nome_parte,
                    tipo_pessoa=tipo_pessoa,
                    polo=tipo_polo,
                    representante=representante_nome,
                    tipo_representante=tipo_representante,
                    assistencia_judiciaria=assistencia
                )
                partes_list.append(parte)
        
        return DadosProcesso(
            numero_processo=numero_processo,
            polo_ativo=polo_ativo,
            polo_passivo=polo_passivo,
            valor_causa=valor_causa,
            classe_processual=classe_processual,
            data_ajuizamento=data_ajuizamento,
            orgao_julgador=orgao_julgador
        )
        
    except Exception as e:
        print(f"Erro ao extrair dados do processo: {e}")
        return None


def agrupar_documentos_por_descricao(docs: List[DocumentoTJMS]) -> List[DocumentoTJMS]:
    """
    Agrupa documentos com mesma descrição e data/hora em um único documento.
    Isso acontece quando a API retorna várias partes do mesmo documento.
    """
    from collections import defaultdict

    # Agrupa por (descricao, data_juntada) - mesma descrição no mesmo momento = mesmo documento
    grupos = defaultdict(list)

    for doc in docs:
        # Chave: descrição + data (arredondada para o minuto)
        data_key = doc.data_juntada.strftime('%Y%m%d%H%M') if doc.data_juntada else 'sem_data'
        chave = (doc.descricao or doc.tipo_documento or 'desconhecido', data_key)
        grupos[chave].append(doc)

    resultado = []

    for (descricao, data_key), docs_grupo in grupos.items():
        if len(docs_grupo) == 1:
            # Documento único, mantém como está
            resultado.append(docs_grupo[0])
        else:
            # Múltiplos documentos com mesma descrição/data - agrupar
            # Usa o primeiro como base
            doc_principal = docs_grupo[0]
            doc_principal.ids_agrupados = [d.id for d in docs_grupo]

            # Concatena os IDs para referência
            ids_str = ", ".join([d.id for d in docs_grupo])
            doc_principal.id = docs_grupo[0].id  # Mantém o primeiro ID como principal

            resultado.append(doc_principal)

    # Reordena por data
    resultado.sort(key=lambda d: d.data_juntada or datetime.min)

    return resultado


def extrair_info_processo_xml(xml_text: str) -> dict:
    """
    Extrai informações do processo do XML (classe processual, processo vinculado, etc.)
    """
    import re

    info = {
        "classe_processual": None,
        "processo_vinculado": None,
        "is_agravo": False
    }

    try:
        root = ET.fromstring(xml_text)

        # Procurar classeProcessual no XML
        for elem in root.iter():
            tag_no_ns = elem.tag.split('}')[-1].lower() if '}' in elem.tag else elem.tag.lower()

            # dadosBasicos contém classeProcessual
            if tag_no_ns == 'dadosbasicos':
                classe = elem.attrib.get('classeProcessual')
                if classe:
                    info["classe_processual"] = classe
                    # Classes de Agravo de Instrumento: 1208 é a mais comum
                    if classe in ['1208', '27', '58']:  # Agravo de Instrumento
                        info["is_agravo"] = True

            # processoVinculado pode ter o processo de origem
            if tag_no_ns in ['processovinculado', 'vinculacao', 'processoreferencia']:
                num_vinc = elem.attrib.get('numeroProcesso') or elem.text
                if num_vinc:
                    # Formatar para CNJ
                    num_limpo = ''.join(c for c in num_vinc if c.isdigit())
                    if len(num_limpo) == 20:
                        info["processo_vinculado"] = f"{num_limpo[:7]}-{num_limpo[7:9]}.{num_limpo[9:13]}.{num_limpo[13]}.{num_limpo[14:16]}.{num_limpo[16:]}"

        # Procurar número de processo de origem no texto do XML
        if not info["processo_vinculado"]:
            # Padrão CNJ no XML
            padrao_cnj = r'\b(\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4})\b'
            matches = re.findall(padrao_cnj, xml_text)
            if len(matches) > 1:
                # O segundo número costuma ser o de origem
                info["processo_vinculado"] = matches[1]

    except Exception:
        pass

    return info


@dataclass
class ConteudoPDF:
    """Representa o conteúdo extraído de um PDF"""
    tipo: str  # 'texto' ou 'imagens'
    conteudo: Any  # str para texto, List[str] para imagens base64
    paginas: int


def extrair_conteudo_pdf(pdf_bytes: bytes, max_paginas_imagem: int = 10) -> ConteudoPDF:
    """
    Extrai conteúdo do PDF - texto ou imagens se for PDF digitalizado.

    Retorna ConteudoPDF com tipo 'texto' ou 'imagens'.
    """
    try:
        # Verifica se é RTF disfarçado
        if pdf_bytes.startswith(b'{\\rtf'):
            texto = pdf_bytes.decode('latin-1', errors='ignore')
            return ConteudoPDF(tipo='texto', conteudo=_normalizar_texto_pdf(texto), paginas=1)

        # Tenta abrir como PDF
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            num_paginas = len(doc)

            # Primeiro tenta extrair texto
            texto_completo = ""
            for page in doc:
                texto_completo += page.get_text()

            # Se tem texto suficiente (mais de 200 chars), retorna texto
            if len(texto_completo.strip()) > 200:
                # Usa pymupdf4llm para extração otimizada
                try:
                    # Suprime avisos do pymupdf4llm (find_tables exceptions)
                    import io
                    old_stderr = sys.stderr
                    sys.stderr = io.StringIO()
                    try:
                        md_text = pymupdf4llm.to_markdown(doc)
                    finally:
                        sys.stderr = old_stderr
                    # pymupdf4llm já formata bem, mas aplicamos normalização leve
                    return ConteudoPDF(tipo='texto', conteudo=md_text, paginas=num_paginas)
                except:
                    # Fallback com normalização
                    return ConteudoPDF(tipo='texto', conteudo=_normalizar_texto_pdf(texto_completo), paginas=num_paginas)

            # PDF digitalizado - converter páginas para imagens
            imagens = []
            paginas_processar = min(num_paginas, max_paginas_imagem)

            for i in range(paginas_processar):
                page = doc[i]
                # Renderiza página como imagem (zoom 2x para melhor qualidade)
                mat = fitz.Matrix(2, 2)
                pix = page.get_pixmap(matrix=mat)

                # Converte para JPEG base64
                img_bytes = pix.tobytes("jpeg", 85)
                img_base64 = base64.b64encode(img_bytes).decode('utf-8')
                imagens.append(f"data:image/jpeg;base64,{img_base64}")

            return ConteudoPDF(tipo='imagens', conteudo=imagens, paginas=num_paginas)

    except Exception as e:
        # Fallback: tenta extração simples de texto
        try:
            with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
                text = ""
                for page in doc:
                    text += page.get_text()
                if text.strip():
                    return ConteudoPDF(tipo='texto', conteudo=_normalizar_texto_pdf(text), paginas=len(doc))
        except:
            pass
        return ConteudoPDF(tipo='texto', conteudo=f"[Erro na extração: {str(e)}]", paginas=0)


def extrair_texto_pdf(pdf_bytes: bytes) -> str:
    """Extrai texto do PDF usando PyMuPDF + pymupdf4llm (mantida para compatibilidade)"""
    resultado = extrair_conteudo_pdf(pdf_bytes)
    if resultado.tipo == 'texto':
        return resultado.conteudo
    return "[PDF digitalizado - sem texto extraível]"


# =========================
# Funções Gemini/LLM (usando serviço centralizado)
# =========================
from services.gemini_service import gemini_service


async def chamar_llm_async(
    session: aiohttp.ClientSession,
    prompt: str,
    system_prompt: str = "",
    modelo: str = MODELO_PADRAO,
    max_tokens: int = 4096,
    temperature: float = 0.3
) -> str:
    """Chama modelo Gemini diretamente (async)"""
    response = await gemini_service.generate_with_session(
        session=session,
        prompt=prompt,
        system_prompt=system_prompt,
        model=modelo,
        max_tokens=max_tokens,
        temperature=temperature
    )
    
    if not response.success:
        raise ValueError(response.error)
    
    return response.content


async def chamar_llm_com_imagens_async(
    session: aiohttp.ClientSession,
    prompt: str,
    imagens_base64: List[str],
    system_prompt: str = "",
    modelo: str = MODELO_PADRAO,
    max_tokens: int = 4096,
    temperature: float = 0.3
) -> str:
    """Chama modelo Gemini com imagens (async) - para PDFs digitalizados"""
    response = await gemini_service.generate_with_images_session(
        session=session,
        prompt=prompt,
        images_base64=imagens_base64,
        system_prompt=system_prompt,
        model=modelo,
        max_tokens=max_tokens,
        temperature=temperature
    )
    
    if not response.success:
        raise ValueError(response.error)
    
    return response.content


# =========================
# Agente Principal
# =========================
class AgenteTJMS:
    """Agente de IA para análise de documentos do TJ-MS"""

    def __init__(
        self,
        prompt_resumo: str = None,
        prompt_relatorio: str = None,
        modelo: str = MODELO_PADRAO,
        max_workers: int = 30,  # Número máximo de chamadas paralelas à IA
        formato_saida: str = "json",  # 'json' ou 'md'
        db_session = None,  # Sessão do banco para buscar formatos JSON
        codigos_permitidos: set = None,  # Códigos de documento a analisar (None = usa filtro legado)
        codigos_primeiro_doc: set = None  # Códigos que devem pegar só o primeiro documento cronológico
    ):
        self.modelo = modelo
        self.max_workers = max_workers
        self.formato_saida = formato_saida
        self.db_session = db_session
        self.codigos_permitidos = codigos_permitidos  # None = usa CATEGORIAS_EXCLUIDAS
        self.codigos_primeiro_doc = codigos_primeiro_doc or set()  # Códigos especiais (ex: Petição Inicial)
        
        # Semáforo para controlar concorrência de chamadas à IA
        self._semaphore = None  # Criado sob demanda no contexto async
        
        # Gerenciador de formatos JSON (carregado sob demanda)
        self._gerenciador_json = None

        # Prompt padrão para resumo individual (usado apenas se formato_saida='md')
        self.prompt_resumo = prompt_resumo or """Analise o documento judicial e produza um resumo DESCRITIVO e OBJETIVO, sem juízos de valor.

## PRIMEIRA LINHA OBRIGATÓRIA - IDENTIFICAÇÃO DO DOCUMENTO:
Comece o resumo com uma linha no formato:
**[TIPO: Nome Exato do Documento]**

Exemplos de tipos:
- **[TIPO: Petição Inicial]**
- **[TIPO: Contestação]**
- **[TIPO: Recurso de Apelação]**
- **[TIPO: Contrarrazões de Apelação]**
- **[TIPO: Agravo de Instrumento]**
- **[TIPO: Contrarrazões de Agravo]**
- **[TIPO: Sentença]**
- **[TIPO: Decisão Interlocutória]**
- **[TIPO: Despacho]**
- **[TIPO: Acórdão]**
- **[TIPO: Parecer do NAT/CATES]**
- **[TIPO: Laudo Médico]**
- **[TIPO: Relatório Médico]**
- **[TIPO: Prescrição Médica]**
- **[TIPO: Manifestação do Ministério Público]**
- **[TIPO: Manifestação da Fazenda Pública]**
- **[TIPO: Embargos de Declaração]**
- **[TIPO: Petição Intermediária]**

## DOCUMENTOS IRRELEVANTES - Marcar como [IRRELEVANTE]:
Se o documento for de natureza **meramente administrativa ou acessória**, sem conteúdo substantivo para análise do mérito, responda APENAS:
**[IRRELEVANTE]** Motivo breve.

**EXEMPLOS DE DOCUMENTOS IRRELEVANTES:**
- Procuração (apenas formaliza representação)
- Documentos pessoais (RG, CPF, comprovante de residência)
- Comprovantes de pagamento de custas/taxas
- Guias de recolhimento
- AR de citação/intimação (apenas comprova ciência)
- Certidões de publicação/intimação
- Protocolos de sistema
- Capas, etiquetas, páginas em branco
- Declarações de hipossuficiência
- Comprovantes administrativos diversos

## DOCUMENTOS RELEVANTES - Produzir resumo:

**DOCUMENTOS PRIORITÁRIOS** (resumo detalhado):
- Petição Inicial, Contestação, Recursos, Decisões, Sentenças, Acórdãos
- Parecer do NAT / CATES / NATJus
- Laudos, relatórios e prescrições médicas COM CONTEÚDO CLÍNICO
- Manifestações do MP e da Fazenda Pública
- Despachos com determinações relevantes

## EXTRAIR QUANDO APLICÁVEL:

1. **Partes**: Autor(es) e Réu(s)
2. **Pedido/Objeto**: O que está sendo requerido
3. **Diagnóstico/CID**: Se mencionado
4. **Tratamento solicitado**:
   - Se MEDICAMENTO: nome comercial, princípio ativo, posologia. **VERIFICAR: está incorporado ao SUS? Se sim, em qual componente (Básico/Estratégico/Especializado)?**
   - Se CIRURGIA: qual procedimento, **é urgente?**, de quem é a responsabilidade
5. **Argumentos principais**: Fundamentos apresentados (sem avaliar mérito)
6. **Decisão/Dispositivo**: Se houver, o que foi decidido, prazos e multas
7. **Processo de Origem**: Se for AGRAVO DE INSTRUMENTO, informar o número do processo de origem (1º grau) no formato CNJ (NNNNNNN-NN.NNNN.N.NN.NNNN)

## ATENÇÃO ESPECIAL:

⚠️ **AGRAVO DE INSTRUMENTO**: Identificar e informar OBRIGATORIAMENTE o número do processo de origem (1º grau) no formato CNJ.
⚠️ **PETIÇÃO INICIAL**: Detalhar pedidos, diagnóstico, tratamento solicitado e tutela de urgência.
⚠️ **PARECER NAT/CATES**: Transcrever conclusão sobre incorporação ao SUS, alternativas terapêuticas e recomendação técnica.
⚠️ **CONTESTAÇÃO/RECURSOS**: Listar todas as teses e argumentos apresentados.

Seja fiel ao documento. Não invente informações.

DOCUMENTO:
{texto_documento}"""

        # Prompt padrão para relatório final
        self.prompt_relatorio = prompt_relatorio or """Com base nos resumos dos documentos, elabore um RELATÓRIO ANALÍTICO COMPLETO para subsidiar a elaboração de peça jurídica. O relatório deve ser DETALHADO, EXPOSITIVO e DESCRITIVO, sem juízos de valor sobre o mérito.

## INSTRUÇÕES GERAIS:
- Seja ANALÍTICO: não apenas liste informações, mas DESENVOLVA cada seção em parágrafos explicativos
- Seja COMPLETO: explore todos os detalhes relevantes encontrados nos documentos
- Seja DESCRITIVO: exponha os fatos e argumentos de forma clara e contextualizada
- CONECTE as informações: mostre como os documentos se relacionam entre si
- NÃO seja telegráfico: desenvolva o texto de forma fluida e compreensível

---

## ESTRUTURA DO RELATÓRIO:

### 1. SÍNTESE DO CASO

Apresente uma visão geral do processo em 2-3 parágrafos, contextualizando:
- Quem são as partes (autor e réus)
- Qual o objeto da demanda (o que está sendo pedido e por quê)
- Qual o diagnóstico/condição de saúde do autor
- Qual o contexto fático que originou a ação
- Qual a situação atual do processo

### 2. DO TRATAMENTO SOLICITADO

Desenvolva uma análise detalhada do tratamento requerido:

**Se MEDICAMENTO:**
- Identificação completa: nome comercial, princípio ativo, apresentação, posologia prescrita
- Indicação terapêutica: para que serve e por que foi prescrito ao autor
- Status regulatório: possui registro na ANVISA? Para quais indicações?
- **Análise de incorporação ao SUS**:
  - Está incorporado? Em qual componente (Básico, Estratégico, Especializado)?
  - Para quais CIDs/indicações está incorporado?
  - O caso do autor se enquadra nas indicações cobertas?
  - Existem alternativas terapêuticas disponíveis no SUS? Quais?
- Informações sobre custo, se mencionadas

**Se CIRURGIA/PROCEDIMENTO:**
- Descrição do procedimento solicitado
- Justificativa médica apresentada
- Análise de urgência: o procedimento é urgente/emergencial? Qual a fundamentação?
- Disponibilidade no SUS: está na tabela de procedimentos? Há fila regulada?
- Responsabilidade federativa: de qual ente é a competência para fornecimento?

### 3. ANÁLISE DO PARECER TÉCNICO (NAT/CATES/NATJus)

⚠️ SEÇÃO CRÍTICA - Desenvolver com máximo detalhamento.

[Se houver parecer, desenvolver em parágrafos:]
- Identificação do parecer (número, data, órgão emissor)
- Contextualização: qual foi a pergunta/demanda encaminhada ao NAT
- **Análise técnica apresentada**:
  - O que o parecer conclui sobre a incorporação ao SUS?
  - O que diz sobre a eficácia/evidência científica do tratamento?
  - Quais alternativas terapêuticas são apontadas?
  - Há ressalvas ou condicionantes na conclusão?
- **Transcrição das conclusões principais** (entre aspas, se possível identificar)
- Impacto do parecer para o caso

[Se NÃO houver parecer nos autos:]
Registrar expressamente: "Não foi identificado Parecer do NAT/CATES/NATJus nos documentos analisados. Recomenda-se verificar se há parecer nos autos físicos ou solicitar sua elaboração."

### 4. DA PETIÇÃO INICIAL E PRETENSÃO AUTORAL

Analise detalhadamente a petição inicial:
- Narrativa fática apresentada pelo autor
- Fundamentação jurídica utilizada (quais dispositivos legais, qual a tese)
- Pedidos formulados (listar todos: principal, subsidiários, tutela de urgência)
- Argumentos para a tutela de urgência (se houver): qual o periculum in mora alegado?
- Provas documentais mencionadas/anexadas
- Valor da causa

### 5. DA CONTESTAÇÃO E TESES DEFENSIVAS

[Se houver contestação, desenvolver:]
- Preliminares arguidas: quais são e qual a fundamentação de cada uma
- Mérito: exposição detalhada de cada argumento defensivo apresentado
- Tese sobre responsabilidade federativa (se houver discussão sobre competência)
- Posição técnica sobre o tratamento: o que a defesa argumenta?
- Documentos e provas indicados pela defesa
- Pedidos formulados

[Se não houver contestação: indicar expressamente]

### 6. DOS RECURSOS E CONTRARRAZÕES

[Para cada recurso identificado, desenvolver:]
- Tipo de recurso e recorrente
- Decisão que está sendo impugnada
- Razões recursais: exposição detalhada de cada argumento
- Pedido recursal
- Contrarrazões (se houver): argumentos apresentados em resposta

### 7. DAS DECISÕES JUDICIAIS

Analise cada decisão relevante de forma detalhada:

**Decisões liminares/tutelas de urgência:**
- Data e teor da decisão
- Fundamentação utilizada pelo juízo
- Obrigação imposta: o que foi determinado, a quem, em qual prazo
- Multa/astreintes fixadas
- Status: foi cumprida? Foi reformada?

**Sentença (se houver):**
- Dispositivo: procedência, improcedência ou procedência parcial
- Fundamentação: principais razões de decidir
- Obrigações impostas
- Honorários e custas
- Há recurso pendente?

**Acórdãos (se houver):**
- Resultado do julgamento
- Teses firmadas
- Votos divergentes (se houver)

### 8. MANIFESTAÇÕES DO MINISTÉRIO PÚBLICO

[Se houver, desenvolver:]
- Síntese do parecer ministerial
- Posicionamento sobre o mérito
- Fundamentação apresentada

### 9. SITUAÇÃO ATUAL DO PROCESSO

Desenvolva em parágrafos:
- Em qual fase processual se encontra
- Qual foi a última movimentação relevante
- Há decisão liminar/tutela vigente? Qual a obrigação?
- Há multa em curso ou risco de bloqueio?
- Quais são as pendências processuais
- Próximos passos esperados

### 10. DOCUMENTOS ANALISADOS

Listar todos os documentos que foram objeto de análise:

### 11. DOCUMENTOS NÃO LOCALIZADOS

Indicar documentos importantes que não foram encontrados nos resumos:
- [ ] Parecer do NAT
- [ ] Laudo médico atualizado
- [ ] Comprovante de negativa administrativa
- [ ] Outros: ___

---

*Este relatório foi elaborado com base nos documentos analisados e tem por finalidade subsidiar a elaboração de peça jurídica. As informações devem ser confirmadas nos autos do processo.*

---

RESUMOS DOS DOCUMENTOS PARA ANÁLISE:

{resumos_documentos}"""

    def _obter_gerenciador_json(self):
        """Obtém o gerenciador de formatos JSON (cria se necessário)"""
        if self._gerenciador_json is None and self.db_session is not None:
            from sistemas.gerador_pecas.extrator_resumo_json import GerenciadorFormatosJSON
            self._gerenciador_json = GerenciadorFormatosJSON(self.db_session)
        return self._gerenciador_json

    def _deve_usar_json(self) -> bool:
        """Verifica se deve usar formato JSON para os resumos"""
        if self.formato_saida != "json":
            return False
        gerenciador = self._obter_gerenciador_json()
        return gerenciador is not None and gerenciador.tem_formatos_configurados()

    async def analisar_processo(
        self,
        numero_processo: str,
        ids_documentos: List[str] = None,
        gerar_relatorio: bool = True
    ) -> ResultadoAnalise:
        """
        Analisa processo completo.

        Args:
            numero_processo: Número CNJ do processo
            ids_documentos: Lista de IDs específicos para analisar (opcional)
            gerar_relatorio: Se True, gera relatório final consolidado (opcional)

        Returns:
            ResultadoAnalise com todos os resumos e relatório final
        """
        resultado = ResultadoAnalise(numero_processo=numero_processo)

        # Configura connector com limite de conexões adequado para paralelização
        connector = aiohttp.TCPConnector(limit=self.max_workers + 10, limit_per_host=self.max_workers + 10)
        async with aiohttp.ClientSession(connector=connector) as session:
            try:
                # 1. Consultar processo para obter lista de documentos
                print(f"[1/4] Consultando processo {numero_processo}...")
                xml_consulta = await consultar_processo_async(session, numero_processo)

                if '<sucesso>false</sucesso>' in xml_consulta or '<sucesso>true</sucesso>' not in xml_consulta:
                    # Debug: mostrar parte da resposta para diagnóstico
                    print(f"      ⚠️ Resposta da API (primeiros 500 chars):")
                    print(f"      {xml_consulta[:500]}")
                    resultado.erro_geral = "Processo não encontrado ou erro na consulta"
                    return resultado

                # Extrair dados do processo (partes, valor da causa, etc) - SEM IA
                dados_processo = extrair_dados_processo_xml(xml_consulta)
                if dados_processo:
                    resultado.dados_processo = dados_processo
                    print(f"      Partes extraídas: {len(dados_processo.polo_ativo)} no polo ativo, {len(dados_processo.polo_passivo)} no polo passivo")

                # NOTA: Detecção de agravo e busca de processo de origem foi desativada.
                # O sistema agora trabalha apenas com os documentos do processo informado.

                # 2. Extrair documentos
                print("[2/4] Extraindo lista de documentos...")
                todos_docs = extrair_documentos_xml(xml_consulta)
                print(f"      Encontrados {len(todos_docs)} documentos no processo")

                # Filtrar documentos por IDs específicos (se fornecidos)
                docs_para_analisar = todos_docs

                if ids_documentos:
                    docs_para_analisar = [d for d in docs_para_analisar if d.id in ids_documentos]
                    print(f"      Filtrado para {len(docs_para_analisar)} documentos por ID")
                else:
                    # Filtrar documentos usando códigos permitidos ou filtro legado
                    # Aplica também lógica especial de "primeiro documento" (ex: Petição Inicial)
                    docs_filtrados = []
                    codigos_primeiro_usados = set()  # Rastreia códigos especiais já usados

                    for d in docs_para_analisar:
                        if not d.tipo_documento:
                            continue

                        codigo = int(d.tipo_documento)

                        # Verifica se o documento é permitido
                        if not documento_permitido(codigo, self.codigos_permitidos):
                            continue

                        # Verifica se é código de "primeiro documento" (ex: Petição Inicial)
                        if codigo in self.codigos_primeiro_doc:
                            # Se já pegamos um documento com este código, pula os demais
                            if codigo in codigos_primeiro_usados:
                                continue
                            # Marca como usado
                            codigos_primeiro_usados.add(codigo)

                        docs_filtrados.append(d)

                    docs_para_analisar = docs_filtrados

                    if self.codigos_permitidos:
                        msg_filtro = f"Filtrado para {len(docs_para_analisar)} documentos (categorias configuradas)"
                        if self.codigos_primeiro_doc:
                            msg_filtro += f" | {len(self.codigos_primeiro_doc)} codigos com filtro 'primeiro documento'"
                        print(f"      {msg_filtro}")
                    else:
                        print(f"      Filtrado para {len(docs_para_analisar)} documentos (excluidas categorias administrativas)")

                if not docs_para_analisar:
                    resultado.erro_geral = "Nenhum documento encontrado com os filtros especificados"
                    return resultado

                # Agrupar documentos com mesma descrição/data (partes do mesmo documento)
                docs_agrupados = agrupar_documentos_por_descricao(docs_para_analisar)
                if len(docs_agrupados) < len(docs_para_analisar):
                    print(f"      Agrupados em {len(docs_agrupados)} documentos únicos")

                resultado.documentos = docs_agrupados

                # 3. Baixar conteúdo dos documentos (incluindo todos os IDs agrupados)
                # Coletar todos os IDs que precisamos baixar
                ids_baixar = []
                for doc in docs_agrupados:
                    if doc.ids_agrupados:
                        ids_baixar.extend(doc.ids_agrupados)
                    else:
                        ids_baixar.append(doc.id)

                print(f"[3/4] Baixando {len(ids_baixar)} arquivos...")

                # Baixa em batches para evitar timeout
                conteudo_map = {}
                BATCH_SIZE = 5
                for i in range(0, len(ids_baixar), BATCH_SIZE):
                    batch_ids = ids_baixar[i:i + BATCH_SIZE]
                    print(f"      Baixando batch {i//BATCH_SIZE + 1}/{(len(ids_baixar) + BATCH_SIZE - 1)//BATCH_SIZE}...")

                    xml_conteudo = await baixar_documentos_async(
                        session, numero_processo, batch_ids
                    )

                    # Extrair conteúdos
                    docs_com_conteudo = extrair_documentos_xml(xml_conteudo)
                    for d in docs_com_conteudo:
                        if d.conteudo_base64:
                            conteudo_map[d.id] = d.conteudo_base64

                # Associar conteúdos aos documentos (juntando se agrupados)
                for doc in resultado.documentos:
                    if doc.ids_agrupados:
                        # Documento agrupado - juntar conteúdos
                        conteudos = []
                        for id_parte in doc.ids_agrupados:
                            if id_parte in conteudo_map:
                                conteudos.append(conteudo_map[id_parte])
                        doc.conteudo_base64 = conteudos if conteudos else None
                    else:
                        # Documento único
                        doc.conteudo_base64 = conteudo_map.get(doc.id)

                # Marcar documentos com o número do processo
                for doc in resultado.documentos:
                    doc.numero_processo = numero_processo

                # 4. Processar documentos em PARALELO com controle de concorrência
                print(f"[4/4] Processando documentos em paralelo com IA (max {self.max_workers} simultâneos)...")

                # Criar semáforo para limitar concorrência
                semaphore = asyncio.Semaphore(self.max_workers)
                
                async def processar_com_semaforo(doc):
                    """Wrapper que aplica o semáforo para controlar concorrência"""
                    async with semaphore:
                        await self._processar_documento_async(session, doc)

                # Criar tasks para processamento paralelo
                tasks = []
                for doc in resultado.documentos:
                    if doc.conteudo_base64:
                        task = processar_com_semaforo(doc)
                        tasks.append(task)
                    else:
                        doc.erro = "Documento sem conteúdo disponível"

                # Executar todos em paralelo (limitado pelo semáforo)
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)

                # Contar sucessos
                docs_ok = resultado.documentos_com_resumo()
                docs_irrelevantes = resultado.documentos_irrelevantes()
                docs_erro = resultado.documentos_com_erro()

                print(f"      ✓ {len(docs_ok)} documentos resumidos")
                if docs_irrelevantes:
                    print(f"      ○ {len(docs_irrelevantes)} documentos irrelevantes (ignorados)")
                if docs_erro:
                    print(f"      ✗ {len(docs_erro)} documentos com erro:")
                    for doc in docs_erro:
                        print(f"         - ID {doc.id}: {doc.erro}")

                # NOTA: Busca de documentos do processo de origem foi desativada.
                # O sistema agora trabalha apenas com os documentos do processo informado.
                # A detecção de agravo e busca de origem pode ser reativada futuramente se necessário.

                # 5. Gerar relatório final (se solicitado)
                if gerar_relatorio and resultado.documentos_com_resumo():
                    print(f"\n[5/5] Gerando relatório final consolidado...")
                    resultado.relatorio_final = await self._gerar_relatorio_async(
                        session, resultado
                    )
                    print("      ✓ Relatório gerado!")

            except Exception as e:
                resultado.erro_geral = f"Erro durante análise: {str(e)}"
                print(f"[ERRO] {resultado.erro_geral}")

        return resultado

    async def _buscar_processo_origem(
        self,
        session: aiohttp.ClientSession,
        resultado: ResultadoAnalise,
        numero_processo_origem: str,
        resumos_existentes: set = None
    ):
        """Busca e processa documentos do processo de origem (1º grau)"""
        if resumos_existentes is None:
            resumos_existentes = set()

        try:
            # 1. Consultar processo de origem
            xml_consulta = await consultar_processo_async(session, numero_processo_origem)

            if '<sucesso>false</sucesso>' in xml_consulta or '<sucesso>true</sucesso>' not in xml_consulta:
                print(f"      ⚠ Não foi possível acessar processo de origem")
                return

            # 2. Extrair documentos
            todos_docs = extrair_documentos_xml(xml_consulta)
            print(f"      Encontrados {len(todos_docs)} documentos no processo de origem")

            # Filtrar documentos usando códigos permitidos ou filtro legado
            docs_filtrados = [
                d for d in todos_docs
                if d.tipo_documento and documento_permitido(
                    int(d.tipo_documento),
                    self.codigos_permitidos
                )
            ]

            # Agrupar documentos com mesma descrição/data
            docs_origem = agrupar_documentos_por_descricao(docs_filtrados)
            print(f"      Filtrado para {len(docs_origem)} documentos relevantes")

            if not docs_origem:
                return

            # 3. Baixar conteúdo (incluindo todos os IDs agrupados)
            ids_baixar = []
            for doc in docs_origem:
                if doc.ids_agrupados:
                    ids_baixar.extend(doc.ids_agrupados)
                else:
                    ids_baixar.append(doc.id)

            conteudo_map = {}
            BATCH_SIZE = 5

            for i in range(0, len(ids_baixar), BATCH_SIZE):
                batch_ids = ids_baixar[i:i + BATCH_SIZE]
                xml_conteudo = await baixar_documentos_async(
                    session, numero_processo_origem, batch_ids
                )
                docs_com_conteudo = extrair_documentos_xml(xml_conteudo)
                for d in docs_com_conteudo:
                    if d.conteudo_base64:
                        conteudo_map[d.id] = d.conteudo_base64

            # Associar conteúdos (juntando se agrupados)
            for doc in docs_origem:
                if doc.ids_agrupados:
                    conteudos = [conteudo_map[id_p] for id_p in doc.ids_agrupados if id_p in conteudo_map]
                    doc.conteudo_base64 = conteudos if conteudos else None
                else:
                    doc.conteudo_base64 = conteudo_map.get(doc.id)

            # 4. Marcar como documentos de origem
            for doc in docs_origem:
                doc.processo_origem = True
                doc.numero_processo = numero_processo_origem

            # 5. Processar em paralelo com controle de concorrência
            print(f"      Processando {len(docs_origem)} documentos do 1º grau (max {self.max_workers} simultâneos)...")
            
            # Criar semáforo para limitar concorrência
            semaphore = asyncio.Semaphore(self.max_workers)
            
            async def processar_com_semaforo(doc):
                """Wrapper que aplica o semáforo para controlar concorrência"""
                async with semaphore:
                    await self._processar_documento_async(session, doc)
            
            tasks = []
            for doc in docs_origem:
                if doc.conteudo_base64:
                    task = processar_com_semaforo(doc)
                    tasks.append(task)

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

            # 6. Verificar duplicatas antes de adicionar
            docs_para_adicionar = []
            duplicatas = 0

            for doc in docs_origem:
                if doc.resumo and not doc.irrelevante:
                    # Hash do resumo para comparar
                    hash_resumo = doc.resumo[:200].lower().strip()
                    if hash_resumo in resumos_existentes:
                        doc.irrelevante = True
                        doc.resumo = "Documento duplicado (já analisado no Agravo)"
                        duplicatas += 1
                    else:
                        resumos_existentes.add(hash_resumo)
                docs_para_adicionar.append(doc)

            # Adicionar ao resultado
            resultado.documentos.extend(docs_para_adicionar)

            # Contar
            docs_origem_ok = [d for d in docs_para_adicionar if d.resumo and not d.irrelevante]
            docs_origem_irrel = [d for d in docs_para_adicionar if d.irrelevante]

            print(f"      ✓ {len(docs_origem_ok)} documentos do 1º grau resumidos")
            if duplicatas > 0:
                print(f"      ⊘ {duplicatas} documentos duplicados (já no Agravo)")
            if docs_origem_irrel and (len(docs_origem_irrel) - duplicatas) > 0:
                print(f"      ○ {len(docs_origem_irrel) - duplicatas} documentos irrelevantes")

        except Exception as e:
            print(f"      ⚠ Erro ao buscar processo de origem: {str(e)}")

    def _obter_prompt_json(self, doc: DocumentoTJMS) -> Optional[str]:
        """
        Obtém o prompt de extração JSON apropriado para o documento.
        Retorna None se não houver formatos configurados.
        """
        if not self._deve_usar_json():
            return None
        
        gerenciador = self._obter_gerenciador_json()
        if not gerenciador:
            return None
        
        # Obtém código do documento
        codigo = int(doc.tipo_documento) if doc.tipo_documento else 0
        formato = gerenciador.obter_formato(codigo)
        
        if not formato:
            return None
        
        from sistemas.gerador_pecas.extrator_resumo_json import gerar_prompt_extracao_json
        return gerar_prompt_extracao_json(formato, doc.descricao or "", db=self.db_session)

    def _obter_prompt_json_imagem(self, doc: DocumentoTJMS) -> Optional[str]:
        """
        Obtém o prompt de extração JSON para imagens (PDFs digitalizados).
        """
        if not self._deve_usar_json():
            return None
        
        gerenciador = self._obter_gerenciador_json()
        if not gerenciador:
            return None
        
        codigo = int(doc.tipo_documento) if doc.tipo_documento else 0
        formato = gerenciador.obter_formato(codigo)
        
        if not formato:
            return None
        
        from sistemas.gerador_pecas.extrator_resumo_json import gerar_prompt_extracao_json_imagem
        return gerar_prompt_extracao_json_imagem(formato, db=self.db_session)

    def _processar_resposta_resumo(self, doc: DocumentoTJMS, resposta: str):
        """
        Processa a resposta da IA e atualiza o documento.
        Suporta tanto formato MD quanto JSON.
        """
        if self._deve_usar_json():
            # Processa resposta JSON
            from sistemas.gerador_pecas.extrator_resumo_json import (
                parsear_resposta_json,
                verificar_irrelevante_json,
                extrair_tipo_documento_json,
                extrair_processo_origem_json
            )

            json_dict, erro = parsear_resposta_json(resposta)

            if erro:
                # Fallback: usa resposta como texto se não conseguir parsear JSON
                is_irrelevante, conteudo = _verificar_irrelevante(resposta)
                if is_irrelevante:
                    doc.irrelevante = True
                    doc.resumo = conteudo
                else:
                    doc.resumo = resposta
                    doc.descricao_ia = _extrair_tipo_documento_ia(resposta)
                return

            is_irrelevante, conteudo = verificar_irrelevante_json(json_dict)

            if is_irrelevante:
                doc.irrelevante = True
                doc.resumo = conteudo
            else:
                # Armazena o JSON como string no resumo
                doc.resumo = conteudo  # já é JSON string formatado
                doc.descricao_ia = extrair_tipo_documento_json(json_dict)
                
                # Tenta extrair processo de origem (para Agravos)
                processo_origem = extrair_processo_origem_json(json_dict)
                if processo_origem and hasattr(doc, '_processo_origem_extraido'):
                    doc._processo_origem_extraido = processo_origem
        else:
            # Processa resposta MD (comportamento original)
            is_irrelevante, conteudo = _verificar_irrelevante(resposta)
            if is_irrelevante:
                doc.irrelevante = True
                doc.resumo = conteudo
            else:
                doc.resumo = resposta
                doc.descricao_ia = _extrair_tipo_documento_ia(resposta)

    def _deve_enviar_texto_integral(self, doc: DocumentoTJMS) -> bool:
        """
        Verifica se o documento deve ser enviado com texto INTEGRAL (sem resumo JSON).
        
        Documentos como Parecer NAT/CATES devem ir completos para os agentes seguintes,
        pois seu conteúdo técnico é essencial para a geração da peça.
        
        Para DESATIVAR esta funcionalidade, basta esvaziar CODIGOS_TEXTO_INTEGRAL no topo do arquivo.
        """
        if not CODIGOS_TEXTO_INTEGRAL:
            return False
        
        try:
            codigo = int(doc.tipo_documento) if doc.tipo_documento else 0
            return codigo in CODIGOS_TEXTO_INTEGRAL
        except (ValueError, TypeError):
            return False

    async def _processar_documento_async(
        self,
        session: aiohttp.ClientSession,
        doc: DocumentoTJMS
    ):
        """Processa um documento: extrai texto/imagens e gera resumo"""
        try:
            # Determina se usa formato JSON ou MD
            usar_json = self._deve_usar_json()

            # Verifica se é documento que deve ir INTEGRAL (sem resumo)
            enviar_integral = self._deve_enviar_texto_integral(doc)

            # Verificar se é documento agrupado (lista de conteúdos) ou único
            if isinstance(doc.conteudo_base64, list):
                # Documento agrupado - juntar textos de todas as partes
                textos = []
                todas_imagens = []
                tem_texto = False

                for i, conteudo_b64 in enumerate(doc.conteudo_base64):
                    try:
                        pdf_bytes = base64.b64decode(conteudo_b64)
                        # Executa extração em thread separada para não bloquear event loop
                        conteudo_pdf = await asyncio.to_thread(extrair_conteudo_pdf, pdf_bytes)

                        if conteudo_pdf.tipo == 'texto' and conteudo_pdf.conteudo:
                            textos.append(f"--- PARTE {i+1} ---\n{conteudo_pdf.conteudo}")
                            tem_texto = True
                        elif conteudo_pdf.tipo == 'imagens':
                            todas_imagens.extend(conteudo_pdf.conteudo)
                    except:
                        continue

                if tem_texto:
                    # Juntar todos os textos
                    texto_completo = "\n\n".join(textos)
                    doc.texto_extraido = texto_completo

                    if len(texto_completo.strip()) < 50:
                        doc.erro = "Texto extraído muito curto ou vazio"
                        return

                    # Se é documento que deve ir INTEGRAL, armazena texto completo como resumo
                    if enviar_integral:
                        # Limita a 150000 chars para evitar problemas de contexto
                        texto_integral = texto_completo[:150000]
                        doc.resumo = f"**[DOCUMENTO INTEGRAL - {doc.categoria_nome}]**\n\n{texto_integral}"
                        doc.descricao_ia = doc.descricao or doc.categoria_nome
                        return

                    # Truncar se muito grande
                    texto = texto_completo[:80000]  # Mais espaço para docs agrupados

                    # Gerar resumo via LLM - usa JSON ou MD conforme configurado
                    prompt_json = self._obter_prompt_json(doc)
                    if prompt_json:
                        prompt = prompt_json.format(texto_documento=texto)
                    else:
                        prompt = self.prompt_resumo.format(texto_documento=texto)
                    
                    resposta = await chamar_llm_async(
                        session,
                        prompt=prompt,
                        modelo=self.modelo
                    )

                    self._processar_resposta_resumo(doc, resposta)

                elif todas_imagens:
                    # PDFs digitalizados - enviar imagens
                    doc.texto_extraido = f"[{len(doc.conteudo_base64)} PDFs digitalizados - analisados via visão]"

                    # Limitar número de imagens
                    imagens = todas_imagens[:15]

                    # Usa prompt JSON ou MD conforme configurado
                    prompt_json = self._obter_prompt_json_imagem(doc)
                    prompt_imagem = prompt_json if prompt_json else self._get_prompt_imagem()
                    
                    resposta = await chamar_llm_com_imagens_async(
                        session,
                        prompt=prompt_imagem,
                        imagens_base64=imagens,
                        modelo=self.modelo
                    )

                    self._processar_resposta_resumo(doc, resposta)
                else:
                    doc.erro = "Nenhum conteúdo extraível"

            else:
                # Documento único - processamento normal
                pdf_bytes = base64.b64decode(doc.conteudo_base64)
                # Executa extração em thread separada para não bloquear event loop
                conteudo_pdf = await asyncio.to_thread(extrair_conteudo_pdf, pdf_bytes)

                if conteudo_pdf.tipo == 'texto':
                    doc.texto_extraido = conteudo_pdf.conteudo

                    if not doc.texto_extraido or len(doc.texto_extraido.strip()) < 50:
                        doc.erro = "Texto extraído muito curto ou vazio"
                        return

                    # Se é documento que deve ir INTEGRAL, armazena texto completo como resumo
                    if enviar_integral:
                        # Limita a 150000 chars para evitar problemas de contexto
                        texto_integral = doc.texto_extraido[:150000]
                        doc.resumo = f"**[DOCUMENTO INTEGRAL - {doc.categoria_nome}]**\n\n{texto_integral}"
                        doc.descricao_ia = doc.descricao or doc.categoria_nome
                        return

                    texto = doc.texto_extraido[:50000]

                    # Gerar resumo via LLM - usa JSON ou MD conforme configurado
                    prompt_json = self._obter_prompt_json(doc)
                    if prompt_json:
                        prompt = prompt_json.format(texto_documento=texto)
                    else:
                        prompt = self.prompt_resumo.format(texto_documento=texto)
                    
                    resposta = await chamar_llm_async(
                        session,
                        prompt=prompt,
                        modelo=self.modelo
                    )

                    self._processar_resposta_resumo(doc, resposta)
                else:
                    # PDF digitalizado - enviar imagens para IA
                    imagens = conteudo_pdf.conteudo

                    if not imagens:
                        doc.erro = "PDF digitalizado sem páginas extraíveis"
                        return

                    doc.texto_extraido = f"[PDF digitalizado com {conteudo_pdf.paginas} páginas - analisado via visão]"

                    # Usa prompt JSON ou MD conforme configurado
                    prompt_json = self._obter_prompt_json_imagem(doc)
                    prompt_imagem = prompt_json if prompt_json else self._get_prompt_imagem()
                    
                    resposta = await chamar_llm_com_imagens_async(
                        session,
                        prompt=prompt_imagem,
                        imagens_base64=imagens,
                        modelo=self.modelo
                    )

                    self._processar_resposta_resumo(doc, resposta)

        except Exception as e:
            import traceback
            doc.erro = f"Erro no processamento: {type(e).__name__}: {str(e) or 'sem detalhes'}"

    def _get_prompt_imagem(self) -> str:
        """Retorna o prompt para análise de imagens (formato MD)"""
        return """Analise as imagens deste documento judicial.

## DOCUMENTOS IRRELEVANTES - Marcar como [IRRELEVANTE]:
Se o documento for de natureza **meramente administrativa ou acessória**, responda APENAS:
**[IRRELEVANTE]** Motivo breve.

**EXEMPLOS DE IRRELEVANTES:** Procuração, documentos pessoais (RG, CPF), comprovantes de pagamento, guias, AR de citação, certidões de publicação, protocolos, capas, páginas em branco, declarações de hipossuficiência.

## PARA DOCUMENTOS RELEVANTES, produza resumo contendo:

1. **Tipo de documento**: Identifique (petição, decisão, sentença, parecer, laudo médico, etc.)
2. **Partes envolvidas**: Quem são os autores/réus/interessados mencionados
3. **Objeto/Pedido**: O que está sendo discutido ou pedido
4. **Argumentos principais**: Os fundamentos jurídicos apresentados
5. **Decisão/Conclusão**: Se houver, o que foi decidido
6. **Pontos relevantes**: Fatos ou argumentos importantes
7. **Processo de Origem**: Se for AGRAVO DE INSTRUMENTO, informar o número do processo de origem no formato CNJ

Seja objetivo e técnico. Não invente informações que não estejam no documento."""

    async def _gerar_relatorio_async(
        self,
        session: aiohttp.ClientSession,
        resultado: ResultadoAnalise
    ) -> str:
        """Gera relatório final consolidado"""
        # Montar texto com todos os resumos
        resumos_texto = []
        for i, doc in enumerate(resultado.documentos_com_resumo(), 1):
            resumos_texto.append(f"""
### Documento {i} - {doc.categoria_nome}
**ID**: {doc.id}
**Data**: {doc.data_texto or 'N/A'}

{doc.resumo}

---
""")

        resumos_consolidados = "\n".join(resumos_texto)

        prompt = self.prompt_relatorio.format(resumos_documentos=resumos_consolidados)

        return await chamar_llm_async(
            session,
            prompt=prompt,
            modelo=self.modelo,
            max_tokens=8192
        )


# =========================
# Funções de Exportação
# =========================
def salvar_resultado(
    resultado: ResultadoAnalise,
    pasta_saida: str = "./analise_processo"
) -> Dict[str, str]:
    """
    Salva resultado da análise em arquivos.

    Retorna dict com caminhos dos arquivos gerados.
    """
    pasta = Path(pasta_saida)
    pasta.mkdir(parents=True, exist_ok=True)

    arquivos = {}

    # 1. Salvar arquivo consolidado com todos os resumos
    # Ordena documentos com resumo por data
    docs_ordenados = sorted(
        resultado.documentos_com_resumo(),
        key=lambda d: (d.processo_origem, d.data_juntada or datetime.min)  # Agravo primeiro, depois origem
    )

    if docs_ordenados:
        caminho_consolidado = pasta / "resumos_consolidados.md"

        # Cabeçalho com info de agravo se aplicável
        cabecalho_agravo = ""
        if resultado.is_agravo and resultado.processo_origem:
            cabecalho_agravo = f"""
**⚠️ AGRAVO DE INSTRUMENTO**
**Processo de Origem (1º Grau)**: {resultado.processo_origem}

> **Nota**: Este é um Agravo de Instrumento. Os documentos marcados com [ORIGEM] são do processo de 1º grau.
> A intimação e atuação processual é no Agravo ({resultado.numero_processo}).

"""

        # Separar documentos do AI e da origem
        docs_ai = [d for d in docs_ordenados if not d.processo_origem]
        docs_origem = [d for d in docs_ordenados if d.processo_origem]

        conteudo_consolidado = f"""# Resumos Consolidados

**Processo (Agravo de Instrumento)**: {resultado.numero_processo}
**Data da análise**: {resultado.data_analise.strftime('%d/%m/%Y %H:%M')}
**Total de documentos analisados**: {len(docs_ordenados)}
{cabecalho_agravo}
---

"""
        # Primeiro os documentos do Agravo
        if docs_ai:
            conteudo_consolidado += "# 📋 DOCUMENTOS DO AGRAVO DE INSTRUMENTO\n\n"
            for i, doc in enumerate(docs_ai, 1):
                conteudo_consolidado += f"""## {i}. {doc.categoria_nome}

**ID**: {doc.id}
**Data/Hora**: {doc.data_formatada}

{doc.resumo}

---

"""

        # Depois os documentos da origem (se houver)
        if docs_origem:
            conteudo_consolidado += f"\n# 📁 DOCUMENTOS DO PROCESSO DE ORIGEM ({resultado.processo_origem})\n\n"
            for i, doc in enumerate(docs_origem, 1):
                conteudo_consolidado += f"""## [ORIGEM] {i}. {doc.categoria_nome}

**ID**: {doc.id}
**Data/Hora**: {doc.data_formatada}
**Processo**: {doc.numero_processo}

{doc.resumo}

---

"""

        caminho_consolidado.write_text(conteudo_consolidado, encoding='utf-8')
        arquivos["resumos_consolidados"] = str(caminho_consolidado)

    # 2. Salvar relatório final
    if resultado.relatorio_final:
        caminho_relatorio = pasta / "relatorio_final.md"

        info_agravo = ""
        if resultado.is_agravo and resultado.processo_origem:
            info_agravo = f"\n**Processo de Origem**: {resultado.processo_origem}\n**Tipo**: Agravo de Instrumento"

        conteudo_relatorio = f"""# Relatório de Análise Processual

**Processo**: {resultado.numero_processo}{info_agravo}
**Data da análise**: {resultado.data_analise.strftime('%d/%m/%Y %H:%M')}
**Documentos analisados**: {len(resultado.documentos_com_resumo())}

---

{resultado.relatorio_final}
"""
        caminho_relatorio.write_text(conteudo_relatorio, encoding='utf-8')
        arquivos["relatorio_final"] = str(caminho_relatorio)

    # 3. Salvar índice JSON (ordenado por data)
    docs_ordenados = sorted(
        resultado.documentos,
        key=lambda d: (d.processo_origem, d.data_juntada or datetime.min)
    )

    indice = {
        "numero_processo": resultado.numero_processo,
        "is_agravo": resultado.is_agravo,
        "processo_origem": resultado.processo_origem,
        "data_analise": resultado.data_analise.isoformat(),
        "total_documentos": len(resultado.documentos),
        "documentos_analisados": len(resultado.documentos_com_resumo()),
        "documentos_agravo": len(resultado.documentos_processo_principal()),
        "documentos_origem": len(resultado.documentos_processo_origem()),
        "documentos_irrelevantes": len(resultado.documentos_irrelevantes()),
        "documentos_com_erro": len(resultado.documentos_com_erro()),
        "arquivos_gerados": arquivos,
        "documentos": [
            {
                "id": d.id,
                "tipo": d.tipo_documento,
                "descricao": d.descricao,
                "categoria": d.categoria_nome,
                "data_hora": d.data_formatada,
                "processo": d.numero_processo,
                "processo_origem": d.processo_origem,
                "tem_resumo": bool(d.resumo) and not d.irrelevante,
                "irrelevante": d.irrelevante,
                "motivo_irrelevante": d.resumo if d.irrelevante else None,
                "erro": d.erro
            }
            for d in docs_ordenados
        ]
    }

    caminho_indice = pasta / "indice.json"
    caminho_indice.write_text(json.dumps(indice, indent=2, ensure_ascii=False), encoding='utf-8')
    arquivos["indice"] = str(caminho_indice)

    return arquivos


# =========================
# Função Principal (CLI Interativo)
# =========================
async def analisar_um_processo():
    """Analisa um único processo - retorna True se deve continuar"""

    numero_processo = input("\n📋 Digite o número do processo (formato CNJ): ").strip()

    if not numero_processo:
        print("\n❌ Erro: O número do processo é obrigatório")
        return True  # Continua para perguntar outro

    # Perguntar se quer gerar relatório final
    gerar_relatorio = input("\n📝 Deseja gerar o relatório final consolidado? (s/N): ").strip().lower()
    gerar_relatorio = gerar_relatorio in ['s', 'sim', 'y', 'yes']

    # Criar agente
    agente = AgenteTJMS(
        modelo=MODELO_PADRAO,
        max_workers=10
    )

    # Executar análise
    print(f"\n🚀 Iniciando análise do processo {numero_processo}\n")
    print("=" * 60)

    resultado = await agente.analisar_processo(numero_processo, gerar_relatorio=gerar_relatorio)

    print("=" * 60)

    # Verificar erros
    if resultado.erro_geral:
        print(f"\n❌ Erro: {resultado.erro_geral}")
        return True  # Continua para perguntar outro

    # Salvar resultados na pasta resultados/<numero_processo>
    pasta_saida = f"./resultados/{numero_processo}"
    arquivos = salvar_resultado(resultado, pasta_saida)

    # Mostrar resumo
    print(f"\n✅ Análise concluída!")

    # Info de Agravo
    if resultado.is_agravo:
        print(f"\n⚖️  AGRAVO DE INSTRUMENTO")
        print(f"   Processo de origem: {resultado.processo_origem}")

    print(f"\n📊 Estatísticas:")
    print(f"   - Total de documentos: {len(resultado.documentos)}")
    print(f"   - Documentos analisados: {len(resultado.documentos_com_resumo())}")

    if resultado.is_agravo:
        docs_ai = resultado.documentos_processo_principal()
        docs_origem = resultado.documentos_processo_origem()
        print(f"      • Do Agravo: {len(docs_ai)}")
        print(f"      • Da Origem (1º grau): {len(docs_origem)}")

    irrelevantes = resultado.documentos_irrelevantes()
    if irrelevantes:
        print(f"   - Documentos irrelevantes: {len(irrelevantes)}")

    erros = resultado.documentos_com_erro()
    if erros:
        print(f"   - Documentos com erro: {len(erros)}")

    print(f"\n📁 Arquivos gerados em: {pasta_saida}")
    for nome, caminho in arquivos.items():
        print(f"   - {Path(caminho).name}")

    return True


async def main_interativo():
    """Execução interativa - loop principal"""

    print("\n🔍 Agente de Análise de Documentos do TJ-MS")
    print("=" * 50)

    while True:
        await analisar_um_processo()

        # Perguntar se quer analisar outro processo
        print("\n" + "-" * 50)
        continuar = input("\n🔄 Deseja analisar outro processo? (S/n): ").strip().lower()

        if continuar in ['n', 'nao', 'não', 'no']:
            print("\n👋 Até logo!")
            break

        print("\n" + "=" * 50)


if __name__ == "__main__":
    asyncio.run(main_interativo())
