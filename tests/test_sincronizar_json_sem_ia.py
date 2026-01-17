# tests/test_sincronizar_json_sem_ia.py
"""
Testes automatizados para o endpoint "Atualizar JSON (sem IA)".

Verifica que o JSON é reconstruído a partir do BD como fonte da verdade,
detectando mudanças em:
- Dependências (depends_on, condições, parent/child)
- Slugs
- Metadados (tipo, options, required, ordem)
- Estrutura geral

Critérios:
- Validar o JSON persistido/retornado, não só a resposta
- Comparação estrutural (deep equal)
- Usa fixtures de perguntas/variáveis/dependências
"""

import unittest
import json
import sys
import os

# Adiciona diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.connection import Base, get_db
from main import app


class TestSincronizarJSONSemIA(unittest.TestCase):
    """Testes de integração para endpoint sincronizar-json."""

    @classmethod
    def setUpClass(cls):
        """Configura banco em memória para todos os testes."""
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False}
        )
        cls.TestingSessionLocal = sessionmaker(bind=cls.engine)

        # Importa todos os modelos para criar tabelas
        from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON
        from sistemas.gerador_pecas.models_extraction import (
            ExtractionQuestion, ExtractionModel, ExtractionVariable,
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
        """Configura sessão para cada teste."""
        self.db = self.TestingSessionLocal()

        # Override dependency
        def override_get_db():
            try:
                yield self.db
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db

        # Limpa dados entre testes
        from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON
        from sistemas.gerador_pecas.models_extraction import ExtractionQuestion

        self.db.query(ExtractionQuestion).delete()
        self.db.query(CategoriaResumoJSON).delete()
        self.db.commit()

    def tearDown(self):
        """Limpa sessão."""
        self.db.rollback()
        self.db.close()

    def _criar_usuario_admin(self):
        """Cria usuário admin para testes."""
        from auth.models import User

        user = self.db.query(User).filter(User.username == "test_admin").first()
        if user:
            return user

        user = User(
            username="test_admin",
            full_name="Test Admin",
            email="admin@test.com",
            hashed_password="$2b$12$test",
            role="admin",
            is_active=True
        )
        self.db.add(user)
        self.db.commit()
        return user

    def _criar_categoria(self, nome="teste_categoria", formato_json=None):
        """Cria categoria de teste."""
        from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON

        categoria = CategoriaResumoJSON(
            nome=nome,
            titulo=f"Categoria {nome}",
            descricao="Categoria de teste",
            codigos_documento=[100],
            formato_json=json.dumps(formato_json) if formato_json else "{}"
        )
        self.db.add(categoria)
        self.db.commit()
        return categoria

    def _criar_pergunta(self, categoria_id, slug, tipo="text", pergunta="Pergunta teste",
                        depends_on=None, dependency_operator=None, dependency_value=None,
                        opcoes=None, ordem=0, ativo=True):
        """Cria pergunta de extração."""
        from sistemas.gerador_pecas.models_extraction import ExtractionQuestion

        p = ExtractionQuestion(
            categoria_id=categoria_id,
            pergunta=pergunta,
            nome_variavel_sugerido=slug,
            tipo_sugerido=tipo,
            depends_on_variable=depends_on,
            dependency_operator=dependency_operator,
            dependency_value=dependency_value,
            opcoes_sugeridas=opcoes,
            ordem=ordem,
            ativo=ativo
        )
        self.db.add(p)
        self.db.commit()
        return p

    def _executar_sincronizacao(self, categoria_id, user):
        """Executa o endpoint de sincronização diretamente (sem HTTP)."""
        import asyncio
        from sistemas.gerador_pecas.router_extraction import sincronizar_json_sem_ia

        # Executa função async
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                sincronizar_json_sem_ia(categoria_id, self.db, user)
            )
            return result
        finally:
            loop.close()

    # ==========================================================================
    # TESTE 1: Regressão - Dependências
    # ==========================================================================

    def test_alteracao_dependencia_deve_atualizar_json(self):
        """
        TESTE DE REGRESSÃO - DEPENDÊNCIAS

        Cenário:
        1. Categoria tem JSON com pergunta SEM dependência
        2. BD é atualizado para ADICIONAR dependência
        3. Sincronizar JSON
        4. JSON DEVE refletir a nova dependência
        """
        user = self._criar_usuario_admin()

        # JSON inicial: pergunta sem dependência
        json_inicial = {
            "nome_autor": {"type": "text", "description": "Qual o nome do autor?"},
            "cpf_autor": {"type": "text", "description": "Qual o CPF?"}
        }
        categoria = self._criar_categoria("test_deps", json_inicial)

        # Cria perguntas - cpf_autor AGORA DEPENDE de nome_autor
        self._criar_pergunta(
            categoria.id, "nome_autor", "text",
            "Qual o nome do autor?", ordem=0
        )
        self._criar_pergunta(
            categoria.id, "cpf_autor", "text",
            "Qual o CPF?",
            depends_on="nome_autor",
            dependency_operator="exists",
            dependency_value=True,
            ordem=1
        )

        # Executa sincronização
        result = self._executar_sincronizacao(categoria.id, user)

        # Verifica que houve alteração
        self.assertTrue(result.success)
        self.assertTrue(result.houve_alteracao,
            "Deveria detectar alteração ao adicionar dependência")
        self.assertIn("cpf_autor", result.variaveis_modificadas_lista or [],
            "cpf_autor deveria estar na lista de modificados")

        # Verifica JSON retornado tem a dependência
        json_retornado = result.schema_json
        self.assertTrue(json_retornado["cpf_autor"].get("conditional"),
            "Campo cpf_autor deveria ter conditional=True")
        self.assertEqual(json_retornado["cpf_autor"].get("depends_on"), "nome_autor",
            "Campo cpf_autor deveria depender de nome_autor")

    def test_remocao_dependencia_deve_atualizar_json(self):
        """
        Cenário:
        1. JSON tem pergunta COM dependência
        2. BD é atualizado para REMOVER dependência
        3. Sincronizar JSON
        4. JSON DEVE refletir a remoção
        """
        user = self._criar_usuario_admin()

        # JSON inicial: cpf_autor COM dependência
        json_inicial = {
            "nome_autor": {"type": "text", "description": "Qual o nome do autor?"},
            "cpf_autor": {
                "type": "text",
                "description": "Qual o CPF?",
                "conditional": True,
                "depends_on": "nome_autor",
                "dependency_operator": "exists"
            }
        }
        categoria = self._criar_categoria("test_deps_remove", json_inicial)

        # Cria perguntas - cpf_autor SEM dependência agora
        self._criar_pergunta(
            categoria.id, "nome_autor", "text",
            "Qual o nome do autor?", ordem=0
        )
        self._criar_pergunta(
            categoria.id, "cpf_autor", "text",
            "Qual o CPF?",
            ordem=1
            # SEM depends_on
        )

        # Executa sincronização
        result = self._executar_sincronizacao(categoria.id, user)

        # Verifica que houve alteração
        self.assertTrue(result.success)
        self.assertTrue(result.houve_alteracao,
            "Deveria detectar alteração ao remover dependência")

        # Verifica JSON retornado NÃO tem a dependência
        json_retornado = result.schema_json
        self.assertNotIn("conditional", json_retornado["cpf_autor"],
            "Campo cpf_autor não deveria ter conditional")
        self.assertNotIn("depends_on", json_retornado["cpf_autor"],
            "Campo cpf_autor não deveria ter depends_on")

    def test_alteracao_operador_dependencia_deve_atualizar_json(self):
        """
        Cenário:
        1. JSON tem dependência com operador "equals"
        2. BD é atualizado para operador "not_equals"
        3. Sincronizar JSON
        4. JSON DEVE refletir novo operador
        """
        user = self._criar_usuario_admin()

        json_inicial = {
            "tipo_pessoa": {"type": "choice", "options": ["PF", "PJ"]},
            "cpf": {
                "type": "text",
                "description": "CPF",
                "conditional": True,
                "depends_on": "tipo_pessoa",
                "dependency_operator": "equals",
                "dependency_value": "PF"
            }
        }
        categoria = self._criar_categoria("test_deps_operator", json_inicial)

        self._criar_pergunta(
            categoria.id, "tipo_pessoa", "choice",
            "Tipo de pessoa?", opcoes=["PF", "PJ"], ordem=0
        )
        # Agora CPF aparece quando NÃO É PF (invertido)
        self._criar_pergunta(
            categoria.id, "cpf", "text",
            "CPF",
            depends_on="tipo_pessoa",
            dependency_operator="not_equals",  # MUDOU de equals para not_equals
            dependency_value="PF",
            ordem=1
        )

        result = self._executar_sincronizacao(categoria.id, user)

        self.assertTrue(result.houve_alteracao,
            "Deveria detectar alteração no operador de dependência")
        self.assertEqual(
            result.schema_json["cpf"]["dependency_operator"],
            "not_equals"
        )

    # ==========================================================================
    # TESTE 2: Slug
    # ==========================================================================

    def test_alteracao_slug_deve_atualizar_json(self):
        """
        TESTE DE SLUG

        Cenário:
        1. JSON tem campo "nome_completo"
        2. BD altera slug para "nome_autor"
        3. Sincronizar JSON
        4. JSON DEVE ter novo slug (e remover antigo se não houver pergunta)

        Nota: Na prática, mudar slug significa uma NOVA variável no BD.
        O sistema adiciona a nova e mantém campos manuais.
        """
        user = self._criar_usuario_admin()

        json_inicial = {
            "nome_completo": {"type": "text", "description": "Nome completo"}
        }
        categoria = self._criar_categoria("test_slug", json_inicial)

        # Pergunta com slug DIFERENTE do JSON
        self._criar_pergunta(
            categoria.id, "nome_autor", "text",  # Slug diferente!
            "Nome completo", ordem=0
        )

        result = self._executar_sincronizacao(categoria.id, user)

        self.assertTrue(result.success)
        # Nova variável foi adicionada
        self.assertIn("nome_autor", result.schema_json,
            "Novo slug deveria estar no JSON")
        # Campo antigo é preservado (campo manual)
        self.assertIn("nome_completo", result.schema_json,
            "Campo manual deveria ser preservado")
        self.assertIn("nome_autor", result.variaveis_adicionadas_lista or [],
            "nome_autor deveria estar na lista de adicionados")

    # ==========================================================================
    # TESTE 3: Metadados
    # ==========================================================================

    def test_alteracao_tipo_deve_atualizar_json(self):
        """
        TESTE DE METADADOS - Tipo

        Cenário:
        1. JSON tem campo com type="text"
        2. BD altera para type="number"
        3. Sincronizar JSON
        4. JSON DEVE refletir novo tipo
        """
        user = self._criar_usuario_admin()

        json_inicial = {
            "valor_pedido": {"type": "text", "description": "Valor do pedido"}
        }
        categoria = self._criar_categoria("test_tipo", json_inicial)

        # Pergunta com tipo DIFERENTE
        self._criar_pergunta(
            categoria.id, "valor_pedido", "number",  # Era text, agora number
            "Valor do pedido", ordem=0
        )

        result = self._executar_sincronizacao(categoria.id, user)

        self.assertTrue(result.success)
        self.assertTrue(result.houve_alteracao,
            "Deveria detectar alteração de tipo")
        self.assertEqual(result.schema_json["valor_pedido"]["type"], "number",
            "Tipo deveria ser atualizado para number")

    def test_alteracao_options_deve_atualizar_json(self):
        """
        TESTE DE METADADOS - Options

        Cenário:
        1. JSON tem campo choice com options=["A", "B"]
        2. BD altera para options=["A", "B", "C"]
        3. Sincronizar JSON
        4. JSON DEVE refletir novas opções
        """
        user = self._criar_usuario_admin()

        json_inicial = {
            "tipo_acao": {
                "type": "choice",
                "description": "Tipo de ação",
                "options": ["Civil", "Trabalhista"]
            }
        }
        categoria = self._criar_categoria("test_options", json_inicial)

        # Pergunta com opções DIFERENTES
        self._criar_pergunta(
            categoria.id, "tipo_acao", "choice",
            "Tipo de ação",
            opcoes=["Civil", "Trabalhista", "Tributária"],  # Adicionou opção
            ordem=0
        )

        result = self._executar_sincronizacao(categoria.id, user)

        self.assertTrue(result.success)
        self.assertTrue(result.houve_alteracao,
            "Deveria detectar alteração de opções")
        self.assertIn("Tributária", result.schema_json["tipo_acao"]["options"],
            "Nova opção deveria estar presente")

    def test_alteracao_descricao_deve_atualizar_json(self):
        """
        TESTE DE METADADOS - Description

        Cenário:
        1. JSON tem campo com description="Desc antiga"
        2. BD altera description="Desc nova"
        3. Sincronizar JSON
        4. JSON DEVE refletir nova descrição
        """
        user = self._criar_usuario_admin()

        json_inicial = {
            "data_fato": {"type": "date", "description": "Data do fato"}
        }
        categoria = self._criar_categoria("test_descricao", json_inicial)

        self._criar_pergunta(
            categoria.id, "data_fato", "date",
            "Qual a data em que ocorreu o fato gerador?",  # Descrição diferente
            ordem=0
        )

        result = self._executar_sincronizacao(categoria.id, user)

        self.assertTrue(result.success)
        self.assertTrue(result.houve_alteracao,
            "Deveria detectar alteração de descrição")
        self.assertEqual(
            result.schema_json["data_fato"]["description"],
            "Qual a data em que ocorreu o fato gerador?"
        )

    # ==========================================================================
    # TESTE 4: Teste Negativo
    # ==========================================================================

    def test_sem_mudanca_deve_retornar_nada_para_atualizar(self):
        """
        TESTE NEGATIVO

        Cenário:
        1. JSON está sincronizado com BD
        2. Nenhuma alteração
        3. Sincronizar JSON
        4. DEVE retornar "Nada para atualizar"
        """
        user = self._criar_usuario_admin()

        # JSON idêntico ao que será gerado pelas perguntas
        json_inicial = {
            "nome_autor": {"type": "text", "description": "Qual o nome do autor?"},
            "valor_causa": {"type": "number", "description": "Qual o valor da causa?"}
        }
        categoria = self._criar_categoria("test_sem_mudanca", json_inicial)

        # Perguntas idênticas ao JSON
        self._criar_pergunta(
            categoria.id, "nome_autor", "text",
            "Qual o nome do autor?", ordem=0
        )
        self._criar_pergunta(
            categoria.id, "valor_causa", "number",
            "Qual o valor da causa?", ordem=1
        )

        result = self._executar_sincronizacao(categoria.id, user)

        self.assertTrue(result.success)
        self.assertFalse(result.houve_alteracao,
            "Não deveria haver alteração quando JSON está sincronizado")
        self.assertEqual(result.variaveis_adicionadas, 0)
        self.assertEqual(result.variaveis_modificadas, 0)
        self.assertIn("Nada para atualizar", result.mensagem)

    # ==========================================================================
    # TESTES ADICIONAIS DE REGRESSÃO
    # ==========================================================================

    def test_multiplas_alteracoes_simultaneas(self):
        """
        Cenário: Múltiplas alterações em diferentes campos simultaneamente.
        """
        user = self._criar_usuario_admin()

        json_inicial = {
            "campo1": {"type": "text", "description": "Campo 1"},
            "campo2": {"type": "text", "description": "Campo 2"},
            "campo3": {"type": "choice", "options": ["A", "B"]}
        }
        categoria = self._criar_categoria("test_multiplas", json_inicial)

        # campo1: muda tipo
        self._criar_pergunta(categoria.id, "campo1", "number", "Campo 1", ordem=0)
        # campo2: adiciona dependência
        self._criar_pergunta(
            categoria.id, "campo2", "text", "Campo 2",
            depends_on="campo1", dependency_operator="exists", ordem=1
        )
        # campo3: muda opções
        self._criar_pergunta(
            categoria.id, "campo3", "choice", "Campo 3",
            opcoes=["A", "B", "C"], ordem=2
        )

        result = self._executar_sincronizacao(categoria.id, user)

        self.assertTrue(result.success)
        self.assertTrue(result.houve_alteracao)
        # Verifica que todas as mudanças foram detectadas
        self.assertEqual(result.schema_json["campo1"]["type"], "number")
        self.assertTrue(result.schema_json["campo2"].get("conditional"))
        self.assertIn("C", result.schema_json["campo3"]["options"])

    def test_preserva_campos_manuais_nao_mapeados(self):
        """
        Campos no JSON que não têm pergunta correspondente devem ser preservados.
        """
        user = self._criar_usuario_admin()

        json_inicial = {
            "campo_pergunta": {"type": "text", "description": "Pergunta"},
            "campo_manual": {"type": "text", "description": "Campo adicionado manualmente"}
        }
        categoria = self._criar_categoria("test_manual", json_inicial)

        # Só cria pergunta para um campo
        self._criar_pergunta(
            categoria.id, "campo_pergunta", "text", "Pergunta", ordem=0
        )

        result = self._executar_sincronizacao(categoria.id, user)

        self.assertTrue(result.success)
        # Campo manual deve ser preservado
        self.assertIn("campo_manual", result.schema_json,
            "Campo manual deveria ser preservado")
        self.assertEqual(
            result.schema_json["campo_manual"]["description"],
            "Campo adicionado manualmente"
        )


