"""
train_river_ev.py

Train a ResNet-style MLP to predict river CFVs (counterfactual values) for both
players given turn-level board + ranges. Replaces the 48-river-subtree CFR solve
with a <10ms neural network inference.

Usage:
    python train_river_ev.py \
        --data-dir EZ-GTO/data/nn-training \
        --output-dir checkpoints/river_ev_v1

    # V2 (larger model, cosine-restart schedule, augmentation):
    python train_river_ev.py \
        --data-dir EZ-GTO/data/nn-training \
        --output-dir checkpoints/river_ev_v2 \
        --hidden-dim 4096 --num-blocks 6 \
        --lr-schedule cosine-restart \
        --augment-prob 0.25 \
        --weight-by-reach

Architecture:
    Input  (2863):  board_onehot (208) + pot_feats (3) + oop_reach (1326) + ip_reach (1326)
    Hidden (2048x4 residual blocks)  [V2: 4096x6]
    Output (2652):  cfv_oop_norm (1326) + cfv_ip_norm (1326)

    CFVs are normalised by effectiveStack during training and must be
    denormalised (x effectiveStack) at inference time.
"""

import sys
import os
import math
import argparse
import time
import itertools
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, random_split

# ─── Import data loader from sibling file ───────────────────────────────────

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from load_training_data import RiverValueDataset, load_chunk, NUM_COMBOS

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

# ─── Constants ───────────────────────────────────────────────────────────────

INPUT_DIM  = 208 + 3 + NUM_COMBOS + NUM_COMBOS  # 2863
OUTPUT_DIM = NUM_COMBOS + NUM_COMBOS             # 2652
BOARD_DIM  = 208   # 4 cards x 52 one-hot
POT_DIM    = 3
NUM_SUITS  = 4
NUM_RANKS  = 13
NUM_CARDS  = 52

# ─── Hand class mapping (169 classes) ────────────────────────────────────────
# Maps each of the 1326 holdem combo indices to one of 169 hand classes.
# Class encoding: pairs (13), suited (78), offsuit (78) = 169 total.
# Combo index k corresponds to cards (c1, c2) where c1 < c2, enumerated as:
#   k = c1 * (2*52 - c1 - 1) // 2 + (c2 - c1 - 1)

def _build_combo_to_cards() -> np.ndarray:
    """Return (1326, 2) array mapping combo index -> (card1, card2)."""
    pairs = np.zeros((NUM_COMBOS, 2), dtype=np.int32)
    k = 0
    for c1 in range(NUM_CARDS):
        for c2 in range(c1 + 1, NUM_CARDS):
            pairs[k, 0] = c1
            pairs[k, 1] = c2
            k += 1
    return pairs

COMBO_TO_CARDS = _build_combo_to_cards()  # (1326, 2)


def _build_hand_class_map() -> np.ndarray:
    """
    Return (1326,) int array mapping combo index to hand class [0..168].

    Class layout:
        0..12   : pocket pairs (22..AA) — rank index 0..12
        13..90  : suited combos (higher_rank, lower_rank), 78 entries
        91..168 : offsuit combos (higher_rank, lower_rank), 78 entries
    """
    classes = np.zeros(NUM_COMBOS, dtype=np.int32)
    for k in range(NUM_COMBOS):
        c1, c2 = COMBO_TO_CARDS[k]
        r1, s1 = c1 // NUM_SUITS, c1 % NUM_SUITS
        r2, s2 = c2 // NUM_SUITS, c2 % NUM_SUITS
        hi, lo = max(r1, r2), min(r1, r2)
        if r1 == r2:
            # Pair
            classes[k] = hi
        elif s1 == s2:
            # Suited — 13 + triangular index
            # There are C(13,2) = 78 suited combos, indexed by (hi, lo) where hi > lo
            idx = hi * (hi - 1) // 2 + lo
            classes[k] = 13 + idx
        else:
            # Offsuit
            idx = hi * (hi - 1) // 2 + lo
            classes[k] = 13 + 78 + idx
    return classes

HAND_CLASS_MAP = _build_hand_class_map()  # (1326,) -> [0..168]
NUM_HAND_CLASSES = 169

# Precompute a name for each hand class for logging
def _hand_class_names() -> List[str]:
    rank_chars = "23456789TJQKA"
    names = []
    # Pairs
    for r in range(NUM_RANKS):
        names.append(f"{rank_chars[r]}{rank_chars[r]}")
    # Suited
    for hi in range(1, NUM_RANKS):
        for lo in range(hi):
            names.append(f"{rank_chars[hi]}{rank_chars[lo]}s")
    # Offsuit
    for hi in range(1, NUM_RANKS):
        for lo in range(hi):
            names.append(f"{rank_chars[hi]}{rank_chars[lo]}o")
    return names

HAND_CLASS_NAMES = _hand_class_names()


# ─── Suit-isomorphic augmentation ────────────────────────────────────────────

