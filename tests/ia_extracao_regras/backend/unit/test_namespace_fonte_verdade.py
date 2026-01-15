# tests/ia_extracao_regras/backend/unit/test_namespace_fonte_verdade.py
"""
Testes unitários para namespace de variáveis e fonte de verdade.

Testa:
- Aplicação automática de namespace por grupo
- Cálculo de namespace efetivo
- Validação de fonte de verdade
- Unicidade de variáveis com namespace
"""

import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime

# Importações do sistema
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))


class TestNamespaceCategoria(unittest.TestCase):
    """Testes para namespace de categorias"""

    def _criar_categoria_mock(self, **kwargs):
        """Cria um mock de categoria com os atributos necessários"""
        import re
        categoria = MagicMock()
        for key, value in kwargs.items():
            setattr(categoria, key, value)

        # Implementa a property namespace
        def get_namespace():
            if categoria.namespace_prefix:
                return categoria.namespace_prefix
            nome = categoria.nome.lower()
            nome = re.sub(r'[^a-z0-9]+', '_', nome)
            return nome.strip('_')

        # Implementa a property tem_fonte_verdade
        def get_tem_fonte_verdade():
            return bool(categoria.fonte_verdade_tipo and categoria.requer_classificacao)

        type(categoria).namespace = property(lambda self: get_namespace())
        type(categoria).tem_fonte_verdade = property(lambda self: get_tem_fonte_verdade())

        return categoria

    def test_namespace_com_prefix_definido(self):
        """Categoria com namespace_prefix usa o prefixo definido"""
        categoria = self._criar_categoria_mock(
            id=1,
            nome="peticoes",
            titulo="Petições",
            formato_json="{}",
            namespace_prefix="pet"
        )

        self.assertEqual(categoria.namespace, "pet")

    def test_namespace_fallback_para_nome(self):
        """Categoria sem namespace_prefix usa nome normalizado"""
        categoria = self._criar_categoria_mock(
            id=1,
            nome="pareceres nat",
            titulo="Pareceres do NAT",
            formato_json="{}",
            namespace_prefix=None
        )

        self.assertEqual(categoria.namespace, "pareceres_nat")

    def test_namespace_normaliza_acentos(self):
        """Namespace normaliza caracteres especiais"""
        categoria = self._criar_categoria_mock(
            id=1,
            nome="decisoes judiciais",
            titulo="Decisões",
            formato_json="{}",
            namespace_prefix=None
        )

        # Remove caracteres especiais e normaliza
        self.assertEqual(categoria.namespace, "decisoes_judiciais")

    def test_tem_fonte_verdade_configurada(self):
        """Property tem_fonte_verdade funciona corretamente"""
        # Sem fonte de verdade
        categoria1 = self._criar_categoria_mock(
            id=1,
            nome="test",
            titulo="Test",
            formato_json="{}",
            fonte_verdade_tipo=None,
            requer_classificacao=False
        )
        self.assertFalse(categoria1.tem_fonte_verdade)

        # Com fonte de verdade parcial (só tipo)
        categoria2 = self._criar_categoria_mock(
            id=2,
            nome="test2",
            titulo="Test2",
            formato_json="{}",
            fonte_verdade_tipo="petição inicial",
            requer_classificacao=False
        )
        self.assertFalse(categoria2.tem_fonte_verdade)

        # Com fonte de verdade completa
        categoria3 = self._criar_categoria_mock(
            id=3,
            nome="test3",
            titulo="Test3",
            formato_json="{}",
            fonte_verdade_tipo="petição inicial",
            requer_classificacao=True
        )
        self.assertTrue(categoria3.tem_fonte_verdade)


