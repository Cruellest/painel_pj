# sistemas/gerador_pecas/services_segundo_grau.py
"""
Serviço de seleção determinística de documentos para processos de 2º grau (competencia=999).

Este serviço implementa uma lógica de seleção otimizada que reduz drasticamente
a quantidade de PDFs carregados em processos de 2º grau, selecionando apenas
os documentos mais relevantes de cada categoria.

Regras de seleção:
- Parecer (NAT): Último documento apenas
- Petição: Últimas N (configurável, default: 10)
- Recurso: Últimas N (configurável, default: 10)
- Despacho: Últimos 3 (fixo)
- Acórdão: TODOS
- Sentença: TODOS
"""

from typing import List, Dict, Set, Optional
from sqlalchemy.orm import Session

from sistemas.gerador_pecas.models_config_pecas import CategoriaDocumento
from admin.models import ConfiguracaoIA


# Código de competência que identifica processos de 2º grau
COMPETENCIA_SEGUNDO_GRAU = "999"

# Limites fixos (não configuráveis)
LIMITE_DESPACHO = 3
LIMITE_PARECER = 1  # Apenas o último parecer NAT

# Defaults para limites configuráveis
DEFAULT_LIMITE_PETICOES = 10
DEFAULT_LIMITE_RECURSOS = 10


def is_modo_segundo_grau(competencia: Optional[str]) -> bool:
    """
    Verifica se o processo está no modo 2º grau (competencia=999).

    Args:
        competencia: Código de competência extraído do XML do processo

    Returns:
        True se competencia == "999", False caso contrário
    """
    return competencia == COMPETENCIA_SEGUNDO_GRAU


def _get_config_limite(db: Session, chave: str, default: int) -> int:
    """
    Obtém valor de configuração de limite do banco de dados.

    Args:
        db: Sessão do banco de dados
        chave: Chave da configuração (ex: "competencia_999_last_peticoes_limit")
        default: Valor padrão se não encontrar configuração

    Returns:
        Valor inteiro do limite (entre 1 e 50)
    """
    config = db.query(ConfiguracaoIA).filter(
        ConfiguracaoIA.sistema == "gerador_pecas",
        ConfiguracaoIA.chave == chave
    ).first()

    if config and config.valor:
        try:
            valor = int(config.valor)
            # Limita entre 1 e 50
            return max(1, min(50, valor))
        except (ValueError, TypeError):
            pass

    return default


def get_codigos_por_categoria(db: Session) -> Dict[str, Set[int]]:
    """
    Obtém mapeamento de categorias para códigos de documento do banco.

    Args:
        db: Sessão do banco de dados

    Returns:
        Dict mapeando nome da categoria para conjunto de códigos.
        Exemplo: {"parecer": {8451, 9636}, "peticao": {500, 510, 9500}, ...}
    """
    categorias = db.query(CategoriaDocumento).filter(
        CategoriaDocumento.ativo == True
    ).all()

    resultado = {}
    for cat in categorias:
        nome_lower = cat.nome.lower()
        codigos = set(cat.get_codigos())
        resultado[nome_lower] = codigos

    return resultado


def _selecionar_ultimos_n(documentos: List, codigos: Set[int], limite: int) -> List:
    """
    Seleciona os últimos N documentos que correspondem aos códigos especificados.

    Assume que os documentos já estão ordenados cronologicamente (mais antigo primeiro).

    Args:
        documentos: Lista de DocumentoTJMS ordenada cronologicamente
        codigos: Conjunto de códigos de documento a filtrar
        limite: Número máximo de documentos a retornar

    Returns:
        Lista com os últimos N documentos correspondentes (mais recentes)
    """
    # Filtra documentos que correspondem aos códigos
    docs_correspondentes = []
    for doc in documentos:
        if doc.tipo_documento:
            try:
                codigo = int(doc.tipo_documento)
                if codigo in codigos:
                    docs_correspondentes.append(doc)
            except (ValueError, TypeError):
                continue

    # Pega os últimos N (mais recentes)
    if len(docs_correspondentes) <= limite:
        return docs_correspondentes

    return docs_correspondentes[-limite:]


def _selecionar_todos(documentos: List, codigos: Set[int]) -> List:
    """
    Seleciona TODOS os documentos que correspondem aos códigos especificados.

    Args:
        documentos: Lista de DocumentoTJMS
        codigos: Conjunto de códigos de documento a filtrar

    Returns:
        Lista com todos os documentos correspondentes
    """
    resultado = []
    for doc in documentos:
        if doc.tipo_documento:
            try:
                codigo = int(doc.tipo_documento)
                if codigo in codigos:
                    resultado.append(doc)
            except (ValueError, TypeError):
                continue

    return resultado


