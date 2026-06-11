from datetime import datetime
from typing import List, Optional
import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from backend.src.config.settings import settings
from backend.src.config.frontend import templates
from backend.src.middleware.auth import get_current_user
from backend.src.middleware.csrf import create_csrf_token, set_csrf_cookie, validate_csrf_token
from backend.src.roles import SUPERVISOR, USER, can_review_art
from backend.src.services.art_service import (
    cargar_asignaciones_art,
    cargar_asignaciones_por_trabajador,
    cargar_registros,
    cargar_registros_por_supervisor,
    cargar_registros_por_usuario,
    eliminar_registro,
    guardar_registro,
    obtener_registro,
    actualizar_registro,
    actualizar_revision_asignacion,
    guardar_asignaciones_art,
    guardar_respuesta_asignacion,
    guardar_respuesta_asignacion_por_id,
    marcar_envio_asignacion,
    obtener_asignacion_art,
    obtener_asignacion_para_trabajador,
    obtener_asignacion_por_token,
    preparar_envio_asignacion,
)
from backend.src.services.email_service import build_art_assignment_email, send_email
from backend.src.services.pdf_service import generar_art_pdf
from backend.src.services.upload_service import save_art_image
from backend.src.services.usuario_service import cargar_usuarios_por_rol


router = APIRouter()

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

MIN_TRABAJADORES_ART = 6
ANSWERED_ASSIGNMENT_STATES = {"respondido", "con_observacion", "aprobado", "observado", "rechazado"}

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


def _trabajadores_activos() -> list[dict]:
    return [
        trabajador
        for trabajador in cargar_usuarios_por_rol(USER)
        if (trabajador.get("estado_cuenta") or "activo") == "activo"
    ]


def _base_url(request: Request) -> str:
    return (settings.public_base_url or str(request.base_url).rstrip("/")).rstrip("/")


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
    respuestas: list[dict] = []
    observaciones_por_pregunta: dict[str, str] = {}
    con_observacion = bool(observaciones.strip())
    for pregunta in _WORKER_QUESTIONS:
        respuesta = str(form.get(f"respuesta_{pregunta['id']}", "")).strip().lower()
        if respuesta not in {"si", "no", "na"}:
            raise HTTPException(status_code=400, detail="Debes responder todas las preguntas obligatorias.")
        obs = str(form.get(f"observacion_{pregunta['id']}", "")).strip()
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


def _es_trabajador_asignado(registro: dict, user: dict) -> bool:
    if user.get("rol") != USER:
        return False
    username = user.get("username", "")
    email = (user.get("email") or "").strip().lower()
    return any(
        str(asignacion.get("trabajador_id")) == str(user.get("id"))
        or (email and (asignacion.get("email") or "").strip().lower() == email)
        or (username and (asignacion.get("username") or "") == username)
        for asignacion in registro.get("asignaciones", [])
    )


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
        registros = cargar_registros_por_usuario(user["username"], limite=10, con_asignaciones=False)
        art_asignadas = cargar_asignaciones_por_trabajador(user["id"], limite=5)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"request": request, "user": user, "registros": registros, "art_asignadas": art_asignadas},
    )