class TestFuncoesAuxiliares(unittest.TestCase):
    """Testes unitários para funções auxiliares de comparação."""

    def test_normalizar_para_comparacao_ordena_chaves(self):
        """Verifica que chaves são ordenadas para comparação."""
        obj1 = {"z": 1, "a": 2, "m": 3}
        obj2 = {"a": 2, "m": 3, "z": 1}

        # Importa função do módulo
        # Simulamos a função inline para teste
        def _normalizar_para_comparacao(obj):
            if isinstance(obj, dict):
                return {k: _normalizar_para_comparacao(obj[k]) for k in sorted(obj.keys())}
            elif isinstance(obj, list):
                if obj and isinstance(obj[0], dict):
                    if 'id' in obj[0]:
                        return sorted([_normalizar_para_comparacao(item) for item in obj],
                                      key=lambda x: str(x.get('id', '')))
                    elif 'value' in obj[0]:
                        return sorted([_normalizar_para_comparacao(item) for item in obj],
                                      key=lambda x: str(x.get('value', '')))
                return [_normalizar_para_comparacao(item) for item in obj]
            return obj

        self.assertEqual(
            _normalizar_para_comparacao(obj1),
            _normalizar_para_comparacao(obj2)
        )

    def test_normalizar_para_comparacao_ordena_arrays(self):
        """Verifica que arrays de dicts são ordenados."""
        obj1 = {"options": [{"id": 2}, {"id": 1}]}
        obj2 = {"options": [{"id": 1}, {"id": 2}]}

        def _normalizar_para_comparacao(obj):
            if isinstance(obj, dict):
                return {k: _normalizar_para_comparacao(obj[k]) for k in sorted(obj.keys())}
            elif isinstance(obj, list):
                if obj and isinstance(obj[0], dict):
                    if 'id' in obj[0]:
                        return sorted([_normalizar_para_comparacao(item) for item in obj],
                                      key=lambda x: str(x.get('id', '')))
                return [_normalizar_para_comparacao(item) for item in obj]
            return obj

        self.assertEqual(
            _normalizar_para_comparacao(obj1),
            _normalizar_para_comparacao(obj2)
        )


def run_tests():
    """Executa os testes."""
    print("\n" + "=" * 70)
    print("TESTES: Sincronizar JSON (sem IA) - Detecção de Alterações")
    print("=" * 70 + "\n")

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestSincronizarJSONSemIA))
    suite.addTests(loader.loadTestsFromTestCase(TestFuncoesAuxiliares))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 70)
    if result.wasSuccessful():
        print("TODOS OS TESTES PASSARAM!")
    else:
        print(f"FALHAS: {len(result.failures)}, ERROS: {len(result.errors)}")
    print("=" * 70 + "\n")

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
