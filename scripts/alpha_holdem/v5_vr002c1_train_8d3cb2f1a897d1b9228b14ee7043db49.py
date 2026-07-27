#!/usr/bin/env python3
"""VR002C1: frozen-H11 faithful Q-boost-core training window.

This is intentionally a small, fresh trainer.  It reuses only immutable LG003C1
environment/deal/assignment/pool utilities; rollout transport, generation
admission, actor update, Q update, evidence, and checkpoint namespaces are
implemented here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import multiprocessing as mp
import os
import random
import sys
import time
from datetime import datetime, timezone
from multiprocessing import shared_memory
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.distributions import Categorical

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from alpha_holdem.environment import NUM_ACTIONS
from alpha_holdem.network_hybrid_h1 import AlphaHoldemNet, CRITIC_V1
from alpha_holdem.train_mp3_hybrid_h1 import compute_gae
from alpha_holdem import v5_lg003c1_train_8bf8cedf78b6e8c8fe153802908ed893 as parent
from alpha_holdem import v5_vr002c1_qboost_core_8d3cb2f1a897d1b9228b14ee7043db49 as qcore


VR002_TOKEN = "8d3cb2f1a897d1b9228b14ee7043db49"
VR002_IDENTITY = "8d3cb2f1a897d1b9228b14ee7043db496c7a319c4af7318aae4e0103ac534a4d"
VR002_PREREG_SHA256 = "a0a9ff27017257a27cad92bacf2a69f64a1442b218495a3d6d6a76ea7244948e"
VR002_SOURCE_SHA256 = parent.LG003_SOURCE_SHA256
VR002_PARENT_TRAINER_SHA256 = "f841144c883d51e66a1d2de889e15303e7339695c8664f81e60208ff77770452"
VR002_SOURCE_HANDS = 576_021_901
VR002_TARGET_HANDS = 581_021_901
VR002_Q_INIT_SEED = 2026072302
VR002_Q_MINIBATCH_SEED = 2026072303
VR002_ACTOR_GENERATION_INITIAL = 35051
VR002_POOL_IDS = parent.LG003_CHECKPOINT_ORDER
VR002_POOL_HASHES = {
    109: "aee38c625bf0faada6b163f23aeb4cc539d67f7cbe46dc234aa4f46b18960953",
    115: "ed92c7724486e446c13e5d4c623327d4288c68652964b7b4f35c0d2a7630d0c1",
    120: "86c3d7bacce72dd5749c21deaad3865c7313c9f118860cbc7e9b8b378070494e",
    129: "9d008780ac3cd259579131532df9775b53b4e3c95c7b0f12f2aac70bc915b255",
    103: "cdec36f3deb27470a61c586b6491cd5de44aa3a99194b026a6e491a3121335a1",
}

CARD_SIZE = 6 * 4 * 13
ACTION_SIZE = 25 * 4 * 5
EXTRA_SIZE = 2
MASK_SIZE = NUM_ACTIONS
OBS_SIZE = CARD_SIZE + ACTION_SIZE + EXTRA_SIZE + MASK_SIZE
RESULT_SIZE = 13
TRACE_AGGREGATE_SCHEMA = "v5.vr002.trace_aggregate.v1"
IDLE, WAITING, READY = 0, 1, 2
HERO_MODEL_ID = -1


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def canonical_sha(record: dict) -> str:
    return hashlib.sha256(
        json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def append_jsonl(path: Path, record: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(record)
    payload["record_sha256"] = canonical_sha(payload)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
        f.flush()
        os.fsync(f.fileno())
    return payload["record_sha256"]


def inherited_absolute_progress_lr(total_hands: int, target_hands: int, base_lr: float) -> float:
    """Bit-for-formula parent schedule: base LR, then linear decay to base/3."""
    progress = float(total_hands) / float(target_hands)
    if progress < 0.5:
        return float(base_lr)
    decay_fraction = (progress - 0.5) / 0.5
    return float(base_lr) * (1 - decay_fraction * (1 - 1 / 3))


def atomic_torch_save(payload: dict, destination: Path) -> None:
    temporary = destination.with_name(destination.name + ".tmp")
    torch.save(payload, temporary)
    os.replace(temporary, destination)


def action_repr(action) -> dict:
    if action is None:
        raise RuntimeError("VR002 forbids a null/passive-fallback action")
    kind = getattr(getattr(action, "type", None), "name", str(getattr(action, "type", None)))
    return {"type": kind, "amount": float(getattr(action, "amount", 0.0))}


def compact_public(state, active: int, hero: int, assignment_local: int) -> dict:
    street = getattr(state.street, "name", str(state.street)).lower()
    street_index = {"preflop": 0, "flop": 1, "turn": 2, "river": 3}.get(street)
    if street_index is None:
        try:
            street_index = int(state.street)
        except Exception as exc:
            raise RuntimeError(f"unknown street {state.street!r}") from exc
    return {
        "active_stack": float(state.stacks[active]),
        "other_stack": float(state.stacks[1 - active]),
        "pot": float(state.pot),
        "active_street_commit": float(state.street_committed[active]),
        "other_street_commit": float(state.street_committed[1 - active]),
        "to_call": float(max(0.0, state.street_committed[1 - active] - state.street_committed[active])),
        "last_bet_size": float(state.last_bet_size),
        "raise_count": int(state.raise_count),
        "num_actions_this_street": int(state.num_actions_this_street),
        "street": int(street_index),
        "active_absolute_seat": int(active),
        "hero_absolute_seat": int(hero),
        "assignment_local": int(assignment_local),
    }


def hand_digest(packet: dict) -> str:
    h = hashlib.sha256()
    packet_header = {
        "hand_uid": packet["hand_uid"], "worker_id": packet["worker_id"],
        "env_id": packet["env_id"], "deal_identity": packet["deal_identity"],
        "hero_seat": packet["hero_seat"],
        "assignment_local": packet["assignment_local"],
        "assignment_member_id": packet["assignment_member_id"],
        "assignment_version": packet["assignment_version"],
        "training_reward": packet["training_reward"],
        "realized_payoff": packet["realized_payoff"],
    }
    h.update(json.dumps(packet_header, sort_keys=True, separators=(",", ":")).encode())
    for row in packet["rows"]:
        for field in ("card", "action_info", "extra", "legal", "pi_ref"):
            h.update(field.encode())
            h.update(np.asarray(row[field], np.float32).tobytes())
        scalar_payload = {
            "uid": row["uid"], "step_index": row["step_index"],
            "active": row["active"], "request_model": row["request_model"],
            "request_model_local": row["request_model_local"],
            "assignment_version": row["assignment_version"],
            "other_hole": list(row["other_hole"]), "public": row["public"],
            "action": row["action"], "engine_action": row["engine_action"],
            "old_log_prob": row["old_log_prob"], "legacy_value": row["legacy_value"],
            "generation": row["generation"], "done": row["done"],
            "next_uid": row["next_uid"], "training_reward": row["training_reward"],
            "realized_payoff": row["realized_payoff"],
        }
        h.update(json.dumps(scalar_payload, sort_keys=True, separators=(",", ":")).encode())
    return h.hexdigest()


def sampled_raw_hand(hand: dict, admitted: bool) -> dict:
    """Compact deterministic raw-row evidence; private state remains hash-only."""
    evidence = []
    for row in hand["rows"]:
        state_hash = hashlib.sha256()
        for value in (row["card"], row["action_info"], row["extra"]):
            state_hash.update(np.asarray(value, np.float32).tobytes())
        state_hash.update(np.asarray(row["other_hole"], np.int16).tobytes())
        state_hash.update(
            json.dumps(row["public"], sort_keys=True, separators=(",", ":")).encode()
        )
        item = {
            "uid": row["uid"], "step_index": row["step_index"],
            "active_absolute_seat": row["active"],
            "request_model_id": row["request_model"],
            "request_model_local_index": row["request_model_local"],
            "assignment_version": row["assignment_version"],
            "actor_generation": row["generation"], "selected_action": row["action"],
            "legal9": np.asarray(row["legal"], np.float32).tolist(),
            "pi_ref9": np.asarray(row["pi_ref"], np.float32).tolist(),
            "old_log_probability": row["old_log_prob"],
            "legacy_scalar_value": row["legacy_value"],
            "engine_action": row["engine_action"], "done": row["done"],
            "next_uid": row["next_uid"], "training_reward": row["training_reward"],
            "realized_payoff": row["realized_payoff"],
            "state_payload_sha256": state_hash.hexdigest(),
            "card6_sha256": hashlib.sha256(
                np.asarray(row["card"], np.float32).tobytes()
            ).hexdigest(),
            "action25_sha256": hashlib.sha256(
                np.asarray(row["action_info"], np.float32).tobytes()
            ).hexdigest(),
            "extra2_sha256": hashlib.sha256(
                np.asarray(row["extra"], np.float32).tobytes()
            ).hexdigest(),
            "other_hole_public_sha256": hashlib.sha256(
                (
                    json.dumps(list(row["other_hole"]), separators=(",", ":"))
                    + json.dumps(row["public"], sort_keys=True, separators=(",", ":"))
                ).encode()
            ).hexdigest(),
        }
        item["row_payload_sha256"] = canonical_sha(item)
        evidence.append(item)
    return {
        "hand_uid": hand["hand_uid"], "admitted": bool(admitted),
        "hand_digest": hand["hand_digest"], "rows": evidence,
    }


def worker_process(
    worker_id, envs_per_worker, run_id, obs_name, result_name, status_name,
    assigned_name, assignment_version_name, request_name, pipe, stop_event,
    worker_seed, starting_stack,
    fixed_deals, mirror_deals, allin_ev, allin_max_runouts,
):
    """Collect complete chronological hands; incomplete hands never cross the pipe."""
    import random as _random
    from multiprocessing import shared_memory as _shm
    from alpha_holdem.environment_v55 import HUNLEnvironment

    _random.seed(worker_seed)
    np.random.seed(worker_seed % (2**32))
    m = int(envs_per_worker)
    base = int(worker_id) * m
    obs_shm = _shm.SharedMemory(name=obs_name)
    result_shm = _shm.SharedMemory(name=result_name)
    status_shm = _shm.SharedMemory(name=status_name)
    assigned_shm = _shm.SharedMemory(name=assigned_name)
    assignment_version_shm = _shm.SharedMemory(name=assignment_version_name)
    request_shm = _shm.SharedMemory(name=request_name)
    obs_buf = np.ndarray((m, OBS_SIZE), np.float32, obs_shm.buf, offset=base * OBS_SIZE * 4)
    result_buf = np.ndarray((m, RESULT_SIZE), np.float32, result_shm.buf, offset=base * RESULT_SIZE * 4)
    status_buf = np.ndarray((m,), np.int32, status_shm.buf, offset=base * 4)
    assigned_buf = np.ndarray((1,), np.int32, assigned_shm.buf, offset=worker_id * 4)
    assignment_version_buf = np.ndarray(
        (1,), np.int64, assignment_version_shm.buf, offset=worker_id * 8
    )
    request_buf = np.ndarray((m,), np.int32, request_shm.buf, offset=base * 4)

    class Slot:
        pass

    slots, completed = [], []
    metrics = parent.exp003_metrics_template()

    def start_hand(e: int):
        s = slots[e]
        if s.mirror_deck is not None:
            s.assignment = HERO_MODEL_ID
            s.obs = parent.exp003_reset_env_with_deck(s.env, s.mirror_deck)
            s.deal_identity = s.mirror_identity
            s.mirror_deck = s.mirror_identity = None
            metrics["mirror_replay_hands"] += 1
        else:
            while True:
                version_before = int(assignment_version_buf[0])
                if version_before <= 0:
                    time.sleep(0.000001)
                    continue
                assignment = int(assigned_buf[0])
                version_after = int(assignment_version_buf[0])
                if version_before == version_after:
                    break
            s.assignment = assignment
            s.assignment_version = version_after
            if fixed_deals:
                di = s.deal_index
                s.obs = parent.exp003_reset_env_with_deck(
                    s.env, parent.fixed_training_deck(worker_seed, e, di)
                )
                s.deal_index += 1
                s.deal_identity = f"w{worker_id}:e{e}:d{di}"
            else:
                s.obs = s.env.reset()
                s.deal_identity = f"w{worker_id}:e{e}:runtime{s.hands_played}"
            if mirror_deals and s.assignment == HERO_MODEL_ID:
                deck = parent.exp003_mirrored_deck_from_env(s.env)
                if deck is not None:
                    s.mirror_deck = deck
                    s.mirror_identity = s.deal_identity + ":mirror"
                    metrics["mirror_source_hands"] += 1
        s.hero_seat = s.hands_played % 2
        s.rows, s.pending, s.last_actor, s.terminal_reward = [], None, None, 0.0

    def submit(e: int):
        s, o = slots[e], slots[e].obs
        active = int(o["player"])
        is_self = s.assignment == HERO_MODEL_ID
        req_local = HERO_MODEL_ID if is_self or active == s.hero_seat else s.assignment
        req_member = (
            HERO_MODEL_ID
            if req_local == HERO_MODEL_ID
            else int(VR002_POOL_IDS[req_local])
        )
        ci = np.asarray(o["card_info"], np.float32).reshape(-1)
        ai = np.asarray(o["action_info"], np.float32).reshape(-1)
        ei = np.asarray(o["extra_info"], np.float32).reshape(-1)
        lm = np.asarray(o["legal_mask"], np.float32).reshape(-1)
        if lm.shape != (9,) or not np.any(lm > 0):
            raise RuntimeError("invalid legal mask")
        engine_action_table = s.env.last_action_table
        state = s.env.state
        other_hole = tuple(int(c) for c in state.hole_cards[1 - active])
        row = obs_buf[e]
        row[:CARD_SIZE] = ci
        row[CARD_SIZE:CARD_SIZE + ACTION_SIZE] = ai
        row[CARD_SIZE + ACTION_SIZE:CARD_SIZE + ACTION_SIZE + EXTRA_SIZE] = ei
        row[-MASK_SIZE:] = lm
        s.pending = {
            "active": active, "request_model": int(req_member),
            "request_model_local": int(req_local),
            "assignment_version": int(s.assignment_version), "card": ci.copy(),
            "action_info": ai.copy(), "extra": ei.copy(), "legal": lm.copy(),
            "other_hole": other_hole, "public": compact_public(
                state, active, s.hero_seat, s.assignment
            ), "action_table": engine_action_table,
        }
        request_buf[e] = req_local
        status_buf[e] = WAITING

    def finish_hand(e: int):
        s = slots[e]
        if not s.rows or s.last_actor is None:
            raise RuntimeError("terminal hand has no physical action")
        train = [0.0, 0.0]
        train[s.last_actor] = float(s.terminal_reward)
        train[1 - s.last_actor] = -float(s.terminal_reward)
        realized = [float(s.env.state.payoff(0)), float(s.env.state.payoff(1))]
        if not math.isclose(train[0] + train[1], 0.0, abs_tol=1e-12):
            raise RuntimeError("training reward is not zero-sum")
        for i, row in enumerate(s.rows):
            row["done"] = bool(i == len(s.rows) - 1)
            row["next_uid"] = None if row["done"] else s.rows[i + 1]["uid"]
            row["training_reward"] = train if row["done"] else [0.0, 0.0]
            row["realized_payoff"] = realized if row["done"] else [0.0, 0.0]
        packet = {
            "type": "hand", "hand_uid": f"{run_id}|{worker_id}|{e}|{s.deal_identity}",
            "worker_id": int(worker_id), "env_id": int(e),
            "deal_identity": s.deal_identity, "hero_seat": int(s.hero_seat),
            "assignment_local": int(s.assignment),
            "assignment_member_id": (
                None if s.assignment == HERO_MODEL_ID else int(VR002_POOL_IDS[s.assignment])
            ),
            "assignment_version": int(s.assignment_version),
            "rows": s.rows, "training_reward": train, "realized_payoff": realized,
        }
        packet["hand_digest"] = hand_digest(packet)
        completed.append(packet)
        s.hands_played += 1

    try:
        for e in range(m):
            s = Slot()
            s.env = HUNLEnvironment(starting_stack=starting_stack)
            s.hands_played = s.deal_index = 0
            s.mirror_deck = s.mirror_identity = None
            slots.append(s)
            start_hand(e)
            submit(e)
        while not stop_event.is_set():
            progressed = False
            for e, s in enumerate(slots):
                if status_buf[e] != READY:
                    continue
                progressed = True
                action = int(result_buf[e, 0])
                lp, legacy = float(result_buf[e, 1]), float(result_buf[e, 2])
                pi_ref = np.asarray(result_buf[e, 3:12], np.float32).copy()
                generation = int(result_buf[e, 12])
                status_buf[e] = IDLE
                pending, s.pending = s.pending, None
                lm = pending["legal"]
                if not 0 <= action < 9 or lm[action] <= 0:
                    raise RuntimeError("served action is illegal")
                if np.any(np.abs(pi_ref[lm <= 0]) > 1e-7):
                    raise RuntimeError("serving policy has illegal mass")
                if not math.isclose(float(pi_ref[lm > 0].sum()), 1.0, rel_tol=0, abs_tol=2e-6):
                    raise RuntimeError("serving policy legal mass != 1")
                if not math.isclose(lp, math.log(max(float(pi_ref[action]), 1e-30)), abs_tol=2e-6):
                    raise RuntimeError("chosen log probability does not match pi_ref")
                engine_action = pending.pop("action_table")[action]
                if engine_action is None:
                    raise RuntimeError("legal slot maps to null action")
                step_index = len(s.rows)
                pending.update({
                    "uid": f"{run_id}|{worker_id}|{e}|{s.deal_identity}|{step_index}",
                    "step_index": step_index, "action": action, "engine_action": action_repr(engine_action),
                    "old_log_prob": lp, "legacy_value": legacy, "pi_ref": pi_ref,
                    "generation": generation,
                })
                s.rows.append(pending)
                s.last_actor = pending["active"]
                pre_board = tuple(s.env.state.board) if allin_ev else None
                obs, reward, done = s.env.step(action)
                if done and allin_ev:
                    ev = parent.exp003_allin_ev_reward(
                        s.env.state, s.last_actor, pre_board, allin_max_runouts
                    )
                    if ev is not None:
                        reward, runouts, skipped = ev
                        if skipped:
                            metrics["allin_ev_skipped_hands"] += 1
                            metrics["allin_ev_skipped_runouts"] += int(runouts)
                        else:
                            metrics["allin_ev_replacements"] += 1
                            metrics["allin_ev_runouts"] += int(runouts)
                if done:
                    s.terminal_reward = float(reward)
                    finish_hand(e)
                    if len(completed) >= 50:
                        pipe.send({"type": "hand_batch", "hands": completed, "exp003": metrics})
                        completed, metrics = [], parent.exp003_metrics_template()
                    start_hand(e)
                else:
                    s.obs = obs
                submit(e)
            if not progressed:
                time.sleep(0.000001)
        if completed:
            pipe.send({"type": "hand_batch", "hands": completed, "exp003": metrics})
        pipe.send(None)
    finally:
        for shm in (
            obs_shm, result_shm, status_shm, assigned_shm,
            assignment_version_shm, request_shm,
        ):
            shm.close()


@torch.no_grad()
def run_inference(model, opponents, obs_np, result_np, status_np, request_np,
                  slots: int, device: str, generation: int, batch_log: list[int]) -> int:
    waiting = np.flatnonzero(status_np == WAITING)
    if waiting.size == 0:
        return 0
    view = obs_np.reshape(slots, OBS_SIZE)
    total = 0
    for mid in np.unique(request_np[waiting]):
        selected = waiting[request_np[waiting] == mid]
        actor = model if int(mid) == HERO_MODEL_ID else opponents[int(mid)]
        if actor.training:
            raise RuntimeError("inference requires frozen eval-mode actor/pool model")
        batch = torch.from_numpy(np.ascontiguousarray(view[selected])).to(device)
        cards = batch[:, :CARD_SIZE].view(-1, 6, 4, 13)
        actions = batch[:, CARD_SIZE:CARD_SIZE + ACTION_SIZE].view(-1, 25, 4, 5)
        extras = batch[:, CARD_SIZE + ACTION_SIZE:CARD_SIZE + ACTION_SIZE + 2]
        masks = batch[:, -9:]
        logits, values = actor(cards, actions, extras, masks)
        probs = F.softmax(logits, dim=-1)
        dist = Categorical(probs)
        sampled = dist.sample()
        out = result_np.reshape(slots, RESULT_SIZE)
        out[selected, 0] = sampled.cpu().numpy()
        out[selected, 1] = dist.log_prob(sampled).cpu().numpy()
        out[selected, 2] = values.squeeze(-1).cpu().numpy()
        out[selected, 3:12] = probs.cpu().numpy()
        out[selected, 12] = generation if int(mid) == HERO_MODEL_ID else -1
        status_np[selected] = READY
        batch_log.append(int(selected.size))
        total += int(selected.size)
    return total


def public_state(row):
    return qcore.PublicState(**row["public"])


def decode_row(row):
    compact = qcore.CompactCentralState.from_arrays(
        actor_card6=np.asarray(row["card"], np.float32).reshape(6, 4, 13),
        actor_action25=np.asarray(row["action_info"], np.float32).reshape(25, 4, 5),
        other_hole_cards=row["other_hole"],
        legal_mask=np.asarray(row["legal"], np.float32),
        public=public_state(row),
    )
    cards, actions, public_two, legal = compact.decode_focal_views()
    return (
        np.asarray(cards, np.float32), np.asarray(actions, np.float32),
        np.asarray(public_two, np.float32), np.asarray(legal, np.float32),
    )


def validate_hand_packet(hand: dict) -> None:
    rows = hand.get("rows") or []
    if not rows or hand_digest(hand) != hand.get("hand_digest"):
        raise RuntimeError("hand packet missing rows or digest mismatch")
    assignment_local = int(hand["assignment_local"])
    assignment_version = int(hand["assignment_version"])
    if assignment_local not in (HERO_MODEL_ID, 0, 1, 2, 3, 4) or assignment_version <= 0:
        raise RuntimeError("hand assignment slot/version contract failed")
    expected_member = (
        None if assignment_local == HERO_MODEL_ID
        else int(VR002_POOL_IDS[assignment_local])
    )
    if hand["assignment_member_id"] != expected_member:
        raise RuntimeError("hand assignment member mapping failed")
    expected_reward = np.asarray(hand["training_reward"], np.float64)
    if expected_reward.shape != (2,) or not math.isclose(
        float(expected_reward.sum()), 0.0, abs_tol=1e-12
    ):
        raise RuntimeError("hand terminal training reward contract failed")
    for index, row in enumerate(rows):
        expected_uid = (
            f'{hand["hand_uid"]}|{index}'
        )
        # hand_uid already ends at deal_identity, so the row form is exact.
        if row["step_index"] != index or row["uid"] != expected_uid:
            raise RuntimeError("hand UID/step chronology failed")
        final = index == len(rows) - 1
        if bool(row["done"]) != final:
            raise RuntimeError("hand done markers failed")
        if row["next_uid"] != (None if final else rows[index + 1]["uid"]):
            raise RuntimeError("hand successor link failed")
        reward = np.asarray(row["training_reward"], np.float64)
        if not np.array_equal(reward, expected_reward if final else np.zeros(2)):
            raise RuntimeError("hand reward placement failed")
        legal = np.asarray(row["legal"], np.float32)
        action = int(row["action"])
        if legal.shape != (9,) or not 0 <= action < 9 or legal[action] != 1:
            raise RuntimeError("hand selected-action legality failed")
        local = int(row["request_model_local"])
        member = int(row["request_model"])
        expected_request_member = (
            HERO_MODEL_ID if local == HERO_MODEL_ID else int(VR002_POOL_IDS[local])
        )
        if (
            local not in (HERO_MODEL_ID, 0, 1, 2, 3, 4)
            or member != expected_request_member
            or int(row["assignment_version"]) != assignment_version
            or int(row["public"]["assignment_local"]) != assignment_local
        ):
            raise RuntimeError("row request-member/assignment-version contract failed")
        qcore.validate_serving_policy(
            row["pi_ref"], legal, selected_slot=action,
            old_log_probability=row["old_log_prob"], atol=2e-6,
        )
        cards, actions, public_two, sidecar = decode_row(row)
        if (
            cards.shape != (7, 4, 13) or actions.shape != (25, 4, 5)
            or public_two.shape != (2, 22) or sidecar.shape != (9,)
        ):
            raise RuntimeError("hand two-focal CENTRAL895 decode failed")


def flatten_hands(hands):
    rows, spans = [], []
    for hand in hands:
        start = len(rows)
        rows.extend(hand["rows"])
        spans.append((start, len(rows), hand))
    return rows, spans


@torch.no_grad()
def evaluate_q_and_pi(model, q_model, rows, device, batch_size=512):
    n = len(rows)
    q_all = np.empty((n, 2, 9), np.float32)
    pi_all = np.stack([np.asarray(r["pi_ref"], np.float32) for r in rows])
    model.eval()
    q_model.eval()
    hero_idx = [i for i, r in enumerate(rows) if r["request_model"] == HERO_MODEL_ID]
    for start in range(0, len(hero_idx), 1024):
        idx = hero_idx[start:start + 1024]
        cards = torch.tensor(np.stack([rows[i]["card"].reshape(6, 4, 13) for i in idx]), device=device)
        actions = torch.tensor(np.stack([rows[i]["action_info"].reshape(25, 4, 5) for i in idx]), device=device)
        extras = torch.tensor(np.stack([rows[i]["extra"] for i in idx]), device=device)
        masks = torch.tensor(np.stack([rows[i]["legal"] for i in idx]), device=device)
        logits, _ = model(cards, actions, extras, masks)
        pi_all[idx] = F.softmax(logits, dim=-1).cpu().numpy()
    for start in range(0, n, batch_size):
        chunk = rows[start:start + batch_size]
        decoded = [decode_row(r) for r in chunk]
        cards = torch.tensor(np.stack([x[0] for x in decoded]), device=device)
        actions = torch.tensor(np.stack([x[1] for x in decoded]), device=device)
        public = torch.tensor(np.stack([x[2] for x in decoded]), device=device)
        q_all[start:start + len(chunk)] = q_model.forward_two_focal(
            cards, actions, public
        ).cpu().numpy()
    return q_all, pi_all


def calculate_rollout(model, q_model, hands, device):
    rows, spans = flatten_hands(hands)
    q_values, policies = evaluate_q_and_pi(model, q_model, rows, device)
    actor_adv, q_targets = {}, np.empty((len(rows), 2), np.float32)
    for start, end, hand in spans:
        rr = rows[start:end]
        actions = torch.tensor([r["action"] for r in rr], dtype=torch.long)
        rewards = torch.tensor(
            [r["training_reward"] for r in rr], dtype=torch.float32
        )
        dones = torch.tensor([r["done"] for r in rr], dtype=torch.float32)
        result = qcore.expected_sarsa_qboost(
            torch.tensor(q_values[start:end]), torch.tensor(policies[start:end]),
            actions, rewards, dones, gamma=0.999, lam=0.95,
            legal_masks=torch.tensor(
                np.stack([r["legal"] for r in rr]), dtype=torch.float32
            ),
        )
        q_targets[start:end] = result["q_target"].cpu().numpy()
        boost = result["advantage"].cpu().numpy()
        for local, row in enumerate(rr):
            if row["request_model"] == HERO_MODEL_ID:
                actor_adv[row["uid"]] = float(boost[local, row["active"]])
    return rows, spans, q_values, policies, actor_adv, q_targets


def legacy_advantages(hands) -> dict[str, float]:
    result = {}
    for hand in hands:
        for seat in (0, 1):
            own = [
                r for r in hand["rows"]
                if r["active"] == seat and r["request_model"] == HERO_MODEL_ID
            ]
            if not own:
                continue
            rewards = np.zeros(len(own), np.float64)
            rewards[-1] = float(hand["training_reward"][seat])
            values = np.asarray([r["legacy_value"] for r in own], np.float64)
            dones = np.zeros(len(own), np.float64)
            dones[-1] = 1.0
            adv, _ = compute_gae(rewards, values, dones, gamma=0.999, lam=0.95)
            result.update({row["uid"]: float(a) for row, a in zip(own, adv)})
    return result


def prior_loss(probs, masks, cards, actions, args):
    class_mass = torch.stack((probs[:, 0], probs[:, 1], probs[:, 2:8].sum(-1), probs[:, 8]), -1)
    class_legal = torch.stack((
        masks[:, 0] > 0, masks[:, 1] > 0, masks[:, 2:8].sum(-1) > 0, masks[:, 8] > 0
    ), -1)
    post = cards[:, 4].sum((1, 2)) > 1e-6
    total = probs.new_zeros(())
    for row_mask, target, coef in (
        (post, (0.0, 0.0, 1.0, 0.0), args.postflop_action_prior_coef),
        (~post, (0.30, 0.25, 0.43, 0.02), args.preflop_action_prior_coef),
    ):
        if coef <= 0 or not bool(row_mask.any()):
            continue
        target_t = probs.new_tensor(target)[None, :] * class_legal.float()
        denom = target_t.sum(-1, keepdim=True)
        valid = row_mask & (denom.squeeze(-1) > 1e-8)
        if bool(valid.any()):
            normalized = target_t[valid] / denom[valid].clamp_min(1e-8)
            total = total + float(coef) * -(normalized * class_mass[valid].clamp_min(1e-8).log()).sum(-1).mean()
    return total


def actor_epoch(model, optimizer, rows, advantages, q_values, device, args):
    actor_indices = [
        i for i, r in enumerate(rows) if r["request_model"] == HERO_MODEL_ID
    ]
    actor_rows = [rows[i] for i in actor_indices]
    values = np.asarray([advantages[r["uid"]] for r in actor_rows], np.float32)
    values = (values - values.mean()) / (values.std(ddof=0) + 1e-8)
    actor_q = np.stack([
        q_values[i, int(rows[i]["active"])] for i in actor_indices
    ]).astype(np.float32, copy=False)
    cards = torch.tensor(np.stack([r["card"].reshape(6, 4, 13) for r in actor_rows]), device=device)
    actions = torch.tensor(np.stack([r["action_info"].reshape(25, 4, 5) for r in actor_rows]), device=device)
    extras = torch.tensor(np.stack([r["extra"] for r in actor_rows]), device=device)
    masks = torch.tensor(np.stack([r["legal"] for r in actor_rows]), device=device)
    q_targets = torch.tensor(actor_q, device=device)
    acts = torch.tensor([r["action"] for r in actor_rows], dtype=torch.long, device=device)
    old_lp = torch.tensor([r["old_log_prob"] for r in actor_rows], device=device)
    adv = torch.tensor(values, device=device)
    order = torch.randperm(len(actor_rows), device=device)
    model.train()
    totals = {
        "policy_loss": 0.0,
        "entropy": 0.0,
        "approx_kl": 0.0,
        "q_guidance_loss": 0.0,
        "q_soft_ce": 0.0,
        "q_margin_loss": 0.0,
        "q_guidance_eligible_fraction": 0.0,
        "q_target_raise_rate": 0.0,
        "minibatches": 0,
    }
    for start in range(0, len(actor_rows), args.mini_batch_size):
        idx = order[start:start + args.mini_batch_size]
        logits, _ = model(cards[idx], actions[idx], extras[idx], masks[idx])
        probs = F.softmax(logits, -1)
        dist = Categorical(probs)
        new_lp = dist.log_prob(acts[idx])
        ratio = torch.exp(new_lp - old_lp[idx])
        clipped = ratio.clamp(0.8, 1.2)
        unclipped = torch.where(adv[idx] < 0, ratio.clamp(max=args.delta1), ratio)
        policy = -torch.min(unclipped * adv[idx], clipped * adv[idx]).mean()
        entropy = dist.entropy().mean()
        entropy_coef = args.entropy_coef * (5.0 if float(entropy.detach()) < args.entropy_floor else 1.0)
        loss = policy - entropy_coef * entropy
        loss = loss + prior_loss(probs, masks[idx], cards[idx], actions[idx], args)

        q_guidance = logits.new_zeros(())
        q_soft_ce = logits.new_zeros(())
        q_margin_loss = logits.new_zeros(())
        eligible_fraction = logits.new_zeros(())
        target_raise_rate = logits.new_zeros(())
        if args.q_guidance_coef > 0.0:
            legal = masks[idx] > 0
            q_legal = q_targets[idx].masked_fill(~legal, -torch.inf)
            top2 = q_legal.topk(k=2, dim=-1).values
            q_gap = top2[:, 0] - top2[:, 1]
            eligible = torch.isfinite(q_gap) & (q_gap >= args.q_guidance_min_gap)
            eligible_fraction = eligible.float().mean()
            if bool(eligible.any()):
                centered_q = q_legal - top2[:, :1]
                target_probs = F.softmax(
                    centered_q / args.q_guidance_temperature, dim=-1
                ).detach()
                row_ce = -(
                    target_probs * F.log_softmax(logits, dim=-1)
                ).sum(dim=-1)
                confidence = (
                    q_gap / max(args.q_guidance_min_gap, 1e-6)
                ).clamp(min=1.0, max=4.0) / 4.0
                weights = confidence[eligible]
                q_soft_ce = (
                    row_ce[eligible] * weights
                ).sum() / weights.sum().clamp_min(1e-6)

                best = q_legal.argmax(dim=-1)
                best_logits = logits.gather(1, best[:, None]).squeeze(1)
                competitors = logits.masked_fill(~legal, -torch.inf)
                competitors = competitors.scatter(
                    1, best[:, None], torch.full_like(best[:, None], -torch.inf, dtype=logits.dtype)
                )
                second_logits = competitors.max(dim=-1).values
                row_margin = F.relu(
                    args.q_guidance_margin - (best_logits - second_logits)
                )
                q_margin_loss = (
                    row_margin[eligible] * weights
                ).sum() / weights.sum().clamp_min(1e-6)
                q_guidance = 0.5 * q_soft_ce + q_margin_loss
                target_raise_rate = (
                    ((best >= 2) & (best <= 7) & eligible).float().sum()
                    / eligible.float().sum().clamp_min(1.0)
                )
                loss = loss + args.q_guidance_coef * q_guidance

        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        nn.utils.clip_grad_norm_(
            [p for p in model.parameters() if p.requires_grad], args.max_grad_norm
        )
        optimizer.step()
        totals["policy_loss"] += float(policy.detach())
        totals["entropy"] += float(entropy.detach())
        totals["approx_kl"] += float((old_lp[idx] - new_lp).mean().detach())
        totals["q_guidance_loss"] += float(q_guidance.detach())
        totals["q_soft_ce"] += float(q_soft_ce.detach())
        totals["q_margin_loss"] += float(q_margin_loss.detach())
        totals["q_guidance_eligible_fraction"] += float(eligible_fraction.detach())
        totals["q_target_raise_rate"] += float(target_raise_rate.detach())
        totals["minibatches"] += 1
    n = max(totals["minibatches"], 1)
    return {k: (v / n if k != "minibatches" else v) for k, v in totals.items()}


def critic_update(q_model, q_optimizer, q_generator, rows, targets, device, args):
    before = {k: v.detach().cpu().clone() for k, v in q_model.state_dict().items()}
    losses, grad_norms = [], []
    q_model.train()
    for _ in range(4):
        order = torch.randperm(len(rows), generator=q_generator).tolist()
        for start in range(0, len(rows), 512):
            idx = order[start:start + 512]
            decoded = [decode_row(rows[i]) for i in idx]
            cards = torch.tensor(np.stack([x[0] for x in decoded]), device=device)
            actions = torch.tensor(np.stack([x[1] for x in decoded]), device=device)
            public = torch.tensor(np.stack([x[2] for x in decoded]), device=device)
            selected = torch.tensor([rows[i]["action"] for i in idx], dtype=torch.long, device=device)
            target = torch.tensor(targets[idx], device=device)
            q = q_model.forward_two_focal(cards, actions, public)
            chosen = q.gather(2, selected[:, None, None].expand(-1, 2, 1)).squeeze(-1)
            loss = 0.5 * F.mse_loss(chosen, target)
            q_optimizer.zero_grad(set_to_none=True)
            loss.backward()
            norm = nn.utils.clip_grad_norm_(q_model.parameters(), 0.5)
            q_optimizer.step()
            losses.append(float(loss.detach()))
            grad_norms.append(float(norm))
    delta = math.sqrt(sum(
        float(((v.detach().cpu() - before[k]).double() ** 2).sum())
        for k, v in q_model.state_dict().items() if torch.is_floating_point(v)
    ))
    return {"q_loss": float(np.mean(losses)), "q_grad_norm": float(np.mean(grad_norms)), "q_parameter_delta": delta}


def tensor_state_equal(a, b) -> bool:
    return a.keys() == b.keys() and all(
        torch.equal(a[k].detach().cpu(), b[k].detach().cpu()) for k in a
    )


def optimizer_state_for_names(optimizer, model, names):
    named = dict(model.named_parameters())
    result = {}
    for name in names:
        result[name] = {}
        for key, value in optimizer.state.get(named[name], {}).items():
            result[name][key] = value.detach().cpu().clone() if torch.is_tensor(value) else value
    return result


def nested_state_equal(a, b):
    if a.keys() != b.keys():
        return False
    for name in a:
        if a[name].keys() != b[name].keys():
            return False
        for key, value in a[name].items():
            other = b[name][key]
            if torch.is_tensor(value):
                if not torch.equal(value, other):
                    return False
            elif value != other:
                return False
    return True


def run_update(model, optimizer, q_model, q_optimizer, q_generator, hands, device, args):
    rows, _, q_values, _, first_adv, _ = calculate_rollout(model, q_model, hands, device)
    legacy = legacy_advantages(hands)
    uids = sorted(first_adv)
    if set(uids) != set(legacy):
        raise RuntimeError("paired actor UID set mismatch")
    av = np.asarray([first_adv[u] for u in uids], np.float64)
    lv = np.asarray([legacy[u] for u in uids], np.float64)
    legacy_var = float(np.var(lv, ddof=0))
    if not math.isfinite(legacy_var) or legacy_var <= 1e-12:
        raise RuntimeError("paired legacy variance denominator invalid")
    qboost_var = float(np.var(av, ddof=0))
    variance_ratio = float(qboost_var / legacy_var)
    paired_uid_sha256 = hashlib.sha256(
        "\n".join(uids).encode("utf-8")
    ).hexdigest()
    paired_correlation = (
        float(np.corrcoef(av, lv)[0, 1])
        if float(np.std(av, ddof=0)) > 0.0 and float(np.std(lv, ddof=0)) > 0.0
        else 0.0
    )
    dispersions = []
    for row, q in zip(rows, q_values):
        if row["request_model"] != HERO_MODEL_ID:
            continue
        legal = np.asarray(row["legal"]) > 0
        if legal.sum() >= 2:
            dispersions.append(float(np.std(q[row["active"], legal], ddof=0)))
    q_dispersion = float(np.median(dispersions)) if dispersions else 0.0
    q_before_actor = {k: v.detach().cpu().clone() for k, v in q_model.state_dict().items()}
    actor_stats, executed = {}, 0
    for _ in range(args.ppo_epochs):
        _, _, epoch_q_values, _, advantages, _ = calculate_rollout(
            model, q_model, hands, device
        )
        actor_stats = actor_epoch(
            model, optimizer, rows, advantages, epoch_q_values, device, args
        )
        executed += 1
        if args.ppo_target_kl > 0 and actor_stats["approx_kl"] > args.ppo_target_kl:
            break
    if not tensor_state_equal(q_before_actor, q_model.state_dict()):
        raise RuntimeError("Q changed during actor phase")
    # Post-actor policy + unchanged pre-critic Qbar produce one immutable target.
    rows2, _, _, _, _, fixed_targets = calculate_rollout(model, q_model, hands, device)
    if [r["uid"] for r in rows2] != [r["uid"] for r in rows]:
        raise RuntimeError("target row order changed")
    actor_before_q = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
    q_stats = critic_update(q_model, q_optimizer, q_generator, rows, fixed_targets, device, args)
    if not tensor_state_equal(actor_before_q, model.state_dict()):
        raise RuntimeError("actor changed during Q phase")
    return {
        **actor_stats, **q_stats, "actor_epochs_completed": executed,
        "paired_variance_ratio": variance_ratio, "q_dispersion": q_dispersion,
        "qboost_advantage_population_variance": qboost_var,
        "legacy_gae_population_variance": legacy_var,
        "paired_actor_row_count": len(uids),
        "paired_actor_uid_sha256": paired_uid_sha256,
        "qboost_advantage_raw_mean": float(np.mean(av)),
        "qboost_advantage_raw_std": float(np.std(av, ddof=0)),
        "legacy_gae_raw_mean": float(np.mean(lv)),
        "legacy_gae_raw_std": float(np.std(lv, ddof=0)),
        "paired_raw_correlation": paired_correlation,
        "q_dispersion_eligible_actor_row_count": len(dispersions),
        "q_dispersion_actor_rows_only": True,
        "physical_rows": len(rows), "actor_rows": len(uids), "q_focal_rows": 2 * len(rows),
    }


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--vr002-preregistration")
    p.add_argument("--vr002-preregistration-sha256")
    p.add_argument("--vr002-contract-probe", action="store_true")
    p.add_argument("--vr002-q-init-seed", type=int, default=VR002_Q_INIT_SEED)
    p.add_argument("--vr002-q-minibatch-seed", type=int, default=VR002_Q_MINIBATCH_SEED)
    p.add_argument("--vr002-actor-generation-initial", type=int, default=VR002_ACTOR_GENERATION_INITIAL)
    p.add_argument("--resume", required=True)
    p.add_argument("--allow-resume", action="store_true")
    p.add_argument("--no-reset-optimizer", action="store_true")
    p.add_argument("--out")
    p.add_argument("--run-dir")
    p.add_argument("--run-id", default=f"v5_vr002c1_{VR002_TOKEN}")
    p.add_argument("--device", default="cuda")
    p.add_argument("--workers", type=int, default=22)
    p.add_argument("--rollout-envs-per-worker", type=int, default=16)
    p.add_argument("--hands-per-iter", type=int, default=16384)
    p.add_argument("--total-hands", type=int, default=VR002_TARGET_HANDS)
    p.add_argument("--starting-stack", type=float, default=200.0)
    p.add_argument("--mini-batch-size", type=int, default=1024)
    p.add_argument("--ppo-epochs", type=int, default=4)
    p.add_argument("--ppo-target-kl", type=float, default=0.03)
    p.add_argument("--delta1", type=float, default=3.0)
    p.add_argument("--lr", type=float, default=0.0003)
    p.add_argument("--entropy-coef", type=float, default=0.05)
    p.add_argument("--entropy-floor", type=float, default=0.3)
    p.add_argument("--postflop-action-prior-coef", type=float, default=0.02)
    p.add_argument("--preflop-action-prior-coef", type=float, default=0.01)
    p.add_argument("--max-grad-norm", type=float, default=0.5)
    p.add_argument("--seed", type=int, default=20260703)
    p.add_argument("--worker-seed-base", type=int, default=73000)
    p.add_argument("--inference-min-batch-slots", type=int, default=256)
    p.add_argument("--inference-batch-deadline-us", type=int, default=1000)
    p.add_argument("--max-runtime-seconds", type=float, default=21600)
    p.add_argument("--fixed-training-deal-stream", action="store_true")
    p.add_argument("--mirror-self-play-deals", action="store_true")
    p.add_argument("--allin-runout-ev", action="store_true")
    p.add_argument("--allin-runout-ev-max-runouts", type=int, default=200)
    p.add_argument("--save-interval", type=int, default=1)
    # Accepted only to make the frozen LG003C1 launcher/config surface explicit.
    p.add_argument("--lg003-arm", default="control_uniform")
    p.add_argument("--lg003-preregistration")
    p.add_argument("--lg003-preregistration-sha256")
    p.add_argument("--env-version", default="v55")
    p.add_argument("--gamma", type=float, default=0.999)
    p.add_argument("--epsilon", type=float, default=0.0)
    p.add_argument("--preflop-sb-open-action-prior-coef", type=float, default=0.0)
    p.add_argument("--preflop-bb-vs-open-action-prior-coef", type=float, default=0.0)
    p.add_argument("--k-best", type=int, default=5)
    p.add_argument("--pool-strategy", default="loss-kbest")
    p.add_argument("--pool-history-limit", type=int, default=200)
    p.add_argument("--self-play-fraction", type=float, default=0.2)
    p.add_argument("--opponent-assignment", default="per-iteration")
    p.add_argument("--opponent-groups", type=int, default=5)
    p.add_argument("--opponent-assignment-provenance-file")
    p.add_argument("--rollout-mode", default="multi")
    p.add_argument("--critic-contract", default=CRITIC_V1)
    p.add_argument("--value-coef", type=float, default=0.0)
    p.add_argument("--snapshot-every", type=int, default=200)
    p.add_argument("--discovery-mode", action="store_true")
    p.add_argument("--resume-q-state", action="store_true")
    p.add_argument("--constant-actor-lr", action="store_true")
    p.add_argument("--q-guidance-coef", type=float, default=0.0)
    p.add_argument("--q-guidance-temperature", type=float, default=2.0)
    p.add_argument("--q-guidance-min-gap", type=float, default=0.25)
    p.add_argument("--q-guidance-margin", type=float, default=0.25)
    return p.parse_args()


def validate_contract(args):
    source = Path(args.resume).resolve()
    if args.discovery_mode:
        checks = {
            "discovery_mode": True,
            "source_exists": source.is_file(),
            "positive_q_guidance": args.q_guidance_coef > 0.0,
            "positive_q_temperature": args.q_guidance_temperature > 0.0,
            "nonnegative_q_gap": args.q_guidance_min_gap >= 0.0,
            "nonnegative_q_margin": args.q_guidance_margin >= 0.0,
            "resume_q_state": args.resume_q_state,
            "constant_actor_lr": args.constant_actor_lr,
            "v55_environment": args.env_version == "v55",
            "greedy_direct_compatible_actions": qcore.NUM_ACTIONS == 9,
        }
        if not all(checks.values()):
            raise RuntimeError(
                "discovery contract failure: " + json.dumps(checks, sort_keys=True)
            )
        return checks
    if not args.vr002_preregistration or not args.vr002_preregistration_sha256:
        raise RuntimeError("VR002 frozen mode requires preregistration arguments")
    prereg = Path(args.vr002_preregistration).resolve()
    lg003_path = (
        Path(args.lg003_preregistration).resolve()
        if args.lg003_preregistration else None
    )
    provenance_exact = bool(
        args.run_dir and args.opponent_assignment_provenance_file
        and Path(args.opponent_assignment_provenance_file).resolve()
        == (Path(args.run_dir).resolve() / "opponent_assignment_provenance.jsonl")
    )
    checks = {
        "identity": VR002_IDENTITY == VR002_TOKEN + VR002_IDENTITY[32:],
        "prereg_hash_arg": args.vr002_preregistration_sha256.lower() == VR002_PREREG_SHA256,
        "prereg_hash_file": sha256_path(prereg) == VR002_PREREG_SHA256,
        "source_hash": sha256_path(source) == VR002_SOURCE_SHA256,
        "parent_trainer_hash": (
            sha256_path(Path(parent.__file__).resolve()) == VR002_PARENT_TRAINER_SHA256
        ),
        "q_init_seed": args.vr002_q_init_seed == VR002_Q_INIT_SEED,
        "q_minibatch_seed": args.vr002_q_minibatch_seed == VR002_Q_MINIBATCH_SEED,
        "actor_generation": args.vr002_actor_generation_initial == VR002_ACTOR_GENERATION_INITIAL,
        "result13": RESULT_SIZE == 13,
        "central895": qcore.CENTRAL_SERIALIZED_FLOATS == 895,
        "actions9": qcore.NUM_ACTIONS == 9,
        "source_hands": args.total_hands == VR002_TARGET_HANDS,
        "lg003_preregistration": bool(
            lg003_path and lg003_path.is_file()
            and args.lg003_preregistration_sha256
            and args.lg003_preregistration_sha256.lower() == parent.LG003_PREREG_SHA256
            and sha256_path(lg003_path) == parent.LG003_PREREG_SHA256
        ),
        "provenance_path": provenance_exact,
        "fixed_config": (
            args.workers == 22 and args.rollout_envs_per_worker == 16
            and args.hands_per_iter == 16384 and args.mini_batch_size == 1024
            and args.ppo_epochs == 4 and args.starting_stack == 200
            and args.lr == 0.0003 and args.ppo_target_kl == 0.03
            and args.delta1 == 3.0 and args.entropy_coef == 0.05
            and args.entropy_floor == 0.3 and args.postflop_action_prior_coef == 0.02
            and args.preflop_action_prior_coef == 0.01 and args.max_grad_norm == 0.5
            and args.seed == 20260703 and args.worker_seed_base == 73000
            and args.inference_min_batch_slots == 256
            and args.inference_batch_deadline_us == 1000
            and args.max_runtime_seconds == 21600 and args.save_interval == 1
            and args.lg003_arm == "control_uniform" and args.env_version == "v55"
            and args.gamma == 0.999 and args.epsilon == 0.0
            and args.preflop_sb_open_action_prior_coef == 0.0
            and args.preflop_bb_vs_open_action_prior_coef == 0.0
            and args.k_best == 5 and args.pool_strategy == "loss-kbest"
            and args.pool_history_limit == 200 and args.self_play_fraction == 0.2
            and args.opponent_assignment == "per-iteration" and args.opponent_groups == 5
            and args.rollout_mode == "multi" and args.critic_contract == CRITIC_V1
            and args.value_coef == 0.0 and args.snapshot_every == 200
            and args.fixed_training_deal_stream and args.mirror_self_play_deals
            and args.allin_runout_ev and args.allin_runout_ev_max_runouts == 200
        ),
    }
    if not all(checks.values()):
        raise RuntimeError("VR002 contract failure: " + json.dumps(checks, sort_keys=True))
    return checks


def main():
    args = parse_args()
    checks = validate_contract(args)
    if args.vr002_contract_probe:
        print(json.dumps({"status": "VR002_CONTRACT_PROBE_PASS", "checks": checks}, sort_keys=True))
        return
    if not args.allow_resume or not args.no_reset_optimizer:
        raise RuntimeError("VR002 requires --allow-resume --no-reset-optimizer")
    if not args.out or not args.run_dir:
        raise RuntimeError("VR002 execution requires --out and --run-dir")
    run_dir, out_path = Path(args.run_dir), Path(args.out)
    if run_dir.exists() or out_path.exists():
        raise RuntimeError("VR002 output collision")
    run_dir.mkdir(parents=True)

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)
    device = args.device
    model = AlphaHoldemNet(num_actions=9, critic_contract=CRITIC_V1).to(device)
    model(torch.zeros(1, 6, 4, 13, device=device), torch.zeros(1, 25, 4, 5, device=device),
          torch.zeros(1, 2, device=device))
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    checkpoint = torch.load(args.resume, map_location=device, weights_only=False)
    source_hands = int(checkpoint["total_hands"])
    source_iteration = int(checkpoint["iteration"])
    source_sha256 = sha256_path(Path(args.resume).resolve())
    if (
        not args.discovery_mode
        and (source_hands != VR002_SOURCE_HANDS or source_iteration != 35051)
    ):
        raise RuntimeError("source checkpoint counters mismatch")
    if args.total_hands <= source_hands:
        raise RuntimeError(
            f"target total_hands {args.total_hands} must exceed source {source_hands}"
        )
    model.load_state_dict(checkpoint["model"])
    optimizer.load_state_dict(checkpoint["optimizer"])
    model.eval()
    value_params = list(model.value_head.parameters())
    for p in value_params:
        p.requires_grad_(False)
    value_names = {n for n, _ in model.value_head.named_parameters(prefix="value_head")}
    value_source = {n: v.detach().cpu().clone() for n, v in model.state_dict().items() if n in value_names}
    value_optimizer_source = optimizer_state_for_names(optimizer, model, value_names)

    q_model = qcore.make_q_critic_isolated(seed=args.vr002_q_init_seed).to(device)
    qcore.assert_models_storage_disjoint(model, q_model)
    q_optimizer = torch.optim.Adam(q_model.parameters(), lr=3e-4, betas=(0.9, 0.999), eps=1e-8)
    q_generator = torch.Generator(device="cpu")
    q_generator.manual_seed(args.vr002_q_minibatch_seed)
    if args.discovery_mode and args.resume_q_state:
        q_model.load_state_dict(checkpoint["vr002_q_model"])
        q_optimizer.load_state_dict(checkpoint["vr002_q_optimizer"])
        q_generator.set_state(
            checkpoint["vr002_q_minibatch_generator_state"].cpu()
        )

    pool = parent.OpponentPool(k=5, strategy="loss-kbest", history_limit=200)
    pool.load_from_checkpoint(checkpoint.get("pool_snapshots") or [])
    if tuple(int(s["id"]) for s in pool.snapshots) != VR002_POOL_IDS:
        raise RuntimeError("frozen pool order mismatch")
    opponents = []
    for snap in pool.snapshots:
        m = AlphaHoldemNet(num_actions=9, critic_contract=CRITIC_V1).to(device)
        m(torch.zeros(1, 6, 4, 13, device=device), torch.zeros(1, 25, 4, 5, device=device),
          torch.zeros(1, 2, device=device))
        m.load_state_dict(snap["state_dict"])
        m.eval()
        opponents.append(m)

    total_hands, iteration = source_hands, source_iteration
    generation = (
        int(checkpoint.get("vr002", {}).get("actor_generation", source_iteration))
        if args.discovery_mode
        else args.vr002_actor_generation_initial
    )
    metrics_path = run_dir / "vr002_metrics.jsonl"
    trace_path = run_dir / "vr002_trace_manifest.jsonl"
    provenance_path = run_dir / "opponent_assignment_provenance.jsonl"
    manifest_path = run_dir / "run_manifest.json"
    trace_record_tail = "0" * 64
    cumulative_hand_sha = "0" * 64
    completed_total = admitted_total = rejected_total = 0
    variance_ratios, q_dispersions = [], []
    trainer_sha = sha256_path(Path(__file__).resolve())
    core_sha = sha256_path(Path(qcore.__file__).resolve())
    experiment_identity = (
        hashlib.sha256(
            json.dumps(
                {
                    "run_id": args.run_id,
                    "source_sha256": source_sha256,
                    "total_hands": args.total_hands,
                    "q_guidance_coef": args.q_guidance_coef,
                    "q_guidance_temperature": args.q_guidance_temperature,
                    "q_guidance_min_gap": args.q_guidance_min_gap,
                    "q_guidance_margin": args.q_guidance_margin,
                    "entropy_coef": args.entropy_coef,
                    "entropy_floor": args.entropy_floor,
                    "postflop_action_prior_coef": args.postflop_action_prior_coef,
                    "preflop_action_prior_coef": args.preflop_action_prior_coef,
                    "trainer_sha256": trainer_sha,
                    "core_sha256": core_sha,
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        if args.discovery_mode
        else VR002_IDENTITY
    )

    def checkpoint_payload():
        return {
            "model": model.state_dict(), "optimizer": optimizer.state_dict(),
            "vr002_q_model": q_model.state_dict(),
            "vr002_q_optimizer": q_optimizer.state_dict(),
            "vr002_q_minibatch_generator_state": q_generator.get_state(),
            "total_hands": total_hands, "iteration": iteration,
            "pool_snapshots": pool.snapshots, "pool_strategy": pool.strategy,
            "version": (
                "v5.discovery.qguided_qboost"
                if args.discovery_mode else "v5.vr002.qboost"
            ),
            "run_id": args.run_id,
            "config": vars(args), "critic_contract": CRITIC_V1,
            "vr002": {
                "identity": experiment_identity,
                "identity_sha256": experiment_identity,
                "token": VR002_TOKEN,
                "preregistration_sha256": VR002_PREREG_SHA256,
                "source_checkpoint_sha256": source_sha256,
                "source_total_hands": source_hands,
                "parent_trainer_sha256": VR002_PARENT_TRAINER_SHA256,
                "core_module": qcore.__name__, "core_sha256": core_sha,
                "trainer": str(Path(__file__).resolve()), "trainer_sha256": trainer_sha,
                "actor_generation": generation, "result_layout": "action,logp,value,pi9,generation",
                "central_floats": 895, "central_serialized_floats": 895,
                "central_learned_floats": 886, "legal_sidecar_floats": 9,
                "two_focal_views": True, "focal_views_per_action": 2,
                "q_contract": "Expected-SARSA(lambda=.95),gamma=.999,current-rollout-only",
                "gamma": 0.999, "lambda": 0.95, "q_init_seed": args.vr002_q_init_seed,
                "q_minibatch_seed": args.vr002_q_minibatch_seed,
                "q_epochs": 4, "q_physical_minibatch_size": 512,
                "terminal_reward": "inherited_allin_ev_adjusted_zero_sum_vector",
                "reward_contract": "EXACT_INHERITED_ALLIN_EV_ADJUSTED_ZERO_SUM_TERMINAL_VECTOR",
                "opponent_assignment": "LG003_ASSIGNMENT_V1_control_uniform",
                "pool_member_ids": list(VR002_POOL_IDS), "pool_ids": list(VR002_POOL_IDS),
                "pool_member_state_dict_sha256": {
                    str(k): v for k, v in VR002_POOL_HASHES.items()
                },
                "pool_state_dict_sha256_by_id": {
                    str(k): v for k, v in VR002_POOL_HASHES.items()
                },
                "assignment_rule": "LG003_ASSIGNMENT_V1",
                "assignment_token": parent.LG003_TOKEN,
                "assignment_seed": parent.LG003_ASSIGNMENT_SEED,
                "q_physical_rows_per_minibatch": 512,
                "actor_before_critic": True, "historical_replay": False,
                "complete_hands": completed_total, "admitted_hands": admitted_total,
                "mixed_or_stale_hands": rejected_total,
                "stale_assignment_hands": stale_assignment_total,
                "assignment_version": assignment_version,
            },
        }

    slots = args.workers * args.rollout_envs_per_worker
    obs_shm = shared_memory.SharedMemory(create=True, size=slots * OBS_SIZE * 4)
    result_shm = shared_memory.SharedMemory(create=True, size=slots * RESULT_SIZE * 4)
    status_shm = shared_memory.SharedMemory(create=True, size=slots * 4)
    assigned_shm = shared_memory.SharedMemory(create=True, size=args.workers * 4)
    assignment_version_shm = shared_memory.SharedMemory(create=True, size=args.workers * 8)
    request_shm = shared_memory.SharedMemory(create=True, size=slots * 4)
    obs_np = np.ndarray((slots * OBS_SIZE,), np.float32, obs_shm.buf)
    result_np = np.ndarray((slots * RESULT_SIZE,), np.float32, result_shm.buf)
    status_np = np.ndarray((slots,), np.int32, status_shm.buf)
    assigned_np = np.ndarray((args.workers,), np.int32, assigned_shm.buf)
    assignment_version_np = np.ndarray(
        (args.workers,), np.int64, assignment_version_shm.buf
    )
    request_np = np.ndarray((slots,), np.int32, request_shm.buf)
    obs_np.fill(0); result_np.fill(0); status_np.fill(IDLE)
    assigned_np.fill(HERO_MODEL_ID); assignment_version_np.fill(0)
    request_np.fill(HERO_MODEL_ID)

    current_hands, batch_sizes = [], []
    rollout_completed = rollout_admitted = rollout_rejected = rollout_physical = 0
    rollout_stale_assignment = 0
    rollout_actor_rows = 0
    rollout_exp003 = parent.exp003_metrics_template()
    cumulative_exp003 = parent.exp003_metrics_template()
    rejected_hand_uids = []
    sampled_hand_digests = []
    sampled_admitted_raw = []
    sampled_rejected_raw = []
    provenance_tail = "0" * 64
    assignment_version = 0
    stale_assignment_total = 0

    def assign_next():
        nonlocal provenance_tail, assignment_version
        local, assignment = parent.lg003_select_opponent(
            "control_uniform", iteration + 1, pool.snapshots
        )
        assignment_version += 1
        assignment_version_np[:] = 0  # seqlock write-in-progress sentinel
        assigned_np[:] = local
        # Publish positive version last. Workers reject 0 and require stable reads.
        assignment_version_np[:] = assignment_version
        provenance_tail = append_jsonl(provenance_path, {
            "schema_version": "v5.vr002.assignment.v1", "run_id": args.run_id,
            "previous_record_sha256": provenance_tail,
            "applies_to_iteration": iteration + 1, "total_hands": total_hands,
            "generation": generation, "assignment_version": assignment_version,
            "assignment": assignment,
        })

    # First exact assignment and provenance are durable before any worker can
    # observe assigned_np or start a hand.
    assign_next()
    pipes, procs = [], []
    stop_event = mp.Event()
    for w in range(args.workers):
        a, b = mp.Pipe()
        pipes.append(a)
        p = mp.Process(target=worker_process, args=(
            w, args.rollout_envs_per_worker, args.run_id, obs_shm.name, result_shm.name,
            status_shm.name, assigned_shm.name, assignment_version_shm.name,
            request_shm.name, b, stop_event,
            args.worker_seed_base + w, args.starting_stack,
            args.fixed_training_deal_stream, args.mirror_self_play_deals,
            args.allin_runout_ev, args.allin_runout_ev_max_runouts,
        ), daemon=True)
        p.start(); b.close(); procs.append(p)

    start_time, last_serve = time.time(), time.time()
    try:
        while True:
            if time.time() - start_time >= args.max_runtime_seconds:
                raise RuntimeError("VR002 runtime guard reached before valid endpoint")
            waiting = int((status_np == WAITING).sum())
            if waiting and (
                waiting >= args.inference_min_batch_slots
                or time.time() - last_serve >= args.inference_batch_deadline_us / 1e6
            ):
                run_inference(model, opponents, obs_np, result_np, status_np, request_np,
                              slots, device, generation, batch_sizes)
                last_serve = time.time()
            for pipe in pipes:
                while pipe.poll():
                    data = pipe.recv()
                    if not data:
                        continue
                    parent.exp003_metrics_add(rollout_exp003, data.get("exp003", {}))
                    parent.exp003_metrics_add(cumulative_exp003, data.get("exp003", {}))
                    for hand in data["hands"]:
                        validate_hand_packet(hand)
                        completed_total += 1
                        total_hands += 1
                        hero_generations = {
                            int(r["generation"]) for r in hand["rows"]
                            if r["request_model"] == HERO_MODEL_ID
                        }
                        generation_pure = hero_generations == {generation}
                        assignment_current = (
                            int(hand["assignment_version"]) == assignment_version
                        )
                        pure = generation_pure and assignment_current
                        if not assignment_current:
                            stale_assignment_total += 1
                            rollout_stale_assignment += 1
                        if pure:
                            admitted_total += 1
                            current_hands.append(hand)
                        else:
                            rejected_total += 1
                        rollout_completed += 1
                        rollout_physical += len(hand["rows"])
                        rollout_actor_rows += sum(
                            r["request_model"] == HERO_MODEL_ID for r in hand["rows"]
                        )
                        if pure:
                            rollout_admitted += 1
                            if len(sampled_admitted_raw) < 4:
                                sampled_admitted_raw.append(sampled_raw_hand(hand, True))
                        else:
                            rollout_rejected += 1
                            rejected_hand_uids.append(hand["hand_uid"])
                            if len(sampled_rejected_raw) < 4:
                                sampled_rejected_raw.append(sampled_raw_hand(hand, False))
                        if len(sampled_hand_digests) < 64:
                            sampled_hand_digests.append({
                                "hand_uid": hand["hand_uid"],
                                "hand_digest": hand["hand_digest"],
                            })
                        cumulative_hand_sha = hashlib.sha256(
                            (cumulative_hand_sha + hand["hand_digest"]).encode()
                        ).hexdigest()
            if len(current_hands) < args.hands_per_iter:
                time.sleep(0.00001)
                continue

            iteration += 1
            generation_reference = generation
            actor_lr = (
                args.lr
                if args.discovery_mode and args.constant_actor_lr
                else inherited_absolute_progress_lr(
                    total_hands, args.total_hands, args.lr
                )
            )
            for group in optimizer.param_groups:
                group["lr"] = actor_lr
            value_before = {n: v.detach().cpu().clone() for n, v in model.state_dict().items() if n in value_names}
            value_optimizer_before = optimizer_state_for_names(optimizer, model, value_names)
            stats = run_update(
                model, optimizer, q_model, q_optimizer, q_generator, current_hands, device, args
            )
            value_frozen = tensor_state_equal(value_before, {
                n: v.detach().cpu() for n, v in model.state_dict().items() if n in value_names
            }) and tensor_state_equal(value_source, {
                n: v.detach().cpu() for n, v in model.state_dict().items() if n in value_names
            }) and nested_state_equal(
                value_optimizer_before, optimizer_state_for_names(optimizer, model, value_names)
            ) and nested_state_equal(
                value_optimizer_source, optimizer_state_for_names(optimizer, model, value_names)
            )
            if not value_frozen:
                raise RuntimeError("scalar value head parameters changed")
            generation += 1
            variance_ratios.append(stats["paired_variance_ratio"])
            q_dispersions.append(stats["q_dispersion"])
            record = {
                "schema_version": "v5.vr002.metric.v1",
                "identity": experiment_identity,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "iteration": iteration, "total_hands": total_hands,
                "new_hands": total_hands - source_hands,
                "actor_generation": generation,
                "actor_generation_reference": generation_reference,
                "actor_generation_after": generation,
                "complete_hands": completed_total,
                "admitted_hands": admitted_total, "mixed_or_stale_hands": rejected_total,
                "rollout_complete_hands": rollout_completed,
                "rollout_admitted_hands": rollout_admitted,
                "rollout_mixed_or_stale_hands": rollout_rejected,
                "rollout_stale_assignment_hands": rollout_stale_assignment,
                "stale_assignment_hands": stale_assignment_total,
                "assignment_version": assignment_version,
                "actor_learning_rate": actor_lr,
                **stats,
                "bijection_pass": stats["actor_rows"] == sum(
                    r["request_model"] == HERO_MODEL_ID
                    for h in current_hands for r in h["rows"]
                ),
                "chronology_coverage_pass": True, "math_contract_pass": True,
                "reward_contract_pass": True, "legal_policy_contract_pass": True,
                "actor_q_isolation_pass": True, "leakage_contract_pass": True,
                "finite_pass": all(
                    math.isfinite(float(v))
                    for v in stats.values()
                    if isinstance(v, (int, float, bool, np.number))
                ),
                "value_head_frozen_pass": value_frozen,
                "trace_hand_chain_sha256": cumulative_hand_sha,
                "exp003_metrics": dict(rollout_exp003),
            }
            append_jsonl(metrics_path, record)
            trace_record = {
                "schema_version": TRACE_AGGREGATE_SCHEMA,
                "identity": experiment_identity,
                "previous_record_sha256": trace_record_tail,
                "iteration": iteration, "actor_generation_collected": generation - 1,
                "assignment_version_collected": assignment_version,
                "complete_hands": rollout_completed, "admitted_hands": rollout_admitted,
                "mixed_or_stale_hands": rollout_rejected,
                "stale_assignment_hands": rollout_stale_assignment,
                "physical_rows": rollout_physical, "actor_rows": rollout_actor_rows,
                "q_focal_rows": 2 * rollout_physical,
                "terminal_rows": rollout_completed,
                "step_contiguous_all": True, "successor_links_all": True,
                "two_focal_views_per_row": True, "terminal_reward_zero_sum_all": True,
                "actor_bijection_all": record["bijection_pass"],
                "rejected_hand_uids": rejected_hand_uids,
                "sampled_hand_digests": sampled_hand_digests,
                "sampled_raw_admitted_hands": sampled_admitted_raw,
                "sampled_raw_rejected_hands": sampled_rejected_raw,
                "cumulative_hand_sha256": cumulative_hand_sha,
                "exp003_metrics": dict(rollout_exp003),
            }
            trace_record_tail = append_jsonl(trace_path, trace_record)
            atomic_torch_save(checkpoint_payload(), out_path)
            current_hands = []
            if total_hands >= args.total_hands:
                delta = total_hands - source_hands
                if not args.discovery_mode and not 5_000_000 <= delta <= 5_050_000:
                    raise RuntimeError(f"first-crossing hand delta invalid: {delta}")
                manifest = {
                    "schema_version": "v5.vr002.endpoint.v1", "status": "finished",
                    "termination_reason": "first_crossing_target",
                    "no_unused_provenance_after_first_crossing": True,
                    "runtime_seconds": time.time() - start_time,
                    "first_crossing": True, "identity": experiment_identity,
                    "trainer_sha256": trainer_sha, "core_sha256": core_sha,
                    "source_hands": source_hands, "total_hands": total_hands,
                    "new_hands": delta, "iteration": iteration, "actor_generation": generation,
                    "checkpoint": str(out_path.resolve()), "checkpoint_sha256": sha256_path(out_path),
                    "metrics_sha256": sha256_path(metrics_path), "trace_sha256": sha256_path(trace_path),
                    "provenance_sha256": sha256_path(provenance_path),
                    "paired_variance_ratios": variance_ratios,
                    "q_dispersions": q_dispersions, "complete_hands": completed_total,
                    "admitted_hands": admitted_total, "mixed_or_stale_hands": rejected_total,
                    "stale_assignment_hands": stale_assignment_total,
                    "assignment_version": assignment_version,
                    "exp003_metrics": dict(cumulative_exp003),
                    "immutable_artifacts": {
                        "checkpoint": {"path": str(out_path.resolve()), "sha256": sha256_path(out_path)},
                        "metrics": {"path": str(metrics_path.resolve()), "sha256": sha256_path(metrics_path)},
                        "trace": {"path": str(trace_path.resolve()), "sha256": sha256_path(trace_path)},
                        "provenance": {"path": str(provenance_path.resolve()), "sha256": sha256_path(provenance_path)},
                    },
                }
                manifest["manifest_payload_sha256"] = canonical_sha(manifest)
                manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                break
            rollout_completed = rollout_admitted = rollout_rejected = rollout_physical = 0
            rollout_stale_assignment = 0
            rollout_actor_rows = 0
            rejected_hand_uids = []
            sampled_hand_digests = []
            sampled_admitted_raw = []
            sampled_rejected_raw = []
            rollout_exp003 = parent.exp003_metrics_template()
            assign_next()
    finally:
        stop_event.set()
        for p in procs:
            p.join(timeout=3)
            if p.is_alive():
                p.terminate()
        for shm in (
            obs_shm, result_shm, status_shm, assigned_shm,
            assignment_version_shm, request_shm,
        ):
            shm.close()
            shm.unlink()


if __name__ == "__main__":
    mp.set_start_method("spawn")
    main()
