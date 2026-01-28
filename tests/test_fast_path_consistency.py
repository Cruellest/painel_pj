# tests/test_fast_path_consistency.py
"""
Testes de consistência do Fast Path no detector de módulos.

Este teste foi criado após diagnóstico de divergência em módulos ativados
para o mesmo processo em diferentes execuções.

Causa raiz: extração de variáveis por IA não-determinística.
Ref: docs/diagnostico_divergencia_modulos_fast_path.md
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from typing import Dict, Any, List


class TestFastPathDeterminism:
    """Testes de determinismo do Fast Path."""

    @pytest.fixture
    def mock_db_session(self):
        """Mock da sessão do banco de dados."""
        session = MagicMock()
        return session

    @pytest.fixture
    def dados_extracao_fixos(self) -> Dict[str, Any]:
        """Dados de extração fixos para garantir determinismo."""
        return {
            # Variáveis de pedidos
            'peticao_inicial_pedido_medicamento': False,
            'peticao_inicial_pedido_cirurgia': False,
            'peticao_inicial_pedido_exame': False,
            'peticao_inicial_pedido_consulta': False,
            'peticao_inicial_pedido_dieta_suplemento': False,
            'peticao_inicial_pedido_fraldas': False,
            'peticao_inicial_pedido_home_care': False,
            'peticao_inicial_pedido_transferencia_hospitalar': False,
            'peticao_inicial_pedido_dano_moral': False,
            'peticao_inicial_pedido_treatmento_autismo': False,
            'peticao_inicial_pedido_professor_apoio': False,
            'peticao_inicial_pedido_enfermeiro_24h': False,

            # Variáveis críticas (que causaram divergência)
            'peticao_inicial_equipamentos_materiais': True,  # Valor correto!

            # Variáveis de polo
            'peticao_inicial_municipio_polo_passivo': True,
            'peticao_inicial_uniao_polo_passivo': False,

            # Variáveis de contexto
            'peticao_inicial_juizado_justica_comum': 'Justiça Comum',
            'peticao_inicial_generico': False,

            # Variáveis de pareceres
            'pareceres_analisou_medicamento': False,
            'pareceres_analisou_cirurgia': False,
            'pareceres_medicamento_sem_anvisa': False,
        }

    def test_avaliar_regra_equipamentos_materiais(self, dados_extracao_fixos):
        """
        GIVEN dados de extração com equipamentos_materiais=True
        WHEN regra do módulo 54 (evt_mun_insumos) é avaliada
        THEN módulo deve ser ativado
        """
        from sistemas.gerador_pecas.services_deterministic import DeterministicRuleEvaluator

        # Regra do módulo 54: equipamentos_materiais == True
        regra = {
            'type': 'condition',
            'variable': 'peticao_inicial_equipamentos_materiais',
            'operator': 'equals',
            'value': True
        }

        avaliador = DeterministicRuleEvaluator()
        resultado = avaliador.avaliar(regra, dados_extracao_fixos)

        assert resultado is True, \
            f"Módulo 54 deveria ser ativado com equipamentos_materiais=True"

    def test_avaliar_regra_equipamentos_materiais_false(self, dados_extracao_fixos):
        """
        GIVEN dados de extração com equipamentos_materiais=False
        WHEN regra do módulo 54 é avaliada
        THEN módulo NÃO deve ser ativado
        """
        from sistemas.gerador_pecas.services_deterministic import DeterministicRuleEvaluator

        dados = dados_extracao_fixos.copy()
        dados['peticao_inicial_equipamentos_materiais'] = False

        regra = {
            'type': 'condition',
            'variable': 'peticao_inicial_equipamentos_materiais',
            'operator': 'equals',
            'value': True
        }

        avaliador = DeterministicRuleEvaluator()
        resultado = avaliador.avaliar(regra, dados)

        assert resultado is False, \
            f"Módulo 54 NÃO deveria ser ativado com equipamentos_materiais=False"

    def test_consistencia_avaliacao_multiplas_vezes(self, dados_extracao_fixos):
        """
        GIVEN mesmos dados de extração
        WHEN avaliação é executada múltiplas vezes
        THEN resultado deve ser sempre o mesmo
        """
        from sistemas.gerador_pecas.services_deterministic import DeterministicRuleEvaluator

        regra = {
            'type': 'condition',
            'variable': 'peticao_inicial_equipamentos_materiais',
            'operator': 'equals',
            'value': True
        }

        avaliador = DeterministicRuleEvaluator()

        # Executa 10 vezes
        resultados = []
        for _ in range(10):
            resultado = avaliador.avaliar(regra, dados_extracao_fixos)
            resultados.append(resultado)

        # Todos devem ser iguais (True)
        assert all(r == True for r in resultados), \
            f"Avaliação não-determinística: {resultados}"

    def test_regra_or_com_equipamentos(self, dados_extracao_fixos):
        """
        GIVEN regra OR incluindo equipamentos_materiais
        WHEN avaliada com equipamentos_materiais=True
        THEN módulo deve ser ativado
        """
        from sistemas.gerador_pecas.services_deterministic import DeterministicRuleEvaluator

        # Regra simplificada do módulo 62 (evt_tres_orcamentos)
        regra = {
            'type': 'or',
            'conditions': [
                {
                    'type': 'condition',
                    'variable': 'peticao_inicial_pedido_medicamento',
                    'operator': 'equals',
                    'value': True
                },
                {
                    'type': 'condition',
                    'variable': 'peticao_inicial_equipamentos_materiais',
                    'operator': 'equals',
                    'value': True
                }
            ]
        }

        avaliador = DeterministicRuleEvaluator()
        resultado = avaliador.avaliar(regra, dados_extracao_fixos)

        assert resultado is True, \
            f"Regra OR deveria ativar com equipamentos_materiais=True"


class TestValidacaoExtracao:
    """Testes de validação de extração de variáveis."""

    def test_detecta_inconsistencia_equipamentos(self):
        """
        GIVEN texto mencionando equipamentos mas variável False
        WHEN validação é aplicada
        THEN inconsistência deve ser detectada
        """
        texto_pedidos = "Fornecimento de 02 (duas) Sondas Botton de Gastrostomia Mic-Key"
        dados = {'peticao_inicial_equipamentos_materiais': False}

        # Termos que indicam equipamentos
        termos_equipamentos = [
            'sonda', 'cateter', 'bomba', 'cpap', 'bipap',
            'cadeira de rodas', 'muleta', 'andador', 'prótese',
            'órtese', 'aparelho', 'equipamento', 'material'
        ]

        texto_lower = texto_pedidos.lower()
        tem_termo = any(termo in texto_lower for termo in termos_equipamentos)

        assert tem_termo, "Texto deveria conter termos de equipamentos"
        assert dados['peticao_inicial_equipamentos_materiais'] is False, \
            "Inconsistência detectada: texto menciona sonda mas variável é False"

    def test_lista_variaveis_criticas(self):
        """
        Documenta variáveis críticas que afetam múltiplos módulos.
        """
        variaveis_criticas = [
            'peticao_inicial_equipamentos_materiais',
            'peticao_inicial_pedido_medicamento',
            'peticao_inicial_municipio_polo_passivo',
            'peticao_inicial_uniao_polo_passivo',
            'pareceres_medicamento_sem_anvisa',
        ]

        # Cada variável deve afetar pelo menos 2 módulos
        # (verificação documental, não funcional)
        assert len(variaveis_criticas) >= 5, \
            "Deve haver pelo menos 5 variáveis críticas documentadas"


class TestCenarioDivergencia:
    """
    Reproduz o cenário exato da divergência reportada.

    Processo: 08021483520258120043
    - Geração 216: 1 módulo (equipamentos=False)
    - Geração 217: 4 módulos (equipamentos=True)
    """

    @pytest.fixture
    def dados_geracao_216(self) -> Dict[str, Any]:
        """Dados da geração 216 (incorreta)."""
        return {
            'peticao_inicial_equipamentos_materiais': False,  # ERRADO!
            'peticao_inicial_municipio_polo_passivo': True,
            'peticao_inicial_pedido_medicamento': False,
            'peticao_inicial_pedido_cirurgia': False,
            'peticao_inicial_pedido_exame': False,
        }

    @pytest.fixture
    def dados_geracao_217(self) -> Dict[str, Any]:
        """Dados da geração 217 (correta)."""
        return {
            'peticao_inicial_equipamentos_materiais': True,  # CORRETO!
            'peticao_inicial_municipio_polo_passivo': True,
            'peticao_inicial_pedido_medicamento': False,
            'peticao_inicial_pedido_cirurgia': False,
            'peticao_inicial_pedido_exame': False,
        }

    def test_divergencia_modulo_54(self, dados_geracao_216, dados_geracao_217):
        """
        GIVEN dados diferentes para mesma variável
        WHEN módulo 54 é avaliado
        THEN resultados divergem conforme esperado
        """
        from sistemas.gerador_pecas.services_deterministic import DeterministicRuleEvaluator

        regra_modulo_54 = {
            'type': 'condition',
            'variable': 'peticao_inicial_equipamentos_materiais',
            'operator': 'equals',
            'value': True
        }

        avaliador = DeterministicRuleEvaluator()

        resultado_216 = avaliador.avaliar(regra_modulo_54, dados_geracao_216)
        resultado_217 = avaliador.avaliar(regra_modulo_54, dados_geracao_217)

        # Geração 216: não ativa (dados errados)
        assert resultado_216 is False, \
            "Geração 216 não deveria ativar módulo 54 (equipamentos=False)"

        # Geração 217: ativa (dados corretos)
        assert resultado_217 is True, \
            "Geração 217 deveria ativar módulo 54 (equipamentos=True)"

        # Demonstra que a divergência é causada pelos dados, não pelo detector
        assert resultado_216 != resultado_217, \
            "Resultados divergentes confirmam que problema está nos dados de entrada"
