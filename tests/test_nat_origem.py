"""
Testes automatizados para a feature de busca de NAT no processo de origem.

Este módulo testa o comportamento quando:
1. Um processo é um agravo (peticao_inicial_agravo=true)
2. O NAT não existe no processo do agravo
3. O sistema deve buscar o NAT no processo de origem

Processo de teste: 1419974-57.2025.8.12.0000 (agravo real)
"""

import asyncio
import json
import pytest

# Configura pytest-asyncio para modo automático
pytest_plugins = ('pytest_asyncio',)
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass
from typing import List, Optional

import sys
import os

# Adiciona o diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sistemas.gerador_pecas.services_nat_origem import (
    CODIGOS_NAT,
    CODIGOS_INDICADORES_AGRAVO,
    NATOrigemResult,
    NATOrigemResolver,
    verificar_nat_em_documentos,
    verificar_agravo_por_documentos,
    selecionar_melhor_nat,
    extrair_dados_peticao_inicial,
    integrar_nat_ao_resultado,
)


# =============================================================================
# Fixtures e Mocks
# =============================================================================

@dataclass
class MockDocumentoTJMS:
    """Mock de DocumentoTJMS para testes."""
    id: str
    tipo_documento: Optional[str] = None
    descricao: Optional[str] = None
    data_juntada: Optional[datetime] = None
    resumo: Optional[str] = None
    conteudo_base64: Optional[str] = None
    processo_origem: bool = False
    numero_processo: Optional[str] = None
    irrelevante: bool = False


@dataclass
class MockResultadoAnalise:
    """Mock de ResultadoAnalise para testes."""
    numero_processo: str
    documentos: List[MockDocumentoTJMS]
    data_analise: datetime = None
    erro_geral: Optional[str] = None
    processo_origem: Optional[str] = None
    is_agravo: bool = False

    def __post_init__(self):
        if self.data_analise is None:
            self.data_analise = datetime.now()

    def documentos_com_resumo(self):
        return [d for d in self.documentos if d.resumo and not d.irrelevante]


def criar_documento_peticao_inicial_agravo(num_origem: str = "0800000-00.2024.8.12.0001"):
    """Cria um documento de petição inicial que indica agravo."""
    json_data = {
        "peticao_inicial_agravo": True,
        "peticao_inicial_num_origem": num_origem,
        "tipo": "Agravo de Instrumento",
        "autor": "Fulano de Tal",
        "reu": "Estado de Mato Grosso do Sul"
    }
    return MockDocumentoTJMS(
        id="doc-001",
        tipo_documento="500",  # Petição Inicial
        descricao="Petição Inicial",
        resumo=json.dumps(json_data, ensure_ascii=False)
    )


def criar_documento_nat(doc_id: str = "nat-001", codigo: int = 8451):
    """Cria um documento NAT."""
    json_data = {
        "tipo": "Parecer NAT",
        "medicamento_analisado": "Pembrolizumabe",
        "incorporado_sus": False,
        "recomendacao": "Desfavorável"
    }
    return MockDocumentoTJMS(
        id=doc_id,
        tipo_documento=str(codigo),
        descricao="Parecer NAT",
        data_juntada=datetime.now(),
        resumo=json.dumps(json_data, ensure_ascii=False),
        conteudo_base64="base64_content_here"
    )


def criar_documento_generico(doc_id: str = "doc-gen", codigo: int = 510):
    """Cria um documento genérico (não NAT)."""
    return MockDocumentoTJMS(
        id=doc_id,
        tipo_documento=str(codigo),
        descricao="Petição Intermediária",
        data_juntada=datetime.now(),
        resumo='{"tipo": "Petição Intermediária"}'
    )


# =============================================================================
# Testes Unitários
# =============================================================================

class TestCodigosNAT:
    """Testes para verificação dos códigos NAT."""

    def test_codigos_nat_definidos(self):
        """Verifica que os códigos NAT estão definidos corretamente."""
        assert 207 in CODIGOS_NAT, "Código 207 (Parecer CATES) deve estar na lista"
        assert 8451 in CODIGOS_NAT, "Código 8451 (Parecer NAT) deve estar na lista"
        assert 9636 in CODIGOS_NAT, "Código 9636 (Parecer NAT alt) deve estar na lista"
        assert 59 in CODIGOS_NAT, "Código 59 (Nota Técnica NATJus) deve estar na lista"
        assert 8490 in CODIGOS_NAT, "Código 8490 (Nota Técnica NATJus alt) deve estar na lista"

    def test_codigos_nat_total(self):
        """Verifica que temos exatamente 5 códigos NAT."""
        assert len(CODIGOS_NAT) == 5


