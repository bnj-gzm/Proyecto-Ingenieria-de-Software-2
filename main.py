from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

app = FastAPI()

# Le decimos a FastAPI dónde están los moldes (Jinja2)
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    # Renderizamos la página base
    return templates.TemplateResponse(request=request, name="base.html")

@app.get("/saludo")
async def get_saludo():
    # HTMX pide este pedacito de HTML y lo inyecta en la página
    return "¡Hola! Este mensaje llegó desde FastAPI sin recargar la página 🚀"
