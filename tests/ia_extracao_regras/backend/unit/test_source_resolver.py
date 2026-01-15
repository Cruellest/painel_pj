# tests/ia_extracao_regras/backend/unit/test_source_resolver.py
"""
Testes unitários para o serviço de resolução de fontes especiais.

Testa:
- Resolução de petição inicial (primeiro documento com código 9500/500/510)
- Ordenação cronológica de documentos
- Tratamento de documentos sem data
- Property usa_fonte_especial no modelo
- Funções de conveniência
"""

import unittest
from unittest.mock import MagicMock
from datetime import datetime, timedelta

# Importações do sistema
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))


class TestSourceResolver(unittest.TestCase):
    """Testes para o SourceResolver"""

    def test_resolve_peticao_inicial_por_data(self):
        """Resolve petição inicial pelo documento mais antigo com código válido"""
        from sistemas.gerador_pecas.services_source_resolver import (
            SourceResolver, DocumentoInfo
        )

        resolver = SourceResolver()

        # Cria lista de documentos com datas diferentes
        docs = [
            DocumentoInfo(id="2", codigo=9500, data=datetime(2024, 2, 1), ordem=1),
            DocumentoInfo(id="1", codigo=9500, data=datetime(2024, 1, 1), ordem=0),  # mais antigo
            DocumentoInfo(id="3", codigo=9500, data=datetime(2024, 3, 1), ordem=2),
        ]

        resultado = resolver.resolve("peticao_inicial", docs)

        self.assertTrue(resultado.sucesso)
        self.assertEqual(resultado.documento_id, "1")  # Documento mais antigo
        self.assertEqual(resultado.candidatos_avaliados, 3)

    def test_resolve_peticao_inicial_por_ordem(self):
        """Usa ordem como fallback quando não há data"""
        from sistemas.gerador_pecas.services_source_resolver import (
            SourceResolver, DocumentoInfo
        )

        resolver = SourceResolver()

        # Documentos sem data - usa ordem
        docs = [
            DocumentoInfo(id="2", codigo=9500, data=None, ordem=1),
            DocumentoInfo(id="1", codigo=9500, data=None, ordem=0),  # menor ordem
            DocumentoInfo(id="3", codigo=9500, data=None, ordem=2),
        ]

        resultado = resolver.resolve("peticao_inicial", docs)

        self.assertTrue(resultado.sucesso)
        self.assertEqual(resultado.documento_id, "1")

    def test_resolve_peticao_inicial_prioriza_data(self):
        """Documentos com data têm prioridade sobre documentos sem data"""
        from sistemas.gerador_pecas.services_source_resolver import (
            SourceResolver, DocumentoInfo
        )

        resolver = SourceResolver()

        # Mix de docs com e sem data
        docs = [
            DocumentoInfo(id="1", codigo=9500, data=None, ordem=0),
            DocumentoInfo(id="2", codigo=9500, data=datetime(2024, 6, 1), ordem=1),  # com data
            DocumentoInfo(id="3", codigo=500, data=None, ordem=2),
        ]

        resultado = resolver.resolve("peticao_inicial", docs)

        self.assertTrue(resultado.sucesso)
        self.assertEqual(resultado.documento_id, "2")  # Doc com data tem prioridade

    def test_resolve_aceita_todos_codigos_peticao(self):
        """Aceita códigos 9500, 500 e 510 como petição"""
        from sistemas.gerador_pecas.services_source_resolver import (
            SourceResolver, DocumentoInfo
        )

        resolver = SourceResolver()

        # Testa cada código válido
        for codigo in [9500, 500, 510]:
            docs = [
                DocumentoInfo(id="1", codigo=codigo, data=datetime(2024, 1, 1), ordem=0)
            ]
            resultado = resolver.resolve("peticao_inicial", docs)
            self.assertTrue(resultado.sucesso, f"Código {codigo} deveria ser aceito")

    def test_resolve_ignora_codigos_invalidos(self):
        """Ignora documentos com códigos que não são de petição"""
        from sistemas.gerador_pecas.services_source_resolver import (
            SourceResolver, DocumentoInfo
        )

        resolver = SourceResolver()

        # Docs com códigos inválidos e um válido
        docs = [
            DocumentoInfo(id="1", codigo=1000, data=datetime(2024, 1, 1), ordem=0),  # inválido
            DocumentoInfo(id="2", codigo=2000, data=datetime(2024, 1, 2), ordem=1),  # inválido
            DocumentoInfo(id="3", codigo=9500, data=datetime(2024, 1, 3), ordem=2),  # válido
        ]

        resultado = resolver.resolve("peticao_inicial", docs)

        self.assertTrue(resultado.sucesso)
        self.assertEqual(resultado.documento_id, "3")

    def test_resolve_falha_sem_codigos_validos(self):
        """Falha quando não há documentos com códigos de petição"""
        from sistemas.gerador_pecas.services_source_resolver import (
            SourceResolver, DocumentoInfo
        )

        resolver = SourceResolver()

        docs = [
            DocumentoInfo(id="1", codigo=1000, data=datetime(2024, 1, 1), ordem=0),
            DocumentoInfo(id="2", codigo=2000, data=datetime(2024, 1, 2), ordem=1),
        ]

        resultado = resolver.resolve("peticao_inicial", docs)

        self.assertFalse(resultado.sucesso)
        self.assertIn("9500", resultado.motivo)  # Deve mencionar códigos válidos

    def test_resolve_falha_lista_vazia(self):
        """Falha quando lista de documentos está vazia"""
        from sistemas.gerador_pecas.services_source_resolver import SourceResolver

        resolver = SourceResolver()
        resultado = resolver.resolve("peticao_inicial", [])

        self.assertFalse(resultado.sucesso)
        self.assertIn("Nenhum documento", resultado.motivo)

    def test_resolve_fonte_invalida(self):
        """Falha quando tipo de fonte não existe"""
        from sistemas.gerador_pecas.services_source_resolver import (
            SourceResolver, DocumentoInfo
        )

        resolver = SourceResolver()

        docs = [DocumentoInfo(id="1", codigo=9500, data=None, ordem=0)]
        resultado = resolver.resolve("fonte_inexistente", docs)

        self.assertFalse(resultado.sucesso)
        self.assertIn("não reconhecida", resultado.motivo)


