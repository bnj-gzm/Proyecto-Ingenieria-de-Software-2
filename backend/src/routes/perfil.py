import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from backend.src.config.frontend import templates
from backend.src.middleware.auth import get_current_user, pwd_context
from backend.src.middleware.csrf import create_csrf_token, set_csrf_cookie, validate_csrf_token
from backend.src.services.usuario_service import actualizar_foto_perfil, actualizar_password, actualizar_perfil, obtener_usuario
from backend.src.services.validation_service import normalizar_telefono_chile, validar_telefono_chile
from backend.src.services.art_service import cargar_registros_por_usuario
from backend.src.services.notification_service import get_notifications
from backend.src.services.notification_service import mark_read

router = APIRouter()
MAX_PROFILE_IMAGE_BYTES = 2 * 1024 * 1024
ALLOWED_PROFILE_EXTENSIONS = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP"}


def _initials(user: dict) -> str:
    source = (user.get("nombre") or user.get("username") or "Usuario").strip()
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


def _safe_profile_path(base_dir: Path, stored_path: str) -> Path | None:
    if not stored_path:
        return None
    filename = Path(stored_path).name
    candidate = (base_dir / filename).resolve()
    base = base_dir.resolve()
    if base not in candidate.parents and candidate != base:
        return None
    return candidate


async def _guardar_foto_perfil(request: Request, archivo: UploadFile, user: dict) -> str:
    original_name = archivo.filename or ""
    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_PROFILE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="La foto debe ser JPG, PNG o WEBP")
    contenido = await archivo.read()
    if not contenido:
        return user.get("foto_perfil") or ""
    if len(contenido) > MAX_PROFILE_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="La foto debe pesar máximo 2 MB")
    try:
        from PIL import Image
        import io

        image = Image.open(io.BytesIO(contenido))
        image.verify()
        if image.format != ALLOWED_PROFILE_EXTENSIONS[extension]:
            raise HTTPException(status_code=400, detail="El contenido de la imagen no coincide con su extensión")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail="La foto no parece ser una imagen válida") from exc
    upload_dir = request.app.state.profile_upload_dir
    filename = f"{uuid.uuid4().hex}{extension}"
    (upload_dir / filename).write_bytes(contenido)
    anterior = _safe_profile_path(upload_dir, user.get("foto_perfil") or "")
    if anterior and anterior.exists():
        anterior.unlink()
    return f"uploads/perfiles/{filename}"


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


@router.post("/perfil/editar")
async def perfil_update(
    request: Request,
    nombre: str = Form(...),
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
    telefono = telefono.strip()
    cargo = cargo.strip()
    if not nombre:
        return _render_profile_edit(request, user, error="El nombre no puede estar vacío.")
    if telefono and not validar_telefono_chile(telefono):
        return _render_profile_edit(request, user, error="El teléfono debe tener formato chileno válido: +56 9 XXXX XXXX.")
    telefono = normalizar_telefono_chile(telefono)
    nueva_foto = user.get("foto_perfil") or ""
    try:
        if foto_perfil and foto_perfil.filename:
            nueva_foto = await _guardar_foto_perfil(request, foto_perfil, user)
    except HTTPException as exc:
        return _render_profile_edit(request, user, error=str(exc.detail))
    actualizar_perfil(user["username"], nombre, telefono, cargo)
    if nueva_foto != (user.get("foto_perfil") or ""):
        actualizar_foto_perfil(user["username"], nueva_foto)
    if password:
        if len(password) < 8:
            fresh_user = obtener_usuario(user["username"]) or user
            return _render_profile_edit(request, fresh_user, error="La contraseña debe tener al menos 8 caracteres.")
        if password != password_confirm:
            fresh_user = obtener_usuario(user["username"]) or user
            return _render_profile_edit(request, fresh_user, error="Las contraseñas no coinciden.")
        actualizar_password(user["username"], pwd_context.hash(password))
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
    upload_dir = request.app.state.profile_upload_dir
    foto = _safe_profile_path(upload_dir, user.get("foto_perfil") or "")
    if foto and foto.exists():
        foto.unlink()
    actualizar_foto_perfil(user["username"], "")
    return RedirectResponse("/perfil/editar", status_code=303)
