# sistemas/pedido_calculo/xml_parser.py
"""
Parser de XML do processo judicial (padrão MNI/CNJ)

Este módulo extrai dados do XML retornado pela API SOAP do TJ-MS,
identificando:
- Dados básicos do processo (partes, comarca, vara, etc.)
- Movimentos relevantes (citação, trânsito em julgado, intimações)
- Documentos para download (sentenças, acórdãos, certidões, etc.)

Autor: LAB/PGE-MS
"""

import re
import xml.etree.ElementTree as ET
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Any, Tuple

from utils.security import safe_parse_xml

from .models import (
    DadosBasicos,
    DocumentosParaDownload,
    MovimentosRelevantes,
    CertidaoCitacaoIntimacao,
    CertidaoCandidata,
    TipoIntimacao,
    DocumentoCumprimento
)


# Códigos de tipos de documento relevantes
TIPOS_DOCUMENTO = {
    # Sentenças (originais e cópias)
    "SENTENCA": ["8", "9626"],
    "SENTENCA_JUIZ_LEIGO": ["54"],
    "COPIA_SENTENCA": ["9557"],  # Cópia de sentença (em cumprimentos autônomos)

    # Acórdãos (originais e cópias)
    "ACORDAO": ["37", "202", "34", "35"],
    "COPIA_ACORDAO": ["9555"],  # Cópia de acórdão (em cumprimentos autônomos)

    # Certidões
    "CERTIDAO_SISTEMA": ["9508"],
    "CERTIDAO_CARTORIO": ["13"],
    "CERTIDAO_TRANSITO": ["9644"],  # Cópia de certidão de trânsito em julgado

    # Petições (exemplificativo)
    "PETICAO": ["9500", "9501"],
    "PLANILHA_CALCULO": ["9553"],

    # Pedido de Cumprimento de Sentença (documento específico)
    "PEDIDO_CUMPRIMENTO": ["286"],  # Pedido de Cumprimento de Sentença contra a Fazenda Pública
}

# Classes processuais de cumprimento de sentença (processos autônomos)
CLASSES_CUMPRIMENTO_AUTONOMO = [
    "156",    # Cumprimento de Sentença
    "157",    # Cumprimento Provisório de Sentença
    "10980",  # Cumprimento de Sentença contra a Fazenda Pública
    "12078",  # Cumprimento de Sentença contra a Fazenda Pública (JEF)
    "12246",  # Cumprimento Provisório de Sentença contra a Fazenda Pública
    "15160",  # Cumprimento de Sentença contra a Fazenda Pública (Obrigação de Fazer)
    "15161",  # Cumprimento Provisório de Sentença contra a Fazenda Pública (Obrigação de Fazer)
    "15215",  # Cumprimento de Sentença contra a Fazenda Pública (Obrigação de Pagar)
]

# Movimento que indica distribuição por dependência (usado em cumprimentos)
MOVIMENTO_DISTRIBUICAO_DEPENDENCIA = "50002"

# Códigos de movimento relevantes
MOVIMENTOS_CUMPRIMENTO = ["50292"]  # Juntada de Execução/Cumprimento de Sentença
MOVIMENTOS_TRANSITO = ["848"]  # Trânsito em julgado

# Mapa de códigos IBGE para comarcas
COMARCAS_IBGE = {
    "5002704": "Campo Grande",
    "5003702": "Dourados",
    "5007208": "Três Lagoas",
    "5003207": "Corumbá",
    "5000708": "Aquidauana",
    "5002100": "Bonito",
    "5005202": "Naviraí",
    "5006200": "Ponta Porã",
    "5003306": "Coxim",
}


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


def _formatar_cpf(cpf: str) -> str:
    """Formata CPF para XXX.XXX.XXX-XX"""
    cpf_limpo = re.sub(r'\D', '', cpf)
    if len(cpf_limpo) == 11:
        return f"{cpf_limpo[:3]}.{cpf_limpo[3:6]}.{cpf_limpo[6:9]}-{cpf_limpo[9:]}"
    return cpf


def _formatar_cnpj(cnpj: str) -> str:
    """Formata CNPJ para XX.XXX.XXX/XXXX-XX"""
    cnpj_limpo = re.sub(r'\D', '', cnpj)
    if len(cnpj_limpo) == 14:
        return f"{cnpj_limpo[:2]}.{cnpj_limpo[2:5]}.{cnpj_limpo[5:8]}/{cnpj_limpo[8:12]}-{cnpj_limpo[12:]}"
    return cnpj


def _formatar_numero_processo(numero: str) -> str:
    """Formata número do processo para padrão CNJ: NNNNNNN-NN.NNNN.N.NN.NNNN"""
    numero_limpo = re.sub(r'\D', '', numero)
    if len(numero_limpo) == 20:
        return f"{numero_limpo[:7]}-{numero_limpo[7:9]}.{numero_limpo[9:13]}.{numero_limpo[13]}.{numero_limpo[14:16]}.{numero_limpo[16:]}"
    return numero


def _get_tag_name(elem: ET.Element) -> str:
    """Retorna nome da tag sem namespace"""
    return elem.tag.split('}')[-1].lower() if '}' in elem.tag else elem.tag.lower()


def _dias_uteis_apos(data_inicial: date, dias_uteis: int) -> date:
    """
    Calcula data após N dias úteis (ignora finais de semana).
    Não considera feriados - seria necessário tabela de feriados.
    """
    data = data_inicial
    dias_contados = 0
    while dias_contados < dias_uteis:
        data += timedelta(days=1)
        if data.weekday() < 5:  # Segunda a Sexta
            dias_contados += 1
    return data


def _primeiro_dia_util_posterior(data_referencia: date) -> date:
    """
    Retorna o primeiro dia útil posterior à data de referência.
    Conforme art. 224 do CPC, o termo inicial do prazo é o primeiro
    dia útil seguinte à data de recebimento da intimação.

    Não considera feriados - seria necessário tabela de feriados.
    """
    data = data_referencia + timedelta(days=1)
    while data.weekday() >= 5:  # Sábado (5) ou Domingo (6)
        data += timedelta(days=1)
    return data


