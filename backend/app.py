import logging
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from backend.src.config.database import init_db, _connect
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
