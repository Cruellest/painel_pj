#!/usr/bin/env python
"""
Teste de agrupamento lógico (parênteses) em regras determinísticas.

Testa que o sistema suporta expressões como:
- A AND (B OR C)
- (A OR B) AND C
- A AND B AND (C OR D)
"""

from sistemas.gerador_pecas.services_deterministic import DeterministicRuleEvaluator

evaluator = DeterministicRuleEvaluator()

print("=" * 70)
print("TESTE DE AGRUPAMENTO LÓGICO EM REGRAS DETERMINÍSTICAS")
print("=" * 70)

# ==============================================================================
# TESTE 1: A AND (B OR C)
# Caso: "Quando for pleiteado medicamento E (não incorporado SUS OU não incorporado patologia)"
# ==============================================================================
print("\n=== TESTE 1: A AND (B OR C) ===")
print("Regra: pleiteado_medicamento AND (nao_incorporado_sus OR nao_incorporado_patologia)")

regra_a_and_b_or_c = {
    "type": "and",
    "conditions": [
        {"type": "condition", "variable": "pleiteado_medicamento", "operator": "equals", "value": True},
        {
            "type": "or",
            "conditions": [
                {"type": "condition", "variable": "nao_incorporado_sus", "operator": "equals", "value": True},
                {"type": "condition", "variable": "nao_incorporado_patologia", "operator": "equals", "value": True}
            ]
        }
    ]
}

# Caso 1: A=true, B=false, C=true → deve ativar (true AND (false OR true) = true AND true = true)
caso1 = {"pleiteado_medicamento": True, "nao_incorporado_sus": False, "nao_incorporado_patologia": True}
resultado1 = evaluator.avaliar(regra_a_and_b_or_c, caso1)
assert resultado1 == True, f"Caso 1 falhou: esperado True, obtido {resultado1}"
print(f"✓ Caso 1: A=T, B=F, C=T → {resultado1} (esperado: True)")

# Caso 2: A=true, B=false, C=false → NÃO deve ativar (true AND (false OR false) = true AND false = false)
caso2 = {"pleiteado_medicamento": True, "nao_incorporado_sus": False, "nao_incorporado_patologia": False}
resultado2 = evaluator.avaliar(regra_a_and_b_or_c, caso2)
assert resultado2 == False, f"Caso 2 falhou: esperado False, obtido {resultado2}"
print(f"✓ Caso 2: A=T, B=F, C=F → {resultado2} (esperado: False)")

# Caso 3: A=false, B=true, C=true → NÃO deve ativar (false AND (true OR true) = false AND true = false)
caso3 = {"pleiteado_medicamento": False, "nao_incorporado_sus": True, "nao_incorporado_patologia": True}
resultado3 = evaluator.avaliar(regra_a_and_b_or_c, caso3)
assert resultado3 == False, f"Caso 3 falhou: esperado False, obtido {resultado3}"
print(f"✓ Caso 3: A=F, B=T, C=T → {resultado3} (esperado: False)")

# Caso 4: A=true, B=true, C=false → deve ativar (true AND (true OR false) = true AND true = true)
caso4 = {"pleiteado_medicamento": True, "nao_incorporado_sus": True, "nao_incorporado_patologia": False}
resultado4 = evaluator.avaliar(regra_a_and_b_or_c, caso4)
assert resultado4 == True, f"Caso 4 falhou: esperado True, obtido {resultado4}"
print(f"✓ Caso 4: A=T, B=T, C=F → {resultado4} (esperado: True)")

# ==============================================================================
# TESTE 2: (A OR B) AND C
# Caso: "(autor idoso OU hipossuficiente) E valor alto"
# ==============================================================================
print("\n=== TESTE 2: (A OR B) AND C ===")
print("Regra: (autor_idoso OR autor_hipossuficiente) AND valor_alto")

regra_a_or_b_and_c = {
    "type": "and",
    "conditions": [
        {
            "type": "or",
            "conditions": [
                {"type": "condition", "variable": "autor_idoso", "operator": "equals", "value": True},
                {"type": "condition", "variable": "autor_hipossuficiente", "operator": "equals", "value": True}
            ]
        },
        {"type": "condition", "variable": "valor_alto", "operator": "equals", "value": True}
    ]
}

# Caso 1: A=true, B=false, C=true → deve ativar ((true OR false) AND true = true)
caso1 = {"autor_idoso": True, "autor_hipossuficiente": False, "valor_alto": True}
resultado1 = evaluator.avaliar(regra_a_or_b_and_c, caso1)
assert resultado1 == True, f"Caso 1 falhou: esperado True, obtido {resultado1}"
print(f"✓ Caso 1: A=T, B=F, C=T → {resultado1} (esperado: True)")

# Caso 2: A=false, B=false, C=true → NÃO deve ativar ((false OR false) AND true = false)
caso2 = {"autor_idoso": False, "autor_hipossuficiente": False, "valor_alto": True}
resultado2 = evaluator.avaliar(regra_a_or_b_and_c, caso2)
assert resultado2 == False, f"Caso 2 falhou: esperado False, obtido {resultado2}"
print(f"✓ Caso 2: A=F, B=F, C=T → {resultado2} (esperado: False)")

