# sistemas/cumprimento_beta/services_processamento_unificado.py
"""
Serviço unificado de processamento de documentos para o módulo beta.

OTIMIZAÇÃO: Combina avaliação de relevância + extração de JSON em UMA ÚNICA chamada.
Também paraleliza o processamento de múltiplos documentos usando asyncio.gather().

Autor: LAB/PGE-MS
"""

import asyncio
import json
import logging
import time
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from dataclasses import dataclass
from sqlalchemy.orm import Session

from admin.models import ConfiguracaoIA
from sistemas.cumprimento_beta.models import SessaoCumprimentoBeta, DocumentoBeta, JSONResumoBeta
from sistemas.cumprimento_beta.constants import (
    StatusSessao, StatusRelevancia, ConfigKeys, CATEGORIA_CUMPRIMENTO_SENTENCA,
    MODELO_PADRAO_AGENTE1
)
from sistemas.gerador_pecas.extrator_resumo_json import obter_criterios_relevancia
from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON
from sistemas.gerador_pecas.gemini_client import chamar_gemini_async

logger = logging.getLogger(__name__)


# Prompt unificado: avalia relevância E extrai JSON em uma única chamada
PROMPT_UNIFICADO = """Você é um assistente jurídico especializado em análise de documentos para cumprimento de sentença.

Analise o documento abaixo e faça DUAS tarefas:

1. **AVALIAR RELEVÂNCIA**: Determine se o documento é relevante para cumprimento de sentença
2. **EXTRAIR INFORMAÇÕES**: Se relevante, extraia informações estruturadas

{criterios_relevancia}

## DOCUMENTO A ANALISAR

**ID:** {documento_id}
**Tipo:** {tipo_documento}
**Data:** {data_documento}

**Conteúdo:**
{conteudo}

## FORMATO DE RESPOSTA

Responda com um JSON no seguinte formato:

```json
{{
  "relevante": true ou false,
  "motivo_classificacao": "breve explicação da classificação",
  "dados_extraidos": {{
    "resumo": "resumo do conteúdo principal (ou null se irrelevante)",
    "pontos_relevantes": ["lista de pontos relevantes (ou [] se irrelevante)"],
    "pedidos_ou_determinacoes": ["lista de pedidos/determinações encontradas"],
    "valores_mencionados": ["R$ X.XXX,XX - descrição do valor"],
    "prazos_mencionados": ["DD/MM/YYYY - descrição do prazo"],
    "partes_mencionadas": ["Nome - qualificação da parte"],
    "observacoes": "observações adicionais relevantes"
  }}
}}
```

{instrucoes_categoria}

IMPORTANTE:
- Se o documento for IRRELEVANTE, preencha dados_extraidos com valores vazios/null
- Se for RELEVANTE, extraia o máximo de informações úteis
- Retorne APENAS o JSON, sem markdown ou explicações adicionais
"""


# Schema padrão para extração
SCHEMA_PADRAO = {
    "resumo": "string ou null",
    "pontos_relevantes": [],
    "pedidos_ou_determinacoes": [],
    "valores_mencionados": [],
    "prazos_mencionados": [],
    "partes_mencionadas": [],
    "observacoes": "string ou null"
}


@dataclass
class ResultadoProcessamento:
    """Resultado do processamento de um documento"""
    documento_id: int
    relevante: bool
    motivo: str
    dados_extraidos: Optional[Dict[str, Any]] = None
    erro: Optional[str] = None
    tempo_ms: int = 0


