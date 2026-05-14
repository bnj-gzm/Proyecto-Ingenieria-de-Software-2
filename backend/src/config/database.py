from __future__ import annotations

import json
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from pathlib import Path
from typing import Any
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_ROOT / ".env")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://neondb_owner:npg_PFNcgyuH3Wj8@ep-nameless-leaf-apj3nj50-pooler.c-7.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require",
)


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
                creado_en TEXT NOT NULL
            )
        """)
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS nombre TEXT DEFAULT ''")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS email TEXT DEFAULT ''")
        cur.execute("ALTER TABLE art_records ADD COLUMN IF NOT EXISTS estado TEXT DEFAULT 'pendiente'")
        conn.commit()
    finally:
        cur.close()
        conn.close()