class TestSourceResolverRawDocs(unittest.TestCase):
    """Testes para resolução a partir de dicts (dados brutos)"""

    def test_resolve_from_raw_docs_default_fields(self):
        """Resolve usando campos padrão dos dicts"""
        from sistemas.gerador_pecas.services_source_resolver import SourceResolver

        resolver = SourceResolver()

        docs = [
            {"id": "1", "tipo_documento": 9500, "data": "2024-01-01T10:00:00"},
            {"id": "2", "tipo_documento": 9500, "data": "2024-02-01T10:00:00"},
        ]

        resultado = resolver.resolve_from_raw_docs("peticao_inicial", docs)

        self.assertTrue(resultado.sucesso)
        self.assertEqual(resultado.documento_id, "1")

    def test_resolve_from_raw_docs_custom_fields(self):
        """Resolve usando campos customizados"""
        from sistemas.gerador_pecas.services_source_resolver import SourceResolver

        resolver = SourceResolver()

        docs = [
            {"doc_id": "1", "codigo": "9500", "criado_em": "2024-01-01"},
            {"doc_id": "2", "codigo": "9500", "criado_em": "2024-02-01"},
        ]

        resultado = resolver.resolve_from_raw_docs(
            "peticao_inicial",
            docs,
            campo_id="doc_id",
            campo_codigo="codigo",
            campo_data="criado_em"
        )

        self.assertTrue(resultado.sucesso)
        self.assertEqual(resultado.documento_id, "1")

    def test_resolve_from_raw_docs_codigo_string(self):
        """Converte código string para int corretamente"""
        from sistemas.gerador_pecas.services_source_resolver import SourceResolver

        resolver = SourceResolver()

        docs = [
            {"id": "1", "tipo_documento": "9500", "data": "2024-01-01"},
        ]

        resultado = resolver.resolve_from_raw_docs("peticao_inicial", docs)

        self.assertTrue(resultado.sucesso)

    def test_resolve_from_raw_docs_data_datetime(self):
        """Aceita data como objeto datetime"""
        from sistemas.gerador_pecas.services_source_resolver import SourceResolver

        resolver = SourceResolver()

        docs = [
            {"id": "1", "tipo_documento": 9500, "data": datetime(2024, 1, 1)},
        ]

        resultado = resolver.resolve_from_raw_docs("peticao_inicial", docs)

        self.assertTrue(resultado.sucesso)


