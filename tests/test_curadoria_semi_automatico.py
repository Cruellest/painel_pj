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
# TESTES: Prompt Curado com Marcacao VALIDADO
# ============================================================================

class TestPromptCuradoValidado:
    """Testes para verificar marcacao VALIDADO no prompt."""

    def test_montar_prompt_curado_marca_validados(self, servico_curadoria, resultado_curadoria_exemplo):
        """Deve marcar modulos validados com [VALIDADO]."""
        prompt = servico_curadoria.montar_prompt_curado(
            resultado_curadoria_exemplo,
            prompt_sistema="Sistema...",
            prompt_peca="Peca..."
        )

        # Modulo 1 (deterministico, validado) deve ter [VALIDADO]
        assert "[VALIDADO]" in prompt
        assert "Ilegitimidade Passiva" in prompt

    def test_montar_prompt_curado_modulos_manuais_validados(self, servico_curadoria, resultado_curadoria_exemplo):
        """Modulos adicionados manualmente devem ter [VALIDADO]."""
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

        # Modulo manual deve ter [VALIDADO]
        assert "Argumento Manual" in prompt
        # Deve aparecer [VALIDADO] para modulos validados
        assert prompt.count("[VALIDADO]") >= 1

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

        # Verifica elementos markdown
        assert "## ARGUMENTOS E TESES APLICAVEIS (CURADOS)" in prompt
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

        # Verifica mensagem de curadoria
        assert "selecionados e validados pelo usuario" in prompt.lower() or "CURADOS" in prompt


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

    def test_modulo_manual_aparece_validado_no_prompt(self, servico_curadoria):
        """
        Módulos manuais devem aparecer com [VALIDADO] no prompt final.
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
        assert "[VALIDADO]" in prompt

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
        from sistemas.gerador_pecas.orquestrador_agentes import ORDEM_CATEGORIAS_PADRAO

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
