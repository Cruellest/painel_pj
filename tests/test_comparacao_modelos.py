# tests/test_comparacao_modelos.py
"""
Testes unitarios para o servico de comparacao de modelos de IA.

Testa normalizacao de valores e comparacao de JSONs estruturados.
"""

import pytest
from sistemas.gerador_pecas.services_comparacao import (
    normalizar_valor_para_comparacao,
    obter_tipo_campo,
    comparar_jsons_estruturados,
    valores_sao_iguais,
    DiferencaCampo,
    RelatorioComparacao
)


class TestNormalizarValor:
    """Testes para a funcao normalizar_valor_para_comparacao"""

    def test_boolean_true_variants(self):
        """Testa que diferentes representacoes de true sao normalizadas"""
        assert normalizar_valor_para_comparacao(True, "boolean") == True
        assert normalizar_valor_para_comparacao("true", "boolean") == True
        assert normalizar_valor_para_comparacao("True", "boolean") == True
        assert normalizar_valor_para_comparacao("TRUE", "boolean") == True
        assert normalizar_valor_para_comparacao("sim", "boolean") == True
        assert normalizar_valor_para_comparacao("Sim", "boolean") == True
        assert normalizar_valor_para_comparacao("yes", "boolean") == True
        assert normalizar_valor_para_comparacao("1", "boolean") == True
        assert normalizar_valor_para_comparacao(1, "boolean") == True
        assert normalizar_valor_para_comparacao("verdadeiro", "boolean") == True

    def test_boolean_false_variants(self):
        """Testa que diferentes representacoes de false sao normalizadas"""
        assert normalizar_valor_para_comparacao(False, "boolean") == False
        assert normalizar_valor_para_comparacao("false", "boolean") == False
        assert normalizar_valor_para_comparacao("False", "boolean") == False
        assert normalizar_valor_para_comparacao("FALSE", "boolean") == False
        assert normalizar_valor_para_comparacao("nao", "boolean") == False
        assert normalizar_valor_para_comparacao("Nao", "boolean") == False
        assert normalizar_valor_para_comparacao("no", "boolean") == False
        assert normalizar_valor_para_comparacao("0", "boolean") == False
        assert normalizar_valor_para_comparacao(0, "boolean") == False
        assert normalizar_valor_para_comparacao("falso", "boolean") == False

    def test_null_equivalence(self):
        """Testa que None e tratado corretamente"""
        assert normalizar_valor_para_comparacao(None, "boolean") is None
        assert normalizar_valor_para_comparacao(None, "number") is None
        assert normalizar_valor_para_comparacao(None, "choice") is None
        assert normalizar_valor_para_comparacao(None, "date") is None

    def test_string_trim(self):
        """Testa que strings sao normalizadas com trim e lowercase"""
        assert normalizar_valor_para_comparacao("  valor  ", "choice") == "valor"
        assert normalizar_valor_para_comparacao("VALOR", "choice") == "valor"
        assert normalizar_valor_para_comparacao("  Valor  ", "choice") == "valor"

    def test_list_ordering(self):
        """Testa que listas sao ordenadas para comparacao independente de ordem"""
        result_a = normalizar_valor_para_comparacao(["b", "a", "c"], "list")
        result_b = normalizar_valor_para_comparacao(["a", "c", "b"], "list")
        assert result_a == result_b
        assert result_a == ["a", "b", "c"]

    def test_list_case_insensitive(self):
        """Testa que itens de lista sao normalizados"""
        result = normalizar_valor_para_comparacao(["A", "B"], "list")
        assert result == ["a", "b"]

    def test_number_float(self):
        """Testa que numeros sao convertidos para float"""
        assert normalizar_valor_para_comparacao(100, "number") == 100.0
        assert normalizar_valor_para_comparacao("100", "number") == 100.0
        assert normalizar_valor_para_comparacao(100.5, "number") == 100.5

    def test_number_invalid(self):
        """Testa que strings invalidas retornam None"""
        assert normalizar_valor_para_comparacao("abc", "number") is None
        assert normalizar_valor_para_comparacao("", "number") is None

    def test_date_normalization(self):
        """Testa normalizacao de datas"""
        assert normalizar_valor_para_comparacao("2024-01-15", "date") == "2024-01-15"
        assert normalizar_valor_para_comparacao("2024-01-15T10:30:00", "date") == "2024-01-15"
        assert normalizar_valor_para_comparacao("  2024-01-15  ", "date") == "2024-01-15"


