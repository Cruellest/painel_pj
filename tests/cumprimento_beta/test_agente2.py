# tests/cumprimento_beta/test_agente2.py
"""
Testes do Agente 2 do módulo Cumprimento de Sentença Beta.

Verifica:
- Consolidação com múltiplos JSONs
- Sugestões geradas corretamente
- Mudança de modelo afeta execução
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, AsyncMock
import json

from sistemas.cumprimento_beta.constants import StatusSessao, MODELO_PADRAO_AGENTE2


class TestConsolidacao:
    """Testes para serviço de consolidação"""

    def test_montar_documentos_json(self):
        """Deve montar string JSON corretamente a partir de lista de resumos"""
        from sistemas.cumprimento_beta.services_consolidacao import ConsolidacaoService

        service = ConsolidacaoService.__new__(ConsolidacaoService)

        # Mocks de JSONResumoBeta
        json1 = Mock()
        json1.json_conteudo = {"resumo": "Documento 1"}
        json1.documento = Mock()
        json1.documento.descricao_documento = "Petição"
        json1.documento.codigo_documento = 500
        json1.documento.data_documento = None

        json2 = Mock()
        json2.json_conteudo = {"resumo": "Documento 2"}
        json2.documento = Mock()
        json2.documento.descricao_documento = "Sentença"
        json2.documento.codigo_documento = 200
        json2.documento.data_documento = None

        resultado = service._montar_documentos_json([json1, json2])

        # Verifica que contém informações de ambos os documentos
        assert "Petição" in resultado or "Documento 1" in resultado
        assert "Sentença" in resultado or "Documento 2" in resultado
        assert "---" in resultado  # Separador

    def test_extrair_dados_resposta_json_valido(self):
        """Deve extrair dados de resposta JSON válida"""
        from sistemas.cumprimento_beta.services_consolidacao import ConsolidacaoService

        service = ConsolidacaoService.__new__(ConsolidacaoService)

        resposta = '''```json
{
    "resumo_consolidado": "Este é o resumo do processo...",
    "dados_processo": {
        "exequente": "Fulano de Tal",
        "executado": "Estado de MS"
    },
    "sugestoes_pecas": [
        {"tipo": "Impugnação", "descricao": "Para contestar valores", "prioridade": "alta"}
    ]
}
```'''

        resultado = service._extrair_dados_resposta(resposta)

        assert resultado is not None
        assert "resumo_consolidado" in resultado
        assert resultado["dados_processo"]["exequente"] == "Fulano de Tal"
        assert len(resultado["sugestoes_pecas"]) == 1

    def test_extrair_dados_resposta_texto_puro(self):
        """Resposta sem JSON deve usar texto como resumo"""
        from sistemas.cumprimento_beta.services_consolidacao import ConsolidacaoService

        service = ConsolidacaoService.__new__(ConsolidacaoService)

        resposta = "Este é apenas um texto de resumo sem formatação JSON."

        resultado = service._extrair_dados_resposta(resposta)

        assert resultado is not None
        assert resultado["resumo_consolidado"] == resposta
        assert resultado["sugestoes_pecas"] == []


class TestSugestoesPecas:
    """Testes para geração de sugestões de peças"""

    def test_sugestoes_extraidas_corretamente(self):
        """Sugestões devem ser extraídas do JSON de resposta"""
        from sistemas.cumprimento_beta.services_consolidacao import ConsolidacaoService

        service = ConsolidacaoService.__new__(ConsolidacaoService)

        resposta_json = {
            "resumo_consolidado": "Resumo...",
            "sugestoes_pecas": [
                {"tipo": "Impugnação ao Cumprimento", "descricao": "Contestar cálculos", "prioridade": "alta"},
                {"tipo": "Pedido de Parcelamento", "descricao": "Solicitar parcelamento", "prioridade": "media"},
            ]
        }

        resposta = f"```json\n{json.dumps(resposta_json)}\n```"

        resultado = service._extrair_dados_resposta(resposta)

        assert len(resultado["sugestoes_pecas"]) == 2
        assert resultado["sugestoes_pecas"][0]["tipo"] == "Impugnação ao Cumprimento"
        assert resultado["sugestoes_pecas"][1]["prioridade"] == "media"


class TestModeloConfiguravel:
    """Testes para verificar que modelo é configurável"""

    def test_modelo_carregado_do_admin(self):
        """Modelo do Agente 2 deve ser carregado do admin"""
        from sistemas.cumprimento_beta.services_consolidacao import ConsolidacaoService

        mock_db = Mock()
        mock_config = Mock()
        mock_config.valor = "gemini-2.0-flash"

        mock_db.query.return_value.filter.return_value.first.return_value = mock_config

        service = ConsolidacaoService.__new__(ConsolidacaoService)
        service.db = mock_db

        modelo = service._carregar_modelo()

        assert modelo == "gemini-2.0-flash"

    def test_modelo_padrao_quando_nao_configurado(self):
        """Deve usar modelo padrão quando não configurado"""
        from sistemas.cumprimento_beta.services_consolidacao import ConsolidacaoService

        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        service = ConsolidacaoService.__new__(ConsolidacaoService)
        service.db = mock_db

        modelo = service._carregar_modelo()

        assert modelo == MODELO_PADRAO_AGENTE2


class TestAgente2Pipeline:
    """Testes do pipeline do Agente 2"""

    def test_verifica_jsons_disponiveis(self):
        """Deve verificar corretamente se há JSONs disponíveis"""
        from sistemas.cumprimento_beta.agente2 import Agente2

        mock_db = Mock()
        mock_db.query.return_value.join.return_value.filter.return_value.count.return_value = 5

        agente = Agente2.__new__(Agente2)
        agente.db = mock_db

        sessao = Mock()
        sessao.id = 1

        count = agente._verificar_jsons_disponiveis(sessao)

        assert count == 5

    def test_sem_jsons_retorna_zero(self):
        """Deve retornar zero quando não há JSONs"""
        from sistemas.cumprimento_beta.agente2 import Agente2

        mock_db = Mock()
        mock_db.query.return_value.join.return_value.filter.return_value.count.return_value = 0

        agente = Agente2.__new__(Agente2)
        agente.db = mock_db

        sessao = Mock()
        sessao.id = 1

        count = agente._verificar_jsons_disponiveis(sessao)

        assert count == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
