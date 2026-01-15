# sistemas/gerador_pecas/services_source_resolver.py
"""
Serviço centralizado para resolução de fontes especiais de documentos.

Define lógicas especiais para identificar documentos-fonte em casos onde
códigos de documento não são suficientes (ex: Petição Inicial).

Uso:
    resolver = SourceResolver()

    # Resolver fonte especial
    doc = resolver.resolve("peticao_inicial", documentos)

    # Listar fontes disponíveis
    fontes = resolver.get_available_sources()
"""

from typing import List, Optional, Dict, Any, Callable
from datetime import datetime
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class DocumentoInfo:
    """Informações de um documento para resolução de fonte."""
    id: str
    codigo: int
    data: Optional[datetime]
    descricao: Optional[str] = None
    ordem: int = 0  # Ordem cronológica no processo


@dataclass
class SourceResolutionResult:
    """Resultado da resolução de fonte especial."""
    sucesso: bool
    documento_id: Optional[str] = None
    documento_info: Optional[DocumentoInfo] = None
    motivo: Optional[str] = None
    regra_aplicada: Optional[str] = None
    candidatos_avaliados: int = 0


@dataclass
class SpecialSourceDefinition:
    """Definição de uma fonte especial."""
    key: str
    nome: str
    descricao: str
    codigos_validos: List[int]
    resolver: Callable[[List[DocumentoInfo]], SourceResolutionResult]


class SourceResolver:
    """
    Resolvedor centralizado de fontes especiais de documentos.

    Fontes especiais disponíveis:
    - peticao_inicial: Primeiro documento do processo com código 9500 ou 500

    Extensível para adicionar novas fontes especiais no futuro.
    """

    # Códigos de petição (9500 = Petição, 500 = Petição Inicial)
    CODIGOS_PETICAO = [9500, 500, 510]

    def __init__(self):
        self._sources: Dict[str, SpecialSourceDefinition] = {}
        self._register_default_sources()

    def _register_default_sources(self):
        """Registra as fontes especiais padrão do sistema."""

        # Petição Inicial
        self.register_source(SpecialSourceDefinition(
            key="peticao_inicial",
            nome="Petição Inicial",
            descricao="Primeiro documento do processo com código 9500 ou 500. "
                      "Identifica a petição inicial mesmo quando há outras petições intermediárias com o mesmo código.",
            codigos_validos=self.CODIGOS_PETICAO,
            resolver=self._resolve_peticao_inicial
        ))

    def register_source(self, source: SpecialSourceDefinition):
        """Registra uma nova fonte especial."""
        self._sources[source.key] = source
        logger.info(f"Fonte especial registrada: {source.key} - {source.nome}")

    def get_available_sources(self) -> List[Dict[str, Any]]:
        """Retorna lista de fontes especiais disponíveis."""
        return [
            {
                "key": source.key,
                "nome": source.nome,
                "descricao": source.descricao,
                "codigos_validos": source.codigos_validos
            }
            for source in self._sources.values()
        ]

    def get_source_info(self, key: str) -> Optional[Dict[str, Any]]:
        """Retorna informações de uma fonte especial específica."""
        source = self._sources.get(key)
        if not source:
            return None
        return {
            "key": source.key,
            "nome": source.nome,
            "descricao": source.descricao,
            "codigos_validos": source.codigos_validos
        }

    def is_valid_source(self, key: str) -> bool:
        """Verifica se uma chave de fonte especial é válida."""
        return key in self._sources

    def resolve(
        self,
        source_type: str,
        documentos: List[DocumentoInfo]
    ) -> SourceResolutionResult:
        """
        Resolve uma fonte especial para uma lista de documentos.

        Args:
            source_type: Tipo da fonte especial (ex: "peticao_inicial")
            documentos: Lista de documentos do processo (deve estar ordenada cronologicamente)

        Returns:
            SourceResolutionResult com o documento encontrado ou motivo da falha
        """
        source = self._sources.get(source_type)

        if not source:
            return SourceResolutionResult(
                sucesso=False,
                motivo=f"Fonte especial '{source_type}' não reconhecida",
                candidatos_avaliados=0
            )

        if not documentos:
            return SourceResolutionResult(
                sucesso=False,
                motivo="Nenhum documento fornecido para análise",
                regra_aplicada=source.key,
                candidatos_avaliados=0
            )

        try:
            result = source.resolver(documentos)
            result.regra_aplicada = source.key
            return result
        except Exception as e:
            logger.error(f"Erro ao resolver fonte especial {source_type}: {e}")
            return SourceResolutionResult(
                sucesso=False,
                motivo=f"Erro interno: {str(e)}",
                regra_aplicada=source.key,
                candidatos_avaliados=len(documentos)
            )

    def resolve_from_raw_docs(
        self,
        source_type: str,
        documentos_raw: List[Dict[str, Any]],
        campo_id: str = "id",
        campo_codigo: str = "tipo_documento",
        campo_data: str = "data",
        campo_descricao: str = "descricao"
    ) -> SourceResolutionResult:
        """
        Resolve fonte especial a partir de uma lista de dicts (dados brutos).

        Conveniência para quando os documentos vêm em formato dict.

        Args:
            source_type: Tipo da fonte especial
            documentos_raw: Lista de dicts com dados dos documentos
            campo_id: Nome do campo que contém o ID
            campo_codigo: Nome do campo que contém o código do documento
            campo_data: Nome do campo que contém a data
            campo_descricao: Nome do campo que contém a descrição

        Returns:
            SourceResolutionResult
        """
        docs_info = []

        for i, doc in enumerate(documentos_raw):
            doc_id = doc.get(campo_id, str(i))
            codigo_raw = doc.get(campo_codigo)

            # Tenta converter código para int
            try:
                codigo = int(codigo_raw) if codigo_raw else 0
            except (ValueError, TypeError):
                codigo = 0

            # Parse da data
            data_raw = doc.get(campo_data)
            data = None
            if isinstance(data_raw, datetime):
                data = data_raw
            elif isinstance(data_raw, str) and data_raw:
                try:
                    # Tenta vários formatos comuns
                    for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
                        try:
                            data = datetime.strptime(data_raw[:19], fmt)
                            break
                        except ValueError:
                            continue
                except Exception:
                    pass

            docs_info.append(DocumentoInfo(
                id=str(doc_id),
                codigo=codigo,
                data=data,
                descricao=doc.get(campo_descricao),
                ordem=i
            ))

        return self.resolve(source_type, docs_info)

    # ==========================================
    # Resolvedores de Fontes Especiais
    # ==========================================

    def _resolve_peticao_inicial(
        self,
        documentos: List[DocumentoInfo]
    ) -> SourceResolutionResult:
        """
        Resolve a petição inicial do processo.

        Regra: Primeiro documento cronológico com código 9500 ou 500.

        Prioridade:
        1. Documentos são ordenados por data (mais antigo primeiro)
        2. Se não houver data, usa a ordem original (assume já ordenado)
        3. Retorna o primeiro documento que tenha código 9500 ou 500
        """
        # Filtra apenas documentos com códigos de petição
        candidatos = [
            doc for doc in documentos
            if doc.codigo in self.CODIGOS_PETICAO
        ]

        if not candidatos:
            return SourceResolutionResult(
                sucesso=False,
                motivo=f"Nenhum documento com código {self.CODIGOS_PETICAO} encontrado no processo",
                candidatos_avaliados=len(documentos)
            )

        # Ordena por data (mais antigo primeiro), usando ordem como fallback
        def sort_key(doc: DocumentoInfo):
            if doc.data:
                return (0, doc.data, doc.ordem)
            return (1, datetime.max, doc.ordem)  # Docs sem data vão por ordem

        candidatos_ordenados = sorted(candidatos, key=sort_key)

        # Pega o primeiro (mais antigo)
        primeiro = candidatos_ordenados[0]

        logger.info(
            f"Petição inicial identificada: doc_id={primeiro.id}, "
            f"codigo={primeiro.codigo}, data={primeiro.data}, "
            f"de {len(candidatos)} candidatos"
        )

        return SourceResolutionResult(
            sucesso=True,
            documento_id=primeiro.id,
            documento_info=primeiro,
            motivo=f"Primeiro documento cronológico com código {primeiro.codigo}",
            candidatos_avaliados=len(documentos)
        )


