# sistemas/cumprimento_beta/agente2.py
"""
Agente 2 do módulo Cumprimento de Sentença Beta

Responsável por:
1. Coletar todos os JSONs gerados pelo Agente 1
2. Consolidar informações em resumo único
3. Gerar sugestões de peças jurídicas
4. Preparar contexto para o chatbot

Pipeline: coleta JSONs -> consolidação -> sugestões
"""

import logging
from typing import Optional, Dict, Any, AsyncGenerator
from datetime import datetime
from sqlalchemy.orm import Session

from sistemas.cumprimento_beta.models import (
    SessaoCumprimentoBeta, DocumentoBeta, JSONResumoBeta, ConsolidacaoBeta
)
from sistemas.cumprimento_beta.constants import StatusSessao, StatusRelevancia
from sistemas.cumprimento_beta.exceptions import ConsolidacaoError, CumprimentoBetaError
from sistemas.cumprimento_beta.services_consolidacao import (
    consolidar_sessao, consolidar_sessao_streaming
)

logger = logging.getLogger(__name__)


class Agente2:
    """
    Agente 2: Consolida e sugere peças.

    Orquestra o pipeline:
    1. Coleta JSONs do Agente 1
    2. Gera resumo consolidado
    3. Sugere peças jurídicas
    """

    def __init__(self, db: Session):
        self.db = db

    def _verificar_jsons_disponiveis(self, sessao: SessaoCumprimentoBeta) -> int:
        """Verifica quantos JSONs estão disponíveis"""
        count = self.db.query(JSONResumoBeta).join(
            DocumentoBeta, JSONResumoBeta.documento_id == DocumentoBeta.id
        ).filter(
            DocumentoBeta.sessao_id == sessao.id
        ).count()

        return count

    async def processar_sessao(
        self,
        sessao: SessaoCumprimentoBeta
    ) -> Dict[str, Any]:
        """
        Processa consolidação de uma sessão.

        Args:
            sessao: Sessão do beta a processar

        Returns:
            Dict com resultado da consolidação
        """
        logger.info(f"[AGENTE2] Iniciando consolidação da sessão {sessao.id}")
        inicio = datetime.utcnow()

        resultado = {
            "sessao_id": sessao.id,
            "sucesso": False,
            "erro": None
        }

        try:
            # Verifica se há JSONs para consolidar
            total_jsons = self._verificar_jsons_disponiveis(sessao)

            if total_jsons == 0:
                logger.warning(f"[AGENTE2] Nenhum JSON disponível na sessão {sessao.id}")
                resultado["erro"] = "Nenhum documento relevante para consolidar"

                # Cria consolidação vazia
                consolidacao = ConsolidacaoBeta(
                    sessao_id=sessao.id,
                    resumo_consolidado="Nenhum documento relevante foi encontrado no processo para análise de cumprimento de sentença.",
                    sugestoes_pecas=[],
                    modelo_usado="nenhum",
                    total_jsons_consolidados=0
                )
                self.db.add(consolidacao)
                sessao.status = StatusSessao.CHATBOT
                self.db.commit()

                resultado["sucesso"] = True
                resultado["consolidacao_id"] = consolidacao.id
                return resultado

            # Executa consolidação
            consolidacao = await consolidar_sessao(self.db, sessao)

            if consolidacao:
                resultado["sucesso"] = True
                resultado["consolidacao_id"] = consolidacao.id
                resultado["total_jsons"] = total_jsons
                resultado["sugestoes"] = consolidacao.sugestoes_pecas

                fim = datetime.utcnow()
                resultado["duracao_segundos"] = (fim - inicio).total_seconds()

                logger.info(
                    f"[AGENTE2] Consolidação concluída: {total_jsons} JSONs, "
                    f"{len(consolidacao.sugestoes_pecas or [])} sugestões"
                )
            else:
                resultado["erro"] = "Falha na consolidação"

            return resultado

        except ConsolidacaoError as e:
            logger.error(f"[AGENTE2] Erro de consolidação: {e}")
            resultado["erro"] = str(e)
            raise

        except Exception as e:
            logger.error(f"[AGENTE2] Erro inesperado: {e}")
            resultado["erro"] = str(e)
            raise CumprimentoBetaError(f"Erro no Agente 2: {e}")

    async def processar_sessao_streaming(
        self,
        sessao: SessaoCumprimentoBeta
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Processa consolidação com streaming de resposta.

        Yields:
            Eventos de streaming no formato:
            {
                "event": "chunk"|"concluido"|"erro",
                "data": {...}
            }
        """
        logger.info(f"[AGENTE2] Iniciando consolidação streaming da sessão {sessao.id}")

        try:
            # Verifica JSONs disponíveis
            total_jsons = self._verificar_jsons_disponiveis(sessao)

            yield {
                "event": "inicio",
                "data": {
                    "sessao_id": sessao.id,
                    "total_jsons": total_jsons
                }
            }

            if total_jsons == 0:
                yield {
                    "event": "chunk",
                    "data": {
                        "texto": "Nenhum documento relevante foi encontrado no processo para análise."
                    }
                }

                # Cria consolidação vazia
                consolidacao = ConsolidacaoBeta(
                    sessao_id=sessao.id,
                    resumo_consolidado="Nenhum documento relevante foi encontrado.",
                    sugestoes_pecas=[],
                    modelo_usado="nenhum",
                    total_jsons_consolidados=0
                )
                self.db.add(consolidacao)
                sessao.status = StatusSessao.CHATBOT
                self.db.commit()

                yield {
                    "event": "concluido",
                    "data": {
                        "consolidacao_id": consolidacao.id,
                        "sugestoes": []
                    }
                }
                return

            # Streaming da consolidação
            async for chunk in consolidar_sessao_streaming(self.db, sessao):
                yield {
                    "event": "chunk",
                    "data": {"texto": chunk}
                }

            # Busca consolidação criada
            consolidacao = self.db.query(ConsolidacaoBeta).filter(
                ConsolidacaoBeta.sessao_id == sessao.id
            ).first()

            yield {
                "event": "concluido",
                "data": {
                    "consolidacao_id": consolidacao.id if consolidacao else None,
                    "sugestoes": consolidacao.sugestoes_pecas if consolidacao else []
                }
            }

        except Exception as e:
            logger.error(f"[AGENTE2] Erro no streaming: {e}")
            yield {
                "event": "erro",
                "data": {"mensagem": str(e)}
            }


async def processar_agente2(
    db: Session,
    sessao: SessaoCumprimentoBeta
) -> Dict[str, Any]:
    """Função auxiliar para processar Agente 2"""
    agente = Agente2(db)
    return await agente.processar_sessao(sessao)


async def processar_agente2_streaming(
    db: Session,
    sessao: SessaoCumprimentoBeta
) -> AsyncGenerator[Dict[str, Any], None]:
    """Função auxiliar para processar Agente 2 com streaming"""
    agente = Agente2(db)
    async for evento in agente.processar_sessao_streaming(sessao):
        yield evento
