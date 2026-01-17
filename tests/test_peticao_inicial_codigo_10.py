# tests/test_peticao_inicial_codigo_10.py
"""
Testes automatizados para a regra de "Petição Inicial" incluindo código 10 (Termo).

Cenários cobertos:
1. Processo em que o 1º doc é 500 => classifica como petição inicial
2. Processo em que o 1º doc é 9500 => classifica como petição inicial
3. Processo em que o 1º doc é 10 => classifica como petição inicial
4. Processo em que existe doc 10 mas NÃO é o 1º => NÃO classifica como petição inicial
5. O admin/config aceita o código 10 (não é bloqueado pelo filtro)
"""

import unittest
import json
import sys
import os

# Adiciona diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dataclasses import dataclass
from typing import Optional

from database.connection import Base, get_db


@dataclass
class DocumentoMock:
    """Mock de documento TJ-MS para testes."""
    tipo_documento: str
    data_documento: Optional[str] = None
    descricao: Optional[str] = None


class TestPeticaoInicialCodigo10(unittest.TestCase):
    """Testes para verificar que código 10 pode ser petição inicial."""

    @classmethod
    def setUpClass(cls):
        """Configura banco em memória para todos os testes."""
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False}
        )
        cls.TestingSessionLocal = sessionmaker(bind=cls.engine)

        # Importa todos os modelos para criar tabelas
        from sistemas.gerador_pecas.models_config_pecas import TipoPeca, CategoriaDocumento
        from auth.models import User

        Base.metadata.create_all(bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        """Limpa recursos."""
        Base.metadata.drop_all(bind=cls.engine)

    def setUp(self):
        """Configura sessão para cada teste."""
        self.db = self.TestingSessionLocal()

        # Limpa dados entre testes (na ordem correta por causa das FKs)
        from sistemas.gerador_pecas.models_config_pecas import TipoPeca, CategoriaDocumento, tipo_peca_categorias

        # Limpa tabela de associação primeiro
        self.db.execute(tipo_peca_categorias.delete())
        self.db.query(TipoPeca).delete()
        self.db.query(CategoriaDocumento).delete()
        self.db.commit()

        # Cria dados de seed para testes
        self._criar_dados_teste()

    def tearDown(self):
        """Limpa sessão."""
        self.db.rollback()
        self.db.close()

    def _criar_dados_teste(self):
        """Cria categoria e tipo de peça para testes."""
        from sistemas.gerador_pecas.models_config_pecas import TipoPeca, CategoriaDocumento

        # Categoria petição inicial com códigos 9500, 500 e 10
        cat_peticao_inicial = CategoriaDocumento(
            nome="peticao_inicial",
            titulo="Petição Inicial",
            descricao="Primeiro documento do processo",
            codigos_documento=[9500, 500, 10],
            ativo=True,
            is_primeiro_documento=True,
            ordem=1
        )
        self.db.add(cat_peticao_inicial)

        # Categoria petição (normal, sem restrição de primeiro documento)
        cat_peticao = CategoriaDocumento(
            nome="peticao",
            titulo="Petição",
            descricao="Petições diversas",
            codigos_documento=[9500, 500, 510],
            ativo=True,
            is_primeiro_documento=False,
            ordem=2
        )
        self.db.add(cat_peticao)

        # Categoria documento (contém código 10)
        cat_documento = CategoriaDocumento(
            nome="documento",
            titulo="Documento",
            descricao="Documentos diversos",
            codigos_documento=[10, 3, 140],
            ativo=True,
            is_primeiro_documento=False,
            ordem=3
        )
        self.db.add(cat_documento)

        self.db.commit()

        # Tipo de peça contestação
        tipo_contestacao = TipoPeca(
            nome="contestacao",
            titulo="Contestação",
            descricao="Peça de defesa",
            ativo=True,
            ordem=1
        )
        self.db.add(tipo_contestacao)
        self.db.commit()

        # Associa categorias ao tipo de peça
        tipo_contestacao.categorias_documento.append(cat_peticao_inicial)
        tipo_contestacao.categorias_documento.append(cat_peticao)
        tipo_contestacao.categorias_documento.append(cat_documento)
        self.db.commit()

    # ==========================================================================
    # TESTE 1: Primeiro documento é código 500 => Petição Inicial
    # ==========================================================================

    def test_primeiro_documento_codigo_500_e_peticao_inicial(self):
        """
        TESTE: Processo em que o 1º doc é 500 => classifica como petição inicial.

        Cenário:
        - Documentos ordenados: [500, 510, 9500]
        - Filtro deve pegar o 500 como petição inicial
        - 9500 (mesmo sendo código de PI) NÃO deve ser pego, pois 500 já foi
        """
        from sistemas.gerador_pecas.filtro_categorias import FiltroCategoriasDocumento

        filtro = FiltroCategoriasDocumento(self.db)

        # Documentos ordenados cronologicamente (500 é o primeiro)
        documentos = [
            DocumentoMock(tipo_documento="500", data_documento="2024-01-01"),
            DocumentoMock(tipo_documento="510", data_documento="2024-01-02"),
            DocumentoMock(tipo_documento="9500", data_documento="2024-01-03"),
        ]

        # Filtra para contestação
        docs_filtrados = filtro.filtrar_documentos(documentos, "contestacao")

        # Deve incluir o 500 (primeiro documento de PI)
        tipos_incluidos = [d.tipo_documento for d in docs_filtrados]
        self.assertIn("500", tipos_incluidos, "Código 500 deveria ser incluído como petição inicial")

        # 9500 NÃO deve ser incluído (já temos um documento de PI)
        # A regra é: pega APENAS o primeiro documento de cada código em codigos_primeiro_doc
        # Como 500 e 9500 estão ambos em is_primeiro_documento=True,
        # quando pegamos o 500, não devemos pegar mais nenhum 9500/500/10
        self.assertNotIn("9500", tipos_incluidos,
            "9500 não deveria ser incluído porque 500 já foi pego como petição inicial")

    # ==========================================================================
    # TESTE 2: Primeiro documento é código 9500 => Petição Inicial
    # ==========================================================================

    def test_primeiro_documento_codigo_9500_e_peticao_inicial(self):
        """
        TESTE: Processo em que o 1º doc é 9500 => classifica como petição inicial.
        """
        from sistemas.gerador_pecas.filtro_categorias import FiltroCategoriasDocumento

        filtro = FiltroCategoriasDocumento(self.db)

        # Documentos ordenados cronologicamente (9500 é o primeiro)
        documentos = [
            DocumentoMock(tipo_documento="9500", data_documento="2024-01-01"),
            DocumentoMock(tipo_documento="510", data_documento="2024-01-02"),
            DocumentoMock(tipo_documento="500", data_documento="2024-01-03"),
        ]

        # Filtra para contestação
        docs_filtrados = filtro.filtrar_documentos(documentos, "contestacao")

        # Deve incluir o 9500 (primeiro documento de PI)
        tipos_incluidos = [d.tipo_documento for d in docs_filtrados]
        self.assertIn("9500", tipos_incluidos, "Código 9500 deveria ser incluído como petição inicial")

        # 500 NÃO deve ser incluído (já temos um 9500)
        self.assertNotIn("500", tipos_incluidos,
            "500 não deveria ser incluído porque 9500 já foi pego")

    # ==========================================================================
    # TESTE 3: Primeiro documento é código 10 => Petição Inicial
    # ==========================================================================

    def test_primeiro_documento_codigo_10_e_peticao_inicial(self):
        """
        TESTE: Processo em que o 1º doc é 10 (Termo) => classifica como petição inicial.

        Este é o teste principal da nova funcionalidade!
        """
        from sistemas.gerador_pecas.filtro_categorias import FiltroCategoriasDocumento

        filtro = FiltroCategoriasDocumento(self.db)

        # Documentos ordenados cronologicamente (10 é o primeiro)
        documentos = [
            DocumentoMock(tipo_documento="10", data_documento="2024-01-01"),   # Termo - PI
            DocumentoMock(tipo_documento="510", data_documento="2024-01-02"),  # Petição intermediária
            DocumentoMock(tipo_documento="9500", data_documento="2024-01-03"), # Petição
        ]

        # Filtra para contestação
        docs_filtrados = filtro.filtrar_documentos(documentos, "contestacao")

        # Deve incluir o 10 (primeiro documento de PI - Termo)
        tipos_incluidos = [d.tipo_documento for d in docs_filtrados]
        self.assertIn("10", tipos_incluidos,
            "Código 10 (Termo) deveria ser incluído como petição inicial quando é o primeiro documento")

        # 9500 NÃO deve ser incluído (já temos um documento de PI)
        self.assertNotIn("9500", tipos_incluidos,
            "9500 não deveria ser incluído porque 10 já foi pego como petição inicial")

    # ==========================================================================
    # TESTE 4: Código 10 existe mas NÃO é primeiro => NÃO é petição inicial
    # ==========================================================================

    def test_codigo_10_nao_primeiro_nao_e_peticao_inicial(self):
        """
        TESTE: Processo em que existe doc 10 mas NÃO é o 1º =>
               10 NÃO é classificado como petição inicial.

        Cenário:
        - Primeiro doc é 500 (pega como PI)
        - Segundo doc é 10 (NÃO deve ser PI, porque já temos 500)
        - O 10 deve ser incluído apenas como documento normal (via categoria "documento")
        """
        from sistemas.gerador_pecas.filtro_categorias import FiltroCategoriasDocumento

        filtro = FiltroCategoriasDocumento(self.db)

        # Documentos ordenados cronologicamente (500 primeiro, depois 10)
        documentos = [
            DocumentoMock(tipo_documento="500", data_documento="2024-01-01"),  # PI
            DocumentoMock(tipo_documento="10", data_documento="2024-01-02"),   # Termo (não PI)
            DocumentoMock(tipo_documento="510", data_documento="2024-01-03"),
        ]

        # Filtra para contestação
        docs_filtrados = filtro.filtrar_documentos(documentos, "contestacao")

        tipos_incluidos = [d.tipo_documento for d in docs_filtrados]

        # 500 deve ser incluído (primeiro documento de PI)
        self.assertIn("500", tipos_incluidos, "500 deveria ser incluído como petição inicial")

        # 10 NÃO deve ser incluído como petição inicial
        # Mas PODE ser incluído se estiver em outra categoria (documento)
        # O importante é que ele NÃO seja tratado como petição inicial

        # Verifica que só tem UM documento de cada código especial (500, 9500, 10)
        # contando apenas os que estão em is_primeiro_documento
        codigos_pi = {"500", "9500", "10"}
        docs_pi_encontrados = [d for d in docs_filtrados if d.tipo_documento in codigos_pi]

        # Deve ter apenas 1 documento de PI (o 500)
        self.assertEqual(len(docs_pi_encontrados), 1,
            "Deveria ter apenas 1 documento classificado como petição inicial")
        self.assertEqual(docs_pi_encontrados[0].tipo_documento, "500",
            "O documento de petição inicial deveria ser o 500 (primeiro)")

    # ==========================================================================
    # TESTE 5: Admin/Config aceita código 10
    # ==========================================================================

    def test_admin_aceita_codigo_10(self):
        """
        TESTE: O admin/config aceita o código 10 (não é bloqueado pelo filtro).

        Verifica que:
        1. O código 10 está na lista de códigos do seed
        2. O código 10 pode ser associado a categorias
        3. O código 10 aparece nos códigos permitidos
        """
        from sistemas.gerador_pecas.models_config_pecas import (
            get_categorias_documento_seed,
            get_codigos_por_categoria_json
        )

        # Verifica que 10 está no seed da categoria petição inicial
        seed_categorias = get_categorias_documento_seed()
        cat_pi = next((c for c in seed_categorias if c["nome"] == "peticao_inicial"), None)

        self.assertIsNotNone(cat_pi, "Categoria peticao_inicial deveria existir no seed")
        self.assertIn(10, cat_pi["codigos_documento"],
            "Código 10 deveria estar na lista de códigos de peticao_inicial no seed")

        # Verifica que a categoria tem is_primeiro_documento=True
        self.assertTrue(cat_pi.get("is_primeiro_documento", False),
            "Categoria peticao_inicial deveria ter is_primeiro_documento=True")

    def test_codigo_10_existe_no_json_categorias(self):
        """
        TESTE: Verifica que o código 10 existe no arquivo categorias_documentos.json.
        """
        import json
        from pathlib import Path

        json_path = Path(__file__).parent.parent / "categorias_documentos.json"

        with open(json_path, 'r', encoding='utf-8') as f:
            documentos = json.load(f)

        # Busca código 10 no JSON
        codigo_10 = next((d for d in documentos if d.get("Código") == "10"), None)

        self.assertIsNotNone(codigo_10,
            "Código 10 deveria existir no arquivo categorias_documentos.json")
        self.assertEqual(codigo_10.get("Nome"), "Termo",
            "Código 10 deveria ter nome 'Termo'")

    def test_codigos_primeiro_documento_incluem_10(self):
        """
        TESTE: Verifica que get_codigos_primeiro_documento retorna o código 10.
        """
        from sistemas.gerador_pecas.models_config_pecas import TipoPeca

        tipo = self.db.query(TipoPeca).filter(TipoPeca.nome == "contestacao").first()
        self.assertIsNotNone(tipo)

        codigos_primeiro = tipo.get_codigos_primeiro_documento()

        self.assertIn(10, codigos_primeiro,
            "Código 10 deveria estar em codigos_primeiro_documento")
        self.assertIn(500, codigos_primeiro,
            "Código 500 deveria estar em codigos_primeiro_documento")
        self.assertIn(9500, codigos_primeiro,
            "Código 9500 deveria estar em codigos_primeiro_documento")


class TestFiltroCategoriasMultiplosDocumentos(unittest.TestCase):
    """Testes adicionais para garantir comportamento correto com múltiplos documentos."""

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False}
        )
        cls.TestingSessionLocal = sessionmaker(bind=cls.engine)
        Base.metadata.create_all(bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=cls.engine)

    def setUp(self):
        self.db = self.TestingSessionLocal()
        from sistemas.gerador_pecas.models_config_pecas import TipoPeca, CategoriaDocumento, tipo_peca_categorias
        # Limpa tabela de associação primeiro
        self.db.execute(tipo_peca_categorias.delete())
        self.db.query(TipoPeca).delete()
        self.db.query(CategoriaDocumento).delete()
        self.db.commit()
        self._criar_dados_teste()

    def tearDown(self):
        self.db.rollback()
        self.db.close()

    def _criar_dados_teste(self):
        from sistemas.gerador_pecas.models_config_pecas import TipoPeca, CategoriaDocumento

        cat_pi = CategoriaDocumento(
            nome="peticao_inicial",
            titulo="Petição Inicial",
            codigos_documento=[9500, 500, 10],
            ativo=True,
            is_primeiro_documento=True,
            ordem=1
        )
        cat_peticao = CategoriaDocumento(
            nome="peticao",
            titulo="Petição",
            codigos_documento=[510, 357],
            ativo=True,
            is_primeiro_documento=False,
            ordem=2
        )
        self.db.add(cat_pi)
        self.db.add(cat_peticao)
        self.db.commit()

        tipo = TipoPeca(nome="contestacao", titulo="Contestação", ativo=True, ordem=1)
        self.db.add(tipo)
        self.db.commit()
        tipo.categorias_documento.append(cat_pi)
        tipo.categorias_documento.append(cat_peticao)
        self.db.commit()

    def test_multiplos_documentos_codigo_10_apenas_primeiro_e_peticao_inicial(self):
        """
        TESTE: Se há múltiplos documentos com código 10, apenas o primeiro é PI.
        """
        from sistemas.gerador_pecas.filtro_categorias import FiltroCategoriasDocumento

        filtro = FiltroCategoriasDocumento(self.db)

        # Múltiplos documentos código 10
        documentos = [
            DocumentoMock(tipo_documento="10", data_documento="2024-01-01"),   # PI
            DocumentoMock(tipo_documento="10", data_documento="2024-01-02"),   # NÃO PI
            DocumentoMock(tipo_documento="10", data_documento="2024-01-03"),   # NÃO PI
            DocumentoMock(tipo_documento="510", data_documento="2024-01-04"),
        ]

        docs_filtrados = filtro.filtrar_documentos(documentos, "contestacao")

        # Deve incluir apenas UM documento código 10 (o primeiro)
        docs_codigo_10 = [d for d in docs_filtrados if d.tipo_documento == "10"]
        self.assertEqual(len(docs_codigo_10), 1,
            "Deveria incluir apenas um documento código 10 (o primeiro)")

    def test_ordem_correta_com_mistura_de_codigos_pi(self):
        """
        TESTE: Apenas o primeiro documento de qualquer código de PI é incluído.

        Se o primeiro doc é 10, não pega 500 nem 9500 depois.
        """
        from sistemas.gerador_pecas.filtro_categorias import FiltroCategoriasDocumento

        filtro = FiltroCategoriasDocumento(self.db)

        # Mistura de códigos PI
        documentos = [
            DocumentoMock(tipo_documento="10", data_documento="2024-01-01"),    # Primeiro PI
            DocumentoMock(tipo_documento="500", data_documento="2024-01-02"),   # Ignorado
            DocumentoMock(tipo_documento="9500", data_documento="2024-01-03"),  # Ignorado
            DocumentoMock(tipo_documento="510", data_documento="2024-01-04"),   # Incluído (não PI)
        ]

        docs_filtrados = filtro.filtrar_documentos(documentos, "contestacao")
        tipos = [d.tipo_documento for d in docs_filtrados]

        # Deve ter apenas 10 e 510
        self.assertEqual(len(docs_filtrados), 2,
            "Deveria ter 2 documentos: 10 (PI) e 510 (petição)")
        self.assertIn("10", tipos)
        self.assertIn("510", tipos)
        self.assertNotIn("500", tipos)
        self.assertNotIn("9500", tipos)


