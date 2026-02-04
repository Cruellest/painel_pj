#!/usr/bin/env python
# scripts/benchmark_latencia.py
"""
Script de benchmark para medir latencia do gerador de pecas.

Executa N requests do mesmo processo e reporta:
- p50/p95 de TTFT e latencia total
- Breakdown por etapa (agente1, agente2, llm, db)
- Estatisticas de streaming (chunks, intervalos)

Uso:
    python scripts/benchmark_latencia.py --cnj 08043300920248120017 --runs 5
    python scripts/benchmark_latencia.py --cnj 08043300920248120017 --runs 3 --tipo contestacao

Requer:
    - Servidor rodando em localhost:8000
    - Token de autenticacao valido no arquivo .env (BENCHMARK_TOKEN)

Autor: LAB/PGE-MS
"""

import os
import sys
import json
import time
import asyncio
import argparse
import statistics
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

import httpx
from dotenv import load_dotenv

load_dotenv()

# Configuracao
API_BASE_URL = os.getenv("BENCHMARK_API_URL", "http://localhost:8000")
AUTH_TOKEN = os.getenv("BENCHMARK_TOKEN", "")


@dataclass
class BenchmarkResult:
    """Resultado de uma execucao de benchmark"""
    run_number: int
    success: bool
    error: Optional[str] = None

    # Tempos em ms
    total_ms: float = 0
    ttft_ms: float = 0
    agente1_ms: float = 0
    agente2_ms: float = 0
    llm_ms: float = 0
    db_ms: float = 0

    # Streaming
    total_chunks: int = 0
    total_bytes: int = 0
    avg_chunk_interval_ms: float = 0

    # Metadados
    request_id: str = ""
    modelo: str = ""
    tipo_peca: str = ""


@dataclass
class BenchmarkSummary:
    """Resumo de todas as execucoes"""
    runs: int = 0
    success_count: int = 0
    error_count: int = 0

    # Estatisticas de latencia (ms)
    total_p50: float = 0
    total_p95: float = 0
    total_avg: float = 0
    total_min: float = 0
    total_max: float = 0

    ttft_p50: float = 0
    ttft_p95: float = 0
    ttft_avg: float = 0

    agente1_avg: float = 0
    agente2_avg: float = 0
    llm_avg: float = 0
    db_avg: float = 0

    # Streaming
    chunks_avg: float = 0
    chunk_interval_avg: float = 0


def calculate_percentile(values: List[float], percentile: float) -> float:
    """Calcula percentil de uma lista de valores"""
    if not values:
        return 0
    sorted_values = sorted(values)
    index = int(len(sorted_values) * percentile / 100)
    return sorted_values[min(index, len(sorted_values) - 1)]


async def run_single_benchmark(
    client: httpx.AsyncClient,
    cnj: str,
    tipo_peca: Optional[str],
    run_number: int,
    group_id: Optional[int] = None
) -> BenchmarkResult:
    """Executa um unico benchmark"""
    result = BenchmarkResult(run_number=run_number, success=False)

    try:
        # Prepara payload
        payload = {
            "numero_cnj": cnj,
            "tipo_peca": tipo_peca
        }
        if group_id:
            payload["group_id"] = group_id

        headers = {
            "Authorization": f"Bearer {AUTH_TOKEN}",
            "Content-Type": "application/json"
        }

        t_start = time.perf_counter()
        first_chunk_time = None
        chunks = []
        chunk_times = []
        last_chunk_time = None

        # Faz request com streaming
        async with client.stream(
            "POST",
            f"{API_BASE_URL}/gerador-pecas/api/processar-stream",
            json=payload,
            headers=headers,
            timeout=300.0
        ) as response:
            if response.status_code != 200:
                result.error = f"HTTP {response.status_code}"
                return result

            # Processa eventos SSE
            buffer = ""
            async for chunk in response.aiter_bytes():
                now = time.perf_counter()

                if first_chunk_time is None:
                    first_chunk_time = now
                    result.ttft_ms = (now - t_start) * 1000

                if last_chunk_time is not None:
                    chunk_times.append((now - last_chunk_time) * 1000)
                last_chunk_time = now

                buffer += chunk.decode("utf-8")

                # Processa linhas completas
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()

                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            chunks.append(data)

                            # Extrai metricas do evento final
                            if data.get("tipo") == "sucesso":
                                perf = data.get("performance", {})
                                if perf:
                                    result.ttft_ms = perf.get("ttft_ms") or result.ttft_ms
                                    result.total_ms = perf.get("total_ms", 0)
                                    result.request_id = perf.get("request_id", "")

                                result.tipo_peca = data.get("tipo_peca", "")

                            elif data.get("tipo") == "erro":
                                result.error = data.get("mensagem", "Erro desconhecido")

                        except json.JSONDecodeError:
                            pass

        t_end = time.perf_counter()

        # Finaliza resultado
        if not result.error:
            result.success = True

        if result.total_ms == 0:
            result.total_ms = (t_end - t_start) * 1000

        result.total_chunks = len(chunks)
        result.total_bytes = sum(len(json.dumps(c)) for c in chunks)

        if chunk_times:
            result.avg_chunk_interval_ms = statistics.mean(chunk_times)

    except httpx.TimeoutException:
        result.error = "Timeout"
    except Exception as e:
        result.error = str(e)

    return result


