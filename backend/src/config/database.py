from __future__ import annotations

import json
import psycopg2
from typing import Any

from backend.src.config.settings import settings

DATABASE_URL = settings.database_url


def _connect() -> psycopg2.extensions.connection:
    return psycopg2.connect(DATABASE_URL)


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
        conn.commit()
    finally:
        cur.close()
        conn.close()
