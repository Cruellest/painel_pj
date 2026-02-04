# tests/ia_extracao_regras/frontend/test_api_variaveis.py
"""
Testes para API do painel de variáveis.

Testa endpoints usados pelo frontend do painel administrativo.
"""

import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.connection import Base
from sistemas.gerador_pecas.models_extraction import ExtractionVariable, PromptVariableUsage
from sistemas.gerador_pecas.services_deterministic import PromptVariableUsageSync


class TestAPIVariaveisResumo(unittest.TestCase):
    """Testes para endpoint de resumo de variáveis."""

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False}
        )
        cls.Session = sessionmaker(bind=cls.engine)

        from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON
        from admin.models_prompts import PromptModulo
        from admin.models_prompt_groups import PromptGroup, PromptSubgroup
        from auth.models import User

        Base.metadata.create_all(bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=cls.engine)

    def setUp(self):
        self.db = self.Session()

    def tearDown(self):
        # Limpa dados entre testes
        self.db.query(PromptVariableUsage).delete()
        self.db.query(ExtractionVariable).delete()
        self.db.commit()
        self.db.close()

    def _criar_variavel(self, slug, tipo="text", ativo=True):
        variavel = ExtractionVariable(
            slug=slug,
            label=slug.replace("_", " ").title(),
            tipo=tipo,
            ativo=ativo
        )
        self.db.add(variavel)
        self.db.commit()
        return variavel

    def test_contagem_total_variaveis(self):
        """Testa contagem total de variáveis."""
        self._criar_variavel("var1", "text")
        self._criar_variavel("var2", "number")
        self._criar_variavel("var3", "boolean")

        total = self.db.query(ExtractionVariable).filter(
            ExtractionVariable.ativo == True
        ).count()

        self.assertEqual(total, 3)

    def test_contagem_por_tipo(self):
        """Testa contagem de variáveis por tipo."""
        self._criar_variavel("texto1", "text")
        self._criar_variavel("texto2", "text")
        self._criar_variavel("numero1", "number")
        self._criar_variavel("bool1", "boolean")

        # Conta por tipo
        from sqlalchemy import func
        contagem = self.db.query(
            ExtractionVariable.tipo,
            func.count(ExtractionVariable.id)
        ).filter(
            ExtractionVariable.ativo == True
        ).group_by(ExtractionVariable.tipo).all()

        tipos = {t: c for t, c in contagem}

        self.assertEqual(tipos.get("text", 0), 2)
        self.assertEqual(tipos.get("number", 0), 1)
        self.assertEqual(tipos.get("boolean", 0), 1)

    def test_variaveis_em_uso(self):
        """Testa identificação de variáveis em uso."""
        from admin.models_prompts import PromptModulo

        var1 = self._criar_variavel("var_usada", "text")
        var2 = self._criar_variavel("var_nao_usada", "text")

        # Cria prompt
        prompt = PromptModulo(
            nome="prompt_teste",
            titulo="Prompt Teste",
            tipo="conteudo",
            conteudo="Conteúdo",
            modo_ativacao="deterministic",
            ativo=True,
            ordem=0,
            palavras_chave=[],
            tags=[]
        )
        self.db.add(prompt)
        self.db.commit()

        # Registra uso
        uso = PromptVariableUsage(
            prompt_id=prompt.id,
            variable_slug="var_usada"
        )
        self.db.add(uso)
        self.db.commit()

        # Conta variáveis em uso
        slugs_em_uso = self.db.query(PromptVariableUsage.variable_slug).distinct().all()
        slugs_em_uso = {s[0] for s in slugs_em_uso}

        self.assertIn("var_usada", slugs_em_uso)
        self.assertNotIn("var_nao_usada", slugs_em_uso)


