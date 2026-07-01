from pathlib import Path
import unittest

from backend.app import app
from backend.src.routes.art import _validar_horario


class ArtScheduleValidationTests(unittest.TestCase):
    def test_empty_optional_schedule_is_valid(self):
        self.assertEqual(_validar_horario("", ""), {})

    def test_schedule_requires_complete_hhmm_range(self):
        self.assertIn("hora_termino", _validar_horario("08:00", ""))
        self.assertIn("hora_inicio", _validar_horario("-1:00", "09:00"))
        self.assertIn("hora_termino", _validar_horario("08:00", "24:00"))

    def test_start_must_be_before_end(self):
        self.assertEqual(_validar_horario("08:00", "09:00"), {})
        self.assertIn("hora_termino", _validar_horario("09:00", "09:00"))
        self.assertIn("hora_termino", _validar_horario("10:00", "09:00"))


class ArtFormUxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.new_art = (root / "frontend/templates/nueva_art.html").read_text(encoding="utf-8")
        cls.edit_art = (root / "frontend/templates/editar_art.html").read_text(encoding="utf-8")
        cls.validation_js = (root / "frontend/static/js/art-form-validation.js").read_text(encoding="utf-8")

    def test_time_errors_are_inline_and_validation_is_interaction_driven(self):
        for template in (self.new_art, self.edit_art):
            self.assertIn("data-art-schedule-form", template)
            self.assertIn('data-time-error="hora_inicio"', template)
            self.assertIn('data-time-error="hora_termino"', template)
        self.assertIn('form.addEventListener("submit"', self.validation_js)
        self.assertNotIn('addEventListener("blur"', self.validation_js)
        self.assertNotIn('addEventListener("input"', self.validation_js)

    def test_worker_and_risk_errors_wait_for_submit(self):
        risk_ui = (Path(__file__).resolve().parents[1] / "frontend/static/js/risk-table.js").read_text(encoding="utf-8")
        self.assertIn("let submitAttempted = false", self.new_art)
        self.assertIn("submitAttempted = true", self.new_art)
        self.assertIn('!submitAttempted || valid', self.new_art)
        input_handler = risk_ui.split('body.addEventListener("input"', 1)[1].split("});", 1)[0]
        self.assertIn("updateState()", input_handler)
        self.assertNotIn("validateRow", input_handler)
        self.assertNotIn('form.addEventListener("invalid"', risk_ui)
        remove_handler = risk_ui.split("window.setTimeout(() => {", 1)[1].split("}, 180);", 1)[0]
        self.assertNotIn("validateRow", remove_handler)

    def test_test_email_endpoint_is_registered_as_post(self):
        methods_by_path = {
            route.path: route.methods
            for route in app.routes
            if getattr(route, "path", None) == "/admin/test-email"
        }
        self.assertIn("/admin/test-email", methods_by_path)
        self.assertEqual(methods_by_path["/admin/test-email"], {"POST"})


if __name__ == "__main__":
    unittest.main()
