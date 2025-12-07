# sistemas/gerador_pecas/test_detector_exemplo.py
"""
Exemplo de teste do detector de módulos IA.
Este arquivo demonstra como testar a detecção inteligente.
"""

import asyncio
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from sistemas.gerador_pecas.detector_modulos import DetectorModulosIA
from admin.models_prompts import PromptModulo


# ========================================
# CONFIGURAÇÃO DO BANCO (ajuste conforme seu ambiente)
# ========================================
DATABASE_URL = "postgresql://usuario:senha@localhost/portal_pge"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


async def exemplo_deteccao_medicamento():
    """
    Exemplo 1: Detecção de módulos para caso de medicamento
    """
    print("\n" + "="*60)
    print("EXEMPLO 1: Caso de Medicamento Não Incorporado")
    print("="*60 + "\n")

    db = SessionLocal()

    try:
        # Resumo dos documentos
        documentos_resumo = """
        PROCESSO: Ação de Obrigação de Fazer c/c Pedido de Tutela de Urgência
        AUTOR: Maria Silva Santos
        RÉU: Estado de Mato Grosso do Sul
        COMARCA: Campo Grande

        PEDIDO:
        Fornecimento do medicamento ADALIMUMABE 40mg para tratamento de
        artrite reumatóide.

        DOCUMENTOS JUNTADOS:
        1. Prescrição médica indicando ADALIMUMABE como única alternativa
           terapêutica eficaz para o caso
        2. Laudo médico detalhado atestando a necessidade do medicamento
           e a falha terapêutica com os medicamentos disponíveis no SUS
        3. Relatórios de exames comprovando diagnóstico de artrite reumatóide
        4. Comprovante de hipossuficiência econômica

        FUNDAMENTOS DA INICIAL:
        - Direito à saúde (CF/88, art. 196)
        - Medicamento não incorporado ao SUS pela CONITEC
        - Ausência de alternativa terapêutica eficaz no protocolo do SUS
        - Risco de morte ou agravamento irreversível do quadro clínico

        VALOR DA CAUSA: R$ 50.000,00

        JURISPRUDÊNCIA CITADA:
        - STF RE 566.471 (repercussão geral)
        - STJ Tema 106
        """

        # Inicializar detector
        detector = DetectorModulosIA(
            db=db,
            modelo="google/gemini-2.0-flash-lite",
            cache_ttl_minutes=60
        )

        # Executar detecção
        print("🤖 Iniciando detecção de módulos relevantes...\n")
        modulos_ids = await detector.detectar_modulos_relevantes(
            documentos_resumo=documentos_resumo
        )

        # Exibir resultados
        print(f"\n✅ Detecção concluída!")
        print(f"📊 Módulos detectados: {len(modulos_ids)}\n")

        if modulos_ids:
            print("MÓDULOS SELECIONADOS:")
            for modulo_id in modulos_ids:
                modulo = db.query(PromptModulo).get(modulo_id)
                if modulo:
                    print(f"  [{modulo_id}] {modulo.titulo}")
                    print(f"       Categoria: {modulo.categoria or 'N/A'}")
                    print(f"       Subcategoria: {modulo.subcategoria or 'N/A'}")
                    print()

    finally:
        db.close()


async def exemplo_deteccao_responsabilidade_civil():
    """
    Exemplo 2: Detecção de módulos para caso de responsabilidade civil
    """
    print("\n" + "="*60)
    print("EXEMPLO 2: Caso de Responsabilidade Civil do Estado")
    print("="*60 + "\n")

    db = SessionLocal()

    try:
        documentos_resumo = """
        PROCESSO: Ação de Indenização por Danos Morais e Materiais
        AUTOR: João Pedro Oliveira
        RÉU: Estado de Mato Grosso do Sul
        COMARCA: Dourados

        PEDIDO:
        Indenização por danos morais (R$ 30.000,00) e materiais (R$ 15.000,00)
        decorrentes de erro médico em hospital público estadual.

        DOCUMENTOS JUNTADOS:
        1. Prontuário médico demonstrando erro no diagnóstico
        2. Perícia médica particular atestando nexo causal
        3. Notas fiscais de tratamento particular necessário
        4. Testemunhas do ocorrido

        FUNDAMENTOS DA INICIAL:
        - Responsabilidade objetiva do Estado (CF/88, art. 37, §6º)
        - Erro médico configurado
        - Nexo causal entre conduta e dano
        - Danos morais pela dor e sofrimento
        - Danos materiais pelos gastos com tratamento

        VALOR DA CAUSA: R$ 45.000,00
        """

        detector = DetectorModulosIA(db=db)

        print("🤖 Iniciando detecção de módulos relevantes...\n")
        modulos_ids = await detector.detectar_modulos_relevantes(
            documentos_resumo=documentos_resumo
        )

        print(f"\n✅ Detecção concluída!")
        print(f"📊 Módulos detectados: {len(modulos_ids)}\n")

        if modulos_ids:
            print("MÓDULOS SELECIONADOS:")
            for modulo_id in modulos_ids:
                modulo = db.query(PromptModulo).get(modulo_id)
                if modulo:
                    print(f"  [{modulo_id}] {modulo.titulo}")
                    print()

    finally:
        db.close()


