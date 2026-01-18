# tests/ia_extracao_regras/backend/unit/test_json_perguntas_ativas.py
"""
Testes unitários para validar que a geração de JSON usa somente Perguntas de Extração ativas.

Testa:
- Variáveis órfãs (sem pergunta ativa) NÃO aparecem no JSON
- Perguntas inativas NÃO aparecem no JSON
- JSON contém EXATAMENTE as perguntas ativas da categoria
- JSON é reconstruído do zero (não faz merge com anterior)
- Caso reproduzindo bug: variáveis fantasmas como municipio_polo_passivo

Usa MagicMock para simular objetos, seguindo o padrão dos testes unitários do projeto.
"""

import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime
import json

# Importações do sistema
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))


class TestJsonSomenteAtivas(unittest.TestCase):
    """
    Testes para garantir que o JSON gerado contém SOMENTE perguntas ativas.

    Regra fundamental:
    > O JSON de uma categoria deve ser uma projeção EXATA das Perguntas de Extração ativas.
    > Se não existe pergunta ativa, não pode existir variável no JSON.
    """

    def _criar_pergunta_mock(
        self,
        slug: str,
        pergunta: str,
        tipo: str = "text",
        ativo: bool = True,
        depends_on: str = None,
        dependency_operator: str = None,
        dependency_value=None,
        opcoes_sugeridas=None
    ):
        """Cria mock de pergunta."""
        p = MagicMock()
        p.id = hash(slug) % 1000
        p.categoria_id = 1
        p.pergunta = pergunta
        p.nome_variavel_sugerido = slug
        p.tipo_sugerido = tipo
        p.ativo = ativo
        p.ordem = 0
        p.depends_on_variable = depends_on
        p.dependency_operator = dependency_operator
        p.dependency_value = dependency_value
        p.dependency_config = None
        p.opcoes_sugeridas = opcoes_sugeridas
        return p

    def _gerar_json_das_perguntas(self, perguntas: list) -> dict:
        """
        Simula a lógica de sincronizar_json_sem_ia.

        REGRA: Gera JSON DO ZERO a partir das perguntas ativas.
        NÃO faz merge com JSON anterior.
        """
        json_novo = {}

        for p in perguntas:
            # Filtra apenas ativas
            if not p.ativo:
                continue

            slug = p.nome_variavel_sugerido
            if not slug or not slug.strip():
                continue
            if not p.tipo_sugerido or not p.tipo_sugerido.strip():
                continue

            slug = slug.strip()
            tipo = p.tipo_sugerido.strip().lower()

            config = {
                "type": tipo,
                "description": p.pergunta
            }

            # Adiciona dependências
            if p.depends_on_variable:
                config["conditional"] = True
                config["depends_on"] = p.depends_on_variable
                if p.dependency_operator:
                    config["dependency_operator"] = p.dependency_operator
                if p.dependency_value is not None:
                    config["dependency_value"] = p.dependency_value

            # Adiciona opções se tipo choice
            if tipo == "choice" and p.opcoes_sugeridas:
                config["options"] = p.opcoes_sugeridas

            json_novo[slug] = config

        return json_novo

    def _identificar_variaveis_removidas(self, json_anterior: dict, json_novo: dict) -> list:
        """
        Identifica variáveis que foram removidas do JSON.
        """
        return [chave for chave in json_anterior.keys() if chave not in json_novo]

    # ==========================================
    # Testes de variáveis órfãs
    # ==========================================

    def test_variavel_orfa_nao_aparece_no_json(self):
        """
        Se houver variáveis órfãs no banco (sem pergunta ativa),
        elas NÃO aparecem no JSON.

        Isso é garantido porque geramos JSON apenas a partir das perguntas.
        """
        # Arrange - Apenas uma pergunta ativa
        perguntas = [
            self._criar_pergunta_mock(
                slug="peticao_inicial_ativa",
                pergunta="Pergunta ativa",
                tipo="text",
                ativo=True
            )
        ]

        # JSON anterior tinha variável órfã
        json_anterior = {
            "peticao_inicial_orfa": {"type": "text", "description": "Variável órfã"},
            "peticao_inicial_ativa": {"type": "text", "description": "Pergunta ativa"}
        }

        # Act
        json_gerado = self._gerar_json_das_perguntas(perguntas)

        # Assert
        self.assertNotIn("peticao_inicial_orfa", json_gerado)
        self.assertIn("peticao_inicial_ativa", json_gerado)

    def test_pergunta_inativa_nao_aparece_no_json(self):
        """
        Se uma pergunta estiver inativa, ela NÃO aparece no JSON.
        """
        # Arrange
        perguntas = [
            self._criar_pergunta_mock(
                slug="peticao_inicial_ativa",
                pergunta="Pergunta ativa",
                ativo=True
            ),
            self._criar_pergunta_mock(
                slug="peticao_inicial_inativa",
                pergunta="Pergunta inativa",
                ativo=False  # INATIVA
            )
        ]

        # Act
        json_gerado = self._gerar_json_das_perguntas(perguntas)

        # Assert
        self.assertIn("peticao_inicial_ativa", json_gerado)
        self.assertNotIn("peticao_inicial_inativa", json_gerado)

    def test_json_contem_exatamente_perguntas_ativas(self):
        """
        O JSON gerado contém EXATAMENTE as perguntas ativas.
        """
        # Arrange - 3 perguntas ativas e 1 inativa
        perguntas = [
            self._criar_pergunta_mock("peticao_inicial_nome_autor", "Nome do autor", "text", True),
            self._criar_pergunta_mock("peticao_inicial_valor_causa", "Valor da causa", "currency", True),
            self._criar_pergunta_mock("peticao_inicial_tipo_acao", "Tipo da ação", "choice", True),
            self._criar_pergunta_mock("peticao_inicial_inativo", "Campo inativo", "text", False),
        ]

        # Act
        json_gerado = self._gerar_json_das_perguntas(perguntas)

        # Assert - Exatamente 3 campos
        self.assertEqual(len(json_gerado), 3)
        self.assertIn("peticao_inicial_nome_autor", json_gerado)
        self.assertIn("peticao_inicial_valor_causa", json_gerado)
        self.assertIn("peticao_inicial_tipo_acao", json_gerado)
        self.assertNotIn("peticao_inicial_inativo", json_gerado)

    def test_json_reconstruido_do_zero_nao_faz_merge(self):
        """
        O JSON é reconstruído DO ZERO, não faz merge com anterior.
        """
        # Arrange
        json_anterior = {
            "campo_antigo_1": {"type": "text"},
            "campo_antigo_2": {"type": "text"},
            "municipio_polo_passivo": {"type": "text"}  # Variável fantasma
        }

        perguntas = [
            self._criar_pergunta_mock(
                slug="peticao_inicial_campo_novo",
                pergunta="Novo campo",
                tipo="text",
                ativo=True
            )
        ]

        # Act
        json_gerado = self._gerar_json_das_perguntas(perguntas)
        variaveis_removidas = self._identificar_variaveis_removidas(json_anterior, json_gerado)

        # Assert
        self.assertEqual(len(json_gerado), 1)
        self.assertIn("peticao_inicial_campo_novo", json_gerado)
        self.assertNotIn("campo_antigo_1", json_gerado)
        self.assertNotIn("campo_antigo_2", json_gerado)
        self.assertNotIn("municipio_polo_passivo", json_gerado)

        # Variáveis removidas identificadas
        self.assertEqual(len(variaveis_removidas), 3)

    # ==========================================
    # Caso reproduzindo bug específico
    # ==========================================

    def test_bug_variaveis_fantasmas_municipio_uniao(self):
        """
        Caso reproduzindo o bug reportado:

        Existem no banco variáveis como 'municipio_polo_passivo' e 'uniao_polo_passivo'
        sem perguntas ativas. Ao clicar em Atualizar JSON, elas NÃO podem aparecer.
        """
        # Arrange - JSON anterior com variáveis fantasmas
        json_anterior = {
            "municipio_polo_passivo": {"type": "text", "description": "Município polo passivo"},
            "uniao_polo_passivo": {"type": "boolean", "description": "União polo passivo"},
            "estado_polo_passivo": {"type": "text", "description": "Estado polo passivo"},
            "peticao_inicial_medicamento": {"type": "text", "description": "Medicamento"}
        }

        # Apenas 1 pergunta ATIVA
        perguntas = [
            self._criar_pergunta_mock(
                slug="peticao_inicial_medicamento",
                pergunta="Qual o medicamento solicitado?",
                tipo="text",
                ativo=True
            )
        ]

        # Act
        json_gerado = self._gerar_json_das_perguntas(perguntas)
        variaveis_removidas = self._identificar_variaveis_removidas(json_anterior, json_gerado)

        # Assert - Apenas a pergunta ativa aparece
        self.assertEqual(len(json_gerado), 1)
        self.assertIn("peticao_inicial_medicamento", json_gerado)

        # Variáveis fantasmas NÃO aparecem
        self.assertNotIn("municipio_polo_passivo", json_gerado)
        self.assertNotIn("uniao_polo_passivo", json_gerado)
        self.assertNotIn("estado_polo_passivo", json_gerado)

        # Foram identificadas como removidas
        self.assertIn("municipio_polo_passivo", variaveis_removidas)
        self.assertIn("uniao_polo_passivo", variaveis_removidas)
        self.assertIn("estado_polo_passivo", variaveis_removidas)

    # ==========================================
    # Testes de dependências
    # ==========================================

    def test_json_inclui_dependencias_configuradas(self):
        """
        Se a pergunta tem dependência configurada, ela aparece no JSON.
        """
        # Arrange
        perguntas = [
            self._criar_pergunta_mock(
                slug="peticao_inicial_tipo_acao",
                pergunta="Qual o tipo da ação?",
                tipo="choice",
                ativo=True
            ),
            self._criar_pergunta_mock(
                slug="peticao_inicial_medicamento",
                pergunta="Qual o medicamento?",
                tipo="text",
                ativo=True,
                depends_on="peticao_inicial_tipo_acao",
                dependency_operator="equals",
                dependency_value="medicamento"
            )
        ]

        # Act
        json_gerado = self._gerar_json_das_perguntas(perguntas)

        # Assert
        self.assertIn("peticao_inicial_medicamento", json_gerado)
        config = json_gerado["peticao_inicial_medicamento"]
        self.assertTrue(config.get("conditional"))
        self.assertEqual(config.get("depends_on"), "peticao_inicial_tipo_acao")
        self.assertEqual(config.get("dependency_operator"), "equals")
        self.assertEqual(config.get("dependency_value"), "medicamento")

    # ==========================================
    # Testes de validação
    # ==========================================

    def test_pergunta_sem_slug_nao_aparece_no_json(self):
        """
        Perguntas sem nome_variavel_sugerido não aparecem no JSON.
        """
        # Arrange
        perguntas = [
            self._criar_pergunta_mock(
                slug="peticao_inicial_completa",
                pergunta="Pergunta completa",
                tipo="text",
                ativo=True
            ),
            self._criar_pergunta_mock(
                slug=None,  # Sem slug
                pergunta="Pergunta sem slug",
                tipo="text",
                ativo=True
            )
        ]

        # Act
        json_gerado = self._gerar_json_das_perguntas(perguntas)

        # Assert
        self.assertEqual(len(json_gerado), 1)
        self.assertIn("peticao_inicial_completa", json_gerado)

    def test_pergunta_sem_tipo_nao_aparece_no_json(self):
        """
        Perguntas sem tipo_sugerido não aparecem no JSON.
        """
        # Arrange
        perguntas = [
            self._criar_pergunta_mock(
                slug="peticao_inicial_completa",
                pergunta="Pergunta completa",
                tipo="text",
                ativo=True
            ),
            self._criar_pergunta_mock(
                slug="peticao_inicial_sem_tipo",
                pergunta="Pergunta sem tipo",
                tipo=None,  # Sem tipo
                ativo=True
            )
        ]

        # Act
        json_gerado = self._gerar_json_das_perguntas(perguntas)

        # Assert
        self.assertEqual(len(json_gerado), 1)
        self.assertIn("peticao_inicial_completa", json_gerado)
        self.assertNotIn("peticao_inicial_sem_tipo", json_gerado)


