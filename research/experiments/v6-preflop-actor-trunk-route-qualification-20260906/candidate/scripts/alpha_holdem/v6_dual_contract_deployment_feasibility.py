"""Offline frozen-deployment feasibility for a dual-contract residual policy."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import sys
import time

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_holdem.audit_slumbot_v6_session import audit_sessions
from alpha_holdem.dual_contract_execution_v6 import (
    DUAL_CONTRACT,
    build_deployment_bundle,
    decide,
    external_decision,
    load_policy,
)
from alpha_holdem.dual_contract_residual_v6 import DualContractResidualPolicy
from alpha_holdem.execution_v6 import sha256_file
from alpha_holdem.legacy_observation_bridge_v6 import load_policy as load_base_policy
from alpha_holdem.play_slumbot_v6_journaled import run_session
from alpha_holdem.policy_contract_v6 import action_table, apply_incr
from alpha_holdem.rules_v6 import ChipState
from alpha_holdem.v6_dual_contract_residual_training_smoke import residual_decide, state_inputs
from deep_cfr.hand_eval import card_to_str


class OfflineServer:
    """Deterministic native-rules fixture; it never opens a network connection."""

    def __init__(self, seed: int, token: str):
        self.rng = random.Random(seed)
        self.token = token
        self.seat = 1
        self.hand = 0
        self.completed = 0
        self.total = 0
        self.state = None
        self.text = ""

    def _move(self, increment: str) -> None:
        old_street = self.state.street
        self.state = apply_incr(self.state, increment)
        self.text += increment
        if self.state.street > old_street and not self.state.terminal:
            self.text += "/"

    def _response(self) -> dict:
        while not self.state.terminal and self.state.actor != self.seat:
            self._move("c" if self.state.to_call else "k")
        response = {
            "token": self.token,
            "action": self.text,
            "client_pos": self.seat,
            "hole_cards": [card_to_str(card) for card in self.state.holes[self.seat]],
            "board": [card_to_str(card) for card in self.state.board],
        }
        if self.state.terminal:
            self.completed += 1
            winnings = self.state.payoffs()[self.seat]
            self.total += winnings
            response.update(
                winnings=winnings,
                session_num_hands=self.completed,
                session_total=self.total,
            )
            if self.state.folded < 0:
                response["bot_hole_cards"] = [
                    card_to_str(card) for card in self.state.holes[1 - self.seat]
                ]
        return response

    def new_hand(self, token):
        if token != (None if self.hand == 0 else self.token):
            raise ValueError("Fixture token mismatch")
        self.hand += 1
        deck = list(range(52))
        self.rng.shuffle(deck)
        self.state = ChipState.new(deck)
        self.text = ""
        return self._response()

    def act(self, token, increment):
        if token != self.token:
            raise ValueError("Fixture token mismatch")
        self._move(increment)
        return self._response()


def load_source_model(source_path: Path, base_path: Path):
    source = torch.load(source_path, map_location="cpu", weights_only=False)
    hidden = source.get("hidden")
    cap = source.get("policy_delta_cap")
    if hidden is None or cap is None:
        parent_path = Path(source["start_checkpoint"]).resolve()
        if sha256_file(parent_path) != source["start_checkpoint_sha256"]:
            raise RuntimeError("Source architecture-parent identity mismatch")
        parent = torch.load(parent_path, map_location="cpu", weights_only=False)
        hidden, cap = parent["hidden"], parent["policy_delta_cap"]
    base_policy = load_base_policy(base_path, "cpu")
    model = DualContractResidualPolicy(
        base_policy.model,
        hidden=hidden,
        policy_delta_cap=cap,
    ).eval()
    incompatible = model.load_state_dict(source["residual_state_dict"], strict=False)
    if incompatible.unexpected_keys or any(
        not key.startswith("base.") for key in incompatible.missing_keys
    ):
        raise RuntimeError("Source residual state did not load exactly")
    return source, base_policy, model


def parity_panel(source_model, source_base, deployment, states: int, seed: int) -> dict:
    rng = random.Random(seed)
    compared = 0
    greedy_matches = 0
    sampled_matches = 0
    max_logit_error = 0.0
    while compared < states:
        deck = list(range(52))
        rng.shuffle(deck)
        state = ChipState.new(deck)
        while not state.terminal and compared < states:
            source_inputs, _, _ = state_inputs(source_base, state, "cpu")
            deployed_inputs, _, _ = state_inputs(deployment.base_policy, state, "cpu")
            with torch.no_grad():
                source_logits = source_model(*source_inputs)[0]
                deployed_logits = deployment.model(*deployed_inputs)[0]
            max_logit_error = max(
                max_logit_error,
                float((source_logits - deployed_logits).abs().max().item()),
            )
            source_action, _ = residual_decide(
                source_model, source_base, state, "cpu", uniform=None
            )
            deployed_action, info = decide(
                deployment, state, uniform=0.317, policy_mode="greedy"
            )
            greedy_matches += int(source_action == deployed_action)
            uniform = rng.random()
            source_sample, _ = residual_decide(
                source_model, source_base, state, "cpu", uniform=uniform
            )
            deployed_sample, _ = decide(
                deployment, state, uniform=uniform, policy_mode="sample"
            )
            sampled_matches += int(source_sample == deployed_sample)
            if info["direct_increment"] != deployed_action:
                raise RuntimeError("Deployment decision metadata mismatch")
            compared += 1
            _, table = action_table(state)
            legal_actions = [action for action in table if action is not None]
            state = apply_incr(state, rng.choice(legal_actions))
    return {
        "reachable_states": compared,
        "greedy_action_matches": greedy_matches,
        "sampled_action_matches": sampled_matches,
        "max_abs_logit_error": max_logit_error,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-checkpoint", type=Path, required=True)
    parser.add_argument("--residual-checkpoint", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--bundle-name", default="dual_contract_seed0_12k_deployment.pt")
    args = parser.parse_args()
    if args.out_dir.exists():
        raise FileExistsError(args.out_dir)
    args.out_dir.mkdir(parents=True)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    started = time.time()
    base_path = args.base_checkpoint.resolve()
    source_path = args.residual_checkpoint.resolve()
    if Path(args.bundle_name).name != args.bundle_name or not args.bundle_name.endswith(".pt"):
        parser.error("--bundle-name must be a plain .pt filename")
    deployment_path = (args.out_dir / args.bundle_name).resolve()
    bundle = build_deployment_bundle(source_path, base_path, deployment_path)
    deployment = load_policy(deployment_path, base_path, "cpu")
    source, source_base, source_model = load_source_model(source_path, base_path)
    parity = parity_panel(source_model, source_base, deployment, 4096, 2026090107)

    session_dirs = []
    for index in range(2):
        server = OfflineServer(2026090200 + index, f"OFFLINE_DUAL_{index}_TOKEN")
        session_dir = args.out_dir / f"mock_session_{index + 1}"
        run_session(
            deployment,
            deployment_path,
            deployment.sha256,
            hands=4,
            seed=2026090300 + index,
            session_id=f"dual_mock_{index + 1}",
            out_dir=session_dir,
            new_hand_fn=server.new_hand,
            act_fn=server.act,
            command=[sys.executable, *sys.argv, f"--offline-session={index + 1}"],
            policy_mode="greedy",
            decision_fn=external_decision,
            execution_metadata={
                "observation_bridge_contract": DUAL_CONTRACT,
                "model_obs_version": "legacy-v4+native-v6",
                "base_checkpoint_sha256": deployment.base_sha256,
                "source_residual_sha256": deployment.source_residual_sha256,
                "offline_fixture": True,
            },
            frozen_artifacts={str(base_path): deployment.base_sha256},
        )
        session_dirs.append(session_dir)
    replay = audit_sessions(
        session_dirs,
        model=deployment,
        expected_model_sha256=deployment.sha256,
        decision_fn=external_decision,
        expected_observation_bridge=DUAL_CONTRACT,
        expected_frozen_artifacts={str(base_path): deployment.base_sha256},
    )

    wrong_base = args.out_dir / "wrong_base.bin"
    wrong_base.write_bytes(b"not the frozen Standard10 checkpoint\n")
    base_mismatch_rejected = False
    try:
        load_policy(deployment_path, wrong_base, "cpu")
    except ValueError:
        base_mismatch_rejected = True

    gates = {
        "source_residual_hash_exact": bundle["source_residual_sha256"] == sha256_file(source_path),
        "base_hash_exact": bundle["base_sha256"] == sha256_file(base_path),
        "architecture_recovered_from_hash_bound_parent": (
            bundle["hidden"] == 128 and bundle["policy_delta_cap"] == 0.25
        ),
        "all_logits_bit_exact": parity["max_abs_logit_error"] == 0.0,
        "all_greedy_actions_exact": parity["greedy_action_matches"] == parity["reachable_states"],
        "all_sampled_actions_exact": parity["sampled_action_matches"] == parity["reachable_states"],
        "journal_and_independent_replay_pass": replay["status"] == "PASS",
        "two_mock_token_chains_disjoint": replay["token_chains_disjoint"] is True,
        "base_mismatch_rejected": base_mismatch_rejected,
    }
    summary = {
        "schema": "cardpilot.dual_contract_deployment_feasibility.v1",
        "status": "COMPLETED",
        "source_checkpoint_schema": source["schema"],
        "bundle": bundle,
        "parity": parity,
        "offline_protocol_hands": replay["successful_hands"],
        "offline_decision_replays": sum(
            row["decision_replays"] for row in replay["results"]
        ),
        "replay": replay,
        "gates": gates,
        "admit_fresh_directional_gate": all(gates.values()),
        "wall_time_seconds": time.time() - started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
    }
    (args.out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, sort_keys=True))
    if not summary["admit_fresh_directional_gate"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
