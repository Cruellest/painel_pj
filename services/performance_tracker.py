# services/performance_tracker.py
"""
Sistema de instrumentacao de performance ponta a ponta.

Rastreia latencia detalhada de cada etapa do processamento de requests,
permitindo diagnostico preciso de gargalos.

Uso:
    from services.performance_tracker import PerformanceTracker, get_tracker

    # No inicio da request
    tracker = PerformanceTracker(request_id="abc123")
    tracker.mark("request_received")

    # Durante processamento
    tracker.mark("auth_done")
    tracker.mark("load_context_done")

    # No final
    tracker.mark("response_sent")
    report = tracker.get_report()

Autor: LAB/PGE-MS
"""

import time
import uuid
import logging
import asyncio
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from contextvars import ContextVar

logger = logging.getLogger(__name__)

# Context variable para rastrear tracker por request
_current_tracker: ContextVar[Optional["PerformanceTracker"]] = ContextVar(
    "performance_tracker", default=None
)


@dataclass
class TimingMark:
    """Um marco de tempo no pipeline"""
    name: str
    timestamp: float  # time.perf_counter()
    wall_time: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChunkStats:
    """Estatisticas de chunks de streaming"""
    total_chunks: int = 0
    total_bytes: int = 0
    first_chunk_time: Optional[float] = None
    last_chunk_time: Optional[float] = None
    chunk_intervals: List[float] = field(default_factory=list)

    @property
    def avg_chunk_size(self) -> float:
        if self.total_chunks == 0:
            return 0
        return self.total_bytes / self.total_chunks

    @property
    def avg_chunk_interval_ms(self) -> float:
        if not self.chunk_intervals:
            return 0
        return sum(self.chunk_intervals) / len(self.chunk_intervals) * 1000

    def record_chunk(self, size: int, timestamp: float):
        """Registra um chunk de streaming"""
        self.total_chunks += 1
        self.total_bytes += size

        if self.first_chunk_time is None:
            self.first_chunk_time = timestamp

        if self.last_chunk_time is not None:
            interval = timestamp - self.last_chunk_time
            self.chunk_intervals.append(interval)

        self.last_chunk_time = timestamp