class TestVerificarNATEmDocumentos:
    """Testes para a função verificar_nat_em_documentos."""

    def test_encontra_nat_codigo_8451(self):
        """Deve encontrar NAT com código 8451."""
        docs = [
            criar_documento_generico("doc-1", 510),
            criar_documento_nat("nat-1", 8451),
            criar_documento_generico("doc-2", 520),
        ]
        resultado = verificar_nat_em_documentos(docs)
        assert len(resultado) == 1
        assert resultado[0].id == "nat-1"

    def test_encontra_nat_codigo_207(self):
        """Deve encontrar NAT com código 207 (CATES)."""
        docs = [criar_documento_nat("cates-1", 207)]
        resultado = verificar_nat_em_documentos(docs)
        assert len(resultado) == 1
        assert resultado[0].tipo_documento == "207"

    def test_encontra_multiplos_nat(self):
        """Deve encontrar múltiplos NATs."""
        docs = [
            criar_documento_nat("nat-1", 8451),
            criar_documento_nat("nat-2", 9636),
            criar_documento_generico("doc-1", 510),
        ]
        resultado = verificar_nat_em_documentos(docs)
        assert len(resultado) == 2

    def test_nao_encontra_nat_em_lista_vazia(self):
        """Não deve encontrar NAT em lista vazia."""
        resultado = verificar_nat_em_documentos([])
        assert len(resultado) == 0

    def test_nao_encontra_nat_sem_documentos_nat(self):
        """Não deve encontrar NAT quando não há documentos NAT."""
        docs = [
            criar_documento_generico("doc-1", 510),
            criar_documento_generico("doc-2", 520),
            criar_documento_peticao_inicial_agravo(),
        ]
        resultado = verificar_nat_em_documentos(docs)
        assert len(resultado) == 0


class TestSelecionarMelhorNAT:
    """Testes para a função selecionar_melhor_nat."""

    def test_seleciona_unico_nat(self):
        """Deve selecionar o único NAT quando há apenas um."""
        docs_nat = [criar_documento_nat("nat-1", 8451)]
        resultado = selecionar_melhor_nat(docs_nat)
        assert resultado is not None
        assert resultado.id == "nat-1"

    def test_seleciona_nat_mais_recente(self):
        """Deve selecionar o NAT mais recente por data de juntada."""
        nat_antigo = criar_documento_nat("nat-antigo", 8451)
        nat_antigo.data_juntada = datetime(2024, 1, 1)

        nat_recente = criar_documento_nat("nat-recente", 8451)
        nat_recente.data_juntada = datetime(2024, 6, 1)

        resultado = selecionar_melhor_nat([nat_antigo, nat_recente])
        assert resultado.id == "nat-recente"

    def test_retorna_none_para_lista_vazia(self):
        """Deve retornar None para lista vazia."""
        resultado = selecionar_melhor_nat([])
        assert resultado is None


class TestExtrairDadosPeticaoInicial:
    """Testes para a função extrair_dados_peticao_inicial."""

    def test_extrai_dados_peticao_inicial_agravo(self):
        """Deve extrair dados da petição inicial corretamente."""
        doc_pi = criar_documento_peticao_inicial_agravo("0800000-00.2024.8.12.0001")
        resultado = MockResultadoAnalise(
            numero_processo="1419974-57.2025.8.12.0000",
            documentos=[doc_pi]
        )

        dados = extrair_dados_peticao_inicial(resultado)

        assert dados.get("peticao_inicial_agravo") == True
        assert dados.get("peticao_inicial_num_origem") == "0800000-00.2024.8.12.0001"

    def test_retorna_vazio_sem_peticao_inicial(self):
        """Deve retornar dicionário vazio sem petição inicial."""
        resultado = MockResultadoAnalise(
            numero_processo="1419974-57.2025.8.12.0000",
            documentos=[criar_documento_generico()]
        )

        dados = extrair_dados_peticao_inicial(resultado)

        assert dados == {}

    def test_retorna_vazio_peticao_sem_json(self):
        """Deve retornar vazio quando petição não é JSON."""
        doc_pi = MockDocumentoTJMS(
            id="doc-001",
            tipo_documento="500",
            resumo="Este é um resumo em texto simples, não JSON."
        )
        resultado = MockResultadoAnalise(
            numero_processo="1419974-57.2025.8.12.0000",
            documentos=[doc_pi]
        )

        dados = extrair_dados_peticao_inicial(resultado)

        assert dados == {}


