# sistemas/classificador_documentos/watchdog.py
"""
Watchdog para detecção de execuções travadas no Classificador de Documentos.

Conforme ADR-0010: Sistema de Recuperação de Execuções Travadas

Funcionalidades:
- Detecta execuções sem progresso por mais de 5 minutos
- Marca execuções como TRAVADO
- Registra logs detalhados
- Pode ser executado como background task

Autor: LAB/PGE-MS
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from sqlalchemy.orm import Session

from utils.timezone import get_utc_now

from .models import (
    ExecucaoClassificacao,
    ResultadoClassificacao,
    StatusExecucao,
    StatusArquivo
)

logger = logging.getLogger(__name__)


# Configurações do watchdog
HEARTBEAT_TIMEOUT_MINUTES = 5  # Tempo sem heartbeat para considerar travado
PROCESSANDO_TIMEOUT_MINUTES = 2  # Tempo máximo para um documento em PROCESSANDO
CHECK_INTERVAL_SECONDS = 60  # Intervalo entre verificações


class ClassificadorWatchdog:
    """
    Watchdog para detectar e tratar execuções travadas.

    Uso:
        watchdog = ClassificadorWatchdog(db)

        # Verificação única
        travadas = await watchdog.verificar_execucoes_travadas()

        # Loop contínuo (background)
        await watchdog.iniciar_monitoramento()
    """

    def __init__(self, db: Session):
        self.db = db
        self._rodando = False

    async def verificar_execucoes_travadas(self) -> List[Dict[str, Any]]:
        """
        Verifica e marca execuções que estão travadas.

        Critérios de travamento:
        1. Status EM_ANDAMENTO sem heartbeat por mais de HEARTBEAT_TIMEOUT_MINUTES
        2. Documentos em PROCESSANDO por mais de PROCESSANDO_TIMEOUT_MINUTES

        Returns:
            Lista de execuções que foram marcadas como travadas
        """
        logger.info("[WATCHDOG] Iniciando verificação de execuções travadas")

        travadas = []
        agora = get_utc_now()
        limite_heartbeat = agora - timedelta(minutes=HEARTBEAT_TIMEOUT_MINUTES)

        # Busca execuções em andamento
        execucoes_em_andamento = self.db.query(ExecucaoClassificacao).filter(
            ExecucaoClassificacao.status == StatusExecucao.EM_ANDAMENTO.value
        ).all()

        logger.info(f"[WATCHDOG] Encontradas {len(execucoes_em_andamento)} execuções em andamento")

        for execucao in execucoes_em_andamento:
            motivo_travamento = None

            # Verifica heartbeat
            if execucao.ultimo_heartbeat:
                if execucao.ultimo_heartbeat < limite_heartbeat:
                    tempo_sem_heartbeat = agora - execucao.ultimo_heartbeat
                    motivo_travamento = f"Sem heartbeat por {tempo_sem_heartbeat.total_seconds() / 60:.1f} minutos"
            else:
                # Se não tem heartbeat mas iniciou há mais de HEARTBEAT_TIMEOUT_MINUTES
                if execucao.iniciado_em and execucao.iniciado_em < limite_heartbeat:
                    tempo_desde_inicio = agora - execucao.iniciado_em
                    motivo_travamento = f"Sem heartbeat desde o início ({tempo_desde_inicio.total_seconds() / 60:.1f} min)"

            # Verifica documentos travados em PROCESSANDO
            if not motivo_travamento:
                docs_processando = self._verificar_documentos_travados(execucao.id)
                if docs_processando:
                    motivo_travamento = f"{len(docs_processando)} documento(s) travado(s) em PROCESSANDO"

            if motivo_travamento:
                logger.warning(
                    f"[WATCHDOG] Execução {execucao.id} travada: {motivo_travamento}"
                )

                # Marca como travada
                execucao.status = StatusExecucao.TRAVADO.value
                execucao.erro_mensagem = f"Travamento detectado: {motivo_travamento}"

                # Marca documentos em PROCESSANDO como ERRO
                self._marcar_documentos_processando_como_erro(execucao.id)

                travadas.append({
                    "execucao_id": execucao.id,
                    "projeto_id": execucao.projeto_id,
                    "motivo": motivo_travamento,
                    "ultimo_heartbeat": execucao.ultimo_heartbeat.isoformat() if execucao.ultimo_heartbeat else None,
                    "ultimo_codigo": execucao.ultimo_codigo_processado,
                    "processados": execucao.arquivos_processados,
                    "total": execucao.total_arquivos,
                    "rota_origem": execucao.rota_origem
                })

        if travadas:
            self.db.commit()
            logger.warning(f"[WATCHDOG] {len(travadas)} execução(ões) marcada(s) como travada(s)")
        else:
            logger.info("[WATCHDOG] Nenhuma execução travada encontrada")

        return travadas

    def _verificar_documentos_travados(self, execucao_id: int) -> List[ResultadoClassificacao]:
        """Verifica documentos que estão em PROCESSANDO por muito tempo."""
        agora = get_utc_now()
        limite = agora - timedelta(minutes=PROCESSANDO_TIMEOUT_MINUTES)

        return self.db.query(ResultadoClassificacao).filter(
            ResultadoClassificacao.execucao_id == execucao_id,
            ResultadoClassificacao.status == StatusArquivo.PROCESSANDO.value,
            ResultadoClassificacao.criado_em < limite
        ).all()

    def _marcar_documentos_processando_como_erro(self, execucao_id: int) -> int:
        """Marca documentos em PROCESSANDO como ERRO."""
        agora = get_utc_now()

        docs = self.db.query(ResultadoClassificacao).filter(
            ResultadoClassificacao.execucao_id == execucao_id,
            ResultadoClassificacao.status == StatusArquivo.PROCESSANDO.value
        ).all()

        for doc in docs:
            doc.status = StatusArquivo.ERRO.value
            doc.erro_mensagem = "Travamento detectado pelo watchdog"
            doc.ultimo_erro_em = agora
            doc.tentativas += 1

        return len(docs)

    async def obter_status_detalhado(self, execucao_id: int) -> Optional[Dict[str, Any]]:
        """
        Obtém status detalhado de uma execução incluindo informações de travamento.

        Returns:
            Dicionário com status detalhado ou None se não encontrada
        """
        execucao = self.db.query(ExecucaoClassificacao).filter(
            ExecucaoClassificacao.id == execucao_id
        ).first()

        if not execucao:
            return None

        # Conta documentos por status
        contagem_status = {}
        for status in StatusArquivo:
            count = self.db.query(ResultadoClassificacao).filter(
                ResultadoClassificacao.execucao_id == execucao_id,
                ResultadoClassificacao.status == status.value
            ).count()
            contagem_status[status.value] = count

        # Lista documentos com erro
        docs_erro = self.db.query(ResultadoClassificacao).filter(
            ResultadoClassificacao.execucao_id == execucao_id,
            ResultadoClassificacao.status == StatusArquivo.ERRO.value
        ).all()

        return {
            "execucao_id": execucao.id,
            "projeto_id": execucao.projeto_id,
            "status": execucao.status,
            "rota_origem": execucao.rota_origem,
            "total_arquivos": execucao.total_arquivos,
            "arquivos_processados": execucao.arquivos_processados,
            "arquivos_sucesso": execucao.arquivos_sucesso,
            "arquivos_erro": execucao.arquivos_erro,
            "progresso_percentual": execucao.progresso_percentual,
            "contagem_por_status": contagem_status,
            "ultimo_heartbeat": execucao.ultimo_heartbeat.isoformat() if execucao.ultimo_heartbeat else None,
            "ultimo_codigo_processado": execucao.ultimo_codigo_processado,
            "tentativas_retry": execucao.tentativas_retry,
            "max_retries": execucao.max_retries,
            "pode_retomar": execucao.pode_retomar,
            "esta_travada": execucao.esta_travada if execucao.status == StatusExecucao.EM_ANDAMENTO.value else False,
            "erro_mensagem": execucao.erro_mensagem,
            "iniciado_em": execucao.iniciado_em.isoformat() if execucao.iniciado_em else None,
            "finalizado_em": execucao.finalizado_em.isoformat() if execucao.finalizado_em else None,
            "documentos_com_erro": [
                {
                    "id": doc.id,
                    "codigo": doc.codigo_documento,
                    "nome_arquivo": doc.nome_arquivo,
                    "erro_mensagem": doc.erro_mensagem,
                    "tentativas": doc.tentativas,
                    "ultimo_erro_em": doc.ultimo_erro_em.isoformat() if doc.ultimo_erro_em else None,
                    "pode_reprocessar": doc.pode_reprocessar
                }
                for doc in docs_erro
            ]
        }

    async def listar_erros(self, execucao_id: int) -> List[Dict[str, Any]]:
        """
        Lista todos os documentos com erro de uma execução.

        Returns:
            Lista de documentos com detalhes do erro
        """
        docs = self.db.query(ResultadoClassificacao).filter(
            ResultadoClassificacao.execucao_id == execucao_id,
            ResultadoClassificacao.status == StatusArquivo.ERRO.value
        ).order_by(ResultadoClassificacao.ultimo_erro_em.desc()).all()

        return [
            {
                "id": doc.id,
                "codigo_documento": doc.codigo_documento,
                "numero_processo": doc.numero_processo,
                "nome_arquivo": doc.nome_arquivo,
                "erro_mensagem": doc.erro_mensagem,
                "erro_stack": doc.erro_stack,
                "tentativas": doc.tentativas,
                "ultimo_erro_em": doc.ultimo_erro_em.isoformat() if doc.ultimo_erro_em else None,
                "pode_reprocessar": doc.pode_reprocessar,
                "criado_em": doc.criado_em.isoformat() if doc.criado_em else None
            }
            for doc in docs
        ]

    async def iniciar_monitoramento(self):
        """
        Inicia loop de monitoramento contínuo.

        Executa verificações periódicas no intervalo CHECK_INTERVAL_SECONDS.
        """
        self._rodando = True
        logger.info(f"[WATCHDOG] Iniciando monitoramento contínuo (intervalo: {CHECK_INTERVAL_SECONDS}s)")

        while self._rodando:
            try:
                await self.verificar_execucoes_travadas()
            except Exception as e:
                logger.exception(f"[WATCHDOG] Erro durante verificação: {e}")

            await asyncio.sleep(CHECK_INTERVAL_SECONDS)

    def parar_monitoramento(self):
        """Para o loop de monitoramento."""
        self._rodando = False
        logger.info("[WATCHDOG] Monitoramento parado")


def get_watchdog(db: Session) -> ClassificadorWatchdog:
    """Factory function para obter instância do watchdog."""
    return ClassificadorWatchdog(db)
