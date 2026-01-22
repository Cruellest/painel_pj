# sistemas/gerador_pecas/router_teste_categorias.py
"""
Router para ambiente de testes de categorias de resumo JSON.

Este módulo implementa a interface de teste/validação dos JSONs de categorias,
permitindo testar classificação em lote e individual de documentos.
"""

import asyncio
import base64
import json
import io
import re
import logging
import uuid
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field

from fastapi import APIRouter, Depends, HTTPException, status, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from database.connection import get_db
from auth.models import User
from auth.dependencies import get_current_active_user
from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON
from sistemas.gerador_pecas.models_teste_categorias import TesteDocumento, TesteObservacao
from services.text_normalizer import text_normalizer

# PDF manipulation
try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/teste-categorias", tags=["Teste de Categorias JSON"])


# ==========================
# Cache de PDFs em memória
# ==========================
# Armazena PDFs temporariamente para servir via endpoint (evita CSP issues)
# Formato: { token: { pdf_base64, expires_at, processo } }
_pdf_cache: Dict[str, Dict[str, Any]] = {}
_PDF_CACHE_TTL_MINUTES = 30


def _limpar_cache_expirado():
    """Remove PDFs expirados do cache"""
    agora = datetime.utcnow()
    expirados = [k for k, v in _pdf_cache.items() if v['expires_at'] < agora]
    for k in expirados:
        del _pdf_cache[k]


def armazenar_pdf_cache(pdf_base64: str, processo: str) -> str:
    """Armazena PDF no cache e retorna token de acesso"""
    _limpar_cache_expirado()

    token = str(uuid.uuid4())
    _pdf_cache[token] = {
        'pdf_base64': pdf_base64,
        'processo': processo,
        'expires_at': datetime.utcnow() + timedelta(minutes=_PDF_CACHE_TTL_MINUTES)
    }
    return token


def obter_pdf_cache(token: str) -> Optional[bytes]:
    """Obtém PDF do cache pelo token"""
    _limpar_cache_expirado()

    if token not in _pdf_cache:
        return None

    entry = _pdf_cache[token]
    if entry['expires_at'] < datetime.utcnow():
        del _pdf_cache[token]
        return None

    return base64.b64decode(entry['pdf_base64'])


# ==========================
# Schemas
# ==========================

class ValidarProcessoRequest(BaseModel):
    """Valida um ou mais números de processo"""
    processos: List[str]  # Lista de números de processo (um por linha)


class ProcessoValidado(BaseModel):
    """Resultado da validação de um processo"""
    original: str
    normalizado: Optional[str] = None
    valido: bool
    erro: Optional[str] = None


class BaixarDocumentosRequest(BaseModel):
    """Request para baixar documentos de processos"""
    processos: List[str]  # Lista de números normalizados
    categoria_id: int


class DocumentoBaixado(BaseModel):
    """Informações de um documento baixado"""
    id: str
    processo: str
    tipo_documento: Optional[str] = None
    descricao: Optional[str] = None
    data_juntada: Optional[str] = None
    tamanho_bytes: int = 0
    num_paginas: int = 0


class ProcessoDocumentos(BaseModel):
    """Resultado do download de documentos de um processo"""
    processo: str
    status: str  # "ok", "erro", "sem_documentos"
    documentos: List[DocumentoBaixado] = []
    pdf_unificado_base64: Optional[str] = None  # PDF unificado em base64
    erro: Optional[str] = None


class ClassificarDocumentoRequest(BaseModel):
    """Request para classificar um documento"""
    processo: str
    categoria_id: int
    pdf_base64: str  # PDF em base64


class ClassificarLoteItem(BaseModel):
    """Item para classificação em lote"""
    processo: str
    pdf_base64: str


class ClassificarLoteRequest(BaseModel):
    """Request para classificar múltiplos documentos em paralelo"""
    categoria_id: int
    itens: List[ClassificarLoteItem]
    max_paralelo: int = 5  # Máximo de classificações simultâneas


class ClassificacaoResultado(BaseModel):
    """Resultado da classificação de um documento"""
    processo: str
    sucesso: bool
    json_extraido: Optional[Dict[str, Any]] = None
    json_raw: Optional[str] = None
    erro: Optional[str] = None
    tempo_processamento_ms: int = 0


class ObservacaoCategoria(BaseModel):
    """Observações persistentes de uma categoria"""
    categoria_id: int
    texto: str


# ==========================
# Schemas para Comparação de Modelos
# ==========================

class ClassificarComparacaoRequest(BaseModel):
    """Request para classificar com comparação de modelos"""
    processo: str
    categoria_id: int
    pdf_base64: str


class DiferencaCampoSchema(BaseModel):
    """Diferença entre valores de um campo"""
    campo: str
    tipo_campo: str
    valor_a: Any
    valor_b: Any
    comparavel: bool


class RelatorioComparacaoSchema(BaseModel):
    """Relatório de comparação entre dois JSONs"""
    total_campos: int
    campos_comparados: int
    campos_iguais: int
    campos_diferentes: int
    campos_text_ignorados: int
    porcentagem_acordo: float
    diferencas: List[DiferencaCampoSchema]
    resumo: str


class ClassificacaoComparacaoResultado(BaseModel):
    """Resultado da classificação com comparação de modelos"""
    processo: str
    sucesso: bool
    resultado_a: Optional[Dict[str, Any]] = None
    resultado_b: Optional[Dict[str, Any]] = None
    modelo_a: str
    modelo_b: str
    config_a: str  # ex: "thinking: low"
    config_b: str  # ex: "thinking: default"
    tempo_a_ms: int
    tempo_b_ms: int
    report: Optional[RelatorioComparacaoSchema] = None
    erro: Optional[str] = None


