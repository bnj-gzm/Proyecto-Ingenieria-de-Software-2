from __future__ import annotations


def password_policy_errors(password: str) -> list[str]:
    errors: list[str] = []
    if len(password) < 8:
        errors.append("mínimo 8 caracteres")
    if not any(char.isupper() for char in password):
        errors.append("una mayúscula")
    if not any(char.islower() for char in password):
        errors.append("una minúscula")
    if not any(char.isdigit() for char in password):
        errors.append("un número")
    return errors


def validate_password_strength(password: str) -> tuple[bool, str]:
    errors = password_policy_errors(password)
    if errors:
        return False, "La contraseña debe incluir " + ", ".join(errors) + "."
    return True, ""