class ProcessamentoUnificadoService:
    """
    Serviço unificado que avalia relevância e extrai JSON em uma única chamada.

    Benefícios:
    - Reduz pela metade o número de chamadas à API
    - Paraleliza processamento de múltiplos documentos
    - Mantém consistência entre avaliação e extração
    """

    def __init__(self, db: Session):
        self.db = db
        self._modelo = self._carregar_modelo()
        self._criterios = self._carregar_criterios()
        self._categoria = self._carregar_categoria()
        self._max_concurrent = 20  # Máximo de chamadas paralelas

    def _carregar_modelo(self) -> str:
        """Carrega modelo configurado para o Agente 1"""
        try:
            config = self.db.query(ConfiguracaoIA).filter(
                ConfiguracaoIA.sistema == "cumprimento_beta",
                ConfiguracaoIA.chave == ConfigKeys.MODELO_AGENTE1
            ).first()

            if config and config.valor:
                return config.valor

        except Exception as e:
            logger.warning(f"[BETA] Erro ao carregar modelo: {e}")

        return MODELO_PADRAO_AGENTE1

    def _carregar_criterios(self) -> str:
        """Carrega critérios de relevância do admin"""
        return obter_criterios_relevancia(self.db)

    def _carregar_categoria(self) -> Optional[CategoriaResumoJSON]:
        """Carrega categoria de cumprimento de sentença"""
        try:
            categoria = self.db.query(CategoriaResumoJSON).filter(
                CategoriaResumoJSON.nome == CATEGORIA_CUMPRIMENTO_SENTENCA,
                CategoriaResumoJSON.ativo == True
            ).first()

            if not categoria:
                # Tenta variações do nome
                categoria = self.db.query(CategoriaResumoJSON).filter(
                    CategoriaResumoJSON.nome.ilike("%cumprimento%sentenca%"),
                    CategoriaResumoJSON.ativo == True
                ).first()

            return categoria

        except Exception as e:
            logger.warning(f"[BETA] Erro ao carregar categoria: {e}")
            return None

    def _get_instrucoes_categoria(self) -> str:
        """Retorna instruções adicionais da categoria se existir"""
        if self._categoria and self._categoria.instrucoes_extracao:
            return f"## INSTRUÇÕES ADICIONAIS\n\n{self._categoria.instrucoes_extracao}"
        return ""

    async def processar_documento(
        self,
        documento: DocumentoBeta
    ) -> ResultadoProcessamento:
        """
        Processa um documento: avalia relevância E extrai JSON em uma única chamada.

        Args:
            documento: Documento a processar

        Returns:
            ResultadoProcessamento com resultado completo
        """
        inicio = time.time()

        # Se não tem conteúdo suficiente, marca como irrelevante sem chamar LLM
        if not documento.conteudo_texto or len(documento.conteudo_texto.strip()) < 50:
            return ResultadoProcessamento(
                documento_id=documento.id,
                relevante=False,
                motivo="Documento sem conteúdo textual suficiente",
                tempo_ms=int((time.time() - inicio) * 1000)
            )

        # Monta prompt unificado
        prompt = PROMPT_UNIFICADO.format(
            criterios_relevancia=self._criterios,
            documento_id=documento.documento_id_tjms,
            tipo_documento=documento.descricao_documento or f"Código {documento.codigo_documento}",
            data_documento=documento.data_documento.strftime("%d/%m/%Y") if documento.data_documento else "Não informada",
            conteudo=documento.conteudo_texto[:12000],  # Limita tamanho
            instrucoes_categoria=self._get_instrucoes_categoria()
        )

        try:
            # Uma única chamada para relevância + extração
            resposta = await chamar_gemini_async(
                prompt=prompt,
                modelo=self._modelo
            )

            tempo_ms = int((time.time() - inicio) * 1000)

            # Extrai JSON da resposta
            resultado = self._extrair_json_resposta(resposta)

            if resultado is None:
                return ResultadoProcessamento(
                    documento_id=documento.id,
                    relevante=False,
                    motivo="Não foi possível processar a resposta da IA",
                    erro="Falha ao extrair JSON da resposta",
                    tempo_ms=tempo_ms
                )

            relevante = resultado.get("relevante", False)
            motivo = resultado.get("motivo_classificacao", "Sem motivo informado")
            dados = resultado.get("dados_extraidos") if relevante else None

            return ResultadoProcessamento(
                documento_id=documento.id,
                relevante=relevante,
                motivo=motivo,
                dados_extraidos=dados,
                tempo_ms=tempo_ms
            )

        except Exception as e:
            tempo_ms = int((time.time() - inicio) * 1000)
            logger.error(f"[BETA] Erro ao processar documento {documento.id}: {e}")
            return ResultadoProcessamento(
                documento_id=documento.id,
                relevante=False,
                motivo=f"Erro no processamento: {str(e)}",
                erro=str(e),
                tempo_ms=tempo_ms
            )

    def _extrair_json_resposta(self, resposta: str) -> Optional[Dict[str, Any]]:
        """Extrai JSON da resposta do Gemini"""
        if not resposta:
            return None

        try:
            import re

            texto = resposta.strip()

            # Remove ```json ... ```
            match = re.search(r'```(?:json)?\s*(\{.*\})\s*```', texto, re.DOTALL)
            if match:
                texto = match.group(1)

            # Tenta parsear
            dados = json.loads(texto)

            if not isinstance(dados, dict):
                return None

            # Valida estrutura mínima
            if "relevante" not in dados:
                return None

            return dados

        except json.JSONDecodeError as e:
            logger.warning(f"[BETA] JSON inválido: {e}")
            return None

    async def processar_documentos_paralelo(
        self,
        documentos: List[DocumentoBeta],
        on_progress: Optional[callable] = None
    ) -> List[ResultadoProcessamento]:
        """
        Processa múltiplos documentos em paralelo.

        Args:
            documentos: Lista de documentos a processar
            on_progress: Callback para progresso

        Returns:
            Lista de ResultadoProcessamento
        """
        if not documentos:
            return []

        total = len(documentos)
        logger.info(f"[BETA] Processando {total} documentos em paralelo (max {self._max_concurrent} simultâneos)")

        resultados = []
        processados = 0

        # Processa em batches para controlar concorrência
        for i in range(0, total, self._max_concurrent):
            batch = documentos[i:i + self._max_concurrent]

            # Executa batch em paralelo
            tasks = [self.processar_documento(doc) for doc in batch]
            batch_resultados = await asyncio.gather(*tasks, return_exceptions=True)

            # Processa resultados do batch
            for idx, resultado in enumerate(batch_resultados):
                if isinstance(resultado, Exception):
                    # Converte exceção em ResultadoProcessamento com erro
                    doc = batch[idx]
                    resultado = ResultadoProcessamento(
                        documento_id=doc.id,
                        relevante=False,
                        motivo=f"Erro: {str(resultado)}",
                        erro=str(resultado)
                    )

                resultados.append(resultado)
                processados += 1

                if on_progress:
                    await on_progress(
                        etapa="processando_documentos",
                        atual=processados,
                        total=total,
                        mensagem=f"Processando documento {processados}/{total}"
                    )

            # Commit parcial a cada batch
            self.db.commit()

        return resultados

    async def processar_sessao(
        self,
        sessao: SessaoCumprimentoBeta,
        on_progress: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Processa todos os documentos pendentes de uma sessão.

        Args:
            sessao: Sessão do beta
            on_progress: Callback para progresso

        Returns:
            Dict com estatísticas do processamento
        """
        # Busca documentos pendentes (não ignorados)
        documentos = self.db.query(DocumentoBeta).filter(
            DocumentoBeta.sessao_id == sessao.id,
            DocumentoBeta.status_relevancia == StatusRelevancia.PENDENTE
        ).all()

        if not documentos:
            logger.info(f"[BETA] Nenhum documento pendente na sessão {sessao.id}")
            return {
                "total": 0,
                "relevantes": 0,
                "irrelevantes": 0,
                "erros": 0
            }

        logger.info(f"[BETA] Processando {len(documentos)} documentos da sessão {sessao.id}")

        # Atualiza status
        sessao.status = StatusSessao.AVALIANDO_RELEVANCIA
        self.db.commit()

        # Processa em paralelo
        resultados = await self.processar_documentos_paralelo(documentos, on_progress)

        # Aplica resultados aos documentos
        relevantes = 0
        irrelevantes = 0
        erros = 0
        jsons_criados = 0

        doc_map = {d.id: d for d in documentos}

        for resultado in resultados:
            doc = doc_map.get(resultado.documento_id)
            if not doc:
                continue

            doc.modelo_avaliacao = self._modelo
            doc.avaliado_em = datetime.utcnow()

            if resultado.erro:
                erros += 1
                doc.status_relevancia = StatusRelevancia.IRRELEVANTE
                doc.motivo_irrelevancia = resultado.motivo
                continue

            if resultado.relevante:
                doc.status_relevancia = StatusRelevancia.RELEVANTE
                relevantes += 1
                sessao.documentos_relevantes = (sessao.documentos_relevantes or 0) + 1

                # Cria JSON se tiver dados extraídos
                if resultado.dados_extraidos:
                    json_resumo = JSONResumoBeta(
                        documento_id=doc.id,
                        json_conteudo=resultado.dados_extraidos,
                        categoria_id=self._categoria.id if self._categoria else None,
                        categoria_nome=self._categoria.nome if self._categoria else "padrao",
                        modelo_usado=self._modelo,
                        tempo_processamento_ms=resultado.tempo_ms,
                        json_valido=True
                    )
                    self.db.add(json_resumo)
                    jsons_criados += 1

            else:
                doc.status_relevancia = StatusRelevancia.IRRELEVANTE
                doc.motivo_irrelevancia = resultado.motivo
                irrelevantes += 1
                sessao.documentos_irrelevantes = (sessao.documentos_irrelevantes or 0) + 1

        # Commit final
        self.db.commit()

        logger.info(
            f"[BETA] Sessão {sessao.id} processada: "
            f"{relevantes} relevantes, {irrelevantes} irrelevantes, "
            f"{jsons_criados} JSONs criados, {erros} erros"
        )

        return {
            "total": len(documentos),
            "relevantes": relevantes,
            "irrelevantes": irrelevantes,
            "jsons_criados": jsons_criados,
            "erros": erros
        }


async def processar_documentos_unificado(
    db: Session,
    sessao: SessaoCumprimentoBeta,
    on_progress: Optional[callable] = None
) -> Tuple[int, int]:
    """
    Função auxiliar para processar documentos com o serviço unificado.

    Substitui as chamadas separadas de avaliar_relevancia_sessao + extrair_jsons_sessao.

    Args:
        db: Sessão do banco de dados
        sessao: Sessão do beta
        on_progress: Callback para progresso

    Returns:
        Tuple (relevantes, irrelevantes)
    """
    service = ProcessamentoUnificadoService(db)
    resultado = await service.processar_sessao(sessao, on_progress)
    return resultado["relevantes"], resultado["irrelevantes"]
