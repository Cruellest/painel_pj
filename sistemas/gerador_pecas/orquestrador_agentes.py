# sistemas/gerador_pecas/orquestrador_agentes.py
"""
Orquestrador de Agentes para Geração de Peças Jurídicas

Coordena os 3 agentes do fluxo:
1. Agente 1 (Coletor): Baixa documentos do TJ-MS e gera resumo consolidado
2. Agente 2 (Detector): Analisa resumo e ativa prompts modulares relevantes
3. Agente 3 (Gerador): Gera a peça jurídica usando Gemini 3 Pro
"""

import os
import json
import asyncio
import httpx
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from sistemas.gerador_pecas.agente_tjms_integrado import AgenteTJMSIntegrado, ResultadoAgente1
from sistemas.gerador_pecas.detector_modulos import DetectorModulosIA
from sistemas.gerador_pecas.gemini_client import chamar_gemini_async, normalizar_modelo
# NOTA: TemplateFormatacao não é mais importado aqui - templates serão usados apenas para MD->DOCX
from admin.models import ConfiguracaoIA
from admin.models_prompts import PromptModulo


# Modelos padrão (usados se não houver configuração no banco)
MODELO_AGENTE1_PADRAO = "gemini-3-flash-preview"


def consolidar_dados_extracao(resultado_agente1: ResultadoAgente1) -> Dict[str, Any]:
    """
    Consolida dados extraídos dos resumos JSON dos documentos.
    
    Percorre todos os documentos com resumo em formato JSON e extrai
    as variáveis para um dicionário consolidado.
    
    Regras de consolidação:
    - Para booleanos: lógica OR (se qualquer documento tem True, resultado é True)
    - Para listas: concatena valores únicos
    - Para strings/números: mantém o primeiro valor encontrado (ou lista se múltiplos)
    
    Args:
        resultado_agente1: Resultado do Agente 1 com documentos analisados
        
    Returns:
        Dicionário {slug: valor} com variáveis consolidadas
    """
    dados_consolidados = {}

    if not resultado_agente1.dados_brutos:
        print("[EXTRAÇÃO] AVISO: dados_brutos é None - não há documentos para extrair")
        return dados_consolidados

    documentos = resultado_agente1.dados_brutos.documentos_com_resumo()
    print(f"[EXTRAÇÃO] Total de documentos com resumo: {len(documentos)}")

    for doc in documentos:
        if not doc.resumo:
            print(f"[EXTRAÇÃO] Doc '{doc.categoria_nome}': resumo vazio, pulando")
            continue

        # Tenta parsear o resumo como JSON
        try:
            # Remove possíveis marcadores de código markdown
            resumo_limpo = doc.resumo.strip()
            if resumo_limpo.startswith('```json'):
                resumo_limpo = resumo_limpo[7:]
            elif resumo_limpo.startswith('```'):
                resumo_limpo = resumo_limpo[3:]
            if resumo_limpo.endswith('```'):
                resumo_limpo = resumo_limpo[:-3]
            resumo_limpo = resumo_limpo.strip()

            # Se não parece JSON, pula
            if not resumo_limpo.startswith('{'):
                print(f"[EXTRAÇÃO] Doc '{doc.categoria_nome}': não é JSON (inicia com: '{resumo_limpo[:50]}...')")
                continue

            dados_doc = json.loads(resumo_limpo)
            print(f"[EXTRAÇÃO] Doc '{doc.categoria_nome}': JSON parseado com {len(dados_doc)} campos")
            
            if not isinstance(dados_doc, dict):
                continue
            
            # Consolida cada variável do documento
            for slug, valor in dados_doc.items():
                if slug.startswith('_'):  # Ignora campos internos/metadata
                    continue
                    
                if slug not in dados_consolidados:
                    # Primeira ocorrência
                    dados_consolidados[slug] = valor
                else:
                    # Consolidação
                    valor_existente = dados_consolidados[slug]
                    
                    # Booleanos: lógica OR
                    if isinstance(valor, bool) and isinstance(valor_existente, bool):
                        dados_consolidados[slug] = valor_existente or valor
                    # Listas: concatena valores únicos
                    elif isinstance(valor, list):
                        if isinstance(valor_existente, list):
                            for v in valor:
                                if v not in valor_existente:
                                    valor_existente.append(v)
                        else:
                            dados_consolidados[slug] = [valor_existente] + valor
                    # Outros: mantém lista de valores
                    elif valor != valor_existente:
                        if isinstance(valor_existente, list):
                            if valor not in valor_existente:
                                valor_existente.append(valor)
                        else:
                            dados_consolidados[slug] = [valor_existente, valor]
                            
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            # Resumo não é JSON válido, ignora
            print(f"[EXTRAÇÃO] Doc '{doc.categoria_nome}': erro ao parsear JSON - {type(e).__name__}: {str(e)[:100]}")
            continue

    if dados_consolidados:
        print(f"[EXTRAÇÃO] Variáveis extraídas dos resumos JSON: {len(dados_consolidados)}")
        # Log de algumas variáveis para debug
        for slug, valor in list(dados_consolidados.items())[:5]:
            print(f"   - {slug}: {valor}")
        if len(dados_consolidados) > 5:
            print(f"   ... e mais {len(dados_consolidados) - 5} variáveis")
    else:
        print("[EXTRAÇÃO] AVISO: Nenhuma variável extraída dos resumos JSON!")

    return dados_consolidados


