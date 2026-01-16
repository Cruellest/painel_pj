#!/usr/bin/env python3
"""
Benchmark de Latência do Gemini API

Este script mede a latência das chamadas ao Gemini API para diagnóstico
e comparação antes/depois de otimizações.

Uso:
    python scripts/benchmark_gemini.py [--runs 10] [--warmup 2]

Métricas coletadas:
    - Tempo total (ms)
    - Time to First Token (TTFT) (ms)
    - Tempo de preparação (ms)
    - Tokens de resposta
    - Cache hits

Estatísticas calculadas:
    - Média
    - Mediana
    - P95
    - P99
    - Min/Max
"""

import asyncio
import argparse
import statistics
import sys
import os
from datetime import datetime
from typing import List, Dict, Any

# Adiciona o diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.gemini_service import gemini_service, GeminiMetrics, _response_cache


# Prompts de teste (diferentes tamanhos)
TEST_PROMPTS = {
    "small": {
        "prompt": "Responda em uma frase: qual é a capital do Brasil?",
        "system": "Você é um assistente objetivo.",
    },
    "medium": {
        "prompt": """Analise o seguinte texto e extraia as informações principais:

O medicamento Trastuzumabe é indicado para tratamento de câncer de mama HER2 positivo.
A posologia recomendada é de 8mg/kg como dose de ataque, seguida de 6mg/kg a cada 3 semanas.
O medicamento deve ser administrado por via intravenosa.

Extraia: nome do medicamento, indicação, posologia e via de administração.""",
        "system": "Você é um assistente especializado em análise de documentos médicos.",
    },
    "large": {
        "prompt": """Analise o seguinte documento jurídico e extraia as informações estruturadas:

EXCELENTÍSSIMO SENHOR DOUTOR JUIZ DE DIREITO DA VARA DE FAZENDA PÚBLICA DA COMARCA DE CAMPO GRANDE/MS

JOSÉ DA SILVA, brasileiro, casado, portador do RG nº 123456 SSP/MS e CPF nº 123.456.789-00,
residente e domiciliado na Rua das Flores, 123, Bairro Centro, Campo Grande/MS, CEP 79000-000,
vem, respeitosamente, à presença de Vossa Excelência, por meio de seu advogado que esta subscreve,
propor a presente AÇÃO DE OBRIGAÇÃO DE FAZER COM PEDIDO DE TUTELA DE URGÊNCIA em face do
ESTADO DE MATO GROSSO DO SUL, pessoa jurídica de direito público interno, com sede na Avenida
Desembargador José Nunes da Cunha, s/n, Parque dos Poderes, Campo Grande/MS.

DOS FATOS:
O requerente é portador de diabetes mellitus tipo 1 (CID E10) desde 2015, necessitando de
insulina glargina para controle glicêmico. O medicamento foi prescrito pelo médico Dr. João
Santos, CRM/MS 12345, conforme receituário anexo.

O requerente protocolou pedido administrativo junto à Secretaria de Saúde do Estado em
01/01/2024, sob o número 2024/0001, porém até a presente data não obteve resposta.

DO DIREITO:
O direito à saúde é garantido constitucionalmente pelos artigos 6º e 196 da Constituição Federal.

DO PEDIDO:
Ante o exposto, requer:
a) A concessão de tutela de urgência para fornecimento imediato do medicamento;
b) A procedência da ação para condenar o réu ao fornecimento contínuo.

Dá-se à causa o valor de R$ 10.000,00.

Extraia em formato JSON: tipo de ação, autor (nome, CPF, endereço), réu, medicamento solicitado,
CID, médico prescritor, número do protocolo administrativo, pedidos formulados.""",
        "system": """Você é um assistente jurídico especializado em análise de petições.
Extraia as informações de forma estruturada e precisa.
Retorne apenas o JSON, sem explicações adicionais.""",
    }
}


async def run_single_benchmark(prompt_type: str, use_cache: bool = True) -> Dict[str, Any]:
    """Executa uma única chamada de benchmark"""
    test = TEST_PROMPTS[prompt_type]

    response = await gemini_service.generate(
        prompt=test["prompt"],
        system_prompt=test["system"],
        temperature=0.1,  # Baixa para determinismo
        use_cache=use_cache
    )

    if response.metrics:
        return {
            "success": response.success,
            "prompt_type": prompt_type,
            "prompt_chars": response.metrics.prompt_chars,
            "response_tokens": response.metrics.response_tokens,
            "time_total_ms": response.metrics.time_total_ms,
            "time_ttft_ms": response.metrics.time_ttft_ms,
            "time_prepare_ms": response.metrics.time_prepare_ms,
            "cached": response.metrics.cached,
            "retry_count": response.metrics.retry_count,
        }
    else:
        return {
            "success": response.success,
            "error": response.error,
            "prompt_type": prompt_type,
        }


def calculate_stats(values: List[float]) -> Dict[str, float]:
    """Calcula estatísticas de uma lista de valores"""
    if not values:
        return {}

    sorted_values = sorted(values)
    n = len(sorted_values)

    return {
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "stdev": statistics.stdev(values) if n > 1 else 0,
        "min": min(values),
        "max": max(values),
        "p95": sorted_values[int(n * 0.95)] if n >= 20 else sorted_values[-1],
        "p99": sorted_values[int(n * 0.99)] if n >= 100 else sorted_values[-1],
    }


