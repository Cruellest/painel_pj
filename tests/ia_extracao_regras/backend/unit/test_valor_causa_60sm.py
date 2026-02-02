"""
Testes unitários para:
- Parsing de valor_causa_numerico
- Variável derivada valor_causa_inferior_60sm
"""

import pytest
from dataclasses import dataclass
from typing import Optional, List
from unittest.mock import MagicMock


@dataclass
class MockParteProcesso:
    """Mock simples de ParteProcesso para os testes."""
    nome: str = ""
    tipo_pessoa: str = "fisica"
    tipo_representante: Optional[str] = None
    assistencia_judiciaria: bool = False


@dataclass
class MockDadosProcesso:
    """Mock de DadosProcesso para os testes."""
    numero_processo: str = "00000000000000000000"
    polo_ativo: List[MockParteProcesso] = None
    polo_passivo: List[MockParteProcesso] = None
    valor_causa: Optional[str] = None
    classe_processual: Optional[str] = None
    data_ajuizamento = None
    orgao_julgador: Optional[str] = None

    def __post_init__(self):
        if self.polo_ativo is None:
            self.polo_ativo = []
        if self.polo_passivo is None:
            self.polo_passivo = []


# Importa as funções a serem testadas
from sistemas.gerador_pecas.services_process_variables import (
    _resolver_valor_causa_numerico,
    _resolver_valor_causa_inferior_60sm,
    LIMITE_60_SALARIOS_MINIMOS,
)


class TestResolverValorCausaNumerico:
    """Testes para _resolver_valor_causa_numerico."""

    def test_formato_xml_padrao_com_ponto_decimal(self):
        """Testa formato XML TJ-MS: 17317.35"""
        dados = MockDadosProcesso(valor_causa="17317.35")
        resultado = _resolver_valor_causa_numerico(dados)
        assert resultado == 17317.35

    def test_formato_xml_inteiro(self):
        """Testa formato XML inteiro: 97260"""
        dados = MockDadosProcesso(valor_causa="97260")
        resultado = _resolver_valor_causa_numerico(dados)
        assert resultado == 97260.0

    def test_formato_xml_com_zero_decimal(self):
        """Testa formato XML: 1000.0"""
        dados = MockDadosProcesso(valor_causa="1000.0")
        resultado = _resolver_valor_causa_numerico(dados)
        assert resultado == 1000.0

    def test_formato_xml_740(self):
        """Testa formato XML: 740.0"""
        dados = MockDadosProcesso(valor_causa="740.0")
        resultado = _resolver_valor_causa_numerico(dados)
        assert resultado == 740.0

    def test_valor_ausente_retorna_none(self):
        """Testa que valor ausente retorna None."""
        dados = MockDadosProcesso(valor_causa=None)
        resultado = _resolver_valor_causa_numerico(dados)
        assert resultado is None

    def test_valor_vazio_retorna_none(self):
        """Testa que valor vazio retorna None."""
        dados = MockDadosProcesso(valor_causa="")
        resultado = _resolver_valor_causa_numerico(dados)
        assert resultado is None

    def test_valor_invalido_retorna_none(self):
        """Testa que valor inválido retorna None."""
        dados = MockDadosProcesso(valor_causa="abc123")
        resultado = _resolver_valor_causa_numerico(dados)
        assert resultado is None

    def test_valor_com_espacos(self):
        """Testa que espaços são removidos."""
        dados = MockDadosProcesso(valor_causa="  17317.35  ")
        resultado = _resolver_valor_causa_numerico(dados)
        assert resultado == 17317.35

    def test_formato_brasileiro_virgula_decimal(self):
        """Testa formato brasileiro: 17317,35"""
        dados = MockDadosProcesso(valor_causa="17317,35")
        resultado = _resolver_valor_causa_numerico(dados)
        assert resultado == 17317.35

    def test_formato_brasileiro_ponto_milhar_virgula_decimal(self):
        """Testa formato brasileiro completo: 250.000,00"""
        dados = MockDadosProcesso(valor_causa="250.000,00")
        resultado = _resolver_valor_causa_numerico(dados)
        assert resultado == 250000.0

    def test_formato_com_simbolo_real(self):
        """Testa formato com R$: R$ 250.000,00"""
        dados = MockDadosProcesso(valor_causa="R$ 250.000,00")
        resultado = _resolver_valor_causa_numerico(dados)
        assert resultado == 250000.0

    def test_dados_none(self):
        """Testa que dados None retorna None."""
        resultado = _resolver_valor_causa_numerico(None)
        assert resultado is None