def _build_cards_to_combo() -> np.ndarray:
    """Return (52, 52) int array; cards_to_combo[c1][c2] = combo index (c1 < c2)."""
    lut = np.full((NUM_CARDS, NUM_CARDS), -1, dtype=np.int32)
    k = 0
    for c1 in range(NUM_CARDS):
        for c2 in range(c1 + 1, NUM_CARDS):
            lut[c1, c2] = k
            lut[c2, c1] = k
            k += 1
    return lut

CARDS_TO_COMBO = _build_cards_to_combo()  # (52, 52)

# All 24 permutations of 4 suits
ALL_SUIT_PERMS = list(itertools.permutations(range(NUM_SUITS)))


def _apply_suit_perm_to_card(card: int, perm: Tuple[int, ...]) -> int:
    """Apply a suit permutation to a single card index."""
    rank = card // NUM_SUITS
    suit = card % NUM_SUITS
    return rank * NUM_SUITS + perm[suit]


def _build_combo_remap_table(perm: Tuple[int, ...]) -> np.ndarray:
    """
    For a given suit permutation, return a (1326,) int array that maps
    old combo index -> new combo index.
    """
    remap = np.zeros(NUM_COMBOS, dtype=np.int32)
    for k in range(NUM_COMBOS):
        c1, c2 = COMBO_TO_CARDS[k]
        new_c1 = _apply_suit_perm_to_card(c1, perm)
        new_c2 = _apply_suit_perm_to_card(c2, perm)
        lo, hi = min(new_c1, new_c2), max(new_c1, new_c2)
        remap[k] = CARDS_TO_COMBO[lo, hi]
    return remap


# Precompute remap tables for all 24 suit permutations (skip identity)
_COMBO_REMAP_TABLES = []
_NON_IDENTITY_PERMS = []
for perm in ALL_SUIT_PERMS:
    if perm == (0, 1, 2, 3):
        continue  # skip identity
    _NON_IDENTITY_PERMS.append(perm)
    _COMBO_REMAP_TABLES.append(_build_combo_remap_table(perm))


class SuitAugmentation:
    """
    Suit-isomorphic data augmentation for poker training samples.

    With probability `prob`, applies a random non-identity suit permutation to
    the board card encoding. Since reach probabilities and EV values are
    suit-isomorphic, this only changes the board one-hot encoding and the
    ordering of combo-indexed arrays (reach, CFV).

    This transform operates on individual samples (not batches).
    """

    def __init__(self, prob: float = 0.25):
        self.prob = prob
        self.num_perms = len(_NON_IDENTITY_PERMS)

    def __call__(self, sample: Dict[str, torch.Tensor]) -> Dict[str, torch.Tensor]:
        if np.random.random() >= self.prob:
            return sample

        # Pick a random non-identity suit permutation
        idx = np.random.randint(self.num_perms)
        perm = _NON_IDENTITY_PERMS[idx]
        combo_remap = _COMBO_REMAP_TABLES[idx]

        # Permute board cards
        flop = sample["flop_board"].numpy()  # (3,)
        turn = sample["turn_card"].item()

        new_flop = np.array([_apply_suit_perm_to_card(int(c), perm) for c in flop],
                            dtype=np.int64)
        new_turn = _apply_suit_perm_to_card(turn, perm)

        sample["flop_board"] = torch.from_numpy(new_flop).long()
        sample["turn_card"]  = torch.tensor(new_turn, dtype=torch.long)

        # Remap reach and CFV arrays: new[combo_remap[k]] = old[k]
        # Equivalently: new[new_idx] = old[old_idx] where new_idx = combo_remap[old_idx]
        for key in ("oop_reach", "ip_reach", "cfv_oop", "cfv_ip"):
            old_arr = sample[key].numpy()
            new_arr = np.zeros_like(old_arr)
            new_arr[combo_remap] = old_arr
            sample[key] = torch.from_numpy(new_arr)

        return sample


# ─── Fast chunk loader (vectorised, avoids Python loop) ─────────────────────

INTS_FIELDS   = 4
FLOAT_FIELDS  = 3
FLOAT_ARRAYS  = 4
RECORD_BYTES  = INTS_FIELDS * 4 + FLOAT_FIELDS * 4 + FLOAT_ARRAYS * NUM_COMBOS * 4
HEADER_BYTES  = 16
MAGIC         = 0x4E4E5652


