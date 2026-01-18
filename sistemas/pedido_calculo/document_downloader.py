# sistemas/pedido_calculo/document_downloader.py
"""
Downloader de documentos do TJ-MS

Baixa documentos do processo via API SOAP para análise
pelos agentes de IA.

Autor: LAB/PGE-MS
"""

import os
import re
import base64
import asyncio
import aiohttp
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional, Tuple
from datetime import datetime

import fitz  # PyMuPDF
import pymupdf4llm

from dotenv import load_dotenv
load_dotenv()

# Serviço centralizado de normalização de texto
from services.text_normalizer import text_normalizer


# Configurações da API TJ-MS
URL_WSDL = os.getenv('URL_WSDL') or os.getenv('TJ_WSDL_URL') or os.getenv('TJ_URL_WSDL')
WS_USER = os.getenv('WS_USER') or os.getenv('TJ_WS_USER')
WS_PASS = os.getenv('WS_PASS') or os.getenv('TJ_WS_PASS')


def _limpar_numero_processo(numero: str) -> str:
    """Remove formatação do número do processo"""
    if '/' in numero:
        numero = numero.split('/')[0]
    return ''.join(c for c in numero if c.isdigit())


def _normalizar_texto_pdf(texto: str) -> str:
    """
    Normaliza texto extraído de PDF.

    NOTA: Esta função agora usa o serviço centralizado text_normalizer.
    Mantida por compatibilidade com código existente.
    """
    result = text_normalizer.normalize(texto)
    return result.text


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
    """Baixa conteúdo de documentos específicos via SOAP"""
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


def extrair_texto_pdf(pdf_bytes: bytes) -> str:
    """
    Extrai texto de PDF usando PyMuPDF.
    
    Tenta usar pymupdf4llm para extração otimizada,
    com fallback para extração padrão.
    """
    try:
        if hasattr(fitz, "TOOLS"):
            display_errors = getattr(fitz.TOOLS, "mupdf_display_errors", None)
            if callable(display_errors):
                display_errors(False)
            display_warnings = getattr(fitz.TOOLS, "mupdf_display_warnings", None)
            if callable(display_warnings):
                display_warnings(False)

        # Verifica se é RTF disfarçado
        if pdf_bytes.startswith(b'{\\rtf'):
            texto = pdf_bytes.decode('latin-1', errors='ignore')
            return _normalizar_texto_pdf(texto)
        
        # Abre PDF
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            num_paginas = len(doc)
            
            # Tenta extração otimizada
            try:
                md_text = pymupdf4llm.to_markdown(doc)
                if md_text and len(md_text.strip()) > 100:
                    return md_text
            except Exception:
                pass
            
            # Fallback para extração padrão
            texto_completo = ""
            for page in doc:
                texto_completo += page.get_text()
            
            return _normalizar_texto_pdf(texto_completo)
            
    except Exception as e:
        return f"[Erro na extração: {str(e)}]"


