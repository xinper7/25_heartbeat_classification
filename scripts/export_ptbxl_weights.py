"""Recreate the NumPy inference weights from the pinned upstream checkpoint.

Run with a Python environment containing torch and numpy. The app itself
does not require torch.
"""

import hashlib
from pathlib import Path

import numpy as np
import torch


ROOT = Path(__file__).resolve().parents[1] / "models/PTB_XL_12lead"
SOURCE = ROOT / "best_model.pt"
TARGET = ROOT / "weights.npz"
EXPECTED_SHA256 = "3c92797fc3c74165c5715ac21fd8a7723fc2c4a39812f0fba340d531abcd9157"


def main():
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest() != EXPECTED_SHA256:
        raise ValueError("Upstream checkpoint hash mismatch")
    payload = torch.load(SOURCE, map_location="cpu", weights_only=True)
    if payload["classes"] != ["NORM", "MI", "STTC", "CD", "HYP"]:
        raise ValueError("Unexpected checkpoint labels")
    arrays = {
        key: value.detach().cpu().numpy()
        for key, value in payload["model"].items()
        if not key.endswith("num_batches_tracked")
    }
    arrays["classes"] = np.asarray(payload["classes"])
    arrays["threshold"] = np.asarray(float(payload["threshold"]), dtype=np.float32)
    np.savez_compressed(TARGET, **arrays)
    print(TARGET, hashlib.sha256(TARGET.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