class TestObterTipoCampo:
    """Testes para a funcao obter_tipo_campo"""

    def test_boolean_type(self):
        """Testa deteccao de tipo boolean"""
        schema = {"campo": {"type": "boolean"}}
        assert obter_tipo_campo("campo", schema) == "boolean"

    def test_number_type(self):
        """Testa deteccao de tipo number"""
        schema = {"campo": {"type": "number"}}
        assert obter_tipo_campo("campo", schema) == "number"

    def test_integer_type(self):
        """Testa deteccao de tipo integer como number"""
        schema = {"campo": {"type": "integer"}}
        assert obter_tipo_campo("campo", schema) == "number"

    def test_array_type(self):
        """Testa deteccao de tipo array como list"""
        schema = {"campo": {"type": "array"}}
        assert obter_tipo_campo("campo", schema) == "list"

    def test_object_type(self):
        """Testa deteccao de tipo object"""
        schema = {"campo": {"type": "object"}}
        assert obter_tipo_campo("campo", schema) == "object"

    def test_enum_as_choice(self):
        """Testa que string com enum e detectado como choice"""
        schema = {"campo": {"type": "string", "enum": ["op1", "op2"]}}
        assert obter_tipo_campo("campo", schema) == "choice"

    def test_date_format(self):
        """Testa deteccao de formato date"""
        schema = {"campo": {"type": "string", "format": "date"}}
        assert obter_tipo_campo("campo", schema) == "date"

    def test_text_by_description(self):
        """Testa deteccao de text por descricao"""
        schema = {"campo": {"type": "string", "description": "Descreva os detalhes"}}
        assert obter_tipo_campo("campo", schema) == "text"

    def test_text_by_name(self):
        """Testa deteccao de text por nome do campo"""
        schema = {"descricao_detalhada": {"type": "string"}}
        assert obter_tipo_campo("descricao_detalhada", schema) == "text"

    def test_unknown_field_default_text(self):
        """Testa que campo desconhecido retorna text"""
        assert obter_tipo_campo("campo_nao_existe", {}) == "text"
        assert obter_tipo_campo("campo", None) == "text"


class TestValoresSaoIguais:
    """Testes para a funcao valores_sao_iguais"""

    def test_both_none(self):
        """Testa que dois None sao iguais"""
        assert valores_sao_iguais(None, None, "boolean") == True
        assert valores_sao_iguais(None, None, "number") == True

    def test_one_none(self):
        """Testa que None vs valor e diferente"""
        assert valores_sao_iguais(None, True, "boolean") == False
        assert valores_sao_iguais(100, None, "number") == False

    def test_boolean_equality(self):
        """Testa comparacao de booleanos"""
        assert valores_sao_iguais(True, True, "boolean") == True
        assert valores_sao_iguais(False, False, "boolean") == True
        assert valores_sao_iguais(True, False, "boolean") == False

    def test_number_tolerance(self):
        """Testa que numeros tem tolerancia para floats"""
        assert valores_sao_iguais(100.0, 100.0, "number") == True
        assert valores_sao_iguais(100.0, 100.0001, "number") == True
        assert valores_sao_iguais(100.0, 100.01, "number") == False

    def test_list_equality(self):
        """Testa comparacao de listas"""
        assert valores_sao_iguais(["a", "b"], ["a", "b"], "list") == True
        assert valores_sao_iguais(["a", "b"], ["a", "c"], "list") == False
        assert valores_sao_iguais([], [], "list") == True

    def test_string_equality(self):
        """Testa comparacao de strings"""
        assert valores_sao_iguais("valor", "valor", "choice") == True
        assert valores_sao_iguais("valor", "outro", "choice") == False


class TestCompararJSONs:
    """Testes para a funcao comparar_jsons_estruturados"""

    def test_jsons_identicos(self):
        """Testa que JSONs identicos retornam 0 diferencas"""
        json_a = {
            "campo_bool": True,
            "campo_num": 100,
            "campo_choice": "opcao1"
        }
        json_b = {
            "campo_bool": True,
            "campo_num": 100,
            "campo_choice": "opcao1"
        }
        schema = {
            "campo_bool": {"type": "boolean"},
            "campo_num": {"type": "number"},
            "campo_choice": {"type": "string", "enum": ["opcao1", "opcao2"]}
        }

        result = comparar_jsons_estruturados(json_a, json_b, schema)

        assert result.campos_diferentes == 0
        assert result.campos_iguais == 3
        assert result.porcentagem_acordo == 100.0

    def test_ignora_campos_text(self):
        """Testa que campos text nao contam como diferenca"""
        json_a = {
            "campo_bool": True,
            "descricao": "Texto longo A com muitos detalhes"
        }
        json_b = {
            "campo_bool": True,
            "descricao": "Texto completamente diferente B"
        }
        schema = {
            "campo_bool": {"type": "boolean"},
            "descricao": {"type": "string", "description": "Descreva os detalhes"}
        }

        result = comparar_jsons_estruturados(json_a, json_b, schema)

        assert result.campos_diferentes == 0
        assert result.campos_text_ignorados == 1
        assert result.campos_comparados == 1

    def test_detecta_boolean_diff(self):
        """Testa deteccao de diferenca em boolean"""
        json_a = {"campo": True}
        json_b = {"campo": False}
        schema = {"campo": {"type": "boolean"}}

        result = comparar_jsons_estruturados(json_a, json_b, schema)

        assert result.campos_diferentes == 1
        assert len([d for d in result.diferencas if d.comparavel]) == 1

    def test_detecta_list_diff(self):
        """Testa deteccao de diferenca em lista"""
        json_a = {"items": ["a", "b"]}
        json_b = {"items": ["a", "c"]}
        schema = {"items": {"type": "array"}}

        result = comparar_jsons_estruturados(json_a, json_b, schema)

        assert result.campos_diferentes == 1

    def test_ignora_campos_especiais(self):
        """Testa que campos irrelevante e motivo sao ignorados"""
        json_a = {"irrelevante": True, "motivo": "teste", "campo": True}
        json_b = {"irrelevante": False, "motivo": "outro", "campo": True}
        schema = {"campo": {"type": "boolean"}}

        result = comparar_jsons_estruturados(json_a, json_b, schema)

        assert result.total_campos == 1  # Apenas 'campo'
        assert result.campos_diferentes == 0

    def test_campo_ausente_em_um_json(self):
        """Testa que campo ausente e tratado como diferente"""
        json_a = {"campo": True}
        json_b = {}
        schema = {"campo": {"type": "boolean"}}

        result = comparar_jsons_estruturados(json_a, json_b, schema)

        assert result.campos_diferentes == 1

    def test_resumo_100_acordo(self):
        """Testa que resumo indica 100% quando todos iguais"""
        json_a = {"campo": True}
        json_b = {"campo": True}
        schema = {"campo": {"type": "boolean"}}

        result = comparar_jsons_estruturados(json_a, json_b, schema)

        assert "100%" in result.resumo
        assert "acordo" in result.resumo.lower()

    def test_resumo_com_diferencas(self):
        """Testa que resumo indica numero de diferencas"""
        json_a = {"campo1": True, "campo2": "a"}
        json_b = {"campo1": False, "campo2": "b"}
        schema = {
            "campo1": {"type": "boolean"},
            "campo2": {"type": "string", "enum": ["a", "b"]}
        }

        result = comparar_jsons_estruturados(json_a, json_b, schema)

        assert "2 diferenca" in result.resumo.lower()


