# tests/test_ia_params_resolver.py
"""
Testes para o serviço de resolução de parâmetros de IA por agente.

Valida:
- Hierarquia de resolução (agente > sistema > global > default)
- Parsing de tipos (float, int)
- Compatibilidade com chaves legadas
- Isolamento entre sistemas
"""

import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy.orm import Session

from services.ia_params_resolver import (
    IAParams,
    get_ia_params,
    listar_agentes,
    listar_sistemas,
    get_config_per_agent,
    DEFAULTS,
    AGENTES_POR_SISTEMA,
    _parse_float,
    _parse_int,
)


# ============================================
# FIXTURES
# ============================================

@pytest.fixture
def mock_db():
    """Mock da sessão do banco de dados"""
    return MagicMock(spec=Session)


def create_config_mock(configs: dict):
    """
    Cria um mock de ConfiguracaoIA que retorna valores baseados em chave/sistema.

    Args:
        configs: Dict no formato {(sistema, chave): valor}
    """
    def mock_filter(*args, **kwargs):
        mock_query = MagicMock()

        # Extrai sistema e chave dos filtros
        sistema = None
        chave = None

        for arg in args:
            # Simula filtro BinaryExpression
            if hasattr(arg, 'right') and hasattr(arg, 'left'):
                left_key = str(arg.left.key) if hasattr(arg.left, 'key') else str(arg.left)
                if 'sistema' in left_key:
                    sistema = arg.right.value if hasattr(arg.right, 'value') else str(arg.right)
                elif 'chave' in left_key:
                    chave = arg.right.value if hasattr(arg.right, 'value') else str(arg.right)

        # Retorna config se existir
        config_key = (sistema, chave)
        if config_key in configs:
            config_mock = MagicMock()
            config_mock.valor = configs[config_key]
            mock_query.first.return_value = config_mock
        else:
            mock_query.first.return_value = None

        return mock_query

    return mock_filter


# ============================================
# TESTES DE HIERARQUIA
# ============================================

class TestHierarquiaResolucao:
    """Testes da hierarquia de resolução: agente > sistema > global > default"""

    def test_agent_level_override(self, mock_db):
        """Config do agente deve prevalecer sobre sistema"""
        configs = {
            ("gerador_pecas", "modelo_geracao"): "modelo-agente",
            ("gerador_pecas", "modelo"): "modelo-sistema",
            ("global", "modelo"): "modelo-global",
        }

        mock_db.query.return_value.filter = create_config_mock(configs)

        params = get_ia_params(mock_db, "gerador_pecas", "geracao")

        assert params.modelo == "modelo-agente"
        assert params.modelo_source == "agent"

    def test_system_level_fallback(self, mock_db):
        """Sem config de agente, deve usar sistema"""
        configs = {
            ("gerador_pecas", "modelo"): "modelo-sistema",
            ("global", "modelo"): "modelo-global",
        }

        mock_db.query.return_value.filter = create_config_mock(configs)

        params = get_ia_params(mock_db, "gerador_pecas", "geracao")

        assert params.modelo == "modelo-sistema"
        assert params.modelo_source == "system"

    def test_global_fallback(self, mock_db):
        """Sem config de sistema, deve usar global"""
        configs = {
            ("global", "modelo"): "modelo-global",
        }

        mock_db.query.return_value.filter = create_config_mock(configs)

        params = get_ia_params(mock_db, "gerador_pecas", "geracao")

        assert params.modelo == "modelo-global"
        assert params.modelo_source == "global"

    def test_default_fallback(self, mock_db):
        """Sem nenhuma config, deve usar default"""
        configs = {}  # Nenhuma configuração

        mock_db.query.return_value.filter = create_config_mock(configs)

        params = get_ia_params(mock_db, "gerador_pecas", "geracao")

        assert params.modelo == DEFAULTS["modelo"]
        assert params.modelo_source == "default"

    def test_hierarchy_agent_over_system(self, mock_db):
        """Confirma precedência: agente > sistema mesmo com ambos configurados"""
        configs = {
            ("pedido_calculo", "temperatura_extracao"): "0.1",
            ("pedido_calculo", "temperatura"): "0.5",
            ("global", "temperatura"): "0.9",
        }

        mock_db.query.return_value.filter = create_config_mock(configs)

        params = get_ia_params(mock_db, "pedido_calculo", "extracao")

        assert params.temperatura == 0.1
        assert params.temperatura_source == "agent"


# ============================================
# TESTES DE COMPATIBILIDADE LEGADA
# ============================================

