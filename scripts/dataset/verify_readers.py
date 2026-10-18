"""Read-only independent checks of an exported WFDB dataset, without training."""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import wfdb

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from src.datasets.ptbxl_wfdb import PTBXLWFDBDataset, read_record
from src.inference.ptbxl import read_ptbxl_record, read_wfdb_record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=PROJECT_ROOT / 'data' / 'processed' / 'ptbxl_wfdb_v1')
    args = parser.parse_args()
    root = args.root.resolve()
    frame = pd.read_csv(root / 'export_manifest.csv')
    checked = []
    for group in ['train', 'validation', 'test', 'train_augmented']:
        subset = frame.loc[frame.purpose.eq(group)].reset_index(drop=True)
        if subset.empty:
            raise ValueError(f'empty purpose group: {group}')
        for index in sorted({0, len(subset) // 2, len(subset) - 1}):
            row = subset.iloc[index]
            path = root / row.filename_lr
            native = wfdb.rdrecord(str(path))
            expected = read_record(path)
            assert (native.fs, native.n_sig, native.sig_len) == (100, 12, 1000)
            assert native.units == ['mV'] * 12
            np.testing.assert_allclose(native.p_signal.T, expected, atol=2e-6, rtol=0)
            np.testing.assert_array_equal(read_wfdb_record(path), expected)
            np.testing.assert_array_equal(read_ptbxl_record(root / group, int(row.ecg_id)), expected)
            if group != 'train_augmented':
                np.testing.assert_array_equal(read_ptbxl_record(root, int(row.ecg_id)), expected)
            checked.append({'purpose': group, 'ecg_id': int(row.ecg_id)})
    counts = {name: len(PTBXLWFDBDataset(root, name)) for name in ['train', 'validation', 'test']}
    base = PTBXLWFDBDataset(root, 'train')
    combined = PTBXLWFDBDataset(root, 'train', include_augmented=True)
    assert len(combined) == 2 * len(base)
    batches = {}
    if importlib.util.find_spec('torch'):
        import torch
        from torch.utils.data import DataLoader, Subset
        groups = [('train', base), ('train_augmented', Subset(combined, range(len(base), min(len(base) + 8, len(combined))))),
                  ('validation', PTBXLWFDBDataset(root, 'validation')), ('test', PTBXLWFDBDataset(root, 'test'))]
        for name, dataset in groups:
            batch = next(iter(DataLoader(dataset, batch_size=8, shuffle=False, num_workers=0)))
            assert batch['signal'].shape[1:] == (12, 1000) and batch['label'].shape[1:] == (5,)
            assert batch['signal'].dtype == batch['label'].dtype == torch.float32
            assert torch.isfinite(batch['signal']).all()
            assert ((batch['label'] == 0) | (batch['label'] == 1)).all()
            assert batch['label'].any(dim=1).all()
            if name == 'train_augmented':
                assert batch['augmented'].all()
            else:
                assert not batch['augmented'].any()
            batches[name] = {'signal_shape': list(batch['signal'].shape), 'label_shape': list(batch['label'].shape)}
    try:
        PTBXLWFDBDataset(root, 'test', include_augmented=True)
    except ValueError:
        pass
    else:
        raise AssertionError('test augmentation must be rejected')
    print(json.dumps({'passed': True, 'representative_records_checked': checked, 'base_split_counts': counts,
                      'combined_train_records': len(combined), 'pytorch_batches': batches,
                      'model_training_performed': False, 'files_modified': False}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
