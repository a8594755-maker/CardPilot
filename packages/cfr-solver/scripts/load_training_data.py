"""
load_training_data.py

Python loader for NN river value training data (.bin files).
Usage:
    from load_training_data import load_chunks, RiverValueDataset

    # Load all chunks from a directory
    data = load_chunks("data/nn-training")
    print(f"Loaded {data['num_samples']} samples")

    # PyTorch dataset
    dataset = RiverValueDataset("data/nn-training")
    sample = dataset[0]
    print(sample['oopReach'].shape)  # (1326,)
"""

import struct
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional

MAGIC = 0x4E4E5652  # "RVNN"
VERSION = 1
NUM_COMBOS = 1326
HEADER_BYTES = 16

# Record layout: 7 fields (28 bytes) + 4*1326 floats (21216 bytes) = 21244 bytes
# Fields: flopBoard[3] (int32), turnCard (int32), potOffset (float32),
#         startingPot (float32), effectiveStack (float32)
# Then: oopReach[1326], ipReach[1326], cfvOOP[1326], cfvIP[1326] (all float32)

INTS_FIELDS = 4   # 3 flop cards + 1 turn card
FLOAT_FIELDS = 3  # potOffset, startingPot, effectiveStack
FLOAT_ARRAYS = 4  # oopReach, ipReach, cfvOOP, cfvIP
RECORD_BYTES = INTS_FIELDS * 4 + FLOAT_FIELDS * 4 + FLOAT_ARRAYS * NUM_COMBOS * 4


def load_chunk(filepath: str) -> Dict[str, np.ndarray]:
    """Load a single .bin chunk file."""
    with open(filepath, "rb") as f:
        # Read header
        header = f.read(HEADER_BYTES)
        magic, version, num_samples, _ = struct.unpack("<4I", header)

        if magic != MAGIC:
            raise ValueError(f"Invalid magic: 0x{magic:08X} (expected 0x{MAGIC:08X})")
        if version != VERSION:
            raise ValueError(f"Unsupported version: {version}")

        # Read all records at once
        raw = f.read()

    expected_bytes = num_samples * RECORD_BYTES
    if len(raw) < expected_bytes:
        actual_samples = len(raw) // RECORD_BYTES
        print(f"Warning: expected {num_samples} samples but only {actual_samples} complete records found")
        num_samples = actual_samples
        raw = raw[:num_samples * RECORD_BYTES]

    # Parse into structured arrays
    flop_boards = np.zeros((num_samples, 3), dtype=np.int32)
    turn_cards = np.zeros(num_samples, dtype=np.int32)
    pot_offsets = np.zeros(num_samples, dtype=np.float32)
    starting_pots = np.zeros(num_samples, dtype=np.float32)
    effective_stacks = np.zeros(num_samples, dtype=np.float32)
    oop_reach = np.zeros((num_samples, NUM_COMBOS), dtype=np.float32)
    ip_reach = np.zeros((num_samples, NUM_COMBOS), dtype=np.float32)
    cfv_oop = np.zeros((num_samples, NUM_COMBOS), dtype=np.float32)
    cfv_ip = np.zeros((num_samples, NUM_COMBOS), dtype=np.float32)

    for i in range(num_samples):
        offset = i * RECORD_BYTES
        rec = raw[offset:offset + RECORD_BYTES]

        # Parse ints
        ints = struct.unpack_from("<4i", rec, 0)
        flop_boards[i] = ints[:3]
        turn_cards[i] = ints[3]

        # Parse float fields
        floats = struct.unpack_from("<3f", rec, 16)
        pot_offsets[i] = floats[0]
        starting_pots[i] = floats[1]
        effective_stacks[i] = floats[2]

        # Parse float arrays
        arr_offset = 28  # 4*4 + 3*4
        arr = np.frombuffer(rec, dtype=np.float32, offset=arr_offset)
        oop_reach[i] = arr[0:NUM_COMBOS]
        ip_reach[i] = arr[NUM_COMBOS:2*NUM_COMBOS]
        cfv_oop[i] = arr[2*NUM_COMBOS:3*NUM_COMBOS]
        cfv_ip[i] = arr[3*NUM_COMBOS:4*NUM_COMBOS]

    return {
        "num_samples": num_samples,
        "flop_boards": flop_boards,
        "turn_cards": turn_cards,
        "pot_offsets": pot_offsets,
        "starting_pots": starting_pots,
        "effective_stacks": effective_stacks,
        "oop_reach": oop_reach,
        "ip_reach": ip_reach,
        "cfv_oop": cfv_oop,
        "cfv_ip": cfv_ip,
    }


