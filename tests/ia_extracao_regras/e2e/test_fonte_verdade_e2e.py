# tests/ia_extracao_regras/e2e/test_fonte_verdade_e2e.py
"""
Testes E2E para fonte de verdade e fontes especiais.

Testa o fluxo completo:
1. Configuração de categoria com fonte de verdade (tipo lógico + código específico)
2. Configuração de categoria com fonte especial (ex: petição inicial)
3. Classificação de documentos
4. Exclusão de documentos de categorias por código quando há fonte especial
5. Seleção de prompts baseada em variáveis extraídas

Usa processo real: 0803505-92.2025.8.12.0029
"""

import unittest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime
from typing import List, Dict, Any

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.connection import Base


# Dados mockados do processo 0803505-92.2025.8.12.0029
# Simula a estrutura real de documentos do TJ-MS
PROCESSO_TESTE = "0803505-92.2025.8.12.0029"

DOCUMENTOS_PROCESSO_MOCK = [
    {
        "id": "doc_001",
        "tipo_documento": 9500,  # Petição
        "descricao": "PETIÇÃO INICIAL",
        "data": datetime(2025, 1, 10, 10, 0, 0),
        "conteudo": """
        EXCELENTÍSSIMO SENHOR DOUTOR JUIZ DE DIREITO...

        JOÃO DA SILVA, brasileiro, casado, portador do CPF xxx.xxx.xxx-xx,
        vem, respeitosamente, perante Vossa Excelência, propor a presente

        AÇÃO ORDINÁRIA COM PEDIDO DE TUTELA ANTECIPADA

        em face do ESTADO DE MATO GROSSO DO SUL, pelos fatos e fundamentos a seguir expostos.

        DOS FATOS
        O autor é portador de diabetes mellitus tipo 2 e necessita do medicamento
        OZEMPIC (semaglutida) para controle da doença...

        DO PEDIDO
        Ante o exposto, requer:
        a) A concessão da tutela antecipada para fornecimento imediato do medicamento;
        b) A procedência da ação para condenar o réu ao fornecimento contínuo;
        c) A condenação do réu em custas e honorários advocatícios.

        Dá-se à causa o valor de R$ 50.000,00.
        """
    },
    {
        "id": "doc_002",
        "tipo_documento": 9500,  # Petição (intermediária)
        "descricao": "PETIÇÃO INTERMEDIÁRIA",
        "data": datetime(2025, 1, 15, 14, 30, 0),
        "conteudo": """
        EXCELENTÍSSIMO SENHOR DOUTOR JUIZ...

        JOÃO DA SILVA, já qualificado nos autos, vem informar novo endereço
        e juntar comprovante de residência atualizado.

        Termos em que pede deferimento.
        """
    },
    {
        "id": "doc_003",
        "tipo_documento": 60,  # Contestação
        "descricao": "CONTESTAÇÃO",
        "data": datetime(2025, 1, 20, 9, 0, 0),
        "conteudo": """
        EXCELENTÍSSIMO SENHOR DOUTOR JUIZ...

        O ESTADO DE MATO GROSSO DO SUL, por sua Procuradoria, vem apresentar

        CONTESTAÇÃO

        à ação ordinária proposta por JOÃO DA SILVA, pelos motivos a seguir:

        PRELIMINARMENTE
        Alega-se a ilegitimidade passiva do Estado...

        NO MÉRITO
        O medicamento solicitado não consta na lista do SUS...
        """
    },
    {
        "id": "doc_004",
        "tipo_documento": 215,  # Parecer Técnico NAT
        "descricao": "NOTA TÉCNICA NATJUS",
        "data": datetime(2025, 1, 22, 11, 0, 0),
        "conteudo": """
        NOTA TÉCNICA Nº 123/2025

        PACIENTE: JOÃO DA SILVA
        MEDICAMENTO SOLICITADO: OZEMPIC (semaglutida)

        ANÁLISE TÉCNICA:
        O medicamento Ozempic é indicado para tratamento de diabetes tipo 2...

        CONCLUSÃO:
        FAVORÁVEL ao fornecimento do medicamento, considerando a indicação
        clínica adequada e a falha terapêutica com tratamentos convencionais.
        """
    },
    {
        "id": "doc_005",
        "tipo_documento": 9500,  # Outra petição
        "descricao": "PETIÇÃO - JUNTADA DE DOCUMENTOS",
        "data": datetime(2025, 1, 25, 16, 0, 0),
        "conteudo": """
        O autor vem juntar laudo médico atualizado e receituário...
        """
    }
]


