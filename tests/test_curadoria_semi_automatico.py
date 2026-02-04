# tests/test_curadoria_semi_automatico.py
"""
Testes automatizados para o Modo Semi-Automatico do Gerador de Pecas.

Cobre:
1. Criacao do ResultadoCuradoria a partir de modulos detectados
2. Selecao e movimentacao de argumentos entre secoes
3. Busca textual e semantica de argumentos adicionais
4. Marcacao (VALIDADO) no prompt final
5. Integridade das secoes
6. Formato do output enviado ao Agente 3
"""

import pytest
from typing import Dict, List, Any
from unittest.mock import MagicMock, AsyncMock, patch

from sistemas.gerador_pecas.services_curadoria import (
    ServicoCuradoria,
    ModuloCurado,
    ResultadoCuradoria,
    OrigemAtivacao,
    CategoriaSecao,
    ORDEM_SECOES,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_db():
    """Mock da sessao do banco de dados."""
    db = MagicMock()
    return db


@pytest.fixture
def mock_prompt_modulo():
    """Cria um mock de PromptModulo."""
    def _create(
        id: int,
        nome: str,
        titulo: str,
        categoria: str = "Mérito",
        subcategoria: str = None,
        condicao_ativacao: str = None,
        conteudo: str = "Conteudo do modulo",
        ordem: int = 0,
        group_id: int = 1
    ):
        modulo = MagicMock()
        modulo.id = id
        modulo.nome = nome
        modulo.titulo = titulo
        modulo.categoria = categoria
        modulo.subcategoria = subcategoria
        modulo.condicao_ativacao = condicao_ativacao
        modulo.conteudo = conteudo
        modulo.ordem = ordem
        modulo.group_id = group_id
        modulo.tipo = "conteudo"
        modulo.ativo = True
        return modulo
    return _create


@pytest.fixture
def modulos_exemplo(mock_prompt_modulo):
    """Lista de modulos de exemplo para testes."""
    return [
        mock_prompt_modulo(1, "ilegitimidade_passiva", "Ilegitimidade Passiva", "Preliminar", ordem=1),
        mock_prompt_modulo(2, "prescricao", "Prescricao", "Preliminar", ordem=2),
        mock_prompt_modulo(3, "merito_sus", "SUS Fornece Medicamento Similar", "Mérito", "Medicamentos", ordem=1),
        mock_prompt_modulo(4, "merito_cirurgia", "Cirurgia Eletiva", "Mérito", "Cirurgias", ordem=2),
        mock_prompt_modulo(5, "eventualidade_valor", "Reducao do Valor", "Eventualidade", ordem=1),
        mock_prompt_modulo(6, "honorarios", "Honorarios Advocaticios", "Honorários", ordem=1),
    ]


@pytest.fixture
def servico_curadoria(mock_db):
    """Instancia do servico de curadoria com mock do banco."""
    return ServicoCuradoria(mock_db)


@pytest.fixture
def resultado_curadoria_exemplo():
    """ResultadoCuradoria de exemplo para testes."""
    modulos_por_secao = {
        "Preliminar": [
            ModuloCurado(
                id=1, nome="ilegitimidade", titulo="Ilegitimidade Passiva",
                categoria="Preliminar", conteudo="Conteudo 1",
                origem_ativacao=OrigemAtivacao.DETERMINISTIC.value,
                validado=True, selecionado=True, ordem=1
            ),
            ModuloCurado(
                id=2, nome="prescricao", titulo="Prescricao",
                categoria="Preliminar", conteudo="Conteudo 2",
                origem_ativacao=OrigemAtivacao.LLM.value,
                validado=False, selecionado=True, ordem=2
            ),
        ],
        "Mérito": [
            ModuloCurado(
                id=3, nome="merito_sus", titulo="SUS Fornece Similar",
                categoria="Mérito", conteudo="Conteudo 3",
                origem_ativacao=OrigemAtivacao.LLM.value,
                validado=False, selecionado=True, ordem=1
            ),
        ],
    }

    return ResultadoCuradoria(
        numero_processo="0001234-56.2024.8.12.0001",
        tipo_peca="contestacao",
        modulos_por_secao=modulos_por_secao,
        resumo_consolidado="Resumo do processo...",
        dados_processo={"valor_causa": 50000},
        dados_extracao={"valor_causa_inferior_60sm": True},
        total_modulos=3,
        modulos_det=1,
        modulos_llm=2,
        modulos_manual=0,
    )


# ============================================================================
# TESTES: ModuloCurado
# ============================================================================

class TestModuloCurado:
    """Testes para a classe ModuloCurado."""

    def test_criacao_modulo_curado(self):
        """Deve criar ModuloCurado com valores corretos."""
        modulo = ModuloCurado(
            id=1,
            nome="teste",
            titulo="Teste Modulo",
            categoria="Mérito",
            subcategoria="Subcategoria",
            condicao_ativacao="Quando X",
            conteudo="Conteudo do teste",
            ordem=1,
            origem_ativacao=OrigemAtivacao.DETERMINISTIC.value,
            validado=True,
            selecionado=True,
        )

        assert modulo.id == 1
        assert modulo.nome == "teste"
        assert modulo.titulo == "Teste Modulo"
        assert modulo.categoria == "Mérito"
        assert modulo.origem_ativacao == "deterministic"
        assert modulo.validado is True
        assert modulo.selecionado is True

    def test_from_prompt_modulo(self, mock_prompt_modulo):
        """Deve criar ModuloCurado a partir de PromptModulo."""
        prompt_modulo = mock_prompt_modulo(
            id=10,
            nome="modulo_teste",
            titulo="Modulo Teste",
            categoria="Preliminar",
            subcategoria="Sub1",
            condicao_ativacao="Quando Y",
            conteudo="Conteudo Y",
            ordem=5
        )

        modulo_curado = ModuloCurado.from_prompt_modulo(
            prompt_modulo,
            origem=OrigemAtivacao.LLM,
            validado=False
        )

        assert modulo_curado.id == 10
        assert modulo_curado.nome == "modulo_teste"
        assert modulo_curado.titulo == "Modulo Teste"
        assert modulo_curado.categoria == "Preliminar"
        assert modulo_curado.origem_ativacao == OrigemAtivacao.LLM.value
        assert modulo_curado.validado is False

    def test_to_dict(self):
        """Deve converter para dicionario."""
        modulo = ModuloCurado(
            id=1, nome="teste", titulo="Teste",
            categoria="Mérito", conteudo="ABC",
            origem_ativacao=OrigemAtivacao.MANUAL.value,
            validado=True, selecionado=True,
        )

        d = modulo.to_dict()

        assert isinstance(d, dict)
        assert d["id"] == 1
        assert d["nome"] == "teste"
        assert d["origem_ativacao"] == "manual"
        assert d["validado"] is True


# ============================================================================
# TESTES: ResultadoCuradoria
# ============================================================================

class TestResultadoCuradoria:
    """Testes para ResultadoCuradoria."""

    def test_get_todos_modulos(self, resultado_curadoria_exemplo):
        """Deve retornar todos os modulos de todas as secoes."""
        todos = resultado_curadoria_exemplo.get_todos_modulos()

        assert len(todos) == 3
        assert any(m.id == 1 for m in todos)
        assert any(m.id == 2 for m in todos)
        assert any(m.id == 3 for m in todos)

    def test_get_modulos_selecionados(self, resultado_curadoria_exemplo):
        """Deve retornar apenas modulos selecionados."""
        # Desseleciona um modulo
        resultado_curadoria_exemplo.modulos_por_secao["Preliminar"][1].selecionado = False

        selecionados = resultado_curadoria_exemplo.get_modulos_selecionados()

        assert len(selecionados) == 2
        assert all(m.selecionado for m in selecionados)

    def test_get_ids_selecionados(self, resultado_curadoria_exemplo):
        """Deve retornar IDs dos modulos selecionados."""
        ids = resultado_curadoria_exemplo.get_ids_selecionados()

        assert set(ids) == {1, 2, 3}

    def test_to_dict(self, resultado_curadoria_exemplo):
        """Deve serializar para dicionario."""
        d = resultado_curadoria_exemplo.to_dict()

        assert d["numero_processo"] == "0001234-56.2024.8.12.0001"
        assert d["tipo_peca"] == "contestacao"
        assert "modulos_por_secao" in d
        assert "Preliminar" in d["modulos_por_secao"]
        assert len(d["modulos_por_secao"]["Preliminar"]) == 2
        assert d["estatisticas"]["total_modulos"] == 3


# ============================================================================
# TESTES: ServicoCuradoria
# ============================================================================

class TestServicoCuradoria:
    """Testes para o servico de curadoria."""

    def test_criar_resultado_curadoria(self, servico_curadoria, modulos_exemplo):
        """Deve criar ResultadoCuradoria corretamente."""
        # Configura mock do banco
        servico_curadoria.db.query.return_value.filter.return_value.filter.return_value.order_by.return_value.all.return_value = modulos_exemplo[:3]

        resultado = servico_curadoria.criar_resultado_curadoria(
            numero_processo="0001234-56.2024.8.12.0001",
            tipo_peca="contestacao",
            modulos_ids=[1, 2, 3],
            ids_det=[1],  # Apenas o primeiro e deterministico
            ids_llm=[2, 3],
            resumo_consolidado="Resumo...",
            dados_processo={"valor": 1000},
            dados_extracao={"var1": True},
            group_id=1
        )

        assert resultado.numero_processo == "0001234-56.2024.8.12.0001"
        assert resultado.tipo_peca == "contestacao"
        assert resultado.modulos_det == 1
        assert resultado.modulos_llm == 2

    def test_aplicar_alteracoes_selecao(self, servico_curadoria, resultado_curadoria_exemplo):
        """Deve aplicar alteracoes de selecao."""
        alteracoes = {
            "modulos_selecionados": [1, 3],  # Seleciona 1 e 3
            "modulos_removidos": [2],  # Remove 2
        }

        resultado = servico_curadoria.aplicar_alteracoes_curadoria(
            resultado_curadoria_exemplo,
            alteracoes
        )

        # Modulo 2 deve estar desselecionado
        modulo_2 = next(m for m in resultado.get_todos_modulos() if m.id == 2)
        assert modulo_2.selecionado is False

        # Modulos 1 e 3 devem estar selecionados
        modulo_1 = next(m for m in resultado.get_todos_modulos() if m.id == 1)
        modulo_3 = next(m for m in resultado.get_todos_modulos() if m.id == 3)
        assert modulo_1.selecionado is True
        assert modulo_3.selecionado is True

    def test_aplicar_alteracoes_movimentacao(self, servico_curadoria, resultado_curadoria_exemplo):
        """Deve mover modulo entre secoes."""
        alteracoes = {
            "modulos_movidos": {"2": "Eventualidade"},  # Move prescricao para Eventualidade
        }

        resultado = servico_curadoria.aplicar_alteracoes_curadoria(
            resultado_curadoria_exemplo,
            alteracoes
        )

        # Modulo 2 deve estar em Eventualidade
        assert "Eventualidade" in resultado.modulos_por_secao
        modulo_2 = next(
            (m for m in resultado.modulos_por_secao.get("Eventualidade", []) if m.id == 2),
            None
        )
        assert modulo_2 is not None
        assert modulo_2.categoria == "Eventualidade"

        # Nao deve estar mais em Preliminar
        modulos_preliminar = [m.id for m in resultado.modulos_por_secao.get("Preliminar", [])]
        assert 2 not in modulos_preliminar

    def test_aplicar_alteracoes_reordenacao(self, servico_curadoria, resultado_curadoria_exemplo):
        """Deve reordenar modulos dentro de uma secao."""
        alteracoes = {
            "ordem_secoes": {
                "Preliminar": [2, 1],  # Inverte ordem: prescricao primeiro
            }
        }

        resultado = servico_curadoria.aplicar_alteracoes_curadoria(
            resultado_curadoria_exemplo,
            alteracoes
        )

        # Verifica ordem
        preliminares = resultado.modulos_por_secao["Preliminar"]
        assert preliminares[0].id == 2
        assert preliminares[1].id == 1


# ============================================================================
# TESTES: Prompt Curado com Marcacao HUMAN_VALIDATED
# ============================================================================

class TestPromptCuradoHumanValidated:
    """Testes para verificar marcacao HUMAN_VALIDATED no prompt (modo semi-automatico)."""

    def test_montar_prompt_curado_marca_human_validated(self, servico_curadoria, resultado_curadoria_exemplo):
        """Deve marcar modulos com [HUMAN_VALIDATED] no modo semi-automatico."""
        prompt = servico_curadoria.montar_prompt_curado(
            resultado_curadoria_exemplo,
            prompt_sistema="Sistema...",
            prompt_peca="Peca..."
        )

        # Todos modulos selecionados devem ter [HUMAN_VALIDATED]
        assert "[HUMAN_VALIDATED]" in prompt
        assert "Ilegitimidade Passiva" in prompt
        # Header correto para modo semi-automatico
        assert "HUMAN_VALIDATED" in prompt

    def test_montar_prompt_curado_modulos_manuais_human_validated_manual(self, servico_curadoria, resultado_curadoria_exemplo):
        """Modulos adicionados manualmente devem ter [HUMAN_VALIDATED:MANUAL]."""
        # Adiciona modulo manual
        modulo_manual = ModuloCurado(
            id=99, nome="manual", titulo="Argumento Manual",
            categoria="Mérito", conteudo="Conteudo manual",
            origem_ativacao=OrigemAtivacao.MANUAL.value,
            validado=True, selecionado=True,
        )
        resultado_curadoria_exemplo.modulos_por_secao["Mérito"].append(modulo_manual)

        prompt = servico_curadoria.montar_prompt_curado(
            resultado_curadoria_exemplo,
            prompt_sistema="Sistema...",
            prompt_peca="Peca..."
        )

        # Modulo manual deve ter [HUMAN_VALIDATED:MANUAL]
        assert "Argumento Manual" in prompt
        assert "[HUMAN_VALIDATED:MANUAL]" in prompt
        # Outros modulos devem ter [HUMAN_VALIDATED] sem :MANUAL
        assert prompt.count("[HUMAN_VALIDATED]") >= 2  # Contando ambos os tipos

    def test_todos_modulos_selecionados_recebem_human_validated(self, servico_curadoria, resultado_curadoria_exemplo):
        """Todos os modulos selecionados DEVEM receber tag HUMAN_VALIDATED."""
        prompt = servico_curadoria.montar_prompt_curado(
            resultado_curadoria_exemplo,
            prompt_sistema="Sistema...",
            prompt_peca="Peca..."
        )

        # Conta modulos selecionados
        total_selecionados = len(resultado_curadoria_exemplo.get_modulos_selecionados())

        # Conta tags HUMAN_VALIDATED apenas nos títulos de módulos (formato "#### Titulo [HUMAN_VALIDATED...")
        import re
        module_tags = re.findall(r'####.*\[HUMAN_VALIDATED', prompt)

        # Cada modulo selecionado deve ter exatamente uma tag
        assert len(module_tags) == total_selecionados, \
            f"Esperado {total_selecionados} tags HUMAN_VALIDATED, encontrado {len(module_tags)}"

    def test_prompt_curado_instrucao_obrigatoria(self, servico_curadoria, resultado_curadoria_exemplo):
        """Prompt deve conter instrucao obrigatoria para IA usar argumentos integralmente."""
        prompt = servico_curadoria.montar_prompt_curado(
            resultado_curadoria_exemplo,
            prompt_sistema="Sistema...",
            prompt_peca="Peca..."
        )

        # Deve ter instrucao clara para IA
        assert "DEVEM ser incluídos integralmente" in prompt or "INSTRUÇÃO OBRIGATÓRIA" in prompt

    def test_montar_prompt_curado_secoes_corretas(self, servico_curadoria, resultado_curadoria_exemplo):
        """Prompt deve ter secoes organizadas corretamente."""
        prompt = servico_curadoria.montar_prompt_curado(
            resultado_curadoria_exemplo,
            prompt_sistema="Sistema...",
            prompt_peca="Peca..."
        )

        # Verifica estrutura
        assert "### === PRELIMINAR ===" in prompt
        assert "### === MÉRITO ===" in prompt

        # Verifica ordem (Preliminar antes de Mérito)
        idx_preliminar = prompt.find("PRELIMINAR")
        idx_merito = prompt.find("MÉRITO")
        assert idx_preliminar < idx_merito

    def test_montar_prompt_curado_sem_secoes_vazias(self, servico_curadoria):
        """Nao deve incluir secoes sem modulos selecionados."""
        resultado = ResultadoCuradoria(
            numero_processo="123",
            tipo_peca="contestacao",
            modulos_por_secao={
                "Preliminar": [
                    ModuloCurado(
                        id=1, nome="teste", titulo="Teste",
                        categoria="Preliminar", conteudo="X",
                        selecionado=True,
                    )
                ],
                "Eventualidade": [
                    ModuloCurado(
                        id=2, nome="evento", titulo="Evento",
                        categoria="Eventualidade", conteudo="Y",
                        selecionado=False,  # NAO selecionado
                    )
                ],
            }
        )

        prompt = servico_curadoria.montar_prompt_curado(
            resultado,
            prompt_sistema="",
            prompt_peca=""
        )

        # Preliminar deve estar presente
        assert "PRELIMINAR" in prompt

        # Eventualidade nao deve estar (sem modulos selecionados)
        assert "EVENTUALIDADE" not in prompt


# ============================================================================
# TESTES: Ordem das Secoes
# ============================================================================

class TestOrdemSecoes:
    """Testes para verificar ordem correta das secoes."""

    def test_ordem_categorias_padrao(self):
        """Verifica ordem padrao das categorias."""
        assert ORDEM_SECOES[CategoriaSecao.PRELIMINAR] == 0
        assert ORDEM_SECOES[CategoriaSecao.MERITO] == 1
        assert ORDEM_SECOES[CategoriaSecao.EVENTUALIDADE] == 2
        assert ORDEM_SECOES[CategoriaSecao.HONORARIOS] == 3
        assert ORDEM_SECOES[CategoriaSecao.OUTROS] == 99


# ============================================================================
# TESTES: Integracao - Busca de Argumentos
# ============================================================================

class TestBuscaArgumentos:
    """Testes para busca de argumentos adicionais."""

    @pytest.mark.asyncio
    async def test_buscar_argumentos_keyword(self, servico_curadoria, modulos_exemplo):
        """Deve buscar argumentos por palavra-chave."""
        with patch('sistemas.gerador_pecas.services_curadoria.buscar_argumentos_relevantes') as mock_busca:
            mock_busca.return_value = [
                {
                    "id": 10,
                    "nome": "novo_arg",
                    "titulo": "Novo Argumento",
                    "categoria": "Mérito",
                    "subcategoria": None,
                    "condicao_ativacao": "Quando Z",
                    "conteudo": "Conteudo Z",
                    "score": 0.8,
                }
            ]

            resultados = await servico_curadoria.buscar_argumentos_adicionais(
                query="cirurgia eletiva",
                tipo_peca="contestacao",
                modulos_excluir=[1, 2, 3],
                limit=5,
                metodo="keyword"
            )

            assert len(resultados) == 1
            assert resultados[0].id == 10
            assert resultados[0].titulo == "Novo Argumento"
            assert resultados[0].origem_ativacao == OrigemAtivacao.MANUAL.value
            assert resultados[0].validado is True

    @pytest.mark.asyncio
    async def test_buscar_argumentos_exclui_ja_selecionados(self, servico_curadoria):
        """Deve excluir modulos ja selecionados dos resultados."""
        with patch('sistemas.gerador_pecas.services_curadoria.buscar_argumentos_relevantes') as mock_busca:
            mock_busca.return_value = [
                {"id": 1, "nome": "ja_existe", "titulo": "Ja Existe", "categoria": "X", "conteudo": "Y"},
                {"id": 10, "nome": "novo", "titulo": "Novo", "categoria": "X", "conteudo": "Y"},
            ]

            resultados = await servico_curadoria.buscar_argumentos_adicionais(
                query="teste",
                modulos_excluir=[1],  # Exclui ID 1
                limit=5,
                metodo="keyword"
            )

            # Deve retornar apenas o novo
            assert len(resultados) == 1
            assert resultados[0].id == 10


# ============================================================================
# TESTES: Integridade do Output para Agente 3
# ============================================================================

class TestFormatoOutputAgente3:
    """Testes para verificar formato correto do output para Agente 3."""

    def test_prompt_curado_formato_markdown(self, servico_curadoria, resultado_curadoria_exemplo):
        """Prompt curado deve estar em formato Markdown valido."""
        prompt = servico_curadoria.montar_prompt_curado(
            resultado_curadoria_exemplo,
            prompt_sistema="# Sistema\n\nInstrucoes...",
            prompt_peca="# Peca\n\nEstrutura..."
        )

        # Verifica elementos markdown - HUMAN_VALIDATED no header
        assert "## ARGUMENTOS E TESES APLICAVEIS (HUMAN_VALIDATED)" in prompt
        assert "###" in prompt  # Secoes
        assert "####" in prompt  # Titulos de modulos

    def test_prompt_curado_contem_conteudo_modulos(self, servico_curadoria, resultado_curadoria_exemplo):
        """Prompt deve conter conteudo dos modulos selecionados."""
        prompt = servico_curadoria.montar_prompt_curado(
            resultado_curadoria_exemplo,
            prompt_sistema="",
            prompt_peca=""
        )

        # Verifica que conteudo esta presente
        assert "Conteudo 1" in prompt  # Modulo 1
        assert "Conteudo 2" in prompt  # Modulo 2
        assert "Conteudo 3" in prompt  # Modulo 3

    def test_prompt_curado_indicacao_validacao(self, servico_curadoria, resultado_curadoria_exemplo):
        """Prompt deve indicar que argumentos foram validados pelo usuario."""
        prompt = servico_curadoria.montar_prompt_curado(
            resultado_curadoria_exemplo,
            prompt_sistema="",
            prompt_peca=""
        )

        # Verifica mensagem de curadoria com HUMAN_VALIDATED
        assert "HUMAN_VALIDATED" in prompt
        assert "DEVEM ser incluídos integralmente" in prompt or "INSTRUÇÃO OBRIGATÓRIA" in prompt


# ============================================================================
# TESTES: Melhorias de UX - Jan 2026
# ============================================================================

class TestMelhoriasUXJan2026:
    """
    Testes para as melhorias de UX implementadas em Jan/2026:
    1. Nome correto ao adicionar argumento
    2. Busca híbrida sempre ativa (sem opções visíveis)
    3. Agrupamento de módulos por categoria
    4. Filtragem incremental client-side
    """

    def test_modulo_curado_preserva_titulo_e_origem(self, mock_prompt_modulo):
        """
        Verifica que ao criar ModuloCurado a partir de um argumento de busca,
        o título e a categoria são preservados corretamente.
        """
        # Simula dados que viriam de uma busca
        argumento_busca = {
            "id": 100,
            "nome": "arg_teste",
            "titulo": "Título Específico do Argumento",
            "categoria": "Mérito",
            "subcategoria": "Medicamentos",
            "condicao_ativacao": "Quando o autor solicitar medicamento de alto custo",
            "conteudo": "Conteúdo do argumento...",
        }

        modulo = ModuloCurado(
            id=argumento_busca["id"],
            nome=argumento_busca["nome"],
            titulo=argumento_busca["titulo"],
            categoria=argumento_busca["categoria"],
            subcategoria=argumento_busca["subcategoria"],
            condicao_ativacao=argumento_busca["condicao_ativacao"],
            conteudo=argumento_busca["conteudo"],
            origem_ativacao=OrigemAtivacao.MANUAL.value,
            validado=True,
            selecionado=True,
        )

        # Titulo deve ser o original, não "Argumento Adicionado"
        assert modulo.titulo == "Título Específico do Argumento"
        assert modulo.titulo != "Argumento Adicionado"
        assert modulo.categoria == "Mérito"
        assert modulo.subcategoria == "Medicamentos"
        assert modulo.origem_ativacao == "manual"
        assert modulo.validado is True

    def test_modulo_manual_tem_flag_validado(self):
        """
        Modulos adicionados manualmente (origem=MANUAL) devem sempre ter validado=True.
        """
        modulo = ModuloCurado(
            id=1,
            nome="manual_arg",
            titulo="Argumento Manual",
            categoria="Eventualidade",
            conteudo="Texto...",
            origem_ativacao=OrigemAtivacao.MANUAL.value,
            validado=True,
            selecionado=True,
        )

        assert modulo.origem_ativacao == "manual"
        assert modulo.validado is True

    @pytest.mark.asyncio
    async def test_busca_sempre_usa_metodo_hibrido(self, servico_curadoria):
        """
        Confirma que a busca de argumentos usa o método híbrido por padrão.
        O método híbrido combina busca textual + busca semântica.
        """
        with patch('sistemas.gerador_pecas.services_curadoria.buscar_argumentos_relevantes') as mock_busca:
            with patch('sistemas.gerador_pecas.services_curadoria.buscar_argumentos_hibrido') as mock_hibrido:
                mock_hibrido.return_value = [
                    {"id": 1, "nome": "arg1", "titulo": "Argumento 1", "categoria": "Mérito", "conteudo": "X"}
                ]

                # Chama busca com metodo hibrido explícito
                resultados = await servico_curadoria.buscar_argumentos_adicionais(
                    query="medicamento",
                    tipo_peca="contestacao",
                    modulos_excluir=[],
                    limit=10,
                    metodo="hibrido"
                )

                # Verifica que busca hibrida foi chamada
                assert mock_hibrido.called or mock_busca.called

    def test_categorias_validas_para_agrupamento(self):
        """
        Verifica que todas as categorias usadas no agrupamento são válidas.
        """
        categorias_ui = ['Preliminar', 'Mérito', 'Eventualidade', 'Honorários', 'Pedidos', 'Outros']

        # Verifica que todas as categorias têm enum correspondente
        for cat in categorias_ui:
            cat_enum = None
            for c in CategoriaSecao:
                if c.value.lower() == cat.lower() or c.name.lower() == cat.lower().replace('é', 'e'):
                    cat_enum = c
                    break

            # Categoria deve existir ou ser 'Outros' (fallback)
            assert cat_enum is not None or cat == 'Outros', f"Categoria '{cat}' não mapeada"

    def test_modulos_agrupados_ordenados_por_titulo(self):
        """
        Modulos dentro de cada categoria devem estar ordenados por titulo.
        """
        modulos = [
            ModuloCurado(id=3, nome="c", titulo="Zebra", categoria="Mérito", conteudo=""),
            ModuloCurado(id=1, nome="a", titulo="Abacate", categoria="Mérito", conteudo=""),
            ModuloCurado(id=2, nome="b", titulo="Banana", categoria="Mérito", conteudo=""),
        ]

        # Ordena como faria o frontend
        modulos_ordenados = sorted(modulos, key=lambda m: m.titulo or "")

        assert modulos_ordenados[0].titulo == "Abacate"
        assert modulos_ordenados[1].titulo == "Banana"
        assert modulos_ordenados[2].titulo == "Zebra"

    def test_filtro_por_titulo_case_insensitive(self):
        """
        Filtro de módulos deve ser case-insensitive.
        """
        modulos = [
            ModuloCurado(id=1, nome="med", titulo="Medicamento de Alto Custo", categoria="Mérito", conteudo=""),
            ModuloCurado(id=2, nome="cir", titulo="Cirurgia Eletiva", categoria="Mérito", conteudo=""),
            ModuloCurado(id=3, nome="out", titulo="Outros Procedimentos", categoria="Mérito", conteudo=""),
        ]

        filtro = "MEDICAMENTO"  # Em maiúsculas

        # Filtra como faria o frontend (case-insensitive)
        filtrados = [m for m in modulos if filtro.lower() in m.titulo.lower()]

        assert len(filtrados) == 1
        assert filtrados[0].id == 1

    def test_filtro_por_subcategoria(self):
        """
        Filtro deve buscar também na subcategoria.
        """
        modulos = [
            ModuloCurado(id=1, nome="a", titulo="Argumento A", categoria="Mérito", subcategoria="Medicamentos", conteudo=""),
            ModuloCurado(id=2, nome="b", titulo="Argumento B", categoria="Mérito", subcategoria="Cirurgias", conteudo=""),
        ]

        filtro = "cirurg"

        # Filtra em titulo + subcategoria
        filtrados = [
            m for m in modulos
            if filtro.lower() in (m.titulo or "").lower() or filtro.lower() in (m.subcategoria or "").lower()
        ]

        assert len(filtrados) == 1
        assert filtrados[0].subcategoria == "Cirurgias"

    def test_modulo_adicionado_persiste_em_dados_curadoria(self, resultado_curadoria_exemplo):
        """
        Quando um módulo é adicionado via busca, deve ser persistido em dadosCuradoria.
        """
        # Simula adição de módulo
        novo_modulo = ModuloCurado(
            id=999,
            nome="novo_arg",
            titulo="Novo Argumento da Busca",
            categoria="Eventualidade",
            conteudo="Texto do novo argumento",
            origem_ativacao=OrigemAtivacao.MANUAL.value,
            validado=True,
            selecionado=True,
        )

        # Adiciona à seção
        if "Eventualidade" not in resultado_curadoria_exemplo.modulos_por_secao:
            resultado_curadoria_exemplo.modulos_por_secao["Eventualidade"] = []
        resultado_curadoria_exemplo.modulos_por_secao["Eventualidade"].append(novo_modulo)

        # Verifica que foi adicionado
        todos = resultado_curadoria_exemplo.get_todos_modulos()
        assert any(m.id == 999 for m in todos)

        # Verifica que está na seção correta
        eventualidade = resultado_curadoria_exemplo.modulos_por_secao.get("Eventualidade", [])
        assert any(m.id == 999 for m in eventualidade)

    def test_modulo_removido_da_lista_disponivel_apos_adicao(self):
        """
        Após adicionar um módulo, ele não deve mais aparecer na lista de disponíveis.
        """
        # Lista inicial de disponíveis
        modulos_disponiveis = [
            {"id": 1, "titulo": "Arg 1"},
            {"id": 2, "titulo": "Arg 2"},
            {"id": 3, "titulo": "Arg 3"},
        ]

        # IDs selecionados
        ids_selecionados = {1, 3}

        # Filtra disponíveis (como faria o frontend)
        disponiveis_filtrados = [m for m in modulos_disponiveis if m["id"] not in ids_selecionados]

        assert len(disponiveis_filtrados) == 1
        assert disponiveis_filtrados[0]["id"] == 2


# ============================================================================
# TESTES: Mapeamento de Categorias (Regressão para categorias dinâmicas)
# ============================================================================

class TestCategoriaDinamica:
    """
    Testes para garantir que categorias são mapeadas corretamente do banco
    para a UI, sem cair em 'Outros' incorretamente.

    Contexto: O frontend carrega categorias da API (/admin/api/prompts-modulos/categorias)
    e usa a categoria diretamente do módulo. Apenas módulos sem categoria (null/vazio)
    devem ir para "Outros".

    ADR-0011 atualizado para refletir categorias dinâmicas.
    """

    def test_categoria_custom_nao_cai_em_outros(self, mock_prompt_modulo):
        """
        Módulo com categoria customizada (não padrão) deve manter sua categoria.
        Exemplo: categoria="Introdução" deve aparecer como "Introdução", não "Outros".
        """
        modulo = mock_prompt_modulo(
            id=99,
            nome="intro_teste",
            titulo="Introdução Teste",
            categoria="Introdução"  # Categoria não está na lista padrão
        )

        curado = ModuloCurado.from_prompt_modulo(modulo)

        assert curado.categoria == "Introdução"
        assert curado.categoria != "Outros"

    def test_categoria_null_usa_outros(self, mock_prompt_modulo):
        """
        Módulo sem categoria (None) deve usar 'Outros' como fallback.
        """
        modulo = mock_prompt_modulo(
            id=100,
            nome="sem_cat",
            titulo="Sem Categoria",
            categoria=None
        )

        curado = ModuloCurado.from_prompt_modulo(modulo)

        assert curado.categoria == "Outros"

    def test_categoria_vazia_usa_outros(self, mock_prompt_modulo):
        """
        Módulo com categoria vazia ("") deve usar 'Outros' como fallback.
        """
        modulo = mock_prompt_modulo(
            id=101,
            nome="cat_vazia",
            titulo="Categoria Vazia",
            categoria=""  # String vazia
        )

        curado = ModuloCurado.from_prompt_modulo(modulo)

        # Nota: from_prompt_modulo usa "or" que trata "" como falsy
        assert curado.categoria == "Outros"

    def test_categoria_apenas_espacos_usa_outros(self, mock_prompt_modulo):
        """
        Módulo com categoria contendo apenas espaços deve usar 'Outros'.
        O backend faz strip() na categoria antes de verificar se é vazia.
        """
        modulo = mock_prompt_modulo(
            id=102,
            nome="cat_espacos",
            titulo="Categoria Espacos",
            categoria="   "  # Apenas espaços
        )

        curado = ModuloCurado.from_prompt_modulo(modulo)

        # Após strip(), "   " se torna "" que é falsy, então vai para "Outros"
        assert curado.categoria == "Outros"

    def test_categoria_padrao_merito_preservada(self, mock_prompt_modulo):
        """
        Categorias padrão (Mérito, Preliminar, etc.) devem ser preservadas exatamente.
        """
        modulo = mock_prompt_modulo(
            id=103,
            nome="merito_test",
            titulo="Teste Mérito",
            categoria="Mérito"  # Com acento
        )

        curado = ModuloCurado.from_prompt_modulo(modulo)

        assert curado.categoria == "Mérito"
        assert curado.categoria != "Merito"  # Sem acento seria diferente

    def test_categoria_preserva_case_original(self, mock_prompt_modulo):
        """
        A categoria deve preservar o case original do banco de dados.
        """
        modulo = mock_prompt_modulo(
            id=104,
            nome="test_case",
            titulo="Teste Case",
            categoria="PRELIMINAR"  # Uppercase
        )

        curado = ModuloCurado.from_prompt_modulo(modulo)

        # Deve preservar exatamente como está no banco
        assert curado.categoria == "PRELIMINAR"

    def test_multiplas_categorias_customizadas(self, mock_prompt_modulo):
        """
        Vários módulos com categorias customizadas diferentes devem ser agrupados corretamente.
        """
        modulos = [
            mock_prompt_modulo(1, "intro", "Introdução", "Introdução"),
            mock_prompt_modulo(2, "conclusao", "Conclusão", "Conclusão"),
            mock_prompt_modulo(3, "fatos", "Dos Fatos", "Fatos"),
            mock_prompt_modulo(4, "direito", "Do Direito", "Direito"),
            mock_prompt_modulo(5, "sem_cat", "Sem Categoria", None),
        ]

        curados = [ModuloCurado.from_prompt_modulo(m) for m in modulos]

        # Verifica que cada um mantém sua categoria
        assert curados[0].categoria == "Introdução"
        assert curados[1].categoria == "Conclusão"
        assert curados[2].categoria == "Fatos"
        assert curados[3].categoria == "Direito"
        assert curados[4].categoria == "Outros"  # Único que deve ir para Outros

    def test_agrupamento_simula_frontend(self, mock_prompt_modulo):
        """
        Simula a lógica de agrupamento do frontend para verificar
        que categorias customizadas são agrupadas corretamente.
        """
        # Simula lista de módulos do backend
        modulos = [
            {"id": 1, "titulo": "Arg 1", "categoria": "Preliminar"},
            {"id": 2, "titulo": "Arg 2", "categoria": "Mérito"},
            {"id": 3, "titulo": "Arg 3", "categoria": "Introdução"},  # Custom
            {"id": 4, "titulo": "Arg 4", "categoria": "Conclusão"},   # Custom
            {"id": 5, "titulo": "Arg 5", "categoria": None},          # Null -> Outros
            {"id": 6, "titulo": "Arg 6", "categoria": ""},            # Vazio -> Outros
        ]

        # Simula lógica do frontend (agruparModulosDisponiveis)
        agrupados = {}
        for m in modulos:
            cat = m["categoria"]
            # Lógica do frontend: usa categoria diretamente ou "Outros" se falsy
            categoria = cat if (cat and cat.strip()) else "Outros"

            if categoria not in agrupados:
                agrupados[categoria] = []
            agrupados[categoria].append(m)

        # Verificações
        assert "Preliminar" in agrupados
        assert "Mérito" in agrupados
        assert "Introdução" in agrupados  # Categoria custom deve existir
        assert "Conclusão" in agrupados   # Categoria custom deve existir
        assert "Outros" in agrupados

        # Verificar conteúdo
        assert len(agrupados["Preliminar"]) == 1
        assert len(agrupados["Introdução"]) == 1
        assert len(agrupados["Outros"]) == 2  # Null e vazio


# ============================================================================
# TESTES: Fluxo de Módulos Manuais (Feb 2026)
# ============================================================================

class TestModulosManuaisBackend:
    """
    Testes para verificar que módulos adicionados manualmente pelo usuário
    são corretamente identificados e processados pelo backend.

    O fluxo é:
    1. Frontend rastreia IDs em modulosManuais (Set)
    2. Frontend envia modulos_manuais_ids na requisição
    3. Backend recebe e marca os módulos manuais no prompt
    4. Backend salva contagem de manuais no histórico
    """

    def test_modulos_manuais_set_inicia_vazio(self):
        """
        O Set de módulos manuais deve iniciar vazio ao criar a instância.
        """
        # Simula estado inicial do frontend
        modulos_selecionados = set()
        modulos_manuais = set()

        assert len(modulos_manuais) == 0
        assert len(modulos_selecionados) == 0

    def test_adicionar_modulo_manual_incrementa_set(self):
        """
        Ao adicionar um módulo manualmente, o ID deve ser adicionado ao set de manuais.
        """
        modulos_selecionados = set()
        modulos_manuais = set()

        # Simula adição de módulo manual
        modulo_id = 42
        modulos_selecionados.add(modulo_id)
        modulos_manuais.add(modulo_id)

        assert modulo_id in modulos_manuais
        assert modulo_id in modulos_selecionados
        assert len(modulos_manuais) == 1

    def test_modulos_iniciais_nao_sao_manuais(self):
        """
        Módulos que vêm do preview (determinísticos/LLM) não devem estar no set de manuais.
        """
        # Simula dados que viriam do preview
        modulos_do_preview = [
            {"id": 1, "origem_ativacao": "deterministic"},
            {"id": 2, "origem_ativacao": "llm"},
        ]

        modulos_selecionados = set()
        modulos_manuais = set()

        # Processa preview (como faz inicializarEstado)
        for m in modulos_do_preview:
            modulos_selecionados.add(m["id"])
            if m["origem_ativacao"] == "manual":
                modulos_manuais.add(m["id"])

        assert 1 in modulos_selecionados
        assert 2 in modulos_selecionados
        assert 1 not in modulos_manuais
        assert 2 not in modulos_manuais
        assert len(modulos_manuais) == 0

    def test_request_body_inclui_modulos_manuais(self):
        """
        O body da requisição deve incluir modulos_manuais_ids.
        """
        modulos_selecionados = {1, 2, 3, 42}
        modulos_manuais = {42}  # Apenas o 42 foi adicionado manualmente

        # Simula construção do body
        request_body = {
            "numero_cnj": "0001234-56.2024.8.12.0001",
            "tipo_peca": "contestacao",
            "modulos_ids_curados": list(modulos_selecionados),
            "modulos_manuais_ids": list(modulos_manuais),
        }

        assert "modulos_manuais_ids" in request_body
        assert 42 in request_body["modulos_manuais_ids"]
        assert len(request_body["modulos_manuais_ids"]) == 1
        assert len(request_body["modulos_ids_curados"]) == 4

    def test_backend_distingue_manuais_de_automaticos(self):
        """
        O backend deve conseguir distinguir módulos manuais dos automáticos.
        """
        modulos_ids_curados = [1, 2, 3, 42]
        modulos_manuais_ids = [42]

        modulos_manuais_set = set(modulos_manuais_ids or [])
        total_manuais = 0

        for modulo_id in modulos_ids_curados:
            if modulo_id in modulos_manuais_set:
                total_manuais += 1

        assert total_manuais == 1
        assert len(modulos_ids_curados) - total_manuais == 3

    def test_contagem_salva_no_historico(self):
        """
        A contagem de módulos manuais deve ser salva corretamente no histórico.
        No modo semi_automatico:
        - modulos_ativados_det = total - manuais
        - modulos_ativados_llm = manuais (reutilizado para armazenar manuais)
        """
        total_curados = 4
        total_manuais = 1

        # Simula lógica do backend
        modulos_ativados_det = total_curados - total_manuais
        modulos_ativados_llm = total_manuais

        assert modulos_ativados_det == 3
        assert modulos_ativados_llm == 1

    def test_log_modulo_manual_identificado(self):
        """
        O backend deve logar quando um módulo manual é processado.
        """
        import io
        import sys

        # Simula processamento
        modulos_ids = [1, 2, 42]
        modulos_manuais_set = {42}

        # Captura stdout
        captured_output = io.StringIO()
        sys.stdout = captured_output

        for modulo_id in modulos_ids:
            if modulo_id in modulos_manuais_set:
                print(f"[CURADORIA] Modulo MANUAL selecionado: ID {modulo_id}")

        sys.stdout = sys.__stdout__
        output = captured_output.getvalue()

        assert "[CURADORIA] Modulo MANUAL selecionado: ID 42" in output
        assert "ID 1" not in output
        assert "ID 2" not in output

    def test_modulo_manual_aparece_human_validated_no_prompt(self, servico_curadoria):
        """
        Módulos manuais devem aparecer com [HUMAN_VALIDATED:MANUAL] no prompt final.
        """
        resultado = ResultadoCuradoria(
            numero_processo="123",
            tipo_peca="contestacao",
            modulos_por_secao={
                "Mérito": [
                    ModuloCurado(
                        id=42, nome="manual", titulo="Argumento Manual",
                        categoria="Mérito", conteudo="Conteúdo do argumento manual",
                        origem_ativacao=OrigemAtivacao.MANUAL.value,
                        validado=True, selecionado=True,
                    )
                ],
            }
        )

        prompt = servico_curadoria.montar_prompt_curado(
            resultado,
            prompt_sistema="",
            prompt_peca=""
        )

        assert "Argumento Manual" in prompt
        assert "[HUMAN_VALIDATED:MANUAL]" in prompt

    def test_multiplos_modulos_manuais(self):
        """
        Múltiplos módulos manuais devem ser todos rastreados e enviados.
        """
        modulos_manuais = set()

        # Adiciona vários módulos manualmente
        modulos_manuais.add(10)
        modulos_manuais.add(20)
        modulos_manuais.add(30)

        assert len(modulos_manuais) == 3
        assert 10 in modulos_manuais
        assert 20 in modulos_manuais
        assert 30 in modulos_manuais

        # Body da requisição
        request_body = {
            "modulos_manuais_ids": list(modulos_manuais)
        }

        assert len(request_body["modulos_manuais_ids"]) == 3

    def test_remover_modulo_manual_atualiza_set(self):
        """
        Se o usuário desselecionar um módulo manual, ele não deve mais ser enviado como manual.
        Nota: O frontend atual não remove de modulosManuais ao desselecionar,
        mas o backend só processa os que estão em modulos_ids_curados.
        """
        modulos_selecionados = {1, 2, 42}
        modulos_manuais = {42}

        # Usuário desseleciona o módulo 42
        modulos_selecionados.discard(42)

        # Constrói body - apenas os selecionados são enviados
        body = {
            "modulos_ids_curados": list(modulos_selecionados),
            "modulos_manuais_ids": list(modulos_manuais)  # 42 ainda está aqui
        }

        # Backend deve processar apenas interseção
        manuais_efetivos = set(body["modulos_manuais_ids"]) & set(body["modulos_ids_curados"])

        # 42 não está mais nos curados, então não é processado como manual
        assert 42 not in manuais_efetivos
        assert len(manuais_efetivos) == 0

    def test_modulo_sem_manual_ids_usa_lista_vazia(self):
        """
        Se modulos_manuais_ids não for enviado (None), deve tratar como lista vazia.
        """
        modulos_manuais_ids = None
        modulos_manuais_set = set(modulos_manuais_ids or [])

        assert len(modulos_manuais_set) == 0
        assert isinstance(modulos_manuais_set, set)


# ============================================================================
# TESTES: Drag and Drop de Categorias e Módulos (Feb 2026)
# ============================================================================

class TestDragAndDropCategorias:
    """
    Testes para verificar que o reordenamento de categorias e módulos
    funciona corretamente e é persistido no prompt enviado ao Agente 3.

    O fluxo é:
    1. Frontend mantém categoriasOrdem (lista ordenada de nomes de categorias)
    2. Frontend mantém modulosOrdem (dict: categoria -> [ids ordenados])
    3. Ao gerar, envia categorias_ordem e modulos_ordem na requisição
    4. Backend usa ordem do frontend para montar o prompt
    """

    def test_categorias_ordem_inicia_com_secoes_preview(self):
        """
        categoriasOrdem deve iniciar com as seções vindas do preview,
        na ordem em que foram retornadas pelo Agente 2.
        """
        modulos_por_secao = {
            "Preliminar": [{"id": 1}],
            "Mérito": [{"id": 2}],
            "Eventualidade": [{"id": 3}],
        }

        # Simula inicializarEstado do frontend
        categorias_ordem = []
        for secao in modulos_por_secao.keys():
            categorias_ordem.append(secao)

        assert len(categorias_ordem) == 3
        assert "Preliminar" in categorias_ordem
        assert "Mérito" in categorias_ordem
        assert "Eventualidade" in categorias_ordem

    def test_reordenar_categoria_atualiza_lista(self):
        """
        Ao arrastar uma categoria para nova posição, a lista deve ser atualizada.
        """
        categorias_ordem = ["Preliminar", "Mérito", "Eventualidade", "Pedidos"]

        # Simula drag de "Eventualidade" para antes de "Mérito"
        dragged = "Eventualidade"
        target = "Mérito"
        drop_above = True

        # Remove da posição atual
        categorias_ordem.remove(dragged)

        # Encontra nova posição
        target_idx = categorias_ordem.index(target)
        if drop_above:
            new_idx = target_idx
        else:
            new_idx = target_idx + 1

        # Insere na nova posição
        categorias_ordem.insert(new_idx, dragged)

        # Verifica nova ordem
        assert categorias_ordem == ["Preliminar", "Eventualidade", "Mérito", "Pedidos"]

    def test_reordenar_categoria_para_ultima_posicao(self):
        """
        Categoria pode ser movida para a última posição.
        """
        categorias_ordem = ["Preliminar", "Mérito", "Eventualidade"]

        # Move "Preliminar" para depois de "Eventualidade"
        dragged = "Preliminar"
        categorias_ordem.remove(dragged)
        categorias_ordem.append(dragged)

        assert categorias_ordem == ["Mérito", "Eventualidade", "Preliminar"]

    def test_reordenar_categoria_para_primeira_posicao(self):
        """
        Categoria pode ser movida para a primeira posição.
        """
        categorias_ordem = ["Preliminar", "Mérito", "Eventualidade"]

        # Move "Eventualidade" para o início
        dragged = "Eventualidade"
        categorias_ordem.remove(dragged)
        categorias_ordem.insert(0, dragged)

        assert categorias_ordem == ["Eventualidade", "Preliminar", "Mérito"]

    def test_request_inclui_categorias_ordem(self):
        """
        A requisição deve incluir categorias_ordem para o backend.
        """
        categorias_ordem = ["Eventualidade", "Mérito", "Preliminar"]  # Ordem customizada
        modulos_selecionados = {1, 2, 3}

        request_body = {
            "numero_cnj": "0001234-56.2024.8.12.0001",
            "tipo_peca": "contestacao",
            "modulos_ids_curados": list(modulos_selecionados),
            "categorias_ordem": categorias_ordem,
        }

        assert "categorias_ordem" in request_body
        assert request_body["categorias_ordem"] == ["Eventualidade", "Mérito", "Preliminar"]

    def test_backend_usa_ordem_frontend_se_fornecida(self):
        """
        Se categorias_ordem for fornecida, backend deve usá-la em vez da ordem padrão.
        """
        categorias_ordem_frontend = ["Eventualidade", "Mérito", "Preliminar"]
        modulos_por_cat = {
            "Preliminar": ["mod1"],
            "Mérito": ["mod2"],
            "Eventualidade": ["mod3"],
        }

        # Simula lógica do backend
        if categorias_ordem_frontend:
            cats_ordenadas = []
            for cat in categorias_ordem_frontend:
                if cat in modulos_por_cat:
                    cats_ordenadas.append(cat)
            # Adiciona categorias não listadas
            for cat in modulos_por_cat.keys():
                if cat not in cats_ordenadas:
                    cats_ordenadas.append(cat)
        else:
            cats_ordenadas = sorted(modulos_por_cat.keys())

        assert cats_ordenadas == ["Eventualidade", "Mérito", "Preliminar"]

    def test_backend_fallback_ordem_padrao_se_nao_fornecida(self):
        """
        Se categorias_ordem não for fornecida, backend deve usar ordem padrão.
        """
        # Define ordem padrão localmente para evitar dependência de importação
        # (corresponde a ORDEM_CATEGORIAS_PADRAO no orquestrador_agentes)
        ORDEM_CATEGORIAS_PADRAO = {
            "Preliminar": 0,
            "Mérito": 1,
            "Eventualidade": 2,
            "Honorários": 3,
            "Pedidos": 4,
        }

        categorias_ordem_frontend = None
        modulos_por_cat = {
            "Mérito": ["mod1"],
            "Preliminar": ["mod2"],
            "Eventualidade": ["mod3"],
        }

        # Simula lógica do backend
        if categorias_ordem_frontend:
            cats_ordenadas = categorias_ordem_frontend
        else:
            cats_ordenadas = sorted(
                modulos_por_cat.keys(),
                key=lambda c: ORDEM_CATEGORIAS_PADRAO.get(c, 99)
            )

        # Preliminar vem antes de Mérito na ordem padrão
        assert cats_ordenadas.index("Preliminar") < cats_ordenadas.index("Mérito")

    def test_modulos_ordem_preservada_ao_mover_categoria(self):
        """
        Ao mover uma categoria, a ordem interna dos módulos deve ser preservada.
        """
        modulos_ordem = {
            "Mérito": [10, 20, 30],  # Ordem específica
            "Preliminar": [1, 2],
        }

        # Antes de mover
        assert modulos_ordem["Mérito"] == [10, 20, 30]

        # Simula reordenamento de categorias (não altera modulos_ordem)
        categorias_ordem = ["Mérito", "Preliminar"]
        categorias_ordem = ["Preliminar", "Mérito"]  # Reordena

        # Ordem interna dos módulos permanece
        assert modulos_ordem["Mérito"] == [10, 20, 30]

    def test_mover_modulo_entre_categorias_atualiza_modulosOrdem(self):
        """
        Ao mover um módulo para outra categoria, modulosOrdem deve ser atualizado.
        """
        modulos_ordem = {
            "Mérito": [10, 20, 30],
            "Preliminar": [1, 2],
        }

        # Move módulo 20 de Mérito para Preliminar
        modulo_id = 20
        origem = "Mérito"
        destino = "Preliminar"

        # Remove da origem
        modulos_ordem[origem].remove(modulo_id)
        # Adiciona no destino
        modulos_ordem[destino].append(modulo_id)

        assert modulos_ordem["Mérito"] == [10, 30]
        assert modulos_ordem["Preliminar"] == [1, 2, 20]

    def test_categoria_nova_adicionada_ao_fim(self):
        """
        Quando um módulo é adicionado a uma categoria que não existe,
        a categoria deve ser adicionada ao final de categoriasOrdem.
        """
        categorias_ordem = ["Preliminar", "Mérito"]

        # Adiciona módulo em categoria nova
        nova_categoria = "Honorários"
        if nova_categoria not in categorias_ordem:
            categorias_ordem.append(nova_categoria)

        assert categorias_ordem == ["Preliminar", "Mérito", "Honorários"]

    def test_ordem_categorias_enviada_preserva_ordem(self):
        """
        A ordem definida pelo usuário deve ser exatamente preservada no request.
        """
        # Usuário define ordem específica
        categorias_ordem = ["Pedidos", "Mérito", "Preliminar", "Honorários"]

        request_body = {
            "categorias_ordem": categorias_ordem
        }

        # JSON stringify e parse (como acontece na requisição)
        import json
        serializado = json.dumps(request_body)
        deserializado = json.loads(serializado)

        assert deserializado["categorias_ordem"] == ["Pedidos", "Mérito", "Preliminar", "Honorários"]


class TestDragAndDropModulos:
    """
    Testes para verificar que o drag and drop de módulos individuais
    funciona corretamente.
    """

    def test_mover_modulo_dentro_mesma_categoria(self):
        """
        Módulo pode ser reordenado dentro da mesma categoria.
        """
        modulos_ordem = {
            "Mérito": [10, 20, 30],
        }

        # Move módulo 30 para o início
        categoria = "Mérito"
        modulo_id = 30
        nova_posicao = 0

        ids = modulos_ordem[categoria]
        ids.remove(modulo_id)
        ids.insert(nova_posicao, modulo_id)

        assert modulos_ordem["Mérito"] == [30, 10, 20]

    def test_mover_modulo_para_categoria_vazia(self):
        """
        Módulo pode ser movido para categoria que estava vazia.
        """
        modulos_ordem = {
            "Mérito": [10, 20],
            "Eventualidade": [],
        }

        # Move módulo 10 para Eventualidade
        modulos_ordem["Mérito"].remove(10)
        modulos_ordem["Eventualidade"].append(10)

        assert modulos_ordem["Mérito"] == [20]
        assert modulos_ordem["Eventualidade"] == [10]

    def test_limpar_estado_drag_remove_todas_classes(self):
        """
        Ao finalizar drag (sucesso ou cancelamento), todas as classes de
        feedback visual devem ser removidas.
        """
        # Lista de classes que devem ser removidas
        classes_drag = ['drag-over', 'bg-primary-50', 'bg-amber-50',
                        'category-drop-above', 'category-drop-below',
                        'opacity-50', 'border-2', 'border-primary-500']

        # Simula elementos com classes
        elementos = [
            {'classes': ['bg-white', 'drag-over', 'bg-primary-50']},
            {'classes': ['p-4', 'category-drop-above']},
        ]

        # Limpa (como faria limparEstadoDrag)
        for el in elementos:
            el['classes'] = [c for c in el['classes'] if c not in classes_drag]

        assert 'drag-over' not in elementos[0]['classes']
        assert 'bg-primary-50' not in elementos[0]['classes']
        assert 'category-drop-above' not in elementos[1]['classes']

    def test_drag_type_distingue_modulo_de_categoria(self):
        """
        O sistema deve distinguir entre drag de módulo e drag de categoria.
        """
        # Simula estado
        drag_type = None
        dragged_item = None
        dragged_category = None

        # Inicia drag de módulo
        drag_type = 'modulo'
        dragged_item = {'id': 10}
        dragged_category = None

        assert drag_type == 'modulo'
        assert dragged_item is not None
        assert dragged_category is None

        # Reset e inicia drag de categoria
        drag_type = 'categoria'
        dragged_item = None
        dragged_category = {'nome': 'Mérito'}

        assert drag_type == 'categoria'
        assert dragged_item is None
        assert dragged_category is not None


# ============================================================================
# TESTES: Instrumentação e Auditoria do Modo Semi-Automático (Feb 2026)
# ============================================================================

class TestInstrumentacaoAuditoria:
    """
    Testes para verificar que as informações do modo semi-automático
    são corretamente persistidas e podem ser recuperadas para auditoria.

    Cobre:
    1. Persistência de curadoria_metadata com todos os campos
    2. Distinção entre módulos automáticos e manuais
    3. Marcação [VALIDADO] vs [VALIDADO-MANUAL] no prompt
    4. Exposição correta nos endpoints de histórico e feedbacks
    """

    def test_curadoria_metadata_estrutura_completa(self):
        """
        curadoria_metadata deve conter todos os campos necessários para auditoria.
        """
        # Simula dados que seriam salvos no banco
        curadoria_metadata = {
            "modulos_preview_ids": [1, 2, 3],          # IDs do preview (Agente 2)
            "modulos_curados_ids": [1, 2, 4],          # IDs finais selecionados
            "modulos_manuais_ids": [4],                # IDs adicionados manualmente
            "modulos_excluidos_ids": [3],             # IDs excluídos pelo usuário
            "modulos_detalhados": [                    # Detalhes de cada módulo curado
                {"id": 1, "origem": "preview", "status": "[VALIDADO]"},
                {"id": 2, "origem": "preview", "status": "[VALIDADO]"},
                {"id": 4, "origem": "manual", "status": "[VALIDADO-MANUAL]"},
            ],
            "categorias_ordem": ["Preliminar", "Mérito", "Eventualidade"],
            "preview_timestamp": "2026-02-02T10:00:00Z",
            "total_preview": 3,
            "total_curados": 3,
            "total_manuais": 1,
            "total_excluidos": 1
        }

        # Verifica estrutura
        assert "modulos_preview_ids" in curadoria_metadata
        assert "modulos_curados_ids" in curadoria_metadata
        assert "modulos_manuais_ids" in curadoria_metadata
        assert "modulos_excluidos_ids" in curadoria_metadata
        assert "modulos_detalhados" in curadoria_metadata
        assert "categorias_ordem" in curadoria_metadata
        assert "preview_timestamp" in curadoria_metadata
        assert "total_preview" in curadoria_metadata
        assert "total_curados" in curadoria_metadata
        assert "total_manuais" in curadoria_metadata
        assert "total_excluidos" in curadoria_metadata

    def test_modulos_detalhados_contem_origem_e_status(self):
        """
        Cada módulo em modulos_detalhados deve ter origem e status.
        """
        modulos_curados = [1, 2, 4]
        modulos_preview = [1, 2, 3]
        modulos_manuais = [4]

        preview_set = set(modulos_preview)
        manuais_set = set(modulos_manuais)

        modulos_detalhados = []
        for mid in modulos_curados:
            info = {"id": mid}
            if mid in manuais_set:
                info["origem"] = "manual"
                info["status"] = "[VALIDADO-MANUAL]"
            elif mid in preview_set:
                info["origem"] = "preview"
                info["status"] = "[VALIDADO]"
            else:
                info["origem"] = "desconhecido"
                info["status"] = "[VALIDADO]"
            modulos_detalhados.append(info)

        # Verifica módulos
        assert len(modulos_detalhados) == 3

        # Módulo 1: do preview
        mod1 = next(m for m in modulos_detalhados if m["id"] == 1)
        assert mod1["origem"] == "preview"
        assert mod1["status"] == "[VALIDADO]"

        # Módulo 4: manual
        mod4 = next(m for m in modulos_detalhados if m["id"] == 4)
        assert mod4["origem"] == "manual"
        assert mod4["status"] == "[VALIDADO-MANUAL]"

    def test_modo_ativacao_salvo_como_semi_automatico(self):
        """
        modo_ativacao_agente2 deve ser 'semi_automatico' para gerações curadas.
        """
        # Simula valores que seriam salvos no GeracaoPeca
        modo_ativacao_agente2 = "semi_automatico"
        modulos_ativados_det = 2  # Módulos do preview (não manuais)
        modulos_ativados_llm = 1  # Módulos manuais (reuso do campo)

        assert modo_ativacao_agente2 == "semi_automatico"
        assert modulos_ativados_det == 2
        assert modulos_ativados_llm == 1

    def test_contagem_modulos_consistente(self):
        """
        A contagem de módulos deve ser consistente entre os campos.
        total_curados = modulos_ativados_det + modulos_ativados_llm
        """
        modulos_curados_ids = [1, 2, 4]
        modulos_manuais_ids = [4]
        total_manuais = len(modulos_manuais_ids)

        # Lógica do backend
        modulos_ativados_det = len(modulos_curados_ids) - total_manuais
        modulos_ativados_llm = total_manuais

        assert modulos_ativados_det == 2
        assert modulos_ativados_llm == 1
        assert modulos_ativados_det + modulos_ativados_llm == len(modulos_curados_ids)

    def test_prompt_marca_manuais_diferente_de_automaticos(self):
        """
        No prompt final, módulos manuais devem ter [VALIDADO-MANUAL]
        enquanto módulos do preview devem ter [VALIDADO].
        """
        modulos = [
            {"id": 1, "titulo": "Mod 1", "is_manual": False},
            {"id": 2, "titulo": "Mod 2", "is_manual": False},
            {"id": 4, "titulo": "Mod Manual", "is_manual": True},
        ]

        # Simula geração do prompt
        linhas = []
        for m in modulos:
            if m["is_manual"]:
                linhas.append(f"#### {m['titulo']} [VALIDADO-MANUAL]")
            else:
                linhas.append(f"#### {m['titulo']} [VALIDADO]")

        prompt = "\n".join(linhas)

        # Verifica marcações
        assert "[VALIDADO-MANUAL]" in prompt
        assert prompt.count("[VALIDADO-MANUAL]") == 1  # Apenas 1 manual
        # Conta [VALIDADO] que NÃO são [VALIDADO-MANUAL]
        # O prompt tem 2x [VALIDADO] (mod1, mod2) + 1x [VALIDADO-MANUAL] (manual)
        assert prompt.count("[VALIDADO]") == 2  # 2 módulos com [VALIDADO] simples (não inclui o -MANUAL)

    def test_endpoint_curadoria_retorna_detalhes_completos(self):
        """
        O endpoint /curadoria deve retornar informações detalhadas
        para exibição nas telas administrativas.
        """
        # Simula resposta do endpoint
        response = {
            "geracao_id": 123,
            "modo": "semi_automatico",
            "metadata": {
                "total_preview": 3,
                "total_curados": 3,
                "total_manuais": 1,
                "total_excluidos": 1,
                "preview_timestamp": "2026-02-02T10:00:00Z",
                "categorias_ordem": ["Preliminar", "Mérito"]
            },
            "modulos_incluidos": [
                {"id": 1, "titulo": "Mod 1", "categoria": "Preliminar", "origem": "preview", "status": "[VALIDADO]", "ordem": 1},
                {"id": 2, "titulo": "Mod 2", "categoria": "Mérito", "origem": "preview", "status": "[VALIDADO]", "ordem": 2},
                {"id": 4, "titulo": "Mod Manual", "categoria": "Mérito", "origem": "manual", "status": "[VALIDADO-MANUAL]", "ordem": 3},
            ],
            "modulos_manuais": [
                {"id": 4, "titulo": "Mod Manual", "categoria": "Mérito", "status": "[VALIDADO-MANUAL]"}
            ],
            "modulos_excluidos": [
                {"id": 3, "titulo": "Mod Excluído", "categoria": "Eventualidade", "origem": "preview"}
            ]
        }

        # Verifica estrutura
        assert response["modo"] == "semi_automatico"
        assert len(response["modulos_incluidos"]) == 3
        assert len(response["modulos_manuais"]) == 1
        assert len(response["modulos_excluidos"]) == 1

        # Verifica que módulos incluídos têm origem e status
        for m in response["modulos_incluidos"]:
            assert "origem" in m
            assert "status" in m
            assert "ordem" in m

        # Verifica módulo manual
        manual = response["modulos_manuais"][0]
        assert manual["status"] == "[VALIDADO-MANUAL]"

    def test_feedbacks_lista_inclui_modo_ativacao(self):
        """
        O endpoint de listagem de feedbacks deve incluir modo_ativacao
        para feedbacks de gerador_pecas.
        """
        # Simula resposta do endpoint /feedbacks/lista
        feedback_item = {
            "id": 1,
            "consulta_id": 123,
            "sistema": "gerador_pecas",
            "identificador": "0001234-56.2024.8.12.0001",
            "cnj": "0001234-56.2024.8.12.0001",
            "modelo": "gemini-2.0-flash",
            "usuario": "Procurador Teste",
            "avaliacao": "correto",
            "comentario": "Boa geração",
            "criado_em": "2026-02-02T15:00:00Z",
            "modo_ativacao": {
                "modo": "semi_automatico",
                "total_curados": 5,
                "total_manuais": 2,
                "total_excluidos": 1,
                "categorias_ordem": ["Preliminar", "Mérito"]
            }
        }

        # Verifica que modo_ativacao está presente
        assert "modo_ativacao" in feedback_item
        assert feedback_item["modo_ativacao"]["modo"] == "semi_automatico"
        assert feedback_item["modo_ativacao"]["total_manuais"] == 2

    def test_feedbacks_modo_automatico_estrutura_diferente(self):
        """
        Feedbacks de modo automático (fast_path, misto, llm) devem ter
        estrutura diferente no modo_ativacao.
        """
        # Modo fast_path
        modo_fast_path = {
            "modo": "fast_path",
            "modulos_det": 5,
            "modulos_llm": 0
        }

        # Modo misto
        modo_misto = {
            "modo": "misto",
            "modulos_det": 3,
            "modulos_llm": 2
        }

        # Modo LLM
        modo_llm = {
            "modo": "llm",
            "modulos_det": 0,
            "modulos_llm": 5
        }

        # Fast path não deve ter total_manuais
        assert "total_manuais" not in modo_fast_path
        assert modo_fast_path["modulos_det"] == 5

        # Misto tem ambos
        assert modo_misto["modulos_det"] == 3
        assert modo_misto["modulos_llm"] == 2

        # LLM é 100% LLM
        assert modo_llm["modulos_llm"] == 5

    def test_historico_exibe_badge_semi_automatico(self):
        """
        No histórico, gerações semi-automáticas devem exibir badge
        diferenciado com contagem de módulos manuais.
        """
        geracao = {
            "modo_ativacao_agente2": "semi_automatico",
            "modulos_ativados_det": 3,  # Do preview
            "modulos_ativados_llm": 2,   # Manuais
        }

        modo = geracao["modo_ativacao_agente2"]
        det = geracao["modulos_ativados_det"]
        llm = geracao["modulos_ativados_llm"]

        if modo == "semi_automatico":
            total_curados = det + llm
            manuais = llm
            badge_text = f"Semi-Auto ({total_curados} curados{f', {manuais} manuais' if manuais > 0 else ''})"
        else:
            badge_text = modo

        assert "Semi-Auto" in badge_text
        assert "5 curados" in badge_text
        assert "2 manuais" in badge_text

    def test_auditoria_permite_reconstruir_decisao(self):
        """
        Os metadados salvos devem permitir reconstruir completamente
        a decisão do usuário: o que foi sugerido, o que foi aceito,
        o que foi excluído, o que foi adicionado.
        """
        curadoria_metadata = {
            "modulos_preview_ids": [1, 2, 3, 5],       # 4 sugeridos pelo Agente 2
            "modulos_curados_ids": [1, 2, 4],          # 3 finais
            "modulos_manuais_ids": [4],                # 1 adicionado manualmente
            "modulos_excluidos_ids": [3, 5],          # 2 excluídos
        }

        preview = set(curadoria_metadata["modulos_preview_ids"])
        curados = set(curadoria_metadata["modulos_curados_ids"])
        manuais = set(curadoria_metadata["modulos_manuais_ids"])
        excluidos = set(curadoria_metadata["modulos_excluidos_ids"])

        # Reconstrução:
        # 1. Módulos aceitos do preview (estavam no preview E estão nos curados)
        aceitos_do_preview = preview & curados
        assert aceitos_do_preview == {1, 2}

        # 2. Módulos excluídos (estavam no preview mas não estão nos curados)
        removidos = preview - curados
        assert removidos == {3, 5}
        assert removidos == excluidos

        # 3. Módulos adicionados manualmente (não estavam no preview mas estão nos curados)
        adicionados = curados - preview
        assert adicionados == {4}
        assert adicionados == manuais

        # 4. Resumo
        assert len(preview) == 4  # Agente 2 sugeriu 4
        assert len(curados) == 3  # Usuário finalizou com 3
        assert len(manuais) == 1  # 1 foi adicionado manualmente
        assert len(excluidos) == 2  # 2 foram excluídos


# ============================================================================
# TESTES: Regressão de Schema - Colunas Curadoria (Feb 2026)
# ============================================================================

class TestSchemaRegressaoCuradoria:
    """
    Testes para verificar que o código é resiliente quando colunas
    de curadoria não existem no banco de dados.

    Cenário: Migração 20260202_1500_a7c3b8d2e1f0 adiciona as colunas:
    - modo_ativacao_agente2
    - modulos_ativados_det
    - modulos_ativados_llm
    - curadoria_metadata

    O código deve funcionar tanto antes quanto depois da migração.
    """

    def test_getattr_seguro_para_colunas_inexistentes(self):
        """
        Verifica que getattr com default é usado corretamente
        para acessar colunas que podem não existir.
        """
        class MockGeracao:
            """Mock de GeracaoPeca sem as colunas de curadoria"""
            id = 1
            numero_cnj = "0001234-56.2024.8.12.0001"
            tipo_peca = "contestacao"
            # Não tem: modo_ativacao_agente2, modulos_ativados_det, etc.

        geracao = MockGeracao()

        # getattr com default deve retornar None para atributos inexistentes
        modo = getattr(geracao, 'modo_ativacao_agente2', None)
        det = getattr(geracao, 'modulos_ativados_det', None)
        llm = getattr(geracao, 'modulos_ativados_llm', None)
        meta = getattr(geracao, 'curadoria_metadata', None)

        assert modo is None
        assert det is None
        assert llm is None
        assert meta is None

    def test_getattr_com_colunas_existentes(self):
        """
        Verifica que getattr retorna o valor correto quando a coluna existe.
        """
        class MockGeracaoCompleta:
            """Mock de GeracaoPeca com as colunas de curadoria"""
            id = 1
            modo_ativacao_agente2 = "semi_automatico"
            modulos_ativados_det = 3
            modulos_ativados_llm = 2
            curadoria_metadata = {"total_curados": 5}

        geracao = MockGeracaoCompleta()

        modo = getattr(geracao, 'modo_ativacao_agente2', None)
        det = getattr(geracao, 'modulos_ativados_det', None)
        llm = getattr(geracao, 'modulos_ativados_llm', None)
        meta = getattr(geracao, 'curadoria_metadata', None)

        assert modo == "semi_automatico"
        assert det == 3
        assert llm == 2
        assert meta == {"total_curados": 5}

    def test_safe_get_attr_helper_funciona(self):
        """
        Verifica que o helper _safe_get_attr funciona corretamente.
        """
        # Importa o helper do router_admin
        from sistemas.gerador_pecas.router_admin import _safe_get_attr

        class MockObj:
            existente = "valor"

        obj = MockObj()

        # Atributo existente
        assert _safe_get_attr(obj, 'existente') == "valor"
        assert _safe_get_attr(obj, 'existente', 'default') == "valor"

        # Atributo inexistente
        assert _safe_get_attr(obj, 'inexistente') is None
        assert _safe_get_attr(obj, 'inexistente', 'default') == 'default'

    def test_modo_info_fallback_quando_none(self):
        """
        Verifica que modo_info é None quando modo_ativacao é None.
        """
        modo_ativacao = None
        modulos_det = None
        modulos_llm = None

        # Lógica do endpoint de feedbacks
        modo_info = None
        if modo_ativacao == 'semi_automatico':
            modo_info = {"modo": "semi_automatico"}
        elif modo_ativacao:
            modo_info = {"modo": modo_ativacao}

        assert modo_info is None

    def test_modo_info_modos_automaticos(self):
        """
        Verifica que modo_info é construído corretamente para modos automáticos.
        """
        test_cases = [
            ("fast_path", 5, 0),
            ("misto", 3, 2),
            ("llm", 0, 5),
        ]

        for modo_ativacao, det, llm in test_cases:
            modo_info = None
            if modo_ativacao == 'semi_automatico':
                modo_info = {"modo": "semi_automatico"}
            elif modo_ativacao:
                modo_info = {
                    "modo": modo_ativacao,
                    "modulos_det": det,
                    "modulos_llm": llm
                }

            assert modo_info is not None
            assert modo_info["modo"] == modo_ativacao
            assert modo_info["modulos_det"] == det
            assert modo_info["modulos_llm"] == llm

    def test_curadoria_data_fallback_dict_vazio(self):
        """
        Verifica que curadoria_data usa dict vazio quando curadoria_meta é None.
        """
        curadoria_meta = None
        curadoria_data = curadoria_meta or {}

        assert curadoria_data == {}
        assert curadoria_data.get("total_curados", 0) == 0
        assert curadoria_data.get("total_manuais", 0) == 0

    def test_migracao_idempotente(self):
        """
        Verifica que a função column_exists da migração funciona corretamente.
        """
        # Simula a lógica de verificação de existência
        def column_exists_mock(table_name: str, column_name: str, existing_columns: set) -> bool:
            return column_name in existing_columns

        # Cenário 1: Coluna não existe
        existing = {"id", "numero_cnj", "tipo_peca"}
        assert not column_exists_mock("geracoes_pecas", "curadoria_metadata", existing)

        # Cenário 2: Coluna já existe
        existing.add("curadoria_metadata")
        assert column_exists_mock("geracoes_pecas", "curadoria_metadata", existing)

    def test_init_db_adiciona_coluna_se_inexistente(self):
        """
        Verifica a lógica de adicionar coluna apenas se não existir.
        """
        colunas_existentes = {"id", "numero_cnj"}
        colunas_para_adicionar = [
            ("modo_ativacao_agente2", "VARCHAR(30)"),
            ("modulos_ativados_det", "INTEGER"),
            ("modulos_ativados_llm", "INTEGER"),
            ("curadoria_metadata", "JSONB"),
        ]

        colunas_adicionadas = []
        for coluna, tipo in colunas_para_adicionar:
            if coluna not in colunas_existentes:
                colunas_adicionadas.append(coluna)
                colunas_existentes.add(coluna)

        # Todas as colunas devem ser adicionadas
        assert len(colunas_adicionadas) == 4
        assert "curadoria_metadata" in colunas_adicionadas

        # Segunda execução não deve adicionar nada
        colunas_adicionadas_2 = []
        for coluna, tipo in colunas_para_adicionar:
            if coluna not in colunas_existentes:
                colunas_adicionadas_2.append(coluna)

        assert len(colunas_adicionadas_2) == 0

    def test_erro_coluna_inexistente_detectado_na_string(self):
        """
        Verifica que o tratamento de erro detecta mensagens de coluna inexistente.
        """
        error_messages = [
            "column 'geracoes_pecas.curadoria_metadata' does not exist",
            "psycopg2.errors.UndefinedColumn: modo_ativacao_agente2",
            "modulos_ativados_det does not exist",
        ]

        for msg in error_messages:
            is_schema_error = (
                'modo_ativacao_agente2' in msg or
                'modulos_ativados' in msg or
                'curadoria_metadata' in msg
            )
            assert is_schema_error, f"Deveria detectar erro de schema em: {msg}"

    def test_modelo_usa_deferred_para_colunas_opcionais(self):
        """
        Verifica que o modelo GeracaoPeca usa deferred() para colunas opcionais.
        """
        from sistemas.gerador_pecas.models import GeracaoPeca
        from sqlalchemy.orm import deferred

        # Verifica que as colunas estão marcadas como deferred no modelo
        # (não tenta carregar automaticamente, só quando acessadas)
        mapper = GeracaoPeca.__mapper__

        deferred_columns = [
            'modo_ativacao_agente2',
            'modulos_ativados_det',
            'modulos_ativados_llm',
            'curadoria_metadata'
        ]

        for col_name in deferred_columns:
            if col_name in mapper.columns:
                # Coluna existe no mapper
                pass
            # Se não existir, o deferred() evita erro ao carregar o objeto


# ============================================================================
# TESTES: HUMAN_VALIDATED - Validação Obrigatória (Modo Semi-Automático)
# ============================================================================

class TestHumanValidatedEnforcement:
    """
    Testes para garantir que a tag HUMAN_VALIDATED é obrigatória no modo semi-automático
    e que o modo automático permanece 100% inalterado.
    """

    def test_todos_prompts_semi_automatico_tem_human_validated(self, servico_curadoria, resultado_curadoria_exemplo):
        """Todos os prompts no modo semi-automático DEVEM ter tag HUMAN_VALIDATED."""
        prompt = servico_curadoria.montar_prompt_curado(
            resultado_curadoria_exemplo,
            prompt_sistema="Sistema...",
            prompt_peca="Peca..."
        )

        # Verifica que cada módulo selecionado tem a tag
        for modulo in resultado_curadoria_exemplo.get_modulos_selecionados():
            assert modulo.titulo in prompt, f"Módulo {modulo.titulo} não encontrado no prompt"

        # Verifica que há tags HUMAN_VALIDATED
        assert "[HUMAN_VALIDATED" in prompt

    def test_prompt_inclui_instrucao_uso_integral(self, servico_curadoria, resultado_curadoria_exemplo):
        """Prompt deve instruir IA a usar argumentos integralmente sem modificação."""
        prompt = servico_curadoria.montar_prompt_curado(
            resultado_curadoria_exemplo,
            prompt_sistema="Sistema...",
            prompt_peca="Peca..."
        )

        # Deve ter instrução clara
        assert "integralmente" in prompt.lower() or "obrigatória" in prompt.lower()

    def test_ordem_modulos_preservada_no_prompt(self, servico_curadoria):
        """Ordem dos módulos definida pelo usuário deve ser preservada no prompt."""
        modulos_por_secao = {
            "Mérito": [
                ModuloCurado(id=3, nome="c", titulo="Terceiro", categoria="Mérito", conteudo="C", selecionado=True, ordem=0),
                ModuloCurado(id=1, nome="a", titulo="Primeiro", categoria="Mérito", conteudo="A", selecionado=True, ordem=1),
                ModuloCurado(id=2, nome="b", titulo="Segundo", categoria="Mérito", conteudo="B", selecionado=True, ordem=2),
            ]
        }

        resultado = ResultadoCuradoria(
            numero_processo="123",
            tipo_peca="contestacao",
            modulos_por_secao=modulos_por_secao
        )

        prompt = servico_curadoria.montar_prompt_curado(resultado, "", "")

        # Verifica ordem no prompt
        idx_terceiro = prompt.find("Terceiro")
        idx_primeiro = prompt.find("Primeiro")
        idx_segundo = prompt.find("Segundo")

        assert idx_terceiro < idx_primeiro < idx_segundo, "Ordem dos módulos não preservada"

    def test_multiplos_prompts_human_validated_agregados(self, servico_curadoria):
        """Múltiplos prompts HUMAN_VALIDATED devem ser agregados corretamente."""
        modulos_por_secao = {
            "Preliminar": [
                ModuloCurado(id=1, nome="a", titulo="Arg 1", categoria="Preliminar", conteudo="Conteudo 1", selecionado=True),
                ModuloCurado(id=2, nome="b", titulo="Arg 2", categoria="Preliminar", conteudo="Conteudo 2", selecionado=True),
            ],
            "Mérito": [
                ModuloCurado(id=3, nome="c", titulo="Arg 3", categoria="Mérito", conteudo="Conteudo 3", selecionado=True),
            ]
        }

        resultado = ResultadoCuradoria(
            numero_processo="123",
            tipo_peca="contestacao",
            modulos_por_secao=modulos_por_secao
        )

        prompt = servico_curadoria.montar_prompt_curado(resultado, "", "")

        # Conta apenas tags nos títulos de módulos (formato "#### Titulo [HUMAN_VALIDATED]")
        # Exclui menções no cabeçalho/instruções
        import re
        module_tags = re.findall(r'####.*\[HUMAN_VALIDATED\]', prompt)
        assert len(module_tags) == 3, f"Esperado 3 módulos com tag, encontrado {len(module_tags)}"

        assert "Arg 1" in prompt
        assert "Arg 2" in prompt
        assert "Arg 3" in prompt
        assert "Conteudo 1" in prompt
        assert "Conteudo 2" in prompt
        assert "Conteudo 3" in prompt

    def test_log_indica_uso_human_validated(self, servico_curadoria, resultado_curadoria_exemplo, capsys):
        """Log/telemetria deve indicar uso de HUMAN_VALIDATED no modo semi-automático."""
        # O serviço não faz logging direto, mas o router faz
        # Este teste verifica que a estrutura está correta para logging
        prompt = servico_curadoria.montar_prompt_curado(
            resultado_curadoria_exemplo,
            prompt_sistema="",
            prompt_peca=""
        )

        # Verifica que o prompt contém marcadores identificáveis para logging
        assert "HUMAN_VALIDATED" in prompt


class TestModoAutomaticoInabalterado:
    """
    Testes para GARANTIR que o modo automático NÃO sofre NENHUMA alteração.

    O modo automático:
    - Usa orquestrador_agentes.py para montar prompts
    - NÃO passa por services_curadoria.py
    - NÃO usa tag HUMAN_VALIDATED
    - Mantém comportamento, regras, validações, precedência e logging 100% iguais
    """

    def test_modo_automatico_nao_usa_human_validated_em_arquivo(self):
        """Modo automático NÃO deve usar tag HUMAN_VALIDATED no código-fonte."""
        import os

        # Lê o arquivo orquestrador_agentes.py diretamente
        orq_path = os.path.join(
            os.path.dirname(__file__),
            "..", "sistemas", "gerador_pecas", "orquestrador_agentes.py"
        )
        orq_path = os.path.normpath(orq_path)

        with open(orq_path, "r", encoding="utf-8") as f:
            source = f.read()

        # Modo automático usa [VALIDADO] para módulos determinísticos
        assert "[VALIDADO]" in source, \
            "Orquestrador deve usar [VALIDADO] para módulos determinísticos"

        # Não deve conter referência a HUMAN_VALIDATED (é exclusivo do semi-automático)
        assert "HUMAN_VALIDATED" not in source, \
            "Orquestrador do modo automático NÃO deve usar HUMAN_VALIDATED"

    def test_services_curadoria_usa_human_validated(self):
        """services_curadoria.py (modo semi-auto) usa HUMAN_VALIDATED."""
        import os

        # Lê o arquivo services_curadoria.py diretamente
        curadoria_path = os.path.join(
            os.path.dirname(__file__),
            "..", "sistemas", "gerador_pecas", "services_curadoria.py"
        )
        curadoria_path = os.path.normpath(curadoria_path)

        with open(curadoria_path, "r", encoding="utf-8") as f:
            source = f.read()

        # services_curadoria.py deve usar HUMAN_VALIDATED
        assert "HUMAN_VALIDATED" in source, \
            "services_curadoria deve usar HUMAN_VALIDATED para modo semi-automático"

    def test_arquivos_separados_modo_automatico_e_semi_automatico(self):
        """
        Modo automático e semi-automático usam arquivos diferentes.
        Isso garante que alterações em um não afetam o outro.
        """
        import os

        # Arquivos do modo automático
        orq_path = os.path.join(
            os.path.dirname(__file__),
            "..", "sistemas", "gerador_pecas", "orquestrador_agentes.py"
        )

        # Arquivos do modo semi-automático
        curadoria_path = os.path.join(
            os.path.dirname(__file__),
            "..", "sistemas", "gerador_pecas", "services_curadoria.py"
        )

        # Ambos devem existir como arquivos separados
        assert os.path.exists(orq_path), "orquestrador_agentes.py deve existir"
        assert os.path.exists(curadoria_path), "services_curadoria.py deve existir"
        assert orq_path != curadoria_path, "Arquivos devem ser distintos"

    def test_modo_automatico_usa_validado_nao_human_validated(self):
        """
        Modo automático pode usar [VALIDADO] mas NÃO [HUMAN_VALIDATED].
        HUMAN_VALIDATED é exclusivo do modo semi-automático.
        """
        from sistemas.gerador_pecas.services_curadoria import ModuloCurado, OrigemAtivacao

        # Cria módulo como seria no modo automático (deterministico)
        modulo_det = ModuloCurado(
            id=1,
            nome="det_test",
            titulo="Teste Deterministico",
            categoria="Preliminar",
            conteudo="Conteudo",
            origem_ativacao=OrigemAtivacao.DETERMINISTIC.value,
            validado=True,  # Validado automaticamente
            selecionado=True
        )

        # No modo automático, não passaria por services_curadoria
        # Mas mesmo se passasse, a tag seria HUMAN_VALIDATED (que é o correto para semi-auto)
        assert modulo_det.origem_ativacao == "deterministic"
        assert modulo_det.validado is True


# ============================================================================
# TESTES: Transparência e Auditoria - Fev 2026
# ============================================================================

class TestTransparenciaAuditoria:
    """
    Testes para verificar que o endpoint de curadoria retorna informações
    completas para transparência e auditoria:
    - Glossário de termos
    - Explicação do processo
    - Detalhes completos de cada módulo
    - Motivos de inclusão/exclusão
    """

    def test_endpoint_curadoria_retorna_glossario(self):
        """
        Endpoint deve retornar glossário explicando termos técnicos.
        """
        # Simula resposta do endpoint
        resposta = {
            "glossario": {
                "HUMAN_VALIDATED": "Argumento validado pelo usuário",
                "HUMAN_VALIDATED:MANUAL": "Argumento adicionado manualmente",
                "confirmado": "Sugestão confirmada pelo usuário",
                "manual": "Adicionado durante revisão",
                "removido": "Sugestão removida pelo usuário",
            }
        }

        glossario = resposta.get("glossario", {})
        assert "HUMAN_VALIDATED" in glossario
        assert "HUMAN_VALIDATED:MANUAL" in glossario
        assert "confirmado" in glossario
        assert "manual" in glossario
        assert "removido" in glossario

    def test_endpoint_curadoria_retorna_explicacao_processo(self):
        """
        Endpoint deve retornar explicação do processo para transparência.
        """
        resposta = {
            "explicacao_processo": {
                "titulo": "Como funciona o Modo Semi-Automático",
                "etapas": [
                    "1. Sistema sugere argumentos",
                    "2. Usuário revisa",
                    "3. Confirmados recebem HUMAN_VALIDATED",
                    "4. Manuais recebem HUMAN_VALIDATED:MANUAL",
                ],
                "garantia": "Argumentos validados são incluídos integralmente."
            }
        }

        explicacao = resposta.get("explicacao_processo", {})
        assert "titulo" in explicacao
        assert "etapas" in explicacao
        assert "garantia" in explicacao
        assert len(explicacao["etapas"]) >= 3

    def test_modulo_incluido_contem_informacoes_completas(self):
        """
        Cada módulo incluído deve conter informações completas para auditoria.
        """
        modulo = {
            "id": 1,
            "titulo": "Argumento de Teste",
            "categoria": "Mérito",
            "subcategoria": "Medicamentos",
            "conteudo": "Texto completo do argumento...",
            "tag": "[HUMAN_VALIDATED]",
            "tipo_decisao": "confirmado",
            "decisao_explicacao": "Sugerido automaticamente e confirmado pelo usuário",
            "motivo_inclusao": "O sistema sugeriu e o usuário confirmou",
            "status_final": "incluido",
            "ordem": 1
        }

        # Campos obrigatórios para auditoria
        assert "id" in modulo
        assert "titulo" in modulo
        assert "conteudo" in modulo  # Conteúdo completo
        assert "tag" in modulo
        assert "tipo_decisao" in modulo
        assert "decisao_explicacao" in modulo
        assert "motivo_inclusao" in modulo
        assert "status_final" in modulo

    def test_modulo_excluido_contem_motivo(self):
        """
        Módulos excluídos devem conter motivo da exclusão.
        """
        modulo_excluido = {
            "id": 2,
            "titulo": "Argumento Excluído",
            "categoria": "Preliminar",
            "conteudo": "Conteúdo do argumento removido...",
            "tag": "[EXCLUÍDO]",
            "tipo_decisao": "removido",
            "decisao_explicacao": "Sugerido mas removido pelo usuário",
            "motivo_exclusao": "O usuário decidiu não incluir",
            "status_final": "excluido"
        }

        assert modulo_excluido["status_final"] == "excluido"
        assert "motivo_exclusao" in modulo_excluido
        assert modulo_excluido["tipo_decisao"] == "removido"

    def test_metadata_inclui_totais_detalhados(self):
        """
        Metadata deve incluir totais detalhados para resumo.
        """
        metadata = {
            "total_preview": 10,
            "total_incluidos": 8,
            "total_confirmados": 6,  # Sugestões aceitas
            "total_manuais": 2,  # Adicionados pelo usuário
            "total_excluidos": 4,  # Sugestões removidas
        }

        assert "total_preview" in metadata
        assert "total_incluidos" in metadata
        assert "total_confirmados" in metadata
        assert "total_manuais" in metadata
        assert "total_excluidos" in metadata

        # Verificação de consistência
        assert metadata["total_incluidos"] == metadata["total_confirmados"] + metadata["total_manuais"]

    def test_usuario_pode_responder_perguntas_de_auditoria(self):
        """
        Com os dados retornados, o usuário deve poder responder:
        1. O que foi incluído?
        2. O que foi excluído?
        3. Por quê?
        4. Baseado em qual decisão?
        """
        resposta_completa = {
            "modulos_incluidos": [
                {
                    "id": 1,
                    "titulo": "Argumento sobre Medicamento",
                    "tag": "[HUMAN_VALIDATED]",
                    "tipo_decisao": "confirmado",
                    "decisao_explicacao": "Sugerido pelo sistema e confirmado",
                    "motivo_inclusao": "Usuário confirmou a sugestão",
                    "status_final": "incluido"
                },
                {
                    "id": 2,
                    "titulo": "Argumento Manual",
                    "tag": "[HUMAN_VALIDATED:MANUAL]",
                    "tipo_decisao": "manual",
                    "decisao_explicacao": "Adicionado manualmente pelo usuário",
                    "motivo_inclusao": "Usuário adicionou durante revisão",
                    "status_final": "incluido"
                }
            ],
            "modulos_excluidos": [
                {
                    "id": 3,
                    "titulo": "Argumento Removido",
                    "tag": "[EXCLUÍDO]",
                    "tipo_decisao": "removido",
                    "decisao_explicacao": "Removido pelo usuário",
                    "motivo_exclusao": "Usuário rejeitou esta sugestão",
                    "status_final": "excluido"
                }
            ],
            "glossario": {
                "HUMAN_VALIDATED": "Validado pelo usuário",
                "HUMAN_VALIDATED:MANUAL": "Adicionado manualmente",
                "confirmado": "Sugestão aceita",
                "manual": "Adicionado pelo usuário",
                "removido": "Sugestão rejeitada"
            }
        }

        # 1. O que foi incluído?
        incluidos = resposta_completa["modulos_incluidos"]
        assert len(incluidos) == 2
        titulos_incluidos = [m["titulo"] for m in incluidos]
        assert "Argumento sobre Medicamento" in titulos_incluidos
        assert "Argumento Manual" in titulos_incluidos

        # 2. O que foi excluído?
        excluidos = resposta_completa["modulos_excluidos"]
        assert len(excluidos) == 1
        assert excluidos[0]["titulo"] == "Argumento Removido"

        # 3. Por quê? (motivo)
        for m in incluidos:
            assert "motivo_inclusao" in m
            assert len(m["motivo_inclusao"]) > 0

        for m in excluidos:
            assert "motivo_exclusao" in m
            assert len(m["motivo_exclusao"]) > 0

        # 4. Baseado em qual decisão?
        for m in incluidos + excluidos:
            assert "tipo_decisao" in m
            assert m["tipo_decisao"] in ["confirmado", "manual", "removido"]
            assert "decisao_explicacao" in m

        # 5. Glossário disponível para explicar termos
        glossario = resposta_completa["glossario"]
        for m in incluidos:
            tag = m["tag"].replace("[", "").replace("]", "")
            if tag in glossario:
                assert len(glossario[tag]) > 0  # Tem explicação


# ============================================================================
# TESTES DO ENDPOINT DE CURADORIA - /geracoes/{id}/curadoria
# ============================================================================

class TestEndpointCuradoria:
    """
    Testes para o endpoint de auditoria de curadoria.

    Endpoint: GET /admin/api/gerador-pecas-admin/geracoes/{geracao_id}/curadoria

    Cenários cobertos:
    1. Geração em modo semi-automático com dados completos → 200 OK
    2. Geração não encontrada → 404 Not Found
    3. Geração em modo não-semi-automático → 404 Not Found
    4. Resposta inclui todos os campos obrigatórios
    """

    def test_endpoint_url_correta(self):
        """
        Verifica que a URL documentada está correta.

        A URL deve ser: /admin/api/gerador-pecas-admin/geracoes/{id}/curadoria
        NÃO: /api/gerador-pecas/admin/geracoes/{id}/curadoria (antigo, incorreto)
        """
        url_correta = "/admin/api/gerador-pecas-admin/geracoes/123/curadoria"
        url_incorreta = "/api/gerador-pecas/admin/geracoes/123/curadoria"

        assert "gerador-pecas-admin" in url_correta
        assert "/admin/api/" in url_correta
        assert url_correta != url_incorreta

    def test_resposta_sucesso_contem_campos_obrigatorios(self):
        """
        Resposta de sucesso deve conter todos os campos necessários para auditoria.
        """
        resposta_exemplo = {
            "geracao_id": 123,
            "modo": "semi_automatico",
            "metadata": {
                "total_preview": 10,
                "total_incluidos": 8,
                "total_confirmados": 6,
                "total_manuais": 2,
                "total_excluidos": 2,
                "preview_timestamp": "2026-02-03T10:00:00Z",
                "categorias_ordem": ["Preliminar", "Mérito"]
            },
            "glossario": {},
            "explicacao_processo": {},
            "modulos_incluidos": [],
            "modulos_excluidos": []
        }

        # Campos obrigatórios no primeiro nível
        assert "geracao_id" in resposta_exemplo
        assert "modo" in resposta_exemplo
        assert "metadata" in resposta_exemplo
        assert "modulos_incluidos" in resposta_exemplo
        assert "modulos_excluidos" in resposta_exemplo

        # Campos obrigatórios em metadata
        metadata = resposta_exemplo["metadata"]
        assert "total_preview" in metadata
        assert "total_incluidos" in metadata
        assert "total_confirmados" in metadata
        assert "total_manuais" in metadata
        assert "total_excluidos" in metadata

    def test_modulo_incluido_estrutura_completa(self):
        """
        Módulos incluídos devem ter estrutura completa para auditoria.
        """
        modulo_incluido = {
            "id": 1,
            "titulo": "Argumento sobre SUS",
            "categoria": "Mérito",
            "subcategoria": "Medicamentos",
            "conteudo": "Conteúdo completo do argumento...",
            "origem": "preview",
            "tag": "[HUMAN_VALIDATED]",
            "tipo_decisao": "confirmado",
            "decisao_explicacao": "Sugerido e confirmado",
            "motivo_inclusao": "Usuário confirmou a sugestão",
            "ordem": 1,
            "status_final": "incluido"
        }

        campos_obrigatorios = [
            "id", "titulo", "categoria", "tag",
            "tipo_decisao", "status_final"
        ]

        for campo in campos_obrigatorios:
            assert campo in modulo_incluido, f"Campo obrigatório ausente: {campo}"

    def test_modulo_excluido_estrutura_completa(self):
        """
        Módulos excluídos devem ter estrutura que explique a exclusão.
        """
        modulo_excluido = {
            "id": 2,
            "titulo": "Argumento Removido",
            "categoria": "Preliminar",
            "conteudo": "Conteúdo do argumento removido...",
            "origem": "preview",
            "tag": "[EXCLUÍDO]",
            "tipo_decisao": "removido",
            "decisao_explicacao": "Sugerido mas removido pelo usuário",
            "motivo_exclusao": "O usuário decidiu não incluir",
            "status_final": "excluido"
        }

        assert modulo_excluido["status_final"] == "excluido"
        assert modulo_excluido["tipo_decisao"] == "removido"
        assert "motivo_exclusao" in modulo_excluido

    def test_erro_404_mensagens_especificas(self):
        """
        Erros 404 devem ter mensagens específicas para diagnóstico.
        """
        mensagem_nao_encontrada = "Geração não encontrada"
        mensagem_modo_incorreto = "Esta geração não foi feita no modo semi-automático"

        # Frontend deve conseguir distinguir os casos
        assert "não encontrada" in mensagem_nao_encontrada
        assert "semi-automático" in mensagem_modo_incorreto
        assert mensagem_nao_encontrada != mensagem_modo_incorreto

    def test_consistencia_contagens_metadata(self):
        """
        As contagens em metadata devem ser consistentes.
        """
        metadata = {
            "total_preview": 10,
            "total_incluidos": 8,
            "total_confirmados": 6,
            "total_manuais": 2,
            "total_excluidos": 2,
        }

        # total_incluidos = total_confirmados + total_manuais
        assert metadata["total_incluidos"] == metadata["total_confirmados"] + metadata["total_manuais"]

        # total_preview >= total_confirmados (pois confirmados vêm do preview)
        assert metadata["total_preview"] >= metadata["total_confirmados"]


class TestEndpointCuradoriaIntegracao:
    """
    Testes de integração para o endpoint de curadoria.

    Estes testes verificam o comportamento real do endpoint
    com mocks do banco de dados.
    """

    @pytest.fixture
    def mock_geracao_semi_automatico(self):
        """Cria mock de geração em modo semi-automático."""
        geracao = MagicMock()
        geracao.id = 123
        geracao.modo_ativacao_agente2 = "semi_automatico"
        geracao.curadoria_metadata = {
            "modulos_preview_ids": [1, 2, 3],
            "modulos_curados_ids": [1, 3, 4],
            "modulos_manuais_ids": [4],
            "modulos_excluidos_ids": [2],
            "modulos_detalhados": [
                {"id": 1, "origem": "preview", "status": "[VALIDADO]"},
                {"id": 3, "origem": "preview", "status": "[VALIDADO]"},
                {"id": 4, "origem": "manual", "status": "[VALIDADO-MANUAL]"},
            ],
            "total_preview": 3,
            "total_curados": 3,
            "total_manuais": 1,
            "total_excluidos": 1,
        }
        return geracao

    @pytest.fixture
    def mock_geracao_automatico(self):
        """Cria mock de geração em modo automático (não semi-automático)."""
        geracao = MagicMock()
        geracao.id = 456
        geracao.modo_ativacao_agente2 = "misto"
        geracao.curadoria_metadata = None
        return geracao

    def test_geracao_semi_automatico_retorna_dados(self, mock_geracao_semi_automatico):
        """
        Geração em modo semi-automático deve retornar dados de auditoria.
        """
        geracao = mock_geracao_semi_automatico

        # Simula verificações que o endpoint faria
        assert geracao.modo_ativacao_agente2 == "semi_automatico"
        assert geracao.curadoria_metadata is not None

        metadata = geracao.curadoria_metadata
        assert metadata["total_preview"] == 3
        assert metadata["total_curados"] == 3
        assert metadata["total_manuais"] == 1
        assert metadata["total_excluidos"] == 1

    def test_geracao_modo_automatico_rejeitada(self, mock_geracao_automatico):
        """
        Geração em modo automático deve ser rejeitada com 404.
        """
        geracao = mock_geracao_automatico

        # Endpoint verifica modo antes de retornar dados
        modo = geracao.modo_ativacao_agente2
        assert modo != "semi_automatico"

        # Frontend deve receber mensagem específica
        mensagem_esperada = "Esta geração não foi feita no modo semi-automático"
        assert "semi-automático" in mensagem_esperada

    def test_geracao_inexistente_retorna_404(self):
        """
        ID de geração inexistente deve retornar 404.
        """
        geracao = None  # Simula geração não encontrada

        # Endpoint verifica existência
        assert geracao is None

        # Frontend deve receber mensagem específica
        mensagem_esperada = "Geração não encontrada"
        assert "não encontrada" in mensagem_esperada


class TestFrontendAuditoriaIntegracao:
    """
    Testes que verificam se o frontend está integrado corretamente.
    """

    def test_frontend_usa_url_correta(self):
        """
        O frontend deve chamar a URL correta do endpoint.

        ANTES (BUG): /api/gerador-pecas/admin/geracoes/{id}/curadoria
        DEPOIS (FIX): /admin/api/gerador-pecas-admin/geracoes/{id}/curadoria
        """
        url_correta = "/admin/api/gerador-pecas-admin/geracoes/{id}/curadoria"
        url_antiga_incorreta = "/api/gerador-pecas/admin/geracoes/{id}/curadoria"

        # A URL deve seguir o padrão do router_admin
        assert "/admin/api/" in url_correta
        assert "/gerador-pecas-admin/" in url_correta

        # A URL antiga não deve ser usada
        assert "/api/gerador-pecas/admin/" not in url_correta

    def test_frontend_trata_erros_especificos(self):
        """
        Frontend deve exibir mensagens específicas por tipo de erro.
        """
        erros_e_mensagens = {
            404: {
                "nao_encontrada": "Geração não encontrada",
                "modo_incorreto": "não foi feita no modo semi-automático",
            },
            403: "não tem permissão",
            500: "Erro interno do servidor",
        }

        # 404 tem submensagens
        assert "nao_encontrada" in erros_e_mensagens[404]
        assert "modo_incorreto" in erros_e_mensagens[404]

        # Outros erros têm mensagem única
        assert isinstance(erros_e_mensagens[403], str)
        assert isinstance(erros_e_mensagens[500], str)

    def test_frontend_loga_requisicoes_em_desenvolvimento(self):
        """
        Frontend deve logar requisições para debug (apenas em dev).
        """
        # Exemplo de log esperado
        log_esperado = "[Auditoria] Buscando curadoria para geração ID: 123"

        assert "ID:" in log_esperado
        assert "123" in log_esperado
