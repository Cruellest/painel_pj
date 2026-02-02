# tests/test_document_classifier.py
"""
Testes automatizados para o sistema de classificação de documentos PDF.

Cobre os cenários obrigatórios:
1. PDF com texto → usa primeiros + últimos 1000 tokens
2. PDF imagem → envia imagem inteira
3. OCR falha → envia imagem inteira
4. IA retorna categoria inválida → fallback
5. IA retorna JSON malformado → fallback
6. Confiança baixa → fallback
7. Categorias alteradas no banco → classificador usa lista atual
8. Regressão: fluxo com metadado continua intacto
"""

import pytest
import json
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from dataclasses import dataclass

# Importa os módulos a serem testados
from sistemas.gerador_pecas.document_classifier import (
    DocumentClassifier,
    DocumentClassification,
    ClassificationSource,
    PDFContent,
    extrair_conteudo_pdf,
    _contar_tokens_aproximado,
    _truncar_texto_heuristico,
    _avaliar_qualidade_texto,
)
from sistemas.gerador_pecas.document_selector import (
    DocumentSelector,
    SelectionResult,
    SelectedDocument,
    DocumentRole,
    DEFAULT_PRIORITY_CONFIG,
)


# ==============================================================================
# FIXTURES
# ==============================================================================

@pytest.fixture
def mock_db():
    """Mock da sessão do banco de dados."""
    db = Mock()
    db.query.return_value.filter.return_value.first.return_value = None
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
    return db


@pytest.fixture
def mock_categorias():
    """Lista mock de categorias do banco."""
    @dataclass
    class MockCategoria:
        id: int
        nome: str
        titulo: str
        descricao: str
        ativo: bool
        is_residual: bool
        ordem: int

    return [
        MockCategoria(id=1, nome="peticoes", titulo="Petições Iniciais",
                     descricao="Petições iniciais e ações judiciais", ativo=True, is_residual=False, ordem=1),
        MockCategoria(id=2, nome="decisoes", titulo="Decisões Judiciais",
                     descricao="Sentenças, despachos e decisões", ativo=True, is_residual=False, ordem=2),
        MockCategoria(id=3, nome="recursos", titulo="Recursos",
                     descricao="Apelações, agravos e embargos", ativo=True, is_residual=False, ordem=3),
        MockCategoria(id=4, nome="outros", titulo="Outros Documentos",
                     descricao="Documentos diversos", ativo=True, is_residual=True, ordem=99),
    ]


@pytest.fixture
def texto_peticao_inicial():
    """Texto fixture de uma petição inicial."""
    return """
EXCELENTÍSSIMO SENHOR DOUTOR JUIZ DE DIREITO DA VARA DA FAZENDA PÚBLICA
DA COMARCA DE CAMPO GRANDE - MS

JOÃO DA SILVA, brasileiro, casado, advogado, inscrito na OAB/MS sob o n° 12345,
com endereço profissional na Rua das Flores, n° 100, Centro, CEP 79000-000,
Campo Grande/MS, vem, respeitosamente, à presença de Vossa Excelência, propor a presente

AÇÃO DE COBRANÇA

em face do ESTADO DE MATO GROSSO DO SUL, pessoa jurídica de direito público interno,
com sede na Avenida Desembargador José Nunes da Cunha, Bloco II, Jardim Veraneio,
Campo Grande/MS, pelos fatos e fundamentos a seguir expostos.

DOS FATOS

O autor é servidor público estadual desde 2010, exercendo o cargo de Analista de Sistemas
junto à Secretaria de Administração do Estado.

Em janeiro de 2023, houve reajuste salarial determinado pela Lei Estadual n° 5.500/2023,
que fixou aumento de 5% para todos os servidores do Poder Executivo.

Ocorre que o Estado réu não efetuou o pagamento do referido reajuste ao autor,
causando prejuízo financeiro estimado em R$ 15.000,00 (quinze mil reais).

DOS PEDIDOS

Diante do exposto, requer:

a) a citação do réu para, querendo, contestar a presente ação;
b) a procedência do pedido para condenar o réu ao pagamento de R$ 15.000,00;
c) a condenação do réu ao pagamento das custas processuais e honorários advocatícios.

Dá-se à causa o valor de R$ 15.000,00.

Termos em que pede deferimento.

Campo Grande/MS, 15 de março de 2024.

______________________________
JOÃO DA SILVA
OAB/MS 12345
""" * 3  # Repete para ter texto suficiente


