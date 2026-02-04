# sistemas/relatorio_cumprimento/agravo_detector.py
"""
Detector de Agravo de Instrumento no Processo de Origem

Este módulo implementa a detecção e validação de Agravos de Instrumento
relacionados ao processo de origem em cumprimentos de sentença autônomos.

Fluxo:
1. Extrai candidatos a agravo do XML do processo de origem
2. Baixa o XML de cada agravo candidato
3. Compara as partes para validar se pertence ao processo
4. Baixa decisões e acórdãos dos agravos validados

Autor: LAB/PGE-MS
"""

import re
import unicodedata
import logging
from datetime import date
from typing import List, Optional, Tuple, Dict, Any
import xml.etree.ElementTree as ET

from utils.security import safe_parse_xml

from .models import (
    AgravoCandidato,
    AgravoValidado,
    ParteProcesso,
    ResultadoDeteccaoAgravo,
    CategoriaDocumento,
    DocumentoClassificado
)

# Cliente TJMS unificado (adaptador compativel)
from services.tjms import DocumentDownloader

# Parser de XML do pedido_calculo (reutilizado para tipos de documento)
from sistemas.pedido_calculo.xml_parser import XMLParser, TIPOS_DOCUMENTO


logger = logging.getLogger(__name__)


# ============================================
# Configuração de Retry
# ============================================

MAX_RETRIES = 3
RETRY_DELAY_BASE = 2  # segundos (backoff exponencial: 2, 4, 8)


async def _retry_async(
    func,
    *args,
    max_retries: int = MAX_RETRIES,
    delay_base: float = RETRY_DELAY_BASE,
    request_id: Optional[str] = None,
    operation_name: str = "operação",
    **kwargs
):
    """
    Executa função assíncrona com retry e backoff exponencial.

    Args:
        func: Função assíncrona a executar
        *args: Argumentos posicionais
        max_retries: Número máximo de tentativas
        delay_base: Delay base em segundos (será multiplicado exponencialmente)
        request_id: ID da requisição para logs
        operation_name: Nome da operação para logs
        **kwargs: Argumentos nomeados

    Returns:
        Resultado da função

    Raises:
        Exception: Se todas as tentativas falharem
    """
    import asyncio
    log_prefix = f"[{request_id}] " if request_id else ""
    last_exception = None

    for attempt in range(max_retries):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            error_msg = str(e)

            # Verifica se é erro recuperável (502, 503, timeout, etc.)
            is_recoverable = any(code in error_msg for code in ['502', '503', '504', 'timeout', 'Proxy'])

            if not is_recoverable or attempt >= max_retries - 1:
                # Erro não recuperável ou última tentativa
                raise

            # Calcula delay com backoff exponencial
            delay = delay_base * (2 ** attempt)
            logger.warning(
                f"{log_prefix}Tentativa {attempt + 1}/{max_retries} de {operation_name} falhou: {error_msg[:100]}. "
                f"Aguardando {delay}s antes de retry..."
            )
            await asyncio.sleep(delay)

    raise last_exception


# ============================================
# Constantes e Padrões
# ============================================

# Regex para número CNJ: NNNNNNN-NN.NNNN.N.NN.NNNN
# Captura números no formato padrão CNJ
REGEX_NUMERO_CNJ = re.compile(
    r'(\d{7}[-.]?\d{2}[.-]?\d{4}[.-]?\d[.-]?\d{2}[.-]?\d{4})'
)

# Padrões textuais para detectar referência a Agravo de Instrumento
# Tolerante a variações de caixa, acentos e pontuação
PADROES_AGRAVO = [
    r'agravo\s+de\s+instrumento',
    r'agravo\s+instrumento',
    r'ag[\.\s]*inst[\.]?',
    r'ai\s*[-:]\s*\d',  # AI - 1234567...
]


# ============================================
# Funções de Normalização
# ============================================

