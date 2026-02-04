"""
Script de teste para investigar documentos NAT.

Verifica:
1. Se os documentos são encontrados
2. Se há conteúdo base64
3. Qual o formato do documento (PDF vs RTF)
"""

import asyncio
import base64
import sys
import os

# Adiciona o diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from services.tjms_client import soap_consultar_processo, soap_baixar_documentos, get_config
from sistemas.gerador_pecas.agente_tjms import extrair_documentos_xml


def detectar_formato(conteudo_base64: str) -> str:
    """Detecta o formato do arquivo a partir do conteúdo base64."""
    try:
        dados = base64.b64decode(conteudo_base64[:1000])  # Primeiros bytes

        # PDF começa com %PDF
        if dados[:4] == b'%PDF':
            return 'PDF'

        # RTF começa com {\rtf
        if dados[:5] == b'{\\rtf':
            return 'RTF'

        # Tentar detectar outros formatos
        if dados[:2] == b'PK':
            return 'ZIP/DOCX'

        if dados[:4] == b'\xd0\xcf\x11\xe0':
            return 'DOC (OLE)'

        # Retorna os primeiros bytes para diagnóstico
        return f'DESCONHECIDO (primeiros bytes: {dados[:20]})'
    except Exception as e:
        return f'ERRO ao detectar: {e}'


async def investigar_processo(numero_processo: str, codigo_nat: int = 8451):
    """Investiga documentos NAT de um processo específico."""
    print(f"\n{'='*60}")
    print(f"PROCESSO: {numero_processo}")
    print(f"{'='*60}")

    config = get_config()
    print(f"Usando proxy: {config.soap_url}")

    try:
        # 1. Consulta processo (sem conteúdo)
        print("\n[1] Consultando processo...")
        xml_consulta = await soap_consultar_processo(numero_processo, movimentos=False, incluir_documentos=True)

        # Salva XML de consulta para análise
        consulta_file = f"debug_consulta_{numero_processo.replace('-', '_').replace('.', '_')}.xml"
        with open(consulta_file, 'w', encoding='utf-8') as f:
            f.write(xml_consulta)
        print(f"    XML de consulta salvo em: {consulta_file}")

        # 2. Extrai lista de documentos
        todos_documentos = extrair_documentos_xml(xml_consulta)
        print(f"    Total de documentos no processo: {len(todos_documentos)}")

        # 3. Filtra documentos NAT (códigos 8451, 9636, 59, 8490)
        codigos_nat = {8451, 9636, 59, 8490}

        # Mostra todos os códigos encontrados
        codigos_encontrados = {}
        for doc in todos_documentos:
            tipo = doc.tipo_documento
            if tipo not in codigos_encontrados:
                codigos_encontrados[tipo] = doc.descricao

        print(f"\n[2] Códigos de documentos encontrados:")
        for codigo, desc in sorted(codigos_encontrados.items(), key=lambda x: int(x[0]) if x[0] and x[0].isdigit() else 0):
            eh_nat = " <-- NAT!" if codigo and int(codigo) in codigos_nat else ""
            print(f"    {codigo}: {desc}{eh_nat}")

        # Filtra NAT
        docs_nat = []
        for doc in todos_documentos:
            try:
                tipo_int = int(doc.tipo_documento) if doc.tipo_documento else 0
                if tipo_int in codigos_nat:
                    docs_nat.append(doc)
            except ValueError:
                pass

        print(f"\n[3] Documentos NAT encontrados: {len(docs_nat)}")

        if not docs_nat:
            print("    NENHUM DOCUMENTO NAT ENCONTRADO NO PROCESSO!")
            return

        for doc in docs_nat:
            print(f"    - ID: {doc.id}, Tipo: {doc.tipo_documento}, Desc: {doc.descricao}, Data: {doc.data_formatada}")

        # 4. Baixa os documentos NAT
        print("\n[4] Baixando documentos NAT...")
        ids_nat = [doc.id for doc in docs_nat]

        try:
            xml_download = await soap_baixar_documentos(numero_processo, ids_nat)

            # Salva XML para debug
            debug_file = f"debug_download_{numero_processo.replace('-', '_').replace('.', '_')}.xml"
            with open(debug_file, 'w', encoding='utf-8') as f:
                f.write(xml_download)
            print(f"    XML de resposta salvo em: {debug_file}")

            # Verifica se há erro no XML
            if '<erro>' in xml_download.lower() or '<fault>' in xml_download.lower():
                print(f"    POSSÍVEL ERRO NO XML!")
                # Extrai mensagem de erro
                import re
                erro_match = re.search(r'<(erro|faultstring)[^>]*>([^<]+)<', xml_download, re.I)
                if erro_match:
                    print(f"    Mensagem: {erro_match.group(2)}")

            # 5. Extrai documentos do XML de download
            docs_baixados = extrair_documentos_xml(xml_download)
            print(f"    Documentos retornados no download: {len(docs_baixados)}")

            for doc in docs_baixados:
                print(f"\n    Documento ID: {doc.id}")
                print(f"    Tipo: {doc.tipo_documento}")
                print(f"    Descrição: {doc.descricao}")

                if doc.conteudo_base64:
                    tamanho = len(doc.conteudo_base64)
                    formato = detectar_formato(doc.conteudo_base64)
                    print(f"    Conteúdo: SIM ({tamanho} bytes em base64)")
                    print(f"    Formato detectado: {formato}")
                else:
                    print(f"    Conteúdo: NÃO (base64 vazio!)")

        except Exception as e:
            print(f"    ERRO ao baixar: {e}")

    except Exception as e:
        print(f"ERRO: {e}")
        import traceback
        traceback.print_exc()