def fast_load_chunk(filepath: str) -> Dict[str, np.ndarray]:
    """Vectorised binary loader — ~10x faster than the reference Python-loop version."""
    with open(filepath, "rb") as f:
        import struct
        header = f.read(HEADER_BYTES)
        magic, _version, declared_samples, _reserved = struct.unpack("<4I", header)
        if magic != MAGIC:
            raise ValueError(f"Invalid magic: 0x{magic:08X}")
        raw = f.read()

    actual_samples = len(raw) // RECORD_BYTES
    if actual_samples < declared_samples:
        print(f"  Warning: declared {declared_samples} samples but only {actual_samples} complete records found")
    n = actual_samples
    raw = raw[:n * RECORD_BYTES]

    # Interpret the raw bytes as a (n, RECORD_BYTES) uint8 view, then slice typed views
    buf = np.frombuffer(raw, dtype=np.uint8).reshape(n, RECORD_BYTES)

    def _ints(col_byte, count):
        return np.frombuffer(buf[:, col_byte:col_byte + count * 4].tobytes(), dtype=np.int32).reshape(n, count)

    def _floats(col_byte, count):
        return np.frombuffer(buf[:, col_byte:col_byte + count * 4].tobytes(), dtype=np.float32).reshape(n, count)

    cards     = _ints(0, 4)           # (n, 4) — flop[3] + turn
    pot_raw   = _floats(16, 3)        # (n, 3) — potOffset, startingPot, effectiveStack
    reach_cfv = _floats(28, 4 * NUM_COMBOS)  # (n, 4*1326)

    return {
        "num_samples":      n,
        "flop_boards":      cards[:, :3].copy(),
        "turn_cards":       cards[:, 3].copy(),
        "pot_offsets":      pot_raw[:, 0].copy(),
        "starting_pots":    pot_raw[:, 1].copy(),
        "effective_stacks": pot_raw[:, 2].copy(),
        "oop_reach":        reach_cfv[:, 0*NUM_COMBOS:1*NUM_COMBOS].copy(),
        "ip_reach":         reach_cfv[:, 1*NUM_COMBOS:2*NUM_COMBOS].copy(),
        "cfv_oop":          reach_cfv[:, 2*NUM_COMBOS:3*NUM_COMBOS].copy(),
        "cfv_ip":           reach_cfv[:, 3*NUM_COMBOS:4*NUM_COMBOS].copy(),
    }


class FastRiverValueDataset(torch.utils.data.Dataset):
    """Like RiverValueDataset but uses vectorised loading."""

    def __init__(self, directory: str, transform=None):
        from pathlib import Path
        import struct
        dirpath = Path(directory)
        files = sorted(dirpath.glob("chunk_*.bin"))
        if not files:
            raise FileNotFoundError(f"No chunk_*.bin files in {directory}")
        print(f"Loading {len(files)} chunk(s) from {directory} ...")
        t0 = time.time()
        chunks = [fast_load_chunk(str(f)) for f in files]
        n = sum(c["num_samples"] for c in chunks)
        print(f"  {n:,} samples loaded in {time.time()-t0:.1f}s")

        def _cat(key):
            return np.concatenate([c[key] for c in chunks], axis=0)

        self.flop_boards      = _cat("flop_boards")       # (n, 3) int32
        self.turn_cards       = _cat("turn_cards")        # (n,)   int32
        self.pot_offsets      = _cat("pot_offsets")       # (n,)   float32
        self.starting_pots    = _cat("starting_pots")     # (n,)   float32
        self.effective_stacks = _cat("effective_stacks")  # (n,)   float32
        self.oop_reach        = _cat("oop_reach")         # (n, 1326) float32
        self.ip_reach         = _cat("ip_reach")          # (n, 1326) float32
        self.cfv_oop          = _cat("cfv_oop")           # (n, 1326) float32
        self.cfv_ip           = _cat("cfv_ip")            # (n, 1326) float32
        self.n = n
        self.transform = transform

    def __len__(self) -> int:
        return self.n

    def __getitem__(self, idx):
        sample = {
            "flop_board":      torch.from_numpy(self.flop_boards[idx].copy()).long(),
            "turn_card":       torch.tensor(int(self.turn_cards[idx]), dtype=torch.long),
            "pot_offset":      torch.tensor(float(self.pot_offsets[idx]),      dtype=torch.float32),
            "starting_pot":    torch.tensor(float(self.starting_pots[idx]),    dtype=torch.float32),
            "effective_stack": torch.tensor(float(self.effective_stacks[idx]), dtype=torch.float32),
            "oop_reach":       torch.from_numpy(self.oop_reach[idx].copy()),
            "ip_reach":        torch.from_numpy(self.ip_reach[idx].copy()),
            "cfv_oop":         torch.from_numpy(self.cfv_oop[idx].copy()),
            "cfv_ip":          torch.from_numpy(self.cfv_ip[idx].copy()),
        }
        if self.transform:
            sample = self.transform(sample)
        return sample


# ─── Feature engineering ─────────────────────────────────────────────────────

