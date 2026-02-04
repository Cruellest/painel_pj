# sistemas/gerador_pecas/services_nat_origem.py
"""
Serviço para buscar Parecer NAT no processo de origem.

Quando um processo é um agravo (peticao_inicial_agravo=true) e não possui
Parecer NAT nos seus documentos, o sistema deve buscar o NAT no processo de origem.

Códigos NAT reconhecidos:
- 207: Parecer do CATES (Câmara Técnica em Saúde)
- 8451: Parecer NAT (principal)
- 9636: Parecer NAT (alternativo)
- 59: Nota Técnica NATJus
- 8490: Nota Técnica NATJus (alternativo)
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Set, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from sistemas.gerador_pecas.agente_tjms import DocumentoTJMS, ResultadoAnalise

# Logger específico para rastreabilidade
logger = logging.getLogger("nat_origem_resolver")


# =========================
# Códigos de documentos NAT
# =========================
CODIGOS_NAT: Set[int] = {
    207,   # Parecer do CATES - Câmara Técnica em Saúde
    8451,  # Parecer NAT (principal)
    9636,  # Parecer NAT (alternativo)
    59,    # Nota Técnica NATJus
    8490,  # Nota Técnica NATJus (alternativo)
}

# Códigos que indicam processo de agravo (fallback quando IA não extrai corretamente)
CODIGOS_INDICADORES_AGRAVO: Set[int] = {
    9516,  # Decisão Agravada - indica claramente que é um agravo
}


@dataclass
class NATOrigemResult:
    """Resultado da busca de NAT no processo de origem."""

    # Indica se a busca foi realizada
    busca_realizada: bool = False

    # Indica se NAT foi encontrado no processo atual (agravo)
    nat_encontrado_agravo: bool = False

    # Indica se NAT foi encontrado no processo de origem
    nat_encontrado_origem: bool = False

    # Documento NAT encontrado (se houver)
    documento_nat: Optional["DocumentoTJMS"] = None

    # Fonte do NAT: 'agravo', 'origem' ou None se não encontrado
    nat_source: Optional[str] = None

    # Número do processo de origem consultado
    numero_processo_origem: Optional[str] = None

    # Motivo da decisão (para logs/auditoria)
    motivo: str = ""

    # Erro ocorrido (se houver)
    erro: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário para logs/telemetria."""
        return {
            "busca_realizada": self.busca_realizada,
            "nat_encontrado_agravo": self.nat_encontrado_agravo,
            "nat_encontrado_origem": self.nat_encontrado_origem,
            "nat_source": self.nat_source,
            "numero_processo_origem": self.numero_processo_origem,
            "motivo": self.motivo,
            "erro": self.erro,
            "documento_nat_id": self.documento_nat.id if self.documento_nat else None,
        }


def verificar_agravo_por_documentos(documentos: List["DocumentoTJMS"]) -> bool:
    """
    Verifica se o processo é um agravo baseado nos tipos de documentos presentes.

    Fallback para casos onde a IA não extraiu corretamente peticao_inicial_agravo.
    A presença de "Decisão Agravada" (código 9516) indica claramente que é um agravo.

    Args:
        documentos: Lista de documentos do processo

    Returns:
        True se há indicadores de que é um agravo
    """
    for doc in documentos:
        if not doc.tipo_documento:
            continue

        try:
            codigo = int(doc.tipo_documento)
            if codigo in CODIGOS_INDICADORES_AGRAVO:
                logger.info(
                    f"[NAT-ORIGEM] Agravo detectado por documento: "
                    f"código={codigo} ({doc.descricao or 'Decisão Agravada'})"
                )
                return True
        except (ValueError, TypeError):
            continue

    return False


def verificar_nat_em_documentos(documentos: List["DocumentoTJMS"]) -> List["DocumentoTJMS"]:
    """
    Verifica se há documentos NAT em uma lista de documentos.

    Args:
        documentos: Lista de documentos a verificar

    Returns:
        Lista de documentos NAT encontrados (pode ser vazia)
    """
    docs_nat = []

    for doc in documentos:
        if not doc.tipo_documento:
            continue

        try:
            codigo = int(doc.tipo_documento)
            if codigo in CODIGOS_NAT:
                docs_nat.append(doc)
        except (ValueError, TypeError):
            continue

    return docs_nat


