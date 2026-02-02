# tests/test_route_system_map.py
"""
Testes para o sistema de mapeamento rota -> sistema.

Testa:
- Match exact funciona
- Match prefix funciona
- Prefix mais especifico vence
- Sem match => unknown
- Alterar nome reflete corretamente
"""

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from admin.models_performance import RouteSystemMap, PerformanceLog
from admin.router_performance import get_system_name_for_route, enrich_log_with_system
from database.connection import Base


class RouteSystemMapModelTests(unittest.TestCase):
    """Testes unitarios do modelo RouteSystemMap."""

    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False}
        )
        self.Session = sessionmaker(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = self.Session()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)

    def _create_mapping(self, pattern, system_name, match_type='prefix', priority=0):
        mapping = RouteSystemMap(
            route_pattern=pattern,
            system_name=system_name,
            match_type=match_type,
            priority=priority
        )
        self.db.add(mapping)
        self.db.commit()
        return mapping

    # ========================================
    # TESTES DE MATCH EXACT
    # ========================================

    def test_exact_match_works(self):
        """Match exact funciona corretamente."""
        mapping = self._create_mapping('/api/gerador-pecas/gerar', 'Gerador de Pecas', 'exact')

        self.assertTrue(mapping.matches('/api/gerador-pecas/gerar'))
        self.assertFalse(mapping.matches('/api/gerador-pecas/gerar/extra'))
        self.assertFalse(mapping.matches('/api/gerador-pecas'))

    def test_exact_match_wins_over_prefix(self):
        """Match exact tem prioridade sobre prefix."""
        self._create_mapping('/api/gerador', 'Sistema Geral', 'prefix')
        exact = self._create_mapping('/api/gerador-pecas/gerar', 'Gerador Especifico', 'exact')

        mappings = self.db.query(RouteSystemMap).all()
        result = get_system_name_for_route('/api/gerador-pecas/gerar', mappings)

        self.assertEqual(result, 'Gerador Especifico')

    # ========================================
    # TESTES DE MATCH PREFIX
    # ========================================

    def test_prefix_match_works(self):
        """Match prefix funciona corretamente."""
        mapping = self._create_mapping('/api/gerador-pecas', 'Gerador de Pecas', 'prefix')

        self.assertTrue(mapping.matches('/api/gerador-pecas'))
        self.assertTrue(mapping.matches('/api/gerador-pecas/gerar'))
        self.assertTrue(mapping.matches('/api/gerador-pecas/lista/123'))
        self.assertFalse(mapping.matches('/api/outro-sistema'))

    def test_longer_prefix_wins(self):
        """Prefix mais especifico (mais longo) vence."""
        self._create_mapping('/api', 'API Geral', 'prefix')
        self._create_mapping('/api/gerador-pecas', 'Gerador de Pecas', 'prefix')
        self._create_mapping('/api/gerador-pecas/gerar', 'Gerador Gerar', 'prefix')

        mappings = self.db.query(RouteSystemMap).all()

        # Deve usar o prefix mais especifico
        result1 = get_system_name_for_route('/api/gerador-pecas/gerar/123', mappings)
        self.assertEqual(result1, 'Gerador Gerar')

        result2 = get_system_name_for_route('/api/gerador-pecas/lista', mappings)
        self.assertEqual(result2, 'Gerador de Pecas')

        result3 = get_system_name_for_route('/api/outro', mappings)
        self.assertEqual(result3, 'API Geral')

    # ========================================
    # TESTES DE MATCH REGEX
    # ========================================

    def test_regex_match_works(self):
        """Match regex funciona corretamente."""
        mapping = self._create_mapping(r'/api/pecas/\d+', 'Pecas com ID', 'regex')

        self.assertTrue(mapping.matches('/api/pecas/123'))
        self.assertTrue(mapping.matches('/api/pecas/456789'))
        self.assertFalse(mapping.matches('/api/pecas/abc'))
        self.assertFalse(mapping.matches('/api/pecas/'))

    def test_regex_uses_priority(self):
        """Regex usa o campo priority para resolver conflitos."""
        self._create_mapping(r'/api/.*', 'Baixa Prioridade', 'regex', priority=10)
        self._create_mapping(r'/api/gerador.*', 'Alta Prioridade', 'regex', priority=100)

        mappings = self.db.query(RouteSystemMap).all()
        result = get_system_name_for_route('/api/gerador-pecas/test', mappings)

        self.assertEqual(result, 'Alta Prioridade')

    def test_invalid_regex_returns_false(self):
        """Regex invalida retorna False no match."""
        mapping = self._create_mapping('[invalid(regex', 'Sistema', 'regex')
        self.assertFalse(mapping.matches('/qualquer/rota'))

    # ========================================
    # TESTES DE SEM MATCH
    # ========================================

    def test_no_match_returns_unknown(self):
        """Sem match retorna 'unknown'."""
        self._create_mapping('/api/gerador-pecas', 'Gerador de Pecas', 'prefix')

        mappings = self.db.query(RouteSystemMap).all()
        result = get_system_name_for_route('/api/outro-sistema', mappings)

        self.assertEqual(result, 'unknown')

    def test_empty_mappings_returns_unknown(self):
        """Lista vazia de mapeamentos retorna 'unknown'."""
        result = get_system_name_for_route('/api/qualquer', [])
        self.assertEqual(result, 'unknown')

    def test_empty_route_returns_unknown(self):
        """Rota vazia retorna 'unknown'."""
        self._create_mapping('/api', 'API', 'prefix')
        mappings = self.db.query(RouteSystemMap).all()

        result = get_system_name_for_route('', mappings)
        self.assertEqual(result, 'unknown')

        result2 = get_system_name_for_route(None, mappings)
        self.assertEqual(result2, 'unknown')

    # ========================================
    # TESTES DE ENRICH LOG
    # ========================================

    def test_enrich_log_adds_system_name(self):
        """enrich_log_with_system adiciona system_name ao dict."""
        self._create_mapping('/api/gerador-pecas', 'Gerador de Pecas', 'prefix')
        mappings = self.db.query(RouteSystemMap).all()

        log_dict = {
            'id': 1,
            'route': '/api/gerador-pecas/gerar',
            'action': 'gerar_peca'
        }

        result = enrich_log_with_system(log_dict, mappings)

        self.assertEqual(result['system_name'], 'Gerador de Pecas')
        self.assertEqual(result['id'], 1)
        self.assertEqual(result['route'], '/api/gerador-pecas/gerar')

    def test_enrich_log_unknown_when_no_match(self):
        """enrich_log_with_system retorna unknown quando nao casa."""
        self._create_mapping('/api/gerador-pecas', 'Gerador de Pecas', 'prefix')
        mappings = self.db.query(RouteSystemMap).all()

        log_dict = {
            'id': 2,
            'route': '/api/outro-sistema/action',
            'action': 'outra_action'
        }

        result = enrich_log_with_system(log_dict, mappings)

        self.assertEqual(result['system_name'], 'unknown')

    # ========================================
    # TESTES DE ATUALIZACAO
    # ========================================

    def test_update_system_name_reflects_in_match(self):
        """Alterar nome do sistema reflete nas consultas."""
        mapping = self._create_mapping('/api/gerador-pecas', 'Nome Antigo', 'prefix')
        mappings = self.db.query(RouteSystemMap).all()

        # Antes da alteracao
        result1 = get_system_name_for_route('/api/gerador-pecas/test', mappings)
        self.assertEqual(result1, 'Nome Antigo')

        # Altera o nome
        mapping.system_name = 'Nome Novo'
        self.db.commit()

        # Recarrega e verifica
        mappings = self.db.query(RouteSystemMap).all()
        result2 = get_system_name_for_route('/api/gerador-pecas/test', mappings)
        self.assertEqual(result2, 'Nome Novo')

    # ========================================
    # TESTES DE TO_DICT
    # ========================================

    def test_to_dict_returns_all_fields(self):
        """to_dict retorna todos os campos corretamente."""
        mapping = self._create_mapping('/api/test', 'Sistema Test', 'prefix', 50)

        result = mapping.to_dict()

        self.assertEqual(result['route_pattern'], '/api/test')
        self.assertEqual(result['system_name'], 'Sistema Test')
        self.assertEqual(result['match_type'], 'prefix')
        self.assertEqual(result['priority'], 50)
        self.assertIsNotNone(result['id'])
        self.assertIsNotNone(result['created_at'])