class TestCompatibilidadeLegada:
    """Testes de compatibilidade com chaves legadas"""

    def test_legacy_modelo_geracao(self, mock_db):
        """Chave legada modelo_geracao deve funcionar"""
        configs = {
            ("gerador_pecas", "modelo_geracao"): "modelo-legado",
        }

        mock_db.query.return_value.filter = create_config_mock(configs)

        params = get_ia_params(mock_db, "gerador_pecas", "geracao")

        assert params.modelo == "modelo-legado"

    def test_legacy_modelo_extracao(self, mock_db):
        """Chave legada modelo_extracao deve funcionar para pedido_calculo"""
        configs = {
            ("pedido_calculo", "modelo_extracao"): "modelo-extracao-legado",
        }

        mock_db.query.return_value.filter = create_config_mock(configs)

        params = get_ia_params(mock_db, "pedido_calculo", "extracao")

        assert params.modelo == "modelo-extracao-legado"

    def test_legacy_temperatura_geracao(self, mock_db):
        """Chave legada temperatura_geracao deve funcionar"""
        configs = {
            ("gerador_pecas", "temperatura_geracao"): "0.7",
        }

        mock_db.query.return_value.filter = create_config_mock(configs)

        params = get_ia_params(mock_db, "gerador_pecas", "geracao")

        assert params.temperatura == 0.7


# ============================================
# TESTES DE ISOLAMENTO
# ============================================

class TestIsolamentoSistemas:
    """Testes para garantir que configurações não vazam entre sistemas"""

    def test_no_parameter_leakage(self, mock_db):
        """Config de um sistema não deve afetar outro"""
        configs = {
            ("gerador_pecas", "modelo_geracao"): "modelo-gerador",
            ("pedido_calculo", "modelo_geracao"): "modelo-pedido",
        }

        mock_db.query.return_value.filter = create_config_mock(configs)

        params_gerador = get_ia_params(mock_db, "gerador_pecas", "geracao")
        params_pedido = get_ia_params(mock_db, "pedido_calculo", "geracao")

        assert params_gerador.modelo == "modelo-gerador"
        assert params_pedido.modelo == "modelo-pedido"

    def test_different_agents_same_system(self, mock_db):
        """Diferentes agentes do mesmo sistema devem ter configs independentes"""
        configs = {
            ("gerador_pecas", "modelo_coletor"): "modelo-coletor",
            ("gerador_pecas", "modelo_deteccao"): "modelo-deteccao",
            ("gerador_pecas", "modelo_geracao"): "modelo-geracao",
        }

        mock_db.query.return_value.filter = create_config_mock(configs)

        params_coletor = get_ia_params(mock_db, "gerador_pecas", "coletor")
        params_deteccao = get_ia_params(mock_db, "gerador_pecas", "deteccao")
        params_geracao = get_ia_params(mock_db, "gerador_pecas", "geracao")

        assert params_coletor.modelo == "modelo-coletor"
        assert params_deteccao.modelo == "modelo-deteccao"
        assert params_geracao.modelo == "modelo-geracao"


# ============================================
# TESTES DE PARSING
# ============================================

class TestParsing:
    """Testes de conversão de tipos"""

    def test_temperatura_parsing_float(self, mock_db):
        """Temperatura deve ser parseada como float"""
        configs = {
            ("gerador_pecas", "temperatura_geracao"): "0.75",
        }

        mock_db.query.return_value.filter = create_config_mock(configs)

        params = get_ia_params(mock_db, "gerador_pecas", "geracao")

        assert params.temperatura == 0.75
        assert isinstance(params.temperatura, float)

    def test_temperatura_parsing_invalid(self, mock_db):
        """Temperatura inválida deve usar default"""
        configs = {
            ("gerador_pecas", "temperatura_geracao"): "invalid",
        }

        mock_db.query.return_value.filter = create_config_mock(configs)

        params = get_ia_params(mock_db, "gerador_pecas", "geracao")

        assert params.temperatura == DEFAULTS["temperatura"]

    def test_max_tokens_parsing_int(self, mock_db):
        """max_tokens deve ser parseado como int"""
        configs = {
            ("gerador_pecas", "max_tokens_geracao"): "50000",
        }

        mock_db.query.return_value.filter = create_config_mock(configs)

        params = get_ia_params(mock_db, "gerador_pecas", "geracao")

        assert params.max_tokens == 50000
        assert isinstance(params.max_tokens, int)

    def test_max_tokens_parsing_invalid(self, mock_db):
        """max_tokens inválido deve usar default"""
        configs = {
            ("gerador_pecas", "max_tokens_geracao"): "not_a_number",
        }

        mock_db.query.return_value.filter = create_config_mock(configs)

        params = get_ia_params(mock_db, "gerador_pecas", "geracao")

        assert params.max_tokens == DEFAULTS["max_tokens"]


class TestParsingHelpers:
    """Testes para funções auxiliares de parsing"""

    def test_parse_float_valid(self):
        assert _parse_float("0.5", 0.0) == 0.5
        assert _parse_float("1.0", 0.0) == 1.0
        assert _parse_float("0", 0.5) == 0.0

    def test_parse_float_invalid(self):
        assert _parse_float("abc", 0.5) == 0.5
        assert _parse_float(None, 0.3) == 0.3
        assert _parse_float("", 0.1) == 0.1

    def test_parse_int_valid(self):
        assert _parse_int("100", None) == 100
        assert _parse_int("50000", 1000) == 50000

    def test_parse_int_invalid(self):
        assert _parse_int("abc", None) is None
        assert _parse_int("abc", 1000) == 1000
        assert _parse_int(None, 500) == 500


# ============================================
# TESTES DE THINKING_LEVEL
# ============================================

