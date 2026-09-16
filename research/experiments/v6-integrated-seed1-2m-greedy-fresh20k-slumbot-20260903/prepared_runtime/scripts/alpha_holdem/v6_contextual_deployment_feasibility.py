"""Offline deployment and session-contract feasibility for posterior context."""
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

from alpha_holdem.contextual_execution_v6 import (
    CONTEXT_CONTRACT,
    SessionContextTracker,
    build_deployment_bundle,
    decide,
    external_decision,
    load_policy,
)
from alpha_holdem.contextual_residual_v6 import PosteriorCenteredResidualPolicy
from alpha_holdem.audit_slumbot_v6_session import audit_sessions
from alpha_holdem.execution_v6 import sha256_file
from alpha_holdem.play_slumbot_v6_journaled import run_session
from alpha_holdem.policy_contract_v6 import action_table, apply_incr
from alpha_holdem.rules_v6 import ChipState
from alpha_holdem.v6_dual_contract_deployment_feasibility import OfflineServer
from alpha_holdem.v6_dual_contract_residual_training_smoke import state_inputs


def read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def source_model(source_path: Path, deployment) -> PosteriorCenteredResidualPolicy:
    payload = torch.load(source_path, map_location="cpu", weights_only=False)
    model = PosteriorCenteredResidualPolicy(
        deployment.base_policy.model,
        deployment.checkpoint["classifier"],
        hidden=int(deployment.checkpoint["hidden"]),
        policy_delta_cap=float(deployment.checkpoint["policy_delta_cap"]),
        reliability_power=float(deployment.checkpoint["reliability_power"]),
    ).eval()
    missing, unexpected = model.load_state_dict(payload["residual_state_dict"], strict=False)
    if unexpected or any(not name.startswith("base.") for name in missing):
        raise ValueError("source residual state did not reload exactly")
    return model


def contexts(seed: int) -> list[np.ndarray]:
    rng = np.random.default_rng(seed)
    result = [np.zeros(20, dtype=np.float32)]
    from alpha_holdem.v6_opponent_context_feasibility import context_features
    for _ in range(11):
        result.append(context_features(rng.integers(0, 33, size=(4, 4))))
    return result


@torch.no_grad()
def parity_panel(source, deployment, *, states: int, seed: int) -> dict:
    rng = random.Random(seed)
    context_rows = contexts(seed + 1)
    compared = greedy_matches = sampled_matches = zero_exact = 0
    max_logit_error = max_zero_error = 0.0
    while compared < states:
        deck = list(range(52))
        rng.shuffle(deck)
        state = ChipState.new(deck)
        while not state.terminal and compared < states:
            values, obs, table = state_inputs(deployment.base_policy, state, "cpu")
            context = context_rows[compared % len(context_rows)]
            context_tensor = torch.as_tensor(context).unsqueeze(0)
            source_logits = source(*values, context_tensor)[0]
            deployed_logits = deployment.model(*values, context_tensor)[0]
            error = float((source_logits - deployed_logits).abs().max())
            max_logit_error = max(max_logit_error, error)
            source_legal = np.flatnonzero(obs["legal_mask"] > 0)
            source_choice = int(source_legal[int(torch.argmax(source_logits[0, source_legal]).item())])
            source_action = table[source_choice]
            deployed_action, _ = decide(
                deployment, state, context, cold_start=False,
                uniform=0.317, policy_mode="greedy",
            )
            greedy_matches += int(source_action == deployed_action)
            uniform = rng.random()
            legal_logits = source_logits[0, source_legal].numpy().astype(np.float64)
            probabilities = np.exp(legal_logits - legal_logits.max())
            probabilities /= probabilities.sum()
            sampled_index = min(
                int(np.searchsorted(np.cumsum(probabilities), uniform, side="right")),
                len(source_legal) - 1,
            )
            source_sample = table[int(source_legal[sampled_index])]
            deployed_sample, sample_info = decide(
                deployment, state, context, cold_start=False,
                uniform=uniform, policy_mode="sample",
            )
            sampled_matches += int(source_sample == deployed_sample)
            if abs(sum(sample_info["behavior_probs"]) - 1.0) > 1e-12:
                raise RuntimeError("sampled behavior probabilities are not normalized")
            zero = torch.zeros((1, 20), dtype=torch.float32)
            zero_logits = deployment.model(*values, zero)[0]
            base_logits = deployment.model.base(values[0], values[1], values[2], values[6])[0]
            zero_error = float((zero_logits - base_logits).abs().max())
            max_zero_error = max(max_zero_error, zero_error)
            zero_exact += int(zero_error == 0.0)
            compared += 1
            _, native_table = action_table(state)
            legal_actions = [action for action in native_table if action is not None]
            state = apply_incr(state, rng.choice(legal_actions))
    return {
        "reachable_states": compared,
        "context_vectors": len(context_rows),
        "greedy_action_matches": greedy_matches,
        "sampled_action_matches": sampled_matches,
        "zero_context_exact_states": zero_exact,
        "max_abs_source_bundle_logit_error": max_logit_error,
        "max_abs_zero_context_base_logit_error": max_zero_error,
    }