async def run_benchmark(
    cnj: str,
    runs: int,
    tipo_peca: Optional[str] = None,
    group_id: Optional[int] = None
) -> BenchmarkSummary:
    """Executa benchmark completo"""
    results: List[BenchmarkResult] = []

    print(f"\n{'='*60}")
    print(f"BENCHMARK DE LATENCIA - GERADOR DE PECAS")
    print(f"{'='*60}")
    print(f"CNJ: {cnj}")
    print(f"Tipo de peca: {tipo_peca or 'auto'}")
    print(f"Execucoes: {runs}")
    print(f"API: {API_BASE_URL}")
    print(f"{'='*60}\n")

    async with httpx.AsyncClient() as client:
        for i in range(runs):
            print(f"[{i+1}/{runs}] Executando...", end=" ", flush=True)

            result = await run_single_benchmark(
                client=client,
                cnj=cnj,
                tipo_peca=tipo_peca,
                run_number=i + 1,
                group_id=group_id
            )
            results.append(result)

            if result.success:
                print(f"OK - TTFT: {result.ttft_ms:.0f}ms | Total: {result.total_ms:.0f}ms | Chunks: {result.total_chunks}")
            else:
                print(f"ERRO - {result.error}")

            # Intervalo entre execucoes
            if i < runs - 1:
                await asyncio.sleep(2)

    # Calcula sumario
    summary = BenchmarkSummary(runs=runs)
    summary.success_count = sum(1 for r in results if r.success)
    summary.error_count = sum(1 for r in results if not r.success)

    successful = [r for r in results if r.success]

    if successful:
        totals = [r.total_ms for r in successful]
        ttfts = [r.ttft_ms for r in successful if r.ttft_ms > 0]
        chunks_list = [r.total_chunks for r in successful]
        intervals = [r.avg_chunk_interval_ms for r in successful if r.avg_chunk_interval_ms > 0]

        summary.total_avg = statistics.mean(totals)
        summary.total_p50 = calculate_percentile(totals, 50)
        summary.total_p95 = calculate_percentile(totals, 95)
        summary.total_min = min(totals)
        summary.total_max = max(totals)

        if ttfts:
            summary.ttft_avg = statistics.mean(ttfts)
            summary.ttft_p50 = calculate_percentile(ttfts, 50)
            summary.ttft_p95 = calculate_percentile(ttfts, 95)

        if chunks_list:
            summary.chunks_avg = statistics.mean(chunks_list)

        if intervals:
            summary.chunk_interval_avg = statistics.mean(intervals)

    return summary


def print_summary(summary: BenchmarkSummary):
    """Imprime resumo do benchmark"""
    print(f"\n{'='*60}")
    print("RESUMO DO BENCHMARK")
    print(f"{'='*60}")
    print(f"\nExecucoes: {summary.runs} ({summary.success_count} sucesso, {summary.error_count} erro)")

    if summary.success_count > 0:
        print(f"\n--- LATENCIA TOTAL ---")
        print(f"  p50:  {summary.total_p50:.0f}ms")
        print(f"  p95:  {summary.total_p95:.0f}ms")
        print(f"  avg:  {summary.total_avg:.0f}ms")
        print(f"  min:  {summary.total_min:.0f}ms")
        print(f"  max:  {summary.total_max:.0f}ms")

        print(f"\n--- TTFT (Time To First Token) ---")
        print(f"  p50:  {summary.ttft_p50:.0f}ms")
        print(f"  p95:  {summary.ttft_p95:.0f}ms")
        print(f"  avg:  {summary.ttft_avg:.0f}ms")

        print(f"\n--- STREAMING ---")
        print(f"  Chunks (avg):    {summary.chunks_avg:.0f}")
        print(f"  Intervalo (avg): {summary.chunk_interval_avg:.1f}ms")

    print(f"\n{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="Benchmark de latencia do gerador de pecas")
    parser.add_argument("--cnj", required=True, help="Numero CNJ do processo")
    parser.add_argument("--runs", type=int, default=5, help="Numero de execucoes (default: 5)")
    parser.add_argument("--tipo", help="Tipo de peca (opcional)")
    parser.add_argument("--group-id", type=int, help="ID do grupo de prompts (opcional)")
    parser.add_argument("--url", help="URL base da API (default: http://localhost:8000)")
    parser.add_argument("--token", help="Token de autenticacao (opcional)")

    args = parser.parse_args()

    # Configura URL e token
    global API_BASE_URL, AUTH_TOKEN
    if args.url:
        API_BASE_URL = args.url
    if args.token:
        AUTH_TOKEN = args.token

    if not AUTH_TOKEN:
        print("ERRO: Token de autenticacao nao configurado.")
        print("Configure BENCHMARK_TOKEN no .env ou use --token")
        sys.exit(1)

    # Executa benchmark
    summary = asyncio.run(run_benchmark(
        cnj=args.cnj,
        runs=args.runs,
        tipo_peca=args.tipo,
        group_id=args.group_id
    ))

    # Imprime resumo
    print_summary(summary)


if __name__ == "__main__":
    main()
