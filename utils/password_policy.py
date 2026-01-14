# utils/password_policy.py
"""
SECURITY: Política de senhas fortes.

Este módulo define regras para validação de senhas:
- Comprimento mínimo
- Complexidade (maiúsculas, minúsculas, números, caracteres especiais)
- Lista de senhas comuns bloqueadas
- Verificação de senhas sequenciais/repetidas

Referências:
- NIST SP 800-63B: Digital Identity Guidelines
- OWASP Password Security Cheat Sheet
"""

import re
from typing import Tuple, List

# Configurações de política de senha
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128
REQUIRE_UPPERCASE = True
REQUIRE_LOWERCASE = True
REQUIRE_DIGIT = True
REQUIRE_SPECIAL = True

# Caracteres especiais aceitos
SPECIAL_CHARACTERS = r"!@#$%^&*(),.?\":{}|<>_\-+=\[\]\\\/~`';€£¥"

# Lista de senhas comuns bloqueadas (expandir conforme necessário)
COMMON_PASSWORDS = {
    # Top 100 senhas mais comuns
    "123456", "password", "123456789", "12345678", "12345", "1234567",
    "1234567890", "qwerty", "abc123", "111111", "123123", "admin",
    "letmein", "welcome", "monkey", "dragon", "master", "password1",
    "senha", "senha123", "mudar123", "trocar123", "admin123", "root",
    "administrator", "user", "test", "guest", "login", "pass", "1234",
    "123", "12", "1", "qwerty123", "password123", "iloveyou", "princess",
    "sunshine", "football", "baseball", "soccer", "hockey", "batman",
    "trustno1", "passw0rd", "p@ssword", "p@ssw0rd", "p455w0rd",
    # Senhas em português
    "brasil", "futebol", "flamengo", "corinthians", "palmeiras", "santos",
    "cruzeiro", "gremio", "internacional", "saopaulo", "botafogo", "vasco",
    "amor", "amor123", "familia", "felicidade", "sucesso", "vitoria",
    "liberdade", "esperanca", "sonho", "jesus", "deus", "cristo",
    # Padrões de teclado
    "qwertyuiop", "asdfghjkl", "zxcvbnm", "1qaz2wsx", "qazwsx",
    "1q2w3e4r", "1q2w3e", "zaq12wsx", "!qaz2wsx", "q1w2e3r4",
}

# Padrões de senhas fracas (regex)
WEAK_PATTERNS = [
    r'^(.)\1+$',  # Caractere repetido (aaaaaa)
    r'^(012|123|234|345|456|567|678|789|890)+$',  # Sequência numérica
    r'^(abc|bcd|cde|def|efg|fgh|ghi|hij|ijk|jkl|klm|lmn|mno|nop|opq|pqr|qrs|rst|stu|tuv|uvw|vwx|wxy|xyz)+$',  # Sequência alfabética
    r'^(qwe|wer|ert|rty|tyu|yui|uio|iop|asd|sdf|dfg|fgh|ghj|hjk|jkl|zxc|xcv|cvb|vbn|bnm)+$',  # Padrão de teclado
]


