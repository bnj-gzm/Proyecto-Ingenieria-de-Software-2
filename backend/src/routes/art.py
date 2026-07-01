from datetime import datetime
import json
import logging
import re
from typing import List, Optional
import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from backend.src.config.settings import settings
from backend.src.config.frontend import templates
from backend.src.constants import (
    CONDICIONES_SUPERVISOR,
    REGLAS_QUE_SALVAN_LA_VIDA,
    REGLAS_VIDA_IDS,
)
from backend.src.middleware.auth import get_current_user
from backend.src.middleware.csrf import create_csrf_token, set_csrf_cookie, validate_csrf_token
from backend.src.roles import SUPERVISOR, USER, can_create_art
from backend.src.services.art_service import (
    actualizar_revision_asignacion,
    cargar_asignaciones_art,
    cargar_asignaciones_por_trabajador,
    cargar_registros,
    cargar_registros_por_supervisor,
    cargar_registros_por_usuario,
    cargar_nombres_asignaciones,
    cargar_trabajadores_art,
    eliminar_registro,
    guardar_registro,
    guardar_asignaciones_art,
    guardar_respuesta_asignacion,
    guardar_respuesta_asignacion_por_id,
    guardar_trabajadores_art,
    marcar_envio_asignacion,
    obtener_asignacion_art,
    obtener_asignacion_para_trabajador,
    obtener_asignacion_por_token,
    obtener_trabajador_art,
    obtener_registro,
    preparar_envio_asignacion,
    actualizar_registro,
    validar_trabajador_art,
    resetear_validaciones_trabajadores,
)
from backend.src.services.content_filter import validate_clean_fields
from backend.src.services.email_service import send_art_assignment_email
from backend.src.services.pdf_service import generar_art_pdf, generar_respuesta_trabajador_pdf
from backend.src.services.upload_service import save_art_image
from backend.src.services.usuario_service import cargar_usuarios_asignables, cargar_usuarios_por_rol
from backend.src.services.notification_service import add_notification
from backend.src.services.realtime_service import realtime_manager


router = APIRouter()
logger = logging.getLogger("dart.art")


async def _notify_supervisor_art_response(registro: dict, asignacion: dict) -> None:
    supervisor = (registro.get("supervisor_asignado") or "").strip()
    if not supervisor:
        return
    try:
        notification = add_notification(
            supervisor,
            f"Nueva respuesta en ART {registro['id']}",
            f"{asignacion.get('nombre') or asignacion.get('email') or 'Un trabajador'} respondió la ART y requiere revisión.",
            f"/art/{registro['id']}",
            "ART_RESPONSE",
        )
        await realtime_manager.send_notification(notification)
        logger.info(
            "NOTIFICATION_ART_RESPONSE art_id=%s assignment_id=%s supervisor=%s notification_id=%s",
            registro["id"],
            asignacion.get("id", ""),
            supervisor,
            notification["id"],
        )
    except Exception:
        logger.exception(
            "notification_art_response_failed art_id=%s assignment_id=%s supervisor=%s",
            registro.get("id", ""),
            asignacion.get("id", ""),
            supervisor,
        )

_CHECKLIST = [
    "Me encuentro en condiciones físicas y psicológicas aptas para realizar la actividad.",
    "Cuento con las autorizaciones de ingreso al área.",
    "Cuento con ART/AST necesario para trabajos cruzados.",
    "Dispongo de todos los elementos de protección personal necesarios.",
    "Dispongo de equipos y herramientas necesarias para la tarea.",
    "Existe procedimiento o instructivo de trabajo.",
    "He sido capacitado para ejecutar correctamente el trabajo.",
    "Conozco el plan de emergencia del área.",
]

_EPP = [
    "Casco de seguridad",
    "Lentes de seguridad",
    "Guantes",
    "Zapatos de seguridad",
    "Protección auditiva",
    "Respirador / mascarilla",
    "Chaleco reflectante",
    "Arnés de seguridad",
]

MIN_TRABAJADORES_ART = 3
ANSWERED_ASSIGNMENT_STATES = {"respondido", "con_observacion", "aprobado", "rechazado"}
FINAL_REVIEW_STATES = {"aprobado", "rechazado"}
_TIME_HHMM_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")

_WORKER_QUESTIONS = [
    {"id": "condicion_fisica_psicologica", "section": "Condiciones físicas y psicológicas", "text": "¿Me encuentro en condiciones físicas y psicológicas aptas para realizar la actividad?", "critical": True},
    {"id": "descansado", "section": "Condiciones físicas y psicológicas", "text": "¿Me siento descansado y en condiciones de ejecutar el trabajo?", "critical": True},
    {"id": "sin_sustancias", "section": "Condiciones físicas y psicológicas", "text": "¿No me encuentro bajo efectos de alcohol, drogas o medicamentos que afecten mi desempeño?", "critical": True},
    {"id": "comprendi_tarea", "section": "Condiciones físicas y psicológicas", "text": "¿Comprendí claramente la tarea que debo realizar?", "critical": True},
    {"id": "autorizaciones_area", "section": "Seguridad y autorización", "text": "¿Cuento con las autorizaciones de ingreso al área?", "critical": True},
    {"id": "conozco_area", "section": "Seguridad y autorización", "text": "¿Conozco el área donde se realizará la actividad?", "critical": False},
    {"id": "area_segura", "section": "Seguridad y autorización", "text": "¿El área de trabajo se encuentra segura y señalizada?", "critical": True},
    {"id": "plan_emergencia", "section": "Seguridad y autorización", "text": "¿Conozco el plan de emergencia del área?", "critical": True},
    {"id": "procedimiento", "section": "Procedimiento, capacitación y riesgos", "text": "¿Existe procedimiento o instructivo de trabajo?", "critical": True},
    {"id": "capacitacion", "section": "Procedimiento, capacitación y riesgos", "text": "¿Fui instruido/capacitado para ejecutar correctamente el trabajo?", "critical": True},
    {"id": "riesgos_tarea", "section": "Procedimiento, capacitación y riesgos", "text": "¿Conozco los riesgos asociados a la tarea?", "critical": True},
    {"id": "controles_definidos", "section": "Procedimiento, capacitación y riesgos", "text": "¿Conozco las medidas de control definidas?", "critical": True},
    {"id": "riesgos_criticos", "section": "Procedimiento, capacitación y riesgos", "text": "¿Identifiqué riesgos críticos asociados a la actividad?", "critical": False},
    {"id": "no_iniciar_sin_control", "section": "Procedimiento, capacitación y riesgos", "text": "Si existe un riesgo crítico sin control, ¿entiendo que no debo iniciar el trabajo?", "critical": True},
    {"id": "epp_requeridos", "section": "EPP y herramientas", "text": "¿Cuento con todos los EPP requeridos para la tarea?", "critical": True},
    {"id": "epp_buen_estado", "section": "EPP y herramientas", "text": "¿Mis EPP se encuentran en buen estado?", "critical": True},
    {"id": "herramientas_necesarias", "section": "EPP y herramientas", "text": "¿Cuento con los equipos y herramientas necesarias?", "critical": True},
    {"id": "herramientas_buen_estado", "section": "EPP y herramientas", "text": "¿Las herramientas/equipos están en buenas condiciones?", "critical": True},
]


def _puede_crear_art(user: dict) -> bool:
    return user.get("rol") in {"admin", SUPERVISOR}