def selecionar_melhor_nat(docs_nat: List["DocumentoTJMS"]) -> Optional["DocumentoTJMS"]:
    """
    Seleciona o melhor NAT quando há múltiplos.

    Critério: documento mais recente por data de juntada.
    Se não houver data, retorna o último da lista (presumivelmente mais recente).

    Args:
        docs_nat: Lista de documentos NAT

    Returns:
        Melhor documento NAT ou None se lista vazia
    """
    if not docs_nat:
        return None

    if len(docs_nat) == 1:
        return docs_nat[0]

    # Ordena por data de juntada (mais recente primeiro)
    docs_ordenados = sorted(
        docs_nat,
        key=lambda d: d.data_juntada or datetime.min,
        reverse=True
    )

    # Retorna o mais recente
    return docs_ordenados[0]


def extrair_dados_peticao_inicial(resultado: "ResultadoAnalise") -> Dict[str, Any]:
    """
    Extrai dados da petição inicial do resultado de análise.

    Procura por documentos que sejam petição inicial (códigos 500, 9500)
    e tenta parsear o JSON do resumo.

    Args:
        resultado: Resultado da análise do processo

    Returns:
        Dicionário com dados extraídos da petição inicial
    """
    import json

    # Códigos de petição inicial
    CODIGOS_PETICAO_INICIAL = {500, 9500, 10}

    dados = {}

    for doc in resultado.documentos:
        if not doc.tipo_documento or not doc.resumo:
            continue

        try:
            codigo = int(doc.tipo_documento)
            if codigo not in CODIGOS_PETICAO_INICIAL:
                continue

            # Tenta parsear o resumo como JSON
            resumo_limpo = doc.resumo.strip()
            if resumo_limpo.startswith('```json'):
                resumo_limpo = resumo_limpo[7:]
            elif resumo_limpo.startswith('```'):
                resumo_limpo = resumo_limpo[3:]
            if resumo_limpo.endswith('```'):
                resumo_limpo = resumo_limpo[:-3]
            resumo_limpo = resumo_limpo.strip()

            if not resumo_limpo.startswith('{'):
                continue

            dados_doc = json.loads(resumo_limpo)
            if isinstance(dados_doc, dict):
                # Mescla dados (em caso de múltiplas petições iniciais)
                dados.update(dados_doc)

        except (ValueError, TypeError, json.JSONDecodeError):
            continue

    return dados


