"""PTB-XL signal readers and archived NumPy inference implementation.

The application currently uses only the readers; the old checkpoint is disabled.

The ECGNet architecture is adapted from the MIT-licensed upstream project:
https://github.com/AndrewLucenko/ptb-xl-ecg-classification
See models/PTB_XL_12lead/LICENSE.upstream for the copyright notice.
"""

from __future__ import annotations

import hashlib
import io
import re
from pathlib import Path

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view


MODEL_PATH = Path(__file__).resolve().parents[2] / "models/PTB_XL_12lead/weights.npz"
MODEL_SHA256 = "5f2f9942847a904a222ce798c59efd52fff25b657f594d1ed0e3130687ea2a15"
LEADS = ("I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6")
CLASSES = ("NORM", "MI", "STTC", "CD", "HYP")
CLASS_NAMES_ZH = {
    "NORM": "正常心电图",
    "MI": "心肌梗死",
    "STTC": "ST/T 改变",
    "CD": "传导异常",
    "HYP": "肥厚",
}


def validate_signal(values) -> np.ndarray:
    """Accept one 10-second recording, 12 leads by 1000 samples at 100 Hz."""
    try:
        signal = np.asarray(values, dtype=np.float32)
    except (TypeError, ValueError) as exc:
        raise ValueError("12 导联数据必须全部为数值。") from exc
    if signal.shape == (1000, 12):
        signal = signal.T
    if signal.shape != (12, 1000):
        raise ValueError("当前数据规格为 12 导联、每导联 1000 点（100 Hz、10 秒）。")
    if not np.isfinite(signal).all():
        raise ValueError("12 导联数据不能包含空值或无穷大。")
    return np.ascontiguousarray(signal)


def normalize_signal(values) -> np.ndarray:
    """Apply the upstream model's independent z-score for each lead."""
    signal = validate_signal(values)
    mean = signal.mean(axis=1, keepdims=True)
    std = np.maximum(signal.std(axis=1, keepdims=True), 1e-6)
    return np.ascontiguousarray((signal - mean) / std)


def read_csv(content: bytes) -> np.ndarray:
    """Read 1000-by-12 CSV, optionally with one row of lead names."""
    import pandas as pd

    if len(content) > 5 * 1024 * 1024:
        raise ValueError("12 导联 CSV 文件不得超过 5 MB。")
    try:
        frame = pd.read_csv(io.BytesIO(content), header=None, encoding="utf-8-sig")
    except pd.errors.EmptyDataError as exc:
        raise ValueError("CSV 文件为空。") from exc
    if frame.empty:
        raise ValueError("CSV 文件为空。")
    if frame.shape[1] != len(LEADS):
        raise ValueError("CSV 必须恰好有 12 列，每列对应一条导联。")
    headers = [str(value).strip().upper() for value in frame.iloc[0]]
    expected = [lead.upper() for lead in LEADS]
    if len(set(headers)) == len(LEADS) and set(headers) == set(expected):
        order = [headers.index(name) for name in expected]
        frame = frame.iloc[1:, order]
    try:
        values = frame.apply(pd.to_numeric, errors="raise").to_numpy(dtype=np.float32)
    except (TypeError, ValueError) as exc:
        raise ValueError("CSV 含非数值内容；表头只能使用标准导联名称。") from exc
    return validate_signal(values)


def read_wfdb_record(record_path: str | Path) -> np.ndarray:
    """Read PTB-XL's single-file, interleaved WFDB format-16 records100 data.

    This is deliberately a limited reader for this model's input format,
    rather than an implementation of every WFDB storage format.
    """
    record = Path(record_path).expanduser()
    if record.suffix.lower() in (".hea", ".dat"):
        record = record.with_suffix("")
    header_path = record.with_suffix(".hea")
    if not header_path.is_file():
        raise FileNotFoundError(f"找不到 WFDB 头文件：{header_path}")
    lines = [line.split() for line in header_path.read_text(encoding="utf-8", errors="replace").splitlines()
             if line.strip() and not line.startswith("#")]
    if not lines or len(lines[0]) < 4:
        raise ValueError("WFDB 头文件缺少记录规格。")
    try:
        n_leads = int(lines[0][1])
        sample_rate = float(lines[0][2].split("/")[0])
        n_samples = int(lines[0][3])
    except ValueError as exc:
        raise ValueError("WFDB 头文件中的导联数、采样率或采样点数无效。") from exc
    if not np.isclose(sample_rate, 100):
        raise ValueError("当前读取器需要 100 Hz 数据；请选择 PTB-XL 的 records100 记录。")
    if n_leads != len(LEADS) or n_samples != 1000 or len(lines) < n_leads + 1:
        raise ValueError("当前读取器需要 12 导联、每导联 1000 点的完整记录。")

    pattern = re.compile(r"(?P<gain>[0-9.]+)\((?P<baseline>[+-]?\d+)\)/(?P<unit>\S+)")
    names, gains, baselines, filenames = [], [], [], []
    for parts in lines[1:n_leads + 1]:
        if len(parts) < 9 or parts[1] != "16":
            raise ValueError("当前仅支持 PTB-XL records100 使用的 WFDB format-16 文件。")
        match = pattern.fullmatch(parts[2])
        if match is None or match["unit"] != "mV":
            raise ValueError("WFDB 导联增益或单位格式不受支持。")
        gain = float(match["gain"])
        if not np.isfinite(gain) or gain <= 0:
            raise ValueError("WFDB 导联增益无效。")
        filenames.append(parts[0])
        gains.append(gain)
        baselines.append(int(match["baseline"]))
        names.append(parts[-1].upper())
    expected = [name.upper() for name in LEADS]
    if len(names) != len(LEADS) or set(names) != set(expected):
        raise ValueError("WFDB 记录必须包含标准的 12 条导联。")
    if len(set(filenames)) != 1 or Path(filenames[0]).name != filenames[0]:
        raise ValueError("当前仅支持所有导联存放在同一目录、同一 .dat 文件中的记录。")
    data_path = record.parent / filenames[0]
    if not data_path.is_file():
        raise FileNotFoundError(f"找不到 WFDB 波形文件：{data_path}")
    if data_path.stat().st_size != n_samples * n_leads * 2:
        raise ValueError("WFDB 波形文件大小与头文件记录不一致。")

    digital = np.fromfile(data_path, dtype="<i2").reshape(n_samples, n_leads)
    if np.any(digital == np.iinfo(np.int16).min):
        raise ValueError("WFDB 波形含缺失采样点，无法读取为完整信号。")
    physical = (digital.astype(np.float32) - np.asarray(baselines, dtype=np.float32)) / np.asarray(gains, dtype=np.float32)
    order = [names.index(name) for name in expected]
    return validate_signal(physical[:, order])


