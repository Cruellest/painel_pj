#!/usr/bin/env python
"""
Script de debug para verificar o fluxo de busca de NAT no processo de origem.

Este script simula o fluxo completo do AgenteTJMSIntegrado e mostra em cada etapa
o que está acontecendo com a busca de NAT.

Uso:
    python scripts/debug_nat_origem.py [numero_processo]

Exemplo:
    python scripts/debug_nat_origem.py 1419974-57.2025.8.12.0000
"""
import sys
import os
import asyncio
import json
import logging

# Configura path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configura logging para ver mensagens do NAT
logging.basicConfig(level=logging.INFO, format='%(name)s - %(message)s')
logger_nat = logging.getLogger("nat_origem_resolver")
logger_nat.setLevel(logging.DEBUG)

from database.connection import SessionLocal


async def debug_nat_origem(numero_processo: str):
    """Debug completo do fluxo de busca de NAT no processo de origem."""

    import aiohttp
    from sistemas.gerador_pecas.agente_tjms import (
        consultar_processo_async,
        extrair_documentos_xml,
        DocumentoTJMS,
        MODELO_PADRAO
    )
    from sistemas.gerador_pecas.services_nat_origem import (
        extrair_dados_peticao_inicial,
        verificar_nat_em_documentos,
        verificar_agravo_por_documentos,
        NATOrigemResolver,
        CODIGOS_NAT,
        CODIGOS_INDICADORES_AGRAVO,
    )
    from sistemas.gerador_pecas.extrator_resumo_json import GerenciadorFormatosJSON

    print("=" * 70)
    print(f"DEBUG: FLUXO DE NAT NO PROCESSO DE ORIGEM")
    print(f"Processo: {numero_processo}")
    print("=" * 70)

    db = SessionLocal()

    try:
        # ETAPA 1: Consultar processo
        print("\n[ETAPA 1] Consultando processo no TJ-MS...")

        connector = aiohttp.TCPConnector(limit=10, limit_per_host=10)
        async with aiohttp.ClientSession(connector=connector) as session:
            xml = await consultar_processo_async(session, numero_processo, timeout=60)

            if '<sucesso>false</sucesso>' in xml:
                print("ERRO: Processo não encontrado no TJ-MS")
                return

            documentos = extrair_documentos_xml(xml)
            print(f"    Documentos encontrados: {len(documentos)}")

        # ETAPA 2: Listar documentos
        print("\n[ETAPA 2] Documentos do processo:")
        CODIGOS_PI = {500, 9500, 10}
        peticao_inicial = None

        for doc in documentos:
            marker = ""
            try:
                codigo = int(doc.tipo_documento)
                if codigo in CODIGOS_NAT:
                    marker = " [NAT]"
                elif codigo in CODIGOS_PI:
                    marker = " [PETICAO INICIAL]"
                    if not peticao_inicial:
                        peticao_inicial = doc
            except:
                pass
            print(f"    - ID: {doc.id} | Código: {doc.tipo_documento} | {doc.descricao}{marker}")

        # ETAPA 3: Verificar NAT no processo
        print("\n[ETAPA 3] Verificando NAT no processo...")
        docs_nat = verificar_nat_em_documentos(documentos)
        if docs_nat:
            print(f"    NAT ENCONTRADO: {len(docs_nat)} documento(s)")
            for doc in docs_nat:
                print(f"    - ID: {doc.id} | Código: {doc.tipo_documento}")
            print("\n    >>> Se NAT existe no agravo, NÃO será buscado na origem!")
        else:
            print("    NAT NÃO encontrado - busca na origem será necessária se for agravo")

        # ETAPA 4: Verificar mapeamento de formato
        print("\n[ETAPA 4] Verificando mapeamento de formato da petição inicial...")
        gerenciador = GerenciadorFormatosJSON(db)
        gerenciador.preparar_lote(documentos)

        if peticao_inicial:
            codigo = int(peticao_inicial.tipo_documento) if peticao_inicial.tipo_documento else 0
            formato = gerenciador.obter_formato(codigo, doc_id=peticao_inicial.id)

            if formato:
                print(f"    Categoria mapeada: {formato.categoria_nome} (ID {formato.categoria_id})")

                # Verifica se o formato tem os campos necessários
                formato_dict = json.loads(formato.formato_json) if isinstance(formato.formato_json, str) else formato.formato_json

                if "peticao_inicial_agravo" in formato_dict:
                    print("    Campo peticao_inicial_agravo: EXISTE no schema")
                else:
                    print("    PROBLEMA: Campo peticao_inicial_agravo NÃO existe no schema!")

                if "peticao_inicial_num_origem" in formato_dict:
                    print("    Campo peticao_inicial_num_origem: EXISTE no schema")
                else:
                    print("    PROBLEMA: Campo peticao_inicial_num_origem NÃO existe no schema!")
            else:
                print("    PROBLEMA: Nenhum formato encontrado para a petição inicial!")
        else:
            print("    PROBLEMA: Nenhuma petição inicial encontrada!")

        # ETAPA 5: Simular extração (se possível, verificar resumo existente)
        print("\n[ETAPA 5] Verificando resumo da petição inicial...")
        if peticao_inicial:
            if peticao_inicial.resumo:
                print(f"    Resumo encontrado ({len(peticao_inicial.resumo)} chars)")

                # Tenta parsear como JSON
                resumo_limpo = peticao_inicial.resumo.strip()
                if resumo_limpo.startswith('```json'):
                    resumo_limpo = resumo_limpo[7:]
                elif resumo_limpo.startswith('```'):
                    resumo_limpo = resumo_limpo[3:]
                if resumo_limpo.endswith('```'):
                    resumo_limpo = resumo_limpo[:-3]
                resumo_limpo = resumo_limpo.strip()

                if resumo_limpo.startswith('{'):
                    try:
                        dados = json.loads(resumo_limpo)
                        print(f"    Campos extraídos: {len(dados)}")

                        # Verifica campos críticos
                        if "peticao_inicial_agravo" in dados:
                            valor = dados["peticao_inicial_agravo"]
                            print(f"    >>> peticao_inicial_agravo = {valor} (tipo: {type(valor).__name__})")

                            if valor is True or str(valor).lower() in ("true", "sim", "yes", "1"):
                                print("    >>> É AGRAVO - busca de NAT na origem DEVERIA ser acionada")
                            else:
                                print("    >>> NÃO é agravo - busca de NAT na origem NÃO será acionada")
                        else:
                            print("    >>> PROBLEMA: Campo peticao_inicial_agravo NÃO foi extraído!")

                        if "peticao_inicial_num_origem" in dados:
                            print(f"    >>> peticao_inicial_num_origem = {dados['peticao_inicial_num_origem']}")
                        else:
                            print("    >>> peticao_inicial_num_origem não encontrado")

                    except json.JSONDecodeError as e:
                        print(f"    ERRO ao parsear JSON: {e}")
                        print(f"    Primeiros 200 chars: {resumo_limpo[:200]}")
                else:
                    print("    Resumo não está em formato JSON")
                    print(f"    Primeiros 200 chars: {peticao_inicial.resumo[:200]}")
            else:
                print("    Documento não foi processado (sem resumo)")
                print("    >>> Isso é esperado em uma consulta simples à API")
                print("    >>> Para teste completo, execute o AgenteTJMSIntegrado")

        # ETAPA 6: Simular a função extrair_dados_peticao_inicial
        print("\n[ETAPA 6] Simulando extrair_dados_peticao_inicial()...")

        # Cria um ResultadoAnalise fake para testar
        class FakeResultado:
            def __init__(self, docs):
                self.documentos = docs
                self.numero_processo = numero_processo

        fake_resultado = FakeResultado(documentos)
        dados_pi = extrair_dados_peticao_inicial(fake_resultado)

        if dados_pi:
            print(f"    Dados extraídos: {len(dados_pi)} campos")
            for k, v in dados_pi.items():
                if k.startswith("peticao_inicial"):
                    print(f"    - {k}: {v}")
        else:
            print("    Nenhum dado extraído da petição inicial")
            print("    >>> Isso é normal se os documentos não foram processados com IA")

        # ETAPA 7: Verificar fallback de detecção de agravo
        print("\n[ETAPA 7] Verificando fallback de detecção de agravo...")
        is_agravo_fallback = verificar_agravo_por_documentos(documentos)
        if is_agravo_fallback:
            print(f"    FALLBACK ATIVADO: Agravo detectado por documento indicador")
            print(f"    Códigos indicadores: {CODIGOS_INDICADORES_AGRAVO}")
        else:
            print("    Nenhum documento indicador de agravo encontrado")

        # ETAPA 8: Conclusão
        print("\n" + "=" * 70)
        print("DIAGNÓSTICO:")
        print("=" * 70)

        if docs_nat:
            print("1. NAT EXISTE no processo atual -> busca na origem NÃO é necessária")
        else:
            print("1. NAT NÃO existe no processo atual -> busca na origem é necessária se for agravo")

        is_agravo_json = dados_pi and dados_pi.get("peticao_inicial_agravo")
        if is_agravo_json:
            print("2. Processo É um agravo (via JSON) -> busca de NAT na origem DEVERIA ser acionada")
        elif is_agravo_fallback:
            print("2. Processo É um agravo (via FALLBACK) -> busca de NAT na origem DEVERIA ser acionada")
            print("   (Campo peticao_inicial_agravo não encontrado, mas Decisão Agravada presente)")
        else:
            print("2. Processo NÃO é agravo -> busca NÃO será acionada")

        if dados_pi and dados_pi.get("peticao_inicial_num_origem"):
            print(f"3. Número de origem disponível: {dados_pi.get('peticao_inicial_num_origem')}")
        else:
            print("3. Número de origem NÃO disponível -> mesmo se for agravo, não é possível buscar")

        print("\nPara verificar o fluxo completo, execute o AgenteTJMSIntegrado:")
        print("    ou verifique os logs quando o processo for executado pela interface.")

    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        numero_processo = sys.argv[1]
    else:
        numero_processo = "1419974-57.2025.8.12.0000"

    asyncio.run(debug_nat_origem(numero_processo))