class PerformanceTracker:
    """
    Rastreador de performance para uma request.

    Marcos padrao (ordem esperada):
    - t0_request_received: Request chegou no servidor
    - t1_auth_done: Autenticacao JWT concluida
    - t2_load_config_done: Configuracoes carregadas do BD
    - t3_agente1_start: Inicio do Agente 1 (coleta TJ-MS)
    - t3_agente1_done: Fim do Agente 1
    - t4_agente2_start: Inicio do Agente 2 (detector)
    - t4_agente2_done: Fim do Agente 2
    - t5_prompt_build_start: Inicio da montagem do prompt
    - t5_prompt_build_done: Fim da montagem do prompt
    - t6_llm_call_start: Chamada ao LLM iniciada
    - t7_first_token: Primeiro token recebido (TTFT)
    - t8_last_token: Ultimo token recebido
    - t9_postprocess_start: Inicio do pos-processamento
    - t9_postprocess_done: Fim do pos-processamento
    - t10_db_save_start: Inicio do salvamento no BD
    - t10_db_save_done: Fim do salvamento no BD
    - t11_response_sent: Resposta enviada ao cliente
    """

    # Nomes padrao dos marcos
    MARKS = {
        "request_received": "t0",
        "auth_done": "t1",
        "load_config_done": "t2",
        "agente1_start": "t3a",
        "agente1_done": "t3b",
        "agente2_start": "t4a",
        "agente2_done": "t4b",
        "prompt_build_start": "t5a",
        "prompt_build_done": "t5b",
        "llm_call_start": "t6",
        "first_token": "t7",
        "last_token": "t8",
        "postprocess_start": "t9a",
        "postprocess_done": "t9b",
        "db_save_start": "t10a",
        "db_save_done": "t10b",
        "response_sent": "t11",
    }

    def __init__(
        self,
        request_id: str = None,
        sistema: str = None,
        route: str = None
    ):
        self.request_id = request_id or str(uuid.uuid4())[:8]
        self.sistema = sistema
        self.route = route
        self.start_time = time.perf_counter()
        self.start_wall_time = datetime.now()
        self.marks: List[TimingMark] = []
        self.chunk_stats = ChunkStats()
        self.metadata: Dict[str, Any] = {}

        # Registra marca inicial automaticamente
        self.mark("request_received")

    def mark(self, name: str, **metadata) -> float:
        """
        Registra um marco de tempo.

        Args:
            name: Nome do marco (ex: "auth_done", "llm_call_start")
            **metadata: Dados adicionais (ex: tokens=1234, bytes=5678)

        Returns:
            Tempo decorrido desde o inicio em ms
        """
        now = time.perf_counter()
        elapsed_ms = (now - self.start_time) * 1000

        mark = TimingMark(
            name=name,
            timestamp=now,
            wall_time=datetime.now(),
            metadata=metadata
        )
        self.marks.append(mark)

        # Log em tempo real para debug
        prefix = self.MARKS.get(name, "??")
        meta_str = ""
        if metadata:
            meta_parts = [f"{k}={v}" for k, v in metadata.items()]
            meta_str = f" [{', '.join(meta_parts)}]"

        logger.debug(
            f"[PERF:{self.request_id}] {prefix} {name}: {elapsed_ms:.1f}ms{meta_str}"
        )

        return elapsed_ms

    def record_chunk(self, chunk: str):
        """Registra um chunk de streaming"""
        self.chunk_stats.record_chunk(len(chunk), time.perf_counter())

    def set_metadata(self, key: str, value: Any):
        """Define metadado da request"""
        self.metadata[key] = value

    def get_elapsed_ms(self, from_mark: str = None) -> float:
        """
        Retorna tempo decorrido em ms.

        Args:
            from_mark: Se especificado, retorna tempo desde esse marco
        """
        if from_mark:
            for m in self.marks:
                if m.name == from_mark:
                    return (time.perf_counter() - m.timestamp) * 1000
            return 0
        return (time.perf_counter() - self.start_time) * 1000

    def get_interval_ms(self, from_mark: str, to_mark: str) -> Optional[float]:
        """
        Retorna intervalo entre dois marcos em ms.
        """
        from_ts = None
        to_ts = None

        for m in self.marks:
            if m.name == from_mark:
                from_ts = m.timestamp
            if m.name == to_mark:
                to_ts = m.timestamp

        if from_ts is not None and to_ts is not None:
            return (to_ts - from_ts) * 1000
        return None

    def get_report(self) -> Dict[str, Any]:
        """
        Gera relatorio completo de performance.

        Returns:
            Dicionario com todas as metricas
        """
        total_ms = self.get_elapsed_ms()

        # Calcula intervalos entre marcos consecutivos
        intervals = []
        for i in range(1, len(self.marks)):
            prev = self.marks[i - 1]
            curr = self.marks[i]
            interval_ms = (curr.timestamp - prev.timestamp) * 1000
            intervals.append({
                "from": prev.name,
                "to": curr.name,
                "ms": round(interval_ms, 2)
            })

        # Metricas agregadas
        ttft_ms = self.get_interval_ms("llm_call_start", "first_token")
        generation_ms = self.get_interval_ms("first_token", "last_token")
        agente1_ms = self.get_interval_ms("agente1_start", "agente1_done")
        agente2_ms = self.get_interval_ms("agente2_start", "agente2_done")
        prompt_build_ms = self.get_interval_ms("prompt_build_start", "prompt_build_done")
        postprocess_ms = self.get_interval_ms("postprocess_start", "postprocess_done")
        db_save_ms = self.get_interval_ms("db_save_start", "db_save_done")

        # Overhead (tempo nao contabilizado nos marcos principais)
        known_time = sum([
            agente1_ms or 0,
            agente2_ms or 0,
            prompt_build_ms or 0,
            ttft_ms or 0,
            generation_ms or 0,
            postprocess_ms or 0,
            db_save_ms or 0
        ])
        overhead_ms = total_ms - known_time if known_time > 0 else None

        report = {
            "request_id": self.request_id,
            "sistema": self.sistema,
            "route": self.route,
            "start_time": self.start_wall_time.isoformat(),
            "total_ms": round(total_ms, 2),

            # Metricas principais
            "metrics": {
                "ttft_ms": round(ttft_ms, 2) if ttft_ms else None,
                "generation_ms": round(generation_ms, 2) if generation_ms else None,
                "agente1_ms": round(agente1_ms, 2) if agente1_ms else None,
                "agente2_ms": round(agente2_ms, 2) if agente2_ms else None,
                "prompt_build_ms": round(prompt_build_ms, 2) if prompt_build_ms else None,
                "postprocess_ms": round(postprocess_ms, 2) if postprocess_ms else None,
                "db_save_ms": round(db_save_ms, 2) if db_save_ms else None,
                "overhead_ms": round(overhead_ms, 2) if overhead_ms else None,
            },

            # Streaming stats
            "streaming": {
                "total_chunks": self.chunk_stats.total_chunks,
                "total_bytes": self.chunk_stats.total_bytes,
                "avg_chunk_size": round(self.chunk_stats.avg_chunk_size, 2),
                "avg_chunk_interval_ms": round(self.chunk_stats.avg_chunk_interval_ms, 2),
            },

            # Timeline detalhada
            "timeline": [
                {
                    "name": m.name,
                    "elapsed_ms": round((m.timestamp - self.start_time) * 1000, 2),
                    "metadata": m.metadata
                }
                for m in self.marks
            ],

            # Intervalos entre marcos
            "intervals": intervals,

            # Metadados da request
            "metadata": self.metadata
        }

        return report

    def log_summary(self, level: int = logging.INFO):
        """
        Loga resumo da performance.
        """
        report = self.get_report()
        metrics = report["metrics"]

        summary_parts = [f"[PERF:{self.request_id}] SUMMARY:"]
        summary_parts.append(f"total={report['total_ms']:.0f}ms")

        if metrics["ttft_ms"]:
            summary_parts.append(f"ttft={metrics['ttft_ms']:.0f}ms")
        if metrics["generation_ms"]:
            summary_parts.append(f"gen={metrics['generation_ms']:.0f}ms")
        if metrics["agente1_ms"]:
            summary_parts.append(f"ag1={metrics['agente1_ms']:.0f}ms")
        if metrics["agente2_ms"]:
            summary_parts.append(f"ag2={metrics['agente2_ms']:.0f}ms")
        if metrics["db_save_ms"]:
            summary_parts.append(f"db={metrics['db_save_ms']:.0f}ms")
        if metrics["overhead_ms"]:
            summary_parts.append(f"overhead={metrics['overhead_ms']:.0f}ms")

        streaming = report["streaming"]
        if streaming["total_chunks"] > 0:
            summary_parts.append(
                f"chunks={streaming['total_chunks']} "
                f"avg_size={streaming['avg_chunk_size']:.0f}b"
            )

        logger.log(level, " | ".join(summary_parts))


