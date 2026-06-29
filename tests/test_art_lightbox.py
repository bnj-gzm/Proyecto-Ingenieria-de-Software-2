from pathlib import Path
import unittest


class ArtLightboxFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.base = (root / "frontend/templates/base.html").read_text(encoding="utf-8")
        cls.app_ui = (root / "frontend/static/js/app-ui.js").read_text(encoding="utf-8")
        cls.evidence_templates = {
            name: (root / f"frontend/templates/{name}").read_text(encoding="utf-8")
            for name in (
                "detalle_art.html",
                "art_respuesta_trabajador.html",
                "art_trabajador_form.html",
                "editar_art.html",
                "dashboard.html",
            )
        }

    def test_global_modal_has_overlay_image_and_close_button(self):
        self.assertIn('id="art-image-lightbox"', self.base)
        self.assertIn('id="art-image-lightbox-panel"', self.base)
        self.assertIn('id="art-image-lightbox-image"', self.base)
        self.assertIn('id="art-image-lightbox-close"', self.base)
        self.assertIn('aria-modal="true"', self.base)

    def test_lightbox_has_fade_scale_and_zoom_cursors(self):
        self.assertIn(".image-lightbox.is-open .image-lightbox-panel", self.base)
        self.assertIn("transform: scale(.96)", self.base)
        self.assertIn("transform: scale(1)", self.base)
        self.assertIn("cursor: zoom-in", self.base)
        self.assertIn("cursor: zoom-out", self.base)

    def test_all_art_evidence_surfaces_use_the_global_trigger(self):
        for name, template in self.evidence_templates.items():
            with self.subTest(template=name):
                self.assertIn("art-visual", template)
                self.assertNotIn('target="_blank"', template)
                self.assertNotIn('href="{{ imagen.src }}"', template)

    def test_close_behaviors_and_keyboard_are_connected(self):
        self.assertIn("event.target === imageLightbox", self.app_ui)
        self.assertIn("event.target === imageLightboxPanel", self.app_ui)
        self.assertIn('event.key === "Escape"', self.app_ui)
        self.assertIn('event.key === "Enter" || event.key === " "', self.app_ui)
        self.assertIn('imageLightboxImage?.addEventListener("click", closeImageLightbox)', self.app_ui)
        self.assertIn("lastLightboxTrigger?.focus?.()", self.app_ui)


if __name__ == "__main__":
    unittest.main()
