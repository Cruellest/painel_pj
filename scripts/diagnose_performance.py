#!/usr/bin/env python3
# scripts/diagnose_performance.py
"""
Script de diagnóstico de performance para o painel admin.

Simula navegação no painel, acessando rotas críticas e registrando tempos.
Os logs são registrados usando o mesmo sistema de performance logs.

Uso:
    python scripts/diagnose_performance.py --base-url http://localhost:8000 --username admin --password senha

Requisitos:
    - Sistema rodando
    - Usuário admin válido
    - Toggle de performance logs ATIVADO
"""

import argparse
import asyncio
import time
import sys
import os
import json
from typing import List, Dict, Any
from datetime import datetime

# Adiciona o diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import httpx
except ImportError:
    print("Erro: httpx não está instalado. Execute: pip install httpx")
    sys.exit(1)


# ==================================================
# CONFIGURAÇÃO
# ==================================================

DEFAULT_TIMEOUT = 60.0  # segundos
ROTAS_CRITICAS = [
    # Dashboard e páginas principais
    {"method": "GET", "path": "/dashboard", "name": "Dashboard"},
    {"method": "GET", "path": "/admin/gerador-pecas", "name": "Admin Gerador Peças"},
    {"method": "GET", "path": "/admin/prompts-modulos", "name": "Admin Prompts Módulos"},
    {"method": "GET", "path": "/admin/categorias-json", "name": "Admin Categorias JSON"},
    {"method": "GET", "path": "/admin/variaveis", "name": "Admin Variáveis"},

    # APIs críticas
    {"method": "GET", "path": "/admin/api/categorias-json", "name": "API Lista Categorias"},
    {"method": "GET", "path": "/admin/api/extraction/variaveis", "name": "API Lista Variáveis"},
    {"method": "GET", "path": "/admin/api/prompts-modulos", "name": "API Lista Prompts"},
    {"method": "GET", "path": "/admin/api/prompts-modulos/grupos", "name": "API Lista Grupos"},

    # Performance próprio (meta-teste)
    {"method": "GET", "path": "/admin/performance/toggle", "name": "API Toggle Status"},
    {"method": "GET", "path": "/admin/performance/summary?hours=24", "name": "API Summary"},
]


# ==================================================
# FUNÇÕES AUXILIARES
# ==================================================

def print_header(text: str):
    """Imprime cabeçalho formatado."""
    print("\n" + "=" * 60)
    print(f" {text}")
    print("=" * 60)


def print_result(name: str, duration_ms: float, status: int, success: bool):
    """Imprime resultado de uma rota."""
    color = "\033[92m" if success else "\033[91m"  # Verde ou vermelho
    reset = "\033[0m"
    warning = "\033[93m"  # Amarelo

    duration_color = reset
    if duration_ms > 1000:
        duration_color = "\033[91m"  # Vermelho
    elif duration_ms > 500:
        duration_color = warning

    icon = "[OK]" if success else "[X]"
    print(f"  {color}{icon}{reset} {name:<40} {duration_color}{duration_ms:>8.1f}ms{reset}  [{status}]")


