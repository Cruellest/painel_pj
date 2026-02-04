# utils/metrics.py
"""
Sistema de métricas básicas para monitoramento de requests.

Fornece métricas estilo Prometheus para:
- Contagem de requests por endpoint e status
- Latência de requests (histograma)
- Erros por tipo
- Métricas de saúde do sistema

USO:
    from utils.metrics import get_metrics, record_request, get_metrics_text

    # No middleware, após processar request
    record_request(
        method="GET",
        path="/api/processos",
        status_code=200,
        duration_seconds=0.5
    )

    # No endpoint /metrics
    return Response(content=get_metrics_text(), media_type="text/plain")

Autor: LAB/PGE-MS
"""

import time
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from utils.timezone import get_utc_now


# ============================================
# CONFIGURAÇÃO DOS BUCKETS DO HISTOGRAMA
# ============================================

# Buckets de latência em segundos (estilo Prometheus)
LATENCY_BUCKETS = [
    0.005,   # 5ms
    0.01,    # 10ms
    0.025,   # 25ms
    0.05,    # 50ms
    0.1,     # 100ms
    0.25,    # 250ms
    0.5,     # 500ms
    1.0,     # 1s
    2.5,     # 2.5s
    5.0,     # 5s
    10.0,    # 10s
    30.0,    # 30s
    60.0,    # 1min
    float('inf')  # +Inf
]


# ============================================
# ESTRUTURAS DE DADOS
# ============================================

@dataclass
class RequestMetrics:
    """Métricas agregadas por endpoint."""
    total_count: int = 0
    success_count: int = 0  # 2xx
    client_error_count: int = 0  # 4xx
    server_error_count: int = 0  # 5xx

    # Latência
    total_duration_seconds: float = 0.0
    min_duration_seconds: float = float('inf')
    max_duration_seconds: float = 0.0

    # Histograma de latência (contagem por bucket)
    latency_histogram: Dict[float, int] = field(default_factory=lambda: defaultdict(int))

    # Último request
    last_request_time: Optional[datetime] = None