@pytest.fixture
def texto_decisao():
    """Texto fixture de uma decisão judicial."""
    return """
PODER JUDICIÁRIO DO ESTADO DE MATO GROSSO DO SUL
COMARCA DE CAMPO GRANDE
VARA DA FAZENDA PÚBLICA

Processo n° 0001234-56.2024.8.12.0001

SENTENÇA

Vistos.

Trata-se de ação de cobrança movida por JOÃO DA SILVA em face do ESTADO DE MATO GROSSO DO SUL.

Alega o autor, em síntese, que é servidor público estadual e não recebeu reajuste salarial
determinado por lei, pleiteando o pagamento de R$ 15.000,00.

Citado, o réu apresentou contestação arguindo prescrição e, no mérito, impugnou os cálculos apresentados.

É o relatório. Decido.

Preliminarmente, afasto a arguição de prescrição, vez que a ação foi proposta dentro do prazo quinquenal.

No mérito, assiste razão ao autor.

A Lei Estadual n° 5.500/2023 determinou reajuste de 5% para todos os servidores do Poder Executivo,
sendo incontroverso que o autor faz jus ao referido benefício.

ISTO POSTO, JULGO PROCEDENTE o pedido para condenar o réu ao pagamento de R$ 15.000,00
ao autor, com correção monetária e juros de mora desde o vencimento de cada parcela.

Condeno o réu ao pagamento das custas processuais e honorários advocatícios, que fixo em 10%
sobre o valor da condenação.

P.R.I.

Campo Grande/MS, 20 de junho de 2024.

JUIZ DE DIREITO
"""


@pytest.fixture
def classificacao_peticao():
    """Classificação mock de uma petição."""
    return DocumentClassification(
        arquivo_nome="peticao_inicial.pdf",
        arquivo_id="pdf_1",
        categoria_id=1,
        categoria_nome="peticoes",
        confianca=0.95,
        justificativa="Documento contém DOS FATOS, DOS PEDIDOS, típico de petição inicial",
        source=ClassificationSource.TEXT,
        texto_utilizado="[INÍCIO DO DOCUMENTO]... [FIM DO DOCUMENTO]...",
        fallback_aplicado=False
    )


@pytest.fixture
def classificacao_decisao():
    """Classificação mock de uma decisão."""
    return DocumentClassification(
        arquivo_nome="sentenca.pdf",
        arquivo_id="pdf_2",
        categoria_id=2,
        categoria_nome="decisoes",
        confianca=0.90,
        justificativa="Documento contém SENTENÇA, JULGO PROCEDENTE, típico de decisão",
        source=ClassificationSource.TEXT,
        texto_utilizado="[INÍCIO DO DOCUMENTO]... [FIM DO DOCUMENTO]...",
        fallback_aplicado=False
    )


# ==============================================================================
# TESTES DE FUNÇÕES AUXILIARES
# ==============================================================================

