# PTB-XL 12-lead research checkpoint

**Status: disabled.** This checkpoint is retained for provenance and historical evaluation only. Neither application entry point loads it or performs classification. No replacement model is currently deployed.

Source: [AndrewLucenko/ptb-xl-ecg-classification](https://github.com/AndrewLucenko/ptb-xl-ecg-classification), `artifacts/best_model.pt`. The upstream code and checkpoint are distributed under the MIT license reproduced in `LICENSE.upstream` (copyright Andrew Lucenko, 2026).

- `best_model.pt`: upstream PyTorch checkpoint; SHA-256 `3c92797fc3c74165c5715ac21fd8a7723fc2c4a39812f0fba340d531abcd9157`.
- `weights.npz`: tensors exported from that checkpoint for NumPy-only inference; SHA-256 `5f2f9942847a904a222ce798c59efd52fff25b657f594d1ed0e3130687ea2a15`.
- Input: 10 seconds at 100 Hz, 12 leads in the order I, II, III, aVR, aVL, aVF, V1–V6. Each lead is independently z-score normalized before inference.
- Output: five independent scores in the order NORM, MI, STTC, CD, HYP. The checkpoint threshold is 0.5.

The upstream project describes this as an educational model. Scores are not calibrated clinical probabilities. Its published evaluation concerns digital PTB-XL signals; paper images and videos are outside that validation. The Streamlit app accepts digital 12-lead CSV and PTB-XL records100 WFDB recordings for this model.
