# sistemas/prestacao_contas/identificador_peticoes.py
"""
Identificador de Petição de Prestação de Contas

Utiliza estratégia em 2 níveis:
1. Regex (rápido) - Busca padrões conhecidos de prestação de contas
2. LLM (quando regex inconclusivo) - Usa modelo pequeno para classificar

Autor: LAB/PGE-MS
"""

import re
import logging
from dataclasses import dataclass
from typing import Optional, List, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


# =====================================================
# PADRÕES REGEX PARA IDENTIFICAÇÃO
# =====================================================

# Padrões fortes que indicam prestação de contas
PADROES_PRESTACAO_FORTE = [
    r"presta[çc][aã]o\s+de\s+contas?",
    r"comprova[çc][aã]o\s+d[eo]s?\s+gasto",
    r"comprova[çc][aã]o\s+d[ao]?\s+utiliza[çc][aã]o",
    r"comprova[çc][aã]o\s+d[ao]?\s+aquisi[çc][aã]o",
    r"prestar\s+contas?\s+d[ao]",
    r"notas?\s+fiscais?\s+em\s+anexo",
    r"comprovo\s+a\s+aquisi[çc][aã]o",
    r"demonstra[çc][aã]o\s+d[eo]s?\s+gasto",
]

# Padrões médios que podem indicar prestação de contas
PADROES_PRESTACAO_MEDIO = [
    r"notas?\s+fiscais?",
    r"comprovantes?\s+de\s+pagamento",
    r"comprovantes?\s+de\s+aquisi[çc][aã]o",
    r"medica[çcm]ento\s+(adquirido|comprado|utilizado)",
    r"valor\s+(bloqueado|levantado|utilizado)",
    r"tratamento\s+(realizado|efetuado)",
    r"recibo[s]?\s+d[aeo]",
    r"cup[oa][mn]\s+fiscal",
]

# Padrões que indicam que NÃO é prestação de contas
PADROES_NEGATIVO = [
    r"peti[çc][aã]o\s+inicial",
    r"tutela\s+(de\s+urg[êe]ncia|antecipada)",
    r"requerer?\s+(a\s+)?tutela",
    r"indefere",
    r"mandado\s+de\s+cita[çc][aã]o",
    r"contesta[çc][aã]o",
    r"replica",
    r"recurso",
    r"apela[çc][aã]o",
    r"agravo",
    r"embargo",
]


@dataclass
class ResultadoIdentificacao:
    """Resultado da identificação de petição"""
    e_prestacao_contas: bool
    metodo: str  # 'regex_forte', 'regex_medio', 'llm', 'negativo'
    confianca: float  # 0.0 a 1.0
    padroes_encontrados: List[str] = None
    explicacao: Optional[str] = None

    def __post_init__(self):
        if self.padroes_encontrados is None:
            self.padroes_encontrados = []


