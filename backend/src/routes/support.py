from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool

from backend.src.config.frontend import templates
from backend.src.middleware.auth import get_current_user
from backend.src.middleware.csrf import create_csrf_token, set_csrf_cookie, validate_csrf_token
from backend.src.roles import can_manage_users
from backend.src.services.content_filter import PROHIBITED_LANGUAGE_MESSAGE, validate_clean_text
from backend.src.services.email_service import send_support_ticket_email
from backend.src.services.support_service import (
    SUPPORT_STATUSES,
    SUPPORT_TYPES,
    create_ticket,
    find_recent_duplicate,
    list_tickets,
    update_ticket_status,
)
from backend.src.services.notification_service import add_notification
from backend.src.services.realtime_service import realtime_manager
from backend.src.services.usuario_service import cargar_usuarios_por_rol
from backend.src.services.rate_limiter import enforce_rate_limit, support_rate_limiter


router = APIRouter()
logger = logging.getLogger("dart.support")
_TICKET_CREATE_LOCK = asyncio.Lock()


@router.get("/support/csrf")
def support_csrf(user=Depends(get_current_user)):
    if not user:
        return JSONResponse({"ok": False}, status_code=401)
    token = create_csrf_token()
    response = JSONResponse({"ok": True, "csrf_token": token})
    set_csrf_cookie(response, token)
    return response


@router.post("/support/ticket")
async def create_support_ticket(
    request: Request,
    type: str = Form(...),
    message: str = Form(...),
    csrf_token: str = Form(...),
    user=Depends(get_current_user),
):
    if not user:
        return JSONResponse({"ok": False, "message": "Debes iniciar sesión para enviar un ticket."}, status_code=401)
    try:
        allowed, retry_after = enforce_rate_limit(request, support_rate_limiter, "support_ticket", 5, 60)
        if not allowed:
            return JSONResponse(
                {"ok": False, "message": f"Demasiadas solicitudes. Intenta nuevamente en {retry_after} segundos."},
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )
        validate_csrf_token(request, csrf_token)
        ticket_type = type.strip().lower()
        clean_message = message.strip()
        if ticket_type not in SUPPORT_TYPES:
            return JSONResponse({"ok": False, "message": "Tipo de ticket inválido."}, status_code=400)
        if not clean_message or len(clean_message) < 10:
            return JSONResponse({"ok": False, "message": "Describe el problema con al menos 10 caracteres."}, status_code=400)
        if len(clean_message) > 4000:
            return JSONResponse({"ok": False, "message": "El mensaje no puede superar 4000 caracteres."}, status_code=400)
        validate_clean_text(clean_message, "support_message", user.get("username", ""))
        async with _TICKET_CREATE_LOCK:
            duplicate = await run_in_threadpool(find_recent_duplicate, user.get("id"), ticket_type, clean_message)
            if duplicate:
                logger.warning("SUPPORT_TICKET_ERROR user=%s stage=duplicate ticket_id=%s", user.get("username", ""), duplicate["id"])
                return JSONResponse(
                    {
                        "ok": True,
                        "duplicate": True,
                        "ticket_id": str(duplicate["id"]),
                        "message": "Este ticket ya fue recibido y está siendo procesado.",
                    }
                )
            ticket = await run_in_threadpool(
                create_ticket,
                user.get("id"),
                user.get("email", ""),
                ticket_type,
                clean_message,
            )
        logger.info(
            "SUPPORT_TICKET_CREATED ticket_id=%s user=%s type=%s",
            ticket["id"],
            user.get("username", ""),
            ticket_type,
        )
        try:
            from backend.src.services import logging_service as _log_svc
            _log_svc.log_event(
                _log_svc.SUPPORT_TICKET_CREATED,
                username=user.get("username", ""),
                details={"ticket_id": str(ticket["id"]), "type": ticket_type},
            )
        except Exception:
            pass
        result = await run_in_threadpool(
            send_support_ticket_email,
            user.get("nombre") or user.get("username") or "Usuario",
            user.get("email", ""),
            ticket_type,
            clean_message,
        )
        if result.ok:
            logger.info("SUPPORT_EMAIL_SENT ticket_id=%s message_id=%s", ticket["id"], result.message_id)
        else:
            logger.error("SUPPORT_TICKET_ERROR ticket_id=%s stage=email error=%s", ticket["id"], result.error)
        try:
            admin_users = await run_in_threadpool(cargar_usuarios_por_rol, "admin")
            for admin_user in admin_users:
                if admin_user.get("estado_cuenta") != "activo":
                    continue
                notification = add_notification(
                    admin_user["username"],
                    "Nuevo ticket de soporte",
                    f"{user.get('nombre') or user.get('username')} reportó: {ticket_type}.",
                    "/admin/support",
                    "SUPPORT_TICKET",
                )
                await realtime_manager.send_notification(notification)
        except Exception:
            logger.exception("SUPPORT_TICKET_ERROR ticket_id=%s stage=notification", ticket["id"])
        return JSONResponse(
            {
                "ok": True,
                "ticket_id": str(ticket["id"]),
                "email_sent": result.ok,
                "message": "Ticket enviado. Nuestro equipo revisará tu solicitud.",
            }
        )
    except HTTPException as exc:
        logger.warning("SUPPORT_TICKET_ERROR user=%s status=%s detail=%s", user.get("username", ""), exc.status_code, exc.detail)
        message_text = PROHIBITED_LANGUAGE_MESSAGE if exc.status_code == 400 else "No pudimos validar el ticket."
        return JSONResponse({"ok": False, "message": message_text}, status_code=exc.status_code)
    except Exception:
        logger.exception("SUPPORT_TICKET_ERROR user=%s stage=create", user.get("username", ""))
        return JSONResponse({"ok": False, "message": "No pudimos crear el ticket. Intenta nuevamente."}, status_code=500)


@router.get("/admin/support", response_class=HTMLResponse)
def admin_support(request: Request, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login", status_code=303)
    if not can_manage_users(user.get("rol", "")):
        return RedirectResponse("/dashboard", status_code=303)
    tickets = list_tickets()
    counts = {
        "open": sum(1 for ticket in tickets if ticket["status"] == "open"),
        "in_progress": sum(1 for ticket in tickets if ticket["status"] == "in_progress"),
        "resolved": sum(1 for ticket in tickets if ticket["status"] == "resolved"),
    }
    csrf_token = create_csrf_token()
    response = templates.TemplateResponse(
        request,
        "admin_support.html",
        {
            "request": request,
            "user": user,
            "title": "Soporte",
            "tickets": tickets,
            "counts": counts,
            "csrf_token": csrf_token,
        },
    )
    set_csrf_cookie(response, csrf_token)
    return response


@router.post("/admin/support/{ticket_id}/status")
def admin_support_status(
    request: Request,
    ticket_id: str,
    status: str = Form(...),
    csrf_token: str = Form(...),
    user=Depends(get_current_user),
):
    if not user:
        return RedirectResponse("/login", status_code=303)
    if not can_manage_users(user.get("rol", "")):
        return RedirectResponse("/dashboard", status_code=303)
    validate_csrf_token(request, csrf_token)
    if status not in SUPPORT_STATUSES:
        raise HTTPException(status_code=400, detail="Estado de ticket inválido")
    if not update_ticket_status(ticket_id, status):
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    return RedirectResponse("/admin/support", status_code=303)
