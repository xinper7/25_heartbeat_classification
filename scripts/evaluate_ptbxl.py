"""Evaluate the unchanged deployed model on all eligible official test-fold ECGs."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
from pathlib import Path
from time import perf_counter

import numpy as np
import pandas as pd

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from src.inference.ptbxl import (
    CLASS_NAMES_ZH, CLASSES, MODEL_PATH, load_model, predict, read_wfdb_record,
)


def divide(numerator, denominator):
    numerator = np.asarray(numerator, dtype=float)
    denominator = np.asarray(denominator, dtype=float)
    return np.divide(numerator, denominator, out=np.zeros_like(numerator), where=denominator != 0)


def metrics(truth: np.ndarray, predicted: np.ndarray) -> dict:
    tp = (truth & predicted).sum(axis=0)
    fp = (~truth & predicted).sum(axis=0)
    fn = (truth & ~predicted).sum(axis=0)
    tn = (~truth & ~predicted).sum(axis=0)
    precision = divide(tp, tp + fp)
    recall = divide(tp, tp + fn)
    f1 = divide(2 * tp, 2 * tp + fp + fn)
    return {
        "exact_match_accuracy": float((truth == predicted).all(axis=1).mean()),
        "hamming_loss": float((truth != predicted).mean()),
        "macro_precision": float(precision.mean()),
        "macro_recall": float(recall.mean()),
        "macro_f1": float(f1.mean()),
        "micro_f1": float(divide(2 * tp.sum(), 2 * tp.sum() + fp.sum() + fn.sum())),
        "per_class": {
            name: {
                "support": int(truth[:, i].sum()),
                "precision": float(precision[i]), "recall": float(recall[i]),
                "f1": float(f1[i]), "tp": int(tp[i]), "fp": int(fp[i]),
                "fn": int(fn[i]), "tn": int(tn[i]),
            } for i, name in enumerate(CLASSES)
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.home() / "Desktop" /
                        "ptb-xl-a-large-publicly-available-electrocardiography-dataset-1.0.3")
    parser.add_argument("--output", type=Path, default=PROJECT / "reports/ptbxl_evaluation")
    args = parser.parse_args()
    metadata = pd.read_csv(args.root / "ptbxl_database.csv")
    statements = pd.read_csv(args.root / "scp_statements.csv", index_col=0)
    diagnostic = statements.loc[statements.diagnostic == 1, "diagnostic_class"].to_dict()
    metadata["labels"] = metadata.scp_codes.map(
        lambda raw: sorted({diagnostic[code] for code in ast.literal_eval(raw)
                            if code in diagnostic and diagnostic[code] in CLASSES})
    )
    all_test = metadata.loc[metadata.strat_fold == 10]
    test = all_test.loc[all_test.labels.map(bool)].sort_values("ecg_id")
    train_patients = set(metadata.loc[metadata.strat_fold <= 8, "patient_id"])
    assert not train_patients.intersection(test.patient_id), "Training/test patients overlap"
    model, threshold = load_model()
    truth = np.asarray([[name in labels for name in CLASSES] for labels in test.labels], dtype=bool)
    scores = []
    start = perf_counter()
    for i, row in enumerate(test.itertuples(), start=1):
        signal = read_wfdb_record(args.root / row.filename_lr)
        scores.append(predict(model, signal))
        if i % 500 == 0 or i == len(test):
            print(f"Evaluated {i}/{len(test)}", flush=True)
    scores = np.asarray(scores)
    predicted = scores >= threshold
    result = metrics(truth, predicted)
    baseline = np.zeros_like(truth)
    baseline[:, CLASSES.index("NORM")] = True
    summary = {
        "dataset": "PTB-XL v1.0.3 records100",
        "dataset_url": "https://physionet.org/content/ptb-xl/1.0.3/",
        "evaluation": "All official fold-10 records with at least one target superclass; no score-based sample selection",
        "total_fold_10": len(all_test), "excluded_no_target_labels": len(all_test) - len(test),
        "evaluated_records": len(test), "patients": int(test.patient_id.nunique()),
        "train_test_patient_overlap": 0, "threshold": threshold,
        "model_sha256": hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest(),
        "metadata_sha256": hashlib.sha256((args.root / "ptbxl_database.csv").read_bytes()).hexdigest(),
        "seconds": perf_counter() - start, "metrics": result,
        "always_norm_baseline": metrics(truth, baseline),
        "limitations": [
            "Same-source held-out evaluation, not external hospital validation.",
            "Five-label exact match requires all labels to match; it is not single-label accuracy.",
            "Threshold remains 0.5; test labels were not used to tune the model or thresholds.",
            "Train/test separation is based on the upstream documented training protocol, not independent training logs.",
        ],
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "metrics.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    with (args.output / "predictions.jsonl").open("w", encoding="utf-8") as stream:
        for row, y, score in zip(test.itertuples(), truth, scores):
            item = {
                "ecg_id": int(row.ecg_id), "filename_lr": row.filename_lr,
                "true_labels": [name for name, present in zip(CLASSES, y) if present],
                "predicted_labels": [name for name, value in zip(CLASSES, score) if value >= threshold],
                "scores": dict(zip(CLASSES, map(float, score))),
                "exact_match": bool(np.array_equal(y, score >= threshold)),
            }
            stream.write(json.dumps(item, ensure_ascii=False) + "\n")
    lines = [
        "# PTB-XL 预训练模型完整测试折评估", "",
        f"评估数据：PTB-XL v1.0.3 records100，官方第 10 折。原有 {len(all_test)} 条，排除无目标标签的 {len(all_test)-len(test)} 条，共评估 {len(test)} 条、{test.patient_id.nunique()} 位患者。",
        "", "按上游公开训练规则，训练只使用第 1–8 折；本次核查训练折与测试折无患者交叉。该结论依据公开规则，不是独立审计上游训练日志。",
        "", "本次未训练、微调、调整阈值或按预测结果筛选样本；使用原有权重和固定阈值 0.5。", "",
        "| 指标 | 本地实测 |", "| --- | ---: |",
        f"| 宏平均精确率 | {result['macro_precision']:.4f} |",
        f"| 宏平均召回率 | {result['macro_recall']:.4f} |",
        f"| 宏平均 F1 | {result['macro_f1']:.4f} |",
        f"| 微平均 F1 | {result['micro_f1']:.4f} |",
        f"| 五标签完全匹配率 | {result['exact_match_accuracy']:.2%} |",
        f"| 标签错误比例（Hamming loss） | {result['hamming_loss']:.2%} |", "",
        "完全匹配率要求五个标签全部正确，不应与普通单分类准确率直接比较。", "",
        "| 类别 | 阳性记录数 | 精确率 | 召回率 | F1 | 误报数 | 漏报数 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, item in result["per_class"].items():
        lines.append(f"| {CLASS_NAMES_ZH[name]}（{name}） | {item['support']} | {item['precision']:.4f} | {item['recall']:.4f} | {item['f1']:.4f} | {item['fp']} | {item['fn']} |")
    lines += ["", "类别支持数之和可超过记录数，因为一条记录可能有多个标签。", "",
              f"始终只输出正常（NORM）的基线：宏平均 F1 {summary['always_norm_baseline']['macro_f1']:.4f}，完全匹配率 {summary['always_norm_baseline']['exact_match_accuracy']:.2%}。", "",
              "这是同源留出测试结果，尚不能证明在其他医院、设备或标注体系中的表现。", "",
              "逐条真值、预测标签和五类分数见 predictions.jsonl；来源和模型校验值见 metrics.json。", "",
              "复现：`python scripts/evaluate_ptbxl.py`，必要时用 `--root` 指定原始数据集根目录。", ""]
    (args.output / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
