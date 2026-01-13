# services/gemini_service.py
"""
Serviço centralizado para chamadas à API do Google Gemini.

Este serviço é usado por todos os sistemas do Portal PGE-MS:
- Gerador de Peças Jurídicas
- Matrículas Confrontantes
- Assistência Judiciária

Autor: LAB/PGE-MS
"""

import os
import aiohttp
import httpx
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from dotenv import load_dotenv
load_dotenv()


@dataclass
class GeminiResponse:
    """Resposta padronizada do Gemini"""
    success: bool
    content: str = ""
    error: Optional[str] = None
    tokens_used: int = 0


class GeminiService:
    """
    Serviço centralizado para chamadas à API do Google Gemini.
    
    Uso:
        from services import gemini_service
        
        # Chamada simples
        response = await gemini_service.generate(prompt="Olá!")
        
        # Com imagens
        response = await gemini_service.generate_with_images(
            prompt="Descreva esta imagem",
            images_base64=[...]
        )
    """
    
    # URL base da API Gemini
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
    
    # Modelos disponíveis
    MODELS = {
        # Modelos rápidos (baixo custo)
        "flash": "gemini-3-flash-preview",
        "flash-lite": "gemini-3-flash-preview",
        
        # Modelos avançados
        "pro": "gemini-2.5-pro",
        "pro-preview": "gemini-3-pro-preview",
        "flash-preview": "gemini-3-flash-preview",
    }
    
    # Modelo padrão para cada tipo de tarefa
    DEFAULT_MODELS = {
        "resumo": "gemini-3-flash-preview",      # Resumir documentos
        "analise": "gemini-3-flash-preview",           # Analisar conteúdo
        "geracao": "gemini-3-pro-preview",       # Gerar peças/relatórios
        "visao": "gemini-3-flash-preview",             # Análise de imagens
    }
    
    def __init__(self, api_key: str = None):
        """
        Inicializa o serviço.
        
        Args:
            api_key: API key do Gemini (opcional, usa GEMINI_KEY do ambiente)
        """
        self._api_key = api_key or os.getenv("GEMINI_KEY", "")
    
    @property
    def api_key(self) -> str:
        """Retorna a API key configurada"""
        return self._api_key
    
    @api_key.setter
    def api_key(self, value: str):
        """Atualiza a API key"""
        self._api_key = value
    
    def is_configured(self) -> bool:
        """Verifica se o serviço está configurado"""
        return bool(self._api_key)
    
    @staticmethod
    def normalize_model(model: str) -> str:
        """
        Normaliza o nome do modelo.
        
        - Remove prefixo 'google/' se presente
        - Converte aliases para nomes completos
        
        Exemplos:
            - google/gemini-3-pro-preview -> gemini-3-pro-preview
            - flash -> gemini-3-flash-preview
            - pro-preview -> gemini-3-pro-preview
        """
        # Remove prefixo google/
        if model.startswith("google/"):
            model = model[7:]
        
        # Converte aliases
        if model in GeminiService.MODELS:
            return GeminiService.MODELS[model]
        
        return model
    
    def get_model_for_task(self, task: str) -> str:
        """
        Retorna o modelo recomendado para uma tarefa.
        
        Args:
            task: Tipo de tarefa (resumo, analise, geracao, visao)
            
        Returns:
            Nome do modelo
        """
        return self.DEFAULT_MODELS.get(task, self.DEFAULT_MODELS["analise"])
    
    async def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        model: str = None,
        task: str = None,
        max_tokens: int = None,
        temperature: float = 0.3
    ) -> GeminiResponse:
        """
        Gera texto usando o Gemini.

        Args:
            prompt: Prompt do usuário
            system_prompt: Instruções do sistema (opcional)
            model: Nome do modelo (opcional, usa padrão se não especificado)
            task: Tipo de tarefa para selecionar modelo automaticamente
            max_tokens: Limite de tokens na resposta (None = sem limite, usa máximo do modelo)
            temperature: Temperatura (0-2)

        Returns:
            GeminiResponse com o resultado
        """
        import time
        inicio = time.time()
        print(f"[GeminiService.generate] Iniciando chamada...")

        if not self._api_key:
            print(f"[GeminiService.generate] ERRO: GEMINI_KEY não configurada")
            return GeminiResponse(
                success=False,
                error="GEMINI_KEY não configurada"
            )

        # Determina o modelo
        if model:
            model = self.normalize_model(model)
        elif task:
            model = self.get_model_for_task(task)
        else:
            model = self.DEFAULT_MODELS["analise"]

        print(f"[GeminiService.generate] Modelo: {model}")
        print(f"[GeminiService.generate] Tamanho prompt: {len(prompt)} chars")

        # Monta URL
        url = f"{self.BASE_URL}/{model}:generateContent?key={self._api_key[:8]}..."

        # Monta payload
        payload = self._build_payload(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature
        )

        try:
            print(f"[GeminiService.generate] Enviando request para API...")
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(f"{self.BASE_URL}/{model}:generateContent?key={self._api_key}", json=payload)
                print(f"[GeminiService.generate] Response status: {response.status_code}")
                response.raise_for_status()
                data = response.json()
                print(f"[GeminiService.generate] Resposta recebida em {time.time() - inicio:.2f}s")
                
                content = self._extract_content(data)
                tokens = self._extract_tokens(data)
                
                return GeminiResponse(
                    success=True,
                    content=content,
                    tokens_used=tokens
                )
                
        except httpx.HTTPStatusError as e:
            return GeminiResponse(
                success=False,
                error=f"Erro HTTP {e.response.status_code}: {e.response.text[:200]}"
            )
        except Exception as e:
            return GeminiResponse(
                success=False,
                error=f"Erro: {str(e)}"
            )
    
    async def generate_with_session(
        self,
        session: aiohttp.ClientSession,
        prompt: str,
        system_prompt: str = "",
        model: str = None,
        task: str = None,
        max_tokens: int = None,
        temperature: float = 0.3
    ) -> GeminiResponse:
        """
        Gera texto usando uma sessão aiohttp existente.

        Útil para chamadas em paralelo.
        """
        if not self._api_key:
            return GeminiResponse(
                success=False, 
                error="GEMINI_KEY não configurada"
            )
        
        # Determina o modelo
        if model:
            model = self.normalize_model(model)
        elif task:
            model = self.get_model_for_task(task)
        else:
            model = self.DEFAULT_MODELS["analise"]
        
        # Monta URL
        url = f"{self.BASE_URL}/{model}:generateContent?key={self._api_key}"
        
        # Monta payload
        payload = self._build_payload(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature
        )
        
        try:
            async with session.post(
                url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=300)
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                
                content = self._extract_content(data)
                tokens = self._extract_tokens(data)
                
                return GeminiResponse(
                    success=True,
                    content=content,
                    tokens_used=tokens
                )
                
        except Exception as e:
            return GeminiResponse(
                success=False,
                error=f"Erro: {str(e)}"
            )
    
    async def generate_with_images(
        self,
        prompt: str,
        images_base64: List[str],
        system_prompt: str = "",
        model: str = None,
        max_tokens: int = None,
        temperature: float = 0.3
    ) -> GeminiResponse:
        """
        Gera texto analisando imagens.
        
        Args:
            prompt: Prompt do usuário
            images_base64: Lista de imagens em base64
            system_prompt: Instruções do sistema (opcional)
            model: Nome do modelo (opcional)
            max_tokens: Limite de tokens na resposta
            temperature: Temperatura (0-2)
            
        Returns:
            GeminiResponse com o resultado
        """
        if not self._api_key:
            return GeminiResponse(
                success=False, 
                error="GEMINI_KEY não configurada"
            )
        
        # Modelo padrão para visão
        if model:
            model = self.normalize_model(model)
        else:
            model = self.DEFAULT_MODELS["visao"]
        
        # Monta URL
        url = f"{self.BASE_URL}/{model}:generateContent?key={self._api_key}"
        
        # Monta payload com imagens
        payload = self._build_payload_with_images(
            prompt=prompt,
            images_base64=images_base64,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature
        )
        
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                
                content = self._extract_content(data)
                tokens = self._extract_tokens(data)
                
                return GeminiResponse(
                    success=True,
                    content=content,
                    tokens_used=tokens
                )
                
        except httpx.HTTPStatusError as e:
            return GeminiResponse(
                success=False,
                error=f"Erro HTTP {e.response.status_code}: {e.response.text[:200]}"
            )
        except Exception as e:
            return GeminiResponse(
                success=False,
                error=f"Erro: {str(e)}"
            )
    
    async def generate_with_images_session(
        self,
        session: aiohttp.ClientSession,
        prompt: str,
        images_base64: List[str],
        system_prompt: str = "",
        model: str = None,
        max_tokens: int = None,
        temperature: float = 0.3
    ) -> GeminiResponse:
        """
        Gera texto analisando imagens usando sessão aiohttp.
        """
        if not self._api_key:
            return GeminiResponse(
                success=False, 
                error="GEMINI_KEY não configurada"
            )
        
        # Modelo padrão para visão
        if model:
            model = self.normalize_model(model)
        else:
            model = self.DEFAULT_MODELS["visao"]
        
        # Monta URL
        url = f"{self.BASE_URL}/{model}:generateContent?key={self._api_key}"
        
        # Monta payload com imagens
        payload = self._build_payload_with_images(
            prompt=prompt,
            images_base64=images_base64,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature
        )
        
        try:
            async with session.post(
                url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=300)
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                
                content = self._extract_content(data)
                tokens = self._extract_tokens(data)
                
                return GeminiResponse(
                    success=True,
                    content=content,
                    tokens_used=tokens
                )
                
        except Exception as e:
            return GeminiResponse(
                success=False,
                error=f"Erro: {str(e)}"
            )
    
    def _build_payload(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int = None,
        temperature: float = 0.3
    ) -> Dict[str, Any]:
        """Monta o payload para chamada de texto"""
        generation_config = {"temperature": temperature}

        # Só adiciona maxOutputTokens se especificado (None = usa máximo do modelo)
        if max_tokens is not None:
            generation_config["maxOutputTokens"] = max_tokens

        payload = {
            "contents": [
                {"role": "user", "parts": [{"text": prompt}]}
            ],
            "generationConfig": generation_config
        }

        if system_prompt:
            payload["systemInstruction"] = {
                "parts": [{"text": system_prompt}]
            }

        return payload
    
    def _build_payload_with_images(
        self,
        prompt: str,
        images_base64: List[str],
        system_prompt: str = "",
        max_tokens: int = None,
        temperature: float = 0.3
    ) -> Dict[str, Any]:
        """Monta o payload para chamada com imagens"""
        parts = []
        
        # Adiciona imagens
        for img_base64 in images_base64:
            if img_base64.startswith("data:"):
                # Formato: data:image/png;base64,<dados>
                header, data = img_base64.split(",", 1)
                mime_type = header.split(":")[1].split(";")[0]
            else:
                mime_type = "image/png"
                data = img_base64
            
            parts.append({
                "inline_data": {
                    "mime_type": mime_type,
                    "data": data
                }
            })
        
        # Adiciona prompt
        parts.append({"text": prompt})

        generation_config = {"temperature": temperature}
        if max_tokens is not None:
            generation_config["maxOutputTokens"] = max_tokens

        payload = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": generation_config
        }

        if system_prompt:
            payload["systemInstruction"] = {
                "parts": [{"text": system_prompt}]
            }

        return payload
    
    async def generate_with_search(
        self,
        prompt: str,
        system_prompt: str = "",
        model: str = None,
        max_tokens: int = None,
        temperature: float = 0.3,
        search_threshold: float = 0.3
    ) -> GeminiResponse:
        """
        Gera texto com Google Search Grounding habilitado.

        Permite que o modelo busque informações na internet quando necessário.
        Útil para verificar informações factuais como medicamentos, leis, etc.

        Args:
            prompt: Prompt do usuário
            system_prompt: Instruções do sistema (opcional)
            model: Nome do modelo (opcional)
            max_tokens: Limite de tokens na resposta
            temperature: Temperatura (0-2)
            search_threshold: Limiar para ativar busca (0-1, menor = mais buscas)

        Returns:
            GeminiResponse com o resultado
        """
        if not self._api_key:
            return GeminiResponse(
                success=False,
                error="GEMINI_KEY não configurada"
            )

        # Determina o modelo
        if model:
            model = self.normalize_model(model)
        else:
            model = self.DEFAULT_MODELS["analise"]

        # Monta URL
        url = f"{self.BASE_URL}/{model}:generateContent?key={self._api_key}"

        # Monta payload base
        generation_config = {"temperature": temperature}
        if max_tokens is not None:
            generation_config["maxOutputTokens"] = max_tokens

        payload = {
            "contents": [
                {"role": "user", "parts": [{"text": prompt}]}
            ],
            "generationConfig": generation_config,
            "tools": [
                {
                    "google_search": {}
                }
            ]
        }

        if system_prompt:
            payload["systemInstruction"] = {
                "parts": [{"text": system_prompt}]
            }

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()

                content = self._extract_content(data)
                tokens = self._extract_tokens(data)

                # Extrai informações de grounding se disponíveis
                grounding_metadata = self._extract_grounding_metadata(data)
                if grounding_metadata:
                    content += f"\n\n---\n**Fontes consultadas:** {grounding_metadata}"

                return GeminiResponse(
                    success=True,
                    content=content,
                    tokens_used=tokens
                )

        except httpx.HTTPStatusError as e:
            return GeminiResponse(
                success=False,
                error=f"Erro HTTP {e.response.status_code}: {e.response.text[:200]}"
            )
        except Exception as e:
            return GeminiResponse(
                success=False,
                error=f"Erro: {str(e)}"
            )

    async def generate_with_images_and_search(
        self,
        prompt: str,
        images_base64: List[str],
        system_prompt: str = "",
        model: str = None,
        max_tokens: int = None,
        temperature: float = 0.3,
        search_threshold: float = 0.3
    ) -> GeminiResponse:
        """
        Gera texto analisando imagens COM Google Search Grounding.

        Combina análise de imagens com busca na internet.
        Ideal para verificar informações em notas fiscais, medicamentos, etc.
        """
        if not self._api_key:
            return GeminiResponse(
                success=False,
                error="GEMINI_KEY não configurada"
            )

        # Modelo padrão para visão
        if model:
            model = self.normalize_model(model)
        else:
            model = self.DEFAULT_MODELS["visao"]

        # Monta URL
        url = f"{self.BASE_URL}/{model}:generateContent?key={self._api_key}"

        # Monta partes com imagens
        parts = []
        for img_base64 in images_base64:
            if img_base64.startswith("data:"):
                header, data = img_base64.split(",", 1)
                mime_type = header.split(":")[1].split(";")[0]
            else:
                mime_type = "image/png"
                data = img_base64

            parts.append({
                "inline_data": {
                    "mime_type": mime_type,
                    "data": data
                }
            })

        parts.append({"text": prompt})

        generation_config = {"temperature": temperature}
        if max_tokens is not None:
            generation_config["maxOutputTokens"] = max_tokens

        payload = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": generation_config,
            "tools": [
                {
                    "google_search": {}
                }
            ]
        }

        if system_prompt:
            payload["systemInstruction"] = {
                "parts": [{"text": system_prompt}]
            }

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()

                content = self._extract_content(data)
                tokens = self._extract_tokens(data)

                return GeminiResponse(
                    success=True,
                    content=content,
                    tokens_used=tokens
                )

        except httpx.HTTPStatusError as e:
            return GeminiResponse(
                success=False,
                error=f"Erro HTTP {e.response.status_code}: {e.response.text[:200]}"
            )
        except Exception as e:
            return GeminiResponse(
                success=False,
                error=f"Erro: {str(e)}"
            )

    def _extract_content(self, data: Dict) -> str:
        """Extrai conteúdo da resposta do Gemini"""
        candidates = data.get("candidates", [])
        if candidates:
            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            if parts:
                return parts[0].get("text", "")
        return ""

    def _extract_tokens(self, data: Dict) -> int:
        """Extrai contagem de tokens da resposta"""
        usage = data.get("usageMetadata", {})
        return usage.get("totalTokenCount", 0)

    def _extract_grounding_metadata(self, data: Dict) -> str:
        """Extrai metadados de grounding (fontes consultadas)"""
        candidates = data.get("candidates", [])
        if not candidates:
            return ""

        grounding = candidates[0].get("groundingMetadata", {})
        if not grounding:
            return ""

        # Extrai URLs das fontes
        sources = grounding.get("webSearchQueries", [])
        chunks = grounding.get("groundingChunks", [])

        urls = []
        for chunk in chunks:
            web = chunk.get("web", {})
            if web.get("uri"):
                urls.append(web.get("uri"))

        if urls:
            return ", ".join(urls[:3])  # Máximo 3 URLs
        elif sources:
            return f"Buscas: {', '.join(sources[:3])}"

        return ""


