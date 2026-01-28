# sistemas/gerador_pecas/services_extraction_validator.py
"""
Validador de variáveis extraídas por IA.

Este módulo implementa validação semântica para detectar e corrigir
inconsistências óbvias na extração de variáveis dos documentos.

Criado após diagnóstico de divergência em módulos ativados:
- Problema: mesmos documentos → variáveis diferentes em cada execução
- Causa: extração por IA não-determinística (temperatura > 0)
- Solução: validação pós-extração para casos óbvios

Ref: docs/diagnostico_divergencia_modulos_fast_path.md
"""

import logging
import re
from typing import Dict, Any, List, Tuple, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# TERMOS INDICADORES POR VARIÁVEL
# =============================================================================

# Termos que indicam responsabilização PESSOAL de agentes públicos
# (não confundir com responsabilização genérica do ente)
TERMOS_RESPONSABILIZACAO_PESSOAL = [
    'secretário', 'secretaria municipal', 'secretaria estadual',
    'prefeito', 'governador', 'gestor', 'responsável',
    'agente público', 'servidor público', 'autoridade',
    'pessoa física', 'cpf',
    'título de crime', 'ato de improbidade',
]

# Termos que indicam responsabilização genérica (NÃO pessoal)
TERMOS_RESPONSABILIZACAO_GENERICA = [
    'estado', 'município', 'união', 'ente', 'fazenda pública',
    'poder público', 'administração pública',
    'bloqueio de verbas', 'sequestro de verbas', 'penhora',
]

# Termos que indicam equipamentos/materiais médicos
TERMOS_EQUIPAMENTOS = [
    'sonda', 'cateter', 'bomba de infusão', 'cpap', 'bipap',
    'cadeira de rodas', 'muleta', 'andador', 'prótese', 'órtese',
    'aparelho auditivo', 'equipamento', 'material', 'insumo',
    'oxigênio', 'concentrador', 'nebulizador', 'aspirador',
    'cama hospitalar', 'colchão', 'almofada', 'bolsa de colostomia',
    'fralda geriátrica',  # Quando não é pedido específico de fraldas
]

# Termos que indicam medicamentos
TERMOS_MEDICAMENTOS = [
    'medicamento', 'remédio', 'comprimido', 'cápsula', 'ampola',
    'injeção', 'insulina', 'canabidiol', 'cbd', 'quimioterapia',
    'quimioterápico', 'imunobiológico', 'biológico',
]

# Termos que indicam cirurgia
TERMOS_CIRURGIA = [
    'cirurgia', 'procedimento cirúrgico', 'operação', 'intervenção',
    'transplante', 'implante', 'artroscopia', 'endoscopia',
]

# Termos que indicam exames
TERMOS_EXAMES = [
    'exame', 'ressonância', 'tomografia', 'ultrassom', 'raio-x',
    'mamografia', 'colonoscopia', 'endoscopia', 'biópsia',
    'pet-scan', 'cintilografia',
]


# =============================================================================
# VALIDADOR PRINCIPAL
# =============================================================================

