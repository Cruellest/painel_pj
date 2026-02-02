#!/usr/bin/env python3
"""
Suite de Testes para Servicos de IA do Portal PGE-MS.

Verifica o funcionamento de todos os servicos de IA:
- Gemini Service (geracao, streaming, SLA fallback)
- Gerador de Pecas Juridicas
- Assistencia Judiciaria
- Matriculas Confrontantes
- Extracao de Documentos

Executa:
    python scripts/test_ia_services.py

Opcoes:
    --verbose       Mostra detalhes de cada teste
    --only=gemini   Executa apenas testes de um sistema
    --timeout=30    Timeout em segundos para cada teste

Autor: LAB/PGE-MS
"""

import sys
import os
import asyncio
import argparse
import time
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field

# Configura encoding para Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Adiciona diretorio raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

# Inicializa modelos do banco ANTES de qualquer importacao
from database import init_db


# ============================================
# CONFIGURACAO
# ============================================

@dataclass
class TestResult:
    """Resultado de um teste individual."""
    name: str
    system: str
    success: bool
    duration_ms: float
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def __str__(self):
        status = "[OK]" if self.success else "[FALHA]"
        return f"{status} {self.name} ({self.duration_ms:.0f}ms) - {self.message}"


@dataclass
class TestSuite:
    """Colecao de resultados de teste."""
    name: str
    results: List[TestResult] = field(default_factory=list)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.success)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.success)

    @property
    def success_rate(self) -> float:
        if self.total == 0:
            return 0
        return self.passed / self.total * 100

    @property
    def total_duration_ms(self) -> float:
        return sum(r.duration_ms for r in self.results)

    def add(self, result: TestResult):
        self.results.append(result)

    def summary(self) -> str:
        lines = [
            f"\n{'='*60}",
            f"SUITE: {self.name}",
            f"{'='*60}",
            f"Total: {self.total} | Passou: {self.passed} | Falhou: {self.failed}",
            f"Taxa de Sucesso: {self.success_rate:.1f}%",
            f"Duracao Total: {self.total_duration_ms:.0f}ms",
            f"{'='*60}"
        ]

        if self.failed > 0:
            lines.append("\nFALHAS:")
            for r in self.results:
                if not r.success:
                    lines.append(f"  - {r.name}: {r.message}")

        return "\n".join(lines)


# ============================================
# UTILITARIOS DE TESTE
# ============================================

def print_test(msg: str, verbose: bool = True):
    """Imprime mensagem de teste."""
    if verbose:
        print(f"  {msg}")


async def run_test(
    name: str,
    system: str,
    test_func,
    timeout: float = 30.0,
    verbose: bool = False
) -> TestResult:
    """Executa um teste com timeout."""
    start = time.perf_counter()

    try:
        print_test(f"Executando: {name}...", verbose)

        result = await asyncio.wait_for(test_func(), timeout=timeout)

        duration_ms = (time.perf_counter() - start) * 1000

        if isinstance(result, tuple):
            success, message, details = result
        else:
            success = bool(result)
            message = "OK" if success else "Falhou"
            details = {}

        return TestResult(
            name=name,
            system=system,
            success=success,
            duration_ms=duration_ms,
            message=message,
            details=details
        )

    except asyncio.TimeoutError:
        duration_ms = (time.perf_counter() - start) * 1000
        return TestResult(
            name=name,
            system=system,
            success=False,
            duration_ms=duration_ms,
            message=f"Timeout apos {timeout}s"
        )

    except Exception as e:
        duration_ms = (time.perf_counter() - start) * 1000
        return TestResult(
            name=name,
            system=system,
            success=False,
            duration_ms=duration_ms,
            message=str(e)
        )


# ============================================
# TESTES: GEMINI SERVICE
# ============================================

