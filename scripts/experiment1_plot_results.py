"""Draw a static, reproducible comparison figure from experiment 1 metrics."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


PROJECT = Path(__file__).resolve().parents[1]
SOURCE = PROJECT / "reports/experiment1_artifacts/sampling_comparison.json"
OUTPUT = PROJECT / "reports/experiment1_artifacts/augmentation_comparison.png"


def main() -> None:
    results = json.loads(SOURCE.read_text(encoding="utf-8"))["models"]
    variants = ("no_sampling", "smote_train_only")
    labels = ("No sampling", "SMOTE (train only)")
    colors = ("#2563eb", "#f97316")
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.5), dpi=170, sharey=True)
    for ax, split in zip(axes, ("validation", "test")):
        for index, variant in enumerate(variants):
            value = results[variant][split]["f1_macro"]
            ax.bar(index, value, color=colors[index], width=0.55)
            ax.text(index, value + 0.008, f"{value:.4f}", ha="center", fontsize=10)
        ax.set_xticks(np.arange(2), labels)
        ax.set_ylim(0, 0.86)
        ax.set_title(f"{split.title()} · macro F1", fontsize=13, weight="bold")
        ax.grid(axis="y", alpha=0.22)
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("Macro F1")
    fig.suptitle("PTB-XL 12-lead feature baseline | patient-disjoint folds", fontsize=13)
    fig.text(0.5, 0.01, "Fixed logistic regression; SMOTE is fitted on training folds only.",
             ha="center", fontsize=9, color="#475569")
    fig.tight_layout(rect=(0, 0.04, 1, 0.96))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(OUTPUT)


if __name__ == "__main__":
    main()