def normalize_text(texto: str) -> str:
    """
    Normaliza texto para comparação.

    Regras aplicadas:
    - Converte para maiúsculas
    - Remove acentos
    - Remove pontuação
    - Remove múltiplos espaços
    - Aplica trim

    Args:
        texto: Texto original

    Returns:
        Texto normalizado
    """
    if not texto:
        return ""

    # Converte para maiúsculas
    texto = texto.upper()

    # Remove acentos usando NFD (decompõe caracteres acentuados)
    texto = unicodedata.normalize('NFD', texto)
    texto = ''.join(c for c in texto if unicodedata.category(c) != 'Mn')

    # Remove pontuação (mantém apenas letras, números e espaços)
    texto = re.sub(r'[^\w\s]', ' ', texto)

    # Remove múltiplos espaços
    texto = re.sub(r'\s+', ' ', texto)

    # Trim
    texto = texto.strip()

    return texto


def normalize_numero_cnj(numero: str) -> str:
    """
    Normaliza número CNJ removendo pontuação.

    Args:
        numero: Número CNJ com ou sem formatação

    Returns:
        Número CNJ apenas com dígitos (20 caracteres)
    """
    if not numero:
        return ""
    return re.sub(r'\D', '', numero)


def format_numero_cnj(numero: str) -> str:
    """
    Formata número CNJ para padrão NNNNNNN-NN.NNNN.N.NN.NNNN

    Args:
        numero: Número CNJ (apenas dígitos ou já formatado)

    Returns:
        Número formatado ou original se inválido
    """
    numero_limpo = normalize_numero_cnj(numero)
    if len(numero_limpo) == 20:
        return f"{numero_limpo[:7]}-{numero_limpo[7:9]}.{numero_limpo[9:13]}.{numero_limpo[13]}.{numero_limpo[14:16]}.{numero_limpo[16:]}"
    return numero


# ============================================
# Funções de Extração
# ============================================

def _get_tag_name(elem: ET.Element) -> str:
    """Retorna nome da tag sem namespace"""
    return elem.tag.split('}')[-1].lower() if '}' in elem.tag else elem.tag.lower()


def _parse_date_tjms(s: Optional[str]) -> Optional[date]:
    """Parse de data no formato TJ-MS: YYYYMMDD ou YYYYMMDDHHMMSS"""
    if not s or len(s) < 8:
        return None
    try:
        from datetime import datetime
        if len(s) >= 14:
            return datetime.strptime(s[:14], "%Y%m%d%H%M%S").date()
        elif len(s) >= 8:
            return datetime.strptime(s[:8], "%Y%m%d").date()
    except ValueError:
        pass
    return None


def _texto_contem_agravo(texto: str) -> bool:
    """
    Verifica se texto contém referência a Agravo de Instrumento.

    Tolerante a variações de:
    - Caixa (maiúsculas/minúsculas)
    - Acentos
    - Pontuação
    - Múltiplos espaços

    Args:
        texto: Texto a verificar

    Returns:
        True se contém referência a agravo
    """
    if not texto:
        return False

    # Normaliza o texto para busca
    texto_normalizado = normalize_text(texto).lower()

    for padrao in PADROES_AGRAVO:
        if re.search(padrao, texto_normalizado, re.IGNORECASE):
            return True

    return False


def _extrair_numeros_cnj(texto: str) -> List[str]:
    """
    Extrai todos os números CNJ de um texto.

    Args:
        texto: Texto contendo possíveis números CNJ

    Returns:
        Lista de números CNJ encontrados (normalizados)
    """
    if not texto:
        return []

    # Remove quebras de linha e múltiplos espaços
    texto_limpo = re.sub(r'\s+', ' ', texto)

    # Encontra todos os matches do padrão CNJ
    matches = REGEX_NUMERO_CNJ.findall(texto_limpo)

    # Normaliza e deduplica
    numeros = []
    vistos = set()
    for match in matches:
        numero = normalize_numero_cnj(match)
        if len(numero) == 20 and numero not in vistos:
            numeros.append(numero)
            vistos.add(numero)

    return numeros


