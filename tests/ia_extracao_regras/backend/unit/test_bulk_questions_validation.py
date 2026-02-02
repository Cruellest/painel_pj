# tests/ia_extracao_regras/backend/unit/test_bulk_questions_validation.py
"""
Testes unitários para validação 1:1 do processamento de perguntas em lote.

Regra crítica: A IA NÃO PODE criar perguntas extras.
O número de perguntas retornadas DEVE ser EXATAMENTE igual ao fornecido.

Cenários testados:
1. IA retorna mais perguntas que o fornecido → REJEITA
2. IA retorna menos perguntas que o fornecido → REJEITA
3. IA retorna quantidade correta com índices válidos → ACEITA
4. IA retorna índices duplicados → REJEITA
5. IA retorna índices fora do range → REJEITA
6. Linhas vazias são corretamente ignoradas na contagem
"""

import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

from sistemas.gerador_pecas.services_dependencies import DependencyInferenceService


class TestBulkQuestionsValidation(unittest.IsolatedAsyncioTestCase):
    """Testes para validação 1:1 de perguntas em lote"""

    async def asyncSetUp(self):
        """Configuração antes de cada teste"""
        self.mock_db = MagicMock()
        self.service = DependencyInferenceService(self.mock_db)

    def _criar_resposta_ia_mock(self, perguntas_normalizadas, dependencias=None):
        """Helper para criar resposta mock da IA"""
        return {
            "perguntas_normalizadas": perguntas_normalizadas,
            "dependencias": dependencias or [],
            "ordem_recomendada": list(range(len(perguntas_normalizadas))),
            "arvore": {}
        }

    @patch('sistemas.gerador_pecas.services_dependencies.gemini_service')
    @patch('sistemas.gerador_pecas.services_dependencies.get_thinking_level')
    async def test_rejeita_quando_ia_retorna_mais_perguntas(self, mock_thinking, mock_gemini):
        """
        Cenário 1: Usuário fornece 5 perguntas, IA retorna 6.
        DEVE rejeitar e retornar erro claro.
        """
        mock_thinking.return_value = "medium"

        # IA retorna 6 perguntas quando deveria retornar 5
        resposta_ia = self._criar_resposta_ia_mock([
            {"indice": 0, "texto_final": "Pergunta 1?", "nome_base_variavel": "var1", "tipo_sugerido": "text"},
            {"indice": 1, "texto_final": "Pergunta 2?", "nome_base_variavel": "var2", "tipo_sugerido": "text"},
            {"indice": 2, "texto_final": "Pergunta 3?", "nome_base_variavel": "var3", "tipo_sugerido": "text"},
            {"indice": 3, "texto_final": "Pergunta 4?", "nome_base_variavel": "var4", "tipo_sugerido": "text"},
            {"indice": 4, "texto_final": "Pergunta 5?", "nome_base_variavel": "var5", "tipo_sugerido": "text"},
            {"indice": 5, "texto_final": "Pergunta extra inventada?", "nome_base_variavel": "var6", "tipo_sugerido": "text"},
        ])

        mock_response = MagicMock()
        mock_response.success = True
        mock_response.content = str(resposta_ia)
        mock_gemini.generate = AsyncMock(return_value=mock_response)

        # Usuário fornece 5 perguntas
        perguntas = [
            "Pergunta 1 original",
            "Pergunta 2 original",
            "Pergunta 3 original",
            "Pergunta 4 original",
            "Pergunta 5 original",
        ]

        with patch.object(self.service, '_extrair_json_resposta', return_value=resposta_ia):
            resultado = await self.service.analisar_dependencias_batch(
                perguntas=perguntas,
                nomes_variaveis=[None] * 5,
                categoria_nome="Teste"
            )

        # DEVE falhar
        self.assertFalse(resultado["success"])
        self.assertIn("retornou 6 perguntas", resultado["erro"])
        self.assertIn("fornecidas 5", resultado["erro"])

    @patch('sistemas.gerador_pecas.services_dependencies.gemini_service')
    @patch('sistemas.gerador_pecas.services_dependencies.get_thinking_level')
    async def test_rejeita_quando_ia_retorna_menos_perguntas(self, mock_thinking, mock_gemini):
        """
        Cenário: Usuário fornece 5 perguntas, IA retorna 4.
        DEVE rejeitar (IA fundiu ou removeu pergunta).
        """
        mock_thinking.return_value = "medium"

        # IA retorna apenas 4 perguntas
        resposta_ia = self._criar_resposta_ia_mock([
            {"indice": 0, "texto_final": "Pergunta 1?", "nome_base_variavel": "var1", "tipo_sugerido": "text"},
            {"indice": 1, "texto_final": "Pergunta 2?", "nome_base_variavel": "var2", "tipo_sugerido": "text"},
            {"indice": 2, "texto_final": "Pergunta 3?", "nome_base_variavel": "var3", "tipo_sugerido": "text"},
            {"indice": 3, "texto_final": "Pergunta 4?", "nome_base_variavel": "var4", "tipo_sugerido": "text"},
            # Falta a pergunta 5!
        ])

        mock_response = MagicMock()
        mock_response.success = True
        mock_response.content = str(resposta_ia)
        mock_gemini.generate = AsyncMock(return_value=mock_response)

        perguntas = [
            "Pergunta 1 original",
            "Pergunta 2 original",
            "Pergunta 3 original",
            "Pergunta 4 original",
            "Pergunta 5 original",
        ]

        with patch.object(self.service, '_extrair_json_resposta', return_value=resposta_ia):
            resultado = await self.service.analisar_dependencias_batch(
                perguntas=perguntas,
                nomes_variaveis=[None] * 5,
                categoria_nome="Teste"
            )

        # DEVE falhar
        self.assertFalse(resultado["success"])
        self.assertIn("retornou 4 perguntas", resultado["erro"])
        self.assertIn("fornecidas 5", resultado["erro"])

    @patch('sistemas.gerador_pecas.services_dependencies.gemini_service')
    @patch('sistemas.gerador_pecas.services_dependencies.get_thinking_level')
    async def test_aceita_quando_quantidade_correta_e_indices_validos(self, mock_thinking, mock_gemini):
        """
        Cenário 2: Usuário fornece 5 perguntas, IA retorna 5 com índices corretos.
        DEVE aceitar.
        """
        mock_thinking.return_value = "medium"

        # IA retorna exatamente 5 perguntas com índices corretos
        resposta_ia = self._criar_resposta_ia_mock([
            {"indice": 0, "texto_final": "Pergunta normalizada 1?", "nome_base_variavel": "var1", "tipo_sugerido": "boolean"},
            {"indice": 1, "texto_final": "Pergunta normalizada 2?", "nome_base_variavel": "var2", "tipo_sugerido": "text"},
            {"indice": 2, "texto_final": "Pergunta normalizada 3?", "nome_base_variavel": "var3", "tipo_sugerido": "choice", "opcoes_sugeridas": ["sim", "nao"]},
            {"indice": 3, "texto_final": "Pergunta normalizada 4?", "nome_base_variavel": "var4", "tipo_sugerido": "date"},
            {"indice": 4, "texto_final": "Pergunta normalizada 5?", "nome_base_variavel": "var5", "tipo_sugerido": "number"},
        ])

        mock_response = MagicMock()
        mock_response.success = True
        mock_response.content = str(resposta_ia)
        mock_gemini.generate = AsyncMock(return_value=mock_response)

        perguntas = [
            "pergunta 1 bagunçada (mãe)",
            "pergunta 2 com instrução interna",
            "pergunta 3 (depende da anterior)",
            "pergunta 4 qualquer",
            "pergunta 5 final",
        ]

        with patch.object(self.service, '_extrair_json_resposta', return_value=resposta_ia):
            resultado = await self.service.analisar_dependencias_batch(
                perguntas=perguntas,
                nomes_variaveis=[None] * 5,
                categoria_nome="Teste"
            )

        # DEVE aceitar
        self.assertTrue(resultado["success"])
        self.assertEqual(len(resultado["perguntas_normalizadas"]), 5)

    @patch('sistemas.gerador_pecas.services_dependencies.gemini_service')
    @patch('sistemas.gerador_pecas.services_dependencies.get_thinking_level')
    async def test_rejeita_quando_indices_duplicados(self, mock_thinking, mock_gemini):
        """
        Cenário: IA retorna índices duplicados (ex: dois itens com índice 2).
        DEVE rejeitar.
        """
        mock_thinking.return_value = "medium"

        # IA retorna 5 perguntas mas com índice duplicado
        resposta_ia = self._criar_resposta_ia_mock([
            {"indice": 0, "texto_final": "Pergunta 1?", "nome_base_variavel": "var1", "tipo_sugerido": "text"},
            {"indice": 1, "texto_final": "Pergunta 2?", "nome_base_variavel": "var2", "tipo_sugerido": "text"},
            {"indice": 2, "texto_final": "Pergunta 3?", "nome_base_variavel": "var3", "tipo_sugerido": "text"},
            {"indice": 2, "texto_final": "Pergunta duplicada?", "nome_base_variavel": "var3b", "tipo_sugerido": "text"},  # DUPLICADO!
            {"indice": 4, "texto_final": "Pergunta 5?", "nome_base_variavel": "var5", "tipo_sugerido": "text"},
        ])

        mock_response = MagicMock()
        mock_response.success = True
        mock_response.content = str(resposta_ia)
        mock_gemini.generate = AsyncMock(return_value=mock_response)

        perguntas = ["P1", "P2", "P3", "P4", "P5"]

        with patch.object(self.service, '_extrair_json_resposta', return_value=resposta_ia):
            resultado = await self.service.analisar_dependencias_batch(
                perguntas=perguntas,
                nomes_variaveis=[None] * 5,
                categoria_nome="Teste"
            )

        # DEVE falhar
        self.assertFalse(resultado["success"])
        self.assertIn("duplicados", resultado["erro"].lower())

    @patch('sistemas.gerador_pecas.services_dependencies.gemini_service')
    @patch('sistemas.gerador_pecas.services_dependencies.get_thinking_level')
    async def test_rejeita_quando_indice_fora_do_range(self, mock_thinking, mock_gemini):
        """
        Cenário 4: IA retorna índice fora do range [0, N-1].
        DEVE rejeitar.
        """
        mock_thinking.return_value = "medium"

        # IA retorna índice 10 quando só existem índices 0-4
        resposta_ia = self._criar_resposta_ia_mock([
            {"indice": 0, "texto_final": "Pergunta 1?", "nome_base_variavel": "var1", "tipo_sugerido": "text"},
            {"indice": 1, "texto_final": "Pergunta 2?", "nome_base_variavel": "var2", "tipo_sugerido": "text"},
            {"indice": 2, "texto_final": "Pergunta 3?", "nome_base_variavel": "var3", "tipo_sugerido": "text"},
            {"indice": 3, "texto_final": "Pergunta 4?", "nome_base_variavel": "var4", "tipo_sugerido": "text"},
            {"indice": 10, "texto_final": "Pergunta com índice inválido?", "nome_base_variavel": "var5", "tipo_sugerido": "text"},  # INVÁLIDO!
        ])

        mock_response = MagicMock()
        mock_response.success = True
        mock_response.content = str(resposta_ia)
        mock_gemini.generate = AsyncMock(return_value=mock_response)

        perguntas = ["P1", "P2", "P3", "P4", "P5"]

        with patch.object(self.service, '_extrair_json_resposta', return_value=resposta_ia):
            resultado = await self.service.analisar_dependencias_batch(
                perguntas=perguntas,
                nomes_variaveis=[None] * 5,
                categoria_nome="Teste"
            )

        # DEVE falhar
        self.assertFalse(resultado["success"])
        self.assertIn("inválidos", resultado["erro"].lower())

    @patch('sistemas.gerador_pecas.services_dependencies.gemini_service')
    @patch('sistemas.gerador_pecas.services_dependencies.get_thinking_level')
    async def test_rejeita_quando_indice_negativo(self, mock_thinking, mock_gemini):
        """
        Cenário: IA retorna índice negativo.
        DEVE rejeitar.
        """
        mock_thinking.return_value = "medium"

        resposta_ia = self._criar_resposta_ia_mock([
            {"indice": -1, "texto_final": "Pergunta?", "nome_base_variavel": "var1", "tipo_sugerido": "text"},  # NEGATIVO!
            {"indice": 1, "texto_final": "Pergunta 2?", "nome_base_variavel": "var2", "tipo_sugerido": "text"},
            {"indice": 2, "texto_final": "Pergunta 3?", "nome_base_variavel": "var3", "tipo_sugerido": "text"},
        ])

        mock_response = MagicMock()
        mock_response.success = True
        mock_response.content = str(resposta_ia)
        mock_gemini.generate = AsyncMock(return_value=mock_response)

        perguntas = ["P1", "P2", "P3"]

        with patch.object(self.service, '_extrair_json_resposta', return_value=resposta_ia):
            resultado = await self.service.analisar_dependencias_batch(
                perguntas=perguntas,
                nomes_variaveis=[None] * 3,
                categoria_nome="Teste"
            )

        # DEVE falhar
        self.assertFalse(resultado["success"])
        self.assertIn("inválidos", resultado["erro"].lower())

    @patch('sistemas.gerador_pecas.services_dependencies.gemini_service')
    @patch('sistemas.gerador_pecas.services_dependencies.get_thinking_level')
    async def test_rejeita_quando_faltam_indices(self, mock_thinking, mock_gemini):
        """
        Cenário: IA retorna quantidade correta mas faltam alguns índices.
        DEVE rejeitar.
        """
        mock_thinking.return_value = "medium"

        # 5 perguntas, mas falta o índice 3
        resposta_ia = self._criar_resposta_ia_mock([
            {"indice": 0, "texto_final": "Pergunta 1?", "nome_base_variavel": "var1", "tipo_sugerido": "text"},
            {"indice": 1, "texto_final": "Pergunta 2?", "nome_base_variavel": "var2", "tipo_sugerido": "text"},
            {"indice": 2, "texto_final": "Pergunta 3?", "nome_base_variavel": "var3", "tipo_sugerido": "text"},
            # Falta índice 3!
            {"indice": 4, "texto_final": "Pergunta 5?", "nome_base_variavel": "var5", "tipo_sugerido": "text"},
            {"indice": 5, "texto_final": "Pergunta extra?", "nome_base_variavel": "var6", "tipo_sugerido": "text"},  # Índice 5 não existe
        ])

        mock_response = MagicMock()
        mock_response.success = True
        mock_response.content = str(resposta_ia)
        mock_gemini.generate = AsyncMock(return_value=mock_response)

        perguntas = ["P1", "P2", "P3", "P4", "P5"]

        with patch.object(self.service, '_extrair_json_resposta', return_value=resposta_ia):
            resultado = await self.service.analisar_dependencias_batch(
                perguntas=perguntas,
                nomes_variaveis=[None] * 5,
                categoria_nome="Teste"
            )

        # DEVE falhar (índice 5 está fora do range)
        self.assertFalse(resultado["success"])