class DocumentoMock:
    """Mock de DocumentoTJMS para testes"""
    def __init__(self, data: Dict[str, Any]):
        self.id = data["id"]
        self.tipo_documento = data["tipo_documento"]
        self.descricao = data.get("descricao", "")
        self.data = data.get("data")
        self.conteudo = data.get("conteudo", "")
        self.resumo = None
        self.irrelevante = False
        self.erro = None
        self.numero_processo = PROCESSO_TESTE


class TestTiposLogicosCategoria(unittest.TestCase):
    """
    Testes para tipos logicos de categoria.

    Verifica que categorias podem ter tipos logicos configurados
    para futura implementacao de classificacao.
    """

    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False}
        )
        Session = sessionmaker(bind=self.engine)

        from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON
        from auth.models import User

        Base.metadata.create_all(bind=self.engine)
        self.db = Session()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)

    def test_categoria_com_tipos_logicos(self):
        """Verifica que categoria pode ter tipos logicos configurados"""
        from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON

        categoria = CategoriaResumoJSON(
            nome="peticoes_autor",
            titulo="Peticoes do Autor",
            descricao="Peticoes protocoladas pelo autor",
            codigos_documento=[9500, 500, 510],
            formato_json='{}',
            namespace_prefix="peticao",
            tipos_logicos_peca=["peticao inicial", "peticao intermediaria", "peticao de juntada"],
            ativo=True
        )
        self.db.add(categoria)
        self.db.commit()

        self.assertIsNotNone(categoria.tipos_logicos_peca)
        self.assertEqual(len(categoria.tipos_logicos_peca), 3)
        self.assertIn("peticao inicial", categoria.tipos_logicos_peca)

    def test_categoria_sem_tipos_logicos(self):
        """Verifica que categoria pode existir sem tipos logicos"""
        from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON

        categoria = CategoriaResumoJSON(
            nome="documentos_gerais",
            titulo="Documentos Gerais",
            codigos_documento=[1000],
            formato_json='{}',
            tipos_logicos_peca=None,
            ativo=True
        )
        self.db.add(categoria)
        self.db.commit()

        self.assertIsNone(categoria.tipos_logicos_peca)

    def test_namespace_com_prefix(self):
        """Verifica que namespace usa prefix quando definido"""
        from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON

        categoria = CategoriaResumoJSON(
            nome="peticoes",
            titulo="Peticoes",
            codigos_documento=[9500],
            formato_json='{}',
            namespace_prefix="pet",
            ativo=True
        )
        self.db.add(categoria)
        self.db.commit()

        self.assertEqual(categoria.namespace, "pet")

    def test_namespace_fallback_para_nome(self):
        """Verifica que namespace usa nome quando prefix nao definido"""
        from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON

        categoria = CategoriaResumoJSON(
            nome="notas_tecnicas",
            titulo="Notas Tecnicas",
            codigos_documento=[215],
            formato_json='{}',
            ativo=True
        )
        self.db.add(categoria)
        self.db.commit()

        self.assertEqual(categoria.namespace, "notas_tecnicas")