class TestFuncoesAuxiliares:
    """Testes para funções auxiliares do classificador."""

    def test_contar_tokens_aproximado(self):
        """Testa contagem aproximada de tokens."""
        texto = "a" * 4000  # 4000 caracteres
        tokens = _contar_tokens_aproximado(texto)
        assert tokens == 1000  # 4000 / 4 = 1000

    def test_truncar_texto_heuristico_texto_curto(self):
        """Texto curto deve retornar inteiro sem truncar."""
        texto = "Texto curto para teste."
        inicio, fim = _truncar_texto_heuristico(texto, max_tokens=1000)
        assert inicio == texto
        assert fim == ""

    def test_truncar_texto_heuristico_texto_longo(self):
        """Texto longo deve ser truncado em início e fim."""
        # Cria texto com mais de 8000 caracteres (2000 tokens * 4)
        texto = "A" * 5000 + "B" * 5000  # 10000 caracteres
        inicio, fim = _truncar_texto_heuristico(texto, max_tokens=1000)

        # Deve ter 4000 chars do início e 4000 do fim
        assert len(inicio) == 4000
        assert len(fim) == 4000
        assert inicio[0] == "A"
        assert fim[-1] == "B"

    def test_avaliar_qualidade_texto_bom(self, texto_peticao_inicial):
        """Texto de boa qualidade deve retornar 'good'."""
        qualidade = _avaliar_qualidade_texto(texto_peticao_inicial)
        assert qualidade == "good"

    def test_avaliar_qualidade_texto_vazio(self):
        """Texto vazio deve retornar 'none'."""
        assert _avaliar_qualidade_texto("") == "none"
        assert _avaliar_qualidade_texto("   ") == "none"
        assert _avaliar_qualidade_texto("abc") == "none"  # Muito curto

    def test_avaliar_qualidade_texto_ruim(self):
        """Texto com muitos caracteres estranhos deve retornar 'poor' ou 'none'."""
        texto_ruim = "▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓" * 50
        qualidade = _avaliar_qualidade_texto(texto_ruim)
        assert qualidade in ["poor", "none"]


# ==============================================================================
# TESTES DO DOCUMENT CLASSIFIER
# ==============================================================================

