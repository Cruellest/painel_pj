# sistemas/gerador_pecas/document_selector.py
"""
Seletor de Documentos para Geração de Peças.

Este módulo é responsável por:
1. Selecionar documentos primários e secundários para cada tipo de peça
2. Aplicar regras de priorização configuráveis
3. Resolver empates entre documentos do mesmo tipo
4. Fornecer razão explicável para cada seleção
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Set
from enum import Enum

from sqlalchemy.orm import Session

from sistemas.gerador_pecas.document_classifier import DocumentClassification

logger = logging.getLogger(__name__)


class DocumentRole(str, Enum):
    """Papel do documento na geração."""
    PRIMARY = "primary"  # Fonte principal de extração
    SECONDARY = "secondary"  # Fonte auxiliar
    EXCLUDED = "excluded"  # Não usado na geração


@dataclass
class SelectedDocument:
    """Documento selecionado para geração."""
    classificacao: DocumentClassification
    role: DocumentRole
    prioridade: int  # Ordem de prioridade (menor = mais prioritário)
    razao: str  # Explicação da seleção


@dataclass
class SelectionResult:
    """Resultado da seleção de documentos."""
    tipo_peca: str
    documentos_primarios: List[SelectedDocument]
    documentos_secundarios: List[SelectedDocument]
    documentos_excluidos: List[SelectedDocument]
    razao_geral: str

    def get_todos_selecionados(self) -> List[SelectedDocument]:
        """Retorna todos os documentos selecionados (primários + secundários)."""
        return self.documentos_primarios + self.documentos_secundarios

    def get_ids_primarios(self) -> List[str]:
        """Retorna IDs dos documentos primários."""
        return [d.classificacao.arquivo_id for d in self.documentos_primarios]

    def get_ids_secundarios(self) -> List[str]:
        """Retorna IDs dos documentos secundários."""
        return [d.classificacao.arquivo_id for d in self.documentos_secundarios]

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "tipo_peca": self.tipo_peca,
            "documentos_primarios": [
                {
                    "arquivo_id": d.classificacao.arquivo_id,
                    "arquivo_nome": d.classificacao.arquivo_nome,
                    "categoria": d.classificacao.categoria_nome,
                    "confianca": d.classificacao.confianca,
                    "prioridade": d.prioridade,
                    "razao": d.razao
                }
                for d in self.documentos_primarios
            ],
            "documentos_secundarios": [
                {
                    "arquivo_id": d.classificacao.arquivo_id,
                    "arquivo_nome": d.classificacao.arquivo_nome,
                    "categoria": d.classificacao.categoria_nome,
                    "confianca": d.classificacao.confianca,
                    "prioridade": d.prioridade,
                    "razao": d.razao
                }
                for d in self.documentos_secundarios
            ],
            "razao_geral": self.razao_geral
        }


# ============================================================================
# CONFIGURAÇÃO DE PRIORIDADES POR TIPO DE PEÇA
# ============================================================================

# Mapeamento de tipo de peça para categorias prioritárias
# Formato: tipo_peca -> {primarias: [categorias], secundarias: [categorias]}
# NOTA: Nomes devem corresponder ao campo 'nome' das categorias no banco
DEFAULT_PRIORITY_CONFIG = {
    "contestacao": {
        "primarias": ["peticoes", "peticao_inicial", "petições", "peticao"],
        "secundarias": ["decisoes", "decisao", "sentencas", "sentenca", "despachos", "pareceres", "residual"],
        "descricao": "Contestação: prioriza petição inicial como fonte primária"
    },
    "contestacao_v1": {
        "primarias": ["peticoes", "peticao_inicial", "petições", "peticao"],
        "secundarias": ["decisoes", "decisao", "sentencas", "sentenca", "despachos", "pareceres", "residual"],
        "descricao": "Contestação v1: prioriza petição inicial como fonte primária"
    },
    "contrarrazoes": {
        "primarias": ["recursos", "apelacao", "agravo", "recurso"],
        "secundarias": ["sentencas", "decisoes", "peticoes", "residual"],
        "descricao": "Contrarrazões: prioriza recurso adversário como fonte primária"
    },
    "recurso_apelacao": {
        "primarias": ["sentencas", "sentenca", "decisoes", "decisao"],
        "secundarias": ["peticoes", "contestacao", "pareceres", "residual"],
        "descricao": "Apelação: prioriza sentença/decisão como fonte primária"
    },
    "agravo_instrumento": {
        "primarias": ["decisoes", "decisao", "despachos"],
        "secundarias": ["peticoes", "pareceres", "residual"],
        "descricao": "Agravo de Instrumento: prioriza decisão interlocutória"
    },
    "parecer": {
        "primarias": ["peticoes", "requerimentos", "peticao"],
        "secundarias": ["documentos", "contratos", "pareceres", "residual"],
        "descricao": "Parecer: prioriza petição/requerimento analisado"
    },
    # Configuração default para tipos não mapeados
    "_default": {
        "primarias": ["peticoes", "peticao_inicial", "peticao"],
        "secundarias": ["decisoes", "sentencas", "pareceres", "residual"],
        "descricao": "Configuração padrão: prioriza petições"
    }
}


class DocumentSelector:
    """
    Seletor de documentos para geração de peças.

    Responsabilidades:
    - Aplicar regras de priorização por tipo de peça
    - Selecionar documentos primários e secundários
    - Resolver empates entre documentos similares
    - Carregar configuração do banco (se disponível)
    """

    def __init__(
        self,
        db: Session,
        config_personalizada: Optional[Dict] = None
    ):
        """
        Inicializa o seletor.

        Args:
            db: Sessão do banco de dados
            config_personalizada: Configuração personalizada (opcional)
        """
        self.db = db
        self._config = config_personalizada or self._carregar_config()

    def _carregar_config(self) -> Dict:
        """
        Carrega configuração de prioridades do banco.

        Se não existir no banco, usa configuração default.
        """
        try:
            from admin.models import ConfiguracaoIA

            config = self.db.query(ConfiguracaoIA).filter(
                ConfiguracaoIA.sistema == "gerador_pecas",
                ConfiguracaoIA.chave == "document_selector_config"
            ).first()

            if config and config.valor:
                import json
                return json.loads(config.valor)
        except Exception as e:
            logger.warning(f"[Selector] Erro ao carregar config: {e}")

        return DEFAULT_PRIORITY_CONFIG

    def _get_config_tipo_peca(self, tipo_peca: str) -> Dict:
        """Obtém configuração para um tipo de peça específico."""
        # Normaliza nome do tipo de peça
        tipo_normalizado = tipo_peca.lower().replace("-", "_").replace(" ", "_")

        if tipo_normalizado in self._config:
            return self._config[tipo_normalizado]

        # Tenta match parcial
        for key in self._config:
            if key != "_default" and key in tipo_normalizado:
                return self._config[key]

        return self._config.get("_default", DEFAULT_PRIORITY_CONFIG["_default"])

    def _calcular_match_score(
        self,
        categoria_doc: str,
        categorias_alvo: List[str]
    ) -> int:
        """
        Calcula score de match entre categoria do documento e categorias alvo.

        Returns:
            Score (menor = melhor match), -1 se não houver match
        """
        categoria_normalizada = categoria_doc.lower().replace("-", "_").replace(" ", "_")

        for i, cat_alvo in enumerate(categorias_alvo):
            cat_alvo_norm = cat_alvo.lower().replace("-", "_").replace(" ", "_")

            # Match exato
            if categoria_normalizada == cat_alvo_norm:
                return i

            # Match parcial (categoria contém alvo ou vice-versa)
            if cat_alvo_norm in categoria_normalizada or categoria_normalizada in cat_alvo_norm:
                return i + 100  # Penaliza match parcial

        return -1

    def _resolver_empate(
        self,
        documentos: List[DocumentClassification]
    ) -> List[DocumentClassification]:
        """
        Resolve empate entre documentos do mesmo tipo.

        Critérios de desempate:
        1. Maior confiança de classificação
        2. Presença de palavras-chave indicativas
        3. Ordem de envio (primeiro documento)

        Returns:
            Lista ordenada por prioridade
        """
        def score_documento(doc: DocumentClassification) -> float:
            score = doc.confianca * 100

            # Bonus por palavras-chave no texto
            if doc.texto_utilizado:
                texto_lower = doc.texto_utilizado.lower()

                # Palavras que indicam documento principal
                keywords_principais = [
                    "dos fatos", "dos pedidos", "requer", "diante do exposto",
                    "ante o exposto", "pelo que requer", "excelentíssimo",
                    "vem, respeitosamente", "conclusão", "isto posto"
                ]

                for kw in keywords_principais:
                    if kw in texto_lower:
                        score += 5

            return score

        # Ordena por score (maior = melhor)
        documentos_ordenados = sorted(
            documentos,
            key=lambda d: score_documento(d),
            reverse=True
        )

        return documentos_ordenados

    def selecionar_documentos(
        self,
        classificacoes: List[DocumentClassification],
        tipo_peca: str
    ) -> SelectionResult:
        """
        Seleciona documentos para geração de uma peça.

        Args:
            classificacoes: Lista de documentos classificados
            tipo_peca: Tipo de peça a ser gerada

        Returns:
            SelectionResult com documentos primários e secundários
        """
        logger.info(f"[Selector] Selecionando docs para '{tipo_peca}' ({len(classificacoes)} docs)")

        config = self._get_config_tipo_peca(tipo_peca)
        categorias_primarias = config.get("primarias", [])
        categorias_secundarias = config.get("secundarias", [])

        # Agrupa documentos por categoria
        docs_por_categoria: Dict[str, List[DocumentClassification]] = {}
        for doc in classificacoes:
            cat_nome = doc.categoria_nome.lower()
            if cat_nome not in docs_por_categoria:
                docs_por_categoria[cat_nome] = []
            docs_por_categoria[cat_nome].append(doc)

        # Seleciona primários
        primarios: List[SelectedDocument] = []
        categorias_usadas: Set[str] = set()

        for doc in classificacoes:
            score = self._calcular_match_score(doc.categoria_nome, categorias_primarias)

            if score >= 0:
                # Verifica se já tem documento desta categoria
                cat_norm = doc.categoria_nome.lower()
                docs_mesma_cat = docs_por_categoria.get(cat_norm, [])

                if len(docs_mesma_cat) > 1:
                    # Resolve empate
                    docs_ordenados = self._resolver_empate(docs_mesma_cat)

                    if doc != docs_ordenados[0]:
                        continue  # Não é o melhor da categoria

                if cat_norm not in categorias_usadas:
                    primarios.append(SelectedDocument(
                        classificacao=doc,
                        role=DocumentRole.PRIMARY,
                        prioridade=score,
                        razao=f"Categoria '{doc.categoria_nome}' é primária para {tipo_peca}"
                    ))
                    categorias_usadas.add(cat_norm)

        # Ordena primários por prioridade
        primarios.sort(key=lambda d: d.prioridade)

        # Seleciona secundários
        secundarios: List[SelectedDocument] = []

        for doc in classificacoes:
            cat_norm = doc.categoria_nome.lower()

            # Pula se já é primário
            if cat_norm in categorias_usadas:
                continue

            score = self._calcular_match_score(doc.categoria_nome, categorias_secundarias)

            if score >= 0:
                # Resolve empate se houver múltiplos
                docs_mesma_cat = docs_por_categoria.get(cat_norm, [])

                if len(docs_mesma_cat) > 1:
                    docs_ordenados = self._resolver_empate(docs_mesma_cat)
                    if doc != docs_ordenados[0]:
                        continue

                if cat_norm not in categorias_usadas:
                    secundarios.append(SelectedDocument(
                        classificacao=doc,
                        role=DocumentRole.SECONDARY,
                        prioridade=score,
                        razao=f"Categoria '{doc.categoria_nome}' é secundária para {tipo_peca}"
                    ))
                    categorias_usadas.add(cat_norm)

        # Ordena secundários por prioridade
        secundarios.sort(key=lambda d: d.prioridade)

        # IMPORTANTE: Inclui TODOS os documentos restantes como secundários
        # (não exclui nenhum, pois toda informação pode ser útil)
        for doc in classificacoes:
            cat_norm = doc.categoria_nome.lower()

            # Pula se já está em primários ou secundários
            if cat_norm in categorias_usadas:
                continue

            # Adiciona como secundário com prioridade baixa
            secundarios.append(SelectedDocument(
                classificacao=doc,
                role=DocumentRole.SECONDARY,
                prioridade=500,  # Prioridade baixa, mas incluído
                razao=f"Documento incluído para contexto adicional"
            ))
            categorias_usadas.add(cat_norm)

        # Lista de excluídos fica vazia (não excluímos mais nenhum documento)
        excluidos: List[SelectedDocument] = []

        # Se não encontrou primários, usa o documento com maior confiança
        if not primarios and classificacoes:
            melhor = max(classificacoes, key=lambda d: d.confianca)
            primarios.append(SelectedDocument(
                classificacao=melhor,
                role=DocumentRole.PRIMARY,
                prioridade=0,
                razao="Selecionado por maior confiança (nenhum primário configurado)"
            ))

            # Remove dos excluídos se estava lá
            excluidos = [e for e in excluidos if e.classificacao != melhor]

        # Monta razão geral
        razao = config.get("descricao", f"Seleção para {tipo_peca}")
        razao += f" | {len(primarios)} primário(s), {len(secundarios)} secundário(s)"

        return SelectionResult(
            tipo_peca=tipo_peca,
            documentos_primarios=primarios,
            documentos_secundarios=secundarios,
            documentos_excluidos=excluidos,
            razao_geral=razao
        )

    def selecionar_automatico(
        self,
        classificacoes: List[DocumentClassification]
    ) -> SelectionResult:
        """
        Seleciona documentos automaticamente quando tipo de peça não é definido.

        Infere o tipo de peça com base nos documentos disponíveis.

        Returns:
            SelectionResult com tipo de peça inferido
        """
        # Conta categorias
        contagem = {}
        for doc in classificacoes:
            cat = doc.categoria_nome.lower()
            contagem[cat] = contagem.get(cat, 0) + 1

        # Infere tipo de peça baseado nas categorias presentes
        tipo_inferido = "contestacao"  # Default

        # Heurística simples: se tem mais decisões/sentenças, provavelmente é recurso
        if contagem.get("sentencas", 0) > 0 or contagem.get("decisoes", 0) > 0:
            if contagem.get("recursos", 0) > 0:
                tipo_inferido = "contrarrazoes"
            else:
                tipo_inferido = "recurso_apelacao"
        elif contagem.get("peticoes", 0) > 0 or contagem.get("peticao_inicial", 0) > 0:
            tipo_inferido = "contestacao"

        logger.info(f"[Selector] Tipo inferido: {tipo_inferido}")

        return self.selecionar_documentos(classificacoes, tipo_inferido)