class NATOrigemResolver:
    """
    Resolvedor de NAT no processo de origem.

    Verifica se um agravo precisa buscar NAT no processo de origem
    e realiza a busca se necessário.
    """

    def __init__(self, agente_tjms: Any, db_session: Any = None):
        """
        Inicializa o resolver.

        Args:
            agente_tjms: Instância do AgenteTJMS para consultar processos
            db_session: Sessão do banco de dados (opcional)
        """
        self.agente = agente_tjms
        self.db_session = db_session

    async def resolver(
        self,
        resultado_agravo: "ResultadoAnalise",
        dados_peticao_inicial: Optional[Dict[str, Any]] = None
    ) -> NATOrigemResult:
        """
        Resolve a necessidade de buscar NAT no processo de origem.

        Regra de negócio:
        1. Se peticao_inicial_agravo != True -> não busca
        2. Se NAT encontrado no agravo -> não busca
        3. Se não há número do processo de origem -> não busca
        4. Busca NAT no processo de origem

        Args:
            resultado_agravo: Resultado da análise do processo de agravo
            dados_peticao_inicial: Dados extraídos da petição inicial (opcional)
                                   Se não fornecido, será extraído automaticamente

        Returns:
            NATOrigemResult com o resultado da operação
        """
        result = NATOrigemResult()

        # Extrai dados da petição inicial se não fornecidos
        if dados_peticao_inicial is None:
            dados_peticao_inicial = extrair_dados_peticao_inicial(resultado_agravo)

        # Log inicial
        logger.info(
            f"[NAT-ORIGEM] Verificando processo {resultado_agravo.numero_processo}"
        )

        # 1. Verifica se é um agravo
        is_agravo = dados_peticao_inicial.get("peticao_inicial_agravo", False)

        # Aceita True, "true", "sim", "yes" (case-insensitive)
        if isinstance(is_agravo, str):
            is_agravo = is_agravo.lower() in ("true", "sim", "yes", "1")
        elif not isinstance(is_agravo, bool):
            is_agravo = bool(is_agravo)

        # Fallback: detecta agravo pela presença de documentos indicadores
        # (ex: Decisão Agravada - código 9516)
        if not is_agravo:
            is_agravo_fallback = verificar_agravo_por_documentos(resultado_agravo.documentos)
            if is_agravo_fallback:
                logger.info(
                    f"[NAT-ORIGEM] Agravo detectado por fallback (documentos indicadores). "
                    f"peticao_inicial_agravo não estava definido."
                )
                is_agravo = True

        if not is_agravo:
            result.motivo = "peticao_inicial_agravo != true e nenhum documento indicador de agravo"
            logger.info(f"[NAT-ORIGEM] Não é agravo, busca não necessária")
            return result

        # 2. Verifica se NAT existe no agravo
        docs_nat_agravo = verificar_nat_em_documentos(resultado_agravo.documentos)

        if docs_nat_agravo:
            result.nat_encontrado_agravo = True
            result.nat_source = "agravo"
            result.documento_nat = selecionar_melhor_nat(docs_nat_agravo)
            result.motivo = f"NAT encontrado no agravo (código {result.documento_nat.tipo_documento})"

            logger.info(
                f"[NAT-ORIGEM] NAT encontrado no agravo: "
                f"doc_id={result.documento_nat.id}, "
                f"codigo={result.documento_nat.tipo_documento}, "
                f"nat_source=agravo"
            )
            return result

        # 3. Obtém número do processo de origem
        numero_origem = dados_peticao_inicial.get("peticao_inicial_num_origem")

        # Fallback: tenta campo 'processo_origem' também
        if not numero_origem:
            numero_origem = dados_peticao_inicial.get("processo_origem")

        # Converte número para string se necessário
        # O schema define o campo como "number", então a IA pode extrair como int/float
        if numero_origem is not None and not isinstance(numero_origem, str):
            # Converte para string e formata no padrão CNJ se necessário
            numero_str = str(int(numero_origem))  # Remove decimais se houver

            # Preenche com zeros à esquerda para ter 20 dígitos (padrão CNJ)
            # Ex: 8015048520258120013 (19 dígitos) -> 08015048520258120013 (20 dígitos)
            if len(numero_str) < 20:
                numero_str = numero_str.zfill(20)

            # Se tem 20 dígitos, formata no padrão CNJ: NNNNNNN-DD.AAAA.J.TR.OOOO
            if len(numero_str) == 20:
                numero_origem = (
                    f"{numero_str[0:7]}-{numero_str[7:9]}.{numero_str[9:13]}."
                    f"{numero_str[13:14]}.{numero_str[14:16]}.{numero_str[16:20]}"
                )
                logger.info(f"[NAT-ORIGEM] Número de origem formatado: {numero_origem}")
            else:
                numero_origem = numero_str
                logger.warning(
                    f"[NAT-ORIGEM] Número de origem com formato inesperado ({len(numero_str)} dígitos): {numero_str}"
                )

        if not numero_origem or numero_origem in ("null", "None", ""):
            result.busca_realizada = False
            result.motivo = "agravo=true, NAT não encontrado no agravo, número do processo de origem não disponível"

            logger.warning(
                f"[NAT-ORIGEM] Agravo sem NAT e sem número de origem disponível. "
                f"Processo: {resultado_agravo.numero_processo}"
            )
            return result

        result.numero_processo_origem = numero_origem
        result.busca_realizada = True

        logger.info(
            f"[NAT-ORIGEM] Iniciando busca de NAT no processo de origem: {numero_origem}"
        )

        # 4. Busca NAT no processo de origem
        try:
            docs_origem = await self._buscar_documentos_origem(numero_origem)

            if not docs_origem:
                result.motivo = f"agravo=true, NAT não encontrado no agravo, NAT não encontrado no origem ({numero_origem})"

                logger.warning(
                    f"[NAT-ORIGEM] Nenhum documento encontrado no processo de origem: {numero_origem}"
                )
                return result

            # Filtra documentos NAT
            docs_nat_origem = verificar_nat_em_documentos(docs_origem)

            if not docs_nat_origem:
                result.motivo = f"agravo=true, NAT não encontrado no agravo, NAT não encontrado no origem ({numero_origem})"

                logger.warning(
                    f"[NAT-ORIGEM] Processo de origem consultado mas NAT não encontrado. "
                    f"Total docs: {len(docs_origem)}, Origem: {numero_origem}"
                )
                return result

            # Seleciona melhor NAT e marca como documento de origem
            nat_selecionado = selecionar_melhor_nat(docs_nat_origem)
            nat_selecionado.processo_origem = True
            nat_selecionado.numero_processo = numero_origem

            result.nat_encontrado_origem = True
            result.nat_source = "origem"
            result.documento_nat = nat_selecionado
            result.motivo = (
                f"NAT encontrado no processo de origem ({numero_origem}), "
                f"código {nat_selecionado.tipo_documento}"
            )

            logger.info(
                f"[NAT-ORIGEM] NAT encontrado no processo de origem: "
                f"doc_id={nat_selecionado.id}, "
                f"codigo={nat_selecionado.tipo_documento}, "
                f"origem={numero_origem}, "
                f"nat_source=origem"
            )

            return result

        except Exception as e:
            result.erro = str(e)
            result.motivo = f"Erro ao buscar processo de origem: {str(e)}"

            logger.error(
                f"[NAT-ORIGEM] Erro ao buscar NAT no processo de origem {numero_origem}: {e}",
                exc_info=True
            )
            return result

    async def _buscar_documentos_origem(
        self,
        numero_processo_origem: str
    ) -> List["DocumentoTJMS"]:
        """
        Busca documentos do processo de origem.

        Args:
            numero_processo_origem: Número do processo de origem

        Returns:
            Lista de documentos do processo de origem
        """
        import aiohttp
        from sistemas.gerador_pecas.agente_tjms import (
            consultar_processo_async,
            extrair_documentos_xml
        )

        connector = aiohttp.TCPConnector(limit=10, limit_per_host=10)
        async with aiohttp.ClientSession(connector=connector) as session:
            # Consulta processo de origem
            xml_consulta = await consultar_processo_async(
                session,
                numero_processo_origem,
                timeout=60
            )

            # Verifica sucesso
            if '<sucesso>false</sucesso>' in xml_consulta or '<sucesso>true</sucesso>' not in xml_consulta:
                logger.warning(
                    f"[NAT-ORIGEM] Não foi possível acessar processo de origem: {numero_processo_origem}"
                )
                return []

            # Extrai documentos
            documentos = extrair_documentos_xml(xml_consulta)

            logger.info(
                f"[NAT-ORIGEM] Processo de origem {numero_processo_origem}: "
                f"{len(documentos)} documentos encontrados"
            )

            return documentos


