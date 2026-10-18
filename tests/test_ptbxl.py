"""Checks for the vendored 12-lead checkpoint and its input adapter."""

import io
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from src.inference.ptbxl import (
    LEADS, load_model, predict, read_csv, read_ptbxl_record,
    read_wfdb_record, validate_signal,
)


class PTBXLInferenceTests(unittest.TestCase):
    def test_checkpoint_matches_reference_output(self):
        signal = np.stack([
            np.sin(np.linspace(0, 20 * np.pi, 1000) + lead)
            for lead in range(12)
        ]).astype(np.float32)
        weights, threshold = load_model()
        scores = predict(weights, signal)
        # Generated once with the upstream ECGNet and original .pt checkpoint.
        reference = np.array([
            0.0086740963, 0.9958790541, 0.0874086916,
            0.4339651167, 0.1456722766,
        ])
        np.testing.assert_allclose(scores, reference, atol=1e-6, rtol=0)
        self.assertEqual(threshold, 0.5)

    def test_named_columns_are_reordered_to_ptbxl_lead_order(self):
        values = np.tile(np.arange(12, dtype=np.float32), (1000, 1))
        columns = list(reversed(LEADS))
        frame = pd.DataFrame(values[:, ::-1], columns=columns)
        output = read_csv(frame.to_csv(index=False).encode())
        np.testing.assert_array_equal(output[:, 0], np.arange(12))

    def test_wrong_shape_and_nonfinite_values_are_rejected(self):
        with self.assertRaises(ValueError):
            validate_signal(np.zeros((187, 12)))
        values = np.zeros((1000, 12), dtype=np.float32)
        values[0, 0] = np.nan
        with self.assertRaises(ValueError):
            validate_signal(values)
        with self.assertRaises(ValueError):
            read_csv(io.BytesIO(b"bad,data\n").getvalue())

    def test_local_ptbxl_wfdb_record_can_be_read_by_id_or_path(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            records = root / "records100" / "00000"
            records.mkdir(parents=True)
            time = np.linspace(0, 2 * np.pi, 1000)
            signal = np.stack([0.1 * np.sin(time + lead) for lead in range(12)], axis=1)
            gains = np.full(12, 1000.0)
            baselines = np.arange(12) - 6
            digital = np.rint(signal * gains + baselines).astype("<i2")
            digital.tofile(records / "00001_lr.dat")
            header = ["00001_lr 12 100 1000"]
            header.extend(
                f"00001_lr.dat 16 {gains[i]:.1f}({baselines[i]})/mV 16 0 "
                f"{digital[0, i]} 0 0 {lead}"
                for i, lead in enumerate(LEADS)
            )
            (records / "00001_lr.hea").write_text("\n".join(header) + "\n", encoding="utf-8")
            pd.DataFrame({
                "ecg_id": [1], "filename_lr": ["records100/00000/00001_lr"],
            }).to_csv(root / "ptbxl_database.csv", index=False)

            by_id = read_ptbxl_record(root, 1)
            by_path = read_wfdb_record(records / "00001_lr.hea")
            self.assertEqual(by_id.shape, (12, 1000))
            np.testing.assert_array_equal(by_id, by_path)
            np.testing.assert_allclose(by_id, signal.T, atol=1e-3, rtol=0)
            with self.assertRaises(ValueError):
                read_ptbxl_record(root, 2)
            (records / "00002_hr.hea").write_text("00002_hr 12 500 5000\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "records100"):
                read_wfdb_record(records / "00002_hr")


if __name__ == "__main__":
    unittest.main()
