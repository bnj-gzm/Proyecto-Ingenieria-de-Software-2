from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from backend.src.config.frontend import templates
from backend.src.middleware.auth import get_current_user
from backend.src.services.art_service import cargar_registros, actualizar_estado_art

router = APIRouter()


@router.get("/admin/art", response_class=HTMLResponse)
def admin_list_art(request: Request, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user.get("rol") != "admin":
        return RedirectResponse("/", status_code=303)
    registros = cargar_registros()
    return templates.TemplateResponse(
        request,
        "admin_art_list.html",
        {"request": request, "user": user, "registros": registros, "title": "Revisar ARTs"},
    )


@router.post("/admin/art/{id_art}/estado")
def admin_change_estado(id_art: str, estado: str = Form(...), user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user.get("rol") != "admin":
        return RedirectResponse("/", status_code=303)
    actualizar_estado_art(id_art, estado)
    return RedirectResponse("/admin/art", status_code=303)
