# tests/test_dados_processo_persistence.py
"""
Testes para verificar a persistência de dados_processo em GeracaoPeca.

Este módulo verifica que as variáveis extraídas (dados_extracao) são
corretamente salvas na coluna dados_processo para auditoria e debug.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock


class TestDadosProcessoPersistence:
    """Testes de persistência de dados_processo"""

    def test_geracao_peca_aceita_dados_processo(self):
        """Verifica que GeracaoPeca aceita o parâmetro dados_processo"""
        from sistemas.gerador_pecas.models import GeracaoPeca

        dados_extracao = {
            "pareceres_patologia_diversa_incorporada": True,
            "pareceres_medicamento_nao_incorporado_sus": False,
            "valor_causa_inferior_60sm": True
        }

        geracao = GeracaoPeca(
            numero_cnj="1234567890123456789",
            tipo_peca="contestacao",
            dados_processo=dados_extracao
        )

        assert geracao.dados_processo == dados_extracao
        assert geracao.dados_processo["pareceres_patologia_diversa_incorporada"] is True

    def test_geracao_peca_sem_dados_processo(self):
        """Verifica que GeracaoPeca funciona sem dados_processo (None)"""
        from sistemas.gerador_pecas.models import GeracaoPeca

        geracao = GeracaoPeca(
            numero_cnj="1234567890123456789",
            tipo_peca="contestacao"
        )

        assert geracao.dados_processo is None

    def test_consolidar_dados_extracao_funciona(self):
        """Verifica que consolidar_dados_extracao extrai variáveis corretamente"""
        from sistemas.gerador_pecas.orquestrador_agentes import consolidar_dados_extracao
        from sistemas.gerador_pecas.agente_tjms_integrado import ResultadoAgente1

        # Mock do resultado com dados brutos contendo documento com resumo JSON
        mock_documento = Mock()
        mock_documento.resumo = '{"pareceres_patologia_diversa_incorporada": true, "medicamento_nome": "Test"}'
        mock_documento.categoria_nome = "Parecer NAT"

        mock_dados_brutos = Mock()
        mock_dados_brutos.documentos_com_resumo = Mock(return_value=[mock_documento])

        resultado_agente1 = ResultadoAgente1(numero_processo="1234567890123456789")
        resultado_agente1.dados_brutos = mock_dados_brutos

        dados = consolidar_dados_extracao(resultado_agente1)

        assert "pareceres_patologia_diversa_incorporada" in dados
        assert dados["pareceres_patologia_diversa_incorporada"] is True
        assert "medicamento_nome" in dados
        assert dados["medicamento_nome"] == "Test"

    def test_consolidar_dados_com_multiplos_documentos_or_logic(self):
        """Verifica lógica OR para booleanos quando há múltiplos documentos"""
        from sistemas.gerador_pecas.orquestrador_agentes import consolidar_dados_extracao
        from sistemas.gerador_pecas.agente_tjms_integrado import ResultadoAgente1

        # Dois documentos com mesmo campo booleano
        mock_doc1 = Mock()
        mock_doc1.resumo = '{"pareceres_patologia_diversa_incorporada": false}'
        mock_doc1.categoria_nome = "Doc1"

        mock_doc2 = Mock()
        mock_doc2.resumo = '{"pareceres_patologia_diversa_incorporada": true}'
        mock_doc2.categoria_nome = "Doc2"

        mock_dados_brutos = Mock()
        mock_dados_brutos.documentos_com_resumo = Mock(return_value=[mock_doc1, mock_doc2])

        resultado_agente1 = ResultadoAgente1(numero_processo="1234567890123456789")
        resultado_agente1.dados_brutos = mock_dados_brutos

        dados = consolidar_dados_extracao(resultado_agente1)

        # Lógica OR: se algum é True, resultado é True
        assert dados["pareceres_patologia_diversa_incorporada"] is True

    def test_consolidar_dados_sem_dados_brutos(self):
        """Verifica que retorna vazio quando não há dados_brutos"""
        from sistemas.gerador_pecas.orquestrador_agentes import consolidar_dados_extracao
        from sistemas.gerador_pecas.agente_tjms_integrado import ResultadoAgente1

        resultado_agente1 = ResultadoAgente1(numero_processo="1234567890123456789")
        resultado_agente1.dados_brutos = None

        dados = consolidar_dados_extracao(resultado_agente1)

        assert dados == {}


class TestRegraDeterministicaComValoresExtraidos:
    """Testes de integração entre extração e avaliação de regras"""

    def test_regra_or_com_valor_true(self):
        """Verifica que regra OR ativa quando uma variável é true"""
        from sistemas.gerador_pecas.services_deterministic import DeterministicRuleEvaluator

        avaliador = DeterministicRuleEvaluator()

        # Regra OR como no módulo mer_med_nao_inc_tema1234
        regra = {
            "type": "or",
            "conditions": [
                {"type": "condition", "variable": "pareceres_medicamento_nao_incorporado_sus", "operator": "equals", "value": True},
                {"type": "condition", "variable": "pareceres_patologia_diversa_incorporada", "operator": "equals", "value": True},
                {"type": "condition", "variable": "pareceres_dosagem_diversa_incorporada", "operator": "equals", "value": True}
            ]
        }

        # Apenas segunda variável é True
        dados = {
            "pareceres_medicamento_nao_incorporado_sus": False,
            "pareceres_patologia_diversa_incorporada": True,
            "pareceres_dosagem_diversa_incorporada": False
        }

        resultado = avaliador.avaliar(regra, dados)
        assert resultado is True

    def test_regra_or_com_todos_false(self):
        """Verifica que regra OR não ativa quando todas variáveis são false"""
        from sistemas.gerador_pecas.services_deterministic import DeterministicRuleEvaluator

        avaliador = DeterministicRuleEvaluator()

        regra = {
            "type": "or",
            "conditions": [
                {"type": "condition", "variable": "pareceres_medicamento_nao_incorporado_sus", "operator": "equals", "value": True},
                {"type": "condition", "variable": "pareceres_patologia_diversa_incorporada", "operator": "equals", "value": True}
            ]
        }

        dados = {
            "pareceres_medicamento_nao_incorporado_sus": False,
            "pareceres_patologia_diversa_incorporada": False
        }

        resultado = avaliador.avaliar(regra, dados)
        assert resultado is False

    def test_regra_comparacao_1_vs_true(self):
        """Verifica que value=1 na regra é comparado corretamente com True"""
        from sistemas.gerador_pecas.services_deterministic import DeterministicRuleEvaluator

        avaliador = DeterministicRuleEvaluator()

        # Regra com value=1 (formato antigo)
        regra = {
            "type": "condition",
            "variable": "pareceres_patologia_diversa_incorporada",
            "operator": "equals",
            "value": 1
        }

        # Dado extraído como booleano True
        dados = {"pareceres_patologia_diversa_incorporada": True}

        resultado = avaliador.avaliar(regra, dados)
        assert resultado is True

    def test_regra_comparacao_true_vs_true(self):
        """Verifica que value=true na regra é comparado corretamente com True"""
        from sistemas.gerador_pecas.services_deterministic import DeterministicRuleEvaluator

        avaliador = DeterministicRuleEvaluator()

        regra = {
            "type": "condition",
            "variable": "pareceres_patologia_diversa_incorporada",
            "operator": "equals",
            "value": True
        }

        dados = {"pareceres_patologia_diversa_incorporada": True}

        resultado = avaliador.avaliar(regra, dados)
        assert resultado is True


class TestPodeAvaliarRegraOR:
    """Testes para a função pode_avaliar_regra com regras OR"""

    def test_pode_avaliar_or_com_uma_variavel_existente(self):
        """Verifica que pode avaliar OR quando pelo menos uma variável existe"""
        from sistemas.gerador_pecas.services_deterministic import pode_avaliar_regra

        regra = {
            "type": "or",
            "conditions": [
                {"type": "condition", "variable": "var1", "operator": "equals", "value": True},
                {"type": "condition", "variable": "var2", "operator": "equals", "value": True},
                {"type": "condition", "variable": "var3", "operator": "equals", "value": True}
            ]
        }

        # Apenas var2 existe
        dados = {"var2": True}

        pode, existentes, faltantes = pode_avaliar_regra(regra, dados)

        assert pode is True  # Pode avaliar porque var2 existe
        assert "var2" in existentes
        assert "var1" in faltantes
        assert "var3" in faltantes

    def test_nao_pode_avaliar_or_sem_nenhuma_variavel(self):
        """Verifica que não pode avaliar OR quando nenhuma variável existe"""
        from sistemas.gerador_pecas.services_deterministic import pode_avaliar_regra

        regra = {
            "type": "or",
            "conditions": [
                {"type": "condition", "variable": "var1", "operator": "equals", "value": True},
                {"type": "condition", "variable": "var2", "operator": "equals", "value": True}
            ]
        }

        # Nenhuma variável existe
        dados = {}

        pode, existentes, faltantes = pode_avaliar_regra(regra, dados)

        assert pode is False
        assert existentes == []
        assert set(faltantes) == {"var1", "var2"}
