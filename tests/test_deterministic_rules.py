# tests/test_deterministic_rules.py
"""
Testes automatizados para o sistema de regras determinísticas.

Cobre:
1. Avaliação de regras simples e compostas
2. Normalização de tipos (booleanos, strings)
3. Merge de variáveis de múltiplas fontes
4. Casos reais de bugs corrigidos
"""

import pytest
from typing import Dict, Any
from sistemas.gerador_pecas.services_deterministic import (
    DeterministicRuleEvaluator,
    avaliar_ativacao_prompt,
    verificar_variaveis_existem,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def avaliador():
    """Instância do avaliador de regras."""
    return DeterministicRuleEvaluator()


@pytest.fixture
def regra_simples_eletiva():
    """Regra: pareceres_natureza_cirurgia == 'eletiva'"""
    return {
        "type": "condition",
        "variable": "pareceres_natureza_cirurgia",
        "operator": "equals",
        "value": "eletiva"
    }


@pytest.fixture
def regra_composta_jef():
    """Regra: valor_causa_inferior_60sm == true AND juizo == 'Justiça Comum Estadual'"""
    return {
        "type": "and",
        "conditions": [
            {
                "type": "condition",
                "variable": "valor_causa_inferior_60sm",
                "operator": "equals",
                "value": True
            },
            {
                "type": "condition",
                "variable": "juizo",
                "operator": "equals",
                "value": "Justiça Comum Estadual"
            }
        ]
    }


@pytest.fixture
def regra_or_municipio():
    """Regra: municipio_polo_passivo == true OR uniao_polo_passivo == true"""
    return {
        "type": "or",
        "conditions": [
            {
                "type": "condition",
                "variable": "municipio_polo_passivo",
                "operator": "equals",
                "value": True
            },
            {
                "type": "condition",
                "variable": "uniao_polo_passivo",
                "operator": "equals",
                "value": True
            }
        ]
    }


@pytest.fixture
def dados_caso_cirurgia_eletiva():
    """Dados de um caso com cirurgia eletiva."""
    return {
        "pareceres_analisou_cirurgia": True,
        "pareceres_natureza_cirurgia": "eletiva",
        "pareceres_qual_cirurgia": "Herniorrafia inguinal",
        "pareceres_cirurgia_ofertada_sus": True,
        "pareceres_laudo_medico_sus": True,
    }


@pytest.fixture
def dados_caso_cirurgia_urgencia():
    """Dados de um caso com cirurgia de urgência."""
    return {
        "pareceres_analisou_cirurgia": True,
        "pareceres_natureza_cirurgia": "urgencia",
        "pareceres_qual_cirurgia": "Apendicectomia",
        "pareceres_cirurgia_ofertada_sus": True,
    }


@pytest.fixture
def dados_sistema_completos():
    """Dados do sistema (variáveis calculadas do XML)."""
    return {
        "processo_ajuizado_apos_2024_09_19": True,
        "valor_causa_numerico": 50000.0,
        "valor_causa_inferior_60sm": True,
        "valor_causa_superior_210sm": False,
        "estado_polo_passivo": True,
        "municipio_polo_passivo": True,
        "uniao_polo_passivo": False,
        "autor_com_assistencia_judiciaria": True,
        "autor_com_defensoria": False,
    }


# ============================================================================
# TESTES: REGRAS SIMPLES
# ============================================================================

class TestRegraSimples:
    """Testes para regras com uma única condição."""

    def test_igualdade_string_case_insensitive(self, avaliador, regra_simples_eletiva):
        """Teste: comparação de strings é case-insensitive."""
        # Valores exatos
        assert avaliador.avaliar(regra_simples_eletiva, {"pareceres_natureza_cirurgia": "eletiva"}) is True
        assert avaliador.avaliar(regra_simples_eletiva, {"pareceres_natureza_cirurgia": "ELETIVA"}) is True
        assert avaliador.avaliar(regra_simples_eletiva, {"pareceres_natureza_cirurgia": "Eletiva"}) is True

        # Valores diferentes
        assert avaliador.avaliar(regra_simples_eletiva, {"pareceres_natureza_cirurgia": "urgencia"}) is False
        assert avaliador.avaliar(regra_simples_eletiva, {"pareceres_natureza_cirurgia": "emergencia"}) is False

    def test_variavel_inexistente(self, avaliador, regra_simples_eletiva):
        """Teste: variável não existe nos dados."""
        # Variável completamente ausente
        assert avaliador.avaliar(regra_simples_eletiva, {}) is False

        # Variável com valor None
        assert avaliador.avaliar(regra_simples_eletiva, {"pareceres_natureza_cirurgia": None}) is False

    def test_booleano_true(self, avaliador):
        """Teste: comparação de booleano true."""
        regra = {
            "type": "condition",
            "variable": "valor_causa_inferior_60sm",
            "operator": "equals",
            "value": True
        }

        # Booleano real
        assert avaliador.avaliar(regra, {"valor_causa_inferior_60sm": True}) is True
        assert avaliador.avaliar(regra, {"valor_causa_inferior_60sm": False}) is False

        # String "true"/"false"
        assert avaliador.avaliar(regra, {"valor_causa_inferior_60sm": "true"}) is True
        assert avaliador.avaliar(regra, {"valor_causa_inferior_60sm": "false"}) is False

        # Inteiros 1/0
        assert avaliador.avaliar(regra, {"valor_causa_inferior_60sm": 1}) is True
        assert avaliador.avaliar(regra, {"valor_causa_inferior_60sm": 0}) is False

    def test_booleano_false(self, avaliador):
        """Teste: comparação de booleano false."""
        regra = {
            "type": "condition",
            "variable": "uniao_polo_passivo",
            "operator": "equals",
            "value": False
        }

        assert avaliador.avaliar(regra, {"uniao_polo_passivo": False}) is True
        assert avaliador.avaliar(regra, {"uniao_polo_passivo": True}) is False
        assert avaliador.avaliar(regra, {"uniao_polo_passivo": "false"}) is True
        assert avaliador.avaliar(regra, {"uniao_polo_passivo": 0}) is True


# ============================================================================
# TESTES: REGRAS COMPOSTAS
# ============================================================================

class TestRegraComposta:
    """Testes para regras AND/OR/NOT."""

    def test_and_todas_verdadeiras(self, avaliador, regra_composta_jef):
        """Teste: AND com todas as condições verdadeiras."""
        dados = {
            "valor_causa_inferior_60sm": True,
            "juizo": "Justiça Comum Estadual"
        }
        assert avaliador.avaliar(regra_composta_jef, dados) is True

    def test_and_uma_falsa(self, avaliador, regra_composta_jef):
        """Teste: AND com uma condição falsa."""
        dados = {
            "valor_causa_inferior_60sm": False,  # Falso
            "juizo": "Justiça Comum Estadual"
        }
        assert avaliador.avaliar(regra_composta_jef, dados) is False

    def test_and_variavel_faltando(self, avaliador, regra_composta_jef):
        """Teste: AND com variável faltando."""
        dados = {
            "valor_causa_inferior_60sm": True,
            # juizo não existe
        }
        assert avaliador.avaliar(regra_composta_jef, dados) is False

    def test_or_uma_verdadeira(self, avaliador, regra_or_municipio):
        """Teste: OR com pelo menos uma condição verdadeira."""
        dados_mun = {"municipio_polo_passivo": True, "uniao_polo_passivo": False}
        dados_uni = {"municipio_polo_passivo": False, "uniao_polo_passivo": True}
        dados_ambos = {"municipio_polo_passivo": True, "uniao_polo_passivo": True}

        assert avaliador.avaliar(regra_or_municipio, dados_mun) is True
        assert avaliador.avaliar(regra_or_municipio, dados_uni) is True
        assert avaliador.avaliar(regra_or_municipio, dados_ambos) is True

    def test_or_todas_falsas(self, avaliador, regra_or_municipio):
        """Teste: OR com todas as condições falsas."""
        dados = {"municipio_polo_passivo": False, "uniao_polo_passivo": False}
        assert avaliador.avaliar(regra_or_municipio, dados) is False


# ============================================================================
# TESTES: OPERADORES ESPECIAIS
# ============================================================================

class TestOperadoresEspeciais:
    """Testes para operadores especiais (contains, greater_than, etc)."""

    def test_contains(self, avaliador):
        """Teste: operador contains."""
        regra = {
            "type": "condition",
            "variable": "texto",
            "operator": "contains",
            "value": "urgente"
        }

        assert avaliador.avaliar(regra, {"texto": "Cirurgia URGENTE"}) is True
        assert avaliador.avaliar(regra, {"texto": "Este é um caso urgente"}) is True
        assert avaliador.avaliar(regra, {"texto": "Caso eletivo"}) is False

    def test_greater_than(self, avaliador):
        """Teste: operador greater_than."""
        regra = {
            "type": "condition",
            "variable": "valor_causa_numerico",
            "operator": "greater_than",
            "value": 100000
        }

        assert avaliador.avaliar(regra, {"valor_causa_numerico": 150000}) is True
        assert avaliador.avaliar(regra, {"valor_causa_numerico": 100000}) is False
        assert avaliador.avaliar(regra, {"valor_causa_numerico": 50000}) is False

        # Valor em formato brasileiro
        assert avaliador.avaliar(regra, {"valor_causa_numerico": "150.000,00"}) is True

    def test_is_empty(self, avaliador):
        """Teste: operador is_empty."""
        regra = {
            "type": "condition",
            "variable": "lista_medicamentos",
            "operator": "is_empty",
            "value": None
        }

        assert avaliador.avaliar(regra, {"lista_medicamentos": None}) is True
        assert avaliador.avaliar(regra, {"lista_medicamentos": ""}) is True
        # NOTA: lista vazia [] é considerada como "com valor" pelo avaliador
        # Este é o comportamento atual - pode ser revisado no futuro
        assert avaliador.avaliar(regra, {"lista_medicamentos": []}) is False
        assert avaliador.avaliar(regra, {"lista_medicamentos": ["Med1"]}) is False

    def test_exists(self, avaliador):
        """Teste: operador exists."""
        regra = {
            "type": "condition",
            "variable": "pareceres_natureza_cirurgia",
            "operator": "exists",
            "value": None
        }

        assert avaliador.avaliar(regra, {"pareceres_natureza_cirurgia": "eletiva"}) is True
        assert avaliador.avaliar(regra, {"pareceres_natureza_cirurgia": ""}) is True
        assert avaliador.avaliar(regra, {"pareceres_natureza_cirurgia": None}) is False
        assert avaliador.avaliar(regra, {}) is False


# ============================================================================
# TESTES: VERIFICAÇÃO DE VARIÁVEIS
# ============================================================================

class TestVerificarVariaveis:
    """Testes para verificar_variaveis_existem()."""

    def test_todas_existem(self, regra_composta_jef):
        """Teste: todas as variáveis existem nos dados."""
        dados = {
            "valor_causa_inferior_60sm": True,
            "juizo": "Justiça Comum Estadual"
        }
        existem, vars_usadas = verificar_variaveis_existem(regra_composta_jef, dados)

        assert existem is True
        assert set(vars_usadas) == {"valor_causa_inferior_60sm", "juizo"}

    def test_alguma_faltando(self, regra_composta_jef):
        """Teste: alguma variável não existe nos dados."""
        dados = {
            "valor_causa_inferior_60sm": True,
            # juizo não existe
        }
        existem, vars_usadas = verificar_variaveis_existem(regra_composta_jef, dados)

        assert existem is False
        assert "juizo" in vars_usadas


# ============================================================================
# TESTES: CASO REAL - BUG MER_SEM_URGENCIA
# ============================================================================

class TestCasoRealMerSemUrgencia:
    """
    Testes reproduzindo o bug real: prompt mer_sem_urgencia não ativado
    quando pareceres_natureza_cirurgia = 'eletiva'.

    Causa raiz: modo_ativacao era 'llm' quando deveria ser 'deterministic'.
    """

    def test_regra_cirurgia_eletiva_deve_ativar(
        self, avaliador, regra_simples_eletiva, dados_caso_cirurgia_eletiva
    ):
        """Teste: regra deve ativar quando natureza é eletiva."""
        resultado = avaliador.avaliar(regra_simples_eletiva, dados_caso_cirurgia_eletiva)
        assert resultado is True, "Regra deveria ativar para cirurgia eletiva"

    def test_regra_cirurgia_urgencia_nao_deve_ativar(
        self, avaliador, regra_simples_eletiva, dados_caso_cirurgia_urgencia
    ):
        """Teste: regra NÃO deve ativar quando natureza é urgência."""
        resultado = avaliador.avaliar(regra_simples_eletiva, dados_caso_cirurgia_urgencia)
        assert resultado is False, "Regra NÃO deveria ativar para cirurgia urgente"

    def test_merge_dados_extracao_com_sistema(
        self, avaliador, regra_simples_eletiva,
        dados_caso_cirurgia_eletiva, dados_sistema_completos
    ):
        """Teste: merge de dados de extração com variáveis de sistema."""
        # Simula o merge feito no detector
        dados_consolidados = dados_caso_cirurgia_eletiva.copy()
        dados_consolidados.update(dados_sistema_completos)

        # Regra de cirurgia deve continuar funcionando
        assert avaliador.avaliar(regra_simples_eletiva, dados_consolidados) is True

        # Variáveis de sistema também disponíveis
        regra_valor = {
            "type": "condition",
            "variable": "valor_causa_inferior_60sm",
            "operator": "equals",
            "value": True
        }
        assert avaliador.avaliar(regra_valor, dados_consolidados) is True


# ============================================================================
# TESTES: LISTAS (CONSOLIDAÇÃO OR)
# ============================================================================

class TestConsolidacaoListas:
    """Testes para consolidação de variáveis em lista (lógica OR)."""

    def test_lista_booleanos_or(self, avaliador):
        """Teste: lista de booleanos usa lógica OR."""
        regra = {
            "type": "condition",
            "variable": "pareceres_medicamento_nao_incorporado_sus",
            "operator": "equals",
            "value": True
        }

        # Lista com pelo menos um True → True
        assert avaliador.avaliar(regra, {"pareceres_medicamento_nao_incorporado_sus": [False, False, True]}) is True

        # Lista com todos False → False
        assert avaliador.avaliar(regra, {"pareceres_medicamento_nao_incorporado_sus": [False, False, False]}) is False


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
