from fastapi import Request
from passlib.context import CryptContext

from backend.src.services.usuario_service import obtener_usuario
from backend.src.services.art_service import contar_art_pendientes

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_current_user(request: Request):
    username = request.cookies.get("user")
    if not username:
        return None
    user = obtener_usuario(username)
    if not user:
        return None
    if user.get("rol") == "admin":
        try:
            user["pendientes"] = contar_art_pendientes()
        except Exception:
            user["pendientes"] = 0
    return user
