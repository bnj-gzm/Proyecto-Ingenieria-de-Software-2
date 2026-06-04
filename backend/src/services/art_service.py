from __future__ import annotations

from pathlib import Path
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


def _normalize_evidence_path(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, dict):
        value = value.get("src") or value.get("data_uri") or value.get("path") or value.get("filename") or ""
    path = str(value).replace("\\", "/").strip()
    if path.startswith("data:") or path.startswith("http://") or path.startswith("https://"):
        return path
    if path.startswith("/static/"):
        path = path[len("/static/"):]
    if path.startswith("static/"):
        path = path[len("static/"):]
    marker = "/uploads/"
    if marker in path:
        path = "uploads/" + path.split(marker, 1)[1]
    if path.startswith("uploads/"):
        return f"/static/{path}"
    if "/" in path or ":" in path:
        return f"/static/uploads/art/{Path(path).name}"
    return f"/static/uploads/{path}"


def _normalize_evidence_item(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    if isinstance(value, dict):
        filename = str(value.get("filename") or value.get("name") or "evidencia").strip() or "evidencia"
        mime_type = str(value.get("mime_type") or value.get("content_type") or "image/jpeg").strip() or "image/jpeg"
        data = str(value.get("data") or value.get("base64") or "").strip()
        src = str(value.get("src") or value.get("data_uri") or "").strip()
        if not src and data:
            src = f"data:{mime_type};base64,{data}"
        if not src:
            src = _normalize_evidence_path(value)
        return {
            "filename": filename,
            "mime_type": mime_type,
            "data": data,
            "src": src,
        }
    src = _normalize_evidence_path(value)
    filename = Path(str(value)).name or "evidencia"
    return {
        "filename": filename,
        "mime_type": "image/jpeg",
        "data": "",
        "src": src,
    }


def _normalize_evidence_list(values: list[Any]) -> list[dict[str, Any]]:
    return [item for item in (_normalize_evidence_item(value) for value in values) if item.get("src")]


def _deserialize(row: dict) -> dict:
    row["checklist"] = _load_json_list(row.pop("checklist_json"))
    row["epp"] = _load_json_list(row.pop("epp_json"))
    row["riesgos"] = _load_json_list(row.pop("riesgos_json"))
    row["evidencia"] = _normalize_evidence_list(_load_json_list(row.pop("evidencia_json")))
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


def actualizar_registro(id_art: str, registro: dict[str, Any]) -> None:
    conn = _connect()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE art_records SET
                empresa = %s,
                trabajador = %s,
                area = %s,
                fecha = %s,
                tipo_tarea = %s,
                descripcion = %s,
                supervisor = %s,
                checklist_json = %s,
                epp_json = %s,
                riesgos_json = %s,
                observaciones = %s,
                evidencia_json = %s,
                asignado_a = %s,
                supervisor_asignado = %s
            WHERE id = %s
            """,
            (
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
                registro.get("asignado_a", ""),
                registro.get("supervisor_asignado", ""),
                id_art,
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


def contar_art_pendientes_por_supervisor(username: str) -> int:
    conn = _connect()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT COUNT(*) FROM art_records WHERE estado = %s AND supervisor_asignado = %s",
            ("pendiente", username),
        )
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
