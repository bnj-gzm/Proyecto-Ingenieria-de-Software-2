from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from backend.src.config.frontend import templates
from backend.src.middleware.auth import get_current_user, pwd_context
from backend.src.middleware.csrf import create_csrf_token, set_csrf_cookie, validate_csrf_token
from backend.src.services.usuario_service import actualizar_perfil, actualizar_password
from backend.src.services.art_service import cargar_registros_por_usuario
from backend.src.services.notification_service import get_notifications
from backend.src.services.notification_service import mark_read

router = APIRouter()


@router.get("/perfil", response_class=HTMLResponse)
def perfil_form(request: Request, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login", status_code=303)
    csrf_token = create_csrf_token()
    registros = cargar_registros_por_usuario(user["username"])
    notificaciones = get_notifications(user["username"])[:10]
    response = templates.TemplateResponse(
        request,
        "profile.html",
        {
            "request": request,
            "user": user,
            "title": "Mi perfil",
            "csrf_token": csrf_token,
            "registros": registros,
            "notificaciones": notificaciones,
        },
    )
    set_csrf_cookie(response, csrf_token)
    return response


@router.get("/notificaciones", response_class=HTMLResponse)
def ver_notificaciones(request: Request, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login", status_code=303)
    notificaciones = get_notifications(user["username"])
    return templates.TemplateResponse(
        request,
        "notificaciones.html",
        {"request": request, "user": user, "notificaciones": notificaciones, "title": "Notificaciones"},
    )


@router.post("/notificaciones/{id}/leer")
def marcar_notificacion_leida(request: Request, id: str, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login", status_code=303)
    try:
        mark_read(id, user["username"])
    except Exception:
        pass
    return RedirectResponse("/notificaciones", status_code=303)


@router.post("/perfil")
def perfil_update(
    request: Request,
    nombre: str = Form(""),
    email: str = Form(""),
    password: str = Form(""),
    csrf_token: str = Form(...),
    user=Depends(get_current_user),
):
    if not user:
        return RedirectResponse("/login", status_code=303)
    validate_csrf_token(request, csrf_token)
    if nombre or email:
        actualizar_perfil(user["username"], nombre, email)
    if password:
        actualizar_password(user["username"], pwd_context.hash(password))
    return RedirectResponse("/dashboard", status_code=303)
