import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from starlette.requests import Request

from backend.src.routes import art, perfil, support
from backend.src.services import email_service, support_service
from backend.src.services.email_service import EmailSendResult


def request(path: str = "/", ajax: bool = False) -> Request:
    headers = [(b"x-requested-with", b"XMLHttpRequest")] if ajax else []
    return Request({"type": "http", "method": "POST", "path": path, "headers": headers})


class SupportSystemTests(unittest.TestCase):
    @patch.object(support, "validate_csrf_token")
    @patch.object(support, "validate_clean_text")
    @patch.object(support, "find_recent_duplicate", return_value=None)
    @patch.object(support, "cargar_usuarios_por_rol", return_value=[])
    @patch.object(
        support,
        "create_ticket",
        return_value={"id": "c5146a18-a2f0-44ec-9ee7-f70a197980f2", "type": "bug", "status": "open"},
    )
    @patch.object(support, "send_support_ticket_email", return_value=EmailSendResult(True, "resend", "mail_123"))
    def test_ticket_is_saved_emailed_and_logged(self, send_email, create_ticket, admins, duplicate, clean, csrf):
        user = {"id": 7, "username": "ana", "nombre": "Ana", "email": "ana@dart-mineria.lat", "rol": "trabajador"}
        with self.assertLogs("dart.support", level="INFO") as captured:
            response = asyncio.run(support.create_support_ticket(request("/support/ticket", ajax=True), "bug", "La vista no carga correctamente", "csrf", user))
        self.assertEqual(response.status_code, 200)
        create_ticket.assert_called_once_with(7, "ana@dart-mineria.lat", "bug", "La vista no carga correctamente")
        send_email.assert_called_once()
        logs = "\n".join(captured.output)
        self.assertIn("SUPPORT_TICKET_CREATED", logs)
        self.assertIn("SUPPORT_EMAIL_SENT", logs)

    @patch.object(email_service, "send_email_result", return_value=EmailSendResult(True, "resend", "mail_456"))
    def test_support_email_targets_admin_and_escapes_message(self, sender):
        result = email_service.send_support_ticket_email("Ana", "ana@dart-mineria.lat", "error", "Falla <script>")
        self.assertTrue(result.ok)
        args = sender.call_args.args
        self.assertEqual(args[0], "admin@dart-mineria.lat")
        self.assertEqual(args[1], "Nuevo ticket de soporte D.A.R.T")
        self.assertIn("&lt;script&gt;", args[2])

    @patch.object(support_service, "_connect")
    def test_create_ticket_commits_to_database(self, connect):
        cursor = MagicMock()
        cursor.fetchone.return_value = {
            "id": "ticket-id",
            "user_id": 3,
            "email": "user@dart-mineria.lat",
            "type": "mejora",
            "message": "Mejorar filtros",
            "status": "open",
            "created_at": None,
        }
        connection = MagicMock()
        connection.cursor.return_value = cursor
        connect.return_value = connection
        ticket = support_service.create_ticket(3, "user@dart-mineria.lat", "mejora", "Mejorar filtros")
        self.assertEqual(ticket["status"], "open")
        connection.commit.assert_called_once()
        self.assertIn("INSERT INTO support_tickets", cursor.execute.call_args.args[0])


class NotificationTests(unittest.TestCase):
    @patch.object(art.realtime_manager, "send_notification", new_callable=AsyncMock, return_value=1)
    @patch.object(art, "add_notification", return_value={"id": "notification-1", "user": "supervisor"})
    def test_worker_response_notifies_supervisor_and_logs_event(self, add_notification, send_notification):
        registro = {"id": "art-01", "supervisor_asignado": "supervisor"}
        asignacion = {"id": 9, "nombre": "Trabajador"}
        with self.assertLogs("dart.art", level="INFO") as captured:
            asyncio.run(art._notify_supervisor_art_response(registro, asignacion))
        add_notification.assert_called_once()
        send_notification.assert_awaited_once()
        self.assertIn("NOTIFICATION_ART_RESPONSE", "\n".join(captured.output))

    @patch.object(perfil, "get_notifications", return_value=[{"id": "1", "read": False}, {"id": "2", "read": True}])
    def test_notifications_api_returns_unread_count(self, notifications):
        response = perfil.api_notificaciones({"username": "supervisor"})
        self.assertEqual(response["unread_count"], 1)


class ProfileAjaxTests(unittest.TestCase):
    @patch.object(perfil, "validate_csrf_token")
    @patch.object(perfil, "validate_clean_fields")
    @patch.object(perfil, "actualizar_perfil")
    @patch.object(perfil, "actualizar_foto_perfil")
    def test_profile_update_returns_json_without_navigation(self, update_photo, update_profile, clean, csrf):
        user = {"username": "ana", "foto_perfil": "", "nombre": "Ana"}
        response = asyncio.run(
            perfil.perfil_update(
                request("/perfil/editar", ajax=True),
                "Ana Soto",
                "",
                "Operadora",
                "",
                "",
                None,
                "csrf",
                user,
            )
        )
        self.assertEqual(response.status_code, 200)
        update_profile.assert_called_once_with("ana", "Ana Soto", "", "Operadora")
        update_photo.assert_not_called()


if __name__ == "__main__":
    unittest.main()