class TestIntegrarNATAoResultado:
    """Testes para a função integrar_nat_ao_resultado."""

    def test_integra_nat_com_sucesso(self):
        """Deve integrar NAT ao resultado com sucesso."""
        resultado = MockResultadoAnalise(
            numero_processo="1419974-57.2025.8.12.0000",
            documentos=[criar_documento_generico()]
        )

        doc_nat = criar_documento_nat("nat-origem", 8451)
        nat_result = NATOrigemResult(
            nat_encontrado_origem=True,
            nat_source="origem",
            documento_nat=doc_nat,
            numero_processo_origem="0800000-00.2024.8.12.0001"
        )

        integrado = integrar_nat_ao_resultado(resultado, nat_result)

        assert integrado == True
        assert len(resultado.documentos) == 2
        assert resultado.documentos[-1].id == "nat-origem"

    def test_nao_duplica_nat_existente(self):
        """Não deve duplicar NAT que já existe no resultado (idempotência)."""
        doc_nat = criar_documento_nat("nat-existente", 8451)
        resultado = MockResultadoAnalise(
            numero_processo="1419974-57.2025.8.12.0000",
            documentos=[criar_documento_generico(), doc_nat]
        )

        nat_result = NATOrigemResult(
            nat_encontrado_origem=True,
            nat_source="origem",
            documento_nat=doc_nat,  # Mesmo documento
            numero_processo_origem="0800000-00.2024.8.12.0001"
        )

        integrado = integrar_nat_ao_resultado(resultado, nat_result)

        assert integrado == False
        assert len(resultado.documentos) == 2  # Não duplicou


class TestVerificarAgravoPorDocumentos:
    """Testes para a função de fallback verificar_agravo_por_documentos."""

    def test_detecta_agravo_por_decisao_agravada(self):
        """Detecta agravo quando há documento de Decisão Agravada."""
        documentos = [
            MockDocumentoTJMS(id="1", tipo_documento="9500", descricao="Petição"),
            MockDocumentoTJMS(id="2", tipo_documento="9516", descricao="Decisão Agravada"),
            MockDocumentoTJMS(id="3", tipo_documento="9501", descricao="Procuração"),
        ]

        resultado = verificar_agravo_por_documentos(documentos)
        assert resultado == True

    def test_nao_detecta_agravo_sem_indicadores(self):
        """Não detecta agravo se não há documentos indicadores."""
        documentos = [
            MockDocumentoTJMS(id="1", tipo_documento="9500", descricao="Petição"),
            MockDocumentoTJMS(id="2", tipo_documento="9501", descricao="Procuração"),
            MockDocumentoTJMS(id="3", tipo_documento="9534", descricao="Receita Médica"),
        ]

        resultado = verificar_agravo_por_documentos(documentos)
        assert resultado == False

    def test_codigos_indicadores_agravo(self):
        """Valida os códigos configurados como indicadores de agravo."""
        assert 9516 in CODIGOS_INDICADORES_AGRAVO  # Decisão Agravada

    def test_ignora_documentos_sem_codigo(self):
        """Ignora documentos sem código de tipo."""
        documentos = [
            MockDocumentoTJMS(id="1", tipo_documento=None),
            MockDocumentoTJMS(id="2", tipo_documento=""),
        ]

        resultado = verificar_agravo_por_documentos(documentos)
        assert resultado == False

    def test_ignora_codigos_invalidos(self):
        """Ignora códigos que não podem ser convertidos para int."""
        documentos = [
            MockDocumentoTJMS(id="1", tipo_documento="abc"),
            MockDocumentoTJMS(id="2", tipo_documento="9516abc"),
        ]

        resultado = verificar_agravo_por_documentos(documentos)
        assert resultado == False


