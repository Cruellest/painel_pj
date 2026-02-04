# sistemas/classificador_documentos/services_openrouter.py
"""
Serviço de integração com OpenRouter para classificação de documentos.

Este serviço encapsula as chamadas à API do OpenRouter, incluindo:
- Retry com backoff exponencial
- Parsing e validação de respostas JSON
- Logging de chamadas para auditoria

Autor: LAB/PGE-MS
"""

import httpx
import json
import re
import asyncio
import logging
import os
import time
from typing import Optional, Tuple, Dict, Any, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# ============================================
# Configuração
# ============================================

@dataclass
class OpenRouterConfig:
    """Configurações do OpenRouter"""
    api_key: str
    base_url: str = "https://openrouter.ai/api/v1/chat/completions"
    timeout: float = 60.0
    retry_delays: List[int] = None
    default_model: str = "google/gemini-2.5-flash-lite"
    temperature: float = 0.1

    def __post_init__(self):
        if self.retry_delays is None:
            self.retry_delays = [5, 15, 30]

    @classmethod
    def from_env(cls) -> "OpenRouterConfig":
        """Carrega configuração das variáveis de ambiente"""
        api_key = os.getenv("OPENROUTER_API_KEY", "")
        if not api_key:
            logger.warning("OPENROUTER_API_KEY não configurada")
        return cls(api_key=api_key)


# ============================================
# Resultado da Chamada
# ============================================

@dataclass
class OpenRouterResult:
    """Resultado de uma chamada ao OpenRouter"""
    sucesso: bool
    resultado: Optional[Dict[str, Any]] = None
    erro: Optional[str] = None
    tokens_entrada: int = 0
    tokens_saida: int = 0
    tempo_ms: int = 0
    resposta_bruta: Optional[str] = None


# ============================================
# Serviço OpenRouter
# ============================================