async def login(client: httpx.AsyncClient, base_url: str, username: str, password: str) -> str:
    """Faz login e retorna o token JWT."""
    print(f"\n[*] Fazendo login como '{username}'...")

    try:
        response = await client.post(
            f"{base_url}/auth/login",
            data={"username": username, "password": password},
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token")
            if token:
                print(f"[OK] Login realizado com sucesso!")
                return token

        print(f"[ERRO] Falha no login: {response.status_code} - {response.text}")
        return None

    except Exception as e:
        print(f"[ERRO] Exceção no login: {e}")
        return None


async def check_performance_toggle(client: httpx.AsyncClient, base_url: str, token: str) -> bool:
    """Verifica se o toggle de performance está ativado."""
    try:
        response = await client.get(
            f"{base_url}/admin/performance/toggle",
            headers={"Authorization": f"Bearer {token}"}
        )

        if response.status_code == 200:
            data = response.json()
            return data.get("enabled", False)

    except Exception:
        pass

    return False


async def test_route(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    route: Dict[str, str]
) -> Dict[str, Any]:
    """Testa uma rota e retorna métricas."""
    method = route["method"]
    path = route["path"]
    name = route["name"]

    start = time.perf_counter()
    status = 0
    success = False
    error = None

    try:
        if method == "GET":
            response = await client.get(
                f"{base_url}{path}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=DEFAULT_TIMEOUT
            )
        elif method == "POST":
            response = await client.post(
                f"{base_url}{path}",
                headers={"Authorization": f"Bearer {token}"},
                json=route.get("body", {}),
                timeout=DEFAULT_TIMEOUT
            )
        else:
            raise ValueError(f"Método não suportado: {method}")

        status = response.status_code
        success = 200 <= status < 400

    except httpx.TimeoutException:
        error = "TIMEOUT"
        status = 504
    except Exception as e:
        error = str(e)
        status = 500

    duration_ms = (time.perf_counter() - start) * 1000

    return {
        "name": name,
        "method": method,
        "path": path,
        "duration_ms": duration_ms,
        "status": status,
        "success": success,
        "error": error
    }


async def run_diagnostic(
    base_url: str,
    username: str,
    password: str,
    iterations: int = 1,
    concurrent: bool = False
):
    """Executa o diagnóstico completo."""
    print_header("DIAGNÓSTICO DE PERFORMANCE - Portal PGE")
    print(f"\nBase URL: {base_url}")
    print(f"Usuário: {username}")
    print(f"Iterações: {iterations}")
    print(f"Modo: {'Concorrente' if concurrent else 'Sequencial'}")

    async with httpx.AsyncClient(verify=False) as client:
        # Login
        token = await login(client, base_url, username, password)
        if not token:
            print("\n[ERRO] Não foi possível fazer login. Abortando.")
            return

        # Verifica toggle
        toggle_active = await check_performance_toggle(client, base_url, token)
        if toggle_active:
            print("[OK] Toggle de performance logs está ATIVO")
        else:
            print("[AVISO] Toggle de performance logs está DESATIVADO")
            print("        Os tempos serão medidos, mas não serão salvos no BD.")

        # Executa testes
        all_results = []

        for i in range(iterations):
            if iterations > 1:
                print_header(f"ITERAÇÃO {i + 1}/{iterations}")

            print(f"\n[*] Testando {len(ROTAS_CRITICAS)} rotas...")

            if concurrent:
                # Executa todas em paralelo
                tasks = [
                    test_route(client, base_url, token, route)
                    for route in ROTAS_CRITICAS
                ]
                results = await asyncio.gather(*tasks)
            else:
                # Executa sequencialmente
                results = []
                for route in ROTAS_CRITICAS:
                    result = await test_route(client, base_url, token, route)
                    results.append(result)

            # Exibe resultados
            print("\nResultados:")
            for result in results:
                print_result(
                    result["name"],
                    result["duration_ms"],
                    result["status"],
                    result["success"]
                )

            all_results.extend(results)

            if i < iterations - 1:
                await asyncio.sleep(1)  # Pausa entre iterações

        # Resumo final
        print_header("RESUMO")

        successful = [r for r in all_results if r["success"]]
        failed = [r for r in all_results if not r["success"]]

        print(f"\nTotal de requisições: {len(all_results)}")
        print(f"Sucesso: {len(successful)} ({len(successful)/len(all_results)*100:.1f}%)")
        print(f"Falhas: {len(failed)} ({len(failed)/len(all_results)*100:.1f}%)")

        if successful:
            durations = [r["duration_ms"] for r in successful]
            avg = sum(durations) / len(durations)
            min_d = min(durations)
            max_d = max(durations)

            print(f"\nTempos (requisições bem-sucedidas):")
            print(f"  Média: {avg:.1f}ms")
            print(f"  Mínimo: {min_d:.1f}ms")
            print(f"  Máximo: {max_d:.1f}ms")

            # Rotas mais lentas
            slow = sorted(successful, key=lambda x: x["duration_ms"], reverse=True)[:5]
            print(f"\nRotas mais lentas:")
            for r in slow:
                print(f"  - {r['name']}: {r['duration_ms']:.1f}ms")

        if failed:
            print(f"\nFalhas:")
            for r in failed:
                print(f"  - {r['name']}: {r['error'] or f'HTTP {r['status']}'}")

        # Salva relatório
        report_path = save_report(all_results, base_url, username)
        print(f"\nRelatório salvo em: {report_path}")


def save_report(results: List[Dict], base_url: str, username: str) -> str:
    """Salva relatório em arquivo JSON."""
    report_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "logs", "performance"
    )
    os.makedirs(report_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(report_dir, f"diagnostic_{timestamp}.json")

    report = {
        "timestamp": datetime.now().isoformat(),
        "base_url": base_url,
        "username": username,
        "total_requests": len(results),
        "successful": len([r for r in results if r["success"]]),
        "failed": len([r for r in results if not r["success"]]),
        "results": results
    }

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    return report_path


# ==================================================
# MAIN
# ==================================================

def main():
    parser = argparse.ArgumentParser(
        description="Script de diagnóstico de performance do Portal PGE"
    )
    parser.add_argument(
        "--base-url", "-u",
        default="http://localhost:8000",
        help="URL base do sistema (default: http://localhost:8000)"
    )
    parser.add_argument(
        "--username", "-U",
        default="admin",
        help="Nome de usuário admin (default: admin)"
    )
    parser.add_argument(
        "--password", "-P",
        required=True,
        help="Senha do usuário admin"
    )
    parser.add_argument(
        "--iterations", "-i",
        type=int,
        default=1,
        help="Número de iterações (default: 1)"
    )
    parser.add_argument(
        "--concurrent", "-c",
        action="store_true",
        help="Executar requisições em paralelo"
    )

    args = parser.parse_args()

    asyncio.run(run_diagnostic(
        base_url=args.base_url,
        username=args.username,
        password=args.password,
        iterations=args.iterations,
        concurrent=args.concurrent
    ))


if __name__ == "__main__":
    main()