class TestSourceResolverHelpers(unittest.TestCase):
    """Testes para funções de conveniência"""

    def test_get_available_sources(self):
        """Lista fontes especiais disponíveis"""
        from sistemas.gerador_pecas.services_source_resolver import (
            get_available_special_sources
        )

        fontes = get_available_special_sources()

        self.assertIsInstance(fontes, list)
        self.assertGreater(len(fontes), 0)

        # Verifica estrutura
        fonte = fontes[0]
        self.assertIn("key", fonte)
        self.assertIn("nome", fonte)
        self.assertIn("descricao", fonte)
        self.assertIn("codigos_validos", fonte)

    def test_is_valid_special_source(self):
        """Verifica se fonte especial é válida"""
        from sistemas.gerador_pecas.services_source_resolver import (
            is_valid_special_source
        )

        self.assertTrue(is_valid_special_source("peticao_inicial"))
        self.assertFalse(is_valid_special_source("fonte_inexistente"))

    def test_resolve_special_source_convenience(self):
        """Função de conveniência resolve corretamente"""
        from sistemas.gerador_pecas.services_source_resolver import (
            resolve_special_source, DocumentoInfo
        )

        docs = [
            DocumentoInfo(id="1", codigo=9500, data=datetime(2024, 1, 1), ordem=0)
        ]

        resultado = resolve_special_source("peticao_inicial", docs)

        self.assertTrue(resultado.sucesso)
        self.assertEqual(resultado.documento_id, "1")

    def test_resolve_special_source_from_dicts_convenience(self):
        """Função de conveniência para dicts resolve corretamente"""
        from sistemas.gerador_pecas.services_source_resolver import (
            resolve_special_source_from_dicts
        )

        docs = [
            {"id": "1", "tipo_documento": 9500, "data": "2024-01-01"}
        ]

        resultado = resolve_special_source_from_dicts("peticao_inicial", docs)

        self.assertTrue(resultado.sucesso)


class TestCategoriaUsaFonteEspecial(unittest.TestCase):
    """Testes para property usa_fonte_especial do modelo"""

    def _criar_categoria_mock(self, **kwargs):
        """Cria um mock de categoria com as properties necessárias"""
        categoria = MagicMock()
        for key, value in kwargs.items():
            setattr(categoria, key, value)

        # Implementa a property usa_fonte_especial
        def get_usa_fonte_especial():
            return categoria.source_type == "special" and bool(categoria.source_special_type)

        type(categoria).usa_fonte_especial = property(lambda self: get_usa_fonte_especial())

        return categoria

    def test_usa_fonte_especial_true(self):
        """Property retorna True quando configurado corretamente"""
        categoria = self._criar_categoria_mock(
            id=1,
            nome="peticao_inicial",
            titulo="Petição Inicial",
            formato_json="{}",
            source_type="special",
            source_special_type="peticao_inicial"
        )

        self.assertTrue(categoria.usa_fonte_especial)

    def test_usa_fonte_especial_false_type_code(self):
        """Property retorna False quando source_type é 'code'"""
        categoria = self._criar_categoria_mock(
            id=1,
            nome="peticoes",
            titulo="Petições",
            formato_json="{}",
            source_type="code",
            source_special_type=None
        )

        self.assertFalse(categoria.usa_fonte_especial)

    def test_usa_fonte_especial_false_sem_special_type(self):
        """Property retorna False quando source_special_type está vazio"""
        categoria = self._criar_categoria_mock(
            id=1,
            nome="test",
            titulo="Test",
            formato_json="{}",
            source_type="special",
            source_special_type=""
        )

        self.assertFalse(categoria.usa_fonte_especial)

    def test_usa_fonte_especial_false_special_type_none(self):
        """Property retorna False quando source_special_type é None"""
        categoria = self._criar_categoria_mock(
            id=1,
            nome="test",
            titulo="Test",
            formato_json="{}",
            source_type="special",
            source_special_type=None
        )

        self.assertFalse(categoria.usa_fonte_especial)


