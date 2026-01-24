# -*- coding: utf-8 -*-
"""
Tradutor de erros tecnicos para mensagens amigaveis.

Este modulo traduz mensagens de erro tecnicas (CUDA, PyTorch, etc)
para linguagem simples que usuarios leigos conseguem entender.
"""

import re
from typing import Optional, Tuple, Dict, Any
from dataclasses import dataclass


@dataclass
class FriendlyError:
    """Erro traduzido com informacoes amigaveis."""
    title: str  # Titulo curto
    message: str  # Mensagem explicativa
    suggestion: Optional[str] = None  # O que o usuario pode fazer
    can_auto_retry: bool = False  # Sistema pode tentar novamente automaticamente
    retry_config: Optional[Dict[str, Any]] = None  # Config para retry automatico


# ==================== Padroes de Erro ====================

ERROR_PATTERNS = [
    # CUDA Out of Memory
    {
        "pattern": r"(CUDA out of memory|OutOfMemoryError|CUDA error: out of memory)",
        "title": "Memoria insuficiente",
        "message": "O computador que estava treinando ficou sem memoria.",
        "suggestion": "Tente novamente com configuracoes mais leves (batch size menor ou textos mais curtos).",
        "can_auto_retry": True,
        "retry_config": {
            "batch_size": 0.5,  # Multiplicador: reduz pela metade
            "max_length": 0.5
        }
    },
    # CUDA not available
    {
        "pattern": r"(CUDA is not available|No GPU found|cuda:0 is not available)",
        "title": "GPU nao disponivel",
        "message": "O computador de treinamento nao tem GPU disponivel ou ela nao foi detectada.",
        "suggestion": "Verifique se o worker esta configurado corretamente e a GPU esta funcionando.",
        "can_auto_retry": False
    },
    # Connection errors
    {
        "pattern": r"(Connection refused|ConnectionError|HTTPSConnectionPool|Max retries exceeded)",
        "title": "Erro de conexao",
        "message": "O computador de treinamento nao conseguiu se conectar ao servidor.",
        "suggestion": "Verifique sua conexao com a internet e tente novamente.",
        "can_auto_retry": True,
        "retry_config": {}  # Retry sem alteracao de config
    },
    # File not found
    {
        "pattern": r"(FileNotFoundError|No such file or directory|Dataset file not found)",
        "title": "Arquivo nao encontrado",
        "message": "O arquivo do dataset nao foi encontrado.",
        "suggestion": "Verifique se o dataset foi enviado corretamente e tente novamente.",
        "can_auto_retry": False
    },
    # Invalid data format
    {
        "pattern": r"(JSONDecodeError|Invalid JSON|cannot decode|UnicodeDecodeError)",
        "title": "Formato de dados invalido",
        "message": "O formato dos dados no arquivo esta incorreto.",
        "suggestion": "Verifique se a planilha esta no formato correto e tente enviar novamente.",
        "can_auto_retry": False
    },
    # Model not found
    {
        "pattern": r"(Model not found|can't load model|model does not exist|OSError: .+ is not a local folder)",
        "title": "Modelo nao encontrado",
        "message": "O modelo base especificado nao foi encontrado.",
        "suggestion": "Verifique se o nome do modelo esta correto ou escolha outro modelo.",
        "can_auto_retry": False
    },
    # Empty dataset / No samples
    {
        "pattern": r"(No samples found|Empty dataset|Dataset is empty|zero samples)",
        "title": "Dataset vazio",
        "message": "O dataset nao contem amostras validas para treinamento.",
        "suggestion": "Verifique se a planilha tem dados validos nas colunas de texto e labels.",
        "can_auto_retry": False
    },
    # Single class
    {
        "pattern": r"(single class|only one class|one unique label|precisa de pelo menos 2)",
        "title": "Apenas uma categoria",
        "message": "Todas as amostras tem a mesma categoria. O modelo precisa de pelo menos 2 categorias diferentes.",
        "suggestion": "Adicione exemplos de outras categorias ao dataset.",
        "can_auto_retry": False
    },
    # Timeout
    {
        "pattern": r"(Timeout|TimeoutError|timed out|job timeout|exceeded timeout)",
        "title": "Tempo esgotado",
        "message": "O treinamento demorou mais do que o esperado e foi interrompido.",
        "suggestion": "Tente novamente com um dataset menor ou configuracoes mais rapidas.",
        "can_auto_retry": True,
        "retry_config": {
            "epochs": 0.5  # Reduz epocas pela metade
        }
    },
    # NaN loss
    {
        "pattern": r"(NaN loss|loss is NaN|NaN detected|gradient overflow)",
        "title": "Erro no treinamento",
        "message": "O modelo encontrou valores invalidos durante o treinamento.",
        "suggestion": "Tente novamente com learning rate menor.",
        "can_auto_retry": True,
        "retry_config": {
            "learning_rate": 0.5  # Reduz learning rate pela metade
        }
    },
    # Worker disconnected
    {
        "pattern": r"(Worker disconnected|worker not responding|heartbeat timeout|worker died)",
        "title": "Computador de treinamento desconectado",
        "message": "O computador que estava treinando parou de responder.",
        "suggestion": "O sistema vai tentar novamente automaticamente quando um computador estiver disponivel.",
        "can_auto_retry": True,
        "retry_config": {}
    },
    # Generic Python errors
    {
        "pattern": r"(RuntimeError|ValueError|TypeError|AttributeError)",
        "title": "Erro interno",
        "message": "Ocorreu um erro inesperado durante o processamento.",
        "suggestion": "Por favor, tente novamente. Se o erro persistir, entre em contato com o suporte.",
        "can_auto_retry": False
    }
]


