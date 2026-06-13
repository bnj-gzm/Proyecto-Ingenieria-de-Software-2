from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any
from datetime import datetime, timedelta, timezone

from psycopg2.extras import RealDictCursor

from backend.src.config.database import _connect, _dump_json, _load_json_dict, _load_json_list

_SELECT = """
    SELECT id, empresa, trabajador, area, fecha, tipo_tarea, descripcion,
           supervisor, checklist_json, epp_json, riesgos_json,
           observaciones, evidencia_json, creado_en, estado, creado_por,
           asignado_a, supervisor_asignado, comentario_supervisor, revisado_por, revisado_en
    FROM art_records
"""

_LIST_SELECT = """
    SELECT id, empresa, trabajador, area, fecha, tipo_tarea, descripcion,
           supervisor, creado_en, estado, creado_por, asignado_a,
           supervisor_asignado, comentario_supervisor, revisado_por, revisado_en
    FROM art_records
"""

_EMPTY_ASSIGNMENT_SUMMARY = {
    "total": 0,
    "respondidos": 0,
    "revisados": 0,
    "enviados": 0,
    "pendientes": 0,
    "fallidos": 0,
    "firmas": 0,
    "con_observaciones": 0,
    "aprobados": 0,
    "evidencias": 0,
    "faltantes": 0,
}


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


def _deserialize_list(row: dict) -> dict:
    row["checklist"] = []
    row["epp"] = []
    row["riesgos"] = []
    row["evidencia"] = []
    row["observaciones"] = ""
    return row


def _deserialize_asignacion(row: dict) -> dict[str, Any]:
    row["respuestas"] = _load_json_dict(row.pop("respuestas_json", "{}"))
    row["evidencia_trabajador"] = _normalize_evidence_list(_load_json_list(row.pop("evidencia_trabajador_json", "[]")))
    if row.get("estado_respuesta") == "fallido":
        row["estado_envio"] = "envio_fallido"
        row["estado_respuesta"] = "pendiente"
    art_keys = {
        "art_empresa": "empresa",
        "art_area": "area",
        "art_fecha": "fecha",
        "art_tipo_tarea": "tipo_tarea",
        "art_descripcion": "descripcion",
        "art_supervisor": "supervisor",
        "art_estado": "estado",
    }
    art = {}
    for source, target in art_keys.items():
        if source in row:
            art[target] = row.pop(source)
    if art:
        art["id"] = row.get("art_id")
        row["art"] = art
    row["con_observacion"] = bool(
        row["respuestas"].get("con_observacion")
        or row["respuestas"].get("observaciones")
        or row["respuestas"].get("observaciones_por_pregunta")
    )
    return row


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _new_token() -> str:
    return secrets.token_urlsafe(32)


def _assignment_summary(asignaciones: list[dict[str, Any]]) -> dict[str, int]:
    total = len(asignaciones)
    response_done_states = {"respondido", "con_observacion", "aprobado", "rechazado"}
    reviewed_states = {"aprobado", "rechazado"}
    respondidos = sum(1 for item in asignaciones if item.get("estado_respuesta") in response_done_states)
    enviados = sum(1 for item in asignaciones if item.get("estado_envio") == "enviado")
    pendientes = sum(1 for item in asignaciones if item.get("estado_respuesta") == "pendiente")
    fallidos = sum(1 for item in asignaciones if item.get("estado_envio") == "envio_fallido")
    firmas = sum(1 for item in asignaciones if item.get("firma_valor") or item.get("firma_imagen_base64"))
    con_observaciones = sum(1 for item in asignaciones if item.get("con_observacion"))
    aprobados = sum(1 for item in asignaciones if item.get("estado_respuesta") == "aprobado")
    revisados = sum(1 for item in asignaciones if item.get("estado_respuesta") in reviewed_states)
    evidencias = sum(1 for item in asignaciones if item.get("evidencia_trabajador"))
    return {
        "total": total,
        "respondidos": respondidos,
        "revisados": revisados,
        "enviados": enviados,
        "pendientes": pendientes,
        "fallidos": fallidos,
        "firmas": firmas,
        "con_observaciones": con_observaciones,
        "aprobados": aprobados,
        "evidencias": evidencias,
        "faltantes": max(total - respondidos, 0),
    }