def audit_context_session(path: Path, expected_hands: int) -> dict:
    hands = read_jsonl(path / "hands.jsonl")
    journal = read_jsonl(path / "journal.jsonl")
    starts = [row for row in journal if row["event"] == "hand_start"]
    if len(hands) != expected_hands or len(starts) != expected_hands:
        raise RuntimeError("context session hand evidence count mismatch")
    previous_context = [0.0] * 20
    decision_count = cold_decisions = active_decisions = 0
    for index, (record, start) in enumerate(zip(hands, starts), start=1):
        start_state = start["session_policy_state"]
        end_state = record["session_policy_state"]
        expected_cold = index <= 64
        if start["hand"] != index or record["successful_hand"] != index:
            raise RuntimeError("context session indices are not contiguous")
        if start_state["context_completed_hands"] != index - 1:
            raise RuntimeError("context start hand count mismatch")
        if end_state["context_completed_hands"] != index:
            raise RuntimeError("context finish hand count mismatch")
        if start_state["context_cold_start"] is not expected_cold:
            raise RuntimeError("context cold-start transition mismatch")
        if not np.array_equal(start_state["context_feature_vector"], previous_context):
            raise RuntimeError("context did not carry exactly between hands")
        for decision in record["decisions"]:
            decision_count += 1
            if decision["context_cold_start"] is not expected_cold:
                raise RuntimeError("decision cold-start metadata mismatch")
            if decision["observation_bridge_contract"] != CONTEXT_CONTRACT:
                raise RuntimeError("decision context contract mismatch")
            if not np.array_equal(decision["context_feature_vector"], start_state["context_feature_vector"]):
                raise RuntimeError("within-hand context changed")
            cold_decisions += int(expected_cold)
            active_decisions += int(not expected_cold)
        previous_context = end_state["context_feature_vector"]
    if active_decisions == 0:
        raise RuntimeError("fixture exercised no post-cold-start decisions")
    zero_hash = SessionContextTracker().metadata()["context_counts_sha256"]
    return {
        "hands": len(hands),
        "decisions": decision_count,
        "cold_decisions": cold_decisions,
        "active_decisions": active_decisions,
        "initial_counts_sha256": starts[0]["session_policy_state"]["context_counts_sha256"],
        "expected_zero_counts_sha256": zero_hash,
        "final_counts_sha256": hands[-1]["session_policy_state"]["context_counts_sha256"],
        "final_context": hands[-1]["session_policy_state"]["context_feature_vector"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-checkpoint", type=Path, required=True)
    parser.add_argument("--base-checkpoint", type=Path, required=True)
    parser.add_argument("--context-classifier", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--states", type=int, default=512)
    parser.add_argument("--session-hands", type=int, default=70)
    parser.add_argument("--seed", type=int, default=2026090207)
    args = parser.parse_args()
    if args.out_dir.exists():
        raise FileExistsError(args.out_dir)
    if args.states < 256 or args.session_hands < 65:
        parser.error("feasibility requires >=256 states and >=65 hands/session")
    args.out_dir.mkdir(parents=True)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    started = time.time()
    deployment_path = (args.out_dir / "posterior_context_endpoint512_seed2_deployment.pt").resolve()
    bundle = build_deployment_bundle(
        args.source_checkpoint, args.base_checkpoint, args.context_classifier,
        deployment_path, cold_start_hands=64, reliability_power=1.0,
    )
    deployment = load_policy(deployment_path, args.base_checkpoint, "cpu")
    source = source_model(args.source_checkpoint.resolve(), deployment)
    parity = parity_panel(source, deployment, states=args.states, seed=args.seed)
    session_results = []
    for index in range(2):
        tracker = SessionContextTracker(deployment.cold_start_hands)
        server = OfflineServer(args.seed + 10_000 + index, f"OFFLINE_CONTEXT_{index}_TOKEN")
        session_dir = args.out_dir / f"mock_session_{index + 1}"

        def contextual_decision(policy, response, *, uniform, device, policy_mode, tracker=tracker):
            return external_decision(
                policy, response, tracker.context, cold_start=tracker.cold_start,
                uniform=uniform, device=device, policy_mode=policy_mode,
            )

        run_session(
            deployment, deployment_path, deployment.sha256,
            hands=args.session_hands, seed=args.seed + 20_000 + index,
            session_id=f"context_mock_{index + 1}", out_dir=session_dir,
            new_hand_fn=server.new_hand, act_fn=server.act,
            command=[sys.executable, *sys.argv, f"--offline-session={index + 1}"],
            policy_mode="greedy", decision_fn=contextual_decision,
            hand_start_fn=tracker.start_hand, hand_end_fn=tracker.finish_hand,
            execution_metadata={
                "observation_bridge_contract": CONTEXT_CONTRACT,
                "model_obs_version": "legacy-v4+native-v6+public-session-context",
                "base_checkpoint_sha256": deployment.base_sha256,
                "source_checkpoint_sha256": deployment.source_checkpoint_sha256,
                "classifier_sha256": deployment.classifier_sha256,
                "context_cold_start_hands": deployment.cold_start_hands,
                "context_reliability_power": float(deployment.checkpoint["reliability_power"]),
                "offline_fixture": True,
            },
            frozen_artifacts={str(deployment.base_path): deployment.base_sha256},
        )
        session_results.append(audit_context_session(session_dir, args.session_hands))
    def replay_decision(policy, response, tracker, *, uniform, device, policy_mode):
        return external_decision(
            policy, response, tracker.context, cold_start=tracker.cold_start,
            uniform=uniform, device=device, policy_mode=policy_mode,
        )
    replay = audit_sessions(
        [args.out_dir / "mock_session_1", args.out_dir / "mock_session_2"],
        model=deployment, expected_model_sha256=deployment.sha256,
        expected_observation_bridge=CONTEXT_CONTRACT,
        expected_frozen_artifacts={str(deployment.base_path): deployment.base_sha256},
        session_state_factory=lambda: SessionContextTracker(deployment.cold_start_hands),
        stateful_decision_fn=replay_decision,
    )
    wrong_base = args.out_dir / "wrong_base.bin"
    wrong_base.write_bytes(b"not Standard10\n")
    mismatch_rejected = False
    try:
        load_policy(deployment_path, wrong_base, "cpu")
    except ValueError:
        mismatch_rejected = True
    gates = {
        "source_hash_exact": bundle["source_checkpoint_sha256"] == sha256_file(args.source_checkpoint),
        "base_hash_exact": bundle["base_sha256"] == sha256_file(args.base_checkpoint),
        "classifier_hash_exact": bundle["classifier_sha256"] == sha256_file(args.context_classifier),
        "source_bundle_logits_bit_exact": parity["max_abs_source_bundle_logit_error"] == 0.0,
        "all_greedy_actions_exact": parity["greedy_action_matches"] == parity["reachable_states"],
        "all_sampled_actions_exact": parity["sampled_action_matches"] == parity["reachable_states"],
        "all_zero_context_logits_bit_exact": parity["zero_context_exact_states"] == parity["reachable_states"],
        "two_sessions_completed": all(row["hands"] == args.session_hands for row in session_results),
        "both_sessions_begin_from_zero_context": all(row["initial_counts_sha256"] == row["expected_zero_counts_sha256"] for row in session_results),
        "both_sessions_cross_cold_start_boundary": all(row["active_decisions"] > 0 for row in session_results),
        "sessions_have_independent_context_evidence": session_results[0]["final_counts_sha256"] != session_results[1]["final_counts_sha256"],
        "journal_protocol_and_stateful_replay_pass": replay["status"] == "PASS",
        "token_chains_disjoint": replay["token_chains_disjoint"] is True,
        "base_mismatch_rejected": mismatch_rejected,
        "bundle_unchanged": sha256_file(deployment_path) == deployment.sha256,
    }
    summary = {
        "schema": "cardpilot.posterior_context_deployment_feasibility.v1",
        "status": "COMPLETED", "claim_scope": "OFFLINE_DEPLOYMENT_AND_SESSION_CONTRACT_ONLY",
        "bundle": bundle, "parity": parity, "sessions": session_results, "replay": replay,
        "offline_fixture_evaluation_hands": 2 * args.session_hands,
        "gates": gates, "admit_fresh_directional_gate": all(gates.values()),
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
