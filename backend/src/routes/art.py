from datetime import datetime
from typing import List, Optional
import uuid

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from backend.src.config.frontend import templates
from backend.src.middleware.auth import get_current_user
from backend.src.services.art_service import cargar_registros, guardar_registro, obtener_registro

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
    registros = cargar_registros()
    return templates.TemplateResponse(
        request, "dashboard.html", {"request": request, "user": user, "registros": registros}
    )


@router.get("/art/nueva", response_class=HTMLResponse)
def nueva_art(request: Request, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        request, "nueva_art.html", {"request": request, "checklist": _CHECKLIST, "epp": _EPP, "user": user}
    )


@router.post("/art/guardar")
async def guardar_art(
    request: Request,
    empresa: str = Form(...),
    trabajador: str = Form(...),
    area: str = Form(...),
    fecha: str = Form(...),
    tipo_tarea: str = Form(...),
    descripcion: str = Form(...),
    supervisor: str = Form(...),
    checklist: Optional[List[str]] = Form(None),
    epp: Optional[List[str]] = Form(None),
    user=Depends(get_current_user),
):
    if not user:
        return RedirectResponse("/login", status_code=303)
    id_art = str(uuid.uuid4())[:8]
    guardar_registro(
        {
            "id": id_art,
            "empresa": empresa,
            "trabajador": trabajador,
            "area": area,
            "fecha": fecha,
            "tipo_tarea": tipo_tarea,
            "descripcion": descripcion,
            "supervisor": supervisor,
            "checklist": checklist or [],
            "epp": epp or [],
            "creado_en": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
    )
    return RedirectResponse(f"/art/{id_art}", status_code=303)


@router.get("/art/{id_art}", response_class=HTMLResponse)
def detalle_art(request: Request, id_art: str, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login", status_code=303)
    registro = obtener_registro(id_art)
    return templates.TemplateResponse(
        request, "detalle_art.html", {"request": request, "registro": registro, "user": user}
    )