def cargar_resumenes_asignaciones(id_art_list: list[str]) -> dict[str, dict[str, int]]:
    ids = [id_art for id_art in dict.fromkeys(id_art_list) if id_art]
    if not ids:
        return {}
    conn = _connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            SELECT art_id,
                   COUNT(*)::int AS total,
                   COUNT(*) FILTER (
                       WHERE estado_respuesta IN ('respondido', 'con_observacion', 'aprobado', 'rechazado')
                   )::int AS respondidos,
                   COUNT(*) FILTER (
                       WHERE estado_respuesta IN ('aprobado', 'rechazado')
                   )::int AS revisados,
                   COUNT(*) FILTER (WHERE estado_respuesta = 'pendiente')::int AS pendientes,
                   COUNT(*) FILTER (WHERE estado_envio = 'enviado')::int AS enviados,
                   COUNT(*) FILTER (WHERE estado_envio = 'envio_fallido')::int AS fallidos
            FROM art_trabajadores_asignados
            WHERE art_id = ANY(%s)
            GROUP BY art_id
            """,
            (ids,),
        )
        resumenes = {row["art_id"]: dict(row) for row in cur.fetchall()}
        for id_art in ids:
            resumenes.setdefault(
                id_art,
                {
                    "art_id": id_art,
                    "total": 0,
                    "respondidos": 0,
                    "revisados": 0,
                    "pendientes": 0,
                    "enviados": 0,
                    "fallidos": 0,
                },
            )
        return resumenes
    finally:
        cur.close()
        conn.close()


def cargar_asignaciones_art(id_art: str) -> list[dict[str, Any]]:
    conn = _connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            SELECT ata.id, ata.art_id, ata.trabajador_id,
                   COALESCE(NULLIF(ata.email, ''), u.email, '') AS email,
                   COALESCE(NULLIF(ata.nombre, ''), u.nombre, u.username, '') AS nombre,
                   COALESCE(NULLIF(ata.rut, ''), u.rut, '') AS rut,
                   COALESCE(NULLIF(ata.cargo, ''), u.cargo, '') AS cargo,
                   COALESCE(NULLIF(ata.area, ''), u.area, '') AS area,
                   COALESCE(NULLIF(ata.telefono, ''), u.telefono, '') AS telefono,
                   u.username,
                   ata.token_acceso, ata.token_expires_at, ata.estado_envio, ata.estado_respuesta,
                   ata.fecha_envio, ata.fecha_respuesta, ata.respuestas_json, ata.evidencia_trabajador_json,
                   ata.firma_tipo, ata.firma_valor, ata.firma_imagen_path,
                   ata.firma_imagen_base64, ata.documento_firma, ata.comentario_revision,
                   ata.fecha_revision, ata.supervisor_revisor_id, ata.created_at, ata.updated_at
            FROM art_trabajadores_asignados ata
            LEFT JOIN users u ON u.id = ata.trabajador_id
            WHERE ata.art_id = %s
            ORDER BY nombre ASC, email ASC
            """,
            (id_art,),
        )
        return [_deserialize_asignacion(dict(row)) for row in cur.fetchall()]
    finally:
        cur.close()
        conn.close()


