# tests/ia_extracao_regras/backend/integration/test_endpoints_teste_ativacao.py
"""
Testes para validar a correção do bug:
'ExtractionVariable' object has no attribute 'categoria'

O bug ocorria porque o código tentava acessar um relacionamento SQLAlchemy
que não existe no model ExtractionVariable. A correção usa LEFT OUTER JOIN
explícito para buscar o título da categoria.
"""

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.connection import Base


class TestGerarVariaveisQuery(unittest.TestCase):
    """
    Testes unitários para a query de variáveis com JOIN de categoria.

    Valida que a correção do bug funciona:
    - Variáveis com categoria retornam o título correto
    - Variáveis sem categoria retornam None
    - O JOIN não causa erro de atributo
    """

    @classmethod
    def setUpClass(cls):
        """Configura banco em memória."""
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False}
        )
        cls.TestingSessionLocal = sessionmaker(bind=cls.engine)

        # Importa todos os modelos necessários para resolver FKs
        from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON
        from sistemas.gerador_pecas.models_extraction import (
            ExtractionVariable, ExtractionQuestion, ExtractionModel,
            PromptVariableUsage, PromptActivationLog
        )
        from admin.models_prompts import PromptModulo
        from admin.models_prompt_groups import PromptGroup, PromptSubgroup
        from auth.models import User

        Base.metadata.create_all(bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        """Limpa recursos."""
        Base.metadata.drop_all(bind=cls.engine)

    def setUp(self):
        """Configura sessão."""
        self.db = self.TestingSessionLocal()

    def tearDown(self):
        """Limpa sessão e dados entre testes."""
        from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON
        from sistemas.gerador_pecas.models_extraction import ExtractionVariable

        # Limpa dados criados pelo teste
        self.db.query(ExtractionVariable).delete()
        self.db.query(CategoriaResumoJSON).delete()
        self.db.commit()
        self.db.close()

    def test_query_variavel_com_categoria_retorna_titulo(self):
        """
        Testa que variáveis com categoria retornam o título corretamente.

        Reproduz a query corrigida do endpoint /gerar-variaveis.
        """
        from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON
        from sistemas.gerador_pecas.models_extraction import ExtractionVariable

        # Cria categoria
        categoria = CategoriaResumoJSON(
            nome="sentencas",
            titulo="Sentenças",
            descricao="Categoria de sentenças",
            codigos_documento=[100],
            formato_json='{"tipo": "string"}'
        )
        self.db.add(categoria)
        self.db.commit()

        # Cria variável com categoria
        variavel = ExtractionVariable(
            slug="valor_condenacao",
            label="Valor da Condenação",
            tipo="number",
            categoria_id=categoria.id,
            ativo=True
        )
        self.db.add(variavel)
        self.db.commit()

        # Executa a query com JOIN (código corrigido)
        query = self.db.query(
            ExtractionVariable,
            CategoriaResumoJSON.titulo.label("categoria_titulo")
        ).outerjoin(
            CategoriaResumoJSON,
            ExtractionVariable.categoria_id == CategoriaResumoJSON.id
        ).filter(ExtractionVariable.ativo == True)

        resultados = query.all()

        # Verifica
        self.assertEqual(len(resultados), 1)
        v, categoria_titulo = resultados[0]
        self.assertEqual(v.slug, "valor_condenacao")
        self.assertEqual(categoria_titulo, "Sentenças")

    def test_query_variavel_sem_categoria_retorna_none(self):
        """
        Testa que variáveis SEM categoria retornam None para categoria_titulo.

        Garante que o OUTER JOIN funciona quando categoria_id é NULL.
        """
        from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON
        from sistemas.gerador_pecas.models_extraction import ExtractionVariable

        # Cria variável sem categoria
        variavel = ExtractionVariable(
            slug="flag_urgente",
            label="Flag Urgente",
            tipo="boolean",
            categoria_id=None,
            ativo=True
        )
        self.db.add(variavel)
        self.db.commit()

        # Executa a query com JOIN
        query = self.db.query(
            ExtractionVariable,
            CategoriaResumoJSON.titulo.label("categoria_titulo")
        ).outerjoin(
            CategoriaResumoJSON,
            ExtractionVariable.categoria_id == CategoriaResumoJSON.id
        ).filter(
            ExtractionVariable.ativo == True,
            ExtractionVariable.slug == "flag_urgente"
        )

        resultados = query.all()

        # Verifica que retornou a variável com categoria None
        self.assertEqual(len(resultados), 1)
        v, categoria_titulo = resultados[0]
        self.assertEqual(v.slug, "flag_urgente")
        self.assertIsNone(categoria_titulo)

    def test_query_mista_variaveis_com_e_sem_categoria(self):
        """
        Testa cenário misto: variáveis com e sem categoria juntas.

        Este é o caso real em produção.
        """
        from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON
        from sistemas.gerador_pecas.models_extraction import ExtractionVariable

        # Cria categoria
        categoria = CategoriaResumoJSON(
            nome="documentos_nat",
            titulo="Documentos NAT",
            descricao="Teste",
            codigos_documento=[200],
            formato_json='{"tipo": "string"}'
        )
        self.db.add(categoria)
        self.db.commit()

        # Variável com categoria
        var1 = ExtractionVariable(
            slug="tipo_medicamento",
            label="Tipo de Medicamento",
            tipo="text",
            categoria_id=categoria.id,
            ativo=True
        )
        # Variável sem categoria
        var2 = ExtractionVariable(
            slug="data_distribuicao",
            label="Data de Distribuição",
            tipo="date",
            categoria_id=None,
            ativo=True
        )
        self.db.add_all([var1, var2])
        self.db.commit()

        # Executa a query com JOIN
        query = self.db.query(
            ExtractionVariable,
            CategoriaResumoJSON.titulo.label("categoria_titulo")
        ).outerjoin(
            CategoriaResumoJSON,
            ExtractionVariable.categoria_id == CategoriaResumoJSON.id
        ).filter(ExtractionVariable.ativo == True)

        resultados = query.all()

        # Deve retornar 2 variáveis
        self.assertEqual(len(resultados), 2)

        # Organiza por slug para facilitar verificação
        por_slug = {v.slug: cat for v, cat in resultados}

        self.assertEqual(por_slug["tipo_medicamento"], "Documentos NAT")
        self.assertIsNone(por_slug["data_distribuicao"])

    def test_construcao_dicionario_variavel_para_ia(self):
        """
        Testa a construção do dicionário de variável como enviado para a IA.

        Simula exatamente o código corrigido no endpoint.
        """
        from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON
        from sistemas.gerador_pecas.models_extraction import ExtractionVariable

        # Setup
        categoria = CategoriaResumoJSON(
            nome="peticoes",
            titulo="Petições",
            descricao="Teste",
            codigos_documento=[500],
            formato_json='{"tipo": "string"}'
        )
        self.db.add(categoria)
        self.db.commit()

        variavel = ExtractionVariable(
            slug="valor_causa",
            label="Valor da Causa",
            tipo="currency",
            descricao="Valor total da causa",
            categoria_id=categoria.id,
            ativo=True
        )
        self.db.add(variavel)
        self.db.commit()

        # Query e construção do dicionário (código corrigido)
        query = self.db.query(
            ExtractionVariable,
            CategoriaResumoJSON.titulo.label("categoria_titulo")
        ).outerjoin(
            CategoriaResumoJSON,
            ExtractionVariable.categoria_id == CategoriaResumoJSON.id
        ).filter(ExtractionVariable.ativo == True)

        variaveis_disponiveis = []
        for v, categoria_titulo in query.all():
            variaveis_disponiveis.append({
                "slug": v.slug,
                "label": v.label,
                "tipo": v.tipo,
                "descricao": v.descricao,
                "categoria": categoria_titulo
            })

        # Verifica
        self.assertEqual(len(variaveis_disponiveis), 1)
        var_dict = variaveis_disponiveis[0]
        self.assertEqual(var_dict["slug"], "valor_causa")
        self.assertEqual(var_dict["label"], "Valor da Causa")
        self.assertEqual(var_dict["tipo"], "currency")
        self.assertEqual(var_dict["descricao"], "Valor total da causa")
        self.assertEqual(var_dict["categoria"], "Petições")


if __name__ == "__main__":
    unittest.main()
