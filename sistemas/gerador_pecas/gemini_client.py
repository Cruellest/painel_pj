# sistemas/gerador_pecas/gemini_client.py
"""
Cliente para API direta do Google Gemini.

Este módulo fornece funções para chamar a API do Gemini diretamente,
sem passar pelo OpenRouter.

Autor: LAB/PGE-MS
"""

import os
import aiohttp
import httpx
from typing import List, Dict, Optional

from dotenv import load_dotenv
load_dotenv()

# Configurações
GEMINI_API_KEY = os.getenv('GEMINI_KEY')
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


def normalizar_modelo(modelo: str) -> str:
    """
    Normaliza o nome do modelo removendo prefixo 'google/' se presente.
    
    Exemplos:
        - google/gemini-3-pro-preview -> gemini-3-pro-preview
        - gemini-3-flash-preview -> gemini-3-flash-preview
    """
    if modelo.startswith("google/"):
        return modelo[7:]  # Remove 'google/'
    return modelo


async def chamar_gemini_async(
    prompt: str,
    system_prompt: str = "",
    modelo: str = "gemini-2.5-flash-lite",
    max_tokens: int = 8192,
    temperature: float = 0.3,
    api_key: str = None
) -> str:
    """
    Chama a API do Gemini de forma assíncrona.
    
    Args:
        prompt: Prompt do usuário
        system_prompt: Prompt de sistema (opcional)
        modelo: Nome do modelo Gemini (sem prefixo google/)
        max_tokens: Limite de tokens na resposta
        temperature: Temperatura (0-2)
        api_key: API key (opcional, usa GEMINI_KEY do ambiente se não fornecida)
        
    Returns:
        Texto da resposta do modelo
        
    Raises:
        ValueError: Se a API key não estiver configurada
        Exception: Se houver erro na chamada à API
    """
    key = api_key or GEMINI_API_KEY
    if not key:
        raise ValueError("GEMINI_KEY não configurada")
    
    # Normaliza o modelo
    modelo = normalizar_modelo(modelo)
    
    # Monta URL
    url = f"{GEMINI_BASE_URL}/{modelo}:generateContent?key={key}"
    
    # Monta conteúdo
    contents = []
    
    # Adiciona system instruction se houver
    system_instruction = None
    if system_prompt:
        system_instruction = {"parts": [{"text": system_prompt}]}
    
    # Adiciona mensagem do usuário
    contents.append({
        "role": "user",
        "parts": [{"text": prompt}]
    })
    
    # Payload
    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens
        }
    }
    
    if system_instruction:
        payload["systemInstruction"] = system_instruction
    
    async with httpx.AsyncClient(timeout=300.0) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        
        # Extrai texto da resposta
        candidates = data.get('candidates', [])
        if candidates:
            content = candidates[0].get('content', {})
            parts = content.get('parts', [])
            if parts:
                return parts[0].get('text', '')
        
        return ''


async def chamar_gemini_aiohttp_async(
    session: aiohttp.ClientSession,
    prompt: str,
    system_prompt: str = "",
    modelo: str = "gemini-2.5-flash-lite",
    max_tokens: int = 8192,
    temperature: float = 0.3,
    api_key: str = None
) -> str:
    """
    Chama a API do Gemini usando sessão aiohttp existente.
    
    Útil para chamadas em paralelo com a mesma sessão.
    
    Args:
        session: Sessão aiohttp
        prompt: Prompt do usuário
        system_prompt: Prompt de sistema (opcional)
        modelo: Nome do modelo Gemini (sem prefixo google/)
        max_tokens: Limite de tokens na resposta
        temperature: Temperatura (0-2)
        api_key: API key (opcional, usa GEMINI_KEY do ambiente se não fornecida)
        
    Returns:
        Texto da resposta do modelo
    """
    key = api_key or GEMINI_API_KEY
    if not key:
        raise ValueError("GEMINI_KEY não configurada")
    
    # Normaliza o modelo
    modelo = normalizar_modelo(modelo)
    
    # Monta URL
    url = f"{GEMINI_BASE_URL}/{modelo}:generateContent?key={key}"
    
    # Monta conteúdo
    contents = []
    
    # Adiciona system instruction se houver
    system_instruction = None
    if system_prompt:
        system_instruction = {"parts": [{"text": system_prompt}]}
    
    # Adiciona mensagem do usuário
    contents.append({
        "role": "user",
        "parts": [{"text": prompt}]
    })
    
    # Payload
    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens
        }
    }
    
    if system_instruction:
        payload["systemInstruction"] = system_instruction
    
    async with session.post(
        url,
        json=payload,
        timeout=aiohttp.ClientTimeout(total=300)
    ) as resp:
        resp.raise_for_status()
        data = await resp.json()
        
        # Extrai texto da resposta
        candidates = data.get('candidates', [])
        if candidates:
            content = candidates[0].get('content', {})
            parts = content.get('parts', [])
            if parts:
                return parts[0].get('text', '')
        
        return ''


async def chamar_gemini_com_imagens_async(
    session: aiohttp.ClientSession,
    prompt: str,
    imagens_base64: List[str],
    system_prompt: str = "",
    modelo: str = "gemini-2.5-flash-lite",
    max_tokens: int = 4096,
    temperature: float = 0.3,
    api_key: str = None
) -> str:
    """
    Chama a API do Gemini com imagens (para PDFs digitalizados).
    
    Args:
        session: Sessão aiohttp
        prompt: Prompt do usuário
        imagens_base64: Lista de imagens em base64 (formato: data:image/png;base64,...)
        system_prompt: Prompt de sistema (opcional)
        modelo: Nome do modelo Gemini
        max_tokens: Limite de tokens na resposta
        temperature: Temperatura (0-2)
        api_key: API key (opcional)
        
    Returns:
        Texto da resposta do modelo
    """
    key = api_key or GEMINI_API_KEY
    if not key:
        raise ValueError("GEMINI_KEY não configurada")
    
    # Normaliza o modelo
    modelo = normalizar_modelo(modelo)
    
    # Monta URL
    url = f"{GEMINI_BASE_URL}/{modelo}:generateContent?key={key}"
    
    # Monta partes do conteúdo
    parts = []
    
    # Adiciona as imagens
    for img_base64 in imagens_base64:
        # Extrai mime type e dados do base64
        if img_base64.startswith("data:"):
            # Formato: data:image/png;base64,<dados>
            header, data = img_base64.split(",", 1)
            mime_type = header.split(":")[1].split(";")[0]
        else:
            # Assume PNG se não tiver header
            mime_type = "image/png"
            data = img_base64
        
        parts.append({
            "inline_data": {
                "mime_type": mime_type,
                "data": data
            }
        })
    
    # Adiciona o prompt de texto
    parts.append({"text": prompt})
    
    # Monta conteúdo
    contents = [{"role": "user", "parts": parts}]
    
    # System instruction
    system_instruction = None
    if system_prompt:
        system_instruction = {"parts": [{"text": system_prompt}]}
    
    # Payload
    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens
        }
    }
    
    if system_instruction:
        payload["systemInstruction"] = system_instruction
    
    async with session.post(
        url,
        json=payload,
        timeout=aiohttp.ClientTimeout(total=300)
    ) as resp:
        resp.raise_for_status()
        data = await resp.json()
        
        # Extrai texto da resposta
        candidates = data.get('candidates', [])
        if candidates:
            content = candidates[0].get('content', {})
            parts = content.get('parts', [])
            if parts:
                return parts[0].get('text', '')
        
        return ''