def load_chunks(directory: str) -> Dict[str, np.ndarray]:
    """Load all .bin chunk files from a directory and concatenate."""
    dirpath = Path(directory)
    files = sorted(dirpath.glob("chunk_*.bin"))
    if not files:
        raise FileNotFoundError(f"No chunk_*.bin files found in {directory}")

    chunks = [load_chunk(str(f)) for f in files]
    print(f"Loaded {len(chunks)} chunks from {directory}")

    # Concatenate all arrays
    result = {}
    for key in chunks[0]:
        if key == "num_samples":
            result[key] = sum(c[key] for c in chunks)
        else:
            result[key] = np.concatenate([c[key] for c in chunks], axis=0)

    print(f"Total samples: {result['num_samples']}")
    return result


# ─── PyTorch Dataset ───

try:
    import torch
    from torch.utils.data import Dataset

    class RiverValueDataset(Dataset):
        """PyTorch Dataset for NN river value training."""

        def __init__(self, directory: str, transform=None):
            self.data = load_chunks(directory)
            self.transform = transform
            self.n = self.data["num_samples"]

        def __len__(self) -> int:
            return self.n

        def __getitem__(self, idx) -> Dict[str, torch.Tensor]:
            sample = {
                "flop_board": torch.from_numpy(self.data["flop_boards"][idx].copy()),
                "turn_card": torch.tensor(self.data["turn_cards"][idx], dtype=torch.long),
                "pot_offset": torch.tensor(self.data["pot_offsets"][idx], dtype=torch.float32),
                "starting_pot": torch.tensor(self.data["starting_pots"][idx], dtype=torch.float32),
                "effective_stack": torch.tensor(self.data["effective_stacks"][idx], dtype=torch.float32),
                "oop_reach": torch.from_numpy(self.data["oop_reach"][idx].copy()),
                "ip_reach": torch.from_numpy(self.data["ip_reach"][idx].copy()),
                "cfv_oop": torch.from_numpy(self.data["cfv_oop"][idx].copy()),
                "cfv_ip": torch.from_numpy(self.data["cfv_ip"][idx].copy()),
            }
            if self.transform:
                sample = self.transform(sample)
            return sample

except ImportError:
    pass  # torch not available


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python load_training_data.py <data_dir>")
        sys.exit(1)

    data = load_chunks(sys.argv[1])
    print(f"\nDataset summary:")
    print(f"  Samples: {data['num_samples']}")
    print(f"  OOP reach shape: {data['oop_reach'].shape}")
    print(f"  IP reach shape: {data['ip_reach'].shape}")
    print(f"  CFV OOP shape: {data['cfv_oop'].shape}")
    print(f"  CFV IP shape: {data['cfv_ip'].shape}")

    # Basic stats
    oop_nonzero = np.count_nonzero(data['oop_reach'], axis=1)
    ip_nonzero = np.count_nonzero(data['ip_reach'], axis=1)
    print(f"\n  Avg non-zero OOP combos: {oop_nonzero.mean():.0f}")
    print(f"  Avg non-zero IP combos: {ip_nonzero.mean():.0f}")

    cfv_oop_abs = np.abs(data['cfv_oop'])
    cfv_ip_abs = np.abs(data['cfv_ip'])
    print(f"  Avg |CFV OOP|: {cfv_oop_abs[data['oop_reach'] > 0].mean():.4f}")
    print(f"  Avg |CFV IP|: {cfv_ip_abs[data['ip_reach'] > 0].mean():.4f}")

    # Sample some boards
    for i in range(min(5, data['num_samples'])):
        flop = data['flop_boards'][i]
        turn = data['turn_cards'][i]
        pot = data['pot_offsets'][i]
        sp = data['starting_pots'][i]
        es = data['effective_stacks'][i]
        print(f"\n  Sample {i}: board=[{flop[0]},{flop[1]},{flop[2]},{turn}] pot_off={pot:.1f} sp={sp:.1f} es={es:.1f}")
