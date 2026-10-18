"""Reproducible PTB-XL v1.0.3 preprocessing; never writes to the source tree.

Dependencies: numpy, pandas, scipy. Output is for five-superclass research.
Run --self-test before building; use --verify to validate an existing build.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import logging
import platform
import re
import shutil
import sys
import time
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import scipy
from numpy.lib.format import open_memmap
from scipy.signal import butter, sosfiltfilt

LEADS = ['I', 'II', 'III', 'aVR', 'aVL', 'aVF', 'V1', 'V2', 'V3', 'V4', 'V5', 'V6']
CLASSES = ['NORM', 'MI', 'STTC', 'CD', 'HYP']
DEFAULT_SOURCE = Path.home() / 'Desktop' / 'ptb-xl-a-large-publicly-available-electrocardiography-dataset-1.0.3'
DEFAULT_OUTPUT = (Path(__file__).resolve().parents[1] if Path(__file__).parent.name == '_build'
                  else Path(__file__).resolve().parents[2] / 'data' / 'processed' / 'ptbxl_100hz_v1')
FILTER = butter(4, 40, btype='lowpass', fs=100, output='sos')
SEED = 42
NOISE_FRACTION = 0.01
SHIFT_MAX = 5


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def checksum_table(root):
    result = {}
    for line in (root / 'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines():
        digest, name = line.split(maxsplit=1)
        result[name.lstrip('*').removeprefix('./')] = digest
    return result


def read_record(root, relative, checksums):
    """Decode and verify the restricted, official 100-Hz WFDB format."""
    record = (root / relative).resolve()
    if not record.is_relative_to(root):
        raise ValueError('record path outside source root')
    header = record.with_suffix('.hea')
    header_bytes = header.read_bytes()
    header_hash = hashlib.sha256(header_bytes).hexdigest()
    if header_hash != checksums[header.relative_to(root).as_posix()]:
        raise ValueError('official header checksum mismatch')
    lines = [line.split() for line in header_bytes.decode('utf-8').splitlines()
             if line.strip() and not line.startswith('#')]
    if len(lines[0]) < 4 or tuple(map(int, lines[0][1:4])) != (12, 100, 1000):
        raise ValueError('expected 12 leads, 100 Hz, 1000 samples')
    names, gains, baselines, files = [], [], [], []
    for parts in lines[1:13]:
        if len(parts) < 9 or parts[1] != '16':
            raise ValueError('expected WFDB format 16')
        match = re.fullmatch(r'([0-9.]+)\(([+-]?\d+)\)/mV', parts[2])
        if not match or float(match[1]) <= 0:
            raise ValueError('invalid gain, baseline, or physical unit')
        files.append(parts[0])
        gains.append(float(match[1]))
        baselines.append(int(match[2]))
        names.append(parts[-1].upper())
    expected = [name.upper() for name in LEADS]
    if len(names) != 12 or set(names) != set(expected) or len(set(files)) != 1:
        raise ValueError('missing/duplicate leads or unsupported data layout')
    if Path(files[0]).name != files[0]:
        raise ValueError('data file outside recording directory')
    data_path = record.parent / files[0]
    content = data_path.read_bytes()
    data_hash = hashlib.sha256(content).hexdigest()
    if data_hash != checksums[data_path.relative_to(root).as_posix()]:
        raise ValueError('official signal checksum mismatch')
    if len(content) != 24000:
        raise ValueError('wrong signal byte count')
    digital = np.frombuffer(content, dtype='<i2').reshape(1000, 12)
    if (digital == -32768).any():
        raise ValueError('WFDB missing-value sentinel found')
    physical = (digital.astype(np.float32) - np.asarray(baselines, dtype=np.float32)) / np.asarray(gains, dtype=np.float32)
    signal = np.ascontiguousarray(physical[:, [names.index(name) for name in expected]].T)
    if signal.shape != (12, 1000) or not np.isfinite(signal).all():
        raise ValueError('invalid waveform shape or nonfinite values')
    return signal, header_hash, data_hash, int((digital == 32767).sum())


def preprocess(signal):
    """Conservative zero-phase low-pass; retain and flag flat leads."""
    constant = signal.std(axis=1, dtype=np.float64) < 1e-8
    result = sosfiltfilt(FILTER, signal.astype(np.float64), axis=-1).astype(np.float32)
    result[constant] = signal[constant]
    if not np.isfinite(result).all():
        raise ValueError('filter produced nonfinite values')
    return result, constant


def shift_signal(signal, shift):
    if shift > 0:
        return np.pad(signal, ((0, 0), (shift, 0)), mode='reflect')[:, :signal.shape[-1]]
    if shift < 0:
        return np.pad(signal, ((0, 0), (0, -shift)), mode='reflect')[:, -shift:]
    return signal.copy()


def augment(signal, ecg_id):
    rng = np.random.default_rng(np.random.SeedSequence([SEED, int(ecg_id)]))
    choices = np.asarray([i for i in range(-SHIFT_MAX, SHIFT_MAX + 1) if i])
    shift = int(rng.choice(choices))
    sigma = signal.std(axis=1, keepdims=True, dtype=np.float64) * NOISE_FRACTION
    sigma[signal.std(axis=1, dtype=np.float64)[:, None] < 1e-8] = 0
    noise = rng.normal(size=signal.shape) * sigma
    result = (shift_signal(signal, shift) + noise).astype(np.float32)
    return result, shift


def label_names(raw, mapping):
    codes = ast.literal_eval(raw)
    if not isinstance(codes, dict):
        raise ValueError('scp_codes must be a dictionary')
    found = {mapping[code] for code in codes if code in mapping}
    return [name for name in CLASSES if name in found]


def split_name(fold):
    return 'train' if fold <= 8 else ('validation' if fold == 9 else 'test')


def chunk_normalize(source, target, mean, std):
    for start in range(0, len(source), 128):
        target[start:start + 128] = ((source[start:start + 128].astype(np.float64) - mean) / std).astype(np.float32)
    target.flush()


def build(source, output):
    started = time.perf_counter()
    source, output = source.resolve(), output.resolve()
    if source == output or source in output.parents or output in source.parents:
        raise ValueError('source and output must be separate sibling/unrelated trees')
    if (output / 'manifest.csv').exists() or (output / 'summary.json').exists():
        raise FileExistsError('refusing to overwrite an existing dataset build')
    output.mkdir(parents=True, exist_ok=True)
    (output / '_build').mkdir(exist_ok=True)
    destination_script = output / '_build' / 'prepare_dataset.py'
    if destination_script.resolve() != Path(__file__).resolve():
        shutil.copyfile(Path(__file__), destination_script)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s',
                        handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(output / 'processing.log', encoding='utf-8')])
    log = logging.getLogger('ptbxl')
    checksums = checksum_table(source)
    metadata_hashes = {}
    for name in ['ptbxl_database.csv', 'scp_statements.csv', 'LICENSE.txt']:
        digest = sha256(source / name)
        if digest != checksums[name]:
            raise ValueError(f'official checksum mismatch: {name}')
        metadata_hashes[name] = digest
    metadata_hashes['SHA256SUMS.txt'] = sha256(source / 'SHA256SUMS.txt')
    metadata = pd.read_csv(source / 'ptbxl_database.csv').sort_values('ecg_id').reset_index(drop=True)
    statements = pd.read_csv(source / 'scp_statements.csv', index_col=0)
    mapping = statements.loc[statements.diagnostic.eq(1), 'diagnostic_class'].to_dict()
    metadata['target_labels'] = metadata.scp_codes.map(lambda value: label_names(value, mapping))
    if metadata.ecg_id.duplicated().any():
        raise ValueError('duplicate ecg_id in official metadata')
    if metadata.groupby('patient_id').strat_fold.nunique().gt(1).any():
        raise ValueError('a patient occurs in different official folds')
    if not metadata.strat_fold.isin(range(1, 11)).all():
        raise ValueError('invalid official fold')
    capacity = int(metadata.target_labels.map(bool).sum())
    staged_path = output / '_signals_staging.npy'
    staged = open_memmap(staged_path, mode='w+', dtype=np.float32, shape=(capacity, 12, 1000))
    audit_rows, rows, fingerprints = [], [], {}
    checksum_rows = []
    train_sum, train_squares, train_values = 0.0, 0.0, 0
    for number, row in enumerate(metadata.itertuples(), start=1):
        fold, labels = int(row.strat_fold), row.target_labels
        audit = {'ecg_id': int(row.ecg_id), 'patient_id': int(row.patient_id),
                 'strat_fold': fold, 'split': split_name(fold), 'filename_lr': row.filename_lr,
                 'labels': '|'.join(labels), 'kept': False, 'reason': '', 'constant_leads': '',
                 'metadata_static_noise': bool(pd.notna(row.static_noise)),
                 'metadata_burst_noise': bool(pd.notna(row.burst_noise)),
                 'metadata_baseline_drift': bool(pd.notna(row.baseline_drift)),
                 'metadata_electrodes_problems': bool(pd.notna(row.electrodes_problems))}
        try:
            raw, header_hash, data_hash, adc_limit = read_record(source, row.filename_lr, checksums)
            checksum_rows.extend([{'path': row.filename_lr + '.hea', 'sha256': header_hash},
                                  {'path': row.filename_lr + '.dat', 'sha256': data_hash}])
            fingerprint = hashlib.sha256(raw.tobytes()).hexdigest()
            fingerprints.setdefault(fingerprint, []).append({'ecg_id': int(row.ecg_id), 'split': split_name(fold)})
            filtered, constant = preprocess(raw)
            audit.update({'constant_leads': '|'.join(np.asarray(LEADS)[constant]),
                          'max_abs_mv': float(np.abs(raw).max()), 'adc_upper_limit_samples': adc_limit,
                          'filter_residual_rms_mv': float(np.sqrt(np.mean((raw.astype(np.float64) - filtered) ** 2))),
                          'waveform_sha256': fingerprint})
            if not labels:
                audit['reason'] = 'no_target_superclass'
            else:
                index = len(rows)
                staged[index] = filtered
                audit.update({'kept': True, 'reason': 'kept_flagged' if constant.any() else 'kept', 'row_index': index})
                rows.append({'row_index': index, 'ecg_id': int(row.ecg_id), 'patient_id': int(row.patient_id),
                             'strat_fold': fold, 'split': split_name(fold), 'filename_lr': row.filename_lr,
                             'labels': '|'.join(labels), 'constant_leads': audit['constant_leads'],
                             'source_hea_sha256': header_hash, 'source_dat_sha256': data_hash})
                if fold <= 8:
                    values = filtered.astype(np.float64)
                    train_sum += float(values.sum())
                    train_squares += float(np.square(values).sum())
                    train_values += values.size
        except (ValueError, OSError, KeyError) as exc:
            audit['reason'] = 'invalid_signal: ' + str(exc)
        audit_rows.append(audit)
        if number % 1000 == 0 or number == len(metadata):
            log.info('Decoded/audited %d/%d; retained %d', number, len(metadata), len(rows))
    staged.flush()
    duplicates = [members for members in fingerprints.values() if len(members) > 1]
    cross_split_duplicates = [members for members in duplicates if len({r['split'] for r in members}) > 1]
    if cross_split_duplicates:
        write_json(output / 'cross_split_duplicates.json', cross_split_duplicates)
        raise ValueError('identical waveforms cross splits; build stopped for explicit review')
    count = len(rows)
    if not count or not train_values:
        raise ValueError('no eligible data/train samples')
    mean = train_sum / train_values
    std = float(np.sqrt(max(train_squares / train_values - mean ** 2, 0)))
    if std < 1e-8:
        raise ValueError('degenerate training standard deviation')
    del staged
    physical_path = output / 'signals_mv.npy'
    if count == capacity:
        staged_path.rename(physical_path)
    else:
        staged = np.load(staged_path, mmap_mode='r', allow_pickle=False)
        physical = open_memmap(physical_path, mode='w+', dtype=np.float32, shape=(count, 12, 1000))
        for start in range(0, count, 128):
            physical[start:start + 128] = staged[start:min(count, start + 128)]
        physical.flush()
        del physical, staged
        staged_path.unlink()
    manifest = pd.DataFrame(rows)
    manifest.to_csv(output / 'manifest.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(audit_rows).to_csv(output / 'quality_audit.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(checksum_rows).to_csv(output / 'source_waveform_checksums.csv', index=False)
    physical = np.load(physical_path, mmap_mode='r', allow_pickle=False)
    normalized = open_memmap(output / 'signals_standardized.npy', mode='w+', dtype=np.float32, shape=physical.shape)
    chunk_normalize(physical, normalized, mean, std)
    labels = np.asarray([[c in r['labels'].split('|') for c in CLASSES] for r in rows], dtype=np.uint8)
    np.save(output / 'labels.npy', labels, allow_pickle=False)
    splits = {}
    for name in ['train', 'validation', 'test']:
        indices = np.flatnonzero(manifest.split.eq(name).to_numpy()).astype(np.int64)
        np.save(output / f'{name}_indices.npy', indices, allow_pickle=False)
        splits[name] = {'records': len(indices), 'patients': int(manifest.iloc[indices].patient_id.nunique()),
                        'class_positive_counts': dict(zip(CLASSES, map(int, labels[indices].sum(axis=0))))}
    train_indices = np.load(output / 'train_indices.npy', allow_pickle=False)
    augmented = open_memmap(output / 'train_augmented_signals_standardized.npy', mode='w+', dtype=np.float32,
                            shape=(len(train_indices), 12, 1000))
    augmented_rows = []
    for j, index in enumerate(train_indices):
        row = rows[int(index)]
        augmented[j], shift = augment(normalized[int(index)], row['ecg_id'])
        augmented_rows.append({'augmented_index': j, 'sample_id': f"ecg_{row['ecg_id']:05d}_aug1",
                               'source_row_index': int(index), 'source_ecg_id': row['ecg_id'],
                               'patient_id': row['patient_id'], 'strat_fold': row['strat_fold'], 'split': 'train',
                               'labels': row['labels'], 'shift_samples': shift, 'shift_seconds': shift / 100,
                               'noise_std_fraction_per_lead': NOISE_FRACTION,
                               'seed_entropy': f"{SEED},{row['ecg_id']}"})
        if (j + 1) % 2000 == 0:
            log.info('Augmented %d/%d training records', j + 1, len(train_indices))
    augmented.flush()
    np.save(output / 'train_augmented_labels.npy', labels[train_indices], allow_pickle=False)
    pd.DataFrame(augmented_rows).to_csv(output / 'augmentation_manifest.csv', index=False, encoding='utf-8-sig')
    config = {
        'dataset': 'PTB-XL', 'source_version': '1.0.3', 'processed_version': '100hz-v1',
        'source_root': str(source), 'leads': LEADS, 'classes': CLASSES, 'sampling_rate_hz': 100, 'duration_seconds': 10,
        'shape_per_record': [12, 1000], 'dtype': 'float32',
        'cleaning': {'exclude': ['unreadable/invalid signal', 'official checksum failure', 'no target superclass'],
                     'constant_leads': 'flag and retain; no imputation',
                     'clinical_noise_flags': 'retain and record, not automatic exclusions',
                     'exact_duplicates': 'audit; stop for review if cross-split; retain within-split'},
        'filter': {'type': 'Butterworth lowpass', 'order': 4, 'cutoff_hz': 40, 'fs_hz': 100,
                   'implementation': 'scipy.signal.sosfiltfilt', 'phase': 'zero phase', 'padding': 'SciPy default odd reflection',
                   'constant_leads': 'left unchanged', 'highpass_or_notch': False},
        'normalization': {'method': 'one global scalar z-score fitted on filtered training values only',
                          'mean_mv': mean, 'std_mv': std, 'fit_values': train_values,
                          'formula': '(filtered_mV - mean_mv) / std_mv',
                          'preserves_between_record_amplitude_differences': True},
        'augmentation': {'training_only': True, 'copies_per_training_record': 1, 'seed': SEED,
                         'rng': 'numpy default_rng(SeedSequence([42, ecg_id]))',
                         'noise': 'independent Gaussian per sample/lead; std=0.01*source lead std',
                         'synchronous_shift_samples': [-5, -4, -3, -2, -1, 1, 2, 3, 4, 5],
                         'shift_padding': 'reflect; no circular wrap', 'changes_labels': False,
                         'operation_order': ['normalize', 'synchronous shift', 'Gaussian noise'],
                         'constant_leads': 'zero noise sigma; remain constant'},
        'split_rule': 'official strat_fold 1-8 train / 9 validation / 10 test; no resplitting',
        'dependencies': {'python': platform.python_version(), 'numpy': np.__version__, 'pandas': pd.__version__, 'scipy': scipy.__version__},
        'initial_model_compatibility': 'These arrays do not certify compatibility with a particular pretrained checkpoint. Use signals_mv.npy and the checkpoint original scaler/preprocessing when required.'}
    write_json(output / 'processing_config.json', config)
    audit_df = pd.DataFrame(audit_rows)
    summary = {'source_records': len(metadata), 'source_patients': int(metadata.patient_id.nunique()),
               'retained_records': count, 'excluded_records': len(metadata) - count,
               'exclusion_reasons': audit_df.loc[~audit_df.kept, 'reason'].value_counts().to_dict(),
               'constant_lead_records': [int(r['ecg_id']) for r in audit_rows if r.get('constant_leads')],
               'constant_leads_total': sum(len(r['constant_leads'].split('|')) for r in audit_rows if r.get('constant_leads')),
               'exact_duplicate_waveform_groups': duplicates, 'cross_split_duplicate_groups': len(cross_split_duplicates),
               'splits': splits, 'augmented_training_records': len(train_indices),
               'combined_training_records': 2 * len(train_indices), 'validation_test_augmented': False,
               'filter_residual_rms_mv_quantiles': {str(q): float(audit_df.filter_residual_rms_mv.quantile(q)) for q in [0, .5, .95, 1]},
               'source_metadata_sha256': metadata_hashes,
               'verified_source_waveform_files': len(checksum_rows),
               'created_at': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
               'seconds_before_verification': time.perf_counter() - started,
               'model_training_performed': False, 'augmentation_performance_improvement_measured': False}
    write_json(output / 'summary.json', summary)
    shutil.copyfile(source / 'LICENSE.txt', output / 'LICENSE.source.txt')
    requirements = '\n'.join(f'{name}=={version}' for name, version in config['dependencies'].items() if name != 'python')
    (output / '_build' / 'requirements.txt').write_text(requirements + '\n', encoding='utf-8')
    write_docs(output, summary, config)
    del physical, normalized, augmented
    log.info('Validating complete arrays, labels, augmentation and source integrity...')
    result = verify(output, source, verify_source=True)
    write_json(output / 'verification.json', result)
    log.info('Completed: %s', output)


def write_docs(output, summary, config):
    train, val, test = [summary['splits'][s]['records'] for s in ['train', 'validation', 'test']]
    text = f'''# PTB-XL v1.0.3 处理版：100 Hz，12 导联

## 两个数据版本

- 官方原始版：`{config['source_root']}`，原始文件只读使用，不复制或覆盖。
- 当前目录：独立处理版 `100hz-v1`。来源为 https://physionet.org/content/ptb-xl/1.0.3/ ，CC BY 4.0，保留 LICENSE.source.txt。

引用：Wagner et al., PTB-XL, a large publicly available electrocardiography dataset, Scientific Data 7, 154 (2020), https://doi.org/10.1038/s41597-020-0495-6 。版本 DOI：https://doi.org/10.13026/kfzx-aw45 。

## 实际规模

完整来源 {summary['source_records']} 条、{summary['source_patients']} 位患者；保留 {summary['retained_records']} 条，排除 {summary['excluded_records']} 条，原因见 summary.json / quality_audit.csv。
官方第 1–8/9/10 折分别为训练 {train}、验证 {val}、测试 {test} 条。未重新随机划分。
另生成 {train} 条训练增强样本，与基础训练样本合用时为 {2 * train} 条，但独立真实记录仍只有 {train} 条。
验证、测试不生成增强样本。

## 数组与对应关系

| 文件 | 形状/含义 |
|---|---|
| signals_mv.npy | ({summary['retained_records']}, 12, 1000)，滤波后的 mV 波形 |
| signals_standardized.npy | 同上，使用训练集统计量标准化；未增强基线 |
| labels.npy | ({summary['retained_records']}, 5)，uint8 多标签 |
| train_indices.npy / validation_indices.npy / test_indices.npy | 对上述全量数组和 manifest.csv 的行号索引 |
| train_augmented_signals_standardized.npy | ({train}, 12, 1000)，每个训练记录一条增强副本 |
| train_augmented_labels.npy | ({train}, 5)，对应增强数组 |
| manifest.csv | 行号、ecg_id、patient_id、折号、标签、来源校验值 |
| augmentation_manifest.csv | 增强行号、源记录、源行号、实际平移量、噪声比例、随机种子 |
| quality_audit.csv | 全部官方记录的质量检查和保留/排除原因 |
| source_waveform_checksums.csv | 读取的原始 .hea/.dat 的 SHA-256 |

导联顺序：{', '.join(LEADS)}。标签顺序：{', '.join(CLASSES)}。波形 dtype=float32。
标准化数组无物理单位，不能作为 mV CSV 直接上传现有应用；需要 mV 时使用 signals_mv.npy。
数组已归一化，训练时不要再次逐记录 Z-score，避免改变已定义的输入。

## 预处理和增强

1. 核对官方 SHA256SUMS、WFDB 配对、格式、100 Hz、12 导联、1000 点、缺失采样和有限值。
2. 映射五个诊断超类；无目标标签的记录不参与该五类任务，不代表信号本身有病理或质量错误。
3. 恒定导联标记并保留，不插值或补造；临床噪声标记不自动删除。跨集合完全相同波形会停止生成以待复核。
4. 保守四阶 40 Hz Butterworth 零相位低通；不实施高通、强基线校正或工频陷波。此步骤不保证改善分类性能。
5. 仅在训练折的滤波波形上拟合一个全局均值/标准差；验证和测试沿用，保留记录间幅值差异。
6. 每条训练记录生成一个副本：全部导联同步平移 ±1 至 ±5 点（10–50 ms，反射填充，无循环拼接），再加标准差为源导联标准差 1% 的独立高斯噪声。恒定导联不加噪声。

完整数值参数、软件版本和种子见 processing_config.json。生成器位于 _build/prepare_dataset.py。

## 用于 ResNet1D 的对照实验

- 基础组：train_indices 索引 signals_standardized.npy，只使用原训练记录。
- 增强组：相同原训练记录加 train_augmented_signals_standardized.npy。
- 两组从同一个初始 checkpoint 出发；固定模型、优化器、类别权重、训练步数、验证策略和种子。
- 训练步数需一致：增强组记录数翻倍不应无意间获得双倍更新次数。可以每步从基础/增强样本中混合采样，并固定总步数。
- 两组共用相同验证和测试记录；只用验证集选模型/阈值，测试集不参与优化。
- 建议多个相同种子重复，报告宏平均 F1、AUROC、各类精确率/召回率和误报/漏报。
- 如需研究滤波的作用，在官方原始波形上应用相同集合/标准化规则做独立对照；不能把滤波和增强同时变化后仅归因于增强。
- 这里是数据产物，尚未训练模型，也没有证明增强带来性能提升。
- 如果使用的预训练权重要求原始训练 scaler、不同滤波或切窗，应按该 checkpoint 协议适配；当前标准化数据并非任意权重的直接替代输入。

## Python 读取示例（节省内存）

```python
from pathlib import Path
import numpy as np
root = Path(r"{output}")
x = np.load(root / 'signals_standardized.npy', mmap_mode='r')
y = np.load(root / 'labels.npy', mmap_mode='r')
idx = np.load(root / 'train_indices.npy')
x_aug = np.load(root / 'train_augmented_signals_standardized.npy', mmap_mode='r')
y_aug = np.load(root / 'train_augmented_labels.npy', mmap_mode='r')
# x[idx[i]], y[idx[i]] 是基础样本；x_aug[i], y_aug[i] 是对应增强样本。
# 训练 Dataset 按单条索引读取，避免一次性把全部数组复制进内存。
```

## 重现与核验

```powershell
python -B _build/prepare_dataset.py --self-test
python -B _build/prepare_dataset.py --source "{config['source_root']}" --output "新的输出目录"
python -B _build/prepare_dataset.py --verify --output "{output}" --source "{config['source_root']}"
```

生成器拒绝覆盖已有数据版本；复现时使用新的输出目录。核验结果见 verification.json，输出文件校验表见 artifacts_sha256.json。
本版未复制自由文本报告、人口学信息或日期；患者编号仅用于本地患者隔离审计。
'''
    (output / 'README.md').write_text(text, encoding='utf-8')
    counts = summary['splits']['train']['class_positive_counts']
    association = f'''# 数据—模型关联与问题分析模板

此表的模型部分是后续实验设计，当前未训练 ResNet1D，不代表已经取得改进结果。

| 数据特点/实际处理 | 本版证据 | 模型选择或优化策略 | 后续验证 |
|---|---|---|---|
| 10 秒、12 导联、100 Hz | 每条 12×1000；输入来源逐文件校验 | 多通道 ResNet1D 提取波形时序特征 | 基础/增强组用同一架构 |
| 五类多标签 | 标签顺序 {', '.join(CLASSES)} | 5 logits + BCEWithLogitsLoss，推理 Sigmoid | 宏 F1、逐类 F1、AUROC |
| 训练类分布不均 | {json.dumps(counts, ensure_ascii=False)}；多标签支持数可重叠 | 类别权重只由训练标签计算，两组固定相同 | HYP 等类别召回与误报变化 |
| 真实训练样本 {train} 条 | manifest.csv / train_indices.npy | 控制模型复杂度；验证集早停 | 训练/验证损失、种子间波动 |
| 单记录包含多导联 | 全导联同步平移，不改变相对时序 | 同步时移增强，降低对起点依赖 | 单独时移组与组合组消融 |
| 信号噪声和恒定导联 | quality_audit.csv；恒定导联记录 {summary['constant_lead_records']} | 保守低通、轻微噪声增强；恒定导联保留标记 | 按质量标记分组评估；检查滤波是否损害类别特征 |
| 标准化 | 仅训练折拟合全局均值/标准差 | 保留记录间幅值差异，避免逐记录幅值缩放被 Z-score 抵消 | 训练均值≈0、标准差≈1；验证/测试不重新拟合 |
| 增强记录 {train} 条 | augmentation_manifest.csv 逐条源记录和参数 | 基础+增强混合训练，保持同等更新步数 | 与未增强微调组对照，不能预设提升 |
| 同一患者多记录 | 官方 1–8/9/10 折，保留 patient_id | 患者隔离，禁止增强样本跨集合 | 患者交集为 0；配对比较或患者级 bootstrap |

## 问题分析应填写实际结果

1. 滤波影响：原始波形与滤波波形的残差统计见 summary.json；必要时对同一记录做波形叠图并分析 MI/STTC/HYP 等类别变化。
2. 类别不平衡：对照增强前后每类精确率/召回率，不以总体指标掩盖弱类别。
3. 增强强度：若验证性能下降，检查噪声幅度和平移边界；用单独噪声、单独时移消融定位原因。
4. 过拟合：检查训练/验证曲线。两组训练步数一致，避免把额外更新次数当作增强收益。
5. 保留技术质量标记与排除原因，禁止按模型预测结果选择样本或删除难例。
6. 增强标签继承源记录是训练假设，不是新医生标注；实验应验证其影响。
'''
    (output / 'data_model_association.md').write_text(association, encoding='utf-8')


def verify(output, source, verify_source=True):
    output, source = Path(output), Path(source)
    config = json.loads((output / 'processing_config.json').read_text(encoding='utf-8'))
    summary = json.loads((output / 'summary.json').read_text(encoding='utf-8'))
    manifest = pd.read_csv(output / 'manifest.csv')
    aug_manifest = pd.read_csv(output / 'augmentation_manifest.csv')
    x_mv = np.load(output / 'signals_mv.npy', mmap_mode='r', allow_pickle=False)
    x = np.load(output / 'signals_standardized.npy', mmap_mode='r', allow_pickle=False)
    y = np.load(output / 'labels.npy', mmap_mode='r', allow_pickle=False)
    xa = np.load(output / 'train_augmented_signals_standardized.npy', mmap_mode='r', allow_pickle=False)
    ya = np.load(output / 'train_augmented_labels.npy', mmap_mode='r', allow_pickle=False)
    n = len(manifest)
    assert x.shape == x_mv.shape == (n, 12, 1000)
    assert y.shape == (n, 5) and np.isin(y, [0, 1]).all() and y.any(axis=1).all()
    assert np.array_equal(manifest.row_index, np.arange(n)) and manifest.ecg_id.is_unique
    indices = {s: np.load(output / f'{s}_indices.npy', allow_pickle=False) for s in ['train', 'validation', 'test']}
    assert np.array_equal(np.sort(np.concatenate(list(indices.values()))), np.arange(n))
    patients = {s: set(manifest.iloc[idx].patient_id) for s, idx in indices.items()}
    overlaps = {f'{a}_{b}': len(patients[a] & patients[b]) for a, b in [('train', 'validation'), ('train', 'test'), ('validation', 'test')]}
    assert not any(overlaps.values())
    assert manifest.iloc[indices['train']].strat_fold.le(8).all()
    assert manifest.iloc[indices['validation']].strat_fold.eq(9).all()
    assert manifest.iloc[indices['test']].strat_fold.eq(10).all()
    for i, raw_labels in enumerate(manifest.labels):
        assert np.array_equal(y[i], [c in raw_labels.split('|') for c in CLASSES])
    mean, std = config['normalization']['mean_mv'], config['normalization']['std_mv']
    for start in range(0, n, 128):
        end = min(n, start + 128)
        assert np.isfinite(x[start:end]).all() and np.isfinite(x_mv[start:end]).all()
        expected = ((x_mv[start:end].astype(np.float64) - mean) / std).astype(np.float32)
        np.testing.assert_array_equal(x[start:end], expected)
    assert xa.shape == (len(indices['train']), 12, 1000)
    np.testing.assert_array_equal(ya, y[indices['train']])
    np.testing.assert_array_equal(aug_manifest.source_row_index, indices['train'])
    assert aug_manifest.strat_fold.le(8).all() and aug_manifest.split.eq('train').all()
    for j, source_index in enumerate(indices['train']):
        assert np.isfinite(xa[j]).all()
        expected, shift = augment(x[int(source_index)], int(manifest.iloc[int(source_index)].ecg_id))
        assert shift == int(aug_manifest.iloc[j].shift_samples)
        np.testing.assert_array_equal(xa[j], expected)
        assert not np.array_equal(xa[j], x[int(source_index)])
    total, squares, elements = 0.0, 0.0, 0
    for start in range(0, len(indices['train']), 128):
        block = x[indices['train'][start:start + 128]].astype(np.float64)
        total += float(block.sum()); squares += float(np.square(block).sum()); elements += block.size
    fitted_mean = total / elements
    fitted_std = float(np.sqrt(squares / elements - fitted_mean ** 2))
    assert abs(fitted_mean) < 1e-6 and abs(fitted_std - 1) < 1e-6
    source_verified = 0
    if verify_source:
        source_checksums = pd.read_csv(output / 'source_waveform_checksums.csv')
        for row in source_checksums.itertuples():
            assert sha256(source / row.path) == row.sha256, f'source changed: {row.path}'
            source_verified += 1
        for name, digest in summary['source_metadata_sha256'].items():
            assert sha256(source / name) == digest, f'source metadata changed: {name}'
    paths = sorted(p for p in output.rglob('*') if p.is_file() and p.name not in
                   {'artifacts_sha256.json', 'verification.json', 'processing.log'})
    checksums = {p.relative_to(output).as_posix(): {'sha256': sha256(p), 'bytes': p.stat().st_size} for p in paths}
    write_json(output / 'artifacts_sha256.json', checksums)
    return {'passed': True, 'records': n, 'augmented_records': len(xa), 'shape': list(x.shape),
            'patient_overlap_counts': overlaps, 'normalization_train_mean': fitted_mean,
            'normalization_train_std': fitted_std, 'all_array_values_finite': True,
            'all_augmented_records_reproduced_exactly': True, 'source_waveform_files_unchanged': source_verified,
            'source_metadata_unchanged': bool(verify_source), 'output_files_hashed': len(checksums)}


class PipelineTests(unittest.TestCase):
    def test_shift_is_synchronous_and_not_circular(self):
        x = np.tile(np.arange(20, dtype=np.float32), (12, 1))
        right, left = shift_signal(x, 3), shift_signal(x, -3)
        np.testing.assert_array_equal(right[:, 3:], x[:, :-3])
        np.testing.assert_array_equal(left[:, :-3], x[:, 3:])
        np.testing.assert_array_equal(right[:, 0], np.full(12, 3))
        np.testing.assert_array_equal(left[:, -1], np.full(12, 16))

    def test_noise_reproducible_and_constant_lead_preserved(self):
        x = np.tile(np.sin(np.linspace(0, 20, 1000)), (12, 1)).astype(np.float32)
        x[4] = 2
        a, shift = augment(x, 123)
        b, shift2 = augment(x, 123)
        np.testing.assert_array_equal(a, b)
        self.assertEqual(shift, shift2)
        np.testing.assert_array_equal(a[4], x[4])
        self.assertFalse(np.array_equal(a, x))

    def test_lowpass_reduces_high_frequency_and_preserves_low_frequency(self):
        t = np.arange(1000) / 100
        low, high = np.sin(2 * np.pi * 5 * t), np.sin(2 * np.pi * 47 * t)
        low_out, _ = preprocess(np.tile(low, (12, 1)).astype(np.float32))
        high_out, _ = preprocess(np.tile(high, (12, 1)).astype(np.float32))
        self.assertLess(float(high_out[:, 100:-100].std()), .05)
        np.testing.assert_allclose(low_out[:, 100:-100], np.tile(low[100:-100], (12, 1)), atol=.001)

    def test_flat_leads_are_flagged_and_not_fabricated(self):
        x = np.full((12, 1000), 2.5, dtype=np.float32)
        filtered, flags = preprocess(x)
        self.assertTrue(flags.all())
        np.testing.assert_array_equal(filtered, x)

    def test_multilabel_mapping_and_official_splits(self):
        result = label_names("{'IMI': 100, 'LBBB': 100, 'OTHER': 10}", {'IMI': 'MI', 'LBBB': 'CD'})
        self.assertEqual(result, ['MI', 'CD'])
        self.assertEqual(label_names("{'OTHER': 100}", {}), [])
        self.assertEqual([split_name(f) for f in [1, 8, 9, 10]], ['train', 'train', 'validation', 'test'])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, default=DEFAULT_SOURCE)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(PipelineTests)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        sys.exit(0 if result.wasSuccessful() else 1)
    if args.verify:
        result = verify(args.output, args.source)
        write_json(args.output / 'verification.json', result)
        print(json.dumps(result, indent=2))
    else:
        build(args.source, args.output)


if __name__ == '__main__':
    main()
