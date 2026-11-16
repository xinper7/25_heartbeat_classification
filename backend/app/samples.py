"""Display names for packaged public samples, independent of model predictions."""

SAMPLE_NOTE = "数据来源：PTB-XL公开数据；匿名化样例记录，不对应本系统真实患者。"


def patient_code(owner_id: int, ecg_id: int) -> str:
    return f"P-{owner_id:03d}-{ecg_id:05d}"


def patient_name(patient_id: int) -> str:
    return f"受检者{patient_id:04d}"


def study_title(kind: str) -> str:
    return "十二导联心电检查" if kind == "signal" else "心电报告图分析"


def source_info(ecg_id: int) -> dict:
    return {
        "dataset": "PTB-XL",
        "version": "1.0.3",
        "ecg_id": ecg_id,
        "split": "test",
        "purpose": "public_sample",
    }


from functools import lru_cache
import hashlib, json
from .config import ROOT

@lru_cache
def packaged_hashes():
    mapping={}
    for row in json.loads((ROOT/'sample-data/manifest.json').read_text(encoding='utf-8')):
        folder=ROOT/'sample-data'/row['directory']
        groups=[[p for p in folder.iterdir() if p.suffix in ('.hea','.dat')], [folder/'signal.csv'], [folder/'report.png']]
        for group in groups:
            if group and all(p.is_file() for p in group):
                mapping[tuple(sorted(hashlib.sha256(p.read_bytes()).hexdigest() for p in group))]=row['ecg_id']
    return mapping

def source_for_hashes(hashes):
    ecg_id=packaged_hashes().get(tuple(sorted(hashes)))
    return source_info(ecg_id) if ecg_id is not None else None
