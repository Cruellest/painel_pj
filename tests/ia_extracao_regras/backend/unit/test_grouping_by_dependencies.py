# tests/ia_extracao_regras/backend/unit/test_grouping_by_dependencies.py
"""
Testes unitários para o algoritmo de agrupamento por dependências.

Cenários testados:
1. 1 mãe + 2 filhos → filhos ficam logo abaixo
2. hierarquia mãe→filho→neto → mantém árvore
3. múltiplas mães → preserva ordem relativa das mães
4. filhos com mesmo pai → preserva ordem relativa original
5. multi-pai → regra determinística aplicada
6. ciclo → não trava, mantém ordem e gera aviso
"""

import unittest
from unittest.mock import MagicMock
from datetime import datetime

# Importações do sistema
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

from sistemas.gerador_pecas.router_extraction import _agrupar_por_dependencias_algoritmo


def criar_pergunta_mock(id: int, pergunta: str, ordem: int,
                         nome_variavel_sugerido: str = None,
                         depends_on_variable: str = None):
    """Cria um mock de ExtractionQuestion para testes"""
    p = MagicMock()
    p.id = id
    p.pergunta = pergunta
    p.ordem = ordem
    p.nome_variavel_sugerido = nome_variavel_sugerido
    p.depends_on_variable = depends_on_variable
    return p


