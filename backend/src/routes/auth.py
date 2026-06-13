from datetime import datetime, timedelta
import logging
import re
import secrets

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from backend.src.config.database import _raw_connect
from backend.src.config.frontend import templates
from backend.src.config.settings import settings
from backend.src.middleware.auth import create_access_token, delete_auth_cookie, pwd_context, set_auth_cookie
from backend.src.middleware.csrf import create_csrf_token, set_csrf_cookie, validate_csrf_token
from backend.src.services.email_service import send_reset_password_email
from backend.src.services.password_policy import validate_password_strength
from backend.src.services.usuario_service import (
    activar_usuario,
    guardar_reset_token,
    obtener_usuario_por_activation_token,
    obtener_usuario_por_email,
    obtener_usuario_por_reset_token,
    resetear_password,
    username_existe,
)

router = APIRouter()
logger = logging.getLogger("dart.auth")
USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,40}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _username_desde_email(email: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9_.-]", "", email.split("@", 1)[0].lower())[:30] or "usuario"
    username = base
    while username_existe(username):
        username = f"{base[:25]}-{secrets.token_hex(2)}"
    return username


def email_corporativo_valido(email: str) -> bool:
    if not EMAIL_RE.fullmatch(email):
        return False
    domain = email.rsplit("@", 1)[-1].lower()
    return domain in settings.allowed_email_domains


def _absolute_url(request: Request, path: str) -> str:
    base = settings.public_base_url or "https://www.dart-mineria.lat"
    return f"{base}{path}"


def _render_simple_form(
    request: Request,
    template_name: str,
    title: str,
    error: str | None = None,
    message: str | None = None,
    **context,
):
    csrf_token = create_csrf_token()
    response = templates.TemplateResponse(
        request,
        template_name,
        {
            "request": request,
            "title": title,
            "csrf_token": csrf_token,
            "error": error,
            "message": message,
            **context,
        },
    )
    set_csrf_cookie(response, csrf_token)
    return response


def _render_login(request: Request, error: str | None = None, message: str | None = None, status_code: int = 200):
    csrf_token = create_csrf_token()
    response = templates.TemplateResponse(
        request,
        "login.html",
        {"request": request, "title": "Iniciar sesión", "csrf_token": csrf_token, "error": error, "message": message},
        status_code=status_code,
    )
    set_csrf_cookie(response, csrf_token)
    return response


def _render_registro(request: Request, error: str | None = None):
    return _render_login(request, error or "El registro público está desactivado. Solicita tu cuenta al administrador.")


def _login_runtime_ok() -> tuple[bool, str]:
    missing = []
    if not getattr(settings, "secret_key", ""):
        missing.append("SECRET_KEY")
    if not getattr(settings, "database_url", ""):
        missing.append("DATABASE_URL")
    if missing:
        return False, f"missing_config:{','.join(missing)}"

    conn = None
    cur = None
    try:
        conn = _raw_connect()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
    except Exception:
        logger.exception("login_database_check_failed")
        return False, "database_unavailable"
    finally:
        if cur is not None:
            cur.close()
        if conn is not None:
            conn.close()
    return True, ""


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return _render_login(request)


@router.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...), csrf_token: str = Form(...)):
    try:
        validate_csrf_token(request, csrf_token)
        email = email.strip().lower()
        if not EMAIL_RE.fullmatch(email):
            return _render_login(request, "Ingresa un correo electrónico válido")
        if not email_corporativo_valido(email):
            return _render_login(request, "Solo se permite acceso con correo corporativo D.A.R.T")

        config_ok, config_error = _login_runtime_ok()
        if not config_ok:
            logger.error("login_runtime_unavailable email=%s cause=%s", email, config_error)
            return _render_login(
                request,
                "No pudimos iniciar sesión en este momento. Intenta nuevamente más tarde.",
                status_code=503,
            )

        user = obtener_usuario_por_email(email)
        if user is None:
            logger.info("login_failed_user_not_found email=%s", email)
            return _render_login(request, "Correo o contraseña incorrectos")

        username = user.get("username") if isinstance(user, dict) else ""
        password_hash = user.get("password_hash") if isinstance(user, dict) else ""
        if not username or not password_hash:
            logger.error(
                "login_user_record_incomplete email=%s username_present=%s password_hash_present=%s",
                email,
                bool(username),
                bool(password_hash),
            )
            return _render_login(request, "Correo o contraseña incorrectos")

        try:
            password_ok = pwd_context.verify(password, password_hash)
        except Exception:
            logger.exception("login_password_verify_failed email=%s username=%s", email, username)
            return _render_login(request, "Correo o contraseña incorrectos")
        if not password_ok:
            return _render_login(request, "Correo o contraseña incorrectos")

        if user.get("estado_cuenta") != "activo":
            return _render_login(request, "Tu cuenta aún no está activa. Revisa el link enviado por administración.")

        response = RedirectResponse("/dashboard", status_code=303)
        set_auth_cookie(response, create_access_token(username))
        return response
    except HTTPException as exc:
        logger.warning("login_rejected status=%s detail=%s", exc.status_code, exc.detail)
        return _render_login(request, "La sesión expiró. Intenta iniciar sesión nuevamente.", status_code=exc.status_code)
    except Exception:
        logger.exception("login_unhandled_error")
        return _render_login(
            request,
            "No pudimos iniciar sesión en este momento. Intenta nuevamente más tarde.",
            status_code=503,
        )