async def processar_nat_do_processo_origem(
    agente_tjms: Any,
    resultado_agravo: "ResultadoAnalise",
    session: Any,
    dados_peticao_inicial: Optional[Dict[str, Any]] = None
) -> NATOrigemResult:
    """
    Função de alto nível para processar NAT do processo de origem.

    Esta função:
    1. Verifica se é necessário buscar NAT no processo de origem
    2. Se necessário, busca e baixa o conteúdo do NAT
    3. Processa o NAT (extrai texto/resumo)
    4. Retorna resultado com documento pronto para adicionar ao pipeline

    Args:
        agente_tjms: Instância do AgenteTJMS
        resultado_agravo: Resultado da análise do processo de agravo
        session: Sessão aiohttp para requisições
        dados_peticao_inicial: Dados extraídos da petição inicial (opcional)

    Returns:
        NATOrigemResult com documento NAT processado (se encontrado)
    """
    from sistemas.gerador_pecas.agente_tjms import baixar_documentos_async, extrair_documentos_xml

    resolver = NATOrigemResolver(agente_tjms)
    result = await resolver.resolver(resultado_agravo, dados_peticao_inicial)

    # Se não encontrou NAT no origem ou não precisa buscar, retorna
    if not result.nat_encontrado_origem or not result.documento_nat:
        return result

    # Baixa o conteúdo do NAT
    try:
        doc_nat = result.documento_nat
        numero_origem = result.numero_processo_origem

        logger.info(
            f"[NAT-ORIGEM] Baixando conteúdo do NAT: doc_id={doc_nat.id}"
        )

        xml_download = await baixar_documentos_async(
            session,
            numero_origem,
            [doc_nat.id],
            timeout=120
        )

        # Extrai conteúdo do documento
        docs_baixados = extrair_documentos_xml(xml_download)

        for doc_baixado in docs_baixados:
            if doc_baixado.id == doc_nat.id and doc_baixado.conteudo_base64:
                doc_nat.conteudo_base64 = doc_baixado.conteudo_base64
                logger.info(
                    f"[NAT-ORIGEM] Conteúdo do NAT baixado: "
                    f"doc_id={doc_nat.id}, "
                    f"tamanho_base64={len(doc_baixado.conteudo_base64)}"
                )
                break
        else:
            logger.warning(
                f"[NAT-ORIGEM] Conteúdo do NAT não encontrado no download: doc_id={doc_nat.id}"
            )
            result.erro = "Conteúdo do NAT não disponível no download"

    except Exception as e:
        logger.error(
            f"[NAT-ORIGEM] Erro ao baixar conteúdo do NAT: {e}",
            exc_info=True
        )
        result.erro = f"Erro ao baixar conteúdo: {str(e)}"

    return result


