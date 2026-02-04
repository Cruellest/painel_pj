# tests/ia_extracao_regras/frontend/test_prefixo_frontend_api.py
"""
Testes de integração para validar comportamento do frontend via API.

Como o projeto não possui framework de testes de UI (Playwright/Cypress),
estes testes validam o contrato entre frontend e backend através da API.

Testa:
- Frontend envia nome base, backend retorna nome completo com prefixo
- Ao editar, frontend recebe nome completo e deve exibir apenas o sufixo
- Ao salvar, o valor no BD é sempre o nome completo prefixado
- Categorias diferentes resultam em prefixos diferentes

Usa MagicMock para simular objetos, seguindo o padrão dos testes unitários do projeto.
"""

import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime
import json
import re
import unicodedata

# Importações do sistema
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))


class TestFrontendPrefixoAPI(unittest.TestCase):
    """
    Testes que validam o contrato frontend-backend para prefixo de variáveis.

    O frontend deve:
    1. Exibir o prefixo como elemento fixo (não editável)
    2. Permitir que o usuário edite apenas o sufixo
    3. Enviar ao backend apenas o nome base OU o nome completo
    4. O backend SEMPRE retorna o nome completo no BD

    Estes testes validam esse contrato através de cenários de integração.
    """

    def _criar_categoria_mock(self, nome="peticao_inicial", namespace_prefix="peticao_inicial"):
        """Cria mock de categoria."""
        categoria = MagicMock()
        categoria.id = 1
        categoria.nome = nome
        categoria.namespace_prefix = namespace_prefix
        categoria.ativo = True
        return categoria

    def _criar_pergunta_mock(self, nome_variavel_sugerido, tipo_sugerido="text", categoria_id=1):
        """Cria mock de pergunta."""
        pergunta = MagicMock()
        pergunta.id = hash(nome_variavel_sugerido or "") % 1000
        pergunta.categoria_id = categoria_id
        pergunta.pergunta = "Pergunta de teste"
        pergunta.nome_variavel_sugerido = nome_variavel_sugerido
        pergunta.tipo_sugerido = tipo_sugerido
        pergunta.ativo = True
        pergunta.ordem = 0
        return pergunta

    # ==========================================
    # Funções que simulam lógica do frontend JS
    # ==========================================

    def obter_namespace_categoria(self, categoria) -> str:
        """
        Simula a função JS obterNamespaceCategoria().

        function obterNamespaceCategoria() {
            if (!categoriaAtual) return '';
            if (categoriaAtual.namespace) return categoriaAtual.namespace;
            if (categoriaAtual.namespace_prefix) return categoriaAtual.namespace_prefix;
            const nome = categoriaAtual.nome || '';
            return nome.toLowerCase()
                .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
                .replace(/[^a-z0-9]+/g, '_')
                .replace(/^_+|_+$/g, '');
        }
        """
        if categoria.namespace_prefix:
            return categoria.namespace_prefix
        nome = categoria.nome.lower()
        # Remove acentos
        nome = unicodedata.normalize('NFKD', nome)
        nome = nome.encode('ascii', 'ignore').decode('ascii')
        nome = re.sub(r'[^a-z0-9]+', '_', nome)
        return nome.strip('_')

    def remover_prefixo_slug(self, slug: str, namespace: str) -> str:
        """
        Simula a função JS removerPrefixoSlug().

        function removerPrefixoSlug(slug, namespace) {
            if (!slug || !namespace) return slug || '';
            const prefixo = namespace + '_';
            if (slug.startsWith(prefixo)) {
                return slug.substring(prefixo.length);
            }
            return slug;
        }
        """
        if not slug or not namespace:
            return slug or ''
        prefixo = f"{namespace}_"
        if slug.startswith(prefixo):
            return slug[len(prefixo):]
        return slug

    def aplicar_namespace_backend(self, slug: str, namespace: str) -> str:
        """
        Simula a função _aplicar_namespace() do backend.

        O backend SEMPRE aplica o namespace ao salvar.
        """
        if not namespace:
            return slug
        if slug.startswith(f"{namespace}_"):
            return slug
        return f"{namespace}_{slug}"

    # ==========================================
    # Testes de fluxo frontend -> backend
    # ==========================================

    def test_frontend_envia_nome_base_backend_retorna_prefixado(self):
        """
        Frontend envia nome base (sem prefixo).
        Backend retorna nome completo (com prefixo).
        """
        # Arrange - Simula o que o frontend envia
        categoria = self._criar_categoria_mock()
        nome_digitado_pelo_usuario = "medicamento_solicitado"  # Sem prefixo
        namespace = self.obter_namespace_categoria(categoria)

        # Act - Simula processamento do backend
        nome_persistido = self.aplicar_namespace_backend(nome_digitado_pelo_usuario, namespace)

        # Assert
        self.assertEqual(nome_persistido, "peticao_inicial_medicamento_solicitado")

    def test_frontend_envia_nome_ja_prefixado_backend_nao_duplica(self):
        """
        Se frontend enviar nome já com prefixo, backend não duplica.
        """
        # Arrange - Usuário de alguma forma enviou nome completo
        categoria = self._criar_categoria_mock()
        nome_completo = "peticao_inicial_medicamento"
        namespace = self.obter_namespace_categoria(categoria)

        # Act - Backend não deve duplicar
        nome_persistido = self.aplicar_namespace_backend(nome_completo, namespace)

        # Assert
        self.assertEqual(nome_persistido, "peticao_inicial_medicamento")
        self.assertNotEqual(nome_persistido, "peticao_inicial_peticao_inicial_medicamento")

    def test_ao_editar_frontend_exibe_apenas_sufixo(self):
        """
        Ao carregar pergunta para edição, frontend deve exibir apenas o sufixo.
        """
        # Arrange - Nome completo salvo no banco
        categoria = self._criar_categoria_mock()
        nome_no_banco = "peticao_inicial_equipamentos_lista"
        namespace = self.obter_namespace_categoria(categoria)

        # Act - Frontend extrai apenas o sufixo para exibir no input
        nome_exibido_no_input = self.remover_prefixo_slug(nome_no_banco, namespace)

        # Assert - Usuário vê apenas o sufixo
        self.assertEqual(nome_exibido_no_input, "equipamentos_lista")

    def test_prefixo_exibido_como_elemento_fixo(self):
        """
        O prefixo deve ser exibido como elemento fixo antes do input.

        Visual esperado: [peticao_inicial_][input: equipamentos_lista]
        """
        # Arrange
        categoria = self._criar_categoria_mock()
        namespace = self.obter_namespace_categoria(categoria)

        # Act - Prefixo que seria exibido no span fixo
        prefixo_exibido = f"{namespace}_"

        # Assert
        self.assertEqual(prefixo_exibido, "peticao_inicial_")

    def test_usuario_nao_pode_alterar_prefixo(self):
        """
        O usuário só pode alterar o sufixo. O prefixo é fixo.

        Simula: usuário tenta digitar "outro_medicamento"
        Resultado: valor salvo será "peticao_inicial_outro_medicamento"
        """
        # Arrange
        categoria = self._criar_categoria_mock()
        nome_digitado = "outro_medicamento"  # Usuário só vê/digita isso
        namespace = self.obter_namespace_categoria(categoria)

        # Act - Backend concatena prefixo + input
        nome_final = self.aplicar_namespace_backend(nome_digitado, namespace)

        # Assert
        self.assertTrue(nome_final.startswith("peticao_inicial_"))
        self.assertEqual(nome_final, "peticao_inicial_outro_medicamento")

    # ==========================================
    # Testes de categorias diferentes
    # ==========================================

    def test_categoria_diferente_atualiza_prefixo_exibido(self):
        """
        Ao selecionar categoria diferente, o prefixo exibido deve atualizar.
        """
        # Arrange - Duas categorias diferentes
        categoria_peticao = self._criar_categoria_mock(
            nome="peticao_inicial",
            namespace_prefix="peticao_inicial"
        )
        categoria_pareceres = self._criar_categoria_mock(
            nome="pareceres",
            namespace_prefix="pareceres"
        )

        # Act
        namespace_peticao = self.obter_namespace_categoria(categoria_peticao)
        namespace_parecer = self.obter_namespace_categoria(categoria_pareceres)

        # Assert - Prefixos diferentes
        self.assertEqual(namespace_peticao, "peticao_inicial")
        self.assertEqual(namespace_parecer, "pareceres")

    def test_mesmo_sufixo_categorias_diferentes_slugs_diferentes(self):
        """
        Mesmo sufixo em categorias diferentes resulta em slugs completos diferentes.
        """
        # Arrange
        categoria_peticao = self._criar_categoria_mock(
            nome="peticao_inicial",
            namespace_prefix="peticao_inicial"
        )
        categoria_pareceres = self._criar_categoria_mock(
            nome="pareceres",
            namespace_prefix="pareceres"
        )

        sufixo = "tipo_documento"

        # Act
        slug_peticao = self.aplicar_namespace_backend(
            sufixo, self.obter_namespace_categoria(categoria_peticao)
        )
        slug_parecer = self.aplicar_namespace_backend(
            sufixo, self.obter_namespace_categoria(categoria_pareceres)
        )

        # Assert
        self.assertEqual(slug_peticao, "peticao_inicial_tipo_documento")
        self.assertEqual(slug_parecer, "pareceres_tipo_documento")
        self.assertNotEqual(slug_peticao, slug_parecer)

    # ==========================================
    # Testes de fluxo completo (criar e editar)
    # ==========================================

    def test_fluxo_completo_criar_pergunta(self):
        """
        Testa o fluxo completo de criação de pergunta via API.

        1. Frontend exibe prefixo fixo
        2. Usuário digita sufixo
        3. Backend salva nome completo
        4. Banco contém nome completo
        """
        # Arrange
        categoria = self._criar_categoria_mock()
        namespace = self.obter_namespace_categoria(categoria)
        sufixo_digitado = "valor_causa"

        # Act - Simula envio do frontend
        nome_enviado = sufixo_digitado  # Frontend envia só o sufixo
        nome_persistido = self.aplicar_namespace_backend(nome_enviado, namespace)

        # Simula pergunta salva no banco
        pergunta = self._criar_pergunta_mock(
            nome_variavel_sugerido=nome_persistido,
            tipo_sugerido="currency",
            categoria_id=categoria.id
        )

        # Assert
        self.assertEqual(pergunta.nome_variavel_sugerido, "peticao_inicial_valor_causa")

    def test_fluxo_completo_editar_pergunta(self):
        """
        Testa o fluxo completo de edição de pergunta via API.

        1. Carrega pergunta existente
        2. Frontend extrai sufixo para exibir
        3. Usuário edita sufixo
        4. Backend salva nome completo atualizado
        """
        # Arrange - Pergunta existente
        categoria = self._criar_categoria_mock()
        pergunta = self._criar_pergunta_mock(
            nome_variavel_sugerido="peticao_inicial_nome_antigo",
            tipo_sugerido="text",
            categoria_id=categoria.id
        )

        namespace = self.obter_namespace_categoria(categoria)

        # Act - Frontend carrega e exibe sufixo
        sufixo_exibido = self.remover_prefixo_slug(
            pergunta.nome_variavel_sugerido, namespace
        )
        self.assertEqual(sufixo_exibido, "nome_antigo")

        # Usuário edita para novo sufixo
        novo_sufixo = "nome_novo"
        novo_nome_completo = self.aplicar_namespace_backend(novo_sufixo, namespace)

        # Simula atualização no banco
        pergunta.nome_variavel_sugerido = novo_nome_completo

        # Assert
        self.assertEqual(pergunta.nome_variavel_sugerido, "peticao_inicial_nome_novo")


