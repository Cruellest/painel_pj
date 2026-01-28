# tests/ia_extracao_regras/backend/unit/test_process_variables.py
"""
Testes unitários para variáveis derivadas do processo XML.

Este módulo cobre:
- Resolução de variáveis a partir de DadosProcesso
- Variável processo_ajuizado_apos_2024_04_19 (Tema 106 STF)
- Variável valor_causa_numerico (conversão de moeda)
- Variável estado_polo_passivo
- Variável autor_com_assistencia_judiciaria
- Variável autor_com_defensoria
"""

import unittest
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Optional

from sistemas.gerador_pecas.services_process_variables import (
    ProcessVariableDefinition,
    ProcessVariableResolver,
    _resolver_ajuizado_apos_2024_09_19,
    _resolver_valor_causa_numerico,
    _resolver_estado_polo_passivo,
    _resolver_autor_com_assistencia_judiciaria,
    _resolver_autor_com_defensoria,
    _resolver_municipio_polo_passivo,
)


# Mock de ParteProcesso para testes
@dataclass
class MockParteProcesso:
    """Mock de ParteProcesso para testes."""
    nome: str
    tipo_pessoa: str = "fisica"
    polo: str = "AT"
    representante: Optional[str] = None
    tipo_representante: Optional[str] = None
    assistencia_judiciaria: bool = False


# Mock de DadosProcesso para testes
@dataclass
class MockDadosProcesso:
    """Mock de DadosProcesso para testes."""
    numero_processo: str
    polo_ativo: List[MockParteProcesso] = field(default_factory=list)
    polo_passivo: List[MockParteProcesso] = field(default_factory=list)
    valor_causa: Optional[str] = None
    classe_processual: Optional[str] = None
    data_ajuizamento: Optional[datetime] = None
    orgao_julgador: Optional[str] = None


class TestProcessoAjuizadoAposTema106(unittest.TestCase):
    """Testes para a variável processo_ajuizado_apos_2024_04_19."""

    def test_data_ajuizamento_nula_retorna_none(self):
        """Data de ajuizamento nula deve retornar None."""
        dados = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            data_ajuizamento=None
        )
        resultado = _resolver_ajuizado_apos_2024_09_19(dados)
        self.assertIsNone(resultado)

    def test_data_antes_corte_retorna_false(self):
        """Data 18/04/2024 (antes do corte) deve retornar False."""
        dados = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            data_ajuizamento=datetime(2024, 4, 18, 10, 30, 0)
        )
        resultado = _resolver_ajuizado_apos_2024_09_19(dados)
        self.assertFalse(resultado)

    def test_data_exata_corte_retorna_false(self):
        """Data 19/04/2024 (exatamente no corte) deve retornar False (é >, não >=)."""
        dados = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            data_ajuizamento=datetime(2024, 4, 19, 10, 30, 0)
        )
        resultado = _resolver_ajuizado_apos_2024_09_19(dados)
        self.assertFalse(resultado)

    def test_data_apos_corte_retorna_true(self):
        """Data 20/04/2024 (após corte) deve retornar True."""
        dados = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            data_ajuizamento=datetime(2024, 4, 20, 10, 30, 0)
        )
        resultado = _resolver_ajuizado_apos_2024_09_19(dados)
        self.assertTrue(resultado)

    def test_data_muito_depois_corte_retorna_true(self):
        """Data em 2025 deve retornar True."""
        dados = MockDadosProcesso(
            numero_processo="0001234-56.2025.8.12.0001",
            data_ajuizamento=datetime(2025, 1, 15, 10, 30, 0)
        )
        resultado = _resolver_ajuizado_apos_2024_09_19(dados)
        self.assertTrue(resultado)

    def test_data_muito_antes_corte_retorna_false(self):
        """Data em 2023 deve retornar False."""
        dados = MockDadosProcesso(
            numero_processo="0001234-56.2023.8.12.0001",
            data_ajuizamento=datetime(2023, 12, 31, 23, 59, 59)
        )
        resultado = _resolver_ajuizado_apos_2024_09_19(dados)
        self.assertFalse(resultado)


