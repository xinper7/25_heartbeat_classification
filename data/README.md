# 本地数据目录

原始数据来自 [官方 PTB-XL v1.0.3](https://physionet.org/content/ptb-xl/1.0.3/)，包含 21,799 条、10 秒、12 导联记录及 SCP 标注。
原始数据、临床报告文本、处理中间缓存和增强波形均不纳入 Git；本目录只提交说明文件。

通过命令行 `--source` 指定官方目录，或通过应用的 `PTBXL_DATA_DIR` 指定查看数据目录。
数据准备说明见 [docs/data_preparation.md](../docs/data_preparation.md)。

默认派生路径：

- `data/processed/ptbxl_100hz_v1/`：质量审计、标签、滤波数组和训练增强中间缓存。
- `data/processed/ptbxl_wfdb_v1/`：最终 WFDB 处理版，包含 train、train_augmented、validation、test 用途目录。
- `data/interim/experiment1/`、`data/processed/experiment1/`：独立文本整理与统计特征实验的本地输出。

五类任务保留多标签 NORM、MI、STTC、CD、HYP；无目标标签的记录不参与该任务。
使用官方 1–8/9/10 折划分，增强仅用于训练，标准化只在训练集拟合，患者不跨集合。

汇总实验结果可提交到 reports；单条临床文本和波形不直接提交公开仓库。
独立实验环境与复现命令见 [实验 1 说明](../experiments/experiment1/README.md)。
