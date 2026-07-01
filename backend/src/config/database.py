from __future__ import annotations

import json
import logging
import os
import psycopg2
from psycopg2 import extensions, pool
from typing import Any

from backend.src.config.settings import settings

DATABASE_URL = settings.database_url
SCHEMA_VERSION = "2026_06_art_formato_oficial_v2"
logger = logging.getLogger("dart")

_CONNECTION_POOL: pool.ThreadedConnectionPool | None = None


class _PooledConnection:
    def __init__(self, conn: psycopg2.extensions.connection, owner: pool.ThreadedConnectionPool):
        self._conn = conn
        self._owner = owner
        self._closed = False

    def __getattr__(self, name: str):
        return getattr(self._conn, name)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type:
            self.rollback()
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        discard = bool(getattr(self._conn, "closed", False))
        try:
            if not discard and self._conn.status != extensions.STATUS_READY:
                self._conn.rollback()
        except psycopg2.Error:
            discard = True
        self._owner.putconn(self._conn, close=discard)


def _get_pool() -> pool.ThreadedConnectionPool:
    global _CONNECTION_POOL
    if _CONNECTION_POOL is None:
        max_connections = max(1, int(os.getenv("DB_POOL_MAX", "5")))
        _CONNECTION_POOL = pool.ThreadedConnectionPool(
            1,
            max_connections,
            DATABASE_URL,
            connect_timeout=int(os.getenv("DB_CONNECT_TIMEOUT", "10")),
            keepalives=1,
            keepalives_idle=30,
            keepalives_interval=10,
            keepalives_count=5,
            application_name=os.getenv("DB_APPLICATION_NAME", "dart-railway"),
        )
    return _CONNECTION_POOL


def _ensure_connection_alive(conn: psycopg2.extensions.connection) -> None:
    cur = conn.cursor()
    try:
        cur.execute("SELECT 1")
        cur.fetchone()
        conn.rollback()
    finally:
        cur.close()


def _connect():
    if os.getenv("DB_POOL_DISABLED", "").lower() in {"1", "true", "yes"}:
        return psycopg2.connect(
            DATABASE_URL,
            connect_timeout=int(os.getenv("DB_CONNECT_TIMEOUT", "10")),
            keepalives=1,
            keepalives_idle=30,
            keepalives_interval=10,
            keepalives_count=5,
            application_name=os.getenv("DB_APPLICATION_NAME", "dart-railway"),
        )
    db_pool = _get_pool()
    conn = db_pool.getconn()
    try:
        _ensure_connection_alive(conn)
    except psycopg2.Error:
        logger.warning("db_pool_connection_stale discarded=true", exc_info=True)
        db_pool.putconn(conn, close=True)
        conn = db_pool.getconn()
        _ensure_connection_alive(conn)
    return _PooledConnection(conn, db_pool)


def _raw_connect() -> psycopg2.extensions.connection:
    return psycopg2.connect(
        DATABASE_URL,
        connect_timeout=int(os.getenv("DB_CONNECT_TIMEOUT", "10")),
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
        application_name=os.getenv("DB_APPLICATION_NAME", "dart-railway"),
    )


def _dump_json(value: Any) -> str:
    return json.dumps(value if value is not None else [], ensure_ascii=False)


def _load_json_list(value: Any) -> list[Any]:
    if not value:
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return []


