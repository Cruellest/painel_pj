# tests/cumprimento_beta/test_chatbot.py
"""
Testes do chatbot e geração de peças do módulo Cumprimento de Sentença Beta.

Verifica:
- Mensagem do usuário persistida
- Resposta do assistente persistida
- Peça gerada corretamente
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, AsyncMock
import json

from sistemas.cumprimento_beta.constants import RoleChat, MODELO_PADRAO_CHATBOT


class TestChatbotService:
    """Testes para serviço de chatbot"""

    def test_montar_contexto_processo_com_consolidacao(self):
        """Deve montar contexto corretamente quando há consolidação"""
        from sistemas.cumprimento_beta.services_chatbot import ChatbotService

        mock_db = Mock()

        # Mock da consolidação
        consolidacao = Mock()
        consolidacao.resumo_consolidado = "Este é o resumo do processo..."
        consolidacao.dados_processo = {
            "exequente": "João Silva",
            "executado": "Estado de MS",
            "valor_execucao": "R$ 50.000,00"
        }
        consolidacao.sugestoes_pecas = [
            {"tipo": "Impugnação", "descricao": "Contestar valores"}
        ]

        mock_db.query.return_value.filter.return_value.first.return_value = consolidacao

        service = ChatbotService.__new__(ChatbotService)
        service.db = mock_db

        sessao = Mock()
        sessao.id = 1
        sessao.numero_processo = "00012345620208120001"
        sessao.numero_processo_formatado = "0001234-56.2020.8.12.0001"

        contexto = service._montar_contexto_processo(sessao)

        assert "0001234-56.2020.8.12.0001" in contexto
        assert "João Silva" in contexto
        assert "Estado de MS" in contexto
        assert "R$ 50.000,00" in contexto

    def test_montar_historico_limita_mensagens(self):
        """Deve limitar quantidade de mensagens no histórico"""
        from sistemas.cumprimento_beta.services_chatbot import ChatbotService
        from sistemas.cumprimento_beta.constants import MAX_MENSAGENS_CONTEXTO

        mock_db = Mock()

        # Cria mais mensagens do que o limite
        mensagens = [Mock() for _ in range(MAX_MENSAGENS_CONTEXTO + 10)]
        for i, m in enumerate(mensagens):
            m.role = "user" if i % 2 == 0 else "assistant"
            m.conteudo = f"Mensagem {i}"

        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = mensagens[:MAX_MENSAGENS_CONTEXTO]

        service = ChatbotService.__new__(ChatbotService)
        service.db = mock_db

        sessao = Mock()
        sessao.id = 1

        historico = service._montar_historico(sessao)

        # Deve ter no máximo MAX_MENSAGENS_CONTEXTO
        assert len(historico) <= MAX_MENSAGENS_CONTEXTO

    def test_salvar_mensagem_usuario(self):
        """Deve salvar mensagem do usuário corretamente"""
        from sistemas.cumprimento_beta.services_chatbot import ChatbotService

        mock_db = Mock()
        mock_db.add = Mock()
        mock_db.commit = Mock()
        mock_db.refresh = Mock()

        service = ChatbotService.__new__(ChatbotService)
        service.db = mock_db

        mensagem = service._salvar_mensagem(
            sessao_id=1,
            role=RoleChat.USER,
            conteudo="Olá, preciso de ajuda"
        )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    def test_salvar_mensagem_assistente_com_modelo(self):
        """Deve salvar mensagem do assistente com informações do modelo"""
        from sistemas.cumprimento_beta.services_chatbot import ChatbotService

        mock_db = Mock()
        mock_db.add = Mock()
        mock_db.commit = Mock()
        mock_db.refresh = Mock()

        service = ChatbotService.__new__(ChatbotService)
        service.db = mock_db

        mensagem = service._salvar_mensagem(
            sessao_id=1,
            role=RoleChat.ASSISTANT,
            conteudo="Posso ajudar com o cumprimento...",
            modelo="gemini-1.5-pro",
            usou_busca=True,
            argumentos=[10, 20, 30]
        )

        mock_db.add.assert_called_once()
        # Verifica que foi chamado com os parâmetros corretos
        call_args = mock_db.add.call_args[0][0]
        assert call_args.role == RoleChat.ASSISTANT
        assert call_args.modelo_usado == "gemini-1.5-pro"
        assert call_args.usou_busca_vetorial == True


class TestGeracaoPeca:
    """Testes para geração de peças jurídicas"""

    def test_gerar_titulo_peca(self):
        """Deve gerar título formatado corretamente"""
        from sistemas.cumprimento_beta.services_geracao_peca import GeracaoPecaService

        service = GeracaoPecaService.__new__(GeracaoPecaService)

        titulo = service._gerar_titulo("impugnação ao cumprimento", "00012345620208120001")

        assert "IMPUGNAÇÃO AO CUMPRIMENTO" in titulo
        assert "00012345620208120001" in titulo

    def test_montar_resumo_com_consolidacao(self):
        """Deve montar resumo do processo a partir da consolidação"""
        from sistemas.cumprimento_beta.services_geracao_peca import GeracaoPecaService

        mock_db = Mock()

        consolidacao = Mock()
        consolidacao.resumo_consolidado = "O processo trata de execução de valores..."

        mock_db.query.return_value.filter.return_value.first.return_value = consolidacao

        service = GeracaoPecaService.__new__(GeracaoPecaService)
        service.db = mock_db

        sessao = Mock()
        sessao.id = 1

        resumo = service._montar_resumo_processo(sessao)

        assert resumo == "O processo trata de execução de valores..."

    def test_montar_resumo_sem_consolidacao(self):
        """Deve retornar mensagem padrão quando não há consolidação"""
        from sistemas.cumprimento_beta.services_geracao_peca import GeracaoPecaService

        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        service = GeracaoPecaService.__new__(GeracaoPecaService)
        service.db = mock_db

        sessao = Mock()
        sessao.id = 1

        resumo = service._montar_resumo_processo(sessao)

        assert "não disponíveis" in resumo.lower()


class TestModeloChatbot:
    """Testes para configuração de modelo do chatbot"""

    def test_modelo_carregado_do_admin(self):
        """Modelo deve ser carregado da configuração do admin"""
        from sistemas.cumprimento_beta.services_chatbot import ChatbotService

        mock_db = Mock()
        mock_config = Mock()
        mock_config.valor = "gemini-2.0-pro"

        mock_db.query.return_value.filter.return_value.first.return_value = mock_config

        service = ChatbotService.__new__(ChatbotService)
        service.db = mock_db

        modelo = service._carregar_modelo()

        assert modelo == "gemini-2.0-pro"

    def test_modelo_padrao_quando_nao_configurado(self):
        """Deve usar modelo padrão quando não configurado"""
        from sistemas.cumprimento_beta.services_chatbot import ChatbotService

        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        service = ChatbotService.__new__(ChatbotService)
        service.db = mock_db

        modelo = service._carregar_modelo()

        assert modelo == MODELO_PADRAO_CHATBOT


class TestHistoricoChat:
    """Testes para histórico de conversas"""

    def test_obter_historico_ordenado(self):
        """Histórico deve vir ordenado cronologicamente"""
        from sistemas.cumprimento_beta.services_chatbot import obter_historico_chat

        mock_db = Mock()

        mensagens = [
            Mock(id=1, role="user", conteudo="Olá"),
            Mock(id=2, role="assistant", conteudo="Oi!"),
            Mock(id=3, role="user", conteudo="Ajuda"),
        ]

        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = mensagens

        historico = obter_historico_chat(mock_db, sessao_id=1)

        assert len(historico) == 3
        assert historico[0].id == 1
        assert historico[2].id == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
