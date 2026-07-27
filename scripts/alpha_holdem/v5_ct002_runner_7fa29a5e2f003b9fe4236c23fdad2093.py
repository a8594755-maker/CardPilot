"""CT002 corrected clean-room runner.

This file is intentionally self-contained around four frozen AlphaHoldem modules.
The contract-probe command is CPU-only and write-free.  Every other command is
fail-closed and writes only beneath the registered CT002 output root.
"""

from __future__ import annotations

import argparse
import base64
import copy
import gzip
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import struct
import sys
import time
import zlib

import numpy as np


ROOT = Path(r"C:\Users\a8594\CardPilot")
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

TOKEN = "7fa29a5e2f003b9fe4236c23fdad2093"
IDENTITY_SHA256 = "7fa29a5e2f003b9fe4236c23fdad20933388345b669b982437c570437cb480f1"
PREREGISTRATION = ROOT / "reports" / f"v5_ct002_corrected_preregistration_{TOKEN}_20260722.json"
PREREGISTRATION_SHA256 = "4c21f92dc37b668a57e850a07ab279ebe90f3115b22b7aff48f66b8f674ac1b2"
PREREGISTRATION_AUDIT = ROOT / "reports" / f"v5_ct002_corrected_preregistration_audit_{TOKEN}_20260722.json"
PREREGISTRATION_AUDIT_SHA256 = "7dc738ce349008fee8f08b79ffc3c094b314ed1f2280f70a62a6f93755b4233a"
OUTPUT_ROOT = ROOT / "models" / "alpha_holdem_v5_hybrid" / f"v5_ct002_{TOKEN}_20260722"
DATASET_ROOT = OUTPUT_ROOT / "calibration_data"
SOURCE_CHECKPOINT = ROOT / "models" / "alpha_holdem_v5_hybrid" / "v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715" / "latest.pt"
SOURCE_SHA256 = "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"
SOURCE_MODEL_SHA256 = "19bf761296f16758f74bad4bc98192b8954319fcbd2bc3bb174363ea21736b10"
SOURCE_ITERATION = 35051
SOURCE_HANDS = 576_021_901

DEAL_SEED = 2026072214
ACTION_SEED = 2026072215
SHUFFLE_SEED = 2026072216
TRAINING_SEED = 2026072217
WORKER_SEED_BASE = 84000
PROBE_NONCES = {
    "control_selfplay_calibration": 2026972214,
    "treatment_opponent_mix_calibration": 2027972214,
}
ARMS = tuple(PROBE_NONCES)
POOL_IDS = (103, 109, 115, 120, 129)
POOL_HASHES = {
    103: "cdec36f3deb27470a61c586b6491cd5de44aa3a99194b026a6e491a3121335a1",
    109: "aee38c625bf0faada6b163f23aeb4cc539d67f7cbe46dc234aa4f46b18960953",
    115: "ed92c7724486e446c13e5d4c623327d4288c68652964b7b4f35c0d2a7630d0c1",
    120: "86c3d7bacce72dd5749c21deaad3865c7313c9f118860cbc7e9b8b378070494e",
    129: "9d008780ac3cd259579131532df9775b53b4e3c95c7b0f12f2aac70bc915b255",
}
APPROVED_MODULES = {
    ROOT / "scripts" / "alpha_holdem" / "network_hybrid_h1.py": "25f4520d31f4ce5ffcfd23fc0d56b8736fd3b5fad537706b9cd13ee270b4a171",
    ROOT / "scripts" / "alpha_holdem" / "train_mp3_hybrid_h1.py": "69197b52baee7463d79e4a940f01f8bb241ed8e70975b51e043b99fd8a5cbc4d",
    ROOT / "scripts" / "alpha_holdem" / "environment_v55.py": "3ab591176a8119d21ac11e043bdfef72bd30b8842e34a9fea45cdd36b945f9de",
    ROOT / "scripts" / "alpha_holdem" / "train_v5_hybrid_h1.py": "91a98cec7677f4ee2ba74491f1be61ef2b3d4bfbb574b3615604d45f569d5591",
}

