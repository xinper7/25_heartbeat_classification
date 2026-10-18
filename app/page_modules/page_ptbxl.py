"""Read and preview one complete digital 12-lead recording without a model."""

import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.inference.ptbxl import (
    LEADS,
    read_csv,
    read_ptbxl_record,
    read_wfdb_record,
)


def render():
    st.title("PTB-XL 12 导联数据查看")
    st.info(
        "当前未启用分类模型。可读取完整数字化 12 导联信号并查看数据和波形："
        "10 秒、100 Hz、每导联 1,000 点。"
    )
    st.caption("支持数字 CSV 和 PTB-XL records100 的 WFDB 记录；不接受报告图片或视频。")
    source = st.radio(
        "输入方式",
        ["本地 PTB-XL 数据集", "WFDB 记录路径", "上传 CSV"],
        horizontal=True,
        key="ptbxl_input_source",
    )
    dataset_root = os.getenv("PTBXL_DATA_DIR", "")
    if not dataset_root:
        desktop_data = (
            Path.home() / "Desktop"
            / "ptb-xl-a-large-publicly-available-electrocardiography-dataset-1.0.3"
        )
        if desktop_data.is_dir():
            dataset_root = str(desktop_data)
    uploaded = None
    record_path = ""
    ecg_id = 1
    if source == "本地 PTB-XL 数据集":
        dataset_root = st.text_input(
            "PTB-XL 数据集根目录", value=dataset_root, key="ptbxl_dataset_root"
        )
        ecg_id = st.number_input(
            "心电记录编号（ecg_id）", min_value=1, value=1, step=1, key="ptbxl_ecg_id"
        )
        st.caption("选择包含 ptbxl_database.csv 和 records100 文件夹的目录。")
    elif source == "WFDB 记录路径":
        record_path = st.text_input("记录文件路径", key="ptbxl_record_path")
        st.caption("输入 .hea、.dat 文件路径或不带扩展名的记录路径，配对文件需放在同一目录。")
    else:
        st.caption(
            "CSV 需为 1000 行 × 12 列，列顺序为 I、II、III、aVR、aVL、aVF、V1–V6；"
            "单位为 mV。可带标准导联表头，带表头时允许调整列顺序。"
        )
        uploaded = st.file_uploader("12 导联心电 CSV", type="csv", key="ptbxl_csv")

    if st.button("读取并查看波形", key="preview_ptbxl", type="primary"):
        try:
            if source == "本地 PTB-XL 数据集":
                signal = read_ptbxl_record(dataset_root, int(ecg_id))
            elif source == "WFDB 记录路径":
                if not record_path.strip():
                    raise ValueError("请输入 WFDB 记录路径。")
                signal = read_wfdb_record(record_path.strip())
            else:
                if uploaded is None:
                    raise ValueError("请先上传 12 导联 CSV 文件。")
                signal = read_csv(uploaded.getvalue())
            st.caption("已读取完整 12 导联信号：每导联 1,000 点，采样率 100 Hz。")
            frame = pd.DataFrame(signal.T, columns=LEADS)
            frame.index.name = "采样点"
            st.line_chart(frame)
            st.caption("信号数值单位：mV。当前仅展示数据，不输出分类分数或诊断标签。")
            st.dataframe(frame, width="stretch")
        except (ValueError, RuntimeError, ImportError, OSError, KeyError) as exc:
            st.error(f"12 导联数据读取失败：{exc}")

    st.caption("分类功能暂未启用。")