class TestFonteEspecialPeticaoInicial(unittest.TestCase):
    """
    Testes para fonte especial "petição inicial".

    Cenário:
    - Categoria "Petição Inicial" usa source_type="special"
    - Categoria "Petições" usa códigos [9500, 500]
    - A petição inicial (primeiro doc 9500) vai para "Petição Inicial"
    - Demais petições 9500 vão para "Petições"
    """

    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False}
        )
        Session = sessionmaker(bind=self.engine)

        from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON
        from auth.models import User

        Base.metadata.create_all(bind=self.engine)
        self.db = Session()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)

    def _criar_categorias_com_fonte_especial(self):
        """Cria categorias: uma especial (petição inicial) e uma por código (petições)"""
        from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON

        # Categoria com fonte especial
        cat_especial = CategoriaResumoJSON(
            nome="peticao_inicial",
            titulo="Petição Inicial",
            descricao="Primeira petição do processo",
            codigos_documento=[],  # Não usa códigos
            formato_json='{"autor": "string", "reu": "string", "pedidos": ["string"], "valor_causa": "number"}',
            namespace_prefix="pi",
            source_type="special",
            source_special_type="peticao_inicial",
            ativo=True
        )

        # Categoria por código (demais petições)
        cat_codigo = CategoriaResumoJSON(
            nome="peticoes_intermediarias",
            titulo="Petições Intermediárias",
            descricao="Petições após a inicial",
            codigos_documento=[9500, 500, 510],
            formato_json='{"tipo": "string", "conteudo_resumido": "string"}',
            namespace_prefix="pet",
            source_type="code",
            ativo=True
        )

        self.db.add_all([cat_especial, cat_codigo])
        self.db.commit()
        return cat_especial, cat_codigo

    def test_gerenciador_identifica_peticao_inicial(self):
        """Testa que GerenciadorFormatosJSON identifica corretamente a petição inicial"""
        from sistemas.gerador_pecas.extrator_resumo_json import GerenciadorFormatosJSON

        cat_especial, cat_codigo = self._criar_categorias_com_fonte_especial()

        # Cria documentos mock
        docs = [DocumentoMock(d) for d in DOCUMENTOS_PROCESSO_MOCK]

        gerenciador = GerenciadorFormatosJSON(self.db)
        gerenciador.preparar_lote(docs)

        # doc_001 (primeira petição 9500) deve ir para categoria especial
        formato_001 = gerenciador.obter_formato(9500, doc_id="doc_001")
        self.assertEqual(formato_001.categoria_nome, "peticao_inicial")

        # doc_002 (segunda petição 9500) deve ir para categoria por código
        formato_002 = gerenciador.obter_formato(9500, doc_id="doc_002")
        self.assertEqual(formato_002.categoria_nome, "peticoes_intermediarias")

        # doc_005 (terceira petição 9500) também deve ir para categoria por código
        formato_005 = gerenciador.obter_formato(9500, doc_id="doc_005")
        self.assertEqual(formato_005.categoria_nome, "peticoes_intermediarias")

    def test_exclusao_automatica_de_codigo(self):
        """Testa que petição inicial é excluída automaticamente da categoria por código"""
        from sistemas.gerador_pecas.extrator_resumo_json import GerenciadorFormatosJSON

        cat_especial, cat_codigo = self._criar_categorias_com_fonte_especial()

        docs = [DocumentoMock(d) for d in DOCUMENTOS_PROCESSO_MOCK]

        gerenciador = GerenciadorFormatosJSON(self.db)
        gerenciador.preparar_lote(docs)

        # Verifica que doc_001 está na lista de exclusão
        self.assertIn("doc_001", gerenciador._docs_excluir_codigo)

        # Verifica que doc_002 e doc_005 NÃO estão na lista de exclusão
        self.assertNotIn("doc_002", gerenciador._docs_excluir_codigo)
        self.assertNotIn("doc_005", gerenciador._docs_excluir_codigo)