MODELO_AGENTE2_PADRAO = "gemini-3-flash-preview"
MODELO_AGENTE3_PADRAO = "gemini-3-pro-preview"

# Ordem padrão das categorias jurídicas (fallback quando não há configuração no banco)
# Ordem lógica para peças de defesa: Preliminar → Mérito → Eventualidade → Honorários
ORDEM_CATEGORIAS_PADRAO = {
    "Preliminar": 0,
    "Mérito": 1,
    "Merito": 1,  # Variante sem acento
    "Eventualidade": 2,
    "honorarios": 3,
    "Honorários": 3,  # Variante com acento
    "Honorarios": 3,  # Variante sem acento
    "Sem Categoria": 99,
    "Outros": 100,
}

# NOTA: Templates de Formatação (TemplateFormatacao) foram removidos do prompt da IA.
# Agora a peça é gerada diretamente em Markdown.
# Os templates serão usados futuramente para conversão MD -> DOCX.


@dataclass
class ResultadoAgente2:
    """Resultado do Agente 2 (Detector de Módulos)"""
    modulos_ids: List[int] = field(default_factory=list)
    prompt_sistema: str = ""
    prompt_peca: str = ""
    prompt_conteudo: str = ""
    justificativa: str = ""
    confianca: str = "media"
    erro: Optional[str] = None
    # Modo de ativação: 'fast_path', 'misto', 'llm'
    modo_ativacao: str = "llm"
    modulos_ativados_det: int = 0  # Quantidade ativados por regra determinística
    modulos_ativados_llm: int = 0  # Quantidade ativados por LLM
    # IDs separados por método de ativação
    ids_det: List[int] = field(default_factory=list)  # IDs ativados deterministicamente
    ids_llm: List[int] = field(default_factory=list)  # IDs ativados por LLM


@dataclass
class ResultadoAgente3:
    """Resultado do Agente 3 (Gerador de Peça)"""
    tipo_peca: str = ""
    conteudo_markdown: str = ""  # Peça gerada diretamente em Markdown
    prompt_enviado: str = ""  # Prompt completo enviado à IA (para auditoria)
    tokens_usados: int = 0
    erro: Optional[str] = None


@dataclass
class ResultadoOrquestracao:
    """Resultado completo da orquestração dos 3 agentes"""
    numero_processo: str
    status: str = "processando"  # processando, sucesso, erro, pergunta
    
    # Resultados de cada agente
    agente1: Optional[ResultadoAgente1] = None
    agente2: Optional[ResultadoAgente2] = None
    agente3: Optional[ResultadoAgente3] = None
    
    # Para UI
    pergunta: Optional[str] = None
    opcoes: Optional[List[str]] = None
    mensagem: Optional[str] = None
    
    # Resultado final
    tipo_peca: Optional[str] = None
    conteudo_markdown: Optional[str] = None  # Peça em Markdown
    url_download: Optional[str] = None
    geracao_id: Optional[int] = None
    
    # Tempos de execução
    tempo_agente1: float = 0.0
    tempo_agente2: float = 0.0
    tempo_agente3: float = 0.0
    tempo_total: float = 0.0


