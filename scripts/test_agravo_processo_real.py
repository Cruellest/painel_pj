# scripts/test_agravo_processo_real.py
"""
Teste dirigido com processo real - Validação de Agravo de Instrumento

Processo de teste: 0813316-60.2025.8.12.0002
Este processo possui Agravo de Instrumento confirmado no processo de origem.

Autor: LAB/PGE-MS
"""

import asyncio
import logging
import sys
import os

# Adiciona o diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sistemas.pedido_calculo.document_downloader import DocumentDownloader
from sistemas.pedido_calculo.xml_parser import XMLParser
from sistemas.relatorio_cumprimento.agravo_detector import (
    extract_agravo_candidates_from_xml,
    detect_and_validate_agravos,
    fetch_all_agravo_documents,
    format_numero_cnj
)
from sistemas.relatorio_cumprimento.models import CategoriaDocumento

# Configura logging detalhado
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# Processo de teste
PROCESSO_CUMPRIMENTO = "0813316-60.2025.8.12.0002"


async def test_agravo_detection():
    """
    Teste completo de detecção de Agravo de Instrumento.

    Fluxo:
    1. Consulta processo de cumprimento
    2. Verifica se é cumprimento autônomo
    3. Identifica processo de origem
    4. Detecta agravos no processo de origem
    5. Valida agravos por comparação de partes
    6. Baixa documentos dos agravos validados
    """

    print("\n" + "="*80)
    print("TESTE DIRIGIDO - DETECÇÃO DE AGRAVO DE INSTRUMENTO")
    print("="*80)
    print(f"Processo de teste: {PROCESSO_CUMPRIMENTO}")
    print("="*80 + "\n")

    resultados = {
        "processo_cumprimento": PROCESSO_CUMPRIMENTO,
        "cumprimento_autonomo": False,
        "processo_origem": None,
        "agravo_detectado": False,
        "numeros_agravo_extraidos": [],
        "agravo_confirmado_por_partes": False,
        "quantidade_decisoes_agravo": 0,
        "quantidade_acordaos_agravo": 0,
        "sucesso": False,
        "motivo_falha": None
    }

    try:
        # ============================================================
        # ETAPA 1: Consultar processo de cumprimento
        # ============================================================
        print("\n[ETAPA 1] Consultando processo de cumprimento...")

        async with DocumentDownloader() as downloader:
            xml_cumprimento = await downloader.consultar_processo(PROCESSO_CUMPRIMENTO)

        parser_cumprimento = XMLParser(xml_cumprimento)
        dados_basicos = parser_cumprimento.extrair_dados_basicos()
        documentos_info = parser_cumprimento.identificar_documentos_para_download()

        print(f"  [OK] Processo consultado: {dados_basicos.numero_processo}")
        print(f"  [OK] Autor: {dados_basicos.autor}")
        print(f"  [OK] Comarca: {dados_basicos.comarca}")

        # ============================================================
        # ETAPA 2: Verificar se é cumprimento autônomo
        # ============================================================
        print("\n[ETAPA 2] Verificando tipo de cumprimento...")

        resultados["cumprimento_autonomo"] = documentos_info.is_cumprimento_autonomo

        if not documentos_info.is_cumprimento_autonomo:
            print("  [FAIL] NÃO é cumprimento autônomo - teste não aplicável")
            resultados["motivo_falha"] = "Processo não é cumprimento autônomo"
            return resultados

        print("  [OK] É cumprimento autônomo")

        # ============================================================
        # ETAPA 3: Identificar processo de origem
        # ============================================================
        print("\n[ETAPA 3] Identificando processo de origem...")

        numero_origem = documentos_info.numero_processo_origem
        resultados["processo_origem"] = numero_origem

        if not numero_origem:
            print("  [FAIL] Processo de origem NÃO identificado")
            resultados["motivo_falha"] = "Processo de origem não identificado"
            return resultados

        print(f"  [OK] Processo de origem: {format_numero_cnj(numero_origem)}")

        # ============================================================
        # ETAPA 4: Baixar XML do processo de origem
        # ============================================================
        print("\n[ETAPA 4] Baixando XML do processo de origem...")

        async with DocumentDownloader() as downloader:
            xml_origem = await downloader.consultar_processo(numero_origem)

        parser_origem = XMLParser(xml_origem)
        dados_origem = parser_origem.extrair_dados_basicos()

        print(f"  [OK] Processo de origem consultado: {dados_origem.numero_processo}")
        print(f"  [OK] Autor: {dados_origem.autor}")

        # ============================================================
        # ETAPA 5: Detectar candidatos a Agravo de Instrumento
        # ============================================================
        print("\n[ETAPA 5] Detectando candidatos a Agravo de Instrumento...")

        candidatos = extract_agravo_candidates_from_xml(xml_origem, "TEST001")

        if not candidatos:
            print("  [FAIL] Nenhum candidato a agravo detectado")
            resultados["motivo_falha"] = "Nenhum agravo detectado no XML do processo de origem"
            return resultados

        resultados["agravo_detectado"] = True
        resultados["numeros_agravo_extraidos"] = [c.numero_cnj for c in candidatos]

        print(f"  [OK] {len(candidatos)} candidato(s) detectado(s):")
        for c in candidatos:
            print(f"    - {format_numero_cnj(c.numero_cnj)}")
            print(f"      Fonte: {c.fonte}")
            print(f"      Texto: {c.texto_original[:100]}...")

        # ============================================================
        # ETAPA 6: Validar agravos por comparação de partes
        # ============================================================
        print("\n[ETAPA 6] Validando agravos por comparação de partes...")

        resultado_deteccao = await detect_and_validate_agravos(xml_origem, "TEST001")

        print(f"  - Candidatos detectados: {len(resultado_deteccao.candidatos_detectados)}")
        print(f"  - Agravos validados: {len(resultado_deteccao.agravos_validados)}")
        print(f"  - Agravos rejeitados: {len(resultado_deteccao.agravos_rejeitados)}")

        if resultado_deteccao.agravos_validados:
            resultados["agravo_confirmado_por_partes"] = True
            print("  [OK] Agravo(s) confirmado(s) por comparação de partes:")
            for agravo in resultado_deteccao.agravos_validados:
                print(f"    - {agravo.numero_formatado}")
                print(f"      Score: {agravo.score_similaridade:.0%}")
                print(f"      Decisões: {len(agravo.ids_decisoes)}")
                print(f"      Acórdãos: {len(agravo.ids_acordaos)}")
        else:
            print("  [FAIL] Nenhum agravo confirmado por partes")

        if resultado_deteccao.agravos_rejeitados:
            print("  [WARN] Agravo(s) rejeitado(s):")
            for rej in resultado_deteccao.agravos_rejeitados:
                print(f"    - {rej.get('candidato', {}).get('numero_cnj', 'N/A')}")
                print(f"      Motivo: {rej.get('motivo', 'N/A')}")

        if not resultado_deteccao.agravos_validados:
            resultados["motivo_falha"] = "Nenhum agravo passou na validação por partes"
            return resultados

        # ============================================================
        # ETAPA 7: Baixar documentos dos agravos validados
        # ============================================================
        print("\n[ETAPA 7] Baixando documentos dos agravos validados...")

        documentos_agravo = await fetch_all_agravo_documents(
            resultado_deteccao.agravos_validados,
            "TEST001"
        )

        qtd_decisoes = sum(1 for d in documentos_agravo if d.categoria == CategoriaDocumento.DECISAO_AGRAVO)
        qtd_acordaos = sum(1 for d in documentos_agravo if d.categoria == CategoriaDocumento.ACORDAO_AGRAVO)

        resultados["quantidade_decisoes_agravo"] = qtd_decisoes
        resultados["quantidade_acordaos_agravo"] = qtd_acordaos

        print(f"  [OK] {len(documentos_agravo)} documento(s) baixado(s):")
        print(f"    - Decisões: {qtd_decisoes}")
        print(f"    - Acórdãos: {qtd_acordaos}")

        if documentos_agravo:
            print("\n  Documentos baixados:")
            for doc in documentos_agravo:
                print(f"    - {doc.nome_padronizado}")
                print(f"      Categoria: {doc.categoria.value}")
                print(f"      Origem: {doc.processo_origem}")
                print(f"      Texto: {len(doc.conteudo_texto or '')} caracteres")

        # ============================================================
        # RESULTADO FINAL
        # ============================================================
        resultados["sucesso"] = True

    except Exception as e:
        import traceback
        traceback.print_exc()
        resultados["motivo_falha"] = f"Erro: {str(e)}"

    return resultados


