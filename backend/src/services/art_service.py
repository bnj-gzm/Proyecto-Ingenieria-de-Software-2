from __future__ import annotations

from typing import Any

from psycopg2.extras import RealDictCursor

from backend.src.config.database import _connect, _dump_json, _load_json_list

_SELECT = """
    SELECT id, empresa, trabajador, area, fecha, tipo_tarea, descripcion,
           supervisor, checklist_json, epp_json, riesgos_json,
           observaciones, evidencia_json, creado_en, estado
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
                observaciones, evidencia_json, creado_en, estado
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
        conn.commit()
    finally:
        cur.close()
        conn.close()


def actualizar_estado_art(id_art: str, estado: str) -> None:
    conn = _connect()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE art_records SET estado = %s WHERE id = %s",
            (estado, id_art),
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
