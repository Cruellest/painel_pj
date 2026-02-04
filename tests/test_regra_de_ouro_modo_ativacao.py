"""
Testes OBRIGATÓRIOS para a REGRA DE OURO do modo de ativação.

INVARIANTE DO SISTEMA:
Se existe QUALQUER regra determinística associada a um módulo,
o módulo DEVE operar em modo 'deterministic', INDEPENDENTE do valor salvo
no campo modo_ativacao.

Estes testes garantem que:
1. A função resolve_activation_mode() funciona corretamente
2. O sistema corrige automaticamente modos inconsistentes
3. O caso real do bug Tema 1033 não pode mais acontecer

IMPORTANTE: Estes testes DEVEM passar para a aplicação ser deployada.
Se falharem, há uma regressão crítica no sistema.
"""

import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy.orm import Session

# Importa as funções que serão testadas
from sistemas.gerador_pecas.services_deterministic import (
    tem_regras_deterministicas,
    resolve_activation_mode,
    resolve_activation_mode_from_db,
    corrigir_modos_ativacao_inconsistentes
)


class TestTemRegrasDeterministicas:
    """Testes para a função tem_regras_deterministicas()."""

    def test_sem_regras_retorna_false(self):
        """Sem nenhuma regra, deve retornar False."""
        resultado = tem_regras_deterministicas()
        assert resultado is False

    def test_com_regra_primaria_retorna_true(self):
        """Com regra primária, deve retornar True."""
        regra = {"type": "condition", "variable": "teste", "operator": "equals", "value": True}
        resultado = tem_regras_deterministicas(regra_primaria=regra)
        assert resultado is True

    def test_com_regra_secundaria_sem_fallback_retorna_false(self):
        """Regra secundária SEM fallback habilitado NÃO conta."""
        regra = {"type": "condition", "variable": "teste", "operator": "equals", "value": True}
        resultado = tem_regras_deterministicas(
            regra_secundaria=regra,
            fallback_habilitado=False
        )
        assert resultado is False

    def test_com_regra_secundaria_com_fallback_retorna_true(self):
        """Regra secundária COM fallback habilitado CONTA."""
        regra = {"type": "condition", "variable": "teste", "operator": "equals", "value": True}
        resultado = tem_regras_deterministicas(
            regra_secundaria=regra,
            fallback_habilitado=True
        )
        assert resultado is True

    def test_com_regra_tipo_peca_retorna_true(self):
        """Regra por tipo de peça deve retornar True."""
        regras = [{"regra_deterministica": {"type": "or", "conditions": []}}]
        resultado = tem_regras_deterministicas(regras_tipo_peca=regras)
        assert resultado is True

    def test_regra_vazia_nao_conta(self):
        """Regra vazia (sem 'type') não deve contar."""
        resultado = tem_regras_deterministicas(regra_primaria={})
        assert resultado is False

    def test_regra_none_nao_conta(self):
        """Regra None não deve contar."""
        resultado = tem_regras_deterministicas(regra_primaria=None)
        assert resultado is False

    def test_regra_or_complexa(self):
        """Regra OR complexa deve ser reconhecida."""
        regra = {
            "type": "or",
            "conditions": [
                {"type": "condition", "variable": "var1", "operator": "equals", "value": True},
                {"type": "condition", "variable": "var2", "operator": "equals", "value": True}
            ]
        }
        resultado = tem_regras_deterministicas(regra_primaria=regra)
        assert resultado is True