def _load_json_dict(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def init_db() -> None:
    conn = _connect()
    cur = conn.cursor()
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                rol TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS support_tickets (
                id UUID PRIMARY KEY,
                user_id INTEGER NULL REFERENCES users(id) ON DELETE SET NULL,
                email TEXT NOT NULL,
                type TEXT NOT NULL CHECK (type IN ('bug', 'error', 'mejora', 'otro')),
                message TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'in_progress', 'resolved')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_support_tickets_status_created ON support_tickets (status, created_at DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_support_tickets_user_type_created ON support_tickets (user_id, type, created_at DESC)")
        cur.execute("ALTER TABLE support_tickets ADD COLUMN IF NOT EXISTS contact_name TEXT")
        cur.execute("ALTER TABLE support_tickets ADD COLUMN IF NOT EXISTS subject TEXT")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS apellido TEXT DEFAULT ''")
        cur.execute(
            """
            UPDATE users
            SET apellido = INITCAP(REPLACE(SUBSTRING(username FROM POSITION('.' IN username) + 1), '.', ' '))
            WHERE COALESCE(apellido, '') = ''
              AND COALESCE(nombre, '') <> ''
              AND nombre !~ '\\s'
              AND username LIKE '%.%'
              AND POSITION('.' IN username) > 1
              AND LENGTH(SUBSTRING(username FROM POSITION('.' IN username) + 1)) > 1
            """
        )
        cur.execute("SELECT 1 FROM schema_migrations WHERE version = %s", (SCHEMA_VERSION,))
        if cur.fetchone():
            conn.commit()
            logger.info("Schema %s ya aplicado; se omite init_db completo.", SCHEMA_VERSION)
            return
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                rol TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS art_records (
                id TEXT PRIMARY KEY,
                empresa TEXT NOT NULL,
                trabajador TEXT NOT NULL,
                area TEXT NOT NULL,
                fecha TEXT NOT NULL,
                tipo_tarea TEXT NOT NULL,
                descripcion TEXT NOT NULL,
                supervisor TEXT NOT NULL,
                checklist_json TEXT NOT NULL DEFAULT '[]',
                epp_json TEXT NOT NULL DEFAULT '[]',
                riesgos_json TEXT NOT NULL DEFAULT '[]',
                observaciones TEXT NOT NULL DEFAULT '',
                evidencia_json TEXT NOT NULL DEFAULT '[]',
                creado_en TEXT NOT NULL,
                creado_por TEXT NOT NULL DEFAULT ''
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS art_trabajadores (
                id SERIAL PRIMARY KEY,
                art_id TEXT NOT NULL REFERENCES art_records(id) ON DELETE CASCADE,
                username TEXT NOT NULL,
                nombre TEXT NOT NULL DEFAULT '',
                cargo TEXT NOT NULL DEFAULT '',
                condicion_ok BOOLEAN NULL,
                validado_en TEXT NOT NULL DEFAULT '',
                observacion TEXT NOT NULL DEFAULT '',
                UNIQUE (art_id, username)
            )
        """)
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS nombre TEXT DEFAULT ''")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS email TEXT DEFAULT ''")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS rut VARCHAR(12) DEFAULT ''")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS telefono TEXT DEFAULT ''")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS cargo TEXT DEFAULT ''")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS empresa TEXT DEFAULT ''")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS area TEXT DEFAULT ''")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS estado_cuenta TEXT DEFAULT 'activo'")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS debe_cambiar_password BOOLEAN DEFAULT FALSE")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS activation_token TEXT DEFAULT ''")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS activation_token_expires_at TIMESTAMP NULL")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_token TEXT DEFAULT ''")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_token_expires_at TIMESTAMP NULL")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS foto_perfil TEXT DEFAULT ''")
        cur.execute("UPDATE users SET rol = 'trabajador' WHERE rol = 'user'")
        cur.execute("UPDATE users SET estado_cuenta = 'activo' WHERE estado_cuenta IS NULL OR estado_cuenta = ''")
        cur.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM users
                    WHERE email IS NOT NULL AND email <> ''
                    GROUP BY lower(email)
                    HAVING count(*) > 1
                ) THEN
                    CREATE UNIQUE INDEX IF NOT EXISTS users_email_unique_idx
                    ON users (lower(email))
                    WHERE email IS NOT NULL AND email <> '';
                END IF;
            END $$;
        """)
        cur.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM users
                    WHERE rut IS NOT NULL AND rut <> ''
                    GROUP BY rut
                    HAVING count(*) > 1
                ) THEN
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_rut_unique
                    ON users (rut)
                    WHERE rut IS NOT NULL AND rut <> '';
                END IF;
            END $$;
        """)
        cur.execute("ALTER TABLE art_records ADD COLUMN IF NOT EXISTS estado TEXT DEFAULT 'pendiente'")
        cur.execute("ALTER TABLE art_records ADD COLUMN IF NOT EXISTS creado_por TEXT DEFAULT ''")
        cur.execute("ALTER TABLE art_records ADD COLUMN IF NOT EXISTS asignado_a TEXT DEFAULT ''")
        cur.execute("ALTER TABLE art_records ADD COLUMN IF NOT EXISTS supervisor_asignado TEXT DEFAULT ''")
        cur.execute("ALTER TABLE art_records ADD COLUMN IF NOT EXISTS comentario_supervisor TEXT DEFAULT ''")
        cur.execute("ALTER TABLE art_records ADD COLUMN IF NOT EXISTS revisado_por TEXT DEFAULT ''")
        cur.execute("ALTER TABLE art_records ADD COLUMN IF NOT EXISTS revisado_en TEXT DEFAULT ''")
        cur.execute("ALTER TABLE art_records ADD COLUMN IF NOT EXISTS gerencia TEXT DEFAULT ''")
        cur.execute("ALTER TABLE art_records ADD COLUMN IF NOT EXISTS hora_inicio TEXT DEFAULT ''")
        cur.execute("ALTER TABLE art_records ADD COLUMN IF NOT EXISTS hora_termino TEXT DEFAULT ''")
        cur.execute("ALTER TABLE art_records ADD COLUMN IF NOT EXISTS lugar TEXT DEFAULT ''")
        cur.execute("ALTER TABLE art_records ADD COLUMN IF NOT EXISTS reglas_vida_json TEXT DEFAULT '[]'")
        cur.execute("ALTER TABLE art_records ADD COLUMN IF NOT EXISTS supervisor_condiciones_json TEXT DEFAULT '[]'")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS art_trabajadores_asignados (
                id SERIAL PRIMARY KEY,
                art_id TEXT NOT NULL REFERENCES art_records(id) ON DELETE CASCADE,
                trabajador_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                email TEXT NOT NULL DEFAULT '',
                nombre TEXT NOT NULL DEFAULT '',
                rut TEXT NOT NULL DEFAULT '',
                cargo TEXT NOT NULL DEFAULT '',
                area TEXT NOT NULL DEFAULT '',
                telefono TEXT NOT NULL DEFAULT '',
                token_acceso TEXT NOT NULL UNIQUE,
                token_expires_at TIMESTAMP NULL,
                estado_envio TEXT NOT NULL DEFAULT 'pendiente',
                estado_respuesta TEXT NOT NULL DEFAULT 'pendiente',
                fecha_envio TIMESTAMP NULL,
                fecha_respuesta TIMESTAMP NULL,
                respuestas_json TEXT NOT NULL DEFAULT '{}',
                evidencia_trabajador_json TEXT NOT NULL DEFAULT '[]',
                firma_tipo TEXT NOT NULL DEFAULT '',
                firma_valor TEXT NOT NULL DEFAULT '',
                firma_imagen_path TEXT NOT NULL DEFAULT '',
                firma_imagen_base64 TEXT NOT NULL DEFAULT '',
                documento_firma TEXT NOT NULL DEFAULT '',
                comentario_revision TEXT NOT NULL DEFAULT '',
                fecha_revision TIMESTAMP NULL,
                supervisor_revisor_id INTEGER NULL REFERENCES users(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (art_id, trabajador_id)
            )
        """)
        cur.execute("ALTER TABLE art_trabajadores_asignados ADD COLUMN IF NOT EXISTS rut TEXT DEFAULT ''")
        cur.execute("ALTER TABLE art_trabajadores_asignados ADD COLUMN IF NOT EXISTS telefono TEXT DEFAULT ''")
        cur.execute("ALTER TABLE art_trabajadores_asignados ADD COLUMN IF NOT EXISTS estado_envio TEXT DEFAULT 'pendiente'")
        cur.execute("ALTER TABLE art_trabajadores_asignados ADD COLUMN IF NOT EXISTS evidencia_trabajador_json TEXT DEFAULT '[]'")
        cur.execute("ALTER TABLE art_trabajadores_asignados ADD COLUMN IF NOT EXISTS comentario_revision TEXT DEFAULT ''")
        cur.execute("ALTER TABLE art_trabajadores_asignados ADD COLUMN IF NOT EXISTS fecha_revision TIMESTAMP NULL")
        cur.execute("ALTER TABLE art_trabajadores_asignados ADD COLUMN IF NOT EXISTS supervisor_revisor_id INTEGER NULL REFERENCES users(id)")
        cur.execute("UPDATE art_trabajadores_asignados SET estado_envio = 'envio_fallido', estado_respuesta = 'pendiente' WHERE estado_respuesta = 'fallido'")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_art_asignados_art_id ON art_trabajadores_asignados (art_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_art_asignados_trabajador_id ON art_trabajadores_asignados (trabajador_id)")
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_art_asignados_token ON art_trabajadores_asignados (token_acceso)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_art_records_creado_por ON art_records (creado_por)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_art_records_supervisor_asignado ON art_records (supervisor_asignado)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_art_records_estado ON art_records (estado)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_art_records_estado_supervisor ON art_records (estado, supervisor_asignado)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_art_records_creado_en_id ON art_records (creado_en DESC, id DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_art_records_supervisor_creado ON art_records (supervisor_asignado, creado_en DESC, id DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_art_records_creador_creado ON art_records (creado_por, creado_en DESC, id DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_art_trabajadores_art_id ON art_trabajadores (art_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_art_trabajadores_username ON art_trabajadores (username)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_art_trabajadores_username_art ON art_trabajadores (username, art_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_art_asignados_estado_respuesta ON art_trabajadores_asignados (estado_respuesta)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_art_asignados_trabajador_created ON art_trabajadores_asignados (trabajador_id, created_at DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_art_asignados_trabajador_art ON art_trabajadores_asignados (trabajador_id, art_id)")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS system_logs (
                id SERIAL PRIMARY KEY,
                event_type TEXT NOT NULL,
                username TEXT DEFAULT '',
                ip_address TEXT DEFAULT '',
                details TEXT DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_system_logs_event_type ON system_logs (event_type)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_system_logs_created_at ON system_logs (created_at DESC)")
        cur.execute(
            """
            INSERT INTO schema_migrations (version)
            VALUES (%s)
            ON CONFLICT (version) DO NOTHING
            """,
            (SCHEMA_VERSION,),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()
