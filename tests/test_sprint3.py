import asyncio
import base64
import io
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import UploadFile
from PIL import Image
from starlette.requests import Request

from backend.src.routes import realtime, support
from backend.src.services import notification_service
from backend.src.services.rate_limiter import SlidingWindowRateLimiter, enforce_rate_limit
from backend.src.services.realtime_service import RealtimeNotificationManager
from backend.src.services.upload_service import save_art_image


def make_request(ip: str = "203.0.113.10") -> Request:
    return Request({"type": "http", "method": "POST", "path": "/login", "headers": [], "client": (ip, 1234)})


class RateLimitTests(unittest.TestCase):
    def test_login_style_limit_allows_five_and_blocks_sixth(self):
        limiter = SlidingWindowRateLimiter()
        request = make_request()
        for _ in range(5):
            self.assertEqual(enforce_rate_limit(request, limiter, "login", 5, 60), (True, 0))
        with self.assertLogs("dart.security", level="WARNING") as captured:
            allowed, retry_after = enforce_rate_limit(request, limiter, "login", 5, 60)
        self.assertFalse(allowed)
        self.assertGreaterEqual(retry_after, 1)
        logs = "\n".join(captured.output)
        self.assertIn("SECURITY_RATE_LIMIT_TRIGGERED", logs)
        self.assertIn("SECURITY_SUSPICIOUS_ACTIVITY", logs)

    def test_limiter_handles_parallel_request_burst(self):
        limiter = SlidingWindowRateLimiter()
        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=16) as executor:
            results = list(executor.map(lambda index: limiter.allow(f"user:{index % 25}", 50, 60)[0], range(1000)))
        self.assertTrue(all(results))
        self.assertLess(time.perf_counter() - started, 2.0)


class FakeWebSocket:
    def __init__(self):
        self.messages = []
        self.accepted = False

    async def accept(self):
        self.accepted = True

    async def send_json(self, payload):
        self.messages.append(payload)


class AckWebSocket(FakeWebSocket):
    def __init__(self):
        super().__init__()
        self.cookies = {realtime.settings.auth_cookie_name: "token"}
        self.headers = {}

    async def receive_json(self):
        from fastapi import WebSocketDisconnect

        if not hasattr(self, "ack_sent"):
            self.ack_sent = True
            return {"type": "ack", "notification_id": "n-1"}
        raise WebSocketDisconnect()

    async def close(self, code=1000):
        self.close_code = code


class RealtimeTests(unittest.TestCase):
    def test_notification_is_delivered_immediately(self):
        async def scenario():
            manager = RealtimeNotificationManager()
            socket = FakeWebSocket()
            await manager.connect("supervisor", socket)
            delivered = await manager.send_notification(
                {"id": "n-1", "user": "supervisor", "event_type": "ART_RESPONSE", "read": False}
            )
            await manager.disconnect("supervisor", socket)
            return socket, delivered

        with self.assertLogs("dart.realtime", level="INFO") as captured:
            socket, delivered = asyncio.run(scenario())
        self.assertTrue(socket.accepted)
        self.assertEqual(delivered, 1)
        self.assertEqual(socket.messages[0]["notification"]["event_type"], "ART_RESPONSE")
        self.assertIn("REALTIME_NOTIFICATION_SENT", "\n".join(captured.output))

    @patch.object(realtime, "get_user_from_token", return_value={"username": "supervisor"})
    @patch.object(realtime, "get_notifications", return_value=[])
    def test_ack_logs_realtime_received(self, notifications, get_user):
        socket = AckWebSocket()
        with self.assertLogs("dart.realtime", level="INFO") as captured:
            asyncio.run(realtime.notification_socket(socket))
        self.assertIn("REALTIME_NOTIFICATION_RECEIVED", "\n".join(captured.output))


class ImageOptimizationTests(unittest.TestCase):
    def test_large_image_is_resized_and_compressed_without_changing_source(self):
        source = io.BytesIO()
        Image.new("RGB", (2400, 1600), "#64748b").save(source, format="JPEG", quality=95)
        original = source.getvalue()
        upload = UploadFile(filename="evidencia.jpg", file=io.BytesIO(original))
        result = asyncio.run(save_art_image(Path("."), upload, max_bytes=5 * 1024 * 1024, max_dimensions=(1200, 1200)))
        optimized = base64.b64decode(result["data"])
        with Image.open(io.BytesIO(optimized)) as image:
            self.assertLessEqual(max(image.size), 1200)
        self.assertLess(len(optimized), len(original))
        self.assertEqual(result["mime_type"], "image/webp")

    def test_signature_dark_mode_is_scoped_only_to_signature(self):
        root = Path(__file__).resolve().parents[1]
        base = (root / "frontend/templates/base.html").read_text(encoding="utf-8")
        worker = (root / "frontend/templates/art_trabajador_form.html").read_text(encoding="utf-8")
        response = (root / "frontend/templates/art_respuesta_trabajador.html").read_text(encoding="utf-8")
        self.assertIn(':root[data-theme="dark"] .signature-visual', base)
        self.assertIn("brightness(0) invert(1) contrast(1.15)", base)
        self.assertIn('id="signature-pad" class="signature-visual', worker)
        self.assertIn('class="signature-visual', response)
        self.assertNotIn(':root[data-theme="dark"] img { filter:', base)


class NotificationCacheTests(unittest.TestCase):
    def test_notification_cache_preserves_unified_event_type(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "notifications.json"
            with (
                patch.object(notification_service, "_storage_path", return_value=path),
                patch.object(notification_service, "_CACHE_ITEMS", None),
                patch.object(notification_service, "_CACHE_MTIME_NS", -1),
            ):
                notification_service.add_notification("worker", "ART", "Creada", "/art/1", "ART_CREATED")
                first = notification_service.get_notifications("worker")
                second = notification_service.get_notifications("worker")
        self.assertEqual(first, second)
        self.assertEqual(first[0]["event_type"], "ART_CREATED")


class SupportDeduplicationTests(unittest.TestCase):
    def setUp(self):
        support.support_rate_limiter.clear()

    @patch.object(support, "validate_csrf_token")
    @patch.object(support, "validate_clean_text")
    @patch.object(support, "find_recent_duplicate", return_value={"id": "existing", "status": "open"})
    @patch.object(support, "create_ticket")
    @patch.object(support, "send_support_ticket_email")
    def test_recent_duplicate_is_not_saved_or_emailed(self, send_email, create_ticket, duplicate, clean, csrf):
        user = {"id": 4, "username": "worker", "email": "worker@dart-mineria.lat"}
        response = asyncio.run(
            support.create_support_ticket(make_request(), "bug", "El formulario presenta el mismo error", "csrf", user)
        )
        self.assertEqual(response.status_code, 200)
        create_ticket.assert_not_called()
        send_email.assert_not_called()


if __name__ == "__main__":
    unittest.main()
