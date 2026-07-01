from pathlib import Path
from fastapi.templating import Jinja2Templates

from backend.src.services.usuario_service import nombre_completo

_FRONTEND_DIR = Path(__file__).resolve().parents[3] / "frontend"
templates = Jinja2Templates(directory=str(_FRONTEND_DIR / "templates"))
templates.env.filters["full_name"] = nombre_completo