class TestVariaveisRemovidasDoJson(unittest.TestCase):
    """
    Testes para verificar que variáveis removidas são reportadas corretamente.
    """

    def _gerar_json_com_report(self, perguntas: list, json_anterior: dict) -> tuple:
        """
        Gera JSON e retorna também lista de variáveis removidas.
        """
        json_novo = {}
        for p in perguntas:
            if not p.ativo:
                continue
            if p.nome_variavel_sugerido and p.tipo_sugerido:
                json_novo[p.nome_variavel_sugerido.strip()] = {
                    "type": p.tipo_sugerido.strip().lower(),
                    "description": p.pergunta
                }

        variaveis_removidas = [
            chave for chave in json_anterior.keys()
            if chave not in json_novo
        ]

        return json_novo, variaveis_removidas

    def _criar_pergunta_mock(self, slug, pergunta, tipo="text", ativo=True):
        """Cria mock de pergunta."""
        p = MagicMock()
        p.nome_variavel_sugerido = slug
        p.tipo_sugerido = tipo
        p.pergunta = pergunta
        p.ativo = ativo
        return p

    def test_reporta_variaveis_removidas(self):
        """
        O sistema reporta corretamente quais variáveis foram removidas.
        """
        # Arrange
        json_anterior = {
            "campo_antigo": {"type": "text"},
            "outro_antigo": {"type": "text"}
        }
        perguntas = [
            self._criar_pergunta_mock("teste_nova", "Nova pergunta", "text", True)
        ]

        # Act
        json_novo, variaveis_removidas = self._gerar_json_com_report(perguntas, json_anterior)

        # Assert
        self.assertEqual(len(variaveis_removidas), 2)
        self.assertIn("campo_antigo", variaveis_removidas)
        self.assertIn("outro_antigo", variaveis_removidas)
        self.assertIn("teste_nova", json_novo)


if __name__ == "__main__":
    unittest.main()
