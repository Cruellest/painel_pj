# -*- coding: utf-8 -*-
"""
Teste end-to-end do sistema de Pedido de Cálculo

Simula o fluxo completo:
1. Análise do XML (Agente 1)
2. Detecção de cumprimento autônomo
3. Busca do processo de origem
4. Download de documentos
5. Extração de informações (Agente 2)
6. Geração do pedido (Agente 3)
"""

import asyncio
import sys
import os
import pytest

# Adiciona o diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

XML_ENV_VAR = "PEDIDO_CALCULO_XML_PATH"
pytestmark = pytest.mark.asyncio

def _skip_if_missing_xml():
    path = os.getenv(XML_ENV_VAR)
    if not path:
        pytest.skip(f"Defina {XML_ENV_VAR} com o caminho do XML para rodar este teste.")
    if not os.path.exists(path):
        pytest.skip(f"Arquivo XML nao encontrado: {path}")
    return path

def _skip_if_missing_soap():
    url = os.getenv('URL_WSDL') or os.getenv('TJ_WSDL_URL') or os.getenv('TJ_URL_WSDL')
    user = os.getenv('WS_USER') or os.getenv('TJ_WS_USER')
    password = os.getenv('WS_PASS') or os.getenv('TJ_WS_PASS')
    missing = []
    if not url:
        missing.append('URL_WSDL/TJ_WSDL_URL/TJ_URL_WSDL')
    if not user:
        missing.append('WS_USER/TJ_WS_USER')
    if not password:
        missing.append('WS_PASS/TJ_WS_PASS')
    if missing:
        pytest.skip('Variaveis de ambiente faltando para SOAP: ' + ', '.join(missing))
    return True

def _skip_if_missing_gemini():
    if not os.getenv('GEMINI_KEY'):
        pytest.skip('GEMINI_KEY nao definido; pulando testes de IA.')
    return True

@pytest.fixture(scope='session')
def xml_path():
    pytest.importorskip('pytest_asyncio')
    return _skip_if_missing_xml()

@pytest.fixture(scope='session')
def soap_config():
    return _skip_if_missing_soap()

@pytest.fixture(scope='session')
def gemini_config():
    return _skip_if_missing_gemini()

@pytest.fixture(scope='session')
async def analise_xml_result(xml_path):
    return await test_analise_xml(xml_path)

@pytest.fixture(scope='session')
def parser_xml(analise_xml_result):
    return analise_xml_result[0]

@pytest.fixture(scope='session')
def documentos(analise_xml_result):
    return analise_xml_result[1]

@pytest.fixture(scope='session')
def dados_basicos(analise_xml_result):
    return analise_xml_result[2]

@pytest.fixture(scope='session')
def agente1_result(parser_xml, documentos, dados_basicos):
    from sistemas.pedido_calculo.models import ResultadoAgente1
    movimentos = parser_xml.extrair_movimentos_relevantes()
    return ResultadoAgente1(
        dados_basicos=dados_basicos,
        documentos_para_download=documentos,
        movimentos_relevantes=movimentos
    )

@pytest.fixture(scope='session')
async def origem_result(soap_config, documentos, dados_basicos):
    return await test_busca_origem(documentos, dados_basicos)

@pytest.fixture(scope='session')
def numero_origem(origem_result):
    return origem_result[0]

@pytest.fixture(scope='session')
def docs_origem(origem_result):
    return origem_result[1]

@pytest.fixture(scope='session')
async def textos_organizados(soap_config, documentos, dados_basicos, numero_origem, docs_origem):
    return await test_download_documentos(documentos, dados_basicos, numero_origem, docs_origem)

@pytest.fixture(scope='session')
async def agente2_result(gemini_config, textos_organizados):
    resultado = await test_extracao_ia(textos_organizados)
    if not resultado:
        pytest.skip('Extracao IA nao retornou resultado.')
    if getattr(resultado, 'erro', None):
        pytest.skip(f'Extracao IA retornou erro: {resultado.erro}')
    return resultado

from sistemas.pedido_calculo.xml_parser import XMLParser, CLASSES_CUMPRIMENTO_AUTONOMO
from sistemas.pedido_calculo.services import PedidoCalculoService
from sistemas.pedido_calculo.agentes import ExtratorProcessoOrigem, Agente2ExtracaoPDFs


