import re
import secrets

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from backend.src.config.frontend import templates
from backend.src.middleware.auth import create_access_token, delete_auth_cookie, pwd_context, set_auth_cookie
from backend.src.middleware.csrf import create_csrf_token, set_csrf_cookie, validate_csrf_token
from backend.src.services.usuario_service import guardar_usuario, obtener_usuario_por_email, username_existe

router = APIRouter()
USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,40}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _username_desde_email(email: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9_.-]", "", email.split("@", 1)[0].lower())[:30] or "usuario"
    username = base
    while username_existe(username):
        username = f"{base[:25]}-{secrets.token_hex(2)}"
    return username


def _render_login(request: Request, error: str | None = None):
    csrf_token = create_csrf_token()
    response = templates.TemplateResponse(
        request,
        "login.html",
        {"request": request, "title": "Iniciar sesión", "csrf_token": csrf_token, "error": error},
    )
    set_csrf_cookie(response, csrf_token)
    return response


def _render_registro(request: Request, error: str | None = None):
    csrf_token = create_csrf_token()
    response = templates.TemplateResponse(
        request,
        "registro.html",
        {"request": request, "title": "Crear cuenta", "csrf_token": csrf_token, "error": error},
    )
    set_csrf_cookie(response, csrf_token)
    return response


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return _render_login(request)


@router.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...), csrf_token: str = Form(...)):
    validate_csrf_token(request, csrf_token)
    email = email.strip().lower()
    if not EMAIL_RE.fullmatch(email):
        return _render_login(request, "Ingresa un correo electrónico válido")
    user = obtener_usuario_por_email(email)
    if not user or not pwd_context.verify(password, user["password_hash"]):
        return _render_login(request, "Correo o contraseña incorrectos")
    response = RedirectResponse("/dashboard", status_code=303)
    set_auth_cookie(response, create_access_token(user["username"]))
    return response


@router.get("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    delete_auth_cookie(response)
    return response


@router.get("/registro", response_class=HTMLResponse)
def registro_form(request: Request):
    return _render_registro(request)


@router.post("/registro")
def registro(
    request: Request,
    password: str = Form(...),
    nombre: str = Form(...),
    email: str = Form(...),
    rut: str = Form(""),
    telefono: str = Form(""),
    cargo: str = Form(""),
    empresa: str = Form(""),
    area: str = Form(""),
    csrf_token: str = Form(...),
):
    validate_csrf_token(request, csrf_token)
    email = email.strip().lower()
    username = _username_desde_email(email)
    if len(password) < 8:
        return _render_registro(request, "La contraseña debe tener al menos 8 caracteres")
    if not nombre.strip() or not email.strip():
        return _render_registro(request, "Nombre completo y email son obligatorios")
    if not EMAIL_RE.fullmatch(email):
        return _render_registro(request, "Ingresa un correo electrónico válido")
    if obtener_usuario_por_email(email):
        return _render_registro(request, "Ya existe una cuenta con ese correo")
    guardar_usuario(
        username,
        pwd_context.hash(password),
        "user",
        nombre.strip(),
        email.strip(),
        rut.strip(),
        telefono.strip(),
        cargo.strip(),
        empresa.strip(),
        area.strip(),
    )
    response = RedirectResponse("/dashboard", status_code=303)
    set_auth_cookie(response, create_access_token(username))
    return response