class TestNATOrigemResolver:
    """Testes para a classe NATOrigemResolver."""

    @pytest.mark.asyncio
    async def test_nao_busca_se_nao_e_agravo(self):
        """Não deve buscar NAT no origem se não é agravo."""
        # Petição inicial que NÃO indica agravo
        doc_pi = MockDocumentoTJMS(
            id="doc-001",
            tipo_documento="500",
            resumo=json.dumps({"peticao_inicial_agravo": False})
        )
        resultado = MockResultadoAnalise(
            numero_processo="0800000-00.2024.8.12.0001",
            documentos=[doc_pi]
        )

        resolver = NATOrigemResolver(MagicMock())
        nat_result = await resolver.resolver(resultado)

        assert nat_result.busca_realizada == False
        assert nat_result.nat_source is None
        assert "agravo" in nat_result.motivo.lower() or "true" in nat_result.motivo.lower()

    @pytest.mark.asyncio
    async def test_nao_busca_se_nat_existe_no_agravo(self):
        """Não deve buscar NAT no origem se já existe NAT no agravo."""
        doc_pi = criar_documento_peticao_inicial_agravo()
        doc_nat = criar_documento_nat("nat-agravo", 8451)

        resultado = MockResultadoAnalise(
            numero_processo="1419974-57.2025.8.12.0000",
            documentos=[doc_pi, doc_nat]
        )

        resolver = NATOrigemResolver(MagicMock())
        nat_result = await resolver.resolver(resultado)

        assert nat_result.nat_encontrado_agravo == True
        assert nat_result.nat_source == "agravo"
        assert nat_result.busca_realizada == False
        assert nat_result.documento_nat.id == "nat-agravo"

    @pytest.mark.asyncio
    async def test_busca_nat_no_origem_quando_ausente_no_agravo(self):
        """Deve buscar NAT no origem quando agravo=true e NAT ausente no agravo."""
        doc_pi = criar_documento_peticao_inicial_agravo("0800000-00.2024.8.12.0001")

        resultado = MockResultadoAnalise(
            numero_processo="1419974-57.2025.8.12.0000",
            documentos=[doc_pi, criar_documento_generico()]  # Sem NAT
        )

        # Mock do método _buscar_documentos_origem
        doc_nat_origem = criar_documento_nat("nat-origem", 8451)

        resolver = NATOrigemResolver(MagicMock())

        with patch.object(resolver, '_buscar_documentos_origem', new_callable=AsyncMock) as mock_buscar:
            mock_buscar.return_value = [doc_nat_origem, criar_documento_generico("doc-origem")]

            nat_result = await resolver.resolver(resultado)

            # Verifica que a busca foi realizada
            assert nat_result.busca_realizada == True
            assert nat_result.numero_processo_origem == "0800000-00.2024.8.12.0001"

            # Verifica que NAT foi encontrado no origem
            assert nat_result.nat_encontrado_origem == True
            assert nat_result.nat_source == "origem"
            assert nat_result.documento_nat.id == "nat-origem"

            # Verifica que o método foi chamado com o número correto
            mock_buscar.assert_called_once_with("0800000-00.2024.8.12.0001")

    @pytest.mark.asyncio
    async def test_registra_log_quando_nat_nao_encontrado_em_nenhum(self):
        """Deve registrar log claro quando NAT não é encontrado em nenhum processo."""
        doc_pi = criar_documento_peticao_inicial_agravo("0800000-00.2024.8.12.0001")

        resultado = MockResultadoAnalise(
            numero_processo="1419974-57.2025.8.12.0000",
            documentos=[doc_pi]  # Sem NAT no agravo
        )

        resolver = NATOrigemResolver(MagicMock())

        with patch.object(resolver, '_buscar_documentos_origem', new_callable=AsyncMock) as mock_buscar:
            # Origem também não tem NAT
            mock_buscar.return_value = [criar_documento_generico("doc-origem")]

            nat_result = await resolver.resolver(resultado)

            assert nat_result.busca_realizada == True
            assert nat_result.nat_encontrado_agravo == False
            assert nat_result.nat_encontrado_origem == False
            assert nat_result.nat_source is None

            # Verifica mensagem de log/motivo
            assert "agravo" in nat_result.motivo.lower()
            assert "origem" in nat_result.motivo.lower()
            assert "não encontrado" in nat_result.motivo.lower() or "nao encontrado" in nat_result.motivo.lower()

    @pytest.mark.asyncio
    async def test_fallback_detecta_agravo_por_decisao_agravada(self):
        """Deve detectar agravo via fallback quando peticao_inicial_agravo não está definido."""
        # Petição inicial SEM campo peticao_inicial_agravo mas COM número de origem
        doc_pi = MockDocumentoTJMS(
            id="doc-001",
            tipo_documento="500",
            resumo=json.dumps({
                "peticao_inicial_fatos": "Fatos do processo...",
                "peticao_inicial_num_origem": "0800000-00.2024.8.12.0001"
            })  # Sem agravo mas com origem
        )

        # Documento de Decisão Agravada (código 9516) indica que É agravo
        doc_decisao_agravada = MockDocumentoTJMS(
            id="doc-002",
            tipo_documento="9516",
            descricao="Decisão Agravada"
        )

        resultado = MockResultadoAnalise(
            numero_processo="1419974-57.2025.8.12.0000",
            documentos=[doc_pi, doc_decisao_agravada]  # Com Decisão Agravada mas sem NAT
        )

        resolver = NATOrigemResolver(MagicMock())

        with patch.object(resolver, '_buscar_documentos_origem', new_callable=AsyncMock) as mock_buscar:
            # Origem também não tem NAT (mas a busca foi acionada!)
            mock_buscar.return_value = [criar_documento_generico("doc-origem")]

            nat_result = await resolver.resolver(resultado)

            # O importante é que a busca FOI realizada apesar de não ter peticao_inicial_agravo
            # Isso confirma que o fallback por Decisão Agravada funcionou
            assert nat_result.busca_realizada == True
            assert nat_result.nat_source is None  # NAT não encontrado, mas busca foi feita

    @pytest.mark.asyncio
    async def test_fallback_nao_aciona_sem_indicadores(self):
        """Não deve acionar fallback quando não há indicadores de agravo."""
        # Petição inicial SEM campo peticao_inicial_agravo E sem Decisão Agravada
        doc_pi = MockDocumentoTJMS(
            id="doc-001",
            tipo_documento="500",
            resumo=json.dumps({"peticao_inicial_fatos": "Fatos do processo..."})
        )

        doc_generico = MockDocumentoTJMS(
            id="doc-002",
            tipo_documento="9501",  # Procuração - não indica agravo
            descricao="Procuração"
        )

        resultado = MockResultadoAnalise(
            numero_processo="0800000-00.2024.8.12.0001",
            documentos=[doc_pi, doc_generico]
        )

        resolver = NATOrigemResolver(MagicMock())
        nat_result = await resolver.resolver(resultado)

        # Não deve ter realizado busca pois não é agravo
        assert nat_result.busca_realizada == False
        assert "agravo" in nat_result.motivo.lower()

    @pytest.mark.asyncio
    async def test_converte_numero_origem_numerico_para_string_cnj(self):
        """Deve converter número de origem numérico para formato CNJ."""
        # Petição inicial com agravo e número de origem como NUMBER (não string)
        doc_pi = MockDocumentoTJMS(
            id="doc-001",
            tipo_documento="500",
            resumo=json.dumps({
                "peticao_inicial_agravo": True,
                "peticao_inicial_num_origem": 8015048520258120013  # Número, não string
            })
        )

        resultado = MockResultadoAnalise(
            numero_processo="1419974-57.2025.8.12.0000",
            documentos=[doc_pi]
        )

        resolver = NATOrigemResolver(MagicMock())

        with patch.object(resolver, '_buscar_documentos_origem', new_callable=AsyncMock) as mock_buscar:
            mock_buscar.return_value = []  # Não encontrou NAT, mas queremos verificar a conversão

            await resolver.resolver(resultado)

            # Verifica que o número foi formatado corretamente no padrão CNJ
            # 8015048520258120013 -> 0801504-85.2025.8.12.0013
            mock_buscar.assert_called_once()
            numero_chamado = mock_buscar.call_args[0][0]
            assert numero_chamado == "0801504-85.2025.8.12.0013"


