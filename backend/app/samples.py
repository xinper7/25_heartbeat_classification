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
