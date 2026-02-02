# sistemas/cumprimento_beta/agente1.py
"""
Agente 1 do módulo Cumprimento de Sentença Beta

Responsável por:
1. Download de documentos do TJ-MS
2. Filtro de códigos ignorados
3. Avaliação de relevância + Extração de JSON (UNIFICADO)

Pipeline: download -> filtro -> (relevância + extração em paralelo)

OTIMIZAÇÃO v2: Usa serviço unificado que:
- Combina relevância + extração em UMA ÚNICA chamada LLM por documento
- Paraleliza processamento de múltiplos documentos com asyncio.gather()
"""

import logging
from typing import Optional, Dict, Any, AsyncGenerator
from datetime import datetime
from sqlalchemy.orm import Session

from sistemas.cumprimento_beta.models import SessaoCumprimentoBeta, DocumentoBeta
from sistemas.cumprimento_beta.constants import StatusSessao, StatusRelevancia
from sistemas.cumprimento_beta.exceptions import (
    TJMSError, ProcessoInvalidoError, CumprimentoBetaError
)
from sistemas.cumprimento_beta.services_download import baixar_documentos_sessao
from sistemas.cumprimento_beta.services_processamento_unificado import processar_documentos_unificado

logger = logging.getLogger(__name__)


class Agente1:
    """
    Agente 1: Coleta, avalia e estrutura documentos.

    Orquestra o pipeline completo:
    1. Download de documentos do TJ-MS
    2. Filtragem por códigos ignorados
    3. Avaliação de relevância
    4. Extração de JSON para documentos relevantes
    """

    def __init__(self, db: Session):
        self.db = db

    async def processar_sessao(
        self,
        sessao: SessaoCumprimentoBeta,
        on_progress: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Processa uma sessão completa do Agente 1.

        Args:
            sessao: Sessão do beta a processar
            on_progress: Callback para progresso (opcional)
                Assinatura: async def on_progress(etapa, atual, total, mensagem)

        Returns:
            Dict com estatísticas do processamento

        Raises:
            TJMSError: Se falhar comunicação com TJ-MS
            CumprimentoBetaError: Se houver erro no processamento
        """
        logger.info(f"[AGENTE1] Iniciando processamento da sessão {sessao.id}")
        inicio = datetime.utcnow()

        resultado = {
            "sessao_id": sessao.id,
            "numero_processo": sessao.numero_processo,
            "etapas": {},
            "sucesso": False,
            "erro": None
        }

        try:
            # === ETAPA 1: Download de documentos ===
            logger.info("[AGENTE1] Etapa 1: Download de documentos")

            if on_progress:
                await on_progress(
                    etapa="iniciando",
                    atual=0,
                    total=2,
                    mensagem="Iniciando download de documentos..."
                )

            documentos = await baixar_documentos_sessao(
                db=self.db,
                sessao=sessao,
                on_progress=on_progress
            )

            resultado["etapas"]["download"] = {
                "total_documentos": len(documentos),
                "ignorados": sessao.documentos_ignorados
            }

            # Se não tem documentos, finaliza
            if not documentos:
                logger.warning(f"[AGENTE1] Nenhum documento encontrado para sessão {sessao.id}")
                sessao.status = StatusSessao.ERRO
                sessao.erro_mensagem = "Nenhum documento encontrado no processo"
                self.db.commit()

                resultado["erro"] = "Nenhum documento encontrado"
                return resultado

            # Conta documentos pendentes (não ignorados)
            docs_pendentes = [d for d in documentos if d.status_relevancia == StatusRelevancia.PENDENTE]

            if not docs_pendentes:
                logger.info(f"[AGENTE1] Todos os documentos foram ignorados na sessão {sessao.id}")
                sessao.status = StatusSessao.CONSOLIDANDO
                self.db.commit()

                resultado["etapas"]["processamento_unificado"] = {
                    "relevantes": 0,
                    "irrelevantes": 0,
                    "jsons_extraidos": 0
                }
                resultado["sucesso"] = True
                return resultado

            # === ETAPA 2: Avaliação de relevância + Extração de JSON (UNIFICADO) ===
            # OTIMIZAÇÃO: Uma única chamada LLM por documento + processamento paralelo
            logger.info(f"[AGENTE1] Etapa 2: Processando {len(docs_pendentes)} documentos (relevância + extração em paralelo)")

            if on_progress:
                await on_progress(
                    etapa="processando_documentos",
                    atual=1,
                    total=2,
                    mensagem=f"Processando {len(docs_pendentes)} documentos em paralelo..."
                )

            relevantes, irrelevantes = await processar_documentos_unificado(
                db=self.db,
                sessao=sessao,
                on_progress=on_progress
            )

            resultado["etapas"]["processamento_unificado"] = {
                "relevantes": relevantes,
                "irrelevantes": irrelevantes,
                "jsons_extraidos": relevantes  # JSONs são criados junto com a avaliação
            }

            # === FINALIZAÇÃO ===
            sessao.status = StatusSessao.CONSOLIDANDO
            self.db.commit()

            fim = datetime.utcnow()
            duracao = (fim - inicio).total_seconds()

            resultado["sucesso"] = True
            resultado["duracao_segundos"] = duracao

            logger.info(
                f"[AGENTE1] Sessão {sessao.id} processada em {duracao:.1f}s: "
                f"{len(documentos)} docs, {relevantes} relevantes, {relevantes} JSONs"
            )

            if on_progress:
                await on_progress(
                    etapa="concluido",
                    atual=2,
                    total=2,
                    mensagem=f"Processamento concluído: {relevantes} documentos estruturados"
                )

            return resultado

        except TJMSError as e:
            logger.error(f"[AGENTE1] Erro TJ-MS na sessão {sessao.id}: {e}")
            sessao.status = StatusSessao.ERRO
            sessao.erro_mensagem = str(e)
            self.db.commit()

            resultado["erro"] = str(e)
            raise

        except Exception as e:
            logger.error(f"[AGENTE1] Erro inesperado na sessão {sessao.id}: {e}")
            sessao.status = StatusSessao.ERRO
            sessao.erro_mensagem = f"Erro no processamento: {str(e)}"
            self.db.commit()

            resultado["erro"] = str(e)
            raise CumprimentoBetaError(f"Erro no Agente 1: {e}")


async def processar_agente1(
    db: Session,
    sessao: SessaoCumprimentoBeta,
    on_progress: Optional[callable] = None
) -> Dict[str, Any]:
    """
    Função auxiliar para processar Agente 1.

    Args:
        db: Sessão do banco de dados
        sessao: Sessão do beta
        on_progress: Callback para progresso

    Returns:
        Dict com estatísticas do processamento
    """
    agente = Agente1(db)
    return await agente.processar_sessao(sessao, on_progress)


async def processar_agente1_streaming(
    db: Session,
    sessao: SessaoCumprimentoBeta
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Processa Agente 1 com streaming de progresso.

    Yields eventos de progresso no formato:
    {
        "event": "progresso"|"documento_processado"|"erro"|"concluido",
        "data": {...}
    }
    """
    agente = Agente1(db)

    async def on_progress(etapa: str, atual: int, total: int, mensagem: str):
        # Este callback será chamado pelo agente, mas para streaming
        # precisamos de outra abordagem
        pass

    try:
        # Inicia processamento
        yield {
            "event": "inicio",
            "data": {
                "sessao_id": sessao.id,
                "numero_processo": sessao.numero_processo
            }
        }

        resultado = await agente.processar_sessao(sessao)

        yield {
            "event": "concluido",
            "data": resultado
        }

    except Exception as e:
        yield {
            "event": "erro",
            "data": {
                "mensagem": str(e),
                "sessao_id": sessao.id
            }
        }