async def testar_download_documento_especifico(numero_processo: str, id_documento: str):
    """Testa download de um documento específico com debug detalhado."""
    print(f"\n{'='*60}")
    print(f"TESTE DE DOWNLOAD ESPECÍFICO")
    print(f"Processo: {numero_processo}")
    print(f"Documento: {id_documento}")
    print(f"{'='*60}")

    config = get_config()
    print(f"Endpoint SOAP: {config.soap_url}")

    try:
        # Tenta baixar
        xml_download = await soap_baixar_documentos(numero_processo, [id_documento])

        # Salva para análise
        debug_file = f"debug_download_single_{id_documento.replace(' ', '_').replace('-', '_')}.xml"
        with open(debug_file, 'w', encoding='utf-8') as f:
            f.write(xml_download)
        print(f"XML salvo em: {debug_file}")

        # Verifica se há documentos com conteúdo
        docs = extrair_documentos_xml(xml_download)
        print(f"Documentos extraídos: {len(docs)}")

        for doc in docs:
            print(f"  - ID: {doc.id}, Tipo: {doc.tipo_documento}, Conteúdo: {'SIM' if doc.conteudo_base64 else 'NÃO'}")
            if doc.conteudo_base64:
                formato = detectar_formato(doc.conteudo_base64)
                print(f"    Formato: {formato}, Tamanho: {len(doc.conteudo_base64)} bytes base64")

    except Exception as e:
        print(f"ERRO: {e}")
        import traceback
        traceback.print_exc()


async def main():
    """Testa os processos reportados."""
    processo = "0803386-54.2023.8.12.0045"

    print("="*60)
    print("INVESTIGAÇÃO DE DOCUMENTOS NAT")
    print("="*60)
    print("\nCódigos NAT:")
    print("  8451 - Parecer NAT")
    print("  9636 - Parecer NAT (alternativo)")
    print("  59   - Nota Técnica NATJus")
    print("  8490 - Nota Técnica NATJus (alternativo)")

    # 1. Investiga documentos do processo
    await investigar_processo(processo)

    # 2. Testa download de documento NAT específico
    # ID encontrado no XML: 177499028 - 0
    await testar_download_documento_especifico(processo, "177499028 - 0")

    # 3. Testa download de documento normal para comparação
    # Petição inicial (primeiro doc do processo)
    await testar_download_documento_especifico(processo, "177499106 - 1")

    # 4. Testa download de documento "- 0" que não seja NAT (Certidão)
    await testar_download_documento_especifico(processo, "177499027 - 0")
    print("\n")


if __name__ == "__main__":
    asyncio.run(main())