class ExtractionValidator:
    """
    Valida e corrige inconsistências na extração de variáveis.

    Uso:
        validator = ExtractionValidator()
        dados_corrigidos, alertas = validator.validar(
            dados_extracao,
            texto_pedidos
        )
    """

    def __init__(self, auto_corrigir: bool = True, log_alertas: bool = True):
        """
        Args:
            auto_corrigir: Se True, corrige automaticamente inconsistências
            log_alertas: Se True, loga alertas de inconsistências
        """
        self.auto_corrigir = auto_corrigir
        self.log_alertas = log_alertas

    def validar(
        self,
        dados: Dict[str, Any],
        texto_pedidos: Optional[str] = None,
        texto_completo: Optional[str] = None
    ) -> Tuple[Dict[str, Any], List[str]]:
        """
        Valida dados de extração e corrige inconsistências.

        Args:
            dados: Dicionário com variáveis extraídas
            texto_pedidos: Texto dos pedidos da petição (opcional)
            texto_completo: Texto completo dos documentos (opcional)

        Returns:
            Tupla (dados_corrigidos, lista_alertas)
        """
        dados_resultado = dados.copy()
        alertas = []

        # Usa texto_pedidos se disponível, senão tenta extrair de dados
        texto = texto_pedidos or dados.get('peticao_inicial_pedidos', '')
        if texto_completo:
            texto = f"{texto} {texto_completo}"

        texto_lower = texto.lower() if texto else ""

        # Validação: equipamentos_materiais
        alerta = self._validar_equipamentos(dados_resultado, texto_lower)
        if alerta:
            alertas.append(alerta)

        # Validação: medicamentos
        alerta = self._validar_medicamentos(dados_resultado, texto_lower)
        if alerta:
            alertas.append(alerta)

        # Validação: cirurgia
        alerta = self._validar_cirurgia(dados_resultado, texto_lower)
        if alerta:
            alertas.append(alerta)

        # Validação: exames
        alerta = self._validar_exames(dados_resultado, texto_lower)
        if alerta:
            alertas.append(alerta)

        # Validação: responsabilização pessoal de agente
        alerta = self._validar_responsabilizacao_pessoal(dados_resultado, texto_lower)
        if alerta:
            alertas.append(alerta)

        # Log consolidado
        if alertas and self.log_alertas:
            logger.warning(
                f"[VALIDAÇÃO EXTRAÇÃO] {len(alertas)} inconsistências encontradas: "
                f"{alertas}"
            )

        return dados_resultado, alertas

    def _validar_equipamentos(
        self,
        dados: Dict[str, Any],
        texto_lower: str
    ) -> Optional[str]:
        """Valida variável de equipamentos/materiais."""
        var = 'peticao_inicial_equipamentos_materiais'
        valor_atual = dados.get(var)

        # Verifica se texto menciona termos de equipamentos
        termo_encontrado = self._encontrar_termo(texto_lower, TERMOS_EQUIPAMENTOS)

        if termo_encontrado and valor_atual is False:
            alerta = (
                f"{var}: False mas texto menciona '{termo_encontrado}' "
                f"-> corrigido para True"
            )
            if self.auto_corrigir:
                dados[var] = True
            return alerta

        return None

    def _validar_medicamentos(
        self,
        dados: Dict[str, Any],
        texto_lower: str
    ) -> Optional[str]:
        """Valida variável de medicamentos."""
        var = 'peticao_inicial_pedido_medicamento'
        valor_atual = dados.get(var)

        termo_encontrado = self._encontrar_termo(texto_lower, TERMOS_MEDICAMENTOS)

        if termo_encontrado and valor_atual is False:
            alerta = (
                f"{var}: False mas texto menciona '{termo_encontrado}' "
                f"-> corrigido para True"
            )
            if self.auto_corrigir:
                dados[var] = True
            return alerta

        return None

    def _validar_cirurgia(
        self,
        dados: Dict[str, Any],
        texto_lower: str
    ) -> Optional[str]:
        """Valida variável de cirurgia."""
        var = 'peticao_inicial_pedido_cirurgia'
        valor_atual = dados.get(var)

        termo_encontrado = self._encontrar_termo(texto_lower, TERMOS_CIRURGIA)

        if termo_encontrado and valor_atual is False:
            alerta = (
                f"{var}: False mas texto menciona '{termo_encontrado}' "
                f"-> corrigido para True"
            )
            if self.auto_corrigir:
                dados[var] = True
            return alerta

        return None

    def _validar_exames(
        self,
        dados: Dict[str, Any],
        texto_lower: str
    ) -> Optional[str]:
        """Valida variável de exames."""
        var = 'peticao_inicial_pedido_exame'
        valor_atual = dados.get(var)

        termo_encontrado = self._encontrar_termo(texto_lower, TERMOS_EXAMES)

        if termo_encontrado and valor_atual is False:
            alerta = (
                f"{var}: False mas texto menciona '{termo_encontrado}' "
                f"-> corrigido para True"
            )
            if self.auto_corrigir:
                dados[var] = True
            return alerta

        return None

    def _validar_responsabilizacao_pessoal(
        self,
        dados: Dict[str, Any],
        texto_lower: str
    ) -> Optional[str]:
        """
        Valida variável de responsabilização pessoal de agente.

        Responsabilização PESSOAL requer:
        1. Menção explícita a agente/cargo (prefeito, secretário, governador)
        2. NÃO apenas "responsabilização" genérica do ente público

        Casos comuns de FALSE POSITIVE:
        - "sob pena de bloqueio de verbas e responsabilização" → NÃO é pessoal
        - "responsabilização do ente público" → NÃO é pessoal
        - "responsabilização do Estado" → NÃO é pessoal

        Casos TRUE POSITIVE:
        - "responsabilização pessoal do prefeito" → é pessoal
        - "sob pena de responsabilização do secretário" → é pessoal
        - "agente público será responsabilizado" → é pessoal
        """
        var = 'decisoes_responsabilizacao_pessoal_agente'
        valor_atual = dados.get(var)

        # Se não está True, não precisa validar
        if valor_atual is not True:
            return None

        # Verifica se tem termo de responsabilização pessoal
        termo_pessoal = self._encontrar_termo(texto_lower, TERMOS_RESPONSABILIZACAO_PESSOAL)

        # Verifica se tem apenas responsabilização genérica
        termo_generico = self._encontrar_termo(texto_lower, TERMOS_RESPONSABILIZACAO_GENERICA)

        # Se não tem termo pessoal MAS tem genérico, é falso positivo
        if not termo_pessoal and termo_generico:
            alerta = (
                f"{var}: True mas texto só menciona responsabilização genérica "
                f"('{termo_generico}'), sem citar agente público específico "
                f"-> corrigido para False"
            )
            if self.auto_corrigir:
                dados[var] = False
            return alerta

        # Se não tem nenhum termo de responsabilização, é falso positivo
        if not termo_pessoal and 'responsabiliza' in texto_lower:
            alerta = (
                f"{var}: True mas texto não cita agente público específico "
                f"(prefeito, secretário, etc.) -> corrigido para False"
            )
            if self.auto_corrigir:
                dados[var] = False
            return alerta

        return None

    def _encontrar_termo(self, texto: str, termos: List[str]) -> Optional[str]:
        """
        Encontra primeiro termo presente no texto.

        Returns:
            Termo encontrado ou None
        """
        for termo in termos:
            if termo in texto:
                return termo
        return None


# =============================================================================
# FUNÇÃO UTILITÁRIA PARA USO DIRETO
# =============================================================================

def validar_extracao(
    dados: Dict[str, Any],
    texto_pedidos: Optional[str] = None,
    auto_corrigir: bool = True
) -> Dict[str, Any]:
    """
    Função utilitária para validar extração.

    Args:
        dados: Dicionário com variáveis extraídas
        texto_pedidos: Texto dos pedidos da petição
        auto_corrigir: Se deve corrigir automaticamente

    Returns:
        Dados validados (e opcionalmente corrigidos)
    """
    validator = ExtractionValidator(auto_corrigir=auto_corrigir)
    dados_resultado, _ = validator.validar(dados, texto_pedidos)
    return dados_resultado


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    'ExtractionValidator',
    'validar_extracao',
    'TERMOS_EQUIPAMENTOS',
    'TERMOS_MEDICAMENTOS',
    'TERMOS_CIRURGIA',
    'TERMOS_EXAMES',
    'TERMOS_RESPONSABILIZACAO_PESSOAL',
    'TERMOS_RESPONSABILIZACAO_GENERICA',
]