# Caso 3: A=true, B=true, C=false → NÃO deve ativar ((true OR true) AND false = false)
caso3 = {"autor_idoso": True, "autor_hipossuficiente": True, "valor_alto": False}
resultado3 = evaluator.avaliar(regra_a_or_b_and_c, caso3)
assert resultado3 == False, f"Caso 3 falhou: esperado False, obtido {resultado3}"
print(f"✓ Caso 3: A=T, B=T, C=F → {resultado3} (esperado: False)")

# ==============================================================================
# TESTE 3: A OR (B AND C)
# Caso: "urgente OU (medicamento alto custo E sem genérico)"
# ==============================================================================
print("\n=== TESTE 3: A OR (B AND C) ===")
print("Regra: urgente OR (medicamento_alto_custo AND sem_generico)")

regra_a_or_b_and_c = {
    "type": "or",
    "conditions": [
        {"type": "condition", "variable": "urgente", "operator": "equals", "value": True},
        {
            "type": "and",
            "conditions": [
                {"type": "condition", "variable": "medicamento_alto_custo", "operator": "equals", "value": True},
                {"type": "condition", "variable": "sem_generico", "operator": "equals", "value": True}
            ]
        }
    ]
}

# Caso 1: A=false, B=true, C=true → deve ativar (false OR (true AND true) = true)
caso1 = {"urgente": False, "medicamento_alto_custo": True, "sem_generico": True}
resultado1 = evaluator.avaliar(regra_a_or_b_and_c, caso1)
assert resultado1 == True, f"Caso 1 falhou: esperado True, obtido {resultado1}"
print(f"✓ Caso 1: A=F, B=T, C=T → {resultado1} (esperado: True)")

# Caso 2: A=true, B=false, C=false → deve ativar (true OR (false AND false) = true)
caso2 = {"urgente": True, "medicamento_alto_custo": False, "sem_generico": False}
resultado2 = evaluator.avaliar(regra_a_or_b_and_c, caso2)
assert resultado2 == True, f"Caso 2 falhou: esperado True, obtido {resultado2}"
print(f"✓ Caso 2: A=T, B=F, C=F → {resultado2} (esperado: True)")

# Caso 3: A=false, B=true, C=false → NÃO deve ativar (false OR (true AND false) = false)
caso3 = {"urgente": False, "medicamento_alto_custo": True, "sem_generico": False}
resultado3 = evaluator.avaliar(regra_a_or_b_and_c, caso3)
assert resultado3 == False, f"Caso 3 falhou: esperado False, obtido {resultado3}"
print(f"✓ Caso 3: A=F, B=T, C=F → {resultado3} (esperado: False)")

# ==============================================================================
# TESTE 4: Nesting profundo - (A AND B) OR (C AND D)
# ==============================================================================
print("\n=== TESTE 4: (A AND B) OR (C AND D) ===")
print("Regra: (idoso AND hipossuficiente) OR (urgente AND valor_alto)")

regra_nesting_profundo = {
    "type": "or",
    "conditions": [
        {
            "type": "and",
            "conditions": [
                {"type": "condition", "variable": "idoso", "operator": "equals", "value": True},
                {"type": "condition", "variable": "hipossuficiente", "operator": "equals", "value": True}
            ]
        },
        {
            "type": "and",
            "conditions": [
                {"type": "condition", "variable": "urgente", "operator": "equals", "value": True},
                {"type": "condition", "variable": "valor_alto", "operator": "equals", "value": True}
            ]
        }
    ]
}

# Caso 1: primeiro grupo verdadeiro
caso1 = {"idoso": True, "hipossuficiente": True, "urgente": False, "valor_alto": False}
resultado1 = evaluator.avaliar(regra_nesting_profundo, caso1)
assert resultado1 == True, f"Caso 1 falhou: esperado True, obtido {resultado1}"
print(f"✓ Caso 1: (T AND T) OR (F AND F) → {resultado1} (esperado: True)")

# Caso 2: segundo grupo verdadeiro
caso2 = {"idoso": False, "hipossuficiente": False, "urgente": True, "valor_alto": True}
resultado2 = evaluator.avaliar(regra_nesting_profundo, caso2)
assert resultado2 == True, f"Caso 2 falhou: esperado True, obtido {resultado2}"
print(f"✓ Caso 2: (F AND F) OR (T AND T) → {resultado2} (esperado: True)")

# Caso 3: nenhum grupo verdadeiro
caso3 = {"idoso": True, "hipossuficiente": False, "urgente": True, "valor_alto": False}
resultado3 = evaluator.avaliar(regra_nesting_profundo, caso3)
assert resultado3 == False, f"Caso 3 falhou: esperado False, obtido {resultado3}"
print(f"✓ Caso 3: (T AND F) OR (T AND F) → {resultado3} (esperado: False)")

