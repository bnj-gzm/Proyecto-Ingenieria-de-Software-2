# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**D.A.R.T** — a web app for managing ART/AST (occupational risk assessment forms used in Chile's industrial sector).

Stack: Python + FastAPI, Jinja2/HTMX/Tailwind, PostgreSQL (Neon), bcrypt auth, JWT cookies, CSRF-protected forms.

Roles:
- `admin` manages users and assigns roles at `/admin/usuarios`.
- `supervisor` reviews ART records at `/supervisor/art`.
- `user` creates ART records and sees only their own records.

## Structure

```
Proyecto-Ingenieria-de-Software/
├── backend/
│   ├── app.py              ← FastAPI app: mounts static, includes routers, calls init_db()
│   ├── server.py           ← entry point: uvicorn.run("backend.app:app", ...)
│   └── src/
│       ├── config/
│       │   ├── database.py ← _connect(), JSON helpers, init_db()
│       │   ├── settings.py ← .env-backed settings
│       │   └── frontend.py ← shared Jinja2Templates instance
│       ├── middleware/
│       │   ├── auth.py     ← JWT cookie helpers, get_current_user(), pwd_context (bcrypt)
│       │   └── csrf.py     ← signed CSRF token helpers
│       ├── models/
│       │   ├── usuario.py  ← Pydantic: UsuarioCreate, UsuarioResponse
│       │   └── art.py      ← Pydantic: ARTCreate, ARTResponse
│       ├── services/
│       │   ├── usuario_service.py ← user CRUD (obtener, guardar, actualizar)
│       │   └── art_service.py     ← ART CRUD + contar_art_pendientes()
│       └── routes/
│           ├── auth.py     ← /login, /logout, /registro
│           ├── perfil.py   ← /perfil
│           ├── art.py      ← /, /dashboard, /art/nueva, /art/guardar, /art/{id}
│           └── admin.py    ← /supervisor/art review flow, /admin/usuarios role management
└── frontend/
    ├── templates/          ← Jinja2 templates (base.html, partials/, etc.)
    └── static/
        └── uploads/        ← user-uploaded evidence files
```

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run dev server (from project root)
uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000

# Or via the entry point script
python backend/server.py
```

## Environment

Copy `.env.example` to `.env` and set:

```
DATABASE_URL=postgresql://[user]:[password]@[host]/[database]?sslmode=require&channel_binding=require
SECRET_KEY=[long-random-secret]
COOKIE_SECURE=false
COOKIE_SAMESITE=lax
ACCESS_TOKEN_MINUTES=120
```

`settings.py` loads the `.env` from the project root at import time via `load_dotenv`.

## Architecture

### Request flow

1. Route handler in `backend/src/routes/` uses `Depends(get_current_user)` → validates the signed JWT auth cookie → fetches user from DB via `usuario_service`
2. Handler calls a `*_service.py` function; service calls `_connect()` from `database.py`
3. Returns `templates.TemplateResponse(...)` — `templates` is the shared instance from `config/frontend.py`

### Data model

Two tables: `users` and `art_records`. Several columns on `art_records` are stored as JSON text (`checklist_json`, `epp_json`, `riesgos_json`, `evidencia_json`); `art_service._deserialize()` converts them to Python lists on read.

### Roles

- **Regular user** — creates and views own ART records
- **Admin** — manages users and roles; can also access review screens.
- **Supervisor** — views all ART records and changes status (`pendiente` / `revisado`).
- **User** — creates ART records and sees only records they created.

### Database migrations

`init_db()` (called once in `app.py`) creates tables if they don't exist and uses `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` for safe upgrades.

## Key conventions

- All DB queries use `%s` parameterized placeholders — never string-format SQL.
- Each service function opens and closes its own connection (no connection pool).
- Protected routes declare `user=Depends(get_current_user)`; unauthenticated requests redirect to `/login`.
- POST routes with browser forms validate `csrf_token` using the signed CSRF cookie.
- Password hashing uses `pwd_context` from `middleware/auth.py` — always hash before calling `guardar_usuario` or `actualizar_password`.
- Public registration always creates regular users; admin role changes must be made intentionally outside the public form.
- HTMX attributes drive partial-page updates in templates — check `hx-target` and `hx-swap` when modifying forms.
