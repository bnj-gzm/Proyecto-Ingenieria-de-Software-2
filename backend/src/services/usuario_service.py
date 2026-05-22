from __future__ import annotations

from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

from backend.src.config.database import _connect


def obtener_usuario(username: str) -> dict[str, Any] | None:
    conn = _connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
                 SELECT id, username, password_hash, rol, nombre, email, rut, telefono,
                     cargo, empresa, area, created_at
            FROM users WHERE username = %s
            """,
            (username,),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        cur.close()
        conn.close()


def obtener_usuario_por_email(email: str) -> dict[str, Any] | None:
    conn = _connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
                 SELECT id, username, password_hash, rol, nombre, email, rut, telefono,
                     cargo, empresa, area, created_at
            FROM users WHERE lower(email) = lower(%s)
            """,
            (email,),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        cur.close()
        conn.close()


def cargar_usuarios() -> list[dict[str, Any]]:
    conn = _connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
                 SELECT id, username, password_hash, rol, nombre, email, rut, telefono,
                     cargo, empresa, area, created_at
            FROM users ORDER BY id ASC
            """
        )
        return [dict(row) for row in cur.fetchall()]
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


def cargar_usuarios_por_rol(rol: str) -> list[dict[str, Any]]:
    conn = _connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            SELECT id, username, rol, nombre, email, rut, telefono, cargo, empresa, area, created_at
            FROM users WHERE rol = %s ORDER BY nombre ASC, username ASC
            """,
            (rol,),
        )
        return [dict(row) for row in cur.fetchall()]
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
) -> None:
    conn = _connect()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO users (
                username, password_hash, rol, nombre, email, rut, telefono, cargo, empresa, area
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (username, password_hash, rol, nombre, email, rut, telefono, cargo, empresa, area),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def actualizar_perfil(username: str, nombre: str, email: str) -> None:
    conn = _connect()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE users SET nombre = %s, email = %s WHERE username = %s",
            (nombre, email, username),
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
            "UPDATE users SET password_hash = %s WHERE username = %s",
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
