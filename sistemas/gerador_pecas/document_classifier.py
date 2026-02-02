# sistemas/gerador_pecas/document_classifier.py
"""
Classificador de Documentos PDF por Categoria.

Este módulo é responsável por:
1. Classificar cada PDF anexado em uma categoria existente no /admin/categorias-resumo-json
2. Detectar se o PDF contém texto extraível ou é imagem
3. Aplicar heurística de texto parcial (primeiros + últimos 1000 tokens) quando possível
4. Enviar PDF como imagem quando OCR falhar
5. Registrar auditoria completa de cada classificação

Modelo obrigatório: gemini-2.5-flash-lite (configurável no admin/prompts-config)
"""

import json
import logging
import base64
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any, Tuple

import fitz  # PyMuPDF
fitz.TOOLS.mupdf_warnings(False)  # Suprime warnings de imagens JPEG2000 corrompidas

# IMPORTANTE: PyMuPDF/MuPDF NÃO é thread-safe!
# Usar lock centralizado para TODAS as operações com fitz
# Sem isso, múltiplas threads causam Segmentation Fault em produção.
from utils.pymupdf_lock import pymupdf_lock as _PYMUPDF_LOCK

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class ClassificationSource(str, Enum):
    """Fonte usada para classificação do documento."""
    TEXT = "text"  # Texto extraído diretamente do PDF
    OCR_TEXT = "ocr_text"  # Texto extraído via OCR
    FULL_IMAGE = "full_image"  # PDF enviado como imagem completa