def read_ptbxl_record(root: str | Path, ecg_id: int) -> np.ndarray:
    """Find a PTB-XL records100 file by its official ECG record ID."""
    import pandas as pd

    root = Path(root).expanduser().resolve()
    metadata_path = root / "ptbxl_database.csv"
    if not metadata_path.is_file():
        raise FileNotFoundError("所选目录中没有 ptbxl_database.csv，请选择 PTB-XL 数据集根目录。")
    metadata = pd.read_csv(metadata_path, usecols=["ecg_id", "filename_lr"])
    matched = metadata.loc[metadata["ecg_id"] == int(ecg_id), "filename_lr"]
    if matched.empty:
        raise ValueError(f"数据集中找不到记录编号 {ecg_id}。")
    record = (root / str(matched.iloc[0])).resolve()
    if not record.is_relative_to(root):
        raise ValueError("记录路径超出所选数据集目录。")
    return read_wfdb_record(record)


def load_model(path: Path = MODEL_PATH):
    """Load the converted weights without executing checkpoint code."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"缺少 PTB-XL 模型文件：{path}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if path.resolve() == MODEL_PATH.resolve() and digest != MODEL_SHA256:
        raise ValueError("PTB-XL 模型文件校验失败，请重新下载。")
    with np.load(path, allow_pickle=False) as data:
        if tuple(data["classes"].tolist()) != CLASSES:
            raise ValueError("PTB-XL 模型的类别与当前适配器不匹配。")
        weights = {key: np.ascontiguousarray(data[key].astype(np.float32))
                   for key in data.files if key not in ("classes", "threshold")}
        threshold = float(data["threshold"])
    expected_shapes = {
        "features.0.weight": (32, 12, 7), "features.0.bias": (32,),
        "features.4.weight": (64, 32, 5), "features.4.bias": (64,),
        "features.7.weight": (128, 64, 3), "features.7.bias": (128,),
        "classifier.weight": (5, 128), "classifier.bias": (5,),
    }
    for prefix, channels in (("features.1", 32), ("features.5", 64), ("features.8", 128)):
        for suffix in ("weight", "bias", "running_mean", "running_var"):
            expected_shapes[f"{prefix}.{suffix}"] = (channels,)
    if set(weights) != set(expected_shapes) or any(weights[key].shape != shape for key, shape in expected_shapes.items()):
        raise ValueError("PTB-XL 模型权重结构不匹配。")
    if not 0 < threshold < 1:
        raise ValueError("PTB-XL 模型阈值无效。")
    return weights, threshold


def _conv1d(signal: np.ndarray, weight: np.ndarray, bias: np.ndarray, *, stride: int, padding: int) -> np.ndarray:
    padded = np.pad(signal, ((0, 0), (padding, padding)))
    windows = sliding_window_view(padded, weight.shape[-1], axis=1)[:, ::stride, :]
    return np.einsum("ock,ctk->ot", weight, windows, optimize=True) + bias[:, None]


def _batch_norm(signal: np.ndarray, weights: dict[str, np.ndarray], prefix: str) -> np.ndarray:
    scale = weights[f"{prefix}.weight"][:, None]
    offset = weights[f"{prefix}.bias"][:, None]
    mean = weights[f"{prefix}.running_mean"][:, None]
    variance = weights[f"{prefix}.running_var"][:, None]
    return (signal - mean) / np.sqrt(variance + 1e-5) * scale + offset


def predict(model: dict[str, np.ndarray], values) -> np.ndarray:
    """Return five independent label scores in CLASSES order."""
    signal = normalize_signal(values)
    for conv, bn, stride, padding in (("features.0", "features.1", 2, 3),
                                      ("features.4", "features.5", 2, 2),
                                      ("features.7", "features.8", 2, 1)):
        signal = _conv1d(signal, model[f"{conv}.weight"], model[f"{conv}.bias"],
                         stride=stride, padding=padding)
        signal = np.maximum(_batch_norm(signal, model, bn), 0)
        if conv == "features.0":
            even_length = signal.shape[1] // 2 * 2
            signal = np.maximum(signal[:, :even_length:2], signal[:, 1:even_length:2])
    pooled = signal.mean(axis=1)
    logits = model["classifier.weight"] @ pooled + model["classifier.bias"]
    scores = 1 / (1 + np.exp(-np.clip(logits, -80, 80)))
    if scores.shape != (len(CLASSES),) or not np.isfinite(scores).all():
        raise RuntimeError("PTB-XL 模型返回了无效分数。")
    return scores
