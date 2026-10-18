# PTB-XL 数据查看应用

在项目根目录运行 `python -m streamlit run app/app.py`，或使用相同功能的 `app/detect.py`。

当前未启用任何分类模型。支持 100 Hz、10 秒、12 导联 WFDB 记录、本地 PTB-XL 编号和 1,000×12 数字 CSV，显示完整波形与 mV 数据表。
点击“读取并查看波形”即可预览。CSV 表头可采用标准导联名称；无表头时必须遵守 I、II、III、aVR、aVL、aVF、V1–V6 的顺序。

查看处理版时，可选择处理版根目录或 train/validation/test/train_augmented 用途目录作为数据集目录，也可直接填写 `.hea` 路径。
500 Hz、报告图片、视频和报告文字不属于当前输入范围。
