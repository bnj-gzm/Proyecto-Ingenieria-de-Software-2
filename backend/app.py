from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.src.config.database import init_db
from backend.src.routes import auth, perfil, art, admin

_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
_UPLOAD_DIR = _FRONTEND_DIR / "static" / "uploads"
_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="ART/AST Digital")

app.mount("/static", StaticFiles(directory=str(_FRONTEND_DIR / "static")), name="static")

app.include_router(auth.router)
app.include_router(perfil.router)
app.include_router(art.router)
app.include_router(admin.router)

init_db()
