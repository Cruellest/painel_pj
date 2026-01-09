# sistemas/pedido_calculo/services.py
"""
Serviço orquestrador para geração de Pedido de Cálculo

Coordena o pipeline de processamento:
1. Upload/análise do XML
2. Download de documentos
3. Extração de informações (Agente 2)
4. Geração do pedido (Agente 3)

Autor: LAB/PGE-MS
"""

import json
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple

from .models import (
    ResultadoAgente1,
    ResultadoAgente2,
    PedidoCalculo,
    DadosBasicos,
    DocumentosParaDownload,
    MovimentosRelevantes
)
from .xml_parser import XMLParser
from .agentes import Agente1AnaliseXML, Agente2ExtracaoPDFs, Agente3GeracaoPedido
from .document_downloader import DocumentDownloader


def _calcular_dias_uteis(data_inicial: date, dias: int) -> date:
    """
    Calcula data final após N dias úteis.
    
    Considera apenas segunda a sexta (não inclui feriados).
    """
    data = data_inicial
    dias_contados = 0
    while dias_contados < dias:
        data += timedelta(days=1)
        if data.weekday() < 5:  # Segunda a Sexta
            dias_contados += 1
    return data


class PedidoCalculoService:
    """
    Serviço principal para geração de Pedido de Cálculo.

    Orquestra todo o pipeline de processamento.
    """

    def __init__(self, modelo: str = "gemini-3-flash-preview", logger=None):
        """
        Inicializa o serviço.

        Args:
            modelo: Modelo de IA a usar (padrão: gemini-3-flash-preview)
            logger: Logger opcional para debug de chamadas de IA
        """
        self.modelo = modelo
        self.logger = logger
        self.agente1 = Agente1AnaliseXML(modelo)
        self.agente2 = Agente2ExtracaoPDFs(modelo, logger=logger)
        self.agente3 = Agente3GeracaoPedido(modelo, logger=logger)
    
    async def processar_xml(self, xml_texto: str) -> Tuple[ResultadoAgente1, Optional[str]]:
        """
        Processa XML do processo (etapa 1).
        
        Args:
            xml_texto: XML completo do processo
            
        Returns:
            Tupla (ResultadoAgente1, erro opcional)
        """
        resultado = await self.agente1.analisar(xml_texto)
        
        if resultado.erro:
            return resultado, resultado.erro
        
        return resultado, None
    
    async def baixar_documentos(
        self,
        numero_processo: str,
        documentos: DocumentosParaDownload,
        dados_agente1: ResultadoAgente1 = None
    ) -> Tuple[Dict[str, str], Optional[str]]:
        """
        Baixa documentos identificados (etapa 2).

        Para cumprimentos autônomos, busca do processo de ORIGEM:
        - Sentenças e acórdãos
        - Certidão de citação
        - Datas processuais (ajuizamento, trânsito em julgado)

        Args:
            numero_processo: Número do processo
            documentos: Documentos identificados pelo Agente 1
            dados_agente1: Resultado do Agente 1 (será atualizado com dados do origem se cumprimento)

        Returns:
            Tupla (dict com textos, erro opcional)
        """
        try:
            # Debug: mostra o que será baixado
            print(f"[DOWNLOAD] Processo: {numero_processo}")
            print(f"[DOWNLOAD] É cumprimento autônomo: {documentos.is_cumprimento_autonomo}")
            print(f"[DOWNLOAD] Processo de origem: {documentos.numero_processo_origem}")

            # IDs de documentos a baixar
            ids_sentencas = list(documentos.sentencas)
            ids_acordaos = list(documentos.acordaos)

            # Número do processo para baixar sentenças/acórdãos
            numero_processo_docs = numero_processo

            # Se for cumprimento autônomo, buscar documentos do processo de ORIGEM
            if documentos.is_cumprimento_autonomo and documentos.numero_processo_origem:
                print(f"[DOWNLOAD] Buscando documentos do processo de ORIGEM: {documentos.numero_processo_origem}")
                print(f"[DOWNLOAD] *** CUMPRIMENTO AUTÔNOMO: Sentenças, acórdãos, certidão de citação, data de ajuizamento e trânsito em julgado serão do processo de ORIGEM ***")

                async with DocumentDownloader() as downloader:
                    # Consulta XML do processo de origem
                    xml_origem = await downloader.consultar_processo(documentos.numero_processo_origem)

                    # Parseia o XML de origem para identificar documentos E DADOS PROCESSUAIS
                    # Usa forcar_busca_sentencas=True porque o processo de origem pode
                    # também ser classificado como cumprimento (em caso de cumprimentos encadeados)
                    parser_origem = XMLParser(xml_origem)

                    # Extrai DADOS BÁSICOS do processo de origem (data ajuizamento, etc)
                    dados_basicos_origem = parser_origem.extrair_dados_basicos()
                    print(f"[ORIGEM] Dados básicos do processo de origem:")
                    print(f"[ORIGEM]   - Data ajuizamento: {dados_basicos_origem.data_ajuizamento}")
                    print(f"[ORIGEM]   - Autor: {dados_basicos_origem.autor}")

                    # Extrai MOVIMENTOS RELEVANTES do processo de origem (trânsito em julgado, etc)
                    movimentos_origem = parser_origem.extrair_movimentos_relevantes()
                    print(f"[ORIGEM] Movimentos do processo de origem:")
                    print(f"[ORIGEM]   - Data trânsito em julgado: {movimentos_origem.transito_julgado}")

                    # Extrai documentos para download do processo de origem
                    docs_origem = parser_origem.identificar_documentos_para_download(
                        forcar_busca_sentencas=True
                    )

                    # *** ATUALIZA DADOS DO AGENTE 1 COM DADOS DO PROCESSO DE ORIGEM ***
                    if dados_agente1:
                        # Preserva o número do processo do cumprimento, mas usa datas do origem
                        print(f"[ORIGEM] Atualizando dados do Agente 1 com informações do processo de origem:")

                        # Data de ajuizamento do processo de ORIGEM
                        if dados_basicos_origem.data_ajuizamento:
                            print(f"[ORIGEM]   - Data ajuizamento: {dados_agente1.dados_basicos.data_ajuizamento} -> {dados_basicos_origem.data_ajuizamento}")
                            dados_agente1.dados_basicos.data_ajuizamento = dados_basicos_origem.data_ajuizamento

                        # Data de trânsito em julgado do processo de ORIGEM
                        if movimentos_origem.transito_julgado:
                            print(f"[ORIGEM]   - Data trânsito em julgado: {dados_agente1.movimentos_relevantes.transito_julgado} -> {movimentos_origem.transito_julgado}")
                            dados_agente1.movimentos_relevantes.transito_julgado = movimentos_origem.transito_julgado

                        # Certidões de citação do processo de ORIGEM
                        if docs_origem.certidoes_citacao_intimacao:
                            print(f"[ORIGEM]   - Certidões de citação: usando {len(docs_origem.certidoes_citacao_intimacao)} certidão(ões) do processo de origem")
                            # Marca que as certidões são do processo de origem para referência
                            dados_agente1.documentos_para_download.certidoes_origem = docs_origem.certidoes_citacao_intimacao

                        # Guarda referência aos dados do processo de origem
                        dados_agente1.dados_processo_origem = {
                            "numero_processo": documentos.numero_processo_origem,
                            "data_ajuizamento": dados_basicos_origem.data_ajuizamento.strftime("%d/%m/%Y") if dados_basicos_origem.data_ajuizamento else None,
                            "data_transito_julgado": movimentos_origem.transito_julgado.strftime("%d/%m/%Y") if movimentos_origem.transito_julgado else None,
                            "autor": dados_basicos_origem.autor,
                            "cpf_autor": dados_basicos_origem.cpf_autor,
                        }

                    # Usa sentenças e acórdãos do processo de origem
                    ids_sentencas = docs_origem.sentencas
                    ids_acordaos = docs_origem.acordaos
                    numero_processo_docs = documentos.numero_processo_origem

                    print(f"[DOWNLOAD] Sentenças do processo de origem: {ids_sentencas}")
                    print(f"[DOWNLOAD] Acórdãos do processo de origem: {ids_acordaos}")

                    # Busca certidão de citação do processo de ORIGEM
                    ids_certidoes_origem = []
                    for cert in docs_origem.certidoes_citacao_intimacao:
                        if cert.id_certidao_9508:
                            ids_certidoes_origem.append(cert.id_certidao_9508)

                    print(f"[DOWNLOAD] Certidões de citação do processo de origem: {ids_certidoes_origem}")

                    # Baixa documentos do processo de origem (sentenças, acórdãos, certidão de citação)
                    textos_origem = await downloader.baixar_todos_relevantes(
                        numero_processo_docs,
                        ids_sentencas=ids_sentencas,
                        ids_acordaos=ids_acordaos,
                        ids_certidoes=ids_certidoes_origem,
                        ids_cumprimento=[]
                    )

                    print(f"[DOWNLOAD] Textos do processo de origem: {list(textos_origem.keys())}")

                    # Agora baixa documentos do processo de CUMPRIMENTO (intimação, planilha)
                    ids_certidoes_cumprimento = []
                    for cert in documentos.certidoes_citacao_intimacao:
                        if cert.id_certidao_9508:
                            ids_certidoes_cumprimento.append(cert.id_certidao_9508)

                    ids_cumprimento = []
                    docs_info_cumprimento = []
                    if documentos.pedido_cumprimento and "documentos" in documentos.pedido_cumprimento:
                        for doc in documentos.pedido_cumprimento["documentos"]:
                            if "id" in doc:
                                ids_cumprimento.append(doc["id"])
                                docs_info_cumprimento.append(doc)

                    print(f"[DOWNLOAD] Certidões do cumprimento: {ids_certidoes_cumprimento}")
                    print(f"[DOWNLOAD] Documentos do cumprimento: {ids_cumprimento}")

                    textos_cumprimento = await downloader.baixar_todos_relevantes(
                        numero_processo,
                        ids_sentencas=[],
                        ids_acordaos=[],
                        ids_certidoes=ids_certidoes_cumprimento,
                        ids_cumprimento=ids_cumprimento,
                        docs_info_cumprimento=docs_info_cumprimento,
                        logger=self.logger
                    )

                    print(f"[DOWNLOAD] Textos do cumprimento: {list(textos_cumprimento.keys())}")

                    # Mescla os textos (origem + cumprimento)
                    textos = {**textos_origem, **textos_cumprimento}

                    print(f"[DOWNLOAD] Total de textos baixados: {list(textos.keys())}")
                    return textos, None

            # Processo normal (não é cumprimento autônomo)
            print(f"[DOWNLOAD] Sentenças: {ids_sentencas}")
            print(f"[DOWNLOAD] Acórdãos: {ids_acordaos}")

            # Coleta IDs de certidões
            ids_certidoes = []
            for cert in documentos.certidoes_citacao_intimacao:
                if cert.id_certidao_9508:
                    ids_certidoes.append(cert.id_certidao_9508)

            print(f"[DOWNLOAD] Certidões: {ids_certidoes}")

            # Coleta IDs do cumprimento
            ids_cumprimento = []
            docs_info_cumprimento = []
            if documentos.pedido_cumprimento and "documentos" in documentos.pedido_cumprimento:
                for doc in documentos.pedido_cumprimento["documentos"]:
                    if "id" in doc:
                        ids_cumprimento.append(doc["id"])
                        docs_info_cumprimento.append(doc)

            print(f"[DOWNLOAD] Cumprimento: {ids_cumprimento}")

            async with DocumentDownloader() as downloader:
                textos = await downloader.baixar_todos_relevantes(
                    numero_processo,
                    ids_sentencas=ids_sentencas,
                    ids_acordaos=ids_acordaos,
                    ids_certidoes=ids_certidoes,
                    ids_cumprimento=ids_cumprimento,
                    docs_info_cumprimento=docs_info_cumprimento,
                    logger=self.logger
                )

            print(f"[DOWNLOAD] Textos baixados: {list(textos.keys())}")
            return textos, None

        except Exception as e:
            import traceback
            traceback.print_exc()
            return {}, f"Erro ao baixar documentos: {str(e)}"
    
    async def extrair_informacoes(
        self, 
        textos_documentos: Dict[str, str]
    ) -> Tuple[ResultadoAgente2, Optional[str]]:
        """
        Extrai informações dos documentos (etapa 3).
        
        Args:
            textos_documentos: Dict com tipo -> texto do documento
            
        Returns:
            Tupla (ResultadoAgente2, erro opcional)
        """
        resultado = await self.agente2.extrair(textos_documentos)
        
        if resultado.erro:
            return resultado, resultado.erro
        
        return resultado, None
    
    async def gerar_pedido(
        self, 
        dados_agente1: ResultadoAgente1,
        dados_agente2: ResultadoAgente2
    ) -> Tuple[str, Optional[str]]:
        """
        Gera pedido de cálculo (etapa 4).
        
        Args:
            dados_agente1: Resultado da análise do XML
            dados_agente2: Resultado da extração dos PDFs
            
        Returns:
            Tupla (markdown do pedido, erro opcional)
        """
        try:
            markdown = await self.agente3.gerar(dados_agente1, dados_agente2)
            
            if markdown.startswith("# ERRO"):
                return markdown, "Erro na geração do pedido"
            
            return markdown, None
            
        except Exception as e:
            return "", f"Erro ao gerar pedido: {str(e)}"
    
    async def processar_completo(
        self, 
        xml_texto: str,
        callback_progresso: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Executa pipeline completo de processamento.
        
        Args:
            xml_texto: XML do processo
            callback_progresso: Função opcional para reportar progresso
            
        Returns:
            Dict com resultado completo:
            {
                "sucesso": bool,
                "erro": str opcional,
                "dados_basicos": dict,
                "documentos_baixados": int,
                "pedido_markdown": str,
                "dados_agente1": dict,
                "dados_agente2": dict
            }
        """
        resultado = {
            "sucesso": False,
            "erro": None,
            "dados_basicos": None,
            "documentos_baixados": 0,
            "pedido_markdown": None,
            "dados_agente1": None,
            "dados_agente2": None
        }
        
        try:
            # Etapa 1: Análise do XML
            if callback_progresso:
                callback_progresso(1, "Analisando XML do processo...")
            
            agente1_result, erro = await self.processar_xml(xml_texto)
            if erro:
                resultado["erro"] = erro
                return resultado
            
            resultado["dados_agente1"] = agente1_result.to_dict()
            resultado["dados_basicos"] = agente1_result.dados_basicos.to_dict()
            
            # Etapa 2: Download de documentos
            # Para cumprimentos autônomos, também busca dados do processo de origem
            if callback_progresso:
                callback_progresso(2, "Baixando documentos do TJ-MS...")

            numero_processo = agente1_result.dados_basicos.numero_processo
            textos, erro = await self.baixar_documentos(
                numero_processo,
                agente1_result.documentos_para_download,
                dados_agente1=agente1_result  # Passa para atualizar com dados do processo de origem
            )

            # Atualiza os dados do agente1 após o download (podem ter sido modificados com dados do origem)
            resultado["dados_agente1"] = agente1_result.to_dict()
            resultado["dados_basicos"] = agente1_result.dados_basicos.to_dict()

            if erro:
                resultado["erro"] = erro
                return resultado
            
            resultado["documentos_baixados"] = len(textos)
            
            # Etapa 3: Extração de informações
            if callback_progresso:
                callback_progresso(3, "Extraindo informações dos documentos...")
            
            agente2_result, erro = await self.extrair_informacoes(textos)
            if erro:
                resultado["erro"] = erro
                return resultado
            
            resultado["dados_agente2"] = agente2_result.to_dict()
            
            # Etapa 4: Geração do pedido
            if callback_progresso:
                callback_progresso(4, "Gerando pedido de cálculo...")
            
            markdown, erro = await self.gerar_pedido(agente1_result, agente2_result)
            if erro:
                resultado["erro"] = erro
                return resultado
            
            resultado["pedido_markdown"] = markdown
            resultado["sucesso"] = True
            
            return resultado
            
        except Exception as e:
            resultado["erro"] = f"Erro no processamento: {str(e)}"
            return resultado
    
    def calcular_prazo_final(self, termo_inicial: date, dias_uteis: int = 30) -> date:
        """
        Calcula prazo final para o cálculo.
        
        Args:
            termo_inicial: Data de início do prazo
            dias_uteis: Número de dias úteis (padrão: 30)
            
        Returns:
            Data do termo final
        """
        return _calcular_dias_uteis(termo_inicial, dias_uteis)
    
    def montar_objeto_pedido(
        self,
        dados_agente1: ResultadoAgente1,
        dados_agente2: ResultadoAgente2
    ) -> PedidoCalculo:
        """
        Monta objeto PedidoCalculo estruturado.
        
        Usado para edição no frontend.
        """
        return self.agente3.montar_pedido_calculo(dados_agente1, dados_agente2)