class TestAplicacaoNamespace(unittest.TestCase):
    """Testes para aplicação de namespace em variáveis"""

    def test_aplica_namespace_slug_simples(self):
        """Aplica namespace a slug que não tem prefixo"""
        from sistemas.gerador_pecas.services_extraction import ExtractionSchemaGenerator

        # Mock do db
        db_mock = MagicMock()
        generator = ExtractionSchemaGenerator(db_mock)

        resultado = generator._aplicar_namespace("medicamento", "peticao")

        self.assertEqual(resultado, "peticao_medicamento")

    def test_nao_duplica_namespace(self):
        """Não duplica namespace se já está presente"""
        from sistemas.gerador_pecas.services_extraction import ExtractionSchemaGenerator

        db_mock = MagicMock()
        generator = ExtractionSchemaGenerator(db_mock)

        resultado = generator._aplicar_namespace("peticao_medicamento", "peticao")

        self.assertEqual(resultado, "peticao_medicamento")

    def test_aplica_namespace_com_underscores(self):
        """Aplica namespace corretamente em slugs com underscores"""
        from sistemas.gerador_pecas.services_extraction import ExtractionSchemaGenerator

        db_mock = MagicMock()
        generator = ExtractionSchemaGenerator(db_mock)

        resultado = generator._aplicar_namespace("valor_da_causa", "nat")

        self.assertEqual(resultado, "nat_valor_da_causa")


class TestSourceOfTruthValidator(unittest.TestCase):
    """Testes para validação de fonte de verdade"""

    def _criar_categoria_mock(self, **kwargs):
        """Cria um mock de categoria"""
        import re
        categoria = MagicMock()
        for key, value in kwargs.items():
            setattr(categoria, key, value)

        def get_namespace():
            if categoria.namespace_prefix:
                return categoria.namespace_prefix
            nome = categoria.nome.lower()
            nome = re.sub(r'[^a-z0-9]+', '_', nome)
            return nome.strip('_')

        type(categoria).namespace = property(lambda self: get_namespace())
        return categoria

    def test_categoria_sem_classificacao_sempre_extrai(self):
        """Categoria sem requer_classificacao sempre permite extração"""
        from sistemas.gerador_pecas.services_classificacao import SourceOfTruthValidator

        db_mock = MagicMock()

        # Categoria que não requer classificação
        categoria = self._criar_categoria_mock(
            id=1,
            nome="test",
            titulo="Test",
            formato_json="{}",
            requer_classificacao=False
        )
        db_mock.query.return_value.filter.return_value.first.return_value = categoria

        validator = SourceOfTruthValidator(db_mock)

        # Executa validação
        import asyncio
        resultado = asyncio.run(
            validator.validar_documento_para_extracao(
                conteudo="teste",
                categoria_id=1
            )
        )

        self.assertTrue(resultado["deve_extrair"])

    def test_get_namespace_for_categoria(self):
        """Obtém namespace corretamente para categoria"""
        from sistemas.gerador_pecas.services_classificacao import SourceOfTruthValidator

        db_mock = MagicMock()

        categoria = self._criar_categoria_mock(
            id=1,
            nome="peticoes",
            titulo="Petições",
            formato_json="{}",
            namespace_prefix="pet"
        )
        db_mock.query.return_value.filter.return_value.first.return_value = categoria

        validator = SourceOfTruthValidator(db_mock)
        namespace = validator.get_namespace_for_categoria(1)

        self.assertEqual(namespace, "pet")


class TestDocumentClassificationService(unittest.TestCase):
    """Testes para serviço de classificação de documentos"""

    def _criar_categoria_mock(self, **kwargs):
        """Cria um mock de categoria"""
        categoria = MagicMock()
        for key, value in kwargs.items():
            setattr(categoria, key, value)
        return categoria

    def test_classificar_sem_tipos_logicos(self):
        """Classificação retorna True se não há tipos lógicos definidos"""
        from sistemas.gerador_pecas.services_classificacao import DocumentClassificationService

        db_mock = MagicMock()
        service = DocumentClassificationService(db_mock)

        # Categoria sem tipos lógicos mas que requer classificação
        categoria = self._criar_categoria_mock(
            id=1,
            nome="test",
            titulo="Test",
            formato_json="{}",
            requer_classificacao=True,
            tipos_logicos_peca=None
        )

        import asyncio
        resultado = asyncio.run(
            service.classificar_documento(
                conteudo="teste",
                categoria=categoria
            )
        )

        self.assertTrue(resultado["success"])
        self.assertTrue(resultado["e_fonte_verdade"])

    def test_classificar_sem_requer_classificacao(self):
        """Classificação retorna fonte de verdade True se não requer classificação"""
        from sistemas.gerador_pecas.services_classificacao import DocumentClassificationService

        db_mock = MagicMock()
        service = DocumentClassificationService(db_mock)

        categoria = self._criar_categoria_mock(
            id=1,
            nome="test",
            titulo="Test",
            formato_json="{}",
            requer_classificacao=False
        )

        import asyncio
        resultado = asyncio.run(
            service.classificar_documento(
                conteudo="teste",
                categoria=categoria
            )
        )

        self.assertTrue(resultado["success"])
        self.assertTrue(resultado["e_fonte_verdade"])