@dataclass
class DocumentClassification:
    """Resultado da classificação de um documento."""
    arquivo_nome: str
    arquivo_id: str
    categoria_id: int
    categoria_nome: str
    confianca: float
    justificativa: str
    source: ClassificationSource
    texto_utilizado: Optional[str] = None  # Truncado para debug
    fallback_aplicado: bool = False
    fallback_motivo: Optional[str] = None
    erro: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário para serialização."""
        return {
            "arquivo_nome": self.arquivo_nome,
            "arquivo_id": self.arquivo_id,
            "categoria_id": self.categoria_id,
            "categoria_nome": self.categoria_nome,
            "confianca": self.confianca,
            "justificativa": self.justificativa,
            "source": self.source.value,
            "texto_utilizado": self.texto_utilizado[:500] if self.texto_utilizado else None,
            "fallback_aplicado": self.fallback_aplicado,
            "fallback_motivo": self.fallback_motivo,
            "erro": self.erro,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class PDFContent:
    """Conteúdo extraído de um PDF."""
    texto: str
    imagens: List[bytes]  # Lista de imagens das páginas
    tem_texto: bool
    ocr_tentado: bool
    ocr_sucesso: bool
    total_paginas: int
    texto_qualidade: str  # "good", "poor", "none"


# ============================================================================
# EXTRAÇÃO DE CONTEÚDO DO PDF
# ============================================================================

def _contar_tokens_aproximado(texto: str) -> int:
    """
    Conta tokens de forma aproximada (1 token ~ 4 caracteres para português).
    """
    return len(texto) // 4


def _truncar_texto_heuristico(texto: str, max_tokens: int = 1000) -> Tuple[str, str]:
    """
    Extrai os primeiros e últimos N tokens do texto.

    Returns:
        Tupla (texto_inicio, texto_fim)
    """
    max_chars = max_tokens * 4  # Aproximação

    if len(texto) <= max_chars * 2:
        # Texto curto, retorna inteiro
        return texto, ""

    inicio = texto[:max_chars]
    fim = texto[-max_chars:]

    return inicio, fim


def _avaliar_qualidade_texto(texto: str) -> str:
    """
    Avalia a qualidade do texto extraído.

    Returns:
        "good" - Texto legível e suficiente
        "poor" - Texto parcial ou com problemas
        "none" - Sem texto útil
    """
    if not texto or len(texto.strip()) < 50:
        return "none"

    # Conta caracteres legíveis vs caracteres estranhos
    legivel = sum(1 for c in texto if c.isalnum() or c.isspace() or c in '.,;:!?()-')
    total = len(texto)

    ratio = legivel / total if total > 0 else 0

    if ratio > 0.85 and len(texto) > 200:
        return "good"
    elif ratio > 0.5 and len(texto) > 100:
        return "poor"
    else:
        return "none"


def extrair_conteudo_pdf(pdf_bytes: bytes) -> PDFContent:
    """
    Extrai conteúdo de um PDF para classificação.

    Tenta:
    1. Extrair texto diretamente
    2. Se não houver texto, converte páginas para imagens

    Args:
        pdf_bytes: Bytes do arquivo PDF

    Returns:
        PDFContent com texto e/ou imagens

    IMPORTANTE: Usa _PYMUPDF_LOCK para serializar acesso ao PyMuPDF,
    que NÃO é thread-safe. Sem isso, múltiplas threads causam SEGFAULT.
    """
    texto_completo = []
    imagens = []
    tem_texto = False
    ocr_tentado = False
    ocr_sucesso = False
    total_paginas = 0

    try:
        # LOCK OBRIGATÓRIO: PyMuPDF/MuPDF não é thread-safe!
        with _PYMUPDF_LOCK:
            pdf = fitz.open(stream=pdf_bytes, filetype="pdf")
            total_paginas = len(pdf)

            # 1. Tenta extrair texto de cada página
            for pagina in pdf:
                texto = pagina.get_text()
                if texto and texto.strip():
                    texto_completo.append(texto)

            texto_final = "\n".join(texto_completo)
            qualidade = _avaliar_qualidade_texto(texto_final)

            if qualidade == "good":
                tem_texto = True
                pdf.close()
                return PDFContent(
                    texto=texto_final,
                    imagens=[],
                    tem_texto=True,
                    ocr_tentado=False,
                    ocr_sucesso=False,
                    total_paginas=total_paginas,
                    texto_qualidade=qualidade
                )

            # 2. Se texto é pobre ou inexistente, converte para imagens
            logger.info(f"[PDF] Texto com qualidade '{qualidade}', convertendo para imagens")

            for i, pagina in enumerate(pdf):
                # Renderiza a página como imagem (PNG)
                # Usa zoom de 2x para melhor qualidade
                mat = fitz.Matrix(2, 2)
                pix = pagina.get_pixmap(matrix=mat)
                img_bytes = pix.tobytes("png")
                imagens.append(img_bytes)

                # Limita a 10 páginas para não sobrecarregar a API
                if i >= 9:
                    logger.warning(f"[PDF] Limitando a 10 páginas (total: {total_paginas})")
                    break

            pdf.close()

        return PDFContent(
            texto=texto_final if qualidade != "none" else "",
            imagens=imagens,
            tem_texto=qualidade != "none",
            ocr_tentado=False,  # OCR é feito pela IA via imagem
            ocr_sucesso=False,
            total_paginas=total_paginas,
            texto_qualidade=qualidade
        )

    except Exception as e:
        logger.error(f"[PDF] Erro ao extrair conteúdo: {e}")
        return PDFContent(
            texto="",
            imagens=[],
            tem_texto=False,
            ocr_tentado=False,
            ocr_sucesso=False,
            total_paginas=0,
            texto_qualidade="none"
        )


# ============================================================================
# CLASSIFICADOR DE DOCUMENTOS
# ============================================================================

class DocumentClassifier:
    """
    Classificador de documentos PDF por categoria via IA.

    Responsabilidades:
    - Carregar categorias dinamicamente do banco
    - Preparar payload correto (texto parcial ou imagem completa)
    - Chamar modelo de classificação
    - Validar resposta e aplicar fallback quando necessário
    - Registrar auditoria completa
    """

    # Threshold de confiança para aceitar classificação
    CONFIDENCE_THRESHOLD = 0.5

    # Modelo padrão (configurável via admin)
    # Usa gemini-3-flash-preview que é rápido e barato
    DEFAULT_MODEL = "gemini-3-flash-preview"

    def __init__(
        self,
        db: Session,
        modelo: Optional[str] = None,
        threshold_confianca: float = 0.5
    ):
        """
        Inicializa o classificador.

        Args:
            db: Sessão do banco de dados
            modelo: Modelo de IA a usar (padrão: gemini-2.5-flash-lite)
            threshold_confianca: Threshold mínimo de confiança (padrão: 0.5)
        """
        self.db = db
        self.modelo = modelo or self._carregar_modelo_config()
        self.threshold = threshold_confianca
        self._categorias_cache: Optional[List[Dict]] = None
        self._categoria_padrao: Optional[Dict] = None

    def _carregar_modelo_config(self) -> str:
        """Carrega modelo configurado no admin ou usa padrão."""
        try:
            from admin.models import ConfiguracaoIA

            config = self.db.query(ConfiguracaoIA).filter(
                ConfiguracaoIA.sistema == "sistemas_acessorios",
                ConfiguracaoIA.chave == "classificador_documentos_modelo"
            ).first()

            if config and config.valor:
                return config.valor
        except Exception as e:
            logger.warning(f"[Classifier] Erro ao carregar config: {e}")

        return self.DEFAULT_MODEL

    def _carregar_categorias(self) -> List[Dict]:
        """
        Carrega categorias ativas do banco.

        Returns:
            Lista de dicts com id, nome, titulo, descricao
        """
        if self._categorias_cache is not None:
            return self._categorias_cache

        from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON

        categorias = self.db.query(CategoriaResumoJSON).filter(
            CategoriaResumoJSON.ativo == True
        ).order_by(CategoriaResumoJSON.ordem).all()

        self._categorias_cache = []

        for cat in categorias:
            cat_dict = {
                "id": cat.id,
                "nome": cat.nome,
                "titulo": cat.titulo,
                "descricao": (cat.descricao or "")[:200]  # Limita descrição
            }
            self._categorias_cache.append(cat_dict)

            # Guarda categoria residual como padrão
            if cat.is_residual:
                self._categoria_padrao = cat_dict

        # Log detalhado para debug
        nomes_categorias = [c["nome"] for c in self._categorias_cache]
        logger.info(f"[Classifier] {len(self._categorias_cache)} categorias carregadas: {nomes_categorias}")
        if self._categoria_padrao:
            logger.info(f"[Classifier] Categoria padrão (residual): {self._categoria_padrao['nome']}")
        return self._categorias_cache

    def _montar_lista_categorias_prompt(self) -> str:
        """
        Monta lista compacta de categorias para o prompt.
        """
        categorias = self._carregar_categorias()

        linhas = []
        for cat in categorias:
            desc = f" - {cat['descricao']}" if cat['descricao'] else ""
            linhas.append(f"- ID: {cat['id']} | {cat['nome']} ({cat['titulo']}){desc}")

        return "\n".join(linhas)

    def _montar_prompt_classificacao(self, conteudo_texto: Optional[str] = None) -> str:
        """
        Monta o prompt estruturado para classificação.

        Args:
            conteudo_texto: Texto do documento (se disponível)
        """
        categorias_lista = self._montar_lista_categorias_prompt()

        prompt = f"""Você é um classificador de documentos jurídicos. Analise o documento fornecido e classifique-o em UMA das categorias listadas abaixo.

