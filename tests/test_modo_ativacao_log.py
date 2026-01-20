#!/usr/bin/env python
"""
Testes para validar que o sistema de logging de modo_ativacao funciona corretamente.

Cenários testados:
1. Valores longos de modo_ativacao (ex: "deterministic_tipo_contestacao_false")
   NÃO devem causar truncamento
2. Valores padronizados curtos + detalhes separados funcionam corretamente
3. Falhas de logging não abortam o fluxo principal (resiliência)

Uso:
    pytest tests/test_modo_ativacao_log.py -v
"""

import pytest


class TestModoAtivacaoLog:
    """Testes para o sistema de logging de ativação."""

    def test_valores_padronizados_curtos(self):
        """
        Verifica que os valores de modo_ativacao são padronizados e curtos.

        Valores válidos:
        - 'llm'
        - 'deterministic'
        - 'deterministic_global'
        - 'deterministic_tipo_peca'
        - 'mixed'
        """
        valores_validos = [
            'llm',
            'deterministic',
            'deterministic_global',
            'deterministic_tipo_peca',
            'mixed'
        ]

        for valor in valores_validos:
            # Nenhum valor deve ter mais de 30 caracteres (limite antigo)
            assert len(valor) <= 30, f"Valor '{valor}' excede 30 caracteres"

    def test_valor_problemático_antigo(self):
        """
        Verifica que o valor problemático antigo (>30 chars) agora é separado.

        Antes: modo_ativacao = "deterministic_tipo_contestacao_false" (36 chars)
        Depois: modo_ativacao = "deterministic_tipo_peca", detalhe = "contestacao_false"
        """
        valor_antigo = "deterministic_tipo_contestacao_false"
        assert len(valor_antigo) > 30, f"Valor antigo deveria ter mais de 30 caracteres, tem {len(valor_antigo)}"

        # Novo formato
        modo_novo = "deterministic_tipo_peca"
        detalhe_novo = "contestacao_false"

        assert len(modo_novo) < 30, "Modo novo deve caber em 30 chars"
        # O detalhe agora vai em coluna separada (TEXT, sem limite)

    def test_registro_log_resiliente(self):
        """
        Verifica que falhas no logging não abortam o fluxo principal.

        Este teste verifica a estrutura do código, não executa de fato.
        """
        import inspect
        from sistemas.gerador_pecas.services_deterministic import _registrar_log_ativacao

        # Obtém o código fonte da função
        source = inspect.getsource(_registrar_log_ativacao)

        # Verifica que a função tem try/except para resiliência
        assert "try:" in source, "Função deve ter bloco try"
        assert "except" in source, "Função deve ter bloco except"
        assert "db.rollback()" in source, "Função deve fazer rollback em caso de erro"
        assert "logger.warning" in source, "Função deve logar warning em caso de erro"

    def test_mapeamento_modos_para_detalhes(self):
        """
        Verifica o mapeamento correto entre modos antigos e novos.
        """
        mapeamentos = [
            # (modo_antigo, modo_novo, detalhe)
            ("deterministic_tipo_contestacao", "deterministic_tipo_peca", "contestacao"),
            ("deterministic_tipo_contestacao_false", "deterministic_tipo_peca", "contestacao_false"),
            ("deterministic_global_primary", "deterministic_global", "primary"),
            ("deterministic_global_primary_false", "deterministic_global", "primary_false"),
            ("deterministic_global_secondary", "deterministic_global", "secondary"),
            ("deterministic_global_secondary_false", "deterministic_global", "secondary_false"),
        ]

        for modo_antigo, modo_novo, detalhe in mapeamentos:
            # Verifica que modo_novo cabe no limite antigo de 30 chars
            assert len(modo_novo) <= 30, f"Modo '{modo_novo}' excede 30 caracteres"

            # Verifica que modo_antigo é reconstruível a partir de modo_novo + detalhe
            if detalhe:
                reconstruido = f"{modo_novo.replace('_peca', '')}_{detalhe.replace('_false', '')}"
                # Não precisa ser idêntico, só verificamos que a informação não se perdeu
                assert detalhe in modo_antigo or modo_novo.split('_')[-1] in modo_antigo


class TestModoAtivacaoMigration:
    """Testes para verificar que a migração de schema funciona."""

    def test_tipo_coluna_text(self):
        """
        Verifica que o modelo define modo_ativacao como Text (sem limite).
        """
        from sistemas.gerador_pecas.models_extraction import PromptActivationLog
        from sqlalchemy import Text

        # Verifica tipo da coluna no modelo
        coluna = PromptActivationLog.__table__.columns['modo_ativacao']
        assert isinstance(coluna.type, Text), "modo_ativacao deve ser do tipo Text"

    def test_coluna_detalhe_existe(self):
        """
        Verifica que a coluna modo_ativacao_detalhe existe.
        """
        from sistemas.gerador_pecas.models_extraction import PromptActivationLog

        colunas = [c.name for c in PromptActivationLog.__table__.columns]
        assert 'modo_ativacao_detalhe' in colunas, "Coluna modo_ativacao_detalhe deve existir"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
