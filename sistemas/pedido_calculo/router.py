# sistemas/pedido_calculo/router.py
"""
Router do sistema de Pedido de Cálculo

Endpoints:
- POST /processar-xml: Processa XML do processo (Agente 1)
- POST /baixar-documentos: Baixa documentos identificados
- POST /extrair-informacoes: Extrai informações dos PDFs (Agente 2)
- POST /gerar-pedido: Gera pedido de cálculo (Agente 3)
- POST /processar-stream: Pipeline completo com SSE
- POST /exportar-docx: Exporta para DOCX

Autor: LAB/PGE-MS
"""

import os
import json
import uuid
import asyncio
from datetime import datetime
from typing import Optional, List, Dict, AsyncGenerator

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth.dependencies import get_current_active_user, get_current_user_from_token_or_query
from auth.models import User
from database.connection import get_db
from admin.models import ConfiguracaoIA, PromptConfig

from .services import PedidoCalculoService
from .models import ResultadoAgente1, ResultadoAgente2
from .ia_logger import create_logger, get_logger


def _converter_rtf_para_pdf(rtf_bytes: bytes) -> bytes:
    """
    Converte documento RTF para PDF.

    Usa striprtf para extrair texto e PyMuPDF para gerar PDF.
    """
    import io
    import re

    try:
        # Tenta usar striprtf se disponível
        try:
            from striprtf.striprtf import rtf_to_text
            texto = rtf_to_text(rtf_bytes.decode('latin-1', errors='ignore'))
        except ImportError:
            # Fallback: extrai texto manualmente removendo comandos RTF
            texto = rtf_bytes.decode('latin-1', errors='ignore')
            # Remove comandos RTF básicos
            texto = re.sub(r'\\[a-z]+\d*\s?', '', texto)
            texto = re.sub(r'[{}]', '', texto)
            texto = texto.replace('\\par', '\n')
            texto = texto.replace('\r\n', '\n')

        # Gera PDF usando PyMuPDF
        import fitz

        # Cria novo documento PDF
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)  # A4

        # Configurações de texto
        font_size = 10
        margin = 50
        max_width = 595 - (2 * margin)
        y_position = margin

        # Divide texto em linhas
        linhas = texto.split('\n')

        for linha in linhas:
            if not linha.strip():
                y_position += font_size
                continue

            # Quebra linha se muito longa
            while linha:
                # Calcula quantos caracteres cabem na linha
                chars_por_linha = int(max_width / (font_size * 0.5))
                parte = linha[:chars_por_linha]
                linha = linha[chars_por_linha:]

                # Nova página se necessário
                if y_position > 842 - margin:
                    page = doc.new_page(width=595, height=842)
                    y_position = margin

                # Insere texto
                page.insert_text(
                    (margin, y_position),
                    parte,
                    fontsize=font_size,
                    fontname="helv"
                )
                y_position += font_size * 1.2

        # Salva em bytes
        pdf_bytes = doc.tobytes()
        doc.close()

        return pdf_bytes

    except Exception as e:
        print(f"[ERRO] Falha ao converter RTF para PDF: {e}")
        # Retorna um PDF de erro
        import fitz
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 50), f"Erro ao converter documento RTF: {str(e)}", fontsize=12)
        pdf_bytes = doc.tobytes()
        doc.close()
        return pdf_bytes


router = APIRouter(tags=["Pedido de Cálculo"])

# Nome do sistema para configurações
SISTEMA = "pedido_calculo"

# Diretório temporário para arquivos DOCX
TEMP_DIR = os.path.join(os.path.dirname(__file__), 'temp_docs')
os.makedirs(TEMP_DIR, exist_ok=True)


# ============================================
# Request/Response Models
# ============================================

class ProcessarXMLRequest(BaseModel):
    """Request para processar XML do processo"""
    xml_texto: str


class BaixarDocumentosRequest(BaseModel):
    """Request para baixar documentos"""
    numero_processo: str
    ids_sentencas: List[str] = []
    ids_acordaos: List[str] = []
    ids_certidoes: List[str] = []
    ids_cumprimento: List[str] = []


class ExtrairInformacoesRequest(BaseModel):
    """Request para extrair informações dos documentos"""
    textos_documentos: Dict[str, str]


class GerarPedidoRequest(BaseModel):
    """Request para gerar pedido de cálculo"""
    dados_agente1: Dict
    dados_agente2: Dict


class ProcessarStreamRequest(BaseModel):
    """Request para processar via stream"""
    numero_cnj: str
    sobrescrever_existente: bool = False  # Se True, sobrescreve registro anterior do mesmo processo


class ExportarDocxRequest(BaseModel):
    """Request para exportar markdown para DOCX"""
    markdown: str
    numero_processo: Optional[str] = None


class FeedbackRequest(BaseModel):
    """Request para enviar feedback sobre o pedido gerado"""
    geracao_id: int
    avaliacao: str  # 'correto', 'parcial', 'incorreto', 'erro_ia'
    nota: Optional[int] = None  # Nota de 1 a 5 estrelas
    comentario: Optional[str] = None
    campos_incorretos: Optional[list] = None


# ============================================
# Endpoints
# ============================================