async def exemplo_cache():
    """
    Exemplo 3: Demonstração do cache
    """
    print("\n" + "="*60)
    print("EXEMPLO 3: Demonstração do Cache")
    print("="*60 + "\n")

    db = SessionLocal()

    try:
        documentos = "Processo simples sobre fornecimento de medicamento."

        detector = DetectorModulosIA(db=db, cache_ttl_minutes=5)

        # Primeira detecção
        print("🔍 PRIMEIRA DETECÇÃO (vai chamar a IA):")
        inicio = asyncio.get_event_loop().time()
        modulos1 = await detector.detectar_modulos_relevantes(documentos)
        tempo1 = asyncio.get_event_loop().time() - inicio
        print(f"⏱️ Tempo: {tempo1:.2f}s")
        print(f"📊 Módulos: {len(modulos1)}\n")

        # Segunda detecção (mesmo documento)
        print("🔍 SEGUNDA DETECÇÃO (vai usar cache):")
        inicio = asyncio.get_event_loop().time()
        modulos2 = await detector.detectar_modulos_relevantes(documentos)
        tempo2 = asyncio.get_event_loop().time() - inicio
        print(f"⏱️ Tempo: {tempo2:.2f}s")
        print(f"📊 Módulos: {len(modulos2)}")
        print(f"💾 Economia de tempo: {((tempo1 - tempo2) / tempo1 * 100):.1f}%\n")

        # Limpar cache
        detector.limpar_cache()

        # Terceira detecção (cache limpo)
        print("🔍 TERCEIRA DETECÇÃO (cache limpo, vai chamar IA novamente):")
        inicio = asyncio.get_event_loop().time()
        modulos3 = await detector.detectar_modulos_relevantes(documentos)
        tempo3 = asyncio.get_event_loop().time() - inicio
        print(f"⏱️ Tempo: {tempo3:.2f}s")
        print(f"📊 Módulos: {len(modulos3)}\n")

    finally:
        db.close()


async def exemplo_fallback():
    """
    Exemplo 4: Demonstração do fallback por palavras-chave
    """
    print("\n" + "="*60)
    print("EXEMPLO 4: Fallback por Palavras-chave")
    print("="*60 + "\n")

    db = SessionLocal()

    try:
        # Criar detector com modelo inválido (para forçar erro)
        detector = DetectorModulosIA(
            db=db,
            modelo="modelo/invalido",  # Modelo que não existe
            cache_ttl_minutes=0  # Desabilita cache
        )

        documentos = """
        Processo sobre fornecimento de medicamento não incorporado ao SUS.
        Paciente apresentou laudo médico.
        """

        print("🤖 Tentando detecção com IA (vai falhar propositalmente)...\n")

        try:
            modulos = await detector.detectar_modulos_relevantes(documentos)
        except Exception as e:
            print(f"❌ Erro esperado: {e}\n")

        print("⚠️ Sistema deve ter usado fallback por palavras-chave")
        print("✅ Teste concluído\n")

    finally:
        db.close()


async def main():
    """Executa todos os exemplos"""
    print("\n" + "🧪 TESTES DO DETECTOR DE MÓDULOS IA " + "\n")

    # Exemplo 1: Medicamento
    await exemplo_deteccao_medicamento()

    # Exemplo 2: Responsabilidade Civil
    # await exemplo_deteccao_responsabilidade_civil()

    # Exemplo 3: Cache
    # await exemplo_cache()

    # Exemplo 4: Fallback
    # await exemplo_fallback()

    print("\n" + "="*60)
    print("✅ TODOS OS TESTES CONCLUÍDOS")
    print("="*60 + "\n")


if __name__ == "__main__":
    # NOTA: Ajuste a DATABASE_URL no topo do arquivo antes de executar!
    asyncio.run(main())