class TestDiferencaCampo:
    """Testes para a dataclass DiferencaCampo"""

    def test_criacao_diferenca_comparavel(self):
        """Testa criacao de diferenca comparavel"""
        diff = DiferencaCampo(
            campo="test",
            tipo_campo="boolean",
            valor_a=True,
            valor_b=False,
            comparavel=True
        )
        assert diff.campo == "test"
        assert diff.comparavel == True

    def test_criacao_diferenca_nao_comparavel(self):
        """Testa criacao de diferenca nao comparavel (text)"""
        diff = DiferencaCampo(
            campo="descricao",
            tipo_campo="text",
            valor_a="texto A",
            valor_b="texto B",
            comparavel=False
        )
        assert diff.comparavel == False


class TestRelatorioComparacao:
    """Testes para a dataclass RelatorioComparacao"""

    def test_criacao_relatorio(self):
        """Testa criacao de relatorio"""
        relatorio = RelatorioComparacao(
            total_campos=10,
            campos_comparados=8,
            campos_iguais=6,
            campos_diferentes=2,
            campos_text_ignorados=2,
            porcentagem_acordo=75.0,
            diferencas=[],
            resumo="2 diferenca(s) em 8 campo(s)"
        )
        assert relatorio.total_campos == 10
        assert relatorio.porcentagem_acordo == 75.0


class TestCasosEspeciais:
    """Testes para casos especiais e edge cases"""

    def test_jsons_vazios(self):
        """Testa comparacao de JSONs vazios"""
        result = comparar_jsons_estruturados({}, {}, {})
        assert result.total_campos == 0
        assert result.porcentagem_acordo == 100.0

    def test_schema_vazio(self):
        """Testa com schema vazio (todos campos tratados como text)"""
        json_a = {"campo": "valor"}
        json_b = {"campo": "outro"}

        result = comparar_jsons_estruturados(json_a, json_b, {})

        # Campo sera tratado como text e ignorado
        assert result.campos_text_ignorados == 1

    def test_lista_vazia_vs_lista_com_itens(self):
        """Testa diferenca entre lista vazia e lista com itens"""
        json_a = {"items": []}
        json_b = {"items": ["item1"]}
        schema = {"items": {"type": "array"}}

        result = comparar_jsons_estruturados(json_a, json_b, schema)

        assert result.campos_diferentes == 1

    def test_objeto_aninhado(self):
        """Testa comparacao de objetos aninhados"""
        json_a = {"obj": {"a": 1, "b": 2}}
        json_b = {"obj": {"a": 1, "b": 3}}
        schema = {"obj": {"type": "object"}}

        result = comparar_jsons_estruturados(json_a, json_b, schema)

        # Objeto aninhado e comparado como um todo
        assert result.campos_diferentes == 1

    def test_normalizacao_preserva_ordem_lista_objetos(self):
        """Testa que listas de objetos sao ordenadas para comparacao"""
        json_a = {"items": [{"id": 2}, {"id": 1}]}
        json_b = {"items": [{"id": 1}, {"id": 2}]}
        schema = {"items": {"type": "array"}}

        result = comparar_jsons_estruturados(json_a, json_b, schema)

        # Listas sao ordenadas, entao devem ser iguais
        assert result.campos_diferentes == 0