async def test_analise_xml(xml_path: str):
    """Testa análise do XML (Etapa 1)"""
    print("=" * 70)
    print("ETAPA 1: ANÁLISE DO XML")
    print("=" * 70)

    # Carrega XML
    with open(xml_path, 'r', encoding='utf-8') as f:
        xml_texto = f.read()

    print(f"XML carregado: {len(xml_texto):,} caracteres")

    # Inicializa parser
    parser = XMLParser(xml_texto)

    # Extrai dados básicos
    dados_basicos = parser.extrair_dados_basicos()
    print(f"\n--- Dados Básicos ---")
    print(f"Número: {dados_basicos.numero_processo}")
    print(f"Autor: {dados_basicos.autor}")
    print(f"CPF: {dados_basicos.cpf_autor}")
    print(f"Réu: {dados_basicos.reu}")
    print(f"Comarca: {dados_basicos.comarca}")
    print(f"Vara: {dados_basicos.vara}")
    print(f"Data ajuizamento: {dados_basicos.data_ajuizamento}")
    print(f"Valor da causa: {dados_basicos.valor_causa}")

    # Identifica documentos
    documentos = parser.identificar_documentos_para_download()
    print(f"\n--- Documentos Identificados ---")
    print(f"Sentenças: {len(documentos.sentencas)}")
    for s in documentos.sentencas:
        print(f"  - ID: {s}")
    print(f"Acórdãos: {len(documentos.acordaos)}")
    for a in documentos.acordaos:
        print(f"  - ID: {a}")
    print(f"Certidões citação/intimação: {len(documentos.certidoes_citacao_intimacao)}")
    for c in documentos.certidoes_citacao_intimacao:
        print(f"  - Tipo: {c.tipo.value}, Cert: {c.tipo_certidao}")
        print(f"    ID: {c.id_certidao_9508}")
        print(f"    Recebimento: {c.data_recebimento}")
        print(f"    Termo inicial: {c.termo_inicial_prazo}")

    print(f"\n--- Cumprimento Autônomo ---")
    print(f"É cumprimento autônomo: {documentos.is_cumprimento_autonomo}")
    print(f"Classes autônomas: {CLASSES_CUMPRIMENTO_AUTONOMO}")

    if documentos.is_cumprimento_autonomo:
        print(f"Número processo origem (XML): {documentos.numero_processo_origem}")
        print(f"ID petição inicial: {documentos.id_peticao_inicial}")

    # Pedido de cumprimento
    if documentos.pedido_cumprimento:
        print(f"\n--- Pedido de Cumprimento ---")
        print(f"Data movimento: {documentos.pedido_cumprimento.get('data_movimento')}")
        docs_pc = documentos.pedido_cumprimento.get('documentos', [])
        print(f"Documentos: {len(docs_pc)}")
        for d in docs_pc:
            print(f"  - {d.get('descricao')}: ID {d.get('id')}")

    # Certidões candidatas (para análise com IA)
    if documentos.certidoes_candidatas:
        print(f"\n--- Certidões Candidatas (para IA) ---")
        print(f"Total: {len(documentos.certidoes_candidatas)}")
        for c in documentos.certidoes_candidatas[:5]:  # Mostra primeiras 5
            print(f"  - ID: {c.id_documento}, Tipo: {c.tipo_documento}")

    # Movimentos relevantes
    movimentos = parser.extrair_movimentos_relevantes()
    print(f"\n--- Movimentos Relevantes ---")
    print(f"Citação expedida: {movimentos.citacao_expedida}")
    print(f"Trânsito em julgado: {movimentos.transito_julgado}")
    print(f"Intimação impugnação: {movimentos.intimacao_impugnacao_expedida}")

    return parser, documentos, dados_basicos