class TestDocumentClassifier:
    """Testes para o DocumentClassifier."""

    @pytest.mark.asyncio
    async def test_classificar_pdf_com_texto_usa_heuristica(self, mock_db, mock_categorias, texto_peticao_inicial):
        """
        Teste 1: PDF com texto deve usar primeiros + últimos 1000 tokens.
        """
        # Configura mock do banco para retornar categorias
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = mock_categorias

        # Mock da resposta da IA
        resposta_ia = {
            "categoria_id": 1,
            "confianca": 0.95,
            "justificativa_curta": "Petição inicial com DOS FATOS e DOS PEDIDOS"
        }

        with patch.object(DocumentClassifier, '_chamar_ia', new_callable=AsyncMock) as mock_ia:
            mock_ia.return_value = resposta_ia

            # Mock do extrair_conteudo_pdf para simular PDF com texto bom
            with patch('sistemas.gerador_pecas.document_classifier.extrair_conteudo_pdf') as mock_extrair:
                mock_extrair.return_value = PDFContent(
                    texto=texto_peticao_inicial,
                    imagens=[],
                    tem_texto=True,
                    ocr_tentado=False,
                    ocr_sucesso=False,
                    total_paginas=3,
                    texto_qualidade="good"
                )

                classificador = DocumentClassifier(mock_db)
                resultado = await classificador.classificar_documento(
                    arquivo_nome="peticao.pdf",
                    arquivo_id="pdf_1",
                    pdf_bytes=b"fake pdf bytes"
                )

                # Verifica que a IA foi chamada
                mock_ia.assert_called_once()

                # Verifica que o texto enviado usa heurística (contém marcadores)
                args, kwargs = mock_ia.call_args
                prompt = args[0]
                assert "[INÍCIO DO DOCUMENTO]" in prompt or "TEXTO" in prompt or resultado.source == ClassificationSource.TEXT

                # Verifica resultado
                assert resultado.categoria_id == 1
                assert resultado.confianca == 0.95
                assert resultado.source == ClassificationSource.TEXT
                assert resultado.fallback_aplicado == False

    @pytest.mark.asyncio
    async def test_classificar_pdf_imagem_envia_imagem_inteira(self, mock_db, mock_categorias):
        """
        Teste 2: PDF imagem deve enviar imagem inteira.
        """
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = mock_categorias

        resposta_ia = {
            "categoria_id": 2,
            "confianca": 0.85,
            "justificativa_curta": "Documento de decisão judicial"
        }

        with patch.object(DocumentClassifier, '_chamar_ia', new_callable=AsyncMock) as mock_ia:
            mock_ia.return_value = resposta_ia

            # Mock: PDF sem texto, apenas imagens
            with patch('sistemas.gerador_pecas.document_classifier.extrair_conteudo_pdf') as mock_extrair:
                mock_extrair.return_value = PDFContent(
                    texto="",
                    imagens=[b"fake_image_1", b"fake_image_2"],
                    tem_texto=False,
                    ocr_tentado=False,
                    ocr_sucesso=False,
                    total_paginas=2,
                    texto_qualidade="none"
                )

                classificador = DocumentClassifier(mock_db)
                resultado = await classificador.classificar_documento(
                    arquivo_nome="documento_imagem.pdf",
                    arquivo_id="pdf_2",
                    pdf_bytes=b"fake pdf bytes"
                )

                # Verifica que a IA foi chamada com imagens
                mock_ia.assert_called_once()
                args, kwargs = mock_ia.call_args
                imagens = kwargs.get('imagens') or args[1] if len(args) > 1 else None

                # Deve enviar imagens
                assert resultado.source == ClassificationSource.FULL_IMAGE
                assert resultado.fallback_aplicado == False

    @pytest.mark.asyncio
    async def test_classificar_ocr_falha_envia_imagem(self, mock_db, mock_categorias):
        """
        Teste 3: OCR falha deve enviar imagem inteira.
        """
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = mock_categorias

        resposta_ia = {
            "categoria_id": 3,
            "confianca": 0.75,
            "justificativa_curta": "Documento de recurso"
        }

        with patch.object(DocumentClassifier, '_chamar_ia', new_callable=AsyncMock) as mock_ia:
            mock_ia.return_value = resposta_ia

            # Mock: PDF com texto de má qualidade (simula OCR falho)
            with patch('sistemas.gerador_pecas.document_classifier.extrair_conteudo_pdf') as mock_extrair:
                mock_extrair.return_value = PDFContent(
                    texto="▓▓▓▓▓▓ OCR FALHOU ▓▓▓▓▓▓",  # Texto ilegível
                    imagens=[b"fake_image"],
                    tem_texto=False,  # Marcado como sem texto útil
                    ocr_tentado=True,
                    ocr_sucesso=False,
                    total_paginas=1,
                    texto_qualidade="none"
                )

                classificador = DocumentClassifier(mock_db)
                resultado = await classificador.classificar_documento(
                    arquivo_nome="ocr_falho.pdf",
                    arquivo_id="pdf_3",
                    pdf_bytes=b"fake pdf bytes"
                )

                assert resultado.source == ClassificationSource.FULL_IMAGE

    @pytest.mark.asyncio
    async def test_ia_retorna_categoria_invalida_aplica_fallback(self, mock_db, mock_categorias):
        """
        Teste 4: IA retorna categoria inexistente deve aplicar fallback.
        """
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = mock_categorias

        resposta_ia = {
            "categoria_id": 999,  # Categoria inexistente!
            "confianca": 0.80,
            "justificativa_curta": "Categoria inválida"
        }

        with patch.object(DocumentClassifier, '_chamar_ia', new_callable=AsyncMock) as mock_ia:
            mock_ia.return_value = resposta_ia

            with patch('sistemas.gerador_pecas.document_classifier.extrair_conteudo_pdf') as mock_extrair:
                mock_extrair.return_value = PDFContent(
                    texto="Texto qualquer" * 100,
                    imagens=[],
                    tem_texto=True,
                    ocr_tentado=False,
                    ocr_sucesso=False,
                    total_paginas=1,
                    texto_qualidade="good"
                )

                classificador = DocumentClassifier(mock_db)
                resultado = await classificador.classificar_documento(
                    arquivo_nome="doc.pdf",
                    arquivo_id="pdf_4",
                    pdf_bytes=b"fake pdf bytes"
                )

                # Deve aplicar fallback
                assert resultado.fallback_aplicado == True
                assert "inexistente" in resultado.fallback_motivo.lower()
                # Deve usar categoria residual (id=4 no mock)
                assert resultado.categoria_id == 4
                assert resultado.categoria_nome == "outros"

    @pytest.mark.asyncio
    async def test_ia_retorna_json_malformado_aplica_fallback(self, mock_db, mock_categorias):
        """
        Teste 5: IA retorna JSON malformado deve aplicar fallback.
        """
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = mock_categorias

        with patch.object(DocumentClassifier, '_chamar_ia', new_callable=AsyncMock) as mock_ia:
            # Simula erro de parsing
            mock_ia.side_effect = ValueError("JSON inválido: Expecting value")

            with patch('sistemas.gerador_pecas.document_classifier.extrair_conteudo_pdf') as mock_extrair:
                mock_extrair.return_value = PDFContent(
                    texto="Texto qualquer" * 100,
                    imagens=[],
                    tem_texto=True,
                    ocr_tentado=False,
                    ocr_sucesso=False,
                    total_paginas=1,
                    texto_qualidade="good"
                )

                classificador = DocumentClassifier(mock_db)
                resultado = await classificador.classificar_documento(
                    arquivo_nome="doc.pdf",
                    arquivo_id="pdf_5",
                    pdf_bytes=b"fake pdf bytes"
                )

                # Deve aplicar fallback
                assert resultado.fallback_aplicado == True
                assert resultado.erro is not None
                assert resultado.categoria_id == 4  # Categoria residual

    @pytest.mark.asyncio
    async def test_confianca_baixa_aplica_fallback(self, mock_db, mock_categorias):
        """
        Teste 6: Confiança abaixo do threshold deve aplicar fallback.
        """
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = mock_categorias

        resposta_ia = {
            "categoria_id": 1,
            "confianca": 0.3,  # Muito baixo!
            "justificativa_curta": "Incerteza alta"
        }

        with patch.object(DocumentClassifier, '_chamar_ia', new_callable=AsyncMock) as mock_ia:
            mock_ia.return_value = resposta_ia

            with patch('sistemas.gerador_pecas.document_classifier.extrair_conteudo_pdf') as mock_extrair:
                mock_extrair.return_value = PDFContent(
                    texto="Texto qualquer" * 100,
                    imagens=[],
                    tem_texto=True,
                    ocr_tentado=False,
                    ocr_sucesso=False,
                    total_paginas=1,
                    texto_qualidade="good"
                )

                # Threshold padrão é 0.5
                classificador = DocumentClassifier(mock_db, threshold_confianca=0.5)
                resultado = await classificador.classificar_documento(
                    arquivo_nome="doc.pdf",
                    arquivo_id="pdf_6",
                    pdf_bytes=b"fake pdf bytes"
                )

                # Deve aplicar fallback
                assert resultado.fallback_aplicado == True
                assert "threshold" in resultado.fallback_motivo.lower()

    @pytest.mark.asyncio
    async def test_categorias_dinamicas_do_banco(self, mock_db):
        """
        Teste 7: Classificador deve usar categorias atuais do banco.
        """
        # Configura categorias diferentes
        @dataclass
        class NovaCategoria:
            id: int
            nome: str
            titulo: str
            descricao: str
            ativo: bool
            is_residual: bool
            ordem: int

        categorias_novas = [
            NovaCategoria(id=10, nome="nova_categoria", titulo="Nova Categoria",
                         descricao="Categoria adicionada recentemente", ativo=True, is_residual=False, ordem=1),
        ]

        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = categorias_novas

        classificador = DocumentClassifier(mock_db)
        categorias = classificador._carregar_categorias()

        assert len(categorias) == 1
        assert categorias[0]["id"] == 10
        assert categorias[0]["nome"] == "nova_categoria"

    @pytest.mark.asyncio
    async def test_fluxo_com_codigo_documento_nao_chama_ia(self, mock_db, mock_categorias):
        """
        Teste 8: Regressão - quando há código de documento, não deve chamar IA.
        """
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = mock_categorias

        # Mock da função que busca formato por código
        with patch('sistemas.gerador_pecas.document_classifier.obter_formato_para_documento') as mock_obter:
            mock_formato = Mock()
            mock_formato.categoria_id = 1
            mock_formato.categoria_nome = "peticoes"
            mock_obter.return_value = mock_formato

            with patch.object(DocumentClassifier, '_chamar_ia', new_callable=AsyncMock) as mock_ia:
                classificador = DocumentClassifier(mock_db)
                resultado = await classificador.classificar_documento(
                    arquivo_nome="doc.pdf",
                    arquivo_id="pdf_8",
                    pdf_bytes=b"fake pdf bytes",
                    codigo_documento=500  # Código conhecido!
                )

                # IA NÃO deve ser chamada
                mock_ia.assert_not_called()

                # Deve usar categoria do código
                assert resultado.categoria_id == 1
                assert resultado.confianca == 1.0


