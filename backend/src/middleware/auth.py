from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Request
from passlib.context import CryptContext

from backend.src.config.settings import settings
from backend.src.roles import can_review_art
from backend.src.services.usuario_service import obtener_usuario
from backend.src.services.notification_service import get_notifications
from backend.src.services.art_service import contar_art_pendientes

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALGORITHM = "HS256"


def create_access_token(username: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": username,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def set_auth_cookie(response, token: str) -> None:
    response.set_cookie(
        settings.auth_cookie_name,
        token,
        max_age=settings.access_token_minutes * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
    )


def delete_auth_cookie(response) -> None:
    response.delete_cookie(settings.auth_cookie_name)


def get_current_user(request: Request):
    token = request.cookies.get(settings.auth_cookie_name)
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    username = payload.get("sub")
    if not isinstance(username, str) or not username:
        return None
    user = obtener_usuario(username)
    if not user:
        return None
    if can_review_art(user.get("rol", "")):
        try:
            user["pendientes"] = contar_art_pendientes()
        except Exception:
            user["pendientes"] = 0
    try:
        # attach unread notification count
        user["notificaciones_no_leidas"] = len([n for n in get_notifications(user["username"]) if not n.get("read")])
    except Exception:
        user["notificaciones_no_leidas"] = 0
    return user