def selecionar_documentos_segundo_grau(
    documentos: List,
    db: Session,
    codigos_por_categoria: Optional[Dict[str, Set[int]]] = None
) -> List:
    """
    Aplica a seleção determinística de documentos para modo 2º grau.

    Esta função implementa as regras de seleção:
    - Parecer: Último apenas
    - Petição: Últimas N (configurável)
    - Recurso: Últimas N (configurável)
    - Despacho: Últimos 3
    - Acórdão: TODOS
    - Sentença: TODOS

    Args:
        documentos: Lista completa de DocumentoTJMS do processo (ordenada cronologicamente)
        db: Sessão do banco de dados
        codigos_por_categoria: Opcional, mapeamento de categorias para códigos.
                              Se não fornecido, será buscado do banco.

    Returns:
        Lista filtrada de documentos seguindo as regras de seleção
    """
    if not documentos:
        return []

    # Obtém mapeamento de códigos se não fornecido
    if codigos_por_categoria is None:
        codigos_por_categoria = get_codigos_por_categoria(db)

    # Obtém limites configuráveis
    limite_peticoes = _get_config_limite(
        db, "competencia_999_last_peticoes_limit", DEFAULT_LIMITE_PETICOES
    )
    limite_recursos = _get_config_limite(
        db, "competencia_999_last_recursos_limit", DEFAULT_LIMITE_RECURSOS
    )

    # Log dos limites
    print(f"[2º-GRAU] Limites configurados: petições={limite_peticoes}, recursos={limite_recursos}")

    # Conjunto para rastrear documentos já selecionados (evita duplicatas)
    ids_selecionados = set()
    documentos_selecionados = []

    # Contadores para log
    contagem_por_categoria = {}

    # Função auxiliar para adicionar documento sem duplicata
    def adicionar_doc(doc, categoria_nome: str):
        if doc.id not in ids_selecionados:
            ids_selecionados.add(doc.id)
            documentos_selecionados.append(doc)
            contagem_por_categoria[categoria_nome] = contagem_por_categoria.get(categoria_nome, 0) + 1

    # 1. Parecer (NAT) - Último apenas
    codigos_parecer = codigos_por_categoria.get("parecer", set())
    if codigos_parecer:
        pareceres = _selecionar_ultimos_n(documentos, codigos_parecer, LIMITE_PARECER)
        for doc in pareceres:
            adicionar_doc(doc, "parecer")

    # 2. Petição - Últimas N
    codigos_peticao = codigos_por_categoria.get("peticao", set())
    if codigos_peticao:
        peticoes = _selecionar_ultimos_n(documentos, codigos_peticao, limite_peticoes)
        for doc in peticoes:
            adicionar_doc(doc, "petição")

    # 3. Recurso - Últimas N
    # Tenta "recurso" e "recursos" (diferentes grafias possíveis)
    codigos_recurso = codigos_por_categoria.get("recurso", set()) | codigos_por_categoria.get("recursos", set())
    if codigos_recurso:
        recursos = _selecionar_ultimos_n(documentos, codigos_recurso, limite_recursos)
        for doc in recursos:
            adicionar_doc(doc, "recurso")

    # 4. Despacho - Últimos 3
    codigos_despacho = codigos_por_categoria.get("despacho", set())
    if codigos_despacho:
        despachos = _selecionar_ultimos_n(documentos, codigos_despacho, LIMITE_DESPACHO)
        for doc in despachos:
            adicionar_doc(doc, "despacho")

    # 5. Acórdão - TODOS
    codigos_acordao = codigos_por_categoria.get("acordao", set())
    if codigos_acordao:
        acordaos = _selecionar_todos(documentos, codigos_acordao)
        for doc in acordaos:
            adicionar_doc(doc, "acórdão")

    # 6. Sentença - TODOS
    codigos_sentenca = codigos_por_categoria.get("sentenca", set())
    if codigos_sentenca:
        sentencas = _selecionar_todos(documentos, codigos_sentenca)
        for doc in sentencas:
            adicionar_doc(doc, "sentença")

    # 7. Decisão - TODOS (importante para análise processual)
    codigos_decisao = codigos_por_categoria.get("decisao", set())
    if codigos_decisao:
        decisoes = _selecionar_todos(documentos, codigos_decisao)
        for doc in decisoes:
            adicionar_doc(doc, "decisão")

    # 8. Petição Inicial - Sempre incluir se disponível
    codigos_pi = codigos_por_categoria.get("peticao_inicial", set())
    if codigos_pi:
        # Pega apenas o primeiro (mais antigo) que é a petição inicial real
        for doc in documentos:
            if doc.tipo_documento:
                try:
                    codigo = int(doc.tipo_documento)
                    if codigo in codigos_pi:
                        adicionar_doc(doc, "petição_inicial")
                        break  # Só o primeiro
                except (ValueError, TypeError):
                    continue

    # Log de seleção
    contagem_str = ", ".join(f"{k}={v}" for k, v in sorted(contagem_por_categoria.items()))
    print(f"[2º-GRAU] Seleção por categoria: {contagem_str}")

    excluidos = len(documentos) - len(documentos_selecionados)
    print(f"[2º-GRAU] Documentos excluídos por limite: {excluidos}")
    print(f"[2º-GRAU] Total selecionados: {len(documentos_selecionados)} de {len(documentos)}")

    # Ordena documentos selecionados na ordem original (cronológica)
    # Cria mapa de índice original
    indice_original = {doc.id: i for i, doc in enumerate(documentos)}
    documentos_selecionados.sort(key=lambda d: indice_original.get(d.id, 0))

    return documentos_selecionados
