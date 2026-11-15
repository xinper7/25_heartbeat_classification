import csv
import io
import re
import warnings
from pathlib import Path

import numpy as np
from PIL import Image, UnidentifiedImageError
from scipy.signal import butter, sosfiltfilt

LEADS = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]
CLASSES = ["NORM", "MI", "STTC", "CD", "HYP"]
CLASS_NAMES = ["正常心电图", "心肌梗死", "ST段/T波改变", "传导障碍", "心肌肥厚"]


class InputError(ValueError):
    pass


def _order(names):
    canonical = [s.strip().upper() for s in names]
    if (
        len(canonical) != 12
        or len(set(canonical)) != 12
        or set(canonical) != {s.upper() for s in LEADS}
    ):
        raise InputError("需要12个不重复的标准导联：" + ", ".join(LEADS))
    return [canonical.index(s.upper()) for s in LEADS]


def read_csv(data: bytes, sampling_rate: int, unit: str):
    if sampling_rate != 100:
        raise InputError("首版仅支持100 Hz、10秒数据；请先按明确协议转换采样率。")
    try:
        reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
        names = reader.fieldnames or []
        lead_names = [s for s in names if s.strip().lower() not in ("time", "time_s")]
        order = _order(lead_names)
        rows = list(reader)
        if len(rows) != 1000:
            raise InputError(f"需要1000行采样数据，实际为{len(rows)}行。")
        x = np.array(
            [[float(r[n]) for n in lead_names] for r in rows], dtype=np.float64
        ).T[order]
        time_col = next(
            (n for n in names if n.strip().lower() in ("time", "time_s")), None
        )
        if time_col:
            times = np.array([float(r[time_col]) for r in rows])
            if not np.isfinite(times).all() or not np.allclose(
                np.diff(times), 0.01, atol=1e-5, rtol=0
            ):
                raise InputError("时间列应以秒为单位，采样间隔必须为0.01秒。")
    except (UnicodeError, TypeError, KeyError, ValueError) as exc:
        if isinstance(exc, InputError):
            raise
        raise InputError("CSV需要UTF-8编码、逗号分隔的标准导联列和有效数值。") from exc
    if unit not in ("mV", "uV"):
        raise InputError("仅支持mV或uV单位。")
    return x / 1000 if unit == "uV" else x


def read_wfdb(files: dict[str, bytes]):
    headers = [n for n in files if n.lower().endswith(".hea")]
    if len(headers) != 1 or len(files) != 2:
        raise InputError("每次检查上传一个.hea及其配套.dat文件。")
    try:
        lines = files[headers[0]].decode("ascii").splitlines()
        rows = [
            line.split()
            for line in lines
            if line.strip() and not line.lstrip().startswith("#")
        ]
        first = rows[0]
        if len(first) < 4 or (int(first[1]), float(first[2]), int(first[3])) != (
            12,
            100.0,
            1000,
        ):
            raise InputError("WFDB应为12导联、100 Hz、1000采样点。")
        lead_rows = rows[1:13]
        if len(lead_rows) != 12:
            raise InputError("头文件导联信息不完整。")
        referenced = {r[0] for r in lead_rows}
        if len(referenced) != 1:
            raise InputError("首版仅支持单个交错存储的WFDB format-16数据文件。")
        filename = next(iter(referenced))
        if (
            "/" in filename
            or "\\" in filename
            or filename not in files
            or not filename.lower().endswith(".dat")
        ):
            raise InputError("头文件引用必须是本次上传的配套.dat文件名。")
        if any(r[1] != "16" for r in lead_rows):
            raise InputError("仅支持WFDB format-16。")
        raw = np.frombuffer(files[filename], dtype="<i2")
        if raw.size != 12000:
            raise InputError("数据文件应包含12000个16位采样值（24000字节）。")
        raw = raw.reshape(1000, 12)
        gains, baselines = [], []
        for i, row in enumerate(lead_rows):
            match = re.fullmatch(r"([\d.eE+-]+)(?:\(([-\d.eE+]+)\))?/mV", row[2])
            if not match:
                raise InputError("头文件必须声明有效的增益和mV单位。")
            gain = float(match[1])
            if not np.isfinite(gain) or gain <= 0:
                raise InputError("WFDB增益必须为正数。")
            gains.append(gain)
            baselines.append(float(match[2]) if match[2] is not None else float(row[4]))
            if int(raw[:, i].astype(np.int64).sum()) % 65536 != int(row[6]) % 65536:
                raise InputError("数据校验和不匹配，请核对.hea/.dat是否配对。")
        order = _order([r[-1] for r in lead_rows])
        return ((raw.astype(np.float64) - baselines) / gains).T[order]
    except (IndexError, ValueError, UnicodeError) as exc:
        if isinstance(exc, InputError):
            raise
        raise InputError("WFDB头文件格式无效。") from exc