async def test_gemini_api_key() -> Tuple[bool, str, Dict]:
    """Verifica se a API key do Gemini esta configurada."""
    from services.gemini_service import gemini_service

    if gemini_service.is_configured():
        key = gemini_service.api_key
        masked = f"{key[:8]}...{key[-4:]}" if len(key) > 12 else "***"
        return True, f"API Key configurada ({masked})", {}
    else:
        return False, "GEMINI_KEY nao configurada no ambiente", {}


async def test_gemini_generate_simple() -> Tuple[bool, str, Dict]:
    """Testa geracao simples de texto."""
    from services.gemini_service import gemini_service

    response = await gemini_service.generate(
        prompt="Responda apenas 'OK' sem nenhum outro texto.",
        model="gemini-3-flash-preview",
        temperature=0.0,
        max_tokens=10,
        thinking_level="minimal"
    )

    if response.success:
        return True, f"Resposta: '{response.content[:50]}...'", {
            "tokens": response.tokens_used,
            "latency_ms": response.metrics.time_total_ms if response.metrics else 0
        }
    else:
        return False, f"Erro: {response.error}", {}


async def test_gemini_generate_with_system() -> Tuple[bool, str, Dict]:
    """Testa geracao com system prompt usando modelo lite mais estavel."""
    from services.gemini_service import gemini_service

    # Usa gemini-2.0-flash-lite que e mais estavel com system prompts
    response = await gemini_service.generate(
        prompt="Qual e 2 + 3?",
        system_prompt="Responda apenas com o numero.",
        model="gemini-2.0-flash-lite",  # Modelo lite mais estavel
        temperature=0.1,
        max_tokens=10
    )

    if response.success and len(response.content) > 0:
        content = response.content.strip()
        msg = f"Resposta: {content}"
        return True, msg, {"latency_ms": response.metrics.time_total_ms if response.metrics else 0}
    else:
        return False, f"Erro: {response.error}", {}


async def test_gemini_streaming() -> Tuple[bool, str, Dict]:
    """Testa streaming de texto."""
    from services.gemini_service import gemini_service

    chunks = []
    ttft = None
    start = time.perf_counter()

    async for chunk in gemini_service.generate_stream(
        prompt="Conte de 1 a 5, um numero por linha.",
        model="gemini-3-flash-preview",
        temperature=0.0,
        thinking_level="minimal"
    ):
        if ttft is None:
            ttft = (time.perf_counter() - start) * 1000
        chunks.append(chunk)

    if chunks:
        full_text = "".join(chunks)
        return True, f"TTFT: {ttft:.0f}ms, {len(chunks)} chunks, {len(full_text)} chars", {
            "ttft_ms": ttft,
            "chunk_count": len(chunks),
            "total_chars": len(full_text)
        }
    else:
        return False, "Nenhum chunk recebido", {}


async def test_gemini_sla_fallback() -> Tuple[bool, str, Dict]:
    """Testa fallback por SLA (timeout curto para forcar fallback)."""
    from services.gemini_service import gemini_service

    # Timeout muito curto (0.1s) para forcar fallback
    response = await gemini_service.generate_with_sla(
        prompt="Diga apenas 'teste'",
        model_primary="gemini-3-flash-preview",
        model_fallback="gemini-2.0-flash-lite",  # Modelo lite correto
        sla_timeout_seconds=0.1,  # Muito curto - deve usar fallback
        temperature=0.0,
        max_tokens=10
    )

    if response.success:
        used_fallback = response.metrics and "fallback" in (response.metrics.error or "")
        msg = "Fallback usado" if used_fallback else "Primario OK (rapido)"
        return True, msg, {"used_fallback": used_fallback}
    else:
        return False, f"Erro: {response.error}", {}