def build_features(batch: Dict[str, torch.Tensor], device: torch.device) -> torch.Tensor:
    """
    Encode a batch dict into a (B, 2863) float32 feature tensor.

    Board encoding (208 dims):
        4 cards (flop[0], flop[1], flop[2], turn) each one-hot over 52 card indices.
        Card index convention: rank = card // 4 (0=2 ... 12=A), suit = card % 4.

    Pot geometry (3 dims):
        [potOffset/es, startingPot/es, es/200.0]
        All three are bounded ~ [0, 1] for typical game states.

    Reach vectors (1326+1326 dims):
        Raw reach probabilities (not renormalised) — same scale as training data.
    """
    flop  = batch["flop_board"].to(device)       # (B, 3) int64
    turn  = batch["turn_card"].to(device)         # (B,)   int64
    es    = batch["effective_stack"].to(device)   # (B,)   float32
    oop_r = batch["oop_reach"].to(device)         # (B, 1326)
    ip_r  = batch["ip_reach"].to(device)          # (B, 1326)

    # Board one-hot: (B, 4, 52) -> (B, 208)
    cards = torch.cat([flop, turn.unsqueeze(1)], dim=1)  # (B, 4)
    board_oh = F.one_hot(cards, num_classes=52).float()  # (B, 4, 52)
    board_flat = board_oh.view(board_oh.size(0), -1)     # (B, 208)

    # Pot geometry
    es_safe = es.clamp(min=1e-6)
    pot_feats = torch.stack([
        batch["pot_offset"].to(device) / es_safe,
        batch["starting_pot"].to(device) / es_safe,
        es_safe / 200.0,
    ], dim=1)  # (B, 3)

    x = torch.cat([board_flat, pot_feats, oop_r, ip_r], dim=1)  # (B, 2863)
    return x


