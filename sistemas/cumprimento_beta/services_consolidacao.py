# sistemas/cumprimento_beta/services_consolidacao.py
"""
Serviço de consolidação para o módulo Cumprimento de Sentença Beta.

Analisa todos os JSONs gerados pelo Agente 1 e produz:
- Resumo consolidado do cumprimento de sentença
- Sugestões de peças jurídicas possíveis
"""

import json
import logging
import time
from typing import List, Optional, Dict, Any, AsyncGenerator
from datetime import datetime
from sqlalchemy.orm import Session

from admin.models import ConfiguracaoIA
from sistemas.cumprimento_beta.models import (
    SessaoCumprimentoBeta, DocumentoBeta, JSONResumoBeta, ConsolidacaoBeta
)
from sistemas.cumprimento_beta.constants import (
    StatusSessao, StatusRelevancia, ConfigKeys,
    MODELO_PADRAO_AGENTE2, TIMEOUT_CONSOLIDACAO
)
from sistemas.cumprimento_beta.exceptions import ConsolidacaoError
from services.gemini_service import gemini_service, chamar_gemini

logger = logging.getLogger(__name__)


# Prompt padrão para consolidação
PROMPT_CONSOLIDACAO_PADRAO = """Você é um assistente jurídico especializado em cumprimento de sentença.

Analise os documentos do processo abaixo e produza:
1. Um RESUMO CONSOLIDADO do caso de cumprimento de sentença
2. Uma lista de SUGESTÕES DE PEÇAS que podem ser elaboradas

## DOCUMENTOS DO PROCESSO

{documentos_json}

## INSTRUÇÕES

### Resumo Consolidado
Produza um resumo executivo que inclua:
- Partes envolvidas (exequente, executado)
- Objeto da execução (o que está sendo cobrado/executado)
- Valor total envolvido (se aplicável)
- Status atual do cumprimento
- Principais eventos processuais
- Prazos relevantes

### Sugestões de Peças
Com base no estado atual do processo, sugira peças jurídicas que podem ser necessárias.
Para cada sugestão, explique brevemente o contexto.

## FORMATO DE RESPOSTA

Responda no seguinte formato JSON:

```json
{{
  "resumo_consolidado": "texto do resumo...",
  "dados_processo": {{
    "exequente": "nome ou null",
    "executado": "nome ou null",
    "valor_execucao": "valor ou null",
    "objeto": "descrição do objeto",
    "status": "status atual"
  }},
  "sugestoes_pecas": [
    {{
      "tipo": "nome da peça",
      "descricao": "breve descrição do contexto",
      "prioridade": "alta|media|baixa"
    }}
  ]
}}
```
"""