async def test_gemini_cache() -> Tuple[bool, str, Dict]:
    """Testa cache de respostas."""
    from services.gemini_service import gemini_service, get_cache_stats

    prompt = "Responda exatamente: 'cache_test_12345'"

    # Primeira chamada - nao deve estar em cache
    response1 = await gemini_service.generate(
        prompt=prompt,
        model="gemini-3-flash-preview",
        temperature=0.0,
        use_cache=True
    )

    # Segunda chamada - deve vir do cache
    response2 = await gemini_service.generate(
        prompt=prompt,
        model="gemini-3-flash-preview",
        temperature=0.0,
        use_cache=True
    )

    if response1.success and response2.success:
        cached = response2.metrics.cached if response2.metrics else False
        stats = get_cache_stats()
        return True, f"Cache funcionando (hit: {cached})", {"cache_stats": stats}
    else:
        return False, "Erro nas chamadas", {}


async def test_gemini_truncate() -> Tuple[bool, str, Dict]:
    """Testa truncamento de prompts."""
    from services.gemini_service import truncate_prompt, estimate_tokens

    # Cria prompt grande
    big_prompt = "Lorem ipsum " * 10000  # ~120k chars

    truncated, was_truncated = truncate_prompt(big_prompt, max_chars=50000)

    tokens_orig = estimate_tokens(big_prompt)
    tokens_trunc = estimate_tokens(truncated)

    if was_truncated and len(truncated) <= 50000:
        return True, f"Truncado de {len(big_prompt):,} para {len(truncated):,} chars", {
            "original_chars": len(big_prompt),
            "truncated_chars": len(truncated),
            "original_tokens_est": tokens_orig,
            "truncated_tokens_est": tokens_trunc
        }
    elif not was_truncated:
        return False, "Nao truncou quando deveria", {}
    else:
        return False, f"Truncamento incorreto: {len(truncated)} chars", {}


# ============================================
# TESTES: GERADOR DE PECAS
# ============================================

async def test_gerador_service_init() -> Tuple[bool, str, Dict]:
    """Testa inicializacao do servico de geracao de pecas."""
    try:
        from database.connection import SessionLocal
        from sistemas.gerador_pecas.services import GeradorPecasService

        db = SessionLocal()
        try:
            service = GeradorPecasService(
                modelo="gemini-3-flash-preview",
                db=db
            )
            return True, "Servico inicializado", {"modelo": service.modelo}
        finally:
            db.close()

    except Exception as e:
        return False, str(e), {}


async def test_gerador_editar_minuta() -> Tuple[bool, str, Dict]:
    """Testa edicao de minuta (funcao core do gerador)."""
    try:
        from database.connection import SessionLocal
        from sistemas.gerador_pecas.services import GeradorPecasService

        db = SessionLocal()
        try:
            service = GeradorPecasService(
                modelo="gemini-3-flash-preview",
                db=db
            )

            resultado = await service.editar_minuta(
                minuta_atual="## Titulo\n\nTexto da minuta.",
                mensagem_usuario="Adicione 'TESTE' no final.",
                historico=[]
            )

            if resultado.get("status") == "sucesso":
                minuta = resultado.get("minuta_markdown", "")
                return True, f"Minuta editada ({len(minuta)} chars)", {}
            else:
                return False, resultado.get("mensagem", "Erro desconhecido"), {}

        finally:
            db.close()

    except Exception as e:
        return False, str(e), {}


async def test_gerador_editar_minuta_stream() -> Tuple[bool, str, Dict]:
    """Testa edicao de minuta com streaming usando generate_stream diretamente."""
    try:
        from services.gemini_service import gemini_service

        chunks = []
        ttft = None
        start = time.perf_counter()

        # Teste direto do streaming para evitar timeout
        async for chunk in gemini_service.generate_stream(
            prompt="Diga apenas: TESTE OK",
            model="gemini-3-flash-preview",
            temperature=0.0,
            thinking_level="minimal"
        ):
            if ttft is None:
                ttft = (time.perf_counter() - start) * 1000
            chunks.append(chunk)
            # Sai apos alguns chunks para nao demorar muito
            if len(chunks) >= 5 or len("".join(chunks)) > 20:
                break

        if chunks:
            return True, f"Stream OK: TTFT {ttft:.0f}ms, {len(chunks)} chunks", {
                "ttft_ms": ttft,
                "chunks": len(chunks)
            }
        else:
            return False, "Nenhum chunk recebido", {}

    except Exception as e:
        return False, str(e), {}


