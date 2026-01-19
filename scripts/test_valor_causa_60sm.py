#!/usr/bin/env python3
"""
Script de teste para validar a extração de valor_causa_numerico e valor_causa_inferior_60sm.

Testa o pipeline de extração nos XMLs fornecidos e imprime um relatório detalhado.

Uso:
    python scripts/test_valor_causa_60sm.py
"""

import json
import logging
import re
import sys
from pathlib import Path

# Adiciona o diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sistemas.gerador_pecas.agente_tjms import extrair_dados_processo_xml
from sistemas.gerador_pecas.services_process_variables import (
    ProcessVariableResolver,
    LIMITE_60_SALARIOS_MINIMOS,
)

# Configura logging para ver os logs de debug
logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)s - %(name)s - %(message)s'
)

# XMLs de teste
XML_FILES = [
    r"C:\Users\kaoye\Downloads\00073941120248120001_processo_completo.xml",
    r"C:\Users\kaoye\Downloads\00000486820238120025_processo_completo.xml",
    r"C:\Users\kaoye\Downloads\00000668920238120025_processo_completo.xml",
]


def extrair_valor_causa_raw(xml_content: str) -> str:
    """Extrai o valor bruto do nó ns2:valorCausa do XML."""
    # Busca o nó <ns2:valorCausa>...</ns2:valorCausa>
    match = re.search(r'<ns2:valorCausa>([^<]*)</ns2:valorCausa>', xml_content)
    if match:
        return match.group(1)
    return "NÃO ENCONTRADO"


def processar_xml(xml_path: str) -> dict:
    """Processa um XML e retorna os dados relevantes."""
    print(f"\n{'='*80}")
    print(f"PROCESSANDO: {xml_path}")
    print('='*80)

    # Lê o XML
    with open(xml_path, 'r', encoding='utf-8') as f:
        xml_content = f.read()

    # Extrai valor raw direto do XML
    valor_causa_raw = extrair_valor_causa_raw(xml_content)
    print(f"\n[XML RAW] ns2:valorCausa = '{valor_causa_raw}'")

    # Extrai DadosProcesso do XML
    dados_processo = extrair_dados_processo_xml(xml_content)

    if not dados_processo:
        print("ERRO: Não foi possível extrair dados do XML")
        return {"erro": "Falha na extração"}

    # Resolve variáveis
    resolver = ProcessVariableResolver(dados_processo)
    variaveis = resolver.resolver_todas()

    # Extrai as variáveis de interesse
    valor_causa_str = dados_processo.valor_causa
    valor_causa_numerico = variaveis.get('valor_causa_numerico')
    valor_causa_inferior_60sm = variaveis.get('valor_causa_inferior_60sm')

    # Imprime relatório
    print(f"\n--- RELATÓRIO DE VARIÁVEIS ---")
    print(f"  valor_causa (string do DadosProcesso): '{valor_causa_str}'")
    print(f"  valor_causa_numerico: {valor_causa_numerico}")
    print(f"  valor_causa_inferior_60sm: {valor_causa_inferior_60sm}")
    print(f"  (limite 60 SM = R$ {LIMITE_60_SALARIOS_MINIMOS:,.2f})")

    # Validação
    if valor_causa_numerico is not None:
        esperado = valor_causa_numerico < LIMITE_60_SALARIOS_MINIMOS
        status = "OK" if valor_causa_inferior_60sm == esperado else "ERRO"
        print(f"\n  [VALIDAÇÃO] {status}: {valor_causa_numerico} < {LIMITE_60_SALARIOS_MINIMOS} = {esperado}")
    else:
        print(f"\n  [VALIDAÇÃO] valor_causa_numerico é None, esperado valor_causa_inferior_60sm = None")

    # Dump do JSON de variáveis (principais)
    print(f"\n--- JSON DE VARIÁVEIS EXTRAÍDAS ---")
    variaveis_principais = {
        'numero_processo': dados_processo.numero_processo,
        'valor_causa': valor_causa_str,
        'valor_causa_numerico': valor_causa_numerico,
        'valor_causa_inferior_60sm': valor_causa_inferior_60sm,
        'processo_ajuizado_apos_2024_04_19': variaveis.get('processo_ajuizado_apos_2024_04_19'),
        'estado_polo_passivo': variaveis.get('estado_polo_passivo'),
        'municipio_polo_passivo': variaveis.get('municipio_polo_passivo'),
        'autor_com_assistencia_judiciaria': variaveis.get('autor_com_assistencia_judiciaria'),
    }
    print(json.dumps(variaveis_principais, indent=2, ensure_ascii=False, default=str))

    return variaveis_principais


def main():
    print("\n" + "="*80)
    print("TESTE DE EXTRAÇÃO DE VALOR DA CAUSA E VARIÁVEL DERIVADA")
    print(f"Limite 60 SM: R$ {LIMITE_60_SALARIOS_MINIMOS:,.2f}")
    print("="*80)

    resultados = []

    for xml_path in XML_FILES:
        path = Path(xml_path)
        if not path.exists():
            print(f"\nARQUIVO NÃO ENCONTRADO: {xml_path}")
            continue

        try:
            resultado = processar_xml(xml_path)
            resultados.append(resultado)
        except Exception as e:
            print(f"\nERRO ao processar {xml_path}: {e}")
            import traceback
            traceback.print_exc()

    # Resumo final
    print("\n" + "="*80)
    print("RESUMO FINAL")
    print("="*80)

    for i, r in enumerate(resultados, 1):
        if 'erro' in r:
            print(f"{i}. ERRO: {r['erro']}")
        else:
            valor_numerico = r.get('valor_causa_numerico', 'N/A')
            inferior_60sm = r.get('valor_causa_inferior_60sm', 'N/A')
            print(f"{i}. Processo: {r.get('numero_processo', 'N/A')}")
            print(f"   valor_causa_numerico: {valor_numerico}")
            print(f"   valor_causa_inferior_60sm: {inferior_60sm}")
            print()

    print("\nTeste concluído!")


if __name__ == "__main__":
    main()