# ==============================================================================
# TESTE 5: Nesting com NOT - A AND NOT(B OR C)
# ==============================================================================
print("\n=== TESTE 5: A AND NOT(B OR C) ===")
print("Regra: pleiteado AND NOT(incorporado_sus OR incorporado_patologia)")

regra_with_not = {
    "type": "and",
    "conditions": [
        {"type": "condition", "variable": "pleiteado", "operator": "equals", "value": True},
        {
            "type": "not",
            "condition": {
                "type": "or",
                "conditions": [
                    {"type": "condition", "variable": "incorporado_sus", "operator": "equals", "value": True},
                    {"type": "condition", "variable": "incorporado_patologia", "operator": "equals", "value": True}
                ]
            }
        }
    ]
}

# Caso 1: A=true, B=false, C=false → deve ativar (true AND NOT(false OR false) = true AND true = true)
caso1 = {"pleiteado": True, "incorporado_sus": False, "incorporado_patologia": False}
resultado1 = evaluator.avaliar(regra_with_not, caso1)
assert resultado1 == True, f"Caso 1 falhou: esperado True, obtido {resultado1}"
print(f"✓ Caso 1: T AND NOT(F OR F) → {resultado1} (esperado: True)")

# Caso 2: A=true, B=true, C=false → NÃO deve ativar (true AND NOT(true OR false) = true AND false = false)
caso2 = {"pleiteado": True, "incorporado_sus": True, "incorporado_patologia": False}
resultado2 = evaluator.avaliar(regra_with_not, caso2)
assert resultado2 == False, f"Caso 2 falhou: esperado False, obtido {resultado2}"
print(f"✓ Caso 2: T AND NOT(T OR F) → {resultado2} (esperado: False)")

# Caso 3: A=true, B=false, C=true → NÃO deve ativar (true AND NOT(false OR true) = true AND false = false)
caso3 = {"pleiteado": True, "incorporado_sus": False, "incorporado_patologia": True}
resultado3 = evaluator.avaliar(regra_with_not, caso3)
assert resultado3 == False, f"Caso 3 falhou: esperado False, obtido {resultado3}"
print(f"✓ Caso 3: T AND NOT(F OR T) → {resultado3} (esperado: False)")

# ==============================================================================
# TESTE 6: Triple nesting - A AND (B OR (C AND D))
# ==============================================================================
print("\n=== TESTE 6: A AND (B OR (C AND D)) - Triple Nesting ===")
print("Regra: principal AND (urgente OR (alto_custo AND sem_alternativa))")

regra_triple_nesting = {
    "type": "and",
    "conditions": [
        {"type": "condition", "variable": "principal", "operator": "equals", "value": True},
        {
            "type": "or",
            "conditions": [
                {"type": "condition", "variable": "urgente", "operator": "equals", "value": True},
                {
                    "type": "and",
                    "conditions": [
                        {"type": "condition", "variable": "alto_custo", "operator": "equals", "value": True},
                        {"type": "condition", "variable": "sem_alternativa", "operator": "equals", "value": True}
                    ]
                }
            ]
        }
    ]
}

# Caso 1: principal=T, urgente=F, alto_custo=T, sem_alternativa=T → true
caso1 = {"principal": True, "urgente": False, "alto_custo": True, "sem_alternativa": True}
resultado1 = evaluator.avaliar(regra_triple_nesting, caso1)
assert resultado1 == True, f"Caso 1 falhou: esperado True, obtido {resultado1}"
print(f"✓ Caso 1: T AND (F OR (T AND T)) → {resultado1} (esperado: True)")

# Caso 2: principal=T, urgente=T, alto_custo=F, sem_alternativa=F → true
caso2 = {"principal": True, "urgente": True, "alto_custo": False, "sem_alternativa": False}
resultado2 = evaluator.avaliar(regra_triple_nesting, caso2)
assert resultado2 == True, f"Caso 2 falhou: esperado True, obtido {resultado2}"
print(f"✓ Caso 2: T AND (T OR (F AND F)) → {resultado2} (esperado: True)")

# Caso 3: principal=T, urgente=F, alto_custo=T, sem_alternativa=F → false
caso3 = {"principal": True, "urgente": False, "alto_custo": True, "sem_alternativa": False}
resultado3 = evaluator.avaliar(regra_triple_nesting, caso3)
assert resultado3 == False, f"Caso 3 falhou: esperado False, obtido {resultado3}"
print(f"✓ Caso 3: T AND (F OR (T AND F)) → {resultado3} (esperado: False)")

# ==============================================================================
# RESUMO
# ==============================================================================
print("\n" + "=" * 70)
print("✅ TODOS OS TESTES DE AGRUPAMENTO LÓGICO PASSARAM!")
print("=" * 70)
print("""
O sistema suporta completamente:
- A AND (B OR C)
- (A OR B) AND C
- A OR (B AND C)
- (A AND B) OR (C AND D)
- A AND NOT(B OR C)
- A AND (B OR (C AND D)) - nesting triplo
""")
