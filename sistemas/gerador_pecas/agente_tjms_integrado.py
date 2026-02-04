# sistemas/gerador_pecas/agente_tjms_integrado.py
"""
Integração do Agente TJ-MS com o Gerador de Peças.

Este módulo adapta o agente_tjms para funcionar como o primeiro agente
do fluxo de geração de peças, baixando documentos e gerando resumo consolidado.

Feature: Busca de NAT no Processo de Origem
-------------------------------------------
Quando um processo é um agravo (peticao_inicial_agravo=true) e não possui
Parecer NAT nos documentos, o sistema busca automaticamente o NAT no processo
de origem (1º grau) e o integra ao pipeline de extração.
"""

import os
import sys
import asyncio
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass, field

# Importa o agente TJ-MS do mesmo diretório
from sistemas.gerador_pecas.agente_tjms import AgenteTJMS, ResultadoAnalise, MODELO_PADRAO

# Importa serviço de busca de NAT no processo de origem
from sistemas.gerador_pecas.services_nat_origem import (
    NATOrigemResolver,
    NATOrigemResult,
    extrair_dados_peticao_inicial,
    verificar_nat_em_documentos,
    integrar_nat_ao_resultado,
    CODIGOS_NAT,
)

# Logger para rastreabilidade da feature de NAT
logger = logging.getLogger("agente_tjms_integrado")


@dataclass
class ResultadoAgente1:
    """Resultado do Agente 1 (Coletor TJ-MS)"""
    numero_processo: str
    numero_processo_origem: Optional[str] = None
    is_agravo: bool = False
    resumo_consolidado: str = ""
    total_documentos: int = 0
    documentos_analisados: int = 0
    erro: Optional[str] = None
    dados_brutos: Optional[ResultadoAnalise] = None

    # Campos para rastreabilidade do NAT
    nat_source: Optional[str] = None  # 'agravo', 'origem' ou None
    nat_origem_result: Optional[NATOrigemResult] = None  # Resultado detalhado da busca


