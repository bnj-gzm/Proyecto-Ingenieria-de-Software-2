from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from backend.src.config.frontend import templates
from backend.src.middleware.auth import get_current_user
from backend.src.middleware.csrf import create_csrf_token, set_csrf_cookie, validate_csrf_token
from backend.src.roles import ROLE_LABELS, ROLES, SUPERVISOR, can_manage_users, can_review_art
from backend.src.services.art_service import cargar_registros, cargar_registros_por_supervisor, actualizar_revision_art, obtener_registro
from backend.src.services.usuario_service import actualizar_rol, cargar_usuarios
from backend.src.services.pdf_service import generar_art_pdf
from backend.src.services.notification_service import add_notification

router = APIRouter()


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


@router.get("/admin/art", response_class=HTMLResponse)
@router.get("/supervisor/art", response_class=HTMLResponse)
def admin_list_art(request: Request, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login", status_code=303)
    if not can_review_art(user.get("rol", "")):
        return RedirectResponse("/", status_code=303)
    registros = cargar_registros() if user.get("rol") == "admin" else cargar_registros_por_supervisor(user["username"])
    csrf_token = create_csrf_token()
    response = templates.TemplateResponse(
        request,
        "admin_art_list.html",
        {
            "request": request,
            "user": user,
            "registros": registros,
            "title": "Revisar ARTs",
            "csrf_token": csrf_token,
            "can_manage_users": can_manage_users(user.get("rol", "")),
        },
    )
    set_csrf_cookie(response, csrf_token)
    return response


@router.post("/admin/art/{id_art}/estado")
@router.post("/supervisor/art/{id_art}/estado")
def admin_change_estado(
    request: Request,
    id_art: str,
    estado: str = Form(...),
    comentario_supervisor: str = Form(""),
    csrf_token: str = Form(...),
    user=Depends(get_current_user),
):
    if not user:
        return RedirectResponse("/login", status_code=303)
    if not can_review_art(user.get("rol", "")):
        return RedirectResponse("/", status_code=303)
    validate_csrf_token(request, csrf_token)
    registro = obtener_registro(id_art)
    if not registro:
        return RedirectResponse("/supervisor/art", status_code=303)
    if not _es_supervisor_asignado(registro, user):
        return RedirectResponse("/dashboard", status_code=303)
    # Prevent changing estado once it's finalized
    if registro.get("estado") in {"aprobada", "rechazada"}:
        return RedirectResponse(f"/art/{id_art}", status_code=303)
    if estado not in {"pendiente", "aprobada", "rechazada", "corregir"}:
        raise HTTPException(status_code=400, detail="Estado de ART inválido")
    if estado in {"aprobada", "rechazada", "corregir"} and not comentario_supervisor.strip():
        raise HTTPException(status_code=400, detail="Debes ingresar un comentario de revisión")
    actualizar_revision_art(
        id_art,
        estado,
        comentario_supervisor.strip(),
        user["username"],
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    )
    # If resolved (approved/rejected), generate PDF backup into uploads
    if estado in {"aprobada", "rechazada"}:
        try:
            registro_actual = obtener_registro(id_art)
            pdf_bytes = generar_art_pdf(registro_actual)
            upload_dir = request.app.state.upload_dir
            (upload_dir / f"art-{id_art}.pdf").write_bytes(pdf_bytes)
            # notify the creator about the resolution
            try:
                creador = registro_actual.get("creado_por")
                if creador:
                    add_notification(
                        creador,
                        f"ART {id_art} {estado}",
                        comentario_supervisor.strip() or "Se actualizó el estado de la ART",
                    )
            except Exception:
                pass
        except Exception:
            # don't block the flow if PDF generation fails
            pass
    return RedirectResponse(f"/art/{id_art}", status_code=303)


@router.get("/admin/usuarios", response_class=HTMLResponse)
def admin_list_usuarios(request: Request, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login", status_code=303)
    if not can_manage_users(user.get("rol", "")):
        return RedirectResponse("/", status_code=303)
    csrf_token = create_csrf_token()
    response = templates.TemplateResponse(
        request,
        "admin_users.html",
        {
            "request": request,
            "user": user,
            "usuarios": cargar_usuarios(),
            "roles": ROLE_LABELS,
            "title": "Gestionar usuarios",
            "csrf_token": csrf_token,
        },
    )
    set_csrf_cookie(response, csrf_token)
    return response


@router.post("/admin/usuarios/{username}/rol")
def admin_update_rol(
    request: Request,
    username: str,
    rol: str = Form(...),
    csrf_token: str = Form(...),
    user=Depends(get_current_user),
):
    if not user:
        return RedirectResponse("/login", status_code=303)
    if not can_manage_users(user.get("rol", "")):
        return RedirectResponse("/", status_code=303)
    validate_csrf_token(request, csrf_token)
    if rol not in ROLES:
        raise HTTPException(status_code=400, detail="Rol inválido")
    if username == user["username"] and rol != "admin":
        raise HTTPException(status_code=400, detail="No puedes quitarte tu propio rol admin")
    actualizar_rol(username, rol)
    return RedirectResponse("/admin/usuarios", status_code=303)
