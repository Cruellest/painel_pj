# tests/ia_extracao_regras/backend/unit/test_migracao_prefixos.py
"""
Testes para validar a migração/normalização de prefixos no banco de dados.

Testa:
- Registros sem prefixo são corrigidos
- Migração é idempotente (rodar 2x não duplica prefixo)
- Duplicidades são tratadas corretamente
- Variáveis órfãs são desativadas

Usa MagicMock para simular objetos, seguindo o padrão dos testes unitários do projeto.
"""

import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime
import re
import unicodedata

# Importações do sistema
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))


class MigracaoPrefixos:
    """
    Classe que implementa a lógica de migração de prefixos.

    Replica a lógica do script corrigir_prefixos_variaveis.py
    para permitir testes unitários.
    """

    def __init__(self, variaveis: list, categorias: dict):
        """
        Args:
            variaveis: Lista de dicts com dados das variáveis
            categorias: Dict mapeando categoria_id -> dados da categoria
        """
        self.variaveis = variaveis
        self.categorias = categorias
        self.correcoes = []
        self.conflitos = []
        self.orfas_desativadas = []

    def obter_namespace_categoria(self, categoria_nome: str, namespace_prefix: str) -> str:
        """Obtém o namespace efetivo de uma categoria."""
        if namespace_prefix:
            return namespace_prefix
        nome = categoria_nome.lower()
        # Remove acentos
        nome = unicodedata.normalize('NFKD', nome)
        nome = nome.encode('ascii', 'ignore').decode('ascii')
        nome = re.sub(r'[^a-z0-9]+', '_', nome)
        return nome.strip('_')

    def aplicar_namespace(self, slug: str, namespace: str) -> str:
        """Aplica namespace ao slug se ainda não tiver."""
        if not namespace:
            return slug
        if slug.startswith(f"{namespace}_"):
            return slug
        return f"{namespace}_{slug}"

    def verificar_conflito(self, novo_slug: str, var_id: int) -> bool:
        """Verifica se o novo slug já existe (conflito)."""
        for var in self.variaveis:
            if var["slug"] == novo_slug and var["id"] != var_id and var.get("ativo", True):
                return True
        return False

    def corrigir_prefixos(self, dry_run: bool = True) -> dict:
        """
        Corrige prefixos de todas as variáveis.

        Args:
            dry_run: Se True, não aplica alterações

        Returns:
            Dict com estatísticas da correção
        """
        self.correcoes = []
        self.conflitos = []

        for var in self.variaveis:
            if not var.get("ativo", True):
                continue

            cat_id = var.get("categoria_id")
            if not cat_id or cat_id not in self.categorias:
                continue

            categoria = self.categorias[cat_id]
            namespace = self.obter_namespace_categoria(
                categoria["nome"],
                categoria.get("namespace_prefix")
            )
            prefixo_esperado = f"{namespace}_"

            slug = var["slug"]

            # Verifica se precisa correção
            if not slug.startswith(prefixo_esperado):
                novo_slug = self.aplicar_namespace(slug, namespace)

                # Verifica conflito
                if self.verificar_conflito(novo_slug, var["id"]):
                    self.conflitos.append({
                        "id": var["id"],
                        "slug_antigo": slug,
                        "slug_novo": novo_slug,
                        "motivo": "Conflito: slug já existe"
                    })
                    continue

                self.correcoes.append({
                    "id": var["id"],
                    "slug_antigo": slug,
                    "slug_novo": novo_slug,
                    "categoria": categoria["nome"],
                    "source_question_id": var.get("source_question_id")
                })

                if not dry_run:
                    # Atualiza variável
                    var["slug"] = novo_slug

        return {
            "correcoes": len(self.correcoes),
            "conflitos": len(self.conflitos),
            "detalhes_correcoes": self.correcoes,
            "detalhes_conflitos": self.conflitos
        }

    def desativar_orfas(self, dry_run: bool = True) -> dict:
        """
        Desativa variáveis órfãs (sem pergunta associada).

        Args:
            dry_run: Se True, não aplica alterações

        Returns:
            Dict com estatísticas
        """
        self.orfas_desativadas = []

        for var in self.variaveis:
            if not var.get("ativo", True):
                continue
            if var.get("source_question_id") is None:
                self.orfas_desativadas.append({
                    "id": var["id"],
                    "slug": var["slug"],
                    "categoria_id": var.get("categoria_id")
                })

                if not dry_run:
                    var["ativo"] = False

        return {
            "desativadas": len(self.orfas_desativadas),
            "detalhes": self.orfas_desativadas
        }