def guardar_asignaciones_art(id_art: str, trabajadores: list[dict[str, Any]]) -> None:
    conn = _connect()
    cur = conn.cursor()
    try:
        for trabajador in trabajadores:
            cur.execute(
                """
                INSERT INTO art_trabajadores_asignados (
                    art_id, trabajador_id, email, nombre, rut, cargo, area, telefono,
                    token_acceso, token_expires_at, estado_envio, estado_respuesta
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pendiente', 'pendiente')
                ON CONFLICT (art_id, trabajador_id) DO UPDATE SET
                    email = EXCLUDED.email,
                    nombre = EXCLUDED.nombre,
                    rut = EXCLUDED.rut,
                    cargo = EXCLUDED.cargo,
                    area = EXCLUDED.area,
                    telefono = EXCLUDED.telefono,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    id_art,
                    trabajador["id"],
                    trabajador.get("email", ""),
                    trabajador.get("nombre") or trabajador.get("username", ""),
                    trabajador.get("rut", ""),
                    trabajador.get("cargo", ""),
                    trabajador.get("area", ""),
                    trabajador.get("telefono", ""),
                    _new_token(),
                    _now() + timedelta(days=7),
                ),
            )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def preparar_envio_asignacion(id_asignacion: int) -> dict[str, Any] | None:
    conn = _connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        expires_at = _now() + timedelta(days=7)
        cur.execute(
            """
            UPDATE art_trabajadores_asignados
            SET token_acceso = CASE
                    WHEN token_acceso = '' OR token_expires_at IS NULL OR token_expires_at < CURRENT_TIMESTAMP
                    THEN %s ELSE token_acceso END,
                token_expires_at = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND estado_respuesta NOT IN ('respondido', 'con_observacion', 'aprobado', 'rechazado')
            RETURNING id, art_id, trabajador_id, email, nombre, rut, cargo, area, telefono, token_acceso,
                      token_expires_at, estado_envio, estado_respuesta, fecha_envio, fecha_respuesta,
                      respuestas_json, evidencia_trabajador_json, firma_tipo, firma_valor, firma_imagen_path,
                      firma_imagen_base64, documento_firma, comentario_revision,
                      fecha_revision, supervisor_revisor_id, created_at, updated_at
            """,
            (_new_token(), expires_at, id_asignacion),
        )
        row = cur.fetchone()
        conn.commit()
        return _deserialize_asignacion(dict(row)) if row else None
    finally:
        cur.close()
        conn.close()


def marcar_envio_asignacion(id_asignacion: int, estado_envio: bool | str) -> None:
    conn = _connect()
    cur = conn.cursor()
    try:
        if isinstance(estado_envio, bool):
            estado = "enviado" if estado_envio else "envio_fallido"
        else:
            estado = estado_envio
        cur.execute(
            """
            UPDATE art_trabajadores_asignados
            SET estado_envio = %s, fecha_envio = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND estado_respuesta NOT IN ('respondido', 'con_observacion', 'aprobado', 'rechazado')
            """,
            (estado, id_asignacion),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def obtener_asignacion_por_token(token: str) -> dict[str, Any] | None:
    conn = _connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            SELECT ata.id, ata.art_id, ata.trabajador_id,
                   COALESCE(NULLIF(ata.email, ''), u.email, '') AS email,
                   COALESCE(NULLIF(ata.nombre, ''), u.nombre, u.username, '') AS nombre,
                   COALESCE(NULLIF(ata.rut, ''), u.rut, '') AS rut,
                   COALESCE(NULLIF(ata.cargo, ''), u.cargo, '') AS cargo,
                   COALESCE(NULLIF(ata.area, ''), u.area, '') AS area,
                   COALESCE(NULLIF(ata.telefono, ''), u.telefono, '') AS telefono,
                   u.username,
                   ata.token_acceso, ata.token_expires_at, ata.estado_envio, ata.estado_respuesta,
                   ata.fecha_envio, ata.fecha_respuesta, ata.respuestas_json, ata.evidencia_trabajador_json,
                   ata.firma_tipo, ata.firma_valor, ata.firma_imagen_path,
                   ata.firma_imagen_base64, ata.documento_firma, ata.comentario_revision,
                   ata.fecha_revision, ata.supervisor_revisor_id, ata.created_at, ata.updated_at
            FROM art_trabajadores_asignados ata
            LEFT JOIN users u ON u.id = ata.trabajador_id
            WHERE ata.token_acceso = %s
            """,
            (token,),
        )
        row = cur.fetchone()
        return _deserialize_asignacion(dict(row)) if row else None
    finally:
        cur.close()
        conn.close()


