#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script para testar a extracao de variaveis derivadas do processo a partir de XMLs.

Uso:
    python scripts/test_process_variables_xml.py <caminho_xml1> [<caminho_xml2> ...]

Exemplo:
    python scripts/test_process_variables_xml.py caminho/para/arquivo.xml
"""

import sys
import os

# Adiciona o diretorio raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sistemas.gerador_pecas.agente_tjms import extrair_dados_processo_xml, DadosProcesso
from sistemas.gerador_pecas.services_process_variables import ProcessVariableResolver


def formatar_parte(parte) -> str:
    """Formata uma parte do processo para exibicao."""
    info = f"    - {parte.nome}"
    if parte.tipo_pessoa:
        info += f" ({parte.tipo_pessoa})"
    if parte.assistencia_judiciaria:
        info += " [ASSISTENCIA JUDICIARIA]"
    if parte.tipo_representante:
        info += f"\n      Representante: {parte.representante} ({parte.tipo_representante})"
    return info


def testar_xml(caminho_xml: str):
    """Testa a extracao de um unico XML."""
    print("\n" + "=" * 80)
    print(f"ARQUIVO: {os.path.basename(caminho_xml)}")
    print("=" * 80)

    # Le o XML
    try:
        with open(caminho_xml, 'r', encoding='utf-8') as f:
            xml_text = f.read()
    except Exception as e:
        print(f"ERRO ao ler arquivo: {e}")
        return

    # Extrai dados do processo
    dados = extrair_dados_processo_xml(xml_text)

    if dados is None:
        print("ERRO: Nao foi possivel extrair dados do processo")
        return

    # Exibe dados do processo
    print("\n[DADOS DO PROCESSO]")
    print(f"  Numero: {dados.numero_processo}")
    print(f"  Classe: {dados.classe_processual}")
    print(f"  Data Ajuizamento: {dados.data_ajuizamento.strftime('%d/%m/%Y %H:%M') if dados.data_ajuizamento else 'N/A'}")
    print(f"  Valor da Causa: {dados.valor_causa or 'N/A'}")
    print(f"  Orgao Julgador: {dados.orgao_julgador or 'N/A'}")

    print("\n[POLO ATIVO - Autor]")
    if dados.polo_ativo:
        for parte in dados.polo_ativo:
            print(formatar_parte(parte))
    else:
        print("    (vazio)")

    print("\n[POLO PASSIVO - Reu]")
    if dados.polo_passivo:
        for parte in dados.polo_passivo:
            print(formatar_parte(parte))
    else:
        print("    (vazio)")

    # Resolve variaveis derivadas
    resolver = ProcessVariableResolver(dados)
    variaveis = resolver.resolver_todas()

    print("\n[VARIAVEIS DERIVADAS]")
    print("-" * 50)

    for slug, valor in variaveis.items():
        # Formatacao visual do valor
        if valor is True:
            valor_str = "[OK] True"
        elif valor is False:
            valor_str = "[X] False"
        elif valor is None:
            valor_str = "[?] None (indeterminado)"
        elif isinstance(valor, float):
            valor_str = f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        else:
            valor_str = str(valor)

        # Obtem descricao da variavel
        definition = ProcessVariableResolver.get_definition(slug)
        desc = definition.descricao if definition else ""

        print(f"  {slug}:")
        print(f"    Valor: {valor_str}")
        if desc:
            print(f"    Descricao: {desc}")
        print()

    # Resumo para uso em regras deterministicas
    print("[RESUMO PARA REGRAS DETERMINISTICAS]")
    print("-" * 50)
    print("Variaveis que podem ser usadas em regras:")
    for slug, valor in variaveis.items():
        if valor is not None:
            print(f'  - "{slug}": {valor}')

    return dados, variaveis


def main():
    # Caminhos padrao para teste
    caminhos_padrao = [
        "C:/Users/kaoye/Downloads/00000486820238120025_processo_completo.xml",
        "C:/Users/kaoye/Downloads/00000668920238120025_processo_completo.xml",
        "C:/Users/kaoye/Downloads/08083233820258120110_processo_completo.xml"
    ]

    # Usa argumentos da linha de comando ou caminhos padrao
    caminhos = sys.argv[1:] if len(sys.argv) > 1 else caminhos_padrao

    print("=" * 80)
    print("TESTE DE EXTRACAO DE VARIAVEIS DO PROCESSO")
    print("=" * 80)

    # Lista as variaveis disponiveis
    print("\n[VARIAVEIS DISPONIVEIS NO SISTEMA]")
    for v in ProcessVariableResolver.get_all_definitions():
        print(f"  - {v.slug} ({v.tipo}): {v.label}")

    # Testa cada XML
    resultados = []
    for caminho in caminhos:
        if os.path.exists(caminho):
            resultado = testar_xml(caminho)
            if resultado:
                resultados.append((caminho, resultado))
        else:
            print(f"\n[!] Arquivo nao encontrado: {caminho}")

    # Tabela comparativa
    if len(resultados) > 1:
        print("\n" + "=" * 80)
        print("[COMPARATIVO ENTRE PROCESSOS]")
        print("=" * 80)

        # Cabecalho
        headers = ["Variavel"] + [os.path.basename(r[0])[:30] for r in resultados]

        # Dados
        slugs = list(resultados[0][1][1].keys())
        for slug in slugs:
            valores = []
            for _, (_, variaveis) in resultados:
                v = variaveis.get(slug)
                if v is True:
                    valores.append("OK")
                elif v is False:
                    valores.append("X")
                elif v is None:
                    valores.append("?")
                elif isinstance(v, float):
                    valores.append(f"R${v:,.0f}".replace(",", "."))
                else:
                    valores.append(str(v)[:15])

            print(f"  {slug:40} | {' | '.join(valores)}")


if __name__ == "__main__":
    main()
