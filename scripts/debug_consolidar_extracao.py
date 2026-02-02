# scripts/debug_consolidar_extracao.py
"""
Script para debugar por que consolidar_dados_extracao() retorna vazio.

Conecta no banco de produção e examina um processo específico.
"""

import os
import sys

# Adiciona o diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Conexão com banco de produção (Railway)
DATABASE_URL = os.environ.get("DATABASE_URL_PROD", "postgresql://postgres:PASSWORD@yamanote.proxy.rlwy.net:48085/railway")

def debug_processo(numero_processo: str):
    """Examina dados de um processo no banco."""

    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Busca a geração de peça mais recente para este processo
        result = session.execute(text("""
            SELECT
                id,
                numero_cnj,
                tipo_peca,
                dados_processo,
                resumo_consolidado,
                created_at
            FROM geracoes_pecas
            WHERE numero_cnj LIKE :cnj
            ORDER BY created_at DESC
            LIMIT 1
        """), {"cnj": f"%{numero_processo[-14:]}%"})

        row = result.fetchone()

        if not row:
            print(f"Nenhuma geração encontrada para o processo {numero_processo}")
            return

        print(f"=" * 80)
        print(f"PROCESSO: {row.numero_cnj}")
        print(f"TIPO PEÇA: {row.tipo_peca}")
        print(f"DATA: {row.created_at}")
        print(f"=" * 80)

        # Analisa dados_processo
        dados = row.dados_processo
        print(f"\n1. DADOS_PROCESSO (armazenado no banco):")
        print(f"   Tipo: {type(dados)}")
        if dados:
            if isinstance(dados, dict):
                print(f"   Quantidade de chaves: {len(dados)}")
                for k, v in list(dados.items())[:10]:
                    print(f"      {k}: {v}")
                if len(dados) > 10:
                    print(f"      ... e mais {len(dados) - 10} chaves")
            else:
                print(f"   Valor: {str(dados)[:500]}")
        else:
            print(f"   VAZIO!")

        # Analisa resumo_consolidado
        resumo = row.resumo_consolidado
        print(f"\n2. RESUMO_CONSOLIDADO:")
        if resumo:
            print(f"   Tamanho: {len(resumo)} caracteres")

            # Conta quantos JSONs existem no resumo
            import json
            import re

            # Encontra todos os blocos JSON
            json_blocks = re.findall(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', resumo, re.DOTALL)
            print(f"   Blocos JSON encontrados: {len(json_blocks)}")

            # Tenta parsear cada um
            jsons_validos = 0
            variaveis_totais = set()

            for block in json_blocks:
                try:
                    data = json.loads(block)
                    if isinstance(data, dict):
                        jsons_validos += 1
                        for k in data.keys():
                            if not k.startswith('_'):
                                variaveis_totais.add(k)
                except:
                    pass

            print(f"   JSONs válidos parseados: {jsons_validos}")
            print(f"   Variáveis únicas encontradas: {len(variaveis_totais)}")

            if variaveis_totais:
                print(f"   Algumas variáveis: {list(variaveis_totais)[:10]}")
        else:
            print(f"   VAZIO!")

        # Conclusão
        print(f"\n" + "=" * 80)
        print("DIAGNÓSTICO:")

        if not dados and resumo:
            print("❌ PROBLEMA CONFIRMADO: dados_processo vazio mas resumo_consolidado tem dados")
            print("   CAUSA PROVÁVEL: consolidar_dados_extracao() não conseguiu extrair dos documentos")
            print("   SOLUÇÃO: O fallback implementado deve resolver isso")
        elif dados and resumo:
            print("✅ OK: Ambos têm dados")
        elif not dados and not resumo:
            print("⚠️ Processo sem dados de extração")

        print("=" * 80)

    except Exception as e:
        print(f"Erro: {e}")
        import traceback
        traceback.print_exc()
    finally:
        session.close()


def debug_documentos_em_memoria():
    """
    Simula o fluxo de consolidar_dados_extracao para entender onde falha.

    Esta função precisa ser chamada durante o processamento de um processo
    para ter acesso ao ResultadoAgente1 real.
    """
    print("""
    Para debugar documentos em memória, adicione este código no router.py
    logo antes da chamada a consolidar_dados_extracao():

    # DEBUG: Verificar estado dos documentos
    print(f"[DEBUG] resultado_agente1.dados_brutos: {resultado_agente1.dados_brutos}")
    if resultado_agente1.dados_brutos:
        docs = resultado_agente1.dados_brutos.documentos
        print(f"[DEBUG] Total documentos: {len(docs)}")
        docs_com_resumo = resultado_agente1.dados_brutos.documentos_com_resumo()
        print(f"[DEBUG] Documentos com resumo: {len(docs_com_resumo)}")
        for doc in docs_com_resumo[:3]:
            print(f"[DEBUG] Doc {doc.id}:")
            print(f"[DEBUG]   categoria_nome: {doc.categoria_nome}")
            print(f"[DEBUG]   resumo (primeiros 200): {doc.resumo[:200] if doc.resumo else 'NONE'}")
            print(f"[DEBUG]   resumo inicia com '{{': {doc.resumo.strip().startswith('{') if doc.resumo else False}")
    """)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python debug_consolidar_extracao.py <numero_processo>")
        print("     ou")
        print("     python debug_consolidar_extracao.py --help")
        sys.exit(1)

    if sys.argv[1] == "--help":
        debug_documentos_em_memoria()
    else:
        debug_processo(sys.argv[1])
