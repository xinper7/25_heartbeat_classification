import hashlib
import json
import threading
import time

import numpy as np

from .config import get_settings
from .inputs import CLASSES, CLASS_NAMES


class ModelEngine:
    def __init__(self):
        self.cfg = get_settings()
        self.manifest = json.loads(
            (self.cfg.models_dir / "manifest.json").read_text(encoding="utf-8")
        )
        self.models = {}
        self.errors = {}
        self.gate = threading.BoundedSemaphore(max(1, self.cfg.inference_concurrency))
        self.load_lock = threading.Lock()

    def load(self, kind):
        with self.load_lock:
            if kind in self.models:
                return self.models[kind]
            info = self.manifest[kind]
            path = self.cfg.models_dir / info["file"]
            if hashlib.sha256(path.read_bytes()).hexdigest() != info["sha256"]:
                raise RuntimeError(f"{kind}模型文件校验失败。")
            if kind == "signal":
                import torch
                from .signal_model import make_signal_model

                torch.set_num_threads(self.cfg.model_threads)
                model = make_signal_model()
                checkpoint = torch.load(path, map_location="cpu", weights_only=True)
                model.load_state_dict(checkpoint["state_dict"], strict=True)
                model.eval()
                with torch.inference_mode():
                    model(torch.zeros(1, 12, 1000))
            else:
                import onnxruntime as ort

                options = ort.SessionOptions()
                options.intra_op_num_threads = self.cfg.model_threads
                options.inter_op_num_threads = 1
                options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
                options.graph_optimization_level = (
                    ort.GraphOptimizationLevel.ORT_ENABLE_ALL
                )
                model = ort.InferenceSession(
                    str(path), sess_options=options, providers=["CPUExecutionProvider"]
                )
                model.run(
                    ["logits"], {"images": np.zeros((1, 3, 224, 224), dtype=np.float32)}
                )
            self.models[kind] = model
            self.errors.pop(kind, None)
            return model

    def warmup(self):
        for kind in ("signal", "image"):
            try:
                self.load(kind)
            except Exception as exc:
                self.errors[kind] = type(exc).__name__ + ": " + str(exc)

    def predict(self, kind, array):
        if not self.gate.acquire(blocking=False):
            raise BlockingIOError("模型正在处理其他检查，请稍后重试或加入批量任务。")
        try:
            start = time.perf_counter()
            model = self.load(kind)
            info = self.manifest[kind]
            if kind == "signal":
                import torch

                x = ((array.astype(np.float64) - info["mean"]) / info["std"]).astype(
                    np.float32
                )[None]
                ready = time.perf_counter()
                with torch.inference_mode():
                    probabilities = torch.sigmoid(model(torch.from_numpy(x))).numpy()[0]
            else:
                x = array.astype(np.float32).transpose(2, 0, 1)[None] / 255.0
                mean = np.array([0.485, 0.456, 0.406], dtype=np.float32).reshape(
                    1, 3, 1, 1
                )
                std = np.array([0.229, 0.224, 0.225], dtype=np.float32).reshape(
                    1, 3, 1, 1
                )
                x = np.ascontiguousarray((x - mean) / std)
                ready = time.perf_counter()
                logits = model.run(["logits"], {"images": x})[0][0]
                probabilities = np.empty_like(logits)
                positive = logits >= 0
                probabilities[positive] = 1 / (1 + np.exp(-logits[positive]))
                exp = np.exp(logits[~positive])
                probabilities[~positive] = exp / (1 + exp)
            end = time.perf_counter()
            if probabilities.shape != (5,) or not np.isfinite(probabilities).all():
                raise RuntimeError("模型输出无效。")
            predictions = [
                dict(
                    code=c,
                    name=n,
                    probability=float(p),
                    threshold=t,
                    positive=bool(p >= t),
                )
                for c, n, p, t in zip(
                    CLASSES, CLASS_NAMES, probabilities, info["thresholds"]
                )
            ]
            return dict(
                model_version=info["version"],
                predictions=predictions,
                timings=dict(
                    normalization_ms=round((ready - start) * 1000, 3),
                    inference_ms=round((end - ready) * 1000, 3),
                    engine_ms=round((end - start) * 1000, 3),
                ),
                provenance=dict(
                    model_sha256=info["sha256"],
                    thresholds=info["thresholds"],
                    classes=CLASSES,
                    threads=self.cfg.model_threads,
                ),
            )
        finally:
            self.gate.release()


_engine = None
_engine_lock = threading.Lock()


def get_engine():
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = ModelEngine()
    return _engine