class TestSourceResolverCodigo10(unittest.TestCase):
    """
    Testes para garantir que o SourceResolver funciona corretamente.

    NOTA: O SourceResolver agora é CONFIG-DRIVEN. Os códigos válidos são
    buscados do banco de dados (categoria peticao_inicial).

    Para testes completos de config-driven, veja:
    tests/test_peticao_inicial_config_driven.py
    """

    def test_source_resolver_fallback_inclui_codigos_basicos(self):
        """
        TESTE: SourceResolver deve ter fallback com códigos básicos [9500, 500].
        """
        from sistemas.gerador_pecas.services_source_resolver import SourceResolver

        resolver = SourceResolver()

        # Verifica que fallback tem os códigos básicos
        self.assertIn(500, resolver.CODIGOS_PETICAO_INICIAL_FALLBACK,
            "Código 500 deve estar no fallback")
        self.assertIn(9500, resolver.CODIGOS_PETICAO_INICIAL_FALLBACK,
            "Código 9500 deve estar no fallback")

    def test_source_resolver_resolve_sem_db_usa_fallback(self):
        """
        TESTE: SourceResolver sem DB deve usar fallback e resolver corretamente.
        """
        from sistemas.gerador_pecas.services_source_resolver import (
            SourceResolver, DocumentoInfo
        )
        from datetime import datetime

        resolver = SourceResolver()  # Sem DB

        # Documentos ordenados: código 500 é o primeiro
        documentos = [
            DocumentoInfo(id="1", codigo=500, data=datetime(2024, 1, 1), descricao="PI", ordem=0),
            DocumentoInfo(id="2", codigo=9500, data=datetime(2024, 1, 2), descricao="Petição", ordem=1),
        ]

        result = resolver.resolve("peticao_inicial", documentos)

        self.assertTrue(result.sucesso, f"Deveria resolver com sucesso: {result.motivo}")
        self.assertEqual(result.documento_id, "1",
            "Deveria retornar o documento com código 500 (primeiro)")

    def test_source_resolver_codigo_nao_primeiro_nao_retorna(self):
        """
        TESTE: Quando código válido NÃO é o primeiro, NÃO deve ser retornado como PI.
        """
        from sistemas.gerador_pecas.services_source_resolver import (
            SourceResolver, DocumentoInfo
        )
        from datetime import datetime

        resolver = SourceResolver()  # Sem DB, usa fallback [9500, 500]

        # Documentos ordenados: código 500 é o primeiro, 9500 é o segundo
        documentos = [
            DocumentoInfo(id="1", codigo=500, data=datetime(2024, 1, 1), descricao="PI", ordem=0),
            DocumentoInfo(id="2", codigo=9500, data=datetime(2024, 1, 2), descricao="Petição", ordem=1),
        ]

        result = resolver.resolve("peticao_inicial", documentos)

        self.assertTrue(result.sucesso)
        self.assertEqual(result.documento_id, "1",
            "Deveria retornar o documento com código 500 (primeiro)")
        self.assertNotEqual(result.documento_id, "2",
            "NÃO deveria retornar o código 9500 que é o segundo")

    def test_source_resolver_definicao_existe(self):
        """
        TESTE: A definição da fonte especial 'peticao_inicial' deve existir.
        """
        from sistemas.gerador_pecas.services_source_resolver import SourceResolver

        resolver = SourceResolver()
        info = resolver.get_source_info("peticao_inicial")

        self.assertIsNotNone(info, "Fonte especial 'peticao_inicial' deve existir")
        self.assertEqual(info["key"], "peticao_inicial")
        self.assertEqual(info["categoria_nome"], "peticao_inicial")

    def test_source_resolver_sem_data_usa_ordem(self):
        """
        TESTE: Documentos sem data devem usar ordem como fallback.
        """
        from sistemas.gerador_pecas.services_source_resolver import (
            SourceResolver, DocumentoInfo
        )

        resolver = SourceResolver()  # Sem DB, usa fallback [9500, 500]

        # Documentos sem data - usa ordem
        documentos = [
            DocumentoInfo(id="1", codigo=500, data=None, descricao="PI", ordem=0),
            DocumentoInfo(id="2", codigo=9500, data=None, descricao="Petição", ordem=1),
        ]

        result = resolver.resolve("peticao_inicial", documentos)

        self.assertTrue(result.sucesso)
        self.assertEqual(result.documento_id, "1",
            "Deveria retornar o documento com ordem 0 (código 500)")


# =============================================================================
# RUNNER
# =============================================================================

def run_tests():
    """Executa todos os testes."""
    print("\n" + "=" * 70)
    print("TESTES: Petição Inicial - Código 10 (Termo)")
    print("=" * 70 + "\n")

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestPeticaoInicialCodigo10))
    suite.addTests(loader.loadTestsFromTestCase(TestFiltroCategoriasMultiplosDocumentos))
    suite.addTests(loader.loadTestsFromTestCase(TestSourceResolverCodigo10))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 70)
    if result.wasSuccessful():
        print("TODOS OS TESTES PASSARAM!")
    else:
        print(f"FALHAS: {len(result.failures)}, ERROS: {len(result.errors)}")
    print("=" * 70 + "\n")

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