# Instância global para uso conveniente
_resolver_instance: Optional[SourceResolver] = None


def get_source_resolver() -> SourceResolver:
    """Retorna a instância global do resolvedor de fontes."""
    global _resolver_instance
    if _resolver_instance is None:
        _resolver_instance = SourceResolver()
    return _resolver_instance


def resolve_special_source(
    source_type: str,
    documentos: List[DocumentoInfo]
) -> SourceResolutionResult:
    """
    Função de conveniência para resolver fonte especial.

    Args:
        source_type: Tipo da fonte especial (ex: "peticao_inicial")
        documentos: Lista de DocumentoInfo

    Returns:
        SourceResolutionResult
    """
    return get_source_resolver().resolve(source_type, documentos)


def resolve_special_source_from_dicts(
    source_type: str,
    documentos: List[Dict[str, Any]],
    **kwargs
) -> SourceResolutionResult:
    """
    Função de conveniência para resolver fonte especial a partir de dicts.

    Args:
        source_type: Tipo da fonte especial
        documentos: Lista de dicts com dados dos documentos
        **kwargs: Mapeamento de campos (campo_id, campo_codigo, etc.)

    Returns:
        SourceResolutionResult
    """
    return get_source_resolver().resolve_from_raw_docs(source_type, documentos, **kwargs)


def get_available_special_sources() -> List[Dict[str, Any]]:
    """Retorna lista de fontes especiais disponíveis."""
    return get_source_resolver().get_available_sources()


def is_valid_special_source(source_type: str) -> bool:
    """Verifica se uma fonte especial é válida."""
    return get_source_resolver().is_valid_source(source_type)
