from __future__ import annotations

import hmac
import secrets
import time

from fastapi import HTTPException, Request

from backend.src.config.settings import settings

TOKEN_TTL_SECONDS = 60 * 60 * 2


def create_csrf_token() -> str:
    nonce = secrets.token_urlsafe(32)
    issued_at = str(int(time.time()))
    message = f"{nonce}.{issued_at}"
    signature = hmac.digest(settings.secret_key.encode(), message.encode(), "sha256").hex()
    return f"{message}.{signature}"


def set_csrf_cookie(response, token: str) -> None:
    response.set_cookie(
        settings.csrf_cookie_name,
        token,
        max_age=TOKEN_TTL_SECONDS,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
    )


def validate_csrf_token(request: Request, csrf_token: str) -> None:
    cookie_token = request.cookies.get(settings.csrf_cookie_name)
    if not cookie_token or not csrf_token or not hmac.compare_digest(cookie_token, csrf_token):
        raise HTTPException(status_code=403, detail="Token CSRF inválido")

    parts = csrf_token.split(".")
    if len(parts) != 3:
        raise HTTPException(status_code=403, detail="Token CSRF inválido")

    nonce, issued_at, signature = parts
    message = f"{nonce}.{issued_at}"
    expected = hmac.digest(settings.secret_key.encode(), message.encode(), "sha256").hex()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=403, detail="Token CSRF inválido")

    try:
        age = time.time() - int(issued_at)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Token CSRF inválido") from exc
    if age > TOKEN_TTL_SECONDS:
        raise HTTPException(status_code=403, detail="Token CSRF expirado")
