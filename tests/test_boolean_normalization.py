#!/usr/bin/env python
"""
Testes de normalização de valores booleanos em regras determinísticas.

Este arquivo testa a correção do bug onde valores booleanos eram 
salvos/carregados como "1"/"0" ao invés de true/false.

Bug corrigido em: Janeiro 2026
"""

from sistemas.gerador_pecas.services_deterministic import DeterministicRuleEvaluator
from admin.router_prompts import normalizar_booleanos_regra


class TestNormalizarBooleanos:
    """Testes para a função normalizar_booleanos_regra."""

    def test_normaliza_1_para_true(self):
        """Valor 1 (int) deve ser convertido para True."""
        regra = {
            "type": "condition",
            "variable": "teste",
            "operator": "equals",
            "value": 1
        }
        resultado = normalizar_booleanos_regra(regra)
        assert resultado["value"] is True

    def test_normaliza_0_para_false(self):
        """Valor 0 (int) deve ser convertido para False."""
        regra = {
            "type": "condition",
            "variable": "teste",
            "operator": "equals",
            "value": 0
        }
        resultado = normalizar_booleanos_regra(regra)
        assert resultado["value"] is False

    def test_normaliza_string_1_para_true(self):
        """Valor "1" (string) deve ser convertido para True."""
        regra = {
            "type": "condition",
            "variable": "teste",
            "operator": "equals",
            "value": "1"
        }
        resultado = normalizar_booleanos_regra(regra)
        assert resultado["value"] is True

    def test_normaliza_string_0_para_false(self):
        """Valor "0" (string) deve ser convertido para False."""
        regra = {
            "type": "condition",
            "variable": "teste",
            "operator": "equals",
            "value": "0"
        }
        resultado = normalizar_booleanos_regra(regra)
        assert resultado["value"] is False

    def test_normaliza_string_true_para_boolean(self):
        """Valor "true" (string) deve ser convertido para True."""
        regra = {
            "type": "condition",
            "variable": "teste",
            "operator": "equals",
            "value": "true"
        }
        resultado = normalizar_booleanos_regra(regra)
        assert resultado["value"] is True

    def test_normaliza_string_false_para_boolean(self):
        """Valor "false" (string) deve ser convertido para False."""
        regra = {
            "type": "condition",
            "variable": "teste",
            "operator": "equals",
            "value": "false"
        }
        resultado = normalizar_booleanos_regra(regra)
        assert resultado["value"] is False

    def test_mantem_boolean_true(self):
        """Valor True (boolean) deve permanecer True."""
        regra = {
            "type": "condition",
            "variable": "teste",
            "operator": "equals",
            "value": True
        }
        resultado = normalizar_booleanos_regra(regra)
        assert resultado["value"] is True

    def test_mantem_boolean_false(self):
        """Valor False (boolean) deve permanecer False."""
        regra = {
            "type": "condition",
            "variable": "teste",
            "operator": "equals",
            "value": False
        }
        resultado = normalizar_booleanos_regra(regra)
        assert resultado["value"] is False

    def test_mantem_valores_nao_booleanos(self):
        """Valores que não são booleanos devem permanecer inalterados."""
        regra = {
            "type": "condition",
            "variable": "teste",
            "operator": "equals",
            "value": "texto qualquer"
        }
        resultado = normalizar_booleanos_regra(regra)
        assert resultado["value"] == "texto qualquer"

    def test_mantem_numeros_nao_binarios(self):
        """Números diferentes de 0/1 devem permanecer inalterados."""
        regra = {
            "type": "condition",
            "variable": "teste",
            "operator": "greater_than",
            "value": 100
        }
        resultado = normalizar_booleanos_regra(regra)
        assert resultado["value"] == 100

    def test_normaliza_regra_complexa_and(self):
        """Normaliza valores em regras complexas com AND."""
        regra = {
            "type": "and",
            "conditions": [
                {"type": "condition", "variable": "a", "operator": "equals", "value": 1},
                {"type": "condition", "variable": "b", "operator": "equals", "value": "0"}
            ]
        }
        resultado = normalizar_booleanos_regra(regra)
        assert resultado["conditions"][0]["value"] is True
        assert resultado["conditions"][1]["value"] is False

    def test_normaliza_regra_aninhada(self):
        """Normaliza valores em regras aninhadas com grupos."""
        regra = {
            "type": "and",
            "conditions": [
                {"type": "condition", "variable": "a", "operator": "equals", "value": 1},
                {
                    "type": "or",
                    "conditions": [
                        {"type": "condition", "variable": "b", "operator": "equals", "value": "1"},
                        {"type": "condition", "variable": "c", "operator": "equals", "value": 0}
                    ]
                }
            ]
        }
        resultado = normalizar_booleanos_regra(regra)
        assert resultado["conditions"][0]["value"] is True
        assert resultado["conditions"][1]["conditions"][0]["value"] is True
        assert resultado["conditions"][1]["conditions"][1]["value"] is False

    def test_normaliza_regra_none(self):
        """Regra None deve retornar None."""
        resultado = normalizar_booleanos_regra(None)
        assert resultado is None

    def test_normaliza_regra_vazia(self):
        """Regra vazia deve retornar vazia."""
        regra = {}
        resultado = normalizar_booleanos_regra(regra)
        assert resultado == {}