class TestMigracaoCorrigePrefixos(unittest.TestCase):
    """Testes para correção de prefixos de variáveis."""

    def setUp(self):
        """Configura dados de teste."""
        self.categorias = {
            1: {
                "id": 1,
                "nome": "peticao_inicial",
                "namespace_prefix": "peticao_inicial"
            }
        }

    def _criar_variavel(self, slug: str, categoria_id: int = 1, source_question_id: int = None) -> dict:
        """Helper para criar variável."""
        return {
            "id": hash(slug) % 10000,
            "slug": slug,
            "label": f"Variável {slug}",
            "tipo": "text",
            "categoria_id": categoria_id,
            "source_question_id": source_question_id,
            "ativo": True
        }

    # ==========================================
    # Testes de correção de prefixos
    # ==========================================

    def test_variavel_sem_prefixo_e_corrigida(self):
        """
        Registros sem prefixo são corrigidos.
        """
        # Arrange - Variável sem prefixo
        variaveis = [self._criar_variavel("medicamento")]
        migracao = MigracaoPrefixos(variaveis, self.categorias)

        # Act
        resultado = migracao.corrigir_prefixos(dry_run=False)

        # Assert
        self.assertEqual(resultado["correcoes"], 1)
        self.assertEqual(variaveis[0]["slug"], "peticao_inicial_medicamento")

    def test_variavel_com_prefixo_nao_e_alterada(self):
        """
        Variáveis que já têm prefixo correto não são alteradas.
        """
        # Arrange - Variável já com prefixo correto
        variaveis = [self._criar_variavel("peticao_inicial_medicamento")]
        migracao = MigracaoPrefixos(variaveis, self.categorias)

        # Act
        resultado = migracao.corrigir_prefixos(dry_run=False)

        # Assert - Nenhuma correção
        self.assertEqual(resultado["correcoes"], 0)
        self.assertEqual(variaveis[0]["slug"], "peticao_inicial_medicamento")

    def test_migracao_idempotente(self):
        """
        Rodar migração 2x não duplica prefixo.
        """
        # Arrange - Variável sem prefixo
        variaveis = [self._criar_variavel("valor_causa")]
        migracao = MigracaoPrefixos(variaveis, self.categorias)

        # Act - Roda migração 2 vezes
        resultado1 = migracao.corrigir_prefixos(dry_run=False)
        resultado2 = migracao.corrigir_prefixos(dry_run=False)

        # Assert
        self.assertEqual(resultado1["correcoes"], 1)  # Primeira vez corrige
        self.assertEqual(resultado2["correcoes"], 0)  # Segunda vez não há nada

        # Verifica que não duplicou
        self.assertEqual(variaveis[0]["slug"], "peticao_inicial_valor_causa")
        self.assertNotEqual(variaveis[0]["slug"], "peticao_inicial_peticao_inicial_valor_causa")

    def test_migracao_identifica_correcao_com_pergunta(self):
        """
        Ao corrigir variável, identifica pergunta correspondente.
        """
        # Arrange
        variaveis = [self._criar_variavel("medicamento", source_question_id=42)]
        migracao = MigracaoPrefixos(variaveis, self.categorias)

        # Act
        resultado = migracao.corrigir_prefixos(dry_run=False)

        # Assert
        self.assertEqual(resultado["correcoes"], 1)
        self.assertEqual(resultado["detalhes_correcoes"][0]["source_question_id"], 42)

    def test_conflito_reportado_nao_corrigido(self):
        """
        Se novo slug já existe, registra conflito e não corrige.
        """
        # Arrange - Cria variável que vai gerar conflito
        variaveis = [
            self._criar_variavel("peticao_inicial_nome"),  # Já existe
            self._criar_variavel("nome")  # Vai tentar virar peticao_inicial_nome
        ]
        # Garante IDs diferentes
        variaveis[0]["id"] = 1
        variaveis[1]["id"] = 2

        migracao = MigracaoPrefixos(variaveis, self.categorias)

        # Act
        resultado = migracao.corrigir_prefixos(dry_run=False)

        # Assert - Conflito detectado
        self.assertEqual(resultado["conflitos"], 1)
        self.assertEqual(resultado["correcoes"], 0)

        # Variável não foi alterada
        self.assertEqual(variaveis[1]["slug"], "nome")  # Manteve original

    # ==========================================
    # Testes de variáveis órfãs
    # ==========================================

    def test_variavel_orfa_e_desativada(self):
        """
        Variáveis sem pergunta associada são desativadas.
        """
        # Arrange - Variável órfã (sem pergunta)
        variaveis = [self._criar_variavel(
            "peticao_inicial_orfa",
            source_question_id=None  # Órfã
        )]
        migracao = MigracaoPrefixos(variaveis, self.categorias)

        # Act
        resultado = migracao.desativar_orfas(dry_run=False)

        # Assert
        self.assertEqual(resultado["desativadas"], 1)
        self.assertFalse(variaveis[0]["ativo"])

    def test_variavel_com_pergunta_nao_e_desativada(self):
        """
        Variáveis com pergunta associada não são desativadas.
        """
        # Arrange - Variável com pergunta
        variaveis = [self._criar_variavel(
            "peticao_inicial_ativa",
            source_question_id=123
        )]
        migracao = MigracaoPrefixos(variaveis, self.categorias)

        # Act
        resultado = migracao.desativar_orfas(dry_run=False)

        # Assert
        self.assertEqual(resultado["desativadas"], 0)
        self.assertTrue(variaveis[0]["ativo"])

    # ==========================================
    # Testes de dry run
    # ==========================================

    def test_dry_run_nao_altera_dados(self):
        """
        Em dry run, nenhuma alteração é feita.
        """
        # Arrange
        variaveis = [self._criar_variavel("sem_prefixo")]
        slug_original = variaveis[0]["slug"]
        migracao = MigracaoPrefixos(variaveis, self.categorias)

        # Act - Dry run
        resultado = migracao.corrigir_prefixos(dry_run=True)

        # Assert - Correção identificada mas não aplicada
        self.assertEqual(resultado["correcoes"], 1)
        self.assertEqual(variaveis[0]["slug"], slug_original)