def extract_agravo_candidates_from_xml(
    xml_texto: str,
    request_id: Optional[str] = None
) -> List[AgravoCandidato]:
    """
    Extrai candidatos a Agravo de Instrumento do XML do processo de origem.

    Analisa movimentos e complementos buscando referências textuais a
    "Agravo de Instrumento" e extrai números CNJ associados.

    Args:
        xml_texto: XML completo do processo de origem
        request_id: ID da requisição para logs

    Returns:
        Lista de candidatos a agravo detectados
    """
    candidatos = []
    numeros_vistos = set()  # Evita duplicatas

    log_prefix = f"[{request_id}] " if request_id else ""

    try:
        root = safe_parse_xml(xml_texto)

        # Percorre todos os movimentos
        for elem in root.iter():
            tag = _get_tag_name(elem)

            if tag == 'movimento':
                data_movimento = _parse_date_tjms(elem.attrib.get('dataHora'))

                # Verifica complemento do movimento
                for child in elem:
                    child_tag = _get_tag_name(child)

                    if child_tag == 'complemento' and child.text:
                        texto = child.text

                        # Verifica se menciona agravo de instrumento
                        if _texto_contem_agravo(texto):
                            # Extrai números CNJ do texto
                            numeros = _extrair_numeros_cnj(texto)

                            for numero in numeros:
                                if numero not in numeros_vistos:
                                    numeros_vistos.add(numero)
                                    candidato = AgravoCandidato(
                                        numero_cnj=numero,
                                        texto_original=texto.strip(),
                                        fonte="movimento",
                                        data_movimento=data_movimento
                                    )
                                    candidatos.append(candidato)
                                    logger.info(
                                        f"{log_prefix}Agravo candidato detectado: {format_numero_cnj(numero)} "
                                        f"(fonte: movimento, data: {data_movimento})"
                                    )

        logger.info(
            f"{log_prefix}Detecção de agravo concluída: {len(candidatos)} candidato(s) encontrado(s)"
        )

    except Exception as e:
        logger.error(f"{log_prefix}Erro ao extrair candidatos de agravo: {e}")

    return candidatos


# ============================================
# Funções de Validação por Partes
# ============================================

def _extrair_partes_do_xml(xml_texto: str) -> Tuple[List[ParteProcesso], List[ParteProcesso]]:
    """
    Extrai partes (polo ativo e passivo) do XML do processo.

    Args:
        xml_texto: XML completo do processo

    Returns:
        Tupla (partes_polo_ativo, partes_polo_passivo)
    """
    partes_ativas = []
    partes_passivas = []

    try:
        root = safe_parse_xml(xml_texto)

        # Busca elemento dadosBasicos
        for elem in root.iter():
            tag = _get_tag_name(elem)

            if tag == 'dadosbasicos':
                # Busca polos
                for polo_elem in elem.iter():
                    if _get_tag_name(polo_elem) != 'polo':
                        continue

                    tipo_polo = polo_elem.attrib.get('polo', '')

                    for parte_elem in polo_elem.iter():
                        if _get_tag_name(parte_elem) != 'parte':
                            continue

                        for pessoa_elem in parte_elem.iter():
                            if _get_tag_name(pessoa_elem) != 'pessoa':
                                continue

                            nome = pessoa_elem.attrib.get('nome', '')
                            if not nome:
                                continue

                            # Busca documento (CPF/CNPJ)
                            documento = None
                            for doc_elem in pessoa_elem.iter():
                                if _get_tag_name(doc_elem) == 'documento':
                                    codigo = doc_elem.attrib.get('codigoDocumento', '')
                                    if codigo:
                                        documento = re.sub(r'\D', '', codigo)
                                        break

                            parte = ParteProcesso(
                                nome=nome,
                                nome_normalizado=normalize_text(nome),
                                polo=tipo_polo,
                                documento=documento
                            )

                            if tipo_polo == 'AT':
                                partes_ativas.append(parte)
                            elif tipo_polo == 'PA':
                                partes_passivas.append(parte)

                break  # Só precisa do primeiro dadosBasicos

    except Exception as e:
        logger.error(f"Erro ao extrair partes do XML: {e}")

    return partes_ativas, partes_passivas