# Instância global do serviço (singleton)
gemini_service = GeminiService()


# ============================================
# Funções de conveniência (compatibilidade)
# ============================================

async def chamar_gemini(
    prompt: str,
    system_prompt: str = "",
    modelo: str = None,
    max_tokens: int = None,
    temperature: float = 0.3
) -> str:
    """
    Função de conveniência para chamadas simples.
    
    Retorna apenas o texto (para compatibilidade).
    """
    response = await gemini_service.generate(
        prompt=prompt,
        system_prompt=system_prompt,
        model=modelo,
        max_tokens=max_tokens,
        temperature=temperature
    )
    
    if not response.success:
        raise ValueError(response.error)
    
    return response.content


async def chamar_gemini_com_imagens(
    prompt: str,
    imagens_base64: List[str],
    system_prompt: str = "",
    modelo: str = None,
    max_tokens: int = None,
    temperature: float = 0.3
) -> str:
    """
    Função de conveniência para chamadas com imagens.
    
    Retorna apenas o texto (para compatibilidade).
    """
    response = await gemini_service.generate_with_images(
        prompt=prompt,
        images_base64=imagens_base64,
        system_prompt=system_prompt,
        model=modelo,
        max_tokens=max_tokens,
        temperature=temperature
    )
    
    if not response.success:
        raise ValueError(response.error)
    
    return response.content
