from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from backend.src.config.frontend import templates
from backend.src.middleware.auth import get_current_user, pwd_context
from backend.src.middleware.csrf import create_csrf_token, set_csrf_cookie, validate_csrf_token
from backend.src.services.usuario_service import actualizar_foto_perfil, actualizar_password, actualizar_perfil, nombre_completo
from backend.src.services.password_policy import validate_password_strength
from backend.src.services.validation_service import normalizar_telefono_chile, validar_telefono_chile
from backend.src.services.content_filter import PROHIBITED_LANGUAGE_MESSAGE, validate_clean_fields
from backend.src.services.art_service import cargar_registros_por_usuario
from backend.src.services.notification_service import get_notifications
from backend.src.services.notification_service import mark_read
from backend.src.services.upload_service import save_art_image

router = APIRouter()
MAX_PROFILE_IMAGE_BYTES = 2 * 1024 * 1024


def _initials(user: dict) -> str:
    source = (user.get("nombre_completo") or user.get("nombre") or user.get("username") or "Usuario").strip()
    parts = [part for part in source.split() if part]
    if len(parts) >= 2:
        return f"{parts[0][0]}{parts[1][0]}".upper()
    return source[:2].upper()


def _render_profile_edit(request: Request, user: dict, error: str | None = None, message: str | None = None):
    csrf_token = create_csrf_token()
    response = templates.TemplateResponse(
        request,
        "profile_edit.html",
        {
            "request": request,
            "user": user,
            "title": "Editar perfil",
            "csrf_token": csrf_token,
            "error": error,
            "message": message,
            "initials": _initials(user),
        },
    )
    set_csrf_cookie(response, csrf_token)
    return response


async def _guardar_foto_perfil(request: Request, archivo: UploadFile, user: dict) -> str:
    if not archivo.filename:
        return user.get("foto_perfil") or ""
    imagen = await save_art_image(
        request.app.state.profile_upload_dir,
        archivo,
        max_bytes=MAX_PROFILE_IMAGE_BYTES,
        max_dimensions=(768, 768),
    )
    return imagen["src"]


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
            "initials": _initials(user),
        },
    )
    set_csrf_cookie(response, csrf_token)
    return response


@router.get("/perfil/editar", response_class=HTMLResponse)
def perfil_editar_form(request: Request, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login", status_code=303)
    return _render_profile_edit(request, user)


@router.get("/notificaciones", response_class=HTMLResponse)
@router.get("/notifications", response_class=HTMLResponse)
def ver_notificaciones(request: Request, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login", status_code=303)
    notificaciones = get_notifications(user["username"])
    csrf_token = create_csrf_token()
    response = templates.TemplateResponse(
        request,
        "notificaciones.html",
        {"request": request, "user": user, "notificaciones": notificaciones, "title": "Notificaciones", "csrf_token": csrf_token},
    )
    set_csrf_cookie(response, csrf_token)
    return response


def _profile_error(request: Request, user: dict, message: str, status_code: int = 400):
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JSONResponse({"ok": False, "message": message}, status_code=status_code)
    return _render_profile_edit(request, user, error=message)


@router.get("/api/notificaciones")
@router.get("/api/notifications")
def api_notificaciones(user=Depends(get_current_user)):
    if not user:
        return JSONResponse({"notifications": [], "unread_count": 0}, status_code=401)
    notifications = get_notifications(user["username"], limit=20)
    return {
        "notifications": notifications,
        "unread_count": sum(1 for notification in notifications if not notification.get("read")),
    }


@router.post("/notificaciones/{id}/leer")
def marcar_notificacion_leida(request: Request, id: str, csrf_token: str = Form(...), user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login", status_code=303)
    try:
        validate_csrf_token(request, csrf_token)
        mark_read(id, user["username"])
    except Exception:
        pass
    return RedirectResponse("/notificaciones", status_code=303)


@router.post("/perfil/editar")
async def perfil_update(
    request: Request,
    nombre: str = Form(...),
    apellido: str = Form(""),
    telefono: str = Form(""),
    cargo: str = Form(""),
    password: str = Form(""),
    password_confirm: str = Form(""),
    foto_perfil: UploadFile | None = File(None),
    csrf_token: str = Form(...),
    user=Depends(get_current_user),
):
    if not user:
        return RedirectResponse("/login", status_code=303)
    validate_csrf_token(request, csrf_token)
    nombre = nombre.strip()
    apellido = apellido.strip()
    telefono = telefono.strip()
    cargo = cargo.strip()
    if not nombre:
        return _profile_error(request, user, "El nombre no puede estar vacío.")
    try:
        validate_clean_fields({"nombre": nombre, "apellido": apellido, "cargo": cargo}, user.get("username", ""))
    except HTTPException:
        return _profile_error(request, user, PROHIBITED_LANGUAGE_MESSAGE)
    if telefono and not validar_telefono_chile(telefono):
        return _profile_error(request, user, "El teléfono debe tener formato chileno válido: +56 9 XXXX XXXX.")
    telefono = normalizar_telefono_chile(telefono)
    if password:
        if password != password_confirm:
            return _profile_error(request, user, "Las contraseñas no coinciden.")
        password_ok, password_error = validate_password_strength(password)
        if not password_ok:
            return _profile_error(request, user, password_error)
    nueva_foto = user.get("foto_perfil") or ""
    try:
        if foto_perfil and foto_perfil.filename:
            nueva_foto = await _guardar_foto_perfil(request, foto_perfil, user)
    except HTTPException as exc:
        return _profile_error(request, user, str(exc.detail))
    actualizar_perfil(user["username"], nombre, apellido, telefono, cargo)
    if nueva_foto != (user.get("foto_perfil") or ""):
        actualizar_foto_perfil(user["username"], nueva_foto)
    if password:
        actualizar_password(user["username"], pwd_context.hash(password))
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JSONResponse(
            {
                "ok": True,
                "message": "Perfil actualizado correctamente.",
                "profile": {
                    "nombre": nombre,
                    "apellido": apellido,
                    "nombre_completo": nombre_completo({"nombre": nombre, "apellido": apellido, "username": user.get("username", "")}),
                    "telefono": telefono,
                    "cargo": cargo,
                    "foto_perfil": nueva_foto,
                },
            }
        )
    return RedirectResponse("/perfil", status_code=303)


@router.post("/perfil")
async def perfil_update_legacy(request: Request, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login", status_code=303)
    return RedirectResponse("/perfil/editar", status_code=303)


@router.post("/perfil/eliminar-foto")
def eliminar_foto_perfil(request: Request, csrf_token: str = Form(...), user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login", status_code=303)
    validate_csrf_token(request, csrf_token)
    actualizar_foto_perfil(user["username"], "")
    return RedirectResponse("/perfil/editar", status_code=303)
