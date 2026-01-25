# sistemas/gerador_pecas/detector_modulos.py
"""
Serviço de detecção inteligente de módulos de CONTEÚDO usando IA.
Utiliza Gemini Flash Lite para análise rápida e eficiente.

Suporta:
- Detecção via LLM (modo tradicional)
- Detecção determinística (sem LLM) usando variáveis de extração
- Variáveis derivadas do processo XML (ProcessVariableResolver)
- Fast path: pula LLM quando TODOS os módulos são determinísticos
"""

import os
import json
import httpx
import time
import logging
from typing import List, Dict, Optional, Any, TYPE_CHECKING
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from admin.models_prompts import PromptModulo, RegraDeterministicaTipoPeca
from sistemas.gerador_pecas.gemini_client import chamar_gemini_async, normalizar_modelo
from sistemas.gerador_pecas.services_deterministic import (
    avaliar_ativacao_prompt,
    _existe_regra_especifica_ativa,
    batch_verificar_regras_especificas
)
from sistemas.gerador_pecas.services_process_variables import ProcessVariableResolver
from sistemas.gerador_pecas.constants import (
    MODO_ATIVACAO_LLM,
    MODO_ATIVACAO_DETERMINISTICO,
    MODO_ATIVACAO_MISTO,
    MODO_ATIVACAO_FAST_PATH,
)

# Logger estruturado para métricas de performance
logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from sistemas.gerador_pecas.agente_tjms import DadosProcesso