class TestFluxoCompletoComPrompts(unittest.TestCase):
    """
    Testes E2E para fluxo completo incluindo seleção de prompts.

    Cenário completo:
    1. Documentos são processados
    2. Variáveis são extraídas da petição inicial
    3. Prompts são selecionados baseados nas variáveis
    """

    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False}
        )
        Session = sessionmaker(bind=self.engine)

        from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON
        from sistemas.gerador_pecas.models_extraction import ExtractionVariable, PromptVariableUsage
        from admin.models_prompts import PromptModulo
        from admin.models_prompt_groups import PromptGroup, PromptSubgroup
        from auth.models import User

        Base.metadata.create_all(bind=self.engine)
        self.db = Session()
        self._criar_dados_teste()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)

    def _criar_dados_teste(self):
        """Cria dados completos para teste E2E"""
        from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON
        from sistemas.gerador_pecas.models_extraction import ExtractionVariable
        from admin.models_prompts import PromptModulo

        # Categoria com fonte especial
        self.categoria = CategoriaResumoJSON(
            nome="peticao_inicial_medicamentos",
            titulo="Petição Inicial - Medicamentos",
            descricao="Petição inicial em ações de medicamentos",
            codigos_documento=[],
            formato_json='{"medicamento": "string", "autor_idoso": "boolean", "valor_causa": "number"}',
            namespace_prefix="med",
            source_type="special",
            source_special_type="peticao_inicial",
            ativo=True
        )
        self.db.add(self.categoria)

        # Variáveis de extração
        self.var_medicamento = ExtractionVariable(
            slug="med_medicamento",
            label="Medicamento Solicitado",
            tipo="text",
            ativo=True
        )
        self.var_idoso = ExtractionVariable(
            slug="med_autor_idoso",
            label="Autor é Idoso",
            tipo="boolean",
            ativo=True
        )
        self.var_valor = ExtractionVariable(
            slug="med_valor_causa",
            label="Valor da Causa",
            tipo="currency",
            ativo=True
        )
        self.db.add_all([self.var_medicamento, self.var_idoso, self.var_valor])

        # Prompts com regras determinísticas
        self.prompt_idoso = PromptModulo(
            nome="argumento_idoso",
            titulo="Argumentação - Autor Idoso",
            tipo="conteudo",
            conteudo="Considerando que o autor é pessoa idosa, aplica-se o Estatuto do Idoso...",
            modo_ativacao="deterministic",
            regra_deterministica={
                "type": "condition",
                "variable": "med_autor_idoso",
                "operator": "equals",
                "value": True
            },
            ativo=True,
            ordem=0,
            palavras_chave=[],
            tags=[]
        )

        self.prompt_alto_valor = PromptModulo(
            nome="argumento_alto_valor",
            titulo="Argumentação - Alto Valor",
            tipo="conteudo",
            conteudo="Considerando o alto valor da causa, recomenda-se atenção especial...",
            modo_ativacao="deterministic",
            regra_deterministica={
                "type": "condition",
                "variable": "med_valor_causa",
                "operator": "greater_than",
                "value": 100000
            },
            ativo=True,
            ordem=1,
            palavras_chave=[],
            tags=[]
        )

        self.prompt_ozempic = PromptModulo(
            nome="argumento_ozempic",
            titulo="Argumentação - Ozempic",
            tipo="conteudo",
            conteudo="Para casos de Ozempic, verificar protocolo específico do SUS...",
            modo_ativacao="deterministic",
            regra_deterministica={
                "type": "condition",
                "variable": "med_medicamento",
                "operator": "contains",
                "value": "ozempic"
            },
            ativo=True,
            ordem=2,
            palavras_chave=[],
            tags=[]
        )

        self.db.add_all([self.prompt_idoso, self.prompt_alto_valor, self.prompt_ozempic])
        self.db.commit()

    def test_fluxo_completo_extracao_e_selecao_prompts(self):
        """Testa fluxo completo: extração de variáveis e seleção de prompts"""
        from sistemas.gerador_pecas.services_deterministic import (
            DeterministicRuleEvaluator,
            avaliar_ativacao_prompt
        )

        # Simula dados extraídos da petição inicial
        dados_extraidos = {
            "med_medicamento": "OZEMPIC (semaglutida)",
            "med_autor_idoso": False,  # João da Silva não é idoso no mock
            "med_valor_causa": 50000
        }

        evaluator = DeterministicRuleEvaluator()

        # Avalia prompt de idoso - deve ser FALSE (autor não é idoso)
        resultado_idoso = avaliar_ativacao_prompt(
            prompt_id=self.prompt_idoso.id,
            modo_ativacao="deterministic",
            regra_deterministica=self.prompt_idoso.regra_deterministica,
            dados_extracao=dados_extraidos,
            db=self.db
        )
        self.assertFalse(resultado_idoso["ativar"])

        # Avalia prompt de alto valor - deve ser FALSE (50k < 100k)
        resultado_valor = avaliar_ativacao_prompt(
            prompt_id=self.prompt_alto_valor.id,
            modo_ativacao="deterministic",
            regra_deterministica=self.prompt_alto_valor.regra_deterministica,
            dados_extracao=dados_extraidos,
            db=self.db
        )
        self.assertFalse(resultado_valor["ativar"])

        # Avalia prompt de Ozempic - deve ser TRUE (medicamento contém "ozempic")
        resultado_ozempic = avaliar_ativacao_prompt(
            prompt_id=self.prompt_ozempic.id,
            modo_ativacao="deterministic",
            regra_deterministica=self.prompt_ozempic.regra_deterministica,
            dados_extracao=dados_extraidos,
            db=self.db
        )
        self.assertTrue(resultado_ozempic["ativar"])

    def test_fluxo_completo_autor_idoso_alto_valor(self):
        """Testa fluxo com autor idoso e alto valor"""
        from sistemas.gerador_pecas.services_deterministic import avaliar_ativacao_prompt

        # Simula dados com autor idoso e alto valor
        dados_extraidos = {
            "med_medicamento": "Insulina NPH",
            "med_autor_idoso": True,
            "med_valor_causa": 150000
        }

        # Avalia prompt de idoso - deve ser TRUE
        resultado_idoso = avaliar_ativacao_prompt(
            prompt_id=self.prompt_idoso.id,
            modo_ativacao="deterministic",
            regra_deterministica=self.prompt_idoso.regra_deterministica,
            dados_extracao=dados_extraidos,
            db=self.db
        )
        self.assertTrue(resultado_idoso["ativar"])

        # Avalia prompt de alto valor - deve ser TRUE (150k > 100k)
        resultado_valor = avaliar_ativacao_prompt(
            prompt_id=self.prompt_alto_valor.id,
            modo_ativacao="deterministic",
            regra_deterministica=self.prompt_alto_valor.regra_deterministica,
            dados_extracao=dados_extraidos,
            db=self.db
        )
        self.assertTrue(resultado_valor["ativar"])

        # Avalia prompt de Ozempic - deve ser FALSE
        resultado_ozempic = avaliar_ativacao_prompt(
            prompt_id=self.prompt_ozempic.id,
            modo_ativacao="deterministic",
            regra_deterministica=self.prompt_ozempic.regra_deterministica,
            dados_extracao=dados_extraidos,
            db=self.db
        )
        self.assertFalse(resultado_ozempic["ativar"])

    def test_selecao_prompts_com_regra_and(self):
        """Testa seleção de prompts com regra AND"""
        from sistemas.gerador_pecas.services_deterministic import (
            DeterministicRuleEvaluator,
            avaliar_ativacao_prompt
        )
        from admin.models_prompts import PromptModulo

        # Cria prompt com regra AND
        prompt_and = PromptModulo(
            nome="argumento_complexo",
            titulo="Argumentação Complexa",
            tipo="conteudo",
            conteudo="Caso complexo: autor idoso + alto valor...",
            modo_ativacao="deterministic",
            regra_deterministica={
                "type": "and",
                "conditions": [
                    {"type": "condition", "variable": "med_autor_idoso", "operator": "equals", "value": True},
                    {"type": "condition", "variable": "med_valor_causa", "operator": "greater_than", "value": 100000}
                ]
            },
            ativo=True,
            ordem=3,
            palavras_chave=[],
            tags=[]
        )
        self.db.add(prompt_and)
        self.db.commit()

        # Caso 1: ambas condições verdadeiras
        dados_1 = {"med_autor_idoso": True, "med_valor_causa": 150000}
        resultado_1 = avaliar_ativacao_prompt(
            prompt_id=prompt_and.id,
            modo_ativacao="deterministic",
            regra_deterministica=prompt_and.regra_deterministica,
            dados_extracao=dados_1,
            db=self.db
        )
        self.assertTrue(resultado_1["ativar"])

        # Caso 2: apenas uma condição verdadeira
        dados_2 = {"med_autor_idoso": True, "med_valor_causa": 50000}
        resultado_2 = avaliar_ativacao_prompt(
            prompt_id=prompt_and.id,
            modo_ativacao="deterministic",
            regra_deterministica=prompt_and.regra_deterministica,
            dados_extracao=dados_2,
            db=self.db
        )
        self.assertFalse(resultado_2["ativar"])