class TestResolverValorCausaInferior60SM:
    """Testes para _resolver_valor_causa_inferior_60sm."""

    def test_valor_inferior_ao_limite(self):
        """Testa valor inferior a 60 SM -> True."""
        dados = MockDadosProcesso(valor_causa="90000")
        resultado = _resolver_valor_causa_inferior_60sm(dados)
        assert resultado is True

    def test_valor_igual_ao_limite(self):
        """Testa valor igual a 60 SM -> False (não é estritamente inferior)."""
        dados = MockDadosProcesso(valor_causa="97260")
        resultado = _resolver_valor_causa_inferior_60sm(dados)
        assert resultado is False

    def test_valor_superior_ao_limite(self):
        """Testa valor superior a 60 SM -> False."""
        dados = MockDadosProcesso(valor_causa="100000")
        resultado = _resolver_valor_causa_inferior_60sm(dados)
        assert resultado is False

    def test_valor_none_retorna_none(self):
        """Testa que valor None retorna None (não chuta)."""
        dados = MockDadosProcesso(valor_causa=None)
        resultado = _resolver_valor_causa_inferior_60sm(dados)
        assert resultado is None

    def test_valor_vazio_retorna_none(self):
        """Testa que valor vazio retorna None."""
        dados = MockDadosProcesso(valor_causa="")
        resultado = _resolver_valor_causa_inferior_60sm(dados)
        assert resultado is None

    def test_valor_invalido_retorna_none(self):
        """Testa que valor inválido retorna None."""
        dados = MockDadosProcesso(valor_causa="invalido")
        resultado = _resolver_valor_causa_inferior_60sm(dados)
        assert resultado is None

    def test_valor_bem_abaixo_do_limite(self):
        """Testa valores bem abaixo do limite."""
        dados = MockDadosProcesso(valor_causa="1000")
        resultado = _resolver_valor_causa_inferior_60sm(dados)
        assert resultado is True

    def test_valor_pouco_abaixo_do_limite(self):
        """Testa valor pouco abaixo do limite: 97259.99 -> True."""
        dados = MockDadosProcesso(valor_causa="97259.99")
        resultado = _resolver_valor_causa_inferior_60sm(dados)
        assert resultado is True

    def test_valor_pouco_acima_do_limite(self):
        """Testa valor pouco acima do limite: 97260.01 -> False."""
        dados = MockDadosProcesso(valor_causa="97260.01")
        resultado = _resolver_valor_causa_inferior_60sm(dados)
        assert resultado is False

    def test_xml_real_17317_35(self):
        """Testa com valor real do XML 1: 17317.35"""
        dados = MockDadosProcesso(valor_causa="17317.35")
        resultado = _resolver_valor_causa_inferior_60sm(dados)
        assert resultado is True

    def test_xml_real_1000_0(self):
        """Testa com valor real do XML 2: 1000.0"""
        dados = MockDadosProcesso(valor_causa="1000.0")
        resultado = _resolver_valor_causa_inferior_60sm(dados)
        assert resultado is True

    def test_xml_real_740_0(self):
        """Testa com valor real do XML 3: 740.0"""
        dados = MockDadosProcesso(valor_causa="740.0")
        resultado = _resolver_valor_causa_inferior_60sm(dados)
        assert resultado is True


class TestConstantes:
    """Testes para verificar constantes."""

    def test_limite_60_sm(self):
        """Verifica que o limite está correto: 97260."""
        assert LIMITE_60_SALARIOS_MINIMOS == 97260.0

    def test_limite_eh_60_vezes_salario_minimo(self):
        """Verifica que 97260 = 1621 * 60 (salário mínimo 2024)."""
        # Salário mínimo 2024 = R$ 1.621,00 (aproximado)
        # 60 SM = 60 * 1621 = 97260
        assert LIMITE_60_SALARIOS_MINIMOS == 97260.0