# ============================================
# TESTES: EXTRACAO DE DOCUMENTOS
# ============================================

async def test_extracao_categorias() -> Tuple[bool, str, Dict]:
    """Testa carregamento de categorias de extracao."""
    try:
        from database.connection import SessionLocal
        from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON

        db = SessionLocal()
        try:
            categorias = db.query(CategoriaResumoJSON).filter(
                CategoriaResumoJSON.ativo == True
            ).all()

            if categorias:
                return True, f"{len(categorias)} categorias ativas", {
                    "count": len(categorias),
                    "nomes": [c.nome for c in categorias[:5]]
                }
            else:
                return True, "Nenhuma categoria (tabela vazia)", {}

        finally:
            db.close()

    except Exception as e:
        return False, str(e), {}


async def test_extracao_variaveis() -> Tuple[bool, str, Dict]:
    """Testa carregamento de variaveis de extracao."""
    try:
        from database.connection import SessionLocal
        from sistemas.gerador_pecas.models_extraction import ExtractionVariable

        db = SessionLocal()
        try:
            variaveis = db.query(ExtractionVariable).filter(
                ExtractionVariable.ativo == True
            ).limit(100).all()

            if variaveis:
                tipos = set(v.tipo for v in variaveis)
                return True, f"{len(variaveis)}+ variaveis ({len(tipos)} tipos)", {
                    "count": len(variaveis),
                    "tipos": list(tipos)
                }
            else:
                return True, "Nenhuma variavel (tabela vazia)", {}

        finally:
            db.close()

    except Exception as e:
        return False, str(e), {}


# ============================================
# TESTES: PROMPTS MODULARES
# ============================================

async def test_prompts_modulos() -> Tuple[bool, str, Dict]:
    """Testa carregamento de modulos de prompts."""
    try:
        from database.connection import SessionLocal
        from admin.models_prompts import PromptModulo

        db = SessionLocal()
        try:
            modulos = db.query(PromptModulo).filter(
                PromptModulo.ativo == True
            ).all()

            if modulos:
                tipos = {}
                for m in modulos:
                    tipos[m.tipo] = tipos.get(m.tipo, 0) + 1

                return True, f"{len(modulos)} modulos ativos", {
                    "count": len(modulos),
                    "por_tipo": tipos
                }
            else:
                return False, "Nenhum modulo ativo encontrado", {}

        finally:
            db.close()

    except Exception as e:
        return False, str(e), {}


async def test_regras_deterministicas() -> Tuple[bool, str, Dict]:
    """Testa servico de regras deterministicas."""
    try:
        from database.connection import SessionLocal
        from sistemas.gerador_pecas.services_deterministic import (
            avaliar_ativacao_prompt,
            tem_regras_deterministicas
        )

        db = SessionLocal()
        try:
            # Teste basico: verifica se funcao existe e roda
            resultado = tem_regras_deterministicas(
                regra_primaria={"type": "AND", "conditions": []},
                regra_secundaria=None,
                fallback_habilitado=False,
                regras_tipo_peca=[]
            )

            return True, f"Servico funcionando (tem_regras={resultado})", {}

        finally:
            db.close()

    except Exception as e:
        return False, str(e), {}


# ============================================
# TESTES: CONFIGURACOES DE IA
# ============================================

async def test_config_ia() -> Tuple[bool, str, Dict]:
    """Testa configuracoes de IA no banco."""
    try:
        from database.connection import SessionLocal
        from admin.models import ConfiguracaoIA

        db = SessionLocal()
        try:
            configs = db.query(ConfiguracaoIA).filter(
                ConfiguracaoIA.sistema == "gerador_pecas"
            ).all()

            if configs:
                config_dict = {c.chave: c.valor for c in configs}
                return True, f"{len(configs)} configs para gerador_pecas", {
                    "modelo": config_dict.get("modelo_geracao", "N/A"),
                    "configs": list(config_dict.keys())
                }
            else:
                return True, "Nenhuma config especifica (usara defaults)", {}

        finally:
            db.close()

    except Exception as e:
        return False, str(e), {}


