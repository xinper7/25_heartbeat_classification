"""Wang ResNet1D inference definition, matching the supplied checkpoint keys.

Adapted from helme/ecg_ptbxl_benchmarking models/resnet1d.py and basic_conv1d.py
(GPL-3.0). Training/fastai dependencies are intentionally absent.
"""

import torch
from torch import nn


class BasicBlock1d(nn.Module):
    def __init__(self, stride=1):
        super().__init__()
        self.conv1 = nn.Conv1d(128, 128, 5, stride, 2, bias=False)
        self.bn1 = nn.BatchNorm1d(128)
        self.relu = nn.ReLU(inplace=True)
        self.conv2 = nn.Conv1d(128, 128, 3, 1, 1, bias=False)
        self.bn2 = nn.BatchNorm1d(128)
        self.downsample = (
            nn.Sequential(
                nn.Conv1d(128, 128, 1, stride, bias=False), nn.BatchNorm1d(128)
            )
            if stride != 1
            else None
        )

    def forward(self, x):
        residual = x if self.downsample is None else self.downsample(x)
        return self.relu(
            self.bn2(self.conv2(self.relu(self.bn1(self.conv1(x))))) + residual
        )


class ConcatPool(nn.Module):
    def forward(self, x):
        return torch.cat(
            (torch.amax(x, dim=-1, keepdim=True), torch.mean(x, dim=-1, keepdim=True)),
            1,
        )


def make_signal_model():
    head = nn.Sequential(
        ConcatPool(),
        nn.Flatten(),
        nn.BatchNorm1d(256),
        nn.Dropout(0.25),
        nn.Linear(256, 128),
        nn.ReLU(inplace=True),
        nn.BatchNorm1d(128),
        nn.Dropout(0.5),
        nn.Linear(128, 5),
    )
    return nn.Sequential(
        nn.Conv1d(12, 128, 7, 1, 3, bias=False),
        nn.BatchNorm1d(128),
        nn.ReLU(inplace=True),
        nn.Sequential(BasicBlock1d()),
        nn.Sequential(BasicBlock1d(2)),
        nn.Sequential(BasicBlock1d(2)),
        head,
    )