class TestValorCausaNumerico(unittest.TestCase):
    """Testes para a variável valor_causa_numerico."""

    def test_valor_nulo_retorna_none(self):
        """Valor da causa nulo deve retornar None."""
        dados = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            valor_causa=None
        )
        resultado = _resolver_valor_causa_numerico(dados)
        self.assertIsNone(resultado)

    def test_valor_simples_inteiro(self):
        """Valor simples '250000' deve retornar 250000.0."""
        dados = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            valor_causa="250000"
        )
        resultado = _resolver_valor_causa_numerico(dados)
        self.assertEqual(resultado, 250000.0)

    def test_valor_formato_brasileiro(self):
        """Valor '250.000,00' deve retornar 250000.0."""
        dados = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            valor_causa="250.000,00"
        )
        resultado = _resolver_valor_causa_numerico(dados)
        self.assertEqual(resultado, 250000.0)

    def test_valor_com_simbolo_moeda(self):
        """Valor 'R$ 250.000,00' deve retornar 250000.0."""
        dados = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            valor_causa="R$ 250.000,00"
        )
        resultado = _resolver_valor_causa_numerico(dados)
        self.assertEqual(resultado, 250000.0)

    def test_valor_decimal_virgula(self):
        """Valor '250,50' deve retornar 250.5."""
        dados = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            valor_causa="250,50"
        )
        resultado = _resolver_valor_causa_numerico(dados)
        self.assertEqual(resultado, 250.5)

    def test_valor_grande_brasileiro(self):
        """Valor '1.234.567,89' deve retornar 1234567.89."""
        dados = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            valor_causa="1.234.567,89"
        )
        resultado = _resolver_valor_causa_numerico(dados)
        self.assertAlmostEqual(resultado, 1234567.89, places=2)

    def test_valor_invalido_retorna_none(self):
        """Valor inválido deve retornar None."""
        dados = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            valor_causa="invalido"
        )
        resultado = _resolver_valor_causa_numerico(dados)
        self.assertIsNone(resultado)


class TestEstadoPoloPassivo(unittest.TestCase):
    """Testes para a variável estado_polo_passivo."""

    def test_polo_passivo_vazio_retorna_none(self):
        """Polo passivo vazio deve retornar None."""
        dados = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            polo_passivo=[]
        )
        resultado = _resolver_estado_polo_passivo(dados)
        self.assertIsNone(resultado)

    def test_estado_ms_no_polo_passivo_retorna_true(self):
        """Estado de MS no polo passivo deve retornar True."""
        dados = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            polo_passivo=[
                MockParteProcesso(nome="Estado de Mato Grosso do Sul", polo="PA")
            ]
        )
        resultado = _resolver_estado_polo_passivo(dados)
        self.assertTrue(resultado)

    def test_estado_ms_variacao_nome_retorna_true(self):
        """Variação 'Estado do Mato Grosso do Sul' deve retornar True."""
        dados = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            polo_passivo=[
                MockParteProcesso(nome="Estado do Mato Grosso do Sul", polo="PA")
            ]
        )
        resultado = _resolver_estado_polo_passivo(dados)
        self.assertTrue(resultado)

    def test_outra_parte_no_polo_passivo_retorna_false(self):
        """Outra parte (não Estado) no polo passivo deve retornar False."""
        dados = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            polo_passivo=[
                MockParteProcesso(nome="Município de Campo Grande", polo="PA")
            ]
        )
        resultado = _resolver_estado_polo_passivo(dados)
        self.assertFalse(resultado)

    def test_estado_entre_multiplas_partes_retorna_true(self):
        """Estado de MS entre múltiplas partes deve retornar True."""
        dados = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            polo_passivo=[
                MockParteProcesso(nome="Município de Campo Grande", polo="PA"),
                MockParteProcesso(nome="Estado de Mato Grosso do Sul", polo="PA"),
                MockParteProcesso(nome="União Federal", polo="PA")
            ]
        )
        resultado = _resolver_estado_polo_passivo(dados)
        self.assertTrue(resultado)


