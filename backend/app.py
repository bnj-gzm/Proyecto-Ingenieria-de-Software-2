import logging
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
_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="ART/AST Digital")
app.state.upload_dir = _UPLOAD_DIR


@app.middleware("http")
async def log_errors(request: Request, call_next):
    try:
        response = await call_next(request)
        if response.status_code >= 400:
            logger.warning("%s %s -> %s", request.method, request.url.path, response.status_code)
        return response
    except Exception:
        logger.exception("Error no controlado en %s %s", request.method, request.url.path)
        raise


app.mount("/static", StaticFiles(directory=str(_FRONTEND_DIR / "static")), name="static")

app.include_router(auth.router)
app.include_router(perfil.router)
app.include_router(art.router)
app.include_router(admin.router)

init_db()
try:
    # Warm up DB connection once at startup to avoid first-request latency
    conn = _connect()
    conn.close()
except Exception:
    # don't fail startup if warmup fails; DB errors will appear on first use
    pass
