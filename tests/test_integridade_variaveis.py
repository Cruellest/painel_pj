"""
Testes para verificação de integridade entre regras determinísticas e variáveis.

Verifica se o sistema detecta corretamente variáveis que não existem
em nenhum JSON de extração ou nas variáveis de sistema.
"""

import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy.orm import Session

# Importa o validador
from sistemas.gerador_pecas.services_deterministic import (
    RuleIntegrityValidator,
    validar_integridade_regras_modulo,
    validar_integridade_todas_regras,
    _extrair_variaveis_regra
)


class TestExtrairVariaveisRegra:
    """Testes para extração de variáveis de uma regra AST."""

    def test_extrai_variavel_simples(self):
        """Deve extrair variável de condição simples."""
        regra = {
            "type": "condition",
            "variable": "medicamento_alto_custo",
            "operator": "equals",
            "value": True
        }
        variaveis = _extrair_variaveis_regra(regra)
        assert variaveis == {"medicamento_alto_custo"}

    def test_extrai_variaveis_and(self):
        """Deve extrair variáveis de AND."""
        regra = {
            "type": "and",
            "conditions": [
                {"type": "condition", "variable": "var1", "operator": "equals", "value": True},
                {"type": "condition", "variable": "var2", "operator": "equals", "value": False}
            ]
        }
        variaveis = _extrair_variaveis_regra(regra)
        assert variaveis == {"var1", "var2"}

    def test_extrai_variaveis_or(self):
        """Deve extrair variáveis de OR."""
        regra = {
            "type": "or",
            "conditions": [
                {"type": "condition", "variable": "var_a", "operator": "equals", "value": True},
                {"type": "condition", "variable": "var_b", "operator": "equals", "value": True}
            ]
        }
        variaveis = _extrair_variaveis_regra(regra)
        assert variaveis == {"var_a", "var_b"}

    def test_extrai_variaveis_aninhadas(self):
        """Deve extrair variáveis de estrutura aninhada."""
        regra = {
            "type": "and",
            "conditions": [
                {"type": "condition", "variable": "var_nivel1", "operator": "equals", "value": True},
                {
                    "type": "or",
                    "conditions": [
                        {"type": "condition", "variable": "var_nivel2a", "operator": "equals", "value": True},
                        {"type": "condition", "variable": "var_nivel2b", "operator": "equals", "value": True}
                    ]
                }
            ]
        }
        variaveis = _extrair_variaveis_regra(regra)
        assert variaveis == {"var_nivel1", "var_nivel2a", "var_nivel2b"}

    def test_extrai_variaveis_not(self):
        """Deve extrair variáveis de NOT."""
        regra = {
            "type": "not",
            "conditions": [
                {"type": "condition", "variable": "var_negada", "operator": "equals", "value": True}
            ]
        }
        variaveis = _extrair_variaveis_regra(regra)
        assert variaveis == {"var_negada"}

    def test_regra_vazia_retorna_set_vazio(self):
        """Regra None deve retornar set vazio."""
        variaveis = _extrair_variaveis_regra({})
        assert variaveis == set()