def obtener_asignacion_art(id_art: str, id_asignacion: int) -> dict[str, Any] | None:
    conn = _connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            SELECT ata.id, ata.art_id, ata.trabajador_id,
                   COALESCE(NULLIF(ata.email, ''), u.email, '') AS email,
                   COALESCE(NULLIF(ata.nombre, ''), u.nombre, u.username, '') AS nombre,
                   COALESCE(NULLIF(ata.rut, ''), u.rut, '') AS rut,
                   COALESCE(NULLIF(ata.cargo, ''), u.cargo, '') AS cargo,
                   COALESCE(NULLIF(ata.area, ''), u.area, '') AS area,
                   COALESCE(NULLIF(ata.telefono, ''), u.telefono, '') AS telefono,
                   u.username,
                   ata.token_acceso, ata.token_expires_at, ata.estado_envio, ata.estado_respuesta,
                   ata.fecha_envio, ata.fecha_respuesta, ata.respuestas_json, ata.evidencia_trabajador_json,
                   ata.firma_tipo, ata.firma_valor, ata.firma_imagen_path,
                   ata.firma_imagen_base64, ata.documento_firma, ata.comentario_revision,
                   ata.fecha_revision, ata.supervisor_revisor_id, ata.created_at, ata.updated_at
            FROM art_trabajadores_asignados ata
            LEFT JOIN users u ON u.id = ata.trabajador_id
            WHERE ata.art_id = %s AND ata.id = %s
            """,
            (id_art, id_asignacion),
        )
        row = cur.fetchone()
        return _deserialize_asignacion(dict(row)) if row else None
    finally:
        cur.close()
        conn.close()


def cargar_asignaciones_por_trabajador(trabajador_id: int, limite: int = 20) -> list[dict[str, Any]]:
    conn = _connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            f"""
            SELECT ata.id, ata.art_id, ata.trabajador_id,
                   COALESCE(NULLIF(ata.email, ''), u.email, '') AS email,
                   COALESCE(NULLIF(ata.nombre, ''), u.nombre, u.username, '') AS nombre,
                   COALESCE(NULLIF(ata.rut, ''), u.rut, '') AS rut,
                   COALESCE(NULLIF(ata.cargo, ''), u.cargo, '') AS cargo,
                   COALESCE(NULLIF(ata.area, ''), u.area, '') AS area,
                   COALESCE(NULLIF(ata.telefono, ''), u.telefono, '') AS telefono,
                   u.username,
                   ata.token_acceso, ata.token_expires_at, ata.estado_envio, ata.estado_respuesta,
                   ata.fecha_envio, ata.fecha_respuesta,
                   ata.respuestas_json, ata.evidencia_trabajador_json,
                   ata.firma_tipo, ata.firma_valor, ata.firma_imagen_path,
                   ata.firma_imagen_base64, ata.documento_firma, ata.comentario_revision,
                   ata.fecha_revision, ata.supervisor_revisor_id, ata.created_at, ata.updated_at,
                   ar.empresa AS art_empresa, ar.area AS art_area, ar.fecha AS art_fecha,
                   ar.tipo_tarea AS art_tipo_tarea, ar.descripcion AS art_descripcion,
                   ar.supervisor AS art_supervisor, ar.estado AS art_estado
            FROM art_trabajadores_asignados ata
            JOIN art_records ar ON ar.id = ata.art_id
            LEFT JOIN users u ON u.id = ata.trabajador_id
            WHERE ata.trabajador_id = %s
            ORDER BY ar.fecha DESC, ata.created_at DESC
            LIMIT {limite}
            """,
            (trabajador_id,),
        )
        return [_deserialize_asignacion(dict(row)) for row in cur.fetchall()]
    finally:
        cur.close()
        conn.close()


def obtener_asignacion_para_trabajador(id_asignacion: int, trabajador_id: int) -> dict[str, Any] | None:
    conn = _connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            SELECT ata.id, ata.art_id, ata.trabajador_id,
                   COALESCE(NULLIF(ata.email, ''), u.email, '') AS email,
                   COALESCE(NULLIF(ata.nombre, ''), u.nombre, u.username, '') AS nombre,
                   COALESCE(NULLIF(ata.rut, ''), u.rut, '') AS rut,
                   COALESCE(NULLIF(ata.cargo, ''), u.cargo, '') AS cargo,
                   COALESCE(NULLIF(ata.area, ''), u.area, '') AS area,
                   COALESCE(NULLIF(ata.telefono, ''), u.telefono, '') AS telefono,
                   u.username,
                   ata.token_acceso, ata.token_expires_at, ata.estado_envio, ata.estado_respuesta,
                   ata.fecha_envio, ata.fecha_respuesta, ata.respuestas_json, ata.evidencia_trabajador_json,
                   ata.firma_tipo, ata.firma_valor, ata.firma_imagen_path,
                   ata.firma_imagen_base64, ata.documento_firma, ata.comentario_revision,
                   ata.fecha_revision, ata.supervisor_revisor_id, ata.created_at, ata.updated_at
            FROM art_trabajadores_asignados ata
            LEFT JOIN users u ON u.id = ata.trabajador_id
            WHERE ata.id = %s AND ata.trabajador_id = %s
            """,
            (id_asignacion, trabajador_id),
        )
        row = cur.fetchone()
        return _deserialize_asignacion(dict(row)) if row else None
    finally:
        cur.close()
        conn.close()


