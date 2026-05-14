from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from backend.src.config.frontend import templates
from backend.src.middleware.auth import get_current_user, pwd_context
from backend.src.services.usuario_service import actualizar_perfil, actualizar_password

router = APIRouter()


@router.get("/perfil", response_class=HTMLResponse)
def perfil_form(request: Request, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request, "profile.html", {"request": request, "user": user, "title": "Mi perfil"})


@router.post("/perfil")
def perfil_update(
    request: Request,
    nombre: str = Form(""),
    email: str = Form(""),
    password: str = Form(""),
    user=Depends(get_current_user),
):
    if not user:
        return RedirectResponse("/login", status_code=303)
    if nombre or email:
        actualizar_perfil(user["username"], nombre, email)
    if password:
        actualizar_password(user["username"], pwd_context.hash(password))
    return RedirectResponse("/dashboard", status_code=303)
