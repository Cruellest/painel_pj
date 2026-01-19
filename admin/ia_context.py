# admin/ia_context.py
"""
Contexto de IA para propagar informações de rastreabilidade para chamadas Gemini.

Este módulo permite que o middleware capture informações da request HTTP
e as propague automaticamente para todas as chamadas Gemini, garantindo
que o campo `sistema` nunca fique como `unknown`.

Uso:
    from admin.ia_context import ia_ctx

    # No início da request (middleware)
    ia_ctx.start_request(
        request_id="abc123",
        route="/admin/categorias-resumo-json/gerar-schema",
        user_id=1,
        username="admin"
    )

    # Durante a chamada Gemini, o contexto é obtido automaticamente
    ctx = ia_ctx.get_context()  # Retorna dict com sistema, modulo, user_id, etc.

    # No final da request
    ia_ctx.clear()
"""

import re
import logging
import inspect
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


@dataclass
class IAContextData:
    """Dados de contexto para chamadas de IA."""
    request_id: str = ""
    route: str = ""
    method: str = ""
    user_id: Optional[int] = None
    username: Optional[str] = None
    # Sistema derivado da rota
    sistema: str = "unknown"
    modulo: Optional[str] = None
    # Fonte explícita (se definida manualmente)
    source_feature: Optional[str] = None
    # Debug info
    debug_info: Optional[str] = None


# ContextVar para armazenar dados por request (thread-safe para async)
_ia_context: ContextVar[Optional[IAContextData]] = ContextVar('ia_context', default=None)


# ==================================================
# MAPEAMENTO DE ROTAS PARA SISTEMAS
# ==================================================

# Mapeamento de prefixos de rota para nomes de sistema
# Ordem importa: mais específico primeiro
ROUTE_TO_SYSTEM_MAP = [
    # Admin - Categorias JSON
    (r"/admin/categorias-resumo-json", "admin_categorias_json"),
    (r"/categorias-resumo-json", "admin_categorias_json"),

    # Admin - Extração e Variáveis
    (r"/admin/variaveis", "admin_variaveis"),
    (r"/extraction/", "extracao"),

    # Admin - Teste de Categorias
    (r"/teste-categorias", "teste_categorias"),

    # Gerador de Peças
    (r"/gerador-pecas", "gerador_pecas"),
    (r"/gerar-peca", "gerador_pecas"),

    # Pedido de Cálculo
    (r"/pedido-calculo", "pedido_calculo"),
    (r"/pedidos-calculo", "pedido_calculo"),

    # Assistência Judiciária
    (r"/assistencia-judiciaria", "assistencia_judiciaria"),

    # Prestação de Contas
    (r"/prestacao-contas", "prestacao_contas"),

    # Matrículas Confrontantes
    (r"/matriculas-confrontantes", "matriculas_confrontantes"),

    # Admin geral
    (r"/admin/", "admin"),

    # API geral
    (r"/api/", "api"),
]


def _derive_system_from_route(route: str) -> str:
    """
    Deriva o nome do sistema a partir da rota HTTP.

    Args:
        route: Caminho da rota (ex: /admin/categorias-resumo-json/123/gerar-schema)

    Returns:
        Nome do sistema (ex: admin_categorias_json)
    """
    if not route:
        return "unknown"

    route_lower = route.lower()

    # Tenta encontrar um match nos mapeamentos
    for pattern, system_name in ROUTE_TO_SYSTEM_MAP:
        if re.search(pattern, route_lower):
            return system_name

    # Fallback: converte a rota em nome de sistema
    # Remove IDs numéricos e normaliza
    # Ex: /admin/categorias-resumo-json/123 -> admin_categorias_resumo_json
    parts = [p for p in route.strip('/').split('/') if p and not p.isdigit()]
    if parts:
        # Limita a 3 partes para evitar nomes muito longos
        sistema = '_'.join(parts[:3]).replace('-', '_')
        return sistema

    return "unknown"


def _derive_module_from_caller() -> Optional[str]:
    """
    Tenta derivar o módulo a partir do stack de chamadas.

    Útil para background jobs onde não há rota HTTP.

    Returns:
        Nome do módulo (ex: services_extraction) ou None
    """
    try:
        # Percorre o stack para encontrar o caller relevante
        for frame_info in inspect.stack():
            module = frame_info.frame.f_globals.get('__name__', '')

            # Ignora módulos internos
            if any(skip in module for skip in ['gemini_service', 'ia_context', 'services_gemini_logs', 'asyncio', 'starlette', 'fastapi']):
                continue

            # Encontrou um módulo relevante
            if module and module.startswith('sistemas.'):
                # Ex: sistemas.gerador_pecas.services_extraction -> services_extraction
                parts = module.split('.')
                if len(parts) >= 3:
                    return parts[-1]  # Último componente
                return module.split('.')[-1]

            if module and module.startswith('admin.'):
                return module.split('.')[-1]

        return None
    except Exception:
        return None


class IAContext:
    """
    Gerenciador de contexto para chamadas de IA.

    Propaga informações de rastreabilidade de forma thread-safe.
    """

    def start_request(
        self,
        request_id: str,
        route: str,
        method: str = "GET",
        user_id: int = None,
        username: str = None
    ):
        """
        Inicia o contexto de IA para uma request HTTP.

        Args:
            request_id: ID único da request
            route: Caminho da rota HTTP
            method: Método HTTP
            user_id: ID do usuário (opcional)
            username: Nome do usuário (opcional)
        """
        # Deriva sistema automaticamente da rota
        sistema = _derive_system_from_route(route)

        ctx_data = IAContextData(
            request_id=request_id,
            route=route,
            method=method,
            user_id=user_id,
            username=username,
            sistema=sistema,
        )
        _ia_context.set(ctx_data)

    def set_source_feature(self, feature: str):
        """
        Define explicitamente a feature/módulo de origem.

        Útil quando o frontend envia o source_feature no payload.

        Args:
            feature: Nome da feature (ex: admin_categorias_json_gerar_schema)
        """
        ctx = _ia_context.get()
        if ctx:
            ctx.source_feature = feature
            # Se temos uma feature explícita, ela tem prioridade
            ctx.sistema = feature

    def set_modulo(self, modulo: str):
        """Define o módulo específico."""
        ctx = _ia_context.get()
        if ctx:
            ctx.modulo = modulo

    def get_context(self) -> Dict[str, Any]:
        """
        Retorna o contexto atual para uso no logging do Gemini.

        Se não houver contexto de request, tenta derivar do stack de chamadas.

        Returns:
            Dict com sistema, modulo, user_id, username, request_id, route
        """
        ctx = _ia_context.get()

        if ctx:
            # Temos contexto de request HTTP
            return {
                'sistema': ctx.source_feature or ctx.sistema,
                'modulo': ctx.modulo or _derive_module_from_caller(),
                'user_id': ctx.user_id,
                'username': ctx.username,
                'request_id': ctx.request_id,
                'route': ctx.route,
            }

        # Não há contexto de request (background job, etc.)
        # Tenta inferir do stack de chamadas
        modulo = _derive_module_from_caller()
        sistema = f"background:{modulo}" if modulo else "background:unknown"

        return {
            'sistema': sistema,
            'modulo': modulo,
            'user_id': None,
            'username': None,
            'request_id': None,
            'route': None,
            'debug_info': "no_http_context",
        }

    def get_raw_data(self) -> Optional[IAContextData]:
        """Retorna os dados brutos do contexto."""
        return _ia_context.get()

    def clear(self):
        """Limpa o contexto atual."""
        _ia_context.set(None)


# Instância global (singleton)
ia_ctx = IAContext()
