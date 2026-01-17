# sistemas/gerador_pecas/services_source_resolver.py
"""
Serviço centralizado para resolução de fontes especiais de documentos.

Define lógicas especiais para identificar documentos-fonte em casos onde
códigos de documento não são suficientes (ex: Petição Inicial).

CONFIG-DRIVEN: Os códigos válidos para cada fonte especial são obtidos
do banco de dados (CategoriaDocumento), não de constantes hardcoded.

Uso:
    resolver = SourceResolver(db)

    # Resolver fonte especial
    doc = resolver.resolve("peticao_inicial", documentos)

    # Listar fontes disponíveis
    fontes = resolver.get_available_sources()

    # Invalidar cache (chamar após salvar config no admin)
    invalidar_cache_source_resolver()
"""

from typing import List, Optional, Dict, Any, Callable, Set
from datetime import datetime
from dataclasses import dataclass, field
import logging
import threading

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
    codigos_usados: List[int] = field(default_factory=list)  # Códigos usados na resolução


@dataclass
class SpecialSourceDefinition:
    """Definição de uma fonte especial."""
    key: str
    nome: str
    descricao: str
    categoria_nome: str  # Nome da categoria no banco (ex: "peticao_inicial")
    codigos_fallback: List[int]  # Fallback se categoria não existir
    resolver: Callable[[List[DocumentoInfo], List[int]], SourceResolutionResult]