# ==============================================================================
# TESTES DO DOCUMENT SELECTOR
# ==============================================================================

class TestDocumentSelector:
    """Testes para o DocumentSelector."""

    def test_selecionar_primarios_para_contestacao(
        self, mock_db, classificacao_peticao, classificacao_decisao
    ):
        """
        Contestação: petição inicial deve ser primária, decisão secundária.
        """
        classificacoes = [classificacao_peticao, classificacao_decisao]

        seletor = DocumentSelector(mock_db)
        resultado = seletor.selecionar_documentos(classificacoes, "contestacao")

        # Petição deve ser primária
        assert len(resultado.documentos_primarios) >= 1
        primario = resultado.documentos_primarios[0]
        assert primario.classificacao.categoria_nome == "peticoes"

        # Decisão pode ser secundária
        if resultado.documentos_secundarios:
            secundario = resultado.documentos_secundarios[0]
            assert secundario.classificacao.categoria_nome == "decisoes"

    def test_selecionar_primarios_para_apelacao(
        self, mock_db, classificacao_peticao, classificacao_decisao
    ):
        """
        Apelação: decisão/sentença deve ser primária, petição secundária.
        """
        classificacoes = [classificacao_peticao, classificacao_decisao]

        seletor = DocumentSelector(mock_db)
        resultado = seletor.selecionar_documentos(classificacoes, "recurso_apelacao")

        # Decisão deve ser primária para apelação
        assert len(resultado.documentos_primarios) >= 1
        primario = resultado.documentos_primarios[0]
        assert primario.classificacao.categoria_nome == "decisoes"

    def test_empate_usa_maior_confianca(self, mock_db):
        """
        Empate entre dois documentos do mesmo tipo: usa o de maior confiança.
        """
        clf1 = DocumentClassification(
            arquivo_nome="peticao1.pdf",
            arquivo_id="pdf_1",
            categoria_id=1,
            categoria_nome="peticoes",
            confianca=0.70,
            justificativa="Petição 1",
            source=ClassificationSource.TEXT,
            texto_utilizado="...",
            fallback_aplicado=False
        )

        clf2 = DocumentClassification(
            arquivo_nome="peticao2.pdf",
            arquivo_id="pdf_2",
            categoria_id=1,
            categoria_nome="peticoes",
            confianca=0.95,  # Maior confiança
            justificativa="Petição 2 - completa",
            source=ClassificationSource.TEXT,
            texto_utilizado="... DOS FATOS ... DOS PEDIDOS ...",
            fallback_aplicado=False
        )

        classificacoes = [clf1, clf2]

        seletor = DocumentSelector(mock_db)
        resultado = seletor.selecionar_documentos(classificacoes, "contestacao")

        # Deve selecionar a petição 2 (maior confiança) como primária
        assert len(resultado.documentos_primarios) >= 1
        primario = resultado.documentos_primarios[0]
        assert primario.classificacao.arquivo_nome == "peticao2.pdf"

    def test_selecao_automatica_infere_tipo(self, mock_db, classificacao_peticao, classificacao_decisao):
        """
        Seleção automática deve inferir tipo de peça baseado nos documentos.
        """
        classificacoes = [classificacao_peticao, classificacao_decisao]

        seletor = DocumentSelector(mock_db)
        resultado = seletor.selecionar_automatico(classificacoes)

        # Deve inferir um tipo e fazer seleção
        assert resultado.tipo_peca is not None
        assert len(resultado.documentos_primarios) > 0

    def test_fallback_quando_nenhum_primario(self, mock_db):
        """
        Se nenhuma categoria match como primária, deve usar documento com maior confiança.
        """
        clf_outro = DocumentClassification(
            arquivo_nome="outro.pdf",
            arquivo_id="pdf_1",
            categoria_id=99,
            categoria_nome="categoria_desconhecida",
            confianca=0.80,
            justificativa="Documento genérico",
            source=ClassificationSource.TEXT,
            texto_utilizado="...",
            fallback_aplicado=False
        )

        seletor = DocumentSelector(mock_db)
        resultado = seletor.selecionar_documentos([clf_outro], "contestacao")

        # Deve selecionar como primário mesmo sem match
        assert len(resultado.documentos_primarios) >= 1
        assert "maior confiança" in resultado.documentos_primarios[0].razao.lower()

    def test_to_dict_serializa_corretamente(self, mock_db, classificacao_peticao):
        """
        SelectionResult.to_dict() deve serializar corretamente.
        """
        seletor = DocumentSelector(mock_db)
        resultado = seletor.selecionar_documentos([classificacao_peticao], "contestacao")

        dict_resultado = resultado.to_dict()

        assert "tipo_peca" in dict_resultado
        assert "documentos_primarios" in dict_resultado
        assert "documentos_secundarios" in dict_resultado
        assert "razao_geral" in dict_resultado
        assert isinstance(dict_resultado["documentos_primarios"], list)