@router.get("/mis-art-asignadas", response_class=HTMLResponse)
def mis_art_asignadas(request: Request, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user.get("rol") != USER:
        return RedirectResponse("/dashboard", status_code=303)
    art_asignadas = cargar_asignaciones_por_trabajador(user["id"])
    return templates.TemplateResponse(
        request,
        "mis_art_asignadas.html",
        {"request": request, "user": user, "art_asignadas": art_asignadas},
    )


@router.get("/art/nueva", response_class=HTMLResponse)
def nueva_art(request: Request, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login", status_code=303)
    if not _puede_crear_art(user):
        raise HTTPException(status_code=403, detail="No tienes permisos para crear ART. Solo puedes completar ART asignadas.")
    csrf_token = create_csrf_token()
    trabajadores = _trabajadores_activos()
    response = templates.TemplateResponse(
        request,
        "nueva_art.html",
        {
            "request": request,
            "user": user,
            "trabajadores": trabajadores,
            "min_trabajadores": MIN_TRABAJADORES_ART,
            "fecha_actual": datetime.now().strftime("%Y-%m-%d"),
            "csrf_token": csrf_token,
        },
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
    trabajadores_asignados: Optional[List[str]] = Form(None),
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
    if not _puede_crear_art(user):
        raise HTTPException(status_code=403, detail="No tienes permisos para crear ART. Solo puedes completar ART asignadas.")
    trabajadores_ids = list(dict.fromkeys(trabajadores_asignados or []))
    if len(trabajadores_ids) < MIN_TRABAJADORES_ART:
        raise HTTPException(status_code=400, detail="Debes asignar al menos 6 trabajadores distintos a la ART.")
    if not observaciones.strip():
        raise HTTPException(status_code=400, detail="Debes ingresar observaciones generales")
    trabajadores_disponibles = {str(t["id"]): t for t in _trabajadores_activos()}
    trabajadores = [trabajadores_disponibles[item] for item in trabajadores_ids if item in trabajadores_disponibles]
    if len(trabajadores) < MIN_TRABAJADORES_ART:
        raise HTTPException(status_code=400, detail="Debes asignar al menos 6 trabajadores distintos a la ART.")
    supervisor = user.get("nombre") or user.get("email") or user["username"]
    trabajador_resumen = f"{len(trabajadores)} trabajadores asignados"
    riesgos = []
    for seq, risk, ctrl in zip(secuencia or [], riesgo or [], control or []):
        if seq.strip() or risk.strip() or ctrl.strip():
            riesgos.append({"secuencia": seq.strip(), "riesgo": risk.strip(), "control": ctrl.strip()})
    if not riesgos or any(not item["secuencia"] or not item["riesgo"] or not item["control"] for item in riesgos):
        raise HTTPException(status_code=400, detail="Debes completar secuencia, riesgo y control")
    archivos = []
    for archivo in evidencia or []:
        if not archivo.filename:
            continue
        archivos.append(await save_art_image(request.app.state.art_upload_dir, archivo))
    id_art = str(uuid.uuid4())[:8]
    guardar_registro(
        {
            "id": id_art,
            "empresa": empresa,
            "trabajador": trabajador_resumen,
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
            "asignado_a": "",
            "supervisor_asignado": user["username"],
        }
    )
    guardar_asignaciones_art(id_art, trabajadores)
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
    links_prueba: list[dict[str, str]] = []
    base_url = _base_url(request)
    for asignacion in asignaciones:
        preparada = preparar_envio_asignacion(asignacion["id"])
        if not preparada:
            continue
        link = f"{base_url}/art/trabajador/{preparada['token_acceso']}"
        if not settings.email_enabled:
            marcar_envio_asignacion(preparada["id"], "enlace_generado")
            links_prueba.append({"nombre": preparada.get("nombre", "Trabajador"), "link": link})
            continue
        subject, html_body, text_body = build_art_assignment_email(link, registro, preparada.get("nombre", ""))
        enviado = send_email(preparada.get("email", ""), subject, html_body, text_body)
        if enviado:
            enviados += 1
            marcar_envio_asignacion(preparada["id"], "enviado")
        else:
            fallidos += 1
            marcar_envio_asignacion(preparada["id"], "envio_fallido")

    message = f"Correos enviados: {enviados}. Correos no enviados: {fallidos}. Total asignados: {len(asignaciones)}."
    if links_prueba:
        message += " Modo prueba: links generados."
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
    if not settings.email_enabled:
        marcar_envio_asignacion(preparada["id"], "enlace_generado")
        message = f"Modo prueba: link generado para {preparada.get('nombre', 'trabajador')}: {link}"
        return RedirectResponse(f"/art/{id_art}?mensaje={quote(message)}", status_code=303)
    subject, html_body, text_body = build_art_assignment_email(link, registro, preparada.get("nombre", ""))
    enviado = send_email(preparada.get("email", ""), subject, html_body, text_body)
    marcar_envio_asignacion(preparada["id"], "enviado" if enviado else "envio_fallido")
    message = "Correo enviado correctamente." if enviado else f"No se pudo enviar el correo. Link de prueba: {link}"
    return RedirectResponse(f"/art/{id_art}?mensaje={quote(message)}", status_code=303)


@router.get("/art/trabajador/{token}", response_class=HTMLResponse)
def formulario_trabajador_token(request: Request, token: str):
    asignacion = obtener_asignacion_por_token(token)
    if not asignacion:
        raise HTTPException(status_code=404, detail="El enlace de ART no existe.")
    registro = obtener_registro(asignacion["art_id"])
    if not registro:
        raise HTTPException(status_code=404, detail="La ART asociada no existe.")
    if asignacion.get("estado_respuesta") in ANSWERED_ASSIGNMENT_STATES:
        return templates.TemplateResponse(
            request,
            "art_trabajador_gracias.html",
            {"request": request, "user": None, "registro": registro, "asignacion": asignacion},
        )
    expires_at = asignacion.get("token_expires_at")
    if expires_at and expires_at < datetime.now():
        raise HTTPException(status_code=403, detail="El enlace de ART expiró. Solicita un reenvío al supervisor.")
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
    asignacion = obtener_asignacion_por_token(token)
    if not asignacion:
        raise HTTPException(status_code=404, detail="El enlace de ART no existe.")
    if asignacion.get("estado_respuesta") in ANSWERED_ASSIGNMENT_STATES:
        return RedirectResponse(f"/art/trabajador/{token}", status_code=303)
    expires_at = asignacion.get("token_expires_at")
    if expires_at and expires_at < datetime.now():
        raise HTTPException(status_code=403, detail="El enlace de ART expiró. Solicita un reenvío al supervisor.")
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


@router.get("/art/{id_art}", response_class=HTMLResponse)
def detalle_art(request: Request, id_art: str, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login", status_code=303)
    registro = obtener_registro(id_art)
    if not registro:
        return RedirectResponse("/dashboard", status_code=303)
    supervisor_asignado = _es_supervisor_asignado(registro, user)
    trabajador_asignado = _es_trabajador_asignado(registro, user)
    if not supervisor_asignado and not trabajador_asignado and user.get("rol") != "admin" and registro.get("creado_por") != user["username"]:
        return RedirectResponse("/dashboard", status_code=303)
    if user.get("rol") == SUPERVISOR and not supervisor_asignado:
        return RedirectResponse("/dashboard", status_code=303)
    csrf_token = create_csrf_token()
    # Only allow supervisor to review if assigned AND the ART is not already approved/rejected
    puede_revisar = supervisor_asignado and registro.get("estado") not in {"aprobada", "rechazada"}
    response = templates.TemplateResponse(
        request,
        "detalle_art.html",
        {
            "request": request,
            "registro": registro,
            "user": user,
            "csrf_token": csrf_token,
            "puede_revisar": puede_revisar,
            "puede_descargar_pdf": registro.get("estado") in {"aprobada", "rechazada"},
            "mensaje": request.query_params.get("mensaje", ""),
            "min_trabajadores": MIN_TRABAJADORES_ART,
            "email_enabled": settings.email_enabled,
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
    estados_validos = {"respondido", "con_observacion", "aprobado", "observado", "rechazado"}
    if resultado not in estados_validos:
        raise HTTPException(status_code=400, detail="Resultado de revisión inválido")
    if resultado in {"observado", "rechazado"} and not comentario_revision.strip():
        raise HTTPException(status_code=400, detail="El comentario es obligatorio al observar o rechazar.")
    actualizar_revision_asignacion(id_asignacion, resultado, comentario_revision.strip(), user["id"])
    return RedirectResponse(f"/art/{id_art}/respuesta/{id_asignacion}", status_code=303)


@router.get("/art/{id_art}/editar", response_class=HTMLResponse)
def editar_art_view(request: Request, id_art: str, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login", status_code=303)
    registro = obtener_registro(id_art)
    if not registro:
        return RedirectResponse("/dashboard", status_code=303)
    
    if registro.get("creado_por") != user["username"]:
        return RedirectResponse("/dashboard", status_code=303)
    if registro.get("estado") not in {"pendiente", "corregir"}:
        return RedirectResponse(f"/art/{id_art}", status_code=303)
        
    csrf_token = create_csrf_token()
    supervisores = cargar_usuarios_por_rol(SUPERVISOR)
    
    response = templates.TemplateResponse(
        request,
        "editar_art.html",
        {
            "request": request,
            "checklist": _CHECKLIST,
            "epp": _EPP,
            "user": user,
            "supervisores": supervisores,
            "csrf_token": csrf_token,
            "registro": registro,
        },
    )
    set_csrf_cookie(response, csrf_token)
    return response


@router.post("/art/{id_art}/editar")
async def editar_art_post(
    request: Request,
    id_art: str,
    empresa: str = Form(...),
    area: str = Form(...),
    tipo_tarea: str = Form(...),
    descripcion: str = Form(...),
    supervisor_asignado: str = Form(...),
    checklist: Optional[List[str]] = Form(None),
    epp: Optional[List[str]] = Form(None),
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
    if registro_existente.get("creado_por") != user["username"]:
        raise HTTPException(status_code=403, detail="No tienes permiso para editar esta ART")
    if registro_existente.get("estado") not in {"pendiente", "corregir"}:
        raise HTTPException(status_code=400, detail="Esta ART no se puede editar en su estado actual")
        
    if len(checklist or []) != len(_CHECKLIST):
        raise HTTPException(status_code=400, detail="Debes completar todo el checklist de seguridad")
    if not epp:
        raise HTTPException(status_code=400, detail="Debes seleccionar al menos un EPP")
    if not observaciones.strip():
        raise HTTPException(status_code=400, detail="Debes ingresar observaciones")
        
    supervisor_user = next((u for u in cargar_usuarios_por_rol(SUPERVISOR) if u["username"] == supervisor_asignado), None)
    trabajador = registro_existente.get("trabajador") or user.get("nombre") or user["username"]
    supervisor = (supervisor_user or {}).get("nombre") or supervisor_asignado
    
    riesgos = []
    for seq, risk, ctrl in zip(secuencia or [], riesgo or [], control or []):
        if seq.strip() or risk.strip() or ctrl.strip():
            riesgos.append({"secuencia": seq.strip(), "riesgo": risk.strip(), "control": ctrl.strip()})
    if not riesgos or any(not item["secuencia"] or not item["riesgo"] or not item["control"] for item in riesgos):
        raise HTTPException(status_code=400, detail="Debes completar secuencia, riesgo y control")
        
    archivos = registro_existente.get("evidencia", []).copy()
    for archivo in evidencia or []:
        if not archivo.filename:
            continue
        archivos.append(await save_art_image(request.app.state.art_upload_dir, archivo))
        
    registro_actualizado = {
        "empresa": empresa,
        "trabajador": trabajador,
        "area": area,
        "fecha": registro_existente.get("fecha"),
        "tipo_tarea": tipo_tarea,
        "descripcion": descripcion,
        "supervisor": supervisor,
        "checklist": checklist or [],
        "epp": epp or [],
        "riesgos": riesgos,
        "observaciones": observaciones,
        "evidencia": archivos,
        "asignado_a": registro_existente.get("asignado_a") or user["username"],
        "supervisor_asignado": supervisor_asignado,
    }
    
    actualizar_registro(id_art, registro_actualizado)
    return RedirectResponse(f"/art/{id_art}", status_code=303)


@router.get("/art/{id_art}/pdf")
def descargar_art_pdf(id_art: str, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login", status_code=303)
    registro = obtener_registro(id_art)
    if not registro:
        return RedirectResponse("/dashboard", status_code=303)
    supervisor_asignado = _es_supervisor_asignado(registro, user)
    if not supervisor_asignado and user.get("rol") != "admin" and registro.get("creado_por") != user["username"]:
        return RedirectResponse("/dashboard", status_code=303)
    if user.get("rol") == SUPERVISOR and not supervisor_asignado:
        return RedirectResponse("/dashboard", status_code=303)
    if registro.get("estado") not in {"aprobada", "rechazada"}:
        raise HTTPException(status_code=400, detail="El PDF estará disponible cuando la ART sea aprobada o rechazada")
    pdf = generar_art_pdf(registro)
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
    if not es_admin and registro.get("estado") not in {"pendiente", "corregir", "rechazada"}:
        raise HTTPException(status_code=400, detail="Esta ART no puede eliminarse en su estado actual")
    eliminar_registro(id_art)
    return RedirectResponse("/dashboard", status_code=303)

@router.get("/partials/riesgo-row", response_class=HTMLResponse)
def agregar_fila_riesgo(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="partials/riesgo_row.html"
    )
