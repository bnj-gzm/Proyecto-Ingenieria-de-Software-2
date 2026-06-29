import inspect
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from backend.src.routes import admin, auth
from backend.src.services import usuario_service


class ReactivationGuardTests(unittest.TestCase):
    def test_active_state_aliases_are_all_blocked(self):
        self.assertTrue(admin._cuenta_activa({"estado_cuenta": "activo"}))
        self.assertTrue(admin._cuenta_activa({"estado": "activo"}))
        self.assertTrue(admin._cuenta_activa({"is_active": True}))

    @patch.object(usuario_service, "_connect")
    def test_activation_token_update_cannot_touch_active_account(self, connect):
        cursor = MagicMock()
        cursor.rowcount = 0
        connection = MagicMock()
        connection.cursor.return_value = cursor
        connect.return_value = connection

        changed = usuario_service.guardar_activation_token("activa", "token", None)

        self.assertFalse(changed)
        sql = cursor.execute.call_args.args[0]
        self.assertIn("estado_cuenta <> 'activo'", sql)
        connection.commit.assert_called_once()

    @patch.object(usuario_service, "_connect")
    def test_activation_is_idempotent_for_active_account(self, connect):
        cursor = MagicMock()
        cursor.rowcount = 0
        connection = MagicMock()
        connection.cursor.return_value = cursor
        connect.return_value = connection

        changed = usuario_service.activar_usuario("activa", "hash")

        self.assertFalse(changed)
        self.assertIn("estado_cuenta <> 'activo'", cursor.execute.call_args.args[0])


class LoginStateIsolationTests(unittest.TestCase):
    def test_login_never_changes_account_state(self):
        source = inspect.getsource(auth.login)
        self.assertNotIn("actualizar_estado_cuenta", source)
        self.assertNotIn("estado_cuenta =", source)
        self.assertIn("record_login_failure", source)


class FrontendCriticalFixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.base = (root / "frontend/templates/base.html").read_text(encoding="utf-8")
        cls.app_ui = (root / "frontend/static/js/app-ui.js").read_text(encoding="utf-8")

    def test_dark_signature_filter_is_strictly_scoped(self):
        self.assertIn(':root[data-theme="dark"] .signature-visual', self.base)
        self.assertIn("brightness(0) invert(1) contrast(1.15)", self.base)
        self.assertNotIn(':root[data-theme="dark"] img { filter:', self.base)

    def test_preview_requires_confirmation_and_cancel_releases_temporary_state(self):
        self.assertIn("image-confirm-ok", self.app_ui)
        self.assertIn("image-confirm-cancel", self.app_ui)
        self.assertIn('input.dataset.imageConfirmed = "true"', self.app_ui)
        self.assertIn('input.value = ""', self.app_ui)
        self.assertIn("URL.revokeObjectURL", self.app_ui)
        self.assertIn("Confirma o cancela la imagen", self.app_ui)

    def test_art_lightbox_uses_original_image_source(self):
        self.assertIn('id="art-image-lightbox"', self.base)
        self.assertIn('event.target.closest?.("img.art-visual")', self.app_ui)
        self.assertIn("image.currentSrc || image.src", self.app_ui)


if __name__ == "__main__":
    unittest.main()