class AgenteTJMSIntegrado:
    """
    Agente 1 - Coletor de Documentos TJ-MS
    
    Responsável por:
    1. Consultar processo via API SOAP do TJ-MS
    2. Baixar documentos relevantes
    3. Gerar resumos individuais de cada documento
    4. Produzir resumo consolidado para os próximos agentes
    """
    
    def __init__(
        self, 
        modelo: str = None, 
        db_session = None, 
        formato_saida: str = "json",
        codigos_permitidos: set = None,  # Códigos de documento a analisar (None = usa filtro legado)
        codigos_primeiro_doc: set = None,  # Códigos que devem pegar só o primeiro documento cronológico
        max_workers: int = 30  # Número máximo de chamadas paralelas à IA
    ):
        """
        Inicializa o agente.
        
        Args:
            modelo: Modelo LLM a usar (padrão: gemini-3-flash-preview)
            db_session: Sessão do banco de dados para buscar formatos JSON
            formato_saida: 'json' ou 'md' - formato de saída dos resumos
            codigos_permitidos: Conjunto de códigos de documento a analisar (None = usa filtro legado)
            codigos_primeiro_doc: Códigos que devem pegar só o primeiro documento (ex: Petição Inicial)
            max_workers: Número máximo de chamadas paralelas à IA (padrão: 30)
        """
        self.modelo = modelo or MODELO_PADRAO
        self.db_session = db_session
        self.formato_saida = formato_saida
        self.codigos_permitidos = codigos_permitidos
        self.codigos_primeiro_doc = codigos_primeiro_doc or set()
        self.max_workers = max_workers
        self.agente = AgenteTJMS(
            modelo=self.modelo,
            formato_saida=formato_saida,
            db_session=db_session,
            codigos_permitidos=codigos_permitidos,
            codigos_primeiro_doc=codigos_primeiro_doc,
            max_workers=max_workers
        )
    
    def atualizar_codigos_permitidos(self, codigos: set, codigos_primeiro_doc: set = None):
        """
        Atualiza os códigos permitidos após inicialização.
        Útil para modo automático onde os códigos são definidos depois.
        
        Args:
            codigos: Códigos de documentos permitidos
            codigos_primeiro_doc: Códigos que devem pegar só o primeiro documento
        """
        self.codigos_permitidos = codigos
        self.agente.codigos_permitidos = codigos
        
        if codigos_primeiro_doc is not None:
            self.codigos_primeiro_doc = codigos_primeiro_doc
            self.agente.codigos_primeiro_doc = codigos_primeiro_doc
    
    async def coletar_e_resumir(
        self,
        numero_processo: str,
        gerar_relatorio: bool = False  # Desativado por padrão - apenas consolida resumos
    ) -> ResultadoAgente1:
        """
        Coleta documentos do processo e gera resumo consolidado.

        Inclui busca automática de NAT no processo de origem quando:
        - A petição inicial indica agravo (peticao_inicial_agravo=true)
        - Não há NAT nos documentos do agravo

        Args:
            numero_processo: Número CNJ do processo (com ou sem formatação)
            gerar_relatorio: Se True, gera relatório final além dos resumos

        Returns:
            ResultadoAgente1 com resumo consolidado e metadados
        """
        resultado = ResultadoAgente1(numero_processo=numero_processo)

        try:
            print(f"\n AGENTE 1 - Iniciando coleta do processo {numero_processo}")
            print("=" * 60)

            # Executa análise completa via AgenteTJMS
            analise = await self.agente.analisar_processo(
                numero_processo=numero_processo,
                gerar_relatorio=gerar_relatorio
            )

            # Verifica erros
            if analise.erro_geral:
                resultado.erro = analise.erro_geral
                return resultado

            # Preenche metadados
            resultado.numero_processo_origem = analise.processo_origem
            resultado.is_agravo = analise.is_agravo
            resultado.total_documentos = len(analise.documentos)
            resultado.documentos_analisados = len(analise.documentos_com_resumo())
            resultado.dados_brutos = analise

            # ==============================================================
            # FEATURE: Busca de NAT no processo de origem para agravos
            # ==============================================================
            nat_result = await self._buscar_nat_processo_origem(analise)
            resultado.nat_origem_result = nat_result
            resultado.nat_source = nat_result.nat_source if nat_result else None

            # Se encontrou NAT no processo de origem, processa e integra
            if nat_result and nat_result.nat_encontrado_origem and nat_result.documento_nat:
                await self._processar_nat_origem(analise, nat_result)
                # Atualiza contadores
                resultado.total_documentos = len(analise.documentos)
                resultado.documentos_analisados = len(analise.documentos_com_resumo())
            # ==============================================================

            # Monta resumo consolidado
            resultado.resumo_consolidado = self._montar_resumo_consolidado(analise)

            print("=" * 60)
            print(f"✅ AGENTE 1 - Coleta concluída!")
            print(f"   📄 Documentos analisados: {resultado.documentos_analisados}")
            if resultado.is_agravo:
                print(f"   [JUR]  Agravo de Instrumento - Origem: {resultado.numero_processo_origem}")

            # Log de telemetria do NAT
            if resultado.nat_source:
                print(f"   🔬 Parecer NAT: nat_source={resultado.nat_source}")
                if resultado.nat_source == "origem" and nat_result:
                    print(f"       NAT obtido do processo de origem: {nat_result.numero_processo_origem}")

            return resultado

        except Exception as e:
            resultado.erro = f"Erro no Agente 1: {str(e)}"
            print(f"[ERRO] AGENTE 1 - Erro: {resultado.erro}")
            import traceback
            traceback.print_exc()
            return resultado

    async def _buscar_nat_processo_origem(
        self,
        analise: ResultadoAnalise
    ) -> Optional[NATOrigemResult]:
        """
        Verifica se é necessário buscar NAT no processo de origem e executa a busca.

        A busca só é realizada quando:
        1. peticao_inicial_agravo = true no JSON da petição inicial
        2. Não existe NAT nos documentos do agravo (códigos 207, 8451, 9636, 59, 8490)

        Args:
            analise: Resultado da análise do processo de agravo

        Returns:
            NATOrigemResult com o resultado da busca (ou None se não aplicável)
        """
        import aiohttp

        try:
            # Extrai dados da petição inicial
            dados_pi = extrair_dados_peticao_inicial(analise)

            if not dados_pi:
                logger.debug("[NAT-ORIGEM] Sem dados de petição inicial extraídos")
                return None

            # Cria resolver e executa verificação
            resolver = NATOrigemResolver(self.agente, self.db_session)

            # Usa sessão aiohttp para a busca
            connector = aiohttp.TCPConnector(limit=10, limit_per_host=10)
            async with aiohttp.ClientSession(connector=connector) as session:
                result = await resolver.resolver(analise, dados_pi)

                # Se precisa baixar o conteúdo do NAT
                if result.nat_encontrado_origem and result.documento_nat:
                    from sistemas.gerador_pecas.agente_tjms import baixar_documentos_async, extrair_documentos_xml

                    doc_nat = result.documento_nat
                    numero_origem = result.numero_processo_origem

                    logger.info(f"[NAT-ORIGEM] Baixando conteúdo do NAT: doc_id={doc_nat.id}")

                    try:
                        xml_download = await baixar_documentos_async(
                            session,
                            numero_origem,
                            [doc_nat.id],
                            timeout=120
                        )

                        docs_baixados = extrair_documentos_xml(xml_download)

                        for doc_baixado in docs_baixados:
                            if doc_baixado.id == doc_nat.id and doc_baixado.conteudo_base64:
                                doc_nat.conteudo_base64 = doc_baixado.conteudo_base64
                                logger.info(
                                    f"[NAT-ORIGEM] Conteúdo do NAT baixado: "
                                    f"doc_id={doc_nat.id}, "
                                    f"tamanho_base64={len(doc_baixado.conteudo_base64)}"
                                )
                                break
                        else:
                            logger.warning(
                                f"[NAT-ORIGEM] Conteúdo do NAT não encontrado no download: doc_id={doc_nat.id}"
                            )
                    except Exception as e:
                        logger.error(f"[NAT-ORIGEM] Erro ao baixar conteúdo do NAT: {e}")
                        result.erro = f"Erro ao baixar conteúdo: {str(e)}"

                return result

        except Exception as e:
            logger.error(f"[NAT-ORIGEM] Erro na busca de NAT no processo de origem: {e}", exc_info=True)
            return NATOrigemResult(
                busca_realizada=False,
                erro=str(e),
                motivo=f"Erro na busca: {str(e)}"
            )

    async def _processar_nat_origem(
        self,
        analise: ResultadoAnalise,
        nat_result: NATOrigemResult
    ) -> bool:
        """
        Processa o NAT encontrado no processo de origem e o integra ao resultado.

        O NAT é processado usando o mesmo pipeline de extração dos demais documentos.

        Args:
            analise: Resultado da análise do processo de agravo
            nat_result: Resultado da busca de NAT contendo o documento

        Returns:
            True se o NAT foi processado e integrado com sucesso
        """
        import aiohttp

        if not nat_result.documento_nat or not nat_result.documento_nat.conteudo_base64:
            logger.warning("[NAT-ORIGEM] NAT sem conteúdo para processar")
            return False

        doc_nat = nat_result.documento_nat

        try:
            # Processa o NAT usando o mesmo pipeline do agente
            connector = aiohttp.TCPConnector(limit=5, limit_per_host=5)
            async with aiohttp.ClientSession(connector=connector) as session:
                print(f"   [NAT-ORIGEM] Processando NAT do processo de origem...")
                await self.agente._processar_documento_async(session, doc_nat)

            # Verifica se o processamento gerou resumo
            if doc_nat.resumo:
                logger.info(
                    f"[NAT-ORIGEM] NAT processado com sucesso: "
                    f"doc_id={doc_nat.id}, "
                    f"resumo_len={len(doc_nat.resumo)}"
                )
                print(f"   [NAT-ORIGEM] ✅ NAT processado e resumido com sucesso")
            else:
                logger.warning(f"[NAT-ORIGEM] NAT processado mas sem resumo: doc_id={doc_nat.id}")
                print(f"   [NAT-ORIGEM] ⚠ NAT processado mas sem resumo")

            # Integra ao resultado (com verificação de idempotência)
            integrado = integrar_nat_ao_resultado(analise, nat_result)

            if integrado:
                print(f"   [NAT-ORIGEM] ✅ NAT integrado ao resultado (nat_source=origem)")

            return integrado

        except Exception as e:
            logger.error(f"[NAT-ORIGEM] Erro ao processar NAT: {e}", exc_info=True)
            print(f"   [NAT-ORIGEM] ❌ Erro ao processar NAT: {e}")
            return False
    
    def _montar_resumo_consolidado(self, analise: ResultadoAnalise) -> str:
        """
        Monta o resumo consolidado a partir dos resumos individuais.
        
        Formato otimizado para o Agente 2 (detector de módulos) processar.
        Os resumos podem estar em formato JSON ou Markdown, dependendo da configuração.
        """
        import json
        partes = []
        
        # Cabeçalho
        partes.append(f"# RESUMO CONSOLIDADO DO PROCESSO")
        partes.append(f"**Processo**: {analise.numero_processo}")
        partes.append(f"**Data da Análise**: {analise.data_analise.strftime('%d/%m/%Y %H:%M')}")
        partes.append(f"**Formato dos Resumos**: {self.formato_saida.upper()}")
        
        if analise.is_agravo:
            partes.append(f"\n**[WARN] AGRAVO DE INSTRUMENTO**")
            partes.append(f"**Processo de Origem (1º Grau)**: {analise.processo_origem}")
        
        partes.append(f"\n**Total de Documentos Analisados**: {len(analise.documentos_com_resumo())}")
        
        # Dados do processo extraídos do XML (SEM IA)
        if analise.dados_processo:
            partes.append("\n---\n")
            partes.append("## DADOS DO PROCESSO (extraídos do sistema)")
            partes.append("```json")
            partes.append(json.dumps(analise.dados_processo.to_json(), indent=2, ensure_ascii=False))
            partes.append("```")
        
        partes.append("\n---\n")
        
        # Documentos do processo principal (ou do AI)
        docs_principal = analise.documentos_processo_principal()
        if docs_principal:
            if analise.is_agravo:
                partes.append("## DOCUMENTOS DO AGRAVO DE INSTRUMENTO\n")
            else:
                partes.append("## DOCUMENTOS DO PROCESSO\n")
            
            for i, doc in enumerate(docs_principal, 1):
                partes.append(f"### {i}. {doc.categoria_nome}")
                partes.append(f"**Data**: {doc.data_formatada}")
                if doc.descricao_ia:
                    partes.append(f"**Tipo identificado**: {doc.descricao_ia}")
                partes.append(f"\n{doc.resumo}\n")
                partes.append("---\n")
        
        # Documentos do processo de origem (se for agravo)
        docs_origem = analise.documentos_processo_origem()
        if docs_origem:
            partes.append(f"\n## DOCUMENTOS DO PROCESSO DE ORIGEM ({analise.processo_origem})\n")
            
            for i, doc in enumerate(docs_origem, 1):
                partes.append(f"### [ORIGEM] {i}. {doc.categoria_nome}")
                partes.append(f"**Data**: {doc.data_formatada}")
                if doc.descricao_ia:
                    partes.append(f"**Tipo identificado**: {doc.descricao_ia}")
                partes.append(f"\n{doc.resumo}\n")
                partes.append("---\n")
        
        # Nota final
        partes.append("\n---")
        partes.append("*Este resumo consolidado foi gerado automaticamente a partir dos documentos do processo.*")
        
        return "\n".join(partes)
    
    def filtrar_e_remontar_resumo(
        self,
        resultado: ResultadoAgente1,
        codigos_permitidos: set
    ) -> str:
        """
        Filtra os documentos do resultado por códigos permitidos e remonta o resumo consolidado.
        
        Usado no modo automático após a detecção do tipo de peça.
        
        Args:
            resultado: Resultado original do Agente 1
            codigos_permitidos: Conjunto de códigos de documento permitidos
            
        Returns:
            Novo resumo consolidado com apenas os documentos filtrados
        """
        if not resultado.dados_brutos or not codigos_permitidos:
            return resultado.resumo_consolidado
        
        analise = resultado.dados_brutos
        
        # Conta quantos documentos serão mantidos
        docs_antes = len(analise.documentos_com_resumo())
        
        # Filtra os documentos temporariamente (sem modificar o original)
        docs_filtrados = []
        for doc in analise.documentos:
            if doc.resumo and not doc.irrelevante:
                try:
                    codigo = int(doc.tipo_documento) if doc.tipo_documento else 0
                    if codigo in codigos_permitidos:
                        docs_filtrados.append(doc)
                except (ValueError, TypeError):
                    # Se não conseguir converter, mantém o documento
                    docs_filtrados.append(doc)
        
        docs_depois = len(docs_filtrados)
        print(f" Filtro pós-detecção: {docs_antes} -> {docs_depois} documentos")
        
        if not docs_filtrados:
            return resultado.resumo_consolidado
        
        # Remonta o resumo com os documentos filtrados
        import json
        partes = []
        
        # Cabeçalho
        partes.append(f"# RESUMO CONSOLIDADO DO PROCESSO (FILTRADO)")
        partes.append(f"**Processo**: {analise.numero_processo}")
        partes.append(f"**Data da Análise**: {analise.data_analise.strftime('%d/%m/%Y %H:%M')}")
        partes.append(f"**Formato dos Resumos**: {self.formato_saida.upper()}")
        partes.append(f"**Documentos após filtro**: {docs_depois} de {docs_antes}")
        
        if analise.is_agravo:
            partes.append(f"\n**[WARN] AGRAVO DE INSTRUMENTO**")
            partes.append(f"**Processo de Origem (1º Grau)**: {analise.processo_origem}")
        
        # Dados do processo extraídos do XML (SEM IA)
        if analise.dados_processo:
            partes.append("\n---\n")
            partes.append("## DADOS DO PROCESSO (extraídos do sistema)")
            partes.append("```json")
            partes.append(json.dumps(analise.dados_processo.to_json(), indent=2, ensure_ascii=False))
            partes.append("```")
        
        partes.append("\n---\n")
        
        # Separa documentos do principal e origem
        docs_principal = [d for d in docs_filtrados if not d.processo_origem]
        docs_origem = [d for d in docs_filtrados if d.processo_origem]
        
        # Documentos do processo principal (ou do AI)
        if docs_principal:
            if analise.is_agravo:
                partes.append("## DOCUMENTOS DO AGRAVO DE INSTRUMENTO\n")
            else:
                partes.append("## DOCUMENTOS DO PROCESSO\n")
            
            for i, doc in enumerate(docs_principal, 1):
                partes.append(f"### {i}. {doc.categoria_nome}")
                partes.append(f"**Data**: {doc.data_formatada}")
                if doc.descricao_ia:
                    partes.append(f"**Tipo identificado**: {doc.descricao_ia}")
                partes.append(f"\n{doc.resumo}\n")
                partes.append("---\n")
        
        # Documentos do processo de origem (se for agravo)
        if docs_origem:
            partes.append(f"\n## DOCUMENTOS DO PROCESSO DE ORIGEM ({analise.processo_origem})\n")
            
            for i, doc in enumerate(docs_origem, 1):
                partes.append(f"### [ORIGEM] {i}. {doc.categoria_nome}")
                partes.append(f"**Data**: {doc.data_formatada}")
                if doc.descricao_ia:
                    partes.append(f"**Tipo identificado**: {doc.descricao_ia}")
                partes.append(f"\n{doc.resumo}\n")
                partes.append("---\n")
        
        # Nota final
        partes.append("\n---")
        partes.append("*Este resumo foi filtrado para incluir apenas documentos relevantes para o tipo de peça selecionado.*")
        
        return "\n".join(partes)


async def processar_processo_tjms(numero_processo: str, db_session = None, formato_saida: str = "json") -> ResultadoAgente1:
    """
    Função de conveniência para processar um processo.
    
    Args:
        numero_processo: Número CNJ do processo
        db_session: Sessão do banco de dados (opcional, para formato JSON)
        formato_saida: 'json' ou 'md' - formato de saída dos resumos
        
    Returns:
        ResultadoAgente1 com resumo consolidado
    """
    agente = AgenteTJMSIntegrado(db_session=db_session, formato_saida=formato_saida)
    return await agente.coletar_e_resumir(numero_processo)


# Teste standalone
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Uso: python agente_tjms_integrado.py <numero_processo>")
        sys.exit(1)
    
    numero = sys.argv[1]
    resultado = asyncio.run(processar_processo_tjms(numero))
    
    if resultado.erro:
        print(f"\n[ERRO] Erro: {resultado.erro}")
    else:
        print(f"\n Resumo consolidado ({len(resultado.resumo_consolidado)} caracteres):")
        print("-" * 40)
        print(resultado.resumo_consolidado[:2000] + "..." if len(resultado.resumo_consolidado) > 2000 else resultado.resumo_consolidado)
