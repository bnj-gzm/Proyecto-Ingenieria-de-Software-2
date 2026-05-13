from __future__ import annotations

import json
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from pathlib import Path
from typing import Any
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Connection string from environment variable
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://neondb_owner:npg_PFNcgyuH3Wj8@ep-nameless-leaf-apj3nj50-pooler.c-7.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require",
)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
ART_JSON_FILE = DATA_DIR / "art_records.json"
USERS_JSON_FILE = DATA_DIR / "usuarios.json"


def _connect() -> psycopg2.extensions.connection:
    """Create and return a PostgreSQL connection."""
    return psycopg2.connect(DATABASE_URL)


def _load_json_file(file_path: Path) -> list[dict[str, Any]]:
    if not file_path.exists():
        return []
    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def _dump_json(value: Any) -> str:
    return json.dumps(value if value is not None else [], ensure_ascii=False)


def _load_json_list(value: Any) -> list[Any]:
    if not value:
        return []
    if isinstance(value, list):
        return value
    try:
        parsed_value = json.loads(value)
        return parsed_value if isinstance(parsed_value, list) else []
    except json.JSONDecodeError:
        return []


def _load_json_dict(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        parsed_value = json.loads(value)
        return parsed_value if isinstance(parsed_value, dict) else {}
    except json.JSONDecodeError:
        return {}


def init_db() -> None:
    """Initialize database tables and migrate from JSON files if needed."""
    connection = _connect()
    cursor = connection.cursor()

    try:
        # Create users table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                rol TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Create art_records table
        cursor.execute(
            """
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
            """
        )

        # Ensure new columns exist (safe for upgrades)
        cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS nombre TEXT DEFAULT ''")
        cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS email TEXT DEFAULT ''")
        cursor.execute("ALTER TABLE art_records ADD COLUMN IF NOT EXISTS estado TEXT DEFAULT 'pendiente'")

        # Migrate from JSON files if tables are empty
        cursor.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]
        if user_count == 0:
            for user in _load_json_file(USERS_JSON_FILE):
                username = user.get("username")
                password = user.get("password")
                rol = user.get("rol", "user")
                if username and password:
                    try:
                        cursor.execute(
                            "INSERT INTO users (username, password_hash, rol) VALUES (%s, %s, %s)",
                            (username, password, rol),
                        )
                    except psycopg2.errors.UniqueViolation:
                        connection.rollback()
                        continue

        cursor.execute("SELECT COUNT(*) FROM art_records")
        art_count = cursor.fetchone()[0]
        if art_count == 0:
            for record in _load_json_file(ART_JSON_FILE):
                record_id = record.get("id")
                if not record_id:
                    continue
                try:
                    cursor.execute(
                        """
                        INSERT INTO art_records (
                            id, empresa, trabajador, area, fecha, tipo_tarea, descripcion,
                            supervisor, checklist_json, epp_json, riesgos_json,
                            observaciones, evidencia_json, creado_en, estado
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            record_id,
                            record.get("empresa", ""),
                            record.get("trabajador", ""),
                            record.get("area", ""),
                            record.get("fecha", ""),
                            record.get("tipo_tarea", ""),
                            record.get("descripcion", ""),
                            record.get("supervisor", ""),
                            _dump_json(record.get("checklist", [])),
                            _dump_json(record.get("epp", [])),
                            _dump_json(record.get("riesgos", [])),
                            record.get("observaciones", ""),
                            _dump_json(record.get("evidencia", [])),
                            record.get("creado_en", ""),
                            record.get("estado", "pendiente"),
                        ),
                    )
                except psycopg2.errors.UniqueViolation:
                    connection.rollback()
                    continue

        connection.commit()
    finally:
        cursor.close()
        connection.close()


def cargar_usuarios() -> list[dict[str, Any]]:
    """Load all users from the database."""
    connection = _connect()
    cursor = connection.cursor(cursor_factory=RealDictCursor)

    try:
        cursor.execute(
            "SELECT id, username, password_hash, rol, nombre, email, created_at FROM users ORDER BY id ASC"
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        cursor.close()
        connection.close()


def obtener_usuario(username: str) -> dict[str, Any] | None:
    """Get a user by username."""
    connection = _connect()
    cursor = connection.cursor(cursor_factory=RealDictCursor)

    try:
        cursor.execute(
            "SELECT id, username, password_hash, rol, nombre, email, created_at FROM users WHERE username = %s",
            (username,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        cursor.close()
        connection.close()


def guardar_usuario(username: str, password_hash: str, rol: str) -> None:
    """Save a new user to the database."""
    connection = _connect()
    cursor = connection.cursor()

    try:
        cursor.execute(
            "INSERT INTO users (username, password_hash, rol, nombre, email) VALUES (%s, %s, %s, %s, %s)",
            (username, password_hash, rol, '', ''),
        )
        connection.commit()
    finally:
        cursor.close()
        connection.close()


def actualizar_password(username: str, new_password_hash: str) -> None:
    """Update an existing user's password hash."""
    connection = _connect()
    cursor = connection.cursor()

    try:
        cursor.execute(
            "UPDATE users SET password_hash = %s WHERE username = %s",
            (new_password_hash, username),
        )
        connection.commit()
    finally:
        cursor.close()
        connection.close()


def cargar_registros() -> list[dict[str, Any]]:
    """Load all ART/AST records from the database."""
    connection = _connect()
    cursor = connection.cursor(cursor_factory=RealDictCursor)

    try:
        cursor.execute(
            """
            SELECT id, empresa, trabajador, area, fecha, tipo_tarea, descripcion,
                   supervisor, checklist_json, epp_json, riesgos_json,
                   observaciones, evidencia_json, creado_en, estado
            FROM art_records
            ORDER BY creado_en DESC, id DESC
            """
        )
        rows = cursor.fetchall()

        registros: list[dict[str, Any]] = []
        for row in rows:
            registro = dict(row)
            registro["checklist"] = _load_json_list(registro.pop("checklist_json"))
            registro["epp"] = _load_json_list(registro.pop("epp_json"))
            registro["riesgos"] = _load_json_list(registro.pop("riesgos_json"))
            registro["evidencia"] = _load_json_list(registro.pop("evidencia_json"))
            registros.append(registro)
        return registros
    finally:
        cursor.close()
        connection.close()


def obtener_registro(id_art: str) -> dict[str, Any] | None:
    """Get a specific ART/AST record by ID."""
    connection = _connect()
    cursor = connection.cursor(cursor_factory=RealDictCursor)

    try:
        cursor.execute(
            """
            SELECT id, empresa, trabajador, area, fecha, tipo_tarea, descripcion,
                   supervisor, checklist_json, epp_json, riesgos_json,
                   observaciones, evidencia_json, creado_en, estado
            FROM art_records
            WHERE id = %s
            """,
            (id_art,),
        )
        row = cursor.fetchone()

        if not row:
            return None

        registro = dict(row)
        registro["checklist"] = _load_json_list(registro.pop("checklist_json"))
        registro["epp"] = _load_json_list(registro.pop("epp_json"))
        registro["riesgos"] = _load_json_list(registro.pop("riesgos_json"))
        registro["evidencia"] = _load_json_list(registro.pop("evidencia_json"))
        return registro
    finally:
        cursor.close()
        connection.close()


def guardar_registro(registro: dict[str, Any]) -> None:
    """Save a new ART/AST record to the database."""
    connection = _connect()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO art_records (
                id, empresa, trabajador, area, fecha, tipo_tarea, descripcion,
                supervisor, checklist_json, epp_json, riesgos_json,
                observaciones, evidencia_json, creado_en, estado
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                registro["id"],
                registro["empresa"],
                registro["trabajador"],
                registro["area"],
                registro["fecha"],
                registro["tipo_tarea"],
                registro["descripcion"],
                registro["supervisor"],
                _dump_json(registro.get("checklist", [])),
                _dump_json(registro.get("epp", [])),
                _dump_json(registro.get("riesgos", [])),
                registro.get("observaciones", ""),
                _dump_json(registro.get("evidencia", [])),
                registro["creado_en"],
                registro.get("estado", "pendiente"),
            ),
        )
        connection.commit()
    finally:
        cursor.close()
        connection.close()


def actualizar_perfil(username: str, nombre: str, email: str) -> None:
    """Update name and email for a user."""
    connection = _connect()
    cursor = connection.cursor()

    try:
        cursor.execute(
            "UPDATE users SET nombre = %s, email = %s WHERE username = %s",
            (nombre, email, username),
        )
        connection.commit()
    finally:
        cursor.close()
        connection.close()


def actualizar_estado_art(id_art: str, estado: str) -> None:
    """Set estado for an ART record."""
    connection = _connect()
    cursor = connection.cursor()

    try:
        cursor.execute(
            "UPDATE art_records SET estado = %s WHERE id = %s",
            (estado, id_art),
        )
        connection.commit()
    finally:
        cursor.close()
        connection.close()


def contar_art_pendientes() -> int:
    """Return count of art_records with estado = 'pendiente'."""
    connection = _connect()
    cursor = connection.cursor()

    try:
        cursor.execute("SELECT COUNT(*) FROM art_records WHERE estado = %s", ("pendiente",))
        return cursor.fetchone()[0]
    finally:
        cursor.close()
        connection.close()


init_db()
