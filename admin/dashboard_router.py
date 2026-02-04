# admin/dashboard_router.py
"""
Dashboard de Métricas - Portal PGE-MS

Fornece endpoints para visualização de métricas e status do sistema.

Endpoints:
- GET /admin/dashboard/api/metrics - Métricas em JSON
- GET /admin/dashboard/api/health - Status de saúde detalhado
- GET /admin/dashboard - Página HTML do dashboard

Autor: LAB/PGE-MS
"""

from datetime import datetime
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from auth.dependencies import get_current_active_user
from auth.models import User

router = APIRouter(prefix="/admin/dashboard", tags=["Admin - Dashboard"])


# ============================================
# API ENDPOINTS
# ============================================

@router.get("/api/metrics")
async def get_dashboard_metrics(
    current_user: User = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """
    Retorna métricas do sistema em formato JSON.

    Inclui:
    - Métricas de requests (contagem, latência, erros)
    - Status dos circuit breakers
    - Informações de cache
    - Status do sistema
    """
    from utils.metrics import get_metrics_summary
    from utils.health_check import run_health_check

    metrics = get_metrics_summary()

    # Circuit breaker status
    cb_status = _get_circuit_breaker_status()

    # Cache status
    cache_status = _get_cache_status()

    return {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "metrics": metrics,
        "circuit_breakers": cb_status,
        "cache": cache_status
    }


@router.get("/api/health")
async def get_dashboard_health(
    current_user: User = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """Retorna status de saúde detalhado do sistema."""
    from utils.health_check import run_health_check

    health = await run_health_check()
    return health


@router.get("/api/errors")
async def get_recent_errors(
    limit: int = 20,
    current_user: User = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """Retorna os erros mais recentes."""
    from utils.metrics import get_metrics

    errors = get_metrics().get_recent_errors(limit)
    return {
        "count": len(errors),
        "errors": errors
    }


# ============================================
# HTML DASHBOARD
# ============================================

@router.get("", response_class=HTMLResponse)
async def dashboard_page(
    request: Request,
    current_user: User = Depends(get_current_active_user)
):
    """Página HTML do dashboard de métricas."""

    html_content = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard - Portal PGE-MS</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #1a1a2e;
            color: #eee;
            min-height: 100vh;
        }
        .header {
            background: #16213e;
            padding: 1rem 2rem;
            border-bottom: 1px solid #0f3460;
        }
        .header h1 { font-size: 1.5rem; color: #e94560; }
        .container { padding: 2rem; max-width: 1400px; margin: 0 auto; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1.5rem; }
        .card {
            background: #16213e;
            border-radius: 12px;
            padding: 1.5rem;
            border: 1px solid #0f3460;
        }
        .card h2 {
            font-size: 0.875rem;
            color: #888;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 0.5rem;
        }
        .card .value {
            font-size: 2.5rem;
            font-weight: 700;
            color: #4ade80;
        }
        .card .value.warning { color: #fbbf24; }
        .card .value.error { color: #ef4444; }
        .card .subtitle { font-size: 0.875rem; color: #666; margin-top: 0.25rem; }
        .status-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.75rem; margin-top: 1rem; }
        .status-item {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.5rem;
            background: #1a1a2e;
            border-radius: 6px;
        }
        .status-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: #4ade80;
        }
        .status-dot.warning { background: #fbbf24; }
        .status-dot.error { background: #ef4444; }
        .status-dot.closed { background: #4ade80; }
        .status-dot.open { background: #ef4444; }
        .status-dot.half-open { background: #fbbf24; }
        .table-container { overflow-x: auto; margin-top: 1rem; }
        table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
        th, td {
            padding: 0.75rem;
            text-align: left;
            border-bottom: 1px solid #0f3460;
        }
        th { color: #888; font-weight: 500; text-transform: uppercase; font-size: 0.75rem; }
        .refresh-btn {
            background: #e94560;
            color: white;
            border: none;
            padding: 0.5rem 1rem;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.875rem;
        }
        .refresh-btn:hover { background: #d63855; }
        .header-actions { display: flex; align-items: center; gap: 1rem; }
        .last-update { font-size: 0.875rem; color: #666; }
        .section-title {
            font-size: 1.25rem;
            color: #fff;
            margin: 2rem 0 1rem;
            padding-bottom: 0.5rem;
            border-bottom: 1px solid #0f3460;
        }
    </style>
</head>
<body>
    <div class="header">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <h1>Dashboard de Metricas</h1>
            <div class="header-actions">
                <span class="last-update" id="lastUpdate">Carregando...</span>
                <button class="refresh-btn" onclick="loadData()">Atualizar</button>
            </div>
        </div>
    </div>

    <div class="container">
        <div class="grid">
            <div class="card">
                <h2>Total de Requests</h2>
                <div class="value" id="totalRequests">-</div>
                <div class="subtitle" id="requestsPerMin">- req/min</div>
            </div>
            <div class="card">
                <h2>Taxa de Erro</h2>
                <div class="value" id="errorRate">-</div>
                <div class="subtitle" id="totalErrors">- erros totais</div>
            </div>
            <div class="card">
                <h2>Latencia Media</h2>
                <div class="value" id="avgLatency">-</div>
                <div class="subtitle">ms</div>
            </div>
            <div class="card">
                <h2>Uptime</h2>
                <div class="value" id="uptime">-</div>
                <div class="subtitle" id="uptimeSeconds">- segundos</div>
            </div>
        </div>

        <h3 class="section-title">Circuit Breakers</h3>
        <div class="grid">
            <div class="card">
                <h2>Status dos Servicos</h2>
                <div class="status-grid" id="circuitBreakers">
                    <div class="status-item">
                        <div class="status-dot"></div>
                        <span>Carregando...</span>
                    </div>
                </div>
            </div>
            <div class="card">
                <h2>Cache</h2>
                <div class="status-grid" id="cacheStatus">
                    <div class="status-item">
                        <div class="status-dot"></div>
                        <span>Carregando...</span>
                    </div>
                </div>
            </div>
        </div>

        <h3 class="section-title">Top Endpoints</h3>
        <div class="card">
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>Endpoint</th>
                            <th>Requests</th>
                            <th>Latencia Media</th>
                        </tr>
                    </thead>
                    <tbody id="topEndpoints">
                        <tr><td colspan="3">Carregando...</td></tr>
                    </tbody>
                </table>
            </div>
        </div>

        <h3 class="section-title">Endpoints Mais Lentos</h3>
        <div class="card">
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>Endpoint</th>
                            <th>Latencia Media</th>
                            <th>Requests</th>
                        </tr>
                    </thead>
                    <tbody id="slowestEndpoints">
                        <tr><td colspan="3">Carregando...</td></tr>
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <script>
        async function loadData() {
            try {
                const response = await fetch('/admin/dashboard/api/metrics');
                const data = await response.json();

                const m = data.metrics;

                // Update cards
                document.getElementById('totalRequests').textContent = m.total_requests.toLocaleString();
                document.getElementById('requestsPerMin').textContent = m.requests_per_minute.toFixed(1) + ' req/min';

                const errorRateEl = document.getElementById('errorRate');
                errorRateEl.textContent = m.error_rate.toFixed(2) + '%';
                errorRateEl.className = 'value ' + (m.error_rate > 5 ? 'error' : m.error_rate > 1 ? 'warning' : '');
                document.getElementById('totalErrors').textContent = m.total_errors + ' erros totais';

                const latencyEl = document.getElementById('avgLatency');
                latencyEl.textContent = m.avg_duration_ms.toFixed(0);
                latencyEl.className = 'value ' + (m.avg_duration_ms > 1000 ? 'error' : m.avg_duration_ms > 500 ? 'warning' : '');

                document.getElementById('uptime').textContent = m.uptime_human;
                document.getElementById('uptimeSeconds').textContent = Math.floor(m.uptime_seconds).toLocaleString() + ' segundos';

                // Circuit breakers
                const cbHtml = Object.entries(data.circuit_breakers || {}).map(([name, status]) => {
                    const state = status.state || 'unknown';
                    return `<div class="status-item">
                        <div class="status-dot ${state}"></div>
                        <span>${name}: ${state}</span>
                    </div>`;
                }).join('') || '<div class="status-item"><span>Nenhum configurado</span></div>';
                document.getElementById('circuitBreakers').innerHTML = cbHtml;

                // Cache
                const cacheHtml = Object.entries(data.cache || {}).map(([name, info]) => {
                    return `<div class="status-item">
                        <div class="status-dot"></div>
                        <span>${name}: ${info.size || 0} itens</span>
                    </div>`;
                }).join('') || '<div class="status-item"><span>Cache nao configurado</span></div>';
                document.getElementById('cacheStatus').innerHTML = cacheHtml;

                // Top endpoints
                const topHtml = (m.top_endpoints || []).map(e =>
                    `<tr><td>${e.endpoint}</td><td>${e.count.toLocaleString()}</td><td>-</td></tr>`
                ).join('') || '<tr><td colspan="3">Nenhum dado</td></tr>';
                document.getElementById('topEndpoints').innerHTML = topHtml;

                // Slowest endpoints
                const slowHtml = (m.slowest_endpoints || []).map(e =>
                    `<tr><td>${e.endpoint}</td><td>${e.avg_ms.toFixed(0)}ms</td><td>${e.count.toLocaleString()}</td></tr>`
                ).join('') || '<tr><td colspan="3">Nenhum dado</td></tr>';
                document.getElementById('slowestEndpoints').innerHTML = slowHtml;

                // Last update
                document.getElementById('lastUpdate').textContent =
                    'Atualizado: ' + new Date().toLocaleTimeString('pt-BR');

            } catch (error) {
                console.error('Erro ao carregar metricas:', error);
            }
        }

        // Load on start
        loadData();

        // Auto-refresh every 30 seconds
        setInterval(loadData, 30000);
    </script>
</body>
</html>
"""
    return HTMLResponse(content=html_content)


# ============================================
# HELPER FUNCTIONS
# ============================================

def _get_circuit_breaker_status() -> Dict[str, Any]:
    """Obtém status dos circuit breakers."""
    try:
        from utils.circuit_breaker import get_tjms_circuit_breaker, get_gemini_circuit_breaker

        result = {}

        tjms_cb = get_tjms_circuit_breaker()
        if tjms_cb:
            result["TJ-MS"] = {
                "state": tjms_cb.state.value,
                "failure_count": tjms_cb.failure_count,
                "success_count": tjms_cb.success_count
            }

        gemini_cb = get_gemini_circuit_breaker()
        if gemini_cb:
            result["Gemini"] = {
                "state": gemini_cb.state.value,
                "failure_count": gemini_cb.failure_count,
                "success_count": gemini_cb.success_count
            }

        return result
    except ImportError:
        return {}
    except Exception:
        return {}


def _get_cache_status() -> Dict[str, Any]:
    """Obtém status dos caches."""
    try:
        from utils.cache import resumo_cache

        return {
            "resumo_cache": {
                "size": resumo_cache.size(),
                "max_size": resumo_cache._max_size
            }
        }
    except ImportError:
        return {}
    except Exception:
        return {}
