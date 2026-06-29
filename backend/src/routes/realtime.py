from __future__ import annotations

import logging
from urllib.parse import urlparse

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.src.config.settings import settings
from backend.src.middleware.auth import get_user_from_token
from backend.src.services.notification_service import get_notifications
from backend.src.services.realtime_service import realtime_manager


router = APIRouter()
logger = logging.getLogger("dart.realtime")


@router.websocket("/ws/notifications")
async def notification_socket(websocket: WebSocket):
    origin = websocket.headers.get("origin", "")
    host = websocket.headers.get("host", "")
    allowed_hosts = {host, urlparse(settings.public_base_url).netloc}
    if origin and urlparse(origin).netloc not in allowed_hosts:
        logger.warning("SECURITY_SUSPICIOUS_ACTIVITY cause=websocket_origin origin=%s", origin[:160])
        await websocket.close(code=4403)
        return
    token = websocket.cookies.get(settings.auth_cookie_name, "")
    user = get_user_from_token(token)
    if not user:
        await websocket.close(code=4401)
        return
    username = user["username"]
    await realtime_manager.connect(username, websocket)
    notifications = get_notifications(username, limit=20)
    await websocket.send_json(
        {
            "type": "ready",
            "unread_count": sum(1 for item in notifications if not item.get("read")),
        }
    )
    try:
        while True:
            message = await websocket.receive_json()
            if message.get("type") == "ack":
                logger.info(
                    "REALTIME_NOTIFICATION_RECEIVED notification_id=%s user=%s",
                    message.get("notification_id", ""),
                    username,
                )
            elif message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.warning("realtime_socket_closed user=%s", username, exc_info=True)
    finally:
        await realtime_manager.disconnect(username, websocket)