class TestNATOrigemResultToDict:
    """Testes para serialização do NATOrigemResult."""

    def test_to_dict_completo(self):
        """Deve serializar resultado completo para dicionário."""
        doc_nat = criar_documento_nat("nat-001", 8451)
        result = NATOrigemResult(
            busca_realizada=True,
            nat_encontrado_agravo=False,
            nat_encontrado_origem=True,
            documento_nat=doc_nat,
            nat_source="origem",
            numero_processo_origem="0800000-00.2024.8.12.0001",
            motivo="NAT encontrado no processo de origem"
        )

        d = result.to_dict()

        assert d["busca_realizada"] == True
        assert d["nat_encontrado_agravo"] == False
        assert d["nat_encontrado_origem"] == True
        assert d["nat_source"] == "origem"
        assert d["numero_processo_origem"] == "0800000-00.2024.8.12.0001"
        assert d["documento_nat_id"] == "nat-001"
        assert d["erro"] is None


# =============================================================================
# Testes de Integração (com processo real mockado)
# =============================================================================

class TestIntegracaoProcessoReal:
    """
    Testes de integração simulando o processo real 1419974-57.2025.8.12.0000.

    Estes testes validam o cenário completo de um agravo que não possui NAT
    e precisa buscar no processo de origem.
    """

    @pytest.fixture
    def dados_processo_agravo(self):
        """Fixture com dados do processo de agravo (sem NAT)."""
        return {
            "numero_processo": "1419974-57.2025.8.12.0000",
            "peticao_inicial": {
                "peticao_inicial_agravo": True,
                "peticao_inicial_num_origem": "0803386-54.2023.8.12.0045",
                "tipo": "Agravo de Instrumento",
                "autor": "Paciente Teste",
                "reu": "Estado de Mato Grosso do Sul"
            }
        }

    @pytest.fixture
    def documentos_agravo_sem_nat(self, dados_processo_agravo):
        """Fixture com documentos do agravo SEM NAT."""
        doc_pi = MockDocumentoTJMS(
            id="doc-pi-agravo",
            tipo_documento="500",
            descricao="Petição Inicial",
            resumo=json.dumps(dados_processo_agravo["peticao_inicial"])
        )
        doc_decisao = MockDocumentoTJMS(
            id="doc-decisao",
            tipo_documento="15",
            descricao="Decisão Interlocutória",
            resumo='{"tipo": "Decisão", "conteudo": "Defiro a tutela de urgência"}'
        )
        return [doc_pi, doc_decisao]

    @pytest.fixture
    def documentos_origem_com_nat(self):
        """Fixture com documentos do processo de origem COM NAT."""
        doc_nat = criar_documento_nat("nat-origem-real", 8451)
        doc_nat.resumo = json.dumps({
            "tipo": "Parecer NAT",
            "medicamento_analisado": "Pembrolizumabe",
            "incorporado_sus": False,
            "recomendacao": "Desfavorável",
            "justificativa": "Medicamento não incorporado ao SUS"
        })
        doc_pi_origem = MockDocumentoTJMS(
            id="doc-pi-origem",
            tipo_documento="500",
            descricao="Petição Inicial",
            resumo='{"tipo": "Petição Inicial"}'
        )
        return [doc_pi_origem, doc_nat]

    @pytest.mark.asyncio
    async def test_cenario_completo_agravo_busca_nat_origem(
        self,
        dados_processo_agravo,
        documentos_agravo_sem_nat,
        documentos_origem_com_nat
    ):
        """
        Teste de integração completo:
        1. Agravo sem NAT
        2. Busca NAT no processo de origem
        3. Encontra e integra NAT
        4. Verifica nat_source=origem
        """
        resultado_agravo = MockResultadoAnalise(
            numero_processo=dados_processo_agravo["numero_processo"],
            documentos=documentos_agravo_sem_nat
        )

        resolver = NATOrigemResolver(MagicMock())

        with patch.object(resolver, '_buscar_documentos_origem', new_callable=AsyncMock) as mock_buscar:
            mock_buscar.return_value = documentos_origem_com_nat

            nat_result = await resolver.resolver(resultado_agravo)

            # 1. Verifica que peticao_inicial_agravo foi reconhecido como true
            assert nat_result.busca_realizada == True, "Busca deveria ter sido realizada (agravo=true)"

            # 2. Verifica que NAT não existia no agravo
            assert nat_result.nat_encontrado_agravo == False, "NAT não deveria existir no agravo"

            # 3. Verifica que processo de origem foi consultado
            mock_buscar.assert_called_once()
            assert nat_result.numero_processo_origem == "0803386-54.2023.8.12.0045"

            # 4. Verifica que NAT foi encontrado no origem
            assert nat_result.nat_encontrado_origem == True
            assert nat_result.documento_nat is not None
            assert nat_result.documento_nat.id == "nat-origem-real"

            # 5. Verifica que nat_source está correto
            assert nat_result.nat_source == "origem"

    @pytest.mark.asyncio
    async def test_cenario_agravo_com_nat_nao_busca_origem(
        self,
        dados_processo_agravo,
        documentos_agravo_sem_nat
    ):
        """
        Teste que verifica que quando NAT existe no agravo, origem NÃO é consultada.
        """
        # Adiciona NAT aos documentos do agravo
        doc_nat_agravo = criar_documento_nat("nat-agravo-existente", 8451)
        documentos_agravo_sem_nat.append(doc_nat_agravo)

        resultado_agravo = MockResultadoAnalise(
            numero_processo=dados_processo_agravo["numero_processo"],
            documentos=documentos_agravo_sem_nat
        )

        resolver = NATOrigemResolver(MagicMock())

        with patch.object(resolver, '_buscar_documentos_origem', new_callable=AsyncMock) as mock_buscar:
            nat_result = await resolver.resolver(resultado_agravo)

            # Verifica que NAT foi encontrado no agravo
            assert nat_result.nat_encontrado_agravo == True
            assert nat_result.nat_source == "agravo"

            # IMPORTANTE: Verifica que a busca no origem NÃO foi feita
            mock_buscar.assert_not_called()