class DetectorModulosIA:
    """
    Detector inteligente que usa IA para analisar documentos e determinar:
    1. Qual TIPO DE PEÇA é mais adequado (contestação, recurso, etc)
    2. Quais módulos de CONTEÚDO são relevantes para o caso

    Utiliza API direta do Gemini para análise rápida e de baixo custo.
    """

    def __init__(
        self,
        db: Session,
        modelo: str = "gemini-3-flash-preview",
        cache_ttl_minutes: int = 60
    ):
        """
        Args:
            db: Sessão do banco de dados
            modelo: Modelo a ser usado (padrão: gemini-3-flash-preview)
            cache_ttl_minutes: Tempo de vida do cache em minutos
        """
        self.db = db
        self.modelo = normalizar_modelo(modelo)
        self.cache_ttl = timedelta(minutes=cache_ttl_minutes)

        # Cache em memória {hash_documentos: (modulos_ids, timestamp)}
        self._cache = {}
        # Cache para detecção de tipo de peça
        self._cache_tipo_peca = {}
        
        # Resultado da última detecção (para auditoria/histórico)
        self.ultimo_modo_ativacao: str = "llm"  # 'fast_path', 'misto', 'llm'
        self.ultimo_modulos_det: int = 0  # Módulos ativados por regra determinística
        self.ultimo_modulos_llm: int = 0  # Módulos ativados por LLM
        # IDs separados por método de ativação (para diferenciação no prompt)
        self.ultimo_ids_det: List[int] = []  # IDs ativados deterministicamente
        self.ultimo_ids_llm: List[int] = []  # IDs ativados por LLM

    async def detectar_modulos_relevantes(
        self,
        documentos_resumo: str,
        documentos_completos: Optional[str] = None,
        tipo_peca: Optional[str] = None,
        group_id: Optional[int] = None,
        subcategoria_ids: Optional[List[int]] = None,
        dados_processo: Optional['DadosProcesso'] = None,
        dados_extracao: Optional[Dict[str, Any]] = None
    ) -> List[int]:
        """
        Analisa os documentos e retorna IDs dos módulos de CONTEÚDO relevantes.

        Suporta dois caminhos:
        1. Fast Path: Se TODOS os módulos elegíveis são determinísticos, pula LLM
        2. Modo Misto: Avalia determinísticos localmente + chama LLM para os demais

        Args:
            documentos_resumo: Resumo dos documentos do processo
            documentos_completos: Texto completo dos documentos (opcional)
            tipo_peca: Tipo de peça para filtrar módulos disponíveis (opcional)
            group_id: ID do grupo de prompts (opcional)
            subcategoria_ids: IDs das subcategorias selecionadas (opcional)
            dados_processo: DadosProcesso extraídos do XML (opcional)
            dados_extracao: Dados de extração de PDFs via IA (opcional)

        Returns:
            Lista de IDs dos módulos relevantes
        """
        # Timing: marca o início da detecção
        t_inicio = time.perf_counter()
        timings = {}  # Dicionário para armazenar tempos de cada fase

        print(f"\n[AGENTE2] ========== INICIO detectar_modulos_relevantes ==========")
        print(f"[AGENTE2] tipo_peca={tipo_peca}, group_id={group_id}, subcategoria_ids={subcategoria_ids}")
        print(f"[AGENTE2] Tamanho do resumo: {len(documentos_resumo)} chars")
        print(f"[AGENTE2] dados_processo presente: {dados_processo is not None}")
        print(f"[AGENTE2] dados_extracao presente: {dados_extracao is not None}")

        # Verificar cache (inclui tipo_peca na chave)
        t_cache_inicio = time.perf_counter()
        subcategoria_cache = ",".join(str(i) for i in (subcategoria_ids or []))
        cache_key = self._gerar_cache_key(f"{tipo_peca or ''}:{group_id or ''}:{subcategoria_cache}:{documentos_resumo}")
        cached = self._verificar_cache(cache_key)
        timings['cache_check'] = time.perf_counter() - t_cache_inicio
        if cached is not None:
            timings['total'] = time.perf_counter() - t_inicio
            print(f"[AGENTE2] ✅ Cache hit - módulos detectados anteriormente: {cached}")
            print(f"[AGENTE2] ⏱️ TIMING: cache_check={timings['cache_check']*1000:.1f}ms, total={timings['total']*1000:.1f}ms")
            return cached

        print(f"[AGENTE2] Cache miss - carregando módulos do banco...")

        # Carregar módulos de CONTEÚDO disponíveis (filtrado por tipo de peça se especificado)
        t_db_inicio = time.perf_counter()
        modulos = self._carregar_modulos_disponiveis(tipo_peca, group_id, subcategoria_ids)
        timings['db_load_modules'] = time.perf_counter() - t_db_inicio
        print(f"[AGENTE2] Módulos carregados do banco: {len(modulos)} (em {timings['db_load_modules']*1000:.1f}ms)")

        if not modulos:
            if tipo_peca:
                print(f"[AGENTE2] [WARN] Nenhum módulo de CONTEÚDO disponível para tipo de peça '{tipo_peca}'")
            else:
                print("[AGENTE2] [WARN] Nenhum módulo de CONTEÚDO disponível no banco")
            return []

        if tipo_peca:
            print(f"[AGENTE2]  {len(modulos)} módulos disponíveis para tipo '{tipo_peca}'")

        # ========================================
        # RESOLUÇÃO DE VARIÁVEIS DERIVADAS DO PROCESSO
        # ========================================
        t_vars_inicio = time.perf_counter()
        variaveis = dados_extracao.copy() if dados_extracao else {}

        if dados_processo:
            # dados_processo pode ser ResultadoAnalise ou DadosProcesso
            # Se for ResultadoAnalise, extrair o DadosProcesso interno
            dados_proc_real = dados_processo
            if hasattr(dados_processo, 'dados_processo') and dados_processo.dados_processo:
                dados_proc_real = dados_processo.dados_processo
                print(f"[AGENTE2] Extraído DadosProcesso de ResultadoAnalise")

            resolver = ProcessVariableResolver(dados_proc_real)
            variaveis_processo = resolver.resolver_todas()
            # Merge: variáveis do processo têm precedência
            variaveis.update(variaveis_processo)
            print(f"[AGENTE2] Variáveis derivadas do processo: {variaveis_processo}")

        timings['variable_resolution'] = time.perf_counter() - t_vars_inicio

        print(f"[AGENTE2] Total de variáveis disponíveis: {len(variaveis)}")
        if variaveis:
            # Log algumas variáveis importantes para debug
            vars_importantes = [
                'valor_causa_inferior_60sm', 'processo_ajuizado_apos_2024_04_19',
                'peticao_inicial_uniao_polo_passivo',
                # Variáveis de pareceres/cirurgia (importantes para mer_sem_urgencia)
                'pareceres_analisou_cirurgia', 'pareceres_natureza_cirurgia',
                'pareceres_qual_cirurgia', 'pareceres_cirurgia_ofertada_sus',
                'pareceres_laudo_medico_sus', 'pareceres_analisou_exame'
            ]
            for var in vars_importantes:
                if var in variaveis:
                    print(f"[AGENTE2]   - {var}: {variaveis[var]}")

            # Log TODAS as variáveis com prefixo 'pareceres_' para debug
            vars_pareceres = {k: v for k, v in variaveis.items() if k.startswith('pareceres_')}
            if vars_pareceres:
                print(f"[AGENTE2] Variáveis de pareceres encontradas: {len(vars_pareceres)}")
                for k, v in vars_pareceres.items():
                    print(f"[AGENTE2]   >> {k}: {v}")

        # ========================================
        # SEPARAÇÃO: DETERMINÍSTICOS vs LLM
        # ========================================
        # Um módulo é considerado determinístico se:
        # 1. Tem modo_ativacao = "deterministic" E
        # 2. Tem regra global (regra_deterministica) OU
        #    Tem regra específica para o tipo_peca atual (na tabela regra_deterministica_tipo_peca)
        t_separacao_inicio = time.perf_counter()
        modulos_det = []
        modulos_llm = []

        # OTIMIZAÇÃO: Batch load das regras específicas (1 query vs N queries)
        regras_especificas_map = {}
        if tipo_peca:
            modulos_det_ids = [m.id for m in modulos if m.modo_ativacao == "deterministic"]
            if modulos_det_ids:
                regras_especificas_map = batch_verificar_regras_especificas(
                    self.db, modulos_det_ids, tipo_peca
                )
                print(f"[AGENTE2] Batch: {len(regras_especificas_map)} módulos verificados para regras específicas")

        for modulo in modulos:
            if modulo.modo_ativacao == "deterministic":
                # Verifica se tem regra global OU regra específica para o tipo_peca
                tem_regra_global = modulo.regra_deterministica is not None
                tem_regra_especifica = regras_especificas_map.get(modulo.id, False)

                if tem_regra_especifica:
                    print(f"[AGENTE2] Módulo '{modulo.nome}' tem regra específica para '{tipo_peca}'")

                if tem_regra_global or tem_regra_especifica:
                    modulos_det.append(modulo)
                else:
                    # Modo determinístico mas sem nenhuma regra configurada -> LLM
                    modulos_llm.append(modulo)
            else:
                modulos_llm.append(modulo)

        timings['module_separation'] = time.perf_counter() - t_separacao_inicio
        print(f"[AGENTE2] Módulos determinísticos: {len(modulos_det)} (inclui regras específicas por tipo de peça)")
        print(f"[AGENTE2] Módulos LLM: {len(modulos_llm)}")
        print(f"[AGENTE2] ⏱️ Separação de módulos: {timings['module_separation']*1000:.1f}ms")

        # ========================================
        # FAST PATH: 100% DETERMINÍSTICO
        # ========================================
        if modulos_det and not modulos_llm:
            print(f"[AGENTE2] ⚡ FAST PATH: 100% determinístico, pulando LLM")
            t_eval_inicio = time.perf_counter()
            ids_ativados = self._avaliar_todos_deterministicos(modulos_det, variaveis, tipo_peca)
            timings['deterministic_evaluation'] = time.perf_counter() - t_eval_inicio

            # Salvar no cache
            self._salvar_cache(cache_key, ids_ativados)

            # Calcular tempo total
            timings['total'] = time.perf_counter() - t_inicio

            # Salvar estatísticas para auditoria
            self.ultimo_modo_ativacao = "fast_path"
            self.ultimo_modulos_det = len(ids_ativados)
            self.ultimo_modulos_llm = 0
            self.ultimo_ids_det = ids_ativados.copy()
            self.ultimo_ids_llm = []

            # Log estruturado de performance
            print(f"[AGENTE2] 🎯 FAST PATH: {len(ids_ativados)} módulos ativados: {ids_ativados}")
            print(f"[AGENTE2] ⏱️ TIMING FAST PATH:")
            print(f"[AGENTE2]   - db_load_modules: {timings.get('db_load_modules', 0)*1000:.1f}ms")
            print(f"[AGENTE2]   - variable_resolution: {timings.get('variable_resolution', 0)*1000:.1f}ms")
            print(f"[AGENTE2]   - module_separation: {timings.get('module_separation', 0)*1000:.1f}ms")
            print(f"[AGENTE2]   - deterministic_evaluation: {timings['deterministic_evaluation']*1000:.1f}ms")
            print(f"[AGENTE2]   - TOTAL: {timings['total']*1000:.1f}ms")
            print(f"[AGENTE2] ========== FIM detectar_modulos_relevantes (FAST PATH) ==========\n")

            # Log JSON estruturado para análise posterior
            logger.info(json.dumps({
                "event": "ag2_fast_path_complete",
                "path": "fast_path",
                "modules_evaluated": len(modulos_det),
                "modules_activated": len(ids_ativados),
                "timings_ms": {k: round(v * 1000, 2) for k, v in timings.items()},
                "total_ms": round(timings['total'] * 1000, 2)
            }))

            return ids_ativados

        # ========================================
        # MODO MISTO: DETERMINÍSTICOS + LLM
        # ========================================
        t_eval_inicio = time.perf_counter()
        ids_det = []
        modulos_para_llm = list(modulos_llm)  # Cópia para não modificar original

        # Avalia módulos determinísticos
        for modulo in modulos_det:
            # Log da regra sendo avaliada para debug
            regra = modulo.regra_deterministica
            if regra and isinstance(regra, dict):
                var_regra = regra.get('variable', regra.get('conditions', [{}])[0].get('variable') if regra.get('conditions') else None)
                valor_esperado = regra.get('value')
                valor_atual = variaveis.get(var_regra) if var_regra else None
                print(f"[AGENTE2] [DET] Avaliando '{modulo.nome}': var={var_regra}, esperado={valor_esperado}, atual={valor_atual}")

            resultado = avaliar_ativacao_prompt(
                prompt_id=modulo.id,
                modo_ativacao="deterministic",
                regra_deterministica=modulo.regra_deterministica,
                dados_extracao=variaveis,
                db=self.db,
                regra_secundaria=getattr(modulo, 'regra_deterministica_secundaria', None),
                fallback_habilitado=getattr(modulo, 'fallback_habilitado', False),
                tipo_peca=tipo_peca  # Passa tipo_peca para avaliar regras específicas
            )

            if resultado["ativar"] is True:
                ids_det.append(modulo.id)
                print(f"[AGENTE2] [DET] >>> '{modulo.titulo}' ATIVADO (regra: {resultado.get('regra_usada', 'N/A')})")
            elif resultado["ativar"] is None:
                # CORRIGIDO: Verifica se é modo LLM real ou indeterminado determinístico
                modo_resultado = resultado.get("modo", "deterministic")
                detalhes = resultado.get('detalhes', 'variaveis indisponiveis')

                if modo_resultado == "llm":
                    # Modo LLM real -> manda para LLM
                    modulos_para_llm.append(modulo)
                    print(f"[AGENTE2] [DET] ??? '{modulo.titulo}' modo LLM -> enviando para LLM")
                else:
                    # Modo determinístico com resultado indeterminado (variáveis faltando)
                    # NÃO envia para LLM - trata como não ativado
                    print(f"[AGENTE2] [DET] --- '{modulo.titulo}' INDETERMINADO (vars faltando) - NAO ativado ({detalhes})")
            else:
                detalhes = resultado.get('detalhes', '')
                print(f"[AGENTE2] [DET] XXX '{modulo.titulo}' NAO ativado - {detalhes}")

        # Timing: avaliação determinística do modo misto
        timings['deterministic_evaluation'] = time.perf_counter() - t_eval_inicio

        # Chama LLM apenas para módulos que precisam
        ids_llm = []
        if modulos_para_llm:
            print(f"[AGENTE2] Enviando {len(modulos_para_llm)} módulos para LLM...")
            t_llm_inicio = time.perf_counter()
            ids_llm = await self._detectar_via_llm(documentos_resumo, documentos_completos, modulos_para_llm)
            timings['llm_detection'] = time.perf_counter() - t_llm_inicio
        else:
            print(f"[AGENTE2] Nenhum módulo precisa de LLM")
            timings['llm_detection'] = 0

        # Combina resultados
        modulos_relevantes = ids_det + ids_llm

        # Salvar no cache
        self._salvar_cache(cache_key, modulos_relevantes)

        # Calcular tempo total
        timings['total'] = time.perf_counter() - t_inicio

        # Salvar estatísticas para auditoria
        if ids_llm:
            self.ultimo_modo_ativacao = "misto" if ids_det else "llm"
        else:
            # Sem LLM -> "fast_path" (100% determinístico, mesmo se nenhum ativado)
            self.ultimo_modo_ativacao = "fast_path"
        self.ultimo_modulos_det = len(ids_det)
        self.ultimo_modulos_llm = len(ids_llm)
        self.ultimo_ids_det = ids_det.copy()
        self.ultimo_ids_llm = ids_llm.copy()

        print(f"[AGENTE2] 🎯 Detectados {len(modulos_relevantes)} módulos relevantes: {modulos_relevantes}")
        print(f"[AGENTE2]    - Determinísticos: {len(ids_det)}")
        print(f"[AGENTE2]    - LLM: {len(ids_llm)}")
        print(f"[AGENTE2]    - Modo: {self.ultimo_modo_ativacao}")
        print(f"[AGENTE2] ⏱️ TIMING ({self.ultimo_modo_ativacao.upper()}):")
        print(f"[AGENTE2]   - db_load_modules: {timings.get('db_load_modules', 0)*1000:.1f}ms")
        print(f"[AGENTE2]   - variable_resolution: {timings.get('variable_resolution', 0)*1000:.1f}ms")
        print(f"[AGENTE2]   - module_separation: {timings.get('module_separation', 0)*1000:.1f}ms")
        print(f"[AGENTE2]   - deterministic_evaluation: {timings.get('deterministic_evaluation', 0)*1000:.1f}ms")
        if timings.get('llm_detection', 0) > 0:
            print(f"[AGENTE2]   - llm_detection: {timings['llm_detection']*1000:.1f}ms")
        print(f"[AGENTE2]   - TOTAL: {timings['total']*1000:.1f}ms")
        print(f"[AGENTE2] ========== FIM detectar_modulos_relevantes ==========\n")

        # Log JSON estruturado para análise posterior
        logger.info(json.dumps({
            "event": "ag2_detection_complete",
            "path": self.ultimo_modo_ativacao,
            "modules_det_evaluated": len(modulos_det),
            "modules_llm_evaluated": len(modulos_para_llm),
            "modules_det_activated": len(ids_det),
            "modules_llm_activated": len(ids_llm),
            "timings_ms": {k: round(v * 1000, 2) for k, v in timings.items()},
            "total_ms": round(timings['total'] * 1000, 2)
        }))

        return modulos_relevantes

    def _avaliar_todos_deterministicos(
        self,
        modulos: List[PromptModulo],
        variaveis: Dict[str, Any],
        tipo_peca: Optional[str] = None
    ) -> List[int]:
        """
        Fast path: avalia todos os módulos determinísticos sem chamar LLM.

        Args:
            modulos: Lista de módulos com regra determinística
            variaveis: Dicionário com variáveis disponíveis
            tipo_peca: Tipo de peça para avaliar regras específicas (opcional)

        Returns:
            Lista de IDs dos módulos ativados
        """
        ids_ativados = []

        for modulo in modulos:
            # Log da regra sendo avaliada para debug
            regra = modulo.regra_deterministica
            if regra and isinstance(regra, dict):
                var_regra = regra.get('variable', regra.get('conditions', [{}])[0].get('variable') if regra.get('conditions') else None)
                valor_esperado = regra.get('value')
                valor_atual = variaveis.get(var_regra) if var_regra else None
                print(f"[AGENTE2] [FAST] Avaliando '{modulo.nome}': var={var_regra}, esperado={valor_esperado}, atual={valor_atual}")

            resultado = avaliar_ativacao_prompt(
                prompt_id=modulo.id,
                modo_ativacao="deterministic",
                regra_deterministica=modulo.regra_deterministica,
                dados_extracao=variaveis,
                db=self.db,
                regra_secundaria=getattr(modulo, 'regra_deterministica_secundaria', None),
                fallback_habilitado=getattr(modulo, 'fallback_habilitado', False),
                tipo_peca=tipo_peca  # Passa tipo_peca para avaliar regras específicas
            )

            if resultado["ativar"] is True:
                ids_ativados.append(modulo.id)
                print(f"[AGENTE2] [FAST] >>> '{modulo.titulo}' ATIVADO (regra: {resultado.get('regra_usada', 'N/A')})")
            elif resultado["ativar"] is None:
                # Variáveis não disponíveis - não ativa (sem fallback para LLM no fast path)
                detalhes = resultado.get('detalhes', 'variaveis indisponiveis')
                print(f"[AGENTE2] [FAST] --- '{modulo.titulo}' nao avaliavel ({detalhes})")
            else:
                detalhes = resultado.get('detalhes', '')
                print(f"[AGENTE2] [FAST] XXX '{modulo.titulo}' NAO ativado - {detalhes}")

        return ids_ativados

    async def _detectar_via_llm(
        self,
        documentos_resumo: str,
        documentos_completos: Optional[str],
        modulos: List[PromptModulo]
    ) -> List[int]:
        """
        Detecta módulos relevantes via chamada à LLM.

        Args:
            documentos_resumo: Resumo dos documentos
            documentos_completos: Texto completo (opcional)
            modulos: Lista de módulos a avaliar

        Returns:
            Lista de IDs dos módulos detectados como relevantes
        """
        if not modulos:
            return []

        # Preparar prompt para a IA
        prompt_deteccao = self._montar_prompt_deteccao(
            documentos_resumo,
            documentos_completos,
            modulos
        )

        try:
            import time
            print(f"[AGENTE2] >>> INICIANDO chamada à IA (modelo: {self.modelo})...")
            inicio_ia = time.time()

            resultado = await self._chamar_ia(prompt_deteccao)

            tempo_ia = time.time() - inicio_ia
            print(f"[AGENTE2] <<< IA respondeu em {tempo_ia:.2f}s")
            print(f"[AGENTE2] Resultado da IA: {resultado}")

            return self._processar_resposta_ia(resultado, modulos)

        except Exception as e:
            import traceback
            print(f"[AGENTE2] [ERRO] Erro na detecção por IA: {e}")
            print(f"[AGENTE2] Traceback: {traceback.format_exc()}")
            return []

    def _carregar_modulos_disponiveis(
        self,
        tipo_peca: str = None,
        group_id: Optional[int] = None,
        subcategoria_ids: Optional[List[int]] = None
    ) -> List[PromptModulo]:
        """
        Carrega modulos de CONTEUDO ativos do banco.

        Se tipo_peca for especificado, filtra apenas modulos ativos para esse tipo.
        Se group_id for informado, restringe aos modulos do grupo.
        Se subcategoria_ids for informado, restringe aos modulos que pertencem a essas subcategorias.
        """
        from admin.models_prompts import ModuloTipoPeca
        from admin.models_prompt_groups import PromptSubcategoria

        # Busca todos os modulos de conteudo ativos globalmente
        query = self.db.query(PromptModulo).filter(
            PromptModulo.tipo == "conteudo",
            PromptModulo.ativo == True
        )

        if group_id is not None:
            query = query.filter(PromptModulo.group_id == group_id)

        if subcategoria_ids:
            # Filtra módulos que:
            # 1. Pertencem a pelo menos uma das subcategorias selecionadas, OU
            # 2. Não têm nenhuma subcategoria associada (são "universais" - sempre elegíveis)
            from sqlalchemy import or_
            query = query.filter(
                or_(
                    PromptModulo.subcategorias.any(PromptSubcategoria.id.in_(subcategoria_ids)),
                    ~PromptModulo.subcategorias.any()
                )
            )

        modulos = query.order_by(PromptModulo.ordem).all()

        # Se nao ha tipo de peca especificado, retorna todos
        if not tipo_peca:
            return modulos

        # Busca associacoes para este tipo de peca
        associacoes = self.db.query(ModuloTipoPeca).filter(
            ModuloTipoPeca.tipo_peca == tipo_peca
        ).all()

        # Se nao ha associacoes configuradas, retorna todos (retrocompatibilidade)
        if not associacoes:
            return modulos

        # Cria mapa: modulo_id -> ativo
        mapa_ativo = {a.modulo_id: a.ativo for a in associacoes}

        # Filtra modulos
        modulos_filtrados = []
        for modulo in modulos:
            # Se nao tem associacao configurada, considera ativo (retrocompatibilidade)
            ativo_para_tipo = mapa_ativo.get(modulo.id, True)
            if ativo_para_tipo:
                modulos_filtrados.append(modulo)

        return modulos_filtrados

    def _montar_prompt_deteccao(
        self,
        documentos_resumo: str,
        documentos_completos: Optional[str],
        modulos: List[PromptModulo]
    ) -> str:
        """Monta o prompt para o agente de detecção"""

        # Preparar lista de módulos disponíveis - usando apenas a CONDIÇÃO DE ATIVAÇÃO
        modulos_info = []
        for idx, modulo in enumerate(modulos):
            # Usa condicao_ativacao para a detecção, não o conteúdo completo
            condicao = modulo.condicao_ativacao or ""
            if not condicao:
                # Fallback: se não tem condição definida, usa início do conteúdo
                condicao = modulo.conteudo[:200] + "..." if len(modulo.conteudo) > 200 else modulo.conteudo
            
            info = {
                "id": idx,  # Índice temporário para a IA
                "nome": modulo.nome,
                "titulo": modulo.titulo,
                "categoria": modulo.categoria or "",
                "subcategoria": modulo.subcategoria or "",
                "condicao_ativacao": condicao  # Apenas a condição, não o conteúdo
            }
            modulos_info.append(info)

        prompt = f"""Você é um assistente especializado em análise jurídica para a Procuradoria-Geral do Estado de Mato Grosso do Sul (PGE-MS).

Sua tarefa é analisar os documentos de um processo judicial e identificar quais módulos de argumentos e teses jurídicas são RELEVANTES para o caso.

## DOCUMENTOS DO PROCESSO

### Resumo:
{documentos_resumo}
"""

        if documentos_completos:
            prompt += f"""
### Documentos Completos:
{documentos_completos[:5000]}  # Limita a 5000 caracteres
"""

        prompt += f"""

## MÓDULOS DISPONÍVEIS

A seguir, uma lista de módulos de argumentos/teses disponíveis. O campo "condicao_ativacao" descreve a SITUAÇÃO FÁTICA em que cada módulo deve ser acionado.

```json
{json.dumps(modulos_info, ensure_ascii=False, indent=2)}
```

## SUA TAREFA

Analise os documentos do processo e selecione APENAS os módulos cuja condição de ativação é **claramente atendida** pelos fatos do caso.

### Critérios de seleção:

1. **Correspondência direta**: A condição de ativação deve estar presente nos fatos do processo
2. **Evidência concreta**: Deve haver menção explícita ou forte indicação nos documentos
3. **Relevância prática**: O módulo deve realmente contribuir para a defesa do Estado neste caso específico

### O que NÃO fazer:

- NÃO inclua módulos por "precaução" ou "por via das dúvidas"
- NÃO inclua módulos apenas por semelhança temática genérica
- NÃO inclua módulos cuja condição não apareça claramente nos fatos

### Regra de ouro:

Se a condição de ativação não estiver **evidenciada nos documentos**, NÃO inclua o módulo. É melhor incluir poucos módulos relevantes do que muitos módulos genéricos.

## FORMATO DE RESPOSTA

Responda APENAS com um objeto JSON no seguinte formato:

```json
{{
  "modulos_relevantes": [
    {{"id": 0, "motivo": "Fato X do processo atende a condição Y"}},
    {{"id": 3, "motivo": "Documento Z menciona situação W"}}
  ],
  "confianca": "alta|media|baixa"
}}
```

Onde:
- `modulos_relevantes`: Array de objetos com ID (índice) e motivo curto (máx 15 palavras)
- `confianca`: Nível de confiança na detecção

Responda SOMENTE com o JSON, sem texto adicional.
"""

        return prompt

    async def _chamar_ia(self, prompt: str) -> Dict:
        """Chama a API do Gemini diretamente"""
        print(f"[AGENTE2._chamar_ia] Iniciando chamada ao Gemini...")
        print(f"[AGENTE2._chamar_ia] Modelo: {self.modelo}")
        print(f"[AGENTE2._chamar_ia] Tamanho do prompt: {len(prompt)} chars")

        try:
            content = await chamar_gemini_async(
                prompt=prompt,
                modelo=self.modelo,
                max_tokens=50000,  # Aumentado para evitar truncamento
                temperature=0.1  # Baixa temperatura para resposta determinística
            )
            print(f"[AGENTE2._chamar_ia] Resposta recebida - tamanho: {len(content)} chars")
        except Exception as e:
            print(f"[AGENTE2._chamar_ia] ERRO na chamada ao Gemini: {e}")
            import traceback
            print(f"[AGENTE2._chamar_ia] Traceback: {traceback.format_exc()}")
            raise

        # Extrair JSON da resposta
        content = content.strip()
        
        # Remover markdown se houver
        if content.startswith('```'):
            lines = content.split('\n')
            # Remove primeira e última linha com ```
            if lines[0].startswith('```'):
                lines = lines[1:]
            if lines and lines[-1].strip() == '```':
                lines = lines[:-1]
            content = '\n'.join(lines).strip()
        
        # Tentar encontrar JSON dentro do texto
        import re
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            content = json_match.group()
        
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            print(f"[WARN] Erro ao parsear JSON: {e}")
            print(f"[WARN] Conteúdo recebido: {content[:200]}...")

            # Tenta extrair módulos do novo formato: {"id": X, "motivo": "..."}
            modulos_obj_match = re.findall(r'\{\s*"id"\s*:\s*(\d+)\s*,\s*"motivo"\s*:\s*"([^"]*)"', content)
            if modulos_obj_match:
                modulos = [{"id": int(m[0]), "motivo": m[1]} for m in modulos_obj_match]
                print(f" Recuperados {len(modulos)} módulos de JSON truncado (formato novo)")
                return {
                    "modulos_relevantes": modulos,
                    "confianca": "media"
                }

            # Fallback: tenta formato antigo [1, 2, 3, ...]
            modulos_match = re.search(r'"modulos_relevantes"\s*:\s*\[([\d,\s]+)', content)
            if modulos_match:
                try:
                    nums_str = modulos_match.group(1).rstrip(',').strip()
                    if nums_str:
                        modulos = [int(n.strip()) for n in nums_str.split(',') if n.strip().isdigit()]
                        print(f" Recuperados {len(modulos)} módulos de JSON truncado (formato antigo)")
                        return {
                            "modulos_relevantes": modulos,
                            "confianca": "media"
                        }
                except:
                    pass

            # Retorna estrutura vazia para fallback
            return {"modulos_relevantes": [], "confianca": "baixa"}

    def _processar_resposta_ia(
        self,
        resposta: Dict,
        modulos: List[PromptModulo]
    ) -> List[int]:
        """
        Processa a resposta da IA e retorna os IDs reais dos módulos.

        Args:
            resposta: Dicionário com a resposta da IA
            modulos: Lista de módulos disponíveis

        Returns:
            Lista de IDs reais dos módulos no banco de dados
        """
        modulos_info = resposta.get('modulos_relevantes', [])
        confianca = resposta.get('confianca', 'media')

        print(f"📊 Detecção IA - Confiança: {confianca}")

        # Converter índices temporários para IDs reais
        ids_reais = []

        for item in modulos_info:
            # Suporta tanto o formato novo (objeto com id e motivo) quanto o antigo (apenas índice)
            if isinstance(item, dict):
                idx = item.get('id', -1)
                motivo = item.get('motivo', '')
            else:
                idx = item
                motivo = ''

            if 0 <= idx < len(modulos):
                ids_reais.append(modulos[idx].id)
                if motivo:
                    print(f"   [OK] {modulos[idx].titulo}: {motivo}")
                else:
                    print(f"   [OK] {modulos[idx].titulo}")

        return ids_reais

    def _gerar_cache_key(self, documentos: str) -> str:
        """Gera chave de cache baseada nos documentos"""
        import hashlib
        return hashlib.md5(documentos.encode()).hexdigest()

    def _verificar_cache(self, cache_key: str) -> Optional[List[int]]:
        """Verifica se há resultado em cache válido"""
        if cache_key in self._cache:
            modulos_ids, timestamp = self._cache[cache_key]
            if datetime.now() - timestamp < self.cache_ttl:
                return modulos_ids
            else:
                # Cache expirado
                del self._cache[cache_key]
        return None

    def _salvar_cache(self, cache_key: str, modulos_ids: List[int]) -> None:
        """Salva resultado no cache"""
        self._cache[cache_key] = (modulos_ids, datetime.now())

    def limpar_cache(self) -> None:
        """Limpa todo o cache"""
        self._cache.clear()
        self._cache_tipo_peca.clear()
        print("[DEL] Cache de detecções limpo")
    
    async def detectar_tipo_peca(
        self,
        documentos_resumo: str
    ) -> Dict:
        """
        Analisa os documentos e determina automaticamente qual TIPO DE PEÇA
        é mais adequado para o caso.

        Args:
            documentos_resumo: Resumo consolidado dos documentos do processo

        Returns:
            Dict com tipo_peca detectado, justificativa e confiança
        """
        print(f"\n[AGENTE2] ========== INICIO detectar_tipo_peca ==========")
        print(f"[AGENTE2] Tamanho do resumo: {len(documentos_resumo)} chars")

        # Verificar cache
        cache_key = self._gerar_cache_key(f"tipo_peca:{documentos_resumo}")
        if cache_key in self._cache_tipo_peca:
            resultado, timestamp = self._cache_tipo_peca[cache_key]
            if datetime.now() - timestamp < self.cache_ttl:
                print(f"[AGENTE2] ✅ Cache hit - tipo de peça detectado anteriormente: {resultado.get('tipo_peca')}")
                return resultado
            else:
                del self._cache_tipo_peca[cache_key]

        print(f"[AGENTE2] Cache miss - buscando tipos de peça no banco...")

        # Buscar tipos de peça disponíveis no banco
        from admin.models_prompts import PromptModulo
        modulos_peca = self.db.query(PromptModulo).filter(
            PromptModulo.tipo == "peca",
            PromptModulo.ativo == True
        ).order_by(PromptModulo.ordem).all()

        print(f"[AGENTE2] Módulos de peça encontrados: {len(modulos_peca)}")

        if not modulos_peca:
            print("[AGENTE2] [WARN] Nenhum módulo de peça disponível no banco")
            return {
                "tipo_peca": None,
                "justificativa": "Nenhum tipo de peça configurado no sistema",
                "confianca": "baixa"
            }
        
        # Preparar lista de tipos disponíveis para a IA
        tipos_info = []
        for modulo in modulos_peca:
            # Usa condição de ativação ou início do conteúdo
            condicao = modulo.condicao_ativacao or ""
            if not condicao:
                condicao = modulo.conteudo[:300] + "..." if len(modulo.conteudo) > 300 else modulo.conteudo

            tipos_info.append({
                "nome": modulo.nome,      # ex: "contestacao", "recurso_apelacao" (identificador único)
                "titulo": modulo.titulo,  # ex: "Contestação", "Recurso de Apelação"
                "quando_usar": condicao
            })
        
        # Montar prompt de detecção
        prompt = f"""Você é um assistente jurídico especializado da Procuradoria-Geral do Estado de Mato Grosso do Sul (PGE-MS).

Sua tarefa é analisar os documentos de um processo judicial e determinar qual TIPO DE PEÇA JURÍDICA deve ser elaborada pela Procuradoria em defesa do Estado.

## DOCUMENTOS DO PROCESSO

{documentos_resumo}

## TIPOS DE PEÇA DISPONÍVEIS

```json
{json.dumps(tipos_info, ensure_ascii=False, indent=2)}
```

## SUA TAREFA

Analise os documentos e determine qual tipo de peça o Estado deve apresentar. Considere:

1. **Fase processual**: O processo está em fase de conhecimento (1º grau), recursal (2º grau)?
2. **Último ato processual**: Houve citação do Estado? Sentença? Recurso da parte contrária?
3. **Prazo**: Qual peça está dentro do prazo para apresentação?
4. **Posição do Estado**: O Estado é réu, apelante, apelado?

**REGRAS IMPORTANTES**:
- Se o Estado foi CITADO e ainda não contestou → CONTESTAÇÃO
- Se houve SENTENÇA DESFAVORÁVEL ao Estado → RECURSO DE APELAÇÃO  
- Se a parte adversa apresentou RECURSO → CONTRARRAZÕES
- Se é uma consulta interna ou análise → PARECER

## FORMATO DE RESPOSTA

Responda APENAS com um objeto JSON:

```json
{{
  "tipo_peca": "nome_do_tipo",
  "justificativa": "Breve explicação de por que este tipo de peça é adequado",
  "confianca": "alta|media|baixa"
}}
```

O campo "tipo_peca" deve conter EXATAMENTE um dos nomes disponíveis: {', '.join([t['nome'] for t in tipos_info])}

Responda SOMENTE com o JSON, sem texto adicional.
"""

        print(f"[AGENTE2] Prompt de detecção de tipo montado - tamanho: {len(prompt)} chars")

        try:
            print(f"[AGENTE2] >>> INICIANDO chamada à IA para detectar tipo de peça...")
            import time
            inicio_ia = time.time()

            resultado = await self._chamar_ia(prompt)

            tempo_ia = time.time() - inicio_ia
            print(f"[AGENTE2] <<< IA respondeu em {tempo_ia:.2f}s")
            print(f"[AGENTE2] Resultado bruto: {resultado}")

            tipo_detectado = resultado.get('tipo_peca')
            justificativa = resultado.get('justificativa', '')
            confianca = resultado.get('confianca', 'media')
            
            # Valida se o tipo retornado existe
            tipos_validos = [t['nome'] for t in tipos_info]
            if tipo_detectado not in tipos_validos:
                print(f"[WARN] Tipo detectado '{tipo_detectado}' não é válido. Tipos válidos: {tipos_validos}")
                # Tenta encontrar correspondência parcial
                for tipo in tipos_validos:
                    if tipo in str(tipo_detectado).lower() or str(tipo_detectado).lower() in tipo:
                        tipo_detectado = tipo
                        break
                else:
                    tipo_detectado = tipos_validos[0] if tipos_validos else None
                    confianca = "baixa"
            
            resultado_final = {
                "tipo_peca": tipo_detectado,
                "justificativa": justificativa,
                "confianca": confianca
            }
            
            print(f"[AGENTE2] 🎯 Tipo de peça detectado: {tipo_detectado}")
            print(f"[AGENTE2] 📊 Confiança: {confianca}")
            print(f"[AGENTE2]  Justificativa: {justificativa}")

            # Salvar no cache
            self._cache_tipo_peca[cache_key] = (resultado_final, datetime.now())

            print(f"[AGENTE2] ========== FIM detectar_tipo_peca ==========\n")
            return resultado_final

        except Exception as e:
            import traceback
            print(f"[AGENTE2] [ERRO] Erro na detecção de tipo de peça: {e}")
            print(f"[AGENTE2] Traceback: {traceback.format_exc()}")
            print(f"[AGENTE2] ========== FIM detectar_tipo_peca (com erro) ==========\n")
            # Fallback: retorna o primeiro tipo disponível
            return {
                "tipo_peca": tipos_info[0]['nome'] if tipos_info else None,
                "justificativa": f"Erro na detecção automática: {str(e)}. Usando tipo padrão.",
                "confianca": "baixa"
            }
