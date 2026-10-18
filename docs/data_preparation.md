# 数据准备与用途划分

## 输入与输出

输入为官方 PTB-XL v1.0.3 目录，包含 ptbxl_database.csv、scp_statements.csv、SHA256SUMS.txt 和 records100。
原始文件保持不变；所有生成数据默认放在项目的 data/processed 中，该目录已被 Git 忽略。

```powershell
python -m pip install -r scripts/dataset/requirements.txt
python -B scripts/dataset/prepare_arrays.py --source "官方数据集目录"
python -B scripts/dataset/export_wfdb.py --source "官方数据集目录"
```

如需自定义缓存和处理版位置：

```powershell
python -B scripts/dataset/prepare_arrays.py --source "官方数据集目录" --output "新的中间缓存目录"
python -B scripts/dataset/export_wfdb.py --source "官方数据集目录" --arrays "新的中间缓存目录" --output "新的WFDB处理版目录"
```

脚本拒绝覆盖已完成的数据版本。中间数组用于高效计算；最终数据为官方风格 WFDB `.hea/.dat`，沿用源记录名和 records100 分桶目录。

## 预处理

- 验证官方文件哈希、WFDB 配对、100 Hz、12 导联、1000 点、增益/单位、缺失采样和有限值。
- 使用五个诊断超类标签 NORM、MI、STTC、CD、HYP，保留多标签；无目标标签的记录不参与该任务。
- 恒定导联和临床噪声标记保留审计，不补造信号；完全相同波形跨集合时停止生成以待复核。
- 四阶 40 Hz Butterworth 零相位低通；保存处理参数和残差统计，不假定滤波必然提高分类性能。
- 每条真实训练记录生成一个增强副本：全导联同步 ±1–5 点平移、反射填充、1% 源导联标准差的独立高斯噪声，固定种子并保存逐条来源。
- 最终 WFDB 保持 mV、format-16、1 µV 分辨率；重新生成初始值和校验和，不将无单位标准化值伪装成 mV。

## 数据用途

| 目录 | 本机运行记录数 | 用途 |
|---|---:|---|
| train | 17084 | 官方折 1–8，基础训练/微调 |
| train_augmented | 17084 | 同一批训练源记录的增强副本 |
| validation | 2146 | 官方折 9，早停及超参数/阈值选择 |
| test | 2158 | 官方折 10，最终评估 |

增强组使用 train + train_augmented；未增强组仅用 train。两组固定初始权重、优化器、类别权重和训练更新次数，避免把样本翻倍造成的额外训练误认为增强收益。
验证、测试不增强，患者不跨集合。增强是否提升性能必须由实际实验检验。

每个用途目录附官方 28 列元数据、RECORDS、标签映射和许可。只导出 100 Hz，filename_hr 留空；500 Hz 原始文件仍位于官方目录。
根目录元数据只汇总基础记录，增强记录单独管理，避免同一 ecg_id 混淆。

## 读取与标准化

```python
from src.datasets.ptbxl_wfdb import PTBXLWFDBDataset

train = PTBXLWFDBDataset(root="处理版目录", split="train")
augmented_train = PTBXLWFDBDataset(root="处理版目录", split="train", include_augmented=True)
validation = PTBXLWFDBDataset(root="处理版目录", split="validation")
test = PTBXLWFDBDataset(root="处理版目录", split="test")
item = train[0]
# signal: float32[12,1000]；label: float32[5]
```

加载器默认使用仅在基础训练集拟合的 normalization.json。
使用公开预训练模型时，核对其标准化、滤波、切窗和类别顺序；需要原始 mV 时设置 normalize=False，再应用权重要求的处理。
本项目尚未完成 ResNet1D 微调。

## 核验

导出器逐条回读所有文件，验证量化误差、初始值、校验和、元数据路径和患者隔离。
附加读取验证可用支持 wfdb 的 Python 环境运行：

```powershell
python -B scripts/dataset/verify_readers.py --root "处理版目录"
```

该命令只读数据；如果安装了 PyTorch，还会实际验证各用途数据的 DataLoader 批次，不训练模型。
完整处理配置、源文件与输出校验值、排除原因、增强来源记录均在处理版目录内。
