#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de teste da correcao de deteccao de agravo em processos evoluidos.

Verifica que a correcao aplicada no router.py esta funcionando:
- Processo de conhecimento (classe 7) deve detectar agravos mencionados
- Cumprimento autonomo deve continuar detectando agravos no processo de origem

Caso real: Processo 0806261-10.2025.8.12.0018 (classe 7)
Agravo esperado: 1420866-63.2025.8.12.0000
"""

import asyncio
import sys
import os

# Adiciona o diretorio raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.tjms import DocumentDownloader
from sistemas.relatorio_cumprimento.agravo_detector import (
    detect_and_validate_agravos,
    fetch_all_agravo_documents,
    format_numero_cnj
)
from sistemas.pedido_calculo.xml_parser import XMLParser


NUMERO_PROCESSO = "0806261-10.2025.8.12.0018"
NUMERO_AGRAVO_ESPERADO = "1420866-63.2025.8.12.0000"


async def testar_correcao():
    print("=" * 80)
    print("TESTE DA CORRECAO: Deteccao de Agravo em Processos Evoluidos")
    print("=" * 80)

    print(f"\n[1] Consultando processo {NUMERO_PROCESSO}...")
    async with DocumentDownloader() as downloader:
        xml_texto = await downloader.consultar_processo(NUMERO_PROCESSO)
    print(f"    XML obtido: {len(xml_texto)} caracteres")

    # Verifica tipo de processo
    parser = XMLParser(xml_texto)
    docs_info = parser.identificar_documentos_para_download()
    print(f"\n[2] Verificando tipo de processo:")
    print(f"    is_cumprimento_autonomo: {docs_info.is_cumprimento_autonomo}")
    print(f"    numero_processo_origem: {docs_info.numero_processo_origem}")

    # Simula a logica corrigida do router.py
    print("\n[3] Simulando logica CORRIGIDA do router.py:")
    xml_para_detectar_agravo = None
    fonte_agravo = None

    if docs_info.is_cumprimento_autonomo and docs_info.numero_processo_origem:
        # Cenario 1: Cumprimento autonomo - busca no processo de ORIGEM
        print("    Modo: cumprimento_autonomo")
        print(f"    Buscaria agravos no processo de origem: {docs_info.numero_processo_origem}")
        async with DocumentDownloader() as downloader:
            xml_para_detectar_agravo = await downloader.consultar_processo(docs_info.numero_processo_origem)
        fonte_agravo = "processo_origem"
    else:
        # Cenario 2: Processo evoluido - busca no PROPRIO processo
        print("    Modo: processo_evoluido (conhecimento)")
        print("    Buscando agravos no PROPRIO processo")
        xml_para_detectar_agravo = xml_texto
        fonte_agravo = "processo_atual"

    # Detecta e valida agravos
    print(f"\n[4] Detectando agravos (fonte: {fonte_agravo})...")
    resultado = await detect_and_validate_agravos(xml_para_detectar_agravo, request_id="CORRECAO_TEST")

    print(f"\n    RESULTADO:")
    print(f"    - Candidatos detectados: {len(resultado.candidatos_detectados)}")
    print(f"    - Agravos validados: {len(resultado.agravos_validados)}")
    print(f"    - Agravos rejeitados: {len(resultado.agravos_rejeitados)}")

    if resultado.candidatos_detectados:
        print(f"\n    CANDIDATOS:")
        for c in resultado.candidatos_detectados:
            print(f"        - {format_numero_cnj(c.numero_cnj)}")

    if resultado.agravos_validados:
        print(f"\n    AGRAVOS VALIDADOS:")
        for a in resultado.agravos_validados:
            print(f"        - {a.numero_formatado} (score: {a.score_similaridade:.0%})")
            print(f"          Decisoes: {len(a.ids_decisoes)}, Acordaos: {len(a.ids_acordaos)}")

        # Baixa documentos
        print(f"\n[5] Baixando documentos dos agravos...")
        docs_agravo = await fetch_all_agravo_documents(resultado.agravos_validados, request_id="CORRECAO_TEST")
        print(f"    Documentos baixados: {len(docs_agravo)}")
        for doc in docs_agravo:
            print(f"        - {doc.categoria.value}: {doc.nome_original}")
            conteudo_preview = (doc.conteudo_texto or '')[:100].replace('\n', ' ')
            print(f"          Conteudo: {conteudo_preview}...")

    # Verifica se encontrou o agravo esperado
    print("\n" + "=" * 80)
    print("VERIFICACAO FINAL")
    print("=" * 80)

    agravo_encontrado = any(
        a.numero_formatado == NUMERO_AGRAVO_ESPERADO
        for a in resultado.agravos_validados
    )

    if agravo_encontrado:
        print(f"\n[OK] SUCESSO! Agravo {NUMERO_AGRAVO_ESPERADO} foi detectado e validado!")
        print("     A correcao esta funcionando corretamente.")
        return True
    else:
        candidato_existe = any(
            format_numero_cnj(c.numero_cnj) == NUMERO_AGRAVO_ESPERADO
            for c in resultado.candidatos_detectados
        )
        if candidato_existe:
            print(f"\n[PARCIAL] Agravo foi detectado como candidato, mas nao foi validado.")
            print("          Pode haver problema na comparacao de partes.")
        else:
            print(f"\n[FALHA] Agravo {NUMERO_AGRAVO_ESPERADO} NAO foi detectado!")
            print("        A correcao pode nao estar completa.")
        return False


if __name__ == "__main__":
    success = asyncio.run(testar_correcao())
    sys.exit(0 if success else 1)