class TestAgruparPorDependencias(unittest.TestCase):
    """Testes para o algoritmo de agrupamento por dependências"""

    def test_cenario_1_mae_com_2_filhos(self):
        """
        Cenário 1: 1 mãe + 2 filhos → filhos ficam logo abaixo da mãe

        Entrada (desordenada):
        - P1: Mãe (ordem 0) - variável: "tipo_acao"
        - P2: Outra pergunta (ordem 1)
        - P3: Filho de P1 (ordem 2) - depende de "tipo_acao"
        - P4: Filho de P1 (ordem 3) - depende de "tipo_acao"

        Saída esperada:
        - P1 (mãe)
        - P3 (filho)
        - P4 (filho)
        - P2 (outra)
        """
        p1 = criar_pergunta_mock(1, "Qual o tipo de ação?", 0, "tipo_acao", None)
        p2 = criar_pergunta_mock(2, "Qual o nome do autor?", 1, "nome_autor", None)
        p3 = criar_pergunta_mock(3, "É medicamento de alto custo?", 2, "alto_custo", "tipo_acao")
        p4 = criar_pergunta_mock(4, "Tem prescrição médica?", 3, "tem_prescricao", "tipo_acao")

        perguntas = [p1, p2, p3, p4]

        resultado, ciclos = _agrupar_por_dependencias_algoritmo(perguntas)

        # Verifica ordem
        ids_resultado = [item["pergunta"].id for item in resultado]
        self.assertEqual(ids_resultado, [1, 3, 4, 2])

        # Verifica níveis
        niveis = [item["nivel"] for item in resultado]
        self.assertEqual(niveis, [0, 1, 1, 0])

        # Sem ciclos
        self.assertEqual(len(ciclos), 0)

    def test_cenario_2_hierarquia_mae_filho_neto(self):
        """
        Cenário 2: hierarquia mãe→filho→neto → mantém árvore

        Entrada:
        - P1: Mãe - variável: "tipo"
        - P2: Filho de P1 - variável: "subtipo" - depende de "tipo"
        - P3: Neto (filho de P2) - depende de "subtipo"
        - P4: Outra raiz

        Saída esperada: P1 → P2 → P3 → P4
        """
        p1 = criar_pergunta_mock(1, "Tipo da ação", 0, "tipo", None)
        p2 = criar_pergunta_mock(2, "Subtipo", 1, "subtipo", "tipo")
        p3 = criar_pergunta_mock(3, "Detalhes do subtipo", 2, "detalhe", "subtipo")
        p4 = criar_pergunta_mock(4, "Outra pergunta", 3, "outra", None)

        perguntas = [p1, p2, p3, p4]

        resultado, ciclos = _agrupar_por_dependencias_algoritmo(perguntas)

        ids_resultado = [item["pergunta"].id for item in resultado]
        self.assertEqual(ids_resultado, [1, 2, 3, 4])

        niveis = [item["nivel"] for item in resultado]
        self.assertEqual(niveis, [0, 1, 2, 0])

        self.assertEqual(len(ciclos), 0)

    def test_cenario_3_multiplas_maes_preserva_ordem(self):
        """
        Cenário 3: múltiplas mães → preserva ordem relativa das mães

        Entrada:
        - P1: Mãe A (ordem 0) - variável: "mae_a"
        - P2: Mãe B (ordem 1) - variável: "mae_b"
        - P3: Mãe C (ordem 2) - variável: "mae_c"
        - P4: Filho de B (ordem 3) - depende de "mae_b"
        - P5: Filho de A (ordem 4) - depende de "mae_a"

        Saída esperada: P1 → P5 → P2 → P4 → P3
        (mães na ordem original, com filhos abaixo de cada mãe)
        """
        p1 = criar_pergunta_mock(1, "Mãe A", 0, "mae_a", None)
        p2 = criar_pergunta_mock(2, "Mãe B", 1, "mae_b", None)
        p3 = criar_pergunta_mock(3, "Mãe C", 2, "mae_c", None)
        p4 = criar_pergunta_mock(4, "Filho de B", 3, "filho_b", "mae_b")
        p5 = criar_pergunta_mock(5, "Filho de A", 4, "filho_a", "mae_a")

        perguntas = [p1, p2, p3, p4, p5]

        resultado, ciclos = _agrupar_por_dependencias_algoritmo(perguntas)

        ids_resultado = [item["pergunta"].id for item in resultado]
        # Mãe A (1) → Filho A (5) → Mãe B (2) → Filho B (4) → Mãe C (3)
        self.assertEqual(ids_resultado, [1, 5, 2, 4, 3])

        self.assertEqual(len(ciclos), 0)

    def test_cenario_4_filhos_mesmo_pai_preserva_ordem(self):
        """
        Cenário 4: filhos com mesmo pai → preserva ordem relativa original

        Entrada:
        - P1: Mãe - variável: "mae"
        - P2: Filho 1 (ordem 1) - depende de "mae"
        - P3: Filho 2 (ordem 2) - depende de "mae"
        - P4: Filho 3 (ordem 3) - depende de "mae"

        Saída: P1 → P2 → P3 → P4 (ordem original dos filhos preservada)
        """
        p1 = criar_pergunta_mock(1, "Mãe", 0, "mae", None)
        p2 = criar_pergunta_mock(2, "Filho 1", 1, "f1", "mae")
        p3 = criar_pergunta_mock(3, "Filho 2", 2, "f2", "mae")
        p4 = criar_pergunta_mock(4, "Filho 3", 3, "f3", "mae")

        perguntas = [p1, p2, p3, p4]

        resultado, ciclos = _agrupar_por_dependencias_algoritmo(perguntas)

        ids_resultado = [item["pergunta"].id for item in resultado]
        self.assertEqual(ids_resultado, [1, 2, 3, 4])

        # Todos os filhos no nível 1
        niveis = [item["nivel"] for item in resultado]
        self.assertEqual(niveis, [0, 1, 1, 1])

    def test_cenario_5_multiplos_pais_usa_primeiro(self):
        """
        Cenário 5: multi-pai → usa o pai que aparece primeiro na ordem atual

        Nota: No modelo atual, uma pergunta só pode ter UM depends_on_variable.
        Este teste verifica que o algoritmo funciona corretamente mesmo que
        a pergunta tenha uma dependência definida, aparecendo corretamente
        como filho do pai especificado.
        """
        p1 = criar_pergunta_mock(1, "Mãe A", 0, "mae_a", None)
        p2 = criar_pergunta_mock(2, "Mãe B", 1, "mae_b", None)
        # P3 depende de mae_b (definido explicitamente)
        p3 = criar_pergunta_mock(3, "Filho com dependência", 2, "filho", "mae_b")

        perguntas = [p1, p2, p3]

        resultado, ciclos = _agrupar_por_dependencias_algoritmo(perguntas)

        ids_resultado = [item["pergunta"].id for item in resultado]
        # P1 (raiz) → P2 (raiz) → P3 (filho de B)
        self.assertEqual(ids_resultado, [1, 2, 3])

        # P3 deve estar abaixo de P2 (seu pai)
        niveis = [item["nivel"] for item in resultado]
        self.assertEqual(niveis, [0, 0, 1])

    def test_cenario_6_ciclo_detectado_sem_travar(self):
        """
        Cenário 6: ciclo → não trava, mantém ordem e gera aviso

        Entrada com ciclo:
        - P1: variável "a", depende de "b"
        - P2: variável "b", depende de "a"
        - P3: sem dependência

        O algoritmo não deve travar e deve reportar o ciclo.
        """
        p1 = criar_pergunta_mock(1, "Pergunta A", 0, "a", "b")
        p2 = criar_pergunta_mock(2, "Pergunta B", 1, "b", "a")
        p3 = criar_pergunta_mock(3, "Pergunta C", 2, "c", None)

        perguntas = [p1, p2, p3]

        resultado, ciclos = _agrupar_por_dependencias_algoritmo(perguntas)

        # Não deve travar - deve retornar todas as perguntas
        self.assertEqual(len(resultado), 3)

        # Deve ter detectado ciclos
        self.assertGreater(len(ciclos), 0)

        # Todas as perguntas devem estar no resultado
        ids_resultado = {item["pergunta"].id for item in resultado}
        self.assertEqual(ids_resultado, {1, 2, 3})

    def test_lista_vazia(self):
        """Algoritmo deve lidar com lista vazia"""
        resultado, ciclos = _agrupar_por_dependencias_algoritmo([])

        self.assertEqual(resultado, [])
        self.assertEqual(ciclos, [])

    def test_uma_pergunta(self):
        """Algoritmo deve lidar com uma única pergunta"""
        p1 = criar_pergunta_mock(1, "Única", 0, "unica", None)

        resultado, ciclos = _agrupar_por_dependencias_algoritmo([p1])

        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado[0]["pergunta"].id, 1)
        self.assertEqual(ciclos, [])

    def test_dependencia_para_variavel_inexistente(self):
        """
        Pergunta que depende de variável que não existe deve ser tratada como raiz
        """
        p1 = criar_pergunta_mock(1, "Raiz", 0, "raiz", None)
        # P2 depende de "inexistente" que não existe
        p2 = criar_pergunta_mock(2, "Órfã", 1, "orfa", "inexistente")

        perguntas = [p1, p2]

        resultado, ciclos = _agrupar_por_dependencias_algoritmo(perguntas)

        # P2 deve ser tratada como raiz já que seu pai não existe
        ids_resultado = [item["pergunta"].id for item in resultado]
        self.assertEqual(ids_resultado, [1, 2])

        # Ambas no nível 0 (raiz)
        niveis = [item["nivel"] for item in resultado]
        self.assertEqual(niveis, [0, 0])

    def test_auto_referencia_ignorada(self):
        """
        Pergunta que depende de si mesma deve ser tratada como raiz (auto-ref ignorada)
        """
        # P1 depende de "auto" que é ela mesma
        p1 = criar_pergunta_mock(1, "Auto", 0, "auto", "auto")
        p2 = criar_pergunta_mock(2, "Normal", 1, "normal", None)

        perguntas = [p1, p2]

        resultado, ciclos = _agrupar_por_dependencias_algoritmo(perguntas)

        # P1 deve ser raiz (auto-referência ignorada)
        self.assertEqual(len(resultado), 2)

        niveis = [item["nivel"] for item in resultado]
        self.assertEqual(niveis, [0, 0])

    def test_arvore_complexa(self):
        """
        Teste de árvore complexa com múltiplos níveis e ramos

        Estrutura:
        - R1 (raiz)
          - F1.1 (filho de R1)
            - N1.1.1 (neto de R1)
          - F1.2 (filho de R1)
        - R2 (raiz)
          - F2.1 (filho de R2)
        """
        r1 = criar_pergunta_mock(1, "Raiz 1", 0, "r1", None)
        r2 = criar_pergunta_mock(2, "Raiz 2", 1, "r2", None)
        f11 = criar_pergunta_mock(3, "Filho 1.1", 2, "f11", "r1")
        f12 = criar_pergunta_mock(4, "Filho 1.2", 3, "f12", "r1")
        f21 = criar_pergunta_mock(5, "Filho 2.1", 4, "f21", "r2")
        n111 = criar_pergunta_mock(6, "Neto 1.1.1", 5, "n111", "f11")

        perguntas = [r1, r2, f11, f12, f21, n111]

        resultado, ciclos = _agrupar_por_dependencias_algoritmo(perguntas)

        # Ordem esperada: R1 → F1.1 → N1.1.1 → F1.2 → R2 → F2.1
        ids_resultado = [item["pergunta"].id for item in resultado]
        self.assertEqual(ids_resultado, [1, 3, 6, 4, 2, 5])

        # Níveis esperados: 0, 1, 2, 1, 0, 1
        niveis = [item["nivel"] for item in resultado]
        self.assertEqual(niveis, [0, 1, 2, 1, 0, 1])

        self.assertEqual(len(ciclos), 0)


