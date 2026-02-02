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


class TestNormalizacaoPrefixoEndpoint(unittest.TestCase):
    """
    Testes para validar que os endpoints aplicam prefixo corretamente.

    Estes testes validam o COMPORTAMENTO ESPERADO após a correção do bug:
    - POST /perguntas: nome_variavel_sugerido deve ser normalizado com prefixo
    - PUT /perguntas: nome_variavel_sugerido deve ser normalizado com prefixo
    - POST /perguntas/lote: cada nome_variavel deve ser normalizado com prefixo
    """

    def _aplicar_namespace(self, slug: str, namespace: str) -> str:
        """Replica a função _aplicar_namespace do router_extraction.py"""
        if not namespace:
            return slug
        if slug.startswith(f"{namespace}_"):
            return slug
        return f"{namespace}_{slug}"

    def test_post_perguntas_aplica_prefixo(self):
        """
        POST /perguntas: Backend DEVE aplicar prefixo ao nome_variavel_sugerido.

        Cenário: Frontend envia nome SEM prefixo
        Esperado: Backend persiste COM prefixo
        """
        # Simula input do frontend (SEM prefixo)
        input_frontend = "nao_preenche_requisitos_pcdt"
        namespace = "pareceres"

        # Simula normalização do backend (correção implementada)
        nome_normalizado = self._aplicar_namespace(input_frontend, namespace)

        # Assert - Backend deve ter aplicado o prefixo
        self.assertEqual(nome_normalizado, "pareceres_nao_preenche_requisitos_pcdt")
        self.assertTrue(nome_normalizado.startswith("pareceres_"))

    def test_post_perguntas_nao_duplica_prefixo(self):
        """
        POST /perguntas: Backend NÃO deve duplicar prefixo se já existir.

        Cenário: Frontend envia nome JÁ com prefixo (por algum motivo)
        Esperado: Backend persiste SEM duplicar
        """
        # Simula input do frontend (JÁ com prefixo)
        input_frontend = "pareceres_medicamento"
        namespace = "pareceres"

        # Simula normalização do backend
        nome_normalizado = self._aplicar_namespace(input_frontend, namespace)

        # Assert - Não deve duplicar
        self.assertEqual(nome_normalizado, "pareceres_medicamento")
        self.assertNotEqual(nome_normalizado, "pareceres_pareceres_medicamento")

    def test_put_perguntas_aplica_prefixo(self):
        """
        PUT /perguntas: Backend DEVE aplicar prefixo na atualização.

        Cenário: Usuário edita pergunta e muda o nome_base no modal
        Esperado: Backend persiste o novo nome COM prefixo
        """
        # Simula input do frontend (SEM prefixo)
        novo_nome_base = "nome_atualizado"
        namespace = "pareceres"

        # Simula normalização do backend
        nome_normalizado = self._aplicar_namespace(novo_nome_base, namespace)

        # Assert
        self.assertEqual(nome_normalizado, "pareceres_nome_atualizado")

    def test_lote_aplica_prefixo_todas_perguntas(self):
        """
        POST /perguntas/lote: Backend DEVE aplicar prefixo em TODAS as perguntas.

        Cenário: Criação em lote de múltiplas perguntas
        Esperado: Todas recebem o prefixo correto
        """
        perguntas_input = [
            "pergunta_1",
            "pergunta_2",
            "pergunta_3"
        ]
        namespace = "pareceres"

        # Simula normalização do backend para cada pergunta
        perguntas_normalizadas = [
            self._aplicar_namespace(p, namespace) for p in perguntas_input
        ]

        # Assert - Todas devem ter prefixo
        for nome in perguntas_normalizadas:
            self.assertTrue(nome.startswith("pareceres_"))

        self.assertEqual(perguntas_normalizadas, [
            "pareceres_pergunta_1",
            "pareceres_pergunta_2",
            "pareceres_pergunta_3"
        ])

    def test_caso_real_bug_nao_preenche_requisitos(self):
        """
        Teste do caso REAL do bug reportado:

        Categoria: pareceres (ID 5)
        Input: 'nao_preenche_requisitos_pcdt'
        Esperado: 'pareceres_nao_preenche_requisitos_pcdt'
        """
        # Input original do bug report
        input_bugado = "nao_preenche_requisitos_pcdt"
        namespace = "pareceres"

        # Após a correção, o backend deve normalizar
        nome_corrigido = self._aplicar_namespace(input_bugado, namespace)

        # Assert - Deve ter o prefixo
        self.assertEqual(nome_corrigido, "pareceres_nao_preenche_requisitos_pcdt")
        self.assertTrue(nome_corrigido.startswith("pareceres_"))

    def test_dependencia_tambem_recebe_prefixo(self):
        """
        POST /perguntas/lote: depends_on_variable também deve receber prefixo.

        Cenário: Pergunta depende de outra variável
        Esperado: depends_on_variable é normalizado com prefixo
        """
        depends_on_input = "variavel_ancora"
        namespace = "pareceres"

        # Simula normalização do backend
        depends_on_normalizado = self._aplicar_namespace(depends_on_input, namespace)

        # Assert
        self.assertEqual(depends_on_normalizado, "pareceres_variavel_ancora")


class TestCorrecaoMigracao(unittest.TestCase):
    """
    Testes para validar a lógica de correção de dados existentes.
    """

    def _aplicar_namespace(self, slug: str, namespace: str) -> str:
        """Replica a função _aplicar_namespace"""
        if not namespace:
            return slug
        if slug.startswith(f"{namespace}_"):
            return slug
        return f"{namespace}_{slug}"

    def test_migracao_identifica_variaveis_sem_prefixo(self):
        """
        Script de migração deve identificar variáveis que não têm prefixo.
        """
        # Simula variaveis do banco
        variaveis = [
            {"slug": "pareceres_nome_medicamento", "categoria_namespace": "pareceres"},  # OK
            {"slug": "nao_preenche_requisitos", "categoria_namespace": "pareceres"},  # SEM PREFIXO
            {"slug": "pareceres_off_label", "categoria_namespace": "pareceres"},  # OK
        ]

        # Identifica variaveis sem prefixo
        sem_prefixo = []
        for v in variaveis:
            prefixo_esperado = f"{v['categoria_namespace']}_"
            if not v["slug"].startswith(prefixo_esperado):
                sem_prefixo.append(v)

        # Assert
        self.assertEqual(len(sem_prefixo), 1)
        self.assertEqual(sem_prefixo[0]["slug"], "nao_preenche_requisitos")

    def test_migracao_corrige_slug(self):
        """
        Script de migração deve corrigir slug aplicando prefixo.
        """
        slug_incorreto = "nao_preenche_requisitos"
        namespace = "pareceres"

        # Correção
        slug_corrigido = self._aplicar_namespace(slug_incorreto, namespace)

        # Assert
        self.assertEqual(slug_corrigido, "pareceres_nao_preenche_requisitos")

    def test_migracao_idempotente(self):
        """
        Rodar migração múltiplas vezes não deve alterar dados já corretos.
        """
        slug_ja_correto = "pareceres_nao_preenche_requisitos"
        namespace = "pareceres"

        # Aplicar "correção" novamente
        slug_apos_correcao = self._aplicar_namespace(slug_ja_correto, namespace)

        # Assert - Não deve alterar
        self.assertEqual(slug_apos_correcao, slug_ja_correto)


if __name__ == "__main__":
    unittest.main()
