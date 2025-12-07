# sistemas/gerador_pecas/orquestrador_agentes.py
"""
Orquestrador de Agentes para Geração de Peças Jurídicas

Coordena os 3 agentes do fluxo:
1. Agente 1 (Coletor): Baixa documentos do TJ-MS e gera resumo consolidado
2. Agente 2 (Detector): Analisa resumo e ativa prompts modulares relevantes
3. Agente 3 (Gerador): Gera a peça jurídica usando Gemini 3 Pro
"""

import os
import asyncio
import httpx
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from sistemas.gerador_pecas.agente_tjms_integrado import AgenteTJMSIntegrado, ResultadoAgente1
from sistemas.gerador_pecas.detector_modulos import DetectorModulosIA
# NOTA: TemplateFormatacao não é mais importado aqui - templates serão usados apenas para MD->DOCX
from admin.models import ConfiguracaoIA
from admin.models_prompts import PromptModulo


# Modelos padrão (usados se não houver configuração no banco)
MODELO_AGENTE1_PADRAO = "google/gemini-2.5-flash-lite"
MODELO_AGENTE2_PADRAO = "google/gemini-2.5-flash-lite"
MODELO_AGENTE3_PADRAO = "google/gemini-2.5-pro-preview-05-06"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

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
        modelo_geracao: str = None
    ):
        """
        Args:
            db: Sessão do banco de dados
            modelo_geracao: Modelo para o Agente 3 (override manual, opcional)
        """
        self.db = db
        self.api_key = os.getenv("OPENROUTER_API_KEY", "")
        
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
        
        # Mantém compatibilidade
        self.modelo_geracao = self.modelo_agente3
        
        # Inicializa agentes com modelos configurados
        # O Agente 1 recebe a sessão do banco para buscar formatos JSON
        self.agente1 = AgenteTJMSIntegrado(
            modelo=self.modelo_agente1,
            db_session=db,
            formato_saida="json"  # Usa formato JSON para resumos
        )
        self.agente2 = DetectorModulosIA(db=db, modelo=self.modelo_agente2)
    
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
        
        try:
            # ========================================
            # AGENTE 1: Coletor TJ-MS
            # ========================================
            print("\n" + "=" * 60)
            print("🤖 AGENTE 1 - COLETOR TJ-MS")
            print("=" * 60)
            
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
            if not tipo_peca:
                print("📋 Detectando tipo de peça automaticamente...")
                deteccao_tipo = await self.agente2.detectar_tipo_peca(resumo_consolidado)
                tipo_peca = deteccao_tipo.get("tipo_peca")
                
                if tipo_peca:
                    print(f"✅ Tipo de peça detectado: {tipo_peca}")
                    print(f"   Justificativa: {deteccao_tipo.get('justificativa', 'N/A')}")
                    print(f"   Confiança: {deteccao_tipo.get('confianca', 'N/A')}")
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
            resultado.agente3 = await self._executar_agente3(
                resumo_consolidado=resumo_consolidado,
                prompt_sistema=resultado.agente2.prompt_sistema,
                prompt_peca=resultado.agente2.prompt_peca,
                prompt_conteudo=resultado.agente2.prompt_conteudo,
                tipo_peca=tipo_peca
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
            print(f"✅ ORQUESTRAÇÃO CONCLUÍDA")
            print(f"⏱️  Tempo Total: {resultado.tempo_total:.1f}s")
            print("=" * 60)
            
            return resultado
            
        except Exception as e:
            resultado.status = "erro"
            resultado.mensagem = f"Erro na orquestração: {str(e)}"
            print(f"❌ Erro: {resultado.mensagem}")
            return resultado
    
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
            modulos_ids = await self.agente2.detectar_modulos_relevantes(
                documentos_resumo=resumo_consolidado
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
                modulos_conteudo = self.db.query(PromptModulo).filter(
                    PromptModulo.tipo == "conteudo",
                    PromptModulo.ativo == True,
                    PromptModulo.id.in_(modulos_ids)
                ).order_by(PromptModulo.ordem).all()
                
                if modulos_conteudo:
                    partes_conteudo = ["## ARGUMENTOS E TESES APLICÁVEIS\n"]
                    for modulo in modulos_conteudo:
                        partes_conteudo.append(f"### {modulo.titulo}\n{modulo.conteudo}\n")
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
        tipo_peca: str
    ) -> ResultadoAgente3:
        """
        Executa o Agente 3 - Gerador de Peça (Gemini 3 Pro)
        
        Recebe:
        - Resumo consolidado (do Agente 1)
        - Prompts modulares (do Agente 2)
        
        Gera a peça jurídica final.
        """
        resultado = ResultadoAgente3(tipo_peca=tipo_peca)
        
        try:
            # NOTA: Templates de Formatação (TemplateFormatacao) NÃO são mais enviados para a IA.
            # A peça é gerada diretamente em Markdown, usando o prompt_peca como guia de estrutura.
            # Os templates serão usados futuramente para conversão MD -> DOCX.
            
            # Monta o prompt final combinando tudo (SEM template JSON)
            prompt_completo = f"""{prompt_sistema}

{prompt_peca}

{prompt_conteudo}

---

## DOCUMENTOS DO PROCESSO PARA ANÁLISE:

{resumo_consolidado}

---

## INSTRUÇÕES FINAIS:

Com base nos documentos acima e nas instruções do sistema, gere a peça jurídica completa.

Retorne a peça formatada em **Markdown**, seguindo a estrutura indicada no prompt de peça acima.
Use formatação adequada: ## para títulos de seção, **negrito** para ênfase, > para citações.
"""
            
            # Salva o prompt para auditoria
            resultado.prompt_enviado = prompt_completo
            
            print(f"📝 Prompt montado: {len(prompt_completo)} caracteres (SEM template JSON)")

            # Chama a API do OpenRouter com Gemini 3 Pro
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    OPENROUTER_URL,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://pge-ms.gov.br",
                        "X-Title": "PGE-MS - Gerador de Pecas"
                    },
                    json={
                        "model": self.modelo_geracao,
                        "messages": [
                            {"role": "user", "content": prompt_completo}
                        ],
                        "temperature": 0.3,
                        "max_tokens": 16000
                    }
                )
                
                response.raise_for_status()
                data = response.json()
                
                content = data['choices'][0]['message']['content']
                
                # Remove possíveis blocos de código markdown que a IA pode ter adicionado
                content_limpo = content.strip()
                if content_limpo.startswith('```markdown'):
                    content_limpo = content_limpo[11:]
                elif content_limpo.startswith('```'):
                    content_limpo = content_limpo[3:]
                if content_limpo.endswith('```'):
                    content_limpo = content_limpo[:-3]
                
                resultado.conteudo_markdown = content_limpo.strip()
                
                # Contabiliza tokens
                if 'usage' in data:
                    resultado.tokens_usados = data['usage'].get('total_tokens', 0)
                
                print(f"✅ Peça gerada com sucesso em Markdown!")
                print(f"📊 Tokens usados: {resultado.tokens_usados}")
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
