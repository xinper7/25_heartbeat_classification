"""Render the experiment-1 data directory diagram from the local filesystem."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


PROJECT = Path(__file__).resolve().parents[1]
PTBXL = Path.home() / "Desktop" / "ptb-xl-a-large-publicly-available-electrocardiography-dataset-1.0.3"
OUTPUT = PROJECT / "reports" / "experiment1_dataset_structure.png"


def status(path: Path) -> str:
    if not path.exists():
        return "[missing]"
    return "[present]"


def main() -> None:
    n_lr = sum(1 for _ in (PTBXL / "records100").rglob("*.hea")) if PTBXL.exists() else 0
    n_hr = sum(1 for _ in (PTBXL / "records500").rglob("*.hea")) if PTBXL.exists() else 0
    n_lr_dat = sum(1 for _ in (PTBXL / "records100").rglob("*.dat")) if PTBXL.exists() else 0
    n_hr_dat = sum(1 for _ in (PTBXL / "records500").rglob("*.dat")) if PTBXL.exists() else 0
    lines = [
        (0, "PTB-XL v1.0.3 source data (Desktop)/"),
        (1, f"ptbxl_database.csv  {status(PTBXL / 'ptbxl_database.csv')}"),
        (1, f"scp_statements.csv  {status(PTBXL / 'scp_statements.csv')}"),
        (1, f"records100/  {n_lr:,} .hea + {n_lr_dat:,} .dat files"),
        (1, f"records500/  {n_hr:,} .hea + {n_hr_dat:,} .dat files"),
        (0, "Experiment 1 local outputs/"),
        (1, f"data/interim/experiment1/ptbxl_reports_raw.jsonl  {status(PROJECT / 'data/interim/experiment1/ptbxl_reports_raw.jsonl')}"),
        (1, f"data/processed/experiment1/ptbxl_manifest.csv  {status(PROJECT / 'data/processed/experiment1/ptbxl_manifest.csv')}"),
        (1, f"data/processed/experiment1/ptbxl_signal_features.npz  {status(PROJECT / 'data/processed/experiment1/ptbxl_signal_features.npz')}"),
        (1, f"data/processed/experiment1/dj_runs/ptbxl_text_20261010_v4/ptbxl_reports_clean.jsonl  {status(PROJECT / 'data/processed/experiment1/dj_runs/ptbxl_text_20261010_v4/ptbxl_reports_clean.jsonl')}"),
        (1, f"reports/experiment1_artifacts/source_audit.json  {status(PROJECT / 'reports/experiment1_artifacts/source_audit.json')}"),
        (1, f"reports/experiment1_artifacts/text_curation_comparison.json  {status(PROJECT / 'reports/experiment1_artifacts/text_curation_comparison.json')}"),
        (1, f"reports/experiment1_artifacts/sampling_comparison.json  {status(PROJECT / 'reports/experiment1_artifacts/sampling_comparison.json')}"),
    ]

    font_path = Path("C:/Windows/Fonts/consola.ttf")
    font = ImageFont.truetype(str(font_path), 25) if font_path.exists() else ImageFont.load_default()
    title_font = ImageFont.truetype(str(font_path), 29) if font_path.exists() else ImageFont.load_default()
    width, line_height, top = 1900, 42, 110
    image = Image.new("RGB", (width, top + len(lines) * line_height + 48), "#111827")
    draw = ImageDraw.Draw(image)
    draw.text((45, 32), f"DATA DIRECTORY SCAN  |  {date.today().isoformat()}", font=title_font, fill="#e5e7eb")
    draw.line((45, 82, width - 45, 82), fill="#3b82f6", width=3)
    for index, (indent, label) in enumerate(lines):
        color = "#93c5fd" if indent == 0 else "#e5e7eb"
        draw.text((50 + indent * 44, top + index * line_height), label, font=font, fill=color)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUTPUT)
    print(OUTPUT)


if __name__ == "__main__":
    main()
