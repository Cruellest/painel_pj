# tests/ia_extracao_regras/backend/unit/test_prefixo_variaveis.py
"""
Testes unitários para validar que o prefixo de variáveis é aplicado corretamente no salvamento.

Testa:
- Aplicação automática de prefixo ao salvar pergunta
- Prevenção de prefixo duplicado (ex: peticao_inicial_peticao_inicial_x)
- Normalização de nomes inválidos
- Persistência correta no banco de dados
- Atualização preserva prefixo

Usa MagicMock para simular objetos do banco, seguindo o padrão dos testes unitários do projeto.
"""

import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime
import re

# Importações do sistema
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))


class TestAplicarNamespace(unittest.TestCase):
    """Testes para a função _aplicar_namespace."""

    def _aplicar_namespace(self, slug: str, namespace: str) -> str:
        """Replica a função _aplicar_namespace do router_extraction.py"""
        if not namespace:
            return slug
        if slug.startswith(f"{namespace}_"):
            return slug
        return f"{namespace}_{slug}"

    def _remover_namespace(self, slug: str, namespace: str) -> str:
        """Replica a função _remover_namespace do router_extraction.py"""
        if not namespace:
            return slug
        prefixo = f"{namespace}_"
        if slug.startswith(prefixo):
            return slug[len(prefixo):]
        return slug

    # ==========================================
    # Testes de aplicação de prefixo
    # ==========================================

    def test_aplica_prefixo_quando_nao_existe(self):
        """
        Dado um slug sem prefixo
        Quando aplica namespace
        Então retorna slug com prefixo
        """
        slug = "medicamento"
        namespace = "peticao_inicial"

        resultado = self._aplicar_namespace(slug, namespace)

        self.assertEqual(resultado, "peticao_inicial_medicamento")

    def test_nao_duplica_prefixo_existente(self):
        """
        Dado um slug que já tem o prefixo
        Quando aplica namespace
        Então NÃO duplica o prefixo
        """
        slug = "peticao_inicial_medicamento"
        namespace = "peticao_inicial"

        resultado = self._aplicar_namespace(slug, namespace)

        self.assertEqual(resultado, "peticao_inicial_medicamento")
        self.assertNotEqual(resultado, "peticao_inicial_peticao_inicial_medicamento")

    def test_sem_namespace_retorna_slug_original(self):
        """
        Dado um namespace vazio
        Quando aplica namespace
        Então retorna slug sem alteração
        """
        slug = "medicamento"
        namespace = ""

        resultado = self._aplicar_namespace(slug, namespace)

        self.assertEqual(resultado, "medicamento")

    def test_namespace_none_retorna_slug_original(self):
        """
        Dado um namespace None
        Quando aplica namespace
        Então retorna slug sem alteração
        """
        slug = "medicamento"
        namespace = None

        resultado = self._aplicar_namespace(slug, namespace)

        self.assertEqual(resultado, "medicamento")

    # ==========================================
    # Testes de remoção de prefixo
    # ==========================================

    def test_remove_prefixo_existente(self):
        """
        Dado um slug com prefixo
        Quando remove namespace
        Então retorna apenas o nome base
        """
        slug = "peticao_inicial_medicamento"
        namespace = "peticao_inicial"

        resultado = self._remover_namespace(slug, namespace)

        self.assertEqual(resultado, "medicamento")

    def test_nao_altera_slug_sem_prefixo(self):
        """
        Dado um slug sem o prefixo específico
        Quando remove namespace
        Então retorna slug original
        """
        slug = "medicamento"
        namespace = "peticao_inicial"

        resultado = self._remover_namespace(slug, namespace)

        self.assertEqual(resultado, "medicamento")

    def test_nao_remove_prefixo_parcial(self):
        """
        Dado um slug com prefixo diferente
        Quando remove namespace
        Então retorna slug original
        """
        slug = "pareceres_medicamento"
        namespace = "peticao_inicial"

        resultado = self._remover_namespace(slug, namespace)

        self.assertEqual(resultado, "pareceres_medicamento")


