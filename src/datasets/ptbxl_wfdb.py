"""Memory-efficient WFDB Dataset, usable with torch DataLoader without fastai.

Does not import torch or write files. Signals are [12,1000], labels float32[5].
"""
import json
import operator
from pathlib import Path

import numpy as np
import pandas as pd


def read_record(record):
    record = Path(record)
    if record.suffix.lower() in ('.hea', '.dat'):
        record = record.with_suffix('')
    lines = record.with_suffix('.hea').read_text(encoding='utf-8').splitlines()
    parts = [line.split() for line in lines if line.strip() and not line.startswith('#')]
    if len(parts) != 13 or parts[0] != [record.name, '12', '100', '1000']:
        raise ValueError('expected one 12-lead, 100-Hz, 1000-sample exported record')
    leads = ['I', 'II', 'III', 'AVR', 'AVL', 'AVF', 'V1', 'V2', 'V3', 'V4', 'V5', 'V6']
    for row, lead in zip(parts[1:], leads):
        if row[0] != record.name + '.dat' or row[1:5] != ['16', '1000.0(0)/mV', '16', '0'] or row[-1] != lead:
            raise ValueError('header does not match this exported dataset protocol')
    content = record.with_suffix('.dat').read_bytes()
    if len(content) != 24000:
        raise ValueError('wrong waveform byte count')
    digital = np.frombuffer(content, dtype='<i2').reshape(1000, 12)
    if (digital == -32768).any():
        raise ValueError('missing-value sentinel in waveform')
    return np.ascontiguousarray(digital.T.astype(np.float32) / np.float32(1000))


class PTBXLWFDBDataset:
    def __init__(self, root=None, split='train', include_augmented=False, normalize=True):
        self.root = (Path(root) if root else
                     Path(__file__).resolve().parents[2] / 'data' / 'processed' / 'ptbxl_wfdb_v1')
        if split not in ('train', 'validation', 'test'):
            raise ValueError('split must be train, validation, or test')
        if include_augmented and split != 'train':
            raise ValueError('augmentation is only allowed for training')
        self.config = json.loads((self.root / 'processing_config.json').read_text(encoding='utf-8'))
        self.classes = tuple(self.config['classes'])
        self.leads = tuple(self.config['leads'])
        frame = pd.read_csv(self.root / 'export_manifest.csv')
        groups = [split, 'train_augmented'] if include_augmented else [split]
        selected = frame.loc[frame.purpose.isin(groups)]
        self.paths = selected.filename_lr.tolist()
        self.labels = selected[[f'y_{c}' for c in self.classes]].to_numpy(dtype=np.float32)
        self.ecg_ids = selected.ecg_id.to_numpy(dtype=np.int64)
        self.augmented = selected.variant.eq('augmented').to_numpy()
        self.normalize = normalize
        stats = json.loads((self.root / 'normalization.json').read_text(encoding='utf-8'))
        self.mean_mv, self.std_mv = float(stats['mean_mv']), float(stats['std_mv'])

    def __len__(self):
        return len(self.paths)

    def __getitem__(self, index):
        index = operator.index(index)
        if index < 0:
            index += len(self)
        if not 0 <= index < len(self):
            raise IndexError(index)
        signal = read_record(self.root / self.paths[index])
        if self.normalize:
            signal = ((signal.astype(np.float64) - self.mean_mv) / self.std_mv).astype(np.float32)
        return {'signal': signal, 'label': self.labels[index].copy(),
                'ecg_id': int(self.ecg_ids[index]), 'augmented': bool(self.augmented[index])}
