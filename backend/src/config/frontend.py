from pathlib import Path
from fastapi.templating import Jinja2Templates

_FRONTEND_DIR = Path(__file__).resolve().parents[3] / "frontend"
templates = Jinja2Templates(directory=str(_FRONTEND_DIR / "templates"))
