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
            "SELECT id, username, password_hash, rol, nombre, email, created_at FROM users WHERE username = %s",
            (username,),
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
            "SELECT id, username, password_hash, rol, nombre, email, created_at FROM users ORDER BY id ASC"
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        cur.close()
        conn.close()


def guardar_usuario(username: str, password_hash: str, rol: str) -> None:
    conn = _connect()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO users (username, password_hash, rol, nombre, email) VALUES (%s, %s, %s, %s, %s)",
            (username, password_hash, rol, "", ""),
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