# ==========================
# Funções auxiliares
# ==========================

def verificar_permissao(user: User):
    """Verifica se usuário tem permissão para testar categorias"""
    if not user.tem_permissao("editar_prompts"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sem permissão para testar categorias de resumo JSON"
        )


def normalizar_processo(numero: str) -> tuple[bool, str, str]:
    """
    Normaliza número de processo para formato CNJ padrão.

    Usa a mesma lógica do módulo assistencia_judiciaria.

    Args:
        numero: Número do processo (com ou sem formatação)

    Returns:
        Tupla (valido, numero_normalizado, mensagem)
    """
    # Remove espaços e caracteres especiais, deixando só dígitos
    digitos = re.sub(r'\D', '', numero.strip())

    if len(digitos) != 20:
        return False, "", f"Número CNJ deve conter 20 dígitos (encontrados: {len(digitos)})"

    # Valida ano (dígitos 9-13) - deve estar entre 1900 e ano atual + 1
    ano = int(digitos[9:13])
    ano_atual = datetime.now().year
    if not (1900 <= ano <= ano_atual + 1):
        return False, "", f"Ano do processo inválido: {ano}"

    # Formata no padrão CNJ: NNNNNNN-NN.NNNN.N.NN.NNNN
    formatado = f"{digitos[0:7]}-{digitos[7:9]}.{digitos[9:13]}.{digitos[13:14]}.{digitos[14:16]}.{digitos[16:20]}"

    return True, formatado, "OK"


def unificar_pdfs(pdfs_base64: List[str]) -> Optional[str]:
    """
    Unifica múltiplos PDFs em um único arquivo.

    Args:
        pdfs_base64: Lista de PDFs em base64

    Returns:
        PDF unificado em base64, ou None se erro
    """
    if not HAS_PYMUPDF:
        logger.warning("PyMuPDF não instalado - não é possível unificar PDFs")
        return pdfs_base64[0] if pdfs_base64 else None

    if not pdfs_base64:
        return None

    if len(pdfs_base64) == 1:
        return pdfs_base64[0]

    try:
        # Cria documento de destino
        doc_final = fitz.open()

        for pdf_b64 in pdfs_base64:
            pdf_bytes = base64.b64decode(pdf_b64)
            doc_temp = fitz.open(stream=pdf_bytes, filetype="pdf")
            doc_final.insert_pdf(doc_temp)
            doc_temp.close()

        # Salva em memória
        output = io.BytesIO()
        doc_final.save(output)
        doc_final.close()

        # Retorna como base64
        output.seek(0)
        return base64.b64encode(output.read()).decode('utf-8')

    except Exception as e:
        logger.error(f"Erro ao unificar PDFs: {e}")
        return pdfs_base64[0] if pdfs_base64 else None


async def consultar_processo_tjms(numero_processo: str) -> tuple[Optional[str], Optional[str]]:
    """
    Consulta processo no TJ-MS via SOAP.

    Returns:
        Tupla (xml_resposta, erro)
    """
    from services.tjms_client import soap_consultar_processo, get_config

    try:
        config = get_config()
        xml_resposta = await soap_consultar_processo(
            numero_processo=numero_processo,
            movimentos=True,
            incluir_documentos=True,
            config=config
        )
        return xml_resposta, None
    except Exception as e:
        logger.error(f"Erro ao consultar processo {numero_processo}: {e}")
        return None, str(e)


async def baixar_documentos_tjms(
    numero_processo: str,
    ids_documentos: List[str]
) -> tuple[Optional[str], Optional[str]]:
    """
    Baixa documentos do TJ-MS via SOAP.

    Returns:
        Tupla (xml_resposta, erro)
    """
    from services.tjms_client import soap_baixar_documentos, get_config

    try:
        config = get_config()
        xml_resposta = await soap_baixar_documentos(
            numero_processo=numero_processo,
            ids_documentos=ids_documentos,
            config=config
        )
        return xml_resposta, None
    except Exception as e:
        logger.error(f"Erro ao baixar documentos do processo {numero_processo}: {e}")
        return None, str(e)