class OpenRouterService:
    """
    Serviço para chamadas à API do OpenRouter.

    Uso:
        service = OpenRouterService()
        result = await service.classificar(
            modelo="google/gemini-2.5-flash-lite",
            prompt_sistema="...",
            nome_arquivo="doc.pdf",
            chunk_texto="texto do documento..."
        )
    """

    def __init__(self, config: Optional[OpenRouterConfig] = None):
        self.config = config or OpenRouterConfig.from_env()

    def _get_headers(self) -> Dict[str, str]:
        """Retorna headers para a requisição"""
        return {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json; charset=utf-8",
            "HTTP-Referer": "https://portal-pge.railway.app",
            "X-Title": "Portal PGE-MS - Classificador de Documentos"
        }

    async def verificar_disponibilidade(self) -> bool:
        """Verifica se a API está disponível e a chave é válida"""
        if not self.config.api_key:
            return False

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    "https://openrouter.ai/api/v1/models",
                    headers={"Authorization": f"Bearer {self.config.api_key}"}
                )
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Erro ao verificar disponibilidade OpenRouter: {e}")
            return False

    async def classificar(
        self,
        modelo: str,
        prompt_sistema: str,
        nome_arquivo: str,
        chunk_texto: str
    ) -> OpenRouterResult:
        """
        Classifica um documento usando OpenRouter.

        Args:
            modelo: Nome do modelo (ex: google/gemini-2.5-flash-lite)
            prompt_sistema: Conteúdo do prompt de sistema
            nome_arquivo: Nome do arquivo sendo processado
            chunk_texto: Trecho do documento para classificar

        Returns:
            OpenRouterResult com resultado ou erro
        """
        if not self.config.api_key:
            return OpenRouterResult(
                sucesso=False,
                erro="OPENROUTER_API_KEY não configurada"
            )

        headers = self._get_headers()

        body = {
            "model": modelo,
            "messages": [
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": f"ARQUIVO: {nome_arquivo}\n\nTRECHO DO DOCUMENTO:\n{chunk_texto}"}
            ],
            "temperature": self.config.temperature,
            "response_format": {"type": "json_object"}
        }

        inicio = time.time()
        resposta_bruta = None

        # Retry com backoff exponencial para rate limit
        for tentativa, delay in enumerate(self.config.retry_delays + [None]):
            try:
                async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                    # Serializa body manualmente para garantir UTF-8
                    body_bytes = json.dumps(body, ensure_ascii=False).encode('utf-8')
                    response = await client.post(
                        self.config.base_url,
                        headers=headers,
                        content=body_bytes
                    )

                    if response.status_code == 429:  # Rate limit
                        if delay is not None:
                            logger.warning(f"Rate limit atingido. Aguardando {delay}s... (tentativa {tentativa + 1})")
                            await asyncio.sleep(delay)
                            continue
                        else:
                            return OpenRouterResult(
                                sucesso=False,
                                erro="Rate limit excedido após todas as tentativas",
                                tempo_ms=int((time.time() - inicio) * 1000)
                            )

                    response.raise_for_status()
                    data = response.json()

                    # Extrai métricas de tokens
                    usage = data.get("usage", {})
                    tokens_entrada = usage.get("prompt_tokens", 0)
                    tokens_saida = usage.get("completion_tokens", 0)

                    # Extrai conteúdo da resposta
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    resposta_bruta = content

                    # Tenta parsear JSON da resposta
                    resultado, erro = self._parsear_resposta_json(content)

                    tempo_ms = int((time.time() - inicio) * 1000)

                    if resultado:
                        return OpenRouterResult(
                            sucesso=True,
                            resultado=resultado,
                            tokens_entrada=tokens_entrada,
                            tokens_saida=tokens_saida,
                            tempo_ms=tempo_ms,
                            resposta_bruta=resposta_bruta
                        )
                    else:
                        return OpenRouterResult(
                            sucesso=False,
                            erro=erro,
                            tokens_entrada=tokens_entrada,
                            tokens_saida=tokens_saida,
                            tempo_ms=tempo_ms,
                            resposta_bruta=resposta_bruta
                        )

            except httpx.TimeoutException:
                return OpenRouterResult(
                    sucesso=False,
                    erro=f"Timeout após {self.config.timeout}s",
                    tempo_ms=int((time.time() - inicio) * 1000)
                )
            except httpx.HTTPStatusError as e:
                return OpenRouterResult(
                    sucesso=False,
                    erro=f"Erro HTTP {e.response.status_code}: {e.response.text[:200]}",
                    tempo_ms=int((time.time() - inicio) * 1000)
                )
            except Exception as e:
                logger.exception(f"Erro inesperado ao chamar OpenRouter: {e}")
                return OpenRouterResult(
                    sucesso=False,
                    erro=f"Erro inesperado: {str(e)}",
                    tempo_ms=int((time.time() - inicio) * 1000)
                )

        return OpenRouterResult(
            sucesso=False,
            erro="Falha após todas as tentativas",
            tempo_ms=int((time.time() - inicio) * 1000)
        )

    def _parsear_resposta_json(self, content: str) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Tenta extrair e validar JSON da resposta da LLM.

        Returns:
            Tupla (resultado_dict, erro_msg)
        """
        try:
            # Tenta parsear diretamente
            resultado = json.loads(content)
        except json.JSONDecodeError:
            # Tenta extrair JSON com regex (para casos onde há texto antes/depois)
            match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', content, re.DOTALL)
            if match:
                try:
                    resultado = json.loads(match.group())
                except json.JSONDecodeError:
                    return None, "Resposta inválida da LLM: JSON malformado"
            else:
                return None, "Resposta inválida da LLM: JSON não encontrado"

        # Valida campos obrigatórios
        campos_obrigatorios = ["categoria", "confianca", "justificativa_breve"]
        campos_faltando = [c for c in campos_obrigatorios if c not in resultado or not resultado[c]]

        # numero_processo_cnj é opcional mas esperado
        if "numero_processo_cnj" not in resultado:
            resultado["numero_processo_cnj"] = None

        if campos_faltando:
            return None, f"Campos obrigatórios faltando: {', '.join(campos_faltando)}"

        # Valida valor de confiança
        confianca = resultado.get("confianca", "").lower()
        if confianca not in ["alta", "media", "média", "baixa"]:
            return None, f"Valor de confiança inválido: {resultado.get('confianca')}"

        # Normaliza confiança
        resultado["confianca"] = "media" if confianca == "média" else confianca

        # Garante que subcategoria existe (pode ser null)
        if "subcategoria" not in resultado:
            resultado["subcategoria"] = None

        return resultado, None


# ============================================
# Instância global do serviço
# ============================================

_openrouter_service: Optional[OpenRouterService] = None


def get_openrouter_service() -> OpenRouterService:
    """Retorna instância singleton do serviço OpenRouter"""
    global _openrouter_service
    if _openrouter_service is None:
        _openrouter_service = OpenRouterService()
    return _openrouter_service