def get_tracker() -> Optional[PerformanceTracker]:
    """
    Retorna o tracker da request atual (se existir).
    """
    return _current_tracker.get()


def set_tracker(tracker: PerformanceTracker):
    """
    Define o tracker para a request atual.
    """
    _current_tracker.set(tracker)


def create_tracker(
    request_id: str = None,
    sistema: str = None,
    route: str = None
) -> PerformanceTracker:
    """
    Cria e registra um novo tracker para a request atual.
    """
    tracker = PerformanceTracker(
        request_id=request_id,
        sistema=sistema,
        route=route
    )
    set_tracker(tracker)
    return tracker


def mark(name: str, **metadata) -> Optional[float]:
    """
    Marca um ponto no tracker atual (se existir).

    Funcao de conveniencia para uso em qualquer lugar do codigo.
    """
    tracker = get_tracker()
    if tracker:
        return tracker.mark(name, **metadata)
    return None


def record_chunk(chunk: str):
    """
    Registra um chunk no tracker atual (se existir).
    """
    tracker = get_tracker()
    if tracker:
        tracker.record_chunk(chunk)


# Exports
__all__ = [
    "PerformanceTracker",
    "get_tracker",
    "set_tracker",
    "create_tracker",
    "mark",
    "record_chunk",
]