async def test_busca_origem(documentos, dados_basicos, soap_config):
    """Testa busca do processo de origem (Etapa 1.5)"""
    print("\n" + "=" * 70)
    print("ETAPA 1.5: BUSCA DO PROCESSO DE ORIGEM")
    print("=" * 70)

    if not documentos.is_cumprimento_autonomo:
        print("Não é cumprimento autônomo - pulando etapa")
        return None, None, None

    numero_origem = documentos.numero_processo_origem

    # Se não encontrou no XML, tenta extrair da petição inicial
    if not numero_origem and documentos.id_peticao_inicial:
        print(f"Número não encontrado no XML, tentando extrair da petição inicial...")
        print(f"ID da petição: {documentos.id_peticao_inicial}")

        # Baixa a petição inicial
        from sistemas.pedido_calculo.document_downloader import DocumentDownloader

        async with DocumentDownloader() as downloader:
            textos_peticao = await downloader.baixar_e_extrair_textos(
                dados_basicos.numero_processo,
                [documentos.id_peticao_inicial]
            )

        if textos_peticao and documentos.id_peticao_inicial in textos_peticao:
            texto_peticao = textos_peticao[documentos.id_peticao_inicial]
            print(f"Petição baixada: {len(texto_peticao):,} caracteres")

            # Extrai número com IA
            extrator = ExtratorProcessoOrigem()
            numero_origem = await extrator.extrair_numero_origem(texto_peticao)

            if numero_origem:
                print(f"Número extraído pela IA: {numero_origem}")
                documentos.numero_processo_origem = numero_origem
            else:
                print("IA não conseguiu extrair o número do processo de origem")
        else:
            print("Não foi possível baixar a petição inicial")
    else:
        print(f"Número do processo de origem: {numero_origem}")

    # Se temos o número, consulta o processo de origem
    if numero_origem:
        print(f"\nConsultando processo de origem: {numero_origem}")

        from sistemas.pedido_calculo.document_downloader import DocumentDownloader

        async with DocumentDownloader() as downloader:
            xml_origem = await downloader.consultar_processo(numero_origem)

        if xml_origem:
            print(f"XML do processo de origem recebido: {len(xml_origem):,} caracteres")

            # Parseia o XML de origem
            parser_origem = XMLParser(xml_origem)
            docs_origem = parser_origem.identificar_documentos_para_download()
            movimentos_origem = parser_origem.extrair_movimentos_relevantes()

            print(f"\n--- Documentos do Processo de Origem ---")
            print(f"Sentenças: {len(docs_origem.sentencas)}")
            print(f"Acórdãos: {len(docs_origem.acordaos)}")
            print(f"Certidões: {len(docs_origem.certidoes_citacao_intimacao)}")

            # Verifica citação na origem
            cert_citacao = next((c for c in docs_origem.certidoes_citacao_intimacao if c.tipo.value == "citacao"), None)
            if cert_citacao:
                print(f"Citação do processo de origem: {cert_citacao.data_recebimento}")

            print(f"Trânsito em julgado (origem): {movimentos_origem.transito_julgado}")

            # NÃO adiciona documentos da origem à lista do cumprimento!
            # Os downloads devem ser feitos separadamente com o número do processo correto

            print(f"\n--- Resumo ---")
            print(f"Documentos do cumprimento: certidões={len(documentos.certidoes_citacao_intimacao)}")
            print(f"Documentos da origem: sentenças={len(docs_origem.sentencas)}, acórdãos={len(docs_origem.acordaos)}")

            return numero_origem, docs_origem, movimentos_origem
        else:
            print("Falha ao consultar processo de origem")

    return None, None, None