def _calcular_similaridade_nome(nome1: str, nome2: str) -> float:
    """
    Calcula similaridade entre dois nomes normalizados.

    Usa comparação de tokens (palavras) para tolerância a variações.

    Args:
        nome1: Primeiro nome (já normalizado)
        nome2: Segundo nome (já normalizado)

    Returns:
        Score de similaridade entre 0 e 1
    """
    if not nome1 or not nome2:
        return 0.0

    # Divide em tokens
    tokens1 = set(nome1.split())
    tokens2 = set(nome2.split())

    # Remove tokens muito curtos (preposições, artigos)
    tokens1 = {t for t in tokens1 if len(t) > 2}
    tokens2 = {t for t in tokens2 if len(t) > 2}

    if not tokens1 or not tokens2:
        return 0.0

    # Calcula interseção
    intersecao = tokens1 & tokens2
    uniao = tokens1 | tokens2

    # Jaccard similarity
    return len(intersecao) / len(uniao) if uniao else 0.0


def compare_parties(
    partes_origem_ativas: List[ParteProcesso],
    partes_origem_passivas: List[ParteProcesso],
    partes_agravo_ativas: List[ParteProcesso],
    partes_agravo_passivas: List[ParteProcesso],
    request_id: Optional[str] = None
) -> Tuple[bool, float, str]:
    """
    Compara partes do processo de origem com partes do agravo.

    Critério de validação:
    - Deve haver correspondência consistente entre as partes principais
      do polo ativo e do polo passivo.

    Em agravos, os polos podem estar invertidos (agravante/agravado),
    então verifica ambas as combinações.

    Args:
        partes_origem_ativas: Partes do polo ativo do processo de origem
        partes_origem_passivas: Partes do polo passivo do processo de origem
        partes_agravo_ativas: Partes do polo ativo do agravo
        partes_agravo_passivas: Partes do polo passivo do agravo
        request_id: ID da requisição para logs

    Returns:
        Tupla (validado, score, motivo)
        - validado: True se agravo pertence ao processo
        - score: Score de similaridade (0 a 1)
        - motivo: Descrição do resultado
    """
    log_prefix = f"[{request_id}] " if request_id else ""

    # Threshold mínimo para considerar match
    THRESHOLD_SIMILARIDADE = 0.5

    if not partes_origem_ativas and not partes_origem_passivas:
        return False, 0.0, "Processo de origem sem partes identificadas"

    if not partes_agravo_ativas and not partes_agravo_passivas:
        return False, 0.0, "Agravo sem partes identificadas"

    # Tenta match direto (mesmo polo)
    score_direto = _calcular_match_partes(
        partes_origem_ativas, partes_origem_passivas,
        partes_agravo_ativas, partes_agravo_passivas
    )

    # Tenta match invertido (polos trocados - comum em agravos)
    score_invertido = _calcular_match_partes(
        partes_origem_ativas, partes_origem_passivas,
        partes_agravo_passivas, partes_agravo_ativas
    )

    # Usa o melhor score
    score = max(score_direto, score_invertido)
    tipo_match = "direto" if score_direto >= score_invertido else "invertido"

    logger.info(
        f"{log_prefix}Comparação de partes: score_direto={score_direto:.2f}, "
        f"score_invertido={score_invertido:.2f}, melhor={score:.2f} ({tipo_match})"
    )

    if score >= THRESHOLD_SIMILARIDADE:
        return True, score, f"Match {tipo_match} com score {score:.2f}"
    else:
        return False, score, f"Score insuficiente ({score:.2f} < {THRESHOLD_SIMILARIDADE})"


def _calcular_match_partes(
    origem_ativas: List[ParteProcesso],
    origem_passivas: List[ParteProcesso],
    agravo_ativas: List[ParteProcesso],
    agravo_passivas: List[ParteProcesso]
) -> float:
    """
    Calcula score de match entre partes de dois processos.

    Args:
        origem_ativas: Partes ativas do processo de origem
        origem_passivas: Partes passivas do processo de origem
        agravo_ativas: Partes ativas do agravo
        agravo_passivas: Partes passivas do agravo

    Returns:
        Score médio de similaridade (0 a 1)
    """
    scores = []

    # Compara polo ativo
    if origem_ativas and agravo_ativas:
        for parte_origem in origem_ativas:
            melhor_score = 0.0
            for parte_agravo in agravo_ativas:
                # Primeiro tenta por documento (mais confiável)
                if parte_origem.documento and parte_agravo.documento:
                    if parte_origem.documento == parte_agravo.documento:
                        melhor_score = 1.0
                        break

                # Se não tem documento, usa nome
                score = _calcular_similaridade_nome(
                    parte_origem.nome_normalizado,
                    parte_agravo.nome_normalizado
                )
                melhor_score = max(melhor_score, score)

            scores.append(melhor_score)

    # Compara polo passivo
    if origem_passivas and agravo_passivas:
        for parte_origem in origem_passivas:
            melhor_score = 0.0
            for parte_agravo in agravo_passivas:
                # Primeiro tenta por documento
                if parte_origem.documento and parte_agravo.documento:
                    if parte_origem.documento == parte_agravo.documento:
                        melhor_score = 1.0
                        break

                # Se não tem documento, usa nome
                score = _calcular_similaridade_nome(
                    parte_origem.nome_normalizado,
                    parte_agravo.nome_normalizado
                )
                melhor_score = max(melhor_score, score)

            scores.append(melhor_score)

    return sum(scores) / len(scores) if scores else 0.0