def filtrar_documentos_por_categoria(
    documentos: List[Dict[str, Any]],
    categoria: CategoriaResumoJSON,
    db: Session = None
) -> List[Dict[str, Any]]:
    """
    Filtra documentos que pertencem a uma categoria específica.

    Args:
        documentos: Lista de documentos do processo
        categoria: Categoria de resumo JSON

    Returns:
        Lista de documentos filtrados
    """
    logger.info(f"Filtrando {len(documentos)} documentos para categoria '{categoria.nome}'")
    logger.info(f"Categoria usa_fonte_especial: {categoria.usa_fonte_especial}")
    logger.info(f"Categoria codigos_documento: {categoria.codigos_documento}")

    # Log dos códigos encontrados nos documentos
    codigos_encontrados = []
    for doc in documentos:
        tipo = doc.get('tipo_documento')
        descricao = doc.get('descricao', '')
        codigos_encontrados.append(f"{tipo} ({descricao})")
    logger.info(f"Códigos nos documentos: {codigos_encontrados[:20]}")  # Limita a 20

    if categoria.usa_fonte_especial:
        # Usa resolvedor de fonte especial
        from sistemas.gerador_pecas.services_source_resolver import (
            get_source_resolver, DocumentoInfo
        )

        # Converte para formato do resolver
        docs_info = []
        for i, doc in enumerate(documentos):
            try:
                codigo = int(doc.get('tipo_documento') or 0)
            except (ValueError, TypeError):
                codigo = 0

            docs_info.append(DocumentoInfo(
                id=doc.get('id', str(i)),
                codigo=codigo,
                data=doc.get('data_juntada'),
                descricao=doc.get('descricao'),
                ordem=i
            ))

        resolver = get_source_resolver(db)
        result = resolver.resolve(categoria.source_special_type, docs_info)

        logger.info(f"Resultado resolver fonte especial '{categoria.source_special_type}': sucesso={result.sucesso}, motivo={result.motivo}")

        if result.sucesso and result.documento_id:
            # Retorna apenas o documento identificado
            doc_encontrado = [d for d in documentos if d.get('id') == result.documento_id]
            logger.info(f"Documento especial encontrado: {doc_encontrado}")
            return doc_encontrado

        logger.warning(f"Fonte especial '{categoria.source_special_type}' não encontrou documento: {result.motivo}")
        return []

    else:
        # Filtra por códigos de documento
        codigos_categoria = set(categoria.codigos_documento or [])
        logger.info(f"Códigos da categoria (set): {codigos_categoria}")

        filtrados = []
        for d in documentos:
            tipo_raw = d.get('tipo_documento')
            try:
                tipo_int = int(tipo_raw) if tipo_raw else 0
            except (ValueError, TypeError):
                tipo_int = 0

            if tipo_int in codigos_categoria:
                logger.info(f"Match! Doc {d.get('id')} tipo={tipo_int} descricao={d.get('descricao')}")
                filtrados.append(d)

        logger.info(f"Total filtrados: {len(filtrados)}")
        return filtrados


async def classificar_documento_com_ia(
    pdf_base64: str,
    categoria: CategoriaResumoJSON,
    db: Session
) -> tuple[Optional[Dict[str, Any]], Optional[str], str]:
    """
    Classifica um documento usando IA baseado na categoria.

    Args:
        pdf_base64: PDF em base64
        categoria: Categoria de resumo JSON
        db: Sessão do banco de dados

    Returns:
        Tupla (json_extraido, erro, json_raw)
    """
    from services.gemini_service import gemini_service, get_thinking_level
    from sistemas.gerador_pecas.extrator_resumo_json import (
        FormatoResumo, gerar_prompt_extracao_json,
        gerar_prompt_extracao_json_imagem, parsear_resposta_json,
        normalizar_json_com_schema
    )

    # Obtém thinking_level configurado para gerador_pecas
    thinking_level = get_thinking_level(db, "gerador_pecas")

    try:
        # Cria objeto de formato
        formato = FormatoResumo(
            categoria_id=categoria.id,
            categoria_nome=categoria.nome,
            formato_json=categoria.formato_json,
            instrucoes_extracao=categoria.instrucoes_extracao,
            is_residual=categoria.is_residual
        )

        # Decodifica PDF
        pdf_bytes = base64.b64decode(pdf_base64)

        # Extrai texto do PDF
        texto_extraido = ""
        if HAS_PYMUPDF:
            try:
                doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                for pagina in doc:
                    texto_extraido += pagina.get_text()
                doc.close()
                # Normaliza texto extraído
                if texto_extraido:
                    result = text_normalizer.normalize(texto_extraido)
                    texto_extraido = result.text
            except Exception as e:
                logger.warning(f"Erro ao extrair texto do PDF: {e}")

        # Decide se usa texto ou imagem
        if texto_extraido and len(texto_extraido.strip()) > 100:
            # Usa texto
            prompt_template = gerar_prompt_extracao_json(formato, db=db)
            prompt = prompt_template.format(texto_documento=texto_extraido[:50000])

            response = await gemini_service.generate(
                prompt=prompt,
                model="gemini-3-flash-preview",
                temperature=0.1,
                max_tokens=8000,
                thinking_level=thinking_level  # Configurável em /admin/prompts-config
            )
        else:
            # Usa imagem (PDF digitalizado)
            prompt = gerar_prompt_extracao_json_imagem(formato, db=db)

            # Converte PDF para imagens
            imagens_base64 = []
            if HAS_PYMUPDF:
                doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                for i, pagina in enumerate(doc):
                    if i >= 10:  # Limita a 10 páginas
                        break
                    pix = pagina.get_pixmap(matrix=fitz.Matrix(2, 2))
                    img_bytes = pix.tobytes("png")
                    imagens_base64.append(base64.b64encode(img_bytes).decode())
                doc.close()

            if imagens_base64:
                response = await gemini_service.generate_with_images(
                    prompt=prompt,
                    images_base64=imagens_base64,
                    model="gemini-3-flash-preview",
                    temperature=0.1,
                    max_tokens=8000,
                    thinking_level=thinking_level  # Configurável em /admin/prompts-config
                )
            else:
                return None, "Não foi possível processar o PDF", ""

        if not response.success:
            return None, response.error, ""

        # Parseia resposta JSON
        json_dict, erro_parse = parsear_resposta_json(response.content)

        if erro_parse:
            return None, erro_parse, response.content

        # Normaliza JSON garantindo que todas as chaves do schema estejam presentes
        json_normalizado = normalizar_json_com_schema(json_dict, categoria.formato_json)

        return json_normalizado, None, response.content

    except Exception as e:
        logger.error(f"Erro ao classificar documento: {e}")
        return None, str(e), ""


