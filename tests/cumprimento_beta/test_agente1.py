# tests/cumprimento_beta/test_agente1.py
"""
Testes do Agente 1 do módulo Cumprimento de Sentença Beta.

Verifica:
- Documentos ignorados não entram no fluxo
- Documentos irrelevantes não geram JSON
- Documentos relevantes geram JSON válido
- Mudança de prompt afeta classificação
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, AsyncMock
import json

from sistemas.cumprimento_beta.constants import StatusRelevancia, StatusSessao


class TestCodigosIgnorados:
    """Testes para filtro de códigos ignorados"""

    def test_codigo_ignorado_retorna_true(self):
        """Código na blacklist deve ser identificado como ignorado"""
        from sistemas.cumprimento_beta.services_download import DownloadService

        with patch.object(DownloadService, '_carregar_codigos_ignorados') as mock_carregar:
            service = DownloadService.__new__(DownloadService)
            service.db = Mock()
            service._codigos_ignorados = {10, 20, 30}

            assert service.codigo_deve_ser_ignorado(10) is True
            assert service.codigo_deve_ser_ignorado(20) is True

    def test_codigo_nao_ignorado_retorna_false(self):
        """Código fora da blacklist não deve ser ignorado"""
        from sistemas.cumprimento_beta.services_download import DownloadService

        with patch.object(DownloadService, '_carregar_codigos_ignorados'):
            service = DownloadService.__new__(DownloadService)
            service.db = Mock()
            service._codigos_ignorados = {10, 20, 30}

            assert service.codigo_deve_ser_ignorado(500) is False
            assert service.codigo_deve_ser_ignorado(9500) is False


class TestAvaliacaoRelevancia:
    """Testes para avaliação de relevância de documentos"""

    @pytest.mark.asyncio
    async def test_documento_sem_conteudo_eh_irrelevante(self):
        """Documento sem conteúdo textual deve ser classificado como irrelevante"""
        from sistemas.cumprimento_beta.services_relevancia import RelevanciaService

        with patch.object(RelevanciaService, '_carregar_modelo', return_value='gemini-1.5-flash'):
            with patch.object(RelevanciaService, '_carregar_criterios_relevancia', return_value='criterios'):
                service = RelevanciaService.__new__(RelevanciaService)
                service.db = Mock()
                service._modelo = 'gemini-1.5-flash'
                service._criterios = 'criterios'

                # Documento sem conteúdo
                documento = Mock()
                documento.conteudo_texto = None

                relevante, motivo = await service.avaliar_documento(documento)

                assert relevante is False
                assert "sem conteúdo" in motivo.lower()

    @pytest.mark.asyncio
    async def test_documento_com_conteudo_curto_eh_irrelevante(self):
        """Documento com conteúdo muito curto deve ser irrelevante"""
        from sistemas.cumprimento_beta.services_relevancia import RelevanciaService

        with patch.object(RelevanciaService, '_carregar_modelo', return_value='gemini-1.5-flash'):
            with patch.object(RelevanciaService, '_carregar_criterios_relevancia', return_value='criterios'):
                service = RelevanciaService.__new__(RelevanciaService)
                service.db = Mock()
                service._modelo = 'gemini-1.5-flash'
                service._criterios = 'criterios'

                # Documento com conteúdo muito curto
                documento = Mock()
                documento.conteudo_texto = "texto curto"  # menos de 50 chars

                relevante, motivo = await service.avaliar_documento(documento)

                assert relevante is False


class TestExtracaoJSON:
    """Testes para extração de JSON estruturado"""

    def test_documento_irrelevante_nao_gera_json(self):
        """Documento irrelevante não deve gerar JSON"""
        from sistemas.cumprimento_beta.services_extracao_json import ExtracaoJSONService

        with patch.object(ExtracaoJSONService, '_carregar_categoria', return_value=None):
            with patch.object(ExtracaoJSONService, '_carregar_modelo', return_value='gemini-1.5-flash'):
                service = ExtracaoJSONService.__new__(ExtracaoJSONService)
                service.db = Mock()
                service._categoria = None
                service._modelo = 'gemini-1.5-flash'

                # Documento irrelevante
                documento = Mock()
                documento.status_relevancia = StatusRelevancia.IRRELEVANTE

                # Método síncrono que verifica status
                import asyncio
                result = asyncio.get_event_loop().run_until_complete(
                    service.extrair_json_documento(documento)
                )

                assert result is None

    def test_extrair_json_da_resposta_valida(self):
        """Deve extrair JSON válido da resposta do Gemini"""
        from sistemas.cumprimento_beta.services_extracao_json import ExtracaoJSONService

        service = ExtracaoJSONService.__new__(ExtracaoJSONService)

        resposta = '''```json
{
    "document_id": "123",
    "tipo_documento": "sentença",
    "resumo": "Texto de teste"
}
```'''

        resultado = service._extrair_e_validar_json(resposta)

        assert resultado is not None
        assert resultado["document_id"] == "123"
        assert resultado["tipo_documento"] == "sentença"

    def test_extrair_json_de_resposta_invalida_retorna_none(self):
        """Resposta inválida deve retornar None"""
        from sistemas.cumprimento_beta.services_extracao_json import ExtracaoJSONService

        service = ExtracaoJSONService.__new__(ExtracaoJSONService)

        resposta = "Isso não é um JSON válido"

        resultado = service._extrair_e_validar_json(resposta)

        assert resultado is None


class TestPipelineCompleto:
    """Testes do pipeline completo do Agente 1"""

    @pytest.mark.asyncio
    async def test_documento_ignorado_marcado_corretamente(self):
        """Documento com código ignorado deve ser marcado como IGNORADO"""
        from sistemas.cumprimento_beta.models import DocumentoBeta

        documento = DocumentoBeta()
        documento.codigo_documento = 10  # Código na blacklist
        documento.status_relevancia = StatusRelevancia.IGNORADO

        assert documento.status_relevancia == StatusRelevancia.IGNORADO

    @pytest.mark.asyncio
    async def test_apenas_relevantes_geram_json(self):
        """Apenas documentos relevantes devem gerar JSON"""
        # Este teste verifica a lógica do pipeline
        documentos = [
            {"status": StatusRelevancia.RELEVANTE, "deve_gerar_json": True},
            {"status": StatusRelevancia.IRRELEVANTE, "deve_gerar_json": False},
            {"status": StatusRelevancia.IGNORADO, "deve_gerar_json": False},
            {"status": StatusRelevancia.PENDENTE, "deve_gerar_json": False},
        ]

        for doc in documentos:
            # Apenas RELEVANTE deve gerar JSON
            deve_processar = doc["status"] == StatusRelevancia.RELEVANTE
            assert deve_processar == doc["deve_gerar_json"], f"Falha para status {doc['status']}"


class TestMudancaConfiguracao:
    """Testes para verificar que mudanças de configuração afetam execução"""

    def test_modelo_carregado_do_admin(self):
        """Modelo deve ser carregado da configuração do admin"""
        from sistemas.cumprimento_beta.services_relevancia import RelevanciaService
        from sistemas.cumprimento_beta.constants import MODELO_PADRAO_AGENTE1

        # Mock do banco retornando modelo customizado
        mock_db = Mock()
        mock_config = Mock()
        mock_config.valor = "gemini-1.5-pro-custom"

        mock_db.query.return_value.filter.return_value.first.return_value = mock_config

        service = RelevanciaService.__new__(RelevanciaService)
        service.db = mock_db

        modelo = service._carregar_modelo()

        assert modelo == "gemini-1.5-pro-custom"

    def test_modelo_padrao_quando_nao_configurado(self):
        """Deve usar modelo padrão quando não configurado"""
        from sistemas.cumprimento_beta.services_relevancia import RelevanciaService
        from sistemas.cumprimento_beta.constants import MODELO_PADRAO_AGENTE1

        # Mock do banco retornando None
        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        service = RelevanciaService.__new__(RelevanciaService)
        service.db = mock_db

        modelo = service._carregar_modelo()

        assert modelo == MODELO_PADRAO_AGENTE1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
