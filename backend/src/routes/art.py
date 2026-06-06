from datetime import datetime
from typing import List, Optional
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from backend.src.config.frontend import templates
from backend.src.middleware.auth import get_current_user
from backend.src.middleware.csrf import create_csrf_token, set_csrf_cookie, validate_csrf_token
from backend.src.roles import SUPERVISOR, can_create_art
from backend.src.services.art_service import (
    cargar_registros,
    cargar_registros_por_supervisor,
    cargar_registros_por_usuario,
    cargar_trabajadores_art,
    eliminar_registro,
    guardar_registro,
    guardar_trabajadores_art,
    obtener_trabajador_art,
    obtener_registro,
    actualizar_registro,
    validar_trabajador_art,
    resetear_validaciones_trabajadores,
)
from backend.src.services.pdf_service import generar_art_pdf
from backend.src.services.upload_service import save_art_image
from backend.src.services.usuario_service import cargar_usuarios_asignables, cargar_usuarios_por_rol
from backend.src.services.notification_service import add_notification


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
        registros = cargar_registros()
    elif user.get("rol") == SUPERVISOR:
        registros = cargar_registros_por_supervisor(user["username"])
    else:
        registros = cargar_registros_por_usuario(user["username"])
    art_asignadas = []
    if user.get("rol") not in {"admin", SUPERVISOR}:
        for registro in registros:
            validacion = obtener_trabajador_art(registro["id"], user["username"])
            if validacion:
                registro["validacion_trabajador"] = validacion
                art_asignadas.append(registro)
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
    csrf_token = create_csrf_token()
    trabajadores = _usuarios_asignables()
    response = templates.TemplateResponse(
        request,
        "nueva_art.html",
        {
            "request": request,
            "checklist": _CHECKLIST,
            "epp": _EPP,
            "user": user,
            "trabajadores": trabajadores,
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
    trabajador_asignado: List[str] = Form(...),
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
    if not can_create_art(user.get("rol", "")):
        raise HTTPException(status_code=403, detail="No tienes permiso para crear ART")
    validate_csrf_token(request, csrf_token)
    usernames_asignados = list(dict.fromkeys(trabajador_asignado))
    trabajadores_disponibles = _usuarios_asignables()
    trabajadores_asignados = [
        trabajador for trabajador in trabajadores_disponibles if trabajador["username"] in usernames_asignados
    ]
    if not trabajadores_asignados:
        raise HTTPException(status_code=400, detail="Debes seleccionar al menos un trabajador registrado")
    if len(checklist or []) != len(_CHECKLIST):
        raise HTTPException(status_code=400, detail="Debes completar todo el checklist de seguridad")
    if not epp:
        raise HTTPException(status_code=400, detail="Debes seleccionar al menos un EPP")
    if not observaciones.strip():
        raise HTTPException(status_code=400, detail="Debes ingresar observaciones")
    if not evidencia:
        raise HTTPException(status_code=400, detail="Debes adjuntar al menos una imagen de evidencia")
    supervisor_user = next((u for u in cargar_usuarios_por_rol(SUPERVISOR) if u["username"] == supervisor_asignado), None)
    trabajador = ", ".join(
        trabajador_user.get("nombre") or trabajador_user.get("email") or trabajador_user["username"]
        for trabajador_user in trabajadores_asignados
    )
    supervisor = (supervisor_user or {}).get("nombre") or supervisor_asignado
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
    registro = {
        "id": id_art,
        "empresa": empresa,
        "trabajador": trabajador,
        "area": area,
        "fecha": datetime.now().strftime("%Y-%m-%d"),
        "tipo_tarea": tipo_tarea,
        "descripcion": descripcion,
        "supervisor": supervisor,
        "checklist": checklist or [],
        "epp": epp or [],
        "riesgos": riesgos,
        "observaciones": observaciones,
        "evidencia": archivos,
        "creado_en": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "creado_por": user["username"],
        "asignado_a": trabajadores_asignados[0]["username"],
        "supervisor_asignado": supervisor_asignado,
    }
    guardar_registro(registro)
    guardar_trabajadores_art(id_art, trabajadores_asignados)
    for trabajador_user in trabajadores_asignados:
        add_notification(
            trabajador_user["username"],
            f"ART {id_art} asignada",
            f"{user.get('nombre') or user.get('username')} te asignó una ART para completar y validar.",
            f"/art/{id_art}",
        )
    return RedirectResponse(f"/art/{id_art}", status_code=303)


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
            "puede_descargar_pdf": registro.get("estado") in {"aprobada", "rechazada"},
            "trabajadores_art": trabajadores_art,
            "validacion_actual": validacion_actual,
            "todos_validados": todos_validados,
        },
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
    
    response = templates.TemplateResponse(
        request,
        "editar_art.html",
        {
            "request": request,
            "checklist": _CHECKLIST,
            "epp": _EPP,
            "user": user,
            "csrf_token": csrf_token,
            "registro": registro,
            "validacion_actual": None,
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
    if not _puede_editar_art(registro_existente, user):
        raise HTTPException(status_code=403, detail="No tienes permiso para editar esta ART")
        
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
        return RedirectResponse("/dashboard", status_code=303)
    supervisor_asignado = _es_supervisor_asignado(registro, user)
    if not _puede_ver_art(registro, user):
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
