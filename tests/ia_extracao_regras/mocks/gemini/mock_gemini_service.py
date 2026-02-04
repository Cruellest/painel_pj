# tests/ia_extracao_regras/mocks/gemini/mock_gemini_service.py
"""
Mock do serviço Gemini para testes automatizados.

Simula respostas da API Gemini sem fazer chamadas reais.
"""

import json
from dataclasses import dataclass
from typing import Optional, Dict, Any, List


@dataclass
class MockGeminiResponse:
    """Resposta mockada do Gemini."""
    success: bool
    content: str
    error: Optional[str] = None
    model: str = "gemini-3-flash-preview"
    tokens_used: int = 100


class MockGeminiService:
    """
    Mock do GeminiService para testes.

    Retorna respostas pré-configuradas baseadas no tipo de prompt.
    """

    def __init__(self):
        self.calls: List[Dict] = []
        self.custom_responses: Dict[str, MockGeminiResponse] = {}

    def set_response(self, pattern: str, response: MockGeminiResponse):
        """Define uma resposta customizada para um padrão de prompt."""
        self.custom_responses[pattern] = response

    async def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        model: str = "gemini-3-flash-preview",
        temperature: float = 0.3
    ) -> MockGeminiResponse:
        """Simula geração de conteúdo."""
        self.calls.append({
            "prompt": prompt,
            "system_prompt": system_prompt,
            "model": model,
            "temperature": temperature
        })

        # Verifica respostas customizadas
        for pattern, response in self.custom_responses.items():
            if pattern.lower() in prompt.lower():
                return response

        # Detecta tipo de requisição e retorna mock apropriado
        if "schema" in prompt.lower() or "extração" in prompt.lower():
            return criar_mock_schema_response()

        if "regra" in prompt.lower() or "condição" in prompt.lower():
            return criar_mock_regra_response(prompt)

        # Resposta genérica
        return MockGeminiResponse(
            success=True,
            content='{"resultado": "mock"}',
            model=model
        )

    def get_call_count(self) -> int:
        """Retorna número de chamadas feitas."""
        return len(self.calls)

    def get_last_call(self) -> Optional[Dict]:
        """Retorna a última chamada feita."""
        return self.calls[-1] if self.calls else None

    def reset(self):
        """Limpa histórico de chamadas."""
        self.calls = []
        self.custom_responses = {}


def criar_mock_schema_response() -> MockGeminiResponse:
    """Cria resposta mock para geração de schema."""
    schema_json = {
        "schema": {
            "nome_autor": {
                "type": "text",
                "description": "Nome completo do autor da ação"
            },
            "valor_causa": {
                "type": "currency",
                "description": "Valor total da causa"
            },
            "autor_idoso": {
                "type": "boolean",
                "description": "Se o autor é idoso (60+ anos)"
            },
            "tipo_medicamento": {
                "type": "choice",
                "description": "Tipo do medicamento solicitado",
                "options": ["Alto custo", "Básico", "Especial"]
            }
        },
        "mapeamento_variaveis": {
            "1": {
                "slug": "nome_autor",
                "label": "Nome do Autor",
                "tipo": "text",
                "descricao": "Nome completo do autor da ação"
            },
            "2": {
                "slug": "valor_causa",
                "label": "Valor da Causa",
                "tipo": "currency",
                "descricao": "Valor total da causa"
            },
            "3": {
                "slug": "autor_idoso",
                "label": "Autor Idoso",
                "tipo": "boolean",
                "descricao": "Se o autor é idoso"
            },
            "4": {
                "slug": "tipo_medicamento",
                "label": "Tipo de Medicamento",
                "tipo": "choice",
                "descricao": "Tipo do medicamento",
                "opcoes": ["Alto custo", "Básico", "Especial"]
            }
        }
    }

    return MockGeminiResponse(
        success=True,
        content=json.dumps(schema_json, ensure_ascii=False),
        model="gemini-3-flash-preview"
    )


def criar_mock_regra_response(prompt: str = "") -> MockGeminiResponse:
    """Cria resposta mock para geração de regra determinística."""

    # Detecta tipo de regra baseado no prompt
    prompt_lower = prompt.lower()

    if "maior que" in prompt_lower or "greater" in prompt_lower:
        regra = {
            "regra": {
                "type": "condition",
                "variable": "valor_causa",
                "operator": "greater_than",
                "value": 100000
            },
            "variaveis_usadas": ["valor_causa"]
        }
    elif "idoso" in prompt_lower and "ou" in prompt_lower:
        regra = {
            "regra": {
                "type": "or",
                "conditions": [
                    {"type": "condition", "variable": "autor_idoso", "operator": "equals", "value": True},
                    {"type": "condition", "variable": "autor_crianca", "operator": "equals", "value": True}
                ]
            },
            "variaveis_usadas": ["autor_idoso", "autor_crianca"]
        }
    elif "alto custo" in prompt_lower and "rename" in prompt_lower:
        regra = {
            "regra": {
                "type": "and",
                "conditions": [
                    {"type": "condition", "variable": "medicamento_alto_custo", "operator": "equals", "value": True},
                    {"type": "condition", "variable": "medicamento_rename", "operator": "equals", "value": False}
                ]
            },
            "variaveis_usadas": ["medicamento_alto_custo", "medicamento_rename"]
        }
    else:
        # Regra simples padrão
        regra = {
            "regra": {
                "type": "condition",
                "variable": "tipo_acao",
                "operator": "equals",
                "value": "medicamentos"
            },
            "variaveis_usadas": ["tipo_acao"]
        }

    return MockGeminiResponse(
        success=True,
        content=json.dumps(regra, ensure_ascii=False),
        model="gemini-3-flash-preview"
    )


def criar_mock_erro_response(erro: str = "Erro simulado") -> MockGeminiResponse:
    """Cria resposta mock de erro."""
    return MockGeminiResponse(
        success=False,
        content="",
        error=erro,
        model="gemini-3-flash-preview"
    )