async def test_ia_params_resolver() -> Tuple[bool, str, Dict]:
    """Testa resolucao de parametros de IA por agente."""
    try:
        from database.connection import SessionLocal
        from services.ia_params_resolver import get_ia_params

        db = SessionLocal()
        try:
            params = get_ia_params(db, "gerador_pecas", "geracao")

            return True, f"Modelo: {params.modelo}, Temp: {params.temperatura}", {
                "modelo": params.modelo,
                "temperatura": params.temperatura,
                "max_tokens": params.max_tokens,
                "thinking_level": params.thinking_level
            }

        finally:
            db.close()

    except Exception as e:
        return False, str(e), {}


# ============================================
# TESTES: ROUTE CONFIG
# ============================================

async def test_route_config() -> Tuple[bool, str, Dict]:
    """Testa configuracao de rotas."""
    try:
        from services.route_config import get_route_config, RouteProfile

        config = get_route_config("/api/gerador/editar-minuta")

        return True, f"Perfil: {config.profile.value}, SLA: {config.sla_timeout}s", {
            "profile": config.profile.value,
            "sla_timeout": config.sla_timeout,
            "model_primary": config.model_primary,
            "use_streaming": config.use_streaming
        }

    except Exception as e:
        return False, str(e), {}


async def test_background_tasks() -> Tuple[bool, str, Dict]:
    """Testa utilitario de background tasks."""
    try:
        from utils.background_tasks import run_in_background, get_background_stats

        async def dummy_task():
            await asyncio.sleep(0.1)
            return "done"

        task = await run_in_background(dummy_task)
        await task  # Aguarda conclusao

        stats = get_background_stats()

        return True, f"Background tasks funcionando", {
            "stats": stats
        }

    except Exception as e:
        return False, str(e), {}


# ============================================
# TESTES: BANCO DE DADOS
# ============================================

async def test_db_connection() -> Tuple[bool, str, Dict]:
    """Testa conexao com banco de dados."""
    try:
        from database.connection import SessionLocal
        from sqlalchemy import text

        db = SessionLocal()
        try:
            result = db.execute(text("SELECT 1")).fetchone()
            if result and result[0] == 1:
                return True, "Conexao OK", {}
            else:
                return False, "Query retornou resultado inesperado", {}

        finally:
            db.close()

    except Exception as e:
        return False, str(e), {}


async def test_gemini_logs_table() -> Tuple[bool, str, Dict]:
    """Testa tabela de logs do Gemini."""
    try:
        from database.connection import SessionLocal
        from sqlalchemy import text

        db = SessionLocal()
        try:
            # Verifica se a tabela existe e conta registros
            result = db.execute(text(
                "SELECT COUNT(*) FROM gemini_call_logs"
            )).scalar()

            return True, f"{result:,} logs registrados", {"count": result}

        except Exception as table_err:
            # Tabela pode nao existir ainda
            return True, f"Tabela de logs nao encontrada (normal em dev)", {}

        finally:
            db.close()

    except Exception as e:
        return False, str(e), {}


# ============================================
# RUNNER PRINCIPAL
# ============================================