def guardar_respuesta_asignacion(
    token: str,
    respuestas: dict[str, Any],
    firma_tipo: str,
    firma_valor: str,
    firma_imagen_base64: str = "",
    evidencia_trabajador: list[dict[str, Any]] | None = None,
) -> None:
    conn = _connect()
    cur = conn.cursor()
    try:
        estado = "con_observacion" if respuestas.get("con_observacion") else "respondido"
        cur.execute(
            """
            UPDATE art_trabajadores_asignados
            SET estado_respuesta = %s,
                fecha_respuesta = CURRENT_TIMESTAMP,
                respuestas_json = %s,
                evidencia_trabajador_json = %s,
                firma_tipo = %s,
                firma_valor = %s,
                firma_imagen_base64 = %s,
                comentario_revision = '',
                fecha_revision = NULL,
                supervisor_revisor_id = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE token_acceso = %s
            """,
            (estado, _dump_json(respuestas), _dump_json(evidencia_trabajador or []), firma_tipo, firma_valor, firma_imagen_base64, token),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def guardar_respuesta_asignacion_por_id(
    id_asignacion: int,
    respuestas: dict[str, Any],
    firma_tipo: str,
    firma_valor: str,
    firma_imagen_base64: str = "",
    evidencia_trabajador: list[dict[str, Any]] | None = None,
) -> None:
    conn = _connect()
    cur = conn.cursor()
    try:
        estado = "con_observacion" if respuestas.get("con_observacion") else "respondido"
        cur.execute(
            """
            UPDATE art_trabajadores_asignados
            SET estado_respuesta = %s,
                fecha_respuesta = CURRENT_TIMESTAMP,
                respuestas_json = %s,
                evidencia_trabajador_json = %s,
                firma_tipo = %s,
                firma_valor = %s,
                firma_imagen_base64 = %s,
                comentario_revision = '',
                fecha_revision = NULL,
                supervisor_revisor_id = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (estado, _dump_json(respuestas), _dump_json(evidencia_trabajador or []), firma_tipo, firma_valor, firma_imagen_base64, id_asignacion),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def actualizar_revision_asignacion(id_asignacion: int, estado: str, comentario: str, supervisor_revisor_id: int) -> None:
    conn = _connect()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE art_trabajadores_asignados
            SET estado_respuesta = %s,
                comentario_revision = %s,
                fecha_revision = CURRENT_TIMESTAMP,
                supervisor_revisor_id = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND estado_respuesta IN ('respondido', 'con_observacion')
            """,
            (estado, comentario, supervisor_revisor_id, id_asignacion),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def cargar_registros(limite: int = 50, con_asignaciones: bool = True) -> list[dict[str, Any]]:
    conn = _connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        select = _SELECT if con_asignaciones else _LIST_SELECT
        deserializer = _deserialize if con_asignaciones else _deserialize_list
        query = select + f"ORDER BY creado_en DESC, id DESC LIMIT {limite}"
        cur.execute(query)
        registros = [deserializer(dict(row)) for row in cur.fetchall()]
        if con_asignaciones:
            for registro in registros:
                registro["asignaciones"] = cargar_asignaciones_art(registro["id"])
                registro["progreso_asignaciones"] = _assignment_summary(registro["asignaciones"])
        else:
            for registro in registros:
                registro["asignaciones"] = []
                registro["progreso_asignaciones"] = _EMPTY_ASSIGNMENT_SUMMARY.copy()
        return registros
    finally:
        cur.close()
        conn.close()


def cargar_registros_por_usuario(username: str, limite: int = 50, con_asignaciones: bool = True) -> list[dict[str, Any]]:
    conn = _connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        select = _SELECT if con_asignaciones else _LIST_SELECT
        deserializer = _deserialize if con_asignaciones else _deserialize_list
        cur.execute(
            select
            + f"""
            WHERE creado_por = %s
            ORDER BY creado_en DESC, id DESC LIMIT {limite}
            """,
            (username,),
        )
        registros = [deserializer(dict(row)) for row in cur.fetchall()]
        if con_asignaciones:
            for registro in registros:
                registro["asignaciones"] = cargar_asignaciones_art(registro["id"])
                registro["progreso_asignaciones"] = _assignment_summary(registro["asignaciones"])
        else:
            for registro in registros:
                registro["asignaciones"] = []
                registro["progreso_asignaciones"] = _EMPTY_ASSIGNMENT_SUMMARY.copy()
        return registros
    finally:
        cur.close()
        conn.close()


def cargar_registros_por_supervisor(username: str, limite: int = 50, con_asignaciones: bool = True) -> list[dict[str, Any]]:
    conn = _connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        select = _SELECT if con_asignaciones else _LIST_SELECT
        deserializer = _deserialize if con_asignaciones else _deserialize_list
        cur.execute(select + f"WHERE supervisor_asignado = %s ORDER BY creado_en DESC, id DESC LIMIT {limite}", (username,))
        registros = [deserializer(dict(row)) for row in cur.fetchall()]
        if con_asignaciones:
            for registro in registros:
                registro["asignaciones"] = cargar_asignaciones_art(registro["id"])
                registro["progreso_asignaciones"] = _assignment_summary(registro["asignaciones"])
        else:
            for registro in registros:
                registro["asignaciones"] = []
                registro["progreso_asignaciones"] = _EMPTY_ASSIGNMENT_SUMMARY.copy()
        return registros
    finally:
        cur.close()
        conn.close()


def obtener_registro(id_art: str) -> dict[str, Any] | None:
    conn = _connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(_SELECT + "WHERE id = %s", (id_art,))
        row = cur.fetchone()
        if not row:
            return None
        registro = _deserialize(dict(row))
        registro["asignaciones"] = cargar_asignaciones_art(registro["id"])
        registro["progreso_asignaciones"] = _assignment_summary(registro["asignaciones"])
        return registro
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


def guardar_trabajadores_art(id_art: str, trabajadores: list[dict[str, Any]]) -> None:
    conn = _connect()
    cur = conn.cursor()
    try:
        for trabajador in trabajadores:
            cur.execute(
                """
                INSERT INTO art_trabajadores (art_id, username, nombre, cargo)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (art_id, username)
                DO UPDATE SET nombre = EXCLUDED.nombre, cargo = EXCLUDED.cargo
                """,
                (
                    id_art,
                    trabajador["username"],
                    trabajador.get("nombre") or trabajador.get("email") or trabajador["username"],
                    trabajador.get("cargo") or "",
                ),
            )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def cargar_trabajadores_art(id_art: str) -> list[dict[str, Any]]:
    conn = _connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            SELECT id, art_id, username, nombre, cargo, condicion_ok, validado_en, observacion
            FROM art_trabajadores
            WHERE art_id = %s
            ORDER BY id ASC
            """,
            (id_art,),
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        cur.close()
        conn.close()


def obtener_trabajador_art(id_art: str, username: str) -> dict[str, Any] | None:
    conn = _connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            SELECT id, art_id, username, nombre, cargo, condicion_ok, validado_en, observacion
            FROM art_trabajadores
            WHERE art_id = %s AND username = %s
            """,
            (id_art, username),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        cur.close()
        conn.close()


def validar_trabajador_art(id_art: str, username: str, condicion_ok: bool, observacion: str, validado_en: str) -> None:
    conn = _connect()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE art_trabajadores
            SET condicion_ok = %s, observacion = %s, validado_en = %s
            WHERE art_id = %s AND username = %s
            """,
            (condicion_ok, observacion, validado_en, id_art, username),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def resetear_validaciones_trabajadores(id_art: str) -> None:
    conn = _connect()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE art_trabajadores
            SET condicion_ok = NULL, observacion = '', validado_en = ''
            WHERE art_id = %s
            """,
            (id_art,)
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