def integrar_nat_ao_resultado(
    resultado_agravo: "ResultadoAnalise",
    nat_result: NATOrigemResult
) -> bool:
    """
    Integra o NAT encontrado no processo de origem ao resultado do agravo.

    Esta função garante idempotência: se o NAT já foi adicionado, não duplica.

    Args:
        resultado_agravo: Resultado da análise do processo de agravo
        nat_result: Resultado da busca de NAT no processo de origem

    Returns:
        True se o NAT foi integrado, False caso contrário
    """
    if not nat_result.nat_encontrado_origem or not nat_result.documento_nat:
        return False

    doc_nat = nat_result.documento_nat

    # Verifica idempotência: não adiciona se já existe documento com mesmo ID
    ids_existentes = {d.id for d in resultado_agravo.documentos}

    if doc_nat.id in ids_existentes:
        logger.info(
            f"[NAT-ORIGEM] NAT já existe no resultado (idempotência): doc_id={doc_nat.id}"
        )
        return False

    # Adiciona o NAT ao resultado
    resultado_agravo.documentos.append(doc_nat)

    logger.info(
        f"[NAT-ORIGEM] NAT integrado ao resultado: "
        f"doc_id={doc_nat.id}, "
        f"processo_origem={nat_result.numero_processo_origem}, "
        f"total_docs={len(resultado_agravo.documentos)}"
    )

    return True


# =============================================================================
# Funções para fluxo de PDFs anexados
# =============================================================================

@dataclass
class NATParaPDFsResult:
    """Resultado da busca de NAT para PDFs anexados."""

    # Indica se a busca foi realizada
    busca_realizada: bool = False

    # Indica se NAT foi encontrado
    nat_encontrado: bool = False

    # Fonte do NAT: 'pdfs_anexados', 'origem' ou None
    nat_source: Optional[str] = None

    # Número do processo de origem consultado
    numero_processo_origem: Optional[str] = None

    # Resumo markdown do NAT (para adicionar ao resumo consolidado)
    resumo_markdown: Optional[str] = None

    # Dados JSON extraídos do NAT (para consolidar variáveis)
    dados_json: Optional[Dict[str, Any]] = None

    # Motivo da decisão (para logs/auditoria)
    motivo: str = ""

    # Erro ocorrido (se houver)
    erro: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário para logs/telemetria."""
        return {
            "busca_realizada": self.busca_realizada,
            "nat_encontrado": self.nat_encontrado,
            "nat_source": self.nat_source,
            "numero_processo_origem": self.numero_processo_origem,
            "motivo": self.motivo,
            "erro": self.erro,
        }


def verificar_agravo_em_dados_consolidados(dados_consolidados: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Verifica se os dados consolidados indicam que é um agravo.

    Procura por variáveis com diversos padrões de nomenclatura:
    - peticao_inicial_agravo
    - peticao_inicial_peticao_inicial_agravo
    - agravo (variante simples)

    Args:
        dados_consolidados: Dicionário com variáveis consolidadas dos PDFs

    Returns:
        Tupla (is_agravo, numero_origem) onde:
        - is_agravo: True se é agravo
        - numero_origem: Número do processo de origem (se disponível)
    """
    if not dados_consolidados:
        return False, None

    # Padrões para variável de agravo
    padroes_agravo = [
        "peticao_inicial_agravo",
        "peticao_inicial_peticao_inicial_agravo",
        "agravo",
        "is_agravo",
        "e_agravo",
    ]

    # Padrões para número de origem
    padroes_origem = [
        "peticao_inicial_num_origem",
        "peticao_inicial_peticao_inicial_num_origem",
        "processo_origem",
        "numero_origem",
        "num_origem",
    ]

    is_agravo = False
    numero_origem = None

    # Verifica se é agravo
    for padrao in padroes_agravo:
        for chave, valor in dados_consolidados.items():
            # Verifica match exato ou sufixo
            if chave == padrao or chave.endswith(f"_{padrao}"):
                if isinstance(valor, bool):
                    is_agravo = valor
                elif isinstance(valor, str):
                    is_agravo = valor.lower() in ("true", "sim", "yes", "1")
                else:
                    is_agravo = bool(valor)

                if is_agravo:
                    break
        if is_agravo:
            break

    # Busca número de origem
    for padrao in padroes_origem:
        for chave, valor in dados_consolidados.items():
            if chave == padrao or chave.endswith(f"_{padrao}"):
                if valor is not None and valor not in ("null", "None", ""):
                    # Converte número para string se necessário
                    if isinstance(valor, (int, float)):
                        numero_str = str(int(valor))
                        # Preenche com zeros à esquerda para ter 20 dígitos
                        if len(numero_str) < 20:
                            numero_str = numero_str.zfill(20)
                        # Se tem 20 dígitos, formata no padrão CNJ
                        if len(numero_str) == 20:
                            numero_origem = (
                                f"{numero_str[0:7]}-{numero_str[7:9]}.{numero_str[9:13]}."
                                f"{numero_str[13:14]}.{numero_str[14:16]}.{numero_str[16:20]}"
                            )
                        else:
                            numero_origem = numero_str
                    elif isinstance(valor, str) and valor.strip():
                        numero_origem = valor
                    break
        if numero_origem:
            break

    return is_agravo, numero_origem