class OrquestradorAgentes:
    """
    Orquestrador que coordena os 3 agentes do fluxo de geração de peças.
    """
    
    def __init__(
        self,
        db: Session,
        modelo_geracao: str = None,
        tipo_peca: str = None,  # Tipo de peça para filtrar categorias
        group_id: Optional[int] = None,
        subcategoria_ids: Optional[List[int]] = None
    ):
        """
        Args:
            db: Sessão do banco de dados
            modelo_geracao: Modelo para o Agente 3 (override manual, opcional)
            tipo_peca: Tipo de peça para filtrar categorias de documentos (opcional)
            group_id: Grupo principal de prompts modulares (opcional)
            subcategoria_ids: Subgrupos selecionados para filtrar prompts modulares (opcional)
        """
        self.db = db
        self.tipo_peca_inicial = tipo_peca
        self.group_id = group_id
        self.subcategoria_ids = subcategoria_ids or []
        
        # Carrega configurações do banco (tabela configuracoes_ia) ou usa padrões
        def get_config(chave: str, padrao: str) -> str:
            config = db.query(ConfiguracaoIA).filter(
                ConfiguracaoIA.sistema == "gerador_pecas",
                ConfiguracaoIA.chave == chave
            ).first()
            return config.valor if config else padrao
        
        self.modelo_agente1 = get_config("modelo_agente1", MODELO_AGENTE1_PADRAO)
        self.modelo_agente2 = get_config("modelo_deteccao", MODELO_AGENTE2_PADRAO)
        self.modelo_agente3 = modelo_geracao or get_config("modelo_geracao", MODELO_AGENTE3_PADRAO)

        # Temperatura do Agente 3 (configurável via admin)
        temp_str = get_config("temperatura_geracao", "0.3")
        try:
            self.temperatura_agente3 = float(temp_str)
        except ValueError:
            self.temperatura_agente3 = 0.3

        # Mantém compatibilidade
        self.modelo_geracao = self.modelo_agente3
        
        # Carrega filtro de categorias (se configurado no banco)
        self._filtro_categorias = None
        codigos_permitidos, codigos_primeiro_doc = self._obter_codigos_permitidos(tipo_peca)
        
        # Inicializa agentes com modelos configurados
        # O Agente 1 recebe a sessão do banco para buscar formatos JSON
        self.agente1 = AgenteTJMSIntegrado(
            modelo=self.modelo_agente1,
            db_session=db,
            formato_saida="json",  # Usa formato JSON para resumos
            codigos_permitidos=codigos_permitidos,
            codigos_primeiro_doc=codigos_primeiro_doc
        )
        self.agente2 = DetectorModulosIA(db=db, modelo=self.modelo_agente2)
    
    def _obter_filtro_categorias(self):
        """Obtém ou cria o filtro de categorias (lazy loading)"""
        if self._filtro_categorias is None:
            try:
                from sistemas.gerador_pecas.filtro_categorias import FiltroCategoriasDocumento
                self._filtro_categorias = FiltroCategoriasDocumento(self.db)
            except Exception as e:
                print(f"[AVISO] Filtro de categorias não disponível: {e}")
                return None
        return self._filtro_categorias
    
    def _obter_codigos_permitidos(self, tipo_peca: str = None) -> tuple:
        """
        Obtém os códigos de documento permitidos para o tipo de peça.
        
        Args:
            tipo_peca: Tipo de peça (ex: 'contestacao'). Se None, retorna None (modo legado).
            
        Returns:
            Tupla (codigos_permitidos, codigos_primeiro_doc), ou (None, set()) para usar filtro legado.
        """
        filtro = self._obter_filtro_categorias()
        
        if filtro is None or not filtro.tem_configuracao():
            # Sem configuração no banco, usa filtro legado
            return None, set()
        
        if tipo_peca:
            # Modo manual: usa categorias do tipo de peça específico
            codigos = filtro.get_codigos_permitidos(tipo_peca)
            codigos_primeiro = filtro.get_codigos_primeiro_documento(tipo_peca)
            if codigos:
                print(f"[CONFIG] Usando {len(codigos)} códigos de documento para '{tipo_peca}'")
                if codigos_primeiro:
                    print(f"[CONFIG] {len(codigos_primeiro)} códigos com filtro 'primeiro documento' (ex: Petição Inicial)")
                return codigos, codigos_primeiro
        
        # Modo automático ou tipo não encontrado: usa todos os códigos configurados
        codigos = filtro.get_todos_codigos()
        if codigos:
            print(f"[CONFIG] Modo automático: usando {len(codigos)} códigos de documento")
            return codigos, set()  # No modo automático, não aplica filtro de primeiro documento
        
        return None, set()
    
    async def processar_processo(
        self,
        numero_processo: str,
        tipo_peca: Optional[str] = None
    ) -> ResultadoOrquestracao:
        """
        Processa um processo executando os 3 agentes em sequência.
        
        Args:
            numero_processo: Número CNJ do processo
            tipo_peca: Tipo de peça (se já conhecido). Se None, o Agente 2 detecta automaticamente.
            
        Returns:
            ResultadoOrquestracao com o resultado completo
        """
        resultado = ResultadoOrquestracao(numero_processo=numero_processo)
        inicio_total = datetime.now()
        
        # Determina se é modo manual ou automático
        modo_automatico = tipo_peca is None
        
        try:
            # ========================================
            # AGENTE 1: Coletor TJ-MS
            # ========================================
            print("\n" + "=" * 60)
            print("[AGENTE 1] COLETOR TJ-MS")
            print("=" * 60)
            
            # Se modo manual, atualiza os códigos permitidos para o tipo específico
            if not modo_automatico:
                codigos, codigos_primeiro = self._obter_codigos_permitidos(tipo_peca)
                if codigos:
                    self.agente1.atualizar_codigos_permitidos(codigos, codigos_primeiro)
            
            inicio = datetime.now()
            resultado.agente1 = await self.agente1.coletar_e_resumir(numero_processo)
            resultado.tempo_agente1 = (datetime.now() - inicio).total_seconds()
            
            if resultado.agente1.erro:
                resultado.status = "erro"
                resultado.mensagem = resultado.agente1.erro
                return resultado
            
            resumo_consolidado = resultado.agente1.resumo_consolidado
            print(f"   Tempo Agente 1: {resultado.tempo_agente1:.1f}s")
            
            # ========================================
            # AGENTE 2: Detector de Módulos (e tipo de peça se necessário)
            # ========================================
            print("\n" + "=" * 60)
            print("[AGENTE 2] DETECTOR DE MODULOS")
            print("=" * 60)
            
            inicio = datetime.now()
            
            # Se não tem tipo de peça, o Agente 2 detecta automaticamente
            if modo_automatico:
                print("   Detectando tipo de peca automaticamente...")
                deteccao_tipo = await self.agente2.detectar_tipo_peca(resumo_consolidado)
                tipo_peca = deteccao_tipo.get("tipo_peca")
                
                if tipo_peca:
                    print(f"[OK] Tipo de peca detectado: {tipo_peca}")
                    print(f"   Justificativa: {deteccao_tipo.get('justificativa', 'N/A')}")
                    print(f"   Confiança: {deteccao_tipo.get('confianca', 'N/A')}")
                    
                    # Filtra resumos para o tipo de peça detectado
                    resumo_consolidado = self._filtrar_resumo_por_tipo(
                        resultado.agente1, 
                        tipo_peca
                    )
                else:
                    # Se mesmo assim não conseguiu detectar, usa fallback
                    print("[WARN] Nao foi possivel detectar o tipo de peca automaticamente")
                    tipo_peca = "contestacao"  # Fallback padrão
                    print(f"   Usando fallback: {tipo_peca}")
            
            # Extrai dados_processo para passar ao Agente 2
            dados_processo = None
            if resultado.agente1.dados_brutos and resultado.agente1.dados_brutos.dados_processo:
                dados_processo = resultado.agente1.dados_brutos.dados_processo

            # Consolida dados extraídos dos resumos JSON para avaliação determinística
            dados_extracao = consolidar_dados_extracao(resultado.agente1)

            resultado.agente2 = await self._executar_agente2(
                resumo_consolidado,
                tipo_peca,
                dados_processo=dados_processo,
                dados_extracao=dados_extracao
            )
            resultado.tempo_agente2 = (datetime.now() - inicio).total_seconds()
            
            if resultado.agente2.erro:
                resultado.status = "erro"
                resultado.mensagem = resultado.agente2.erro
                return resultado
            
            print(f"   Tempo Agente 2: {resultado.tempo_agente2:.1f}s")
            
            # ========================================
            # AGENTE 3: Gerador de Peça (Gemini 3 Pro)
            # ========================================
            print("\n" + "=" * 60)
            print("[AGENTE 3] GERADOR (Gemini 3 Pro)")
            print("=" * 60)
            
            inicio = datetime.now()

            # Extrai dados estruturados do processo (se disponíveis)
            dados_processo_json = None
            if resultado.agente1.dados_brutos and resultado.agente1.dados_brutos.dados_processo:
                dados_processo_json = resultado.agente1.dados_brutos.dados_processo.to_json()

            resultado.agente3 = await self._executar_agente3(
                resumo_consolidado=resumo_consolidado,
                prompt_sistema=resultado.agente2.prompt_sistema,
                prompt_peca=resultado.agente2.prompt_peca,
                prompt_conteudo=resultado.agente2.prompt_conteudo,
                tipo_peca=tipo_peca,
                dados_processo=dados_processo_json
            )
            resultado.tempo_agente3 = (datetime.now() - inicio).total_seconds()
            
            if resultado.agente3.erro:
                resultado.status = "erro"
                resultado.mensagem = resultado.agente3.erro
                return resultado
            
            print(f"   Tempo Agente 3: {resultado.tempo_agente3:.1f}s")
            
            # Sucesso!
            resultado.status = "sucesso"
            resultado.tipo_peca = tipo_peca
            resultado.conteudo_markdown = resultado.agente3.conteudo_markdown
            
            resultado.tempo_total = (datetime.now() - inicio_total).total_seconds()
            
            print("\n" + "=" * 60)
            print("[OK] ORQUESTRACAO CONCLUIDA")
            print(f"   Tempo Total: {resultado.tempo_total:.1f}s")
            print("=" * 60)
            
            return resultado
            
        except Exception as e:
            resultado.status = "erro"
            resultado.mensagem = f"Erro na orquestração: {str(e)}"
            print(f"[ERRO] {resultado.mensagem}")
            return resultado
    
    def _filtrar_resumo_por_tipo(
        self,
        resultado_agente1: ResultadoAgente1,
        tipo_peca: str
    ) -> str:
        """
        Filtra o resumo consolidado para incluir apenas documentos 
        das categorias permitidas para o tipo de peça.
        
        Usado no modo automático após a detecção do tipo de peça.
        
        Args:
            resultado_agente1: Resultado do Agente 1 com dados brutos
            tipo_peca: Tipo de peça detectado
            
        Returns:
            Resumo consolidado filtrado
        """
        filtro = self._obter_filtro_categorias()
        
        if filtro is None or not filtro.tem_configuracao():
            # Sem filtro configurado, retorna resumo original
            return resultado_agente1.resumo_consolidado
        
        codigos_permitidos = filtro.get_codigos_permitidos(tipo_peca)
        if not codigos_permitidos:
            # Tipo de peça não encontrado, retorna resumo original
            return resultado_agente1.resumo_consolidado
        
        # Se temos acesso aos dados brutos, podemos refazer o resumo
        if resultado_agente1.dados_brutos:
            from sistemas.gerador_pecas.agente_tjms_integrado import AgenteTJMSIntegrado
            
            # Filtra documentos pelos códigos permitidos
            docs_originais = resultado_agente1.dados_brutos.documentos
            docs_filtrados = [
                doc for doc in docs_originais
                if doc.tipo_documento and int(doc.tipo_documento) in codigos_permitidos
                and doc.resumo and not doc.irrelevante
            ]
            
            if len(docs_filtrados) < len(resultado_agente1.dados_brutos.documentos_com_resumo()):
                print(f"   Filtrado: {len(docs_filtrados)} de {len(resultado_agente1.dados_brutos.documentos_com_resumo())} documentos para '{tipo_peca}'")
                
                # Remonta o resumo com os documentos filtrados
                # Por ora, retorna o resumo original com uma nota
                # TODO: Implementar remontagem do resumo consolidado
                nota_filtro = f"\n\n> **NOTA**: Resumos filtrados para tipo de peça '{tipo_peca}'. "
                nota_filtro += f"{len(docs_filtrados)} de {resultado_agente1.dados_brutos.documentos_analisados()} documentos considerados.\n\n"
                
                return resultado_agente1.resumo_consolidado
        
        return resultado_agente1.resumo_consolidado
    
    async def _executar_agente2(
        self,
        resumo_consolidado: str,
        tipo_peca: Optional[str] = None,
        dados_processo: Optional[Any] = None,
        dados_extracao: Optional[Dict[str, Any]] = None
    ) -> ResultadoAgente2:
        """
        Executa o Agente 2 - Detector de Módulos

        Analisa o resumo e monta os prompts modulares.
        Usa variáveis derivadas do processo para avaliação determinística.

        Args:
            resumo_consolidado: Resumo dos documentos
            tipo_peca: Tipo de peça para filtrar módulos
            dados_processo: DadosProcesso extraídos do XML (opcional)
            dados_extracao: Variáveis extraídas dos resumos JSON (opcional)
        """
        resultado = ResultadoAgente2()

        try:
            # Detecta módulos de conteúdo relevantes
            # Passa dados_processo para resolução de variáveis derivadas
            # Passa dados_extracao para avaliação determinística
            # Permite fast path se todos os módulos são determinísticos
            modulos_ids = await self.agente2.detectar_modulos_relevantes(
                documentos_resumo=resumo_consolidado,
                tipo_peca=tipo_peca,
                group_id=self.group_id,
                subcategoria_ids=self.subcategoria_ids,
                dados_processo=dados_processo,
                dados_extracao=dados_extracao
            )
            resultado.modulos_ids = modulos_ids
            
            # Captura estatísticas do modo de ativação
            resultado.modo_ativacao = self.agente2.ultimo_modo_ativacao
            resultado.modulos_ativados_det = self.agente2.ultimo_modulos_det
            resultado.modulos_ativados_llm = self.agente2.ultimo_modulos_llm
            resultado.ids_det = self.agente2.ultimo_ids_det.copy()
            resultado.ids_llm = self.agente2.ultimo_ids_llm.copy()

            # Carrega módulos BASE (sempre ativos)
            modulos_base = self.db.query(PromptModulo).filter(
                PromptModulo.tipo == "base",
                PromptModulo.ativo == True
            ).order_by(PromptModulo.ordem).all()
            
            # Monta prompt do sistema
            partes_sistema = []
            for modulo in modulos_base:
                partes_sistema.append(f"## {modulo.titulo}\n\n{modulo.conteudo}")
            resultado.prompt_sistema = "\n\n".join(partes_sistema)
            
            # Carrega módulo de PEÇA (se tipo especificado)
            if tipo_peca:
                modulo_peca = self.db.query(PromptModulo).filter(
                    PromptModulo.tipo == "peca",
                    PromptModulo.nome == tipo_peca,  # Busca por nome (identificador único)
                    PromptModulo.ativo == True
                ).first()

                if modulo_peca:
                    resultado.prompt_peca = f"## ESTRUTURA DA PEÇA: {modulo_peca.titulo}\n\n{modulo_peca.conteudo}"
            
            # Carrega módulos de CONTEÚDO detectados
            if modulos_ids:
                modulos_query = self.db.query(PromptModulo).filter(
                    PromptModulo.tipo == "conteudo",
                    PromptModulo.ativo == True,
                    PromptModulo.id.in_(modulos_ids)
                )

                if self.group_id is not None:
                    modulos_query = modulos_query.filter(PromptModulo.group_id == self.group_id)

                if self.subcategoria_ids:
                    # Filtra módulos que:
                    # 1. Pertencem a pelo menos uma das subcategorias selecionadas, OU
                    # 2. Não têm nenhuma subcategoria associada (são "universais" - sempre elegíveis)
                    from admin.models_prompt_groups import PromptSubcategoria
                    from sqlalchemy import or_
                    modulos_query = modulos_query.filter(
                        or_(
                            PromptModulo.subcategorias.any(PromptSubcategoria.id.in_(self.subcategoria_ids)),
                            ~PromptModulo.subcategorias.any()
                        )
                    )

                modulos_conteudo = modulos_query.order_by(PromptModulo.categoria, PromptModulo.ordem).all()

                if modulos_conteudo:
                    # Busca ordem das categorias configurada
                    from admin.models_prompt_groups import CategoriaOrdem
                    ordem_categorias = {}
                    group_id_ordem = self.group_id
                    if group_id_ordem is None:
                        group_ids = {m.group_id for m in modulos_conteudo if m.group_id is not None}
                        if len(group_ids) == 1:
                            group_id_ordem = next(iter(group_ids))

                    if group_id_ordem is not None:
                        configs_ordem = self.db.query(CategoriaOrdem).filter(
                            CategoriaOrdem.group_id == group_id_ordem,
                            CategoriaOrdem.ativo == True
                        ).all()
                        ordem_categorias = {c.nome: c.ordem for c in configs_ordem}