class RouteSystemMapIntegrationTests(unittest.TestCase):
    """Testes de integracao simulando cenarios reais."""

    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False}
        )
        self.Session = sessionmaker(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = self.Session()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)

    def _create_mapping(self, pattern, system_name, match_type='prefix', priority=0):
        mapping = RouteSystemMap(
            route_pattern=pattern,
            system_name=system_name,
            match_type=match_type,
            priority=priority
        )
        self.db.add(mapping)
        self.db.commit()
        return mapping

    def test_realistic_route_mapping_scenario(self):
        """Cenario realista com multiplos sistemas."""
        # Configura mapeamentos como um admin faria
        self._create_mapping('/api/gerador-pecas', 'Gerador de Pecas', 'prefix')
        self._create_mapping('/api/categorias-resumo', 'Categorias Resumo', 'prefix')
        self._create_mapping('/api/prompts-modulos', 'Prompts Modulos', 'prefix')
        self._create_mapping('/api/pedido-calculo', 'Pedido Calculo', 'prefix')
        self._create_mapping('/api/auth', 'Autenticacao', 'prefix')

        mappings = self.db.query(RouteSystemMap).all()

        # Testa diversas rotas
        test_cases = [
            ('/api/gerador-pecas/gerar', 'Gerador de Pecas'),
            ('/api/gerador-pecas/lista/123', 'Gerador de Pecas'),
            ('/api/categorias-resumo/atualizar', 'Categorias Resumo'),
            ('/api/prompts-modulos/criar', 'Prompts Modulos'),
            ('/api/pedido-calculo/processar', 'Pedido Calculo'),
            ('/api/auth/login', 'Autenticacao'),
            ('/api/outro-endpoint', 'unknown'),  # Sem mapeamento
        ]

        for route, expected_system in test_cases:
            result = get_system_name_for_route(route, mappings)
            self.assertEqual(
                result, expected_system,
                f"Falhou para rota '{route}': esperado '{expected_system}', obtido '{result}'"
            )


if __name__ == '__main__':
    unittest.main()
