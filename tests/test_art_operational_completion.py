from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from backend.src.services import art_service


class ArtOperationalCompletionTests(unittest.TestCase):
    @patch.object(art_service, "_connect")
    def test_last_completed_review_closes_pending_art_atomically(self, connect):
        cursor = MagicMock()
        cursor.fetchone.side_effect = [("abc12345",), ("abc12345",), ("abc12345",)]
        connection = MagicMock()
        connection.cursor.return_value = cursor
        connect.return_value = connection

        completed = art_service.actualizar_revision_asignacion(10, "aprobado", "Revisada", 3)

        self.assertTrue(completed)
        self.assertEqual(cursor.execute.call_count, 3)
        self.assertIn("FOR UPDATE", cursor.execute.call_args_list[1].args[0])
        completion_sql = cursor.execute.call_args_list[2].args[0]
        self.assertIn("SET estado = 'completada'", completion_sql)
        self.assertIn("ar.estado = 'pendiente'", completion_sql)
        self.assertIn("NOT EXISTS", completion_sql)
        self.assertIn("NOT IN ('aprobado', 'rechazado')", completion_sql)
        connection.commit.assert_called_once()

    @patch.object(art_service, "_connect")
    def test_art_stays_open_while_any_review_is_pending(self, connect):
        cursor = MagicMock()
        cursor.fetchone.side_effect = [("abc12345",), ("abc12345",), None]
        connection = MagicMock()
        connection.cursor.return_value = cursor
        connect.return_value = connection

        completed = art_service.actualizar_revision_asignacion(10, "aprobado", "Revisada", 3)

        self.assertFalse(completed)
        connection.commit.assert_called_once()


class ArtOperationalFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.detail = (root / "frontend/templates/detalle_art.html").read_text(encoding="utf-8")
        cls.dashboard = (root / "frontend/templates/dashboard.html").read_text(encoding="utf-8")
        cls.admin_list = (root / "frontend/templates/admin_art_list.html").read_text(encoding="utf-8")

    def test_completed_state_is_visible_in_operational_surfaces(self):
        self.assertIn("Estado operacional", self.detail)
        self.assertIn("registro.estado == 'completada'", self.detail)
        self.assertIn("stats.completadas", self.dashboard)
        self.assertIn('value="completada"', self.admin_list)
        self.assertIn("resumen.completadas", self.admin_list)


if __name__ == "__main__":
    unittest.main()