def translate_error(error_message: str) -> FriendlyError:
    """
    Traduz uma mensagem de erro tecnica para linguagem amigavel.

    Args:
        error_message: Mensagem de erro original

    Returns:
        FriendlyError com informacoes amigaveis
    """
    if not error_message:
        return FriendlyError(
            title="Erro desconhecido",
            message="Ocorreu um erro durante o processamento.",
            suggestion="Por favor, tente novamente."
        )

    error_lower = error_message.lower()

    for pattern_info in ERROR_PATTERNS:
        if re.search(pattern_info["pattern"], error_message, re.IGNORECASE):
            return FriendlyError(
                title=pattern_info["title"],
                message=pattern_info["message"],
                suggestion=pattern_info.get("suggestion"),
                can_auto_retry=pattern_info.get("can_auto_retry", False),
                retry_config=pattern_info.get("retry_config")
            )

    # Fallback para erros nao reconhecidos
    return FriendlyError(
        title="Erro no treinamento",
        message="Ocorreu um erro durante o treinamento do modelo.",
        suggestion="Por favor, tente novamente. Se o erro persistir, entre em contato com o suporte."
    )


def get_friendly_error_message(error_message: str) -> str:
    """
    Retorna apenas a mensagem amigavel (string simples).

    Args:
        error_message: Mensagem de erro original

    Returns:
        Mensagem traduzida
    """
    friendly = translate_error(error_message)
    parts = [friendly.message]
    if friendly.suggestion:
        parts.append(friendly.suggestion)
    return " ".join(parts)


def calculate_retry_config(
    original_config: Dict[str, Any],
    error_message: str
) -> Tuple[bool, Dict[str, Any]]:
    """
    Calcula configuracao para retry automatico baseado no erro.

    Args:
        original_config: Configuracao original do run
        error_message: Mensagem de erro

    Returns:
        Tuple de (pode_tentar_novamente, nova_configuracao)
    """
    friendly = translate_error(error_message)

    if not friendly.can_auto_retry or not friendly.retry_config:
        return False, original_config

    new_config = dict(original_config)

    for key, multiplier in friendly.retry_config.items():
        if key in new_config and new_config[key] is not None:
            if isinstance(new_config[key], int):
                new_config[key] = max(1, int(new_config[key] * multiplier))
            elif isinstance(new_config[key], float):
                new_config[key] = new_config[key] * multiplier

    return True, new_config


# ==================== Traducao de Metricas ====================