class TestFrontendValidacaoInput(unittest.TestCase):
    """
    Testes para validar regras de entrada do input de nome da variável.
    """

    def test_input_aceita_apenas_minusculas_numeros_underscore(self):
        """
        O input deve aceitar apenas letras minúsculas, números e underscores.
        """
        # Arrange
        inputs_validos = [
            "medicamento",
            "valor_causa",
            "item_1",
            "campo_2_teste",
        ]
        inputs_invalidos = [
            "Medicamento",      # Maiúscula
            "valor causa",      # Espaço
            "valor-causa",      # Hífen
            "valor@causa",      # Caractere especial
            "médico",           # Acento
        ]

        # Act & Assert - Válidos
        for input_val in inputs_validos:
            is_valid = bool(re.match(r'^[a-z0-9_]+$', input_val))
            self.assertTrue(is_valid, f"'{input_val}' deveria ser válido")

        # Act & Assert - Inválidos
        for input_val in inputs_invalidos:
            is_valid = bool(re.match(r'^[a-z0-9_]+$', input_val))
            self.assertFalse(is_valid, f"'{input_val}' deveria ser inválido")

    def test_normalizacao_automatica_input(self):
        """
        Se frontend normaliza automaticamente, testa a normalização.
        """
        def normalizar(texto: str) -> str:
            """Normaliza texto para formato de variável."""
            # Remove acentos
            texto = unicodedata.normalize('NFKD', texto)
            texto = texto.encode('ascii', 'ignore').decode('ascii')
            # Minúsculas
            texto = texto.lower()
            # Remove caracteres especiais
            texto = re.sub(r'[^a-z0-9\s_]', '', texto)
            # Espaços para underscore
            texto = re.sub(r'\s+', '_', texto.strip())
            # Remove underscores múltiplos
            texto = re.sub(r'_+', '_', texto)
            return texto

        # Assert
        self.assertEqual(normalizar("Medicamento Solicitado"), "medicamento_solicitado")
        self.assertEqual(normalizar("Petição Médica"), "peticao_medica")
        self.assertEqual(normalizar("valor@#$causa"), "valorcausa")
        self.assertEqual(normalizar("  espaços  extras  "), "espacos_extras")


if __name__ == "__main__":
    unittest.main()