async def _leer_condiciones_supervisor(request: Request) -> list[dict]:
    """Lee y valida la declaración física/psicológica del supervisor desde el form.

    Todas las preguntas deben responderse "Sí" para poder crear/editar la ART;
    de lo contrario se bloquea con un 400. Devuelve la lista persistible
    [{id, pregunta, respuesta}].
    """
    form = await request.form()
    condiciones = []
    for pregunta in CONDICIONES_SUPERVISOR:
        respuesta = str(form.get(f"supervisor_cond_{pregunta['id']}", "")).strip().lower()
        if respuesta != "si":
            raise HTTPException(
                status_code=400,
                detail="Debes confirmar todas las condiciones físicas y psicológicas en 'Sí' para registrar la ART.",
            )
        condiciones.append({"id": pregunta["id"], "pregunta": pregunta["text"], "respuesta": "si"})
    return condiciones


def _validar_horario(hora_inicio: str, hora_termino: str) -> dict[str, str]:
    """Valida un rango horario opcional y devuelve errores asociados a cada campo."""
    inicio = hora_inicio.strip()
    termino = hora_termino.strip()
    errors: dict[str, str] = {}
    if not inicio and not termino:
        return errors
    if not inicio:
        errors["hora_inicio"] = "Ingresa el horario de inicio."
    elif not _TIME_HHMM_RE.fullmatch(inicio):
        errors["hora_inicio"] = "Usa un horario válido en formato HH:MM (00:00 a 23:59)."
    if not termino:
        errors["hora_termino"] = "Ingresa el horario de término."
    elif not _TIME_HHMM_RE.fullmatch(termino):
        errors["hora_termino"] = "Usa un horario válido en formato HH:MM (00:00 a 23:59)."
    if not errors and inicio >= termino:
        errors["hora_termino"] = "El horario de término debe ser posterior al horario de inicio."
    return errors


def _trabajadores_activos() -> list[dict]:
    return [
        trabajador
        for trabajador in cargar_usuarios_por_rol(USER)
        if (trabajador.get("estado_cuenta") or "activo") == "activo"
    ]


def _base_url(request: Request) -> str:
    return (settings.public_base_url or str(request.base_url).rstrip("/")).rstrip("/")


def _render_art_link_error(request: Request, message: str, status_code: int = 404):
    return templates.TemplateResponse(
        request,
        "art_trabajador_error.html",
        {
            "request": request,
            "title": "Enlace de ART no disponible",
            "message": message,
            "status_code": status_code,
        },
        status_code=status_code,
    )


async def _save_worker_evidence(request: Request, evidencia: list[UploadFile] | None) -> list[dict]:
    archivos = []
    for archivo in evidencia or []:
        if not archivo.filename:
            continue
        archivos.append(await save_art_image(request.app.state.art_upload_dir, archivo))
    return archivos


def _render_worker_form(request: Request, registro: dict, asignacion: dict, user: dict | None = None):
    csrf_token = create_csrf_token()
    response = templates.TemplateResponse(
        request,
        "art_trabajador_form.html",
        {
            "request": request,
            "user": user,
            "registro": registro,
            "asignacion": asignacion,
            "worker_questions": _WORKER_QUESTIONS,
            "epp": _EPP + ["Otro"],
            "csrf_token": csrf_token,
        },
    )
    set_csrf_cookie(response, csrf_token)
    return response


async def _build_worker_response_payload(
    request: Request,
    asignacion: dict,
    epp: list[str] | None,
    observaciones: str,
    firma_valor: str,
    firma_imagen_base64: str,
    telefono_confirmado: str,
    datos_confirmados: str | None,
    declaracion: str | None,
) -> dict:
    form = await request.form()
    content_user = str(asignacion.get("trabajador_id") or asignacion.get("email") or "anonymous")
    validate_clean_fields({"observaciones": observaciones, "firma": firma_valor}, content_user)
    respuestas: list[dict] = []
    observaciones_por_pregunta: dict[str, str] = {}
    con_observacion = bool(observaciones.strip())
    for pregunta in _WORKER_QUESTIONS:
        respuesta = str(form.get(f"respuesta_{pregunta['id']}", "")).strip().lower()
        if respuesta not in {"si", "no"}:
            raise HTTPException(status_code=400, detail="Debes responder todas las preguntas obligatorias.")
        obs = str(form.get(f"observacion_{pregunta['id']}", "")).strip()
        validate_clean_fields({f"observacion_{pregunta['id']}": obs}, content_user)
        if pregunta["critical"] and respuesta == "no" and not obs and not observaciones.strip():
            raise HTTPException(status_code=400, detail="Debes agregar una observación para cada respuesta crítica marcada como No.")
        if respuesta == "no":
            con_observacion = True
        if obs:
            observaciones_por_pregunta[pregunta["id"]] = obs
            con_observacion = True
        respuestas.append(
            {
                "id": pregunta["id"],
                "seccion": pregunta["section"],
                "pregunta": pregunta["text"],
                "respuesta": respuesta,
                "critica": pregunta["critical"],
                "observacion": obs,
            }
        )
    if not datos_confirmados:
        raise HTTPException(status_code=400, detail="Debes confirmar que tus datos personales son correctos.")
    if not declaracion:
        raise HTTPException(status_code=400, detail="Debes aceptar la declaración antes de enviar.")
    if not epp:
        raise HTTPException(status_code=400, detail="Debes seleccionar los EPP que usarás en la tarea.")
    if not firma_valor.strip() or not firma_imagen_base64.strip():
        raise HTTPException(status_code=400, detail="Debes firmar digitalmente antes de enviar.")
    return {
        "datos_trabajador": {
            "nombre": asignacion.get("nombre", ""),
            "rut": asignacion.get("rut", ""),
            "cargo": asignacion.get("cargo", ""),
            "area": asignacion.get("area", ""),
            "email": asignacion.get("email", ""),
            "telefono": telefono_confirmado.strip() or asignacion.get("telefono", ""),
        },
        "datos_confirmados": True,
        "preguntas": respuestas,
        "epp": epp or [],
        "observaciones": observaciones.strip(),
        "observaciones_por_pregunta": observaciones_por_pregunta,
        "con_observacion": con_observacion,
        "declaracion": True,
    }


def _es_supervisor_asignado(registro: dict, user: dict) -> bool:
    if user.get("rol") != SUPERVISOR:
        return False
    asignado = (registro.get("supervisor_asignado") or "").strip().lower()
    if asignado:
        return asignado == user.get("username", "").strip().lower()
    supervisor_texto = (registro.get("supervisor") or "").strip().lower()
    opciones = {
        user.get("username", "").strip().lower(),
        user.get("nombre", "").strip().lower(),
        user.get("email", "").strip().lower(),
    }
    return supervisor_texto in opciones


def _es_asignado(registro: dict, user: dict) -> bool:
    username = user.get("username", "")
    return (
        obtener_trabajador_art(registro.get("id", ""), username) is not None
        or (registro.get("asignado_a") or "").strip().lower() == username.strip().lower()
    )


def _es_trabajador_asignado_pdf(registro: dict, user: dict) -> bool:
    """Valida la pertenencia usando las asignaciones actuales y el respaldo legacy."""
    if user.get("rol") != USER:
        return False
    trabajador_id = str(user.get("id") or "")
    asignaciones = registro.get("asignaciones") or []
    if asignaciones:
        return bool(trabajador_id) and any(
            str(asignacion.get("trabajador_id") or "") == trabajador_id
            for asignacion in asignaciones
        )
    return _es_asignado(registro, user)