class MetricsRegistry:
    """
    Registro central de métricas da aplicação.

    Thread-safe para uso com múltiplos workers.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._start_time = time.time()

        # Métricas por endpoint (method:path)
        self._endpoints: Dict[str, RequestMetrics] = defaultdict(RequestMetrics)

        # Métricas globais
        self._total_requests = 0
        self._total_errors = 0
        self._active_requests = 0

        # Erros por tipo
        self._errors_by_type: Dict[str, int] = defaultdict(int)

        # Últimos N erros para debug
        self._recent_errors: List[Dict] = []
        self._max_recent_errors = 100

    def record_request(
        self,
        method: str,
        path: str,
        status_code: int,
        duration_seconds: float,
        error_type: Optional[str] = None
    ):
        """
        Registra métricas de uma request.

        Args:
            method: Método HTTP (GET, POST, etc.)
            path: Caminho da requisição
            status_code: Código de status HTTP
            duration_seconds: Duração em segundos
            error_type: Tipo de erro (se houver)
        """
        # Normaliza path (remove query string e IDs numéricos)
        normalized_path = self._normalize_path(path)
        key = f"{method}:{normalized_path}"

        with self._lock:
            metrics = self._endpoints[key]

            # Contadores
            metrics.total_count += 1
            self._total_requests += 1

            if 200 <= status_code < 300:
                metrics.success_count += 1
            elif 400 <= status_code < 500:
                metrics.client_error_count += 1
            elif status_code >= 500:
                metrics.server_error_count += 1
                self._total_errors += 1

            # Latência
            metrics.total_duration_seconds += duration_seconds
            metrics.min_duration_seconds = min(metrics.min_duration_seconds, duration_seconds)
            metrics.max_duration_seconds = max(metrics.max_duration_seconds, duration_seconds)

            # Histograma
            for bucket in LATENCY_BUCKETS:
                if duration_seconds <= bucket:
                    metrics.latency_histogram[bucket] += 1
                    break

            metrics.last_request_time = get_utc_now()

            # Registro de erros
            if error_type:
                self._errors_by_type[error_type] += 1
                self._recent_errors.append({
                    "time": get_utc_now().isoformat(),
                    "method": method,
                    "path": path,
                    "status_code": status_code,
                    "error_type": error_type,
                    "duration_s": round(duration_seconds, 3)
                })
                # Mantém só os últimos N erros
                if len(self._recent_errors) > self._max_recent_errors:
                    self._recent_errors.pop(0)

    def start_request(self):
        """Registra início de uma request (para contagem de ativos)."""
        with self._lock:
            self._active_requests += 1

    def end_request(self):
        """Registra fim de uma request."""
        with self._lock:
            self._active_requests = max(0, self._active_requests - 1)

    def get_summary(self) -> Dict:
        """
        Retorna resumo das métricas em formato JSON.
        """
        with self._lock:
            uptime_seconds = time.time() - self._start_time

            # Calcula estatísticas globais
            total_duration = sum(m.total_duration_seconds for m in self._endpoints.values())
            avg_duration = total_duration / self._total_requests if self._total_requests > 0 else 0

            # Top endpoints por contagem
            top_endpoints = sorted(
                [(k, m.total_count) for k, m in self._endpoints.items()],
                key=lambda x: x[1],
                reverse=True
            )[:10]

            # Top endpoints por latência média
            slowest_endpoints = []
            for key, metrics in self._endpoints.items():
                if metrics.total_count > 0:
                    avg = metrics.total_duration_seconds / metrics.total_count
                    slowest_endpoints.append((key, avg, metrics.total_count))
            slowest_endpoints.sort(key=lambda x: x[1], reverse=True)

            return {
                "uptime_seconds": round(uptime_seconds, 1),
                "uptime_human": self._format_uptime(uptime_seconds),
                "total_requests": self._total_requests,
                "total_errors": self._total_errors,
                "active_requests": self._active_requests,
                "error_rate": round(self._total_errors / self._total_requests * 100, 2) if self._total_requests > 0 else 0,
                "avg_duration_ms": round(avg_duration * 1000, 2),
                "requests_per_minute": round(self._total_requests / (uptime_seconds / 60), 2) if uptime_seconds > 60 else self._total_requests,
                "top_endpoints": [
                    {"endpoint": e[0], "count": e[1]}
                    for e in top_endpoints
                ],
                "slowest_endpoints": [
                    {"endpoint": e[0], "avg_ms": round(e[1] * 1000, 2), "count": e[2]}
                    for e in slowest_endpoints[:10]
                ],
                "errors_by_type": dict(self._errors_by_type),
                "endpoints_count": len(self._endpoints)
            }

    def get_prometheus_text(self) -> str:
        """
        Retorna métricas em formato Prometheus text-based.

        Compatível com Prometheus scraping.
        """
        with self._lock:
            lines = []

            # Informações do serviço
            uptime = time.time() - self._start_time
            lines.append(f"# HELP portal_pge_uptime_seconds Tempo de execução do serviço")
            lines.append(f"# TYPE portal_pge_uptime_seconds gauge")
            lines.append(f"portal_pge_uptime_seconds {uptime:.2f}")
            lines.append("")

            # Requests ativos
            lines.append(f"# HELP portal_pge_active_requests Número de requests em processamento")
            lines.append(f"# TYPE portal_pge_active_requests gauge")
            lines.append(f"portal_pge_active_requests {self._active_requests}")
            lines.append("")

            # Total de requests
            lines.append(f"# HELP portal_pge_requests_total Total de requests processados")
            lines.append(f"# TYPE portal_pge_requests_total counter")
            lines.append(f"portal_pge_requests_total {self._total_requests}")
            lines.append("")

            # Total de erros
            lines.append(f"# HELP portal_pge_errors_total Total de erros (5xx)")
            lines.append(f"# TYPE portal_pge_errors_total counter")
            lines.append(f"portal_pge_errors_total {self._total_errors}")
            lines.append("")

            # Requests por endpoint e status
            lines.append(f"# HELP portal_pge_http_requests_total Requests HTTP por endpoint e status")
            lines.append(f"# TYPE portal_pge_http_requests_total counter")
            for key, metrics in self._endpoints.items():
                method, path = key.split(":", 1)
                safe_path = path.replace('"', '\\"')

                if metrics.success_count > 0:
                    lines.append(f'portal_pge_http_requests_total{{method="{method}",path="{safe_path}",status="2xx"}} {metrics.success_count}')
                if metrics.client_error_count > 0:
                    lines.append(f'portal_pge_http_requests_total{{method="{method}",path="{safe_path}",status="4xx"}} {metrics.client_error_count}')
                if metrics.server_error_count > 0:
                    lines.append(f'portal_pge_http_requests_total{{method="{method}",path="{safe_path}",status="5xx"}} {metrics.server_error_count}')
            lines.append("")

            # Latência por endpoint (histograma)
            lines.append(f"# HELP portal_pge_http_request_duration_seconds Duração dos requests HTTP")
            lines.append(f"# TYPE portal_pge_http_request_duration_seconds histogram")
            for key, metrics in self._endpoints.items():
                if metrics.total_count == 0:
                    continue

                method, path = key.split(":", 1)
                safe_path = path.replace('"', '\\"')

                # Buckets acumulativos
                cumulative = 0
                for bucket in LATENCY_BUCKETS:
                    cumulative += metrics.latency_histogram.get(bucket, 0)
                    bucket_label = "+Inf" if bucket == float('inf') else f"{bucket}"
                    lines.append(f'portal_pge_http_request_duration_seconds_bucket{{method="{method}",path="{safe_path}",le="{bucket_label}"}} {cumulative}')

                lines.append(f'portal_pge_http_request_duration_seconds_sum{{method="{method}",path="{safe_path}"}} {metrics.total_duration_seconds:.4f}')
                lines.append(f'portal_pge_http_request_duration_seconds_count{{method="{method}",path="{safe_path}"}} {metrics.total_count}')
            lines.append("")

            # Erros por tipo
            if self._errors_by_type:
                lines.append(f"# HELP portal_pge_errors_by_type_total Erros por tipo")
                lines.append(f"# TYPE portal_pge_errors_by_type_total counter")
                for error_type, count in self._errors_by_type.items():
                    safe_type = error_type.replace('"', '\\"')
                    lines.append(f'portal_pge_errors_by_type_total{{type="{safe_type}"}} {count}')
                lines.append("")

            return "\n".join(lines)

    def get_recent_errors(self, limit: int = 20) -> List[Dict]:
        """Retorna os erros mais recentes."""
        with self._lock:
            return list(reversed(self._recent_errors[-limit:]))

    def reset(self):
        """Reseta todas as métricas (para testes)."""
        with self._lock:
            self._endpoints.clear()
            self._total_requests = 0
            self._total_errors = 0
            self._active_requests = 0
            self._errors_by_type.clear()
            self._recent_errors.clear()
            self._start_time = time.time()

    def _normalize_path(self, path: str) -> str:
        """
        Normaliza path removendo:
        - Query strings
        - IDs numéricos (substitui por {id})
        - UUIDs (substitui por {uuid})
        """
        # Remove query string
        if "?" in path:
            path = path.split("?")[0]

        # Substitui segmentos numéricos por {id}
        parts = path.split("/")
        normalized_parts = []
        for part in parts:
            if part.isdigit():
                normalized_parts.append("{id}")
            elif len(part) == 36 and part.count("-") == 4:
                # Provavelmente UUID
                normalized_parts.append("{uuid}")
            else:
                normalized_parts.append(part)

        return "/".join(normalized_parts)

    def _format_uptime(self, seconds: float) -> str:
        """Formata uptime em formato legível."""
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            minutes = seconds / 60
            return f"{minutes:.1f}m"
        elif seconds < 86400:
            hours = seconds / 3600
            return f"{hours:.1f}h"
        else:
            days = seconds / 86400
            return f"{days:.1f}d"


# ============================================
# INSTÂNCIA GLOBAL (SINGLETON)
# ============================================

_metrics_registry: Optional[MetricsRegistry] = None


def get_metrics() -> MetricsRegistry:
    """Retorna a instância singleton do registro de métricas."""
    global _metrics_registry
    if _metrics_registry is None:
        _metrics_registry = MetricsRegistry()
    return _metrics_registry


def record_request(
    method: str,
    path: str,
    status_code: int,
    duration_seconds: float,
    error_type: Optional[str] = None
):
    """Função de conveniência para registrar request."""
    get_metrics().record_request(method, path, status_code, duration_seconds, error_type)


def get_metrics_text() -> str:
    """Função de conveniência para obter métricas em formato Prometheus."""
    return get_metrics().get_prometheus_text()


def get_metrics_summary() -> Dict:
    """Função de conveniência para obter resumo das métricas."""
    return get_metrics().get_summary()


# ============================================
# EXPORTS
# ============================================

__all__ = [
    "MetricsRegistry",
    "get_metrics",
    "record_request",
    "get_metrics_text",
    "get_metrics_summary",
    "LATENCY_BUCKETS",
]