def verificar_nat_em_pdfs_anexados(
    documentos_processados: List[Dict[str, Any]],
    dados_consolidados: Dict[str, Any]
) -> bool:
    """
    Verifica se há NAT entre os PDFs anexados.

    Verifica tanto pela categoria do documento quanto por variáveis extraídas
    que indicam presença de parecer NAT.

    Args:
        documentos_processados: Lista de documentos processados (metadados)
        dados_consolidados: Dados consolidados dos PDFs

    Returns:
        True se há NAT nos PDFs anexados
    """
    # 1. Verifica por categoria
    categorias_nat = [
        "parecer nat", "parecer_nat", "nat", "natjus",
        "nota técnica natjus", "nota_tecnica_natjus",
        "parecer cates", "parecer_cates", "cates"
    ]

    for doc in documentos_processados:
        categoria = doc.get("categoria", "").lower()
        if any(cat in categoria for cat in categorias_nat):
            logger.info(f"[NAT-PDFS] NAT encontrado nos PDFs por categoria: {categoria}")
            return True

    # 2. Verifica por variáveis extraídas
    # Se há variáveis típicas de parecer NAT preenchidas
    padroes_nat = [
        "parecer_nat_", "nat_", "natjus_", "cates_"
    ]

    for chave, valor in dados_consolidados.items():
        chave_lower = chave.lower()
        for padrao in padroes_nat:
            if padrao in chave_lower and valor is not None:
                # Se encontrou variável de NAT com valor, considera que há NAT
                if isinstance(valor, bool) and valor:
                    logger.info(f"[NAT-PDFS] NAT inferido por variável: {chave}={valor}")
                    return True
                elif isinstance(valor, str) and valor.strip():
                    logger.info(f"[NAT-PDFS] NAT inferido por variável: {chave}={valor[:50]}...")
                    return True

    return False


