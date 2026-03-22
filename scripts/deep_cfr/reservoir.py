"""
Reservoir buffer for SD-CFR advantage samples.
Fixed-size buffer with reservoir sampling — guarantees uniform sampling of all
items seen so far regardless of stream length.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

import numpy as np
import torch


@dataclass
class AdvantageSample:
    """One advantage sample: state features + advantage values for each action."""
    state: np.ndarray          # encoded state vector (float32)
    advantages: np.ndarray     # advantage per action slot (float32, padded to max_actions)
    legal_mask: np.ndarray     # 1.0 for legal actions, 0.0 otherwise (float32)
    iteration: int             # which CFR iteration produced this


class ReservoirBuffer:
    """Fixed-size reservoir buffer with weighted sampling for training."""

    def __init__(self, max_size: int = 40_000_000):
        self.max_size = max_size
        self.buffer: list[AdvantageSample] = []
        self.n_seen = 0
        self._max_iteration = 0

    def add(self, sample: AdvantageSample) -> None:
        self.n_seen += 1
        if sample.iteration > self._max_iteration:
            self._max_iteration = sample.iteration
        if len(self.buffer) < self.max_size:
            self.buffer.append(sample)
        else:
            idx = random.randint(0, self.n_seen - 1)
            if idx < self.max_size:
                self.buffer[idx] = sample

    def __len__(self) -> int:
        return len(self.buffer)

    def sample_batch(self, batch_size: int, device: torch.device) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Sample a random mini-batch.
        Returns: (states, advantages, legal_masks, weights) all as tensors on `device`.
        Weights are Linear CFR weights: iteration / max_iteration_seen.
        """
        indices = random.sample(range(len(self.buffer)), min(batch_size, len(self.buffer)))
        max_iter = max(self._max_iteration, 1)

        states = np.stack([self.buffer[i].state for i in indices])
        advs = np.stack([self.buffer[i].advantages for i in indices])
        masks = np.stack([self.buffer[i].legal_mask for i in indices])
        weights = np.array([self.buffer[i].iteration / max_iter for i in indices], dtype=np.float32)

        return (
            torch.from_numpy(states).to(device),
            torch.from_numpy(advs).to(device),
            torch.from_numpy(masks).to(device),
            torch.from_numpy(weights).to(device),
        )

    def clear(self) -> None:
        self.buffer.clear()
        self.n_seen = 0