class TestSourceResolverExtensibility(unittest.TestCase):
    """Testes para extensibilidade do resolver"""

    def test_register_custom_source(self):
        """Permite registrar novas fontes especiais"""
        from sistemas.gerador_pecas.services_source_resolver import (
            SourceResolver, SpecialSourceDefinition, DocumentoInfo, SourceResolutionResult
        )

        resolver = SourceResolver()

        # Registra fonte customizada
        def resolver_sentenca(docs):
            # Exemplo: retorna o documento mais recente com código 6000
            candidatos = [d for d in docs if d.codigo == 6000]
            if not candidatos:
                return SourceResolutionResult(sucesso=False, motivo="Sem sentença")
            mais_recente = max(candidatos, key=lambda d: d.data or datetime.min)
            return SourceResolutionResult(
                sucesso=True,
                documento_id=mais_recente.id,
                documento_info=mais_recente
            )

        resolver.register_source(SpecialSourceDefinition(
            key="sentenca_mais_recente",
            nome="Sentença Mais Recente",
            descricao="Última sentença do processo",
            codigos_validos=[6000],
            resolver=resolver_sentenca
        ))

        # Verifica que foi registrada
        self.assertTrue(resolver.is_valid_source("sentenca_mais_recente"))

        # Usa a fonte customizada
        docs = [
            DocumentoInfo(id="1", codigo=6000, data=datetime(2024, 1, 1), ordem=0),
            DocumentoInfo(id="2", codigo=6000, data=datetime(2024, 6, 1), ordem=1),  # mais recente
        ]

        resultado = resolver.resolve("sentenca_mais_recente", docs)

        self.assertTrue(resultado.sucesso)
        self.assertEqual(resultado.documento_id, "2")  # Mais recente

    def test_get_source_info(self):
        """Retorna informações de uma fonte específica"""
        from sistemas.gerador_pecas.services_source_resolver import SourceResolver

        resolver = SourceResolver()

        info = resolver.get_source_info("peticao_inicial")

        self.assertIsNotNone(info)
        self.assertEqual(info["key"], "peticao_inicial")
        self.assertIn("nome", info)
        self.assertIn("descricao", info)
        self.assertIn("codigos_validos", info)

    def test_get_source_info_inexistente(self):
        """Retorna None para fonte inexistente"""
        from sistemas.gerador_pecas.services_source_resolver import SourceResolver

        resolver = SourceResolver()

        info = resolver.get_source_info("fonte_inexistente")

        self.assertIsNone(info)