class TestIntegracaoProcessoReal(unittest.TestCase):
    """
    Teste de integração simulando processo real 0803505-92.2025.8.12.0029

    Este teste simula todo o pipeline com dados que imitam um processo real.
    """

    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False}
        )
        Session = sessionmaker(bind=self.engine)

        from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON
        from sistemas.gerador_pecas.models_extraction import ExtractionVariable
        from admin.models_prompts import PromptModulo
        from admin.models_prompt_groups import PromptGroup, PromptSubgroup
        from auth.models import User

        Base.metadata.create_all(bind=self.engine)
        self.db = Session()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)

    def test_pipeline_completo_processo_0803505(self):
        """
        Simula pipeline completo para processo 0803505-92.2025.8.12.0029

        Etapas:
        1. Carrega documentos
        2. Identifica petição inicial (fonte especial)
        3. Classifica demais documentos
        4. Extrai variáveis
        5. Seleciona prompts
        """
        from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON
        from sistemas.gerador_pecas.extrator_resumo_json import GerenciadorFormatosJSON
        from sistemas.gerador_pecas.services_deterministic import DeterministicRuleEvaluator

        # Setup: categorias
        cat_pi = CategoriaResumoJSON(
            nome="peticao_inicial",
            titulo="Petição Inicial",
            formato_json='{}',
            source_type="special",
            source_special_type="peticao_inicial",
            ativo=True
        )
        cat_pet = CategoriaResumoJSON(
            nome="peticoes",
            titulo="Petições",
            formato_json='{}',
            codigos_documento=[9500, 500],
            source_type="code",
            ativo=True
        )
        cat_nat = CategoriaResumoJSON(
            nome="nat",
            titulo="Nota Técnica NAT",
            formato_json='{}',
            codigos_documento=[215],
            source_type="code",
            ativo=True
        )
        cat_contestacao = CategoriaResumoJSON(
            nome="contestacao",
            titulo="Contestação",
            formato_json='{}',
            codigos_documento=[60],
            source_type="code",
            ativo=True
        )
        self.db.add_all([cat_pi, cat_pet, cat_nat, cat_contestacao])
        self.db.commit()

        # Carrega documentos mock
        docs = [DocumentoMock(d) for d in DOCUMENTOS_PROCESSO_MOCK]

        # Prepara gerenciador
        gerenciador = GerenciadorFormatosJSON(self.db)
        gerenciador.preparar_lote(docs)

        # Verifica roteamento correto de cada documento
        resultados = {}
        for doc in docs:
            formato = gerenciador.obter_formato(
                int(doc.tipo_documento),
                doc_id=doc.id
            )
            resultados[doc.id] = formato.categoria_nome if formato else None

        # Verificações
        self.assertEqual(resultados["doc_001"], "peticao_inicial")  # Primeira petição = especial
        self.assertEqual(resultados["doc_002"], "peticoes")  # Segunda petição = por código
        self.assertEqual(resultados["doc_003"], "contestacao")  # Contestação
        self.assertEqual(resultados["doc_004"], "nat")  # Nota técnica NAT
        self.assertEqual(resultados["doc_005"], "peticoes")  # Terceira petição = por código

        # Simula extração de variáveis da petição inicial
        variaveis_extraidas = {
            "pi_autor": "JOÃO DA SILVA",
            "pi_reu": "ESTADO DE MATO GROSSO DO SUL",
            "pi_medicamento": "OZEMPIC",
            "pi_valor_causa": 50000,
            "pi_autor_idoso": False
        }

        # Avalia regras determinísticas
        evaluator = DeterministicRuleEvaluator()

        # Regra: medicamento contém "OZEMPIC"
        regra_ozempic = {
            "type": "condition",
            "variable": "pi_medicamento",
            "operator": "contains",
            "value": "OZEMPIC"
        }
        self.assertTrue(evaluator.avaliar(regra_ozempic, variaveis_extraidas))

        # Regra: valor > 100k
        regra_valor = {
            "type": "condition",
            "variable": "pi_valor_causa",
            "operator": "greater_than",
            "value": 100000
        }
        self.assertFalse(evaluator.avaliar(regra_valor, variaveis_extraidas))

        print(f"\n[OK] Pipeline completo para processo {PROCESSO_TESTE}")
        print(f"  - Documentos processados: {len(docs)}")
        print(f"  - Petição inicial identificada: doc_001")
        print(f"  - Variáveis extraídas: {len(variaveis_extraidas)}")


if __name__ == "__main__":
    unittest.main()