async def test_download_documentos(documentos, dados_basicos, numero_origem, docs_origem, soap_config):
    """Testa download dos documentos (Etapa 2)"""
    print("\n" + "=" * 70)
    print("ETAPA 2: DOWNLOAD DE DOCUMENTOS")
    print("=" * 70)

    from sistemas.pedido_calculo.document_downloader import DocumentDownloader

    textos = {}
    textos_organizados = {}

    # 2.1: Baixa documentos do CUMPRIMENTO
    print(f"\n--- Download do Cumprimento ({dados_basicos.numero_processo}) ---")

    ids_cumprimento = []

    # Certidões do cumprimento
    for cert in documentos.certidoes_citacao_intimacao:
        if cert.id_certidao_9508:
            ids_cumprimento.append(cert.id_certidao_9508)

    # Pedido de cumprimento (planilha)
    if documentos.pedido_cumprimento:
        for doc in documentos.pedido_cumprimento.get("documentos", []):
            if doc.get("id"):
                ids_cumprimento.append(doc["id"])

    if ids_cumprimento:
        print(f"IDs do cumprimento: {len(ids_cumprimento)}")
        for id_doc in ids_cumprimento:
            print(f"  - {id_doc}")

        async with DocumentDownloader() as downloader:
            textos_cumprimento = await downloader.baixar_e_extrair_textos(
                dados_basicos.numero_processo,
                ids_cumprimento
            )

        print(f"Baixados: {len(textos_cumprimento)}")
        textos.update(textos_cumprimento)

        # Organiza certidões do cumprimento
        for cert in documentos.certidoes_citacao_intimacao:
            if cert.id_certidao_9508 and cert.id_certidao_9508 in textos:
                if cert.tipo.value == "intimacao_impugnacao":
                    textos_organizados["certidao_intimacao"] = textos[cert.id_certidao_9508]

        # Organiza pedido de cumprimento
        if documentos.pedido_cumprimento:
            for doc in documentos.pedido_cumprimento.get("documentos", []):
                if doc.get("id") and doc["id"] in textos:
                    desc = doc.get("descricao", "").lower()
                    if "planilha" in desc or "calculo" in desc or "memoria" in desc:
                        textos_organizados["planilha_calculo"] = textos[doc["id"]]
                    else:
                        textos_organizados["pedido_cumprimento"] = textos[doc["id"]]

    # 2.2: Baixa documentos do PROCESSO DE ORIGEM
    # IMPORTANTE: Só baixar sentenças, acórdãos e certidão de CITAÇÃO
    # NÃO baixar pedido_cumprimento (tem planilha antiga) nem certidão de intimação
    if numero_origem and docs_origem:
        print(f"\n--- Download da Origem ({numero_origem}) ---")
        print("  (apenas sentenças, acórdãos e certidão de citação)")

        ids_origem = []
        ids_origem.extend(docs_origem.sentencas)
        ids_origem.extend(docs_origem.acordaos)

        # APENAS certidão de CITAÇÃO da origem (não intimação para cumprimento!)
        cert_citacao_origem = next((c for c in docs_origem.certidoes_citacao_intimacao if c.tipo.value == "citacao"), None)
        if cert_citacao_origem and cert_citacao_origem.id_certidao_9508:
            ids_origem.append(cert_citacao_origem.id_certidao_9508)

        if ids_origem:
            print(f"IDs da origem: {len(ids_origem)}")
            for id_doc in ids_origem:
                print(f"  - {id_doc}")

            async with DocumentDownloader() as downloader:
                textos_origem = await downloader.baixar_e_extrair_textos(
                    numero_origem,
                    ids_origem
                )

            print(f"Baixados: {len(textos_origem)}")
            textos.update(textos_origem)

            # Organiza sentenças
            for i, id_sent in enumerate(docs_origem.sentencas):
                if id_sent in textos:
                    key = f"sentenca_{i+1}" if i > 0 else "sentenca"
                    textos_organizados[key] = textos[id_sent]

            # Organiza acórdãos
            for i, id_ac in enumerate(docs_origem.acordaos):
                if id_ac in textos:
                    key = f"acordao_{i+1}" if i > 0 else "acordao"
                    textos_organizados[key] = textos[id_ac]

            # Organiza certidão de citação
            if cert_citacao_origem and cert_citacao_origem.id_certidao_9508:
                if cert_citacao_origem.id_certidao_9508 in textos:
                    textos_organizados["certidao_citacao"] = textos[cert_citacao_origem.id_certidao_9508]

    print(f"\n--- Resumo Final ---")
    print(f"Total documentos baixados: {len(textos)}")
    print(f"\n--- Textos Organizados por Tipo ---")
    for tipo, texto in textos_organizados.items():
        print(f"  - {tipo}: {len(texto):,} caracteres")

    return textos_organizados


