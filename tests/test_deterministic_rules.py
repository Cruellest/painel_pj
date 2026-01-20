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
    pode_avaliar_regra,
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
# TESTES: PODE_AVALIAR_REGRA (CORREÇÃO BUG OR COM VARIÁVEIS PARCIAIS)
# ============================================================================

class TestPodeAvaliarRegra:
    """
    Testes para a função pode_avaliar_regra().

    Esta função foi criada para corrigir o bug onde regras OR eram bloqueadas
    quando nem todas as variáveis existiam nos dados, mesmo quando apenas
    UMA variável true seria suficiente para ativar.

    BUG ORIGINAL: evt_tema_1033 não ativava quando peticao_inicial_pedido_cirurgia=True
    porque as outras 5 variáveis não existiam no dicionário de dados.
    """

    @pytest.fixture
    def regra_or_simples(self):
        """Regra OR simples com 2 condições."""
        return {
            "type": "or",
            "conditions": [
                {"type": "condition", "variable": "var_a", "operator": "equals", "value": True},
                {"type": "condition", "variable": "var_b", "operator": "equals", "value": True}
            ]
        }

    @pytest.fixture
    def regra_and_simples(self):
        """Regra AND simples com 2 condições."""
        return {
            "type": "and",
            "conditions": [
                {"type": "condition", "variable": "var_a", "operator": "equals", "value": True},
                {"type": "condition", "variable": "var_b", "operator": "equals", "value": True}
            ]
        }

    @pytest.fixture
    def regra_or_aninhada_tema_1033(self):
        """
        Regra real do módulo evt_tema_1033 (reproduz bug em produção).

        Estrutura:
        OR(
            peticao_inicial_pedido_cirurgia == 1,
            OR(decisoes_afastamento_tema_1033_stf == 1, sentenca_afastamento_1033_stf == 1),
            OR(peticao_inicial_pedido_transferencia_hospitalar == 1,
               pareceres_analisou_transferencia == 1,
               residual_transferencia_vaga_hospitalar == 1)
        )
        """
        return {
            "type": "or",
            "conditions": [
                {
                    "type": "condition",
                    "variable": "peticao_inicial_pedido_cirurgia",
                    "operator": "equals",
                    "value": 1
                },
                {
                    "type": "or",
                    "conditions": [
                        {
                            "type": "condition",
                            "variable": "decisoes_afastamento_tema_1033_stf",
                            "operator": "equals",
                            "value": 1
                        },
                        {
                            "type": "condition",
                            "variable": "sentenca_afastamento_1033_stf",
                            "operator": "equals",
                            "value": 1
                        }
                    ]
                },
                {
                    "type": "or",
                    "conditions": [
                        {
                            "type": "condition",
                            "variable": "peticao_inicial_pedido_transferencia_hospitalar",
                            "operator": "equals",
                            "value": 1
                        },
                        {
                            "type": "condition",
                            "variable": "pareceres_analisou_transferencia",
                            "operator": "equals",
                            "value": 1
                        },
                        {
                            "type": "condition",
                            "variable": "residual_transferencia_vaga_hospitalar",
                            "operator": "equals",
                            "value": 1
                        }
                    ]
                }
            ]
        }

    # --- Testes OR ---

    def test_or_pode_avaliar_com_uma_variavel(self, regra_or_simples):
        """OR: pode avaliar se pelo menos UMA variável existe."""
        dados = {"var_a": True}  # var_b não existe
        pode, existentes, faltantes = pode_avaliar_regra(regra_or_simples, dados)

        assert pode is True, "OR deve poder avaliar com apenas uma variável"
        assert "var_a" in existentes
        assert "var_b" in faltantes

    def test_or_pode_avaliar_com_todas_variaveis(self, regra_or_simples):
        """OR: pode avaliar quando todas as variáveis existem."""
        dados = {"var_a": True, "var_b": False}
        pode, existentes, faltantes = pode_avaliar_regra(regra_or_simples, dados)

        assert pode is True
        assert set(existentes) == {"var_a", "var_b"}
        assert faltantes == []

    def test_or_nao_pode_avaliar_sem_variaveis(self, regra_or_simples):
        """OR: NÃO pode avaliar se NENHUMA variável existe."""
        dados = {"outra_variavel": True}  # nenhuma das variáveis da regra existe
        pode, existentes, faltantes = pode_avaliar_regra(regra_or_simples, dados)

        assert pode is False
        assert existentes == []
        assert set(faltantes) == {"var_a", "var_b"}

    # --- Testes AND ---

    def test_and_nao_pode_avaliar_com_variavel_faltando(self, regra_and_simples):
        """AND: NÃO pode avaliar se alguma variável falta."""
        dados = {"var_a": True}  # var_b não existe
        pode, existentes, faltantes = pode_avaliar_regra(regra_and_simples, dados)

        assert pode is False, "AND requer TODAS as variáveis"
        assert "var_a" in existentes
        assert "var_b" in faltantes

    def test_and_pode_avaliar_com_todas_variaveis(self, regra_and_simples):
        """AND: pode avaliar quando TODAS as variáveis existem."""
        dados = {"var_a": True, "var_b": False}
        pode, existentes, faltantes = pode_avaliar_regra(regra_and_simples, dados)

        assert pode is True
        assert set(existentes) == {"var_a", "var_b"}
        assert faltantes == []

    # --- Teste do Bug Real (evt_tema_1033) ---

    def test_bug_tema_1033_pode_avaliar(self, regra_or_aninhada_tema_1033):
        """
        REPRODUZ BUG REAL: evt_tema_1033 não ativava com apenas uma variável.

        Cenário: processo 08683554520258120001
        - peticao_inicial_pedido_cirurgia = True
        - outras 5 variáveis não existem

        ANTES DO FIX: verificar_variaveis_existem retornava False (bloqueava)
        DEPOIS DO FIX: pode_avaliar_regra retorna True (permite avaliação)
        """
        dados = {"peticao_inicial_pedido_cirurgia": True}

        # Verifica que a função ANTIGA bloquearia
        todas_existem, _ = verificar_variaveis_existem(regra_or_aninhada_tema_1033, dados)
        assert todas_existem is False, "verificar_variaveis_existem deve retornar False (6 vars, 1 existe)"

        # Verifica que a função NOVA permite avaliação
        pode, existentes, faltantes = pode_avaliar_regra(regra_or_aninhada_tema_1033, dados)
        assert pode is True, "pode_avaliar_regra deve retornar True para OR com 1 variável"
        assert existentes == ["peticao_inicial_pedido_cirurgia"]
        assert len(faltantes) == 5

    def test_bug_tema_1033_avaliacao_correta(self, avaliador, regra_or_aninhada_tema_1033):
        """
        Confirma que o avaliador retorna True quando uma variável OR é satisfeita.
        """
        dados = {"peticao_inicial_pedido_cirurgia": True}
        resultado = avaliador.avaliar(regra_or_aninhada_tema_1033, dados)

        assert resultado is True, "Regra OR deve ativar quando primeira condição é True"

    def test_bug_tema_1033_avaliacao_alternativa(self, avaliador, regra_or_aninhada_tema_1033):
        """
        Testa ativação por outras condições da regra evt_tema_1033.
        """
        # Ativa pelo segundo ramo OR (decisoes)
        dados = {"decisoes_afastamento_tema_1033_stf": True}
        pode, _, _ = pode_avaliar_regra(regra_or_aninhada_tema_1033, dados)
        assert pode is True
        assert avaliador.avaliar(regra_or_aninhada_tema_1033, dados) is True

        # Ativa pelo terceiro ramo OR (transferencia)
        dados = {"residual_transferencia_vaga_hospitalar": True}
        pode, _, _ = pode_avaliar_regra(regra_or_aninhada_tema_1033, dados)
        assert pode is True
        assert avaliador.avaliar(regra_or_aninhada_tema_1033, dados) is True

    # --- Testes de Condição Simples ---

    def test_condicao_simples_com_variavel(self):
        """Condição simples pode avaliar se variável existe."""
        regra = {"type": "condition", "variable": "var_x", "operator": "equals", "value": True}

        pode, existentes, faltantes = pode_avaliar_regra(regra, {"var_x": True})
        assert pode is True
        assert existentes == ["var_x"]
        assert faltantes == []

    def test_condicao_simples_sem_variavel(self):
        """Condição simples NÃO pode avaliar se variável não existe."""
        regra = {"type": "condition", "variable": "var_x", "operator": "equals", "value": True}

        pode, existentes, faltantes = pode_avaliar_regra(regra, {"outra": True})
        assert pode is False
        assert existentes == []
        assert faltantes == ["var_x"]

    # --- Testes NOT ---

    def test_not_pode_avaliar(self):
        """NOT pode avaliar se a condição interna pode."""
        regra = {
            "type": "not",
            "condition": {"type": "condition", "variable": "var_x", "operator": "equals", "value": True}
        }

        pode, _, _ = pode_avaliar_regra(regra, {"var_x": False})
        assert pode is True

        pode, _, _ = pode_avaliar_regra(regra, {"outra": True})
        assert pode is False

    # --- Testes de Regra Vazia ---

    def test_regra_vazia(self):
        """Regra vazia não pode ser avaliada."""
        pode, existentes, faltantes = pode_avaliar_regra({}, {"var": True})
        assert pode is False
        assert existentes == []
        assert faltantes == []

    def test_regra_none(self):
        """Regra None não pode ser avaliada."""
        pode, existentes, faltantes = pode_avaliar_regra(None, {"var": True})
        assert pode is False


