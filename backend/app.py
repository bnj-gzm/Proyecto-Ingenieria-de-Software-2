import logging
import posixpath
import re
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from backend.src.config.database import init_db, _connect
from backend.src.config.frontend import templates
from backend.src.routes import auth, perfil, art, admin, support, realtime

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

_STATIC_UPLOADS_PREFIX = "/static/uploads/"
_STATIC_ART_PDF_RE = re.compile(r"^art-([a-z0-9_-]+)\.pdf$")


def _protected_static_file_response(request: Request):
    """Impide que respaldos privados sean servidos por StaticFiles."""
    normalized_path = "/" + posixpath.normpath(request.url.path.replace("\\", "/")).lstrip("/")
    normalized_path = normalized_path.casefold()

    if normalized_path == f"{_STATIC_UPLOADS_PREFIX}notifications.json":
        return Response(status_code=404, headers={"Cache-Control": "no-store"})

    if normalized_path.startswith(_STATIC_UPLOADS_PREFIX) and normalized_path.endswith(".pdf"):
        filename = normalized_path.rsplit("/", 1)[-1]
        match = _STATIC_ART_PDF_RE.fullmatch(filename)
        if not match:
            return Response(status_code=404, headers={"Cache-Control": "no-store"})
        return RedirectResponse(
            url=f"/art/{match.group(1)}/pdf",
            status_code=307,
            headers={"Cache-Control": "no-store"},
        )

    return None


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
    try:
        from backend.src.services import logging_service as _log_svc
        _log_svc.log_event(
            _log_svc.SYSTEM_ERROR_CAPTURED,
            details={"error": str(exc)[:500], "path": str(request.url.path), "type": type(exc).__name__},
        )
    except Exception:
        pass
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


@app.middleware("http")
async def security_and_cache_headers(request: Request, call_next):
    protected_response = _protected_static_file_response(request)
    if protected_response is not None:
        return protected_response
    response = await call_next(request)
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://unpkg.com https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com; "
        "font-src 'self' data: https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
        "img-src 'self' data: blob:; connect-src 'self' ws: wss:; "
        "object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
    )
    if request.url.scheme == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    if request.url.path.startswith("/static/"):
        response.headers.setdefault("Cache-Control", "public, max-age=604800, immutable")
    else:
        response.headers.setdefault("Cache-Control", "no-store")
    return response


app.mount("/static", StaticFiles(directory=str(_FRONTEND_DIR / "static")), name="static")

app.include_router(auth.router)
app.include_router(perfil.router)
app.include_router(art.router)
app.include_router(admin.router)
app.include_router(support.router)
app.include_router(realtime.router)

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
