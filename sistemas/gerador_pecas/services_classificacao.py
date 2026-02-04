# sistemas/gerador_pecas/services_classificacao.py
"""
Serviço de classificação de tipo lógico de documentos.

Este módulo implementa:
- Classificação de documentos por tipo lógico (petição inicial, contestação, etc.)
- Verificação de fonte de verdade antes da extração
- Suporte a grupos com múltiplos tipos de peça

Usa Gemini 3 Flash Preview para classificação inteligente.
"""

import logging
import json
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session

from services.gemini_service import gemini_service, get_thinking_level
from .models_resumo_json import CategoriaResumoJSON

logger = logging.getLogger(__name__)

# Modelo padrão para classificação
GEMINI_MODEL = "gemini-3-flash-preview"


class DocumentClassificationService:
    """
    Serviço para classificar documentos por tipo lógico.

    Usado quando uma categoria tem múltiplos tipos de peça possíveis
    e precisa identificar qual tipo é o documento antes de extrair.
    """

    def __init__(self, db: Session):
        self.db = db

    async def classificar_documento(
        self,
        conteudo: str,
        categoria: CategoriaResumoJSON,
        metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Classifica um documento identificando seu tipo lógico.

        Args:
            conteudo: Conteúdo textual do documento
            categoria: Categoria do documento
            metadata: Metadados opcionais (código, nome do arquivo, etc.)

        Returns:
            Dict com:
                - success: bool
                - tipo_logico: str (tipo identificado)
                - confianca: float (0-1)
                - justificativa: str
                - e_fonte_verdade: bool (se é a fonte de verdade do grupo)
        """
        # Se categoria não requer classificação, retorna sempre como fonte de verdade
        if not categoria.requer_classificacao:
            return {
                "success": True,
                "tipo_logico": None,
                "confianca": 1.0,
                "justificativa": "Categoria não requer classificação",
                "e_fonte_verdade": True
            }

        # Obtém tipos lógicos possíveis
        tipos_possiveis = categoria.tipos_logicos_peca or []
        if not tipos_possiveis:
            return {
                "success": True,
                "tipo_logico": None,
                "confianca": 1.0,
                "justificativa": "Nenhum tipo lógico definido para esta categoria",
                "e_fonte_verdade": True
            }

        try:
            # Monta o prompt de classificação
            prompt = self._montar_prompt_classificacao(
                conteudo=conteudo,
                tipos_possiveis=tipos_possiveis,
                categoria_nome=categoria.titulo,
                metadata=metadata
            )

            # Obtém thinking_level da config
            thinking_level = get_thinking_level(self.db, "gerador_pecas")

            # Chama o Gemini
            response = await gemini_service.generate(
                prompt=prompt,
                system_prompt=self._get_system_prompt(),
                model=GEMINI_MODEL,
                temperature=0.1,
                thinking_level=thinking_level  # Configurável em /admin/prompts-config
            )

            if not response.success:
                logger.error(f"Erro na classificação: {response.error}")
                return {
                    "success": False,
                    "erro": f"Erro na IA: {response.error}"
                }

            # Parseia a resposta
            resultado = self._extrair_resultado(response.content)

            if not resultado:
                logger.warning(f"Resposta de classificação inválida: {response.content[:300]}")
                return {
                    "success": False,
                    "erro": "Resposta de classificação inválida"
                }

            tipo_logico = resultado.get("tipo_logico")
            confianca = resultado.get("confianca", 0.5)
            justificativa = resultado.get("justificativa", "")

            # Verifica se é a fonte de verdade
            fonte_verdade = categoria.fonte_verdade_tipo
            e_fonte_verdade = (
                tipo_logico == fonte_verdade or
                fonte_verdade is None or
                fonte_verdade == ""
            )

            return {
                "success": True,
                "tipo_logico": tipo_logico,
                "confianca": confianca,
                "justificativa": justificativa,
                "e_fonte_verdade": e_fonte_verdade,
                "fonte_verdade_esperada": fonte_verdade
            }

        except Exception as e:
            logger.exception(f"Erro na classificação de documento: {e}")
            return {
                "success": False,
                "erro": str(e)
            }

    def _get_system_prompt(self) -> str:
        """Retorna o prompt de sistema para classificação."""
        return """Você é um especialista em classificação de documentos jurídicos.

Sua tarefa é identificar o TIPO LÓGICO do documento apresentado.

INSTRUÇÕES:
1. Analise o conteúdo e estrutura do documento
2. Identifique características que definem o tipo (petição inicial tem pedidos iniciais, contestação contesta pedidos, etc.)
3. Escolha o tipo mais apropriado da lista fornecida
4. Forneça uma justificativa breve
5. Indique sua confiança (0.0 a 1.0)

RETORNE APENAS JSON no formato:
{
    "tipo_logico": "nome do tipo identificado",
    "confianca": 0.95,
    "justificativa": "breve explicação"
}

Se não conseguir classificar com certeza, use confiança baixa (< 0.5)."""

    def _montar_prompt_classificacao(
        self,
        conteudo: str,
        tipos_possiveis: List[str],
        categoria_nome: str,
        metadata: Optional[Dict] = None
    ) -> str:
        """Monta o prompt para classificação."""
        # Limita o conteúdo para não exceder o contexto
        conteudo_limitado = conteudo[:8000] if len(conteudo) > 8000 else conteudo

        prompt = f"""Classifique o documento abaixo.

CATEGORIA: {categoria_nome}

TIPOS POSSÍVEIS:
{chr(10).join(f'- {tipo}' for tipo in tipos_possiveis)}
"""

        if metadata:
            prompt += f"\nMETADADOS: {json.dumps(metadata, ensure_ascii=False)}\n"

        prompt += f"""
CONTEÚDO DO DOCUMENTO:
---
{conteudo_limitado}
---

Identifique qual dos tipos possíveis melhor descreve este documento.
Retorne APENAS o JSON de resposta."""

        return prompt

    def _extrair_resultado(self, resposta: str) -> Optional[Dict]:
        """Extrai o JSON da resposta."""
        try:
            # Tenta parsear diretamente
            return json.loads(resposta)
        except json.JSONDecodeError:
            pass

        # Tenta encontrar JSON na resposta
        import re
        json_match = re.search(r'\{[^{}]*"tipo_logico"[^{}]*\}', resposta, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        return None


class SourceOfTruthValidator:
    """
    Validador de fonte de verdade para extração.

    Garante que variáveis só são extraídas de documentos
    que são a fonte de verdade configurada para o grupo.
    """

    def __init__(self, db: Session):
        self.db = db
        self.classification_service = DocumentClassificationService(db)

    async def validar_documento_para_extracao(
        self,
        conteudo: str,
        categoria_id: int,
        metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Valida se um documento deve ter variáveis extraídas.

        Args:
            conteudo: Conteúdo do documento
            categoria_id: ID da categoria
            metadata: Metadados do documento

        Returns:
            Dict com:
                - deve_extrair: bool
                - tipo_logico: str (se classificado)
                - motivo: str
        """
        # Busca a categoria
        categoria = self.db.query(CategoriaResumoJSON).filter(
            CategoriaResumoJSON.id == categoria_id
        ).first()

        if not categoria:
            return {
                "deve_extrair": False,
                "motivo": "Categoria não encontrada"
            }

        # Se não requer classificação, sempre extrai
        if not categoria.requer_classificacao:
            return {
                "deve_extrair": True,
                "tipo_logico": None,
                "motivo": "Categoria não requer classificação de fonte de verdade"
            }

        # Classifica o documento
        resultado = await self.classification_service.classificar_documento(
            conteudo=conteudo,
            categoria=categoria,
            metadata=metadata
        )

        if not resultado.get("success"):
            # Em caso de erro, permite extração (fail-open)
            logger.warning(f"Erro na classificação, permitindo extração: {resultado.get('erro')}")
            return {
                "deve_extrair": True,
                "tipo_logico": None,
                "motivo": f"Erro na classificação: {resultado.get('erro')}"
            }

        tipo_logico = resultado.get("tipo_logico")
        e_fonte_verdade = resultado.get("e_fonte_verdade", True)

        if e_fonte_verdade:
            return {
                "deve_extrair": True,
                "tipo_logico": tipo_logico,
                "confianca": resultado.get("confianca"),
                "motivo": f"Documento classificado como '{tipo_logico}' (fonte de verdade)"
            }
        else:
            fonte_esperada = resultado.get("fonte_verdade_esperada")
            return {
                "deve_extrair": False,
                "tipo_logico": tipo_logico,
                "confianca": resultado.get("confianca"),
                "motivo": f"Documento classificado como '{tipo_logico}', mas fonte de verdade é '{fonte_esperada}'"
            }

    def get_namespace_for_categoria(self, categoria_id: int) -> Optional[str]:
        """Retorna o namespace de uma categoria."""
        categoria = self.db.query(CategoriaResumoJSON).filter(
            CategoriaResumoJSON.id == categoria_id
        ).first()

        return categoria.namespace if categoria else None