class IdentificadorPeticoes:
    """
    Identificador de petições de prestação de contas.
    Usa estratégia em 2 níveis: regex primeiro, LLM se inconclusivo.
    """

    def __init__(
        self,
        usar_llm: bool = True,
        modelo_llm: str = "gemini-2.0-flash-lite",
        temperatura_llm: float = 0.1
    ):
        """
        Args:
            usar_llm: Se True, usa LLM quando regex for inconclusivo
            modelo_llm: Modelo de IA a usar (configurável via admin)
            temperatura_llm: Temperatura da IA (configurável via admin)
        """
        self.usar_llm = usar_llm
        self.modelo_llm = modelo_llm
        self.temperatura_llm = temperatura_llm
        self._padroes_forte = [re.compile(p, re.IGNORECASE) for p in PADROES_PRESTACAO_FORTE]
        self._padroes_medio = [re.compile(p, re.IGNORECASE) for p in PADROES_PRESTACAO_MEDIO]
        self._padroes_negativo = [re.compile(p, re.IGNORECASE) for p in PADROES_NEGATIVO]

    def identificar(self, texto: str) -> ResultadoIdentificacao:
        """
        Identifica se o texto é uma petição de prestação de contas.

        Args:
            texto: Texto da petição

        Returns:
            ResultadoIdentificacao
        """
        if not texto or len(texto.strip()) < 50:
            return ResultadoIdentificacao(
                e_prestacao_contas=False,
                metodo="vazio",
                confianca=1.0,
                explicacao="Texto muito curto ou vazio"
            )

        # Limita o texto para análise (primeiras 5000 caracteres geralmente são suficientes)
        texto_analise = texto[:5000].lower()

        # Etapa 1: Verifica padrões negativos
        resultado_negativo = self._verificar_padroes_negativos(texto_analise)
        if resultado_negativo.e_prestacao_contas == False and resultado_negativo.confianca > 0.8:
            return resultado_negativo

        # Etapa 2: Verifica padrões fortes
        resultado_forte = self._verificar_padroes_fortes(texto_analise)
        if resultado_forte.confianca > 0.7:
            return resultado_forte

        # Etapa 3: Verifica padrões médios
        resultado_medio = self._verificar_padroes_medios(texto_analise)
        if resultado_medio.confianca > 0.6:
            return resultado_medio

        # Etapa 4: Se inconclusivo e LLM habilitado, usa LLM
        if self.usar_llm and resultado_medio.confianca < 0.5:
            return self._identificar_com_llm(texto)

        # Retorna resultado médio se não usar LLM
        return resultado_medio

    def _verificar_padroes_negativos(self, texto: str) -> ResultadoIdentificacao:
        """Verifica se há padrões que indicam que NÃO é prestação de contas"""
        matches = []
        for padrao in self._padroes_negativo:
            if padrao.search(texto):
                matches.append(padrao.pattern)

        if len(matches) >= 2:
            return ResultadoIdentificacao(
                e_prestacao_contas=False,
                metodo="negativo",
                confianca=0.9,
                padroes_encontrados=matches,
                explicacao=f"Encontrados {len(matches)} padrões negativos"
            )
        elif len(matches) == 1:
            return ResultadoIdentificacao(
                e_prestacao_contas=False,
                metodo="negativo",
                confianca=0.6,
                padroes_encontrados=matches,
                explicacao="Encontrado padrão negativo"
            )

        return ResultadoIdentificacao(
            e_prestacao_contas=False,
            metodo="negativo",
            confianca=0.0
        )

    def _verificar_padroes_fortes(self, texto: str) -> ResultadoIdentificacao:
        """Verifica padrões fortes de prestação de contas"""
        matches = []
        for padrao in self._padroes_forte:
            match = padrao.search(texto)
            if match:
                matches.append(match.group())

        if matches:
            confianca = min(0.95, 0.7 + (len(matches) * 0.1))
            return ResultadoIdentificacao(
                e_prestacao_contas=True,
                metodo="regex_forte",
                confianca=confianca,
                padroes_encontrados=matches,
                explicacao=f"Encontrados {len(matches)} padrões fortes de prestação de contas"
            )

        return ResultadoIdentificacao(
            e_prestacao_contas=False,
            metodo="regex_forte",
            confianca=0.0
        )

    def _verificar_padroes_medios(self, texto: str) -> ResultadoIdentificacao:
        """Verifica padrões médios de prestação de contas"""
        matches = []
        for padrao in self._padroes_medio:
            match = padrao.search(texto)
            if match:
                matches.append(match.group())

        if len(matches) >= 3:
            return ResultadoIdentificacao(
                e_prestacao_contas=True,
                metodo="regex_medio",
                confianca=0.75,
                padroes_encontrados=matches,
                explicacao=f"Encontrados {len(matches)} padrões médios de prestação de contas"
            )
        elif len(matches) >= 2:
            return ResultadoIdentificacao(
                e_prestacao_contas=True,
                metodo="regex_medio",
                confianca=0.55,
                padroes_encontrados=matches,
                explicacao=f"Encontrados {len(matches)} padrões médios"
            )
        elif len(matches) == 1:
            return ResultadoIdentificacao(
                e_prestacao_contas=False,
                metodo="regex_medio",
                confianca=0.3,
                padroes_encontrados=matches,
                explicacao="Apenas 1 padrão médio encontrado"
            )

        return ResultadoIdentificacao(
            e_prestacao_contas=False,
            metodo="regex_medio",
            confianca=0.2,
            explicacao="Nenhum padrão de prestação de contas encontrado"
        )

    async def _identificar_com_llm(self, texto: str) -> ResultadoIdentificacao:
        """
        Usa LLM para identificar se é prestação de contas.
        Usa modelo e temperatura configurados via admin/prompts-config.
        """
        try:
            from services.gemini_service import GeminiService

            # Limita texto para não estourar contexto
            texto_truncado = texto[:3000]

            prompt = f"""Analise o texto abaixo e determine se é uma PETIÇÃO DE PRESTAÇÃO DE CONTAS em processo judicial de medicamentos.

Uma petição de prestação de contas tipicamente:
- Informa que o autor comprou o medicamento determinado judicialmente
- Apresenta notas fiscais ou recibos como comprovação
- Demonstra como o dinheiro bloqueado/levantado foi utilizado
- Solicita arquivamento ou devolução de saldo excedente

IMPORTANTE: NÃO é prestação de contas se for:
- Petição inicial pedindo medicamento
- Tutela de urgência
- Contestação ou réplica
- Recurso ou agravo
- Manifestação sobre outra questão

TEXTO:
{texto_truncado}

Responda APENAS com:
SIM - se for claramente uma prestação de contas
NAO - se não for prestação de contas
INCERTO - se não for possível determinar com certeza"""

            service = GeminiService()
            resposta_obj = await service.generate(
                prompt=prompt,
                model=self.modelo_llm,
                temperature=self.temperatura_llm,
            )

            # Extrai conteúdo do GeminiResponse
            if not resposta_obj.success:
                raise Exception(resposta_obj.error or "Erro na chamada da IA")

            resposta_limpa = resposta_obj.content.strip().upper()

            if resposta_limpa.startswith("SIM"):
                return ResultadoIdentificacao(
                    e_prestacao_contas=True,
                    metodo="llm",
                    confianca=0.85,
                    explicacao="LLM identificou como prestação de contas"
                )
            elif resposta_limpa.startswith("NAO") or resposta_limpa.startswith("NÃO"):
                return ResultadoIdentificacao(
                    e_prestacao_contas=False,
                    metodo="llm",
                    confianca=0.85,
                    explicacao="LLM identificou como NÃO sendo prestação de contas"
                )
            else:
                return ResultadoIdentificacao(
                    e_prestacao_contas=False,
                    metodo="llm",
                    confianca=0.4,
                    explicacao="LLM não conseguiu determinar com certeza"
                )

        except Exception as e:
            logger.error(f"Erro ao usar LLM para identificação: {e}")
            return ResultadoIdentificacao(
                e_prestacao_contas=False,
                metodo="llm_erro",
                confianca=0.0,
                explicacao=f"Erro ao usar LLM: {str(e)}"
            )

    def identificar_sync(self, texto: str) -> ResultadoIdentificacao:
        """
        Versão síncrona que não usa LLM.
        Útil quando não se quer overhead de chamada async.
        """
        self.usar_llm = False
        return self.identificar(texto)


async def identificar_peticao_prestacao(texto: str, usar_llm: bool = True) -> ResultadoIdentificacao:
    """
    Função de conveniência para identificar petição de prestação de contas.

    Args:
        texto: Texto da petição
        usar_llm: Se True, usa LLM quando regex for inconclusivo

    Returns:
        ResultadoIdentificacao
    """
    identificador = IdentificadorPeticoes(usar_llm=usar_llm)
    return identificador.identificar(texto)


def identificar_peticao_prestacao_sync(texto: str) -> ResultadoIdentificacao:
    """
    Versão síncrona (sem LLM) para identificar petição.

    Args:
        texto: Texto da petição

    Returns:
        ResultadoIdentificacao
    """
    identificador = IdentificadorPeticoes(usar_llm=False)
    return identificador.identificar_sync(texto)