def print_resultado_final(resultados):
    """Imprime resumo do resultado do teste."""

    print("\n" + "="*80)
    print("RESULTADO DO TESTE")
    print("="*80)

    print(f"""
LOGS OBRIGATÓRIOS:
  processo_cumprimento:        {resultados['processo_cumprimento']}
  cumprimento_autonomo:        {resultados['cumprimento_autonomo']}
  processo_origem:             {resultados['processo_origem'] or 'N/A'}
  agravo_detectado:            {resultados['agravo_detectado']}
  numeros_agravo_extraidos:    {resultados['numeros_agravo_extraidos'] or 'N/A'}
  agravo_confirmado_por_partes:{resultados['agravo_confirmado_por_partes']}
  quantidade_decisoes_agravo:  {resultados['quantidade_decisoes_agravo']}
  quantidade_acordaos_agravo:  {resultados['quantidade_acordaos_agravo']}
""")

    print("="*80)
    if resultados["sucesso"]:
        print("[OK] TESTE PASSOU - Agravo detectado, validado e documentos incorporados!")
    else:
        print(f"[FAIL] TESTE FALHOU - Motivo: {resultados['motivo_falha']}")
    print("="*80)


if __name__ == "__main__":
    resultados = asyncio.run(test_agravo_detection())
    print_resultado_final(resultados)