# Agrupa módulos por categoria
                    modulos_por_categoria = {}
                    for modulo in modulos_conteudo:
                        cat = modulo.categoria or "Outros"
                        if cat not in modulos_por_categoria:
                            modulos_por_categoria[cat] = []
                        modulos_por_categoria[cat].append(modulo)

                    # Ordena categorias usando:
                    # 1. Configuração do banco (se existir)
                    # 2. Ordem padrão jurídica (Preliminar > Mérito > Eventualidade > Honorários)
                    # 3. Alfabético como último fallback
                    def get_categoria_ordem(cat_nome):
                        # Prioridade 1: Configuração explícita do banco
                        if cat_nome in ordem_categorias:
                            return (0, ordem_categorias[cat_nome], cat_nome)
                        # Prioridade 2: Ordem padrão jurídica (fallback)
                        if cat_nome in ORDEM_CATEGORIAS_PADRAO:
                            return (1, ORDEM_CATEGORIAS_PADRAO[cat_nome], cat_nome)
                        # Prioridade 3: Categorias desconhecidas vão para o final, ordenadas alfabeticamente
                        return (2, 0, cat_nome)

                    categorias_ordenadas = sorted(modulos_por_categoria.keys(), key=get_categoria_ordem)

                    # Log para debug da ordem das categorias
                    print(f"   [ORDEM] Categorias ordenadas: {categorias_ordenadas}")
                    if ordem_categorias:
                        print(f"   [ORDEM] Usando configuração do banco: {ordem_categorias}")
                    else:
                        print(f"   [ORDEM] Usando ordem padrão (fallback): ORDEM_CATEGORIAS_PADRAO")

                    # Monta prompt agrupado por categoria com headers
                    partes_conteudo = ["## ARGUMENTOS E TESES APLICÁVEIS\n"]

                    for categoria in categorias_ordenadas:
                        modulos_cat = sorted(modulos_por_categoria[categoria], key=lambda m: (m.ordem or 0, m.id))

                        # Header da seção de categoria
                        partes_conteudo.append(f"\n### === {categoria.upper()} ===\n")

                        # Módulos desta categoria
                        for modulo in modulos_cat:
                            # Inclui subcategoria se houver
                            subcategoria_info = ""
                            if modulo.subcategoria:
                                subcategoria_info = f" ({modulo.subcategoria})"

                            # Verifica se foi ativado deterministicamente ou por LLM
                            is_deterministico = modulo.id in resultado.ids_det

                            if is_deterministico:
                                # Módulos determinísticos: NÃO inclui condição (já foi validado)
                                # Marca como [VALIDADO] para a IA saber que DEVE usar
                                partes_conteudo.append(f"#### {modulo.titulo}{subcategoria_info} [VALIDADO]\n\n{modulo.conteudo}\n")
                                print(f"   [+] Modulo ativado: [{categoria}] {modulo.titulo} [DET-VALIDADO]")
                            else:
                                # Módulos LLM: inclui condição para avaliação crítica
                                condicao = modulo.condicao_ativacao or ""
                                if condicao:
                                    partes_conteudo.append(f"#### {modulo.titulo}{subcategoria_info}\n\n**Condição de ativação:** {condicao}\n\n{modulo.conteudo}\n")
                                else:
                                    partes_conteudo.append(f"#### {modulo.titulo}{subcategoria_info}\n\n{modulo.conteudo}\n")
                                print(f"   [+] Modulo ativado: [{categoria}] {modulo.titulo} [LLM]")

                    resultado.prompt_conteudo = "\n".join(partes_conteudo)

            print(f"   Modulos detectados: {len(modulos_ids)}")
            print(f"   Prompt sistema: {len(resultado.prompt_sistema)} chars")
            print(f"   Prompt peca: {len(resultado.prompt_peca)} chars")
            print(f"   Prompt conteudo: {len(resultado.prompt_conteudo)} chars")
            
            return resultado
            
        except Exception as e:
            resultado.erro = f"Erro no Agente 2: {str(e)}"
            return resultado
    
    async def _executar_agente3(
        self,
        resumo_consolidado: str,
        prompt_sistema: str,
        prompt_peca: str,
        prompt_conteudo: str,
        tipo_peca: str,
        observacao_usuario: Optional[str] = None,
        dados_processo: Optional[Dict[str, Any]] = None
    ) -> ResultadoAgente3:
        """
        Executa o Agente 3 - Gerador de Peça (Gemini 3 Pro)

        Recebe:
        - Resumo consolidado (do Agente 1)
        - Prompts modulares (do Agente 2)
        - Observação do usuário (opcional)

        Gera a peça jurídica final.
        """
        resultado = ResultadoAgente3(tipo_peca=tipo_peca)
        
        try:
            # NOTA: Templates de Formatação (TemplateFormatacao) NÃO são mais enviados para a IA.
            # A peça é gerada diretamente em Markdown, usando o prompt_peca como guia de estrutura.
            # Os templates serão usados futuramente para conversão MD -> DOCX.
            
            # Monta seção de observação do usuário (se houver)
            secao_observacao = ""
            if observacao_usuario:
                secao_observacao = f"""
---

## OBSERVAÇÕES DO USUÁRIO:

O usuário responsável pela peça forneceu as seguintes observações importantes que DEVEM ser consideradas na elaboração:

> {observacao_usuario}

**ATENÇÃO:** As observações acima são instruções específicas do usuário e devem ser incorporadas na peça conforme solicitado.

"""
                print(f" Observação do usuário incluída: {len(observacao_usuario)} caracteres")

            # Monta seção de dados estruturados do processo (se disponíveis)
            secao_dados_processo = ""
            if dados_processo:
                dados_json = json.dumps(dados_processo, indent=2, ensure_ascii=False)
                secao_dados_processo = f"""
---

## DADOS ESTRUTURADOS DO PROCESSO

Os dados abaixo foram extraídos automaticamente do sistema judicial e são confiáveis:

```json
{dados_json}
```

**IMPORTANTE:** Utilize estes dados para:
- Identificar corretamente as partes (polo ativo e polo passivo)
- Verificar a data de ajuizamento da demanda
- Consultar o valor da causa
- Identificar o órgão julgador
- Verificar representação processual (advogados, defensoria, etc.)

"""
                print(f" Dados do processo incluídos: {len(dados_json)} caracteres")

            # Monta o prompt final combinando tudo (SEM template JSON)
            prompt_completo = f"""{prompt_sistema}

{prompt_peca}

{prompt_conteudo}
{secao_observacao}{secao_dados_processo}
---

## DOCUMENTOS DO PROCESSO PARA ANÁLISE:

{resumo_consolidado}

---

## INSTRUÇÕES FINAIS:

Com base nos documentos acima e nas instruções do sistema, gere a peça jurídica completa.

**REGRAS OBRIGATÓRIAS sobre os Argumentos e Teses:**

1. **Argumentos marcados com [VALIDADO]**: DEVEM ser incluídos na peça SEM QUESTIONAMENTO. Estes argumentos já foram validados automaticamente com base nas variáveis extraídas dos documentos. NÃO os omita.

2. **Argumentos com "Condição de ativação"**: Avalie criticamente se a condição se aplica aos fatos. Se NÃO corresponder, NÃO inclua.

3. **Seções vazias**: Se uma categoria (ex: PRELIMINARES) não tiver NENHUM argumento listado acima, NÃO crie essa seção na peça. Só inclua seções que tenham argumentos ativados.

4. **Ordem**: Respeite a ordem das categorias e argumentos como apresentada em "ARGUMENTOS E TESES APLICÁVEIS".

Retorne a peça formatada em **Markdown**, seguindo a estrutura indicada no prompt de peça acima.
Use formatação adequada: ## para títulos de seção, **negrito** para ênfase, > para citações.
"""
            
            # Salva o prompt para auditoria
            resultado.prompt_enviado = prompt_completo
            
            print(f" Prompt montado: {len(prompt_completo)} caracteres (SEM template JSON)")

            # Chama a API do Gemini diretamente
            content = await chamar_gemini_async(
                prompt=prompt_completo,
                modelo=self.modelo_geracao,
                max_tokens=16000,
                temperature=self.temperatura_agente3
            )
            
            # Remove possíveis blocos de código markdown que a IA pode ter adicionado
            content_limpo = content.strip()
            if content_limpo.startswith('```markdown'):
                content_limpo = content_limpo[11:]
            elif content_limpo.startswith('```'):
                content_limpo = content_limpo[3:]
            if content_limpo.endswith('```'):
                content_limpo = content_limpo[:-3]
            
            resultado.conteudo_markdown = content_limpo.strip()

            print("[OK] Peca gerada com sucesso em Markdown!")
            print(f"📄 Tamanho da peça: {len(resultado.conteudo_markdown)} caracteres")
            
            return resultado
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            resultado.erro = f"Erro no Agente 3: {str(e)}"
            return resultado


async def processar_com_agentes(
    db: Session,
    numero_processo: str,
    tipo_peca: Optional[str] = None
) -> ResultadoOrquestracao:
    """
    Função de conveniência para processar um processo com os 3 agentes.
    """
    orquestrador = OrquestradorAgentes(db=db)
    return await orquestrador.processar_processo(numero_processo, tipo_peca)
