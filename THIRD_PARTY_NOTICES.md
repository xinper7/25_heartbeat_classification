# Third-party sources

- Signal architecture: adapted from [helme/ecg_ptbxl_benchmarking](https://github.com/helme/ecg_ptbxl_benchmarking), Wang ResNet1D and classification head, GPL-3.0. This repository includes the upstream GPL-3.0 license. See `backend/app/signal_model.py`.
- Trained model files are the project's experiment 2/3 outputs. Exact experiment identifiers, SHA-256 checksums, thresholds and preprocessing are in `models/manifest.json`.
- Demonstration data are five processed PTB-XL v1.0.3 test-fold records and report images rendered from those records. Dataset license: CC BY 4.0. Source: https://physionet.org/content/ptb-xl/1.0.3/ . The package does not include patient names or the full clinical metadata database.
- Dataset citation: Wagner P, Strodthoff N, Bousseljot R D, et al. PTB-XL, a large publicly available electrocardiography dataset. Scientific Data 7, 154 (2020). DOI: 10.1038/s41597-020-0495-6.
- Benchmark citation: Strodthoff N, Wagner P, Schaeffter T, Samek W. Deep Learning for ECG Analysis: Benchmarks and Insights from PTB-XL. IEEE JBHI 25(5), 1519–1528 (2021). DOI: 10.1109/JBHI.2020.3022989.
- Image architecture: EfficientNet-B0, Tan M and Le Q, ICML 2019. Inference uses the packaged ONNX model and does not download ImageNet weights at startup.
- Frontend and Python dependencies retain their respective upstream licenses. No external language-model API or credentials are included.
