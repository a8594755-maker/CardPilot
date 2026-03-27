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
    sizing_target: float = -1.0  # sizing regression target [0,1], -1 = no target


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

    def sample_batch(self, batch_size: int, device: torch.device) -> tuple[
        torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor
    ]:
        """
        Sample a random mini-batch.
        Returns: (states, advantages, legal_masks, weights, sizing_targets) on `device`.
        Weights are Linear CFR weights: iteration / max_iteration_seen.
        sizing_targets: (batch,) float, -1.0 = no target.
        """
        indices = random.sample(range(len(self.buffer)), min(batch_size, len(self.buffer)))
        max_iter = max(self._max_iteration, 1)

        states = np.stack([self.buffer[i].state for i in indices])
        advs = np.stack([self.buffer[i].advantages for i in indices])
        masks = np.stack([self.buffer[i].legal_mask for i in indices])
        # DCFR discounting: t^alpha / (t^alpha + 1), alpha=1.5
        # Better than linear weighting — emphasizes later iterations more aggressively
        alpha = 1.5
        weights = np.array([
            (self.buffer[i].iteration ** alpha) / (self.buffer[i].iteration ** alpha + 1)
            for i in indices
        ], dtype=np.float32)
        sizing = np.array([self.buffer[i].sizing_target for i in indices], dtype=np.float32)

        return (
            torch.from_numpy(states).to(device),
            torch.from_numpy(advs).to(device),
            torch.from_numpy(masks).to(device),
            torch.from_numpy(weights).to(device),
            torch.from_numpy(sizing).to(device),
        )

    def clear(self) -> None:
        self.buffer.clear()
        self.n_seen = 0


# ---------- Policy buffer for average strategy training ----------

class PolicySample:
    """One strategy sample: state features + regret-matched strategy."""
    __slots__ = ('state', 'strategy', 'legal_mask', 'iteration')

    def __init__(self, state: np.ndarray, strategy: np.ndarray,
                 legal_mask: np.ndarray, iteration: int):
        self.state = state
        self.strategy = strategy
        self.legal_mask = legal_mask
        self.iteration = iteration


class PolicyBuffer:
    """Reservoir buffer for (state, strategy) pairs for policy network training."""

    def __init__(self, max_size: int = 2_000_000):
        self.max_size = max_size
        self.buffer: list[PolicySample] = []
        self.n_seen = 0
        self._max_iteration = 0

    def add(self, sample: PolicySample) -> None:
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

    def sample_batch(self, batch_size: int, device: torch.device) -> tuple[
        torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor
    ]:
        """Returns: (states, strategies, legal_masks, weights) on device."""
        indices = random.sample(range(len(self.buffer)), min(batch_size, len(self.buffer)))
        max_iter = max(self._max_iteration, 1)

        states = np.stack([self.buffer[i].state for i in indices])
        strategies = np.stack([self.buffer[i].strategy for i in indices])
        masks = np.stack([self.buffer[i].legal_mask for i in indices])
        weights = np.array([self.buffer[i].iteration / max_iter for i in indices], dtype=np.float32)

        return (
            torch.from_numpy(states).to(device),
            torch.from_numpy(strategies).to(device),
            torch.from_numpy(masks).to(device),
            torch.from_numpy(weights).to(device),
        )
