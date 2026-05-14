from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from backend.src.config.frontend import templates
from backend.src.middleware.auth import pwd_context
from backend.src.services.usuario_service import obtener_usuario, guardar_usuario

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse(request, "login.html", {"request": request, "title": "Iniciar sesión"})


@router.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    user = obtener_usuario(username)
    if not user or not pwd_context.verify(password, user["password_hash"]):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"request": request, "error": "Usuario o contraseña incorrectos", "title": "Iniciar sesión"},
        )
    response = RedirectResponse("/", status_code=303)
    response.set_cookie("user", username)
    return response


@router.get("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("user")
    return response


@router.get("/registro", response_class=HTMLResponse)
def registro_form(request: Request):
    return templates.TemplateResponse(request, "registro.html", {"request": request, "title": "Crear cuenta"})


@router.post("/registro")
def registro(request: Request, username: str = Form(...), password: str = Form(...), rol: str = Form(...)):
    if obtener_usuario(username):
        return templates.TemplateResponse(
            request,
            "registro.html",
            {"request": request, "error": "El usuario ya existe", "title": "Crear cuenta"},
        )
    guardar_usuario(username, pwd_context.hash(password), rol)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie("user", username)
    return response