class TestResolveActivationMode:
    """Testes para a função resolve_activation_mode() - FONTE ÚNICA DE VERDADE."""

    def test_sem_regras_respeita_valor_salvo(self):
        """Sem regras, deve respeitar o valor salvo."""
        modo = resolve_activation_mode(modo_ativacao_salvo="llm", log_correcao=False)
        assert modo == "llm"

    def test_sem_regras_default_llm(self):
        """Sem regras e sem valor, default é 'llm'."""
        modo = resolve_activation_mode(modo_ativacao_salvo=None, log_correcao=False)
        assert modo == "llm"

    def test_com_regra_primaria_forca_deterministic(self):
        """Com regra primária, DEVE forçar 'deterministic'."""
        regra = {"type": "condition", "variable": "teste", "operator": "equals", "value": True}
        modo = resolve_activation_mode(
            modo_ativacao_salvo="llm",  # Valor "errado" salvo
            regra_primaria=regra,
            log_correcao=False
        )
        assert modo == "deterministic"

    def test_ignora_valor_salvo_quando_ha_regra(self):
        """CRÍTICO: Deve ignorar valor salvo quando há regra."""
        regra = {"type": "or", "conditions": []}
        modo = resolve_activation_mode(
            modo_ativacao_salvo="llm",  # Valor salvo incorretamente como 'llm'
            regra_primaria=regra,
            log_correcao=False
        )
        assert modo == "deterministic"

    def test_com_regra_secundaria_e_fallback(self):
        """Com regra secundária E fallback, deve forçar 'deterministic'."""
        regra = {"type": "condition", "variable": "teste", "operator": "equals", "value": True}
        modo = resolve_activation_mode(
            modo_ativacao_salvo="llm",
            regra_secundaria=regra,
            fallback_habilitado=True,
            log_correcao=False
        )
        assert modo == "deterministic"

    def test_com_regra_tipo_peca(self):
        """Com regra por tipo de peça, deve forçar 'deterministic'."""
        regras = [{"regra_deterministica": {"type": "or", "conditions": []}}]
        modo = resolve_activation_mode(
            modo_ativacao_salvo="llm",
            regras_tipo_peca=regras,
            log_correcao=False
        )
        assert modo == "deterministic"

    def test_remocao_regras_permite_llm(self):
        """Ao remover todas as regras, pode voltar para 'llm'."""
        # Simula situação onde regras foram removidas
        modo = resolve_activation_mode(
            modo_ativacao_salvo="llm",
            regra_primaria=None,
            regra_secundaria=None,
            fallback_habilitado=False,
            regras_tipo_peca=None,
            log_correcao=False
        )
        assert modo == "llm"


class TestCasoRealTema1033:
    """
    Testes baseados no bug real do Tema 1033 (STF).

    O bug original:
    - Módulo tinha regra determinística configurada
    - Campo modo_ativacao estava como 'llm'
    - Sistema não ativava o módulo quando deveria

    Estes testes garantem que este bug NUNCA mais aconteça.
    """

    def test_tema_1033_cenario_original_bug(self):
        """
        Reproduz o cenário exato do bug original.

        Módulo: evt_tema_1033 (Reembolso a Agente Privado - Tema 1.033)
        modo_ativacao salvo: 'llm' (INCORRETO!)
        Regra: OR com múltiplas condições
        """
        regra_tema_1033 = {
            "type": "or",
            "conditions": [
                {"type": "condition", "variable": "peticao_inicial_pedido_cirurgia", "operator": "equals", "value": True},
                {
                    "type": "or",
                    "conditions": [
                        {"type": "condition", "variable": "decisoes_afastamento_tema_1033_stf", "operator": "equals", "value": True},
                        {"type": "condition", "variable": "sentenca_afastamento_1033_stf", "operator": "equals", "value": True}
                    ]
                }
            ]
        }

        # O modo estava salvo como 'llm' (bug!)
        modo_resolvido = resolve_activation_mode(
            modo_ativacao_salvo="llm",
            regra_primaria=regra_tema_1033,
            log_correcao=False
        )

        # A função DEVE corrigir para 'deterministic'
        assert modo_resolvido == "deterministic", (
            "REGRESSÃO CRÍTICA: Bug do Tema 1033 pode acontecer novamente! "
            "O sistema deveria forçar 'deterministic' quando há regra."
        )

    def test_tema_1033_com_dados_processo(self):
        """
        Verifica que com os dados do processo, o módulo seria ativado.
        """
        # Dados do processo 08703941520258120001
        dados = {
            "peticao_inicial_pedido_cirurgia": True,
            "decisoes_afastamento_tema_1033_stf": False,
            "sentenca_afastamento_1033_stf": False
        }

        regra = {
            "type": "or",
            "conditions": [
                {"type": "condition", "variable": "peticao_inicial_pedido_cirurgia", "operator": "equals", "value": True},
                {"type": "condition", "variable": "decisoes_afastamento_tema_1033_stf", "operator": "equals", "value": True}
            ]
        }

        # O modo deve ser resolvido como 'deterministic'
        modo = resolve_activation_mode(
            modo_ativacao_salvo="llm",
            regra_primaria=regra,
            log_correcao=False
        )
        assert modo == "deterministic"

        # A regra deveria avaliar como True
        from sistemas.gerador_pecas.services_deterministic import DeterministicRuleEvaluator
        avaliador = DeterministicRuleEvaluator()
        resultado = avaliador.avaliar(regra, dados)
        assert resultado is True, (
            "REGRESSÃO: O módulo não seria ativado mesmo com peticao_inicial_pedido_cirurgia=True"
        )


