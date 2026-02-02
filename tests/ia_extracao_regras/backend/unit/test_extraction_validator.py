# tests/ia_extracao_regras/backend/unit/test_extraction_validator.py
"""
Testes para o validador de extração de variáveis.

Testa correção de inconsistências óbvias como:
- Responsabilização pessoal vs genérica
- Equipamentos/medicamentos/cirurgia/exames
"""

import unittest
from sistemas.gerador_pecas.services_extraction_validator import (
    ExtractionValidator,
    validar_extracao,
)


class TestResponsabilizacaoPessoal(unittest.TestCase):
    """Testes para validação de responsabilização pessoal de agente."""

    def setUp(self):
        self.validator = ExtractionValidator(auto_corrigir=True, log_alertas=False)

    def test_responsabilizacao_generica_nao_e_pessoal(self):
        """
        Caso real: processo 08009221020258120038
        "sob pena de bloqueio de verbas públicas e responsabilização"
        NÃO é responsabilização pessoal (sem citar agente).
        """
        dados = {
            'decisoes_responsabilizacao_pessoal_agente': True,  # Extraído incorretamente
        }

        texto = (
            "Fornecimento do medicamento pelo Município e Estado, "
            "sob pena de bloqueio de verbas públicas e responsabilização."
        )

        dados_corrigidos, alertas = self.validator.validar(dados, texto_pedidos=texto)

        # Deve corrigir para False
        self.assertFalse(
            dados_corrigidos['decisoes_responsabilizacao_pessoal_agente'],
            "Responsabilização genérica não deve ser marcada como pessoal"
        )

        # Deve gerar alerta
        self.assertEqual(len(alertas), 1)
        self.assertIn("responsabilização genérica", alertas[0])

    def test_responsabilizacao_do_ente_nao_e_pessoal(self):
        """Responsabilização do Estado/Município não é pessoal."""
        dados = {
            'decisoes_responsabilizacao_pessoal_agente': True,
        }

        texto = "Determino a responsabilização do Estado em caso de descumprimento."

        dados_corrigidos, _ = self.validator.validar(dados, texto_pedidos=texto)

        self.assertFalse(dados_corrigidos['decisoes_responsabilizacao_pessoal_agente'])

    def test_responsabilizacao_com_bloqueio_nao_e_pessoal(self):
        """Bloqueio de verbas + responsabilização genérica não é pessoal."""
        dados = {
            'decisoes_responsabilizacao_pessoal_agente': True,
        }

        texto = (
            "sob pena de sequestro de verbas públicas e responsabilização "
            "da Fazenda Pública Municipal."
        )

        dados_corrigidos, _ = self.validator.validar(dados, texto_pedidos=texto)

        self.assertFalse(dados_corrigidos['decisoes_responsabilizacao_pessoal_agente'])

    def test_responsabilizacao_do_prefeito_e_pessoal(self):
        """Responsabilização do prefeito É pessoal."""
        dados = {
            'decisoes_responsabilizacao_pessoal_agente': True,
        }

        texto = (
            "Determino o fornecimento do medicamento, "
            "sob pena de responsabilização pessoal do prefeito."
        )

        dados_corrigidos, alertas = self.validator.validar(dados, texto_pedidos=texto)

        # Deve MANTER True (está correto)
        self.assertTrue(dados_corrigidos['decisoes_responsabilizacao_pessoal_agente'])

        # NÃO deve gerar alerta
        self.assertEqual(len(alertas), 0)

    def test_responsabilizacao_do_secretario_e_pessoal(self):
        """Responsabilização do secretário É pessoal."""
        dados = {
            'decisoes_responsabilizacao_pessoal_agente': True,
        }

        texto = "Responsabilizo o Secretário Municipal de Saúde pelo descumprimento."

        dados_corrigidos, alertas = self.validator.validar(dados, texto_pedidos=texto)

        # Deve MANTER True
        self.assertTrue(dados_corrigidos['decisoes_responsabilizacao_pessoal_agente'])
        self.assertEqual(len(alertas), 0)

    def test_agente_publico_citado_e_pessoal(self):
        """Citação de agente público É responsabilização pessoal."""
        dados = {
            'decisoes_responsabilizacao_pessoal_agente': True,
        }

        texto = "O agente público será responsabilizado em caso de omissão."

        dados_corrigidos, alertas = self.validator.validar(dados, texto_pedidos=texto)

        # Deve MANTER True
        self.assertTrue(dados_corrigidos['decisoes_responsabilizacao_pessoal_agente'])
        self.assertEqual(len(alertas), 0)

    def test_false_nao_e_alterado(self):
        """Se a variável já está False, não deve alterar."""
        dados = {
            'decisoes_responsabilizacao_pessoal_agente': False,
        }

        texto = "Responsabilização genérica do município."

        dados_corrigidos, alertas = self.validator.validar(dados, texto_pedidos=texto)

        # Deve MANTER False
        self.assertFalse(dados_corrigidos['decisoes_responsabilizacao_pessoal_agente'])
        self.assertEqual(len(alertas), 0)


class TestFuncaoUtilitaria(unittest.TestCase):
    """Testa função utilitária validar_extracao."""

    def test_validar_extracao_corrige_automaticamente(self):
        """Função utilitária deve corrigir por padrão."""
        dados = {
            'decisoes_responsabilizacao_pessoal_agente': True,
        }

        texto = "bloqueio de verbas e responsabilização do Estado"

        dados_corrigidos = validar_extracao(dados, texto, auto_corrigir=True)

        self.assertFalse(dados_corrigidos['decisoes_responsabilizacao_pessoal_agente'])

    def test_validar_extracao_sem_correcao(self):
        """Função pode não corrigir se auto_corrigir=False."""
        dados = {
            'decisoes_responsabilizacao_pessoal_agente': True,
        }

        texto = "bloqueio de verbas e responsabilização do Estado"

        dados_corrigidos = validar_extracao(dados, texto, auto_corrigir=False)

        # Não deve ter corrigido
        self.assertTrue(dados_corrigidos['decisoes_responsabilizacao_pessoal_agente'])


if __name__ == "__main__":
    unittest.main()