@router.get("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    delete_auth_cookie(response)
    return response


@router.get("/registro", response_class=HTMLResponse)
def registro_form(request: Request):
    return RedirectResponse("/login", status_code=303)


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
    return _render_registro(request)


@router.get("/activar-cuenta/{token}", response_class=HTMLResponse)
def activar_cuenta_form(request: Request, token: str):
    user = obtener_usuario_por_activation_token(token)
    if not user:
        return _render_simple_form(request, "activar_cuenta.html", "Activar cuenta", error="Link inválido o vencido.", token=token)
    expires_at = user.get("activation_token_expires_at")
    if expires_at and expires_at < datetime.now():
        return _render_simple_form(request, "activar_cuenta.html", "Activar cuenta", error="El link de activación expiró.", token=token)
    return _render_simple_form(request, "activar_cuenta.html", "Activar cuenta", token=token, cuenta=user)


@router.post("/activar-cuenta/{token}")
def activar_cuenta_post(
    request: Request,
    token: str,
    password: str = Form(...),
    password_confirm: str = Form(...),
    csrf_token: str = Form(...),
):
    validate_csrf_token(request, csrf_token)
    user = obtener_usuario_por_activation_token(token)
    if not user:
        return _render_simple_form(request, "activar_cuenta.html", "Activar cuenta", error="Link inválido o vencido.", token=token)
    expires_at = user.get("activation_token_expires_at")
    if expires_at and expires_at < datetime.now():
        return _render_simple_form(request, "activar_cuenta.html", "Activar cuenta", error="El link de activación expiró.", token=token)
    if password != password_confirm:
        return _render_simple_form(request, "activar_cuenta.html", "Activar cuenta", error="Las contraseñas no coinciden.", token=token, cuenta=user)
    password_ok, password_error = validate_password_strength(password)
    if not password_ok:
        return _render_simple_form(request, "activar_cuenta.html", "Activar cuenta", error=password_error, token=token, cuenta=user)
    activar_usuario(user["username"], pwd_context.hash(password))
    return _render_login(request, message="Cuenta activada. Ya puedes iniciar sesión.")


@router.get("/olvide-password", response_class=HTMLResponse)
def olvide_password_form(request: Request):
    return _render_simple_form(request, "olvide_password.html", "Olvidé mi contraseña")


@router.post("/olvide-password")
def olvide_password_post(request: Request, email: str = Form(...), csrf_token: str = Form(...)):
    validate_csrf_token(request, csrf_token)
    email = email.strip().lower()
    if email_corporativo_valido(email):
        user = obtener_usuario_por_email(email)
        if user and user.get("estado_cuenta") == "activo":
            token = secrets.token_urlsafe(32)
            guardar_reset_token(user["username"], token, datetime.now() + timedelta(hours=2))
            reset_link = _absolute_url(request, f"/reset-password/{token}")
            result = send_reset_password_email(email, reset_link)
            if not result.ok:
                logger.error("email_failed flow=reset_password username=%s email=%s error=%s", user["username"], email, result.error)
    message = "Si el correo existe, enviaremos instrucciones para recuperar la cuenta."
    return _render_simple_form(request, "olvide_password.html", "Olvidé mi contraseña", message=message)


@router.get("/reset-password/{token}", response_class=HTMLResponse)
def reset_password_form(request: Request, token: str):
    user = obtener_usuario_por_reset_token(token)
    if not user:
        return _render_simple_form(request, "reset_password.html", "Restablecer contraseña", error="Link inválido o vencido.", token=token)
    expires_at = user.get("reset_token_expires_at")
    if expires_at and expires_at < datetime.now():
        return _render_simple_form(request, "reset_password.html", "Restablecer contraseña", error="El link de recuperación expiró.", token=token)
    return _render_simple_form(request, "reset_password.html", "Restablecer contraseña", token=token)


@router.post("/reset-password/{token}")
def reset_password_post(
    request: Request,
    token: str,
    password: str = Form(...),
    password_confirm: str = Form(...),
    csrf_token: str = Form(...),
):
    validate_csrf_token(request, csrf_token)
    user = obtener_usuario_por_reset_token(token)
    if not user:
        return _render_simple_form(request, "reset_password.html", "Restablecer contraseña", error="Link inválido o vencido.", token=token)
    expires_at = user.get("reset_token_expires_at")
    if expires_at and expires_at < datetime.now():
        return _render_simple_form(request, "reset_password.html", "Restablecer contraseña", error="El link de recuperación expiró.", token=token)
    if password != password_confirm:
        return _render_simple_form(request, "reset_password.html", "Restablecer contraseña", error="Las contraseñas no coinciden.", token=token)
    password_ok, password_error = validate_password_strength(password)
    if not password_ok:
        return _render_simple_form(request, "reset_password.html", "Restablecer contraseña", error=password_error, token=token)
    resetear_password(user["username"], pwd_context.hash(password))
    return _render_login(request, message="Contraseña actualizada. Ya puedes iniciar sesión.")
