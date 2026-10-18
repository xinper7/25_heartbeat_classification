"""Audit Data-Juicer's five-op text result against a simple Python baseline."""

from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter

import regex
from data_juicer.ops.common.special_characters import VARIOUS_WHITESPACES
from data_juicer.ops.mapper.clean_email_mapper import CleanEmailMapper
from data_juicer.ops.mapper.punctuation_normalization_mapper import PunctuationNormalizationMapper
from data_juicer.ops.mapper.remove_specific_chars_mapper import RemoveSpecificCharsMapper


PROJECT = Path(__file__).resolve().parents[1]
RAW = PROJECT / "data/interim/experiment1/ptbxl_reports_raw.jsonl"
DJ = PROJECT / "data/processed/experiment1/dj_runs/ptbxl_text_20261010_v4/ptbxl_reports_clean.jsonl"
DJ_RUN = DJ.parent
MANUAL = PROJECT / "data/processed/experiment1/ptbxl_reports_manual.jsonl"
AUDIT = PROJECT / "reports/experiment1_artifacts/text_curation_comparison.json"
EMAIL = regex.compile(CleanEmailMapper().pattern, flags=regex.DOTALL)
NONCLINICAL_SYMBOL = regex.compile(RemoveSpecificCharsMapper(chars_to_remove="\u00A9").pattern)
PUNCTUATION = PunctuationNormalizationMapper().punctuation_unicode


def manual_clean(text: str) -> str:
    # Reuse the five operators' constants/patterns, but run a plain Python loop
    # to compare framework overhead with equivalent small-data processing.
    text = EMAIL.sub("", text)
    text = NONCLINICAL_SYMBOL.sub("", text)
    text = "".join(PUNCTUATION.get(char, char) for char in text)
    text = "".join(" " if char in VARIOUS_WHITESPACES else char for char in text.strip())
    return text


def main() -> None:
    started = perf_counter()
    raw = [json.loads(line) for line in RAW.open(encoding="utf-8")]
    manual = []
    with MANUAL.open("w", encoding="utf-8", newline="\n") as output:
        for row in raw:
            cleaned = manual_clean(row["text"])
            if not 1 <= len(cleaned) <= 10000:
                continue
            item = {**row, "text": cleaned}
            manual.append(item)
            output.write(json.dumps(item, ensure_ascii=False) + "\n")
    manual_seconds = round(perf_counter() - started, 3)

    dj = [json.loads(line) for line in DJ.open(encoding="utf-8")]
    events = [json.loads(line) for path in DJ_RUN.glob("events_*.jsonl")
              for line in path.open(encoding="utf-8")]
    completions = [event for event in events if event.get("event_type") == "job_complete"]
    if not completions:
        raise RuntimeError("缺少 Data-Juicer job_complete 事件，不能填写耗时")
    dj_seconds = round(float(completions[-1]["duration"]), 3)
    raw_by_id = {item["ecg_id"]: item["text"] for item in raw}
    raw_row_by_id = {item["ecg_id"]: item for item in raw}
    dj_by_id = {item["ecg_id"]: item["text"] for item in dj}
    manual_by_id = {item["ecg_id"]: item["text"] for item in manual}
    alphanumeric = lambda text: "".join(char for char in text if char.isalnum()).casefold()
    metrics = {
        "raw_records": len(raw),
        "raw_blank_texts": sum(not item["text"].strip() for item in raw),
        "data_juicer_records": len(dj),
        "data_juicer_blank_texts": sum(not item["text"].strip() for item in dj),
        "data_juicer_changed_texts": sum(raw_by_id[item_id] != text for item_id, text in dj_by_id.items()),
        "data_juicer_alphanumeric_preserved": sum(
            alphanumeric(raw_by_id[item_id]) == alphanumeric(text) for item_id, text in dj_by_id.items()
        ),
        "data_juicer_preserved_labels": sum(
            item["label"] == raw_row_by_id[item["ecg_id"]]["label"] for item in dj
        ),
        "data_juicer_preserved_folds": sum(
            item["strat_fold"] == raw_row_by_id[item["ecg_id"]]["strat_fold"] for item in dj
        ),
        "manual_records": len(manual),
        "manual_blank_texts": sum(not item["text"].strip() for item in manual),
        "manual_changed_texts": sum(raw_by_id[item_id] != text for item_id, text in manual_by_id.items()),
        "same_cleaned_text_on_shared_ids": sum(
            dj_by_id[item_id] == manual_by_id[item_id] for item_id in dj_by_id.keys() & manual_by_id.keys()
        ),
        "shared_ids": len(dj_by_id.keys() & manual_by_id.keys()),
        "manual_read_clean_export_seconds": manual_seconds,
        "data_juicer_version": "1.6.0",
        "data_juicer_job_seconds_from_event": dj_seconds,
        "note": "Plain Python loop reuses Data-Juicer's exact email/symbol patterns and punctuation/whitespace tables. Both times include input read, transformation and file export; Data-Juicer additionally includes framework setup/logging, so this is a small-data overhead comparison.",
    }
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    AUDIT.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