@router.post("/processar-xml")
async def processar_xml(
    req: ProcessarXMLRequest,
    current_user: User = Depends(get_current_active_user)
):
    """
    Processa XML do processo (Agente 1).
    
    Extrai dados básicos, identifica documentos para download
    e movimentos relevantes.
    """
    try:
        service = PedidoCalculoService()
        resultado, erro = await service.processar_xml(req.xml_texto)
        
        if erro:
            raise HTTPException(status_code=400, detail=erro)
        
        return {
            "status": "sucesso",
            "dados": resultado.to_dict()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/baixar-documentos")
async def baixar_documentos(
    req: BaixarDocumentosRequest,
    current_user: User = Depends(get_current_active_user)
):
    """
    Baixa documentos identificados do TJ-MS.
    
    Retorna textos extraídos dos PDFs.
    """
    try:
        from .document_downloader import DocumentDownloader
        
        async with DocumentDownloader() as downloader:
            textos = await downloader.baixar_todos_relevantes(
                req.numero_processo,
                ids_sentencas=req.ids_sentencas,
                ids_acordaos=req.ids_acordaos,
                ids_certidoes=req.ids_certidoes,
                ids_cumprimento=req.ids_cumprimento
            )
        
        return {
            "status": "sucesso",
            "documentos_baixados": len(textos),
            "textos": textos
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/extrair-informacoes")
async def extrair_informacoes(
    req: ExtrairInformacoesRequest,
    current_user: User = Depends(get_current_active_user)
):
    """
    Extrai informações dos documentos (Agente 2).
    
    Analisa textos e extrai dados estruturados.
    """
    try:
        service = PedidoCalculoService()
        resultado, erro = await service.extrair_informacoes(req.textos_documentos)
        
        if erro:
            raise HTTPException(status_code=400, detail=erro)
        
        return {
            "status": "sucesso",
            "dados": resultado.to_dict()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/gerar-pedido")
async def gerar_pedido(
    req: GerarPedidoRequest,
    current_user: User = Depends(get_current_active_user)
):
    """
    Gera pedido de cálculo (Agente 3).
    
    Retorna documento em formato Markdown.
    """
    try:
        from .agentes import Agente3GeracaoPedido
        from .models import (
            ResultadoAgente1, ResultadoAgente2,
            DadosBasicos, DocumentosParaDownload, MovimentosRelevantes,
            PeriodoCondenacao, CorrecaoMonetaria, JurosMoratorios,
            DatasProcessuais, CalculoExequente
        )
        
        # Reconstrói objetos a partir dos dicts
        db = req.dados_agente1.get("dados_basicos", {})
        dados_basicos = DadosBasicos(
            numero_processo=db.get("numero_processo", ""),
            autor=db.get("autor", ""),
            cpf_autor=db.get("cpf_autor"),
            reu=db.get("reu", "Estado de Mato Grosso do Sul"),
            comarca=db.get("comarca"),
            vara=db.get("vara")
        )
        
        agente1 = ResultadoAgente1(
            dados_basicos=dados_basicos,
            documentos_para_download=DocumentosParaDownload(),
            movimentos_relevantes=MovimentosRelevantes()
        )
        
        # Reconstrói Agente 2
        ext = req.dados_agente2
        agente2 = ResultadoAgente2(
            objeto_condenacao=ext.get("objeto_condenacao"),
            valor_solicitado_parte=ext.get("valor_solicitado_parte"),
            criterios_calculo=ext.get("criterios_calculo", [])
        )
        
        # Período
        periodo = ext.get("periodo_condenacao", {})
        if periodo:
            agente2.periodo_condenacao = PeriodoCondenacao(
                inicio=periodo.get("inicio"),
                fim=periodo.get("fim")
            )
        
        # Correção
        cm = ext.get("correcao_monetaria", {})
        if cm:
            agente2.correcao_monetaria = CorrecaoMonetaria(
                indice=cm.get("indice"),
                termo_inicial=cm.get("termo_inicial"),
                termo_final=cm.get("termo_final"),
                observacao=cm.get("observacao")
            )
        
        # Juros
        juros = ext.get("juros_moratorios", {})
        if juros:
            agente2.juros_moratorios = JurosMoratorios(
                taxa=juros.get("taxa"),
                termo_inicial=juros.get("termo_inicial"),
                termo_final=juros.get("termo_final"),
                observacao=juros.get("observacao")
            )
        
        # Datas
        datas = ext.get("datas", {})
        if datas:
            from datetime import datetime
            def parse_date(s):
                if not s:
                    return None
                try:
                    return datetime.strptime(s[:10], "%d/%m/%Y").date()
                except:
                    return None
            
            agente2.datas = DatasProcessuais(
                citacao_recebimento=parse_date(datas.get("citacao_recebimento")),
                transito_julgado=parse_date(datas.get("transito_julgado")),
                intimacao_impugnacao_recebimento=parse_date(datas.get("intimacao_impugnacao_recebimento"))
            )
        
        # Cálculo exequente
        calc = ext.get("calculo_exequente", {})
        if calc:
            agente2.calculo_exequente = CalculoExequente(
                valor_total=calc.get("valor_total"),
                data_base=calc.get("data_base")
            )
        
        # Gera pedido
        agente3 = Agente3GeracaoPedido()
        markdown = await agente3.gerar(agente1, agente2)
        
        return {
            "status": "sucesso",
            "pedido_markdown": markdown
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/processar-stream")
async def processar_stream(
    req: ProcessarStreamRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Processa processo via número CNJ com streaming SSE.

    Pipeline completo: Consulta TJ-MS → XML → Documentos → Extração → Geração
    """
    # Captura IDs fora do gerador para poder salvar no banco
    user_id = current_user.id
    numero_cnj = req.numero_cnj
    sobrescrever_existente = req.sobrescrever_existente

    async def event_generator() -> AsyncGenerator[str, None]:
        # Variáveis para salvar no histórico
        geracao_id = None
        agente1_result = None
        agente2_result = None
        markdown = None
        documentos_baixados = []
        tempo_inicio = datetime.now()

        # Cria logger para esta requisição
        ia_logger = create_logger()

        try:
            # ============================================================
            # ETAPA 1: CONSULTA AO TJ-MS E ANÁLISE DO XML
            # ============================================================
            yield f"data: {json.dumps({'tipo': 'inicio', 'mensagem': 'Iniciando processamento do pedido de cálculo...'})}\n\n"

            yield f"data: {json.dumps({'tipo': 'agente', 'agente': 1, 'status': 'ativo', 'mensagem': 'Conectando ao webservice do TJ-MS...'})}\n\n"

            yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'Buscando processo CNJ: {numero_cnj}'})}\n\n"

            from .document_downloader import DocumentDownloader

            async with DocumentDownloader() as downloader:
                xml_texto = await downloader.consultar_processo(numero_cnj)

            if not xml_texto or '<sucesso>false</sucesso>' in xml_texto.lower():
                yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': f'Processo {numero_cnj} não encontrado no TJ-MS. Verifique se o número está correto.'})}\n\n"
                return

            yield f"data: {json.dumps({'tipo': 'info', 'mensagem': 'XML do processo recebido, iniciando análise da estrutura...'})}\n\n"

            # Analisa o XML (passa o logger para as chamadas de IA)
            service = PedidoCalculoService(logger=ia_logger)
            agente1_result, erro = await service.processar_xml(xml_texto)

            if erro:
                yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': f'Erro na análise do XML: {erro}'})}\n\n"
                return

            # Dados básicos extraídos
            db_info = agente1_result.dados_basicos
            autor_info = db_info.autor or "[não identificado]"
            comarca_info = db_info.comarca or "[N/I]"
            vara_info = db_info.vara or "[N/I]"
            yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'Processo identificado: {db_info.numero_processo}'})}\n\n"
            yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'Autor: {autor_info}'})}\n\n"
            yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'Comarca/Vara: {comarca_info} - {vara_info}'})}\n\n"

            # Documentos identificados
            docs = agente1_result.documentos_para_download
            qtd_sentencas = len(docs.sentencas)
            qtd_acordaos = len(docs.acordaos)
            qtd_certidoes = len(docs.certidoes_citacao_intimacao)
            qtd_cumprimento = len(docs.pedido_cumprimento.get("documentos", [])) if docs.pedido_cumprimento else 0
            total_docs = qtd_sentencas + qtd_acordaos + qtd_certidoes + qtd_cumprimento

            yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'Documentos identificados para análise: {total_docs} documento(s)'})}\n\n"

            if qtd_sentencas > 0:
                yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'  • {qtd_sentencas} sentença(s)'})}\n\n"
            if qtd_acordaos > 0:
                yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'  • {qtd_acordaos} acórdão(s)'})}\n\n"
            if qtd_certidoes > 0:
                # Mostra detalhes de cada certidão identificada
                for cert in docs.certidoes_citacao_intimacao:
                    tipo_intim = "Intimacao p/ Cumprimento" if cert.tipo.value == "intimacao_impugnacao" else cert.tipo.value.replace("_", " ").title()
                    tipo_cert = "Sistema" if cert.tipo_certidao == "sistema" else "Cartorio (decurso)"
                    data_receb = cert.data_recebimento.strftime("%d/%m/%Y") if cert.data_recebimento else "N/A"
                    termo_ini = cert.termo_inicial_prazo.strftime("%d/%m/%Y") if cert.termo_inicial_prazo else "N/A"
                    yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'  - {tipo_intim} (Cert. {tipo_cert})'})}\n\n"
                    yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'    Recebimento: {data_receb} | Termo inicial (art. 224 CPC): {termo_ini}'})}\n\n"
            if qtd_cumprimento > 0:
                yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'  • {qtd_cumprimento} documento(s) do pedido de cumprimento'})}\n\n"
                # Debug detalhado: mostra TODOS os detalhes dos documentos
                for doc in docs.pedido_cumprimento.get("documentos", []):
                    tipo_cod = doc.get("tipo", "")
                    # Identifica planilha por código OU descrição
                    is_planilha = tipo_cod in ["9553", "61", "9535"]
                    doc_descr = doc.get("descricao", "")
                    if not is_planilha and doc_descr:
                        descr_lower = doc_descr.lower()
                        is_planilha = any(t in descr_lower for t in ['planilha', 'cálculo', 'calculo', 'demonstrativo'])
                    tipo_doc = "PLANILHA" if is_planilha else "Petição"
                    doc_id = doc.get("id", "")
                    doc_data = doc.get("data", "")
                    yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'    - {tipo_doc} (código {tipo_cod}): {doc_descr}'})}\n\n"
                    yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'      ID: {doc_id} | Data: {doc_data}'})}\n\n"
            else:
                # Debug: Se não encontrou documentos do cumprimento, mostrar aviso
                yield f"data: {json.dumps({'tipo': 'info', 'mensagem': '  [AVISO] Nenhum documento do pedido de cumprimento identificado!'})}\n\n"
                if docs.pedido_cumprimento:
                    data_ref = docs.pedido_cumprimento.get("data_referencia", "N/A")
                    yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'  [DEBUG] Data referência (intimação): {data_ref}'})}\n\n"

            # Mostra certidões candidatas para análise com IA
            if docs.certidoes_candidatas:
                yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'  • {len(docs.certidoes_candidatas)} certidão(ões) candidata(s) para análise com IA'})}\n\n"
                if docs.certidao_heuristica:
                    # Mostra sugestão da heurística (será validada pela IA)
                    tipo_cert_str = "Sistema" if docs.certidao_heuristica.tipo_certidao == "sistema" else "Cartório (decurso)"
                    yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'    Sugestão heurística: Cert. {tipo_cert_str} (será validada pela IA)'})}\n\n"
            else:
                yield f"data: {json.dumps({'tipo': 'info', 'mensagem': 'Nenhuma certidão candidata identificada no XML'})}\n\n"

            yield f"data: {json.dumps({'tipo': 'agente', 'agente': 1, 'status': 'concluido', 'mensagem': f'Análise do XML concluída - {db_info.numero_processo}'})}\n\n"

            # ============================================================
            # ETAPA 1.5: CUMPRIMENTO AUTÔNOMO - BUSCAR PROCESSO DE ORIGEM
            # ============================================================
            # Variáveis para guardar documentos da origem (baixar separadamente)
            docs_origem_para_baixar = None
            movimentos_origem = None
            dados_basicos_origem = None

            # Debug: mostra se é cumprimento autônomo
            tipo_processo = "CUMPRIMENTO AUTÔNOMO" if docs.is_cumprimento_autonomo else "Processo normal"
            yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'Tipo de processo: {tipo_processo}'})}\n\n"

            if docs.is_cumprimento_autonomo:
                yield f"data: {json.dumps({'tipo': 'info', 'mensagem': 'Buscando documentos do processo de ORIGEM (sentença, acórdão)...'})}\n\n"

                numero_origem = docs.numero_processo_origem
                origem_info = numero_origem if numero_origem else "NÃO ENCONTRADO"
                yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'Número da origem no XML: {origem_info}'})}\n\n"

                # Se não encontrou número no XML, extrai da petição inicial com IA
                if not numero_origem and docs.id_peticao_inicial:
                    yield f"data: {json.dumps({'tipo': 'info', 'mensagem': 'Número do processo de origem não encontrado no XML - analisando petição inicial...'})}\n\n"

                    # Baixa e extrai texto da petição inicial
                    async with DocumentDownloader() as downloader_pet:
                        textos_peticao = await downloader_pet.baixar_e_extrair_textos(
                            db_info.numero_processo,
                            [docs.id_peticao_inicial]
                        )

                    if textos_peticao and docs.id_peticao_inicial in textos_peticao:
                        texto_peticao = textos_peticao[docs.id_peticao_inicial]
                        yield f"data: {json.dumps({'tipo': 'info', 'mensagem': 'Extraindo número do processo de origem com IA...'})}\n\n"

                        from .agentes import ExtratorProcessoOrigem
                        extrator = ExtratorProcessoOrigem()
                        numero_origem = await extrator.extrair_numero_origem(texto_peticao)

                        if numero_origem:
                            docs.numero_processo_origem = numero_origem
                            yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'Processo de origem identificado pela IA: {numero_origem}'})}\n\n"
                        else:
                            yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': 'Não foi possível identificar o processo de origem'})}\n\n"
                    else:
                        yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': 'Não foi possível baixar a petição inicial'})}\n\n"

                # Se temos o número do processo de origem, consulta e extrai documentos
                # IMPORTANTE: Busca RECURSIVA até encontrar processo de CONHECIMENTO (não cumprimento)
                if numero_origem:
                    # Limite de recursão para evitar loops infinitos
                    MAX_RECURSAO = 5
                    processos_visitados = set()
                    processo_atual = numero_origem
                    encontrou_conhecimento = False

                    for nivel in range(MAX_RECURSAO):
                        if processo_atual in processos_visitados:
                            yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': f'Loop detectado na cadeia de processos!'})}\n\n"
                            break

                        processos_visitados.add(processo_atual)
                        yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'Consultando processo: {processo_atual} (nível {nivel + 1})...'})}\n\n"

                        try:
                            async with DocumentDownloader() as downloader_origem:
                                xml_origem = await downloader_origem.consultar_processo(processo_atual)

                            if not xml_origem:
                                yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': f'Falha ao consultar {processo_atual}'})}\n\n"
                                break

                            from .xml_parser import XMLParser
                            parser_origem = XMLParser(xml_origem)
                            docs_temp = parser_origem.identificar_documentos_para_download()
                            movimentos_temp = parser_origem.extrair_movimentos_relevantes()
                            dados_basicos_temp = parser_origem.extrair_dados_basicos()

                            # Verifica se é cumprimento autônomo
                            if docs_temp.is_cumprimento_autonomo:
                                yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'  {processo_atual} é CUMPRIMENTO AUTÔNOMO'})}\n\n"

                                # Busca próximo processo na cadeia
                                proximo = docs_temp.numero_processo_origem
                                if proximo and proximo not in processos_visitados:
                                    yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'  Seguindo para origem: {proximo}'})}\n\n"
                                    processo_atual = proximo
                                    continue
                                else:
                                    yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'  Sem mais processos na cadeia'})}\n\n"
                                    break
                            else:
                                # ENCONTROU processo de CONHECIMENTO!
                                yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'  {processo_atual} é PROCESSO DE CONHECIMENTO (origem real)'})}\n\n"
                                encontrou_conhecimento = True

                                # Usa os documentos e dados deste processo
                                docs_origem_para_baixar = docs_temp
                                movimentos_origem = movimentos_temp
                                dados_basicos_origem = dados_basicos_temp

                                # Atualiza o número da origem para o processo de conhecimento
                                docs.numero_processo_origem = processo_atual

                                # Log da data de ajuizamento do processo de origem
                                if dados_basicos_origem.data_ajuizamento:
                                    data_aj = dados_basicos_origem.data_ajuizamento.strftime("%d/%m/%Y")
                                    yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'  • Data de ajuizamento (origem): {data_aj}'})}\n\n"

                                # Log dos documentos encontrados
                                if docs_origem_para_baixar.sentencas:
                                    ids_sent = str(docs_origem_para_baixar.sentencas)
                                    yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'  • {len(docs_origem_para_baixar.sentencas)} sentença(s)'})}\n\n"
                                    yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'    IDs: {ids_sent}'})}\n\n"

                                if docs_origem_para_baixar.acordaos:
                                    ids_acord = str(docs_origem_para_baixar.acordaos)
                                    yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'  • {len(docs_origem_para_baixar.acordaos)} acórdão(s)'})}\n\n"
                                    yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'    IDs: {ids_acord}'})}\n\n"

                                # Certidão de citação
                                cert_citacao_origem = next((c for c in docs_origem_para_baixar.certidoes_citacao_intimacao if c.tipo.value == "citacao"), None)
                                if cert_citacao_origem:
                                    data_cit = cert_citacao_origem.data_recebimento.strftime("%d/%m/%Y") if cert_citacao_origem.data_recebimento else "N/A"
                                    yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'  • Citação: {data_cit}'})}\n\n"

                                # Trânsito em julgado
                                if movimentos_origem and movimentos_origem.transito_julgado:
                                    data_transito = movimentos_origem.transito_julgado.strftime("%d/%m/%Y")
                                    yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'  • Trânsito em julgado: {data_transito}'})}\n\n"

                                break

                        except Exception as e:
                            import traceback
                            print(f"[ERRO] {traceback.format_exc()}")
                            yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': f'Erro ao consultar {processo_atual}: {str(e)}'})}\n\n"
                            break

                    if not encontrou_conhecimento:
                        yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': 'Não foi possível encontrar o processo de conhecimento original'})}\n\n"
                        docs_origem_para_baixar = None
                else:
                    yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': 'Processo de origem não identificado - continuando apenas com documentos do cumprimento'})}\n\n"

            # ============================================================
            # ETAPA 2: DOWNLOAD E EXTRAÇÃO DE TEXTO DOS DOCUMENTOS
            # ============================================================
            yield f"data: {json.dumps({'tipo': 'agente', 'agente': 2, 'status': 'ativo', 'mensagem': f'Iniciando download de documento(s) do TJ-MS...'})}\n\n"

            textos = {}

            # 2.1: Baixa documentos do CUMPRIMENTO (certidão intimação, pedido cumprimento)
            if qtd_certidoes > 0 or qtd_cumprimento > 0:
                yield f"data: {json.dumps({'tipo': 'info', 'mensagem': 'Baixando documentos do processo de cumprimento...'})}\n\n"

                try:
                    textos_cumprimento, erro = await service.baixar_documentos(
                        agente1_result.dados_basicos.numero_processo,
                        agente1_result.documentos_para_download
                    )

                    if erro:
                        if '502' in str(erro) or 'Proxy' in str(erro):
                            yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': 'Erro de conexão com o TJ-MS (502). Tente novamente em alguns minutos.'})}\n\n"
                            return
                        yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': f'Erro no download (cumprimento): {erro}'})}\n\n"
                    else:
                        textos.update(textos_cumprimento)
                        yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'  • {len(textos_cumprimento)} documento(s) do cumprimento'})}\n\n"
                except Exception as e_dl:
                    erro_str = str(e_dl)
                    if '502' in erro_str or 'Proxy' in erro_str:
                        yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': 'Erro de conexão com o TJ-MS (502). O servidor pode estar temporariamente indisponível. Tente novamente em alguns minutos.'})}\n\n"
                    else:
                        yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': f'Erro ao baixar documentos do cumprimento: {erro_str}'})}\n\n"
                    return

            # 2.2: Baixa documentos do PROCESSO DE ORIGEM (sentenças, acórdãos, citação)
            # IMPORTANTE: NÃO baixar pedido_cumprimento da origem (tem planilha antiga!)
            if docs_origem_para_baixar and docs.numero_processo_origem:
                yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'Baixando documentos do processo de origem ({docs.numero_processo_origem})...'})}\n\n"

                # Debug detalhado: mostra EXATAMENTE o que será baixado da origem
                qtd_sent_origem = len(docs_origem_para_baixar.sentencas)
                ids_sent_origem = str(docs_origem_para_baixar.sentencas)
                qtd_acord_origem = len(docs_origem_para_baixar.acordaos)
                ids_acord_origem = str(docs_origem_para_baixar.acordaos)

                yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'  [DEBUG] Sentenças da origem: {qtd_sent_origem} - IDs: {ids_sent_origem}'})}\n\n"
                yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'  [DEBUG] Acórdãos da origem: {qtd_acord_origem} - IDs: {ids_acord_origem}'})}\n\n"

                # Limpa pedido_cumprimento da origem para não baixar planilha antiga
                docs_origem_para_baixar.pedido_cumprimento = None

                # Filtra certidões: apenas CITAÇÃO da origem, não intimação para cumprimento
                # (intimação para cumprimento da origem é do cumprimento antigo, não queremos)
                docs_origem_para_baixar.certidoes_citacao_intimacao = [
                    c for c in docs_origem_para_baixar.certidoes_citacao_intimacao
                    if c.tipo.value == "citacao"
                ]

                qtd_cert_origem = len(docs_origem_para_baixar.certidoes_citacao_intimacao)
                yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'  [DEBUG] Certidões citação origem: {qtd_cert_origem}'})}\n\n"

                # Download usando o número do processo de ORIGEM (não do cumprimento!)
                yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'  [DEBUG] Chamando baixar_documentos com processo: {docs.numero_processo_origem}'})}\n\n"

                try:
                    textos_origem, erro = await service.baixar_documentos(
                        docs.numero_processo_origem,
                        docs_origem_para_baixar
                    )

                    if erro:
                        if '502' in str(erro) or 'Proxy' in str(erro):
                            yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': 'Erro de conexão com o TJ-MS (502). Tente novamente em alguns minutos.'})}\n\n"
                            return
                        yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': f'Erro no download (origem): {erro}'})}\n\n"
                except Exception as e_origem:
                    erro_str = str(e_origem)
                    if '502' in erro_str or 'Proxy' in erro_str:
                        yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': 'Erro de conexão com o TJ-MS (502). O servidor pode estar temporariamente indisponível. Tente novamente em alguns minutos.'})}\n\n"
                    else:
                        yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': f'Erro ao baixar documentos da origem: {erro_str}'})}\n\n"
                    return

                if not erro:
                    # Debug: mostra o que foi baixado
                    chaves_origem = list(textos_origem.keys())
                    yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'  [DEBUG] Documentos baixados da origem: {chaves_origem}'})}\n\n"

                    textos.update(textos_origem)
                    yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'  • {len(textos_origem)} documento(s) do processo de origem baixado(s)'})}\n\n"

                    # Adiciona informações da origem aos dados do agente1 para uso posterior
                    # Isso permite que o Agente 2 e 3 tenham acesso às datas corretas
                    # IMPORTANTE: Em cumprimentos autônomos, as datas processuais são do processo de ORIGEM
                    if movimentos_origem:
                        if movimentos_origem.transito_julgado:
                            agente1_result.movimentos_relevantes.transito_julgado = movimentos_origem.transito_julgado
                        if movimentos_origem.citacao_expedida:
                            agente1_result.movimentos_relevantes.citacao_expedida = movimentos_origem.citacao_expedida

                    # Atualiza data de ajuizamento do processo de ORIGEM
                    if dados_basicos_origem and dados_basicos_origem.data_ajuizamento:
                        agente1_result.dados_basicos.data_ajuizamento = dados_basicos_origem.data_ajuizamento
                        data_aj_str = dados_basicos_origem.data_ajuizamento.strftime("%d/%m/%Y")
                        yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'  Data de ajuizamento atualizada para: {data_aj_str}'})}\n\n"

                    # Guarda referência aos dados do processo de origem
                    agente1_result.dados_processo_origem = {
                        "numero_processo": docs.numero_processo_origem,
                        "data_ajuizamento": dados_basicos_origem.data_ajuizamento.strftime("%d/%m/%Y") if dados_basicos_origem and dados_basicos_origem.data_ajuizamento else None,
                        "data_transito_julgado": movimentos_origem.transito_julgado.strftime("%d/%m/%Y") if movimentos_origem and movimentos_origem.transito_julgado else None,
                    }

                    # Adiciona certidão de citação da origem para extração de data
                    cert_citacao_origem = next((c for c in docs_origem_para_baixar.certidoes_citacao_intimacao if c.tipo.value == "citacao"), None)
                    if cert_citacao_origem:
                        agente1_result.documentos_para_download.certidoes_citacao_intimacao.append(cert_citacao_origem)

            if not textos:
                yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': 'Nenhum documento foi baixado com sucesso'})}\n\n"
                return

            # Estatísticas de extração
            total_chars = sum(len(t) for t in textos.values())
            yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'Texto extraído: {total_chars:,} caracteres de {len(textos)} documento(s)'})}\n\n"

            for tipo_doc, texto in textos.items():
                nome_doc = tipo_doc.replace("_", " ").title()
                yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'  • {nome_doc}: {len(texto):,} caracteres'})}\n\n"

            yield f"data: {json.dumps({'tipo': 'agente', 'agente': 2, 'status': 'concluido', 'mensagem': f'Download concluído - {len(textos)} documento(s) processado(s)'})}\n\n"

            # ============================================================
            # ETAPA 2.5: ANÁLISE DE CERTIDÕES COM IA (SEMPRE)
            # ============================================================
            # A IA SEMPRE analisa as certidões para extrair a data real de intimação
            # lendo o conteúdo do documento (não apenas metadados do XML)
            if docs.certidoes_candidatas:
                qtd_candidatas = len(docs.certidoes_candidatas)
                yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'Analisando {qtd_candidatas} certidão(ões) com IA para extrair data de intimação...'})}\n\n"

                # Baixa e extrai texto das certidões candidatas
                ids_candidatas = [c.id_documento for c in docs.certidoes_candidatas]

                yield f"data: {json.dumps({'tipo': 'info', 'mensagem': 'Baixando certidões para análise...'})}\n\n"

                try:
                    async with DocumentDownloader() as downloader_cert:
                        textos_candidatas = await downloader_cert.baixar_e_extrair_textos(
                            agente1_result.dados_basicos.numero_processo,
                            ids_candidatas
                        )
                except Exception as e_cert:
                    erro_str = str(e_cert)
                    if '502' in erro_str or 'Proxy' in erro_str:
                        yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': 'Erro de conexão com o TJ-MS (502). O servidor pode estar temporariamente indisponível. Tente novamente em alguns minutos.'})}\n\n"
                    else:
                        yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': f'Erro ao baixar certidões: {erro_str}'})}\n\n"
                    return

                if textos_candidatas:
                    yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'Texto extraído de {len(textos_candidatas)} certidão(ões), analisando com IA...'})}\n\n"

                    # Prepara dict para análise: id -> (texto, tipo_documento)
                    certidoes_para_analise = {}
                    for cert in docs.certidoes_candidatas:
                        if cert.id_documento in textos_candidatas:
                            certidoes_para_analise[cert.id_documento] = (
                                textos_candidatas[cert.id_documento],
                                cert.tipo_documento
                            )

                    # Análise paralela com IA (passa o logger para debug)
                    from .agentes import AnalisadorCertidoesCumprimento
                    analisador = AnalisadorCertidoesCumprimento(logger=ia_logger)
                    resultados_analise = await analisador.analisar_certidoes_paralelo(certidoes_para_analise)

                    # Identifica a certidão correta
                    certidao_encontrada = analisador.identificar_certidao_cumprimento(resultados_analise)

                    if certidao_encontrada:
                        # Busca data do documento da certidão candidata
                        data_doc = None
                        for cert in docs.certidoes_candidatas:
                            if cert.id_documento == certidao_encontrada.get("id_certidao"):
                                data_doc = cert.data_documento
                                break

                        # Cria objeto CertidaoCitacaoIntimacao com dados da IA
                        cert_cumprimento = analisador.criar_certidao_intimacao(certidao_encontrada, data_doc)

                        # Adiciona à lista de certidões (substitui qualquer sugestão da heurística)
                        # Remove certidões de intimação_impugnacao anteriores (da heurística)
                        docs.certidoes_citacao_intimacao = [
                            c for c in docs.certidoes_citacao_intimacao
                            if c.tipo.value != "intimacao_impugnacao"
                        ]
                        docs.certidoes_citacao_intimacao.append(cert_cumprimento)

                        # Log detalhado
                        data_receb = cert_cumprimento.data_recebimento.strftime("%d/%m/%Y") if cert_cumprimento.data_recebimento else "N/A"
                        termo_ini = cert_cumprimento.termo_inicial_prazo.strftime("%d/%m/%Y") if cert_cumprimento.termo_inicial_prazo else "N/A"
                        tipo_cert = "Sistema" if cert_cumprimento.tipo_certidao == "sistema" else "Cartório (decurso)"
                        confianca = certidao_encontrada.get("confianca", "N/A")

                        yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'Certidão de INTIMAÇÃO P/ CUMPRIMENTO identificada pela IA (confiança: {confianca})'})}\n\n"
                        yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'  - Tipo: Cert. {tipo_cert}'})}\n\n"
                        yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'  - Data intimação (lida do documento): {data_receb}'})}\n\n"
                        yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'  - TERMO INICIAL (art. 224 CPC): {termo_ini}'})}\n\n"
                    else:
                        # IA não encontrou - usa fallback da heurística se disponível
                        if docs.certidao_heuristica:
                            docs.certidoes_citacao_intimacao.append(docs.certidao_heuristica)
                            data_receb = docs.certidao_heuristica.data_recebimento.strftime("%d/%m/%Y") if docs.certidao_heuristica.data_recebimento else "N/A"
                            termo_ini = docs.certidao_heuristica.termo_inicial_prazo.strftime("%d/%m/%Y") if docs.certidao_heuristica.termo_inicial_prazo else "N/A"
                            yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'IA não identificou certidão - usando fallback da heurística'})}\n\n"
                            yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'  - TERMO INICIAL (heurística): {termo_ini}'})}\n\n"
                        else:
                            yield f"data: {json.dumps({'tipo': 'info', 'mensagem': 'IA não conseguiu identificar certidão de intimação p/ cumprimento'})}\n\n"
                else:
                    # Não conseguiu baixar - usa heurística como fallback
                    yield f"data: {json.dumps({'tipo': 'info', 'mensagem': 'Não foi possível extrair texto das certidões'})}\n\n"
                    if docs.certidao_heuristica:
                        docs.certidoes_citacao_intimacao.append(docs.certidao_heuristica)
                        yield f"data: {json.dumps({'tipo': 'info', 'mensagem': 'Usando dados da heurística como fallback'})}\n\n"
            else:
                # Sem candidatas - usa heurística se disponível
                if docs.certidao_heuristica:
                    docs.certidoes_citacao_intimacao.append(docs.certidao_heuristica)
                    data_receb = docs.certidao_heuristica.data_recebimento.strftime("%d/%m/%Y") if docs.certidao_heuristica.data_recebimento else "N/A"
                    termo_ini = docs.certidao_heuristica.termo_inicial_prazo.strftime("%d/%m/%Y") if docs.certidao_heuristica.termo_inicial_prazo else "N/A"
                    yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'Nenhuma certidão candidata para IA - usando heurística'})}\n\n"
                    yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'  - TERMO INICIAL (heurística): {termo_ini}'})}\n\n"
                else:
                    yield f"data: {json.dumps({'tipo': 'info', 'mensagem': 'Certidão de intimação p/ cumprimento não identificada'})}\n\n"

            # ============================================================
            # ETAPA 3: EXTRAÇÃO INTELIGENTE COM IA (AGENTE 2)
            # ============================================================
            yield f"data: {json.dumps({'tipo': 'agente', 'agente': 3, 'status': 'ativo', 'mensagem': 'Iniciando análise inteligente dos documentos com IA...'})}\n\n"

            yield f"data: {json.dumps({'tipo': 'info', 'mensagem': 'Analisando sentença/acórdão para identificar objeto da condenação...'})}\n\n"
            yield f"data: {json.dumps({'tipo': 'info', 'mensagem': 'Extraindo critérios de correção monetária e juros moratórios...'})}\n\n"
            yield f"data: {json.dumps({'tipo': 'info', 'mensagem': 'Identificando período da condenação e datas processuais...'})}\n\n"
            yield f"data: {json.dumps({'tipo': 'info', 'mensagem': 'Verificando certidões para datas de citação e intimação...'})}\n\n"

            agente2_result, erro = await service.extrair_informacoes(textos)

            if erro:
                yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': f'Erro na extração de informações: {erro}'})}\n\n"
                return

            # Resumo das informações extraídas
            ext = agente2_result
            if ext.objeto_condenacao:
                obj_resumo = ext.objeto_condenacao[:100] + "..." if len(ext.objeto_condenacao) > 100 else ext.objeto_condenacao
                yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'Objeto identificado: {obj_resumo}'})}\n\n"

            if ext.correcao_monetaria and ext.correcao_monetaria.indice:
                yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'Correção monetária: {ext.correcao_monetaria.indice}'})}\n\n"

            if ext.juros_moratorios and ext.juros_moratorios.taxa:
                yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'Juros moratórios: {ext.juros_moratorios.taxa}'})}\n\n"

            if ext.datas:
                if ext.datas.citacao_recebimento:
                    data_citacao = ext.datas.citacao_recebimento.strftime("%d/%m/%Y")
                    yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'Data de citacao (recebimento): {data_citacao}'})}\n\n"
                if ext.datas.transito_julgado:
                    data_transito = ext.datas.transito_julgado.strftime("%d/%m/%Y")
                    yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'Transito em julgado: {data_transito}'})}\n\n"
                # DESTAQUE: Data de intimação para cumprimento/impugnação (TERMO INICIAL)
                if ext.datas.intimacao_impugnacao_recebimento:
                    data_intim = ext.datas.intimacao_impugnacao_recebimento.strftime("%d/%m/%Y")
                    yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'TERMO INICIAL DO PRAZO: {data_intim} (intimacao p/ cumprimento)'})}\n\n"
                else:
                    yield f"data: {json.dumps({'tipo': 'info', 'mensagem': 'Data de intimacao p/ cumprimento NAO encontrada nos documentos'})}\n\n"

            yield f"data: {json.dumps({'tipo': 'agente', 'agente': 3, 'status': 'concluido', 'mensagem': 'Extração inteligente concluída com sucesso'})}\n\n"

            # ============================================================
            # ETAPA 4: GERAÇÃO DO PEDIDO DE CÁLCULO (AGENTE 3)
            # ============================================================
            yield f"data: {json.dumps({'tipo': 'agente', 'agente': 4, 'status': 'ativo', 'mensagem': 'Iniciando geração do pedido de cálculo...'})}\n\n"

            yield f"data: {json.dumps({'tipo': 'info', 'mensagem': 'Consolidando dados dos agentes anteriores...'})}\n\n"
            yield f"data: {json.dumps({'tipo': 'info', 'mensagem': 'Aplicando formato padrão PGE-MS para pedido de cálculo...'})}\n\n"
            yield f"data: {json.dumps({'tipo': 'info', 'mensagem': 'Gerando documento com IA...'})}\n\n"

            markdown, erro = await service.gerar_pedido(agente1_result, agente2_result)

            if erro:
                yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': f'Erro na geração do pedido: {erro}'})}\n\n"
                return

            tempo_processamento = int((datetime.now() - tempo_inicio).total_seconds())
            yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'Pedido de cálculo gerado em {tempo_processamento} segundos'})}\n\n"

            yield f"data: {json.dumps({'tipo': 'agente', 'agente': 4, 'status': 'concluido', 'mensagem': 'Pedido de cálculo gerado com sucesso!'})}\n\n"

            # ============================================================
            # FINALIZAÇÃO: SALVAR NO HISTÓRICO
            # ============================================================
            # Coleta todos os IDs de documentos baixados

            # Número do processo principal (cumprimento)
            numero_cumprimento = agente1_result.dados_basicos.numero_processo
            # Número do processo de origem (se cumprimento autônomo)
            numero_origem = docs.numero_processo_origem

            # 1. Documentos do PROCESSO PRINCIPAL
            # Sentenças
            for id_doc in docs.sentencas:
                documentos_baixados.append({
                    "id": id_doc,
                    "tipo": "Sentença",
                    "processo": "principal",
                    "numero_processo": numero_cumprimento
                })

            # Acórdãos
            for id_doc in docs.acordaos:
                documentos_baixados.append({
                    "id": id_doc,
                    "tipo": "Acórdão",
                    "processo": "principal",
                    "numero_processo": numero_cumprimento
                })

            # Certidões (citação e intimação)
            for cert in docs.certidoes_citacao_intimacao:
                if cert.id_certidao_9508:
                    documentos_baixados.append({
                        "id": cert.id_certidao_9508,
                        "tipo": f"Certidão ({cert.tipo.value})",
                        "processo": "principal",
                        "numero_processo": numero_cumprimento
                    })

            # Pedido de cumprimento e planilha de cálculo
            # IMPORTANTE: Usa metadados da IA para classificar corretamente os documentos
            # Só mostra os documentos que foram efetivamente selecionados pela IA
            if docs.pedido_cumprimento and "documentos" in docs.pedido_cumprimento:
                # Obtém IDs dos documentos selecionados pela IA
                planilha_id = textos.get("_planilha_id")
                peticao_id = textos.get("_peticao_id")
                planilha_info = textos.get("_planilha_info", {})

                # Log para debug
                print(f"[DOCUMENTOS] Planilha ID selecionada: {planilha_id}")
                print(f"[DOCUMENTOS] Petição ID selecionada: {peticao_id}")

                for doc in docs.pedido_cumprimento["documentos"]:
                    doc_id = doc.get("id", "")
                    descricao = doc.get("descricao", "Documento")

                    # Só inclui documentos que foram selecionados pela IA
                    if doc_id == planilha_id:
                        # Este é o documento identificado como planilha de cálculo
                        tipo_display = "Planilha de Cálculo"
                        if planilha_info.get("valor_total"):
                            tipo_display += f" ({planilha_info['valor_total']})"

                        documentos_baixados.append({
                            "id": doc_id,
                            "tipo": tipo_display,
                            "descricao": descricao,
                            "processo": "principal",
                            "numero_processo": numero_cumprimento,
                            "classificacao_ia": "planilha_calculo",
                            "confianca_ia": planilha_info.get("confianca")
                        })

                    elif doc_id == peticao_id:
                        # Este é o documento identificado como petição de cumprimento
                        documentos_baixados.append({
                            "id": doc_id,
                            "tipo": "Petição de Cumprimento",
                            "descricao": descricao,
                            "processo": "principal",
                            "numero_processo": numero_cumprimento,
                            "classificacao_ia": "peticao"
                        })

                    elif not planilha_id and not peticao_id:
                        # Fallback: se IA não classificou nada, usa lógica antiga
                        tipo_doc = doc.get("tipo", "")
                        descr_lower = descricao.lower() if descricao else ""

                        if tipo_doc in ["9500", "9501"]:
                            tipo_display = "Petição de Cumprimento"
                        elif tipo_doc in ["9553", "61", "9535"] or any(t in descr_lower for t in ['planilha', 'cálculo', 'calculo']):
                            tipo_display = "Planilha de Cálculo"
                        else:
                            tipo_display = descricao

                        documentos_baixados.append({
                            "id": doc_id,
                            "tipo": tipo_display,
                            "descricao": descricao,
                            "processo": "principal",
                            "numero_processo": numero_cumprimento
                        })

            # 2. Documentos do PROCESSO DE ORIGEM (se cumprimento autônomo)
            if docs_origem_para_baixar and numero_origem:
                # Sentenças da origem
                for id_doc in docs_origem_para_baixar.sentencas:
                    documentos_baixados.append({
                        "id": id_doc,
                        "tipo": "Sentença",
                        "processo": "origem",
                        "numero_processo": numero_origem
                    })

                # Acórdãos da origem
                for id_doc in docs_origem_para_baixar.acordaos:
                    documentos_baixados.append({
                        "id": id_doc,
                        "tipo": "Acórdão",
                        "processo": "origem",
                        "numero_processo": numero_origem
                    })

                # Certidão de citação da origem
                for cert in docs_origem_para_baixar.certidoes_citacao_intimacao:
                    if cert.id_certidao_9508 and cert.tipo.value == "citacao":
                        documentos_baixados.append({
                            "id": cert.id_certidao_9508,
                            "tipo": "Certidão (citação)",
                            "processo": "origem",
                            "numero_processo": numero_origem
                        })

            # Salva no histórico do banco de dados
            from .models import GeracaoPedidoCalculo, LogChamadaIA, FeedbackPedidoCalculo
            from database.connection import SessionLocal

            db_session = SessionLocal()
            try:
                numero_cnj_limpo = numero_cnj.replace(".", "").replace("-", "").replace("/", "")

                # Verifica se deve sobrescrever registro existente
                geracao_existente = None
                if sobrescrever_existente:
                    geracao_existente = db_session.query(GeracaoPedidoCalculo).filter(
                        GeracaoPedidoCalculo.numero_cnj == numero_cnj_limpo,
                        GeracaoPedidoCalculo.usuario_id == user_id
                    ).first()

                if geracao_existente:
                    # ATUALIZA registro existente
                    # Primeiro, deleta logs antigos
                    db_session.query(LogChamadaIA).filter(
                        LogChamadaIA.geracao_id == geracao_existente.id
                    ).delete()

                    # Atualiza os dados
                    geracao_existente.numero_cnj_formatado = agente1_result.dados_basicos.numero_processo
                    geracao_existente.dados_processo = agente1_result.dados_basicos.to_dict()
                    geracao_existente.dados_agente1 = agente1_result.to_dict()
                    geracao_existente.dados_agente2 = agente2_result.to_dict()
                    geracao_existente.documentos_baixados = documentos_baixados
                    geracao_existente.conteudo_gerado = markdown
                    geracao_existente.modelo_usado = "gemini-2.0-flash"
                    geracao_existente.tempo_processamento = tempo_processamento
                    geracao_existente.criado_em = datetime.utcnow()  # Atualiza timestamp

                    db_session.commit()
                    geracao_id = geracao_existente.id

                    yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'Pedido atualizado no histórico (ID: {geracao_id})'})}\n\n"
                else:
                    # CRIA novo registro
                    geracao = GeracaoPedidoCalculo(
                        numero_cnj=numero_cnj_limpo,
                        numero_cnj_formatado=agente1_result.dados_basicos.numero_processo,
                        dados_processo=agente1_result.dados_basicos.to_dict(),
                        dados_agente1=agente1_result.to_dict(),
                        dados_agente2=agente2_result.to_dict(),
                        documentos_baixados=documentos_baixados,
                        conteudo_gerado=markdown,
                        modelo_usado="gemini-2.0-flash",
                        tempo_processamento=tempo_processamento,
                        usuario_id=user_id
                    )
                    db_session.add(geracao)
                    db_session.commit()
                    geracao_id = geracao.id

                    yield f"data: {json.dumps({'tipo': 'info', 'mensagem': f'Pedido salvo no histórico (ID: {geracao_id})'})}\n\n"

                # Salva logs de IA vinculados a esta geração
                ia_logger.set_geracao_id(geracao_id)
                ia_logger.salvar_logs(db_session)
            except Exception as e:
                db_session.rollback()
                import traceback
                traceback.print_exc()
                yield f"data: {json.dumps({'tipo': 'info', 'mensagem': 'Aviso: Não foi possível salvar no histórico'})}\n\n"
            finally:
                db_session.close()

            # Resultado final com documentos baixados e ID do histórico
            yield f"data: {json.dumps({'tipo': 'sucesso', 'geracao_id': geracao_id, 'dados_basicos': agente1_result.dados_basicos.to_dict(), 'dados_extracao': agente2_result.to_dict(), 'pedido_markdown': markdown, 'documentos_baixados': documentos_baixados})}\n\n"

        except Exception as e:
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': f'Erro inesperado no processamento: {str(e)}'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("/exportar-docx")
async def exportar_docx(
    req: ExportarDocxRequest,
    current_user: User = Depends(get_current_active_user)
):
    """
    Exporta pedido de cálculo para DOCX.
    Usa conversor específico SEM recuos.
    """
    try:
        from .docx_converter import pedido_calculo_to_docx
        
        # Gera nome do arquivo
        file_id = str(uuid.uuid4())[:8]
        if req.numero_processo:
            numero_limpo = ''.join(c for c in req.numero_processo if c.isdigit())[-8:]
            filename = f"pedido_calculo_{numero_limpo}_{file_id}.docx"
        else:
            filename = f"pedido_calculo_{file_id}.docx"
        
        filepath = os.path.join(TEMP_DIR, filename)
        
        # Converte usando o conversor específico para pedido de cálculo (sem recuos)
        success = pedido_calculo_to_docx(req.markdown, filepath)
        
        if not success:
            raise HTTPException(status_code=500, detail="Erro ao gerar DOCX")
        
        return {
            "status": "sucesso",
            "url_download": f"/pedido-calculo/api/download/{filename}",
            "filename": filename
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/download/{filename}")
async def download_documento(
    filename: str,
    token: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user_from_token_or_query)
):
    """Download do documento gerado"""
    filepath = os.path.join(TEMP_DIR, filename)
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    
    return FileResponse(
        filepath,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=filename
    )


@router.get("/documento/{numero_processo}/{id_documento}")
async def obter_documento(
    numero_processo: str,
    id_documento: str,
    token: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user_from_token_or_query)
):
    """
    Obtém um documento específico do TJ-MS.

    Retorna o PDF em base64 para visualização no frontend.
    Converte RTF para PDF se necessário.
    """
    try:
        from .document_downloader import DocumentDownloader
        import base64

        async with DocumentDownloader() as downloader:
            docs = await downloader.baixar_documentos(numero_processo, [id_documento])

        if not docs or id_documento not in docs:
            raise HTTPException(status_code=404, detail="Documento não encontrado")

        doc_bytes = docs[id_documento]

        # Verifica se é RTF e converte para PDF
        if doc_bytes.startswith(b'{\\rtf'):
            pdf_bytes = _converter_rtf_para_pdf(doc_bytes)
        else:
            pdf_bytes = doc_bytes

        # Valida PDF para evitar documentos corrompidos
        try:
            import fitz
            with fitz.open(stream=pdf_bytes, filetype="pdf") as _doc:
                pass
        except Exception:
            raise HTTPException(status_code=422, detail="Documento invalido ou corrompido")

        pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')

        return {
            "id": id_documento,
            "conteudo_base64": pdf_base64,
            "tipo": "application/pdf"
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/verificar-existente")
async def verificar_processo_existente(
    numero_cnj: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Verifica se um processo já existe no histórico do usuário.
    Retorna informações sobre o registro existente se encontrado.
    """
    from .models import GeracaoPedidoCalculo
    from datetime import timezone, timedelta

    # Normaliza o número CNJ (remove formatação)
    numero_cnj_limpo = numero_cnj.replace(".", "").replace("-", "").replace("/", "").strip()

    # Busca registro existente
    geracao_existente = db.query(GeracaoPedidoCalculo).filter(
        GeracaoPedidoCalculo.numero_cnj == numero_cnj_limpo,
        GeracaoPedidoCalculo.usuario_id == current_user.id
    ).order_by(GeracaoPedidoCalculo.criado_em.desc()).first()

    if not geracao_existente:
        return {"existe": False}

    # Timezone de Brasília (UTC-3)
    tz_brasilia = timezone(timedelta(hours=-3))

    def converter_para_brasilia(dt):
        if not dt:
            return None
        dt_utc = dt.replace(tzinfo=timezone.utc)
        dt_brasilia = dt_utc.astimezone(tz_brasilia)
        return dt_brasilia.strftime("%d/%m/%Y às %H:%M")

    return {
        "existe": True,
        "geracao_id": geracao_existente.id,
        "numero_cnj_formatado": geracao_existente.numero_cnj_formatado,
        "criado_em": converter_para_brasilia(geracao_existente.criado_em),
        "autor": geracao_existente.dados_processo.get("autor") if geracao_existente.dados_processo else None
    }


@router.get("/historico")
async def listar_historico(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Lista histórico de pedidos de cálculo gerados pelo usuário.
    Ordenado por data de criação (mais recentes primeiro).
    """
    from .models import GeracaoPedidoCalculo
    from datetime import timezone, timedelta

    # Timezone de Brasília (UTC-3)
    tz_brasilia = timezone(timedelta(hours=-3))

    historico = db.query(GeracaoPedidoCalculo).filter(
        GeracaoPedidoCalculo.usuario_id == current_user.id
    ).order_by(GeracaoPedidoCalculo.criado_em.desc()).limit(50).all()

    def converter_para_brasilia(dt):
        """Converte datetime UTC para horário de Brasília"""
        if not dt:
            return None
        # Assume que o datetime está em UTC (como salvo pelo banco)
        dt_utc = dt.replace(tzinfo=timezone.utc)
        dt_brasilia = dt_utc.astimezone(tz_brasilia)
        return dt_brasilia.isoformat()

    return [
        {
            "id": h.id,
            "numero_cnj": h.numero_cnj,
            "numero_cnj_formatado": h.numero_cnj_formatado,
            "dados_processo": h.dados_processo,
            "conteudo_gerado": h.conteudo_gerado,
            "documentos_baixados": h.documentos_baixados,
            "criado_em": converter_para_brasilia(h.criado_em),
            "tempo_processamento": h.tempo_processamento
        }
        for h in historico
    ]


@router.get("/historico/{id}")
async def obter_historico(
    id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Obtém um pedido específico do histórico.
    """
    from .models import GeracaoPedidoCalculo
    from datetime import timezone, timedelta

    # Timezone de Brasília (UTC-3)
    tz_brasilia = timezone(timedelta(hours=-3))

    def converter_para_brasilia(dt):
        if not dt:
            return None
        dt_utc = dt.replace(tzinfo=timezone.utc)
        return dt_utc.astimezone(tz_brasilia).isoformat()

    geracao = db.query(GeracaoPedidoCalculo).filter(
        GeracaoPedidoCalculo.id == id,
        GeracaoPedidoCalculo.usuario_id == current_user.id
    ).first()

    if not geracao:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")

    return {
        "id": geracao.id,
        "numero_cnj": geracao.numero_cnj,
        "numero_cnj_formatado": geracao.numero_cnj_formatado,
        "dados_processo": geracao.dados_processo,
        "dados_agente1": geracao.dados_agente1,
        "dados_agente2": geracao.dados_agente2,
        "documentos_baixados": geracao.documentos_baixados,
        "conteudo_gerado": geracao.conteudo_gerado,
        "historico_chat": geracao.historico_chat,
        "criado_em": converter_para_brasilia(geracao.criado_em),
        "tempo_processamento": geracao.tempo_processamento
    }


class EditarPedidoRequest(BaseModel):
    """Request para editar pedido via chat"""
    pedido_markdown: str
    mensagem_usuario: str
    historico_chat: List[Dict] = []
    dados_basicos: Dict = {}
    dados_extracao: Dict = {}


@router.post("/editar-pedido")
async def editar_pedido(
    req: EditarPedidoRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Edita pedido de cálculo via chat com IA.
    """
    try:
        # Busca prompt do banco de dados
        prompt_db = db.query(PromptConfig).filter(
            PromptConfig.sistema == SISTEMA,
            PromptConfig.tipo == "edicao_pedido",
            PromptConfig.is_active == True
        ).first()
        
        # Busca modelo do banco
        modelo_config = db.query(ConfiguracaoIA).filter(
            ConfiguracaoIA.sistema == SISTEMA,
            ConfiguracaoIA.chave == "modelo_edicao"
        ).first()
        modelo = modelo_config.valor if modelo_config else "gemini-3-flash-preview"
        
        # Monta prompt de edição
        if prompt_db:
            prompt_edicao = prompt_db.conteudo.format(
                mensagem_usuario=req.mensagem_usuario,
                pedido_markdown=req.pedido_markdown,
                autor=req.dados_basicos.get('autor', 'N/A'),
                numero_processo=req.dados_basicos.get('numero_processo', 'N/A'),
                objeto_condenacao=req.dados_extracao.get('objeto_condenacao', 'N/A')
            )
        else:
            # Fallback para prompt padrão
            prompt_edicao = f"""Você é um assistente especializado em editar pedidos de cálculo judicial.

O usuário solicitou a seguinte alteração no pedido de cálculo:

"{req.mensagem_usuario}"

## Pedido Atual (Markdown):
{req.pedido_markdown}

## Dados do Processo:
- Autor: {req.dados_basicos.get('autor', 'N/A')}
- Processo: {req.dados_basicos.get('numero_processo', 'N/A')}
- Objeto: {req.dados_extracao.get('objeto_condenacao', 'N/A')}

## Instruções:
1. Aplique APENAS a alteração solicitada pelo usuário
2. Mantenha toda a estrutura e formatação do pedido
3. Retorne o pedido completo atualizado em Markdown
4. NÃO adicione comentários ou explicações, apenas o pedido atualizado

Pedido atualizado:"""

        # Chama a IA via Gemini Service
        from services.gemini_service import gemini_service
        
        response = await gemini_service.generate(
            prompt=prompt_edicao,
            model=modelo,
            temperature=0.3
        )
        
        if not response.success or not response.content:
            return {
                "status": "erro",
                "mensagem": response.error or "Não foi possível processar a edição"
            }
        
        return {
            "status": "sucesso",
            "pedido_markdown": response.content.strip()
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "status": "erro",
            "mensagem": str(e)
        }


# ============================================
# Endpoints de Configuração (Admin)
# ============================================

class PromptConfigRequest(BaseModel):
    """Request para atualizar prompt"""
    conteudo: str
    descricao: Optional[str] = None


class ConfiguracaoRequest(BaseModel):
    """Request para atualizar configuração"""
    valor: str
    descricao: Optional[str] = None


@router.get("/config/prompts")
async def listar_prompts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Lista todos os prompts configurados para o sistema pedido_calculo"""
    prompts = db.query(PromptConfig).filter(
        PromptConfig.sistema == SISTEMA,
        PromptConfig.is_active == True
    ).all()
    
    return [
        {
            "id": p.id,
            "tipo": p.tipo,
            "nome": p.nome,
            "descricao": p.descricao,
            "conteudo": p.conteudo,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
            "updated_by": p.updated_by
        }
        for p in prompts
    ]


@router.get("/config/prompts/{tipo}")
async def obter_prompt(
    tipo: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Obtém um prompt específico pelo tipo"""
    prompt = db.query(PromptConfig).filter(
        PromptConfig.sistema == SISTEMA,
        PromptConfig.tipo == tipo,
        PromptConfig.is_active == True
    ).first()
    
    if not prompt:
        raise HTTPException(status_code=404, detail=f"Prompt '{tipo}' não encontrado")
    
    return {
        "id": prompt.id,
        "tipo": prompt.tipo,
        "nome": prompt.nome,
        "descricao": prompt.descricao,
        "conteudo": prompt.conteudo,
        "updated_at": prompt.updated_at.isoformat() if prompt.updated_at else None,
        "updated_by": prompt.updated_by
    }


@router.put("/config/prompts/{tipo}")
async def atualizar_prompt(
    tipo: str,
    req: PromptConfigRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Atualiza um prompt existente"""
    prompt = db.query(PromptConfig).filter(
        PromptConfig.sistema == SISTEMA,
        PromptConfig.tipo == tipo,
        PromptConfig.is_active == True
    ).first()
    
    if not prompt:
        raise HTTPException(status_code=404, detail=f"Prompt '{tipo}' não encontrado")
    
    prompt.conteudo = req.conteudo
    if req.descricao:
        prompt.descricao = req.descricao
    prompt.updated_by = current_user.username
    
    db.commit()
    
    return {"status": "sucesso", "mensagem": f"Prompt '{tipo}' atualizado com sucesso"}


@router.get("/config/modelos")
async def listar_modelos(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Lista configurações de modelos de IA"""
    configs = db.query(ConfiguracaoIA).filter(
        ConfiguracaoIA.sistema == SISTEMA
    ).all()
    
    return [
        {
            "id": c.id,
            "chave": c.chave,
            "valor": c.valor,
            "tipo_valor": c.tipo_valor,
            "descricao": c.descricao
        }
        for c in configs
    ]


@router.get("/config/modelos/{chave}")
async def obter_modelo(
    chave: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Obtém uma configuração de modelo específica"""
    config = db.query(ConfiguracaoIA).filter(
        ConfiguracaoIA.sistema == SISTEMA,
        ConfiguracaoIA.chave == chave
    ).first()
    
    if not config:
        raise HTTPException(status_code=404, detail=f"Configuração '{chave}' não encontrada")
    
    return {
        "id": config.id,
        "chave": config.chave,
        "valor": config.valor,
        "tipo_valor": config.tipo_valor,
        "descricao": config.descricao
    }


@router.put("/config/modelos/{chave}")
async def atualizar_modelo(
    chave: str,
    req: ConfiguracaoRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Atualiza uma configuração de modelo"""
    config = db.query(ConfiguracaoIA).filter(
        ConfiguracaoIA.sistema == SISTEMA,
        ConfiguracaoIA.chave == chave
    ).first()
    
    if not config:
        # Cria nova configuração
        config = ConfiguracaoIA(
            sistema=SISTEMA,
            chave=chave,
            valor=req.valor,
            descricao=req.descricao
        )
        db.add(config)
    else:
        config.valor = req.valor
        if req.descricao:
            config.descricao = req.descricao
    
    db.commit()

    return {"status": "sucesso", "mensagem": f"Configuração '{chave}' atualizada com sucesso"}


# ============================================
# Endpoints de Feedback
# ============================================

@router.post("/feedback")
async def enviar_feedback(
    req: FeedbackRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Envia feedback sobre o pedido de cálculo gerado."""
    try:
        from .models import GeracaoPedidoCalculo, FeedbackPedidoCalculo

        geracao = db.query(GeracaoPedidoCalculo).filter(
            GeracaoPedidoCalculo.id == req.geracao_id
        ).first()

        if not geracao:
            raise HTTPException(status_code=404, detail="Geração não encontrada")

        feedback_existente = db.query(FeedbackPedidoCalculo).filter(
            FeedbackPedidoCalculo.geracao_id == req.geracao_id
        ).first()

        if feedback_existente:
            raise HTTPException(
                status_code=400,
                detail="Feedback já foi enviado para esta geração"
            )

        feedback = FeedbackPedidoCalculo(
            geracao_id=req.geracao_id,
            usuario_id=current_user.id,
            avaliacao=req.avaliacao,
            nota=req.nota,
            comentario=req.comentario,
            campos_incorretos=req.campos_incorretos
        )
        db.add(feedback)

        db.commit()

        return {"success": True, "message": "Feedback registrado com sucesso"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/feedback/{geracao_id}")
async def obter_feedback(
    geracao_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Obtém o feedback de uma geração específica."""
    try:
        from .models import FeedbackPedidoCalculo

        feedback = db.query(FeedbackPedidoCalculo).filter(
            FeedbackPedidoCalculo.geracao_id == geracao_id
        ).first()

        if not feedback:
            return {"has_feedback": False}

        return {
            "has_feedback": True,
            "avaliacao": feedback.avaliacao,
            "nota": feedback.nota,
            "comentario": feedback.comentario,
            "campos_incorretos": feedback.campos_incorretos,
            "criado_em": feedback.criado_em.isoformat() if feedback.criado_em else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