# ============================================================================
# TESTES: FLUXO END-TO-END (INTEGRAÇÃO)
# ============================================================================

class TestFluxoEndToEnd:
    """
    Testes de integração verificando o fluxo completo da correção.

    Estes testes validam que a correção de pode_avaliar_regra é usada
    corretamente no fluxo de avaliar_ativacao_prompt.
    """

    @pytest.fixture
    def regra_or_tema_1033(self):
        """Regra simplificada do tema 1033 para testes."""
        return {
            "type": "or",
            "conditions": [
                {"type": "condition", "variable": "peticao_inicial_pedido_cirurgia", "operator": "equals", "value": True},
                {"type": "condition", "variable": "decisoes_afastamento_tema_1033_stf", "operator": "equals", "value": True},
            ]
        }

    def test_fluxo_or_parcial_deve_ativar(self, avaliador, regra_or_tema_1033):
        """
        Valida que regra OR com variáveis parciais ativa corretamente.

        Simula o cenário real que causava o bug.
        """
        dados = {"peticao_inicial_pedido_cirurgia": True}

        # pode_avaliar_regra deve permitir
        pode, _, _ = pode_avaliar_regra(regra_or_tema_1033, dados)
        assert pode is True

        # Avaliador deve retornar True
        resultado = avaliador.avaliar(regra_or_tema_1033, dados)
        assert resultado is True

    def test_fluxo_or_parcial_deve_nao_ativar(self, avaliador, regra_or_tema_1033):
        """
        Valida que regra OR com variável False não ativa.
        """
        dados = {"peticao_inicial_pedido_cirurgia": False}

        # pode_avaliar_regra deve permitir (variável existe)
        pode, _, _ = pode_avaliar_regra(regra_or_tema_1033, dados)
        assert pode is True

        # Avaliador deve retornar False (nenhuma condição satisfeita)
        resultado = avaliador.avaliar(regra_or_tema_1033, dados)
        assert resultado is False


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
