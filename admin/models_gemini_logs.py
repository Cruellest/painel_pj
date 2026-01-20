# admin/models_gemini_logs.py
"""
Modelo para logs de chamadas da API Gemini.

Captura TODAS as chamadas de IA de TODOS os usuários/sistemas para:
- Monitoramento de uso e custos
- Diagnóstico de latência
- Análise de taxa de sucesso/erro
- Identificação de gargalos por sistema/módulo
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, Text, Index
from database.connection import Base
from utils.timezone import get_utc_now


class GeminiApiLog(Base):
    """
    Log de chamadas à API do Gemini.

    Diferente dos PerformanceLogs (que são por admin ativo),
    este modelo captura TODAS as chamadas de IA globalmente.
    """
    __tablename__ = "gemini_api_logs"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=get_utc_now, index=True)

    # Identificação do contexto (sem FK para evitar dependência circular)
    user_id = Column(Integer, nullable=True, index=True)
    username = Column(String(100), nullable=True)
    sistema = Column(String(100), nullable=False, index=True)  # gerador_pecas, pedido_calculo, etc
    modulo = Column(String(100), nullable=True)  # agentes, services_classificacao, etc

    # Rastreabilidade de request HTTP
    request_id = Column(String(36), nullable=True, index=True)  # UUID da request
    route = Column(String(255), nullable=True)  # Rota HTTP que originou a chamada

    # Request info
    model = Column(String(100), nullable=False, index=True)  # gemini-3-flash-preview, etc
    prompt_chars = Column(Integer, nullable=False)  # Tamanho do prompt em caracteres
    prompt_tokens_estimated = Column(Integer, nullable=True)  # Estimativa de tokens (~4 chars/token)
    has_images = Column(Boolean, default=False)  # Se a chamada incluiu imagens
    has_search = Column(Boolean, default=False)  # Se usou Google Search Grounding
    temperature = Column(Float, nullable=True)

    # Response info
    response_tokens = Column(Integer, nullable=True)  # Tokens na resposta
    success = Column(Boolean, nullable=False, index=True)  # Se a chamada foi bem-sucedida
    cached = Column(Boolean, default=False)  # Se veio do cache
    error = Column(String(500), nullable=True)  # Mensagem de erro (se houver)

    # Timing (milissegundos)
    time_prepare_ms = Column(Float, nullable=True)  # Tempo preparando payload
    time_connect_ms = Column(Float, nullable=True)  # Tempo conectando (TCP + TLS)
    time_ttft_ms = Column(Float, nullable=True)  # Time to First Token
    time_generation_ms = Column(Float, nullable=True)  # Tempo gerando resposta
    time_total_ms = Column(Float, nullable=False, index=True)  # Tempo total

    # Retry info
    retry_count = Column(Integer, default=0)  # Número de tentativas

    # Metadados extras (opcional)
    extra_info = Column(Text, nullable=True)  # JSON com info adicional se necessário

    # Indexes compostos para queries frequentes
    __table_args__ = (
        Index('ix_gemini_logs_date_sistema', 'created_at', 'sistema'),
        Index('ix_gemini_logs_sistema_model', 'sistema', 'model'),
        Index('ix_gemini_logs_success_date', 'success', 'created_at'),
        Index('ix_gemini_logs_user_date', 'user_id', 'created_at'),
    )

    def __repr__(self):
        return f"<GeminiApiLog(id={self.id}, sistema='{self.sistema}', model='{self.model}', success={self.success}, total={self.time_total_ms}ms)>"

    def to_dict(self):
        """Converte para dicionário para serialização"""
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "user_id": self.user_id,
            "username": self.username,
            "sistema": self.sistema,
            "modulo": self.modulo,
            "request_id": self.request_id,
            "route": self.route,
            "model": self.model,
            "prompt_chars": self.prompt_chars,
            "prompt_tokens_estimated": self.prompt_tokens_estimated,
            "has_images": self.has_images,
            "has_search": self.has_search,
            "temperature": self.temperature,
            "response_tokens": self.response_tokens,
            "success": self.success,
            "cached": self.cached,
            "error": self.error,
            "time_prepare_ms": self.time_prepare_ms,
            "time_connect_ms": self.time_connect_ms,
            "time_ttft_ms": self.time_ttft_ms,
            "time_generation_ms": self.time_generation_ms,
            "time_total_ms": self.time_total_ms,
            "retry_count": self.retry_count,
        }