def build_targets(batch: Dict[str, torch.Tensor], device: torch.device
                  ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """
    Returns (cfv_oop_norm, cfv_ip_norm, effective_stack) each normalised by es.
    Both target tensors are (B, 1326) float32.
    """
    es     = batch["effective_stack"].to(device)  # (B,)
    es_safe = es.clamp(min=1e-6).unsqueeze(1)     # (B, 1)
    cfv_oop = batch["cfv_oop"].to(device) / es_safe   # (B, 1326)
    cfv_ip  = batch["cfv_ip"].to(device)  / es_safe   # (B, 1326)
    return cfv_oop, cfv_ip, es


# ─── Model ───────────────────────────────────────────────────────────────────

class ResidualBlock(nn.Module):
    """Pre-LN residual block: LN -> Linear -> GELU -> LN -> Linear -> (+residual) -> GELU"""

    def __init__(self, dim: int):
        super().__init__()
        self.ln1    = nn.LayerNorm(dim)
        self.lin1   = nn.Linear(dim, dim)
        self.ln2    = nn.LayerNorm(dim)
        self.lin2   = nn.Linear(dim, dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        h = self.lin1(F.gelu(self.ln1(x)))
        h = self.lin2(F.gelu(self.ln2(h)))
        return x + h


class RiverEVNet(nn.Module):
    """
    ResNet-style MLP that maps (board, pot, ranges) -> (cfv_oop_norm, cfv_ip_norm).

    input_dim  = 2863   (208 board + 3 pot + 1326 oop_reach + 1326 ip_reach)
    output_dim = 2652   (1326 cfv_oop + 1326 cfv_ip, both / effectiveStack)
    """

    def __init__(self, hidden_dim: int = 2048, num_blocks: int = 4,
                 input_dim: int = INPUT_DIM, output_dim: int = OUTPUT_DIM):
        super().__init__()
        self.input_dim  = input_dim
        self.output_dim = output_dim
        self.hidden_dim = hidden_dim
        self.num_blocks = num_blocks

        self.input_proj = nn.Linear(input_dim, hidden_dim)
        self.input_ln   = nn.LayerNorm(hidden_dim)
        self.blocks     = nn.ModuleList([ResidualBlock(hidden_dim) for _ in range(num_blocks)])
        self.output_proj = nn.Linear(hidden_dim, output_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: (B, input_dim) -> out: (B, output_dim)"""
        h = F.gelu(self.input_ln(self.input_proj(x)))
        for block in self.blocks:
            h = block(h)
        return self.output_proj(h)

    def split_output(self, out: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """Split (B, 2652) -> (cfv_oop_norm (B,1326), cfv_ip_norm (B,1326))"""
        return out[:, :NUM_COMBOS], out[:, NUM_COMBOS:]

    @property
    def num_parameters(self) -> int:
        return sum(p.numel() for p in self.parameters() if p.requires_grad)


# ─── Loss ────────────────────────────────────────────────────────────────────

def masked_huber_loss(
    pred_oop: torch.Tensor,
    pred_ip:  torch.Tensor,
    tgt_oop:  torch.Tensor,
    tgt_ip:   torch.Tensor,
    oop_reach: torch.Tensor,
    ip_reach:  torch.Tensor,
    delta: float = 1.0,
    weight_by_reach: bool = False,
) -> torch.Tensor:
    """
    Huber loss only on combos where at least one player has reach > 1e-6.
    All inputs are (B, 1326). Returns a scalar loss.

    If weight_by_reach=True, each combo's loss contribution is weighted by
    sqrt(max(oop_reach, ip_reach)) so high-reach combos matter more.
    """
    mask = ((oop_reach > 1e-6) | (ip_reach > 1e-6)).float()  # (B, 1326)

    loss_oop = F.huber_loss(pred_oop, tgt_oop, reduction="none", delta=delta)  # (B, 1326)
    loss_ip  = F.huber_loss(pred_ip,  tgt_ip,  reduction="none", delta=delta)  # (B, 1326)

    per_combo_loss = (loss_oop + loss_ip) * mask  # (B, 1326)

    if weight_by_reach:
        # Weight by sqrt of the max reach across both players
        reach_weight = torch.sqrt(torch.max(oop_reach, ip_reach).clamp(min=0.0))  # (B, 1326)
        per_combo_loss = per_combo_loss * reach_weight
        # Normalise by sum of weights (not count)
        weight_sum = (reach_weight * mask).sum().clamp(min=1e-8)
        return per_combo_loss.sum() / weight_sum
    else:
        n_active = mask.sum().clamp(min=1.0)
        return per_combo_loss.sum() / n_active


# ─── Evaluation ──────────────────────────────────────────────────────────────

@torch.no_grad()
def evaluate(
    model:  RiverEVNet,
    loader: DataLoader,
    device: torch.device,
    delta:  float = 1.0,
    use_amp: bool = False,
    amp_dtype: torch.dtype = torch.bfloat16,
    weight_by_reach: bool = False,
) -> float:
    model.eval()
    total_loss = 0.0
    n_batches  = 0

    for batch in loader:
        oop_r = batch["oop_reach"].to(device)
        ip_r  = batch["ip_reach"].to(device)

        with torch.amp.autocast(device_type=device.type, dtype=amp_dtype, enabled=use_amp):
            x = build_features(batch, device)
            out = model(x)
            pred_oop, pred_ip = model.split_output(out)
            tgt_oop, tgt_ip, _ = build_targets(batch, device)
            loss = masked_huber_loss(pred_oop, pred_ip, tgt_oop, tgt_ip,
                                     oop_r, ip_r, delta, weight_by_reach)

        total_loss += loss.item()
        n_batches  += 1

    return total_loss / max(n_batches, 1)


@torch.no_grad()
def evaluate_per_hand_class(
    model:  RiverEVNet,
    loader: DataLoader,
    device: torch.device,
    use_amp: bool = False,
    amp_dtype: torch.dtype = torch.bfloat16,
) -> Tuple[float, Dict[int, float]]:
    """
    Compute per-hand-class MAE on the validation set.

    Returns:
        mean_class_mae: Mean of per-class MAE values across all 169 hand classes
                        (only classes with at least one active combo are included).
        class_maes:     Dict mapping hand class index -> MAE for that class.
    """
    model.eval()

    # Accumulators per hand class: sum of absolute errors and count of active combos
    hand_class_map_t = torch.from_numpy(HAND_CLASS_MAP).long().to(device)  # (1326,)
    class_abs_err_sum = torch.zeros(NUM_HAND_CLASSES, dtype=torch.float64, device=device)
    class_count       = torch.zeros(NUM_HAND_CLASSES, dtype=torch.float64, device=device)

    for batch in loader:
        oop_r = batch["oop_reach"].to(device)
        ip_r  = batch["ip_reach"].to(device)

        with torch.amp.autocast(device_type=device.type, dtype=amp_dtype, enabled=use_amp):
            x = build_features(batch, device)
            out = model(x)
            pred_oop, pred_ip = model.split_output(out)
            tgt_oop, tgt_ip, _ = build_targets(batch, device)

        # Cast to float32 for MAE computation (exit autocast context)
        pred_oop = pred_oop.float()
        pred_ip  = pred_ip.float()
        tgt_oop  = tgt_oop.float()
        tgt_ip   = tgt_ip.float()

        mask = ((oop_r > 1e-6) | (ip_r > 1e-6)).float()  # (B, 1326)

        # Per-combo absolute error (average of OOP + IP)
        abs_err = (torch.abs(pred_oop - tgt_oop) + torch.abs(pred_ip - tgt_ip)) * 0.5  # (B, 1326)
        abs_err_masked = abs_err * mask  # (B, 1326)

        B = abs_err_masked.size(0)
        # Accumulate into per-class bins
        # hand_class_map_t is (1326,), expand to (B, 1326)
        class_indices = hand_class_map_t.unsqueeze(0).expand(B, -1)  # (B, 1326)

        # Flatten for scatter_add
        flat_indices = class_indices.reshape(-1)          # (B*1326,)
        flat_err     = abs_err_masked.reshape(-1).double()  # (B*1326,)
        flat_mask    = mask.reshape(-1).double()           # (B*1326,)

        class_abs_err_sum.scatter_add_(0, flat_indices, flat_err)
        class_count.scatter_add_(0, flat_indices, flat_mask)

    # Compute per-class MAE
    class_maes = {}
    active_maes = []
    for c in range(NUM_HAND_CLASSES):
        cnt = class_count[c].item()
        if cnt > 0:
            mae = class_abs_err_sum[c].item() / cnt
            class_maes[c] = mae
            active_maes.append(mae)

    mean_class_mae = np.mean(active_maes) if active_maes else 0.0
    return mean_class_mae, class_maes


# ─── Checkpoint helpers ──────────────────────────────────────────────────────

def save_checkpoint(path: str, epoch: int, step: int, model: RiverEVNet,
                    optimizer, scheduler, scaler, val_loss: float,
                    best_val_loss: float) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    torch.save({
        "epoch":              epoch,
        "step":               step,
        "model_state_dict":   model.state_dict(),
        "optimizer_state_dict": optimizer.state_dict(),
        "scheduler_state_dict": scheduler.state_dict(),
        "scaler_state_dict":  scaler.state_dict(),
        "val_loss":           val_loss,
        "best_val_loss":      best_val_loss,
        "config": {
            "hidden_dim":  model.hidden_dim,
            "num_blocks":  model.num_blocks,
            "input_dim":   model.input_dim,
            "output_dim":  model.output_dim,
        },
    }, path)


def load_checkpoint(path: str, model: RiverEVNet, optimizer, scheduler,
                    scaler, device: torch.device) -> Dict:
    ckpt = torch.load(path, map_location=device, weights_only=False)
    model.load_state_dict(ckpt["model_state_dict"])
    optimizer.load_state_dict(ckpt["optimizer_state_dict"])
    scheduler.load_state_dict(ckpt["scheduler_state_dict"])
    scaler.load_state_dict(ckpt["scaler_state_dict"])
    return ckpt


# ─── Argument parsing ────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Train RiverEVNet on RVNN binary training data",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--data-dir",    default="EZ-GTO/data/nn-training",
                   help="Directory containing chunk_*.bin files")
    p.add_argument("--output-dir",  default="checkpoints/river_ev_v1",
                   help="Directory to save checkpoints")

    # Model
    p.add_argument("--hidden-dim",  type=int, default=2048,
                   help="Hidden dimension (2048 for V1; 4096 for V2)")
    p.add_argument("--num-blocks",  type=int, default=4,
                   help="Number of residual blocks (4 for V1; 6 for V2)")

    # Training
    p.add_argument("--batch-size",  type=int,   default=256)
    p.add_argument("--num-epochs",  type=int,   default=100)
    p.add_argument("--patience",    type=int,   default=15,
                   help="Early stopping patience (epochs)")
    p.add_argument("--lr",          type=float, default=3e-4)
    p.add_argument("--weight-decay",type=float, default=1e-4)
    p.add_argument("--grad-clip",   type=float, default=1.0)
    p.add_argument("--huber-delta", type=float, default=1.0)
    p.add_argument("--val-split",   type=float, default=0.2)
    p.add_argument("--seed",        type=int,   default=42)
    p.add_argument("--num-workers", type=int,   default=0,
                   help="DataLoader workers (0=main process; keep 0 on Windows/emsdk Python)")
    p.add_argument("--save-every",  type=int,   default=10,
                   help="Save a numbered checkpoint every N epochs")
    p.add_argument("--log-every",   type=int,   default=50,
                   help="Log training loss every N steps")
    p.add_argument("--eval-interval", type=int, default=1,
                   help="Run per-hand-class MAE evaluation every N epochs")

    # LR schedule
    p.add_argument("--lr-schedule", choices=["onecycle", "cosine-restart"],
                   default="onecycle",
                   help="LR schedule: 'onecycle' (default, backward-compatible) "
                        "or 'cosine-restart' (CosineAnnealingWarmRestarts)")
    p.add_argument("--cosine-t0",   type=int,   default=20,
                   help="First cycle length in epochs for cosine-restart schedule")
    p.add_argument("--cosine-t-mult", type=int, default=2,
                   help="Cycle length multiplier for cosine-restart schedule")
    p.add_argument("--cosine-eta-min", type=float, default=1e-6,
                   help="Minimum LR for cosine-restart schedule")

    # Data augmentation
    p.add_argument("--augment-prob", type=float, default=0.0,
                   help="Probability of applying suit-isomorphic augmentation per sample "
                        "(0.0=disabled, 0.25 recommended for V2)")

    # Loss weighting
    p.add_argument("--weight-by-reach", action="store_true", default=False,
                   help="Weight loss by sqrt(reach_probability) so high-reach combos "
                        "matter more (off by default for backward compatibility)")

    # Resume / precision
    p.add_argument("--resume",      default=None,
                   help="Path to checkpoint to resume from")
    p.add_argument("--fp16",        action="store_true",
                   help="Use float16 instead of bfloat16 for mixed precision")
    p.add_argument("--no-amp",      action="store_true",
                   help="Disable automatic mixed precision")
    p.add_argument("--dry-run",     action="store_true",
                   help="Instantiate model, run one batch, print shapes, then exit")
    p.add_argument("--fast-load",   action="store_true", default=True,
                   help="Use vectorised fast_load_chunk (recommended)")
    return p.parse_args()


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    # ── Device ──
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")
    if device.type == "cuda":
        print(f"  GPU: {torch.cuda.get_device_name(0)}")
        mem_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
        print(f"  VRAM: {mem_gb:.1f} GB")

    use_amp   = not args.no_amp and device.type == "cuda"
    amp_dtype = torch.float16 if args.fp16 else torch.bfloat16
    if use_amp:
        print(f"  AMP: enabled ({amp_dtype})")

    # ── Data augmentation transform ──
    transform = None
    if args.augment_prob > 0:
        transform = SuitAugmentation(prob=args.augment_prob)
        print(f"\nSuit augmentation: enabled (prob={args.augment_prob})")

    # ── Dataset ──
    print(f"\nLoading data from: {args.data_dir}")
    if args.fast_load:
        dataset = FastRiverValueDataset(args.data_dir, transform=transform)
    else:
        dataset = RiverValueDataset(args.data_dir, transform=transform)
    n_total = len(dataset)
    print(f"  Total samples: {n_total:,}")

    n_val   = int(n_total * args.val_split)
    n_train = n_total - n_val
    gen     = torch.Generator().manual_seed(args.seed)
    train_ds, val_ds = random_split(dataset, [n_train, n_val], generator=gen)
    print(f"  Train: {n_train:,}  Val: {n_val:,}")

    loader_kwargs = dict(
        batch_size=args.batch_size,
        num_workers=args.num_workers,
        pin_memory=(device.type == "cuda"),
        prefetch_factor=2 if args.num_workers > 0 else None,
        persistent_workers=(args.num_workers > 0),
    )
    train_loader = DataLoader(train_ds, shuffle=True,  drop_last=True,  **loader_kwargs)
    val_loader   = DataLoader(val_ds,   shuffle=False, drop_last=False, **loader_kwargs)

    # ── Model ──
    model = RiverEVNet(hidden_dim=args.hidden_dim, num_blocks=args.num_blocks).to(device)
    print(f"\nModel: RiverEVNet(hidden={args.hidden_dim}, blocks={args.num_blocks})")
    print(f"  Parameters: {model.num_parameters:,}")
    print(f"  Input dim:  {model.input_dim}")
    print(f"  Output dim: {model.output_dim}")

    # ── Dry run ──
    if args.dry_run:
        model.eval()
        dummy_batch = next(iter(train_loader))
        with torch.no_grad():
            x   = build_features(dummy_batch, device)
            out = model(x)
            oop_pred, ip_pred = model.split_output(out)
            tgt_oop, tgt_ip, _ = build_targets(dummy_batch, device)
            oop_r = dummy_batch["oop_reach"].to(device)
            ip_r  = dummy_batch["ip_reach"].to(device)
            loss  = masked_huber_loss(oop_pred, ip_pred, tgt_oop, tgt_ip, oop_r, ip_r)
        print(f"\nDry run OK:")
        print(f"  x shape:   {x.shape}")
        print(f"  out shape: {out.shape}")
        print(f"  loss:      {loss.item():.4f}")
        print("Exiting (--dry-run).")
        return

    # ── Optimiser & scheduler ──
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=args.lr,
        weight_decay=args.weight_decay,
        betas=(0.9, 0.999),
        eps=1e-8,
    )
    steps_per_epoch = len(train_loader)
    total_steps     = args.num_epochs * steps_per_epoch

    if args.lr_schedule == "onecycle":
        scheduler = torch.optim.lr_scheduler.OneCycleLR(
            optimizer,
            max_lr=args.lr,
            total_steps=total_steps,
            pct_start=0.05,
            anneal_strategy="cos",
            div_factor=300,
            final_div_factor=30,
        )
        scheduler_step_per = "step"  # step scheduler every training step
        print(f"\nLR schedule: OneCycleLR (max_lr={args.lr}, total_steps={total_steps})")
    elif args.lr_schedule == "cosine-restart":
        scheduler = torch.optim.lr_scheduler.CosineAnnealingWarmRestarts(
            optimizer,
            T_0=args.cosine_t0,
            T_mult=args.cosine_t_mult,
            eta_min=args.cosine_eta_min,
        )
        scheduler_step_per = "epoch"  # step scheduler every epoch
        print(f"\nLR schedule: CosineAnnealingWarmRestarts "
              f"(T_0={args.cosine_t0}, T_mult={args.cosine_t_mult}, "
              f"eta_min={args.cosine_eta_min})")
    else:
        raise ValueError(f"Unknown LR schedule: {args.lr_schedule}")

    scaler = torch.amp.GradScaler(enabled=use_amp)

    if args.weight_by_reach:
        print(f"  Loss weighting: sqrt(reach) enabled")

    # ── Resume ──
    start_epoch    = 0
    global_step    = 0
    best_val_loss  = math.inf
    no_improve     = 0

    if args.resume and Path(args.resume).exists():
        print(f"\nResuming from: {args.resume}")
        ckpt = load_checkpoint(args.resume, model, optimizer, scheduler, scaler, device)
        start_epoch   = ckpt["epoch"] + 1
        global_step   = ckpt["step"]
        best_val_loss = ckpt["best_val_loss"]
        print(f"  Resumed at epoch {start_epoch}, step {global_step}, best_val={best_val_loss:.6f}")

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── Training loop ──
    print(f"\nTraining for up to {args.num_epochs} epochs (patience={args.patience})...")
    print(f"  steps/epoch={steps_per_epoch}, total_steps={total_steps}\n")

    for epoch in range(start_epoch, args.num_epochs):
        model.train()
        epoch_loss = 0.0
        t_epoch    = time.time()

        it = enumerate(train_loader)
        if HAS_TQDM:
            it = enumerate(tqdm(train_loader, desc=f"Epoch {epoch+1:03d}", leave=False))

        for step_in_epoch, batch in it:
            oop_r = batch["oop_reach"].to(device)
            ip_r  = batch["ip_reach"].to(device)

            optimizer.zero_grad(set_to_none=True)
            with torch.amp.autocast(device_type=device.type, dtype=amp_dtype, enabled=use_amp):
                x   = build_features(batch, device)
                out = model(x)
                pred_oop, pred_ip   = model.split_output(out)
                tgt_oop, tgt_ip, _  = build_targets(batch, device)
                loss = masked_huber_loss(pred_oop, pred_ip, tgt_oop, tgt_ip,
                                         oop_r, ip_r, args.huber_delta,
                                         args.weight_by_reach)

            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(model.parameters(), args.grad_clip)
            scaler.step(optimizer)
            scaler.update()

            # Step LR scheduler (per-step for OneCycleLR)
            if scheduler_step_per == "step":
                scheduler.step()

            loss_val    = loss.item()
            epoch_loss += loss_val
            global_step += 1

            if global_step % args.log_every == 0:
                lr_now = scheduler.get_last_lr()[0]
                print(f"  step={global_step:6d}  epoch={epoch+1:3d}  "
                      f"train_loss={loss_val:.5f}  lr={lr_now:.2e}")

        # Step LR scheduler (per-epoch for CosineAnnealingWarmRestarts)
        if scheduler_step_per == "epoch":
            scheduler.step()

        # ── Validation ──
        val_loss   = evaluate(model, val_loader, device, args.huber_delta,
                              use_amp, amp_dtype, args.weight_by_reach)
        avg_train  = epoch_loss / steps_per_epoch
        elapsed    = time.time() - t_epoch
        improved   = " *BEST*" if val_loss < best_val_loss else ""

        print(f"Epoch {epoch+1:3d}/{args.num_epochs}  "
              f"train={avg_train:.5f}  val={val_loss:.5f}  "
              f"({elapsed:.0f}s){improved}")

        # ── Per-hand-class MAE (every eval_interval epochs) ──
        if (epoch + 1) % args.eval_interval == 0:
            mean_class_mae, class_maes = evaluate_per_hand_class(
                model, val_loader, device, use_amp, amp_dtype)
            print(f"  Per-hand-class MAE (mean across {len(class_maes)} classes): "
                  f"{mean_class_mae:.6f}")

            # Show worst 10 hand classes
            if class_maes:
                worst = sorted(class_maes.items(), key=lambda kv: -kv[1])[:10]
                worst_strs = [f"{HAND_CLASS_NAMES[c]}={mae:.5f}" for c, mae in worst]
                print(f"  Worst 10: {', '.join(worst_strs)}")

                # Show best 5 hand classes
                best = sorted(class_maes.items(), key=lambda kv: kv[1])[:5]
                best_strs = [f"{HAND_CLASS_NAMES[c]}={mae:.5f}" for c, mae in best]
                print(f"  Best  5:  {', '.join(best_strs)}")

        # ── Checkpointing ──
        save_checkpoint(str(out_dir / "latest_model.pt"),
                        epoch, global_step, model, optimizer, scheduler, scaler,
                        val_loss, best_val_loss)

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            no_improve    = 0
            save_checkpoint(str(out_dir / "best_model.pt"),
                            epoch, global_step, model, optimizer, scheduler, scaler,
                            val_loss, best_val_loss)
            print(f"  >> New best val_loss: {best_val_loss:.6f}")
        else:
            no_improve += 1

        if (epoch + 1) % args.save_every == 0:
            save_checkpoint(str(out_dir / f"epoch_{epoch+1:04d}.pt"),
                            epoch, global_step, model, optimizer, scheduler, scaler,
                            val_loss, best_val_loss)

        # ── Early stopping ──
        if no_improve >= args.patience:
            print(f"\nEarly stopping: no improvement for {args.patience} epochs.")
            break

    print(f"\nTraining complete. Best val_loss: {best_val_loss:.6f}")
    print(f"Best model saved to: {out_dir / 'best_model.pt'}")


if __name__ == "__main__":
    main()