# =============================================================================
# Testes para fluxo de PDFs anexados
# =============================================================================

class TestVerificarAgravoEmDadosConsolidados:
    """Testes para verificar_agravo_em_dados_consolidados."""

    def test_detecta_agravo_variavel_padrao(self):
        """Deve detectar agravo com variável padrão."""
        from sistemas.gerador_pecas.services_nat_origem import verificar_agravo_em_dados_consolidados

        dados = {
            "peticao_inicial_agravo": True,
            "peticao_inicial_num_origem": "0800000-00.2024.8.12.0001"
        }

        is_agravo, num_origem = verificar_agravo_em_dados_consolidados(dados)

        assert is_agravo == True
        assert num_origem == "0800000-00.2024.8.12.0001"

    def test_detecta_agravo_variavel_com_prefixo_duplicado(self):
        """Deve detectar agravo mesmo com prefixo duplicado (namespace)."""
        from sistemas.gerador_pecas.services_nat_origem import verificar_agravo_em_dados_consolidados

        dados = {
            "peticao_inicial_peticao_inicial_agravo": True,
            "peticao_inicial_peticao_inicial_num_origem": "0800000-00.2024.8.12.0001"
        }

        is_agravo, num_origem = verificar_agravo_em_dados_consolidados(dados)

        assert is_agravo == True
        assert num_origem == "0800000-00.2024.8.12.0001"

    def test_nao_detecta_agravo_quando_false(self):
        """Não deve detectar agravo quando variável é False."""
        from sistemas.gerador_pecas.services_nat_origem import verificar_agravo_em_dados_consolidados

        dados = {
            "peticao_inicial_agravo": False,
            "peticao_inicial_num_origem": "0800000-00.2024.8.12.0001"
        }

        is_agravo, num_origem = verificar_agravo_em_dados_consolidados(dados)

        assert is_agravo == False

    def test_detecta_agravo_string_sim(self):
        """Deve detectar agravo quando valor é string 'sim'."""
        from sistemas.gerador_pecas.services_nat_origem import verificar_agravo_em_dados_consolidados

        dados = {
            "peticao_inicial_agravo": "sim",
            "peticao_inicial_num_origem": "0800000-00.2024.8.12.0001"
        }

        is_agravo, num_origem = verificar_agravo_em_dados_consolidados(dados)

        assert is_agravo == True


