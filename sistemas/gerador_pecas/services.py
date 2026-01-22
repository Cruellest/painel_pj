# sistemas/gerador_pecas/services.py
"""
Serviços do sistema Gerador de Peças Jurídicas
Utiliza prompts modulares: BASE + PEÇA + CONTEÚDO

Fluxo com 3 agentes:
1. Agente TJ-MS: Baixa documentos e gera resumo consolidado
2. Agente Detector: Analisa resumo e ativa módulos relevantes
3. Agente Gerador (Gemini 3 Pro): Gera a peça final
"""

import os
import json
import uuid
import httpx
import re
from typing import Dict, List, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from docx import Document
from docx.shared import Pt, Inches, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH

from sistemas.gerador_pecas.models import GeracaoPeca
from admin.models_prompts import PromptModulo
from admin.models import ConfiguracaoIA
from admin.models_prompt_groups import CategoriaOrdem
from sistemas.gerador_pecas.detector_modulos import DetectorModulosIA

# Flag para indicar se o orquestrador está disponível (será verificado na primeira chamada)
ORQUESTRADOR_DISPONIVEL = None  # None = não verificado ainda
_OrquestradorAgentes = None  # Cache da classe


def _carregar_orquestrador():
    """Carrega o orquestrador de forma lazy para evitar importação circular"""
    global ORQUESTRADOR_DISPONIVEL, _OrquestradorAgentes
    
    if ORQUESTRADOR_DISPONIVEL is not None:
        return ORQUESTRADOR_DISPONIVEL
    
    try:
        from sistemas.gerador_pecas.orquestrador_agentes import OrquestradorAgentes
        _OrquestradorAgentes = OrquestradorAgentes
        ORQUESTRADOR_DISPONIVEL = True
        print("Orquestrador de agentes carregado com sucesso")
    except Exception as e:
        ORQUESTRADOR_DISPONIVEL = False
        print(f"[WARN] Orquestrador de agentes nao disponivel - modo legado ativo. Erro: {e}")
        import traceback
        traceback.print_exc()
    
    return ORQUESTRADOR_DISPONIVEL