async def classificar_documento_com_modelo(
    pdf_base64: str,
    categoria: CategoriaResumoJSON,
    modelo: str,
    thinking_level: Optional[str],
    db: Session
) -> Tuple[Optional[Dict[str, Any]], Optional[str], int]:
    """
    Versão parametrizada de classificar_documento_com_ia.

    Permite especificar modelo e thinking_level para comparações A/B.

    Args:
        pdf_base64: PDF em base64
        categoria: Categoria de resumo JSON
        modelo: Nome do modelo (ex: "gemini-3-flash-preview", "gemini-2.5-flash-lite")
        thinking_level: Nível de thinking ("low", "medium", "high", None)
        db: Sessão do banco de dados

    Returns:
        Tupla (json_extraido, erro, tempo_ms)
    """
    import time
    from services.gemini_service import gemini_service
    from sistemas.gerador_pecas.extrator_resumo_json import (
        FormatoResumo, gerar_prompt_extracao_json,
        gerar_prompt_extracao_json_imagem, parsear_resposta_json,
        normalizar_json_com_schema
    )

    inicio = time.time()

    try:
        # Cria objeto de formato
        formato = FormatoResumo(
            categoria_id=categoria.id,
            categoria_nome=categoria.nome,
            formato_json=categoria.formato_json,
            instrucoes_extracao=categoria.instrucoes_extracao,
            is_residual=categoria.is_residual
        )

        # Decodifica PDF
        pdf_bytes = base64.b64decode(pdf_base64)

        # Extrai texto do PDF
        texto_extraido = ""
        if HAS_PYMUPDF:
            try:
                doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                for pagina in doc:
                    texto_extraido += pagina.get_text()
                doc.close()
                # Normaliza texto extraído
                if texto_extraido:
                    result = text_normalizer.normalize(texto_extraido)
                    texto_extraido = result.text
            except Exception as e:
                logger.warning(f"Erro ao extrair texto do PDF: {e}")

        # Decide se usa texto ou imagem
        if texto_extraido and len(texto_extraido.strip()) > 100:
            # Usa texto
            prompt_template = gerar_prompt_extracao_json(formato, db=db)
            prompt = prompt_template.format(texto_documento=texto_extraido[:50000])

            response = await gemini_service.generate(
                prompt=prompt,
                model=modelo,
                temperature=0.1,
                max_tokens=8000,
                thinking_level=thinking_level
            )
        else:
            # Usa imagem (PDF digitalizado)
            prompt = gerar_prompt_extracao_json_imagem(formato, db=db)

            # Converte PDF para imagens
            imagens_base64 = []
            if HAS_PYMUPDF:
                doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                for i, pagina in enumerate(doc):
                    if i >= 10:  # Limita a 10 páginas
                        break
                    pix = pagina.get_pixmap(matrix=fitz.Matrix(2, 2))
                    img_bytes = pix.tobytes("png")
                    imagens_base64.append(base64.b64encode(img_bytes).decode())
                doc.close()

            if imagens_base64:
                response = await gemini_service.generate_with_images(
                    prompt=prompt,
                    images_base64=imagens_base64,
                    model=modelo,
                    temperature=0.1,
                    max_tokens=8000,
                    thinking_level=thinking_level
                )
            else:
                tempo_ms = int((time.time() - inicio) * 1000)
                return None, "Não foi possível processar o PDF", tempo_ms

        tempo_ms = int((time.time() - inicio) * 1000)

        if not response.success:
            return None, response.error, tempo_ms

        # Parseia resposta JSON
        json_dict, erro_parse = parsear_resposta_json(response.content)

        if erro_parse:
            return None, erro_parse, tempo_ms

        # Normaliza JSON garantindo que todas as chaves do schema estejam presentes
        json_normalizado = normalizar_json_com_schema(json_dict, categoria.formato_json)

        return json_normalizado, None, tempo_ms

    except Exception as e:
        tempo_ms = int((time.time() - inicio) * 1000)
        logger.error(f"Erro ao classificar documento com modelo {modelo}: {e}")
        return None, str(e), tempo_ms


# ==========================
# Endpoints
# ==========================

@router.post("/validar-processos", response_model=List[ProcessoValidado])
async def validar_processos(
    request: ValidarProcessoRequest,
    current_user: User = Depends(get_current_active_user)
):
    """
    Valida e normaliza uma lista de números de processo.

    Retorna para cada processo:
    - Se é válido
    - O número normalizado (formato CNJ)
    - Mensagem de erro (se inválido)
    """
    verificar_permissao(current_user)

    resultados = []
    for processo in request.processos:
        processo = processo.strip()
        if not processo:
            continue

        valido, normalizado, mensagem = normalizar_processo(processo)

        resultados.append(ProcessoValidado(
            original=processo,
            normalizado=normalizado if valido else None,
            valido=valido,
            erro=None if valido else mensagem
        ))

    return resultados