class TestCorrigirModosInconsistentes:
    """Testes para a função de correção em lote."""

    @pytest.fixture
    def mock_db(self):
        """Mock da sessão do banco."""
        return MagicMock(spec=Session)

    def test_modulo_inconsistente_e_corrigido(self, mock_db):
        """Módulo com regra e modo='llm' deve ser corrigido."""
        # Mock do módulo
        mock_modulo = MagicMock()
        mock_modulo.id = 53
        mock_modulo.nome = "evt_tema_1033"
        mock_modulo.modo_ativacao = "llm"  # Inconsistente!
        mock_modulo.regra_deterministica = {"type": "or", "conditions": []}
        mock_modulo.regra_deterministica_secundaria = None
        mock_modulo.fallback_habilitado = False

        mock_db.query.return_value.all.return_value = [mock_modulo]
        mock_db.query.return_value.filter.return_value.all.return_value = []  # Sem regras tipo peça

        with patch('sistemas.gerador_pecas.services_deterministic.logger'):
            resultado = corrigir_modos_ativacao_inconsistentes(mock_db, commit=False)

        assert resultado["corrigidos"] >= 1, "Deveria ter corrigido o módulo inconsistente"

    def test_modulo_consistente_nao_e_alterado(self, mock_db):
        """Módulo com regra e modo='deterministic' não deve ser alterado."""
        mock_modulo = MagicMock()
        mock_modulo.id = 1
        mock_modulo.nome = "modulo_correto"
        mock_modulo.modo_ativacao = "deterministic"  # Correto!
        mock_modulo.regra_deterministica = {"type": "condition", "variable": "x", "operator": "equals", "value": True}
        mock_modulo.regra_deterministica_secundaria = None
        mock_modulo.fallback_habilitado = False

        mock_db.query.return_value.all.return_value = [mock_modulo]
        mock_db.query.return_value.filter.return_value.all.return_value = []

        with patch('sistemas.gerador_pecas.services_deterministic.logger'):
            resultado = corrigir_modos_ativacao_inconsistentes(mock_db, commit=False)

        assert resultado["corrigidos"] == 0, "Módulo consistente não deveria ser alterado"


class TestInvariantesSistema:
    """
    Testes de invariantes do sistema.

    Estes testes verificam propriedades que SEMPRE devem ser verdadeiras,
    independente do estado dos dados.
    """

    def test_regra_implica_deterministic(self):
        """INVARIANTE: Se há regra, modo DEVE ser 'deterministic'."""
        # Gera várias combinações de regras
        regras_validas = [
            {"type": "condition", "variable": "x", "operator": "equals", "value": True},
            {"type": "and", "conditions": [{"type": "condition", "variable": "x", "operator": "equals", "value": True}]},
            {"type": "or", "conditions": [{"type": "condition", "variable": "x", "operator": "equals", "value": True}]},
            {"type": "not", "conditions": [{"type": "condition", "variable": "x", "operator": "equals", "value": True}]},
        ]

        modos_salvos = ["llm", "deterministic", None, "", "invalido"]

        for regra in regras_validas:
            for modo_salvo in modos_salvos:
                modo_resolvido = resolve_activation_mode(
                    modo_ativacao_salvo=modo_salvo,
                    regra_primaria=regra,
                    log_correcao=False
                )
                assert modo_resolvido == "deterministic", (
                    f"INVARIANTE VIOLADO: regra={regra}, modo_salvo={modo_salvo}, "
                    f"modo_resolvido={modo_resolvido}"
                )

    def test_sem_regra_permite_llm(self):
        """INVARIANTE: Sem regra, 'llm' deve ser permitido."""
        modo = resolve_activation_mode(
            modo_ativacao_salvo="llm",
            regra_primaria=None,
            regra_secundaria=None,
            fallback_habilitado=False,
            regras_tipo_peca=None,
            log_correcao=False
        )
        assert modo == "llm"

    def test_funcao_e_idempotente(self):
        """INVARIANTE: Chamar a função múltiplas vezes deve ter o mesmo resultado."""
        regra = {"type": "condition", "variable": "x", "operator": "equals", "value": True}

        resultado1 = resolve_activation_mode("llm", regra_primaria=regra, log_correcao=False)
        resultado2 = resolve_activation_mode(resultado1, regra_primaria=regra, log_correcao=False)
        resultado3 = resolve_activation_mode(resultado2, regra_primaria=regra, log_correcao=False)

        assert resultado1 == resultado2 == resultado3 == "deterministic"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