class GeradorPecasService:
    """
    Serviço principal para geração de peças jurídicas.
    
    Utiliza sistema de 3 agentes:
    - Agente 1 (TJ-MS): Coleta documentos e gera resumo consolidado
    - Agente 2 (Detector): Analisa e ativa módulos de conteúdo relevantes
    - Agente 3 (Gemini 3 Pro): Gera a peça jurídica final
    
    Prompts modulares:
    - BASE: System prompt (sempre ativo)
    - PEÇA: Estrutura específica do tipo de peça (ativado por escolha)
    - CONTEÚDO: Argumentos/teses (ativados por detecção de situação)
    """
    
    def __init__(
        self,
        modelo: str = "gemini-3-pro-preview",
        db: Session = None,
        group_id: Optional[int] = None,
        subcategoria_ids: Optional[List[int]] = None
    ):
        self.modelo = modelo
        self.db = db
        self.group_id = group_id
        self.subcategoria_ids = subcategoria_ids or []

        # Diretório para arquivos temporários
        self.temp_dir = os.path.join(os.path.dirname(__file__), 'temp_docs')
        os.makedirs(self.temp_dir, exist_ok=True)

        # Inicializar detector de módulos com configurações do banco
        self.detector = None
        self.orquestrador = None
        
        if self.db:
            self.detector = self._inicializar_detector()
            # Inicializa orquestrador se disponível (carregamento lazy)
            if _carregar_orquestrador():
                try:
                    self.orquestrador = _OrquestradorAgentes(
                        db=self.db,
                        modelo_geracao=self.modelo,
                        group_id=self.group_id,
                        subcategoria_ids=self.subcategoria_ids
                    )
                    print("Orquestrador de agentes inicializado com sucesso")
                except Exception as e:
                    print(f"[ERRO] Erro ao inicializar orquestrador: {e}")
                    import traceback
                    traceback.print_exc()
                    self.orquestrador = None
    
    def _inicializar_detector(self) -> Optional[DetectorModulosIA]:
        """Inicializa o detector de módulos com configurações do banco"""
        try:
            # Carregar configurações do banco
            modelo_config = self.db.query(ConfiguracaoIA).filter(
                ConfiguracaoIA.sistema == "gerador_pecas",
                ConfiguracaoIA.chave == "modelo_deteccao"
            ).first()

            cache_config = self.db.query(ConfiguracaoIA).filter(
                ConfiguracaoIA.sistema == "gerador_pecas",
                ConfiguracaoIA.chave == "cache_ttl_minutos"
            ).first()

            modelo = modelo_config.valor if modelo_config else "gemini-3-flash-preview"
            cache_ttl = int(cache_config.valor) if cache_config else 60

            return DetectorModulosIA(
                db=self.db,
                modelo=modelo,
                cache_ttl_minutes=cache_ttl
            )
        except Exception as e:
            print(f"[ERRO] Erro ao inicializar detector de modulos: {e}")
            return None

    def _carregar_modulos_base(self) -> List[PromptModulo]:
        """Carrega todos os módulos BASE (sempre ativos)"""
        if not self.db:
            return []
        return self.db.query(PromptModulo).filter(
            PromptModulo.tipo == "base",
            PromptModulo.ativo == True
        ).order_by(PromptModulo.ordem).all()
    
    def _carregar_modulo_peca(self, tipo_peca: str) -> Optional[PromptModulo]:
        """Carrega o módulo de PEÇA específico"""
        if not self.db:
            return None
        return self.db.query(PromptModulo).filter(
            PromptModulo.tipo == "peca",
            PromptModulo.nome == tipo_peca,  # Busca por nome (identificador único)
            PromptModulo.ativo == True
        ).first()
    
    def _carregar_modulos_conteudo(
        self,
        modulos_ids: List[int] = None,
        group_id: Optional[int] = None,
        subcategoria_ids: Optional[List[int]] = None
    ) -> List[PromptModulo]:
        """
        Carrega módulos de CONTEÚDO ordenados por categoria e depois por ordem do módulo.

        Args:
            modulos_ids: IDs dos módulos detectados pela IA (se None, retorna todos)
            group_id: Grupo principal para prompts modulares (opcional)
            subcategoria_ids: Subcategorias selecionadas para prompts modulares (opcional)
        """
        if not self.db:
            return []

        group_id = self.group_id if group_id is None else group_id
        subcategoria_ids = self.subcategoria_ids if subcategoria_ids is None else subcategoria_ids

        query = self.db.query(PromptModulo).filter(
            PromptModulo.tipo == "conteudo",
            PromptModulo.ativo == True
        )

        # Se IDs específicos fornecidos, filtra por eles
        if modulos_ids is not None:
            query = query.filter(PromptModulo.id.in_(modulos_ids))

        if group_id is not None:
            query = query.filter(PromptModulo.group_id == group_id)

        if subcategoria_ids:
            # Filtra módulos que:
            # 1. Pertencem a pelo menos uma das subcategorias selecionadas, OU
            # 2. Não têm nenhuma subcategoria associada (são "universais" - sempre elegíveis)
            from admin.models_prompt_groups import PromptSubcategoria
            from sqlalchemy import or_
            query = query.filter(
                or_(
                    PromptModulo.subcategorias.any(PromptSubcategoria.id.in_(subcategoria_ids)),
                    ~PromptModulo.subcategorias.any()
                )
            )

        # Busca todos os módulos
        modulos = query.all()

        # Ordena por categoria (usando CategoriaOrdem) e depois por ordem do módulo
        if group_id and modulos:
            # Busca ordem das categorias configurada
            categorias_ordem = self.db.query(CategoriaOrdem).filter(
                CategoriaOrdem.group_id == group_id
            ).all()
            ordem_categorias = {co.nome: co.ordem for co in categorias_ordem}

            # Ordena: primeiro por ordem da categoria, depois por ordem do módulo
            modulos.sort(key=lambda m: (
                ordem_categorias.get(m.categoria, 9999),  # Categoria sem ordem vai pro final
                m.ordem or 0
            ))

            # Log da ordem dos prompts para debug
            print(f"[ORDEM PROMPTS] Grupo {group_id} - Ordem das categorias: {ordem_categorias}")
            for idx, m in enumerate(modulos):
                cat_ordem = ordem_categorias.get(m.categoria, 9999)
                print(f"  {idx+1}. [{m.categoria}:{cat_ordem}] ordem={m.ordem or 0} - {m.titulo}")
        else:
            # Fallback: ordena apenas por ordem do módulo
            modulos.sort(key=lambda m: m.ordem or 0)

        return modulos
    
    def _montar_prompt_sistema(
        self,
        tipo_peca: str = None,
        modulos_ids: List[int] = None,
        group_id: Optional[int] = None,
        subcategoria_ids: Optional[List[int]] = None
    ) -> str:
        """
        Monta o prompt de sistema combinando módulos:
        BASE + PEÇA + CONTEÚDO

        Args:
            tipo_peca: Tipo da peça (contestacao, recurso, etc)
            modulos_ids: IDs dos módulos detectados pela IA
            group_id: Grupo principal para prompts modulares (opcional)
            subcategoria_ids: Subcategorias selecionadas para prompts modulares (opcional)
        """
        partes = []

        # 1. Módulos BASE (sempre incluídos)
        modulos_base = self._carregar_modulos_base()
        for modulo in modulos_base:
            partes.append(f"## {modulo.titulo}\n\n{modulo.conteudo}")

        # 2. Módulo de PEÇA (se tipo especificado)
        if tipo_peca:
            modulo_peca = self._carregar_modulo_peca(tipo_peca)
            if modulo_peca:
                partes.append(f"## ESTRUTURA DA PEÇA: {modulo_peca.titulo}\n\n{modulo_peca.conteudo}")

        # 3. Módulos de CONTEÚDO (baseado em detecção por IA)
        modulos_conteudo = self._carregar_modulos_conteudo(
            modulos_ids,
            group_id=group_id,
            subcategoria_ids=subcategoria_ids
        )
        if modulos_conteudo:
            partes.append("## ARGUMENTOS E TESES APLICÁVEIS\n")
            for modulo in modulos_conteudo:
                partes.append(f"### {modulo.titulo}\n{modulo.conteudo}\n")

        # Se não há módulos no banco, usa prompt padrão
        if not partes:
            return self._get_prompt_padrao()

        return "\n\n".join(partes)
    
    def _get_prompt_padrao(self) -> str:
        """Retorna prompt padrão caso não haja módulos no banco"""
        return """Você é um assistente jurídico especializado da Procuradoria-Geral do Estado de Mato Grosso do Sul (PGE-MS).

Sua função é analisar processos judiciais e gerar peças jurídicas profissionais (contestações, pareceres, recursos).

## DIRETRIZES GERAIS

1. **Análise Completa**: Leia TODOS os documentos fornecidos cronologicamente
2. **Identificação Automática**: Determine qual tipo de peça é necessária baseado nos documentos
3. **Fundamentação Técnica**: Use jurisprudência e doutrina quando necessário
4. **Linguagem Forense**: Use linguagem técnico-jurídica adequada
5. **Estrutura Formal**: Siga rigorosamente a estrutura padrão de cada tipo de peça

## TIPOS DE PEÇAS

### CONTESTAÇÃO
- Usado quando: Processo em 1º grau, Estado é réu, prazo de contestação em aberto
- Estrutura: Qualificação → Preliminares → Mérito → Pedidos

### RECURSO DE APELAÇÃO
- Usado quando: Sentença desfavorável ao Estado
- Estrutura: Endereçamento → Razões Recursais → Preliminares → Mérito → Pedidos

### CONTRARRAZÕES DE RECURSO
- Usado quando: Parte contrária apresentou recurso
- Estrutura: Endereçamento → Admissibilidade → Mérito → Pedidos

### PARECER JURÍDICO
- Usado quando: Análise técnica de questão jurídica específica
- Estrutura: Relatório → Fundamentação → Conclusão

## QUANDO TEM DÚVIDAS

Se você NÃO conseguir determinar com certeza qual peça gerar ou precisar de informações adicionais, retorne:
```json
{
  "tipo": "pergunta",
  "pergunta": "Qual tipo de peça você deseja gerar? Identifiquei que...",
  "opcoes": ["contestacao", "recurso_apelacao", "contrarrazoes", "parecer"]
}
```

## IMPORTANTE

- NUNCA invente fatos não presentes nos documentos
- SEMPRE fundamente tecnicamente seus argumentos
- Use dispositivos legais completos (Lei nº X, art. Y, § Z)
- Cite jurisprudência quando houver (STF, STJ, TJMS)
- Mantenha tom formal e respeitoso
"""
    
    async def processar_processo(
        self,
        numero_cnj: str,
        numero_cnj_formatado: str = None,
        tipo_peca: Optional[str] = None,
        resposta_usuario: Optional[str] = None,
        usuario_id: int = None,
        documentos_resumo: Optional[str] = None,
        documentos_completos: Optional[str] = None,
        usar_agentes: bool = True
    ) -> Dict:
        """
        Processa um processo e gera a peça jurídica usando os 3 agentes.

        Fluxo com agentes (usar_agentes=True):
        1. Agente 1 (TJ-MS): Baixa documentos e gera resumo consolidado
        2. Agente 2 (Detector): Analisa resumo e ativa módulos relevantes
        3. Agente 3 (Gemini 3 Pro): Gera a peça jurídica final

        Args:
            numero_cnj: Número do processo sem formatação
            numero_cnj_formatado: Número formatado para exibição
            tipo_peca: Tipo de peça a gerar (contestacao, recurso_apelacao, etc)
            resposta_usuario: Resposta a uma pergunta anterior
            usuario_id: ID do usuário
            documentos_resumo: Resumo dos documentos (bypass do Agente 1)
            documentos_completos: Texto completo dos documentos (opcional)
            usar_agentes: Se True, usa o fluxo completo com 3 agentes
        """
        try:
            # Normaliza o CNJ
            cnj_limpo = re.sub(r'\D', '', numero_cnj)
            cnj_display = numero_cnj_formatado or numero_cnj

            # Debug
            orq_disponivel = _carregar_orquestrador()
            print(f"[DEBUG] Debug: usar_agentes={usar_agentes}, orquestrador={self.orquestrador is not None}, ORQUESTRADOR_DISPONIVEL={orq_disponivel}")

            # Se tem orquestrador e usar_agentes está ativo, usa o novo fluxo
            if usar_agentes and self.orquestrador and orq_disponivel:
                return await self._processar_com_agentes(
                    numero_cnj=cnj_limpo,
                    numero_cnj_formatado=cnj_display,
                    tipo_peca=tipo_peca or resposta_usuario,
                    usuario_id=usuario_id
                )

            # Fallback: modo legado (sem integração TJ-MS)
            return await self._processar_modo_legado(
                numero_cnj=cnj_limpo,
                numero_cnj_formatado=cnj_display,
                tipo_peca=tipo_peca,
                resposta_usuario=resposta_usuario,
                usuario_id=usuario_id,
                documentos_resumo=documentos_resumo,
                documentos_completos=documentos_completos
            )
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {
                "status": "erro",
                "mensagem": str(e)
            }
    
    async def _processar_com_agentes(
        self,
        numero_cnj: str,
        numero_cnj_formatado: str,
        tipo_peca: Optional[str],
        usuario_id: int
    ) -> Dict:
        """
        Processa usando os 3 agentes integrados.
        """
        print("\nIniciando processamento com 3 agentes...")
        print(f"   Processo: {numero_cnj_formatado}")
        
        # Executa o orquestrador (passa número limpo, sem formatação)
        resultado = await self.orquestrador.processar_processo(
            numero_processo=numero_cnj,  # Número sem formatação (só dígitos)
            tipo_peca=tipo_peca
        )
        
        # Trata resultado de pergunta
        if resultado.status == "pergunta":
            return {
                "status": "pergunta",
                "pergunta": resultado.pergunta,
                "opcoes": resultado.opcoes,
                "mensagem": resultado.mensagem
            }
        
        # Trata erro
        if resultado.status == "erro":
            return {
                "status": "erro",
                "mensagem": resultado.mensagem
            }
        
        # Sucesso - salva no banco
        # NOTA: Agora o conteúdo é diretamente em Markdown, não mais JSON
        minuta_markdown = resultado.conteudo_markdown

        # Extrai dados para auditoria
        dados_extracao = None
        if resultado.agente1:
            try:
                from sistemas.gerador_pecas.orquestrador_agentes import consolidar_dados_extracao
                dados_extracao = consolidar_dados_extracao(resultado.agente1)
            except Exception:
                pass  # Se falhar, não é crítico

        # Salva no banco (incluindo prompt e resumo para auditoria)
        # conteudo_gerado agora armazena a string markdown diretamente

        # Calcula tempo de processamento (usa tempo_total ou soma dos tempos individuais)
        tempo_total = resultado.tempo_total
        if not tempo_total or tempo_total == 0.0:
            # Fallback: soma tempos individuais dos agentes
            tempo_total = (
                (resultado.tempo_agente1 or 0.0) +
                (resultado.tempo_agente2 or 0.0) +
                (resultado.tempo_agente3 or 0.0)
            )
        tempo_processamento = int(tempo_total) if tempo_total > 0 else None
        print(f"[DEBUG] tempo_total: {resultado.tempo_total}, tempos individuais: a1={resultado.tempo_agente1}, a2={resultado.tempo_agente2}, a3={resultado.tempo_agente3}, final={tempo_processamento}")

        geracao = GeracaoPeca(
            numero_cnj=numero_cnj,
            numero_cnj_formatado=numero_cnj_formatado,
            tipo_peca=resultado.tipo_peca,
            dados_processo=dados_extracao,  # Persiste variáveis extraídas para auditoria
            conteudo_gerado=minuta_markdown,  # Agora é markdown string, não JSON dict
            prompt_enviado=resultado.agente3.prompt_enviado if resultado.agente3 else None,
            resumo_consolidado=resultado.agente1.resumo_consolidado if resultado.agente1 else None,
            modelo_usado=self.modelo,
            tempo_processamento=tempo_processamento,
            usuario_id=usuario_id
        )

        # Campos de modo de ativação (podem não existir no banco se migration pendente)
        # Atribuídos após criação para permitir fallback
        try:
            geracao.modo_ativacao_agente2 = resultado.agente2.modo_ativacao if resultado.agente2 else None
            geracao.modulos_ativados_det = resultado.agente2.modulos_ativados_det if resultado.agente2 else None
            geracao.modulos_ativados_llm = resultado.agente2.modulos_ativados_llm if resultado.agente2 else None
        except AttributeError:
            # Colunas não existem no modelo (improvável, mas defensivo)
            pass

        if self.db:
            try:
                self.db.add(geracao)
                self.db.commit()
                self.db.refresh(geracao)
            except Exception as e:
                # Se falhou por colunas inexistentes, tenta sem os campos de modo de ativação
                if 'modo_ativacao_agente2' in str(e) or 'modulos_ativados' in str(e):
                    self.db.rollback()
                    # Remove os campos problemáticos e tenta novamente
                    geracao.modo_ativacao_agente2 = None
                    geracao.modulos_ativados_det = None
                    geracao.modulos_ativados_llm = None
                    # Força exclusão dos campos do estado do objeto
                    from sqlalchemy import inspect
                    state = inspect(geracao)
                    for attr in ['modo_ativacao_agente2', 'modulos_ativados_det', 'modulos_ativados_llm']:
                        if attr in state.dict:
                            del state.dict[attr]
                    self.db.add(geracao)
                    self.db.commit()
                    self.db.refresh(geracao)
                else:
                    raise
        
        # NOTA: Geração de DOCX desabilitada temporariamente para novo fluxo markdown
        # O DOCX será implementado com conversor MD->DOCX no futuro
        # Por enquanto, o usuário pode copiar o markdown e colar no Word
        
        return {
            "status": "sucesso",
            "geracao_id": geracao.id if self.db else None,
            "url_download": None,  # DOCX temporariamente desabilitado para novas gerações
            "tipo_peca": resultado.tipo_peca,
            "conteudo_json": None,  # Não há mais JSON
            "minuta_markdown": minuta_markdown,
            "tempo_total": resultado.tempo_total
        }
    
    async def _processar_modo_legado(
        self,
        numero_cnj: str,
        numero_cnj_formatado: str,
        tipo_peca: Optional[str],
        resposta_usuario: Optional[str],
        usuario_id: int,
        documentos_resumo: Optional[str],
        documentos_completos: Optional[str]
    ) -> Dict:
        """
        Modo legado: sem integração com TJ-MS (documento de exemplo em Markdown).
        Se tipo_peca não for especificado e há documentos_resumo, tenta detectar automaticamente.
        """
        print("[WARN] Usando modo legado (sem integracao TJ-MS)")

        tipo_final = tipo_peca or resposta_usuario

        # Se não tem tipo de peça, tenta detectar automaticamente se há documentos
        if not tipo_final and self.detector and documentos_resumo:
            print("[INFO] Detectando tipo de peca automaticamente (modo legado)...")
            try:
                deteccao = await self.detector.detectar_tipo_peca(documentos_resumo)
                tipo_final = deteccao.get("tipo_peca")
                if tipo_final:
                    print(f"Tipo detectado: {tipo_final} (confianca: {deteccao.get('confianca', 'N/A')})")
            except Exception as e:
                print(f"[WARN] Erro na deteccao automatica: {e}")

        # Se ainda não tem tipo de peça, pergunta ao usuário
        if not tipo_final:
            return {
                "status": "pergunta",
                "pergunta": f"Qual tipo de peça jurídica você deseja gerar para o processo {numero_cnj_formatado or numero_cnj}?",
                "opcoes": ["contestacao", "recurso_apelacao", "contrarrazoes", "parecer"],
                "mensagem": "Não foi possível detectar automaticamente. Por favor, selecione o tipo de peça."
            }

        # Monta o prompt usando módulos (para auditoria)
        prompt_sistema = self._montar_prompt_sistema(
            tipo_final,
            modulos_ids=None,
            group_id=self.group_id,
            subcategoria_ids=self.subcategoria_ids
        )
        
        # Gera documento de exemplo em Markdown
        minuta_markdown = self._gerar_documento_exemplo_markdown(numero_cnj_formatado or numero_cnj, tipo_final)
        
        # Salva no banco
        geracao = GeracaoPeca(
            numero_cnj=numero_cnj,
            numero_cnj_formatado=numero_cnj_formatado,
            tipo_peca=tipo_final,
            conteudo_gerado=minuta_markdown,  # Agora é Markdown string
            modelo_usado=self.modelo,
            usuario_id=usuario_id
        )
        
        if self.db:
            self.db.add(geracao)
            self.db.commit()
            self.db.refresh(geracao)
        
        return {
            "status": "sucesso",
            "geracao_id": geracao.id if self.db else None,
            "tipo_peca": tipo_final,
            "minuta_markdown": minuta_markdown
        }
    
    def _gerar_documento_exemplo_markdown(self, numero_cnj: str, tipo_peca: str) -> str:
        """Gera documento de exemplo em Markdown para demonstração"""
        
        tipo_labels = {
            "contestacao": "CONTESTAÇÃO",
            "recurso_apelacao": "RECURSO DE APELAÇÃO",
            "contrarrazoes": "CONTRARRAZÕES DE RECURSO",
            "parecer": "PARECER JURÍDICO"
        }
        
        titulo = tipo_labels.get(tipo_peca, "PEÇA JURÍDICA")
        
        return f"""**EXCELENTÍSSIMO SENHOR DOUTOR JUIZ DE DIREITO DA ___ VARA CÍVEL DA COMARCA DE CAMPO GRANDE - MS**

Processo nº {numero_cnj}

O **ESTADO DE MATO GROSSO DO SUL**, pessoa jurídica de direito público interno, inscrito no CNPJ sob o nº 15.412.257/0001-28, por meio de sua Procuradoria-Geral, vem, respeitosamente, à presença de Vossa Excelência, apresentar a presente **{titulo}**, pelos fundamentos de fato e de direito a seguir expostos.

## I - DOS FATOS

Trata-se de ação judicial em que o Estado de Mato Grosso do Sul figura no polo passivo. *[DESCRIÇÃO DOS FATOS SERÁ INSERIDA AQUI COM BASE NOS DOCUMENTOS DO PROCESSO]*

## II - DO DIREITO

*[FUNDAMENTAÇÃO JURÍDICA SERÁ INSERIDA AQUI COM BASE NA ANÁLISE DO PROCESSO]*

> A jurisprudência do Superior Tribunal de Justiça é pacífica no sentido de que a responsabilidade civil do Estado, embora objetiva, exige a comprovação do nexo de causalidade entre a conduta estatal e o dano alegado.
> — STJ, AgRg no AREsp 123.456/MS

## III - DOS PEDIDOS

Ante o exposto, requer seja julgado **improcedente** o pedido formulado na inicial, condenando-se a parte autora ao pagamento das custas processuais e honorários advocatícios.

---

*Campo Grande/MS, {datetime.now().strftime('%d de %B de %Y')}*

**[NOME DO PROCURADOR]**
Procurador do Estado
OAB/MS nº [NÚMERO]
"""

    async def editar_minuta(
        self,
        minuta_atual: str,
        mensagem_usuario: str,
        historico: List[Dict] = None
    ) -> Dict:
        """
        Processa pedido de edição da minuta via chat usando IA.
        
        Args:
            minuta_atual: Markdown da minuta atual
            mensagem_usuario: Pedido de alteração do usuário
            historico: Histórico de mensagens anteriores do chat
            
        Returns:
            Dict com status e minuta atualizada
        """
        from sistemas.gerador_pecas.gemini_client import chamar_gemini_async
        
        try:
            # Monta o prompt de sistema para edição
            system_prompt = """Você é um assistente jurídico especializado em edição de peças jurídicas.

Sua função é modificar a minuta fornecida de acordo com o pedido do usuário.

REGRAS IMPORTANTES:
1. Retorne APENAS a minuta editada em markdown, sem explicações adicionais
2. Mantenha a formatação formal juridica
3. Preserve as partes que não foram solicitadas para alteração
4. Use markdown correto (## para títulos, **negrito**, *itálico*, > para citações)
5. Se o pedido não for claro, faça a melhor interpretação possível
6. Mantenha o tom formal e técnico-jurídico

NÃO inclua:
- Explicações sobre as alterações
- Comentários sobre o documento
- Texto como "Aqui está a minuta editada"

Retorne SOMENTE a minuta editada em markdown."""

            # Monta o prompt do usuário com histórico
            prompt_parts = []
            
            # Adiciona histórico se houver
            if historico:
                prompt_parts.append("### Histórico da conversa:")
                for msg in historico:
                    role = "Usuário" if msg.get("role") == "user" else "Assistente"
                    prompt_parts.append(f"{role}: {msg.get('content', '')}")
                prompt_parts.append("")
            
            # Adiciona a mensagem atual com a minuta
            prompt_parts.append(f"""### Minuta atual:

{minuta_atual}

---

### Pedido de alteração: {mensagem_usuario}""")
            
            prompt_completo = "\n".join(prompt_parts)
            
            # Logging para diagnóstico
            prompt_len = len(prompt_completo)
            print(f"[EDITAR] 📝 Prompt de edição: {prompt_len:,} chars (~{prompt_len//4:,} tokens est.)")
            
            # Chama a IA com limite alto de tokens para suportar minutas grandes
            minuta_editada = await chamar_gemini_async(
                prompt=prompt_completo,
                system_prompt=system_prompt,
                modelo=self.modelo,
                max_tokens=50000,  # Limite alto para minutas jurídicas extensas
                temperature=0.3
            )
            
            # Remove possíveis blocos de código markdown que a IA pode ter adicionado
            if minuta_editada.startswith('```markdown'):
                minuta_editada = minuta_editada[11:]
            if minuta_editada.startswith('```'):
                minuta_editada = minuta_editada[3:]
            if minuta_editada.endswith('```'):
                minuta_editada = minuta_editada[:-3]
            
            minuta_editada = minuta_editada.strip()

            return {
                "status": "sucesso",
                "minuta_markdown": minuta_editada
            }

        except httpx.HTTPStatusError as e:
            print(f"[ERRO] Erro HTTP na edicao: {e}")
            return {
                "status": "erro",
                "mensagem": f"Erro na comunicação com a IA: {e.response.status_code}"
            }
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {
                "status": "erro",
                "mensagem": str(e)
            }

    async def editar_minuta_stream(
        self,
        minuta_atual: str,
        mensagem_usuario: str,
        historico: List[Dict] = None
    ):
        """
        Processa edição da minuta com streaming real.

        PERFORMANCE: Usa streamGenerateContent do Gemini para enviar
        tokens assim que são gerados, reduzindo TTFT de 15-60s para 1-3s.

        Args:
            minuta_atual: Markdown da minuta atual
            mensagem_usuario: Pedido de alteração do usuário
            historico: Histórico de mensagens anteriores

        Yields:
            Chunks de texto conforme são gerados
        """
        from services.gemini_service import gemini_service

        # Monta o prompt de sistema para edição
        system_prompt = """Você é um assistente jurídico especializado em edição de peças jurídicas.

Sua função é modificar a minuta fornecida de acordo com o pedido do usuário.

REGRAS IMPORTANTES:
1. Retorne APENAS a minuta editada em markdown, sem explicações adicionais
2. Mantenha a formatação formal juridica
3. Preserve as partes que não foram solicitadas para alteração
4. Use markdown correto (## para títulos, **negrito**, *itálico*, > para citações)
5. Se o pedido não for claro, faça a melhor interpretação possível
6. Mantenha o tom formal e técnico-jurídico

NÃO inclua:
- Explicações sobre as alterações
- Comentários sobre o documento
- Texto como "Aqui está a minuta editada"

Retorne SOMENTE a minuta editada em markdown."""

        # Monta o prompt do usuário com histórico
        prompt_parts = []

        # Adiciona histórico se houver
        if historico:
            prompt_parts.append("### Histórico da conversa:")
            for msg in historico:
                role = "Usuário" if msg.get("role") == "user" else "Assistente"
                prompt_parts.append(f"{role}: {msg.get('content', '')}")
            prompt_parts.append("")

        # Adiciona a mensagem atual com a minuta
        prompt_parts.append(f"""### Minuta atual:

{minuta_atual}

---

### Pedido de alteração: {mensagem_usuario}""")

        prompt_completo = "\n".join(prompt_parts)

        # Logging para diagnóstico
        prompt_len = len(prompt_completo)
        print(f"[EDITAR STREAM] 📝 Prompt: {prompt_len:,} chars (~{prompt_len//4:,} tokens est.)")

        # Usa streaming real do Gemini
        async for chunk in gemini_service.generate_stream(
            prompt=prompt_completo,
            system_prompt=system_prompt,
            model=self.modelo,
            max_tokens=50000,
            temperature=0.3,
            context={"sistema": "gerador_pecas", "modulo": "editar_minuta"}
        ):
            yield chunk
