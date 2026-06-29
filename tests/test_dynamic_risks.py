from pathlib import Path
import inspect
import unittest

from backend.src.routes import art


class DynamicRiskRowsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.new_art = (root / "frontend/templates/nueva_art.html").read_text(encoding="utf-8")
        cls.edit_art = (root / "frontend/templates/editar_art.html").read_text(encoding="utf-8")
        cls.row = (root / "frontend/templates/partials/riesgo_row.html").read_text(encoding="utf-8")
        cls.base = (root / "frontend/templates/base.html").read_text(encoding="utf-8")
        cls.app_ui = (root / "frontend/static/js/app-ui.js").read_text(encoding="utf-8")
        cls.risk_ui = (root / "frontend/static/js/risk-table.js").read_text(encoding="utf-8")

    def test_creation_and_editing_use_same_dynamic_component(self):
        for template in (self.new_art, self.edit_art):
            self.assertIn("data-risk-form", template)
            self.assertIn("data-risk-add", template)
            self.assertIn("Agregar Riesgo", template)
            self.assertIn("data-risk-rows", template)
            self.assertIn("data-risk-error", template)
            self.assertNotIn("hx-get=\"/partials/riesgo-row\"", template)
            self.assertNotIn("data-risk-row-template", template)

    def test_row_keeps_backend_compatible_parallel_field_names(self):
        self.assertIn('name="secuencia"', self.row)
        self.assertIn('name="riesgo"', self.row)
        self.assertIn('name="control"', self.row)
        self.assertEqual(self.row.count("required"), 3)
        self.assertIn("data-risk-remove", self.row)
        self.assertIn("Eliminar", self.row)

    def test_vanilla_controller_adds_removes_and_reindexes_rows(self):
        self.assertIn('baseRow.cloneNode(true)', self.risk_ui)
        self.assertIn('addButton.addEventListener("click", addRow)', self.risk_ui)
        self.assertIn('row.remove()', self.risk_ui)
        self.assertIn('textContent = String(index + 1)', self.risk_ui)
        self.assertIn('requestAnimationFrame', self.risk_ui)
        self.assertNotIn('htmx.ajax', self.risk_ui)

    def test_component_always_keeps_one_row_and_disables_its_delete_button(self):
        self.assertIn("activeRows().length <= 1", self.risk_ui)
        self.assertIn("row.parentElement !== body", self.risk_ui)
        self.assertIn("removeButton.disabled = isOnlyRow", self.risk_ui)
        self.assertIn('aria-disabled', self.risk_ui)
        self.assertIn('.risk-remove-button:disabled', self.base)

    def test_internal_row_state_and_clean_cloning_match_requested_shape(self):
        self.assertIn("let riskRowsState = []", self.risk_ui)
        self.assertIn("actividad:", self.risk_ui)
        self.assertIn("riesgo:", self.risk_ui)
        self.assertIn("control:", self.risk_ui)
        self.assertIn('field.value = ""', self.risk_ui)
        self.assertIn("risk-table-scroll", self.new_art)
        self.assertIn("risk-table-scroll", self.edit_art)
        self.assertIn("[data-risk-field] { min-height:", self.base)

    def test_incomplete_and_empty_rows_block_submission_visually(self):
        self.assertIn('currentRows.length >= 1', self.risk_ui)
        self.assertIn('event.preventDefault()', self.risk_ui)
        self.assertIn('risk-row-invalid', self.risk_ui)
        self.assertIn('aria-invalid', self.risk_ui)
        self.assertIn('[data-risk-row].risk-row-removing', self.base)
        self.assertIn('.risk-field-invalid', self.base)

    def test_dedicated_controller_is_cache_busted_and_initialized_once(self):
        self.assertIn('/static/js/risk-table.js?v=20260629.2', self.base)
        self.assertIn('riskInitialized', self.risk_ui)
        self.assertNotIn('[data-risk-form]', self.app_ui)

    def test_backend_still_reconstructs_the_expected_list_of_objects(self):
        create_source = inspect.getsource(art.guardar_art)
        edit_source = inspect.getsource(art.editar_art_post)
        expected = '{"secuencia": seq.strip(), "riesgo": risk.strip(), "control": ctrl.strip()}'
        for source in (create_source, edit_source):
            self.assertIn("zip(secuencia or [], riesgo or [], control or [])", source)
            self.assertIn(expected, source)


if __name__ == "__main__":
    unittest.main()