## CATEGORIAS DISPONÍVEIS
{categorias_lista}

## REGRAS
1. Escolha EXATAMENTE UMA categoria da lista acima.
2. Use o ID exato da categoria escolhida.
3. Se tiver dúvida entre categorias, escolha a mais provável e indique confiança baixa.
4. A confiança deve refletir sua certeza: 1.0 = certeza absoluta, 0.0 = chute.

## DOCUMENTO A CLASSIFICAR
"""

        if conteudo_texto:
            prompt += f"""
### Texto do documento:
{conteudo_texto}
"""
        else:
            prompt += """
### Imagens do documento:
[Analise as imagens fornecidas]
"""

        prompt += """

## FORMATO DE RESPOSTA (JSON)
Retorne SOMENTE este JSON, sem texto adicional:
```json
{
  "categoria_id": <ID_NUMERICO_DA_CATEGORIA>,
  "confianca": <0.0_A_1.0>,
  "justificativa_curta": "<até 140 caracteres explicando a escolha>"
}
```
"""
        return prompt

    async def _chamar_ia(
        self,
        prompt: str,
        imagens: Optional[List[bytes]] = None
    ) -> Dict[str, Any]:
        """
        Chama a IA para classificação usando o serviço centralizado.

        Args:
            prompt: Prompt de classificação
            imagens: Lista de imagens em bytes (opcional)

        Returns:
            Dict com categoria_id, confianca, justificativa_curta
        """
        try:
            # Usa serviço centralizado de Gemini
            from services.gemini_service import gemini_service

            # Carrega config de temperatura
            from admin.models import ConfiguracaoIA
            temp_config = self.db.query(ConfiguracaoIA).filter(
                ConfiguracaoIA.sistema == "sistemas_acessorios",
                ConfiguracaoIA.chave == "classificador_documentos_temperatura"
            ).first()
            temperatura = float(temp_config.valor) if temp_config and temp_config.valor else 0.1

            # Chama modelo apropriado
            if imagens:
                # Converte bytes para base64
                imagens_b64 = [base64.b64encode(img).decode() for img in imagens]

                response = await gemini_service.generate_with_images(
                    prompt=prompt,
                    images_base64=imagens_b64,
                    model=self.modelo,
                    temperature=temperatura,
                    max_tokens=500,
                    thinking_level="low",  # Classificação não precisa de thinking alto
                    context={"sistema": "document_classifier", "modulo": "classificacao_categoria"}
                )
            else:
                response = await gemini_service.generate(
                    prompt=prompt,
                    model=self.modelo,
                    temperature=temperatura,
                    max_tokens=500,
                    thinking_level="low",
                    context={"sistema": "document_classifier", "modulo": "classificacao_categoria"}
                )

            if not response.success:
                raise ValueError(f"Erro na API Gemini: {response.error}")

            texto_resposta = response.content.strip()
            logger.info(f"[Classifier] Resposta IA: {texto_resposta[:200]}...")

            # Extrai JSON de bloco markdown se presente
            import re
            match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', texto_resposta)
            if match:
                json_str = match.group(1)
            else:
                # Tenta extrair JSON direto
                first_brace = texto_resposta.find('{')
                last_brace = texto_resposta.rfind('}')
                if first_brace >= 0 and last_brace > first_brace:
                    json_str = texto_resposta[first_brace:last_brace + 1]
                else:
                    json_str = texto_resposta

            resultado = json.loads(json_str)

            # Valida campos obrigatórios
            if "categoria_id" not in resultado:
                raise ValueError("Resposta sem categoria_id")

            resultado["confianca"] = float(resultado.get("confianca", 0.5))
            resultado["justificativa_curta"] = resultado.get("justificativa_curta", "")[:140]

            logger.info(f"[Classifier] Resultado: categoria_id={resultado['categoria_id']}, confianca={resultado['confianca']}")
            return resultado

        except json.JSONDecodeError as e:
            logger.error(f"[Classifier] Erro ao parsear JSON: {e}")
            raise ValueError(f"JSON inválido: {e}")
        except Exception as e:
            logger.error(f"[Classifier] Erro ao chamar IA: {e}")
            raise

    def _validar_categoria(self, categoria_id: int) -> Optional[Dict]:
        """
        Valida se categoria_id existe.

        Returns:
            Dict da categoria ou None
        """
        categorias = self._carregar_categorias()
        for cat in categorias:
            if cat["id"] == categoria_id:
                return cat
        return None

    def _aplicar_fallback(self, motivo: str) -> Tuple[int, str]:
        """
        Aplica fallback determinístico.

        Returns:
            Tupla (categoria_id, categoria_nome)
        """
        # Usa categoria residual/padrão se existir
        if self._categoria_padrao:
            return self._categoria_padrao["id"], self._categoria_padrao["nome"]

        # Se não houver categoria padrão, usa a primeira da lista
        categorias = self._carregar_categorias()
        if categorias:
            return categorias[0]["id"], categorias[0]["nome"]

        raise ValueError("Nenhuma categoria disponível para fallback")

    async def classificar_documento(
        self,
        arquivo_nome: str,
        arquivo_id: str,
        pdf_bytes: bytes,
        codigo_documento: Optional[int] = None
    ) -> DocumentClassification:
        """
        Classifica um documento PDF.

        Args:
            arquivo_nome: Nome do arquivo
            arquivo_id: ID único do arquivo
            pdf_bytes: Bytes do PDF
            codigo_documento: Código TJ-MS (se disponível, pula classificação IA)

        Returns:
            DocumentClassification com resultado
        """
        logger.info(f"[Classifier] Classificando: {arquivo_nome}")

        # Se tem código conhecido, usa fluxo existente (não chama IA)
        if codigo_documento:
            from sistemas.gerador_pecas.extrator_resumo_json import obter_formato_para_documento
            formato = obter_formato_para_documento(self.db, codigo_documento)

            if formato:
                return DocumentClassification(
                    arquivo_nome=arquivo_nome,
                    arquivo_id=arquivo_id,
                    categoria_id=formato.categoria_id,
                    categoria_nome=formato.categoria_nome,
                    confianca=1.0,
                    justificativa="Código de documento conhecido",
                    source=ClassificationSource.TEXT,
                    fallback_aplicado=False
                )

        # Extrai conteúdo do PDF
        conteudo = extrair_conteudo_pdf(pdf_bytes)

        # Decide estratégia: texto parcial ou imagem completa
        source = ClassificationSource.TEXT
        texto_para_enviar = None
        imagens_para_enviar = None

        if conteudo.tem_texto and conteudo.texto_qualidade == "good":
            # Caso 1: PDF com texto extraível - usa heurística de texto parcial
            inicio, fim = _truncar_texto_heuristico(conteudo.texto, max_tokens=1000)

            if fim:
                texto_para_enviar = f"[INÍCIO DO DOCUMENTO]\n{inicio}\n\n[...]\n\n[FIM DO DOCUMENTO]\n{fim}"
            else:
                texto_para_enviar = conteudo.texto

            source = ClassificationSource.TEXT
            logger.info(f"[Classifier] Usando texto ({len(texto_para_enviar)} chars)")

        elif conteudo.imagens:
            # Caso 2: PDF é imagem ou OCR falhou - envia imagens
            imagens_para_enviar = conteudo.imagens
            source = ClassificationSource.FULL_IMAGE
            logger.info(f"[Classifier] Usando {len(imagens_para_enviar)} imagens")

        else:
            # Caso 3: Não conseguiu extrair nada - fallback
            logger.warning(f"[Classifier] Sem conteúdo extraível: {arquivo_nome}")
            cat_id, cat_nome = self._aplicar_fallback("Sem conteúdo extraível")

            return DocumentClassification(
                arquivo_nome=arquivo_nome,
                arquivo_id=arquivo_id,
                categoria_id=cat_id,
                categoria_nome=cat_nome,
                confianca=0.0,
                justificativa="Documento sem conteúdo extraível",
                source=ClassificationSource.FULL_IMAGE,
                fallback_aplicado=True,
                fallback_motivo="Sem conteúdo extraível do PDF"
            )

        # Monta prompt e chama IA
        prompt = self._montar_prompt_classificacao(texto_para_enviar)

        try:
            resultado = await self._chamar_ia(prompt, imagens_para_enviar)

            # Valida categoria retornada
            categoria = self._validar_categoria(resultado["categoria_id"])

            if not categoria:
                # Categoria inválida - fallback
                logger.warning(f"[Classifier] Categoria inválida: {resultado['categoria_id']}")
                cat_id, cat_nome = self._aplicar_fallback("Categoria inexistente")

                return DocumentClassification(
                    arquivo_nome=arquivo_nome,
                    arquivo_id=arquivo_id,
                    categoria_id=cat_id,
                    categoria_nome=cat_nome,
                    confianca=resultado["confianca"],
                    justificativa=resultado["justificativa_curta"],
                    source=source,
                    texto_utilizado=texto_para_enviar,
                    fallback_aplicado=True,
                    fallback_motivo=f"IA retornou categoria inexistente: {resultado['categoria_id']}"
                )

            # Verifica threshold de confiança
            if resultado["confianca"] < self.threshold:
                logger.warning(f"[Classifier] Confiança baixa: {resultado['confianca']}")
                cat_id, cat_nome = self._aplicar_fallback("Confiança baixa")

                return DocumentClassification(
                    arquivo_nome=arquivo_nome,
                    arquivo_id=arquivo_id,
                    categoria_id=cat_id,
                    categoria_nome=cat_nome,
                    confianca=resultado["confianca"],
                    justificativa=resultado["justificativa_curta"],
                    source=source,
                    texto_utilizado=texto_para_enviar,
                    fallback_aplicado=True,
                    fallback_motivo=f"Confiança {resultado['confianca']:.2f} abaixo do threshold {self.threshold}"
                )

            # Classificação bem-sucedida
            return DocumentClassification(
                arquivo_nome=arquivo_nome,
                arquivo_id=arquivo_id,
                categoria_id=categoria["id"],
                categoria_nome=categoria["nome"],
                confianca=resultado["confianca"],
                justificativa=resultado["justificativa_curta"],
                source=source,
                texto_utilizado=texto_para_enviar,
                fallback_aplicado=False
            )

        except Exception as e:
            # Erro na IA - fallback
            logger.error(f"[Classifier] Erro na classificação: {e}")
            cat_id, cat_nome = self._aplicar_fallback(str(e))

            return DocumentClassification(
                arquivo_nome=arquivo_nome,
                arquivo_id=arquivo_id,
                categoria_id=cat_id,
                categoria_nome=cat_nome,
                confianca=0.0,
                justificativa="Erro na classificação via IA",
                source=source,
                texto_utilizado=texto_para_enviar,
                fallback_aplicado=True,
                fallback_motivo=f"Erro IA: {str(e)[:100]}",
                erro=str(e)
            )

    async def classificar_lote(
        self,
        documentos: List[Dict[str, Any]]
    ) -> List[DocumentClassification]:
        """
        Classifica um lote de documentos.

        Args:
            documentos: Lista de dicts com 'nome', 'id', 'bytes', 'codigo' (opcional)

        Returns:
            Lista de DocumentClassification
        """
        resultados = []

        for doc in documentos:
            resultado = await self.classificar_documento(
                arquivo_nome=doc["nome"],
                arquivo_id=doc["id"],
                pdf_bytes=doc["bytes"],
                codigo_documento=doc.get("codigo")
            )
            resultados.append(resultado)

        return resultados