class TestVerificarNATEmPDFsAnexados:
    """Testes para verificar_nat_em_pdfs_anexados."""

    def test_detecta_nat_por_categoria(self):
        """Deve detectar NAT pela categoria do documento."""
        from sistemas.gerador_pecas.services_nat_origem import verificar_nat_em_pdfs_anexados

        docs = [
            {"categoria": "Petição Inicial"},
            {"categoria": "Parecer NAT"},
        ]
        dados = {}

        assert verificar_nat_em_pdfs_anexados(docs, dados) == True

    def test_detecta_nat_por_variavel(self):
        """Deve detectar NAT por variável extraída."""
        from sistemas.gerador_pecas.services_nat_origem import verificar_nat_em_pdfs_anexados

        docs = [{"categoria": "Petição Inicial"}]
        dados = {
            "parecer_nat_medicamento_analisado": "Pembrolizumabe",
            "parecer_nat_incorporado_sus": False
        }

        assert verificar_nat_em_pdfs_anexados(docs, dados) == True

    def test_nao_detecta_nat_sem_documentos_nat(self):
        """Não deve detectar NAT quando não há documentos NAT."""
        from sistemas.gerador_pecas.services_nat_origem import verificar_nat_em_pdfs_anexados

        docs = [
            {"categoria": "Petição Inicial"},
            {"categoria": "Contestação"},
        ]
        dados = {
            "peticao_inicial_agravo": True,
            "peticao_inicial_autor": "Fulano"
        }

        assert verificar_nat_em_pdfs_anexados(docs, dados) == False


