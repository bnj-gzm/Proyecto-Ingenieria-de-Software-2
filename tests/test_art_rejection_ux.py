import asyncio
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from starlette.requests import Request

from backend.src.routes import admin, art


class ArtRejectionBackendTests(unittest.TestCase):
    @patch.object(art, "validate_csrf_token")
    @patch.object(art, "obtener_asignacion_art")
    @patch.object(art, "obtener_registro")
    def test_empty_rejection_comment_returns_structured_json(
        self,
        obtener_registro,
        obtener_asignacion,
        _validate_csrf,
    ):
        obtener_registro.return_value = {"id": "abc12345", "supervisor_asignado": "supervisor"}
        obtener_asignacion.return_value = {"estado_respuesta": "respondido"}
        request = Request({"type": "http", "method": "POST", "path": "/revision", "headers": []})

        response = art.revisar_respuesta_trabajador(
            request,
            "abc12345",
            10,
            resultado="rechazado",
            comentario_revision="   ",
            csrf_token="token",
            user={"id": 3, "rol": "supervisor", "username": "supervisor"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            json.loads(response.body),
            {
                "error": "validation_error",
                "field": "comentario",
                "message": "Comentario obligatorio para rechazar ART",
            },
        )

    @patch.object(admin, "validate_csrf_token")
    @patch.object(admin, "obtener_registro")
    def test_general_rejection_uses_same_validation_contract(self, obtener_registro, _validate_csrf):
        obtener_registro.return_value = {
            "id": "abc12345",
            "estado": "pendiente",
            "supervisor_asignado": "supervisor",
        }
        request = Request({"type": "http", "method": "POST", "path": "/estado", "headers": []})

        response = asyncio.run(
            admin.admin_change_estado(
                request,
                "abc12345",
                estado="rechazada",
                comentario_supervisor="",
                csrf_token="token",
                user={"id": 3, "rol": "supervisor", "username": "supervisor"},
            )
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(json.loads(response.body)["field"], "comentario")


class ArtRejectionFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.template = (root / "frontend/templates/art_respuesta_trabajador.html").read_text(encoding="utf-8")

    def test_rejection_is_validated_and_sent_as_ajax(self):
        self.assertIn("data-art-review-form", self.template)
        self.assertIn("Debes ingresar un comentario para rechazar la ART", self.template)
        self.assertIn('action !== "rechazado"', self.template)
        self.assertIn("event.preventDefault()", self.template)
        self.assertIn("comment.focus()", self.template)
        self.assertIn('response.status === 400', self.template)
        self.assertIn('"X-Requested-With": "XMLHttpRequest"', self.template)


if __name__ == "__main__":
    unittest.main()