@router.post("/baixar-documentos")
async def baixar_documentos_categoria(
    request: BaixarDocumentosRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Baixa documentos de processos filtrados por categoria.

    Para cada processo:
    1. Consulta o processo no TJ-MS
    2. Filtra documentos pela categoria selecionada
    3. Baixa os documentos filtrados
    4. Unifica em um único PDF se houver múltiplos
    """
    verificar_permissao(current_user)

    # Busca categoria
    categoria = db.query(CategoriaResumoJSON).filter(
        CategoriaResumoJSON.id == request.categoria_id
    ).first()

    if not categoria:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")

    resultados = []

    for processo in request.processos:
        try:
            # 1. Consulta processo
            xml_consulta, erro = await consultar_processo_tjms(processo)

            if erro:
                resultados.append(ProcessoDocumentos(
                    processo=processo,
                    status="erro",
                    erro=f"Erro ao consultar processo: {erro}"
                ))
                continue

            # 2. Extrai lista de documentos do XML
            from sistemas.gerador_pecas.agente_tjms import extrair_documentos_xml
            todos_documentos = extrair_documentos_xml(xml_consulta)

            # Converte para dicts para filtrar
            docs_dict = [
                {
                    'id': doc.id,
                    'tipo_documento': doc.tipo_documento,
                    'descricao': doc.descricao,
                    'data_juntada': doc.data_juntada
                }
                for doc in todos_documentos
            ]

            # 3. Filtra por categoria
            docs_filtrados = filtrar_documentos_por_categoria(docs_dict, categoria, db)

            if not docs_filtrados:
                # Monta mensagem de erro detalhada
                # Cria mapa de códigos -> descrições para diagnóstico
                codigos_com_desc = {}
                for d in docs_dict:
                    tipo = str(d.get('tipo_documento', '?'))
                    desc = d.get('descricao', '')
                    if tipo not in codigos_com_desc:
                        codigos_com_desc[tipo] = desc

                # Formata lista de códigos com descrição
                codigos_lista = [f"{k}({v})" if v else k for k, v in list(codigos_com_desc.items())[:15]]
                codigos_categoria = categoria.codigos_documento or []

                if categoria.usa_fonte_especial:
                    erro_msg = f"Nenhum documento encontrado para '{categoria.titulo}' (fonte especial: {categoria.source_special_type}). Códigos no processo: {', '.join(codigos_lista)}"
                else:
                    erro_msg = f"Nenhum documento encontrado para '{categoria.titulo}'. Códigos configurados: {codigos_categoria}. Códigos no processo: {', '.join(codigos_lista)}"

                logger.warning(f"Processo {processo}: {erro_msg}")

                resultados.append(ProcessoDocumentos(
                    processo=processo,
                    status="erro",
                    erro=erro_msg
                ))
                continue

            # 4. Baixa documentos
            ids_baixar = [d['id'] for d in docs_filtrados]
            xml_download, erro = await baixar_documentos_tjms(processo, ids_baixar)

            if erro:
                resultados.append(ProcessoDocumentos(
                    processo=processo,
                    status="erro",
                    erro=f"Erro ao baixar documentos: {erro}"
                ))
                continue

            # 5. Extrai PDFs do XML de download
            docs_baixados = extrair_documentos_xml(xml_download)

            documentos_info = []
            pdfs_base64 = []

            for doc in docs_baixados:
                if doc.conteudo_base64:
                    pdfs_base64.append(doc.conteudo_base64)

                    # Conta páginas
                    num_paginas = 0
                    tamanho = len(base64.b64decode(doc.conteudo_base64))

                    if HAS_PYMUPDF:
                        try:
                            pdf_bytes = base64.b64decode(doc.conteudo_base64)
                            doc_pdf = fitz.open(stream=pdf_bytes, filetype="pdf")
                            num_paginas = len(doc_pdf)
                            doc_pdf.close()
                        except:
                            pass

                    documentos_info.append(DocumentoBaixado(
                        id=doc.id,
                        processo=processo,
                        tipo_documento=doc.tipo_documento,
                        descricao=doc.descricao,
                        data_juntada=doc.data_formatada if hasattr(doc, 'data_formatada') else None,
                        tamanho_bytes=tamanho,
                        num_paginas=num_paginas
                    ))

            # 6. Verifica se há PDFs disponíveis
            if not pdfs_base64:
                # Documentos foram encontrados mas não têm conteúdo PDF
                codigos_docs = [d.get('tipo_documento', '?') for d in docs_filtrados]
                resultados.append(ProcessoDocumentos(
                    processo=processo,
                    status="erro",
                    erro=f"Documentos encontrados ({len(docs_filtrados)}) mas sem conteúdo PDF disponível. Códigos: {codigos_docs}"
                ))
                continue

            # 7. Unifica PDFs
            pdf_unificado = unificar_pdfs(pdfs_base64)

            if not pdf_unificado:
                resultados.append(ProcessoDocumentos(
                    processo=processo,
                    status="erro",
                    erro=f"Erro ao unificar {len(pdfs_base64)} PDFs"
                ))
                continue

            resultados.append(ProcessoDocumentos(
                processo=processo,
                status="ok",
                documentos=documentos_info,
                pdf_unificado_base64=pdf_unificado
            ))

        except Exception as e:
            logger.error(f"Erro ao processar processo {processo}: {e}")
            resultados.append(ProcessoDocumentos(
                processo=processo,
                status="erro",
                erro=str(e)
            ))

    return resultados


@router.post("/classificar", response_model=ClassificacaoResultado)
async def classificar_documento(
    request: ClassificarDocumentoRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Classifica um documento usando IA baseado na categoria selecionada.

    Retorna o JSON extraído formatado.
    """
    verificar_permissao(current_user)

    import time
    inicio = time.time()

    # Busca categoria
    categoria = db.query(CategoriaResumoJSON).filter(
        CategoriaResumoJSON.id == request.categoria_id
    ).first()

    if not categoria:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")

    # Classifica com IA
    json_extraido, erro, json_raw = await classificar_documento_com_ia(
        request.pdf_base64,
        categoria,
        db
    )

    tempo_ms = int((time.time() - inicio) * 1000)

    if erro:
        return ClassificacaoResultado(
            processo=request.processo,
            sucesso=False,
            erro=erro,
            json_raw=json_raw,
            tempo_processamento_ms=tempo_ms
        )

    return ClassificacaoResultado(
        processo=request.processo,
        sucesso=True,
        json_extraido=json_extraido,
        json_raw=json_raw,
        tempo_processamento_ms=tempo_ms
    )


@router.post("/classificar-lote", response_model=List[ClassificacaoResultado])
async def classificar_lote(
    request: ClassificarLoteRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Classifica múltiplos documentos em paralelo usando IA.

    Executa até max_paralelo classificações simultaneamente para melhor performance.
    """
    verificar_permissao(current_user)

    # Busca categoria
    categoria = db.query(CategoriaResumoJSON).filter(
        CategoriaResumoJSON.id == request.categoria_id
    ).first()

    if not categoria:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")

    import time

    async def classificar_item(item: ClassificarLoteItem) -> ClassificacaoResultado:
        """Classifica um único item"""
        inicio = time.time()
        try:
            json_extraido, erro, json_raw = await classificar_documento_com_ia(
                item.pdf_base64,
                categoria,
                db
            )
            tempo_ms = int((time.time() - inicio) * 1000)

            if erro:
                return ClassificacaoResultado(
                    processo=item.processo,
                    sucesso=False,
                    erro=erro,
                    json_raw=json_raw,
                    tempo_processamento_ms=tempo_ms
                )

            return ClassificacaoResultado(
                processo=item.processo,
                sucesso=True,
                json_extraido=json_extraido,
                json_raw=json_raw,
                tempo_processamento_ms=tempo_ms
            )
        except Exception as e:
            tempo_ms = int((time.time() - inicio) * 1000)
            logger.error(f"Erro ao classificar {item.processo}: {e}")
            return ClassificacaoResultado(
                processo=item.processo,
                sucesso=False,
                erro=str(e),
                tempo_processamento_ms=tempo_ms
            )

    # Executa em paralelo com limite de concorrência
    semaphore = asyncio.Semaphore(request.max_paralelo)

    async def classificar_com_semaforo(item: ClassificarLoteItem) -> ClassificacaoResultado:
        async with semaphore:
            return await classificar_item(item)

    # Executa todas as classificações em paralelo
    resultados = await asyncio.gather(
        *[classificar_com_semaforo(item) for item in request.itens],
        return_exceptions=False
    )

    return resultados


@router.post("/classificar-comparacao", response_model=ClassificacaoComparacaoResultado)
async def classificar_com_comparacao(
    request: ClassificarComparacaoRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Classifica um documento usando dois modelos de IA e compara resultados.

    Modelo A: gemini-3-flash-preview com thinking="low"
    Modelo B: gemini-2.5-flash-lite com thinking=None (padrão)

    Executa ambos em paralelo e retorna relatório de comparação.
    """
    from sistemas.gerador_pecas.services_comparacao import comparar_jsons_estruturados

    verificar_permissao(current_user)

    # Busca categoria
    categoria = db.query(CategoriaResumoJSON).filter(
        CategoriaResumoJSON.id == request.categoria_id
    ).first()

    if not categoria:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")

    # Configurações dos modelos
    MODELO_A = "gemini-3-flash-preview"
    THINKING_A = "low"
    CONFIG_A = "thinking: low"

    MODELO_B = "gemini-2.5-flash-lite"
    THINKING_B = None
    CONFIG_B = "thinking: default"

    # Executa ambos modelos em paralelo
    logger.info(f"[COMPARE] Iniciando comparação: processo={request.processo}, "
                f"modelo_a={MODELO_A}, modelo_b={MODELO_B}")

    task_a = classificar_documento_com_modelo(
        request.pdf_base64, categoria, MODELO_A, THINKING_A, db
    )
    task_b = classificar_documento_com_modelo(
        request.pdf_base64, categoria, MODELO_B, THINKING_B, db
    )

    # Aguarda ambas completarem
    resultado_a, resultado_b = await asyncio.gather(task_a, task_b)
    json_a, erro_a, tempo_a = resultado_a
    json_b, erro_b, tempo_b = resultado_b

    # Log
    logger.info(f"[COMPARE] Resultado: compare_mode=true, modelo_a={MODELO_A}, "
                f"modelo_b={MODELO_B}, tempo_a={tempo_a}ms, tempo_b={tempo_b}ms, "
                f"erro_a={erro_a}, erro_b={erro_b}")

    # Se ambos falharam, retorna erro
    if erro_a and erro_b:
        return ClassificacaoComparacaoResultado(
            processo=request.processo,
            sucesso=False,
            modelo_a=MODELO_A,
            modelo_b=MODELO_B,
            config_a=CONFIG_A,
            config_b=CONFIG_B,
            tempo_a_ms=tempo_a,
            tempo_b_ms=tempo_b,
            erro=f"Ambos modelos falharam. A: {erro_a} | B: {erro_b}"
        )

    # Se apenas um falhou, ainda retorna parcialmente
    if erro_a:
        return ClassificacaoComparacaoResultado(
            processo=request.processo,
            sucesso=True,  # Parcialmente bem-sucedido
            resultado_a=None,
            resultado_b=json_b,
            modelo_a=MODELO_A,
            modelo_b=MODELO_B,
            config_a=CONFIG_A,
            config_b=CONFIG_B,
            tempo_a_ms=tempo_a,
            tempo_b_ms=tempo_b,
            erro=f"Modelo A falhou: {erro_a}"
        )

    if erro_b:
        return ClassificacaoComparacaoResultado(
            processo=request.processo,
            sucesso=True,  # Parcialmente bem-sucedido
            resultado_a=json_a,
            resultado_b=None,
            modelo_a=MODELO_A,
            modelo_b=MODELO_B,
            config_a=CONFIG_A,
            config_b=CONFIG_B,
            tempo_a_ms=tempo_a,
            tempo_b_ms=tempo_b,
            erro=f"Modelo B falhou: {erro_b}"
        )

    # Compara os resultados
    try:
        schema = json.loads(categoria.formato_json) if categoria.formato_json else {}
    except json.JSONDecodeError:
        schema = {}

    relatorio = comparar_jsons_estruturados(json_a, json_b, schema)

    # Converte para schema Pydantic
    report_schema = RelatorioComparacaoSchema(
        total_campos=relatorio.total_campos,
        campos_comparados=relatorio.campos_comparados,
        campos_iguais=relatorio.campos_iguais,
        campos_diferentes=relatorio.campos_diferentes,
        campos_text_ignorados=relatorio.campos_text_ignorados,
        porcentagem_acordo=relatorio.porcentagem_acordo,
        diferencas=[
            DiferencaCampoSchema(
                campo=d.campo,
                tipo_campo=d.tipo_campo,
                valor_a=d.valor_a,
                valor_b=d.valor_b,
                comparavel=d.comparavel
            )
            for d in relatorio.diferencas
        ],
        resumo=relatorio.resumo
    )

    logger.info(f"[COMPARE] Comparação concluída: {relatorio.resumo}")

    return ClassificacaoComparacaoResultado(
        processo=request.processo,
        sucesso=True,
        resultado_a=json_a,
        resultado_b=json_b,
        modelo_a=MODELO_A,
        modelo_b=MODELO_B,
        config_a=CONFIG_A,
        config_b=CONFIG_B,
        tempo_a_ms=tempo_a,
        tempo_b_ms=tempo_b,
        report=report_schema
    )


@router.get("/categorias-ativas")
async def listar_categorias_ativas(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Lista categorias ativas para seleção no teste"""
    verificar_permissao(current_user)

    categorias = db.query(CategoriaResumoJSON).filter(
        CategoriaResumoJSON.ativo == True
    ).order_by(CategoriaResumoJSON.ordem, CategoriaResumoJSON.nome).all()

    return [
        {
            "id": cat.id,
            "nome": cat.nome,
            "titulo": cat.titulo,
            "descricao": cat.descricao,
            "codigos_documento": cat.codigos_documento or [],
            "usa_fonte_especial": cat.usa_fonte_especial,
            "source_special_type": cat.source_special_type,
            "is_residual": cat.is_residual
        }
        for cat in categorias
    ]


@router.get("/categoria/{categoria_id}/formato")
async def obter_formato_categoria(
    categoria_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Obtém o formato JSON de uma categoria"""
    verificar_permissao(current_user)

    categoria = db.query(CategoriaResumoJSON).filter(
        CategoriaResumoJSON.id == categoria_id
    ).first()

    if not categoria:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")

    # Parse do formato JSON para retornar estruturado
    try:
        formato_parsed = json.loads(categoria.formato_json)
    except:
        formato_parsed = {}

    return {
        "id": categoria.id,
        "nome": categoria.nome,
        "titulo": categoria.titulo,
        "formato_json": categoria.formato_json,
        "formato_parsed": formato_parsed,
        "instrucoes_extracao": categoria.instrucoes_extracao
    }


# ==========================
# Persistência de Documentos de Teste
# ==========================

class SalvarDocumentoRequest(BaseModel):
    """Request para salvar/atualizar um documento de teste"""
    processo: str
    categoria_id: int
    status: str  # pendente, baixado, classificado, erro
    json_resultado: Optional[Dict[str, Any]] = None
    num_documentos: int = 0
    erro: Optional[str] = None
    revisado: bool = False


class DocumentoTesteResponse(BaseModel):
    """Response de um documento de teste"""
    id: int
    processo: str
    categoria_id: int
    status: str
    json_resultado: Optional[Dict[str, Any]] = None
    num_documentos: int = 0
    erro: Optional[str] = None
    revisado: bool = False
    data_criacao: Optional[str] = None
    data_download: Optional[str] = None
    data_classificacao: Optional[str] = None


@router.get("/documentos/{categoria_id}")
async def listar_documentos_categoria(
    categoria_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Lista todos os documentos de teste do usuário para uma categoria.
    """
    verificar_permissao(current_user)

    documentos = db.query(TesteDocumento).filter(
        TesteDocumento.usuario_id == current_user.id,
        TesteDocumento.categoria_id == categoria_id
    ).order_by(TesteDocumento.data_criacao.desc()).all()

    return [doc.to_dict() for doc in documentos]


@router.post("/documentos", response_model=DocumentoTesteResponse)
async def salvar_documento(
    request: SalvarDocumentoRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Salva ou atualiza um documento de teste.

    Se já existir um documento com o mesmo (usuario, categoria, processo),
    atualiza os dados. Caso contrário, cria um novo.
    """
    verificar_permissao(current_user)

    # Busca documento existente
    doc = db.query(TesteDocumento).filter(
        TesteDocumento.usuario_id == current_user.id,
        TesteDocumento.categoria_id == request.categoria_id,
        TesteDocumento.processo == request.processo
    ).first()

    agora = datetime.utcnow()

    if doc:
        # Atualiza existente
        doc.status = request.status
        doc.json_resultado = request.json_resultado
        doc.num_documentos = request.num_documentos
        doc.erro = request.erro
        doc.revisado = request.revisado

        # Atualiza timestamps conforme status
        if request.status == 'baixado' and not doc.data_download:
            doc.data_download = agora
        if request.status == 'classificado' and not doc.data_classificacao:
            doc.data_classificacao = agora
        if request.revisado and not doc.data_revisao:
            doc.data_revisao = agora
    else:
        # Cria novo
        doc = TesteDocumento(
            usuario_id=current_user.id,
            categoria_id=request.categoria_id,
            processo=request.processo,
            status=request.status,
            json_resultado=request.json_resultado,
            num_documentos=request.num_documentos,
            erro=request.erro,
            revisado=request.revisado,
            data_criacao=agora
        )

        if request.status == 'baixado':
            doc.data_download = agora
        if request.status == 'classificado':
            doc.data_classificacao = agora

        db.add(doc)

    db.commit()
    db.refresh(doc)

    return doc.to_dict()


@router.post("/documentos/lote")
async def salvar_documentos_lote(
    documentos: List[SalvarDocumentoRequest],
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Salva múltiplos documentos de uma vez.
    """
    verificar_permissao(current_user)

    resultados = []
    for req in documentos:
        doc = db.query(TesteDocumento).filter(
            TesteDocumento.usuario_id == current_user.id,
            TesteDocumento.categoria_id == req.categoria_id,
            TesteDocumento.processo == req.processo
        ).first()

        agora = datetime.utcnow()

        if doc:
            doc.status = req.status
            doc.json_resultado = req.json_resultado
            doc.num_documentos = req.num_documentos
            doc.erro = req.erro
            doc.revisado = req.revisado

            if req.status == 'baixado' and not doc.data_download:
                doc.data_download = agora
            if req.status == 'classificado' and not doc.data_classificacao:
                doc.data_classificacao = agora
            if req.revisado and not doc.data_revisao:
                doc.data_revisao = agora
        else:
            doc = TesteDocumento(
                usuario_id=current_user.id,
                categoria_id=req.categoria_id,
                processo=req.processo,
                status=req.status,
                json_resultado=req.json_resultado,
                num_documentos=req.num_documentos,
                erro=req.erro,
                revisado=req.revisado,
                data_criacao=agora
            )

            if req.status == 'baixado':
                doc.data_download = agora
            if req.status == 'classificado':
                doc.data_classificacao = agora

            db.add(doc)

        resultados.append(doc)

    db.commit()

    return {"salvos": len(resultados)}


@router.delete("/documentos/{documento_id}")
async def excluir_documento(
    documento_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Exclui um documento de teste.
    """
    verificar_permissao(current_user)

    doc = db.query(TesteDocumento).filter(
        TesteDocumento.id == documento_id,
        TesteDocumento.usuario_id == current_user.id
    ).first()

    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    db.delete(doc)
    db.commit()

    return {"excluido": True}


@router.delete("/documentos/categoria/{categoria_id}/erros")
async def excluir_erros_categoria(
    categoria_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Exclui todos os documentos com erro de uma categoria.
    """
    verificar_permissao(current_user)

    count = db.query(TesteDocumento).filter(
        TesteDocumento.usuario_id == current_user.id,
        TesteDocumento.categoria_id == categoria_id,
        TesteDocumento.status == 'erro'
    ).delete()

    db.commit()

    return {"excluidos": count}


# ==========================
# Observações por Categoria
# ==========================

@router.get("/observacao/{categoria_id}")
async def obter_observacao(
    categoria_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Obtém a observação do usuário para uma categoria.
    """
    verificar_permissao(current_user)

    obs = db.query(TesteObservacao).filter(
        TesteObservacao.usuario_id == current_user.id,
        TesteObservacao.categoria_id == categoria_id
    ).first()

    return {"texto": obs.texto if obs else ""}


@router.put("/observacao/{categoria_id}")
async def salvar_observacao(
    categoria_id: int,
    texto: str = "",
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Salva a observação do usuário para uma categoria.
    """
    verificar_permissao(current_user)

    obs = db.query(TesteObservacao).filter(
        TesteObservacao.usuario_id == current_user.id,
        TesteObservacao.categoria_id == categoria_id
    ).first()

    if obs:
        obs.texto = texto
    else:
        obs = TesteObservacao(
            usuario_id=current_user.id,
            categoria_id=categoria_id,
            texto=texto
        )
        db.add(obs)

    db.commit()

    return {"salvo": True}


# ==========================
# Endpoints de PDF (evita CSP)
# ==========================

class ArmazenarPDFRequest(BaseModel):
    """Request para armazenar PDF no cache"""
    processo: str
    pdf_base64: str


class ArmazenarPDFResponse(BaseModel):
    """Response com token do PDF"""
    token: str
    url: str


@router.post("/pdf/armazenar", response_model=ArmazenarPDFResponse)
async def armazenar_pdf(
    request: ArmazenarPDFRequest,
    current_user: User = Depends(get_current_active_user)
):
    """
    Armazena um PDF no cache temporário e retorna um token para acessá-lo.

    Isso evita problemas de CSP ao exibir PDFs no frontend.
    """
    verificar_permissao(current_user)

    token = armazenar_pdf_cache(request.pdf_base64, request.processo)

    return ArmazenarPDFResponse(
        token=token,
        url=f"/admin/api/teste-categorias/pdf/{token}"
    )


@router.get("/pdf/{token}")
async def servir_pdf(token: str):
    """
    Serve um PDF do cache pelo token.

    Não requer autenticação pois o token é único e expira.
    """
    pdf_bytes = obter_pdf_cache(token)

    if pdf_bytes is None:
        raise HTTPException(status_code=404, detail="PDF não encontrado ou expirado")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": "inline",
            "Cache-Control": "private, max-age=1800"
        }
    )
