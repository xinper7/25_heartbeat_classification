# 当前 PTB-XL 模型的评估数据选择

## 直接可评估：本地 PTB-XL v1.0.3 官方测试折

模型接受 100 Hz、10 秒、12 导联的数字信号。使用本机已下载的 records100，无需下载新的数据。严格按上游代码映射 SCP 诊断超类，排除无五个目标标签的记录；第 10 折共有 2,198 条，其中 2,158 条可评估、涉及 1,877 位患者。完整实测结果见 report.md，逐条结果见 predictions.jsonl。

按上游公开规则，第 1–8 折训练、第 9 折验证、第 10 折测试。本地核验训练折与测试折无患者交叉。该评估检验同来源的留出表现，不构成外部医院泛化验证；上游实际训练过程未独立审计。

- 官方数据与划分说明：https://physionet.org/content/ptb-xl/1.0.3/
- 上游标签映射：https://github.com/AndrewLucenko/ptb-xl-ecg-classification/blob/main/src/data.py
- 上游训练规则：https://github.com/AndrewLucenko/ptb-xl-ecg-classification/blob/main/src/train.py

## 外部候选一：Chapman–Shaoxing 原始 CSV 数据集

原始论文描述 10,646 位患者、10 秒、12 导联、500 Hz 的心电记录。波形以每条 5,000 行 × 12 列 CSV 保存，并提供独立诊断文件和代码字典。这是寻找外部真实波形 CSV 的优先入口。

- 原始数据集合：https://doi.org/10.6084/m9.figshare.c.4560497.v2
- 原始论文和 CSV 说明：https://www.nature.com/articles/s41597-020-0386-x

当前应用不能直接读取 5,000 行的文件。需要用带抗混叠滤波的重采样转为 100 Hz，核对导联顺序和幅值单位，再导出 1,000 × 12 波形 CSV。诊断体系包含心律和其他疾病，需预先制定与 NORM、MI、STTC、CD、HYP 的有效映射及不可评估标签规则。“窦性心律”不能直接等同于“正常心电图”。本次尚未下载或完成外部评估。

PhysioNet 另提供 45,152 条的扩展版，包含 Chapman、Shaoxing 和 Ningbo 来源，属于不同规模的发布版本，不应与原始 10,646 条混为一谈：https://physionet.org/content/ecg-arrhythmia/1.0.0/

## 外部候选二：Georgia 12-lead ECG Challenge 数据

PhysioNet/CinC 2020 发布的 Georgia 子集有 10,344 条、10 秒、12 导联、500 Hz 记录，附 SNOMED-CT 诊断标注。其数据来源不同于 PTB-XL，适合作为外部评估候选。

- 官方来源、下载入口和文件格式：https://physionet.org/content/challenge-2020/1.0.2/

需要从官方页面 Files/training 下选择 georgia，而非整个混合挑战数据集。波形为配套 .hea/.mat；当前项目的简化 WFDB 读取器不支持此格式。需单独解码、重采样、统一导联，再转换为模型 CSV。SNOMED-CT 与 SCP 超类映射和标注覆盖范围须先确认，不能把未标注的类别自动视为可靠阴性。本次尚未下载或完成外部评估。

## 外部候选三：CPSC 2018

官方公开集为 6,877 条、12 导联、500 Hz，时长 6–60 秒，可从同一 PhysioNet/CinC 2020 官方入口选择 cpsc_2018 获取。

除重采样和标签映射外，还需固定选取 10 秒窗口的规则，并明确不足 10 秒记录的排除策略。该集侧重特定心律失常和其他异常，其标签与本模型五个超类不同，未必支持五类完整指标。本次尚未下载或完成外部评估。

## 使用边界

波形能被转换为输入，只说明能推理；有可靠的可比标签、完整预处理规则和无泄漏评估，才能衡量识别效果。跨库评价还需要核查数据来源和重复记录。

PTB-XL records500 是同批记录的另一采样率版本，PTB-XL+ 是其派生特征资源，都不应作为全新外部测试集。
