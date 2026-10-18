"""Export processed PTB-XL arrays to official-style WFDB format and partitions.

Source data and the existing array version are read-only. No dependency on wfdb.
Writes format-16, gain 1000 ADC units/mV, with regenerated init/checksum fields.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

LEADS = ['I', 'II', 'III', 'AVR', 'AVL', 'AVF', 'V1', 'V2', 'V3', 'V4', 'V5', 'V6']
CLASSES = ['NORM', 'MI', 'STTC', 'CD', 'HYP']
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARRAYS = (Path(__file__).resolve().parents[1].parent / 'ptbxl_100hz_v1'
                  if Path(__file__).parent.name == '_build'
                  else PROJECT_ROOT / 'data' / 'processed' / 'ptbxl_100hz_v1')
DEFAULT_SOURCE = Path.home() / 'Desktop' / 'ptb-xl-a-large-publicly-available-electrocardiography-dataset-1.0.3'
DEFAULT_OUTPUT = (Path(__file__).resolve().parents[1] if Path(__file__).parent.name == '_build'
                  else PROJECT_ROOT / 'data' / 'processed' / 'ptbxl_wfdb_v1')


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def read_export(record):
    parts = [line.split() for line in record.with_suffix('.hea').read_text(encoding='utf-8').splitlines()]
    assert parts[0] == [record.name, '12', '100', '1000']
    content = record.with_suffix('.dat').read_bytes()
    assert len(content) == 24000
    digital = np.frombuffer(content, dtype='<i2').reshape(1000, 12)
    assert not (digital == -32768).any()
    for index, (row, lead) in enumerate(zip(parts[1:], LEADS)):
        assert row[0] == record.name + '.dat' and row[1:5] == ['16', '1000.0(0)/mV', '16', '0']
        assert row[-1] == lead and int(row[5]) == int(digital[0, index])
        assert int(row[6]) == int(digital[:, index].astype(np.int64).sum() & 0xffff)
    return np.ascontiguousarray(digital.T.astype(np.float32) / np.float32(1000))


def write_record(record, signal, checksums, output):
    assert signal.shape == (12, 1000) and np.isfinite(signal).all()
    digital64 = np.rint(signal.T.astype(np.float64) * 1000).astype(np.int64)
    if digital64.min() < -32767 or digital64.max() > 32767:
        raise ValueError(f'format-16 range exceeded; refusing to clip: {record}')
    digital = digital64.astype('<i2')
    content = digital.tobytes()
    lines = [f'{record.name} 12 100 1000']
    for i, lead in enumerate(LEADS):
        checksum = int(digital64[:, i].sum() & 0xffff)
        lines.append(f'{record.name}.dat 16 1000.0(0)/mV 16 0 {int(digital[0, i])} {checksum} 0 {lead}')
    header = ('\n'.join(lines) + '\n').encode('utf-8')
    record.with_suffix('.dat').write_bytes(content)
    record.with_suffix('.hea').write_bytes(header)
    for suffix, blob in [('.hea', header), ('.dat', content)]:
        path = record.with_suffix(suffix)
        digest = hashlib.sha256(blob).hexdigest()
        assert sha256(path) == digest, f'write verification failed: {path}'
        checksums[path.relative_to(output).as_posix()] = digest
    recovered = read_export(record)
    error = float(np.max(np.abs(recovered.astype(np.float64) - signal)))
    assert error <= .000502, (record, error)
    return recovered, error


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--arrays', type=Path, default=DEFAULT_ARRAYS)
    parser.add_argument('--source', type=Path, default=DEFAULT_SOURCE)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    arrays, source, output = [p.resolve() for p in [args.arrays, args.source, args.output]]
    if output == source or output.is_relative_to(source) or output == arrays or output.is_relative_to(arrays):
        raise ValueError('output must be a separate version directory')
    if (output / 'export_manifest.csv').exists() or (output / 'summary.json').exists():
        raise FileExistsError('refusing to overwrite an existing WFDB version')
    output.mkdir(parents=True, exist_ok=True)
    (output / '_build').mkdir(exist_ok=True)
    if Path(__file__).resolve() != output / '_build' / Path(__file__).name:
        shutil.copyfile(__file__, output / '_build' / Path(__file__).name)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s',
                        handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(output / 'export.log', encoding='utf-8')])
    started = time.perf_counter()
    expected = json.loads((arrays / 'artifacts_sha256.json').read_text(encoding='utf-8'))
    input_hashes = {}
    for name in ['signals_mv.npy', 'train_augmented_signals_standardized.npy', 'manifest.csv',
                 'augmentation_manifest.csv', 'processing_config.json', 'labels.npy', 'train_augmented_labels.npy']:
        digest = sha256(arrays / name)
        if digest != expected[name]['sha256']:
            raise ValueError(f'array version input changed: {name}')
        input_hashes[name] = digest
    logging.info('Input array integrity verified; exporting WFDB records.')
    config = json.loads((arrays / 'processing_config.json').read_text(encoding='utf-8'))
    previous_summary = json.loads((arrays / 'summary.json').read_text(encoding='utf-8'))
    for name, digest in previous_summary['source_metadata_sha256'].items():
        if sha256(source / name) != digest:
            raise ValueError(f'official source metadata changed: {name}')
    manifest = pd.read_csv(arrays / 'manifest.csv')
    augmented_manifest = pd.read_csv(arrays / 'augmentation_manifest.csv')
    original = pd.read_csv(source / 'ptbxl_database.csv').set_index('ecg_id', drop=False)
    selected = original.loc[manifest.ecg_id].copy().reset_index(drop=True)
    physical = np.load(arrays / 'signals_mv.npy', mmap_mode='r', allow_pickle=False)
    augmented = np.load(arrays / 'train_augmented_signals_standardized.npy', mmap_mode='r', allow_pickle=False)
    y = np.load(arrays / 'labels.npy', allow_pickle=False)
    ya = np.load(arrays / 'train_augmented_labels.npy', allow_pickle=False)
    train_indices = np.flatnonzero(manifest.split.eq('train').to_numpy())
    np.testing.assert_array_equal(augmented_manifest.source_row_index, train_indices)
    np.testing.assert_array_equal(ya, y[train_indices])
    source_waveform_samples = {}
    for i in [0, len(manifest) // 2, len(manifest) - 1]:
        row = manifest.iloc[i]
        for suffix, digest_key in [('.hea', 'source_hea_sha256'), ('.dat', 'source_dat_sha256')]:
            relative = row.filename_lr + suffix
            source_waveform_samples[relative] = sha256(source / relative)
            assert source_waveform_samples[relative] == row[digest_key]
    checksums, export_rows, directory_cache = {}, [], set()
    max_error, train_sum, train_squares, train_values = 0.0, 0.0, 0.0, 0
    original_mean, original_std = config['normalization']['mean_mv'], config['normalization']['std_mv']
    for variant, frame in [('base', manifest), ('augmented', augmented_manifest)]:
        for i, row in enumerate(frame.itertuples(index=False)):
            if variant == 'base':
                index = int(row.row_index)
                group, ecg_id, relative, signal = row.split, int(row.ecg_id), row.filename_lr, physical[index]
                labels = y[index]
            else:
                index = int(row.source_row_index)
                group, ecg_id = 'train_augmented', int(row.source_ecg_id)
                relative = manifest.iloc[index].filename_lr
                signal = augmented[i].astype(np.float64) * original_std + original_mean
                labels = ya[i]
            record = output / group / relative
            if record.parent not in directory_cache:
                record.parent.mkdir(parents=True, exist_ok=True)
                directory_cache.add(record.parent)
            recovered, error = write_record(record, signal, checksums, output)
            max_error = max(max_error, error)
            entry = {'ecg_id': ecg_id, 'patient_id': int(manifest.iloc[index].patient_id),
                     'strat_fold': int(manifest.iloc[index].strat_fold), 'purpose': group, 'variant': variant,
                     'filename_lr': record.relative_to(output).as_posix(),
                     'source_filename_lr': relative, 'source_row_index': index,
                     'labels': '|'.join(c for c, present in zip(CLASSES, labels) if present),
                     'quantization_max_abs_error_mv': error}
            entry.update({f'y_{c}': int(present) for c, present in zip(CLASSES, labels)})
            export_rows.append(entry)
            if group == 'train':
                values = recovered.astype(np.float64)
                train_sum += float(values.sum())
                train_squares += float(np.square(values).sum())
                train_values += values.size
            if (i + 1) % 1000 == 0 or i + 1 == len(frame):
                logging.info('Exported/read-back verified %s %d/%d', variant, i + 1, len(frame))
    export_manifest = pd.DataFrame(export_rows)
    export_manifest.to_csv(output / 'export_manifest.csv', index=False, encoding='utf-8-sig')
    group_counts = export_manifest.purpose.value_counts().to_dict()
    purpose_descriptions = {'train': '未增强训练集：用于模型参数更新。',
                            'validation': '验证集：用于早停、选择超参数和阈值，不参与梯度更新。',
                            'test': '最终测试集：仅用于最终评估，不用于选择模型或阈值。',
                            'train_augmented': '增强训练副本：只用于训练，与 train 中相同 ecg_id 的记录对应。'}
    for group, description in purpose_descriptions.items():
        group_dir = output / group
        subset = export_manifest.loc[export_manifest.purpose.eq(group)].copy()
        meta = original.loc[subset.ecg_id].copy().reset_index(drop=True)
        # Keep the official 28-column schema. Only records100 is exported.
        meta['filename_hr'] = ''
        meta.to_csv(group_dir / 'ptbxl_database.csv', index=False, encoding='utf-8-sig')
        for name in ['scp_statements.csv', 'LICENSE.txt']:
            shutil.copyfile(source / name, group_dir / name)
        subset.to_csv(group_dir / 'manifest.csv', index=False, encoding='utf-8-sig')
        (group_dir / 'RECORDS').write_text('\n'.join(subset.source_filename_lr) + '\n', encoding='utf-8')
        (group_dir / 'README.md').write_text(f'# {group}\n\n{description}\n\n共 {len(subset)} 条，100 Hz、10 秒、12 导联，mV 单位。\n'
            '文件基名和 records100 子目录沿用官方命名；filename_lr 可在此目录直接解析。\n'
            '本目录仅含 100 Hz 记录，filename_hr 留空，不代表存在 records500。\n'
            'train_augmented 的标签与临床元数据继承源记录，属于合成训练副本，不是新增患者或临床采集。\n', encoding='utf-8')
    root_meta = selected.copy()
    root_meta['filename_lr'] = manifest.split + '/' + manifest.filename_lr
    root_meta['filename_hr'] = ''
    root_meta.to_csv(output / 'ptbxl_database.csv', index=False, encoding='utf-8-sig')
    for name in ['scp_statements.csv', 'LICENSE.txt']:
        shutil.copyfile(source / name, output / name)
    for name in ['quality_audit.csv', 'augmentation_manifest.csv']:
        shutil.copyfile(arrays / name, output / name)
    (output / 'RECORDS').write_text('\n'.join(root_meta.filename_lr) + '\n', encoding='utf-8')
    (output / 'RECORDS_train_augmented').write_text('\n'.join(export_manifest.loc[export_manifest.variant.eq('augmented'), 'filename_lr']) + '\n', encoding='utf-8')
    mean = train_sum / train_values
    std = float(np.sqrt(train_squares / train_values - mean ** 2))
    write_json(output / 'normalization.json', {
        'method': 'one global scalar z-score; apply at training/inference load time, not encoded into WFDB',
        'mean_mv': mean, 'std_mv': std, 'fit_split': 'train', 'fit_records': group_counts['train'],
        'fit_values': train_values, 'fit_on': 'exported quantized filtered mV waveforms',
        'formula': '(physical_signal_mv - mean_mv) / std_mv',
        'checkpoint_compatibility': 'Use the original checkpoint scaler instead if its protocol requires it.'})
    updated_config = dict(config)
    updated_config.update({'processed_version': 'wfdb-v1',
                           'dtype': 'int16 (stored digital samples)', 'decoded_training_dtype': 'float32',
                           'augmentation_generator_normalization': dict(config['normalization']),
                           'initial_model_compatibility': 'WFDB records contain filtered/augmented physical mV. Apply the preprocessing/scaler required by the selected checkpoint at load time.',
                           'storage': {'format': 'WFDB 16', 'gain_adc_per_mv': 1000, 'baseline': 0,
                                       'resolution_mv': .001, 'unit': 'mV', 'sample_order': 'sample-major interleaved',
                                       'normalization_encoded_in_waveforms': False},
                           'array_version': str(arrays), 'array_input_sha256': input_hashes})
    updated_config['normalization'] = json.loads((output / 'normalization.json').read_text(encoding='utf-8'))
    updated_config['augmentation'] = dict(config['augmentation'])
    updated_config['augmentation']['export_operation_order'] = ['restore_mV_from_generator_scaler', 'round_to_1_microvolt', 'write_WFDB_format16']
    write_json(output / 'processing_config.json', updated_config)
    patients = {g: set(export_manifest.loc[export_manifest.purpose.eq(g), 'patient_id']) for g in purpose_descriptions}
    overlaps = {f'{a}_{b}': len(patients[a] & patients[b]) for a, b in
                [('train', 'validation'), ('train', 'test'), ('validation', 'test'),
                 ('train_augmented', 'validation'), ('train_augmented', 'test')]}
    assert not any(overlaps.values())
    assert export_manifest.loc[export_manifest.variant.eq('augmented'), 'strat_fold'].le(8).all()
    for group, frame in export_manifest.groupby('purpose'):
        assert frame.ecg_id.is_unique
        meta = pd.read_csv(output / group / 'ptbxl_database.csv')
        assert list(meta.columns) == list(original.columns)
        assert len(meta) == len(frame)
        for relative in meta.filename_lr:
            assert (output / group / relative).with_suffix('.hea').is_file()
            assert (output / group / relative).with_suffix('.dat').is_file()
    for name, digest in previous_summary['source_metadata_sha256'].items():
        assert sha256(source / name) == digest
    for relative, digest in source_waveform_samples.items():
        assert sha256(source / relative) == digest
    summary = {'source_version': 'PTB-XL v1.0.3', 'source_root': str(source), 'processed_root': str(output),
               'groups': group_counts, 'base_records': len(manifest), 'augmented_records': len(augmented),
               'wfdb_records': len(export_manifest), 'wfdb_file_pairs': len(export_manifest),
               'format': 'WFDB format-16, 100 Hz, 12 leads, 1000 samples, mV',
               'maximum_quantization_error_mv': max_error,
               'source_exclusions': previous_summary['exclusion_reasons'],
               'constant_lead_records_flagged_and_retained': previous_summary['constant_lead_records'],
               'created_at': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
               'seconds': time.perf_counter() - started, 'training_performed': False}
    write_json(output / 'summary.json', summary)
    write_json(output / 'verification.json', {'passed': True, 'all_records_written_and_read_back': len(export_manifest),
               'all_record_file_hashes_verified': 2 * len(export_manifest), 'all_header_init_and_checksums_verified': True,
               'all_metadata_paths_resolve': True, 'official_28_column_metadata_schema_preserved': True,
               'original_record_basenames_preserved': True, 'physical_units_mv': True,
               'no_clipping_or_missing_value_sentinels': True, 'maximum_quantization_error_mv': max_error,
               'patient_overlap_counts': overlaps, 'augmentation_only_train': True,
               'input_array_integrity_verified': True, 'source_metadata_unchanged': True,
               'sampled_source_waveform_files_unchanged': len(source_waveform_samples)})
    write_readme(output, source, summary)
    # Standard WFDB checksum list; contains every record and all ancillary files.
    for path in output.rglob('*'):
        if path.is_file() and path.name not in ['SHA256SUMS.txt', 'export.log']:
            relative = path.relative_to(output).as_posix()
            if relative not in checksums:
                checksums[relative] = sha256(path)
    (output / 'SHA256SUMS.txt').write_text('\n'.join(f'{digest} {name}' for name, digest in sorted(checksums.items())) + '\n', encoding='utf-8')
    logging.info('Completed WFDB version: %s; %d records', output, len(export_manifest))


def write_readme(output, source, summary):
    text = f'''# PTB-XL v1.0.3 处理版：官方 WFDB 格式与用途划分

官方原始版：`{source}`，原始文件未覆盖。当前目录为正式 WFDB 处理版。

## 用途与文件命名

```text
train/records100/00000/00001_lr.hea        未增强训练记录
train/records100/00000/00001_lr.dat
train_augmented/records100/00000/00001_lr.hea  同一源记录的增强训练副本
train_augmented/records100/00000/00001_lr.dat
validation/records100/xxxxx/xxxxx_lr.hea/.dat
test/records100/xxxxx/xxxxx_lr.hea/.dat
```

实际目录与文件基名完全沿用源记录 filename_lr；增强副本通过用途目录区分，不给文件基名增加后缀，不重新编号。

| 目录 | 条数 | 用途 |
|---|---:|---|
| train | {summary['groups']['train']} | 官方折 1–8；参数更新、未增强对照 |
| train_augmented | {summary['groups']['train_augmented']} | 同一批训练源记录的增强副本；只用于训练 |
| validation | {summary['groups']['validation']} | 官方折 9；早停、超参数、阈值选择 |
| test | {summary['groups']['test']} | 官方折 10；最终性能评估 |

增强训练组应同时使用 train 与 train_augmented，共 34,168 条；独立真实训练记录仍为 17,084 条。
未增强对照组仅使用 train。两组保持同等训练更新次数、初始模型、优化器和验证策略。

## 官方格式兼容性

- 每条为 `.hea/.dat` 配对，WFDB format-16，100 Hz、10 秒、12 导联、每导联 1000 点。
- 使用物理 mV 数值，增益 1000 ADC/mV、baseline=0，分辨率 1 µV，与官方 records100 存储规格一致。
- 对滤波/增强浮点结果进行四舍五入量化，不截断或裁剪越界幅值。最大实际往返误差 {summary['maximum_quantization_error_mv']:.9f} mV，约 0.5 µV。
- 每条头文件的初始值和 checksum 已按新波形重算，不能沿用旧头文件 checksum。
- 不把标准化后的无单位数值写成 mV。标准化参数保存在 normalization.json，训练加载时应用。
- 此版仅导出 records100；官方 records500 仍在原始目录。各 ptbxl_database.csv 保留官方 28 列，filename_hr 留空以免指向不存在的 500 Hz 文件。
- 每个用途目录含独立 ptbxl_database.csv、scp_statements.csv、RECORDS、LICENSE.txt，filename_lr 在对应目录下直接有效。
- 根目录 ptbxl_database.csv 汇总 21,388 条基础记录，filename_lr 带 train/validation/test 前缀；不把增强副本当作新的独立 ecg_id 混入。
- 可以在现有应用中选择用途目录作为数据集根目录；也可直接填写任何 `.hea` 文件路径。应用默认仍可能指向官方原始目录，需要手动切换。

## 处理内容与来源

基于官方 v1.0.3 records100；质量核验、五类标签映射，排除 411 条无目标标签记录。
恒定导联记录 12722 的 V5 保留并标记；不补造导联，不按预测结果删样本。
滤波为四阶 40 Hz Butterworth 零相位低通；不额外做高通或强基线校正。
训练增强为 1% 导联标准差的高斯噪声 + 全导联同步 ±1–5 点平移，反射填充；标签继承源记录。
保存的归一化参数仅由导出后 train 的 mV 波形拟合；使用预训练权重时须匹配该权重的预处理协议。

## 清单与报告

- export_manifest.csv：全部基础/增强记录的用途、源编号、物理路径和五类标签。
- quality_audit.csv：全部 21,799 条官方源记录的质量审计和排除原因。
- augmentation_manifest.csv：每条增强记录的源编号、平移量、噪声幅度和随机种子。
- processing_config.json / normalization.json：处理与归一化参数。
- summary.json / verification.json：实际规模和核验结果。
- SHA256SUMS.txt：新版本记录及附属文件校验值；不替换官方源目录中的校验文件。
- _build/export_wfdb.py：重现导出脚本；依赖 numpy、pandas，输入为已核验的数组版。

临床元数据与报告文字沿用官方 ptbxl_database.csv，增强副本的元数据来自源记录，不代表新的临床检查。
数据准备已完成，但未训练 ResNet1D，也尚未证明增强提高模型性能。

来源：https://physionet.org/content/ptb-xl/1.0.3/ ，CC BY 4.0，许可见 LICENSE.txt。
引用：Wagner et al. (2020), PTB-XL, a large publicly available electrocardiography dataset, Scientific Data 7, 154, https://doi.org/10.1038/s41597-020-0495-6 。
'''
    (output / 'README.md').write_text(text, encoding='utf-8')
    association = '''# 数据—模型关联表

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
'''
    (output / 'data_model_association.md').write_text(association, encoding='utf-8')


if __name__ == '__main__':
    main()
