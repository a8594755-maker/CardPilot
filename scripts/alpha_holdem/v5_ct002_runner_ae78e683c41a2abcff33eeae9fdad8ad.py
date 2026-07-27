#!/usr/bin/env python3
"""Canonical clean-room runner for CT002 ae78.

The registered intervention is only the critic calibration data distribution.
This file owns deterministic data generation, value-head-only calibration,
mechanism gating, and matched PPO orchestration.  Contract-probe mode is strictly
CPU/read-only and never creates the registered output root.
"""

from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import heapq
import json
import math
import os
import shutil
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

ROOT = Path(r"C:\Users\a8594\CardPilot")
SCRIPT_DIR = ROOT / "scripts" / "alpha_holdem"
SCRIPTS_DIR = ROOT / "scripts"
for _path in (str(SCRIPT_DIR), str(SCRIPTS_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

TOKEN = "ae78e683c41a2abcff33eeae9fdad8ad"
IDENTITY_SHA256 = "ae78e683c41a2abcff33eeae9fdad8adecd7db86db4827fe659583a2b33c4096"
PREREG = ROOT / "reports" / f"v5_ct002_preregistration_{TOKEN}_20260722.json"
PREREG_SHA256 = "faef13eff5a57270bc59b43ff3272a3eb6bedf0fe43f0539494a2cd0993072da"
PREREG_AUDIT = ROOT / "reports" / f"v5_ct002_preregistration_audit_{TOKEN}_20260722.json"
PREREG_AUDIT_SHA256 = "2426ca7663d9f347d7884a0e6ebf36831924f110acc316a5326f80fcfa04860e"
SOURCE = ROOT / "models" / "alpha_holdem_v5_hybrid" / "v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715" / "latest.pt"
SOURCE_SHA256 = "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"
OUTPUT_ROOT = ROOT / "models" / "alpha_holdem_v5_hybrid" / f"v5_ct002_{TOKEN}_20260722"
DATASET_ROOT = OUTPUT_ROOT / "calibration_data"
IMPLEMENTATION_AUDIT_RESULT = ROOT / "reports" / f"v5_ct002_implementation_audit_result_{TOKEN}_20260722.json"

PYTHON_EXE = Path(r"C:\Users\a8594\AppData\Local\Programs\Python\Python312\python.exe")
PYTHON_SHA256 = "4d6f5f81a4bca11191c4c7c6b43632694d0a4ce74e068619d8fdc161d469859a"
DEVICE_MODE_PROBE = "CPU_ONLY_NO_GPU_NO_OUTPUT"
DEVICE_MODE_EXECUTION = "CUDA_SINGLE_GPU_SEQUENTIAL_NO_FALLBACK"
PROBE_NONCES = {"control": "2026072213", "treatment": "2026072214"}

CLEAN_SOURCES = {
    SCRIPT_DIR / "network_hybrid_h1.py": "25f4520d31f4ce5ffcfd23fc0d56b8736fd3b5fad537706b9cd13ee270b4a171",
    SCRIPT_DIR / "train_mp3_hybrid_h1.py": "69197b52baee7463d79e4a940f01f8bb241ed8e70975b51e043b99fd8a5cbc4d",
    SCRIPT_DIR / "environment_v55.py": "3ab591176a8119d21ac11e043bdfef72bd30b8842e34a9fea45cdd36b945f9de",
    SCRIPT_DIR / "train_v5_hybrid_h1.py": "91a98cec7677f4ee2ba74491f1be61ef2b3d4bfbb574b3615604d45f569d5591",
}
FORBIDDEN_TRAINER = SCRIPT_DIR / "train_v5.py"
FORBIDDEN_TRAINER_SHA256 = "9d42ff31a57c13ae8afd361b553fe9ea6e086c3e6d0c46328012f39b245b5310"

SOURCE_ITERATION = 35051
SOURCE_HANDS = 576_021_901
STAGE_A_TARGET_HANDS = 581_021_901
STAGE_A_OVERSHOOT_MAX = 50_000
POOL_CHECKPOINT_ORDER = [109, 115, 120, 129, 103]
POOL_ASCENDING_ORDER = [103, 109, 115, 120, 129]
POOL_SPECS = {
    103: (26200, 430445532, "cdec36f3deb27470a61c586b6491cd5de44aa3a99194b026a6e491a3121335a1"),
    109: (27400, 450186098, "aee38c625bf0faada6b163f23aeb4cc539d67f7cbe46dc234aa4f46b18960953"),
    115: (28600, 469929538, "ed92c7724486e446c13e5d4c623327d4288c68652964b7b4f35c0d2a7630d0c1"),
    120: (29600, 486379183, "86c3d7bacce72dd5749c21deaad3865c7313c9f118860cbc7e9b8b378070494e"),
    129: (31400, 515989661, "9d008780ac3cd259579131532df9775b53b4e3c95c7b0f12f2aac70bc915b255"),
}
SOURCE_MODEL_SHA256 = "19bf761296f16758f74bad4bc98192b8954319fcbd2bc3bb174363ea21736b10"

DEAL_SEED = 2026072204
ACTION_SEED = 2026072205
SHUFFLE_SEED = 2026072206
PPO_SEED = 2026072207
WORKER_SEED_BASE = 83000
TRAIN_DEAL_RANGE = range(0, 25_000)
HELDOUT_DEAL_RANGE = range(25_000, 30_000)
TRAIN_HANDS_PER_ARM = 50_000
HELDOUT_HANDS_PER_ARM = 10_000
TRAIN_ROWS = 250_000
HELDOUT_ROWS = 50_000
CALIBRATION_BATCH_SIZE = 1_000
CALIBRATION_EPOCHS = 4
CALIBRATION_UPDATES = 1_000
CALIBRATION_LR = 1e-4
GAMMA = 0.999
SHARD_ROWS = 1_000
SELF_PLAY_THRESHOLD_U64 = (1 << 64) // 5


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.resolve(strict=True).open("rb") as handle:
        for block in iter(lambda: handle.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_u64(label: str, *parts: object) -> int:
    material = "|".join([label, *(str(part) for part in parts)]).encode("utf-8")
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big")


def state_dict_sha256(state_dict: dict[str, Any]) -> str:
    digest = hashlib.sha256()
    for name in sorted(state_dict):
        tensor = state_dict[name].detach().cpu().contiguous()
        metadata = json.dumps(
            [name, str(tensor.dtype), list(tensor.shape)],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        digest.update(len(metadata).to_bytes(8, "big"))
        digest.update(metadata)
        digest.update(tensor.numpy().tobytes())
    return digest.hexdigest()


def exclusive_json(path: Path, value: Any) -> None:
    path = path.resolve(strict=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False)
        handle.write("\n")


def exact_path(observed: str | Path, expected: Path, label: str, *, must_exist: bool | None = None) -> Path:
    raw = Path(observed)
    if not raw.is_absolute():
        raise RuntimeError(f"{label}_not_absolute")
    resolved = raw.resolve(strict=False)
    if resolved != expected.resolve(strict=False):
        raise RuntimeError(f"{label}_path_mismatch")
    if must_exist is True and not resolved.exists():
        raise RuntimeError(f"{label}_missing")
    if must_exist is False and resolved.exists():
        raise RuntimeError(f"{label}_collision")
    return resolved


def deterministic_deck(deal_index: int) -> list[int]:
    if not 0 <= int(deal_index) < 30_000:
        raise ValueError("deal_index_out_of_registered_range")
    deck = list(range(52))
    for upper in range(51, 0, -1):
        pick = sha256_u64("CT002_DECK_FY_V1", DEAL_SEED, int(deal_index), upper) % (upper + 1)
        deck[upper], deck[pick] = deck[pick], deck[upper]
    return deck


def action_u64(role: str, deal_index: int, hero_seat: int, decision_ordinal: int) -> int:
    if role not in {"hero", "control_opponent", "treatment_opponent"}:
        raise ValueError("unknown_action_role")
    return sha256_u64(
        "CT002_ACTION_INVERSE_CDF_V1", ACTION_SEED, role,
        int(deal_index), int(hero_seat), int(decision_ordinal),
    )


def inverse_cdf_index(probabilities: Sequence[float], legal_mask: Sequence[float], u64: int) -> int:
    legal = [i for i, flag in enumerate(legal_mask) if float(flag) > 0.0]
    if not legal:
        raise RuntimeError("no_legal_action")
    weights = [max(0.0, float(probabilities[i])) for i in legal]
    total = math.fsum(weights)
    if not math.isfinite(total) or total <= 0.0:
        raise RuntimeError("invalid_policy_probability_mass")
    target = (int(u64) + 0.5) / float(1 << 64) * total
    cumulative = 0.0
    for index, weight in zip(legal, weights):
        cumulative += weight
        if target <= cumulative:
            return index
    return legal[-1]


def row_key(arm: str, split: str, deal_index: int, hero_seat: int, hero_ordinal: int) -> str:
    if arm not in {"control", "treatment"} or split not in {"train", "heldout"}:
        raise ValueError("invalid_row_identity")
    material = f"CT002_ROW_V1|{arm}|{split}|{deal_index}|{hero_seat}|{hero_ordinal}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def calibration_order_key(epoch: int, key: str) -> str:
    return hashlib.sha256(f"CT002_CAL_SHUFFLE_V1|{SHUFFLE_SEED}|{epoch}|{key}".encode("utf-8")).hexdigest()


def ppo_assignment(applies_to_iteration: int) -> dict[str, int | str]:
    u64 = sha256_u64("CT002_PPO_ASSIGNMENT_V1", PPO_SEED, int(applies_to_iteration))
    if u64 < SELF_PLAY_THRESHOLD_U64:
        return {"kind": "self", "member_id": -1, "local_index": -1, "u64": u64}
    conditional = u64 - SELF_PLAY_THRESHOLD_U64
    span = (1 << 64) - SELF_PLAY_THRESHOLD_U64
    bucket = min(4, (conditional * 5) // span)
    member_id = POOL_ASCENDING_ORDER[bucket]
    return {
        "kind": "pool", "member_id": member_id,
        "local_index": POOL_CHECKPOINT_ORDER.index(member_id), "u64": u64,
    }


def validate_registration_files() -> dict[str, Any]:
    exact_path(PREREG, PREREG, "preregistration", must_exist=True)
    exact_path(PREREG_AUDIT, PREREG_AUDIT, "preregistration_audit", must_exist=True)
    if sha256_file(PREREG) != PREREG_SHA256:
        raise RuntimeError("preregistration_hash_mismatch")
    if sha256_file(PREREG_AUDIT) != PREREG_AUDIT_SHA256:
        raise RuntimeError("preregistration_audit_hash_mismatch")
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    if prereg["identity"]["sha256"] != IDENTITY_SHA256 or prereg["identity"]["token"] != TOKEN:
        raise RuntimeError("registration_identity_mismatch")
    if prereg["one_coherent_behavior_intervention"]["identity"] != "CRITIC_ONLY_CALIBRATION_DATA_DISTRIBUTION":
        raise RuntimeError("registered_intervention_mismatch")
    for path, expected_hash in CLEAN_SOURCES.items():
        if sha256_file(path) != expected_hash:
            raise RuntimeError(f"clean_source_hash_mismatch:{path.name}")
    if sha256_file(FORBIDDEN_TRAINER) != FORBIDDEN_TRAINER_SHA256:
        raise RuntimeError("forbidden_trainer_observed_hash_changed")
    if sha256_file(PYTHON_EXE) != PYTHON_SHA256:
        raise RuntimeError("python_hash_mismatch")
    return prereg


def inspect_source_checkpoint() -> tuple[dict[str, Any], dict[str, Any]]:
    if sha256_file(SOURCE) != SOURCE_SHA256:
        raise RuntimeError("source_checkpoint_hash_mismatch")
    import torch

    checkpoint = torch.load(SOURCE, map_location="cpu", weights_only=False)
    if int(checkpoint.get("iteration", -1)) != SOURCE_ITERATION:
        raise RuntimeError("source_iteration_mismatch")
    if int(checkpoint.get("total_hands", -1)) != SOURCE_HANDS:
        raise RuntimeError("source_hand_count_mismatch")
    if checkpoint.get("env_version") != "v55" or checkpoint.get("action_space_version") != "9slot_v5":
        raise RuntimeError("source_environment_or_action_space_mismatch")
    if checkpoint.get("critic_contract") != "critic_v1" or "optimizer" not in checkpoint:
        raise RuntimeError("source_critic_or_optimizer_mismatch")
    model_hash = state_dict_sha256(checkpoint.get("model") or {})
    if model_hash != SOURCE_MODEL_SHA256:
        raise RuntimeError("source_model_state_hash_mismatch")
    snapshots = checkpoint.get("pool_snapshots") or []
    if [int(item.get("id", -1)) for item in snapshots] != POOL_CHECKPOINT_ORDER:
        raise RuntimeError("source_pool_order_mismatch")
    members = []
    for local_index, snapshot in enumerate(snapshots):
        member_id = int(snapshot["id"])
        iteration, hands, expected_hash = POOL_SPECS[member_id]
        actual_hash = state_dict_sha256(snapshot.get("state_dict") or {})
        if (int(snapshot.get("iteration", -1)), int(snapshot.get("hands", -1)), actual_hash) != (iteration, hands, expected_hash):
            raise RuntimeError(f"source_pool_member_mismatch:{member_id}")
        members.append({"id": member_id, "local_index": local_index, "state_sha256": actual_hash})
    summary = {
        "checkpoint_sha256": SOURCE_SHA256,
        "iteration": SOURCE_ITERATION,
        "total_hands": SOURCE_HANDS,
        "model_state_sha256": model_hash,
        "optimizer_present": True,
        "pool_members": members,
    }
    return checkpoint, summary


def build_model(state_dict: dict[str, Any], device: str):
    import torch
    from alpha_holdem.network_hybrid_h1 import AlphaHoldemNet, CRITIC_V1

    model = AlphaHoldemNet(num_actions=9, critic_contract=CRITIC_V1).to(device)
    with torch.no_grad():
        model(
            torch.zeros(1, 6, 4, 13, device=device),
            torch.zeros(1, 25, 4, 5, device=device),
            torch.zeros(1, 2, device=device),
        )
    model.load_state_dict(state_dict)
    model.eval()
    return model


def reset_with_deck(environment: Any, deck: Sequence[int]) -> dict[str, Any]:
    environment.reset()
    state = environment.state
    state.deck = list(deck)
    state.hole_cards = [(deck[0], deck[1]), (deck[2], deck[3])]
    state.board = [] if getattr(state.config, "include_preflop", True) else list(deck[4:7])
    environment._legal_calls_this_hand = 0
    return environment._get_obs()


@dataclass
class HandTask:
    arm: str
    split: str
    deal_index: int
    hero_seat: int
    opponent_id: int
    environment: Any
    observation: dict[str, Any]
    action_ordinal: int = 0
    hero_rows: list[dict[str, Any]] = field(default_factory=list)


class RawShardWriter:
    def __init__(self, directory: Path):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=False)
        self.buffer: list[dict[str, Any]] = []
        self.locations: list[tuple[str, int, int]] = []
        self.shard_index = 0

    def add(self, row: dict[str, Any]) -> None:
        self.buffer.append(row)
        if len(self.buffer) == SHARD_ROWS:
            self.flush()

    def flush(self) -> None:
        if not self.buffer:
            return
        import numpy as np

        rows = self.buffer
        arrays = {
            "card": np.stack([row["card"] for row in rows]).astype(np.float32, copy=False),
            "action": np.stack([row["action"] for row in rows]).astype(np.float32, copy=False),
            "extra": np.stack([row["extra"] for row in rows]).astype(np.float32, copy=False),
            "target": np.asarray([row["target"] for row in rows], dtype=np.float32),
            "key": np.asarray([row["key"] for row in rows], dtype="U64"),
            "deal_index": np.asarray([row["deal_index"] for row in rows], dtype=np.int32),
            "hero_seat": np.asarray([row["hero_seat"] for row in rows], dtype=np.int8),
            "hero_ordinal": np.asarray([row["hero_ordinal"] for row in rows], dtype=np.int16),
            "action_index": np.asarray([row["action_index"] for row in rows], dtype=np.int8),
            "opponent_id": np.asarray([row["opponent_id"] for row in rows], dtype=np.int16),
        }
        path = self.directory / f"raw_{self.shard_index:05d}.npz"
        with path.open("xb") as handle:
            np.savez_compressed(handle, **arrays)
        for row_index, row in enumerate(rows):
            self.locations.append((row["key"], self.shard_index, row_index))
        self.shard_index += 1
        self.buffer = []


def policy_probabilities(model: Any, observations: list[dict[str, Any]], device: str):
    import numpy as np
    import torch

    card = torch.as_tensor(np.stack([obs["card_info"] for obs in observations]), dtype=torch.float32, device=device)
    action = torch.as_tensor(np.stack([obs["action_info"] for obs in observations]), dtype=torch.float32, device=device)
    extra = torch.as_tensor(np.stack([obs["extra_info"] for obs in observations]), dtype=torch.float32, device=device)
    mask = torch.as_tensor(np.stack([obs["legal_mask"] for obs in observations]), dtype=torch.float32, device=device)
    with torch.no_grad():
        logits, _ = model(card, action, extra, mask)
        probabilities = torch.softmax(logits, dim=-1).cpu().numpy()
    return probabilities


def collect_split(
    *, arm: str, split: str, deal_range: range, source_model: Any,
    pool_models: dict[int, Any], device: str, writer: RawShardWriter,
    hand_manifest: gzip.GzipFile, batch_hands: int = 128,
) -> dict[str, int]:
    from alpha_holdem.environment_v55 import HUNLEnvironmentV55

    task_specs = [
        (deal_index, hero_seat)
        for deal_index in deal_range
        for hero_seat in (0, 1)
    ]
    completed = decisions = 0
    for offset in range(0, len(task_specs), batch_hands):
        active: list[HandTask] = []
        for deal_index, hero_seat in task_specs[offset:offset + batch_hands]:
            opponent_id = -1 if arm == "control" else POOL_ASCENDING_ORDER[(deal_index + hero_seat) % 5]
            environment = HUNLEnvironmentV55(starting_stack=200.0)
            observation = reset_with_deck(environment, deterministic_deck(deal_index))
            active.append(HandTask(arm, split, deal_index, hero_seat, opponent_id, environment, observation))
        while active:
            groups: dict[int, list[HandTask]] = defaultdict(list)
            for task in active:
                acting_seat = int(task.observation["player"])
                policy_id = -1 if acting_seat == task.hero_seat or arm == "control" else task.opponent_id
                groups[policy_id].append(task)
            finished: list[HandTask] = []
            for policy_id, tasks in groups.items():
                model = source_model if policy_id == -1 else pool_models[policy_id]
                probabilities = policy_probabilities(model, [task.observation for task in tasks], device)
                for task, probs in zip(tasks, probabilities):
                    acting_seat = int(task.observation["player"])
                    is_hero = acting_seat == task.hero_seat
                    role = "hero" if is_hero else ("control_opponent" if arm == "control" else "treatment_opponent")
                    action_index = inverse_cdf_index(
                        probs, task.observation["legal_mask"],
                        action_u64(role, task.deal_index, task.hero_seat, task.action_ordinal),
                    )
                    if is_hero:
                        task.hero_rows.append({
                            "card": task.observation["card_info"].copy(),
                            "action": task.observation["action_info"].copy(),
                            "extra": task.observation["extra_info"].copy(),
                            "deal_index": task.deal_index,
                            "hero_seat": task.hero_seat,
                            "hero_ordinal": len(task.hero_rows),
                            "action_index": action_index,
                            "opponent_id": task.opponent_id,
                        })
                    task.action_ordinal += 1
                    next_observation, _, done = task.environment.step(action_index)
                    if done:
                        profit = float(task.environment.state.payoff(task.hero_seat)) / float(task.environment.big_blind)
                        count = len(task.hero_rows)
                        for index, row in enumerate(task.hero_rows):
                            row["target"] = (GAMMA ** (count - 1 - index)) * profit
                            row["key"] = row_key(arm, split, task.deal_index, task.hero_seat, index)
                            writer.add(row)
                            decisions += 1
                        manifest_row = {
                            "schema_version": "v5.ct002.hand.v1", "arm": arm, "split": split,
                            "deal_index": task.deal_index, "hero_seat": task.hero_seat,
                            "opponent_id": task.opponent_id, "hero_decisions": count,
                            "terminal_profit_bb": profit,
                            "deck_sha256": hashlib.sha256(bytes(deterministic_deck(task.deal_index))).hexdigest(),
                        }
                        hand_manifest.write((canonical_json(manifest_row) + "\n").encode("utf-8"))
                        completed += 1
                        finished.append(task)
                    else:
                        task.observation = next_observation
            if finished:
                finished_ids = {id(task) for task in finished}
                active = [task for task in active if id(task) not in finished_ids]
    writer.flush()
    return {"hands": completed, "candidate_rows": decisions, "raw_shards": writer.shard_index}


def materialize_selected_shards(raw_writer: RawShardWriter, destination: Path, expected_rows: int) -> list[dict[str, Any]]:
    import numpy as np

    if len(raw_writer.locations) < expected_rows:
        raise RuntimeError(f"row_shortfall:{len(raw_writer.locations)}<{expected_rows}")
    chosen = sorted(raw_writer.locations, key=lambda item: item[0])[:expected_rows]
    destination.mkdir(parents=True, exist_ok=False)
    # Candidate volume is bounded by the registered 50k/10k complete-hand sets.
    # Decompress each raw shard once, then index the globally key-sorted selection.
    candidate_arrays: dict[str, list[Any]] = defaultdict(list)
    for raw_shard in range(raw_writer.shard_index):
        with np.load(raw_writer.directory / f"raw_{raw_shard:05d}.npz", allow_pickle=False) as source:
            for name in source.files:
                candidate_arrays[name].append(source[name])
    combined = {name: np.concatenate(values, axis=0) for name, values in candidate_arrays.items()}
    chosen_indices = np.asarray(
        [raw_shard * SHARD_ROWS + raw_index for _, raw_shard, raw_index in chosen],
        dtype=np.int64,
    )
    manifests = []
    for shard_out, start in enumerate(range(0, expected_rows, SHARD_ROWS)):
        indices = chosen_indices[start:start + SHARD_ROWS]
        arrays = {name: values[indices] for name, values in combined.items()}
        path = destination / f"rows_{shard_out:05d}.npz"
        with path.open("xb") as handle:
            np.savez_compressed(handle, **arrays)
        manifests.append({"path": str(path), "sha256": sha256_file(path), "rows": len(indices)})
    return manifests


def build_datasets() -> dict[str, Any]:
    if os.environ.get("CUDA_VISIBLE_DEVICES") != "0" or os.environ.get("CT002_DEVICE_MODE") != DEVICE_MODE_EXECUTION:
        raise RuntimeError("dataset_device_contract_mismatch")
    exact_path(OUTPUT_ROOT, OUTPUT_ROOT, "output_root", must_exist=False)
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("cuda_required_no_fallback")
    checkpoint, source_summary = inspect_source_checkpoint()
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=False)
    DATASET_ROOT.mkdir(parents=False, exist_ok=False)
    source_model = build_model(checkpoint["model"], "cuda")
    pool_models = {int(item["id"]): build_model(item["state_dict"], "cuda") for item in checkpoint["pool_snapshots"]}
    manifest: dict[str, Any] = {
        "schema_version": "v5.ct002.dataset_bundle.v1", "token": TOKEN,
        "source": source_summary, "deal_seed": DEAL_SEED, "action_seed": ACTION_SEED,
        "arms": {},
    }
    for arm in ("control", "treatment"):
        arm_dir = DATASET_ROOT / arm
        arm_dir.mkdir(parents=False, exist_ok=False)
        arm_manifest: dict[str, Any] = {}
        hand_path = arm_dir / "hands.jsonl.gz"
        with gzip.open(hand_path, "xb", compresslevel=6) as hand_manifest:
            for split, deal_range, expected_hands, expected_rows in (
                ("train", TRAIN_DEAL_RANGE, TRAIN_HANDS_PER_ARM, TRAIN_ROWS),
                ("heldout", HELDOUT_DEAL_RANGE, HELDOUT_HANDS_PER_ARM, HELDOUT_ROWS),
            ):
                raw = RawShardWriter(arm_dir / f".{split}_raw")
                observed = collect_split(
                    arm=arm, split=split, deal_range=deal_range,
                    source_model=source_model, pool_models=pool_models, device="cuda",
                    writer=raw, hand_manifest=hand_manifest,
                )
                if observed["hands"] != expected_hands:
                    raise RuntimeError(f"{arm}_{split}_hand_count_mismatch")
                shards = materialize_selected_shards(raw, arm_dir / split, expected_rows)
                raw_root = raw.directory.resolve(strict=True)
                if OUTPUT_ROOT.resolve(strict=True) not in raw_root.parents:
                    raise RuntimeError("temporary_raw_root_escape")
                shutil.rmtree(raw_root)
                arm_manifest[split] = {**observed, "selected_rows": expected_rows, "shards": shards}
        arm_manifest["hands_jsonl_gz"] = {"path": str(hand_path), "sha256": sha256_file(hand_path)}
        manifest["arms"][arm] = arm_manifest
    manifest_path = DATASET_ROOT / "manifest.json"
    exclusive_json(manifest_path, manifest)
    return manifest


def dataset_shards(arm: str, split: str) -> list[Path]:
    directory = DATASET_ROOT / arm / split
    paths = sorted(directory.glob("rows_*.npz"))
    expected = TRAIN_ROWS // SHARD_ROWS if split == "train" else HELDOUT_ROWS // SHARD_ROWS
    if len(paths) != expected:
        raise RuntimeError(f"{arm}_{split}_shard_count_mismatch")
    return paths


def load_rows(arm: str, split: str) -> dict[str, Any]:
    import numpy as np

    combined: dict[str, list[Any]] = defaultdict(list)
    for path in dataset_shards(arm, split):
        with np.load(path, allow_pickle=False) as shard:
            for name in shard.files:
                combined[name].append(shard[name])
    return {name: np.concatenate(values, axis=0) for name, values in combined.items()}


def non_value_state_sha256(model: Any) -> str:
    return state_dict_sha256({name: value for name, value in model.state_dict().items() if not name.startswith("value_head.")})


def zero_value_optimizer_moments(source_optimizer: dict[str, Any], model: Any) -> dict[str, Any]:
    import torch

    transformed = copy.deepcopy(source_optimizer)
    parameter_names = [name for name, _ in model.named_parameters()]
    flat_ids = [pid for group in transformed["param_groups"] for pid in group["params"]]
    if len(flat_ids) != len(parameter_names) or len(set(flat_ids)) != len(flat_ids):
        raise RuntimeError("optimizer_parameter_mapping_mismatch")
    name_to_id = dict(zip(parameter_names, flat_ids))
    named_parameters = dict(model.named_parameters())
    for name in ("value_head.weight", "value_head.bias"):
        pid = name_to_id[name]
        state = transformed["state"].get(pid, transformed["state"].get(str(pid), {}))
        zeroed = {}
        for key, value in state.items():
            zeroed[key] = torch.zeros_like(value) if torch.is_tensor(value) else type(value)(0)
        if not zeroed:
            parameter = named_parameters[name].detach().cpu()
            zeroed = {"step": torch.tensor(0.0), "exp_avg": torch.zeros_like(parameter), "exp_avg_sq": torch.zeros_like(parameter)}
        transformed["state"][pid] = zeroed
        transformed["state"].pop(str(pid), None)
    return transformed


def trunk_features(model: Any, card: Any, action: Any, extra: Any):
    import torch
    with torch.no_grad():
        return model.trunk(torch.cat([model.card_cnn(card), model.action_cnn(action), model.extra_fc(extra)], dim=1)).detach()


def calibrate(arm: str) -> dict[str, Any]:
    if arm not in {"control", "treatment"}:
        raise RuntimeError("invalid_calibration_arm")
    if os.environ.get("CUDA_VISIBLE_DEVICES") != "0" or os.environ.get("CT002_DEVICE_MODE") != DEVICE_MODE_EXECUTION:
        raise RuntimeError("calibration_device_contract_mismatch")
    import numpy as np
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("cuda_required_no_fallback")
    checkpoint, source_summary = inspect_source_checkpoint()
    rows = load_rows(arm, "train")
    if len(rows["key"]) != TRAIN_ROWS:
        raise RuntimeError("calibration_train_row_count_mismatch")
    model = build_model(checkpoint["model"], "cuda")
    model.eval()
    before_non_value = non_value_state_sha256(model)
    for name, parameter in model.named_parameters():
        parameter.requires_grad_(name in {"value_head.weight", "value_head.bias"})
    optimizer = torch.optim.Adam(model.value_head.parameters(), lr=CALIBRATION_LR)
    updates = 0
    losses = []
    keys = [str(value) for value in rows["key"]]
    for epoch in range(CALIBRATION_EPOCHS):
        order = np.asarray(sorted(range(TRAIN_ROWS), key=lambda index: calibration_order_key(epoch, keys[index])), dtype=np.int64)
        for offset in range(0, TRAIN_ROWS, CALIBRATION_BATCH_SIZE):
            indices = order[offset:offset + CALIBRATION_BATCH_SIZE]
            card = torch.as_tensor(rows["card"][indices], dtype=torch.float32, device="cuda")
            action = torch.as_tensor(rows["action"][indices], dtype=torch.float32, device="cuda")
            extra = torch.as_tensor(rows["extra"][indices], dtype=torch.float32, device="cuda")
            target = torch.as_tensor(rows["target"][indices], dtype=torch.float32, device="cuda")
            features = trunk_features(model, card, action, extra)
            prediction = model.value_head(features).squeeze(-1)
            loss = torch.mean((prediction - target) ** 2)
            if not torch.isfinite(loss):
                raise RuntimeError("nonfinite_calibration_loss")
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(list(model.value_head.parameters()), 1.0)
            optimizer.step()
            losses.append(float(loss.detach().cpu()))
            updates += 1
    if updates != CALIBRATION_UPDATES:
        raise RuntimeError("calibration_update_count_mismatch")
    after_non_value = non_value_state_sha256(model)
    if after_non_value != before_non_value:
        raise RuntimeError("calibration_actor_or_buffer_changed")
    payload = copy.deepcopy(checkpoint)
    payload["model"] = {name: tensor.detach().cpu() for name, tensor in model.state_dict().items()}
    payload["optimizer"] = zero_value_optimizer_moments(checkpoint["optimizer"], model)
    payload["ct002"] = {
        "registration_token": TOKEN, "preregistration_sha256": PREREG_SHA256,
        "source_checkpoint_sha256": SOURCE_SHA256, "arm": arm,
        "intervention": "CRITIC_ONLY_CALIBRATION_DATA_DISTRIBUTION",
        "calibration_updates": updates, "train_rows": TRAIN_ROWS,
        "actor_non_value_state_sha256": after_non_value,
    }
    arm_root = OUTPUT_ROOT / arm
    arm_root.mkdir(parents=False, exist_ok=False)
    checkpoint_path = arm_root / "calibrated.pt"
    with checkpoint_path.open("xb") as handle:
        torch.save(payload, handle)
    report = {
        "schema_version": "v5.ct002.calibration_result.v1", "arm": arm,
        "source": source_summary, "checkpoint": {"path": str(checkpoint_path), "sha256": sha256_file(checkpoint_path)},
        "updates": updates, "rows": TRAIN_ROWS, "epochs": CALIBRATION_EPOCHS,
        "loss_mean": math.fsum(losses) / len(losses), "loss_last": losses[-1],
        "non_value_state_before": before_non_value, "non_value_state_after": after_non_value,
    }
    exclusive_json(arm_root / "calibration_result.json", report)
    return report


def mse_on_rows(model: Any, rows: dict[str, Any], device: str) -> float:
    import torch
    total = 0.0
    count = 0
    for offset in range(0, len(rows["target"]), 2_000):
        sl = slice(offset, offset + 2_000)
        card = torch.as_tensor(rows["card"][sl], dtype=torch.float32, device=device)
        action = torch.as_tensor(rows["action"][sl], dtype=torch.float32, device=device)
        extra = torch.as_tensor(rows["extra"][sl], dtype=torch.float32, device=device)
        target = torch.as_tensor(rows["target"][sl], dtype=torch.float32, device=device)
        with torch.no_grad():
            _, value = model(card, action, extra)
            squared = (value.squeeze(-1) - target) ** 2
        total += float(squared.sum().cpu())
        count += int(squared.numel())
    return total / count


def mechanism_gate() -> dict[str, Any]:
    if os.environ.get("CUDA_VISIBLE_DEVICES") != "0" or os.environ.get("CT002_DEVICE_MODE") != DEVICE_MODE_EXECUTION:
        raise RuntimeError("mechanism_device_contract_mismatch")
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("cuda_required_no_fallback")
    models = {}
    for arm in ("control", "treatment"):
        path = OUTPUT_ROOT / arm / "calibrated.pt"
        checkpoint = torch.load(path, map_location="cpu", weights_only=False)
        metadata = checkpoint.get("ct002") or {}
        if metadata.get("registration_token") != TOKEN or metadata.get("arm") != arm:
            raise RuntimeError(f"{arm}_calibrated_checkpoint_identity_mismatch")
        models[arm] = build_model(checkpoint["model"], "cuda")
    rows = {distribution: load_rows(distribution, "heldout") for distribution in ("control", "treatment")}
    mse = {
        arm: {distribution: mse_on_rows(models[arm], rows[distribution], "cuda") for distribution in rows}
        for arm in models
    }
    opponent_ratio = mse["treatment"]["treatment"] / mse["control"]["treatment"]
    selfplay_ratio = mse["treatment"]["control"] / mse["control"]["control"]
    combined_control = 0.5 * (mse["control"]["control"] + mse["control"]["treatment"])
    combined_treatment = 0.5 * (mse["treatment"]["control"] + mse["treatment"]["treatment"])
    combined_ratio = combined_treatment / combined_control
    checks = {
        "opponent_heldout_ratio_max_0_90": opponent_ratio <= 0.90,
        "selfplay_heldout_ratio_max_1_10": selfplay_ratio <= 1.10,
        "equal_weight_combined_ratio_max_0_98": combined_ratio <= 0.98,
    }
    result = {
        "schema_version": "v5.ct002.mechanism_result.v1", "token": TOKEN,
        "mse_bb2": mse, "opponent_ratio": opponent_ratio,
        "selfplay_ratio": selfplay_ratio, "combined_ratio": combined_ratio,
        "checks": checks, "classification": "PASS_AUTHORIZE_MATCHED_STAGE_A_PPO_LATER_ONLY" if all(checks.values()) else "CT002_SCIENTIFIC_FAIL_MECHANISM_NO_PPO_NO_QUICK5K",
    }
    exclusive_json(OUTPUT_ROOT / "mechanism_result.json", result)
    return result


class AssignmentRandomFacade:
    """Drop-in facade for the clean trainer's only main-process random use."""
    def __init__(self, first_iteration: int):
        import random as stdlib_random
        self._stdlib = stdlib_random
        self._next_iteration = int(first_iteration)
        self._pending: dict[str, int | str] | None = None

    def seed(self, value: object = None) -> None:
        self._stdlib.seed(value)

    def random(self) -> float:
        if self._pending is not None:
            raise RuntimeError("assignment_random_reentered")
        assignment = ppo_assignment(self._next_iteration)
        if assignment["kind"] == "self":
            self._next_iteration += 1
        else:
            self._pending = assignment
        return (int(assignment["u64"]) + 0.5) / float(1 << 64)

    def randint(self, lower: int, upper: int) -> int:
        if (lower, upper) != (0, 4) or self._pending is None:
            raise RuntimeError("unexpected_assignment_randint")
        result = int(self._pending["local_index"])
        self._pending = None
        self._next_iteration += 1
        return result


def run_matched_ppo(arm: str) -> dict[str, Any]:
    if arm not in {"control", "treatment"}:
        raise RuntimeError("invalid_ppo_arm")
    if os.environ.get("CUDA_VISIBLE_DEVICES") != "0" or os.environ.get("CT002_DEVICE_MODE") != DEVICE_MODE_EXECUTION:
        raise RuntimeError("ppo_device_contract_mismatch")
    mechanism = json.loads((OUTPUT_ROOT / "mechanism_result.json").read_text(encoding="utf-8"))
    if mechanism.get("classification") != "PASS_AUTHORIZE_MATCHED_STAGE_A_PPO_LATER_ONLY":
        raise RuntimeError("mechanism_gate_not_pass")
    calibrated = OUTPUT_ROOT / arm / "calibrated.pt"
    run_dir = OUTPUT_ROOT / arm / "stage_a_5m"
    out = run_dir / "latest.pt"
    provenance = run_dir / "opponent_assignment_provenance.jsonl"
    if run_dir.exists():
        raise RuntimeError("ppo_output_collision")
    import multiprocessing as mp
    import train_v5_hybrid_h1 as clean_trainer

    original_random = clean_trainer.random
    original_argv = sys.argv[:]
    clean_trainer.random = AssignmentRandomFacade(SOURCE_ITERATION + 1)
    sys.argv = [
        str(CLEAN_SOURCES.keys().__iter__().__next__()),
        "--device", "cuda", "--workers", "22", "--hands-per-iter", "16384",
        "--total-hands", str(STAGE_A_TARGET_HANDS), "--starting-stack", "200",
        "--env-version", "v55", "--lr", "0.0003", "--ppo-epochs", "4",
        "--mini-batch-size", "1024", "--epsilon", "0", "--gamma", "0.999",
        "--delta1", "3", "--entropy-coef", "0.05", "--entropy-floor", "0.3",
        "--postflop-action-prior-coef", "0.02", "--postflop-action-prior-target", "0.15,0.30,0.52,0.03",
        "--preflop-action-prior-coef", "0.01", "--preflop-action-prior-target", "0.24,0.36,0.38,0.02",
        "--preflop-sb-open-action-prior-coef", "0", "--preflop-bb-vs-open-action-prior-coef", "0",
        "--k-best", "5", "--pool-strategy", "loss-kbest", "--pool-history-limit", "200",
        "--self-play-fraction", "0.2", "--opponent-assignment", "per-iteration",
        "--opponent-assignment-provenance-file", str(provenance),
        "--rollout-mode", "multi", "--rollout-envs-per-worker", "16",
        "--inference-min-batch-slots", "256", "--inference-batch-deadline-us", "1000",
        "--worker-seed-base", str(WORKER_SEED_BASE), "--fixed-training-deal-stream",
        "--mirror-self-play-deals", "--allin-runout-ev", "--allin-runout-ev-max-runouts", "200",
        "--critic-contract", "critic_v1", "--value-coef", "0.5",
        "--snapshot-every", "1000000", "--save-interval", "1",
        "--run-id", f"v5_ct002_{TOKEN}_{arm}_stage_a_5m", "--run-dir", str(run_dir), "--out", str(out),
        "--seed", str(PPO_SEED), "--max-runtime-seconds", "10800",
        "--resume", str(calibrated), "--allow-resume", "--no-reset-optimizer",
    ]
    try:
        try:
            mp.set_start_method("spawn")
        except RuntimeError:
            if mp.get_start_method() != "spawn":
                raise
        clean_trainer.main()
    finally:
        clean_trainer.random = original_random
        sys.argv = original_argv
    import torch
    endpoint = torch.load(out, map_location="cpu", weights_only=False)
    hands = int(endpoint.get("total_hands", -1))
    if not STAGE_A_TARGET_HANDS <= hands <= STAGE_A_TARGET_HANDS + STAGE_A_OVERSHOOT_MAX:
        raise RuntimeError("stage_a_endpoint_hand_count_mismatch")
    endpoint["ct002"] = {
        "registration_token": TOKEN, "preregistration_sha256": PREREG_SHA256,
        "source_checkpoint_sha256": SOURCE_SHA256, "arm": arm, "stage": "stage_a_5m",
        "mechanism_result_sha256": sha256_file(OUTPUT_ROOT / "mechanism_result.json"),
    }
    temporary = out.with_suffix(".ct002-finalizing.pt")
    with temporary.open("xb") as handle:
        torch.save(endpoint, handle)
    os.replace(temporary, out)
    result = {"arm": arm, "hands": hands, "iteration": int(endpoint["iteration"]), "checkpoint_sha256": sha256_file(out)}
    exclusive_json(run_dir / "ct002_endpoint.json", result)
    return result


def contract_probe(args: argparse.Namespace) -> dict[str, Any]:
    expected_nonce = PROBE_NONCES[args.arm]
    if os.environ.get("CUDA_VISIBLE_DEVICES") != "-1":
        raise RuntimeError("probe_cuda_visible_devices_mismatch")
    if os.environ.get("CT002_DEVICE_MODE") != DEVICE_MODE_PROBE:
        raise RuntimeError("probe_device_mode_mismatch")
    if os.environ.get("CT002_CONTRACT_NONCE") != expected_nonce or args.nonce != expected_nonce:
        raise RuntimeError("probe_nonce_mismatch")
    exact_path(args.preregistration, PREREG, "preregistration_arg", must_exist=True)
    exact_path(args.preregistration_audit, PREREG_AUDIT, "preregistration_audit_arg", must_exist=True)
    exact_path(args.source_checkpoint, SOURCE, "source_checkpoint_arg", must_exist=True)
    exact_path(args.output_root, OUTPUT_ROOT, "output_root_arg", must_exist=False)
    validate_registration_files()
    checkpoint, source_summary = inspect_source_checkpoint()
    import torch
    if torch.cuda.is_available():
        raise RuntimeError("probe_gpu_visible")
    if OUTPUT_ROOT.exists() or IMPLEMENTATION_AUDIT_RESULT.exists():
        raise RuntimeError("probe_registered_output_collision")
    return {
        "schema_version": "v5.ct002.contract_probe.v1", "token": TOKEN,
        "arm": args.arm, "nonce": args.nonce,
        "CUDA_VISIBLE_DEVICES": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "CT002_DEVICE_MODE": os.environ.get("CT002_DEVICE_MODE"),
        "CT002_CONTRACT_NONCE": os.environ.get("CT002_CONTRACT_NONCE"),
        "python_executable": str(Path(sys.executable).resolve()), "python_sha256": sha256_file(Path(sys.executable)),
        "torch_cuda_available": False, "source": source_summary,
        "optimizer_state_entries": len(checkpoint["optimizer"]["state"]),
        "deterministic_replay": {
            "deck0_sha256": hashlib.sha256(bytes(deterministic_deck(0))).hexdigest(),
            "hero_action_u64": action_u64("hero", 0, 0, 0),
            "control_row_key": row_key("control", "train", 0, 0, 0),
            "assignment_35052": ppo_assignment(35052),
        },
        "files_written": 0,
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Canonical CT002 ae78 clean-room runner")
    result.add_argument("--mode", required=True, choices=("contract-probe", "build-data", "calibrate", "mechanism", "ppo"))
    result.add_argument("--arm", choices=("control", "treatment"))
    result.add_argument("--nonce", default="")
    result.add_argument("--preregistration", required=True)
    result.add_argument("--preregistration-audit", required=True)
    result.add_argument("--source-checkpoint", required=True)
    result.add_argument("--output-root", required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    exact_path(args.preregistration, PREREG, "preregistration_arg", must_exist=True)
    exact_path(args.preregistration_audit, PREREG_AUDIT, "preregistration_audit_arg", must_exist=True)
    exact_path(args.source_checkpoint, SOURCE, "source_checkpoint_arg", must_exist=True)
    exact_path(args.output_root, OUTPUT_ROOT, "output_root_arg")
    if args.mode == "contract-probe":
        if args.arm is None:
            raise RuntimeError("contract_probe_arm_required")
        print(canonical_json(contract_probe(args)))
        return 0
    validate_registration_files()
    if args.mode == "build-data":
        if args.arm is not None:
            raise RuntimeError("build_data_forbids_arm_argument")
        print(canonical_json(build_datasets()))
        return 0
    if args.mode == "calibrate":
        if args.arm is None:
            raise RuntimeError("calibration_arm_required")
        print(canonical_json(calibrate(args.arm)))
        return 0
    if args.mode == "mechanism":
        if args.arm is not None:
            raise RuntimeError("mechanism_forbids_arm_argument")
        print(canonical_json(mechanism_gate()))
        return 0
    if args.mode == "ppo":
        if args.arm is None:
            raise RuntimeError("ppo_arm_required")
        print(canonical_json(run_matched_ppo(args.arm)))
        return 0
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
