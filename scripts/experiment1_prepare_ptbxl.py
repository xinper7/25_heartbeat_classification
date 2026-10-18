"""Build a reproducible PTB-XL manifest and text-curation input for experiment 1.

This script does not change the downloaded PTB-XL dataset. It records metadata,
labels and paths; patient-level folds come from PTB-XL v1.0.3 itself.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from collections import Counter
from pathlib import Path

import pandas as pd


PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = Path.home() / "Desktop" / "ptb-xl-a-large-publicly-available-electrocardiography-dataset-1.0.3"
CLASSES = {"NORM", "MI", "STTC", "CD", "HYP"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    metadata_path = root / "ptbxl_database.csv"
    statements_path = root / "scp_statements.csv"
    if not metadata_path.is_file() or not statements_path.is_file():
        raise FileNotFoundError("PTB-XL 根目录需包含 ptbxl_database.csv 与 scp_statements.csv")

    metadata = pd.read_csv(metadata_path)
    statements = pd.read_csv(statements_path)
    class_map = statements.set_index("Unnamed: 0")["diagnostic_class"].dropna().to_dict()
    if metadata["ecg_id"].duplicated().any():
        raise ValueError("ecg_id 不唯一")
    if metadata["patient_id"].isna().any():
        raise ValueError("patient_id 存在空值，无法验证患者隔离")
    patient_folds = metadata.groupby("patient_id")["strat_fold"].nunique()
    if (patient_folds > 1).any():
        raise ValueError("同一患者出现在多个 strat_fold 中")

    interim = PROJECT / "data" / "interim" / "experiment1"
    processed = PROJECT / "data" / "processed" / "experiment1"
    audit_dir = PROJECT / "reports" / "experiment1_artifacts"
    for folder in (interim, processed, audit_dir):
        folder.mkdir(parents=True, exist_ok=True)
    raw_text_path = interim / "ptbxl_reports_raw.jsonl"
    manifest_path = processed / "ptbxl_manifest.csv"

    manifest_rows = []
    label_counts = Counter()
    empty_text = 0
    missing_pair = 0
    with raw_text_path.open("w", encoding="utf-8", newline="\n") as output:
        for row in metadata.itertuples(index=False):
            ecg_id = int(row.ecg_id)
            codes = ast.literal_eval(row.scp_codes)
            labels = sorted({class_map[code] for code in codes if code in class_map} & CLASSES)
            label_counts.update(labels)
            text = "" if pd.isna(row.report) else str(row.report)
            empty_text += not text.strip()
            relative = Path(str(row.filename_lr))
            record = (root / relative).resolve()
            if not record.is_relative_to(root):
                raise ValueError(f"记录路径越过数据根目录: {relative}")
            if not record.with_suffix(".hea").is_file() or not record.with_suffix(".dat").is_file():
                missing_pair += 1
            fold = int(row.strat_fold)
            split = "train" if fold <= 8 else "validation" if fold == 9 else "test"
            output.write(json.dumps({
                "ecg_id": ecg_id,
                "text": text,
                "label": labels,
                "strat_fold": fold,
            }, ensure_ascii=False) + "\n")
            manifest_rows.append({
                "ecg_id": ecg_id,
                "patient_id": int(row.patient_id),
                "filename_lr": relative.as_posix(),
                "strat_fold": fold,
                "split": split,
                "labels": "|".join(labels),
                "report_nonempty": bool(text.strip()),
            })

    manifest = pd.DataFrame(manifest_rows)
    manifest.to_csv(manifest_path, index=False, encoding="utf-8")
    audit = {
        "dataset": "PTB-XL",
        "version": "1.0.3",
        "records": len(metadata),
        "metadata_columns": len(metadata.columns),
        "patients": int(metadata.patient_id.nunique()),
        "duplicate_ecg_id": int(metadata.ecg_id.duplicated().sum()),
        "patients_across_folds": int((patient_folds > 1).sum()),
        "blank_reports_before": int(empty_text),
        "missing_wfdb_pairs": int(missing_pair),
        "split_counts": {k: int(v) for k, v in manifest.split.value_counts().items()},
        "label_counts_multilabel": dict(label_counts),
        "source_files_sha256": {
            "ptbxl_database.csv": sha256(metadata_path),
            "scp_statements.csv": sha256(statements_path),
        },
        "outputs": {
            "raw_text_jsonl": str(raw_text_path.relative_to(PROJECT)),
            "manifest_csv": str(manifest_path.relative_to(PROJECT)),
        },
    }
    (audit_dir / "source_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
