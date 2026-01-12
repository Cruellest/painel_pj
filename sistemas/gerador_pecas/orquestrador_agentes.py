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
MODELO_AGENTE2_PADRAO = "gemini-3-flash-preview"
MODELO_AGENTE3_PADRAO = "gemini-3-pro-preview"

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
            print("🤖 AGENTE 1 - COLETOR TJ-MS")
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
            print(f"⏱️  Tempo Agente 1: {resultado.tempo_agente1:.1f}s")
            
            # ========================================
            # AGENTE 2: Detector de Módulos (e tipo de peça se necessário)
            # ========================================
            print("\n" + "=" * 60)
            print("🤖 AGENTE 2 - DETECTOR DE MÓDULOS")
            print("=" * 60)
            
            inicio = datetime.now()
            
            # Se não tem tipo de peça, o Agente 2 detecta automaticamente
            if modo_automatico:
                print("📋 Detectando tipo de peça automaticamente...")
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
                    print("⚠️ Não foi possível detectar o tipo de peça automaticamente")
                    tipo_peca = "contestacao"  # Fallback padrão
                    print(f"   Usando fallback: {tipo_peca}")
            
            resultado.agente2 = await self._executar_agente2(resumo_consolidado, tipo_peca)
            resultado.tempo_agente2 = (datetime.now() - inicio).total_seconds()
            
            if resultado.agente2.erro:
                resultado.status = "erro"
                resultado.mensagem = resultado.agente2.erro
                return resultado
            
            print(f"⏱️  Tempo Agente 2: {resultado.tempo_agente2:.1f}s")
            
            # ========================================
            # AGENTE 3: Gerador de Peça (Gemini 3 Pro)
            # ========================================
            print("\n" + "=" * 60)
            print("🤖 AGENTE 3 - GERADOR (Gemini 3 Pro)")
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
            
            print(f"⏱️  Tempo Agente 3: {resultado.tempo_agente3:.1f}s")
            
            # Sucesso!
            resultado.status = "sucesso"
            resultado.tipo_peca = tipo_peca
            resultado.conteudo_markdown = resultado.agente3.conteudo_markdown
            
            resultado.tempo_total = (datetime.now() - inicio_total).total_seconds()
            
            print("\n" + "=" * 60)
            print("[OK] ORQUESTRACAO CONCLUIDA")
            print(f"⏱️  Tempo Total: {resultado.tempo_total:.1f}s")
            print("=" * 60)
            
            return resultado
            
        except Exception as e:
            resultado.status = "erro"
            resultado.mensagem = f"Erro na orquestração: {str(e)}"
            print(f"❌ Erro: {resultado.mensagem}")
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
                print(f"   📋 Filtrado: {len(docs_filtrados)} de {len(resultado_agente1.dados_brutos.documentos_com_resumo())} documentos para '{tipo_peca}'")
                
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
        tipo_peca: Optional[str] = None
    ) -> ResultadoAgente2:
        """
        Executa o Agente 2 - Detector de Módulos
        
        Analisa o resumo e monta os prompts modulares.
        """
        resultado = ResultadoAgente2()
        
        try:
            # Detecta módulos de conteúdo relevantes via IA
            # Passa tipo_peca para filtrar módulos disponíveis
            modulos_ids = await self.agente2.detectar_modulos_relevantes(
                documentos_resumo=resumo_consolidado,
                tipo_peca=tipo_peca,
                group_id=self.group_id,
                subcategoria_ids=self.subcategoria_ids
            )
            resultado.modulos_ids = modulos_ids
            
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
                    PromptModulo.categoria == tipo_peca,
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
                    from admin.models_prompt_groups import PromptSubcategoria
                    modulos_query = modulos_query.filter(
                        PromptModulo.subcategorias.any(PromptSubcategoria.id.in_(self.subcategoria_ids))
                    )

                modulos_conteudo = modulos_query.order_by(PromptModulo.categoria, PromptModulo.ordem).all()
                
                if modulos_conteudo:
                    partes_conteudo = ["## ARGUMENTOS E TESES APLICÁVEIS\n"]
                    for modulo in modulos_conteudo:
                        # Monta cabeçalho com categoria e subcategoria
                        categoria_info = ""
                        if modulo.categoria:
                            categoria_info = f"[{modulo.categoria}"
                            if modulo.subcategoria:
                                categoria_info += f" > {modulo.subcategoria}"
                            categoria_info += "] "
                        
                        # Inclui a condição de ativação para que o Agente 3 possa fazer juízo crítico
                        condicao = modulo.condicao_ativacao or ""
                        if condicao:
                            partes_conteudo.append(f"### {categoria_info}{modulo.titulo}\n\n**Condição de ativação:** {condicao}\n\n{modulo.conteudo}\n")
                        else:
                            partes_conteudo.append(f"### {categoria_info}{modulo.titulo}\n\n{modulo.conteudo}\n")
                        print(f"   ✓ Módulo ativado: {modulo.titulo}")
                    resultado.prompt_conteudo = "\n".join(partes_conteudo)
            
            print(f"📋 Módulos detectados: {len(modulos_ids)}")
            print(f"📝 Prompt sistema: {len(resultado.prompt_sistema)} chars")
            print(f"📝 Prompt peça: {len(resultado.prompt_peca)} chars")
            print(f"📝 Prompt conteúdo: {len(resultado.prompt_conteudo)} chars")
            
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
                print(f"📝 Observação do usuário incluída: {len(observacao_usuario)} caracteres")

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
                print(f"📝 Dados do processo incluídos: {len(dados_json)} caracteres")

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

**IMPORTANTE sobre os Argumentos e Teses Aplicáveis:**
Cada argumento/tese acima possui uma "Condição de ativação" que indica em qual situação fática ele deve ser utilizado.
Antes de incorporar cada argumento na peça, avalie criticamente se a condição de ativação realmente se aplica aos fatos do caso concreto.
Se a condição NÃO corresponder aos fatos, NÃO inclua esse argumento na peça.

Retorne a peça formatada em **Markdown**, seguindo a estrutura indicada no prompt de peça acima.
Use formatação adequada: ## para títulos de seção, **negrito** para ênfase, > para citações.
"""
            
            # Salva o prompt para auditoria
            resultado.prompt_enviado = prompt_completo
            
            print(f"📝 Prompt montado: {len(prompt_completo)} caracteres (SEM template JSON)")

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
