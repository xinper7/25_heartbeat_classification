"""Regression checks for the 12-lead application's entry points and inputs."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from streamlit.testing.v1 import AppTest

from src.inference.ptbxl import LEADS


ROOT = Path(__file__).resolve().parents[1]


class PTBXLAppTests(unittest.TestCase):
    def _open_app(self, entry="app.py"):
        with patch.object(sys, "path", [str(ROOT / "app"), *sys.path]):
            return AppTest.from_file(str(ROOT / "app" / entry), default_timeout=20).run()

    def test_both_entry_points_open_without_loading_a_model(self):
        for entry in ("app.py", "detect.py"):
            with self.subTest(entry=entry):
                with patch("src.inference.ptbxl.load_model", side_effect=AssertionError("model must remain disabled")) as load_model:
                    app = self._open_app(entry)
                    load_model.assert_not_called()
                self.assertEqual(len(app.exception), 0)
                self.assertEqual(len(app.radio), 1)
                self.assertEqual(len(app.radio[0].options), 3)
                self.assertEqual(len(app.button), 1)
                self.assertEqual(app.button[0].label, "读取并查看波形")
                self.assertTrue(any("当前未启用分类模型" in item.value for item in app.info))

    def test_missing_wfdb_path_is_reported_without_crashing(self):
        app = self._open_app()
        app.radio[0].set_value(app.radio[0].options[1]).run()
        app.button[0].click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.error), 1)
        self.assertEqual(len(app.dataframe), 0)

    def test_wfdb_record_previews_signal_without_loading_or_predicting(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            digital = np.stack([
                100 * np.sin(np.linspace(0, 20 * np.pi, 1000) + lead)
                for lead in range(12)
            ], axis=1).astype("<i2")
            digital.tofile(root / "example.dat")
            header = ["example 12 100 1000"]
            header.extend(
                f"example.dat 16 1000.0(0)/mV 16 0 {digital[0, i]} 0 0 {lead}"
                for i, lead in enumerate(LEADS)
            )
            (root / "example.hea").write_text("\n".join(header) + "\n", encoding="utf-8")
            with patch("src.inference.ptbxl.load_model", side_effect=AssertionError("model must remain disabled")) as load_model, \
                 patch("src.inference.ptbxl.predict", side_effect=AssertionError("prediction must remain disabled")) as predict:
                app = self._open_app()
                app.radio[0].set_value(app.radio[0].options[1]).run()
                app.text_input[0].set_value(str(root / "example.hea"))
                app.button[0].click().run()
                load_model.assert_not_called()
                predict.assert_not_called()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(len(app.error), 0)
            self.assertEqual(app.dataframe[0].value.shape, (1000, 12))
            self.assertEqual(list(app.dataframe[0].value.columns), list(LEADS))
            np.testing.assert_allclose(app.dataframe[0].value.to_numpy(), digital / 1000, atol=1e-8)


if __name__ == "__main__":
    unittest.main()