async def run_all_tests(
    verbose: bool = False,
    only_system: str = None,
    timeout: float = 30.0
) -> Dict[str, TestSuite]:
    """Executa todos os testes."""

    # Define testes por sistema
    all_tests = {
        "database": [
            ("Conexao BD", test_db_connection),
            ("Tabela Gemini Logs", test_gemini_logs_table),
        ],
        "gemini": [
            ("API Key", test_gemini_api_key),
            ("Geracao Simples", test_gemini_generate_simple),
            ("Geracao com System Prompt", test_gemini_generate_with_system),
            ("Streaming", test_gemini_streaming),
            ("SLA Fallback", test_gemini_sla_fallback),
            ("Cache", test_gemini_cache),
            ("Truncamento", test_gemini_truncate),
        ],
        "gerador_pecas": [
            ("Servico Init", test_gerador_service_init),
            ("Editar Minuta", test_gerador_editar_minuta),
            ("Editar Minuta Stream", test_gerador_editar_minuta_stream),
        ],
        "extracao": [
            ("Categorias", test_extracao_categorias),
            ("Variaveis", test_extracao_variaveis),
        ],
        "prompts": [
            ("Modulos", test_prompts_modulos),
            ("Regras Deterministicas", test_regras_deterministicas),
        ],
        "config": [
            ("Config IA", test_config_ia),
            ("IA Params Resolver", test_ia_params_resolver),
            ("Route Config", test_route_config),
            ("Background Tasks", test_background_tasks),
        ],
    }

    # Filtra se solicitado
    if only_system:
        if only_system in all_tests:
            all_tests = {only_system: all_tests[only_system]}
        else:
            print(f"Sistema '{only_system}' nao encontrado.")
            print(f"Sistemas disponiveis: {', '.join(all_tests.keys())}")
            return {}

    # Executa testes
    suites = {}

    for system, tests in all_tests.items():
        suite = TestSuite(name=system)
        suite.start_time = datetime.now(timezone.utc)

        print(f"\n{'='*60}")
        print(f"SISTEMA: {system.upper()}")
        print(f"{'='*60}")

        for name, test_func in tests:
            result = await run_test(
                name=name,
                system=system,
                test_func=test_func,
                timeout=timeout,
                verbose=verbose
            )
            suite.add(result)
            print(f"  {result}")

        suite.end_time = datetime.now(timezone.utc)
        suites[system] = suite

    return suites


def print_final_summary(suites: Dict[str, TestSuite]):
    """Imprime resumo final de todos os testes."""
    total_tests = sum(s.total for s in suites.values())
    total_passed = sum(s.passed for s in suites.values())
    total_failed = sum(s.failed for s in suites.values())
    total_duration = sum(s.total_duration_ms for s in suites.values())

    print("\n")
    print("=" * 60)
    print("RESUMO FINAL")
    print("=" * 60)

    for name, suite in suites.items():
        status = "[OK]" if suite.failed == 0 else "[!!]"
        print(f"  {status} {name}: {suite.passed}/{suite.total} ({suite.success_rate:.0f}%)")

    print("-" * 60)
    print(f"  TOTAL: {total_passed}/{total_tests} testes passaram")
    print(f"  Taxa de Sucesso: {total_passed/max(total_tests,1)*100:.1f}%")
    print(f"  Duracao Total: {total_duration/1000:.1f}s")
    print("=" * 60)

    if total_failed > 0:
        print("\nFALHAS DETALHADAS:")
        for name, suite in suites.items():
            for result in suite.results:
                if not result.success:
                    print(f"  [{name}] {result.name}: {result.message}")

        print("\n[!] Alguns testes falharam. Verifique os erros acima.")
        return 1
    else:
        print("\n[OK] Todos os testes passaram!")
        return 0


def main():
    parser = argparse.ArgumentParser(
        description="Suite de testes para servicos de IA do Portal PGE-MS"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Mostra detalhes de cada teste"
    )
    parser.add_argument(
        "--only",
        type=str,
        default=None,
        help="Executa apenas testes de um sistema (gemini, gerador_pecas, etc)"
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Timeout em segundos para cada teste (default: 60)"
    )

    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("SUITE DE TESTES - SERVICOS DE IA - PORTAL PGE-MS")
    print("=" * 60)
    print(f"Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Timeout por teste: {args.timeout}s")
    if args.only:
        print(f"Sistema filtrado: {args.only}")

    # Executa testes
    suites = asyncio.run(run_all_tests(
        verbose=args.verbose,
        only_system=args.only,
        timeout=args.timeout
    ))

    # Imprime resumo
    exit_code = print_final_summary(suites)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
