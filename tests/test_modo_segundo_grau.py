# tests/test_modo_segundo_grau.py
"""
Testes automatizados para o modo 2º grau (competencia=999).

Cobre:
1. Detecção de modo (competencia=999 vs outros)
2. Regras de seleção por categoria
3. Configuração de limites
4. Fluxo quando competencia != "999"
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Optional


# ============================================================================
# MOCK DO DocumentoTJMS para testes
# ============================================================================

@dataclass
class MockDocumentoTJMS:
    """Mock simplificado de DocumentoTJMS para testes."""
    id: str
    tipo_documento: Optional[str] = None
    descricao: Optional[str] = None
    data_juntada: Optional[datetime] = None


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_db_session():
    """Mock da sessão do banco de dados."""
    session = MagicMock()

    # Mock para ConfiguracaoIA
    mock_config_peticoes = MagicMock()
    mock_config_peticoes.valor = "5"

    mock_config_recursos = MagicMock()
    mock_config_recursos.valor = "3"

    def query_side_effect(model):
        mock_query = MagicMock()

        def filter_side_effect(*args, **kwargs):
            mock_filter = MagicMock()

            def first_side_effect():
                # Verifica qual chave está sendo buscada
                for arg in args:
                    if hasattr(arg, 'right') and hasattr(arg.right, 'value'):
                        chave = arg.right.value
                        if chave == "competencia_999_last_peticoes_limit":
                            return mock_config_peticoes
                        elif chave == "competencia_999_last_recursos_limit":
                            return mock_config_recursos
                return None

            mock_filter.first = first_side_effect
            mock_filter.filter = filter_side_effect
            mock_filter.all = lambda: []
            return mock_filter

        mock_query.filter = filter_side_effect
        return mock_query

    session.query.side_effect = query_side_effect
    return session


@pytest.fixture
def codigos_por_categoria():
    """Mapeamento simulado de categorias para códigos."""
    return {
        "parecer": {8451, 9636, 207},
        "peticao": {500, 510, 9500},
        "peticao_inicial": {500, 9500, 10},
        "recurso": {8335, 8305, 8340},
        "recursos": set(),  # Alternativa vazia
        "despacho": {6, 53},
        "acordao": {34},
        "sentenca": {8},
        "decisao": {15, 137, 44}
    }


@pytest.fixture
def documentos_variados():
    """Lista de documentos simulando um processo de 2º grau."""
    docs = [
        # Petição Inicial
        MockDocumentoTJMS(id="1", tipo_documento="9500", descricao="Petição Inicial"),

        # Petições (15 documentos)
        MockDocumentoTJMS(id="10", tipo_documento="510", descricao="Petição 1"),
        MockDocumentoTJMS(id="11", tipo_documento="510", descricao="Petição 2"),
        MockDocumentoTJMS(id="12", tipo_documento="510", descricao="Petição 3"),
        MockDocumentoTJMS(id="13", tipo_documento="510", descricao="Petição 4"),
        MockDocumentoTJMS(id="14", tipo_documento="510", descricao="Petição 5"),
        MockDocumentoTJMS(id="15", tipo_documento="510", descricao="Petição 6"),
        MockDocumentoTJMS(id="16", tipo_documento="510", descricao="Petição 7"),
        MockDocumentoTJMS(id="17", tipo_documento="510", descricao="Petição 8"),
        MockDocumentoTJMS(id="18", tipo_documento="510", descricao="Petição 9"),
        MockDocumentoTJMS(id="19", tipo_documento="510", descricao="Petição 10"),
        MockDocumentoTJMS(id="20", tipo_documento="510", descricao="Petição 11"),
        MockDocumentoTJMS(id="21", tipo_documento="510", descricao="Petição 12"),
        MockDocumentoTJMS(id="22", tipo_documento="510", descricao="Petição 13"),
        MockDocumentoTJMS(id="23", tipo_documento="510", descricao="Petição 14"),
        MockDocumentoTJMS(id="24", tipo_documento="510", descricao="Petição 15"),

        # Despachos (5 documentos)
        MockDocumentoTJMS(id="30", tipo_documento="6", descricao="Despacho 1"),
        MockDocumentoTJMS(id="31", tipo_documento="6", descricao="Despacho 2"),
        MockDocumentoTJMS(id="32", tipo_documento="6", descricao="Despacho 3"),
        MockDocumentoTJMS(id="33", tipo_documento="6", descricao="Despacho 4"),
        MockDocumentoTJMS(id="34", tipo_documento="6", descricao="Despacho 5"),

        # Pareceres (3 documentos)
        MockDocumentoTJMS(id="40", tipo_documento="8451", descricao="Parecer NAT 1"),
        MockDocumentoTJMS(id="41", tipo_documento="8451", descricao="Parecer NAT 2"),
        MockDocumentoTJMS(id="42", tipo_documento="8451", descricao="Parecer NAT 3"),

        # Recursos (5 documentos)
        MockDocumentoTJMS(id="50", tipo_documento="8335", descricao="Recurso 1"),
        MockDocumentoTJMS(id="51", tipo_documento="8335", descricao="Recurso 2"),
        MockDocumentoTJMS(id="52", tipo_documento="8335", descricao="Recurso 3"),
        MockDocumentoTJMS(id="53", tipo_documento="8335", descricao="Recurso 4"),
        MockDocumentoTJMS(id="54", tipo_documento="8335", descricao="Recurso 5"),

        # Acórdão (2 documentos)
        MockDocumentoTJMS(id="60", tipo_documento="34", descricao="Acórdão 1"),
        MockDocumentoTJMS(id="61", tipo_documento="34", descricao="Acórdão 2"),

        # Sentença
        MockDocumentoTJMS(id="70", tipo_documento="8", descricao="Sentença"),

        # Decisões (3 documentos)
        MockDocumentoTJMS(id="80", tipo_documento="15", descricao="Decisão 1"),
        MockDocumentoTJMS(id="81", tipo_documento="15", descricao="Decisão 2"),
        MockDocumentoTJMS(id="82", tipo_documento="15", descricao="Decisão 3"),
    ]
    return docs


# ============================================================================
# TESTES - is_modo_segundo_grau
# ============================================================================

class TestIsModoSegundoGrau:
    """Testes para a função is_modo_segundo_grau."""

    def test_competencia_999_retorna_true(self):
        """Competencia=999 deve ativar modo 2º grau."""
        from sistemas.gerador_pecas.services_segundo_grau import is_modo_segundo_grau

        assert is_modo_segundo_grau("999") is True

    def test_competencia_diferente_retorna_false(self):
        """Competencia diferente de 999 não deve ativar modo 2º grau."""
        from sistemas.gerador_pecas.services_segundo_grau import is_modo_segundo_grau

        assert is_modo_segundo_grau("1") is False
        assert is_modo_segundo_grau("100") is False
        assert is_modo_segundo_grau("998") is False
        assert is_modo_segundo_grau("0") is False

    def test_competencia_none_retorna_false(self):
        """Competencia None não deve ativar modo 2º grau."""
        from sistemas.gerador_pecas.services_segundo_grau import is_modo_segundo_grau

        assert is_modo_segundo_grau(None) is False

    def test_competencia_string_vazia_retorna_false(self):
        """Competencia vazia não deve ativar modo 2º grau."""
        from sistemas.gerador_pecas.services_segundo_grau import is_modo_segundo_grau

        assert is_modo_segundo_grau("") is False


# ============================================================================
# TESTES - _selecionar_ultimos_n
# ============================================================================

class TestSelecionarUltimosN:
    """Testes para a função _selecionar_ultimos_n."""

    def test_seleciona_ultimos_n_documentos(self, documentos_variados, codigos_por_categoria):
        """Deve selecionar os últimos N documentos da categoria."""
        from sistemas.gerador_pecas.services_segundo_grau import _selecionar_ultimos_n

        # Filtra petições (código 510)
        codigos_peticao = {510}
        resultado = _selecionar_ultimos_n(documentos_variados, codigos_peticao, 5)

        # Deve retornar os 5 últimos (Petição 11 a 15)
        assert len(resultado) == 5
        ids = [d.id for d in resultado]
        assert ids == ["20", "21", "22", "23", "24"]

    def test_retorna_todos_se_menos_que_limite(self, documentos_variados):
        """Se há menos documentos que o limite, retorna todos."""
        from sistemas.gerador_pecas.services_segundo_grau import _selecionar_ultimos_n

        # Filtra acórdãos (código 34) - só há 2
        codigos_acordao = {34}
        resultado = _selecionar_ultimos_n(documentos_variados, codigos_acordao, 10)

        assert len(resultado) == 2

    def test_lista_vazia_retorna_vazio(self):
        """Lista vazia deve retornar lista vazia."""
        from sistemas.gerador_pecas.services_segundo_grau import _selecionar_ultimos_n

        resultado = _selecionar_ultimos_n([], {100, 200}, 5)
        assert resultado == []


# ============================================================================
# TESTES - selecionar_documentos_segundo_grau
# ============================================================================

class TestSelecionarDocumentosSegundoGrau:
    """Testes para a função principal de seleção."""

    def test_selecao_completa_com_limites(
        self, mock_db_session, documentos_variados, codigos_por_categoria
    ):
        """Verifica seleção completa aplicando todas as regras."""
        from sistemas.gerador_pecas.services_segundo_grau import (
            selecionar_documentos_segundo_grau
        )

        resultado = selecionar_documentos_segundo_grau(
            documentos_variados,
            mock_db_session,
            codigos_por_categoria
        )

        # Verifica que retornou menos documentos que o original
        assert len(resultado) < len(documentos_variados)

        # Conta por tipo
        tipos = {}
        for doc in resultado:
            tipo = doc.tipo_documento
            tipos[tipo] = tipos.get(tipo, 0) + 1

        # Parecer: deve ter apenas 1 (último)
        assert tipos.get("8451", 0) == 1

        # Acórdão: deve ter todos (2)
        assert tipos.get("34", 0) == 2

        # Sentença: deve ter todos (1)
        assert tipos.get("8", 0) == 1

        # Despacho: deve ter no máximo 3
        assert tipos.get("6", 0) <= 3

    def test_lista_vazia_retorna_vazio(self, mock_db_session, codigos_por_categoria):
        """Lista vazia deve retornar lista vazia."""
        from sistemas.gerador_pecas.services_segundo_grau import (
            selecionar_documentos_segundo_grau
        )

        resultado = selecionar_documentos_segundo_grau(
            [],
            mock_db_session,
            codigos_por_categoria
        )

        assert resultado == []

    def test_preserva_ordem_cronologica(
        self, mock_db_session, documentos_variados, codigos_por_categoria
    ):
        """Documentos selecionados devem manter a ordem cronológica original."""
        from sistemas.gerador_pecas.services_segundo_grau import (
            selecionar_documentos_segundo_grau
        )

        resultado = selecionar_documentos_segundo_grau(
            documentos_variados,
            mock_db_session,
            codigos_por_categoria
        )

        # Verifica se os IDs estão em ordem crescente (ordem original)
        ids_numericos = [int(doc.id) for doc in resultado]
        assert ids_numericos == sorted(ids_numericos)


# ============================================================================
# TESTES - Limites configuráveis
# ============================================================================

class TestLimitesConfiguraveis:
    """Testes para verificar leitura de limites do banco."""

    def test_get_config_limite_valor_valido(self, mock_db_session):
        """Deve retornar valor do banco quando válido."""
        from sistemas.gerador_pecas.services_segundo_grau import _get_config_limite

        # Mock retorna "5" para peticoes
        with patch.object(mock_db_session, 'query') as mock_query:
            mock_config = MagicMock()
            mock_config.valor = "5"
            mock_query.return_value.filter.return_value.first.return_value = mock_config

            resultado = _get_config_limite(
                mock_db_session,
                "competencia_999_last_peticoes_limit",
                10
            )

            assert resultado == 5

    def test_get_config_limite_usa_default_quando_nao_existe(self, mock_db_session):
        """Deve usar valor default quando configuração não existe."""
        from sistemas.gerador_pecas.services_segundo_grau import _get_config_limite

        with patch.object(mock_db_session, 'query') as mock_query:
            mock_query.return_value.filter.return_value.first.return_value = None

            resultado = _get_config_limite(
                mock_db_session,
                "chave_inexistente",
                15
            )

            assert resultado == 15

    def test_get_config_limite_limita_entre_1_e_50(self, mock_db_session):
        """Valor deve ser limitado entre 1 e 50."""
        from sistemas.gerador_pecas.services_segundo_grau import _get_config_limite

        # Testa valor acima do máximo
        with patch.object(mock_db_session, 'query') as mock_query:
            mock_config = MagicMock()
            mock_config.valor = "100"
            mock_query.return_value.filter.return_value.first.return_value = mock_config

            resultado = _get_config_limite(mock_db_session, "chave", 10)
            assert resultado == 50

        # Testa valor abaixo do mínimo
        with patch.object(mock_db_session, 'query') as mock_query:
            mock_config = MagicMock()
            mock_config.valor = "0"
            mock_query.return_value.filter.return_value.first.return_value = mock_config

            resultado = _get_config_limite(mock_db_session, "chave", 10)
            assert resultado == 1


# ============================================================================
# TESTES - Integração com DadosProcesso
# ============================================================================

class TestIntegracaoDadosProcesso:
    """Testes para verificar integração com o campo competencia de DadosProcesso."""

    def test_dados_processo_tem_campo_competencia(self):
        """DadosProcesso deve ter o campo competencia."""
        from sistemas.gerador_pecas.agente_tjms import DadosProcesso

        dados = DadosProcesso(
            numero_processo="0000001-00.2024.8.12.0001",
            competencia="999"
        )

        assert dados.competencia == "999"

    def test_dados_processo_competencia_none_por_default(self):
        """Campo competencia deve ser None por default."""
        from sistemas.gerador_pecas.agente_tjms import DadosProcesso

        dados = DadosProcesso(numero_processo="0000001-00.2024.8.12.0001")

        assert dados.competencia is None

    def test_dados_processo_to_json_inclui_competencia(self):
        """Método to_json deve incluir campo competencia."""
        from sistemas.gerador_pecas.agente_tjms import DadosProcesso

        dados = DadosProcesso(
            numero_processo="0000001-00.2024.8.12.0001",
            competencia="999"
        )

        json_data = dados.to_json()

        assert "competencia" in json_data
        assert json_data["competencia"] == "999"


# ============================================================================
# TESTES - Casos especiais
# ============================================================================

class TestCasosEspeciais:
    """Testes para casos especiais e edge cases."""

    def test_documento_sem_tipo_e_ignorado(self, codigos_por_categoria):
        """Documentos sem tipo_documento devem ser ignorados."""
        from sistemas.gerador_pecas.services_segundo_grau import _selecionar_ultimos_n

        docs = [
            MockDocumentoTJMS(id="1", tipo_documento=None),
            MockDocumentoTJMS(id="2", tipo_documento="510"),
            MockDocumentoTJMS(id="3", tipo_documento=""),
        ]

        resultado = _selecionar_ultimos_n(docs, {510}, 10)

        assert len(resultado) == 1
        assert resultado[0].id == "2"

    def test_tipo_documento_invalido_e_ignorado(self, codigos_por_categoria):
        """Tipo de documento inválido (não-numérico) deve ser ignorado."""
        from sistemas.gerador_pecas.services_segundo_grau import _selecionar_ultimos_n

        docs = [
            MockDocumentoTJMS(id="1", tipo_documento="abc"),
            MockDocumentoTJMS(id="2", tipo_documento="510"),
        ]

        resultado = _selecionar_ultimos_n(docs, {510}, 10)

        assert len(resultado) == 1
        assert resultado[0].id == "2"

    def test_categoria_vazia_nao_causa_erro(
        self, mock_db_session, documentos_variados
    ):
        """Categoria sem códigos não deve causar erro."""
        from sistemas.gerador_pecas.services_segundo_grau import (
            selecionar_documentos_segundo_grau
        )

        codigos_vazios = {
            "parecer": set(),
            "peticao": set(),
            "recurso": set(),
            "despacho": set(),
            "acordao": set(),
            "sentenca": set(),
            "decisao": set(),
            "peticao_inicial": set()
        }

        resultado = selecionar_documentos_segundo_grau(
            documentos_variados,
            mock_db_session,
            codigos_vazios
        )

        # Deve retornar lista vazia sem erro
        assert resultado == []

    def test_nao_duplica_documentos(
        self, mock_db_session, codigos_por_categoria
    ):
        """Mesmo documento não deve aparecer duplicado no resultado."""
        from sistemas.gerador_pecas.services_segundo_grau import (
            selecionar_documentos_segundo_grau
        )

        # Documento que poderia se encaixar em múltiplas categorias
        docs = [
            MockDocumentoTJMS(id="1", tipo_documento="9500", descricao="Petição"),
        ]

        resultado = selecionar_documentos_segundo_grau(
            docs,
            mock_db_session,
            codigos_por_categoria
        )

        ids = [d.id for d in resultado]
        # Verifica que não há duplicatas
        assert len(ids) == len(set(ids))
