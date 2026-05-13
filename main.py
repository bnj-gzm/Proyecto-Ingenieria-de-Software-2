# main.py
from fastapi import FastAPI, Request, Form, UploadFile, File, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from passlib.context import CryptContext
from pathlib import Path
from typing import List, Optional
import uuid, shutil
from datetime import datetime
from db import (
    cargar_registros,
    guardar_registro,
    cargar_usuarios,
    guardar_usuario,
    init_db,
    obtener_registro,
    obtener_usuario,
)

app = FastAPI(title="ART/AST Digital")

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = BASE_DIR / "static" / "uploads"

DATA_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
init_db()

def get_current_user(request: Request):
    username = request.cookies.get("user")
    if not username:
        return None
    user = obtener_usuario(username)
    if not user:
        return None
    # If admin, add pending count for navbar
    try:
        if user.get("rol") == "admin":
            from db import contar_art_pendientes

            user["pendientes"] = contar_art_pendientes()
    except Exception:
        user["pendientes"] = 0
    return user

# ---------------------
# LOGIN / LOGOUT
# ---------------------
@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse(request, "login.html", {"request": request, "title": "Iniciar sesión"})

@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    user = obtener_usuario(username)
    if not user or not pwd_context.verify(password, user["password_hash"]):
        return templates.TemplateResponse(request, "login.html", {"request": request, "error": "Usuario o contraseña incorrectos", "title": "Iniciar sesión"})
    response = RedirectResponse("/", status_code=303)
    response.set_cookie("user", username)
    return response

@app.get("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("user")
    return response

# ---------------------
# REGISTRO
# ---------------------
@app.get("/registro", response_class=HTMLResponse)
def registro_form(request: Request):
    return templates.TemplateResponse(request, "registro.html", {"request": request, "title": "Crear cuenta"})

@app.post("/registro")
def registro(request: Request, username: str = Form(...), password: str = Form(...), rol: str = Form(...)):
    if obtener_usuario(username):
        return templates.TemplateResponse(request, "registro.html", {"request": request, "error": "El usuario ya existe", "title": "Crear cuenta"})
    hash_password = pwd_context.hash(password)
    guardar_usuario(username, hash_password, rol)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie("user", username)
    return response


@app.get("/perfil", response_class=HTMLResponse)
def perfil_form(request: Request, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request, "profile.html", {"request": request, "user": user, "title": "Mi perfil"})


@app.post("/perfil")
def perfil_update(request: Request, password: str = Form(...), user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login", status_code=303)
    # actualizar nombre/email y contraseña opcional
    form = request.form()
    # form is a Starlette UploadFile/ form mapping when executed sync; use request.form() in threadpool
    try:
        data = request._form if hasattr(request, '_form') else None
    except Exception:
        data = None
    # safer: read via request.form() synchronously by using dependents; but simplest: accept fields from parameters
    nombre = request.form().get('nombre') if request.form() else None
    email = request.form().get('email') if request.form() else None
    pwd = request.form().get('password') if request.form() else None
    from db import actualizar_perfil, actualizar_password

    if nombre is not None or email is not None:
        actualizar_perfil(user["username"], nombre or "", email or "")
    if pwd:
        new_hash = pwd_context.hash(pwd)
        actualizar_password(user["username"], new_hash)
    response = RedirectResponse("/dashboard", status_code=303)
    return response


@app.post("/admin/art/{id_art}/estado")
def admin_change_estado(id_art: str, estado: str = Form(...), user=Depends(get_current_user)):
    if not user:
        return RedirectResponse('/login', status_code=303)
    if user.get('rol') != 'admin':
        return RedirectResponse('/', status_code=303)
    from db import actualizar_estado_art
    actualizar_estado_art(id_art, estado)
    return RedirectResponse('/admin/art', status_code=303)


@app.get("/admin/art", response_class=HTMLResponse)
def admin_list_art(request: Request, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user.get("rol") != "admin":
        return RedirectResponse("/", status_code=303)
    registros = cargar_registros()
    return templates.TemplateResponse(request, "admin_art_list.html", {"request": request, "user": user, "registros": registros, "title": "Revisar ARTs"})

# ---------------------
# DASHBOARD
# ---------------------
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login", status_code=303)
    registros = cargar_registros()
    return templates.TemplateResponse(request, "dashboard.html", {"request": request, "user": user, "registros": registros})

# ---------------------
# ART/AST
# ---------------------
@app.get("/", response_class=HTMLResponse)
def inicio(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse(request, "portada.html", {"request": request, "user": user, "title": "D.A.R.T"})

@app.get("/art/nueva", response_class=HTMLResponse)
def nueva_art(request: Request, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login", status_code=303)
    checklist = [
        "Me encuentro en condiciones físicas y psicológicas aptas para realizar la actividad.",
        "Cuento con las autorizaciones de ingreso al área.",
        "Cuento con ART/AST necesario para trabajos cruzados.",
        "Dispongo de todos los elementos de protección personal necesarios.",
        "Dispongo de equipos y herramientas necesarias para la tarea.",
        "Existe procedimiento o instructivo de trabajo.",
        "He sido capacitado para ejecutar correctamente el trabajo.",
        "Conozco el plan de emergencia del área.",
    ]
    epp = [
        "Casco de seguridad", "Lentes de seguridad", "Guantes", "Zapatos de seguridad",
        "Protección auditiva", "Respirador / mascarilla", "Chaleco reflectante", "Arnés de seguridad"
    ]
    return templates.TemplateResponse(request, "nueva_art.html", {"request": request, "checklist": checklist, "epp": epp, "user": user})

# ---------------------
# GUARDAR ART
# ---------------------
@app.post("/art/guardar")
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
):
    id_art = str(uuid.uuid4())[:8]
    guardar_registro({
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
    })
    return RedirectResponse(f"/art/{id_art}", status_code=303)

@app.get("/art/{id_art}", response_class=HTMLResponse)
def detalle_art(request: Request, id_art: str, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login", status_code=303)
    registro = obtener_registro(id_art)
    return templates.TemplateResponse(request, "detalle_art.html", {"request": request, "registro": registro, "user": user})