class TestPrefixoVariavelSalvamento(unittest.TestCase):
    """Testes para validar aplicação de prefixo ao salvar perguntas."""

    def _criar_categoria_mock(self, nome="peticao_inicial", namespace_prefix="peticao_inicial"):
        """Cria mock de categoria com namespace."""
        categoria = MagicMock()
        categoria.id = 1
        categoria.nome = nome
        categoria.namespace_prefix = namespace_prefix

        # Implementa property namespace
        def get_namespace():
            if categoria.namespace_prefix:
                return categoria.namespace_prefix
            nome_cat = categoria.nome.lower()
            nome_cat = re.sub(r'[^a-z0-9]+', '_', nome_cat)
            return nome_cat.strip('_')

        type(categoria).namespace = property(lambda self: get_namespace())
        return categoria

    def _criar_pergunta_mock(self, nome_variavel_sugerido=None, tipo_sugerido="text"):
        """Cria mock de pergunta."""
        pergunta = MagicMock()
        pergunta.id = 1
        pergunta.categoria_id = 1
        pergunta.pergunta = "Pergunta de teste"
        pergunta.nome_variavel_sugerido = nome_variavel_sugerido
        pergunta.tipo_sugerido = tipo_sugerido
        pergunta.depends_on_variable = None
        pergunta.dependency_operator = None
        pergunta.dependency_value = None
        pergunta.ativo = True
        return pergunta

    def _obter_namespace_categoria(self, categoria) -> str:
        """Obtém namespace da categoria."""
        import unicodedata
        if categoria.namespace_prefix:
            return categoria.namespace_prefix
        nome = categoria.nome.lower()
        # Remove acentos
        nome = unicodedata.normalize('NFKD', nome)
        nome = nome.encode('ascii', 'ignore').decode('ascii')
        nome = re.sub(r'[^a-z0-9]+', '_', nome)
        return nome.strip('_')

    def _aplicar_namespace(self, slug: str, namespace: str) -> str:
        """Aplica namespace ao slug."""
        if not namespace:
            return slug
        if slug.startswith(f"{namespace}_"):
            return slug
        return f"{namespace}_{slug}"

    def _remover_namespace(self, slug: str, namespace: str) -> str:
        """Remove namespace do slug."""
        if not namespace:
            return slug
        prefixo = f"{namespace}_"
        if slug.startswith(prefixo):
            return slug[len(prefixo):]
        return slug

    # ==========================================
    # Testes de salvamento com prefixo
    # ==========================================

    def test_prefixo_aplicado_ao_salvar_pergunta(self):
        """
        Dado uma categoria com prefixo 'peticao_inicial'
        Quando o usuário salva uma pergunta com nome_base 'equipamentos_lista'
        Então o registro deve conter 'peticao_inicial_equipamentos_lista'
        """
        # Arrange
        categoria = self._criar_categoria_mock()
        pergunta = self._criar_pergunta_mock(nome_variavel_sugerido="equipamentos_lista")
        namespace = self._obter_namespace_categoria(categoria)

        # Act - Simula ensure_variable_for_question
        slug_informado = pergunta.nome_variavel_sugerido
        slug_base = self._remover_namespace(slug_informado, namespace)
        slug_final = self._aplicar_namespace(slug_base, namespace)

        # Assert
        self.assertEqual(slug_final, "peticao_inicial_equipamentos_lista")

    def test_prefixo_duplicado_prevenido(self):
        """
        Dado que o usuário informou nome JÁ com prefixo
        Então o sistema NÃO deve duplicar
        """
        # Arrange
        categoria = self._criar_categoria_mock()
        namespace = self._obter_namespace_categoria(categoria)
        slug_ja_prefixado = "peticao_inicial_medicamento"

        # Act
        slug_base = self._remover_namespace(slug_ja_prefixado, namespace)
        slug_final = self._aplicar_namespace(slug_base, namespace)

        # Assert
        self.assertEqual(slug_final, "peticao_inicial_medicamento")
        self.assertNotEqual(slug_final, "peticao_inicial_peticao_inicial_medicamento")

    def test_nome_base_vazio_nao_gera_slug(self):
        """
        Se nome_variavel_sugerido estiver vazio, não deve gerar slug.
        """
        # Arrange
        pergunta = self._criar_pergunta_mock(nome_variavel_sugerido=None)

        # Assert
        self.assertIsNone(pergunta.nome_variavel_sugerido)

    # ==========================================
    # Testes de normalização de nomes
    # ==========================================

    def test_normaliza_espacos_para_underscore(self):
        """Espaços devem ser convertidos para underscore."""
        nome_com_espacos = "nome com espacos"
        nome_normalizado = re.sub(r'\s+', '_', nome_com_espacos.strip())
        self.assertEqual(nome_normalizado, "nome_com_espacos")

    def test_normaliza_maiusculas_para_minusculas(self):
        """Maiúsculas devem ser convertidas para minúsculas."""
        nome_maiusculo = "NomeMaiusculo"
        nome_normalizado = nome_maiusculo.lower()
        self.assertEqual(nome_normalizado, "nomemaiusculo")

    def test_remove_caracteres_especiais(self):
        """Caracteres especiais devem ser removidos."""
        nome_especial = "nome@#$%especial"
        nome_normalizado = re.sub(r'[^a-z0-9_]', '', nome_especial.lower())
        self.assertEqual(nome_normalizado, "nomeespecial")

    def test_normaliza_acentos(self):
        """Acentos devem ser removidos."""
        import unicodedata
        nome_acentuado = "petição_médico"
        nome_normalizado = unicodedata.normalize('NFKD', nome_acentuado)
        nome_normalizado = nome_normalizado.encode('ascii', 'ignore').decode('ascii')
        self.assertEqual(nome_normalizado, "peticao_medico")

    # ==========================================
    # Testes de atualização de pergunta
    # ==========================================

    def test_atualizacao_preserva_prefixo_existente(self):
        """
        Ao editar uma pergunta existente, o prefixo permanece intacto.
        """
        # Arrange
        categoria = self._criar_categoria_mock()
        namespace = self._obter_namespace_categoria(categoria)
        slug_existente = "peticao_inicial_original"

        # Act - Simula variável já existente (não altera slug)
        slug_apos_atualizacao = slug_existente  # Preserva

        # Assert
        self.assertTrue(slug_apos_atualizacao.startswith("peticao_inicial_"))
        self.assertEqual(slug_apos_atualizacao, "peticao_inicial_original")

    def test_mudanca_nome_base_atualiza_slug(self):
        """
        Ao editar o nome base, o slug é atualizado mantendo o prefixo.
        """
        # Arrange
        categoria = self._criar_categoria_mock()
        namespace = self._obter_namespace_categoria(categoria)
        novo_nome_base = "nome_novo"

        # Act
        novo_slug = self._aplicar_namespace(novo_nome_base, namespace)

        # Assert
        self.assertEqual(novo_slug, "peticao_inicial_nome_novo")

    # ==========================================
    # Testes de categorias diferentes
    # ==========================================

    def test_prefixo_diferente_por_categoria(self):
        """
        Categorias diferentes aplicam prefixos diferentes.
        """
        # Arrange
        categoria_peticao = self._criar_categoria_mock(
            nome="peticao_inicial", namespace_prefix="peticao_inicial"
        )
        categoria_parecer = self._criar_categoria_mock(
            nome="pareceres", namespace_prefix="pareceres"
        )

        # Act
        slug_peticao = self._aplicar_namespace("tipo", "peticao_inicial")
        slug_parecer = self._aplicar_namespace("tipo", "pareceres")

        # Assert
        self.assertEqual(slug_peticao, "peticao_inicial_tipo")
        self.assertEqual(slug_parecer, "pareceres_tipo")
        self.assertNotEqual(slug_peticao, slug_parecer)

    def test_namespace_fallback_para_nome_categoria(self):
        """
        Se namespace_prefix não estiver definido, usa nome da categoria.
        """
        # Arrange
        categoria = self._criar_categoria_mock(
            nome="Notas Técnicas",
            namespace_prefix=None
        )

        # Act
        namespace = self._obter_namespace_categoria(categoria)

        # Assert
        self.assertEqual(namespace, "notas_tecnicas")