def check_password_strength(password: str) -> Tuple[bool, List[str]]:
    """
    SECURITY: Verifica a força de uma senha.

    Args:
        password: Senha a ser verificada

    Returns:
        Tuple (is_valid, list_of_errors)

    Example:
        is_valid, errors = check_password_strength("MinhaS3nh@!")
        if not is_valid:
            print("Erros:", errors)
    """
    errors = []

    # Verifica comprimento
    if len(password) < MIN_PASSWORD_LENGTH:
        errors.append(f"Senha deve ter pelo menos {MIN_PASSWORD_LENGTH} caracteres")

    if len(password) > MAX_PASSWORD_LENGTH:
        errors.append(f"Senha deve ter no máximo {MAX_PASSWORD_LENGTH} caracteres")

    # Verifica complexidade
    if REQUIRE_UPPERCASE and not re.search(r'[A-Z]', password):
        errors.append("Senha deve conter pelo menos uma letra maiúscula")

    if REQUIRE_LOWERCASE and not re.search(r'[a-z]', password):
        errors.append("Senha deve conter pelo menos uma letra minúscula")

    if REQUIRE_DIGIT and not re.search(r'\d', password):
        errors.append("Senha deve conter pelo menos um número")

    if REQUIRE_SPECIAL and not re.search(f'[{re.escape(SPECIAL_CHARACTERS)}]', password):
        errors.append("Senha deve conter pelo menos um caractere especial (!@#$%^&*)")

    # Verifica lista de senhas comuns
    if password.lower() in COMMON_PASSWORDS:
        errors.append("Esta senha é muito comum e não pode ser usada")

    # Verifica padrões fracos
    password_lower = password.lower()
    for pattern in WEAK_PATTERNS:
        if re.match(pattern, password_lower):
            errors.append("Senha contém padrão fraco (sequência ou repetição)")
            break

    # Verifica se contém informações óbvias
    obvious_words = ["password", "senha", "admin", "user", "login", "root"]
    for word in obvious_words:
        if word in password_lower:
            errors.append(f"Senha não pode conter a palavra '{word}'")
            break

    return len(errors) == 0, errors


def validate_password(password: str) -> str:
    """
    SECURITY: Valida senha e retorna ela mesma se válida, ou levanta ValueError.

    Esta função é útil para usar como Pydantic validator.

    Args:
        password: Senha a ser validada

    Returns:
        A senha se válida

    Raises:
        ValueError: Se a senha não atende aos requisitos
    """
    is_valid, errors = check_password_strength(password)

    if not is_valid:
        raise ValueError("; ".join(errors))

    return password


def get_password_requirements() -> dict:
    """
    Retorna os requisitos de senha em formato legível.

    Útil para exibir ao usuário na interface.
    """
    return {
        "min_length": MIN_PASSWORD_LENGTH,
        "max_length": MAX_PASSWORD_LENGTH,
        "require_uppercase": REQUIRE_UPPERCASE,
        "require_lowercase": REQUIRE_LOWERCASE,
        "require_digit": REQUIRE_DIGIT,
        "require_special": REQUIRE_SPECIAL,
        "special_characters": SPECIAL_CHARACTERS,
        "description": (
            f"A senha deve ter entre {MIN_PASSWORD_LENGTH} e {MAX_PASSWORD_LENGTH} caracteres, "
            "incluindo pelo menos: uma letra maiúscula, uma letra minúscula, "
            "um número e um caractere especial (!@#$%^&*)"
        )
    }


def generate_password_feedback(password: str) -> dict:
    """
    Gera feedback detalhado sobre a força de uma senha.

    Útil para mostrar indicador de força em tempo real na UI.
    """
    score = 0
    feedback = []

    # Pontuação por comprimento
    if len(password) >= MIN_PASSWORD_LENGTH:
        score += 1
        if len(password) >= 12:
            score += 1
        if len(password) >= 16:
            score += 1
    else:
        feedback.append("Adicione mais caracteres")

    # Pontuação por complexidade
    if re.search(r'[A-Z]', password):
        score += 1
    else:
        feedback.append("Adicione letras maiúsculas")

    if re.search(r'[a-z]', password):
        score += 1
    else:
        feedback.append("Adicione letras minúsculas")

    if re.search(r'\d', password):
        score += 1
    else:
        feedback.append("Adicione números")

    if re.search(f'[{re.escape(SPECIAL_CHARACTERS)}]', password):
        score += 1
    else:
        feedback.append("Adicione caracteres especiais")

    # Penalidades
    if password.lower() in COMMON_PASSWORDS:
        score = max(0, score - 3)
        feedback.append("Evite senhas comuns")

    # Classificação
    if score <= 2:
        strength = "weak"
        strength_label = "Fraca"
    elif score <= 4:
        strength = "fair"
        strength_label = "Razoável"
    elif score <= 6:
        strength = "good"
        strength_label = "Boa"
    else:
        strength = "strong"
        strength_label = "Forte"

    return {
        "score": score,
        "max_score": 7,
        "strength": strength,
        "strength_label": strength_label,
        "feedback": feedback
    }