def _puede_descargar_pdf_general(registro: dict, user: dict) -> bool:
    if user.get("rol") == "admin":
        return True
    if user.get("rol") == SUPERVISOR:
        return _es_supervisor_asignado(registro, user)
    return _es_trabajador_asignado_pdf(registro, user)


def _puede_ver_art(registro: dict, user: dict) -> bool:
    return (
        user.get("rol") == "admin"
        or registro.get("creado_por") == user.get("username")
        or _es_asignado(registro, user)
        or _es_supervisor_asignado(registro, user)
    )


def _puede_editar_art(registro: dict, user: dict) -> bool:
    return (
        registro.get("estado") == "pendiente"
        and registro.get("creado_por") == user.get("username")
    )


def _puede_validar_art(registro: dict, user: dict) -> bool:
    return registro.get("estado") == "pendiente" and _es_asignado(registro, user)


def _usuarios_asignables() -> list[dict]:
    return cargar_usuarios_asignables()


@router.get("/", response_class=HTMLResponse)
def inicio(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse(request, "portada.html", {"request": request, "user": user, "title": "D.A.R.T"})


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login", status_code=303)

    if user.get("rol") == "admin":
        registros = cargar_registros(limite=10, con_asignaciones=False)
        art_asignadas = []
    elif user.get("rol") == SUPERVISOR:
        registros = cargar_registros_por_supervisor(user["username"], limite=15, con_asignaciones=False)
        art_asignadas = []
    else:
        registros = []
        art_asignadas = cargar_asignaciones_por_trabajador(user["id"], limite=10)
    nombres_por_art = cargar_nombres_asignaciones([registro["id"] for registro in registros])
    for registro in registros:
        registro["trabajadores_nombres"] = nombres_por_art.get(registro["id"], [])
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"request": request, "user": user, "registros": registros, "art_asignadas": art_asignadas},
    )