def prepare_signal(files, profile, sampling_rate=100, unit="mV"):
    if profile not in ("filtered_mv", "raw_mv"):
        raise InputError("请选择原始mV波形或已完成40 Hz低通的波形。")
    csv_files = [n for n in files if n.lower().endswith(".csv")]
    if csv_files:
        if len(files) != 1:
            raise InputError("CSV检查仅接收一个文件。")
        x = read_csv(files[csv_files[0]], sampling_rate, unit)
        source_format = "csv"
    else:
        x = read_wfdb(files)
        source_format = "wfdb16"
    x = x.astype(np.float32)
    if not np.isfinite(x).all():
        raise InputError("波形中存在NaN或无穷值。")
    if float(np.abs(x).max()) > 100:
        raise InputError("幅值超过100 mV，请检查单位、增益或数据内容。")
    constant = [LEADS[i] for i in range(12) if float(np.std(x[i])) < 1e-8]
    if len(constant) == 12:
        raise InputError("全部导联为恒定值，无法进行有效分析。")
    if profile == "raw_mv":
        sos = butter(4, 40, btype="lowpass", fs=100, output="sos")
        x = sosfiltfilt(sos, x, axis=-1).astype(np.float32)
        # Match the processed WFDB dataset's 1 microvolt storage quantization.
        x = (np.rint(x.astype(np.float64) * 1000) / 1000).astype(np.float32)
    meta = dict(
        format=source_format,
        leads=LEADS,
        sampling_rate=100,
        duration_seconds=10,
        samples=1000,
        unit="mV",
        input_profile=profile,
        applied_filter=profile == "raw_mv",
        warnings=[f"恒定导联 {s} 已保留" for s in constant],
        preprocessing_version="signal-v1-40hz-global-zscore",
    )
    return np.ascontiguousarray(x), meta


def prepare_image(files):
    if len(files) != 1:
        raise InputError("每次检查上传一张完整标准报告图。")
    name, data = next(iter(files.items()))
    if Path(name).suffix.lower() not in (".png", ".jpg", ".jpeg"):
        raise InputError("报告图支持PNG、JPG和JPEG。")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format not in ("PNG", "JPEG"):
                    raise InputError("图片内容与PNG/JPEG格式不符。")
                if (
                    min(image.size) < 100
                    or max(image.size) > 8000
                    or image.width * image.height > 25_000_000
                ):
                    raise InputError(
                        "图片边长需在100至8000像素之间，总像素不超过2500万。"
                    )
                image.load()
                image = image.convert("RGB")
                cache = np.array(
                    image.resize((224, 224), Image.Resampling.BILINEAR), dtype=np.uint8
                )
                return (
                    image,
                    cache,
                    dict(
                        format="report_image",
                        width=image.width,
                        height=image.height,
                        input_size=[224, 224],
                        layout="standard-3x4-rhythm-II",
                        warnings=[
                            "仅适用于项目既定3×4布局及底部II导联节律条；系统未自动验证图片布局。"
                        ],
                        preprocessing_version="image-v1-pillow-bilinear-imagenet",
                    ),
                )
    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise InputError("图片损坏或尺寸过大，无法安全读取。") from exc
