# services/text_normalizer/models.py
"""
Modelos de dados para o serviço de normalização de texto.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class NormalizationMode(str, Enum):
    """
    Modos de normalização disponíveis.

    - conservative: Apenas limpezas básicas, preserva formatação
    - balanced: Limpeza moderada, bom equilíbrio (padrão)
    - aggressive: Máxima compressão, remove redundâncias
    """
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"


class NormalizationOptions(BaseModel):
    """Opções configuráveis para normalização de texto."""

    mode: NormalizationMode = Field(
        default=NormalizationMode.BALANCED,
        description="Modo de normalização"
    )

    remove_control_chars: bool = Field(
        default=True,
        description="Remove caracteres de controle (exceto newline)"
    )

    remove_invisible_unicode: bool = Field(
        default=True,
        description="Remove caracteres Unicode invisíveis"
    )

    collapse_whitespace: bool = Field(
        default=True,
        description="Colapsa múltiplos espaços em um"
    )

    remove_page_numbers: bool = Field(
        default=True,
        description="Remove números de página isolados"
    )

    detect_headers_footers: bool = Field(
        default=True,
        description="Detecta e remove headers/footers repetidos"
    )

    fix_hyphenation: bool = Field(
        default=True,
        description="Corrige palavras hifenizadas quebradas entre linhas"
    )

    smart_line_join: bool = Field(
        default=True,
        description="Junta linhas quebradas no meio de frases"
    )

    deduplicate_blocks: bool = Field(
        default=False,
        description="Remove blocos de texto duplicados (apenas modo aggressive)"
    )

    normalize_unicode: bool = Field(
        default=True,
        description="Normaliza caracteres Unicode (smart quotes, dashes)"
    )

    max_consecutive_newlines: int = Field(
        default=2,
        ge=1,
        le=5,
        description="Máximo de quebras de linha consecutivas"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "mode": "balanced",
                "remove_control_chars": True,
                "fix_hyphenation": True,
                "smart_line_join": True
            }
        }
    )


@dataclass
class NormalizationStats:
    """Estatísticas da normalização."""

    original_length: int = 0
    normalized_length: int = 0
    original_lines: int = 0
    normalized_lines: int = 0
    chars_removed: int = 0
    lines_joined: int = 0
    hyphenations_fixed: int = 0
    headers_removed: int = 0
    footers_removed: int = 0
    page_numbers_removed: int = 0
    blocks_deduplicated: int = 0
    processing_time_ms: float = 0.0

    @property
    def compression_ratio(self) -> float:
        """Taxa de compressão (0-1, quanto menor, mais comprimido)."""
        if self.original_length == 0:
            return 1.0
        return self.normalized_length / self.original_length

    @property
    def reduction_percent(self) -> float:
        """Percentual de redução de tamanho."""
        return (1 - self.compression_ratio) * 100

    def to_dict(self) -> dict:
        """Converte para dicionário."""
        return {
            "original_length": self.original_length,
            "normalized_length": self.normalized_length,
            "original_lines": self.original_lines,
            "normalized_lines": self.normalized_lines,
            "chars_removed": self.chars_removed,
            "lines_joined": self.lines_joined,
            "hyphenations_fixed": self.hyphenations_fixed,
            "headers_removed": self.headers_removed,
            "footers_removed": self.footers_removed,
            "page_numbers_removed": self.page_numbers_removed,
            "blocks_deduplicated": self.blocks_deduplicated,
            "compression_ratio": round(self.compression_ratio, 4),
            "reduction_percent": round(self.reduction_percent, 2),
            "processing_time_ms": round(self.processing_time_ms, 2)
        }


class NormalizationRequest(BaseModel):
    """Request para normalização de texto via API."""

    text: str = Field(
        ...,
        min_length=1,
        description="Texto a ser normalizado"
    )

    options: Optional[NormalizationOptions] = Field(
        default=None,
        description="Opções de normalização (usa padrões se não fornecido)"
    )


class NormalizationResponse(BaseModel):
    """Response da normalização de texto via API."""

    text: str = Field(
        ...,
        description="Texto normalizado"
    )

    stats: dict = Field(
        ...,
        description="Estatísticas da normalização"
    )

    estimated_tokens: int = Field(
        ...,
        description="Estimativa de tokens (~4 chars/token)"
    )


@dataclass
class NormalizationResult:
    """Resultado completo da normalização (uso interno)."""

    text: str
    stats: NormalizationStats = field(default_factory=NormalizationStats)

    @property
    def estimated_tokens(self) -> int:
        """Estimativa de tokens (~4 chars/token)."""
        return len(self.text) // 4 if self.text else 0

    def to_response(self) -> NormalizationResponse:
        """Converte para response da API."""
        return NormalizationResponse(
            text=self.text,
            stats=self.stats.to_dict(),
            estimated_tokens=self.estimated_tokens
        )