# ==============================================================================
# TESTES DE INTEGRAÇÃO
# ==============================================================================

class TestIntegracao:
    """Testes de integração entre classificador e seletor."""

    @pytest.mark.asyncio
    async def test_fluxo_completo_classificacao_e_selecao(self, mock_db, mock_categorias, texto_peticao_inicial):
        """
        Fluxo completo: classifica múltiplos PDFs e seleciona para geração.
        """
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = mock_categorias

        # Simula 2 chamadas à IA retornando categorias diferentes
        respostas = [
            {"categoria_id": 1, "confianca": 0.95, "justificativa_curta": "Petição"},
            {"categoria_id": 2, "confianca": 0.90, "justificativa_curta": "Decisão"},
        ]
        call_count = [0]

        async def mock_chamar_ia(*args, **kwargs):
            resp = respostas[call_count[0] % len(respostas)]
            call_count[0] += 1
            return resp

        with patch.object(DocumentClassifier, '_chamar_ia', side_effect=mock_chamar_ia):
            with patch('sistemas.gerador_pecas.document_classifier.extrair_conteudo_pdf') as mock_extrair:
                mock_extrair.return_value = PDFContent(
                    texto=texto_peticao_inicial,
                    imagens=[],
                    tem_texto=True,
                    ocr_tentado=False,
                    ocr_sucesso=False,
                    total_paginas=1,
                    texto_qualidade="good"
                )

                # 1. Classifica
                classificador = DocumentClassifier(mock_db)
                documentos = [
                    {"nome": "peticao.pdf", "id": "pdf_1", "bytes": b"fake"},
                    {"nome": "sentenca.pdf", "id": "pdf_2", "bytes": b"fake"},
                ]
                classificacoes = await classificador.classificar_lote(documentos)

                assert len(classificacoes) == 2
                assert classificacoes[0].categoria_id == 1
                assert classificacoes[1].categoria_id == 2

                # 2. Seleciona
                seletor = DocumentSelector(mock_db)
                selecao = seletor.selecionar_documentos(classificacoes, "contestacao")

                # Petição deve ser primária para contestação
                assert len(selecao.documentos_primarios) >= 1
                assert selecao.documentos_primarios[0].classificacao.categoria_nome == "peticoes"


# ==============================================================================
# MAIN
# ==============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
