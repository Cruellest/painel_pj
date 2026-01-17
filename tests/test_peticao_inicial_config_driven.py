# tests/test_peticao_inicial_config_driven.py
"""
Testes para validar que a categoria "Petição Inicial" é config-driven.

A categoria especial "peticao_inicial" deve usar APENAS os códigos configurados
no banco de dados (via /api/gerador-pecas/config/admin), sem depender de
constantes hardcoded.

Cenários cobertos:
1. Códigos [500, 9500] configurados → detecção usa exatamente esses códigos
2. Códigos [500, 9500, 10] configurados → detecção aceita 10 sem alterar código
3. Remover código da config → para de aceitar imediatamente
4. Cache não mantém configuração antiga após salvar
5. Documento com código configurado que NÃO é o primeiro → não classifica como PI
"""

import unittest
import sys
import os
from datetime import datetime
from unittest.mock import MagicMock, patch

# Adiciona diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.connection import Base


class TestSourceResolverConfigDriven(unittest.TestCase):
    """
    Testes para verificar que o SourceResolver busca códigos do banco de dados.
    """

    @classmethod
    def setUpClass(cls):
        """Configura banco em memória para todos os testes."""
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False}
        )
        cls.TestingSessionLocal = sessionmaker(bind=cls.engine)
        Base.metadata.create_all(bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        """Limpa recursos."""
        Base.metadata.drop_all(bind=cls.engine)

    def setUp(self):
        """Configura sessão para cada teste."""
        self.db = self.TestingSessionLocal()

        # Limpa dados entre testes
        from sistemas.gerador_pecas.models_config_pecas import CategoriaDocumento
        self.db.query(CategoriaDocumento).delete()
        self.db.commit()

        # Reseta instância global do resolver para cada teste
        from sistemas.gerador_pecas import services_source_resolver
        services_source_resolver._resolver_instance = None

    def tearDown(self):
        """Limpa sessão."""
        self.db.rollback()
        self.db.close()

    def _criar_categoria_peticao_inicial(self, codigos: list):
        """Helper para criar categoria peticao_inicial com códigos específicos."""
        from sistemas.gerador_pecas.models_config_pecas import CategoriaDocumento

        categoria = CategoriaDocumento(
            nome="peticao_inicial",
            titulo="Petição Inicial",
            descricao="Primeiro documento do processo",
            codigos_documento=codigos,
            ativo=True,
            is_primeiro_documento=True,
            ordem=1
        )
        self.db.add(categoria)
        self.db.commit()
        return categoria

    # ==========================================================================
    # TESTE 1: Códigos [500, 9500] configurados
    # ==========================================================================

    def test_codigos_500_9500_configurados(self):
        """
        TESTE: Ao salvar categoria com códigos [500, 9500], a detecção
        usa exatamente esses códigos.
        """
        from sistemas.gerador_pecas.services_source_resolver import (
            get_source_resolver, DocumentoInfo
        )

        # Cria categoria com códigos [500, 9500]
        self._criar_categoria_peticao_inicial([500, 9500])

        resolver = get_source_resolver(self.db)

        # Verifica que códigos válidos são exatamente [500, 9500]
        codigos = resolver.get_codigos_validos("peticao_inicial")
        self.assertEqual(set(codigos), {500, 9500},
            "Códigos válidos devem ser exatamente [500, 9500]")

        # Testa resolução - código 10 NÃO deve ser aceito
        documentos = [
            DocumentoInfo(id="1", codigo=10, data=datetime(2024, 1, 1), ordem=0),
            DocumentoInfo(id="2", codigo=500, data=datetime(2024, 1, 2), ordem=1),
        ]

        result = resolver.resolve("peticao_inicial", documentos)

        # Deve pegar o 500 (primeiro código válido)
        self.assertTrue(result.sucesso)
        self.assertEqual(result.documento_id, "2",
            "Deve retornar documento com código 500, não 10")
        self.assertEqual(result.documento_info.codigo, 500)
        self.assertEqual(result.codigos_usados, [500, 9500])

    # ==========================================================================
    # TESTE 2: Códigos [500, 9500, 10] configurados
    # ==========================================================================

    def test_codigos_500_9500_10_configurados(self):
        """
        TESTE: Ao salvar categoria com códigos [500, 9500, 10], a detecção
        aceita código 10 sem precisar alterar código.
        """
        from sistemas.gerador_pecas.services_source_resolver import (
            get_source_resolver, DocumentoInfo
        )

        # Cria categoria com códigos [500, 9500, 10]
        self._criar_categoria_peticao_inicial([500, 9500, 10])

        resolver = get_source_resolver(self.db)

        # Verifica que códigos válidos incluem 10
        codigos = resolver.get_codigos_validos("peticao_inicial")
        self.assertIn(10, codigos, "Código 10 deve estar nos códigos válidos")
        self.assertIn(500, codigos)
        self.assertIn(9500, codigos)

        # Testa resolução - código 10 DEVE ser aceito quando é o primeiro
        documentos = [
            DocumentoInfo(id="1", codigo=10, data=datetime(2024, 1, 1), ordem=0),
            DocumentoInfo(id="2", codigo=500, data=datetime(2024, 1, 2), ordem=1),
        ]

        result = resolver.resolve("peticao_inicial", documentos)

        # Deve pegar o 10 (primeiro documento)
        self.assertTrue(result.sucesso)
        self.assertEqual(result.documento_id, "1",
            "Deve retornar documento com código 10 (primeiro)")
        self.assertEqual(result.documento_info.codigo, 10)
        self.assertIn(10, result.codigos_usados)

    # ==========================================================================
    # TESTE 3: Remover código para de aceitar imediatamente
    # ==========================================================================

    def test_remover_codigo_para_de_aceitar(self):
        """
        TESTE: Remover um código da config faz com que pare de aceitar imediatamente.
        """
        from sistemas.gerador_pecas.services_source_resolver import (
            get_source_resolver, invalidar_cache_source_resolver, DocumentoInfo
        )
        from sistemas.gerador_pecas.models_config_pecas import CategoriaDocumento

        # Cria categoria com códigos [500, 9500, 10]
        categoria = self._criar_categoria_peticao_inicial([500, 9500, 10])

        resolver = get_source_resolver(self.db)

        # Verifica que 10 é aceito
        codigos = resolver.get_codigos_validos("peticao_inicial")
        self.assertIn(10, codigos)

        # Remove código 10 da categoria
        categoria.codigos_documento = [500, 9500]
        self.db.commit()

        # Invalida cache (simula o que o router faz)
        invalidar_cache_source_resolver("peticao_inicial")

        # Verifica que 10 NÃO é mais aceito
        codigos_apos = resolver.get_codigos_validos("peticao_inicial")
        self.assertNotIn(10, codigos_apos,
            "Código 10 não deve mais ser aceito após remoção")
        self.assertEqual(set(codigos_apos), {500, 9500})

    # ==========================================================================
    # TESTE 4: Cache não mantém configuração antiga após salvar
    # ==========================================================================

    def test_cache_invalidado_ao_salvar(self):
        """
        TESTE: Cache é invalidado ao salvar alterações na config.
        """
        from sistemas.gerador_pecas.services_source_resolver import (
            get_source_resolver, invalidar_cache_source_resolver
        )
        from sistemas.gerador_pecas.models_config_pecas import CategoriaDocumento

        # Cria categoria inicial com [500, 9500]
        categoria = self._criar_categoria_peticao_inicial([500, 9500])

        resolver = get_source_resolver(self.db)

        # Popula cache
        codigos_v1 = resolver.get_codigos_validos("peticao_inicial")
        self.assertEqual(set(codigos_v1), {500, 9500})

        # Altera categoria para [500, 9500, 10, 20]
        categoria.codigos_documento = [500, 9500, 10, 20]
        self.db.commit()

        # Sem invalidar cache, ainda retorna valores antigos
        codigos_cache = resolver.get_codigos_validos("peticao_inicial")
        self.assertEqual(set(codigos_cache), {500, 9500},
            "Cache ainda tem valores antigos")

        # Invalida cache
        invalidar_cache_source_resolver("peticao_inicial")

        # Agora deve retornar novos valores
        codigos_v2 = resolver.get_codigos_validos("peticao_inicial")
        self.assertEqual(set(codigos_v2), {500, 9500, 10, 20},
            "Após invalidar cache, deve retornar novos valores")

    # ==========================================================================
    # TESTE 5: Documento com código configurado que NÃO é o primeiro
    # ==========================================================================

    def test_codigo_configurado_nao_primeiro_nao_classifica(self):
        """
        TESTE: Documento com código configurado que NÃO é o primeiro do processo
        não é classificado como petição inicial.
        """
        from sistemas.gerador_pecas.services_source_resolver import (
            get_source_resolver, DocumentoInfo
        )

        # Cria categoria com códigos [500, 9500, 10]
        self._criar_categoria_peticao_inicial([500, 9500, 10])

        resolver = get_source_resolver(self.db)

        # Documentos: código 500 é o primeiro, código 10 é o segundo
        documentos = [
            DocumentoInfo(id="1", codigo=500, data=datetime(2024, 1, 1), ordem=0),
            DocumentoInfo(id="2", codigo=10, data=datetime(2024, 1, 2), ordem=1),
            DocumentoInfo(id="3", codigo=9500, data=datetime(2024, 1, 3), ordem=2),
        ]

        result = resolver.resolve("peticao_inicial", documentos)

        # Deve pegar o 500 (primeiro documento)
        self.assertTrue(result.sucesso)
        self.assertEqual(result.documento_id, "1",
            "Deve retornar o primeiro documento (código 500)")
        self.assertNotEqual(result.documento_id, "2",
            "Não deve retornar o código 10 que é o segundo")

    # ==========================================================================
    # TESTE 6: Fallback quando categoria não existe
    # ==========================================================================

    def test_fallback_sem_categoria_no_banco(self):
        """
        TESTE: Quando a categoria não existe no banco, usa códigos de fallback.
        """
        from sistemas.gerador_pecas.services_source_resolver import (
            get_source_resolver, SourceResolver
        )

        # NÃO cria categoria no banco
        resolver = get_source_resolver(self.db)

        # Deve usar fallback [9500, 500]
        codigos = resolver.get_codigos_validos("peticao_inicial")
        self.assertEqual(set(codigos), set(SourceResolver.CODIGOS_PETICAO_INICIAL_FALLBACK),
            f"Deve usar fallback {SourceResolver.CODIGOS_PETICAO_INICIAL_FALLBACK}")

    # ==========================================================================
    # TESTE 7: Informações da fonte incluem códigos do banco
    # ==========================================================================

    def test_get_source_info_retorna_codigos_do_banco(self):
        """
        TESTE: get_source_info retorna os códigos configurados no banco.
        """
        from sistemas.gerador_pecas.services_source_resolver import get_source_resolver

        # Cria categoria com códigos customizados
        self._criar_categoria_peticao_inicial([500, 9500, 10, 25, 30])

        resolver = get_source_resolver(self.db)
        info = resolver.get_source_info("peticao_inicial")

        self.assertIsNotNone(info)
        self.assertEqual(info["key"], "peticao_inicial")
        self.assertEqual(info["categoria_nome"], "peticao_inicial")
        self.assertEqual(set(info["codigos_validos"]), {500, 9500, 10, 25, 30},
            "Deve retornar códigos configurados no banco")


class TestInvalidacaoCacheNoRouter(unittest.TestCase):
    """
    Testes para verificar que o router invalida o cache ao salvar categorias.
    """

    def test_router_importa_invalidar_cache(self):
        """
        TESTE: O router de config importa a função de invalidação de cache.
        """
        # Verifica que a importação não gera erro
        from sistemas.gerador_pecas.router_config_pecas import invalidar_cache_source_resolver
        self.assertIsNotNone(invalidar_cache_source_resolver)


# =============================================================================
# RUNNER
# =============================================================================

def run_tests():
    """Executa todos os testes."""
    print("\n" + "=" * 70)
    print("TESTES: Petição Inicial - Config-Driven")
    print("=" * 70 + "\n")

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestSourceResolverConfigDriven))
    suite.addTests(loader.loadTestsFromTestCase(TestInvalidacaoCacheNoRouter))

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