class TestBuscarNATParaPDFsAnexados:
    """Testes para buscar_nat_para_pdfs_anexados."""

    @pytest.mark.asyncio
    async def test_nao_busca_se_nao_e_agravo(self):
        """Não deve buscar NAT se não é agravo."""
        from sistemas.gerador_pecas.services_nat_origem import buscar_nat_para_pdfs_anexados

        dados = {
            "peticao_inicial_agravo": False,
        }
        docs = [{"categoria": "Petição Inicial"}]

        result = await buscar_nat_para_pdfs_anexados(dados, docs)

        assert result.busca_realizada == False
        assert "agravo" in result.motivo.lower()

    @pytest.mark.asyncio
    async def test_nao_busca_se_nat_presente_nos_pdfs(self):
        """Não deve buscar NAT se já está presente nos PDFs."""
        from sistemas.gerador_pecas.services_nat_origem import buscar_nat_para_pdfs_anexados

        dados = {
            "peticao_inicial_agravo": True,
            "peticao_inicial_num_origem": "0800000-00.2024.8.12.0001",
            "parecer_nat_medicamento_analisado": "Pembrolizumabe"
        }
        docs = [
            {"categoria": "Petição Inicial"},
            {"categoria": "Parecer NAT"}
        ]

        result = await buscar_nat_para_pdfs_anexados(dados, docs)

        assert result.nat_encontrado == True
        assert result.nat_source == "pdfs_anexados"
        assert result.busca_realizada == False

    @pytest.mark.asyncio
    async def test_nao_busca_sem_numero_origem(self):
        """Não deve buscar se não tem número de origem."""
        from sistemas.gerador_pecas.services_nat_origem import buscar_nat_para_pdfs_anexados

        dados = {
            "peticao_inicial_agravo": True,
            # Sem peticao_inicial_num_origem
        }
        docs = [{"categoria": "Petição Inicial"}]

        result = await buscar_nat_para_pdfs_anexados(dados, docs)

        assert result.busca_realizada == False
        assert "origem" in result.motivo.lower()


class TestNATParaPDFsResult:
    """Testes para NATParaPDFsResult."""

    def test_to_dict(self):
        """Deve serializar corretamente para dicionário."""
        from sistemas.gerador_pecas.services_nat_origem import NATParaPDFsResult

        result = NATParaPDFsResult(
            busca_realizada=True,
            nat_encontrado=True,
            nat_source="origem",
            numero_processo_origem="0800000-00.2024.8.12.0001",
            motivo="NAT encontrado"
        )

        d = result.to_dict()

        assert d["busca_realizada"] == True
        assert d["nat_encontrado"] == True
        assert d["nat_source"] == "origem"
        assert d["numero_processo_origem"] == "0800000-00.2024.8.12.0001"


# =============================================================================
# Runner
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