class TestAutorComAssistenciaJudiciaria(unittest.TestCase):
    """Testes para a variável autor_com_assistencia_judiciaria."""

    def test_polo_ativo_vazio_retorna_none(self):
        """Polo ativo vazio deve retornar None."""
        dados = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            polo_ativo=[]
        )
        resultado = _resolver_autor_com_assistencia_judiciaria(dados)
        self.assertIsNone(resultado)

    def test_autor_com_assistencia_retorna_true(self):
        """Autor com assistência judiciária deve retornar True."""
        dados = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            polo_ativo=[
                MockParteProcesso(
                    nome="João da Silva",
                    polo="AT",
                    assistencia_judiciaria=True
                )
            ]
        )
        resultado = _resolver_autor_com_assistencia_judiciaria(dados)
        self.assertTrue(resultado)

    def test_autor_sem_assistencia_retorna_false(self):
        """Autor sem assistência judiciária deve retornar False."""
        dados = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            polo_ativo=[
                MockParteProcesso(
                    nome="João da Silva",
                    polo="AT",
                    assistencia_judiciaria=False
                )
            ]
        )
        resultado = _resolver_autor_com_assistencia_judiciaria(dados)
        self.assertFalse(resultado)

    def test_um_autor_com_assistencia_entre_varios_retorna_true(self):
        """Pelo menos um autor com assistência deve retornar True."""
        dados = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            polo_ativo=[
                MockParteProcesso(nome="João da Silva", polo="AT", assistencia_judiciaria=False),
                MockParteProcesso(nome="Maria Santos", polo="AT", assistencia_judiciaria=True),
                MockParteProcesso(nome="Pedro Souza", polo="AT", assistencia_judiciaria=False)
            ]
        )
        resultado = _resolver_autor_com_assistencia_judiciaria(dados)
        self.assertTrue(resultado)


class TestAutorComDefensoria(unittest.TestCase):
    """Testes para a variável autor_com_defensoria."""

    def test_polo_ativo_vazio_retorna_none(self):
        """Polo ativo vazio deve retornar None."""
        dados = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            polo_ativo=[]
        )
        resultado = _resolver_autor_com_defensoria(dados)
        self.assertIsNone(resultado)

    def test_autor_com_defensoria_retorna_true(self):
        """Autor representado por Defensoria deve retornar True."""
        dados = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            polo_ativo=[
                MockParteProcesso(
                    nome="João da Silva",
                    polo="AT",
                    tipo_representante="defensoria"
                )
            ]
        )
        resultado = _resolver_autor_com_defensoria(dados)
        self.assertTrue(resultado)

    def test_autor_com_advogado_retorna_false(self):
        """Autor representado por advogado deve retornar False."""
        dados = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            polo_ativo=[
                MockParteProcesso(
                    nome="João da Silva",
                    polo="AT",
                    tipo_representante="advogado",
                    representante="Dr. Fulano de Tal"
                )
            ]
        )
        resultado = _resolver_autor_com_defensoria(dados)
        self.assertFalse(resultado)

    def test_autor_sem_representante_retorna_false(self):
        """Autor sem representante deve retornar False."""
        dados = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            polo_ativo=[
                MockParteProcesso(
                    nome="João da Silva",
                    polo="AT",
                    tipo_representante=None
                )
            ]
        )
        resultado = _resolver_autor_com_defensoria(dados)
        self.assertFalse(resultado)


