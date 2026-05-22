from __future__ import annotations

from typing import Any

from psycopg2.extras import RealDictCursor

from backend.src.config.database import _connect, _dump_json, _load_json_list

_SELECT = """
    SELECT id, empresa, trabajador, area, fecha, tipo_tarea, descripcion,
           supervisor, checklist_json, epp_json, riesgos_json,
           observaciones, evidencia_json, creado_en, estado, creado_por,
           asignado_a, supervisor_asignado, comentario_supervisor, revisado_por, revisado_en
    FROM art_records
"""


def _deserialize(row: dict) -> dict:
    row["checklist"] = _load_json_list(row.pop("checklist_json"))
    row["epp"] = _load_json_list(row.pop("epp_json"))
    row["riesgos"] = _load_json_list(row.pop("riesgos_json"))
    row["evidencia"] = _load_json_list(row.pop("evidencia_json"))
    return row


def cargar_registros() -> list[dict[str, Any]]:
    conn = _connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(_SELECT + "ORDER BY creado_en DESC, id DESC")
        return [_deserialize(dict(row)) for row in cur.fetchall()]
    finally:
        cur.close()
        conn.close()


def cargar_registros_por_usuario(username: str) -> list[dict[str, Any]]:
    conn = _connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            _SELECT + "WHERE creado_por = %s OR asignado_a = %s ORDER BY creado_en DESC, id DESC",
            (username, username),
        )
        return [_deserialize(dict(row)) for row in cur.fetchall()]
    finally:
        cur.close()
        conn.close()


def cargar_registros_por_supervisor(username: str) -> list[dict[str, Any]]:
    conn = _connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(_SELECT + "WHERE supervisor_asignado = %s ORDER BY creado_en DESC, id DESC", (username,))
        return [_deserialize(dict(row)) for row in cur.fetchall()]
    finally:
        cur.close()
        conn.close()


def obtener_registro(id_art: str) -> dict[str, Any] | None:
    conn = _connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(_SELECT + "WHERE id = %s", (id_art,))
        row = cur.fetchone()
        return _deserialize(dict(row)) if row else None
    finally:
        cur.close()
        conn.close()


def guardar_registro(registro: dict[str, Any]) -> None:
    conn = _connect()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO art_records (
                id, empresa, trabajador, area, fecha, tipo_tarea, descripcion,
                supervisor, checklist_json, epp_json, riesgos_json,
                observaciones, evidencia_json, creado_en, estado, creado_por,
                asignado_a, supervisor_asignado, comentario_supervisor, revisado_por, revisado_en
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                registro.get("creado_por", ""),
                registro.get("asignado_a", ""),
                registro.get("supervisor_asignado", ""),
                registro.get("comentario_supervisor", ""),
                registro.get("revisado_por", ""),
                registro.get("revisado_en", ""),
            ),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def actualizar_revision_art(id_art: str, estado: str, comentario: str, revisado_por: str, revisado_en: str) -> None:
    conn = _connect()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE art_records
            SET estado = %s, comentario_supervisor = %s, revisado_por = %s, revisado_en = %s
            WHERE id = %s
            """,
            (estado, comentario, revisado_por, revisado_en, id_art),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def contar_art_pendientes() -> int:
    conn = _connect()
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM art_records WHERE estado = %s", ("pendiente",))
        return cur.fetchone()[0]
    finally:
        cur.close()
        conn.close()

def eliminar_registro(id_art: str) -> None:
    conn = _connect()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM art_records WHERE id = %s", (id_art,))
        conn.commit()
    finally:
        cur.close()
        conn.close()
