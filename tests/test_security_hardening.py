from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from starlette.requests import Request

from backend.src.routes import admin, auth
from backend.src.services import email_service
from backend.src.services.content_filter import (
    PROHIBITED_LANGUAGE_MESSAGE,
    contains_prohibited_language,
    validate_clean_text,
)
from backend.src.services.login_security import (
    clear_all_login_attempts,
    record_login_failure,
    remaining_block_minutes,
    reset_login_attempts,
)


class LoginSecurityTests(unittest.TestCase):
    def setUp(self):
        clear_all_login_attempts()
        auth.login_rate_limiter.clear()
        self.security_notification = patch.object(auth, "_notify_login_security")
        self.security_notification.start()

    def tearDown(self):
        self.security_notification.stop()
        clear_all_login_attempts()
        auth.login_rate_limiter.clear()

    def test_third_failure_blocks_for_three_minutes(self):
        email = "persona@dart-mineria.lat"
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.assertEqual(record_login_failure(email, now), (1, 0))
        self.assertEqual(record_login_failure(email, now), (2, 0))
        self.assertEqual(record_login_failure(email, now), (3, 3))
        self.assertEqual(remaining_block_minutes(email, now), 3)

    def test_progressive_blocks_and_sixty_minute_cap(self):
        email = "persona@dart-mineria.lat"
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        expected = [0, 0, 3, 10, 30, 60, 60]
        for index, minutes in enumerate(expected, start=1):
            failures, actual_minutes = record_login_failure(email, now)
            self.assertEqual((failures, actual_minutes), (index, minutes))
            now += timedelta(minutes=actual_minutes)
            remaining_block_minutes(email, now)

    def test_success_reset_removes_previous_failures(self):
        email = "persona@dart-mineria.lat"
        record_login_failure(email)
        record_login_failure(email)
        reset_login_attempts(email)
        self.assertEqual(record_login_failure(email), (1, 0))

    def test_successful_login_resets_failures_and_logs_ok(self):
        email = "persona@dart-mineria.lat"
        record_login_failure(email)
        record_login_failure(email)
        user = {"username": "persona", "password_hash": "hash", "estado_cuenta": "activo"}
        with (
            patch.object(auth, "validate_csrf_token"),
            patch.object(auth, "email_corporativo_valido", return_value=True),
            patch.object(auth, "_login_runtime_ok", return_value=(True, "")),
            patch.object(auth, "obtener_usuario_por_email", return_value=user),
            patch.object(auth.pwd_context, "verify", return_value=True),
            patch.object(auth, "create_access_token", return_value="token"),
            patch.object(auth, "set_auth_cookie"),
            self.assertLogs("dart.auth", level="INFO") as captured,
        ):
            response = auth.login(MagicMock(), email, "correcta", "csrf")
        self.assertEqual(response.status_code, 303)
        self.assertIn("LOGIN_OK", "\n".join(captured.output))
        self.assertEqual(record_login_failure(email), (1, 0))

    @patch.object(auth, "_render_login", side_effect=lambda request, error=None, message=None, status_code=200: {"error": error, "status": status_code})
    @patch.object(auth, "_login_runtime_ok", return_value=(True, ""))
    @patch.object(auth, "email_corporativo_valido", return_value=True)
    @patch.object(auth, "validate_csrf_token")
    @patch.object(auth, "obtener_usuario_por_email", return_value={"username": "persona", "password_hash": "hash", "estado_cuenta": "activo"})
    @patch.object(auth.pwd_context, "verify", return_value=False)
    def test_login_route_logs_failure_and_block(self, verify, get_user, csrf, valid_email, runtime, render):
        with self.assertLogs("dart.auth", level="INFO") as captured:
            auth.login(MagicMock(), "persona@dart-mineria.lat", "mala", "csrf")
            auth.login(MagicMock(), "persona@dart-mineria.lat", "mala", "csrf")
            response = auth.login(MagicMock(), "persona@dart-mineria.lat", "mala", "csrf")
        self.assertEqual(response["status"], 429)
        logs = "\n".join(captured.output)
        self.assertIn("LOGIN_FAIL", logs)
        self.assertIn("LOGIN_BLOCKED", logs)