METRIC_TRANSLATIONS = {
    "accuracy": {
        "name": "Acertos",
        "description": "Porcentagem de classificacoes corretas",
        "tooltip": "De cada 100 textos, quantos o modelo classifica corretamente"
    },
    "macro_f1": {
        "name": "Equilibrio entre categorias",
        "description": "Media de acerto considerando todas as categorias igualmente",
        "tooltip": "Util quando algumas categorias tem menos exemplos"
    },
    "weighted_f1": {
        "name": "F1 ponderado",
        "description": "Media de acerto ponderada pelo numero de exemplos",
        "tooltip": "Considera o tamanho de cada categoria"
    },
    "precision": {
        "name": "Precisao",
        "description": "Quando o modelo diz que e X, esta certo?",
        "tooltip": "Porcentagem de acerto das predicoes positivas"
    },
    "recall": {
        "name": "Cobertura",
        "description": "O modelo encontra todos os X?",
        "tooltip": "Porcentagem de exemplos da categoria que foram encontrados"
    },
    "loss": {
        "name": "Erro",
        "description": "Erro durante o treinamento (quanto menor, melhor)",
        "tooltip": "Medida interna de quanto o modelo esta errando"
    }
}


def translate_metric_name(metric_key: str) -> str:
    """Traduz nome da metrica para portugues amigavel."""
    if metric_key in METRIC_TRANSLATIONS:
        return METRIC_TRANSLATIONS[metric_key]["name"]
    return metric_key.replace("_", " ").title()


def get_metric_tooltip(metric_key: str) -> str:
    """Retorna tooltip explicativo da metrica."""
    if metric_key in METRIC_TRANSLATIONS:
        return METRIC_TRANSLATIONS[metric_key]["tooltip"]
    return ""


# ==================== Alertas de Qualidade ====================

def get_quality_alert(metrics: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """
    Gera alerta de qualidade baseado nas metricas.

    Args:
        metrics: Dicionario com metricas (accuracy, macro_f1, etc)

    Returns:
        Dicionario com tipo, mensagem e cor do alerta, ou None
    """
    accuracy = metrics.get("accuracy") or metrics.get("final_accuracy")
    macro_f1 = metrics.get("macro_f1") or metrics.get("final_macro_f1")
    train_accuracy = metrics.get("train_accuracy")
    val_accuracy = metrics.get("val_accuracy")

    if accuracy is None:
        return None

    # Overfitting detection
    if train_accuracy and val_accuracy:
        if train_accuracy - val_accuracy > 0.15:
            return {
                "type": "overfitting",
                "title": "Possivel memorizacao",
                "message": "O modelo decorou os exemplos de treino. Adicione mais dados variados.",
                "color": "orange"
            }

    # Underfitting detection
    if train_accuracy and train_accuracy < 0.70:
        return {
            "type": "underfitting",
            "title": "Modelo nao aprendeu",
            "message": "O modelo nao conseguiu aprender. Verifique a qualidade dos dados.",
            "color": "red"
        }

    # Class imbalance issue
    if macro_f1 and accuracy - macro_f1 > 0.10:
        return {
            "type": "class_imbalance",
            "title": "Categorias ignoradas",
            "message": "Algumas categorias estao sendo ignoradas. Adicione mais exemplos das categorias menores.",
            "color": "orange"
        }

    # Quality levels
    if accuracy > 0.95:
        return {
            "type": "excellent",
            "title": "Excelente",
            "message": "Seu modelo esta muito preciso!",
            "color": "green"
        }
    elif accuracy >= 0.85:
        return {
            "type": "good",
            "title": "Bom",
            "message": "Seu modelo tem uma precisao adequada.",
            "color": "green"
        }
    elif accuracy >= 0.70:
        return {
            "type": "acceptable",
            "title": "Aceitavel",
            "message": "O modelo funciona, mas pode melhorar. Considere adicionar mais exemplos.",
            "color": "yellow"
        }
    else:
        return {
            "type": "poor",
            "title": "Precisa melhorar",
            "message": "O modelo precisa de melhorias. Verifique se os dados estao corretos.",
            "color": "red"
        }


def format_accuracy_friendly(accuracy: float) -> str:
    """
    Formata accuracy como porcentagem com interpretacao.

    Args:
        accuracy: Valor de accuracy (0-1)

    Returns:
        String formatada (ex: "87% (Bom)")
    """
    percentage = int(accuracy * 100)
    alert = get_quality_alert({"accuracy": accuracy})

    if alert:
        return f"{percentage}% ({alert['title']})"
    return f"{percentage}%"
