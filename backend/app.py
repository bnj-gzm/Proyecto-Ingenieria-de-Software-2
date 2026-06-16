import logging
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.src.config.database import init_db, _connect
from backend.src.config.frontend import templates
from backend.src.routes import auth, perfil, art, admin

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("dart")

_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
_UPLOAD_DIR = _FRONTEND_DIR / "static" / "uploads"
_ART_UPLOAD_DIR = _UPLOAD_DIR / "art"
_PROFILE_UPLOAD_DIR = _UPLOAD_DIR / "perfiles"
_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
_ART_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
_PROFILE_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="ART/AST Digital")
app.state.upload_dir = _UPLOAD_DIR
app.state.art_upload_dir = _ART_UPLOAD_DIR
app.state.profile_upload_dir = _PROFILE_UPLOAD_DIR


def _prefers_html(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    return "text/html" in accept or "*/*" in accept


@app.exception_handler(HTTPException)
async def controlled_http_error(request: Request, exc: HTTPException):
    logger.warning("HTTP_ERROR status=%s path=%s detail=%s", exc.status_code, request.url.path, exc.detail)
    if not _prefers_html(request):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "request": request,
            "title": "No pudimos abrir esta página",
            "status_code": exc.status_code,
            "message": exc.detail or "La solicitud no pudo completarse.",
        },
        status_code=exc.status_code,
    )


@app.exception_handler(Exception)
async def controlled_unhandled_error(request: Request, exc: Exception):
    logger.exception("UNHANDLED_ERROR path=%s", request.url.path)
    if not _prefers_html(request):
        return JSONResponse({"detail": "Error interno controlado."}, status_code=500)
    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "request": request,
            "title": "Servicio temporalmente no disponible",
            "status_code": 500,
            "message": "No pudimos completar la solicitud. Intenta nuevamente en unos segundos.",
        },
        status_code=500,
    )


@app.middleware("http")
async def log_errors(request: Request, call_next):
    start = time.time()
    try:
        response = await call_next(request)
        duration = time.time() - start
        if response.status_code >= 400:
            logger.warning("%s %s -> %s (%.3fs)", request.method, request.url.path, response.status_code, duration)
        else:
            logger.info("%s %s -> %s (%.3fs)", request.method, request.url.path, response.status_code, duration)
        return response
    except Exception:
        logger.exception("Error no controlado en %s %s", request.method, request.url.path)
        raise


app.mount("/static", StaticFiles(directory=str(_FRONTEND_DIR / "static")), name="static")

app.include_router(auth.router)
app.include_router(perfil.router)
app.include_router(art.router)
app.include_router(admin.router)

start_time = time.time()
logger.info("Iniciando inicialización de la base de datos...")
try:
    init_db()
    logger.info("init_db completado en %.2f s", time.time() - start_time)
except Exception:
    logger.exception("Error durante init_db")

try:
    # Warm up DB connection once at startup to avoid first-request latency
    warm_start = time.time()
    conn = _connect()
    conn.close()
    logger.info("Warmup de conexión completado en %.2f s", time.time() - warm_start)
except Exception:
    logger.exception("Error en warmup de conexión; continuará sin fail de arranque")