class SourceResolver:
    """
    Resolvedor centralizado de fontes especiais de documentos.

    CONFIG-DRIVEN: Os códigos válidos são obtidos do banco de dados
    (tabela CategoriaDocumento), não de constantes hardcoded.

    Fontes especiais disponíveis:
    - peticao_inicial: Primeiro documento do processo com códigos configurados
      na categoria "peticao_inicial" do admin (/api/gerador-pecas/config/admin)

    Critério de "primeiro documento":
    - Ordenação por data_juntada (mais antiga primeiro)
    - Se não houver data, usa ordem de aparição no array (assume já ordenado)

    Extensível para adicionar novas fontes especiais no futuro.
    """

    # Códigos de fallback (usados APENAS se a categoria não existir no banco)
    CODIGOS_PETICAO_INICIAL_FALLBACK = [9500, 500]

    # Códigos de petição em geral (incluindo intermediárias) - hardcoded pois não é categoria especial
    CODIGOS_PETICAO = [9500, 500, 510]

    def __init__(self, db=None):
        """
        Inicializa o resolver.

        Args:
            db: Sessão do banco de dados (opcional, pode ser passada depois via set_db)
        """
        self._db = db
        self._sources: Dict[str, SpecialSourceDefinition] = {}
        self._codigos_cache: Dict[str, List[int]] = {}
        self._cache_lock = threading.Lock()
        self._register_default_sources()

    def set_db(self, db):
        """Define a sessão do banco de dados."""
        self._db = db

    def _register_default_sources(self):
        """Registra as fontes especiais padrão do sistema."""

        # Petição Inicial
        self.register_source(SpecialSourceDefinition(
            key="peticao_inicial",
            nome="Petição Inicial",
            descricao="Primeiro documento do processo com códigos configurados "
                      "na categoria 'peticao_inicial' do admin. "
                      "Identifica a petição inicial mesmo quando há outras petições intermediárias.",
            categoria_nome="peticao_inicial",
            codigos_fallback=self.CODIGOS_PETICAO_INICIAL_FALLBACK,
            resolver=self._resolve_peticao_inicial
        ))

    def register_source(self, source: SpecialSourceDefinition):
        """Registra uma nova fonte especial."""
        self._sources[source.key] = source
        logger.debug(f"Fonte especial registrada: {source.key} - {source.nome}")

    def _get_codigos_from_db(self, categoria_nome: str, codigos_fallback: List[int]) -> List[int]:
        """
        Obtém os códigos de uma categoria do banco de dados.

        Esta é a fonte de verdade para os códigos válidos.

        Args:
            categoria_nome: Nome da categoria (ex: "peticao_inicial")
            codigos_fallback: Códigos de fallback se categoria não existir

        Returns:
            Lista de códigos da categoria
        """
        # Verifica cache primeiro
        with self._cache_lock:
            if categoria_nome in self._codigos_cache:
                return self._codigos_cache[categoria_nome]

        # Se não tem DB, usa fallback
        if not self._db:
            logger.warning(
                f"[CONFIG-DRIVEN] DB não disponível para categoria '{categoria_nome}'. "
                f"Usando fallback: {codigos_fallback}"
            )
            return codigos_fallback

        try:
            from sistemas.gerador_pecas.models_config_pecas import CategoriaDocumento

            categoria = self._db.query(CategoriaDocumento).filter(
                CategoriaDocumento.nome == categoria_nome,
                CategoriaDocumento.ativo == True
            ).first()

            if categoria and categoria.codigos_documento:
                codigos = categoria.codigos_documento
                logger.info(
                    f"[CONFIG-DRIVEN] Códigos carregados do BD para '{categoria_nome}': {codigos}"
                )

                # Atualiza cache
                with self._cache_lock:
                    self._codigos_cache[categoria_nome] = codigos

                return codigos
            else:
                logger.warning(
                    f"[CONFIG-DRIVEN] Categoria '{categoria_nome}' não encontrada ou vazia no BD. "
                    f"Usando fallback: {codigos_fallback}"
                )
                return codigos_fallback

        except Exception as e:
            logger.error(
                f"[CONFIG-DRIVEN] Erro ao buscar categoria '{categoria_nome}': {e}. "
                f"Usando fallback: {codigos_fallback}"
            )
            return codigos_fallback

    def invalidar_cache(self, categoria_nome: Optional[str] = None):
        """
        Invalida o cache de códigos.

        IMPORTANTE: Chamar este método após salvar alterações na config do admin.

        Args:
            categoria_nome: Nome da categoria específica para invalidar, ou None para invalidar tudo
        """
        with self._cache_lock:
            if categoria_nome:
                if categoria_nome in self._codigos_cache:
                    del self._codigos_cache[categoria_nome]
                    logger.info(f"[CONFIG-DRIVEN] Cache invalidado para categoria '{categoria_nome}'")
            else:
                self._codigos_cache.clear()
                logger.info("[CONFIG-DRIVEN] Cache de todas as categorias invalidado")

    def get_codigos_validos(self, source_key: str) -> List[int]:
        """
        Retorna os códigos válidos para uma fonte especial.

        Busca do banco de dados (config-driven).

        Args:
            source_key: Chave da fonte especial (ex: "peticao_inicial")

        Returns:
            Lista de códigos válidos
        """
        source = self._sources.get(source_key)
        if not source:
            return []

        return self._get_codigos_from_db(source.categoria_nome, source.codigos_fallback)

    def get_available_sources(self) -> List[Dict[str, Any]]:
        """Retorna lista de fontes especiais disponíveis."""
        return [
            {
                "key": source.key,
                "nome": source.nome,
                "descricao": source.descricao,
                "codigos_validos": self.get_codigos_validos(source.key),
                "categoria_nome": source.categoria_nome
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
            "codigos_validos": self.get_codigos_validos(key),
            "categoria_nome": source.categoria_nome
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
            # Obtém códigos da config (banco de dados)
            codigos = self._get_codigos_from_db(source.categoria_nome, source.codigos_fallback)

            result = source.resolver(documentos, codigos)
            result.regra_aplicada = source.key
            result.codigos_usados = codigos
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
        documentos: List[DocumentoInfo],
        codigos_validos: List[int]
    ) -> SourceResolutionResult:
        """
        Resolve a petição inicial do processo.

        Regra: Primeiro documento cronológico com código ∈ codigos_validos (config-driven).

        Critério de "primeiro documento":
        1. Documentos são ordenados por data (mais antigo primeiro)
        2. Se não houver data, usa a ordem original (assume já ordenado pelo TJ-MS)
        3. Retorna o primeiro documento que tenha código na lista configurada

        Args:
            documentos: Lista de DocumentoInfo
            codigos_validos: Lista de códigos válidos (obtida da config do admin)

        Returns:
            SourceResolutionResult
        """
        # Filtra apenas documentos com códigos configurados no admin
        candidatos = [
            doc for doc in documentos
            if doc.codigo in codigos_validos
        ]

        if not candidatos:
            return SourceResolutionResult(
                sucesso=False,
                motivo=f"Nenhum documento com código {codigos_validos} encontrado no processo",
                candidatos_avaliados=len(documentos),
                codigos_usados=codigos_validos
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
            f"[CONFIG-DRIVEN] Petição inicial identificada: doc_id={primeiro.id}, "
            f"codigo={primeiro.codigo}, data={primeiro.data}, "
            f"de {len(candidatos)} candidatos. Códigos usados: {codigos_validos}"
        )

        return SourceResolutionResult(
            sucesso=True,
            documento_id=primeiro.id,
            documento_info=primeiro,
            motivo=f"Primeiro documento cronológico com código {primeiro.codigo}",
            candidatos_avaliados=len(documentos),
            codigos_usados=codigos_validos
        )


# ==========================================
# Instância Global e Funções de Conveniência
# ==========================================

# Instância global para uso conveniente
_resolver_instance: Optional[SourceResolver] = None
_instance_lock = threading.Lock()


def get_source_resolver(db=None) -> SourceResolver:
    """
    Retorna a instância global do resolvedor de fontes.

    Args:
        db: Sessão do banco de dados (opcional, mas recomendado para config-driven)

    Returns:
        SourceResolver
    """
    global _resolver_instance
    with _instance_lock:
        if _resolver_instance is None:
            _resolver_instance = SourceResolver(db)
        elif db is not None:
            _resolver_instance.set_db(db)
        return _resolver_instance


def invalidar_cache_source_resolver(categoria_nome: Optional[str] = None):
    """
    Invalida o cache do SourceResolver.

    IMPORTANTE: Chamar esta função após salvar alterações na config do admin.

    Args:
        categoria_nome: Nome da categoria específica para invalidar, ou None para invalidar tudo

    Exemplo de uso no router de config:
        @router.put("/categorias/{categoria_id}")
        async def atualizar_categoria(...):
            # ... salva categoria ...
            invalidar_cache_source_resolver(categoria.nome)
            return categoria
    """
    global _resolver_instance
    if _resolver_instance is not None:
        _resolver_instance.invalidar_cache(categoria_nome)
    logger.info(f"[CONFIG-DRIVEN] Cache do SourceResolver invalidado: {categoria_nome or 'TODOS'}")


def resolve_special_source(
    source_type: str,
    documentos: List[DocumentoInfo],
    db=None
) -> SourceResolutionResult:
    """
    Função de conveniência para resolver fonte especial.

    Args:
        source_type: Tipo da fonte especial (ex: "peticao_inicial")
        documentos: Lista de DocumentoInfo
        db: Sessão do banco de dados (opcional, mas recomendado)

    Returns:
        SourceResolutionResult
    """
    return get_source_resolver(db).resolve(source_type, documentos)


def resolve_special_source_from_dicts(
    source_type: str,
    documentos: List[Dict[str, Any]],
    db=None,
    **kwargs
) -> SourceResolutionResult:
    """
    Função de conveniência para resolver fonte especial a partir de dicts.

    Args:
        source_type: Tipo da fonte especial
        documentos: Lista de dicts com dados dos documentos
        db: Sessão do banco de dados (opcional, mas recomendado)
        **kwargs: Mapeamento de campos (campo_id, campo_codigo, etc.)

    Returns:
        SourceResolutionResult
    """
    return get_source_resolver(db).resolve_from_raw_docs(source_type, documentos, **kwargs)


def get_available_special_sources(db=None) -> List[Dict[str, Any]]:
    """Retorna lista de fontes especiais disponíveis."""
    return get_source_resolver(db).get_available_sources()


def is_valid_special_source(source_type: str) -> bool:
    """Verifica se uma fonte especial é válida."""
    return get_source_resolver().is_valid_source(source_type)