class XMLParser:
    """Parser do XML do processo judicial (padrão MNI/CNJ)"""
    
    def __init__(self, xml_text: str):
        """
        Inicializa o parser.
        
        Args:
            xml_text: XML completo do processo
        """
        self.xml_text = xml_text
        # SECURITY: Usa parsing seguro para prevenir XXE
        self.root = safe_parse_xml(xml_text)
        self._dados_basicos = None
        self._movimentos = []
        self._documentos = []
        self._doc_movimento_map = {}  # Mapeia doc_id -> info do movimento pai
        self._parse_estrutura()

    def _parse_estrutura(self):
        """Parse inicial para identificar estrutura do XML"""
        for elem in self.root.iter():
            tag = _get_tag_name(elem)

            if tag == 'dadosbasicos':
                self._dados_basicos = elem
            elif tag == 'movimento':
                self._movimentos.append(elem)
                # Extrai info do movimento para mapear aos documentos filhos
                mov_complemento = ""
                mov_descricao = ""
                # Primeiro passa para pegar complemento e descrição
                for child in elem:
                    child_tag = _get_tag_name(child)
                    if child_tag == 'complemento' and child.text:
                        mov_complemento = child.text
                    elif child_tag == 'movimentolocal':
                        mov_descricao = child.attrib.get('descricao', '')
                # Segunda passada para mapear documentos com o complemento já extraído
                for child in elem:
                    child_tag = _get_tag_name(child)
                    if child_tag == 'documento':
                        # Mapeia este documento ao movimento pai
                        doc_id = child.attrib.get('idDocumento', child.attrib.get('id', ''))
                        if doc_id:
                            self._doc_movimento_map[doc_id] = {
                                'complemento': mov_complemento,
                                'descricao_movimento': mov_descricao
                            }
            elif tag == 'documento':
                self._documentos.append(elem)

    def get_movimento_info(self, doc_id: str) -> Optional[Dict[str, str]]:
        """
        Retorna informações do movimento pai de um documento.

        Args:
            doc_id: ID do documento

        Returns:
            Dict com 'complemento' e 'descricao_movimento', ou None se não encontrado
        """
        return self._doc_movimento_map.get(doc_id)
    
    def extrair_dados_basicos(self) -> DadosBasicos:
        """
        Extrai dados básicos do processo do XML.
        
        Returns:
            DadosBasicos com informações extraídas
        """
        if self._dados_basicos is None:
            raise ValueError("XML não contém dados básicos do processo")
        
        elem = self._dados_basicos
        
        # Número do processo
        numero = elem.attrib.get('numero', '')
        numero_formatado = _formatar_numero_processo(numero)
        
        # Data de ajuizamento
        data_ajuiz = _parse_date_tjms(elem.attrib.get('dataAjuizamento'))
        
        # Valor da causa
        valor_causa = None
        for child in elem.iter():
            if _get_tag_name(child) == 'valorcausa' and child.text:
                try:
                    valor_causa = float(child.text.strip())
                except ValueError:
                    pass
                break
        
        # Órgão julgador e comarca
        vara = None
        comarca = None
        for child in elem.iter():
            if _get_tag_name(child) == 'orgaojulgador':
                vara = child.attrib.get('nomeOrgao')
                codigo_ibge = child.attrib.get('codigoMunicipioIBGE')
                if codigo_ibge:
                    comarca = COMARCAS_IBGE.get(codigo_ibge, codigo_ibge)
                break
        
        # Partes
        autor = None
        cpf_autor = None
        reu = "Estado de Mato Grosso do Sul"
        
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
                    
                    if tipo_polo == 'AT' and not autor:
                        autor = nome
                        # Busca CPF ou CNPJ
                        for doc_elem in pessoa_elem.iter():
                            if _get_tag_name(doc_elem) == 'documento':
                                tipo_doc = doc_elem.attrib.get('tipoDocumento', '')
                                doc_raw = doc_elem.attrib.get('codigoDocumento', '')
                                doc_limpo = re.sub(r'\D', '', doc_raw)

                                # CPF (tipo CMF)
                                if tipo_doc == 'CMF' and len(doc_limpo) == 11:
                                    cpf_autor = _formatar_cpf(doc_raw)
                                    break
                                # CNPJ (tipo CAN ou outros códigos)
                                elif tipo_doc in ['CAN', 'CNPJ'] and len(doc_limpo) == 14:
                                    cpf_autor = _formatar_cnpj(doc_raw)
                                    break
                                # Detecta automaticamente pelo tamanho se tipo não for padrão
                                elif len(doc_limpo) == 11:
                                    cpf_autor = _formatar_cpf(doc_raw)
                                    break
                                elif len(doc_limpo) == 14:
                                    cpf_autor = _formatar_cnpj(doc_raw)
                                    break
                        break
                    elif tipo_polo == 'PA' and not reu:
                        reu = nome
                        break
        
        return DadosBasicos(
            numero_processo=numero_formatado,
            autor=autor or "Não identificado",
            cpf_autor=cpf_autor,
            reu=reu,
            comarca=comarca,
            vara=vara,
            data_ajuizamento=data_ajuiz,
            valor_causa=valor_causa
        )
    
    def identificar_documentos_para_download(
        self,
        forcar_busca_sentencas: bool = False
    ) -> DocumentosParaDownload:
        """
        Identifica documentos relevantes para download.

        Analisa o XML identificando:
        - Sentenças e acórdãos (originais ou cópias em cumprimentos autônomos)
        - Certidões de citação/intimação (9508)
        - Certidão de trânsito em julgado
        - Pedido de cumprimento e cálculos do exequente

        Em cumprimentos autônomos, também extrai o número do processo de origem.

        Args:
            forcar_busca_sentencas: Se True, busca sentenças e acórdãos mesmo
                                    se for cumprimento autônomo. Útil quando
                                    estamos analisando o processo de ORIGEM.

        Returns:
            DocumentosParaDownload com IDs dos documentos
        """
        resultado = DocumentosParaDownload()

        # Verifica se é um cumprimento autônomo
        is_cumprimento_autonomo = self._verificar_cumprimento_autonomo()
        resultado.is_cumprimento_autonomo = is_cumprimento_autonomo

        # Mapear documentos por tipo
        docs_por_tipo: Dict[str, List[Tuple[str, datetime, str]]] = {}
        for doc in self._documentos:
            doc_id = doc.attrib.get('idDocumento', doc.attrib.get('id', ''))
            tipo = doc.attrib.get('tipoDocumentoLocal', doc.attrib.get('tipoDocumento', ''))
            descricao = doc.attrib.get('descricao', '')
            data_str = doc.attrib.get('dataHora', '')
            data = _parse_datahora_tjms(data_str)

            if tipo not in docs_por_tipo:
                docs_por_tipo[tipo] = []
            docs_por_tipo[tipo].append((doc_id, data, descricao))

        # Decide se busca sentenças/acórdãos deste processo
        # Se forcar_busca_sentencas=True, busca mesmo se for cumprimento autônomo
        buscar_sentencas_aqui = not is_cumprimento_autonomo or forcar_busca_sentencas

        if is_cumprimento_autonomo and not forcar_busca_sentencas:
            # CUMPRIMENTO AUTÔNOMO: sentenças, acórdãos e citação serão buscados do processo de ORIGEM
            print(f"[CUMPRIMENTO AUTÔNOMO] Documentos serão buscados do processo de origem")

            # Extrai número do processo de origem do XML
            numero_origem = self._extrair_numero_processo_origem()
            resultado.numero_processo_origem = numero_origem

            if numero_origem:
                print(f"[CUMPRIMENTO AUTÔNOMO] Processo de origem encontrado no XML: {numero_origem}")
            else:
                # Não encontrou no XML - será necessário usar IA para extrair da petição inicial
                print(f"[CUMPRIMENTO AUTÔNOMO] Número não encontrado no XML - será extraído da petição inicial")

            # Guarda ID da primeira petição (para análise IA se necessário)
            id_peticao = self._identificar_primeira_peticao(docs_por_tipo)
            resultado.id_peticao_inicial = id_peticao
            if id_peticao:
                print(f"[CUMPRIMENTO AUTÔNOMO] Petição inicial: {id_peticao}")

            # NÃO adiciona sentenças/acórdãos do cumprimento (serão buscados do processo de origem)
            # Mas ainda precisamos identificar a intimação DESTE processo de cumprimento

        if buscar_sentencas_aqui:
            # PROCESSO NORMAL ou forçando busca: busca sentenças e acórdãos deste processo
            if forcar_busca_sentencas:
                print(f"[ORIGEM] Forçando busca de sentenças e acórdãos do processo de origem")

            # Sentenças (originais)
            for tipo_cod in TIPOS_DOCUMENTO["SENTENCA"] + TIPOS_DOCUMENTO["SENTENCA_JUIZ_LEIGO"]:
                if tipo_cod in docs_por_tipo:
                    for doc_id, _, _ in docs_por_tipo[tipo_cod]:
                        resultado.sentencas.append(doc_id)

            # Acórdãos (originais)
            for tipo_cod in TIPOS_DOCUMENTO["ACORDAO"]:
                if tipo_cod in docs_por_tipo:
                    for doc_id, _, _ in docs_por_tipo[tipo_cod]:
                        resultado.acordaos.append(doc_id)

            # Certidão de trânsito em julgado
            # 1. Primeiro tenta pelo tipo de documento (9644)
            for tipo_cod in TIPOS_DOCUMENTO["CERTIDAO_TRANSITO"]:
                if tipo_cod in docs_por_tipo:
                    for doc_id, _, _ in docs_por_tipo[tipo_cod]:
                        resultado.certidao_transito = doc_id
                        print(f"[TRÂNSITO] Certidão de trânsito (tipo 9644): {doc_id}")
                        break

            # 2. Se não encontrou, busca pelo documento vinculado ao movimento de trânsito (código 848)
            if not resultado.certidao_transito:
                doc_vinculado_transito = self._buscar_documento_vinculado_movimento_transito()
                if doc_vinculado_transito:
                    resultado.certidao_transito = doc_vinculado_transito
                    print(f"[TRÂNSITO] Certidão de trânsito (vinculada ao movimento 848): {doc_vinculado_transito}")

            if forcar_busca_sentencas:
                print(f"[ORIGEM] Sentenças encontradas: {resultado.sentencas}")
                print(f"[ORIGEM] Acórdãos encontrados: {resultado.acordaos}")
        
        # Identifica certidão de citação (heurística - funciona bem)
        resultado.certidoes_citacao_intimacao = self._identificar_certidoes_citacao_intimacao(docs_por_tipo)

        # Identifica certidão de intimação para cumprimento
        # 1. Primeiro, encontra a data do movimento de cumprimento
        data_mov_cumprimento = self._encontrar_data_movimento_cumprimento()
        resultado.data_movimento_cumprimento = data_mov_cumprimento

        # 2. SEMPRE coleta candidatas para análise IA (a IA vai ler o conteúdo e extrair data real)
        # A heurística é usada apenas como referência, mas a IA tem prioridade
        resultado.certidoes_candidatas = self._identificar_certidoes_candidatas_cumprimento(
            docs_por_tipo, data_mov_cumprimento
        )

        # 3. Guarda sugestão da heurística (será sobrescrita pela IA se ela encontrar algo)
        cert_cumprimento_sistema = self._identificar_certidao_cumprimento_sistema(docs_por_tipo, data_mov_cumprimento)
        cert_cumprimento_cartorio = self._identificar_certidao_cumprimento_cartorio(docs_por_tipo, data_mov_cumprimento)

        if cert_cumprimento_sistema:
            resultado.certidao_heuristica = cert_cumprimento_sistema
            print(f"[HEURÍSTICA] Certidão do SISTEMA sugerida - será validada pela IA")
        elif cert_cumprimento_cartorio:
            resultado.certidao_heuristica = cert_cumprimento_cartorio
            print(f"[HEURÍSTICA] Certidão de CARTÓRIO sugerida - será validada pela IA")
        else:
            resultado.certidao_heuristica = None
            print(f"[HEURÍSTICA] Nenhuma sugestão - IA analisará {len(resultado.certidoes_candidatas)} candidatas")

        # Identifica documentos do pedido de cumprimento
        resultado.pedido_cumprimento = self._identificar_pedido_cumprimento()

        return resultado

    def _verificar_cumprimento_autonomo(self) -> bool:
        """
        Verifica se o processo é um cumprimento de sentença autônomo.

        Cumprimentos autônomos são processos separados ajuizados para
        executar uma sentença de outro processo.

        IMPORTANTE: Processos "evoluídos" (onde a classe foi alterada de
        conhecimento para cumprimento, mas os documentos ficam no mesmo
        processo) NÃO são considerados autônomos. Para detectar isso,
        verificamos se existem sentenças ORIGINAIS (tipos 8, 54) no processo.
        Se existirem, os documentos estão todos aqui, não é autônomo.

        Usa múltiplas heurísticas para identificar cumprimentos, pois
        às vezes os processos são classificados com código errado:
        1. Classe processual conhecida de cumprimento (mas verifica se tem sentença original)
        2. Movimento "Distribuído por Dependência" com complemento "CUMPRIMENTO DE SENTENÇA"
        3. Presença de cópias de sentença/acórdão/trânsito em julgado
        4. Movimento de apensamento a outro processo

        Returns:
            True se for cumprimento autônomo, False caso contrário
        """
        if self._dados_basicos is None:
            return False

        # PRIMEIRO: Verifica se tem sentenças ORIGINAIS no processo
        # Se tiver, é um processo "evoluído" (classe alterada), não autônomo
        tem_sentenca_original = False
        tem_acordao_original = False
        for doc in self._documentos:
            tipo = doc.attrib.get('tipoDocumentoLocal', doc.attrib.get('tipoDocumento', ''))
            # Tipos de sentença original (não cópia)
            if tipo in TIPOS_DOCUMENTO["SENTENCA"] + TIPOS_DOCUMENTO["SENTENCA_JUIZ_LEIGO"]:
                tem_sentenca_original = True
            # Tipos de acórdão original (não cópia)
            if tipo in TIPOS_DOCUMENTO["ACORDAO"]:
                tem_acordao_original = True

        if tem_sentenca_original:
            print(f"[CUMPRIMENTO] Processo tem sentença ORIGINAL - é processo 'evoluído', não autônomo")
            print(f"              (sentenças e acórdãos serão buscados deste mesmo processo)")
            return False

        # 1. Verifica pela classe processual
        classe_processual = self._dados_basicos.attrib.get('classeProcessual', '')
        if classe_processual in CLASSES_CUMPRIMENTO_AUTONOMO:
            print(f"[CUMPRIMENTO] Identificado pela classe processual: {classe_processual}")
            return True

        # 2. Verifica movimento "Distribuído por Dependência" com complemento "CUMPRIMENTO DE SENTENÇA"
        for mov in self._movimentos:
            codigo_movimento = ""
            complemento = ""

            for child in mov.iter():
                tag = _get_tag_name(child)
                if tag == 'movimentolocal':
                    codigo_movimento = child.attrib.get('codigoMovimento', '')
                elif tag == 'complemento' and child.text:
                    complemento = child.text

            # Movimento de distribuição por dependência (50002)
            if codigo_movimento == MOVIMENTO_DISTRIBUICAO_DEPENDENCIA:
                complemento_upper = complemento.upper()
                if 'CUMPRIMENTO DE SENTENÇA' in complemento_upper or 'CUMPRIMENTO DE SENTENCA' in complemento_upper:
                    print(f"[CUMPRIMENTO] Identificado por movimento de dependência com complemento: {complemento[:80]}...")
                    return True

        # 3. Verifica presença de cópias de sentença, acórdão ou trânsito em julgado
        # Esses documentos são típicos de cumprimentos autônomos
        tipos_copia = set(TIPOS_DOCUMENTO["COPIA_SENTENCA"] + TIPOS_DOCUMENTO["COPIA_ACORDAO"] + TIPOS_DOCUMENTO["CERTIDAO_TRANSITO"])
        tem_copia_sentenca = False
        tem_copia_acordao = False
        tem_copia_transito = False

        for doc in self._documentos:
            tipo = doc.attrib.get('tipoDocumentoLocal', doc.attrib.get('tipoDocumento', ''))
            if tipo in TIPOS_DOCUMENTO["COPIA_SENTENCA"]:
                tem_copia_sentenca = True
            if tipo in TIPOS_DOCUMENTO["COPIA_ACORDAO"]:
                tem_copia_acordao = True
            if tipo in TIPOS_DOCUMENTO["CERTIDAO_TRANSITO"]:
                tem_copia_transito = True

        # Se tem cópia de sentença E (cópia de acórdão OU cópia de trânsito), é cumprimento
        if tem_copia_sentenca and (tem_copia_acordao or tem_copia_transito):
            print(f"[CUMPRIMENTO] Identificado por cópias de documentos (sentença={tem_copia_sentenca}, acórdão={tem_copia_acordao}, trânsito={tem_copia_transito})")
            return True

        # 4. Verifica movimento de apensamento a outro processo
        padrao_cnj = r'\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}'
        for mov in self._movimentos:
            complemento = ""
            for child in mov.iter():
                tag = _get_tag_name(child)
                if tag == 'complemento' and child.text:
                    complemento = child.text.lower()

            # Verifica se tem "apensado ao processo" ou similar
            if 'apensado ao processo' in complemento or 'apenso ao processo' in complemento:
                # Verifica se menciona cumprimento ou execução
                if 'cumprimento' in complemento or 'execução' in complemento or 'execucao' in complemento:
                    print(f"[CUMPRIMENTO] Identificado por apensamento com menção a cumprimento/execução")
                    return True

        return False

    def _buscar_documento_vinculado_movimento_transito(self) -> Optional[str]:
        """
        Busca o ID do documento vinculado ao movimento de trânsito em julgado.

        O movimento de trânsito em julgado (código nacional 848) pode ter um
        documento vinculado através da tag <idDocumentoVinculado>. Este documento
        geralmente é a certidão de trânsito em julgado.

        Exemplo de XML:
        <ns2:movimento dataHora="20230510104010" nivelSigilo="0">
            <ns2:complemento>Certifico que transitou em julgado...</ns2:complemento>
            <ns2:movimentoNacional codigoNacional="848"/>
            <ns2:idDocumentoVinculado>124419043 - 0</ns2:idDocumentoVinculado>
        </ns2:movimento>

        Returns:
            ID do documento vinculado ou None se não encontrado
        """
        for mov in self._movimentos:
            codigo_nacional = ""
            id_doc_vinculado = None
            complemento = ""

            for child in mov.iter():
                tag = _get_tag_name(child)
                if tag == 'movimentonacional':
                    codigo_nacional = child.attrib.get('codigoNacional', '')
                elif tag == 'iddocumentovinculado' and child.text:
                    # O ID pode vir com sufixo como "124419043 - 0", pegamos só o número principal
                    id_doc_vinculado = child.text.strip().split(' - ')[0].strip()
                elif tag == 'complemento' and child.text:
                    complemento = child.text

            # Verifica se é movimento de trânsito em julgado (código 848)
            if codigo_nacional in MOVIMENTOS_TRANSITO and id_doc_vinculado:
                print(f"[TRÂNSITO] Documento vinculado encontrado no movimento 848: {id_doc_vinculado}")
                if complemento:
                    print(f"[TRÂNSITO] Complemento: {complemento[:80]}...")
                return id_doc_vinculado

        return None

    def _extrair_numero_processo_origem(self) -> Optional[str]:
        """
        Extrai o número do processo de origem de um cumprimento autônomo.

        O número geralmente aparece em:
        1. Complemento do movimento de apensamento/distribuição por dependência
        2. Texto da petição inicial (se não encontrar no movimento)

        Returns:
            Número CNJ formatado do processo de origem ou None
        """
        # Padrão CNJ: NNNNNNN-NN.NNNN.N.NN.NNNN
        import re
        padrao_cnj = r'\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}'

        # Busca nos movimentos
        for mov in self._movimentos:
            complemento = ""
            for child in mov.iter():
                tag = _get_tag_name(child)
                if tag == 'complemento' and child.text:
                    complemento = child.text

            # Procura padrão CNJ no complemento
            match = re.search(padrao_cnj, complemento)
            if match:
                numero_origem = match.group(0)
                print(f"[ORIGEM] Processo de origem encontrado no movimento: {numero_origem}")
                return numero_origem

            # Procura termos indicativos
            complemento_lower = complemento.lower()
            if 'apensado ao processo' in complemento_lower or 'dependência' in complemento_lower:
                # Tenta extrair número mesmo em formato diferente
                # Ex: "0815077-35.2021.8.12.0110"
                match = re.search(padrao_cnj, complemento)
                if match:
                    return match.group(0)

        return None

    def _identificar_primeira_peticao(
        self,
        docs_por_tipo: Dict[str, List[Tuple[str, datetime, str]]]
    ) -> Optional[str]:
        """
        Identifica a primeira petição do processo (petição inicial).

        Em cumprimentos autônomos, a petição inicial contém o número
        do processo de origem que pode ser extraído por IA.

        Returns:
            ID da primeira petição ou None
        """
        # Busca petições (tipo 9500)
        peticoes = []
        for tipo_cod in TIPOS_DOCUMENTO["PETICAO"]:
            if tipo_cod in docs_por_tipo:
                for doc_id, doc_data, doc_descr in docs_por_tipo[tipo_cod]:
                    if doc_data:
                        peticoes.append((doc_id, doc_data, doc_descr))

        if not peticoes:
            return None

        # Ordena por data (mais antiga primeiro)
        peticoes.sort(key=lambda x: x[1])

        # Retorna a primeira petição
        return peticoes[0][0]

    def _encontrar_data_movimento_cumprimento(self) -> Optional[date]:
        """
        Encontra a data do movimento de intimação para cumprimento mais recente.
        """
        data_movimento_cumprimento = None
        termos_cumprimento = [
            'impugnar', 'impugnação', 'impugnacao',
            'cumprimento de sentença', 'cumprimento de sentenca',
            'cumprir a obrigação', 'cumprir a obrigacao',
            'cumprimento da obrigação', 'cumprimento da obrigacao',
            'pagar ou impugnar',
            'intimação para cumprimento', 'intimacao para cumprimento',
            'intimado para cumprimento',
            'art. 523', 'art. 535',
        ]

        for mov in self._movimentos:
            data_mov_str = mov.attrib.get('dataHora', '')
            data_mov = _parse_datahora_tjms(data_mov_str)

            if not data_mov:
                continue

            # Verifica descrição e complemento do movimento
            descricao_mov = ""
            complemento_mov = ""

            for child in mov.iter():
                tag = _get_tag_name(child)
                if tag == 'movimentolocal':
                    descricao_mov = child.attrib.get('descricao', '').lower()
                elif tag == 'complemento' and child.text:
                    complemento_mov = child.text.lower()

            texto_completo = f"{descricao_mov} {complemento_mov}".lower()

            # Verifica se é movimento de intimação para cumprimento
            if any(termo in texto_completo for termo in termos_cumprimento):
                # Pega o movimento mais recente de cumprimento
                if data_movimento_cumprimento is None or data_mov.date() > data_movimento_cumprimento:
                    data_movimento_cumprimento = data_mov.date()
                    print(f"[MOVIMENTO] Intimação p/ cumprimento encontrada: {data_movimento_cumprimento}")
                    print(f"            Descrição: {descricao_mov[:80]}...")

        return data_movimento_cumprimento

    def _identificar_certidao_cumprimento_sistema(
        self,
        docs_por_tipo: Dict[str, List[Tuple[str, datetime, str]]],
        data_movimento_cumprimento: Optional[date]
    ) -> Optional[CertidaoCitacaoIntimacao]:
        """
        Tenta identificar a certidão do SISTEMA (9508) para intimação de cumprimento
        usando heurística (sem IA).

        A certidão do sistema geralmente é emitida poucos dias após o movimento
        de intimação para cumprimento.

        Returns:
            CertidaoCitacaoIntimacao se encontrada, None caso contrário
        """
        if not data_movimento_cumprimento:
            return None

        # Coleta certidões do sistema (9508) disponíveis
        certidoes_sistema = []
        for tipo_cod in TIPOS_DOCUMENTO["CERTIDAO_SISTEMA"]:
            if tipo_cod in docs_por_tipo:
                for cert_id, cert_data, cert_descr in docs_por_tipo[tipo_cod]:
                    if cert_data:
                        certidoes_sistema.append((cert_id, cert_data, cert_descr))

        if not certidoes_sistema:
            return None

        # Busca certidão do sistema emitida até 15 dias úteis após o movimento
        data_limite = _dias_uteis_apos(data_movimento_cumprimento, 15)

        for cert_id, cert_data, cert_descr in certidoes_sistema:
            # Certidão deve ser posterior ao movimento e dentro do limite
            if data_movimento_cumprimento <= cert_data.date() <= data_limite:
                # A data da certidão do sistema É a data de recebimento pela PGE
                data_recebimento = cert_data.date()
                termo_inicial = _primeiro_dia_util_posterior(data_recebimento)

                print(f"[CUMPRIMENTO] Certidão do SISTEMA identificada por heurística")
                print(f"              Movimento cumprimento: {data_movimento_cumprimento}")
                print(f"              Data recebimento: {data_recebimento}")
                print(f"              Termo inicial: {termo_inicial}")

                return CertidaoCitacaoIntimacao(
                    tipo=TipoIntimacao.INTIMACAO_IMPUGNACAO,
                    data_expedicao=data_movimento_cumprimento,
                    id_certidao_9508=cert_id,
                    data_certidao=data_recebimento,
                    data_recebimento=data_recebimento,
                    termo_inicial_prazo=termo_inicial,
                    tipo_certidao="sistema",
                    identificado_por_ia=False
                )

        return None

    def _identificar_certidao_cumprimento_cartorio(
        self,
        docs_por_tipo: Dict[str, List[Tuple[str, datetime, str]]],
        data_movimento_cumprimento: Optional[date]
    ) -> Optional[CertidaoCitacaoIntimacao]:
        """
        Tenta identificar a certidão de CARTÓRIO (tipo 13) para intimação de cumprimento
        por decurso de prazo (inexistência de leitura).

        Procura por movimentos com complemento indicando "Inexistência de Leitura"
        que tenham certidão de cartório vinculada.

        Returns:
            CertidaoCitacaoIntimacao se encontrada, None caso contrário
        """
        if not data_movimento_cumprimento:
            return None

        # Termos que indicam certidão de decurso de prazo
        termos_decurso = [
            'inexistência de leitura',
            'inexistencia de leitura',
            'decurso de prazo',
            'decurso do prazo',
        ]

        # Busca movimento de certidão cartorária com indicação de decurso de prazo
        # após o movimento de cumprimento
        for mov in self._movimentos:
            data_mov_str = mov.attrib.get('dataHora', '')
            data_mov = _parse_datahora_tjms(data_mov_str)

            if not data_mov:
                continue

            # Deve ser posterior ao movimento de cumprimento
            if data_mov.date() < data_movimento_cumprimento:
                continue

            # Verifica complemento e descrição do movimento
            complemento_mov = ""
            descricao_mov = ""
            id_doc_vinculado = None

            for child in mov.iter():
                tag = _get_tag_name(child)
                if tag == 'complemento' and child.text:
                    complemento_mov = child.text.lower()
                elif tag == 'movimentolocal':
                    descricao_mov = child.attrib.get('descricao', '').lower()
                elif tag == 'iddocumentovinculado' and child.text:
                    id_doc_vinculado = child.text.strip()

            texto_completo = f"{complemento_mov} {descricao_mov}".lower()

            # Verifica se indica decurso de prazo
            if any(termo in texto_completo for termo in termos_decurso):
                # A data do movimento de decurso É a data de intimação automática
                data_intimacao = data_mov.date()
                termo_inicial = _primeiro_dia_util_posterior(data_intimacao)

                # Busca ID da certidão vinculada ou usa o ID do documento vinculado
                cert_id = id_doc_vinculado

                # Se não tem documento vinculado, busca certidão do cartório próxima
                if not cert_id:
                    for tipo_cod in TIPOS_DOCUMENTO["CERTIDAO_CARTORIO"]:
                        if tipo_cod in docs_por_tipo:
                            for doc_id, doc_data, doc_descr in docs_por_tipo[tipo_cod]:
                                if doc_data and doc_data.date() == data_intimacao:
                                    cert_id = doc_id
                                    break

                print(f"[CUMPRIMENTO] Certidão de CARTÓRIO (decurso) identificada por heurística")
                print(f"              Movimento cumprimento: {data_movimento_cumprimento}")
                print(f"              Data decurso/intimação: {data_intimacao}")
                print(f"              Termo inicial: {termo_inicial}")
                print(f"              Complemento: {complemento_mov[:60]}...")

                return CertidaoCitacaoIntimacao(
                    tipo=TipoIntimacao.INTIMACAO_IMPUGNACAO,
                    data_expedicao=data_movimento_cumprimento,
                    id_certidao_9508=cert_id,
                    data_certidao=data_intimacao,
                    data_recebimento=data_intimacao,
                    termo_inicial_prazo=termo_inicial,
                    tipo_certidao="cartorio",
                    identificado_por_ia=False
                )

        return None

    def _identificar_certidoes_candidatas_cumprimento(
        self,
        docs_por_tipo: Dict[str, List[Tuple[str, datetime, str]]],
        data_movimento_cumprimento: Optional[date]
    ) -> List[CertidaoCandidata]:
        """
        Coleta certidões candidatas para análise pela IA.

        Este método é chamado APENAS quando a heurística não encontrou
        a certidão do sistema (9508). Neste caso, coleta certidões do
        cartório (13) e também do sistema para análise pela IA.

        Returns:
            Lista de certidões candidatas para análise
        """
        certidoes_candidatas = []

        if not data_movimento_cumprimento:
            print("[AVISO] Movimento de cumprimento não encontrado, usando data antiga")
            data_movimento_cumprimento = date(2020, 1, 1)

        # Adiciona margem de 1 dia antes para garantir
        data_minima = data_movimento_cumprimento - timedelta(days=1)

        # Certidões do Sistema (tipo 9508) - podem existir várias, IA vai identificar
        for tipo_cod in TIPOS_DOCUMENTO["CERTIDAO_SISTEMA"]:
            if tipo_cod in docs_por_tipo:
                for cert_id, cert_data, cert_descr in docs_por_tipo[tipo_cod]:
                    if cert_data and cert_data.date() >= data_minima:
                        certidoes_candidatas.append(CertidaoCandidata(
                            id_documento=cert_id,
                            tipo_documento="9508",
                            data_documento=cert_data.date(),
                            descricao=cert_descr
                        ))

        # Certidões Cartorária (tipo 13) - decurso de prazo
        for tipo_cod in TIPOS_DOCUMENTO["CERTIDAO_CARTORIO"]:
            if tipo_cod in docs_por_tipo:
                for cert_id, cert_data, cert_descr in docs_por_tipo[tipo_cod]:
                    if cert_data and cert_data.date() >= data_minima:
                        certidoes_candidatas.append(CertidaoCandidata(
                            id_documento=cert_id,
                            tipo_documento="13",
                            data_documento=cert_data.date(),
                            descricao=cert_descr
                        ))

        # Ordena por data (mais recentes primeiro)
        certidoes_candidatas.sort(key=lambda x: x.data_documento or date.min, reverse=True)

        # Limita a 10 certidões mais recentes para não sobrecarregar a IA
        certidoes_candidatas = certidoes_candidatas[:10]

        print(f"[CERTIDÕES P/ IA] {len(certidoes_candidatas)} certidões candidatas para análise pela IA")
        for cert in certidoes_candidatas:
            tipo_str = "Sistema" if cert.tipo_documento == "9508" else "Cartório"
            print(f"            - {tipo_str} ({cert.tipo_documento}): {cert.data_documento} - ID: {cert.id_documento}")

        return certidoes_candidatas

    def _identificar_certidao_citacao(
        self,
        docs_por_tipo: Dict[str, List[Tuple[str, datetime, str]]]
    ) -> Optional[CertidaoCitacaoIntimacao]:
        """
        Identifica a certidão de CITAÇÃO usando heurística (método legado).
        A certidão de citação geralmente é encontrada corretamente por este método.
        """
        # Coleta certidões disponíveis
        certidoes_disponiveis = []

        for tipo_cod in TIPOS_DOCUMENTO["CERTIDAO_SISTEMA"]:
            if tipo_cod in docs_por_tipo:
                for cert in docs_por_tipo[tipo_cod]:
                    certidoes_disponiveis.append((*cert, "sistema"))

        for tipo_cod in TIPOS_DOCUMENTO["CERTIDAO_CARTORIO"]:
            if tipo_cod in docs_por_tipo:
                for cert in docs_por_tipo[tipo_cod]:
                    certidoes_disponiveis.append((*cert, "cartorio"))

        # Procura movimento de citação
        for mov in self._movimentos:
            data_mov_str = mov.attrib.get('dataHora', '')
            data_mov = _parse_datahora_tjms(data_mov_str)

            if not data_mov:
                continue

            descricao_mov = ""
            for child in mov.iter():
                tag = _get_tag_name(child)
                if tag == 'movimentolocal':
                    descricao_mov = child.attrib.get('descricao', '').lower()
                    break

            # Verifica se é citação
            if 'citação' in descricao_mov or 'citacao' in descricao_mov:
                if 'certidão' not in descricao_mov and 'certidao' not in descricao_mov:
                    # Busca certidão correspondente
                    data_limite = _dias_uteis_apos(data_mov.date(), 15)

                    for cert_id, cert_data, cert_descr, cert_origem in certidoes_disponiveis:
                        if cert_data and data_mov.date() <= cert_data.date() <= data_limite:
                            data_recebimento = cert_data.date()
                            termo_inicial = _primeiro_dia_util_posterior(data_recebimento)

                            print(f"[CITAÇÃO] Certidão de citação identificada")
                            print(f"          Data expedição: {data_mov.date()}")
                            print(f"          Data recebimento: {data_recebimento}")
                            print(f"          Termo inicial: {termo_inicial}")

                            return CertidaoCitacaoIntimacao(
                                tipo=TipoIntimacao.CITACAO,
                                data_expedicao=data_mov.date(),
                                id_certidao_9508=cert_id,
                                data_certidao=data_recebimento,
                                data_recebimento=data_recebimento,
                                termo_inicial_prazo=termo_inicial,
                                tipo_certidao=cert_origem,
                                identificado_por_ia=False
                            )

        return None

    def _identificar_certidoes_citacao_intimacao(
        self,
        docs_por_tipo: Dict[str, List[Tuple[str, datetime, str]]]
    ) -> List[CertidaoCitacaoIntimacao]:
        """
        Identifica apenas a certidão de CITAÇÃO (heurística).
        A certidão de intimação para cumprimento será identificada pela IA.
        """
        certidoes = []

        # Identifica certidão de citação (método legado funciona bem)
        cert_citacao = self._identificar_certidao_citacao(docs_por_tipo)
        if cert_citacao:
            certidoes.append(cert_citacao)

        return certidoes
    
    def _identificar_pedido_cumprimento(self) -> Dict[str, Any]:
        """
        Identifica documentos do pedido de cumprimento de sentença ATUAL.

        Estratégia NOVA (corrigida):
        1. PRIMEIRO: Encontra o documento tipo 286 (Pedido de Cumprimento) ou petição com
           descrição indicando pedido de cumprimento
        2. Usa a DATA/HORA desse documento como referência
        3. Busca planilhas anexadas no MESMO MOMENTO (mesmo dataHora)
        4. Para documentos 9509 (Outros): só inclui os do mesmo momento

        A estratégia antiga falhava porque usava a data da INTIMAÇÃO (que pode ser
        meses depois do pedido) como referência, excluindo o próprio pedido da janela.
        """
        resultado = {
            "movimento_identificador": None,
            "descricao_movimento": None,
            "documentos": [],
            "data_referencia": None
        }

        # 1. PRIMEIRO: Encontra o documento tipo 286 (Pedido de Cumprimento)
        # Isso define a data de referência corretamente
        pedido_cumprimento_286 = None
        data_hora_pedido_ref = None

        for doc in self._documentos:
            doc_id = doc.attrib.get('idDocumento', doc.attrib.get('id', ''))
            doc_tipo = doc.attrib.get('tipoDocumentoLocal', doc.attrib.get('tipoDocumento', ''))
            doc_descr = doc.attrib.get('descricao', '')
            doc_data_str = doc.attrib.get('dataHora', '')
            doc_data = _parse_datahora_tjms(doc_data_str)

            descr_lower = doc_descr.lower()

            # Verifica se é Pedido de Cumprimento pelo tipo 286
            if doc_tipo in TIPOS_DOCUMENTO["PEDIDO_CUMPRIMENTO"]:
                pedido_cumprimento_286 = {
                    "id": doc_id,
                    "tipo": doc_tipo,
                    "descricao": doc_descr,
                    "data": doc_data,
                    "data_hora_str": doc_data_str
                }
                data_hora_pedido_ref = doc_data_str
                print(f"[CUMPRIMENTO] ✓ Pedido de Cumprimento tipo 286 encontrado: {doc_id}")
                print(f"              Data/Hora: {doc_data_str} - {doc_descr}")
                break

            # Verifica pela descrição
            if 'pedido de cumprimento' in descr_lower or 'cumprimento de sentença' in descr_lower:
                if not pedido_cumprimento_286:  # Só se ainda não encontrou tipo 286
                    pedido_cumprimento_286 = {
                        "id": doc_id,
                        "tipo": doc_tipo,
                        "descricao": doc_descr,
                        "data": doc_data,
                        "data_hora_str": doc_data_str
                    }
                    data_hora_pedido_ref = doc_data_str
                    print(f"[CUMPRIMENTO] Pedido de Cumprimento encontrado pela descrição: {doc_id}")
                    print(f"              Data/Hora: {doc_data_str} - {doc_descr}")

        # Se não encontrou pedido 286, usa a data da intimação como fallback
        data_intimacao_cumprimento = None
        if not pedido_cumprimento_286:
            data_intimacao_cumprimento = self._encontrar_data_movimento_cumprimento()
            if not data_intimacao_cumprimento:
                print("[AVISO] Nenhum pedido de cumprimento ou intimação encontrado - usando data atual")
                data_intimacao_cumprimento = date.today()
            else:
                print(f"[CUMPRIMENTO] Usando data da intimação como referência: {data_intimacao_cumprimento}")
        else:
            # Usa a data do pedido 286 como referência
            if pedido_cumprimento_286["data"]:
                data_intimacao_cumprimento = pedido_cumprimento_286["data"].date()
                print(f"[CUMPRIMENTO] Usando data do pedido 286 como referência: {data_intimacao_cumprimento}")

        resultado["data_referencia"] = data_intimacao_cumprimento.strftime("%d/%m/%Y") if data_intimacao_cumprimento else None

        # Termos que indicam planilha de cálculo na descrição
        termos_planilha = [
            'planilha', 'cálculo', 'calculo', 'memória de cálculo',
            'memoria de calculo', 'demonstrativo', 'evolução do débito',
            'evolucao do debito', 'atualização monetária', 'atualizacao monetaria',
            'memória de cálculo atualizada', 'memoria atualizada',
            'cálculos', 'calculos', 'débito', 'debito', 'valor atualizado',
            'atualização do valor', 'atualizacao do valor', 'conta de liquidação',
            'conta de liquidacao', 'valor devido'
        ]

        # Códigos conhecidos de planilhas de cálculo
        # 9553 = Planilha de Cálculo
        # 61 = Planilha/Cálculo (alguns sistemas usam)
        # 9535 = Anexo (pode ser planilha anexa)
        codigos_planilha = ["9553", "61", "9535"]

        # Códigos de petições
        # 9500 = Petição
        # 9501 = Petição Inicial
        codigos_peticao = ["9500", "9501"]

        # Código específico de Pedido de Cumprimento de Sentença
        # 286 = Pedido de Cumprimento de Sentença contra a Fazenda Pública
        codigos_pedido_cumprimento = ["286"]

        # Códigos que podem conter planilha (quando classificado incorretamente)
        # 9509 = Outros documentos - frequentemente usado para planilhas
        codigos_outros_docs = ["9509"]

        # 2. Coleta planilhas e outros documentos que tenham o MESMO dataHora do pedido
        # Se temos data_hora_pedido_ref, usamos para filtrar EXATAMENTE
        # Senão, usamos a janela de 90 dias
        planilhas_no_periodo = []
        docs_9509_filtrados = []
        peticoes_no_periodo = []
        lista_pedidos_286 = []

        # Janela de 90 dias (usada só se não encontramos pedido 286)
        data_limite_antes = data_intimacao_cumprimento - timedelta(days=90) if data_intimacao_cumprimento else date.today() - timedelta(days=90)

        for doc in self._documentos:
            doc_id = doc.attrib.get('idDocumento', doc.attrib.get('id', ''))
            doc_descr = doc.attrib.get('descricao', '')
            doc_tipo = doc.attrib.get('tipoDocumentoLocal', doc.attrib.get('tipoDocumento', ''))
            doc_data_str = doc.attrib.get('dataHora', '')
            doc_data = _parse_datahora_tjms(doc_data_str)

            if not doc_data:
                continue

            descr_lower = doc_descr.lower()

            # Pega info do movimento pai (complemento) para verificar tipo real
            mov_info = self.get_movimento_info(doc_id)
            complemento_movimento = mov_info.get('complemento', '') if mov_info else ''

            doc_info = {
                "id": doc_id,
                "tipo": doc_tipo,
                "descricao": doc_descr,
                "data": doc_data,
                "data_date": doc_data.date(),
                "data_hora_str": doc_data_str,
                "complemento_movimento": complemento_movimento
            }

            # Classifica o documento
            is_pedido_cumprimento_tipo = doc_tipo in codigos_pedido_cumprimento
            is_planilha_por_codigo = doc_tipo in codigos_planilha
            is_planilha_por_descricao = any(termo in descr_lower for termo in termos_planilha)
            is_peticao = doc_tipo in codigos_peticao
            is_outros_doc = doc_tipo in codigos_outros_docs

            # Se temos data_hora_pedido_ref (encontramos tipo 286), filtra por MESMO dataHora
            if data_hora_pedido_ref:
                if doc_data_str == data_hora_pedido_ref:
                    # Documento anexado no mesmo momento do pedido
                    if is_planilha_por_codigo or is_planilha_por_descricao:
                        doc_info["tipo"] = "9553"
                        planilhas_no_periodo.append(doc_info)
                        print(f"[CUMPRIMENTO] ✓ Planilha do mesmo momento: {doc_id} (dataHora={doc_data_str})")
                    elif is_outros_doc:
                        parece_planilha = any(termo in descr_lower for termo in termos_planilha)
                        doc_info["tipo"] = "9553" if parece_planilha else "9509"
                        doc_info["is_outros_doc"] = True
                        docs_9509_filtrados.append(doc_info)
                    elif is_pedido_cumprimento_tipo:
                        lista_pedidos_286.append(doc_info)
                    elif is_peticao:
                        peticoes_no_periodo.append(doc_info)
            else:
                # Sem data_hora_pedido_ref, usa janela de 90 dias
                if not (data_limite_antes <= doc_data.date() <= data_intimacao_cumprimento):
                    continue

                if is_pedido_cumprimento_tipo:
                    lista_pedidos_286.append(doc_info)
                    print(f"[CUMPRIMENTO] Encontrado Pedido de Cumprimento (tipo 286): {doc_id}")
                elif is_peticao:
                    peticoes_no_periodo.append(doc_info)
                elif is_planilha_por_codigo or is_planilha_por_descricao:
                    doc_info["tipo"] = "9553"
                    planilhas_no_periodo.append(doc_info)
                elif is_outros_doc:
                    docs_9509_filtrados.append(doc_info)

        # 3. Define o pedido de cumprimento principal
        pedido_cumprimento_principal = pedido_cumprimento_286  # Já encontrado no primeiro loop
        data_hora_pedido = data_hora_pedido_ref

        # Se não encontrou no primeiro loop, tenta da lista ou petições
        if not pedido_cumprimento_principal:
            if lista_pedidos_286:
                lista_pedidos_286.sort(key=lambda x: x["data"], reverse=True)
                pedido_cumprimento_principal = lista_pedidos_286[0]
                data_hora_pedido = pedido_cumprimento_principal["data_hora_str"]
                print(f"[CUMPRIMENTO] ✓ Pedido de Cumprimento encontrado (tipo 286): {pedido_cumprimento_principal['id']}")
            elif peticoes_no_periodo:
                peticoes_no_periodo.sort(key=lambda x: x["data"], reverse=True)
                pedido_cumprimento_principal = peticoes_no_periodo[0]
                data_hora_pedido = pedido_cumprimento_principal["data_hora_str"]
                print(f"[CUMPRIMENTO] Usando petição mais recente: {pedido_cumprimento_principal['id']}")
            else:
                print(f"[CUMPRIMENTO] Nenhum pedido de cumprimento encontrado")

        print(f"[CUMPRIMENTO] Planilhas encontradas: {len(planilhas_no_periodo)}")
        print(f"[CUMPRIMENTO] Docs 9509 encontrados: {len(docs_9509_filtrados)}")

        # 4. Monta lista final: pedido cumprimento (286) + planilhas + 9509 filtrados
        documentos_relevantes = []

        # Adiciona pedido de cumprimento tipo 286 (prioridade)
        if pedido_cumprimento_286:
            documentos_relevantes.append({
                "id": pedido_cumprimento_286["id"],
                "tipo": pedido_cumprimento_286["tipo"],
                "descricao": pedido_cumprimento_286["descricao"],
                "data": pedido_cumprimento_286["data"],
                "is_outros_doc": False,
                "complemento_movimento": pedido_cumprimento_286.get("complemento_movimento", ""),
                "is_pedido_cumprimento": True  # Marca como pedido de cumprimento
            })
        elif lista_pedidos_286:
            # Usa da lista se encontrou no segundo loop
            for doc in lista_pedidos_286:
                documentos_relevantes.append({
                    "id": doc["id"],
                    "tipo": doc["tipo"],
                    "descricao": doc["descricao"],
                    "data": doc["data"],
                    "is_outros_doc": False,
                    "complemento_movimento": doc.get("complemento_movimento", ""),
                    "is_pedido_cumprimento": True
                })

        # Adiciona petições (apenas se não tiver pedido 286)
        if not pedido_cumprimento_286 and not lista_pedidos_286:
            for doc in peticoes_no_periodo:
                documentos_relevantes.append({
                    "id": doc["id"],
                    "tipo": doc["tipo"],
                    "descricao": doc["descricao"],
                    "data": doc["data"],
                    "is_outros_doc": False,
                    "complemento_movimento": doc.get("complemento_movimento", "")
                })

        # Adiciona planilhas
        for doc in planilhas_no_periodo:
            documentos_relevantes.append({
                "id": doc["id"],
                "tipo": doc["tipo"],
                "descricao": doc["descricao"],
                "data": doc["data"],
                "is_outros_doc": False,
                "complemento_movimento": doc.get("complemento_movimento", "")
            })

        # Adiciona 9509 filtrados (apenas do mesmo dia da petição)
        for doc in docs_9509_filtrados:
            documentos_relevantes.append({
                "id": doc["id"],
                "tipo": doc["tipo"],
                "descricao": doc["descricao"],
                "data": doc["data"],
                "is_outros_doc": True,
                "complemento_movimento": doc.get("complemento_movimento", "")
            })

        # Ordena por data decrescente
        documentos_relevantes.sort(key=lambda x: x["data"], reverse=True)

        # Debug: mostra todos os documentos relevantes encontrados
        print(f"[CUMPRIMENTO] Total de documentos relevantes: {len(documentos_relevantes)}")
        for doc in documentos_relevantes:
            is_outros = doc.get("is_outros_doc", False)
            is_pedido = doc.get("is_pedido_cumprimento", False)
            if is_outros:
                tipo_str = "9509 (possível planilha)"
            elif doc["tipo"] == "9553":
                tipo_str = "Planilha"
            elif is_pedido or doc["tipo"] == "286":
                tipo_str = "Pedido de Cumprimento (286)"
            else:
                tipo_str = "Petição"
            print(f"              - {tipo_str}: {doc['id']} - Data: {doc['data'].strftime('%d/%m/%Y')}")

        # 7. Monta resultado final
        for doc in documentos_relevantes:
            resultado["documentos"].append({
                "id": doc["id"],
                "tipo": doc["tipo"],
                "descricao": doc["descricao"],
                "data": doc["data"].strftime("%d/%m/%Y %H:%M"),
                "is_outros_doc": doc.get("is_outros_doc", False),
                "is_pedido_cumprimento": doc.get("is_pedido_cumprimento", False),
                "complemento_movimento": doc.get("complemento_movimento", "")
            })

        if resultado["documentos"]:
            print(f"[CUMPRIMENTO] Documentos do pedido identificados:")
            print(f"              Data intimação: {data_intimacao_cumprimento}")
            for doc in resultado["documentos"]:
                is_outros = doc.get("is_outros_doc", False)
                is_pedido = doc.get("is_pedido_cumprimento", False)
                if is_outros:
                    tipo_str = "9509 (possível planilha)"
                elif doc["tipo"] == "9553":
                    tipo_str = "Planilha"
                elif is_pedido or doc["tipo"] == "286":
                    tipo_str = "Pedido de Cumprimento (286)"
                else:
                    tipo_str = "Petição"
                print(f"              - {tipo_str}: {doc['id']} ({doc['data']})")

        # Fallback: se nenhum documento foi selecionado, inclui planilhas/peticoes encontradas
        # MAS ainda respeitando a janela de 90 dias antes da intimação
        if not resultado["documentos"]:
            print(f"[CUMPRIMENTO] FALLBACK: Nenhum documento encontrado na lógica principal, buscando planilhas/petições recentes...")
            ids_adicionados = set()
            for doc in self._documentos:
                doc_id = doc.attrib.get('idDocumento', doc.attrib.get('id', ''))
                if not doc_id or doc_id in ids_adicionados:
                    continue

                doc_descr = doc.attrib.get('descricao', '')
                doc_tipo = doc.attrib.get('tipoDocumentoLocal', doc.attrib.get('tipoDocumento', ''))
                doc_data_str = doc.attrib.get('dataHora', '')
                doc_data = _parse_datahora_tjms(doc_data_str)

                # Filtra por data: só documentos nos últimos 90 dias antes da intimação
                if doc_data and data_intimacao_cumprimento:
                    if not (data_limite_antes <= doc_data.date() <= data_intimacao_cumprimento):
                        continue  # Fora do período relevante

                descr_lower = doc_descr.lower()
                is_pedido_cumprimento = doc_tipo in codigos_pedido_cumprimento
                is_planilha = doc_tipo in codigos_planilha or any(termo in descr_lower for termo in termos_planilha)
                is_peticao = doc_tipo in codigos_peticao

                if is_pedido_cumprimento or is_planilha or is_peticao:
                    descricao = doc_descr
                    if not descricao:
                        if is_pedido_cumprimento:
                            descricao = "Pedido de Cumprimento"
                        elif is_planilha:
                            descricao = "Planilha de Calculo"
                        else:
                            descricao = "Peticao"

                    # Pega info do movimento pai
                    mov_info = self.get_movimento_info(doc_id)
                    complemento_movimento = mov_info.get('complemento', '') if mov_info else ''

                    resultado["documentos"].append({
                        "id": doc_id,
                        "tipo": doc_tipo if is_pedido_cumprimento else ("9553" if is_planilha else doc_tipo),
                        "descricao": descricao,
                        "data": doc_data.strftime("%d/%m/%Y %H:%M") if doc_data else None,
                        "is_pedido_cumprimento": is_pedido_cumprimento,
                        "complemento_movimento": complemento_movimento
                    })
                    ids_adicionados.add(doc_id)
                    print(f"[CUMPRIMENTO] FALLBACK: Adicionado {doc_id} - {descricao} ({doc_data.strftime('%d/%m/%Y') if doc_data else 'sem data'})")

        return resultado
    
    def extrair_movimentos_relevantes(self) -> MovimentosRelevantes:
        """
        Extrai datas de movimentos relevantes.
        
        Returns:
            MovimentosRelevantes com datas de citação, trânsito, intimações
        """
        resultado = MovimentosRelevantes()
        
        for mov in self._movimentos:
            data_mov_str = mov.attrib.get('dataHora', '')
            data_mov = _parse_date_tjms(data_mov_str)
            
            # Busca descrição e código do movimento
            descricao = ""
            codigo = ""
            codigo_nacional = ""
            complemento_texto = ""
            
            for child in mov.iter():
                tag = _get_tag_name(child)
                if tag == 'movimentolocal':
                    codigo = child.attrib.get('codigoMovimento', '')
                    descricao = child.attrib.get('descricao', '').lower()
                elif tag == 'movimentonacional':
                    codigo_nacional = child.attrib.get('codigoNacional', '')
                elif tag == 'complemento' and child.text:
                    complemento_texto = child.text
            
            # Citação
            if data_mov and ('citação' in descricao or 'citacao' in descricao):
                if not resultado.citacao_expedida:
                    resultado.citacao_expedida = data_mov
            
            # Trânsito em julgado - procura no complemento
            if complemento_texto:
                texto_lower = complemento_texto.lower()
                if 'transitou em julgado' in texto_lower or 'trânsito em julgado' in texto_lower:
                    # Tenta extrair data do texto: "em DD/MM/YYYY" ou "em DD/MM/AAAA"
                    import re
                    match = re.search(r'em\s+(\d{1,2})/(\d{1,2})/(\d{4})', complemento_texto)
                    if match:
                        try:
                            dia, mes, ano = int(match.group(1)), int(match.group(2)), int(match.group(3))
                            from datetime import date as dt_date
                            resultado.transito_julgado = dt_date(ano, mes, dia)
                        except ValueError:
                            resultado.transito_julgado = data_mov
                    else:
                        resultado.transito_julgado = data_mov
            
            # Trânsito em julgado pelo código nacional 848
            if codigo_nacional in MOVIMENTOS_TRANSITO and not resultado.transito_julgado:
                resultado.transito_julgado = data_mov
            
            # Intimação para impugnar
            if data_mov and ('impugnar' in descricao or 'cumprimento' in descricao):
                resultado.intimacao_impugnacao_expedida = data_mov
        
        return resultado


def parse_xml_processo(xml_text: str) -> Tuple[DadosBasicos, DocumentosParaDownload, MovimentosRelevantes]:
    """
    Função de conveniência para parsear XML completo.
    
    Args:
        xml_text: XML do processo
        
    Returns:
        Tupla com (DadosBasicos, DocumentosParaDownload, MovimentosRelevantes)
    """
    parser = XMLParser(xml_text)
    return (
        parser.extrair_dados_basicos(),
        parser.identificar_documentos_para_download(),
        parser.extrair_movimentos_relevantes()
    )