class TestThinkingLevel:
    """Testes para thinking_level"""

    def test_thinking_level_agent(self, mock_db):
        """thinking_level configurado por agente"""
        configs = {
            ("gerador_pecas", "thinking_level_geracao"): "high",
        }

        mock_db.query.return_value.filter = create_config_mock(configs)

        params = get_ia_params(mock_db, "gerador_pecas", "geracao")

        assert params.thinking_level == "high"
        assert params.thinking_level_source == "agent"

    def test_thinking_level_system(self, mock_db):
        """thinking_level configurado por sistema"""
        configs = {
            ("gerador_pecas", "thinking_level"): "medium",
        }

        mock_db.query.return_value.filter = create_config_mock(configs)

        params = get_ia_params(mock_db, "gerador_pecas", "geracao")

        assert params.thinking_level == "medium"
        assert params.thinking_level_source == "system"

    def test_thinking_level_invalid(self, mock_db):
        """thinking_level inválido deve virar None"""
        configs = {
            ("gerador_pecas", "thinking_level_geracao"): "super_high",  # inválido
        }

        mock_db.query.return_value.filter = create_config_mock(configs)

        params = get_ia_params(mock_db, "gerador_pecas", "geracao")

        assert params.thinking_level is None


# ============================================
# TESTES DE ESTRUTURA IAParams
# ============================================

class TestIAParamsStructure:
    """Testes da estrutura IAParams"""

    def test_to_dict(self, mock_db):
        """to_dict deve retornar dicionário completo"""
        configs = {
            ("gerador_pecas", "modelo_geracao"): "modelo-test",
            ("gerador_pecas", "temperatura_geracao"): "0.5",
        }

        mock_db.query.return_value.filter = create_config_mock(configs)

        params = get_ia_params(mock_db, "gerador_pecas", "geracao")
        d = params.to_dict()

        assert "modelo" in d
        assert "temperatura" in d
        assert "max_tokens" in d
        assert "sources" in d
        assert "sistema" in d
        assert "agente" in d

        assert d["modelo"] == "modelo-test"
        assert d["temperatura"] == 0.5
        assert d["sources"]["modelo"] == "agent"
        assert d["sistema"] == "gerador_pecas"
        assert d["agente"] == "geracao"

    def test_log_summary(self, mock_db):
        """log_summary deve retornar string formatada"""
        configs = {
            ("gerador_pecas", "modelo_geracao"): "modelo-test",
        }

        mock_db.query.return_value.filter = create_config_mock(configs)

        params = get_ia_params(mock_db, "gerador_pecas", "geracao")
        summary = params.log_summary()

        assert "[IA]" in summary
        assert "sistema=gerador_pecas" in summary
        assert "agente=geracao" in summary
        assert "modelo=modelo-test" in summary


# ============================================
# TESTES DE UTILITÁRIOS
# ============================================

class TestUtilitarios:
    """Testes das funções utilitárias"""

    def test_listar_sistemas(self):
        """listar_sistemas deve retornar lista de sistemas"""
        sistemas = listar_sistemas()

        assert isinstance(sistemas, list)
        assert "gerador_pecas" in sistemas
        assert "pedido_calculo" in sistemas
        assert "prestacao_contas" in sistemas

    def test_listar_agentes(self):
        """listar_agentes deve retornar dict de agentes"""
        agentes = listar_agentes("gerador_pecas")

        assert isinstance(agentes, dict)
        assert "coletor" in agentes
        assert "deteccao" in agentes
        assert "geracao" in agentes

    def test_listar_agentes_sistema_inexistente(self):
        """listar_agentes para sistema inexistente deve retornar dict vazio"""
        agentes = listar_agentes("sistema_fake")

        assert agentes == {}

    def test_get_config_per_agent(self, mock_db):
        """get_config_per_agent deve retornar configs de todos agentes"""
        configs = {
            ("gerador_pecas", "modelo_coletor"): "modelo-coletor",
            ("gerador_pecas", "modelo_geracao"): "modelo-geracao",
        }

        mock_db.query.return_value.filter = create_config_mock(configs)

        result = get_config_per_agent(mock_db, "gerador_pecas")

        assert "coletor" in result
        assert "deteccao" in result
        assert "geracao" in result
        assert isinstance(result["coletor"], IAParams)
        assert result["coletor"].modelo == "modelo-coletor"


# ============================================
# TESTES DE DEFAULTS OVERRIDE
# ============================================

class TestDefaultsOverride:
    """Testes para override de defaults"""

    def test_defaults_override(self, mock_db):
        """defaults_override deve sobrescrever valores padrão"""
        configs = {}  # Sem configs

        mock_db.query.return_value.filter = create_config_mock(configs)

        params = get_ia_params(
            mock_db,
            "gerador_pecas",
            "geracao",
            defaults_override={
                "modelo": "modelo-custom",
                "temperatura": 0.9,
                "max_tokens": 10000,
            }
        )

        assert params.modelo == "modelo-custom"
        assert params.temperatura == 0.9
        assert params.max_tokens == 10000


# ============================================
# MAIN
# ============================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
