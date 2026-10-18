# PTB-XL 数据集实验说明

本实验只使用 [PTB-XL v1.0.3](https://physionet.org/content/ptb-xl/1.0.3/)，用于课程中的数据采集、清洗、整理和增强方法对照。原始数据位于 `C:\Users\zyh20\Desktop\ptb-xl-a-large-publicly-available-electrocardiography-dataset-1.0.3`，许可为 CC BY 4.0。换电脑时需先从官方页面取得数据，再用脚本的 `--root` 参数指定目录。

## 原始数据

- `ptbxl_database.csv`：21,799 行、28 列；`ecg_id` 为记录编号，`patient_id` 为患者编号，`filename_lr` 指向 100 Hz 波形，`strat_fold` 为官方数据折，`scp_codes` 为心电标注，`report` 为报告文字。
- `scp_statements.csv`：把 SCP-ECG 标注代码映射到 NORM、MI、STTC、CD、HYP 等诊断超类；一条记录可能有多个类别。
- `records100/`：21,799 对 `.hea/.dat`，每条为 10 秒、12 导联、100 Hz。本次逐条读取并检查。
- `records500/`：21,799 对 `.hea/.dat`，本次只核对文件配对，没有纳入对照实验。

## 本次生成的数据

| 文件 | 字段或形状 | 用途 |
| --- | --- | --- |
| `data/interim/experiment1/ptbxl_reports_raw.jsonl` | `ecg_id`、`text`、`label`、`strat_fold`；21,799 行 | 清洗前的报告文本。 |
| `data/processed/experiment1/ptbxl_manifest.csv` | `ecg_id`、`patient_id`、`filename_lr`、`strat_fold`、`split`、`labels`、`report_nonempty`；21,799 行 | 关联波形、标注和数据划分，不复制波形。 |
| `data/processed/experiment1/dj_runs/ptbxl_text_20261010_v4/ptbxl_reports_clean.jsonl` | 保留 `text`、`label` 等字段；21,797 行 | 五算子清洗后的报告文本。 |
| `data/processed/experiment1/ptbxl_signal_features.npz` | `ecg_id` 和每条记录 60 维特征 | 数据增强对照的本地缓存。 |

这些是本地派生文件，已加入 `.gitignore`；本说明中的数量以 2026-10-10 的运行结果为准。

## 处理过程与质量检查

1. `scripts/experiment1_prepare_ptbxl.py` 读取元数据，检查 `ecg_id` 唯一、患者不跨折、路径不越过数据根目录、`.hea/.dat` 配对。实测 21,799 条记录、18,869 位患者；上述检查均无异常。脚本同时保存原始元数据文件的 SHA-256 到 `reports/experiment1_artifacts/source_audit.json`。
2. `data_juicer_reports.yaml` 依次执行邮件清理、版权符号清理、标点规范、空白规范和长度过滤。原报告中有 2 条空白，清洗后剩 21,797 条；其中 198 条文字发生规范化，保留文字的字母数字序列、标签和数据折号均未变化。配置设 `skip_op_error: false`。具体对照在 `reports/experiment1_artifacts/text_curation_comparison.json`。
3. `scripts/experiment1_compare_sampling.py` 解码全部 21,799 条 `records100`：非有限值记录 0 条，记录 12722 有 1 个恒定的 V5 导联，已标记但未自动删除。脚本从每个导联提取均值、标准差、最小值、最大值和一阶差分绝对值均值，共 60 维。
4. 完整数据按官方 `strat_fold` 的 1–8/9/10 划分为训练/验证/测试，分别有 17,418/2,183/2,198 条。同一 `patient_id` 不跨折。教学用二分类只取 NORM-only 与不含 NORM 的其他诊断超类，排除混合或无诊断超类的 856 条；其采样对照结果见 `reports/experiment1_artifacts/sampling_comparison.json`。

## 复现命令

在独立 Python 3.12 环境中，从实验文件所在目录运行：

```powershell
python -m pip install -r experiments/experiment1/requirements.txt
python scripts/experiment1_prepare_ptbxl.py
dj-process --config experiments/experiment1/data_juicer_reports.yaml
python scripts/experiment1_audit_text_curation.py
python scripts/experiment1_compare_sampling.py
python scripts/generate_experiment1_dataset_structure.py
```

固定的 Data-Juicer `job_id` 用于记录本次结果。重新运行时请换一个作业 ID，并同步调整文本核验脚本中的清洗结果路径，避免把新结果和旧日志混用。

## 使用限制与隐私

PTB-XL 官方记录其数据已做假名化处理，但报告文字仍属于医学数据。本次 JSONL 和特征缓存仅保存在本机，报告不展示单条文字。公开使用时应遵守数据集许可并注明来源。这里的质量检查与逻辑回归对照不能作为个人诊断，也没有代替专业人员复核标注或恒定导联。