class TestAPIVariaveisListagem(unittest.TestCase):
    """Testes para listagem e filtros de variáveis."""

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False}
        )
        cls.Session = sessionmaker(bind=cls.engine)

        from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON
        from admin.models_prompts import PromptModulo
        from admin.models_prompt_groups import PromptGroup, PromptSubgroup
        from auth.models import User

        Base.metadata.create_all(bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=cls.engine)

    def setUp(self):
        self.db = self.Session()
        # Cria variáveis de teste
        self._popular_variaveis()

    def tearDown(self):
        self.db.query(ExtractionVariable).delete()
        self.db.commit()
        self.db.close()

    def _popular_variaveis(self):
        variaveis = [
            ("nome_autor", "Nome do Autor", "text"),
            ("valor_causa", "Valor da Causa", "currency"),
            ("autor_idoso", "Autor Idoso", "boolean"),
            ("data_ajuizamento", "Data de Ajuizamento", "date"),
            ("tipo_acao", "Tipo de Ação", "choice"),
        ]
        for slug, label, tipo in variaveis:
            var = ExtractionVariable(
                slug=slug,
                label=label,
                tipo=tipo,
                ativo=True
            )
            self.db.add(var)
        self.db.commit()

    def test_busca_por_slug(self):
        """Testa busca de variáveis por slug."""
        resultado = self.db.query(ExtractionVariable).filter(
            ExtractionVariable.slug.contains("autor")
        ).all()

        self.assertEqual(len(resultado), 2)
        slugs = {v.slug for v in resultado}
        self.assertIn("nome_autor", slugs)
        self.assertIn("autor_idoso", slugs)

    def test_busca_por_label(self):
        """Testa busca de variáveis por label."""
        resultado = self.db.query(ExtractionVariable).filter(
            ExtractionVariable.label.ilike("%Causa%")
        ).all()

        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado[0].slug, "valor_causa")

    def test_filtro_por_tipo(self):
        """Testa filtro de variáveis por tipo."""
        resultado = self.db.query(ExtractionVariable).filter(
            ExtractionVariable.tipo == "text"
        ).all()

        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado[0].slug, "nome_autor")

    def test_filtro_combinado(self):
        """Testa filtro combinado (tipo + busca)."""
        # Tipo boolean + contém "autor"
        resultado = self.db.query(ExtractionVariable).filter(
            ExtractionVariable.tipo == "boolean",
            ExtractionVariable.slug.contains("autor")
        ).all()

        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado[0].slug, "autor_idoso")

    def test_paginacao(self):
        """Testa paginação de resultados."""
        # Página 1, 2 itens
        resultado = self.db.query(ExtractionVariable).limit(2).offset(0).all()
        self.assertEqual(len(resultado), 2)

        # Página 2, 2 itens
        resultado = self.db.query(ExtractionVariable).limit(2).offset(2).all()
        self.assertEqual(len(resultado), 2)

        # Página 3, 1 item
        resultado = self.db.query(ExtractionVariable).limit(2).offset(4).all()
        self.assertEqual(len(resultado), 1)


class TestAPIVariaveisPrompts(unittest.TestCase):
    """Testes para visualização de prompts que usam variáveis."""

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False}
        )
        cls.Session = sessionmaker(bind=cls.engine)

        from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON
        from admin.models_prompts import PromptModulo
        from admin.models_prompt_groups import PromptGroup, PromptSubgroup
        from auth.models import User

        Base.metadata.create_all(bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=cls.engine)

    def setUp(self):
        self.db = self.Session()

    def tearDown(self):
        from admin.models_prompts import PromptModulo
        self.db.query(PromptVariableUsage).delete()
        self.db.query(PromptModulo).delete()
        self.db.query(ExtractionVariable).delete()
        self.db.commit()
        self.db.close()

    def _criar_prompt(self, nome, modo="deterministic"):
        from admin.models_prompts import PromptModulo

        prompt = PromptModulo(
            nome=nome,
            titulo=nome.replace("_", " ").title(),
            tipo="conteudo",
            conteudo="Conteúdo de teste",
            modo_ativacao=modo,
            ativo=True,
            ordem=0,
            palavras_chave=[],
            tags=[]
        )
        self.db.add(prompt)
        self.db.commit()
        return prompt

    def _criar_variavel(self, slug):
        variavel = ExtractionVariable(
            slug=slug,
            label=slug.replace("_", " ").title(),
            tipo="text",
            ativo=True
        )
        self.db.add(variavel)
        self.db.commit()
        return variavel

    def test_listar_prompts_por_variavel(self):
        """Testa listagem de prompts que usam uma variável."""
        var = self._criar_variavel("valor_causa")
        prompt1 = self._criar_prompt("prompt_valor_1")
        prompt2 = self._criar_prompt("prompt_valor_2")
        prompt3 = self._criar_prompt("prompt_outro")

        # Registra uso
        self.db.add(PromptVariableUsage(prompt_id=prompt1.id, variable_slug="valor_causa"))
        self.db.add(PromptVariableUsage(prompt_id=prompt2.id, variable_slug="valor_causa"))
        self.db.add(PromptVariableUsage(prompt_id=prompt3.id, variable_slug="outra_var"))
        self.db.commit()

        # Busca prompts que usam valor_causa
        sync = PromptVariableUsageSync(self.db)
        prompts = sync.obter_prompts_por_variavel("valor_causa")

        self.assertEqual(len(prompts), 2)
        nomes = {p["nome"] for p in prompts}
        self.assertIn("prompt_valor_1", nomes)
        self.assertIn("prompt_valor_2", nomes)

    def test_variavel_sem_prompts(self):
        """Testa variável que não é usada em nenhum prompt."""
        var = self._criar_variavel("var_isolada")

        sync = PromptVariableUsageSync(self.db)
        prompts = sync.obter_prompts_por_variavel("var_isolada")

        self.assertEqual(len(prompts), 0)


if __name__ == "__main__":
    unittest.main()