async def buscar_nat_para_pdfs_anexados(
    dados_consolidados: Dict[str, Any],
    documentos_processados: List[Dict[str, Any]],
    db_session: Any = None
) -> NATParaPDFsResult:
    """
    Busca NAT no processo de origem quando PDFs são anexados.

    Esta função é chamada no fluxo de PDFs anexados para:
    1. Verificar se os dados indicam agravo (peticao_inicial_agravo=true)
    2. Verificar se já há NAT nos PDFs anexados
    3. Se não houver, buscar NAT no processo de origem
    4. Processar o NAT e retornar em formato markdown + JSON

    Args:
        dados_consolidados: Variáveis extraídas dos PDFs
        documentos_processados: Metadados dos documentos processados
        db_session: Sessão do banco de dados (opcional)

    Returns:
        NATParaPDFsResult com resumo markdown e dados JSON do NAT
    """
    import aiohttp

    result = NATParaPDFsResult()

    # 1. Verifica se é agravo
    is_agravo, numero_origem = verificar_agravo_em_dados_consolidados(dados_consolidados)

    if not is_agravo:
        result.motivo = "PDFs anexados não indicam agravo (peticao_inicial_agravo != true)"
        logger.info(f"[NAT-PDFS] {result.motivo}")
        return result

    logger.info(f"[NAT-PDFS] PDFs indicam AGRAVO, processo de origem: {numero_origem}")

    # 2. Verifica se já há NAT nos PDFs anexados
    if verificar_nat_em_pdfs_anexados(documentos_processados, dados_consolidados):
        result.nat_encontrado = True
        result.nat_source = "pdfs_anexados"
        result.motivo = "NAT já presente nos PDFs anexados"
        logger.info(f"[NAT-PDFS] {result.motivo}")
        return result

    # 3. Verifica se temos número de origem
    if not numero_origem:
        result.motivo = "Agravo identificado, mas número do processo de origem não disponível nos PDFs"
        logger.warning(f"[NAT-PDFS] {result.motivo}")
        return result

    result.numero_processo_origem = numero_origem
    result.busca_realizada = True

    logger.info(f"[NAT-PDFS] Iniciando busca de NAT no processo de origem: {numero_origem}")

    # 4. Busca NAT no processo de origem
    try:
        from sistemas.gerador_pecas.agente_tjms import (
            consultar_processo_async,
            extrair_documentos_xml,
            baixar_documentos_async
        )

        connector = aiohttp.TCPConnector(limit=10, limit_per_host=10)
        async with aiohttp.ClientSession(connector=connector) as session:
            # Consulta processo de origem
            xml_consulta = await consultar_processo_async(
                session,
                numero_origem,
                timeout=60
            )

            if '<sucesso>false</sucesso>' in xml_consulta or '<sucesso>true</sucesso>' not in xml_consulta:
                result.erro = f"Não foi possível acessar processo de origem: {numero_origem}"
                result.motivo = result.erro
                logger.warning(f"[NAT-PDFS] {result.erro}")
                return result

            # Extrai documentos
            documentos = extrair_documentos_xml(xml_consulta)
            logger.info(f"[NAT-PDFS] Processo de origem: {len(documentos)} documentos encontrados")

            # Filtra documentos NAT
            docs_nat = verificar_nat_em_documentos(documentos)

            if not docs_nat:
                result.motivo = f"agravo=true, NAT não encontrado nos PDFs anexados, NAT não encontrado no processo de origem ({numero_origem})"
                logger.warning(f"[NAT-PDFS] {result.motivo}")
                return result

            # Seleciona melhor NAT
            nat_selecionado = selecionar_melhor_nat(docs_nat)
            logger.info(
                f"[NAT-PDFS] NAT encontrado no processo de origem: "
                f"doc_id={nat_selecionado.id}, codigo={nat_selecionado.tipo_documento}"
            )

            # Baixa conteúdo do NAT
            xml_download = await baixar_documentos_async(
                session,
                numero_origem,
                [nat_selecionado.id],
                timeout=120
            )

            docs_baixados = extrair_documentos_xml(xml_download)

            conteudo_base64 = None
            for doc_baixado in docs_baixados:
                if doc_baixado.id == nat_selecionado.id and doc_baixado.conteudo_base64:
                    conteudo_base64 = doc_baixado.conteudo_base64
                    break

            if not conteudo_base64:
                result.erro = "Conteúdo do NAT não disponível para download"
                result.motivo = result.erro
                logger.warning(f"[NAT-PDFS] {result.erro}")
                return result

            # Processa o NAT (extrai texto e JSON)
            resumo_md, dados_json = await _processar_nat_para_markdown(
                conteudo_base64,
                nat_selecionado,
                numero_origem,
                db_session
            )

            result.nat_encontrado = True
            result.nat_source = "origem"
            result.resumo_markdown = resumo_md
            result.dados_json = dados_json
            result.motivo = f"NAT encontrado no processo de origem ({numero_origem}), código {nat_selecionado.tipo_documento}"

            logger.info(
                f"[NAT-PDFS] NAT processado com sucesso: "
                f"nat_source=origem, "
                f"origem={numero_origem}, "
                f"resumo_len={len(resumo_md) if resumo_md else 0}"
            )

            return result

    except Exception as e:
        result.erro = str(e)
        result.motivo = f"Erro ao buscar NAT no processo de origem: {str(e)}"
        logger.error(f"[NAT-PDFS] {result.motivo}", exc_info=True)
        return result