class TestGerenciadorFormatosJSONFontesEspeciais(unittest.TestCase):
    """Testes para GerenciadorFormatosJSON com fontes especiais"""

    def _criar_categoria_mock(self, **kwargs):
        """Cria um mock de categoria"""
        categoria = MagicMock()
        defaults = {
            'ativo': True,
            'is_residual': False,
            'codigos_documento': [],
            'source_type': 'code',
            'source_special_type': None
        }
        defaults.update(kwargs)
        for key, value in defaults.items():
            setattr(categoria, key, value)

        # Property usa_fonte_especial
        def get_usa_fonte_especial():
            return categoria.source_type == "special" and bool(categoria.source_special_type)
        type(categoria).usa_fonte_especial = property(lambda self: get_usa_fonte_especial())

        return categoria

    def _criar_documento_mock(self, doc_id, tipo_documento, data=None):
        """Cria um mock de documento"""
        doc = MagicMock()
        doc.id = doc_id
        doc.tipo_documento = tipo_documento
        doc.data = data
        return doc

    def test_preparar_lote_identifica_peticao_inicial(self):
        """preparar_lote identifica corretamente a petição inicial"""
        from sistemas.gerador_pecas.extrator_resumo_json import GerenciadorFormatosJSON
        from unittest.mock import patch

        db_mock = MagicMock()

        # Categorias: uma especial (petição inicial) e uma por código (petições)
        cat_especial = self._criar_categoria_mock(
            id=1,
            nome="peticao_inicial",
            formato_json="{}",
            instrucoes_extracao=None,
            source_type="special",
            source_special_type="peticao_inicial"
        )
        cat_codigo = self._criar_categoria_mock(
            id=2,
            nome="peticoes",
            formato_json="{}",
            instrucoes_extracao=None,
            codigos_documento=[9500, 500]
        )

        db_mock.query.return_value.filter.return_value.all.return_value = [cat_especial, cat_codigo]

        # Documentos: 3 petições com código 9500
        docs = [
            self._criar_documento_mock("doc1", 9500, datetime(2024, 1, 1)),  # primeira = petição inicial
            self._criar_documento_mock("doc2", 9500, datetime(2024, 2, 1)),
            self._criar_documento_mock("doc3", 9500, datetime(2024, 3, 1)),
        ]

        gerenciador = GerenciadorFormatosJSON(db_mock)
        gerenciador.preparar_lote(docs)

        # doc1 deve estar no cache de fonte especial
        self.assertIn("doc1", gerenciador._doc_fonte_especial)
        self.assertIn("doc1", gerenciador._docs_excluir_codigo)

        # doc2 e doc3 não devem estar
        self.assertNotIn("doc2", gerenciador._doc_fonte_especial)
        self.assertNotIn("doc3", gerenciador._doc_fonte_especial)

    def test_obter_formato_retorna_categoria_especial_para_primeiro_doc(self):
        """obter_formato retorna categoria especial para petição inicial"""
        from sistemas.gerador_pecas.extrator_resumo_json import GerenciadorFormatosJSON, FormatoResumo

        db_mock = MagicMock()

        cat_especial = self._criar_categoria_mock(
            id=1,
            nome="peticao_inicial",
            formato_json='{"especial": true}',
            instrucoes_extracao=None,
            source_type="special",
            source_special_type="peticao_inicial"
        )
        cat_codigo = self._criar_categoria_mock(
            id=2,
            nome="peticoes",
            formato_json='{"codigo": true}',
            instrucoes_extracao=None,
            codigos_documento=[9500, 500]
        )

        db_mock.query.return_value.filter.return_value.all.return_value = [cat_especial, cat_codigo]

        docs = [
            self._criar_documento_mock("doc1", 9500, datetime(2024, 1, 1)),
            self._criar_documento_mock("doc2", 9500, datetime(2024, 2, 1)),
        ]

        gerenciador = GerenciadorFormatosJSON(db_mock)
        gerenciador.preparar_lote(docs)

        # doc1 (petição inicial) deve retornar categoria especial
        formato1 = gerenciador.obter_formato(9500, doc_id="doc1")
        self.assertIsNotNone(formato1)
        self.assertEqual(formato1.categoria_nome, "peticao_inicial")

        # doc2 deve retornar categoria por código
        formato2 = gerenciador.obter_formato(9500, doc_id="doc2")
        self.assertIsNotNone(formato2)
        self.assertEqual(formato2.categoria_nome, "peticoes")

    def test_obter_formato_sem_preparar_lote_usa_codigo(self):
        """Sem chamar preparar_lote, usa apenas código"""
        from sistemas.gerador_pecas.extrator_resumo_json import GerenciadorFormatosJSON

        db_mock = MagicMock()

        cat_codigo = self._criar_categoria_mock(
            id=1,
            nome="peticoes",
            formato_json='{}',
            instrucoes_extracao=None,
            codigos_documento=[9500]
        )

        db_mock.query.return_value.filter.return_value.all.return_value = [cat_codigo]

        gerenciador = GerenciadorFormatosJSON(db_mock)

        # Sem preparar_lote, usa apenas código
        formato = gerenciador.obter_formato(9500, doc_id="doc1")
        self.assertIsNotNone(formato)
        self.assertEqual(formato.categoria_nome, "peticoes")

    def test_obter_formato_usa_residual_para_doc_excluido_sem_categoria_codigo(self):
        """Doc excluído de categoria por código usa residual se não tiver categoria especial"""
        from sistemas.gerador_pecas.extrator_resumo_json import GerenciadorFormatosJSON

        db_mock = MagicMock()

        # Apenas categoria especial, sem categoria por código para 9500
        cat_especial = self._criar_categoria_mock(
            id=1,
            nome="peticao_inicial",
            formato_json='{}',
            instrucoes_extracao=None,
            source_type="special",
            source_special_type="peticao_inicial"
        )
        cat_residual = self._criar_categoria_mock(
            id=2,
            nome="outros",
            formato_json='{}',
            instrucoes_extracao=None,
            is_residual=True
        )

        db_mock.query.return_value.filter.return_value.all.return_value = [cat_especial, cat_residual]

        docs = [
            self._criar_documento_mock("doc1", 9500, datetime(2024, 1, 1)),
            self._criar_documento_mock("doc2", 9500, datetime(2024, 2, 1)),
        ]

        gerenciador = GerenciadorFormatosJSON(db_mock)
        gerenciador.preparar_lote(docs)

        # doc1 tem categoria especial
        formato1 = gerenciador.obter_formato(9500, doc_id="doc1")
        self.assertEqual(formato1.categoria_nome, "peticao_inicial")

        # doc2 não tem categoria por código, usa residual
        formato2 = gerenciador.obter_formato(9500, doc_id="doc2")
        self.assertEqual(formato2.categoria_nome, "outros")


if __name__ == '__main__':
    unittest.main()
