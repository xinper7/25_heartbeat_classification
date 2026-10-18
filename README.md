# PTB-XL 12 导联数据查看与预处理

本项目使用官方 **PTB-XL v1.0.3**，提供数字心电读取、波形查看、数据质量审计、预处理和训练集增强的可复现代码。

**当前未启用分类模型。**原 ECGNet 已停用；ResNet1D 尚未接入或微调。应用只展示数据，不输出诊断标签或分类分数。

## 运行应用

需要 Python 3.10 或更新版本：

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app/app.py
```

`app/detect.py` 提供相同入口。输入为 100 Hz、10 秒、12 导联，每导联 1,000 点，支持本地 PTB-XL 记录编号、WFDB `.hea/.dat` 路径或数字 CSV。
导联顺序为 I、II、III、aVR、aVL、aVF、V1–V6，物理单位为 mV。CSV 为 1,000 行 × 12 列，可带标准导联表头。

可通过 `PTBXL_DATA_DIR` 环境变量指定数据目录；默认寻找桌面上的官方数据集目录。原始及处理后数据均不上传 GitHub。

## 清洗、预处理和增强

官方数据入口：[PTB-XL v1.0.3](https://physionet.org/content/ptb-xl/1.0.3/)，许可 CC BY 4.0。

```powershell
python -m pip install -r scripts/dataset/requirements.txt
python -B scripts/dataset/prepare_arrays.py --source "官方数据集目录"
python -B scripts/dataset/export_wfdb.py --source "官方数据集目录"
```

第一阶段生成忽略上传的中间缓存；第二阶段导出 WFDB 格式处理版。默认输出在 `data/processed/`，不会覆盖官方数据。

| 用途 | 记录数 | 官方折号 |
|---|---:|---|
| 未增强训练集 train | 17,084 | 1–8 |
| 增强副本 train_augmented | 17,084 | 源记录均来自 1–8 |
| 验证集 validation | 2,146 | 9 |
| 最终测试集 test | 2,158 | 10 |

以上为本机完整运行的五诊断超类任务统计；411 条无目标标签记录不纳入该任务。新运行以输出审计报告为准。
处理包括官方文件校验、质量标记、五类标签映射、40 Hz 零相位低通和训练集统计量标准化；增强仅用于训练，采用轻微噪声和全导联同步时间平移。
WFDB 文件保留 mV 单位及 `records100/xxxxx/xxxxx_lr.hea/.dat` 命名，标准化在训练加载时应用。

详见 [数据准备与读取方法](docs/data_preparation.md)、[数据—模型关联表](docs/data_model_association.md)。
数据准备完成不代表增强已提高模型性能，仍需固定模型、训练预算和验证/测试集开展对照实验。

## 实验与历史模型

- [实验 1](experiments/experiment1/README.md)：报告文本整理、60 维波形统计特征与逻辑回归采样对照，使用独立依赖环境。
- [历史评估报告](reports/ptbxl_evaluation/report.md)：旧 ECGNet 的本地测试宏平均 F1 为 0.6920，仅作为历史记录。
- [历史权重及许可](models/PTB_XL_12lead/README.md)：保留两个小型权重文件用于参考测试和复现，应用不加载它们。

## 验证

```powershell
python -B -m unittest discover -s tests -v
python -B scripts/dataset/prepare_arrays.py --self-test
```

数据处理自测需要先安装 `scripts/dataset/requirements.txt` 中的依赖。
代码副本的手动提交和推送步骤见 [GitHub 推送说明](docs/github_publish.md)。

## 项目来源与许可

项目代码保留原 [MIT 许可](LICENSE)，原项目来源为 [chrmei/heartbeat_classification](https://github.com/chrmei/heartbeat_classification)。
旧 ECGNet 来源为 [AndrewLucenko/ptb-xl-ecg-classification](https://github.com/AndrewLucenko/ptb-xl-ecg-classification)，保留其上游许可。
PTB-XL 数据引用：Wagner et al. (2020), Scientific Data 7, 154，[论文](https://doi.org/10.1038/s41597-020-0495-6)。