class ConsolidacaoService:
    """Serviço para consolidação de JSONs do Agente 2"""

    def __init__(self, db: Session):
        self.db = db
        self._modelo = self._carregar_modelo()
        self._prompt_customizado = self._carregar_prompt_customizado()

    def _carregar_modelo(self) -> str:
        """Carrega modelo configurado para o Agente 2"""
        try:
            config = self.db.query(ConfiguracaoIA).filter(
                ConfiguracaoIA.sistema == "cumprimento_beta",
                ConfiguracaoIA.chave == ConfigKeys.MODELO_AGENTE2
            ).first()

            if config and config.valor:
                logger.info(f"[BETA] Modelo Agente 2 carregado: {config.valor}")
                return config.valor

        except Exception as e:
            logger.warning(f"[BETA] Erro ao carregar modelo: {e}")

        logger.info(f"[BETA] Usando modelo padrão: {MODELO_PADRAO_AGENTE2}")
        return MODELO_PADRAO_AGENTE2

    def _carregar_prompt_customizado(self) -> Optional[str]:
        """Carrega prompt customizado do admin se existir"""
        try:
            config = self.db.query(ConfiguracaoIA).filter(
                ConfiguracaoIA.sistema == "cumprimento_beta",
                ConfiguracaoIA.chave == ConfigKeys.PROMPT_CONSOLIDACAO_BETA
            ).first()

            if config and config.valor:
                logger.info("[BETA] Prompt de consolidação customizado carregado")
                return config.valor

        except Exception as e:
            logger.warning(f"[BETA] Erro ao carregar prompt customizado: {e}")

        return None

    def _montar_documentos_json(self, jsons: List[JSONResumoBeta]) -> str:
        """Monta string com todos os JSONs para o prompt"""
        documentos = []

        for idx, json_resumo in enumerate(jsons, 1):
            doc = json_resumo.documento
            doc_info = {
                "numero": idx,
                "tipo": doc.descricao_documento or f"Código {doc.codigo_documento}",
                "data": doc.data_documento.strftime("%d/%m/%Y") if doc.data_documento else "Não informada",
                "conteudo": json_resumo.json_conteudo
            }
            documentos.append(json.dumps(doc_info, ensure_ascii=False, indent=2))

        return "\n\n---\n\n".join(documentos)

    def _get_prompt(self, documentos_json: str) -> str:
        """Retorna prompt completo para consolidação"""
        if self._prompt_customizado:
            # Usa prompt customizado se tiver placeholder
            if "{documentos_json}" in self._prompt_customizado:
                return self._prompt_customizado.format(documentos_json=documentos_json)
            # Senão, adiciona documentos no final
            return f"{self._prompt_customizado}\n\n## DOCUMENTOS\n\n{documentos_json}"

        return PROMPT_CONSOLIDACAO_PADRAO.format(documentos_json=documentos_json)

    async def consolidar_sessao(
        self,
        sessao: SessaoCumprimentoBeta
    ) -> Optional[ConsolidacaoBeta]:
        """
        Consolida todos os JSONs de uma sessão.

        Args:
            sessao: Sessão do beta

        Returns:
            ConsolidacaoBeta criada ou None se falhar
        """
        # Busca JSONs da sessão
        jsons = self.db.query(JSONResumoBeta).join(
            DocumentoBeta, JSONResumoBeta.documento_id == DocumentoBeta.id
        ).filter(
            DocumentoBeta.sessao_id == sessao.id
        ).all()

        if not jsons:
            logger.warning(f"[BETA] Nenhum JSON para consolidar na sessão {sessao.id}")
            return None

        logger.info(f"[BETA] Consolidando {len(jsons)} JSONs da sessão {sessao.id}")

        # Atualiza status
        sessao.status = StatusSessao.CONSOLIDANDO
        self.db.commit()

        # Monta prompt
        documentos_json = self._montar_documentos_json(jsons)
        prompt = self._get_prompt(documentos_json)

        inicio = time.time()

        try:
            # Chama Gemini
            resposta = await chamar_gemini(
                prompt=prompt,
                modelo=self._modelo
            )

            tempo_ms = int((time.time() - inicio) * 1000)

            # Extrai dados da resposta
            dados = self._extrair_dados_resposta(resposta)

            if not dados:
                logger.error(f"[BETA] Falha ao extrair dados da consolidação")
                return None

            # Cria consolidação
            consolidacao = ConsolidacaoBeta(
                sessao_id=sessao.id,
                resumo_consolidado=dados.get("resumo_consolidado", resposta),
                sugestoes_pecas=dados.get("sugestoes_pecas", []),
                dados_processo=dados.get("dados_processo"),
                modelo_usado=self._modelo,
                tempo_processamento_ms=tempo_ms,
                total_jsons_consolidados=len(jsons)
            )

            self.db.add(consolidacao)

            # Atualiza status da sessão
            sessao.status = StatusSessao.CHATBOT
            self.db.commit()

            logger.info(f"[BETA] Consolidação concluída em {tempo_ms}ms")

            return consolidacao

        except Exception as e:
            logger.error(f"[BETA] Erro na consolidação: {e}")
            sessao.status = StatusSessao.ERRO
            sessao.erro_mensagem = f"Erro na consolidação: {str(e)}"
            self.db.commit()
            raise ConsolidacaoError(f"Falha na consolidação: {e}")

    def _extrair_dados_resposta(self, resposta: str) -> Optional[Dict[str, Any]]:
        """Extrai dados estruturados da resposta"""
        if not resposta:
            return None

        try:
            import re

            # Tenta extrair JSON
            match = re.search(r'```(?:json)?\s*(\{.*\})\s*```', resposta, re.DOTALL)
            if match:
                return json.loads(match.group(1))

            # Tenta parsear resposta direta
            if resposta.strip().startswith("{"):
                return json.loads(resposta.strip())

            # Se não tem JSON, usa resposta como resumo
            return {
                "resumo_consolidado": resposta,
                "sugestoes_pecas": [],
                "dados_processo": None
            }

        except json.JSONDecodeError as e:
            logger.warning(f"[BETA] Erro ao parsear JSON da consolidação: {e}")
            return {
                "resumo_consolidado": resposta,
                "sugestoes_pecas": [],
                "dados_processo": None
            }

    async def consolidar_sessao_streaming(
        self,
        sessao: SessaoCumprimentoBeta
    ) -> AsyncGenerator[str, None]:
        """
        Consolida sessão com streaming de resposta.

        Yields:
            Chunks de texto conforme são gerados
        """
        # Busca JSONs da sessão
        jsons = self.db.query(JSONResumoBeta).join(
            DocumentoBeta, JSONResumoBeta.documento_id == DocumentoBeta.id
        ).filter(
            DocumentoBeta.sessao_id == sessao.id
        ).all()

        if not jsons:
            yield "Nenhum documento relevante encontrado para consolidar."
            return

        logger.info(f"[BETA] Consolidando {len(jsons)} JSONs com streaming")

        # Atualiza status
        sessao.status = StatusSessao.CONSOLIDANDO
        self.db.commit()

        # Monta prompt
        documentos_json = self._montar_documentos_json(jsons)
        prompt = self._get_prompt(documentos_json)

        resposta_completa = ""
        inicio = time.time()

        try:
            # Streaming do Gemini
            async for chunk in gemini_service.generate_stream(
                prompt=prompt,
                model=self._modelo
            ):
                resposta_completa += chunk
                yield chunk

            tempo_ms = int((time.time() - inicio) * 1000)

            # Extrai dados e salva consolidação
            dados = self._extrair_dados_resposta(resposta_completa)

            consolidacao = ConsolidacaoBeta(
                sessao_id=sessao.id,
                resumo_consolidado=dados.get("resumo_consolidado", resposta_completa) if dados else resposta_completa,
                sugestoes_pecas=dados.get("sugestoes_pecas", []) if dados else [],
                dados_processo=dados.get("dados_processo") if dados else None,
                modelo_usado=self._modelo,
                tempo_processamento_ms=tempo_ms,
                total_jsons_consolidados=len(jsons)
            )

            self.db.add(consolidacao)
            sessao.status = StatusSessao.CHATBOT
            self.db.commit()

            logger.info(f"[BETA] Consolidação streaming concluída em {tempo_ms}ms")

        except Exception as e:
            logger.error(f"[BETA] Erro na consolidação streaming: {e}")
            sessao.status = StatusSessao.ERRO
            sessao.erro_mensagem = f"Erro na consolidação: {str(e)}"
            self.db.commit()
            yield f"\n\n[ERRO: {str(e)}]"


async def consolidar_sessao(
    db: Session,
    sessao: SessaoCumprimentoBeta
) -> Optional[ConsolidacaoBeta]:
    """Função auxiliar para consolidar sessão"""
    service = ConsolidacaoService(db)
    return await service.consolidar_sessao(sessao)


async def consolidar_sessao_streaming(
    db: Session,
    sessao: SessaoCumprimentoBeta
) -> AsyncGenerator[str, None]:
    """Função auxiliar para consolidar sessão com streaming"""
    service = ConsolidacaoService(db)
    async for chunk in service.consolidar_sessao_streaming(sessao):
        yield chunk