class TestCasosEspeciais(unittest.TestCase):
    """Testes para casos especiais e edge cases"""

    def test_nome_variavel_case_insensitive(self):
        """
        O matching de variáveis deve ser case-insensitive
        """
        p1 = criar_pergunta_mock(1, "Mãe", 0, "TipoAcao", None)
        p2 = criar_pergunta_mock(2, "Filho", 1, "filho", "tipoacao")  # lowercase

        perguntas = [p1, p2]

        resultado, ciclos = _agrupar_por_dependencias_algoritmo(perguntas)

        # P2 deve ser filho de P1
        niveis = [item["nivel"] for item in resultado]
        self.assertEqual(niveis, [0, 1])

    def test_nome_variavel_com_espacos(self):
        """
        Nomes de variáveis com espaços em branco devem ser tratados (strip)
        """
        p1 = criar_pergunta_mock(1, "Mãe", 0, " tipo ", None)
        p2 = criar_pergunta_mock(2, "Filho", 1, "filho", "tipo")

        perguntas = [p1, p2]

        resultado, ciclos = _agrupar_por_dependencias_algoritmo(perguntas)

        niveis = [item["nivel"] for item in resultado]
        self.assertEqual(niveis, [0, 1])

    def test_perguntas_sem_nome_variavel(self):
        """
        Perguntas sem nome_variavel_sugerido não podem ser pais
        """
        p1 = criar_pergunta_mock(1, "Sem variável", 0, None, None)
        p2 = criar_pergunta_mock(2, "Tenta depender", 1, "x", "sem_variavel")

        perguntas = [p1, p2]

        resultado, ciclos = _agrupar_por_dependencias_algoritmo(perguntas)

        # P2 deve ser raiz já que P1 não tem variável
        niveis = [item["nivel"] for item in resultado]
        self.assertEqual(niveis, [0, 0])


if __name__ == "__main__":
    unittest.main()