async def test_extracao_ia(textos_organizados, gemini_config):
    """Testa extração com IA (Etapa 3)"""
    print("\n" + "=" * 70)
    print("ETAPA 3: EXTRAÇÃO DE INFORMAÇÕES COM IA")
    print("=" * 70)

    if not textos_organizados:
        print("Nenhum texto para extrair")
        return None

    agente2 = Agente2ExtracaoPDFs()
    resultado = await agente2.extrair(textos_organizados)

    if resultado.erro:
        print(f"ERRO: {resultado.erro}")
        return resultado

    print(f"\n--- Informações Extraídas ---")
    print(f"Objeto da condenação: {resultado.objeto_condenacao}")
    print(f"Valor solicitado: {resultado.valor_solicitado_parte}")

    if resultado.periodo_condenacao:
        print(f"Período: {resultado.periodo_condenacao.inicio} a {resultado.periodo_condenacao.fim}")

    if resultado.correcao_monetaria:
        print(f"\nCorreção monetária:")
        print(f"  - Índice: {resultado.correcao_monetaria.indice}")
        print(f"  - Termo inicial: {resultado.correcao_monetaria.termo_inicial}")
        print(f"  - Termo final: {resultado.correcao_monetaria.termo_final}")

    if resultado.juros_moratorios:
        print(f"\nJuros moratórios:")
        print(f"  - Taxa: {resultado.juros_moratorios.taxa}")
        print(f"  - Termo inicial: {resultado.juros_moratorios.termo_inicial}")
        print(f"  - Termo final: {resultado.juros_moratorios.termo_final}")

    if resultado.datas:
        print(f"\nDatas extraídas:")
        print(f"  - Citação (recebimento): {resultado.datas.citacao_recebimento}")
        print(f"  - Trânsito em julgado: {resultado.datas.transito_julgado}")
        print(f"  - Intimação impugnação: {resultado.datas.intimacao_impugnacao_recebimento}")

    if resultado.criterios_calculo:
        print(f"\nCritérios de cálculo:")
        for c in resultado.criterios_calculo:
            print(f"  - {c}")

    if resultado.calculo_exequente:
        print(f"\nCálculo do exequente:")
        print(f"  - Valor total: {resultado.calculo_exequente.valor_total}")
        print(f"  - Data base: {resultado.calculo_exequente.data_base}")

    return resultado


async def test_geracao_pedido(agente1_result, agente2_result, gemini_config):
    """Testa geração do pedido (Etapa 4)"""
    print("\n" + "=" * 70)
    print("ETAPA 4: GERAÇÃO DO PEDIDO DE CÁLCULO")
    print("=" * 70)

    from sistemas.pedido_calculo.agentes import Agente3GeracaoPedido

    agente3 = Agente3GeracaoPedido()
    markdown = await agente3.gerar(agente1_result, agente2_result)

    print(f"\n--- Pedido Gerado ({len(markdown):,} caracteres) ---")
    print(markdown[:2000])
    if len(markdown) > 2000:
        print(f"\n... [truncado, total: {len(markdown):,} caracteres]")

    return markdown


async def main():
    """Executa teste completo"""
    # Caminho do arquivo XML de teste
    xml_path = r"C:\Users\kaoye\Downloads\08229651620258120110_processo_completo.xml"

    if not os.path.exists(xml_path):
        print(f"ERRO: Arquivo não encontrado: {xml_path}")
        return

    print("=" * 70)
    print("TESTE END-TO-END - PEDIDO DE CÁLCULO")
    print("=" * 70)
    print(f"Arquivo: {xml_path}")
    print()

    try:
        # Etapa 1: Análise do XML
        parser, documentos, dados_basicos = await test_analise_xml(xml_path)

        # Cria resultado do Agente 1 para uso posterior
        from sistemas.pedido_calculo.models import ResultadoAgente1, MovimentosRelevantes
        movimentos = parser.extrair_movimentos_relevantes()
        agente1_result = ResultadoAgente1(
            dados_basicos=dados_basicos,
            documentos_para_download=documentos,
            movimentos_relevantes=movimentos
        )

        # Etapa 1.5: Busca do processo de origem (se cumprimento autônomo)
        numero_origem, docs_origem, movimentos_origem = await test_busca_origem(documentos, dados_basicos)

        # Atualiza movimentos com dados da origem (se disponíveis)
        if movimentos_origem:
            if movimentos_origem.transito_julgado:
                movimentos.transito_julgado = movimentos_origem.transito_julgado
            if movimentos_origem.citacao_expedida:
                movimentos.citacao_expedida = movimentos_origem.citacao_expedida

        # Etapa 2: Download de documentos (separados: cumprimento + origem)
        textos_organizados = await test_download_documentos(documentos, dados_basicos, numero_origem, docs_origem)

        # Etapa 3: Extração com IA
        agente2_result = await test_extracao_ia(textos_organizados)

        if agente2_result and not agente2_result.erro:
            # Etapa 4: Geração do pedido
            markdown = await test_geracao_pedido(agente1_result, agente2_result)

        print("\n" + "=" * 70)
        print("TESTE CONCLUÍDO COM SUCESSO!")
        print("=" * 70)

    except Exception as e:
        import traceback
        print("\n" + "=" * 70)
        print(f"ERRO NO TESTE: {e}")
        print("=" * 70)
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