class TestEvaluatorComValoresLegados:
    """Testes para garantir que o avaliador funciona com valores 1/0 legados."""

    def setup_method(self):
        self.evaluator = DeterministicRuleEvaluator()

    def test_avalia_regra_com_1_como_true(self):
        """O avaliador deve tratar value:1 como true."""
        regra = {
            "type": "condition",
            "variable": "teste",
            "operator": "equals",
            "value": 1  # Legado: 1 ao invés de true
        }
        dados = {"teste": True}
        resultado = self.evaluator.avaliar(regra, dados)
        assert resultado is True

    def test_avalia_regra_com_0_como_false(self):
        """O avaliador deve tratar value:0 como false."""
        regra = {
            "type": "condition",
            "variable": "teste",
            "operator": "equals",
            "value": 0  # Legado: 0 ao invés de false
        }
        dados = {"teste": False}
        resultado = self.evaluator.avaliar(regra, dados)
        assert resultado is True

    def test_avalia_regra_mista_1_e_true(self):
        """Regra com value:1 deve funcionar com dados boolean True."""
        regra = {
            "type": "and",
            "conditions": [
                {"type": "condition", "variable": "a", "operator": "equals", "value": 1},
                {"type": "condition", "variable": "b", "operator": "equals", "value": True}
            ]
        }
        dados = {"a": True, "b": True}
        resultado = self.evaluator.avaliar(regra, dados)
        assert resultado is True

    def test_avalia_regra_mista_0_e_false(self):
        """Regra com value:0 deve funcionar com dados boolean False."""
        regra = {
            "type": "and",
            "conditions": [
                {"type": "condition", "variable": "a", "operator": "equals", "value": 0},
                {"type": "condition", "variable": "b", "operator": "equals", "value": False}
            ]
        }
        dados = {"a": False, "b": False}
        resultado = self.evaluator.avaliar(regra, dados)
        assert resultado is True


if __name__ == "__main__":
    # Executa os testes diretamente
    print("=" * 70)
    print("TESTES DE NORMALIZAÇÃO DE BOOLEANOS")
    print("=" * 70)

    test_class = TestNormalizarBooleanos()
    
    test_class.test_normaliza_1_para_true()
    print("✓ test_normaliza_1_para_true")
    
    test_class.test_normaliza_0_para_false()
    print("✓ test_normaliza_0_para_false")
    
    test_class.test_normaliza_string_1_para_true()
    print("✓ test_normaliza_string_1_para_true")
    
    test_class.test_normaliza_string_0_para_false()
    print("✓ test_normaliza_string_0_para_false")
    
    test_class.test_normaliza_string_true_para_boolean()
    print("✓ test_normaliza_string_true_para_boolean")
    
    test_class.test_normaliza_string_false_para_boolean()
    print("✓ test_normaliza_string_false_para_boolean")
    
    test_class.test_mantem_boolean_true()
    print("✓ test_mantem_boolean_true")
    
    test_class.test_mantem_boolean_false()
    print("✓ test_mantem_boolean_false")
    
    test_class.test_mantem_valores_nao_booleanos()
    print("✓ test_mantem_valores_nao_booleanos")
    
    test_class.test_mantem_numeros_nao_binarios()
    print("✓ test_mantem_numeros_nao_binarios")
    
    test_class.test_normaliza_regra_complexa_and()
    print("✓ test_normaliza_regra_complexa_and")
    
    test_class.test_normaliza_regra_aninhada()
    print("✓ test_normaliza_regra_aninhada")
    
    test_class.test_normaliza_regra_none()
    print("✓ test_normaliza_regra_none")
    
    test_class.test_normaliza_regra_vazia()
    print("✓ test_normaliza_regra_vazia")

    print("\n" + "-" * 70)
    print("TESTES DE AVALIADOR COM VALORES LEGADOS")
    print("-" * 70)

    eval_test = TestEvaluatorComValoresLegados()
    eval_test.setup_method()
    
    eval_test.test_avalia_regra_com_1_como_true()
    print("✓ test_avalia_regra_com_1_como_true")
    
    eval_test.test_avalia_regra_com_0_como_false()
    print("✓ test_avalia_regra_com_0_como_false")
    
    eval_test.test_avalia_regra_mista_1_e_true()
    print("✓ test_avalia_regra_mista_1_e_true")
    
    eval_test.test_avalia_regra_mista_0_e_false()
    print("✓ test_avalia_regra_mista_0_e_false")

    print("\n" + "=" * 70)
    print("✅ TODOS OS TESTES PASSARAM!")
    print("=" * 70)