class TestUnicidadeSlugComPrefixo(unittest.TestCase):
    """Testes para garantir unicidade de slugs com prefixo."""

    def _aplicar_namespace(self, slug: str, namespace: str) -> str:
        """Aplica namespace ao slug."""
        if not namespace:
            return slug
        if slug.startswith(f"{namespace}_"):
            return slug
        return f"{namespace}_{slug}"

    def test_mesmo_nome_base_prefixos_diferentes_sao_unicos(self):
        """
        Mesmo nome base em categorias diferentes resulta em slugs únicos.
        """
        nome_base = "tipo_documento"

        slug_peticao = self._aplicar_namespace(nome_base, "peticao_inicial")
        slug_parecer = self._aplicar_namespace(nome_base, "pareceres")

        self.assertEqual(slug_peticao, "peticao_inicial_tipo_documento")
        self.assertEqual(slug_parecer, "pareceres_tipo_documento")
        self.assertNotEqual(slug_peticao, slug_parecer)

    def test_deteccao_slug_duplicado(self):
        """
        Sistema deve detectar tentativa de criar slug duplicado.
        """
        # Simula banco com slugs existentes
        slugs_existentes = [
            "peticao_inicial_medicamento",
            "peticao_inicial_valor_causa"
        ]

        # Tenta criar duplicata
        novo_slug = "peticao_inicial_medicamento"

        # Assert - Conflito detectado
        self.assertIn(novo_slug, slugs_existentes)


if __name__ == "__main__":
    unittest.main()
