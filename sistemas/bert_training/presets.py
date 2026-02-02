# -*- coding: utf-8 -*-
"""
Presets de configuracao para treinamento BERT.

Este modulo define os presets padrao do sistema em MEMORIA (sem banco de dados).
Isso permite usar presets sem precisar de migracao de banco.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


# ==================== Dataclass para Preset ====================

@dataclass
class Preset:
    """Preset de configuracao em memoria."""
    name: str
    display_name: str
    description: str
    icon: str
    config: Dict[str, Any]
    estimated_time_minutes_min: int
    estimated_time_minutes_max: int
    is_recommended: bool
    sort_order: int


# ==================== Definicao dos Presets ====================

DEFAULT_PRESETS: Dict[str, Preset] = {
    "rapido": Preset(
        name="rapido",
        display_name="Rapido",
        description="Ideal para testar se o dataset esta no formato certo. Treino rapido com menos precisao.",
        icon="zap",
        config={
            "learning_rate": 2e-5,
            "batch_size": 32,
            "epochs": 3,
            "max_length": 512,
            "train_split": 0.8,
            "warmup_steps": 0,
            "weight_decay": 0.01,
            "gradient_accumulation_steps": 1,
            "early_stopping_patience": None,
            "use_class_weights": True,
            "seed": 42,
            "truncation_side": "right"
        },
        estimated_time_minutes_min=5,
        estimated_time_minutes_max=15,
        is_recommended=False,
        sort_order=1
    ),
    "equilibrado": Preset(
        name="equilibrado",
        display_name="Equilibrado",
        description="Melhor custo-beneficio para a maioria dos casos. Recomendado para uso geral.",
        icon="scale",
        config={
            "learning_rate": 5e-5,
            "batch_size": 16,
            "epochs": 10,
            "max_length": 512,
            "train_split": 0.8,
            "warmup_steps": 0,
            "weight_decay": 0.01,
            "gradient_accumulation_steps": 1,
            "early_stopping_patience": 3,
            "use_class_weights": True,
            "seed": 42,
            "truncation_side": "right"
        },
        estimated_time_minutes_min=30,
        estimated_time_minutes_max=60,
        is_recommended=True,
        sort_order=2
    ),
    "preciso": Preset(
        name="preciso",
        display_name="Preciso",
        description="Maximo de qualidade, mais demorado. Use quando precisar da melhor precisao possivel.",
        icon="target",
        config={
            "learning_rate": 3e-5,
            "batch_size": 8,
            "epochs": 30,
            "max_length": 512,
            "train_split": 0.8,
            "warmup_steps": 100,
            "weight_decay": 0.01,
            "gradient_accumulation_steps": 2,
            "early_stopping_patience": 5,
            "use_class_weights": True,
            "seed": 42,
            "truncation_side": "right"
        },
        estimated_time_minutes_min=120,
        estimated_time_minutes_max=240,
        is_recommended=False,
        sort_order=3
    )
}


# ==================== Funcoes de Acesso ====================

def get_preset_by_name(name: str) -> Optional[Preset]:
    """
    Busca um preset pelo nome.

    Args:
        name: Nome do preset (rapido, equilibrado, preciso)

    Returns:
        Preset encontrado ou None
    """
    return DEFAULT_PRESETS.get(name)


def get_all_presets() -> List[Preset]:
    """
    Retorna todos os presets ordenados.
    """
    return sorted(DEFAULT_PRESETS.values(), key=lambda p: p.sort_order)


def get_default_preset() -> Preset:
    """
    Retorna o preset padrao (equilibrado).
    """
    return DEFAULT_PRESETS["equilibrado"]


def get_recommended_preset() -> Preset:
    """
    Retorna o preset recomendado.
    """
    for preset in DEFAULT_PRESETS.values():
        if preset.is_recommended:
            return preset
    return get_default_preset()


def get_preset_config(name: str) -> Dict[str, Any]:
    """
    Retorna apenas a configuracao de um preset.

    Args:
        name: Nome do preset

    Returns:
        Dicionario de configuracao ou config do preset padrao
    """
    preset = get_preset_by_name(name)
    if preset:
        return dict(preset.config)
    return dict(get_default_preset().config)


def merge_preset_with_overrides(
    preset_name: str,
    overrides: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Mescla configuracao do preset com overrides do usuario.

    Args:
        preset_name: Nome do preset base
        overrides: Parametros para sobrescrever (opcional)

    Returns:
        Configuracao final mesclada
    """
    config = get_preset_config(preset_name)

    if overrides:
        for key, value in overrides.items():
            if value is not None:
                config[key] = value

    return config


def preset_to_dict(preset: Preset) -> Dict[str, Any]:
    """
    Converte preset para dicionario (para resposta API).
    """
    return {
        "name": preset.name,
        "display_name": preset.display_name,
        "description": preset.description,
        "icon": preset.icon,
        "config": preset.config,
        "estimated_time_minutes_min": preset.estimated_time_minutes_min,
        "estimated_time_minutes_max": preset.estimated_time_minutes_max,
        "is_recommended": preset.is_recommended
    }


def get_all_presets_as_dicts() -> List[Dict[str, Any]]:
    """
    Retorna todos os presets como lista de dicionarios.
    """
    return [preset_to_dict(p) for p in get_all_presets()]
