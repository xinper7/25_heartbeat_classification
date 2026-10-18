# 数据—模型关联表

| 数据处理特点 | 数据证据 | 模型/优化策略 | 实验比较 |
|---|---|---|---|
| 12 导联、100 Hz、10 秒 | 官方风格 WFDB，单条 12×1000 | 多通道 ResNet1D；按 checkpoint 协议切窗 | 固定相同模型结构 |
| 五类多标签 | manifest 中 y_NORM/y_MI/y_STTC/y_CD/y_HYP | 5 logits + BCEWithLogitsLoss，推理 Sigmoid | 逐类 F1、宏 F1、AUROC |
| 类别不平衡 | 对 train 元数据统计各类阳性数 | 类别权重只由 train 计算，两组相同 | 分析 HYP 等类别召回和误报 |
| 未增强真实训练记录 17084 条 | train | 作为微调基线 | 同一初始权重、相同训练步数 |
| 增强副本 17084 条 | train_augmented；逐条源记录和参数 | 与 train 混合训练，提高对轻微扰动的鲁棒性 | 与仅 train 的组比较；不得预设改善 |
| 40 Hz 低通滤波和恒定导联标记 | quality_audit.csv / processing_config.json | 分析滤波对特征和异常类别的影响 | 如需滤波消融，用相同记录从官方原始版取波形 |
| 官方患者隔离折 | train 1–8 / validation 9 / test 10 | 验证集选模型、测试集最终评估 | 无患者交叉；增强仅 train |
| 标准化仅在 train 拟合 | normalization.json；WFDB 仍保留 mV | 保留跨记录幅值差异 | 不在验证/测试重新拟合 |

问题分析需关联实际质量标记、滤波残差、增强强度、类别分布和训练/验证曲线。
增强对照两组的基础预处理必须相同；训练数据数目不同应固定更新次数，避免混淆因素。
