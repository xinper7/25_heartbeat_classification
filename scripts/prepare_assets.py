"""Developer-only packaging from the adjacent experiment archive; sources stay untouched."""

import csv
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent


def main():
    models = ROOT / "models"
    models.mkdir(exist_ok=True)
    manifest = {}
    for kind, source, filename, directory, version in [
        (
            "signal",
            SOURCE / "results/optimized/best_model.pt",
            "resnet1d_a3.pt",
            "optimized",
            "resnet1d-a3-seed42-epoch21",
        ),
        (
            "image",
            SOURCE / "experiment3/models/efficientnet_b0.onnx",
            "efficientnet_b0_fp32.onnx",
            "image_aug",
            "efficientnet-b0-b2-fp32-epoch25",
        ),
    ]:
        target = models / filename
        shutil.copyfile(source, target)
        with (SOURCE / f"results/{directory}/thresholds.csv").open(
            encoding="utf-8-sig"
        ) as f:
            thresholds = {r["class"]: float(r["threshold"]) for r in csv.DictReader(f)}
        manifest[kind] = dict(
            file=filename,
            version=version,
            sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
            classes=["NORM", "MI", "STTC", "CD", "HYP"],
            thresholds=[thresholds[c] for c in ["NORM", "MI", "STTC", "CD", "HYP"]],
            source=str(source.relative_to(SOURCE)),
            license="See LICENSE and THIRD_PARTY_NOTICES.md",
        )
    manifest["signal"].update(
        mean=-0.000825238479071099,
        std=0.2319963188761816,
        input_shape=[1, 12, 1000],
        preprocessing="100Hz, 10s, 40Hz lowpass physical mV, global train-only z-score",
    )
    manifest["image"].update(
        input_shape=[1, 3, 224, 224],
        preprocessing="Pillow bilinear resize 224x224, RGB /255, ImageNet mean/std",
    )
    (models / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    shutil.copyfile(SOURCE / "ecg_ptbxl_benchmarking/LICENSE", ROOT / "LICENSE")
    base = SOURCE / "DATA/ptb-xl-1.0.3-processed-wfdb-v1"
    with (base / "test/manifest.csv").open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    selected = []
    for c in ["NORM", "MI", "STTC", "CD", "HYP"]:
        selected.append(
            next(
                r
                for r in rows
                if r["y_" + c] == "1"
                and r["ecg_id"] not in {s["ecg_id"] for s in selected}
            )
        )
    sample_root = ROOT / "sample-data"
    sample_root.mkdir(exist_ok=True)
    metadata = []
    ids = np.load(SOURCE / "results/optimized/test_ids.npy")
    signal_preds = np.load(SOURCE / "results/optimized/y_test_pred.npy")
    image_preds = np.load(
        SOURCE
        / "experiment3/results/evaluation_test_20261031_191937_670525/onnxruntime_predictions.npy"
    )
    image_ids = np.load(
        SOURCE
        / "experiment3/results/evaluation_test_20261031_191937_670525/ecg_ids.npy"
    )
    for row in selected:
        eid = int(row["ecg_id"])
        folder = sample_root / str(eid)
        folder.mkdir(exist_ok=True)
        src = base / row["filename_lr"]
        for ext in (".hea", ".dat"):
            shutil.copyfile(Path(str(src) + ext), folder / (src.name + ext))
        shutil.copyfile(SOURCE / f"ECG_IMAGES/test/{eid}.png", folder / "report.png")
        metadata.append(
            dict(
                ecg_id=eid,
                directory=str(eid),
                source_split="test",
                signal_profile="filtered_mv",
                labels=[
                    c
                    for c in ["NORM", "MI", "STTC", "CD", "HYP"]
                    if row["y_" + c] == "1"
                ],
                expected_signal=signal_preds[
                    int(np.flatnonzero(ids == eid)[0])
                ].tolist(),
                expected_image=image_preds[
                    int(np.flatnonzero(image_ids == eid)[0])
                ].tolist(),
            )
        )
    # Portable CSV example contains the same unstandardized filtered physical samples.
    first = sample_root / str(metadata[0]["ecg_id"])
    hea = next(first.glob("*.hea"))
    raw = (
        np.fromfile(hea.with_suffix(".dat"), dtype="<i2")
        .reshape(1000, 12)
        .astype(float)
        / 1000
    )
    with (first / "signal.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]
        )
        writer.writerows(raw)
    (sample_root / "manifest.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        "Packaged 2 models, fixed configs, 5 sample pairs and 1 CSV; original archive unchanged."
    )


if __name__ == "__main__":
    main()