async def _processar_nat_para_markdown(
    conteudo_base64: str,
    documento: "DocumentoTJMS",
    numero_origem: str,
    db_session: Any = None
) -> tuple[str, Optional[Dict[str, Any]]]:
    """
    Processa o conteúdo do NAT e retorna resumo em markdown + dados JSON.

    Args:
        conteudo_base64: Conteúdo do documento em base64
        documento: Metadados do documento NAT
        numero_origem: Número do processo de origem
        db_session: Sessão do banco de dados

    Returns:
        Tupla (resumo_markdown, dados_json)
    """
    import base64
    import fitz  # PyMuPDF

    try:
        # Decodifica PDF
        pdf_bytes = base64.b64decode(conteudo_base64)
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        # Extrai texto
        texto_paginas = []
        for page in doc:
            texto_paginas.append(page.get_text())
        doc.close()

        texto_completo = "\n".join(texto_paginas)

        # Se conseguiu extrair texto, tenta extrair JSON estruturado
        dados_json = None
        resumo_md = None

        if texto_completo and len(texto_completo.strip()) > 100:
            # Tenta extrair JSON estruturado usando o formato da categoria NAT
            if db_session:
                try:
                    from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON
                    from sistemas.gerador_pecas.extrator_resumo_json import (
                        FormatoResumo,
                        gerar_prompt_extracao_json,
                        parsear_resposta_json,
                        normalizar_json_com_schema,
                        json_para_markdown
                    )
                    from sistemas.gerador_pecas.gemini_client import chamar_gemini_async

                    # Busca categoria NAT (código 8451 ou nome similar)
                    categoria = db_session.query(CategoriaResumoJSON).filter(
                        CategoriaResumoJSON.ativo == True
                    ).filter(
                        (CategoriaResumoJSON.nome.ilike("%nat%")) |
                        (CategoriaResumoJSON.nome.ilike("%parecer%"))
                    ).first()

                    if categoria and categoria.formato_json:
                        formato = FormatoResumo(
                            categoria_id=categoria.id,
                            categoria_nome=categoria.nome,
                            formato_json=categoria.formato_json,
                            instrucoes_extracao=categoria.instrucoes_extracao,
                            is_residual=False
                        )

                        prompt = gerar_prompt_extracao_json(formato, "Parecer NAT do processo de origem", db_session)
                        prompt_final = prompt.replace("{texto_documento}", texto_completo[:30000])

                        resposta = await chamar_gemini_async(
                            prompt=prompt_final,
                            modelo="gemini-2.5-flash-lite",
                            temperature=0.1,
                            max_tokens=8000
                        )

                        json_extraido, erro = parsear_resposta_json(resposta)

                        if not erro and json_extraido:
                            dados_json = normalizar_json_com_schema(json_extraido, categoria.formato_json)
                            resumo_md = json_para_markdown(dados_json)

                            logger.info(f"[NAT-PDFS] JSON extraído do NAT com {len(dados_json)} campos")

                except Exception as e:
                    logger.warning(f"[NAT-PDFS] Erro ao extrair JSON do NAT: {e}")

            # Se não conseguiu extrair JSON, usa texto bruto
            if not resumo_md:
                # Limita texto e formata como markdown
                texto_limitado = texto_completo[:10000]
                if len(texto_completo) > 10000:
                    texto_limitado += "\n\n[... conteúdo truncado ...]"

                resumo_md = texto_limitado

        else:
            resumo_md = "[Conteúdo do NAT não pôde ser extraído - documento pode ser digitalizado/imagem]"

        # Monta markdown final com cabeçalho
        header = f"### [ORIGEM] Parecer NAT ({documento.tipo_documento})\n"
        header += f"**Processo de Origem**: {numero_origem}\n"
        header += f"**Data**: {documento.data_formatada if hasattr(documento, 'data_formatada') else 'N/A'}\n"
        header += f"**nat_source**: origem\n\n"

        resumo_final = header + resumo_md

        return resumo_final, dados_json

    except Exception as e:
        logger.error(f"[NAT-PDFS] Erro ao processar conteúdo do NAT: {e}", exc_info=True)
        return f"[Erro ao processar NAT: {str(e)}]", None