# ============================================
# Funções de Busca de Documentos
# ============================================

def _identificar_documentos_agravo(xml_texto: str) -> Tuple[List[str], List[str]]:
    """
    Identifica IDs de decisões e acórdãos no XML do agravo.

    Args:
        xml_texto: XML completo do agravo

    Returns:
        Tupla (ids_decisoes, ids_acordaos)
    """
    ids_decisoes = []
    ids_acordaos = []

    try:
        root = safe_parse_xml(xml_texto)

        for elem in root.iter():
            tag = _get_tag_name(elem)

            if tag == 'documento':
                doc_id = elem.attrib.get('idDocumento', elem.attrib.get('id', ''))
                tipo = elem.attrib.get('tipoDocumentoLocal', elem.attrib.get('tipoDocumento', ''))

                if not doc_id:
                    continue

                # Verifica se é decisão
                if tipo in TIPOS_DOCUMENTO.get("DECISAO", []):
                    ids_decisoes.append(doc_id)

                # Verifica se é acórdão
                if tipo in TIPOS_DOCUMENTO.get("ACORDAO", []):
                    ids_acordaos.append(doc_id)

    except Exception as e:
        logger.error(f"Erro ao identificar documentos do agravo: {e}")

    return ids_decisoes, ids_acordaos


# ============================================
# Função Principal de Validação
# ============================================

async def fetch_and_validate_agravo(
    candidato: AgravoCandidato,
    partes_origem_ativas: List[ParteProcesso],
    partes_origem_passivas: List[ParteProcesso],
    downloader: DocumentDownloader,
    request_id: Optional[str] = None
) -> Tuple[Optional[AgravoValidado], Optional[Dict[str, Any]]]:
    """
    Baixa XML do agravo candidato e valida por comparação de partes.

    Args:
        candidato: Agravo candidato a validar
        partes_origem_ativas: Partes do polo ativo do processo de origem
        partes_origem_passivas: Partes do polo passivo do processo de origem
        downloader: Instância do DocumentDownloader
        request_id: ID da requisição para logs

    Returns:
        Tupla (agravo_validado ou None, info_rejeicao ou None)
    """
    log_prefix = f"[{request_id}] " if request_id else ""
    numero_formatado = format_numero_cnj(candidato.numero_cnj)

    try:
        logger.info(f"{log_prefix}Validando agravo candidato: {numero_formatado}")

        # 1. Baixa XML do agravo (com retry para erros de proxy)
        try:
            xml_agravo = await _retry_async(
                downloader.consultar_processo,
                candidato.numero_cnj,
                request_id=request_id,
                operation_name=f"baixar XML do agravo {numero_formatado}"
            )
        except Exception as e:
            motivo = f"Erro ao baixar XML do agravo (após {MAX_RETRIES} tentativas): {str(e)}"
            logger.warning(f"{log_prefix}{motivo}")
            return None, {
                "candidato": candidato.to_dict(),
                "motivo": motivo
            }

        # 2. Extrai partes do agravo
        partes_agravo_ativas, partes_agravo_passivas = _extrair_partes_do_xml(xml_agravo)

        logger.info(
            f"{log_prefix}Partes do agravo: "
            f"{len(partes_agravo_ativas)} ativas, {len(partes_agravo_passivas)} passivas"
        )

        # 3. Compara partes
        validado, score, motivo = compare_parties(
            partes_origem_ativas,
            partes_origem_passivas,
            partes_agravo_ativas,
            partes_agravo_passivas,
            request_id
        )

        if not validado:
            logger.info(f"{log_prefix}Agravo {numero_formatado} rejeitado: {motivo}")
            return None, {
                "candidato": candidato.to_dict(),
                "motivo": motivo,
                "score": score,
                "partes_agravo_ativas": [p.to_dict() for p in partes_agravo_ativas],
                "partes_agravo_passivas": [p.to_dict() for p in partes_agravo_passivas]
            }

        # 4. Identifica documentos do agravo
        ids_decisoes, ids_acordaos = _identificar_documentos_agravo(xml_agravo)

        logger.info(
            f"{log_prefix}Agravo {numero_formatado} validado! "
            f"Score: {score:.2f}, Decisões: {len(ids_decisoes)}, Acórdãos: {len(ids_acordaos)}"
        )

        # 5. Cria objeto de agravo validado
        agravo = AgravoValidado(
            numero_cnj=candidato.numero_cnj,
            numero_formatado=numero_formatado,
            partes_polo_ativo=partes_agravo_ativas,
            partes_polo_passivo=partes_agravo_passivas,
            ids_decisoes=ids_decisoes,
            ids_acordaos=ids_acordaos,
            data_validacao=date.today(),
            score_similaridade=score
        )

        return agravo, None

    except Exception as e:
        motivo = f"Erro inesperado ao validar agravo: {str(e)}"
        logger.error(f"{log_prefix}{motivo}")
        return None, {
            "candidato": candidato.to_dict(),
            "motivo": motivo
        }