class TestRuleIntegrityValidator:
    """Testes para o validador de integridade de regras."""

    @pytest.fixture
    def mock_db(self):
        """Mock da sessão do banco de dados."""
        return MagicMock(spec=Session)

    @pytest.fixture
    def validator(self, mock_db):
        """Cria instância do validador com mocks."""
        with patch.object(RuleIntegrityValidator, '_carregar_variaveis_disponiveis') as mock_carregar:
            validator = RuleIntegrityValidator(mock_db)
            # Simula variáveis disponíveis
            validator._variaveis_extracao = {"var_extracao_1", "var_extracao_2"}
            validator._variaveis_sistema = {"valor_causa_superior_210sm", "processo_ajuizado_apos_2024_09_19"}
            validator._variaveis_disponiveis = validator._variaveis_extracao | validator._variaveis_sistema
            return validator

    def test_valida_regra_com_variaveis_validas(self, validator):
        """Regra com variáveis válidas não deve gerar erros."""
        regra = {
            "type": "condition",
            "variable": "var_extracao_1",
            "operator": "equals",
            "value": True
        }
        resultado = validator.validar_regra(regra, "teste")
        assert resultado == []

    def test_valida_regra_com_variavel_sistema(self, validator):
        """Variáveis de sistema devem ser aceitas."""
        regra = {
            "type": "condition",
            "variable": "valor_causa_superior_210sm",
            "operator": "equals",
            "value": True
        }
        resultado = validator.validar_regra(regra, "teste")
        assert resultado == []

    def test_detecta_variavel_invalida(self, validator):
        """Deve detectar variável que não existe."""
        regra = {
            "type": "condition",
            "variable": "variavel_inexistente_xyz",
            "operator": "equals",
            "value": True
        }
        resultado = validator.validar_regra(regra, "regra_teste")
        assert len(resultado) == 1
        assert resultado[0]["variavel"] == "variavel_inexistente_xyz"
        assert resultado[0]["regra"] == "regra_teste"

    def test_detecta_multiplas_variaveis_invalidas(self, validator):
        """Deve detectar múltiplas variáveis inválidas."""
        regra = {
            "type": "and",
            "conditions": [
                {"type": "condition", "variable": "var_extracao_1", "operator": "equals", "value": True},
                {"type": "condition", "variable": "variavel_fake_1", "operator": "equals", "value": True},
                {"type": "condition", "variable": "variavel_fake_2", "operator": "equals", "value": False}
            ]
        }
        resultado = validator.validar_regra(regra, "teste")
        assert len(resultado) == 2
        variaveis_detectadas = {r["variavel"] for r in resultado}
        assert variaveis_detectadas == {"variavel_fake_1", "variavel_fake_2"}

    def test_infere_tipo_boolean(self, validator):
        """Deve inferir tipo boolean para variáveis com padrões específicos."""
        assert validator._inferir_tipo_variavel("autor_idoso") == "boolean"
        assert validator._inferir_tipo_variavel("medicamento_aprovado") == "boolean"
        assert validator._inferir_tipo_variavel("possui_documento") == "boolean"
        assert validator._inferir_tipo_variavel("tem_advogado") == "boolean"

    def test_infere_tipo_currency(self, validator):
        """Deve inferir tipo currency para variáveis com padrões específicos."""
        assert validator._inferir_tipo_variavel("valor_causa") == "currency"
        assert validator._inferir_tipo_variavel("custo_medicamento") == "currency"
        assert validator._inferir_tipo_variavel("preco_tratamento") == "currency"

    def test_infere_tipo_date(self, validator):
        """Deve inferir tipo date para variáveis com padrões específicos."""
        assert validator._inferir_tipo_variavel("data_nascimento") == "date"
        assert validator._inferir_tipo_variavel("data_vencimento") == "date"

    def test_infere_tipo_number(self, validator):
        """Deve inferir tipo number para variáveis com padrões específicos."""
        assert validator._inferir_tipo_variavel("quantidade_medicamentos") == "number"
        assert validator._inferir_tipo_variavel("numero_protocolo") == "number"
        assert validator._inferir_tipo_variavel("qtd_itens") == "number"

    def test_infere_tipo_text_padrao(self, validator):
        """Deve inferir tipo text como padrão."""
        assert validator._inferir_tipo_variavel("nome_medicamento") == "text"
        assert validator._inferir_tipo_variavel("descricao_pedido") == "text"

    def test_regra_none_valida(self, validator):
        """Regra None deve ser considerada válida (sem variáveis)."""
        resultado = validator.validar_regra(None, "teste")
        assert resultado == []


class TestValidarModulo:
    """Testes para validação de módulo completo."""

    @pytest.fixture
    def mock_db(self):
        """Mock da sessão do banco de dados."""
        return MagicMock(spec=Session)

    def test_modulo_inexistente(self, mock_db):
        """Módulo inexistente deve retornar erro."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with patch.object(RuleIntegrityValidator, '_carregar_variaveis_disponiveis'):
            validator = RuleIntegrityValidator(mock_db)
            validator._variaveis_disponiveis = set()
            validator._variaveis_extracao = set()
            validator._variaveis_sistema = set()

            resultado = validator.validar_modulo(999)

        assert resultado["valido"] == False
        assert "erro" in resultado

    def test_modulo_sem_regras_valido(self, mock_db):
        """Módulo sem regras determinísticas deve ser válido."""
        mock_modulo = MagicMock()
        mock_modulo.id = 1
        mock_modulo.nome = "teste"
        mock_modulo.regra_deterministica = None
        mock_modulo.regra_deterministica_secundaria = None

        mock_db.query.return_value.filter.return_value.first.return_value = mock_modulo
        mock_db.query.return_value.filter.return_value.all.return_value = []

        with patch.object(RuleIntegrityValidator, '_carregar_variaveis_disponiveis'):
            validator = RuleIntegrityValidator(mock_db)
            validator._variaveis_disponiveis = set()
            validator._variaveis_extracao = set()
            validator._variaveis_sistema = set()

            resultado = validator.validar_modulo(1)

        assert resultado["valido"] == True
        assert resultado["variaveis_invalidas"] == []


class TestIntegracaoCompleta:
    """Testes de integração do sistema de validação."""

    def test_funcao_conveniencia_validar_modulo(self):
        """Função de conveniência deve chamar o validador corretamente."""
        mock_db = MagicMock()
        mock_modulo = MagicMock()
        mock_modulo.id = 1
        mock_modulo.nome = "teste"
        mock_modulo.regra_deterministica = None
        mock_modulo.regra_deterministica_secundaria = None

        mock_db.query.return_value.filter.return_value.first.return_value = mock_modulo
        mock_db.query.return_value.filter.return_value.all.return_value = []

        with patch.object(RuleIntegrityValidator, '_carregar_variaveis_disponiveis'):
            with patch.object(RuleIntegrityValidator, 'validar_modulo', return_value={"valido": True}):
                resultado = validar_integridade_regras_modulo(mock_db, 1)

        assert resultado["valido"] == True

    def test_funcao_conveniencia_validar_todos(self):
        """Função de conveniência para validar todos deve funcionar."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = []

        with patch.object(RuleIntegrityValidator, '_carregar_variaveis_disponiveis'):
            with patch.object(RuleIntegrityValidator, 'validar_todos_modulos', return_value={"valido": True}):
                resultado = validar_integridade_todas_regras(mock_db)

        assert resultado["valido"] == True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