GAMMA = 0.999
TRAIN_ROWS = 250_000
HELDOUT_ROWS = 50_000
TRAIN_DEALS = range(0, 25_000)
HELDOUT_DEALS = range(25_000, 30_000)
MAX_DATASET_BYTES = 15_000_000_000
MAX_OUTPUT_BYTES = 100_000_000_000
VALUE_NAMES = ("value_head.weight", "value_head.bias")
PPO_TARGET_HANDS = 581_021_901
PPO_OVERSHOOT_MAX = 50_000
PPO_TARGET_KL = 0.03


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def atomic_json_new(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def state_dict_sha256(state: dict) -> str:
    """H4 tensor-state hash: sorted name, length-prefixed metadata, raw bytes."""
    digest = hashlib.sha256()
    for name in sorted(state):
        tensor = state[name].detach().cpu().contiguous()
        meta = json.dumps([name, str(tensor.dtype), list(tensor.shape)], separators=(",", ":"))
        meta_bytes = meta.encode("utf-8")
        digest.update(len(meta_bytes).to_bytes(8, "big"))
        digest.update(meta_bytes)
        digest.update(tensor.numpy().tobytes(order="C"))
    return digest.hexdigest()


def _hash_parts(*parts: object) -> bytes:
    return hashlib.sha256("|".join(str(part) for part in parts).encode("ascii")).digest()


def deterministic_deck(deal_index: int) -> list[int]:
    """SHA256-keyed unbiased Fisher-Yates deck for one registered deal index."""
    if deal_index < 0:
        raise ValueError("deal_index must be nonnegative")
    deck = list(range(52))
    counter = 0
    space = 1 << 256
    for i in range(51, 0, -1):
        bound = i + 1
        limit = space - (space % bound)
        while True:
            value = int.from_bytes(
                _hash_parts("CT002_DECK_V1", TOKEN, DEAL_SEED, deal_index, i, counter), "big"
            )
            counter += 1
            if value < limit:
                break
        j = value % bound
        deck[i], deck[j] = deck[j], deck[i]
    if sorted(deck) != list(range(52)):
        raise RuntimeError("deck permutation invariant failed")
    return deck


def action_u64(role: str, deal_index: int, hero_seat: int, decision_index: int) -> int:
    return int.from_bytes(
        _hash_parts(
            "CT002_ACTION_V1", TOKEN, ACTION_SEED, role, deal_index, hero_seat, decision_index
        )[:8],
        "big",
    )


def inverse_cdf_legal(probabilities: np.ndarray, legal_mask: np.ndarray, u64: int) -> int:
    legal = np.flatnonzero(np.asarray(legal_mask) > 0.0)
    if legal.size == 0:
        raise RuntimeError("no legal action")
    probs = np.asarray(probabilities, dtype=np.float64)[legal]
    if not np.isfinite(probs).all() or float(probs.sum()) <= 0.0:
        raise RuntimeError("invalid policy probabilities")
    probs /= probs.sum()
    draw = int(u64) / float(1 << 64)
    cumulative = 0.0
    for local_index, probability in zip(legal.tolist(), probs.tolist()):
        cumulative += probability
        if draw < cumulative:
            return int(local_index)
    return int(legal[-1])


def treatment_opponent_id(deal_index: int, hero_seat: int) -> int:
    return POOL_IDS[(int(deal_index) * 2 + int(hero_seat)) % len(POOL_IDS)]


def row_key(arm: str, split: str, deal_index: int, hero_seat: int, hero_decision: int) -> str:
    return hashlib.sha256(
        canonical_json(
            ["CT002_ROW_V1", TOKEN, arm, split, deal_index, hero_seat, hero_decision]
        ).encode("ascii")
    ).hexdigest()


def shuffle_key(epoch: int, key: str) -> str:
    return hashlib.sha256(
        canonical_json(["CT002_CALIBRATION_SHUFFLE_V1", TOKEN, SHUFFLE_SEED, epoch, key]).encode("ascii")
    ).hexdigest()


def ppo_assignment_u64(absolute_iteration: int) -> int:
    return int.from_bytes(
        _hash_parts(
            "CT002_PPO_ASSIGNMENT_V1", TOKEN, TRAINING_SEED, int(absolute_iteration)
        )[:8],
        "big",
    )


def ppo_assignment(absolute_iteration: int) -> dict:
    value = ppo_assignment_u64(absolute_iteration)
    space = 1 << 64
    self_width = space // 5
    if value < self_width:
        return {"absolute_iteration": int(absolute_iteration), "u64": value, "kind": "self", "member_id": None}
    member_index = ((value - self_width) * 5) // (space - self_width)
    return {
        "absolute_iteration": int(absolute_iteration),
        "u64": value,
        "kind": "pool",
        "member_id": POOL_IDS[min(int(member_index), 4)],
    }


def pack_observation(obs: dict) -> str:
    arrays = (
        np.asarray(obs["card_info"], dtype="<f4").reshape(6, 4, 13),
        np.asarray(obs["action_info"], dtype="<f4").reshape(25, 4, 5),
        np.asarray(obs["extra_info"], dtype="<f4").reshape(2),
        np.asarray(obs["legal_mask"], dtype="<f4").reshape(9),
    )
    raw = b"".join(array.tobytes(order="C") for array in arrays)
    return base64.b64encode(zlib.compress(raw, level=9)).decode("ascii")


def unpack_observation(blob: str) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    raw = zlib.decompress(base64.b64decode(blob.encode("ascii")))
    expected_floats = 6 * 4 * 13 + 25 * 4 * 5 + 2 + 9
    values = np.frombuffer(raw, dtype="<f4")
    if values.size != expected_floats:
        raise RuntimeError("observation payload size mismatch")
    cursor = 0
    card_n = 6 * 4 * 13
    action_n = 25 * 4 * 5
    card = values[cursor : cursor + card_n].reshape(6, 4, 13).copy()
    cursor += card_n
    action = values[cursor : cursor + action_n].reshape(25, 4, 5).copy()
    cursor += action_n
    extra = values[cursor : cursor + 2].copy()
    cursor += 2
    mask = values[cursor : cursor + 9].copy()
    return card, action, extra, mask


def _verify_static_inputs(*, include_checkpoint: bool) -> None:
    expected = {
        PREREGISTRATION: PREREGISTRATION_SHA256,
        PREREGISTRATION_AUDIT: PREREGISTRATION_AUDIT_SHA256,
        **APPROVED_MODULES,
    }
    if include_checkpoint:
        expected[SOURCE_CHECKPOINT] = SOURCE_SHA256
    for path, wanted in expected.items():
        if not path.is_file() or sha256_file(path) != wanted:
            raise RuntimeError(f"frozen input mismatch: {path}")


def _torch_modules():
    import torch
    from alpha_holdem.network_hybrid_h1 import AlphaHoldemNet
    import alpha_holdem.environment_v55 as environment_v55

    return torch, AlphaHoldemNet, environment_v55


def _new_model(torch, AlphaHoldemNet, device: str):
    model = AlphaHoldemNet(num_actions=9, critic_contract="critic_v1")
    # Lazy layers must be ordinary tensors because calibration subsequently
    # updates the value head; inference-mode construction makes them immutable.
    with torch.no_grad():
        model(
            torch.zeros((1, 6, 4, 13), dtype=torch.float32),
            torch.zeros((1, 25, 4, 5), dtype=torch.float32),
            torch.zeros((1, 2), dtype=torch.float32),
            torch.ones((1, 9), dtype=torch.float32),
        )
    return model.to(device)


def load_source_bundle(device: str, *, verify_file: bool = True):
    if verify_file:
        _verify_static_inputs(include_checkpoint=True)
    torch, AlphaHoldemNet, environment_v55 = _torch_modules()
    checkpoint = torch.load(SOURCE_CHECKPOINT, map_location="cpu", weights_only=False)
    required = {
        "iteration": SOURCE_ITERATION,
        "total_hands": SOURCE_HANDS,
        "env_version": "v55",
        "obs_version": "v55",
        "action_space_version": "9slot_v5",
        "critic_contract": "critic_v1",
    }
    for key, wanted in required.items():
        if checkpoint.get(key) != wanted:
            raise RuntimeError(f"source checkpoint {key} mismatch")
    if float(checkpoint.get("starting_stack_bb", -1.0)) != 200.0:
        raise RuntimeError("source starting stack mismatch")
    if state_dict_sha256(checkpoint["model"]) != SOURCE_MODEL_SHA256:
        raise RuntimeError("source model-state hash mismatch")
    snapshots = checkpoint.get("pool_snapshots") or []
    by_id = {int(snapshot["id"]): snapshot for snapshot in snapshots}
    if set(by_id) != set(POOL_IDS):
        raise RuntimeError("source frozen pool membership mismatch")
    for member_id in POOL_IDS:
        if state_dict_sha256(by_id[member_id]["state_dict"]) != POOL_HASHES[member_id]:
            raise RuntimeError(f"pool member {member_id} state mismatch")

    source_model = _new_model(torch, AlphaHoldemNet, device)
    source_model.load_state_dict(checkpoint["model"], strict=True)
    source_model.eval()
    pool_models = {}
    for member_id in POOL_IDS:
        model = _new_model(torch, AlphaHoldemNet, device)
        model.load_state_dict(by_id[member_id]["state_dict"], strict=True)
        model.eval()
        pool_models[member_id] = model
    return torch, environment_v55, checkpoint, source_model, pool_models


def _policy_probabilities(torch, model, obs: dict, device: str) -> np.ndarray:
    with torch.inference_mode():
        card = torch.from_numpy(np.asarray(obs["card_info"], dtype=np.float32)).unsqueeze(0).to(device)
        action = torch.from_numpy(np.asarray(obs["action_info"], dtype=np.float32)).unsqueeze(0).to(device)
        extra = torch.from_numpy(np.asarray(obs["extra_info"], dtype=np.float32)).unsqueeze(0).to(device)
        mask = torch.from_numpy(np.asarray(obs["legal_mask"], dtype=np.float32)).unsqueeze(0).to(device)
        logits, _ = model(card, action, extra, mask)
        return torch.softmax(logits.float(), dim=-1)[0].detach().cpu().numpy().astype(np.float64)


def _reset_with_deck(environment_v55, deck: list[int]):
    env = environment_v55.HUNLEnvironmentV55(starting_stack=200.0)
    state = environment_v55.HUNLGameState(config=env._make_config())
    state.hole_cards = [(deck[0], deck[1]), (deck[2], deck[3])]
    state.deck = list(reversed(deck[4:]))
    env.state = state
    env._legal_calls_this_hand = 0
    return env, env._get_obs()


def _play_hand(torch, environment_v55, source_model, pool_models, device: str, arm: str,
               deal_index: int, hero_seat: int, split: str) -> tuple[list[dict], dict]:
    deck = deterministic_deck(deal_index)
    env, obs = _reset_with_deck(environment_v55, deck)
    opponent_id = None if arm == ARMS[0] else treatment_opponent_id(deal_index, hero_seat)
    rows: list[dict] = []
    action_trace: list[dict] = []
    role_decisions = {"hero": 0, "opponent": 0}
    global_decision = 0
    done = False
    while not done:
        acting_player = int(obs["player"])
        is_hero = acting_player == hero_seat
        if is_hero:
            role = "shared_hero"
            model = source_model
            role_index = role_decisions["hero"]
            role_decisions["hero"] += 1
        else:
            role = "control_opponent" if arm == ARMS[0] else "treatment_opponent"
            model = source_model if opponent_id is None else pool_models[opponent_id]
            role_index = role_decisions["opponent"]
            role_decisions["opponent"] += 1
        u64 = action_u64(role, deal_index, hero_seat, role_index)
        probabilities = _policy_probabilities(torch, model, obs, device)
        action_index = inverse_cdf_legal(probabilities, obs["legal_mask"], u64)
        if is_hero:
            hero_decision = role_decisions["hero"] - 1
            rows.append({
                "row_key": row_key(arm, split, deal_index, hero_seat, hero_decision),
                "arm": arm,
                "split": split,
                "deal_index": int(deal_index),
                "hero_seat": int(hero_seat),
                "hero_decision": int(hero_decision),
                "global_decision": int(global_decision),
                "observation": pack_observation(obs),
                "action": int(action_index),
                "action_u64": int(u64),
            })
        action_trace.append({
            "global_decision": int(global_decision),
            "player": acting_player,
            "role": role,
            "role_decision": int(role_index),
            "action": int(action_index),
            "u64": int(u64),
        })
        obs, _, done = env.step(action_index)
        global_decision += 1
        if global_decision > 1000:
            raise RuntimeError("hand decision ceiling exceeded")
    profit = float(env.state.payoff(hero_seat))
    for row in rows:
        remaining = (global_decision - 1) - int(row["global_decision"])
        row["target_bb"] = float((GAMMA ** remaining) * profit)
        del row["global_decision"]
    manifest = {
        "arm": arm,
        "split": split,
        "deal_index": int(deal_index),
        "hero_seat": int(hero_seat),
        "opponent_id": opponent_id,
        "deck_sha256": hashlib.sha256(bytes(deck)).hexdigest(),
        "terminal_profit_bb": profit,
        "row_keys": [row["row_key"] for row in rows],
        "actions": action_trace,
    }
    return rows, manifest


def _tree_bytes(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _write_gzip_line(handle, payload: dict) -> None:
    handle.write(canonical_json(payload) + "\n")


def build_data() -> dict:
    _require_device("CUDA_SINGLE_GPU_SEQUENTIAL_NO_FALLBACK", gpu=True)
    _verify_static_inputs(include_checkpoint=True)
    if OUTPUT_ROOT.exists():
        raise RuntimeError("registered output root already exists; overwrite and repair are forbidden")
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=False)
    DATASET_ROOT.mkdir(exist_ok=False)
    started = time.time()
    torch, environment_v55, checkpoint, source_model, pool_models = load_source_bundle("cuda", verify_file=False)
    prefix_root = DATASET_ROOT / "raw_prefix"
    prefix_root.mkdir()
    all_summaries = {}
    try:
        for arm in ARMS:
            arm_root = DATASET_ROOT / arm
            arm_root.mkdir()
            all_summaries[arm] = {}
            for split, deal_range, required_rows in (
                ("train", TRAIN_DEALS, TRAIN_ROWS),
                ("heldout", HELDOUT_DEALS, HELDOUT_ROWS),
            ):
                split_prefix = prefix_root / arm / split
                split_prefix.mkdir(parents=True)
                shard_handles = [
                    gzip.open(split_prefix / f"{index:02x}.jsonl.gz", "xt", encoding="utf-8", newline="\n")
                    for index in range(256)
                ]
                hand_path = arm_root / f"{split}_hands.jsonl.gz"
                row_count = 0
                hand_count = 0
                try:
                    with gzip.open(hand_path, "xt", encoding="utf-8", newline="\n") as hand_handle:
                        for deal_index in deal_range:
                            for hero_seat in (0, 1):
                                rows, manifest = _play_hand(
                                    torch, environment_v55, source_model, pool_models, "cuda",
                                    arm, deal_index, hero_seat, split,
                                )
                                _write_gzip_line(hand_handle, manifest)
                                hand_count += 1
                                for row in rows:
                                    _write_gzip_line(shard_handles[int(row["row_key"][:2], 16)], row)
                                    row_count += 1
                            if time.time() - started > 14_400:
                                raise RuntimeError("combined data-generation wall ceiling exceeded")
                            if _tree_bytes(OUTPUT_ROOT) > MAX_DATASET_BYTES:
                                raise RuntimeError("combined dataset byte ceiling exceeded")
                finally:
                    for handle in shard_handles:
                        handle.close()
                if row_count < required_rows:
                    raise RuntimeError(f"{arm}/{split} row shortfall {row_count} < {required_rows}")
                selected_path = arm_root / f"{split}_rows.jsonl.gz"
                selected = 0
                last_key = None
                with gzip.open(selected_path, "xt", encoding="utf-8", newline="\n") as out_handle:
                    for shard_path in sorted(split_prefix.glob("*.jsonl.gz")):
                        with gzip.open(shard_path, "rt", encoding="utf-8") as in_handle:
                            shard_rows = [json.loads(line) for line in in_handle]
                        shard_rows.sort(key=lambda row: row["row_key"])
                        for row in shard_rows:
                            if selected >= required_rows:
                                break
                            if row["row_key"] == last_key:
                                raise RuntimeError("duplicate row key")
                            _write_gzip_line(out_handle, row)
                            last_key = row["row_key"]
                            selected += 1
                        if selected >= required_rows:
                            break
                if selected != required_rows:
                    raise RuntimeError("exact selected-row count invariant failed")
                raw_shards = [
                    {"path": str(path), "sha256": sha256_file(path), "bytes": path.stat().st_size}
                    for path in sorted(split_prefix.glob("*.jsonl.gz"))
                ]
                all_summaries[arm][split] = {
                    "hands": hand_count,
                    "raw_rows": row_count,
                    "selected_rows": selected,
                    "rows_path": str(selected_path),
                    "rows_sha256": sha256_file(selected_path),
                    "hands_path": str(hand_path),
                    "hands_sha256": sha256_file(hand_path),
                    "raw_prefix_shards": raw_shards,
                }
        manifest = {
            "schema_version": "v5.ct002.calibration_dataset.v1",
            "identity_sha256": IDENTITY_SHA256,
            "registration_sha256": PREREGISTRATION_SHA256,
            "source_checkpoint_sha256": SOURCE_SHA256,
            "deal_seed": DEAL_SEED,
            "action_seed": ACTION_SEED,
            "gamma": GAMMA,
            "arms": all_summaries,
            "combined_bytes": _tree_bytes(DATASET_ROOT),
            "wall_seconds": time.time() - started,
            "status": "DATA_GENERATION_COMPLETE_AUDIT_REQUIRED",
        }
        if manifest["combined_bytes"] > MAX_DATASET_BYTES:
            raise RuntimeError("final dataset byte ceiling exceeded")
        atomic_json_new(DATASET_ROOT / "manifest.json", manifest)
        return manifest
    except Exception as exc:
        failure = {
            "schema_version": "v5.ct002.data_failure.v1",
            "identity_sha256": IDENTITY_SHA256,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "wall_seconds": time.time() - started,
            "classification": "INCONCLUSIVE_STOP_NO_REPAIR_IN_PLACE",
        }
        try:
            atomic_json_new(OUTPUT_ROOT / "data_failure.json", failure)
        except FileExistsError:
            pass
        raise


def _read_rows(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


def _batch_from_rows(torch, rows: list[dict], device: str):
    unpacked = [unpack_observation(row["observation"]) for row in rows]
    cards = torch.from_numpy(np.stack([item[0] for item in unpacked])).to(device)
    actions = torch.from_numpy(np.stack([item[1] for item in unpacked])).to(device)
    extras = torch.from_numpy(np.stack([item[2] for item in unpacked])).to(device)
    masks = torch.from_numpy(np.stack([item[3] for item in unpacked])).to(device)
    targets = torch.tensor([row["target_bb"] for row in rows], dtype=torch.float32, device=device)
    return cards, actions, extras, masks, targets


def _non_value_state(state: dict) -> dict:
    return {name: tensor for name, tensor in state.items() if name not in VALUE_NAMES}


def _zero_value_optimizer_moments(torch, optimizer_state: dict, model) -> tuple[dict, list[int]]:
    transformed = copy.deepcopy(optimizer_state)
    named_parameters = list(model.named_parameters())
    flat_ids = [item for group in transformed["param_groups"] for item in group["params"]]
    if len(flat_ids) != len(named_parameters):
        raise RuntimeError("optimizer/model parameter mapping mismatch")
    value_ids = []
    for state_id, (name, _) in zip(flat_ids, named_parameters):
        if name in VALUE_NAMES:
            value_ids.append(int(state_id))
            for key, value in transformed["state"][state_id].items():
                if key in ("exp_avg", "exp_avg_sq", "max_exp_avg_sq"):
                    value.zero_()
    if len(value_ids) != 2:
        raise RuntimeError("value-head optimizer mapping mismatch")
    return transformed, value_ids


def _policy_logits(torch, model, rows: list[dict], device: str) -> list[bytes]:
    result = []
    model.eval()
    with torch.inference_mode():
        for start in range(0, len(rows), 256):
            cards, actions, extras, masks, _ = _batch_from_rows(torch, rows[start : start + 256], device)
            logits, _ = model(cards, actions, extras, masks)
            result.append(logits.detach().cpu().contiguous().numpy().tobytes())
    return result


def _require_dataset_audit() -> dict:
    manifest_path = DATASET_ROOT / "manifest.json"
    audit_path = DATASET_ROOT / "independent_audit.json"
    if not manifest_path.is_file() or not audit_path.is_file():
        raise RuntimeError("independent dataset audit is required before calibration")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit.get("status") != "PASS" or audit.get("manifest_sha256") != sha256_file(manifest_path):
        raise RuntimeError("independent dataset audit identity mismatch")
    return audit


def calibrate(arm: str) -> dict:
    _require_device("CUDA_SINGLE_GPU_SEQUENTIAL_NO_FALLBACK", gpu=True)
    _verify_static_inputs(include_checkpoint=True)
    _require_dataset_audit()
    if arm not in ARMS:
        raise ValueError("unknown arm")
    out_dir = OUTPUT_ROOT / "calibrated" / arm
    if out_dir.exists():
        raise RuntimeError("calibration arm output already exists")
    out_dir.mkdir(parents=True, exist_ok=False)
    started = time.time()
    torch, _, source_checkpoint, source_model, _ = load_source_bundle("cuda", verify_file=False)
    train_rows = _read_rows(DATASET_ROOT / arm / "train_rows.jsonl.gz")
    if len(train_rows) != TRAIN_ROWS:
        raise RuntimeError("calibration train row count mismatch")
    source_state = copy.deepcopy(source_checkpoint["model"])
    source_non_value_hash = state_dict_sha256(_non_value_state(source_state))
    for name, parameter in source_model.named_parameters():
        parameter.requires_grad_(name in VALUE_NAMES)
    source_model.eval()
    optimizer = torch.optim.Adam(
        [parameter for name, parameter in source_model.named_parameters() if name in VALUE_NAMES],
        lr=1e-4,
    )
    updates = 0
    losses = []
    for epoch in range(4):
        ordered = sorted(train_rows, key=lambda row: shuffle_key(epoch, row["row_key"]))
        for start in range(0, TRAIN_ROWS, 1000):
            batch = ordered[start : start + 1000]
            cards, actions, extras, masks, targets = _batch_from_rows(torch, batch, "cuda")
            _, values = source_model(cards, actions, extras, masks)
            loss = torch.mean((values.squeeze(-1) - targets) ** 2)
            if not torch.isfinite(loss):
                raise RuntimeError("non-finite calibration loss")
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            updates += 1
            losses.append(float(loss.detach().cpu().item()))
        if time.time() - started > 3600:
            raise RuntimeError("calibration wall ceiling exceeded")
    if updates != 1000:
        raise RuntimeError("exact calibration update count mismatch")
    calibrated_state = source_model.state_dict()
    if state_dict_sha256(_non_value_state(calibrated_state)) != source_non_value_hash:
        raise RuntimeError("actor or non-value buffer changed during calibration")
    probe_rows = sorted(
        _read_rows(DATASET_ROOT / ARMS[0] / "heldout_rows.jsonl.gz")
        + _read_rows(DATASET_ROOT / ARMS[1] / "heldout_rows.jsonl.gz"),
        key=lambda row: row["row_key"],
    )[:4096]
    baseline = _new_model(torch, type(source_model), "cuda")
    baseline.load_state_dict(source_state)
    if _policy_logits(torch, baseline, probe_rows, "cuda") != _policy_logits(torch, source_model, probe_rows, "cuda"):
        raise RuntimeError("4096-row policy-logit bitwise identity gate failed")
    transformed_optimizer, value_optimizer_ids = _zero_value_optimizer_moments(
        torch, source_checkpoint["optimizer"], source_model
    )
    dataset_manifest = DATASET_ROOT / "manifest.json"
    checkpoint_payload = copy.deepcopy(source_checkpoint)
    checkpoint_payload["model"] = {name: tensor.detach().cpu() for name, tensor in calibrated_state.items()}
    checkpoint_payload["optimizer"] = transformed_optimizer
    checkpoint_payload["ct002"] = {
        "schema_version": "v5.ct002.calibrated_checkpoint.v1",
        "identity_sha256": IDENTITY_SHA256,
        "registration_sha256": PREREGISTRATION_SHA256,
        "source_checkpoint_sha256": SOURCE_SHA256,
        "dataset_manifest_sha256": sha256_file(dataset_manifest),
        "dataset_audit_sha256": sha256_file(DATASET_ROOT / "independent_audit.json"),
        "arm": arm,
        "trainable_names": list(VALUE_NAMES),
        "updates": updates,
        "shuffle_seed": SHUFFLE_SEED,
        "actor_non_value_state_sha256": source_non_value_hash,
        "value_head_state_sha256": state_dict_sha256({name: calibrated_state[name] for name in VALUE_NAMES}),
        "optimizer_transform": "SOURCE_EXACT_ZERO_VALUE_HEAD_EXP_AVG_AND_EXP_AVG_SQ_ONLY",
        "value_optimizer_state_ids": value_optimizer_ids,
        "loss_first": losses[0],
        "loss_last": losses[-1],
    }
    checkpoint_path = out_dir / "calibrated.pt"
    torch.save(checkpoint_payload, checkpoint_path)
    result = {
        **checkpoint_payload["ct002"],
        "checkpoint_path": str(checkpoint_path),
        "checkpoint_sha256": sha256_file(checkpoint_path),
        "wall_seconds": time.time() - started,
        "status": "CALIBRATION_COMPLETE_MECHANISM_REQUIRED",
    }
    atomic_json_new(out_dir / "result.json", result)
    return result


def _heldout_mse(torch, model, rows: list[dict], device: str) -> float:
    squared_error = 0.0
    count = 0
    model.eval()
    with torch.inference_mode():
        for start in range(0, len(rows), 1000):
            cards, actions, extras, masks, targets = _batch_from_rows(torch, rows[start : start + 1000], device)
            _, values = model(cards, actions, extras, masks)
            squared_error += float(torch.sum((values.squeeze(-1) - targets) ** 2).cpu().item())
            count += int(targets.numel())
    return squared_error / count


def mechanism() -> dict:
    _require_device("CUDA_SINGLE_GPU_SEQUENTIAL_NO_FALLBACK", gpu=True)
    _verify_static_inputs(include_checkpoint=True)
    _require_dataset_audit()
    result_path = OUTPUT_ROOT / "mechanism_result.json"
    if result_path.exists():
        raise RuntimeError("mechanism result already exists")
    torch, AlphaHoldemNet, _ = _torch_modules()
    models = {}
    checkpoint_hashes = {}
    for arm in ARMS:
        path = OUTPUT_ROOT / "calibrated" / arm / "calibrated.pt"
        result = json.loads((path.parent / "result.json").read_text(encoding="utf-8"))
        if result.get("checkpoint_sha256") != sha256_file(path):
            raise RuntimeError("calibrated checkpoint result mismatch")
        payload = torch.load(path, map_location="cpu", weights_only=False)
        meta = payload.get("ct002") or {}
        if meta.get("identity_sha256") != IDENTITY_SHA256 or meta.get("arm") != arm:
            raise RuntimeError("calibrated checkpoint identity mismatch")
        model = _new_model(torch, AlphaHoldemNet, "cuda")
        model.load_state_dict(payload["model"])
        model.eval()
        models[arm] = model
        checkpoint_hashes[arm] = sha256_file(path)
    rows = {
        arm: _read_rows(DATASET_ROOT / arm / "heldout_rows.jsonl.gz") for arm in ARMS
    }
    mse = {
        model_arm: {data_arm: _heldout_mse(torch, models[model_arm], rows[data_arm], "cuda") for data_arm in ARMS}
        for model_arm in ARMS
    }
    control, treatment = ARMS
    opponent_ratio = mse[treatment][treatment] / mse[control][treatment]
    selfplay_ratio = mse[treatment][control] / mse[control][control]
    combined_ratio = (
        0.5 * (mse[treatment][treatment] + mse[treatment][control])
        / (0.5 * (mse[control][treatment] + mse[control][control]))
    )
    passed = opponent_ratio <= 0.90 and selfplay_ratio <= 1.10 and combined_ratio <= 0.98
    result = {
        "schema_version": "v5.ct002.mechanism.v1",
        "identity_sha256": IDENTITY_SHA256,
        "registration_sha256": PREREGISTRATION_SHA256,
        "checkpoint_sha256": checkpoint_hashes,
        "mse": mse,
        "ratios": {
            "opponent_treatment_over_control": opponent_ratio,
            "selfplay_treatment_over_control": selfplay_ratio,
            "equal_weight_treatment_over_control": combined_ratio,
        },
        "thresholds": {"opponent_max": 0.90, "selfplay_max": 1.10, "equal_weight_max": 0.98},
        "status": "PASS" if passed else "CT002_SCIENTIFIC_FAIL_MECHANISM_NO_PPO_NO_QUICK5K",
        "ppo_authority": "MATCHED_STAGE_A_LATER_ONLY" if passed else "NONE",
    }
    atomic_json_new(result_path, result)
    return result


class _AssignmentRandomProxy:
    """Proxy the trainer random module while replacing only per-iteration assignment draws."""

    def __init__(self, module, start_iteration: int, pool_local_index: dict[int, int]):
        self._module = module
        self._iteration = int(start_iteration)
        self._pool_local_index = dict(pool_local_index)
        self._pending = None

    def __getattr__(self, name):
        return getattr(self._module, name)

    def random(self):
        if self._pending is not None:
            raise RuntimeError("assignment random called before pending pool selection consumed")
        assignment = ppo_assignment(self._iteration)
        if assignment["kind"] == "self":
            self._iteration += 1
            return 0.0
        self._pending = assignment
        return 0.5

    def randint(self, lower: int, upper: int):
        if self._pending is None or (lower, upper) != (0, 4):
            raise RuntimeError("unexpected trainer assignment randint contract")
        result = self._pool_local_index[int(self._pending["member_id"])]
        self._pending = None
        self._iteration += 1
        return result


def ppo_arguments(arm: str, resume: Path, run_dir: Path, out: Path, provenance: Path) -> list[str]:
    return [
        "train_v5_hybrid_h1.py", "--device", "cuda", "--workers", "22",
        "--hands-per-iter", "16384", "--total-hands", str(PPO_TARGET_HANDS),
        "--starting-stack", "200", "--env-version", "v55", "--lr", "0.0003",
        "--ppo-epochs", "4", "--mini-batch-size", "1024", "--epsilon", "0",
        "--gamma", "0.999", "--delta1", "3", "--entropy-coef", "0.05",
        "--entropy-floor", "0.3", "--postflop-action-prior-coef", "0.02",
        "--postflop-action-prior-target", "0.15,0.30,0.52,0.03",
        "--preflop-action-prior-coef", "0.01", "--preflop-action-prior-target", "0.24,0.36,0.38,0.02",
        "--preflop-sb-open-action-prior-coef", "0", "--preflop-bb-vs-open-action-prior-coef", "0",
        "--k-best", "5", "--pool-strategy", "loss-kbest", "--self-play-fraction", "0.2",
        "--opponent-assignment", "per-iteration", "--opponent-assignment-provenance-file", str(provenance),
        "--rollout-mode", "multi", "--rollout-envs-per-worker", "16",
        "--inference-min-batch-slots", "256", "--inference-batch-deadline-us", "1000",
        "--worker-seed-base", str(WORKER_SEED_BASE), "--fixed-training-deal-stream",
        "--mirror-self-play-deals", "--allin-runout-ev", "--allin-runout-ev-max-runouts", "200",
        "--critic-contract", "critic_v1", "--value-coef", "0.5", "--snapshot-every", "1000000000",
        "--save-interval", "1", "--run-id", f"ct002_{TOKEN}_{arm}", "--run-dir", str(run_dir),
        "--out", str(out), "--seed", str(TRAINING_SEED), "--max-runtime-seconds", "10800",
        "--resume", str(resume), "--allow-resume", "--no-reset-optimizer",
    ]


def run_ppo(arm: str) -> dict:
    _require_device("CUDA_SINGLE_GPU_SEQUENTIAL_NO_FALLBACK", gpu=True)
    _verify_static_inputs(include_checkpoint=True)
    if arm not in ARMS:
        raise ValueError("unknown arm")
    mechanism_path = OUTPUT_ROOT / "mechanism_result.json"
    mechanism_result = json.loads(mechanism_path.read_text(encoding="utf-8"))
    if mechanism_result.get("status") != "PASS" or mechanism_result.get("identity_sha256") != IDENTITY_SHA256:
        raise RuntimeError("mechanism PASS is required before PPO")
    arm_root = OUTPUT_ROOT / "stage_a_ppo" / arm
    if arm_root.exists():
        raise RuntimeError("PPO arm output already exists")
    arm_root.mkdir(parents=True, exist_ok=False)
    calibrated = OUTPUT_ROOT / "calibrated" / arm / "calibrated.pt"
    raw_out = arm_root / "trainer_latest.pt"
    final_out = arm_root / "latest.pt"
    provenance = arm_root / "assignment_provenance.jsonl"
    trainer = importlib.import_module("alpha_holdem.train_v5_hybrid_h1")
    pool_order = [109, 115, 120, 129, 103]
    trainer.random = _AssignmentRandomProxy(
        trainer.random, SOURCE_ITERATION + 1, {member_id: pool_order.index(member_id) for member_id in POOL_IDS}
    )
    approved_ppo = trainer.trinal_clip_ppo_update

    def exact_ppo(*args, **kwargs):
        kwargs["target_kl"] = PPO_TARGET_KL
        kwargs["value_head_catchup"] = True
        kwargs["value_head_catchup_loss"] = "mse"
        kwargs["value_head_catchup_smooth_l1_beta"] = 1.0
        return approved_ppo(*args, **kwargs)

    trainer.trinal_clip_ppo_update = exact_ppo
    argv_before = sys.argv
    sys.argv = ppo_arguments(arm, calibrated, arm_root, raw_out, provenance)
    try:
        trainer.main()
    finally:
        sys.argv = argv_before
    torch, _, _ = _torch_modules()
    payload = torch.load(raw_out, map_location="cpu", weights_only=False)
    hands = int(payload.get("total_hands", -1))
    if not PPO_TARGET_HANDS <= hands <= PPO_TARGET_HANDS + PPO_OVERSHOOT_MAX:
        raise RuntimeError("PPO endpoint hand-count gate failed")
    if payload.get("env_version") != "v55" or payload.get("critic_contract") != "critic_v1":
        raise RuntimeError("PPO endpoint environment or critic contract mismatch")
    provenance_lines = provenance.read_text(encoding="utf-8").splitlines()
    if not provenance_lines:
        raise RuntimeError("assignment provenance is empty")
    for line in provenance_lines:
        record = json.loads(line)
        iteration = int(record["applies_to_iteration"])
        expected = ppo_assignment(iteration)
        assignments = {int(value) for value in record["assignments"]}
        expected_local = -1 if expected["kind"] == "self" else pool_order.index(expected["member_id"])
        if assignments != {expected_local}:
            raise RuntimeError(f"assignment provenance mismatch at iteration {iteration}")
    payload["ct002"] = {
        "schema_version": "v5.ct002.stage_a_checkpoint.v1",
        "identity_sha256": IDENTITY_SHA256,
        "registration_sha256": PREREGISTRATION_SHA256,
        "arm": arm,
        "source_checkpoint_sha256": SOURCE_SHA256,
        "calibrated_checkpoint_sha256": sha256_file(calibrated),
        "mechanism_result_sha256": sha256_file(mechanism_path),
        "assignment_rule": "CT002_PPO_ASSIGNMENT_V1_ABSOLUTE_ITERATION",
        "assignment_provenance_sha256": sha256_file(provenance),
        "target_kl": PPO_TARGET_KL,
        "value_head_catchup_after_kl_stop": True,
        "catchup_loss": "mse",
    }
    torch.save(payload, final_out)
    result = {
        **payload["ct002"],
        "checkpoint_path": str(final_out),
        "checkpoint_sha256": sha256_file(final_out),
        "total_hands": hands,
        "iteration": int(payload["iteration"]),
        "status": "STAGE_A_PPO_COMPLETE_QUICK5K_REQUIRED_AFTER_BOTH_ARMS",
    }
    atomic_json_new(arm_root / "result.json", result)
    if _tree_bytes(OUTPUT_ROOT) > MAX_OUTPUT_BYTES:
        raise RuntimeError("CT002 output byte ceiling exceeded")
    return result


def _require_device(expected_mode: str, *, gpu: bool) -> None:
    if os.environ.get("CT002_IDENTITY_TOKEN") != TOKEN:
        raise RuntimeError("CT002 identity token mismatch")
    if os.environ.get("CT002_DEVICE_MODE") != expected_mode:
        raise RuntimeError("CT002 device mode mismatch")
    visible = os.environ.get("CUDA_VISIBLE_DEVICES")
    wanted = "0" if gpu else "-1"
    if visible != wanted:
        raise RuntimeError(f"CUDA_VISIBLE_DEVICES must be {wanted}")
    if gpu:
        import torch
        if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
            raise RuntimeError("exactly one CUDA device is required")


def contract_probe(arm: str, nonce: int) -> dict:
    _require_device("CPU_ONLY_NO_GPU_NO_OUTPUT", gpu=False)
    if arm not in ARMS or int(nonce) != PROBE_NONCES[arm]:
        raise RuntimeError("contract probe arm or nonce mismatch")
    if os.environ.get("CT002_PROBE_NONCE") != str(nonce):
        raise RuntimeError("child-observed probe nonce mismatch")
    _verify_static_inputs(include_checkpoint=True)
    import torch
    if torch.cuda.is_available() or torch.cuda.device_count() != 0:
        raise RuntimeError("CPU-only probe observed a Torch CUDA device")
    checkpoint = torch.load(SOURCE_CHECKPOINT, map_location="cpu", weights_only=False)
    if state_dict_sha256(checkpoint["model"]) != SOURCE_MODEL_SHA256:
        raise RuntimeError("probe source model identity mismatch")
    pool = {int(item["id"]): item for item in checkpoint["pool_snapshots"]}
    observed = {str(member_id): state_dict_sha256(pool[member_id]["state_dict"]) for member_id in POOL_IDS}
    if observed != {str(key): value for key, value in POOL_HASHES.items()}:
        raise RuntimeError("probe pool identity mismatch")
    replay = {
        "deck_0_sha256": hashlib.sha256(bytes(deterministic_deck(0))).hexdigest(),
        "deck_29999_sha256": hashlib.sha256(bytes(deterministic_deck(29999))).hexdigest(),
        "hero_action_u64": action_u64("shared_hero", 17, 1, 3),
        "treatment_member": treatment_opponent_id(17, 1),
        "row_key": row_key(arm, "heldout", 29999, 1, 7),
        "assignment_35052": ppo_assignment(35052),
    }
    return {
        "schema_version": "v5.ct002.contract_probe.v1",
        "status": "PASS",
        "identity_sha256": IDENTITY_SHA256,
        "token": TOKEN,
        "arm": arm,
        "nonce": int(nonce),
        "device_mode": os.environ["CT002_DEVICE_MODE"],
        "cuda_visible_devices": os.environ["CUDA_VISIBLE_DEVICES"],
        "torch_cuda_available": False,
        "source_checkpoint_sha256": SOURCE_SHA256,
        "source_model_state_sha256": SOURCE_MODEL_SHA256,
        "pool_state_sha256": observed,
        "replay": replay,
        "files_written": 0,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Registered CT002 corrected clean-room runner")
    subparsers = parser.add_subparsers(dest="command", required=True)
    probe = subparsers.add_parser("contract-probe")
    probe.add_argument("--arm", choices=ARMS, required=True)
    probe.add_argument("--nonce", type=int, required=True)
    subparsers.add_parser("build-data")
    calibration = subparsers.add_parser("calibrate")
    calibration.add_argument("--arm", choices=ARMS, required=True)
    subparsers.add_parser("mechanism")
    ppo_parser = subparsers.add_parser("ppo")
    ppo_parser.add_argument("--arm", choices=ARMS, required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.command == "contract-probe":
        result = contract_probe(args.arm, args.nonce)
    elif args.command == "build-data":
        result = build_data()
    elif args.command == "calibrate":
        result = calibrate(args.arm)
    elif args.command == "mechanism":
        result = mechanism()
    elif args.command == "ppo":
        result = run_ppo(args.arm)
    else:
        raise AssertionError(args.command)
    print(canonical_json(result))


if __name__ == "__main__":
    main()