async def run_benchmark(runs: int = 10, warmup: int = 2, prompt_type: str = "medium"):
    """Executa o benchmark completo"""
    print("=" * 70)
    print("BENCHMARK DE LATÊNCIA - GEMINI API")
    print("=" * 70)
    print(f"Data/Hora: {datetime.now().isoformat()}")
    print(f"Runs: {runs} | Warmup: {warmup} | Prompt: {prompt_type}")
    print(f"Tamanho do prompt: {len(TEST_PROMPTS[prompt_type]['prompt'])} chars")
    print()

    # Verifica se API key está configurada
    if not gemini_service.is_configured():
        print("ERRO: GEMINI_KEY não configurada!")
        print("Configure a variável de ambiente GEMINI_KEY e tente novamente.")
        return

    # Warmup (sem cache para aquecer conexões)
    print(f"[1/3] Warmup ({warmup} runs sem cache)...")
    for i in range(warmup):
        result = await run_single_benchmark(prompt_type, use_cache=False)
        status = "OK" if result.get("success") else f"ERRO: {result.get('error', 'unknown')}"
        time_ms = result.get("time_total_ms", 0)
        print(f"  Warmup {i+1}: {time_ms:.0f}ms - {status}")

    # Benchmark principal (sem cache para medir latência real)
    print(f"\n[2/3] Benchmark principal ({runs} runs sem cache)...")
    results_no_cache = []
    for i in range(runs):
        result = await run_single_benchmark(prompt_type, use_cache=False)
        results_no_cache.append(result)
        status = "OK" if result.get("success") else "ERRO"
        time_ms = result.get("time_total_ms", 0)
        ttft_ms = result.get("time_ttft_ms", 0)
        print(f"  Run {i+1:2d}: total={time_ms:6.0f}ms  ttft={ttft_ms:6.0f}ms  {status}")

    # Benchmark com cache
    print(f"\n[3/3] Benchmark com cache ({runs} runs)...")
    results_cache = []
    for i in range(runs):
        result = await run_single_benchmark(prompt_type, use_cache=True)
        results_cache.append(result)
        cached = "CACHE" if result.get("cached") else "API"
        time_ms = result.get("time_total_ms", 0)
        print(f"  Run {i+1:2d}: total={time_ms:6.0f}ms  {cached}")

    # Calcula estatísticas
    print("\n" + "=" * 70)
    print("RESULTADOS")
    print("=" * 70)

    # Filtra apenas resultados bem-sucedidos
    success_no_cache = [r for r in results_no_cache if r.get("success")]
    success_cache = [r for r in results_cache if r.get("success")]

    if success_no_cache:
        times_total = [r["time_total_ms"] for r in success_no_cache]
        times_ttft = [r["time_ttft_ms"] for r in success_no_cache]

        stats_total = calculate_stats(times_total)
        stats_ttft = calculate_stats(times_ttft)

        print("\n[SEM CACHE - Latência Real da API]")
        print(f"  Tempo Total (ms):")
        print(f"    Média:   {stats_total['mean']:7.0f}ms")
        print(f"    Mediana: {stats_total['median']:7.0f}ms")
        print(f"    P95:     {stats_total['p95']:7.0f}ms")
        print(f"    P99:     {stats_total['p99']:7.0f}ms")
        print(f"    Min/Max: {stats_total['min']:7.0f}ms / {stats_total['max']:.0f}ms")

        print(f"\n  Time to First Token (ms):")
        print(f"    Média:   {stats_ttft['mean']:7.0f}ms")
        print(f"    Mediana: {stats_ttft['median']:7.0f}ms")
        print(f"    P95:     {stats_ttft['p95']:7.0f}ms")

        # Tokens
        tokens = [r["response_tokens"] for r in success_no_cache if r.get("response_tokens")]
        if tokens:
            print(f"\n  Tokens de resposta: {statistics.mean(tokens):.0f} (média)")

    if success_cache:
        cache_hits = sum(1 for r in success_cache if r.get("cached"))
        cache_times = [r["time_total_ms"] for r in success_cache if r.get("cached")]

        print(f"\n[COM CACHE]")
        print(f"  Cache hits: {cache_hits}/{len(success_cache)}")
        if cache_times:
            print(f"  Tempo médio (cache hit): {statistics.mean(cache_times):.2f}ms")

    # Estatísticas do cache
    cache_stats = _response_cache.stats()
    print(f"\n[CACHE STATS]")
    print(f"  Tamanho: {cache_stats['size']}/{cache_stats['max_size']}")
    print(f"  Hits: {cache_stats['hits']} | Misses: {cache_stats['misses']}")
    print(f"  Hit Rate: {cache_stats['hit_rate']}")

    # Erros
    errors = [r for r in results_no_cache if not r.get("success")]
    if errors:
        print(f"\n[ERROS: {len(errors)}]")
        for e in errors[:3]:
            print(f"  - {e.get('error', 'unknown')[:80]}")

    print("\n" + "=" * 70)
    print("FIM DO BENCHMARK")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Benchmark de latência do Gemini API")
    parser.add_argument("--runs", type=int, default=10, help="Número de execuções (default: 10)")
    parser.add_argument("--warmup", type=int, default=2, help="Execuções de warmup (default: 2)")
    parser.add_argument("--prompt", choices=["small", "medium", "large"], default="medium",
                        help="Tipo de prompt (default: medium)")

    args = parser.parse_args()

    asyncio.run(run_benchmark(
        runs=args.runs,
        warmup=args.warmup,
        prompt_type=args.prompt
    ))


if __name__ == "__main__":
    main()
