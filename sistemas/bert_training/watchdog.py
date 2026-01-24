# -*- coding: utf-8 -*-
"""
Watchdog para monitoramento de jobs BERT travados.

Este modulo implementa um sistema de monitoramento que:
- Detecta jobs sem progresso por muito tempo
- Detecta workers que pararam de responder
- Toma acoes automaticas (warn, restart, reassign)
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_
import logging

from sistemas.bert_training.models import BertJob, BertRun, BertWorker, JobStatus
from sistemas.bert_training import services

logger = logging.getLogger(__name__)


# ==================== Configuracao ====================

class WatchdogConfig:
    """Configuracao do watchdog."""

    # Tempo sem progresso antes de considerar travado
    NO_PROGRESS_TIMEOUT_MINUTES = 15

    # Tempo sem heartbeat antes de considerar worker morto
    WORKER_HEARTBEAT_TIMEOUT_MINUTES = 5

    # Tempo de epoch travada
    STUCK_EPOCH_TIMEOUT_MINUTES = 30

    # Maximo de retries automaticos
    MAX_AUTO_RETRIES = 3

    # Tempo maximo de job antes de timeout
    JOB_MAX_DURATION_HOURS = 24


# ==================== Regras de Deteccao ====================

def check_no_progress_jobs(db: Session) -> List[Dict[str, Any]]:
    """
    Detecta jobs sem progresso por muito tempo.

    Returns:
        Lista de jobs problematicos com informacoes
    """
    cutoff_time = datetime.utcnow() - timedelta(
        minutes=WatchdogConfig.NO_PROGRESS_TIMEOUT_MINUTES
    )

    # Busca jobs em treinamento sem atualizacao recente
    stuck_jobs = db.query(BertJob).filter(
        BertJob.status == JobStatus.TRAINING,
        BertJob.started_at < cutoff_time
    ).all()

    problems = []
    for job in stuck_jobs:
        # Verifica se teve progresso recente via metricas
        from sistemas.bert_training.models import BertMetric
        latest_metric = db.query(BertMetric).filter(
            BertMetric.run_id == job.run_id
        ).order_by(BertMetric.recorded_at.desc()).first()

        if latest_metric:
            if latest_metric.recorded_at < cutoff_time:
                problems.append({
                    "job_id": job.id,
                    "run_id": job.run_id,
                    "type": "no_progress",
                    "message": f"Job sem progresso por mais de {WatchdogConfig.NO_PROGRESS_TIMEOUT_MINUTES} minutos",
                    "last_activity": latest_metric.recorded_at.isoformat(),
                    "current_epoch": job.current_epoch,
                    "worker_id": job.worker_id
                })
        elif job.started_at < cutoff_time:
            problems.append({
                "job_id": job.id,
                "run_id": job.run_id,
                "type": "no_metrics",
                "message": "Job iniciado mas sem metricas registradas",
                "started_at": job.started_at.isoformat(),
                "worker_id": job.worker_id
            })

    return problems


def check_dead_workers(db: Session) -> List[Dict[str, Any]]:
    """
    Detecta workers que pararam de responder.

    Returns:
        Lista de workers problematicos
    """
    cutoff_time = datetime.utcnow() - timedelta(
        minutes=WatchdogConfig.WORKER_HEARTBEAT_TIMEOUT_MINUTES
    )

    dead_workers = db.query(BertWorker).filter(
        BertWorker.is_active == True,
        BertWorker.current_job_id.isnot(None),
        BertWorker.last_heartbeat < cutoff_time
    ).all()

    problems = []
    for worker in dead_workers:
        # Busca job associado
        job = db.query(BertJob).filter(BertJob.id == worker.current_job_id).first()

        problems.append({
            "worker_id": worker.id,
            "worker_name": worker.name,
            "type": "dead_worker",
            "message": f"Worker sem heartbeat por mais de {WatchdogConfig.WORKER_HEARTBEAT_TIMEOUT_MINUTES} minutos",
            "last_heartbeat": worker.last_heartbeat.isoformat() if worker.last_heartbeat else None,
            "job_id": worker.current_job_id,
            "run_id": job.run_id if job else None
        })

    return problems


def check_stuck_epochs(db: Session) -> List[Dict[str, Any]]:
    """
    Detecta jobs travados na mesma epoch por muito tempo.
    """
    cutoff_time = datetime.utcnow() - timedelta(
        minutes=WatchdogConfig.STUCK_EPOCH_TIMEOUT_MINUTES
    )

    # Busca jobs em treinamento
    training_jobs = db.query(BertJob).filter(
        BertJob.status == JobStatus.TRAINING,
        BertJob.current_epoch.isnot(None)
    ).all()

    problems = []
    for job in training_jobs:
        # Busca metricas da epoch atual
        from sistemas.bert_training.models import BertMetric
        epoch_metrics = db.query(BertMetric).filter(
            BertMetric.run_id == job.run_id,
            BertMetric.epoch == job.current_epoch
        ).order_by(BertMetric.recorded_at.desc()).first()

        if epoch_metrics and epoch_metrics.recorded_at < cutoff_time:
            problems.append({
                "job_id": job.id,
                "run_id": job.run_id,
                "type": "stuck_epoch",
                "message": f"Epoch {job.current_epoch} travada por mais de {WatchdogConfig.STUCK_EPOCH_TIMEOUT_MINUTES} minutos",
                "current_epoch": job.current_epoch,
                "last_metric_time": epoch_metrics.recorded_at.isoformat(),
                "worker_id": job.worker_id
            })

    return problems


def check_timeout_jobs(db: Session) -> List[Dict[str, Any]]:
    """
    Detecta jobs que excederam tempo maximo.
    """
    cutoff_time = datetime.utcnow() - timedelta(
        hours=WatchdogConfig.JOB_MAX_DURATION_HOURS
    )

    timeout_jobs = db.query(BertJob).filter(
        BertJob.status.in_([JobStatus.TRAINING, JobStatus.CLAIMED, JobStatus.DOWNLOADING]),
        BertJob.started_at < cutoff_time
    ).all()

    return [{
        "job_id": job.id,
        "run_id": job.run_id,
        "type": "timeout",
        "message": f"Job excedeu tempo maximo de {WatchdogConfig.JOB_MAX_DURATION_HOURS} horas",
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "worker_id": job.worker_id
    } for job in timeout_jobs]


# ==================== Acoes ====================

def handle_stuck_job(db: Session, job_id: int, reason: str) -> Dict[str, Any]:
    """
    Trata um job travado.

    Acoes possiveis:
    1. Se retry_count < max_retries: marca como failed e cria novo job
    2. Se retry_count >= max_retries: marca como failed definitivamente
    """
    job = db.query(BertJob).filter(BertJob.id == job_id).first()
    if not job:
        return {"action": "none", "reason": "job not found"}

    run = db.query(BertRun).filter(BertRun.id == job.run_id).first()

    # Marca job atual como failed
    job.status = JobStatus.FAILED
    job.error_message = f"[Watchdog] {reason}"
    job.completed_at = datetime.utcnow()

    # Libera worker se associado
    if job.worker_id:
        worker = db.query(BertWorker).filter(BertWorker.id == job.worker_id).first()
        if worker:
            worker.current_job_id = None

    result = {
        "job_id": job_id,
        "action": "marked_failed",
        "reason": reason
    }

    # Verifica se pode retry
    if job.retry_count < WatchdogConfig.MAX_AUTO_RETRIES:
        # Cria novo job
        new_job = BertJob(
            run_id=job.run_id,
            status=JobStatus.PENDING,
            total_epochs=job.total_epochs,
            retry_count=job.retry_count + 1,
            max_retries=job.max_retries,
            timeout_seconds=job.timeout_seconds
        )
        db.add(new_job)

        result["new_job_created"] = True
        result["retry_count"] = new_job.retry_count

        logger.warning(f"Job {job_id} marcado como failed, novo job criado (retry {new_job.retry_count})")
    else:
        # Run falhou definitivamente
        run.status = "failed"
        run.error_message = f"[Watchdog] {reason}. Maximo de retries excedido."
        run.completed_at = datetime.utcnow()

        result["run_failed"] = True
        logger.error(f"Job {job_id} falhou definitivamente apos {job.retry_count} retries")

    db.commit()
    return result


def handle_dead_worker(db: Session, worker_id: int) -> Dict[str, Any]:
    """
    Trata um worker que parou de responder.
    """
    worker = db.query(BertWorker).filter(BertWorker.id == worker_id).first()
    if not worker:
        return {"action": "none", "reason": "worker not found"}

    result = {
        "worker_id": worker_id,
        "worker_name": worker.name,
        "action": "marked_inactive"
    }

    # Marca worker como inativo
    worker.is_active = False

    # Se tinha job, trata
    if worker.current_job_id:
        job_result = handle_stuck_job(
            db,
            worker.current_job_id,
            f"Worker '{worker.name}' parou de responder"
        )
        result["job_action"] = job_result
        worker.current_job_id = None

    db.commit()
    logger.warning(f"Worker {worker.name} marcado como inativo por falta de heartbeat")

    return result


# ==================== Execucao do Watchdog ====================

def run_watchdog_check(db: Session) -> Dict[str, Any]:
    """
    Executa verificacao completa do watchdog.

    Deve ser chamada periodicamente (ex: a cada 5 minutos).
    """
    results = {
        "timestamp": datetime.utcnow().isoformat(),
        "problems_detected": [],
        "actions_taken": []
    }

    # 1. Verifica jobs sem progresso
    no_progress = check_no_progress_jobs(db)
    for problem in no_progress:
        results["problems_detected"].append(problem)
        action = handle_stuck_job(db, problem["job_id"], problem["message"])
        results["actions_taken"].append(action)

    # 2. Verifica workers mortos
    dead_workers = check_dead_workers(db)
    for problem in dead_workers:
        results["problems_detected"].append(problem)
        action = handle_dead_worker(db, problem["worker_id"])
        results["actions_taken"].append(action)

    # 3. Verifica epochs travadas
    stuck_epochs = check_stuck_epochs(db)
    for problem in stuck_epochs:
        results["problems_detected"].append(problem)
        # Epochs travadas geralmente sao tratadas com no_progress

    # 4. Verifica timeouts
    timeout_jobs = check_timeout_jobs(db)
    for problem in timeout_jobs:
        results["problems_detected"].append(problem)
        action = handle_stuck_job(db, problem["job_id"], problem["message"])
        results["actions_taken"].append(action)

    # Loga resumo
    if results["problems_detected"]:
        logger.info(f"Watchdog: {len(results['problems_detected'])} problemas detectados, "
                   f"{len(results['actions_taken'])} acoes tomadas")
    else:
        logger.debug("Watchdog: nenhum problema detectado")

    return results


def get_system_health(db: Session) -> Dict[str, Any]:
    """
    Retorna status de saude do sistema.

    Util para dashboards de monitoramento.
    """
    now = datetime.utcnow()
    heartbeat_threshold = now - timedelta(minutes=WatchdogConfig.WORKER_HEARTBEAT_TIMEOUT_MINUTES)

    # Contagens
    total_workers = db.query(BertWorker).filter(BertWorker.is_active == True).count()
    active_workers = db.query(BertWorker).filter(
        BertWorker.is_active == True,
        BertWorker.last_heartbeat > heartbeat_threshold
    ).count()

    pending_jobs = db.query(BertJob).filter(BertJob.status == JobStatus.PENDING).count()
    training_jobs = db.query(BertJob).filter(BertJob.status == JobStatus.TRAINING).count()
    failed_today = db.query(BertJob).filter(
        BertJob.status == JobStatus.FAILED,
        BertJob.completed_at > now - timedelta(hours=24)
    ).count()
    completed_today = db.query(BertJob).filter(
        BertJob.status == JobStatus.COMPLETED,
        BertJob.completed_at > now - timedelta(hours=24)
    ).count()

    # Determina status geral
    if total_workers == 0:
        health_status = "warning"
        health_message = "Nenhum worker registrado"
    elif active_workers == 0:
        health_status = "critical"
        health_message = "Nenhum worker respondendo"
    elif pending_jobs > 0 and active_workers == 0:
        health_status = "warning"
        health_message = f"{pending_jobs} jobs na fila sem workers disponiveis"
    elif failed_today > completed_today and completed_today > 0:
        health_status = "warning"
        health_message = "Alta taxa de falhas nas ultimas 24h"
    else:
        health_status = "healthy"
        health_message = "Sistema operando normalmente"

    return {
        "status": health_status,
        "message": health_message,
        "workers": {
            "total": total_workers,
            "active": active_workers,
            "inactive": total_workers - active_workers
        },
        "jobs": {
            "pending": pending_jobs,
            "training": training_jobs,
            "completed_24h": completed_today,
            "failed_24h": failed_today
        },
        "thresholds": {
            "no_progress_minutes": WatchdogConfig.NO_PROGRESS_TIMEOUT_MINUTES,
            "heartbeat_minutes": WatchdogConfig.WORKER_HEARTBEAT_TIMEOUT_MINUTES,
            "max_duration_hours": WatchdogConfig.JOB_MAX_DURATION_HOURS
        }
    }