async def fetch_agravo_documents(
    agravo: AgravoValidado,
    downloader: DocumentDownloader,
    request_id: Optional[str] = None
) -> List[DocumentoClassificado]:
    """
    Baixa documentos (decisões e acórdãos) de um agravo validado.

    Args:
        agravo: Agravo validado com IDs de documentos
        downloader: Instância do DocumentDownloader
        request_id: ID da requisição para logs

    Returns:
        Lista de DocumentoClassificado do agravo
    """
    log_prefix = f"[{request_id}] " if request_id else ""
    documentos = []

    try:
        # Coleta todos os IDs
        ids_para_baixar = agravo.ids_decisoes + agravo.ids_acordaos

        if not ids_para_baixar:
            logger.info(f"{log_prefix}Agravo {agravo.numero_formatado} não tem documentos para baixar")
            return documentos

        # Baixa textos (com retry para erros de proxy)
        textos = await _retry_async(
            downloader.baixar_e_extrair_textos,
            agravo.numero_cnj,
            ids_para_baixar,
            request_id=request_id,
            operation_name=f"baixar documentos do agravo {agravo.numero_formatado}"
        )

        # Processa decisões
        for i, id_decisao in enumerate(agravo.ids_decisoes, 1):
            if id_decisao in textos:
                doc = DocumentoClassificado(
                    id_documento=id_decisao,
                    categoria=CategoriaDocumento.DECISAO_AGRAVO,
                    nome_original=f"Decisão do Agravo {agravo.numero_formatado}",
                    nome_padronizado=f"06_decisao_agravo_{i:02d}.pdf",
                    processo_origem="agravo_instrumento",
                    conteudo_texto=textos[id_decisao],
                    descricao=f"Decisão do Agravo de Instrumento {agravo.numero_formatado}"
                )
                documentos.append(doc)

        # Processa acórdãos
        for i, id_acordao in enumerate(agravo.ids_acordaos, 1):
            if id_acordao in textos:
                doc = DocumentoClassificado(
                    id_documento=id_acordao,
                    categoria=CategoriaDocumento.ACORDAO_AGRAVO,
                    nome_original=f"Acórdão do Agravo {agravo.numero_formatado}",
                    nome_padronizado=f"07_acordao_agravo_{i:02d}.pdf",
                    processo_origem="agravo_instrumento",
                    conteudo_texto=textos[id_acordao],
                    descricao=f"Acórdão do Agravo de Instrumento {agravo.numero_formatado}"
                )
                documentos.append(doc)

        logger.info(
            f"{log_prefix}Baixados {len(documentos)} documentos do agravo {agravo.numero_formatado}"
        )

    except Exception as e:
        logger.error(f"{log_prefix}Erro ao baixar documentos do agravo: {e}")

    return documentos