class TestLinhasVazias(unittest.TestCase):
    """Testes síncronos para validação de linhas vazias"""

    def test_linhas_vazias_sao_ignoradas_antes_do_envio(self):
        """
        Cenário 3: Linhas vazias devem ser ignoradas e N contabiliza corretamente.
        Este teste valida a lógica do frontend que filtra linhas vazias.
        """
        # Simula o comportamento do frontend
        texto_usuario = """
        Pergunta 1?

        Pergunta 2?


        Pergunta 3?
        """

        # Lógica do frontend: filtra linhas vazias
        linhas = [l.strip() for l in texto_usuario.split('\n') if l.strip()]

        # DEVE ter exatamente 3 perguntas após filtrar vazias
        self.assertEqual(len(linhas), 3)
        self.assertEqual(linhas[0], "Pergunta 1?")
        self.assertEqual(linhas[1], "Pergunta 2?")
        self.assertEqual(linhas[2], "Pergunta 3?")


class TestBulkQuestionsValidationAsync(unittest.IsolatedAsyncioTestCase):
    """Testes assíncronos para validação 1:1"""

    async def asyncSetUp(self):
        """Configuração assíncrona"""
        self.mock_db = MagicMock()
        self.service = DependencyInferenceService(self.mock_db)

    async def test_lista_vazia_retorna_sucesso(self):
        """Lista vazia de perguntas deve retornar sucesso com maps vazios"""
        resultado = await self.service.analisar_dependencias_batch(
            perguntas=[],
            nomes_variaveis=[],
            categoria_nome="Teste"
        )

        self.assertTrue(resultado["success"])
        self.assertEqual(resultado["perguntas_normalizadas"], {})
        self.assertEqual(resultado["dependencias"], {})


if __name__ == '__main__':
    unittest.main()
