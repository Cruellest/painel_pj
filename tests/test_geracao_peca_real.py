"""
Teste de geração de peça real para verificar que o sistema funciona
antes de subir para produção.
"""

import asyncio
import sys
import os

# Adiciona o diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Importa modelos na ordem correta para evitar erros de dependência circular
from auth.models import User  # Importa User primeiro
from sqlalchemy.orm import Session
from database.connection import SessionLocal
from sistemas.gerador_pecas.services import GeradorPecasService
from admin.models_prompt_groups import PromptGroup


async def testar_geracao_peca(numero_cnj: str):
    """Testa geração de peça para um processo real."""

    print("="*70)
    print(f"TESTE DE GERAÇÃO DE PEÇA - Processo: {numero_cnj}")
    print("="*70)

    db = SessionLocal()

    try:
        # Busca o primeiro grupo ativo
        grupo = db.query(PromptGroup).filter(PromptGroup.active == True).first()

        if not grupo:
            print("[ERRO] Nenhum grupo de prompts ativo encontrado!")
            return False

        print(f"\n[INFO] Usando grupo: {grupo.name} (ID: {grupo.id})")

        # Busca modelo configurado no banco
        from admin.models import ConfiguracaoIA
        config_modelo = db.query(ConfiguracaoIA).filter(
            ConfiguracaoIA.sistema == "gerador_pecas",
            ConfiguracaoIA.chave == "modelo_geracao"
        ).first()
        modelo = config_modelo.valor if config_modelo else "gemini-3-pro-preview"
        print(f"[INFO] Modelo de geração: {modelo}")

        # Inicializa o serviço
        service = GeradorPecasService(
            modelo=modelo,
            db=db,
            group_id=grupo.id,
            subcategoria_ids=[]
        )

        print(f"\n[INFO] Iniciando processamento do processo...")
        print("-"*70)

        # Processa o processo
        resultado = await service.processar_processo(
            numero_cnj=numero_cnj,
            numero_cnj_formatado=numero_cnj,
            tipo_peca=None,  # Deixa a IA decidir
            resposta_usuario=None,
            usuario_id=1  # Admin
        )

        print("-"*70)
        print("\n[RESULTADO]")
        print(f"  Status: {resultado.get('status', 'N/A')}")

        if resultado.get('status') == 'sucesso':
            print(f"  Tipo de peça: {resultado.get('tipo_peca', 'N/A')}")
            print(f"  URL download: {resultado.get('url_download', 'N/A')}")

            conteudo = resultado.get('conteudo_json', {})
            if conteudo:
                titulo = conteudo.get('titulo', 'N/A')
                resumo = conteudo.get('resumo', '')[:200] + '...' if conteudo.get('resumo') else 'N/A'
                print(f"  Título: {titulo}")
                print(f"  Resumo: {resumo}")

            print("\n[SUCESSO] Peça gerada com sucesso!")
            return True

        elif resultado.get('status') == 'pergunta':
            print(f"  Pergunta: {resultado.get('pergunta', 'N/A')}")
            print(f"  Opções: {resultado.get('opcoes', [])}")
            print("\n[INFO] Sistema precisa de mais informações (comportamento esperado)")
            return True

        else:
            print(f"  Mensagem: {resultado.get('mensagem', 'N/A')}")
            print(f"  Detalhes: {resultado}")
            return False

    except Exception as e:
        import traceback
        print(f"\n[ERRO] {e}")
        traceback.print_exc()
        return False

    finally:
        db.close()


async def verificar_ordem_prompts(group_id: int = None):
    """Verifica a ordem dos prompts que serão enviados à IA."""

    print("\n" + "="*70)
    print("VERIFICAÇÃO DA ORDEM DOS PROMPTS")
    print("="*70)

    db = SessionLocal()

    try:
        if group_id is None:
            grupo = db.query(PromptGroup).filter(PromptGroup.active == True).first()
            if grupo:
                group_id = grupo.id
                print(f"\n[INFO] Usando grupo: {grupo.name} (ID: {group_id})")

        if not group_id:
            print("[ERRO] Nenhum grupo encontrado")
            return

        service = GeradorPecasService(
            db=db,
            group_id=group_id
        )

        print("\n[INFO] Carregando módulos de conteúdo na ordem configurada...")
        modulos = service._carregar_modulos_conteudo()

        if not modulos:
            print("[INFO] Nenhum módulo de conteúdo encontrado para este grupo")
        else:
            print(f"\n[INFO] {len(modulos)} módulos encontrados:\n")
            for idx, m in enumerate(modulos):
                print(f"  {idx+1}. [{m.categoria}] ordem={m.ordem or 0} - {m.titulo}")

    finally:
        db.close()


if __name__ == "__main__":
    # Número do processo para teste
    NUMERO_PROCESSO = "0802139-60.2025.8.12.0015"

    print("\n" + "#"*70)
    print("#  TESTE PRÉ-PRODUÇÃO - Portal PGE-MS")
    print("#"*70 + "\n")

    # Primeiro verifica a ordem dos prompts
    asyncio.run(verificar_ordem_prompts())

    # Depois testa a geração
    print("\n")
    sucesso = asyncio.run(testar_geracao_peca(NUMERO_PROCESSO))

    print("\n" + "="*70)
    if sucesso:
        print("[OK] TESTE CONCLUIDO - Sistema pronto para producao")
    else:
        print("[FALHOU] TESTE FALHOU - Verifique os erros acima")
    print("="*70 + "\n")
