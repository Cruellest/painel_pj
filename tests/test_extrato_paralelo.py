# tests/test_extrato_paralelo.py
"""
Testes automatizados para extração paralela de extrato de subconta.

Cenários testados:
1. A válido -> usa A (scrapper vence)
2. A lento, B rápido, A válido no fim -> usa A (scrapper tem prioridade)
3. A falha/timeout -> usa B (fallback)
4. A inválido -> usa B (fallback)
5. A e B falham -> documento gerado com extrato null e observação
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass
from typing import Optional, List

from sistemas.prestacao_contas.extrato_paralelo import (
    ExtratorParalelo,
    ConfigExtratoParalelo,
    ExtratoSource,
    ExtratoFailReason,
    ResultadoExtratoParalelo,
    is_valid_extrato,
    extrair_extrato_paralelo,
)
from sistemas.prestacao_contas.scrapper_subconta import (
    StatusProcessamento,
    ResultadoExtracao,
)


# =====================================================
# FIXTURES
# =====================================================

@pytest.fixture
def config_extrato():
    """Configuração padrão para testes."""
    return ConfigExtratoParalelo(
        scrapper_timeout=5.0,  # Timeout curto para testes
        fallback_timeout=5.0,
        min_caracteres_extrato=100,
        min_caracteres_util=200,
    )


@pytest.fixture
def mock_documentos():
    """Documentos mockados para fallback."""
    @dataclass
    class MockDocumento:
        id: str
        tipo_codigo: str
        tipo_descricao: str
        data_juntada: Optional[str] = None

    return [
        MockDocumento(id="doc1", tipo_codigo="71", tipo_descricao="Extrato da Conta Única"),
        MockDocumento(id="doc2", tipo_codigo="71", tipo_descricao="Extrato da Conta Única"),
        MockDocumento(id="doc3", tipo_codigo="25", tipo_descricao="Petição"),
    ]


@pytest.fixture
def extrato_valido():
    """Texto de extrato válido com marcadores esperados."""
    return """
    EXTRATO DA SUBCONTA
    Número do Processo: 0857327-80.2025.8.12.0001

    INFORMAÇÕES DA SUBCONTA
    Valor Bloqueado: R$ 50.000,00
    Saldo Atual: R$ 45.000,00

    MOVIMENTAÇÃO
    - 01/01/2025: Bloqueio R$ 50.000,00
    - 15/01/2025: Liberação R$ 5.000,00

    Este texto tem mais de 200 caracteres para ser considerado válido pelo sistema
    de validação de extrato que verifica o tamanho mínimo do texto extraído.
    """


@pytest.fixture
def extrato_invalido_curto():
    """Texto de extrato inválido (muito curto)."""
    return "Texto curto"


@pytest.fixture
def extrato_invalido_sem_marcadores():
    """Texto sem marcadores esperados."""
    return "A" * 300  # Texto longo mas sem marcadores


# =====================================================
# TESTES is_valid_extrato
# =====================================================

class TestIsValidExtrato:
    """Testes da função de validação de extrato."""

    def test_extrato_valido(self, extrato_valido, config_extrato):
        """Extrato válido deve retornar True."""
        assert is_valid_extrato(extrato_valido, config_extrato) is True

    def test_extrato_vazio(self, config_extrato):
        """Extrato vazio deve retornar False."""
        assert is_valid_extrato("", config_extrato) is False
        assert is_valid_extrato(None, config_extrato) is False
        assert is_valid_extrato("   ", config_extrato) is False

    def test_extrato_curto(self, extrato_invalido_curto, config_extrato):
        """Extrato muito curto deve retornar False."""
        assert is_valid_extrato(extrato_invalido_curto, config_extrato) is False

    def test_extrato_sem_marcadores(self, extrato_invalido_sem_marcadores, config_extrato):
        """Extrato sem marcadores esperados deve retornar False."""
        assert is_valid_extrato(extrato_invalido_sem_marcadores, config_extrato) is False

    def test_extrato_com_marcador_parcial(self, config_extrato):
        """Extrato com pelo menos 1 marcador deve ser válido."""
        texto = "Este texto contém a palavra SUBCONTA e tem mais de 100 caracteres para ser considerado válido pelo sistema de validação."
        assert is_valid_extrato(texto, config_extrato) is True


# =====================================================
# TESTES ExtratorParalelo
# =====================================================

class TestExtratorParalelo:
    """Testes do orquestrador de extração paralela."""

    @pytest.mark.asyncio
    async def test_cenario_1_scrapper_valido(self, config_extrato, mock_documentos, extrato_valido):
        """
        Cenário 1: A válido -> usa A
        Scrapper retorna extrato válido, deve usar o scrapper.
        """
        with patch('sistemas.prestacao_contas.extrato_paralelo.extrair_extrato_subconta') as mock_scrapper:
            # Mock scrapper retorna extrato válido
            mock_scrapper.return_value = ResultadoExtracao(
                numero_processo="0857327-80.2025.8.12.0001",
                status=StatusProcessamento.OK,
                pdf_bytes=b"PDF_CONTENT",
                texto_extraido=extrato_valido,
            )

            extrator = ExtratorParalelo(config=config_extrato, correlation_id="test1")
            resultado = await extrator.extrair_paralelo(
                numero_cnj="0857327-80.2025.8.12.0001",
                documentos=mock_documentos,
            )

            # Deve usar o scrapper
            assert resultado.source == ExtratoSource.SCRAPPER
            assert resultado.valido is True
            assert resultado.texto == extrato_valido
            assert resultado.metricas.extrato_source == ExtratoSource.SCRAPPER
            assert resultado.metricas.t_scrapper is not None
            assert resultado.metricas.t_scrapper > 0

    @pytest.mark.asyncio
    async def test_cenario_2_scrapper_lento_mas_valido(self, config_extrato, mock_documentos, extrato_valido):
        """
        Cenário 2: A lento, B rápido, A válido no fim -> usa A
        Mesmo que o scrapper seja mais lento, se retornar válido, usa scrapper.
        """
        async def scrapper_lento(*args, **kwargs):
            await asyncio.sleep(0.5)  # Simula scrapper lento
            return ResultadoExtracao(
                numero_processo="0857327-80.2025.8.12.0001",
                status=StatusProcessamento.OK,
                pdf_bytes=b"PDF_CONTENT",
                texto_extraido=extrato_valido,
            )

        with patch('sistemas.prestacao_contas.extrato_paralelo.extrair_extrato_subconta', side_effect=scrapper_lento):
            with patch('sistemas.prestacao_contas.extrato_paralelo.baixar_documentos_async') as mock_baixar:
                # Mock fallback retorna rápido mas com texto válido também
                mock_baixar.return_value = """
                <documento idDocumento="doc1">
                    <conteudo>UERGW==</conteudo>
                </documento>
                """

                extrator = ExtratorParalelo(config=config_extrato, correlation_id="test2")
                resultado = await extrator.extrair_paralelo(
                    numero_cnj="0857327-80.2025.8.12.0001",
                    documentos=mock_documentos,
                )

                # Deve usar o scrapper (tem prioridade mesmo sendo mais lento)
                assert resultado.source == ExtratoSource.SCRAPPER
                assert resultado.valido is True

    @pytest.mark.asyncio
    async def test_cenario_3_scrapper_timeout_usa_fallback(self, config_extrato, mock_documentos, extrato_valido):
        """
        Cenário 3: A falha/timeout -> usa B
        Scrapper dá timeout, deve usar o fallback.
        """
        async def scrapper_timeout(*args, **kwargs):
            await asyncio.sleep(10)  # Maior que o timeout
            return ResultadoExtracao(
                numero_processo="0857327-80.2025.8.12.0001",
                status=StatusProcessamento.OK,
                texto_extraido=extrato_valido,
            )

        # Configura timeout curto
        config_extrato.scrapper_timeout = 0.1

        with patch('sistemas.prestacao_contas.extrato_paralelo.extrair_extrato_subconta', side_effect=scrapper_timeout):
            with patch('sistemas.prestacao_contas.extrato_paralelo.baixar_documentos_async') as mock_baixar:
                with patch('sistemas.prestacao_contas.extrato_paralelo.extrair_texto_pdf') as mock_extrair:
                    # Mock fallback retorna extrato válido
                    import base64
                    mock_baixar.return_value = f"""
                    <documento idDocumento="doc1">
                        <conteudo>{base64.b64encode(b"PDF_CONTENT").decode()}</conteudo>
                    </documento>
                    """
                    mock_extrair.return_value = extrato_valido

                    extrator = ExtratorParalelo(config=config_extrato, correlation_id="test3")
                    resultado = await extrator.extrair_paralelo(
                        numero_cnj="0857327-80.2025.8.12.0001",
                        documentos=mock_documentos,
                    )

                    # Deve usar o fallback
                    assert resultado.source == ExtratoSource.FALLBACK_DOCUMENTOS
                    assert resultado.valido is True
                    assert resultado.metricas.scrapper_fail_reason == ExtratoFailReason.TIMEOUT

    @pytest.mark.asyncio
    async def test_cenario_4_scrapper_invalido_usa_fallback(self, config_extrato, mock_documentos, extrato_valido, extrato_invalido_curto):
        """
        Cenário 4: A inválido -> usa B
        Scrapper retorna extrato inválido (curto), deve usar fallback.
        """
        with patch('sistemas.prestacao_contas.extrato_paralelo.extrair_extrato_subconta') as mock_scrapper:
            with patch('sistemas.prestacao_contas.extrato_paralelo.baixar_documentos_async') as mock_baixar:
                with patch('sistemas.prestacao_contas.extrato_paralelo.extrair_texto_pdf') as mock_extrair:
                    # Mock scrapper retorna extrato inválido (curto)
                    mock_scrapper.return_value = ResultadoExtracao(
                        numero_processo="0857327-80.2025.8.12.0001",
                        status=StatusProcessamento.OK,
                        pdf_bytes=b"PDF_CONTENT",
                        texto_extraido=extrato_invalido_curto,
                    )

                    # Mock fallback retorna extrato válido
                    import base64
                    mock_baixar.return_value = f"""
                    <documento idDocumento="doc1">
                        <conteudo>{base64.b64encode(b"PDF_CONTENT").decode()}</conteudo>
                    </documento>
                    """
                    mock_extrair.return_value = extrato_valido

                    extrator = ExtratorParalelo(config=config_extrato, correlation_id="test4")
                    resultado = await extrator.extrair_paralelo(
                        numero_cnj="0857327-80.2025.8.12.0001",
                        documentos=mock_documentos,
                    )

                    # Deve usar o fallback
                    assert resultado.source == ExtratoSource.FALLBACK_DOCUMENTOS
                    assert resultado.valido is True
                    assert resultado.metricas.scrapper_fail_reason == ExtratoFailReason.INVALID

    @pytest.mark.asyncio
    async def test_cenario_5_ambos_falham_continua_sem_extrato(self, config_extrato, mock_documentos):
        """
        Cenário 5: A e B falham -> documento ainda é gerado com extrato null e observação
        Ambas as fontes falham, deve continuar sem extrato e com observação.
        """
        with patch('sistemas.prestacao_contas.extrato_paralelo.extrair_extrato_subconta') as mock_scrapper:
            with patch('sistemas.prestacao_contas.extrato_paralelo.baixar_documentos_async') as mock_baixar:
                # Mock scrapper falha (sem subconta)
                mock_scrapper.return_value = ResultadoExtracao(
                    numero_processo="0857327-80.2025.8.12.0001",
                    status=StatusProcessamento.SEM_SUBCONTA,
                    erro="Processo não possui subconta",
                )

                # Mock fallback também falha (erro de rede)
                mock_baixar.side_effect = Exception("Erro de conexão")

                extrator = ExtratorParalelo(config=config_extrato, correlation_id="test5")
                resultado = await extrator.extrair_paralelo(
                    numero_cnj="0857327-80.2025.8.12.0001",
                    documentos=mock_documentos,
                )

                # Deve retornar sem extrato mas com observação
                assert resultado.source == ExtratoSource.NONE
                assert resultado.valido is False
                assert resultado.texto is None
                assert resultado.observacao is not None
                assert "EXTRATO DA SUBCONTA NÃO LOCALIZADO" in resultado.observacao
                assert resultado.metricas.extrato_source == ExtratoSource.NONE
                assert resultado.metricas.scrapper_fail_reason == ExtratoFailReason.SEM_SUBCONTA


# =====================================================
# TESTES DE MÉTRICAS
# =====================================================

class TestMetricasExtracao:
    """Testes das métricas de observabilidade."""

    @pytest.mark.asyncio
    async def test_metricas_tempos_registrados(self, config_extrato, mock_documentos, extrato_valido):
        """Verifica se os tempos são registrados corretamente."""
        with patch('sistemas.prestacao_contas.extrato_paralelo.extrair_extrato_subconta') as mock_scrapper:
            mock_scrapper.return_value = ResultadoExtracao(
                numero_processo="0857327-80.2025.8.12.0001",
                status=StatusProcessamento.OK,
                pdf_bytes=b"PDF_CONTENT",
                texto_extraido=extrato_valido,
            )

            extrator = ExtratorParalelo(config=config_extrato, correlation_id="metrics_test")
            resultado = await extrator.extrair_paralelo(
                numero_cnj="0857327-80.2025.8.12.0001",
                documentos=mock_documentos,
            )

            # Verifica métricas
            assert resultado.metricas.correlation_id == "metrics_test"
            assert resultado.metricas.t_scrapper is not None
            assert resultado.metricas.t_fallback is not None
            assert resultado.metricas.t_total > 0
            assert resultado.metricas.t_total >= resultado.metricas.t_scrapper or resultado.metricas.t_total >= resultado.metricas.t_fallback

    @pytest.mark.asyncio
    async def test_metricas_to_dict(self, config_extrato, mock_documentos, extrato_valido):
        """Verifica serialização das métricas."""
        with patch('sistemas.prestacao_contas.extrato_paralelo.extrair_extrato_subconta') as mock_scrapper:
            mock_scrapper.return_value = ResultadoExtracao(
                numero_processo="0857327-80.2025.8.12.0001",
                status=StatusProcessamento.OK,
                pdf_bytes=b"PDF_CONTENT",
                texto_extraido=extrato_valido,
            )

            extrator = ExtratorParalelo(config=config_extrato, correlation_id="dict_test")
            resultado = await extrator.extrair_paralelo(
                numero_cnj="0857327-80.2025.8.12.0001",
                documentos=mock_documentos,
            )

            metricas_dict = resultado.metricas.to_dict()

            # Verifica estrutura do dict
            assert "correlation_id" in metricas_dict
            assert "t_scrapper" in metricas_dict
            assert "t_fallback" in metricas_dict
            assert "t_total" in metricas_dict
            assert "extrato_source" in metricas_dict
            assert metricas_dict["extrato_source"] == "scrapper"


# =====================================================
# TESTES DE INTEGRAÇÃO (função de conveniência)
# =====================================================

class TestExtrairExtratoParalelo:
    """Testes da função de conveniência."""

    @pytest.mark.asyncio
    async def test_funcao_conveniencia(self, config_extrato, mock_documentos, extrato_valido):
        """Testa a função de conveniência extrair_extrato_paralelo."""
        with patch('sistemas.prestacao_contas.extrato_paralelo.extrair_extrato_subconta') as mock_scrapper:
            mock_scrapper.return_value = ResultadoExtracao(
                numero_processo="0857327-80.2025.8.12.0001",
                status=StatusProcessamento.OK,
                pdf_bytes=b"PDF_CONTENT",
                texto_extraido=extrato_valido,
            )

            resultado = await extrair_extrato_paralelo(
                numero_cnj="0857327-80.2025.8.12.0001",
                documentos=mock_documentos,
                config=config_extrato,
                correlation_id="conv_test",
            )

            assert resultado.valido is True
            assert resultado.source == ExtratoSource.SCRAPPER
            assert resultado.metricas.correlation_id == "conv_test"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
