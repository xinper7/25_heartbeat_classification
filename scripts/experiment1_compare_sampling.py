"""Controlled preprocessing comparison on PTB-XL v1.0.3, not a deployed model.

The binary teaching task is NORM-only versus at least one non-NORM diagnostic
superclass. Mixed/unspecified records are excluded, and the official
patient-disjoint strat_fold split is kept. The two fixed logistic-regression
pipelines differ only in training-fold SMOTE; validation/test are untouched.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from time import perf_counter

import numpy as np
import pandas as pd
from imblearn.over_sampling import SMOTE
from imblearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score
from sklearn.preprocessing import StandardScaler

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from src.inference.ptbxl import read_wfdb_record


DEFAULT_ROOT = Path.home() / "Desktop" / "ptb-xl-a-large-publicly-available-electrocardiography-dataset-1.0.3"
FEATURE_FILE = PROJECT / "data" / "processed" / "experiment1" / "ptbxl_signal_features.npz"
RESULT_FILE = PROJECT / "reports" / "experiment1_artifacts" / "sampling_comparison.json"


def summarize_signal(signal: np.ndarray) -> np.ndarray:
    """Five transparent signal summaries per lead, in standard lead order."""
    return np.concatenate(
        [
            signal.mean(axis=1),
            signal.std(axis=1),
            signal.min(axis=1),
            signal.max(axis=1),
            np.abs(np.diff(signal, axis=1)).mean(axis=1),
        ]
    ).astype(np.float32)


def build_features(root: Path, manifest: pd.DataFrame) -> tuple[np.ndarray, dict]:
    features = np.empty((len(manifest), 60), dtype=np.float32)
    nonfinite_records = 0
    constant_leads = 0
    maximum_absolute_mv = 0.0
    started = perf_counter()
    for index, relative in enumerate(manifest.filename_lr):
        signal = read_wfdb_record(root / relative)
        nonfinite_records += not bool(np.isfinite(signal).all())
        constant_leads += int(np.count_nonzero(signal.std(axis=1) < 1e-8))
        maximum_absolute_mv = max(maximum_absolute_mv, float(np.max(np.abs(signal))))
        features[index] = summarize_signal(signal)
        if (index + 1) % 5000 == 0:
            print(f"波形特征提取：{index + 1}/{len(manifest)}", flush=True)
    FEATURE_FILE.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(FEATURE_FILE, ecg_id=manifest.ecg_id.to_numpy(), features=features)
    return features, {
        "records_read": len(manifest),
        "nonfinite_records": nonfinite_records,
        "constant_leads": constant_leads,
        "max_abs_mv": maximum_absolute_mv,
        "seconds": round(perf_counter() - started, 3),
    }


def scores(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    return {
        "n": len(y_true),
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 6),
        "balanced_accuracy": round(float(balanced_accuracy_score(y_true, y_pred)), 6),
        "f1_macro": round(float(f1_score(y_true, y_pred, average="macro")), 6),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--reuse-features", action="store_true")
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    manifest = pd.read_csv(PROJECT / "data/processed/experiment1/ptbxl_manifest.csv")
    if args.reuse_features:
        cached = np.load(FEATURE_FILE)
        if not np.array_equal(cached["ecg_id"], manifest.ecg_id.to_numpy()):
            raise ValueError("特征缓存的 ecg_id 顺序与 manifest 不一致")
        features = cached["features"]
        signal_audit = {"records_read": len(manifest), "feature_cache_reused": True}
    else:
        features, signal_audit = build_features(root, manifest)

    label_sets = [set(str(value).split("|")) if pd.notna(value) and str(value) else set()
                  for value in manifest.labels]
    normal = np.array([labels == {"NORM"} for labels in label_sets])
    abnormal = np.array([bool(labels - {"NORM"}) and "NORM" not in labels for labels in label_sets])
    eligible = normal | abnormal
    x = features[eligible]
    y = abnormal[eligible].astype(np.int8)
    fold = manifest.strat_fold.to_numpy()[eligible]
    masks = {"train": fold <= 8, "validation": fold == 9, "test": fold == 10}
    counts = {name: {"normal": int(np.count_nonzero(y[mask] == 0)),
                     "abnormal": int(np.count_nonzero(y[mask] == 1))}
              for name, mask in masks.items()}

    common_clf = {"C": 1.0, "max_iter": 2000, "random_state": 42}
    variants = {
        "no_sampling": Pipeline([
            ("scale", StandardScaler()),
            ("model", LogisticRegression(**common_clf)),
        ]),
        "smote_train_only": Pipeline([
            ("scale", StandardScaler()),
            ("sample", SMOTE(random_state=42, k_neighbors=5)),
            ("model", LogisticRegression(**common_clf)),
        ]),
    }
    results = {}
    for name, pipeline in variants.items():
        started = perf_counter()
        pipeline.fit(x[masks["train"]], y[masks["train"]])
        results[name] = {
            "train_seconds": round(perf_counter() - started, 3),
            "validation": scores(y[masks["validation"]], pipeline.predict(x[masks["validation"]])),
            "test": scores(y[masks["test"]], pipeline.predict(x[masks["test"]])),
        }

    report = {
        "purpose": "data-augmentation teaching comparison; not the application's PTB-XL diagnostic model",
        "source": "PTB-XL v1.0.3 records100",
        "label_rule": "NORM-only=0, non-NORM diagnostic superclass without NORM=1; mixed/no-diagnostic excluded",
        "excluded_mixed_or_unlabelled": int(np.count_nonzero(~eligible)),
        "features": "per lead: mean, standard deviation, minimum, maximum, mean absolute first difference (60 total)",
        "split": "official strat_fold: 1-8 train, 9 validation, 10 test; patient disjoint",
        "counts": counts,
        "signal_audit": signal_audit,
        "models": results,
        "versions": {
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scikit_learn": __import__("sklearn").__version__,
            "imbalanced_learn": __import__("imblearn").__version__,
        },
    }
    RESULT_FILE.parent.mkdir(parents=True, exist_ok=True)
    RESULT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