class DocumentDownloader:
    """
    Classe para download e extração de documentos do TJ-MS.
    """
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def consultar_processo(self, numero_processo: str) -> str:
        """Consulta XML completo do processo"""
        if not self.session:
            raise RuntimeError("Use 'async with DocumentDownloader()' para gerenciar a sessão")
        
        return await consultar_processo_async(self.session, numero_processo)
    
    async def baixar_documentos(
        self, 
        numero_processo: str, 
        ids_documentos: List[str]
    ) -> Dict[str, bytes]:
        """
        Baixa documentos e retorna conteúdo binário.
        
        Args:
            numero_processo: Número do processo
            ids_documentos: Lista de IDs para baixar
            
        Returns:
            Dict com id -> bytes do PDF
        """
        if not self.session:
            raise RuntimeError("Use 'async with DocumentDownloader()' para gerenciar a sessão")
        
        if not ids_documentos:
            return {}
        
        resultado = {}
        
        # Baixa em batches de 3 para evitar timeout
        BATCH_SIZE = 3
        for i in range(0, len(ids_documentos), BATCH_SIZE):
            batch = ids_documentos[i:i + BATCH_SIZE]
            
            xml_response = await baixar_documentos_async(
                self.session, numero_processo, batch
            )
            
            # Extrai conteúdo base64
            root = ET.fromstring(xml_response)
            for elem in root.iter():
                tag_no_ns = elem.tag.split('}')[-1].lower() if '}' in elem.tag else elem.tag.lower()
                if tag_no_ns == 'documento':
                    doc_id = elem.attrib.get('idDocumento') or elem.attrib.get('id')
                    if doc_id in batch:
                        conteudo_b64 = elem.attrib.get('conteudo')
                        if not conteudo_b64:
                            for child in elem:
                                child_tag = child.tag.split('}')[-1].lower()
                                if child_tag == 'conteudo' and child.text:
                                    conteudo_b64 = child.text.strip()
                                    break
                        
                        if conteudo_b64:
                            try:
                                resultado[doc_id] = base64.b64decode(conteudo_b64)
                            except Exception:
                                pass
        
        return resultado
    
    async def baixar_e_extrair_textos(
        self, 
        numero_processo: str, 
        ids_documentos: List[str]
    ) -> Dict[str, str]:
        """
        Baixa documentos e extrai texto de cada um.
        
        Args:
            numero_processo: Número do processo
            ids_documentos: Lista de IDs para baixar
            
        Returns:
            Dict com id -> texto extraído
        """
        docs_bytes = await self.baixar_documentos(numero_processo, ids_documentos)
        
        resultado = {}
        for doc_id, pdf_bytes in docs_bytes.items():
            texto = extrair_texto_pdf(pdf_bytes)
            if texto and not texto.startswith("[Erro"):
                resultado[doc_id] = texto
        
        return resultado
    
    async def baixar_todos_relevantes(
        self,
        numero_processo: str,
        ids_sentencas: List[str],
        ids_acordaos: List[str],
        ids_certidoes: List[str],
        ids_cumprimento: List[str],
        docs_info_cumprimento: List[Dict] = None,
        usar_ia_planilha: bool = True,
        logger = None,
        id_certidao_transito: str = None
    ) -> Dict[str, str]:
        """
        Baixa e extrai texto de todos os documentos relevantes EM PARALELO.

        Args:
            numero_processo: Número CNJ do processo
            ids_sentencas: IDs de sentenças
            ids_acordaos: IDs de acórdãos
            ids_certidoes: IDs de certidões
            ids_cumprimento: IDs de documentos do cumprimento (petições, planilhas)
            docs_info_cumprimento: Lista com info dos docs (id, tipo, descricao) para ajudar na classificação
            usar_ia_planilha: Se True, usa IA para identificar planilha correta quando há múltiplos candidatos
            logger: Logger opcional para debug das chamadas de IA
            id_certidao_transito: ID da certidão de trânsito em julgado

        Retorna dict categorizado por tipo:
        - sentenca: texto da(s) sentença(s)
        - acordao: texto do(s) acórdão(s)
        - certidao_citacao: texto da certidão de citação
        - certidao_intimacao: texto da certidão de intimação
        - certidao_transito: texto da certidão de trânsito em julgado
        - pedido_cumprimento: texto da petição de cumprimento
        - planilha_calculo: texto da planilha de cálculos
        """
        resultado = {}

        # Cria tasks para baixar todos os tipos em paralelo
        tasks = []
        tipos = []

        if ids_sentencas:
            tasks.append(self.baixar_e_extrair_textos(numero_processo, ids_sentencas))
            tipos.append("sentenca")

        if ids_acordaos:
            tasks.append(self.baixar_e_extrair_textos(numero_processo, ids_acordaos))
            tipos.append("acordao")

        if ids_certidoes:
            tasks.append(self.baixar_e_extrair_textos(numero_processo, ids_certidoes))
            tipos.append("certidoes")

        if id_certidao_transito:
            tasks.append(self.baixar_e_extrair_textos(numero_processo, [id_certidao_transito]))
            tipos.append("certidao_transito")

        # Verifica se já existe planilha óbvia pelo tipo ou descrição antes de baixar tudo
        planilha_obvia_id = None
        peticao_obvia_id = None
        ids_cumprimento_otimizado = ids_cumprimento

        # Códigos conhecidos de pedido de cumprimento
        codigos_pedido_cumprimento = ["286"]  # Pedido de Cumprimento de Sentença contra a Fazenda Pública
        # Termos na descrição que indicam pedido de cumprimento
        termos_pedido_cumprimento = ['pedido de cumprimento', 'cumprimento de sentença',
                                      'cumprimento de sentenca', 'execução de sentença',
                                      'execucao de sentenca']

        if ids_cumprimento and docs_info_cumprimento:
            # PRIMEIRO: Procura pedido de cumprimento óbvio (tipo 286 ou descrição clara)
            for doc_info in docs_info_cumprimento:
                doc_id = doc_info.get("id", "")
                doc_tipo = doc_info.get("tipo", "")
                doc_descr = doc_info.get("descricao", "").lower()
                is_pedido_flag = doc_info.get("is_pedido_cumprimento", False)

                # Tipo 286 ou flag do XML parser
                if doc_tipo in codigos_pedido_cumprimento or is_pedido_flag:
                    peticao_obvia_id = doc_id
                    print(f"[DOWNLOAD] ✓ Pedido de Cumprimento ÓBVIO identificado pelo tipo {doc_tipo}: {doc_id}")
                    break

                # Descrição explícita de pedido de cumprimento
                if any(termo in doc_descr for termo in termos_pedido_cumprimento):
                    peticao_obvia_id = doc_id
                    print(f"[DOWNLOAD] ✓ Pedido de Cumprimento ÓBVIO identificado pela descrição: {doc_id} - '{doc_descr}'")
                    break

            # SEGUNDO: Procura planilha óbvia (tipo 9553 ou descrição clara)
            # IMPORTANTE: Se já encontramos o pedido de cumprimento, só aceita planilhas
            # do MESMO MOMENTO (mesmo dataHora) para evitar pegar planilhas antigas
            data_hora_pedido = None
            if peticao_obvia_id:
                for doc_info in docs_info_cumprimento:
                    if doc_info.get("id", "") == peticao_obvia_id:
                        data_hora_pedido = doc_info.get("data", "")
                        print(f"[DOWNLOAD] Data/hora do pedido de cumprimento: {data_hora_pedido}")
                        break

            for doc_info in docs_info_cumprimento:
                doc_id = doc_info.get("id", "")
                doc_tipo = doc_info.get("tipo", "")
                doc_descr = doc_info.get("descricao", "").lower()
                doc_data = doc_info.get("data", "")

                # Se temos data do pedido, só aceita planilhas do MESMO momento
                if data_hora_pedido and doc_data != data_hora_pedido:
                    continue

                # Tipo 9553 = Planilha de Cálculo (código oficial)
                if doc_tipo == "9553":
                    planilha_obvia_id = doc_id
                    print(f"[DOWNLOAD] ✓ Planilha ÓBVIA identificada pelo tipo 9553: {doc_id} (data: {doc_data})")
                    break

                # Descrição explícita de planilha
                if 'planilha de cálculo' in doc_descr or 'planilha de calculo' in doc_descr:
                    planilha_obvia_id = doc_id
                    print(f"[DOWNLOAD] ✓ Planilha ÓBVIA identificada pela descrição: {doc_id} - '{doc_descr}'")
                    break

            # Se encontrou planilha óbvia E/OU pedido óbvio, otimiza o download
            if planilha_obvia_id or peticao_obvia_id:
                # Se ainda não tem pedido óbvio, procura a petição mais antiga (códigos 9500 ou 9501)
                if not peticao_obvia_id:
                    # Prioriza petições confirmadas pelo complemento do movimento
                    peticoes_confirmadas = []
                    peticoes_candidatas = []

                    # Termos que excluem do complemento
                    termos_excluir = ['cópia de lei', 'copia de lei', 'certidão', 'certidao',
                                      'comprovante', 'recibo', 'procuração', 'procuracao']
                    # Termos que confirmam petição no complemento
                    termos_peticao_compl = ['petição', 'peticao', 'cumprimento de sentença',
                                      'cumprimento de sentenca', 'inicial', 'requerimento']

                    for doc_info in docs_info_cumprimento:
                        doc_id = doc_info.get("id", "")
                        doc_tipo = doc_info.get("tipo", "")
                        doc_descr = doc_info.get("descricao", "").lower()
                        data_str = doc_info.get("data", "")
                        complemento = doc_info.get("complemento_movimento", "").lower()

                        if doc_id == planilha_obvia_id:
                            continue

                        # Exclui se complemento indica que não é petição
                        if any(termo in complemento for termo in termos_excluir):
                            print(f"[DOWNLOAD] Documento {doc_id} excluído pelo complemento: '{complemento[:40]}'")
                            continue

                        # É uma petição (não procuração)
                        is_peticao = doc_tipo in ["9500", "9501"] and 'procura' not in doc_descr
                        if is_peticao:
                            # Verifica se é confirmada pelo complemento
                            is_confirmada = any(termo in complemento for termo in termos_peticao_compl)
                            if is_confirmada:
                                peticoes_confirmadas.append((doc_id, data_str))
                            else:
                                peticoes_candidatas.append((doc_id, data_str))

                    # Prioriza confirmadas, senão usa candidatas
                    peticoes_final = peticoes_confirmadas if peticoes_confirmadas else peticoes_candidatas

                    # Ordena por data (mais antiga primeiro)
                    if peticoes_final:
                        peticoes_final.sort(key=lambda x: x[1] if x[1] else "99999999")
                        peticao_obvia_id = peticoes_final[0][0]
                        confirmacao = " (confirmada)" if peticoes_confirmadas else ""
                        print(f"[DOWNLOAD] ✓ Petição identificada: {peticao_obvia_id}{confirmacao}")

                # Otimiza: baixa apenas planilha e petição, não todos os documentos
                ids_cumprimento_otimizado = []
                if planilha_obvia_id:
                    ids_cumprimento_otimizado.append(planilha_obvia_id)
                if peticao_obvia_id:
                    ids_cumprimento_otimizado.append(peticao_obvia_id)

                print(f"[DOWNLOAD] OTIMIZAÇÃO: Baixando apenas {len(ids_cumprimento_otimizado)} docs (planilha + petição) em vez de {len(ids_cumprimento)}")

        if ids_cumprimento_otimizado:
            tasks.append(self.baixar_e_extrair_textos(numero_processo, ids_cumprimento_otimizado))
            tipos.append("cumprimento")

        if not tasks:
            return resultado

        # Executa todas as tasks em paralelo
        resultados_paralelos = await asyncio.gather(*tasks, return_exceptions=True)

        # Processa resultados
        for i, (tipo, res) in enumerate(zip(tipos, resultados_paralelos)):
            if isinstance(res, Exception):
                continue  # Ignora erros individuais

            textos = res

            if tipo == "sentenca" and textos:
                resultado["sentenca"] = "\n\n---\n\n".join(textos.values())

            elif tipo == "acordao" and textos:
                resultado["acordao"] = "\n\n---\n\n".join(textos.values())

            elif tipo == "certidoes" and textos:
                # Separa por tipo baseado na ordem (citação vem primeiro, depois intimação)
                certidoes_lista = list(textos.values())
                if len(certidoes_lista) >= 1:
                    resultado["certidao_citacao"] = certidoes_lista[0]
                if len(certidoes_lista) >= 2:
                    resultado["certidao_intimacao"] = certidoes_lista[1]

            elif tipo == "certidao_transito" and textos:
                # Certidão de trânsito em julgado
                resultado["certidao_transito"] = "\n\n---\n\n".join(textos.values())
                print(f"[DOWNLOAD] ✓ Certidão de trânsito em julgado baixada")

            elif tipo == "cumprimento" and textos:
                # Se já identificamos planilha óbvia, usa diretamente sem classificação complexa
                if planilha_obvia_id and planilha_obvia_id in textos:
                    resultado["planilha_calculo"] = textos[planilha_obvia_id]
                    resultado["_planilha_id"] = planilha_obvia_id
                    print(f"[DOWNLOAD] ✓ Usando planilha ÓBVIA diretamente: {planilha_obvia_id} (IA não necessária)")

                    if peticao_obvia_id and peticao_obvia_id in textos:
                        resultado["pedido_cumprimento"] = textos[peticao_obvia_id]
                        resultado["_peticao_id"] = peticao_obvia_id
                        print(f"[DOWNLOAD] ✓ Usando petição identificada: {peticao_obvia_id}")

                    # Pula toda a classificação complexa
                    continue

                # Caso contrário, faz classificação normal (com IA se necessário)
                # Monta mapa de descrições dos documentos
                descricoes = {}
                if docs_info_cumprimento:
                    for doc_info in docs_info_cumprimento:
                        descricoes[doc_info.get("id", "")] = doc_info.get("descricao", "")

                # Monta mapa de datas dos documentos para ordenação
                datas_docs = {}
                if docs_info_cumprimento:
                    for doc_info in docs_info_cumprimento:
                        doc_id = doc_info.get("id", "")
                        data_str = doc_info.get("data", "")
                        datas_docs[doc_id] = data_str

                # Monta mapa de complemento do movimento (info do XML)
                complementos_mov = {}
                if docs_info_cumprimento:
                    for doc_info in docs_info_cumprimento:
                        doc_id = doc_info.get("id", "")
                        complemento = doc_info.get("complemento_movimento", "")
                        complementos_mov[doc_id] = complemento

                # Monta mapa de tipos de documento e flags
                tipos_docs = {}
                is_pedido_cumprimento_flags = {}
                if docs_info_cumprimento:
                    for doc_info in docs_info_cumprimento:
                        doc_id = doc_info.get("id", "")
                        tipos_docs[doc_id] = doc_info.get("tipo", "")
                        is_pedido_cumprimento_flags[doc_id] = doc_info.get("is_pedido_cumprimento", False)

                # Separa candidatos a planilha vs petições vs procurações vs outros excludentes
                candidatos_planilha = {}
                peticoes = {}
                pedidos_cumprimento_286 = {}  # Tipo 286 (prioridade máxima)
                procuracoes = {}  # Excluídos da classificação
                outros_excluidos = {}  # Cópia de lei, certidões, etc

                for doc_id, texto in textos.items():
                    texto_lower = texto.lower()
                    descricao = descricoes.get(doc_id, "").lower()
                    complemento_mov = complementos_mov.get(doc_id, "").lower()
                    tipo_doc = tipos_docs.get(doc_id, "")
                    is_pedido_flag = is_pedido_cumprimento_flags.get(doc_id, False)

                    # ZERO: Verifica se é um Pedido de Cumprimento (tipo 286 ou flag)
                    if tipo_doc in codigos_pedido_cumprimento or is_pedido_flag:
                        pedidos_cumprimento_286[doc_id] = texto
                        print(f"[DOWNLOAD] Documento {doc_id} identificado como PEDIDO DE CUMPRIMENTO (tipo {tipo_doc})")
                        continue

                    # PRIMEIRO: Verifica o complemento do movimento (fonte mais confiável)
                    # O complemento diz exatamente o que é o documento na movimentação
                    termos_excluir_complemento = [
                        'cópia de lei', 'copia de lei',
                        'cópia de acórdão', 'copia de acordao',
                        'cópia de sentença', 'copia de sentenca',
                        'cópia de decisão', 'copia de decisao',
                        'certidão', 'certidao',
                        'comprovante', 'recibo',
                        'procuração', 'procuracao'
                    ]

                    is_excluido_por_complemento = any(termo in complemento_mov for termo in termos_excluir_complemento)

                    if is_excluido_por_complemento:
                        outros_excluidos[doc_id] = texto
                        print(f"[DOWNLOAD] Documento {doc_id} excluído pelo complemento: '{complemento_mov[:50]}...'")
                        continue

                    # SEGUNDO: Identifica procurações (excluídas de petição/planilha)
                    # Procuração pode ter código 9501 mas descrição "Procuração"
                    termos_procuracao = ['procuração', 'procuracao', 'poderes', 'substabelecer',
                                         'outorgante', 'outorgado', 'mandato']
                    is_procuracao = 'procura' in descricao or any(termo in texto_lower[:2000] for termo in termos_procuracao)

                    if is_procuracao:
                        procuracoes[doc_id] = texto
                        print(f"[DOWNLOAD] Documento {doc_id} identificado como PROCURAÇÃO (excluído)")
                        continue

                    # Verifica se parece planilha por palavras-chave
                    termos_planilha = ['planilha', 'cálculo', 'calculo', 'demonstrativo',
                                       'memória de cálculo', 'memoria de calculo', 'evolução',
                                       'correção monetária', 'correcao monetaria', 'juros']
                    parece_planilha = any(termo in texto_lower or termo in descricao for termo in termos_planilha)

                    # Verifica se é claramente uma petição (pelo conteúdo)
                    termos_peticao_conteudo = ['excelentíssimo', 'excelentissimo', 'meritíssimo',
                                               'requer', 'ante o exposto', 'diante do exposto',
                                               'pede deferimento', 'termos em que']
                    parece_peticao_conteudo = any(termo in texto_lower for termo in termos_peticao_conteudo)

                    # Verifica se tem "Petição" na descrição do XML
                    is_peticao_descricao = 'peti' in descricao and 'procura' not in descricao

                    if parece_planilha and not parece_peticao_conteudo and not is_peticao_descricao:
                        candidatos_planilha[doc_id] = (texto, descricoes.get(doc_id, ""))
                    else:
                        peticoes[doc_id] = texto

                # Se não encontrou candidatos por palavras-chave, todos (exceto procurações, outros excluídos e pedidos 286) são candidatos
                if not candidatos_planilha and textos:
                    for doc_id, texto in textos.items():
                        if doc_id not in procuracoes and doc_id not in outros_excluidos and doc_id not in pedidos_cumprimento_286:
                            candidatos_planilha[doc_id] = (texto, descricoes.get(doc_id, ""))
                    peticoes = {}

                print(f"[DOWNLOAD] Documentos de cumprimento: {len(textos)} total")
                print(f"[DOWNLOAD]   - Pedidos de Cumprimento (286): {len(pedidos_cumprimento_286)}")
                print(f"[DOWNLOAD]   - Candidatos a planilha: {len(candidatos_planilha)}")
                print(f"[DOWNLOAD]   - Petições identificadas: {len(peticoes)}")
                print(f"[DOWNLOAD]   - Procurações (excluídas): {len(procuracoes)}")
                print(f"[DOWNLOAD]   - Outros excluídos por complemento: {len(outros_excluidos)}")

                # Usa IA para identificar planilha correta se há múltiplos candidatos
                if len(candidatos_planilha) > 1 and usar_ia_planilha:
                    print(f"[DOWNLOAD] Usando IA para identificar planilha correta entre {len(candidatos_planilha)} candidatos...")
                    try:
                        from .agentes import AnalisadorPlanilhaCalculo
                        analisador = AnalisadorPlanilhaCalculo(logger=logger)
                        planilha_identificada = await analisador.identificar_planilha_correta(candidatos_planilha)

                        if planilha_identificada:
                            resultado["planilha_calculo"] = planilha_identificada["texto"]
                            resultado["_planilha_id"] = planilha_identificada["doc_id"]
                            resultado["_planilha_info"] = {
                                "id": planilha_identificada["doc_id"],
                                "valor_total": planilha_identificada.get("valor_total_encontrado"),
                                "data_base": planilha_identificada.get("data_base_encontrada"),
                                "confianca": planilha_identificada.get("confianca")
                            }
                            print(f"[DOWNLOAD] ✓ Planilha identificada por IA: {planilha_identificada['doc_id']}")

                            # O restante vai para pedido_cumprimento
                            for doc_id, (texto, _) in candidatos_planilha.items():
                                if doc_id != planilha_identificada["doc_id"]:
                                    if "pedido_cumprimento" not in resultado:
                                        resultado["pedido_cumprimento"] = texto
                                        resultado["_peticao_id"] = doc_id
                        else:
                            # IA não identificou planilha, usa o primeiro candidato
                            primeiro_id, (primeiro_texto, _) = list(candidatos_planilha.items())[0]
                            resultado["planilha_calculo"] = primeiro_texto
                            resultado["_planilha_id"] = primeiro_id
                            print(f"[DOWNLOAD] IA não identificou planilha, usando primeiro candidato: {primeiro_id}")
                    except Exception as e:
                        print(f"[DOWNLOAD] Erro ao usar IA para planilha: {e}")
                        # Fallback: usa o primeiro candidato
                        if candidatos_planilha:
                            primeiro_id, (primeiro_texto, _) = list(candidatos_planilha.items())[0]
                            resultado["planilha_calculo"] = primeiro_texto
                            resultado["_planilha_id"] = primeiro_id

                elif len(candidatos_planilha) == 1:
                    # Só um candidato, usa diretamente
                    doc_id, (texto, _) = list(candidatos_planilha.items())[0]
                    resultado["planilha_calculo"] = texto
                    resultado["_planilha_id"] = doc_id
                    print(f"[DOWNLOAD] Único candidato a planilha: {doc_id}")

                elif candidatos_planilha:
                    # Múltiplos candidatos mas IA desabilitada, usa o primeiro
                    primeiro_id, (primeiro_texto, _) = list(candidatos_planilha.items())[0]
                    resultado["planilha_calculo"] = primeiro_texto
                    resultado["_planilha_id"] = primeiro_id
                    print(f"[DOWNLOAD] Múltiplos candidatos (IA desabilitada), usando primeiro: {primeiro_id}")

                # Adiciona pedido de cumprimento identificado
                # PRIORIDADE: tipo 286 > petições com complemento confirmado > petições por data

                # Se temos tipo 286, usa diretamente (máxima prioridade)
                if pedidos_cumprimento_286:
                    # Usa o primeiro (ou mais recente se houver múltiplos)
                    primeiro_doc_id = list(pedidos_cumprimento_286.keys())[0]
                    resultado["pedido_cumprimento"] = pedidos_cumprimento_286[primeiro_doc_id]
                    resultado["_peticao_id"] = primeiro_doc_id
                    print(f"[DOWNLOAD] ✓ Pedido de cumprimento identificado pelo tipo 286: {primeiro_doc_id}")

                # Senão, usa petições normais
                elif peticoes:
                    # Função para converter data "DD/MM/YYYY HH:MM" em formato ordenável
                    def data_para_ordenacao(doc_id):
                        data_str = datas_docs.get(doc_id, "")
                        if not data_str:
                            return "99999999999999"  # Fallback para o fim
                        try:
                            # Formato: "29/08/2025 16:41"
                            from datetime import datetime
                            dt = datetime.strptime(data_str, "%d/%m/%Y %H:%M")
                            return dt.strftime("%Y%m%d%H%M%S")
                        except:
                            return "99999999999999"

                    # Verifica quais petições têm complemento confirmando que são petições
                    termos_peticao_complemento = ['petição', 'peticao', 'cumprimento de sentença',
                                                   'cumprimento de sentenca', 'inicial', 'requerimento']
                    peticoes_confirmadas = {}
                    peticoes_nao_confirmadas = {}

                    for doc_id, texto in peticoes.items():
                        complemento = complementos_mov.get(doc_id, "").lower()
                        is_peticao_por_complemento = any(termo in complemento for termo in termos_peticao_complemento)

                        if is_peticao_por_complemento:
                            peticoes_confirmadas[doc_id] = texto
                            print(f"[DOWNLOAD] Documento {doc_id} CONFIRMADO como petição pelo complemento: '{complemento[:50]}...'")
                        else:
                            peticoes_nao_confirmadas[doc_id] = texto
                            if complemento:
                                print(f"[DOWNLOAD] Documento {doc_id} não confirmado pelo complemento: '{complemento[:50]}...'")

                    # Prioriza petições confirmadas pelo complemento
                    peticoes_para_ordenar = peticoes_confirmadas if peticoes_confirmadas else peticoes

                    # Ordena petições por data (mais antiga primeiro)
                    peticoes_ordenadas = sorted(
                        peticoes_para_ordenar.items(),
                        key=lambda x: data_para_ordenacao(x[0])
                    )

                    print(f"[DOWNLOAD] Petições ordenadas por data:")
                    for doc_id, _ in peticoes_ordenadas:
                        data = datas_docs.get(doc_id, "?")
                        descr = descricoes.get(doc_id, "?")
                        complemento = complementos_mov.get(doc_id, "")[:30]
                        print(f"[DOWNLOAD]   - {doc_id}: {data} - {descr} [complemento: {complemento}]")

                    # A primeira petição (mais antiga, prioridade para confirmadas) é o pedido de cumprimento
                    primeiro_doc_id, primeiro_texto = peticoes_ordenadas[0]
                    resultado["pedido_cumprimento"] = primeiro_texto
                    resultado["_peticao_id"] = primeiro_doc_id
                    confirmacao = " (confirmado pelo complemento)" if primeiro_doc_id in peticoes_confirmadas else ""
                    print(f"[DOWNLOAD] ✓ Pedido de cumprimento identificado: {primeiro_doc_id} (mais antigo){confirmacao}")

        return resultado


async def baixar_documentos_processo(
    numero_processo: str,
    ids_sentencas: List[str] = None,
    ids_acordaos: List[str] = None,
    ids_certidoes: List[str] = None,
    ids_cumprimento: List[str] = None
) -> Dict[str, str]:
    """
    Função de conveniência para baixar documentos de um processo.
    
    Returns:
        Dict categorizado com textos extraídos
    """
    async with DocumentDownloader() as downloader:
        return await downloader.baixar_todos_relevantes(
            numero_processo,
            ids_sentencas or [],
            ids_acordaos or [],
            ids_certidoes or [],
            ids_cumprimento or []
        )