class TestProcessVariableResolver(unittest.TestCase):
    """Testes para o ProcessVariableResolver."""

    def test_dados_processo_nulo_retorna_dict_vazio(self):
        """Dados do processo nulo deve retornar dicionário vazio."""
        resolver = ProcessVariableResolver(None)
        resultado = resolver.resolver_todas()
        self.assertEqual(resultado, {})

    def test_resolver_todas_retorna_todas_variaveis(self):
        """Resolver todas deve retornar todas as variáveis registradas."""
        dados = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            data_ajuizamento=datetime(2024, 5, 1),
            valor_causa="100.000,00",
            polo_passivo=[MockParteProcesso(nome="Estado de Mato Grosso do Sul", polo="PA")],
            polo_ativo=[MockParteProcesso(nome="João da Silva", polo="AT", assistencia_judiciaria=True)]
        )

        resolver = ProcessVariableResolver(dados)
        resultado = resolver.resolver_todas()

        # Verifica que todas as variáveis estão presentes
        self.assertIn("processo_ajuizado_apos_2024_04_19", resultado)
        self.assertIn("valor_causa_numerico", resultado)
        self.assertIn("estado_polo_passivo", resultado)
        self.assertIn("autor_com_assistencia_judiciaria", resultado)
        self.assertIn("autor_com_defensoria", resultado)

        # Verifica valores
        self.assertTrue(resultado["processo_ajuizado_apos_2024_04_19"])
        self.assertEqual(resultado["valor_causa_numerico"], 100000.0)
        self.assertTrue(resultado["estado_polo_passivo"])
        self.assertTrue(resultado["autor_com_assistencia_judiciaria"])
        self.assertFalse(resultado["autor_com_defensoria"])

    def test_resolver_variavel_especifica(self):
        """Resolver variável específica deve funcionar."""
        dados = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            data_ajuizamento=datetime(2024, 5, 1)
        )

        resolver = ProcessVariableResolver(dados)
        resultado = resolver.resolver("processo_ajuizado_apos_2024_04_19")

        self.assertTrue(resultado)

    def test_resolver_variavel_inexistente_retorna_none(self):
        """Resolver variável inexistente deve retornar None."""
        dados = MockDadosProcesso(numero_processo="0001234-56.2024.8.12.0001")

        resolver = ProcessVariableResolver(dados)
        resultado = resolver.resolver("variavel_inexistente")

        self.assertIsNone(resultado)

    def test_get_all_definitions(self):
        """Deve retornar todas as definições registradas."""
        definitions = ProcessVariableResolver.get_all_definitions()

        self.assertGreaterEqual(len(definitions), 5)

        slugs = [d.slug for d in definitions]
        self.assertIn("processo_ajuizado_apos_2024_04_19", slugs)
        self.assertIn("valor_causa_numerico", slugs)
        self.assertIn("estado_polo_passivo", slugs)
        self.assertIn("autor_com_assistencia_judiciaria", slugs)
        self.assertIn("autor_com_defensoria", slugs)

    def test_get_definition_existente(self):
        """Deve retornar a definição correta para slug existente."""
        definition = ProcessVariableResolver.get_definition("processo_ajuizado_apos_2024_04_19")

        self.assertIsNotNone(definition)
        self.assertEqual(definition.slug, "processo_ajuizado_apos_2024_04_19")
        self.assertEqual(definition.tipo, "boolean")
        self.assertIn("Tema 106", definition.descricao)

    def test_get_definition_inexistente(self):
        """Deve retornar None para slug inexistente."""
        definition = ProcessVariableResolver.get_definition("slug_inexistente")
        self.assertIsNone(definition)


class TestProcessVariableDefinition(unittest.TestCase):
    """Testes para ProcessVariableDefinition."""

    def test_dataclass_creation(self):
        """Deve criar dataclass corretamente."""
        def mock_resolver(dados):
            return True

        definition = ProcessVariableDefinition(
            slug="test_var",
            label="Test Variable",
            tipo="boolean",
            descricao="Test description",
            resolver=mock_resolver
        )

        self.assertEqual(definition.slug, "test_var")
        self.assertEqual(definition.label, "Test Variable")
        self.assertEqual(definition.tipo, "boolean")
        self.assertEqual(definition.descricao, "Test description")
        self.assertEqual(definition.resolver(None), True)


