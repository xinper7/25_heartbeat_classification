# Demonstration inputs

Five public PTB-XL processed test-fold records are packaged with the application. `manifest.json` identifies source ECG IDs, label superclasses and reference probabilities. These are demonstration and regression fixtures; they do not constitute a new independent test set.

Each numbered directory includes a WFDB `.hea/.dat` pair and the corresponding fixed-layout `report.png`. Directory `9` also contains `signal.csv` (12 named columns, 1000 samples, physical mV).

For all these signal files, choose **filtered_mv: 已完成40 Hz低通，物理mV**. Do not apply the lowpass filter again. CSV sampling rate is 100 Hz; unit is mV.

The dashboard's “导入演示样本” creates five synthetic display profiles and ten ready checks for the current analyst/admin. Import is idempotent. It does not insert reference probabilities into the analysis table: click analysis or create a batch to run the actual models.

Reference image probabilities come from the original experiment 3 local ONNX FP32 evaluation. Runtime versions may produce small floating-point differences; classification decisions use the fixed packaged thresholds.

Source and attribution: see `THIRD_PARTY_NOTICES.md`. CC BY 4.0 applies to these dataset-derived examples.