class AccountActivationTests(unittest.TestCase):
    @patch.object(admin, "_enviar_activacion_usuario")
    @patch.object(admin, "_crear_activation_link")
    @patch.object(admin, "obtener_usuario", return_value={"username": "activa", "estado_cuenta": "activo", "email": "activa@dart-mineria.lat"})
    @patch.object(admin, "validate_csrf_token")
    def test_active_user_does_not_get_new_token_or_email(self, csrf, get_user, create_link, send_email):
        request = Request({"type": "http", "method": "POST", "path": "/", "headers": []})
        with self.assertLogs("dart.admin", level="WARNING") as captured:
            response = admin.admin_reenviar_activacion(
                request,
                "activa",
                "csrf",
                {"username": "admin", "rol": "admin"},
            )
        self.assertEqual(response.status_code, 303)
        self.assertIn("Cuenta+ya+est%C3%A1+activada", response.headers["location"])
        create_link.assert_not_called()
        send_email.assert_not_called()
        self.assertIn("USER_ALREADY_ACTIVE", "\n".join(captured.output))


class EmailHardeningTests(unittest.TestCase):
    @patch.object(email_service.settings, "email_enabled", True)
    @patch.object(email_service.settings, "resend_api_key", "re_test")
    @patch.object(email_service, "_send_with_resend_sdk", side_effect=[RuntimeError("API temporal"), {"id": "mail_123"}])
    def test_resend_retries_once_and_uses_required_sender(self, sdk_send):
        with self.assertLogs("dart.email", level="INFO") as captured:
            result = email_service.send_email_result("destino@dart-mineria.lat", "Asunto", "<p>Hola</p>")
        self.assertTrue(result.ok)
        self.assertEqual(sdk_send.call_count, 2)
        self.assertEqual(sdk_send.call_args.args[0]["from"], "D.A.R.T <notificaciones@dart-mineria.lat>")
        logs = "\n".join(captured.output)
        self.assertIn("EMAIL_RETRY", logs)
        self.assertIn("EMAIL_SENT_OK", logs)

    @patch.object(email_service.settings, "email_enabled", True)
    @patch.object(email_service.settings, "resend_api_key", "re_test")
    @patch.object(email_service, "_send_with_resend_sdk", side_effect=RuntimeError("API caída"))
    def test_resend_failure_is_controlled_after_one_retry(self, sdk_send):
        with self.assertLogs("dart.email", level="INFO") as captured:
            result = email_service.send_email_result("destino@dart-mineria.lat", "Asunto", "<p>Hola</p>")
        self.assertFalse(result.ok)
        self.assertEqual(sdk_send.call_count, 2)
        self.assertIn("EMAIL_SENT_FAIL", "\n".join(captured.output))


class ContentFilterTests(unittest.TestCase):
    def test_blocks_accents_symbols_and_repeated_letters(self):
        for text in ("weeeoon", "p.e.n.e", "C0NCH4TUM4DRE", "héntai", "saco---wea"):
            with self.subTest(text=text):
                self.assertTrue(contains_prohibited_language(text))

    def test_controlled_message_and_log(self):
        with self.assertLogs("dart.content_filter", level="WARNING") as captured:
            with self.assertRaises(HTTPException) as raised:
                validate_clean_text("eres un idiota", "comentario", "persona")
        self.assertEqual(raised.exception.detail, PROHIBITED_LANGUAGE_MESSAGE)
        self.assertEqual(raised.exception.detail, "El contenido ingresado no es válido.")
        self.assertIn("CONTENT_BLOCKED", "\n".join(captured.output))

    def test_does_not_block_allowed_operational_phrase(self):
        self.assertFalse(contains_prohibited_language("Usar pico y pala según procedimiento"))


if __name__ == "__main__":
    unittest.main()