class TestMunicipioPoloPassivo(unittest.TestCase):
    """
    Testes para a variavel municipio_polo_passivo.

    Lógica simplificada: Se a parte tem 'Município' ou 'Prefeitura Municipal'
    no nome e é pessoa jurídica, então é um município no polo passivo.
    """

    def test_polo_passivo_vazio_retorna_none(self):
        """Polo passivo vazio deve retornar None."""
        dados = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            polo_passivo=[]
        )
        resultado = _resolver_municipio_polo_passivo(dados)
        self.assertIsNone(resultado)

    def test_municipio_padrao_completo_retorna_true(self):
        """'Municipio de Bandeirantes/MS' deve retornar True."""
        dados = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            polo_passivo=[
                MockParteProcesso(nome="Municipio de Bandeirantes/MS", tipo_pessoa="juridica", polo="PA")
            ]
        )
        resultado = _resolver_municipio_polo_passivo(dados)
        self.assertTrue(resultado)

    def test_municipio_com_acento_retorna_true(self):
        """'Município de Campo Grande' deve retornar True."""
        dados = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            polo_passivo=[
                MockParteProcesso(nome="Município de Campo Grande", tipo_pessoa="juridica", polo="PA")
            ]
        )
        resultado = _resolver_municipio_polo_passivo(dados)
        self.assertTrue(resultado)

    def test_municipio_dourados_retorna_true(self):
        """'Municipio de Dourados' deve retornar True."""
        dados = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            polo_passivo=[
                MockParteProcesso(nome="Municipio de Dourados", tipo_pessoa="juridica", polo="PA")
            ]
        )
        resultado = _resolver_municipio_polo_passivo(dados)
        self.assertTrue(resultado)

    def test_prefeitura_municipal_retorna_true(self):
        """'Prefeitura Municipal de Corumba' deve retornar True."""
        dados = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            polo_passivo=[
                MockParteProcesso(nome="Prefeitura Municipal de Corumba", tipo_pessoa="juridica", polo="PA")
            ]
        )
        resultado = _resolver_municipio_polo_passivo(dados)
        self.assertTrue(resultado)

    def test_apenas_estado_retorna_false(self):
        """Apenas Estado no polo passivo deve retornar False."""
        dados = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            polo_passivo=[
                MockParteProcesso(nome="Estado de Mato Grosso do Sul", tipo_pessoa="juridica", polo="PA")
            ]
        )
        resultado = _resolver_municipio_polo_passivo(dados)
        self.assertFalse(resultado)

    def test_municipio_outro_estado_retorna_true(self):
        """Município de outro estado também deve retornar True (lógica simplificada)."""
        dados = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            polo_passivo=[
                MockParteProcesso(nome="Municipio de Sao Paulo/SP", tipo_pessoa="juridica", polo="PA")
            ]
        )
        resultado = _resolver_municipio_polo_passivo(dados)
        self.assertTrue(resultado)

    def test_municipio_entre_multiplas_partes_retorna_true(self):
        """Municipio entre multiplas partes deve retornar True."""
        dados = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            polo_passivo=[
                MockParteProcesso(nome="Estado de Mato Grosso do Sul", tipo_pessoa="juridica", polo="PA"),
                MockParteProcesso(nome="Municipio de Bandeirantes/MS", tipo_pessoa="juridica", polo="PA")
            ]
        )
        resultado = _resolver_municipio_polo_passivo(dados)
        self.assertTrue(resultado)

    def test_tres_lagoas_retorna_true(self):
        """'Municipio de Tres Lagoas' deve retornar True."""
        dados = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            polo_passivo=[
                MockParteProcesso(nome="Município de Três Lagoas", tipo_pessoa="juridica", polo="PA")
            ]
        )
        resultado = _resolver_municipio_polo_passivo(dados)
        self.assertTrue(resultado)

    def test_municipio_qualquer_nome_retorna_true(self):
        """Qualquer município (não só de MS) deve retornar True."""
        dados = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            polo_passivo=[
                MockParteProcesso(nome="Município de São Paulo", tipo_pessoa="juridica", polo="PA")
            ]
        )
        resultado = _resolver_municipio_polo_passivo(dados)
        self.assertTrue(resultado)

    def test_municipio_com_variacao_preposicao_retorna_true(self):
        """'Município de/do X' deve retornar True independente da preposição."""
        # Com "do"
        dados_do = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            polo_passivo=[
                MockParteProcesso(nome="Município do Rio de Janeiro", tipo_pessoa="juridica", polo="PA")
            ]
        )
        self.assertTrue(_resolver_municipio_polo_passivo(dados_do))

        # Com "de"
        dados_de = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            polo_passivo=[
                MockParteProcesso(nome="Município de São Paulo", tipo_pessoa="juridica", polo="PA")
            ]
        )
        self.assertTrue(_resolver_municipio_polo_passivo(dados_de))

    def test_municipio_pessoa_fisica_retorna_false(self):
        """Pessoa física com 'Município' no nome não deve retornar True."""
        dados = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            polo_passivo=[
                MockParteProcesso(nome="João do Município", tipo_pessoa="fisica", polo="PA")
            ]
        )
        resultado = _resolver_municipio_polo_passivo(dados)
        self.assertFalse(resultado)

    def test_prefeitura_sem_municipal_nao_retorna_true(self):
        """'Prefeitura' sem 'Municipal' não deve retornar True."""
        dados = MockDadosProcesso(
            numero_processo="0001234-56.2024.8.12.0001",
            polo_passivo=[
                MockParteProcesso(nome="Prefeitura da Universidade", tipo_pessoa="juridica", polo="PA")
            ]
        )
        resultado = _resolver_municipio_polo_passivo(dados)
        self.assertFalse(resultado)


if __name__ == "__main__":
    unittest.main()