# ============================================
# Função Orquestradora Principal
# ============================================

async def detect_and_validate_agravos(
    xml_processo_origem: str,
    request_id: Optional[str] = None
) -> ResultadoDeteccaoAgravo:
    """
    Detecta e valida Agravos de Instrumento do processo de origem.

    Pipeline completo:
    1. Extrai candidatos a agravo do XML
    2. Para cada candidato, baixa XML e valida por partes
    3. Para agravos validados, identifica documentos

    Args:
        xml_processo_origem: XML do processo de origem (conhecimento)
        request_id: ID da requisição para logs estruturados

    Returns:
        ResultadoDeteccaoAgravo com candidatos, validados e rejeitados
    """
    log_prefix = f"[{request_id}] " if request_id else ""
    resultado = ResultadoDeteccaoAgravo()

    try:
        # 1. Extrai candidatos
        candidatos = extract_agravo_candidates_from_xml(xml_processo_origem, request_id)
        resultado.candidatos_detectados = candidatos

        if not candidatos:
            logger.info(f"{log_prefix}Nenhum agravo candidato detectado no processo de origem")
            return resultado

        # 2. Extrai partes do processo de origem para comparação
        partes_origem_ativas, partes_origem_passivas = _extrair_partes_do_xml(xml_processo_origem)

        logger.info(
            f"{log_prefix}Partes do processo de origem: "
            f"{len(partes_origem_ativas)} ativas, {len(partes_origem_passivas)} passivas"
        )

        # Log estruturado
        logger.info(
            f"{log_prefix}AGRAVO_DETECTION | "
            f"candidatos={len(candidatos)} | "
            f"partes_ativas={len(partes_origem_ativas)} | "
            f"partes_passivas={len(partes_origem_passivas)}"
        )

        # 3. Valida cada candidato
        async with DocumentDownloader() as downloader:
            for candidato in candidatos:
                agravo_validado, info_rejeicao = await fetch_and_validate_agravo(
                    candidato,
                    partes_origem_ativas,
                    partes_origem_passivas,
                    downloader,
                    request_id
                )

                if agravo_validado:
                    resultado.agravos_validados.append(agravo_validado)
                elif info_rejeicao:
                    resultado.agravos_rejeitados.append(info_rejeicao)

        # Log final estruturado
        logger.info(
            f"{log_prefix}AGRAVO_VALIDATION_COMPLETE | "
            f"candidatos={len(resultado.candidatos_detectados)} | "
            f"validados={len(resultado.agravos_validados)} | "
            f"rejeitados={len(resultado.agravos_rejeitados)}"
        )

    except Exception as e:
        resultado.erro = f"Erro na detecção de agravos: {str(e)}"
        logger.error(f"{log_prefix}{resultado.erro}")

    return resultado


async def fetch_all_agravo_documents(
    agravos_validados: List[AgravoValidado],
    request_id: Optional[str] = None
) -> List[DocumentoClassificado]:
    """
    Baixa documentos de todos os agravos validados.

    Args:
        agravos_validados: Lista de agravos validados
        request_id: ID da requisição para logs

    Returns:
        Lista consolidada de DocumentoClassificado
    """
    log_prefix = f"[{request_id}] " if request_id else ""
    todos_documentos = []

    if not agravos_validados:
        return todos_documentos

    async with DocumentDownloader() as downloader:
        for agravo in agravos_validados:
            documentos = await fetch_agravo_documents(agravo, downloader, request_id)
            todos_documentos.extend(documentos)

    logger.info(
        f"{log_prefix}Total de documentos de agravos: {len(todos_documentos)} "
        f"({sum(len(a.ids_decisoes) for a in agravos_validados)} decisões, "
        f"{sum(len(a.ids_acordaos) for a in agravos_validados)} acórdãos)"
    )

    return todos_documentos
