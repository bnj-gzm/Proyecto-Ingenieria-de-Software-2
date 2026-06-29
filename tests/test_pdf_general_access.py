from pathlib import Path
import inspect
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from backend.src.routes import art
from backend.src.services import pdf_service


class PdfGeneralAccessTests(unittest.TestCase):
    def setUp(self):
        self.registro = {
            "id": "art-pendiente",
            "estado": "pendiente",
            "supervisor_asignado": "supervisor.demo",
            "supervisor": "Supervisor Demo",
            "creado_por": "supervisor.demo",
            "asignaciones": [
                {
                    "id": 10,
                    "trabajador_id": 7,
                    "nombre": "Trabajador Demo",
                    "estado_respuesta": "pendiente",
                    "respuestas": {},
                }
            ],
        }

    @patch.object(art, "generar_art_pdf", return_value=b"%PDF-1.4 test")
    @patch.object(art, "obtener_registro")
    def test_supervisor_downloads_pending_art(self, obtener_registro, generar_pdf):
        obtener_registro.return_value = self.registro

        response = art.descargar_art_pdf(
            self.registro["id"],
            user={"id": 3, "rol": "supervisor", "username": "supervisor.demo"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.media_type, "application/pdf")
        self.assertIn("attachment", response.headers["content-disposition"])
        generar_pdf.assert_called_once_with(self.registro)

    @patch.object(art, "generar_art_pdf", return_value=b"%PDF-1.4 test")
    @patch.object(art, "obtener_registro")
    def test_assigned_worker_can_download_general_pdf(self, obtener_registro, _generar_pdf):
        obtener_registro.return_value = self.registro

        response = art.descargar_art_pdf(
            self.registro["id"],
            user={"id": 7, "rol": "trabajador", "username": "trabajador.demo"},
        )

        self.assertEqual(response.status_code, 200)

    @patch.object(art, "obtener_registro")
    def test_unassigned_worker_gets_403(self, obtener_registro):
        obtener_registro.return_value = self.registro

        with self.assertRaises(HTTPException) as error:
            art.descargar_art_pdf(
                self.registro["id"],
                user={"id": 99, "rol": "trabajador", "username": "otro"},
            )

        self.assertEqual(error.exception.status_code, 403)

    @patch.object(art, "obtener_registro", return_value=None)
    def test_missing_art_gets_404(self, _obtener_registro):
        with self.assertRaises(HTTPException) as error:
            art.descargar_art_pdf(
                "no-existe",
                user={"id": 1, "rol": "admin", "username": "admin"},
            )
        self.assertEqual(error.exception.status_code, 404)


class PdfGeneralPresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.detail = (root / "frontend/templates/detalle_art.html").read_text(encoding="utf-8")
        cls.admin_list = (root / "frontend/templates/admin_art_list.html").read_text(encoding="utf-8")
        cls.worker_response = (root / "frontend/templates/art_respuesta_trabajador.html").read_text(encoding="utf-8")

    def test_general_pdf_button_is_visible_without_final_state_condition(self):
        self.assertIn("Descargar PDF ART General", self.detail)
        self.assertIn('href="/art/{{ registro.id }}/pdf"', self.detail)
        self.assertNotIn("registro.estado in ['aprobada', 'rechazada']", self.detail)
        self.assertIn("Descargar PDF ART General", self.admin_list)
        self.assertNotIn("r.estado in ['aprobada', 'rechazada']", self.admin_list)

    def test_worker_response_exposes_own_general_pdf(self):
        self.assertIn("user.rol == 'trabajador'", self.worker_response)
        self.assertIn('href="/art/{{ registro.id }}/pdf"', self.worker_response)
        individual_end = self.worker_response.index("{% endif %}", self.worker_response.index("asignacion.estado_respuesta == 'aprobado'"))
        general_link = self.worker_response.index('href="/art/{{ registro.id }}/pdf"')
        self.assertGreater(general_link, individual_end)

    def test_pdf_logic_marks_incomplete_data_without_changing_layout_helpers(self):
        source = inspect.getsource(pdf_service.generar_art_pdf)
        signature_source = inspect.getsource(pdf_service._firma_cell)
        self.assertIn('"PENDIENTE"', source)
        self.assertIn('_firmas_block(asignaciones, registro)', source)
        self.assertIn('Firma: SIN RESPONDER', signature_source)

    def test_incomplete_art_still_generates_a_valid_pdf(self):
        pdf = pdf_service.generar_art_pdf(
            {
                "id": "art-incompleta",
                "estado": "pendiente",
                "asignaciones": [
                    {
                        "nombre": "Trabajador pendiente",
                        "estado_respuesta": "pendiente",
                        "respuestas": {},
                    }
                ],
            }
        )
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(pdf), 500)


if __name__ == "__main__":
    unittest.main()
