# main.py
from fastapi import FastAPI, Request, Form, UploadFile, File, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from passlib.context import CryptContext
from pathlib import Path
from typing import List, Optional
import uuid, shutil, json
from datetime import datetime

app = FastAPI(title="ART/AST Digital")

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = BASE_DIR / "static" / "uploads"

DATA_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ART_FILE = DATA_DIR / "art_records.json"
USERS_FILE = DATA_DIR / "usuarios.json"

ART_FILE.write_text("[]", encoding="utf-8") if not ART_FILE.exists() else None
USERS_FILE.write_text("[]", encoding="utf-8") if not USERS_FILE.exists() else None

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ---------------------
# UTILIDADES
# ---------------------
def cargar_registros():
    with open(ART_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def guardar_registros(registros):
    with open(ART_FILE, "w", encoding="utf-8") as f:
        json.dump(registros, f, ensure_ascii=False, indent=4)

def cargar_usuarios():
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def guardar_usuarios(usuarios):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(usuarios, f, ensure_ascii=False, indent=4)

def get_current_user(request: Request):
    username = request.cookies.get("user")
    if not username:
        return None
    usuarios = cargar_usuarios()
    return next((u for u in usuarios if u["username"] == username), None)

# ---------------------
# LOGIN / LOGOUT
# ---------------------
@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse(request, "login.html", {"request": request, "title": "Iniciar sesión"})

@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    usuarios = cargar_usuarios()
    user = next((u for u in usuarios if u["username"] == username), None)
    if not user or not pwd_context.verify(password, user["password"]):
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
    usuarios = cargar_usuarios()
    if any(u["username"] == username for u in usuarios):
        return templates.TemplateResponse(request, "registro.html", {"request": request, "error": "El usuario ya existe", "title": "Crear cuenta"})
    hash_password = pwd_context.hash(password)
    usuarios.append({"username": username, "password": hash_password, "rol": rol})
    guardar_usuarios(usuarios)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie("user", username)
    return response

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
    registros = cargar_registros()
    id_art = str(uuid.uuid4())[:8]
    registros.insert(0, {
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
    guardar_registros(registros)
    return RedirectResponse(f"/art/{id_art}", status_code=303)

@app.get("/art/{id_art}", response_class=HTMLResponse)
def detalle_art(request: Request, id_art: str, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login", status_code=303)
    registros = cargar_registros()
    registro = next((r for r in registros if r["id"] == id_art), None)
    return templates.TemplateResponse(request, "detalle_art.html", {"request": request, "registro": registro, "user": user})