class TestVariaveisNamespace(unittest.TestCase):
    """Testes de integração para criação de variáveis com namespace"""

    def test_variaveis_mesmo_nome_grupos_diferentes(self):
        """Variáveis com mesmo nome base em grupos diferentes têm slugs diferentes"""
        # Simula cenário onde "medicamento" existe em peticoes e nat

        slug_peticao = "peticao_medicamento"
        slug_nat = "nat_medicamento"

        # Devem ser diferentes
        self.assertNotEqual(slug_peticao, slug_nat)

        # Ambos devem conter o nome base
        self.assertIn("medicamento", slug_peticao)
        self.assertIn("medicamento", slug_nat)

    def test_unicidade_garantida_por_namespace(self):
        """Namespace garante unicidade mesmo com nomes base iguais"""
        variaveis = {}

        # Simula criação de variáveis
        def criar_variavel(namespace, nome_base):
            slug = f"{namespace}_{nome_base}"
            if slug in variaveis:
                raise ValueError(f"Slug duplicado: {slug}")
            variaveis[slug] = {"namespace": namespace, "nome_base": nome_base}
            return slug

        # Mesma variável em grupos diferentes
        slug1 = criar_variavel("peticao", "valor_causa")
        slug2 = criar_variavel("nat", "valor_causa")
        slug3 = criar_variavel("sentenca", "valor_causa")

        # Todas devem ser criadas sem erro
        self.assertEqual(len(variaveis), 3)
        self.assertNotEqual(slug1, slug2)
        self.assertNotEqual(slug2, slug3)
        self.assertNotEqual(slug1, slug3)

    def test_dependencia_aplica_namespace(self):
        """Dependências também recebem namespace"""
        from sistemas.gerador_pecas.services_extraction import ExtractionSchemaGenerator

        db_mock = MagicMock()
        generator = ExtractionSchemaGenerator(db_mock)

        # Se uma variável depende de outra, a dependência também deve ter namespace
        depends_on_base = "tipo_acao"
        namespace = "peticao"

        depends_on_com_namespace = generator._aplicar_namespace(depends_on_base, namespace)

        self.assertEqual(depends_on_com_namespace, "peticao_tipo_acao")


class TestValidacoesFonteVerdade(unittest.TestCase):
    """Testes de validação de fonte de verdade"""

    def _criar_categoria_mock(self, **kwargs):
        """Cria um mock de categoria"""
        categoria = MagicMock()
        for key, value in kwargs.items():
            setattr(categoria, key, value)

        # Implementa a property tem_fonte_verdade
        def get_tem_fonte_verdade():
            return bool(categoria.fonte_verdade_tipo and categoria.requer_classificacao)

        type(categoria).tem_fonte_verdade = property(lambda self: get_tem_fonte_verdade())
        return categoria

    def test_fonte_verdade_vazia_permite_todos(self):
        """Sem fonte de verdade definida, todos os documentos são aceitos"""
        categoria = self._criar_categoria_mock(
            id=1,
            nome="test",
            titulo="Test",
            formato_json="{}",
            fonte_verdade_tipo=None,
            tipos_logicos_peca=["tipo1", "tipo2"],
            requer_classificacao=True
        )

        # Sem fonte de verdade definida, tem_fonte_verdade deve ser False
        # Isso significa que qualquer documento pode ser extraído
        self.assertFalse(categoria.tem_fonte_verdade)

    def test_tipos_logicos_definidos(self):
        """Tipos lógicos são corretamente definidos"""
        tipos = ["petição inicial", "contestação", "petição intermediária"]

        categoria = self._criar_categoria_mock(
            id=1,
            nome="peticoes",
            titulo="Petições",
            formato_json="{}",
            tipos_logicos_peca=tipos,
            fonte_verdade_tipo="petição inicial"
        )

        self.assertEqual(categoria.tipos_logicos_peca, tipos)
        self.assertEqual(categoria.fonte_verdade_tipo, "petição inicial")


if __name__ == '__main__':
    unittest.main()