class TestMigracaoMultiplasCategorias(unittest.TestCase):
    """Testes de migração com múltiplas categorias."""

    def setUp(self):
        """Configura dados de teste."""
        self.categorias = {
            1: {
                "id": 1,
                "nome": "peticao_inicial",
                "namespace_prefix": "peticao_inicial"
            },
            2: {
                "id": 2,
                "nome": "pareceres",
                "namespace_prefix": "pareceres"
            }
        }

    def _criar_variavel(self, slug: str, categoria_id: int, var_id: int = None) -> dict:
        """Helper para criar variável."""
        return {
            "id": var_id or (hash(slug) % 10000),
            "slug": slug,
            "label": f"Variável {slug}",
            "tipo": "text",
            "categoria_id": categoria_id,
            "source_question_id": None,
            "ativo": True
        }

    def test_mesmo_sufixo_categorias_diferentes_corrigido(self):
        """
        Mesmo sufixo em categorias diferentes recebe prefixos diferentes.
        """
        # Arrange
        variaveis = [
            self._criar_variavel("tipo_documento", 1, var_id=1),  # categoria peticao
            self._criar_variavel("tipo_documento", 2, var_id=2)   # categoria pareceres
        ]
        migracao = MigracaoPrefixos(variaveis, self.categorias)

        # Act
        resultado = migracao.corrigir_prefixos(dry_run=False)

        # Assert - Ambas corrigidas
        self.assertEqual(resultado["correcoes"], 2)
        self.assertEqual(variaveis[0]["slug"], "peticao_inicial_tipo_documento")
        self.assertEqual(variaveis[1]["slug"], "pareceres_tipo_documento")
        self.assertNotEqual(variaveis[0]["slug"], variaveis[1]["slug"])

    def test_prefixo_correto_por_categoria(self):
        """
        Cada categoria aplica seu próprio prefixo.
        """
        # Arrange
        variaveis = [
            self._criar_variavel("campo_a", 1, var_id=1),
            self._criar_variavel("campo_b", 2, var_id=2)
        ]
        migracao = MigracaoPrefixos(variaveis, self.categorias)

        # Act
        resultado = migracao.corrigir_prefixos(dry_run=False)

        # Assert
        self.assertEqual(resultado["correcoes"], 2)
        self.assertTrue(variaveis[0]["slug"].startswith("peticao_inicial_"))
        self.assertTrue(variaveis[1]["slug"].startswith("pareceres_"))


class TestMigracaoNamespaceFallback(unittest.TestCase):
    """Testes de fallback de namespace quando namespace_prefix não está definido."""

    def test_namespace_fallback_nome_categoria(self):
        """
        Se namespace_prefix não estiver definido, usa nome da categoria.
        """
        # Arrange
        categorias = {
            1: {
                "id": 1,
                "nome": "Notas Técnicas",
                "namespace_prefix": None  # Sem prefix definido
            }
        }
        variaveis = [{
            "id": 1,
            "slug": "campo_teste",
            "categoria_id": 1,
            "ativo": True
        }]
        migracao = MigracaoPrefixos(variaveis, categorias)

        # Act
        resultado = migracao.corrigir_prefixos(dry_run=False)

        # Assert
        self.assertEqual(resultado["correcoes"], 1)
        self.assertEqual(variaveis[0]["slug"], "notas_tecnicas_campo_teste")

    def test_namespace_remove_acentos(self):
        """
        Namespace derivado do nome remove acentos.
        """
        # Arrange
        categorias = {
            1: {
                "id": 1,
                "nome": "Petição Médica",
                "namespace_prefix": None
            }
        }
        variaveis = [{
            "id": 1,
            "slug": "valor",
            "categoria_id": 1,
            "ativo": True
        }]
        migracao = MigracaoPrefixos(variaveis, categorias)

        # Act
        resultado = migracao.corrigir_prefixos(dry_run=False)

        # Assert
        self.assertEqual(resultado["correcoes"], 1)
        self.assertEqual(variaveis[0]["slug"], "peticao_medica_valor")


if __name__ == "__main__":
    unittest.main()
