from __future__ import annotations

from base64 import b64encode
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

from backend.src.config.database import _connect

_STATIC_DIR = Path(__file__).resolve().parents[3] / "frontend" / "static"
_PROFILE_PREFIX = "uploads/perfiles/"
_MIME_BY_EXTENSION = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def _foto_perfil_src(value: Any) -> str:
    if not value:
        return ""
    texto = str(value).strip()
    if texto.startswith("data:"):
        return texto
    if texto.startswith("/static/"):
        texto = texto[len("/static/"):]
    if texto.startswith("static/"):
        texto = texto[len("static/"):]
    candidate = _STATIC_DIR / texto
    if not candidate.exists() and texto.startswith(_PROFILE_PREFIX):
        candidate = _STATIC_DIR / texto
    if candidate.exists():
        mime_type = _MIME_BY_EXTENSION.get(candidate.suffix.lower(), "image/jpeg")
        data = b64encode(candidate.read_bytes()).decode("ascii")
        return f"data:{mime_type};base64,{data}"
    return ""


def _normalize_user_row(row: dict[str, Any]) -> dict[str, Any]:
    row["foto_perfil"] = _foto_perfil_src(row.get("foto_perfil") or "")
    return row

_USER_COLUMNS = """
    id, username, password_hash, rol, nombre, email, rut, telefono, cargo,
    empresa, area, estado_cuenta, debe_cambiar_password, activation_token,
    activation_token_expires_at, reset_token, reset_token_expires_at,
    foto_perfil, created_at
"""


def obtener_usuario(username: str) -> dict[str, Any] | None:
    conn = _connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            SELECT
            """ + _USER_COLUMNS + """
            FROM users WHERE username = %s
            """,
            (username,),
        )
        row = cur.fetchone()
        return _normalize_user_row(dict(row)) if row else None
    finally:
        cur.close()
        conn.close()


def obtener_usuario_por_email(email: str) -> dict[str, Any] | None:
    conn = _connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            SELECT
            """ + _USER_COLUMNS + """
            FROM users WHERE lower(email) = lower(%s)
            """,
            (email,),
        )
        row = cur.fetchone()
        return _normalize_user_row(dict(row)) if row else None
    finally:
        cur.close()
        conn.close()


def cargar_usuarios() -> list[dict[str, Any]]:
    conn = _connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            SELECT
            """ + _USER_COLUMNS + """
            FROM users ORDER BY id ASC
            """
        )
        return [_normalize_user_row(dict(row)) for row in cur.fetchall()]
    finally:
        cur.close()
        conn.close()


def username_existe(username: str) -> bool:
    conn = _connect()
    cur = conn.cursor()
    try:
        cur.execute("SELECT 1 FROM users WHERE username = %s", (username,))
        return cur.fetchone() is not None
    finally:
        cur.close()
        conn.close()


def email_existe(email: str) -> bool:
    conn = _connect()
    cur = conn.cursor()
    try:
        cur.execute("SELECT 1 FROM users WHERE lower(email) = lower(%s)", (email,))
        return cur.fetchone() is not None
    finally:
        cur.close()
        conn.close()


def rut_existe(rut: str, username_excluir: str = "") -> bool:
    conn = _connect()
    cur = conn.cursor()
    try:
        if username_excluir:
            cur.execute("SELECT 1 FROM users WHERE rut = %s AND username <> %s", (rut, username_excluir))
        else:
            cur.execute("SELECT 1 FROM users WHERE rut = %s", (rut,))
        return cur.fetchone() is not None
    finally:
        cur.close()
        conn.close()


def cargar_usuarios_por_rol(rol: str) -> list[dict[str, Any]]:
    conn = _connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            SELECT id, username, rol, nombre, email, rut, telefono, cargo, empresa,
                   area, estado_cuenta, foto_perfil, created_at
            FROM users WHERE rol = %s ORDER BY nombre ASC, username ASC
            """,
            (rol,),
        )
        return [_normalize_user_row(dict(row)) for row in cur.fetchall()]
    finally:
        cur.close()
        conn.close()


def guardar_usuario(
    username: str,
    password_hash: str,
    rol: str,
    nombre: str = "",
    email: str = "",
    rut: str = "",
    telefono: str = "",
    cargo: str = "",
    empresa: str = "",
    area: str = "",
    estado_cuenta: str = "activo",
    debe_cambiar_password: bool = False,
    activation_token: str = "",
    activation_token_expires_at: datetime | None = None,
) -> None:
    conn = _connect()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO users (
                username, password_hash, rol, nombre, email, rut, telefono, cargo, empresa, area,
                estado_cuenta, debe_cambiar_password, activation_token, activation_token_expires_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                username,
                password_hash,
                rol,
                nombre,
                email,
                rut,
                telefono,
                cargo,
                empresa,
                area,
                estado_cuenta,
                debe_cambiar_password,
                activation_token,
                activation_token_expires_at,
            ),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def actualizar_perfil(username: str, nombre: str, telefono: str = "", cargo: str = "") -> None:
    conn = _connect()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE users SET nombre = %s, telefono = %s, cargo = %s WHERE username = %s",
            (nombre, telefono, cargo, username),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def actualizar_password(username: str, new_password_hash: str) -> None:
    conn = _connect()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE users SET password_hash = %s, debe_cambiar_password = FALSE WHERE username = %s",
            (new_password_hash, username),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def actualizar_rol(username: str, rol: str) -> None:
    conn = _connect()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE users SET rol = %s WHERE username = %s",
            (rol, username),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def actualizar_estado_cuenta(username: str, estado: str) -> None:
    conn = _connect()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE users SET estado_cuenta = %s WHERE username = %s", (estado, username))
        conn.commit()
    finally:
        cur.close()
        conn.close()


def actualizar_foto_perfil(username: str, foto_perfil: str) -> None:
    conn = _connect()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE users SET foto_perfil = %s WHERE username = %s", (foto_perfil, username))
        conn.commit()
    finally:
        cur.close()
        conn.close()


def guardar_activation_token(username: str, token: str, expires_at: datetime) -> None:
    conn = _connect()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE users
            SET activation_token = %s, activation_token_expires_at = %s,
                estado_cuenta = 'pendiente', debe_cambiar_password = TRUE
            WHERE username = %s
            """,
            (token, expires_at, username),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def obtener_usuario_por_activation_token(token: str) -> dict[str, Any] | None:
    conn = _connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT " + _USER_COLUMNS + " FROM users WHERE activation_token = %s", (token,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        cur.close()
        conn.close()


def activar_usuario(username: str, password_hash: str) -> None:
    conn = _connect()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE users
            SET password_hash = %s, estado_cuenta = 'activo', debe_cambiar_password = FALSE,
                activation_token = '', activation_token_expires_at = NULL
            WHERE username = %s
            """,
            (password_hash, username),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def guardar_reset_token(username: str, token: str, expires_at: datetime) -> None:
    conn = _connect()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE users SET reset_token = %s, reset_token_expires_at = %s WHERE username = %s",
            (token, expires_at, username),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def obtener_usuario_por_reset_token(token: str) -> dict[str, Any] | None:
    conn = _connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT " + _USER_COLUMNS + " FROM users WHERE reset_token = %s", (token,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        cur.close()
        conn.close()


def resetear_password(username: str, password_hash: str) -> None:
    conn = _connect()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE users
            SET password_hash = %s, reset_token = '', reset_token_expires_at = NULL,
                debe_cambiar_password = FALSE
            WHERE username = %s
            """,
            (password_hash, username),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()
