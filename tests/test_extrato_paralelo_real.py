#!/usr/bin/env python
# tests/test_extrato_paralelo_real.py
"""
Teste REAL de extração paralela de extrato de subconta.

Executa o fluxo completo garantindo que AMBOS os métodos são executados:
- Scrapper de subconta
- Fallback por busca em documentos

Reporta métricas de tempo e fonte utilizada.

Uso:
    python tests/test_extrato_paralelo_real.py [numero_cnj]

Exemplo:
    python tests/test_extrato_paralelo_real.py 0857327-80.2025.8.12.0001
"""

import asyncio
import logging
import sys
import time
from datetime import datetime

# Configura logging detalhado
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Adiciona path do projeto
sys.path.insert(0, ".")


async def executar_teste_real(numero_cnj: str):
    """
    Executa teste real do pipeline de extração paralela.

    Args:
        numero_cnj: Número CNJ do processo a testar
    """
    import aiohttp
    from sistemas.prestacao_contas.extrato_paralelo import (
        ExtratorParalelo,
        ConfigExtratoParalelo,
        ExtratoSource,
    )
    from sistemas.pedido_calculo.document_downloader import (
        consultar_processo_async,
    )
    from sistemas.prestacao_contas.xml_parser import parse_xml_processo

    print("\n" + "=" * 70)
    print(f"TESTE REAL DE EXTRAÇÃO PARALELA")
    print(f"Processo: {numero_cnj}")
    print(f"Início: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70 + "\n")

    inicio_total = time.time()

    # =====================================================
    # ETAPA 1: CONSULTA XML DO PROCESSO
    # =====================================================
    print("[1/3] Consultando XML do processo...")
    inicio_xml = time.time()

    async with aiohttp.ClientSession() as session:
        xml_response = await consultar_processo_async(session, numero_cnj)

    resultado_xml = parse_xml_processo(xml_response)
    t_xml = time.time() - inicio_xml

    if resultado_xml.erro:
        print(f"ERRO: {resultado_xml.erro}")
        return

    print(f"      Processo encontrado: {resultado_xml.dados_basicos.autor}")
    print(f"      Total de documentos: {len(resultado_xml.documentos)}")
    print(f"      Tempo XML: {t_xml:.2f}s")

    # Conta documentos código 71 (Extrato da Conta Única)
    extratos_cod_71 = [d for d in resultado_xml.documentos if str(d.tipo_codigo) == "71"]
    print(f"      Documentos código 71 (fallback): {len(extratos_cod_71)}")

    # =====================================================
    # ETAPA 2: EXTRAÇÃO PARALELA DE EXTRATO
    # =====================================================
    print("\n[2/3] Executando extração paralela (scrapper + fallback)...")

    # Configura extração com timeouts para teste real
    config = ConfigExtratoParalelo(
        scrapper_timeout=60.0,   # 1 minuto
        fallback_timeout=60.0,   # 1 minuto
        min_caracteres_extrato=200,
        min_caracteres_util=500,
    )

    correlation_id = f"test_{datetime.now().strftime('%H%M%S')}"

    extrator = ExtratorParalelo(config=config, correlation_id=correlation_id)
    resultado = await extrator.extrair_paralelo(
        numero_cnj=numero_cnj,
        documentos=resultado_xml.documentos,
    )

    # =====================================================
    # ETAPA 3: RELATÓRIO DE RESULTADOS
    # =====================================================
    t_total = time.time() - inicio_total

    print("\n[3/3] Relatório de Resultados")
    print("-" * 50)

    # Métricas de tempo
    print("\nMÉTRICAS DE TEMPO:")
    print(f"  t_scrapper:  {resultado.metricas.t_scrapper:.2f}s" if resultado.metricas.t_scrapper else "  t_scrapper:  N/A")
    print(f"  t_fallback:  {resultado.metricas.t_fallback:.2f}s" if resultado.metricas.t_fallback else "  t_fallback:  N/A")
    print(f"  t_xml:       {t_xml:.2f}s")
    print(f"  t_total:     {t_total:.2f}s (pipeline completo)")

    # Fonte utilizada
    print(f"\nFONTE DO EXTRATO:")
    print(f"  extrato_source: {resultado.source.value}")
    print(f"  extrato_valido: {resultado.valido}")

    # Detalhes de falha (se houver)
    if resultado.metricas.scrapper_fail_reason:
        print(f"\nFALHA SCRAPPER:")
        print(f"  Motivo: {resultado.metricas.scrapper_fail_reason.value}")
        print(f"  Erro: {resultado.metricas.scrapper_erro}")

    if resultado.metricas.fallback_fail_reason:
        print(f"\nFALHA FALLBACK:")
        print(f"  Motivo: {resultado.metricas.fallback_fail_reason.value}")
        print(f"  Erro: {resultado.metricas.fallback_erro}")

    # Conteúdo do extrato
    if resultado.valido:
        print(f"\nEXTRATO OBTIDO:")
        print(f"  Tamanho texto: {len(resultado.texto or '')} caracteres")
        print(f"  Tem PDF: {'Sim' if resultado.pdf_bytes else 'Não'}")
        print(f"  Imagens fallback: {len(resultado.imagens_fallback)}")

        # Preview do texto
        if resultado.texto:
            preview = resultado.texto[:500].replace('\n', ' ')
            print(f"\n  Preview do texto:")
            print(f"  {preview}...")
    else:
        print(f"\nEXTRATO NÃO LOCALIZADO:")
        print(f"  Observação: {resultado.observacao}")

    # Verificação de paralelismo
    print("\n" + "=" * 50)
    print("VERIFICAÇÃO DE PARALELISMO:")
    print("=" * 50)

    # Verifica se ambos os métodos foram executados
    scrapper_executado = resultado.metricas.t_scrapper is not None
    fallback_executado = resultado.metricas.t_fallback is not None

    print(f"  Scrapper executado: {'SIM' if scrapper_executado else 'NÃO'}")
    print(f"  Fallback executado: {'SIM' if fallback_executado else 'NÃO'}")

    if scrapper_executado and fallback_executado:
        # Calcula ganho de paralelismo
        tempo_sequencial = (resultado.metricas.t_scrapper or 0) + (resultado.metricas.t_fallback or 0)
        tempo_paralelo = resultado.metricas.t_total

        if tempo_sequencial > 0:
            ganho = ((tempo_sequencial - tempo_paralelo) / tempo_sequencial) * 100
            print(f"\n  Tempo se fosse sequencial: {tempo_sequencial:.2f}s")
            print(f"  Tempo paralelo:            {tempo_paralelo:.2f}s")
            print(f"  Ganho de performance:      {ganho:.1f}%")

        # Verifica se não ficou ocioso
        if resultado.source == ExtratoSource.SCRAPPER and resultado.metricas.t_scrapper:
            if resultado.metricas.t_scrapper > 30:  # Scrapper demorou mais de 30s
                print(f"\n  NOTA: Scrapper demorou {resultado.metricas.t_scrapper:.1f}s mas o pipeline")
                print(f"        NÃO ficou ocioso pois o fallback rodou em paralelo.")
    else:
        print(f"\n  AVISO: Nem todos os métodos foram executados.")
        print(f"         Isso pode indicar um problema na implementação.")

    # Resumo final
    print("\n" + "=" * 70)
    print("RESUMO DO TESTE")
    print("=" * 70)
    print(f"  Processo:        {numero_cnj}")
    print(f"  Fonte usada:     {resultado.source.value}")
    print(f"  Extrato válido:  {resultado.valido}")
    print(f"  Tempo total:     {t_total:.2f}s")
    print(f"  Correlation ID:  {correlation_id}")

    if resultado.valido:
        print("\n  STATUS: SUCESSO - Extrato obtido")
    else:
        print("\n  STATUS: PARCIAL - Pipeline continuou sem extrato")
        print(f"  (A análise final pode prosseguir com observação)")

    print("=" * 70 + "\n")

    return resultado


if __name__ == "__main__":
    # Número CNJ padrão ou passado como argumento
    numero_cnj = sys.argv[1] if len(sys.argv) > 1 else "0857327-80.2025.8.12.0001"

    # Executa teste
    asyncio.run(executar_teste_real(numero_cnj))