@router.get("/art/nueva", response_class=HTMLResponse)
def nueva_art(request: Request, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login", status_code=303)
    if not can_create_art(user.get("rol", "")):
        return RedirectResponse("/dashboard", status_code=303)
    return _render_nueva_art_form(request, user)


def _render_nueva_art_form(
    request: Request,
    user: dict,
    *,
    error: str | None = None,
    status_code: int = 200,
    form_values: dict | None = None,
    form_riesgos: list[dict] | None = None,
    trabajadores_seleccionados: list[str] | None = None,
    reglas_seleccionadas: list[str] | None = None,
    condiciones_seleccionadas: dict[str, str] | None = None,
    form_errors: dict[str, str] | None = None,
):
    csrf_token = create_csrf_token()
    response = templates.TemplateResponse(
        request,
        "nueva_art.html",
        {
            "request": request,
            "user": user,
            "trabajadores": _usuarios_asignables(),
            "min_trabajadores": MIN_TRABAJADORES_ART,
            "fecha_actual": datetime.now().strftime("%Y-%m-%d"),
            "reglas_disponibles": REGLAS_QUE_SALVAN_LA_VIDA,
            "reglas_seleccionadas": reglas_seleccionadas or [],
            "condiciones_supervisor": CONDICIONES_SUPERVISOR,
            "condiciones_seleccionadas": condiciones_seleccionadas or {},
            "trabajadores_seleccionados": trabajadores_seleccionados or [],
            "form_values": form_values or {},
            "form_riesgos": form_riesgos or [],
            "form_error": error,
            "form_errors": form_errors or {},
            "csrf_token": csrf_token,
        },
        status_code=status_code,
    )
    set_csrf_cookie(response, csrf_token)
    return response


@router.post("/art/guardar")
async def guardar_art(
    request: Request,
    empresa: str = Form(...),
    area: str = Form(...),
    tipo_tarea: str = Form(...),
    descripcion: str = Form(...),
    trabajador_asignado: Optional[List[str]] = Form(None),
    trabajadores_asignados: Optional[List[str]] = Form(None),
    supervisor_asignado: str = Form(...),
    gerencia: str = Form(""),
    hora_inicio: str = Form(""),
    hora_termino: str = Form(""),
    lugar: str = Form(""),
    reglas_vida: Optional[List[str]] = Form(None),
    checklist: Optional[List[str]] = Form(None),
    epp: Optional[List[str]] = Form(None),
    secuencia: Optional[List[str]] = Form(None),
    riesgo: Optional[List[str]] = Form(None),
    control: Optional[List[str]] = Form(None),
    riesgos_json: str = Form(""),
    observaciones: str = Form(""),
    evidencia: Optional[List[UploadFile]] = File(None),
    csrf_token: str = Form(...),
    user=Depends(get_current_user),
):
    if not user:
        return RedirectResponse("/login", status_code=303)
    if not can_create_art(user.get("rol", "")):
        raise HTTPException(status_code=403, detail="No tienes permiso para crear ART")
    validate_csrf_token(request, csrf_token)
    seleccion = list(dict.fromkeys(trabajadores_asignados or trabajador_asignado or []))
    reglas_seleccionadas = [item for item in (reglas_vida or []) if item in REGLAS_VIDA_IDS]
    form_values = {
        "empresa": empresa,
        "area": area,
        "tipo_tarea": tipo_tarea,
        "descripcion": descripcion,
        "supervisor_asignado": supervisor_asignado,
        "gerencia": gerencia,
        "hora_inicio": hora_inicio,
        "hora_termino": hora_termino,
        "lugar": lugar,
        "observaciones": observaciones,
    }
    form = await request.form()
    condiciones_seleccionadas = {
        pregunta["id"]: str(form.get(f"supervisor_cond_{pregunta['id']}", "")).strip().lower()
        for pregunta in CONDICIONES_SUPERVISOR
    }
    riesgos_recibidos: list[dict[str, str]] = []
    if riesgos_json.strip():
        try:
            decoded_for_render = json.loads(riesgos_json)
            if isinstance(decoded_for_render, list):
                riesgos_recibidos = [
                    {
                        "secuencia": str(item.get("actividad") or item.get("secuencia") or "").strip(),
                        "riesgo": str(item.get("riesgo") or "").strip(),
                        "control": str(item.get("control") or "").strip(),
                    }
                    for item in decoded_for_render
                    if isinstance(item, dict)
                ]
        except json.JSONDecodeError:
            pass
    else:
        riesgos_recibidos = [
            {"secuencia": seq.strip(), "riesgo": risk.strip(), "control": ctrl.strip()}
            for seq, risk, ctrl in zip(secuencia or [], riesgo or [], control or [])
            if seq.strip() or risk.strip() or ctrl.strip()
        ]

    def validation_error(
        message: str,
        stage: str,
        riesgos_form: list[dict] | None = None,
        field_errors: dict[str, str] | None = None,
    ):
        logger.warning(
            "ART_CREATE_VALIDATION_FAILED stage=%s user=%s workers=%s risk_rows=%s detail=%s",
            stage,
            user.get("username", ""),
            len(seleccion),
            len(riesgos_form or []),
            message,
        )
        return _render_nueva_art_form(
            request,
            user,
            error=message,
            status_code=200,
            form_values=form_values,
            form_riesgos=riesgos_form if riesgos_form is not None else riesgos_recibidos,
            trabajadores_seleccionados=[str(item) for item in seleccion],
            reglas_seleccionadas=reglas_seleccionadas,
            condiciones_seleccionadas=condiciones_seleccionadas,
            form_errors=field_errors,
        )

    logger.info(
        "ART_CREATE_VALIDATION_START user=%s workers_received=%s risk_json_present=%s evidence_files=%s",
        user.get("username", ""),
        len(seleccion),
        bool(riesgos_json.strip()),
        len(evidencia or []),
    )
    logger.info("ART_CREATE_VALIDATION stage=trabajadores user=%s", user.get("username", ""))
    trabajadores_disponibles = _usuarios_asignables()
    ids_asignados = {int(item) for item in seleccion if str(item).isdigit()}
    usernames_asignados = {item for item in seleccion if not str(item).isdigit()}
    trabajadores_asignados_lista = [
        trabajador
        for trabajador in trabajadores_disponibles
        if trabajador["id"] in ids_asignados or trabajador["username"] in usernames_asignados
    ]
    if len(trabajadores_asignados_lista) < MIN_TRABAJADORES_ART:
        return validation_error(
            f"Trabajadores asignados: debes seleccionar al menos {MIN_TRABAJADORES_ART} trabajadores activos y distintos.",
            "trabajadores",
        )
    supervisor_user = next((u for u in cargar_usuarios_por_rol(SUPERVISOR) if u["username"] == supervisor_asignado), None)
    trabajador = ", ".join(
        trabajador_user.get("nombre_completo") or trabajador_user.get("nombre") or trabajador_user.get("email") or trabajador_user["username"]
        for trabajador_user in trabajadores_asignados_lista
    )
    supervisor = (supervisor_user or {}).get("nombre_completo") or (supervisor_user or {}).get("nombre") or supervisor_asignado
    riesgos: list[dict[str, str]] = []
    logger.info("ART_CREATE_VALIDATION stage=riesgos user=%s", user.get("username", ""))
    if riesgos_json.strip():
        try:
            decoded_risks = json.loads(riesgos_json)
        except json.JSONDecodeError:
            return validation_error("Riesgos: el formato recibido no es JSON válido.", "riesgos_json")
        if not isinstance(decoded_risks, list):
            return validation_error("Riesgos: se esperaba una lista de filas.", "riesgos_json")
        for index, item in enumerate(decoded_risks, start=1):
            if not isinstance(item, dict):
                return validation_error(f"Riesgos: la fila {index} no tiene un formato válido.", "riesgos_json", riesgos)
            riesgos.append(
                {
                    "secuencia": str(item.get("actividad") or item.get("secuencia") or "").strip(),
                    "riesgo": str(item.get("riesgo") or "").strip(),
                    "control": str(item.get("control") or "").strip(),
                }
            )
    else:
        if not (len(secuencia or []) == len(riesgo or []) == len(control or [])):
            return validation_error("Riesgos: las columnas llegaron incompletas o desalineadas.", "riesgos_listas")
        for seq, risk, ctrl in zip(secuencia or [], riesgo or [], control or []):
            if seq.strip() or risk.strip() or ctrl.strip():
                riesgos.append({"secuencia": seq.strip(), "riesgo": risk.strip(), "control": ctrl.strip()})
    if not riesgos:
        return validation_error("Riesgos: debes agregar al menos una fila.", "riesgos_vacios")
    for index, item in enumerate(riesgos, start=1):
        missing = [label for key, label in (("secuencia", "actividad"), ("riesgo", "riesgo"), ("control", "control")) if not item[key]]
        if missing:
            return validation_error(
                f"Error en riesgos, fila {index}: completa {', '.join(missing)}.",
                "riesgos_campos",
                riesgos,
            )
    horario_errors = _validar_horario(hora_inicio, hora_termino)
    if horario_errors:
        return validation_error(
            "Revisa los horarios indicados.",
            "horarios",
            riesgos,
            horario_errors,
        )
    logger.info("ART_CREATE_VALIDATION stage=contenido user=%s", user.get("username", ""))
    try:
        validate_clean_fields(
            {
                "empresa": empresa,
                "área": area,
                "tipo de tarea": tipo_tarea,
                "descripción": descripcion,
                "observaciones": observaciones,
                "gerencia": gerencia,
                "lugar": lugar,
                **{
                    f"riesgos, fila {index}, {key}": item[field]
                    for index, item in enumerate(riesgos, start=1)
                    for key, field in (("actividad", "secuencia"), ("riesgo", "riesgo"), ("control", "control"))
                },
            },
            user.get("username", ""),
        )
    except HTTPException as exc:
        return validation_error(str(exc.detail), "filtro_contenido", riesgos)
    logger.info("ART_CREATE_VALIDATION stage=condiciones_supervisor user=%s", user.get("username", ""))
    try:
        condiciones_supervisor = await _leer_condiciones_supervisor(request)
    except HTTPException as exc:
        return validation_error(str(exc.detail), "condiciones_supervisor", riesgos)
    archivos = []
    logger.info("ART_CREATE_VALIDATION stage=evidencia user=%s", user.get("username", ""))
    for archivo in evidencia or []:
        if not archivo.filename:
            continue
        try:
            archivos.append(await save_art_image(request.app.state.art_upload_dir, archivo))
        except HTTPException as exc:
            return validation_error(f"Evidencia: {exc.detail}", "evidencia", riesgos)
    id_art = str(uuid.uuid4())[:8]
    registro = {
        "id": id_art,
        "empresa": empresa,
        "trabajador": trabajador,
        "area": area,
        "fecha": datetime.now().strftime("%Y-%m-%d"),
        "tipo_tarea": tipo_tarea,
        "descripcion": descripcion,
        "supervisor": supervisor,
        "checklist": [],
        "epp": [],
        "riesgos": riesgos,
        "observaciones": observaciones,
        "evidencia": archivos,
        "creado_en": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "creado_por": user["username"],
        "asignado_a": trabajadores_asignados_lista[0]["username"],
        "supervisor_asignado": supervisor_asignado,
        "gerencia": gerencia.strip(),
        "hora_inicio": hora_inicio.strip(),
        "hora_termino": hora_termino.strip(),
        "lugar": lugar.strip(),
        "reglas_vida": reglas_seleccionadas,
        "supervisor_condiciones": condiciones_supervisor,
    }
    guardar_registro(registro)
    guardar_trabajadores_art(id_art, trabajadores_asignados_lista)
    guardar_asignaciones_art(id_art, trabajadores_asignados_lista)
    try:
        from backend.src.services import logging_service as _log_svc
        _log_svc.log_event(_log_svc.ART_CREATED, username=user.get("username", ""), details={"art_id": id_art})
    except Exception:
        pass
    for trabajador_user in trabajadores_asignados_lista:
        try:
            notification = add_notification(
                trabajador_user["username"],
                f"ART {id_art} asignada",
                f"{user.get('nombre') or user.get('username')} te asignó una ART para completar y validar.",
                f"/art/{id_art}",
                "ART_CREATED",
            )
            await realtime_manager.send_notification(notification)
        except Exception:
            logger.exception("art_created_notification_failed art_id=%s user=%s", id_art, trabajador_user["username"])
    logger.info(
        "ART_CREATED_OK art_id=%s created_by=%s supervisor=%s assigned_workers=%s",
        id_art,
        user.get("username"),
        supervisor_asignado,
        len(trabajadores_asignados_lista),
    )
    return RedirectResponse(f"/art/{id_art}", status_code=303)


@router.post("/art/{id_art}/enviar-trabajadores")
def enviar_art_trabajadores(
    request: Request,
    id_art: str,
    csrf_token: str = Form(...),
    user=Depends(get_current_user),
):
    if not user:
        return RedirectResponse("/login", status_code=303)
    validate_csrf_token(request, csrf_token)
    registro = obtener_registro(id_art)
    if not registro:
        return RedirectResponse("/dashboard", status_code=303)
    supervisor_asignado = _es_supervisor_asignado(registro, user)
    if user.get("rol") != "admin" and not supervisor_asignado:
        raise HTTPException(status_code=403, detail="No tienes permiso para enviar esta ART")
    asignaciones = cargar_asignaciones_art(id_art)
    if len(asignaciones) < MIN_TRABAJADORES_ART:
        raise HTTPException(status_code=400, detail="Debes asignar al menos 6 trabajadores distintos a la ART.")

    enviados = 0
    fallidos = 0
    base_url = _base_url(request)
    for asignacion in asignaciones:
        preparada = preparar_envio_asignacion(asignacion["id"])
        if not preparada:
            continue
        link = f"{base_url}/art/trabajador/{preparada['token_acceso']}"
        result = send_art_assignment_email(preparada.get("email", ""), link, registro, preparada.get("nombre", ""))
        if result.ok:
            enviados += 1
            marcar_envio_asignacion(preparada["id"], "enviado")
            logger.info(
                "EMAIL_SENT_OK context=art_assignment art_id=%s assignment_id=%s to=%s message_id=%s",
                id_art,
                preparada["id"],
                preparada.get("email", ""),
                result.message_id,
            )
        else:
            fallidos += 1
            marcar_envio_asignacion(preparada["id"], "envio_fallido")
            logger.error(
                "EMAIL_SENT_FAIL context=art_assignment art_id=%s assignment_id=%s to=%s error=%s",
                id_art,
                preparada["id"],
                preparada.get("email", ""),
                result.error,
            )

    message = f"Correos enviados: {enviados}. Correos no enviados: {fallidos}. Total asignados: {len(asignaciones)}."
    return RedirectResponse(f"/art/{id_art}?mensaje={quote(message)}", status_code=303)


@router.post("/art/{id_art}/enviar-trabajador/{id_asignacion}")
def enviar_art_trabajador(
    request: Request,
    id_art: str,
    id_asignacion: int,
    csrf_token: str = Form(...),
    user=Depends(get_current_user),
):
    if not user:
        return RedirectResponse("/login", status_code=303)
    validate_csrf_token(request, csrf_token)
    registro = obtener_registro(id_art)
    if not registro:
        return RedirectResponse("/dashboard", status_code=303)
    supervisor_asignado = _es_supervisor_asignado(registro, user)
    if user.get("rol") != "admin" and not supervisor_asignado:
        raise HTTPException(status_code=403, detail="No tienes permiso para enviar esta ART")
    asignacion = obtener_asignacion_art(id_art, id_asignacion)
    if not asignacion:
        raise HTTPException(status_code=404, detail="Trabajador asignado no encontrado")
    preparada = preparar_envio_asignacion(id_asignacion)
    if not preparada:
        return RedirectResponse(f"/art/{id_art}?mensaje={quote('El trabajador ya respondió esta ART.')}", status_code=303)
    link = f"{_base_url(request)}/art/trabajador/{preparada['token_acceso']}"
    result = send_art_assignment_email(preparada.get("email", ""), link, registro, preparada.get("nombre", ""))
    marcar_envio_asignacion(preparada["id"], "enviado" if result.ok else "envio_fallido")
    if result.ok:
        logger.info(
            "EMAIL_SENT_OK context=art_assignment art_id=%s assignment_id=%s to=%s message_id=%s",
            id_art,
            preparada["id"],
            preparada.get("email", ""),
            result.message_id,
        )
    else:
        logger.error(
            "EMAIL_SENT_FAIL context=art_assignment art_id=%s assignment_id=%s to=%s error=%s",
            id_art,
            preparada["id"],
            preparada.get("email", ""),
            result.error,
        )
    message = "Correo enviado correctamente." if result.ok else "No se pudo enviar el correo. Revisa la configuración de email."
    return RedirectResponse(f"/art/{id_art}?mensaje={quote(message)}", status_code=303)


@router.get("/art/trabajador/{token}", response_class=HTMLResponse)
def formulario_trabajador_token(request: Request, token: str):
    try:
        asignacion = obtener_asignacion_por_token(token)
    except Exception:
        logger.exception("ART_TOKEN_LOOKUP_FAILED token_prefix=%s", token[:8])
        return _render_art_link_error(
            request,
            "No pudimos validar este enlace de ART en este momento. Intenta nuevamente en unos segundos.",
            status_code=503,
        )
    if not asignacion:
        logger.warning("ART_TOKEN_NOT_FOUND token_prefix=%s", token[:8])
        return _render_art_link_error(request, "El enlace de ART no existe o ya no está disponible.", status_code=404)
    try:
        registro = obtener_registro(asignacion["art_id"])
    except Exception:
        logger.exception("ART_LOOKUP_FAILED token_prefix=%s art_id=%s", token[:8], asignacion.get("art_id"))
        return _render_art_link_error(
            request,
            "No pudimos cargar la ART asociada. Intenta nuevamente en unos segundos.",
            status_code=503,
        )
    if not registro:
        logger.warning("ART_TOKEN_NOT_FOUND token_prefix=%s art_id=%s cause=art_missing", token[:8], asignacion.get("art_id"))
        return _render_art_link_error(request, "La ART asociada a este enlace no existe.", status_code=404)
    if asignacion.get("estado_respuesta") in ANSWERED_ASSIGNMENT_STATES:
        return templates.TemplateResponse(
            request,
            "art_trabajador_gracias.html",
            {"request": request, "user": None, "registro": registro, "asignacion": asignacion},
        )
    expires_at = asignacion.get("token_expires_at")
    if expires_at and expires_at < datetime.now():
        logger.warning("ART_TOKEN_NOT_FOUND token_prefix=%s art_id=%s cause=expired", token[:8], asignacion.get("art_id"))
        return _render_art_link_error(
            request,
            "El enlace de ART expiró. Solicita un reenvío al supervisor.",
            status_code=403,
        )
    return _render_worker_form(request, registro, asignacion)


@router.post("/art/trabajador/{token}")
async def guardar_formulario_trabajador_token(
    request: Request,
    token: str,
    epp: Optional[List[str]] = Form(None),
    observaciones: str = Form(""),
    firma_tipo: str = Form("simple"),
    firma_valor: str = Form(...),
    firma_imagen_base64: str = Form(""),
    evidencia_trabajador: Optional[List[UploadFile]] = File(None),
    telefono_confirmado: str = Form(""),
    datos_confirmados: Optional[str] = Form(None),
    declaracion: Optional[str] = Form(None),
    csrf_token: str = Form(...),
):
    validate_csrf_token(request, csrf_token)
    try:
        asignacion = obtener_asignacion_por_token(token)
    except Exception:
        logger.exception("ART_TOKEN_LOOKUP_FAILED token_prefix=%s method=POST", token[:8])
        return _render_art_link_error(
            request,
            "No pudimos validar este enlace de ART en este momento. Intenta nuevamente en unos segundos.",
            status_code=503,
        )
    if not asignacion:
        logger.warning("ART_TOKEN_NOT_FOUND token_prefix=%s method=POST", token[:8])
        return _render_art_link_error(request, "El enlace de ART no existe o ya no está disponible.", status_code=404)
    if asignacion.get("estado_respuesta") in ANSWERED_ASSIGNMENT_STATES:
        return RedirectResponse(f"/art/trabajador/{token}", status_code=303)
    expires_at = asignacion.get("token_expires_at")
    if expires_at and expires_at < datetime.now():
        logger.warning("ART_TOKEN_NOT_FOUND token_prefix=%s art_id=%s method=POST cause=expired", token[:8], asignacion.get("art_id"))
        return _render_art_link_error(
            request,
            "El enlace de ART expiró. Solicita un reenvío al supervisor.",
            status_code=403,
        )
    payload = await _build_worker_response_payload(
        request,
        asignacion,
        epp,
        observaciones,
        firma_valor,
        firma_imagen_base64,
        telefono_confirmado,
        datos_confirmados,
        declaracion,
    )
    evidencia_archivos = await _save_worker_evidence(request, evidencia_trabajador)
    guardar_respuesta_asignacion(
        token,
        payload,
        firma_tipo,
        firma_valor.strip(),
        firma_imagen_base64.strip(),
        evidencia_archivos,
    )
    await _notify_supervisor_art_response(registro, asignacion)
    return RedirectResponse(f"/art/trabajador/{token}", status_code=303)


@router.get("/art/asignada/{id_asignacion}/responder", response_class=HTMLResponse)
def responder_art_asignada_view(request: Request, id_asignacion: int, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user.get("rol") != USER:
        raise HTTPException(status_code=403, detail="Solo el trabajador asignado puede completar esta ART.")
    asignacion = obtener_asignacion_para_trabajador(id_asignacion, user["id"])
    if not asignacion:
        raise HTTPException(status_code=404, detail="ART asignada no encontrada.")
    registro = obtener_registro(asignacion["art_id"])
    if not registro:
        raise HTTPException(status_code=404, detail="La ART asociada no existe.")
    if asignacion.get("estado_respuesta") in ANSWERED_ASSIGNMENT_STATES:
        return RedirectResponse(f"/art/asignada/{id_asignacion}/respuesta", status_code=303)
    return _render_worker_form(request, registro, asignacion, user)


@router.post("/art/asignada/{id_asignacion}/responder")
async def responder_art_asignada_post(
    request: Request,
    id_asignacion: int,
    epp: Optional[List[str]] = Form(None),
    observaciones: str = Form(""),
    firma_tipo: str = Form("simple"),
    firma_valor: str = Form(...),
    firma_imagen_base64: str = Form(""),
    evidencia_trabajador: Optional[List[UploadFile]] = File(None),
    telefono_confirmado: str = Form(""),
    datos_confirmados: Optional[str] = Form(None),
    declaracion: Optional[str] = Form(None),
    csrf_token: str = Form(...),
    user=Depends(get_current_user),
):
    if not user:
        return RedirectResponse("/login", status_code=303)
    validate_csrf_token(request, csrf_token)
    if user.get("rol") != USER:
        raise HTTPException(status_code=403, detail="Solo el trabajador asignado puede completar esta ART.")
    asignacion = obtener_asignacion_para_trabajador(id_asignacion, user["id"])
    if not asignacion:
        raise HTTPException(status_code=404, detail="ART asignada no encontrada.")
    if asignacion.get("estado_respuesta") in ANSWERED_ASSIGNMENT_STATES:
        return RedirectResponse(f"/art/asignada/{id_asignacion}/respuesta", status_code=303)
    payload = await _build_worker_response_payload(
        request,
        asignacion,
        epp,
        observaciones,
        firma_valor,
        firma_imagen_base64,
        telefono_confirmado,
        datos_confirmados,
        declaracion,
    )
    evidencia_archivos = await _save_worker_evidence(request, evidencia_trabajador)
    guardar_respuesta_asignacion_por_id(
        id_asignacion,
        payload,
        firma_tipo,
        firma_valor.strip(),
        firma_imagen_base64.strip(),
        evidencia_archivos,
    )
    registro = obtener_registro(asignacion["art_id"])
    if registro:
        await _notify_supervisor_art_response(registro, asignacion)
    return RedirectResponse(f"/art/asignada/{id_asignacion}/respuesta", status_code=303)


@router.get("/art/asignada/{id_asignacion}/respuesta", response_class=HTMLResponse)
def respuesta_art_asignada_view(request: Request, id_asignacion: int, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user.get("rol") != USER:
        raise HTTPException(status_code=403, detail="Solo el trabajador asignado puede ver esta respuesta.")
    asignacion = obtener_asignacion_para_trabajador(id_asignacion, user["id"])
    if not asignacion:
        raise HTTPException(status_code=404, detail="ART asignada no encontrada.")
    registro = obtener_registro(asignacion["art_id"])
    if not registro:
        raise HTTPException(status_code=404, detail="La ART asociada no existe.")
    return templates.TemplateResponse(
        request,
        "art_respuesta_trabajador.html",
        {"request": request, "user": user, "registro": registro, "asignacion": asignacion},
    )


@router.get("/mis-art-asignadas", response_class=HTMLResponse)
def mis_art_asignadas(request: Request, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user.get("rol") != USER:
        return RedirectResponse("/dashboard", status_code=303)
    art_asignadas = cargar_asignaciones_por_trabajador(user["id"], limite=30)
    return templates.TemplateResponse(
        request,
        "mis_art_asignadas.html",
        {"request": request, "user": user, "art_asignadas": art_asignadas},
    )


@router.get("/art/{id_art}", response_class=HTMLResponse)
def detalle_art(request: Request, id_art: str, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login", status_code=303)
    registro = obtener_registro(id_art)
    if not registro:
        return RedirectResponse("/dashboard", status_code=303)
    supervisor_asignado = _es_supervisor_asignado(registro, user)
    if not _puede_ver_art(registro, user):
        return RedirectResponse("/dashboard", status_code=303)
    if user.get("rol") == SUPERVISOR and not supervisor_asignado:
        return RedirectResponse("/dashboard", status_code=303)
    csrf_token = create_csrf_token()
    trabajadores_art = cargar_trabajadores_art(id_art)
    validacion_actual = next(
        (item for item in trabajadores_art if item.get("username") == user.get("username")),
        None,
    )
    # Only allow supervisor to review if assigned AND the ART is not already approved/rejected
    puede_revisar = supervisor_asignado and registro.get("estado") not in {"aprobada", "rechazada"}
    todos_validados = all(t.get("condicion_ok") is not None for t in trabajadores_art) if trabajadores_art else False
    response = templates.TemplateResponse(
        request,
        "detalle_art.html",
        {
            "request": request,
            "registro": registro,
            "user": user,
            "csrf_token": csrf_token,
            "puede_revisar": puede_revisar,
            "puede_editar": _puede_editar_art(registro, user),
            "puede_validar": _puede_validar_art(registro, user),
            "puede_descargar_pdf": _puede_descargar_pdf_general(registro, user),
            "trabajadores_art": trabajadores_art,
            "validacion_actual": validacion_actual,
            "todos_validados": todos_validados,
        },
    )
    set_csrf_cookie(response, csrf_token)
    return response


@router.get("/art/{id_art}/respuesta/{id_asignacion}", response_class=HTMLResponse)
def detalle_respuesta_trabajador(
    request: Request,
    id_art: str,
    id_asignacion: int,
    user=Depends(get_current_user),
):
    if not user:
        return RedirectResponse("/login", status_code=303)
    registro = obtener_registro(id_art)
    if not registro:
        return RedirectResponse("/dashboard", status_code=303)
    supervisor_asignado = _es_supervisor_asignado(registro, user)
    if user.get("rol") != "admin" and not supervisor_asignado:
        raise HTTPException(status_code=403, detail="No tienes permiso para ver esta respuesta")
    asignacion = obtener_asignacion_art(id_art, id_asignacion)
    if not asignacion:
        raise HTTPException(status_code=404, detail="Respuesta no encontrada")
    csrf_token = create_csrf_token()
    response = templates.TemplateResponse(
        request,
        "art_respuesta_trabajador.html",
        {"request": request, "user": user, "registro": registro, "asignacion": asignacion, "csrf_token": csrf_token},
    )
    set_csrf_cookie(response, csrf_token)
    return response


@router.post("/art/{id_art}/trabajador/{id_asignacion}/revision")
def revisar_respuesta_trabajador(
    request: Request,
    id_art: str,
    id_asignacion: int,
    resultado: str = Form(...),
    comentario_revision: str = Form(""),
    csrf_token: str = Form(...),
    user=Depends(get_current_user),
):
    if not user:
        return RedirectResponse("/login", status_code=303)
    validate_csrf_token(request, csrf_token)
    registro = obtener_registro(id_art)
    if not registro:
        return RedirectResponse("/dashboard", status_code=303)
    supervisor_asignado = _es_supervisor_asignado(registro, user)
    if user.get("rol") != "admin" and not supervisor_asignado:
        raise HTTPException(status_code=403, detail="No tienes permiso para revisar esta respuesta")
    asignacion = obtener_asignacion_art(id_art, id_asignacion)
    if not asignacion:
        raise HTTPException(status_code=404, detail="Respuesta no encontrada")
    if asignacion.get("estado_respuesta") in FINAL_REVIEW_STATES:
        return RedirectResponse(f"/art/{id_art}?mensaje={quote('La revisión individual ya está cerrada.')}", status_code=303)
    if asignacion.get("estado_respuesta") not in ANSWERED_ASSIGNMENT_STATES:
        raise HTTPException(status_code=400, detail="El trabajador aún no ha enviado su respuesta")
    estados_validos = FINAL_REVIEW_STATES
    if resultado not in estados_validos:
        raise HTTPException(status_code=400, detail="Resultado de revisión inválido")
    if resultado == "rechazado" and not comentario_revision.strip():
        return JSONResponse(
            {
                "error": "validation_error",
                "field": "comentario",
                "message": "Comentario obligatorio para rechazar ART",
            },
            status_code=400,
        )
    validate_clean_fields({"comentario_revision": comentario_revision}, user.get("username", ""))
    art_completada = actualizar_revision_asignacion(id_asignacion, resultado, comentario_revision.strip(), user["id"])
    if art_completada:
        message = "Revisión registrada. Todas las validaciones finalizaron y la ART quedó completada."
    else:
        message = "Revisión individual aprobada." if resultado == "aprobado" else "Revisión individual rechazada."
    return RedirectResponse(f"/art/{id_art}?mensaje={quote(message)}", status_code=303)


@router.get("/art/{id_art}/trabajador/{id_asignacion}/pdf")
def descargar_respuesta_trabajador_pdf(
    id_art: str,
    id_asignacion: int,
    user=Depends(get_current_user),
):
    if not user:
        return RedirectResponse("/login", status_code=303)
    registro = obtener_registro(id_art)
    if not registro:
        return RedirectResponse("/dashboard", status_code=303)
    supervisor_asignado = _es_supervisor_asignado(registro, user)
    if user.get("rol") != "admin" and not supervisor_asignado:
        raise HTTPException(status_code=403, detail="No tienes permiso para descargar este PDF")
    asignacion = obtener_asignacion_art(id_art, id_asignacion)
    if not asignacion:
        raise HTTPException(status_code=404, detail="Respuesta no encontrada")
    if asignacion.get("estado_respuesta") != "aprobado":
        raise HTTPException(status_code=400, detail="El PDF estará disponible cuando la respuesta esté aprobada")
    pdf = generar_respuesta_trabajador_pdf(registro, asignacion)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="art-{id_art}-trabajador-{id_asignacion}.pdf"'},
    )


def _render_editar_art_form(
    request: Request,
    user: dict,
    registro: dict,
    *,
    error: str | None = None,
    form_errors: dict[str, str] | None = None,
    condiciones_seleccionadas: dict[str, str] | None = None,
):
    csrf_token = create_csrf_token()
    if condiciones_seleccionadas is None:
        condiciones_seleccionadas = {
            item.get("id"): item.get("respuesta")
            for item in registro.get("supervisor_condiciones", [])
        }
    response = templates.TemplateResponse(
        request,
        "editar_art.html",
        {
            "request": request,
            "user": user,
            "csrf_token": csrf_token,
            "registro": registro,
            "validacion_actual": None,
            "reglas_disponibles": REGLAS_QUE_SALVAN_LA_VIDA,
            "reglas_seleccionadas": registro.get("reglas_vida", []),
            "condiciones_supervisor": CONDICIONES_SUPERVISOR,
            "condiciones_seleccionadas": condiciones_seleccionadas,
            "form_error": error,
            "form_errors": form_errors or {},
        },
        status_code=200,
    )
    set_csrf_cookie(response, csrf_token)
    return response


@router.get("/art/{id_art}/editar", response_class=HTMLResponse)
def editar_art_view(request: Request, id_art: str, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login", status_code=303)
    registro = obtener_registro(id_art)
    if not registro:
        return RedirectResponse("/dashboard", status_code=303)
    
    csrf_token = create_csrf_token()
    validacion_actual = obtener_trabajador_art(id_art, user["username"])
    if validacion_actual and _puede_validar_art(registro, user):
        response = templates.TemplateResponse(
            request,
            "validar_art.html",
            {
                "request": request,
                "user": user,
                "csrf_token": csrf_token,
                "registro": registro,
                "validacion_actual": validacion_actual,
            },
        )
        set_csrf_cookie(response, csrf_token)
        return response
    if not _puede_editar_art(registro, user):
        return RedirectResponse("/dashboard", status_code=303)
    
    return _render_editar_art_form(request, user, registro)


@router.post("/art/{id_art}/editar")
async def editar_art_post(
    request: Request,
    id_art: str,
    empresa: str = Form(...),
    area: str = Form(...),
    tipo_tarea: str = Form(...),
    descripcion: str = Form(...),
    supervisor_asignado: str = Form(...),
    gerencia: str = Form(""),
    hora_inicio: str = Form(""),
    hora_termino: str = Form(""),
    lugar: str = Form(""),
    reglas_vida: Optional[List[str]] = Form(None),
    secuencia: Optional[List[str]] = Form(None),
    riesgo: Optional[List[str]] = Form(None),
    control: Optional[List[str]] = Form(None),
    observaciones: str = Form(""),
    evidencia: Optional[List[UploadFile]] = File(None),
    csrf_token: str = Form(...),
    user=Depends(get_current_user),
):
    if not user:
        return RedirectResponse("/login", status_code=303)
    validate_csrf_token(request, csrf_token)

    registro_existente = obtener_registro(id_art)
    if not registro_existente:
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    if not _puede_editar_art(registro_existente, user):
        raise HTTPException(status_code=403, detail="No tienes permiso para editar esta ART")

    form = await request.form()
    condiciones_seleccionadas = {
        pregunta["id"]: str(form.get(f"supervisor_cond_{pregunta['id']}", "")).strip().lower()
        for pregunta in CONDICIONES_SUPERVISOR
    }
    reglas_seleccionadas = [item for item in (reglas_vida or []) if item in REGLAS_VIDA_IDS]

    supervisor_user = next((u for u in cargar_usuarios_por_rol(SUPERVISOR) if u["username"] == supervisor_asignado), None)
    trabajador = registro_existente.get("trabajador") or user.get("nombre") or user["username"]
    supervisor = (supervisor_user or {}).get("nombre") or supervisor_asignado
    
    riesgos = []
    for seq, risk, ctrl in zip(secuencia or [], riesgo or [], control or []):
        if seq.strip() or risk.strip() or ctrl.strip():
            riesgos.append({"secuencia": seq.strip(), "riesgo": risk.strip(), "control": ctrl.strip()})
    registro_form = {
        **registro_existente,
        "empresa": empresa,
        "area": area,
        "tipo_tarea": tipo_tarea,
        "descripcion": descripcion,
        "supervisor_asignado": supervisor_asignado,
        "gerencia": gerencia,
        "hora_inicio": hora_inicio,
        "hora_termino": hora_termino,
        "lugar": lugar,
        "observaciones": observaciones,
        "riesgos": riesgos,
        "reglas_vida": reglas_seleccionadas,
    }

    def validation_error(message: str, field_errors: dict[str, str] | None = None):
        return _render_editar_art_form(
            request,
            user,
            registro_form,
            error=message,
            form_errors=field_errors,
            condiciones_seleccionadas=condiciones_seleccionadas,
        )

    horario_errors = _validar_horario(hora_inicio, hora_termino)
    if horario_errors:
        return validation_error("Revisa los horarios indicados.", horario_errors)
    if not riesgos or any(not item["secuencia"] or not item["riesgo"] or not item["control"] for item in riesgos):
        return validation_error("Completa actividad, riesgo y control en cada fila.")
    try:
        validate_clean_fields(
            {
                "empresa": empresa,
                "area": area,
                "tipo_tarea": tipo_tarea,
                "descripcion": descripcion,
                "observaciones": observaciones,
                "gerencia": gerencia,
                "lugar": lugar,
                "secuencia": [item["secuencia"] for item in riesgos],
                "riesgo": [item["riesgo"] for item in riesgos],
                "control": [item["control"] for item in riesgos],
            },
            user.get("username", ""),
        )
        condiciones_supervisor = await _leer_condiciones_supervisor(request)
    except HTTPException as exc:
        return validation_error(str(exc.detail))

    archivos = registro_existente.get("evidencia", []).copy()
    for archivo in evidencia or []:
        if not archivo.filename:
            continue
        try:
            archivos.append(await save_art_image(request.app.state.art_upload_dir, archivo))
        except HTTPException as exc:
            return validation_error(f"Evidencia: {exc.detail}")
        
    registro_actualizado = {
        "empresa": empresa,
        "trabajador": trabajador,
        "area": area,
        "fecha": registro_existente.get("fecha"),
        "tipo_tarea": tipo_tarea,
        "descripcion": descripcion,
        "supervisor": supervisor,
        "checklist": registro_existente.get("checklist", []),
        "epp": registro_existente.get("epp", []),
        "riesgos": riesgos,
        "observaciones": observaciones,
        "evidencia": archivos,
        "asignado_a": registro_existente.get("asignado_a") or user["username"],
        "supervisor_asignado": supervisor_asignado,
        "gerencia": gerencia.strip(),
        "hora_inicio": hora_inicio.strip(),
        "hora_termino": hora_termino.strip(),
        "lugar": lugar.strip(),
        "reglas_vida": reglas_seleccionadas,
        "supervisor_condiciones": condiciones_supervisor,
    }

    actualizar_registro(id_art, registro_actualizado)
    resetear_validaciones_trabajadores(id_art)
    return RedirectResponse(f"/art/{id_art}", status_code=303)


@router.post("/art/{id_art}/validar")
def validar_art_trabajador(
    request: Request,
    id_art: str,
    condicion_ok: str = Form(...),
    observacion_validacion: str = Form(""),
    csrf_token: str = Form(...),
    user=Depends(get_current_user),
):
    if not user:
        return RedirectResponse("/login", status_code=303)
    validate_csrf_token(request, csrf_token)
    registro = obtener_registro(id_art)
    if not registro:
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    if not _puede_validar_art(registro, user):
        raise HTTPException(status_code=403, detail="No tienes permiso para validar esta ART")
    if condicion_ok not in {"si", "no"}:
        raise HTTPException(status_code=400, detail="Debes validar tus condiciones físicas y psicológicas")
    validate_clean_fields({"observacion_validacion": observacion_validacion}, user.get("username", ""))
    condicion_es_ok = condicion_ok == "si"
    validado_en = datetime.now().strftime("%Y-%m-%d %H:%M")
    validar_trabajador_art(
        id_art,
        user["username"],
        condicion_es_ok,
        observacion_validacion.strip(),
        validado_en,
    )
    if not condicion_es_ok and registro.get("supervisor_asignado"):
        add_notification(
            registro["supervisor_asignado"],
            f"ART {id_art} requiere atención",
            f"{user.get('nombre') or user.get('username')} indicó que no está en condiciones de realizar el trabajo.",
            f"/art/{id_art}",
        )
    return RedirectResponse(f"/art/{id_art}", status_code=303)


@router.get("/art/{id_art}/pdf")
def descargar_art_pdf(id_art: str, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login", status_code=303)
    registro = obtener_registro(id_art)
    if not registro:
        raise HTTPException(status_code=404, detail="ART no encontrada")
    if not _puede_descargar_pdf_general(registro, user):
        raise HTTPException(status_code=403, detail="No tienes permiso para descargar este PDF")
    pdf = generar_art_pdf(registro)  # registro ya trae sus asignaciones
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="art-{id_art}.pdf"'},
    )


@router.post("/art/{id_art}/eliminar")
def borrar_art(
    request: Request,
    id_art: str,
    csrf_token: str = Form(...),
    user=Depends(get_current_user),
):
    if not user:
        return RedirectResponse("/login", status_code=303)
    validate_csrf_token(request, csrf_token)
    registro = obtener_registro(id_art)
    if not registro:
        return RedirectResponse("/dashboard", status_code=303)
    es_admin = user.get("rol") == "admin"
    es_creador = registro.get("creado_por") == user["username"]
    if not es_admin and not es_creador:
        raise HTTPException(status_code=403, detail="No tienes permiso para eliminar esta ART")
    if not es_admin and registro.get("estado") not in {"pendiente", "rechazada"}:
        raise HTTPException(status_code=400, detail="Esta ART no puede eliminarse en su estado actual")
    eliminar_registro(id_art)
    return RedirectResponse("/dashboard", status_code=303)

@router.get("/partials/riesgo-row", response_class=HTMLResponse)
def agregar_fila_riesgo(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="partials/riesgo_row.html"
    )
