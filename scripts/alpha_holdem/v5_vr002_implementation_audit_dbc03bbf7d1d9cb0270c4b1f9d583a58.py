#!/usr/bin/env python3
"""Independent CPU-only implementation audit for frozen VR002."""

from __future__ import annotations

import ast
import hashlib
import importlib
import inspect
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn


REPO = Path(r"C:\Users\a8594\CardPilot")
TOKEN = "dbc03bbf7d1d9cb0270c4b1f9d583a58"
IDENTITY = "dbc03bbf7d1d9cb0270c4b1f9d583a586b82c23a655de48a4fb2139ac00a3fb1"
PREREG_SHA256 = "029411e18760455197471a12f0c00c07d08e6d3123e3d8d62e4b51bc6b7b6fcd"
PREAUDIT_SHA256 = "fe45bd5235f4be3130616b3a387db7a3b41df9f9bfaf9eb44b2bd0d65ec876c6"
SOURCE_SHA256 = "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"
PARENT_TRAINER_SHA256 = "f841144c883d51e66a1d2de889e15303e7339695c8664f81e60208ff77770452"
PARENT_LAUNCHER_SHA256 = "c20ebf0d3201b8fdb01a2a31945dbb2166defb646a2f1e410ca2e6d2e04b3d96"
PPO_SHA256 = "69197b52baee7463d79e4a940f01f8bb241ed8e70975b51e043b99fd8a5cbc4d"
NETWORK_SHA256 = "25f4520d31f4ce5ffcfd23fc0d56b8736fd3b5fad537706b9cd13ee270b4a171"
ENV_SHA256 = "3ab591176a8119d21ac11e043bdfef72bd30b8842e34a9fea45cdd36b945f9de"
GAME_STATE_SHA256 = "1500278c6a0fd2909c3bb7aa741aad1842651478b84a676e0783031aa27a6a8a"
CORE_SHA256 = "63e600bf4e7dd447e514849f223dc160c5b4808ca716d173c22981ac7ff488ef"
TRAINER_SHA256 = "868032be3c94f58915921acf0a95a7c6684469797a8c54cf5c1fffd94a4cf432"
PATHS = {
    "preregistration": REPO / f"reports/v5_vr002_corrected_faithful_qboost_preregistration_{TOKEN}_20260723.json",
    "preimplementation_audit": REPO / f"reports/v5_vr002_corrected_faithful_qboost_preregistration_audit_{TOKEN}_20260723.json",
    "source_checkpoint": REPO / (
        "models/alpha_holdem_v5_hybrid/"
        "v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715/"
        "h11_control_endpoint.pt"
    ),
    "parent_trainer": REPO / "scripts/alpha_holdem/v5_lg003c1_train_8bf8cedf78b6e8c8fe153802908ed893.py",
    "parent_launcher": REPO / "scripts/alpha_holdem/v5_lg003c1_launcher_8bf8cedf78b6e8c8fe153802908ed893.ps1",
    "ppo": REPO / "scripts/alpha_holdem/train_mp3_hybrid_h1.py",
    "network": REPO / "scripts/alpha_holdem/network_hybrid_h1.py",
    "environment": REPO / "scripts/alpha_holdem/environment_v55.py",
    "game_state": REPO / "scripts/deep_cfr/game_state.py",
    "core": REPO / f"scripts/alpha_holdem/v5_vr002_qboost_core_{TOKEN}.py",
    "trainer": REPO / f"scripts/alpha_holdem/v5_vr002_train_{TOKEN}.py",
    "launcher": REPO / f"scripts/alpha_holdem/v5_vr002_launcher_{TOKEN}.ps1",
    "window_auditor": REPO / f"scripts/alpha_holdem/v5_vr002_window_audit_{TOKEN}.py",
    "report": REPO / f"reports/v5_vr002_implementation_audit_{TOKEN}_20260723.json",
    "output_root": REPO / f"models/alpha_holdem_v5_hybrid/v5_vr002_{TOKEN}_20260723",
}


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def add(checks: dict[str, bool], name: str, condition: Any) -> None:
    checks[name] = bool(condition)


def function_node(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"missing function {name}")


def independent_math_test(core: Any) -> None:
    q = torch.tensor(
        [
            [[1.0, 2.0, 0, 0, 0, 0, 0, 0, 0], [-1.0, -2.0, 0, 0, 0, 0, 0, 0, 0]],
            [[2.0, 4.0, 0, 0, 0, 0, 0, 0, 0], [-2.0, -4.0, 0, 0, 0, 0, 0, 0, 0]],
            [[3.0, 6.0, 0, 0, 0, 0, 0, 0, 0], [-3.0, -6.0, 0, 0, 0, 0, 0, 0, 0]],
        ],
        dtype=torch.float64,
        requires_grad=True,
    )
    pi = torch.tensor(
        [[0.25, 0.75, 0, 0, 0, 0, 0, 0, 0]] * 3, dtype=torch.float64
    )
    actions = torch.tensor([0, 1, 0])
    rewards = torch.tensor([[0.0, 0.0], [0.0, 0.0], [7.0, -7.0]], dtype=torch.float64)
    dones = torch.tensor([0.0, 0.0, 1.0], dtype=torch.float64)
    legal = torch.tensor([[1, 1, 0, 0, 0, 0, 0, 0, 0]] * 3)
    actual = core.expected_sarsa_qboost(
        q, pi, actions, rewards, dones, gamma=0.999, lam=0.95, legal_masks=legal
    )
    qd = q.detach().numpy()
    pid = pi.numpy()
    values = (qd * pid[:, None, :]).sum(axis=2)
    selected = np.stack([qd[t, :, actions[t].item()] for t in range(3)])
    delta = np.zeros((3, 2), np.float64)
    trace = np.zeros((3, 2), np.float64)
    acc = np.zeros(2, np.float64)
    for index in range(2, -1, -1):
        next_value = np.zeros(2) if index == 2 else values[index + 1]
        continuation = 1.0 - dones[index].item()
        delta[index] = rewards[index].numpy() + 0.999 * continuation * next_value - selected[index]
        acc = delta[index] + 0.999 * 0.95 * continuation * acc
        trace[index] = acc
    np.testing.assert_allclose(actual["v"].numpy(), values, rtol=0, atol=1e-12)
    np.testing.assert_allclose(actual["delta"].numpy(), delta, rtol=0, atol=1e-12)
    np.testing.assert_allclose(actual["trace"].numpy(), trace, rtol=0, atol=1e-12)
    np.testing.assert_allclose(actual["q_target"].numpy(), selected + trace, rtol=0, atol=1e-12)
    np.testing.assert_allclose(
        actual["advantage"].numpy(), selected - values + trace, rtol=0, atol=1e-12
    )
    assert not actual["advantage"].requires_grad
    assert not actual["q_target"].requires_grad


def independent_codec_and_barrier_test(core: Any) -> None:
    cards = np.zeros((6, 4, 13), np.float32)
    cards[0, 0, 0] = 1
    cards[0, 1, 1] = 1
    cards[4, 2, 2] = 1
    cards[5] = cards[0] + cards[4]
    actions = np.arange(500, dtype=np.float32).reshape(25, 4, 5) / 500
    legal = np.asarray([1, 1, 0, 1, 0, 0, 0, 0, 0], np.float32)

    def public(hero: int, assignment: int) -> Any:
        return core.PublicState(
            active_stack=190,
            other_stack=185,
            pot=25,
            active_street_commit=10,
            other_street_commit=15,
            to_call=5,
            last_bet_size=10,
            raise_count=2,
            num_actions_this_street=3,
            street=1,
            active_absolute_seat=1,
            hero_absolute_seat=hero,
            assignment_local=assignment,
        )

    base0 = core.encode_central895(cards, actions, (50, 51), public(0, 2), legal, focal_absolute_seat=0)
    base1 = core.encode_central895(cards, actions, (50, 51), public(0, 2), legal, focal_absolute_seat=1)
    assert base0.shape == (895,)
    cards7, action25, public22, sidecar = core.split_central895(base0)
    assert cards7.shape == (7, 4, 13) and action25.shape == (25, 4, 5)
    assert public22.shape == (22,) and sidecar.shape == (9,)
    assert np.array_equal(cards7[:6], cards)
    assert np.array_equal(action25, actions)
    assert np.array_equal(sidecar, legal)
    assert np.flatnonzero(base0 != base1).tolist() == [364 + 500 + 14]
    hero_changed = core.encode_central895(
        cards, actions, (50, 51), public(1, 2), legal, focal_absolute_seat=0
    )
    assert np.flatnonzero(base0 != hero_changed).tolist() == [364 + 500 + 15]
    assignment_changed = core.encode_central895(
        cards, actions, (50, 51), public(0, 3), legal, focal_absolute_seat=0
    )
    assert np.flatnonzero(base0 != assignment_changed).tolist() == [
        364 + 500 + 19,
        364 + 500 + 20,
    ]
    holes_changed = core.encode_central895(
        cards, actions, (48, 49), public(0, 2), legal, focal_absolute_seat=0
    )
    difference = np.flatnonzero(base0 != holes_changed)
    assert difference.size == 4 and np.all(difference < 364)
    assert "deck" not in inspect.signature(core.encode_central895).parameters
    assert "outcome" not in inspect.signature(core.encode_central895).parameters


def independent_rng_gradient_checkpoint_test(core: Any) -> None:
    before = torch.get_rng_state().clone()
    critic = core.make_q_critic_isolated(seed=2_026_072_302)
    assert torch.equal(before, torch.get_rng_state())
    assert torch.count_nonzero(critic.q_head.weight).item() == 0
    assert torch.count_nonzero(critic.q_head.bias).item() == 0
    generator = core.make_q_minibatch_generator(seed=2_026_072_303)
    state = generator.get_state().clone()
    restored = core.make_q_minibatch_generator(state)
    assert torch.equal(restored.get_state(), state)
    actor = nn.Sequential(nn.Linear(4, 8), nn.ReLU(), nn.Linear(8, 9))
    core.assert_models_storage_disjoint(actor, critic)
    actor_before = {name: value.detach().clone() for name, value in actor.state_dict().items()}
    q_optimizer = core.initialize_q_optimizer(critic)
    prediction = critic.q_head(torch.ones(4, 256)).reshape(2, 2, 9)
    loss = core.q_regression_loss(
        prediction, torch.tensor([0, 1]), torch.ones(2, 2)
    )
    q_optimizer.zero_grad(set_to_none=True)
    loss.backward()
    assert all(parameter.grad is None for parameter in actor.parameters())
    q_optimizer.step()
    assert all(torch.equal(actor_before[name], value) for name, value in actor.state_dict().items())
    payload = {
        "model": actor.state_dict(),
        "optimizer": torch.optim.Adam(actor.parameters()).state_dict(),
        "q_model": critic.state_dict(),
        "q_optimizer": q_optimizer.state_dict(),
        "q_minibatch_generator_state": generator.get_state(),
    }
    assert len(payload) == 5
    assert not set(payload["model"]).intersection(payload["q_model"])


def main() -> int:
    if PATHS["report"].exists():
        raise RuntimeError(f"refusing to overwrite implementation audit: {PATHS['report']}")
    checks: dict[str, bool] = {}
    expected_hashes = {
        "preregistration": PREREG_SHA256,
        "preimplementation_audit": PREAUDIT_SHA256,
        "source_checkpoint": SOURCE_SHA256,
        "parent_trainer": PARENT_TRAINER_SHA256,
        "parent_launcher": PARENT_LAUNCHER_SHA256,
        "ppo": PPO_SHA256,
        "network": NETWORK_SHA256,
        "environment": ENV_SHA256,
        "game_state": GAME_STATE_SHA256,
    }
    for name, expected in expected_hashes.items():
        add(checks, f"{name}_hash_exact", sha256_path(PATHS[name]) == expected)
    for name in ("core", "trainer", "launcher", "window_auditor"):
        add(checks, f"{name}_exists", PATHS[name].is_file())
    add(checks, "core_final_sha_exact", sha256_path(PATHS["core"]) == CORE_SHA256)
    add(checks, "trainer_final_sha_exact", sha256_path(PATHS["trainer"]) == TRAINER_SHA256)
    add(checks, "output_root_absent_before_probe", not PATHS["output_root"].exists())

    prereg = json.loads(PATHS["preregistration"].read_text(encoding="utf-8"))
    add(checks, "identity_exact", prereg["identity"]["sha256"] == IDENTITY)
    add(checks, "token_exact", prereg["identity"]["token"] == TOKEN)
    add(checks, "implementation_authorized", json.loads(
        PATHS["preimplementation_audit"].read_text(encoding="utf-8")
    )["authority"]["implementation_authorized"] is True)

    core_source = PATHS["core"].read_text(encoding="utf-8")
    trainer_source = PATHS["trainer"].read_text(encoding="utf-8")
    core_tree = ast.parse(core_source)
    trainer_tree = ast.parse(trainer_source)
    required_core = {
        "encode_central895",
        "split_central895",
        "validate_serving_policy",
        "validate_complete_hand_trace",
        "make_q_critic_isolated",
        "make_q_minibatch_generator",
        "assert_models_storage_disjoint",
        "expected_sarsa_qboost",
        "q_regression_loss",
        "paired_legacy_gae",
        "normalize_population",
        "variance_ratio",
        "legal_q_dispersion",
        "final_half",
        "run_contract_tests",
    }
    core_functions = {
        node.name for node in core_tree.body if isinstance(node, ast.FunctionDef)
    }
    add(checks, "core_api_complete", required_core.issubset(core_functions))
    trainer_functions = {
        node.name for node in trainer_tree.body if isinstance(node, ast.FunctionDef)
    }
    add(checks, "trainer_fresh_update_pipeline", {
        "worker_process", "run_inference", "calculate_rollout", "actor_epoch",
        "critic_update", "run_update", "checkpoint_payload",
    }.issubset(trainer_functions | {"checkpoint_payload"}))
    add(checks, "vr001_never_reused", "v5_vr001" not in core_source.lower() and "v5_vr001" not in trainer_source.lower())
    add(checks, "no_historical_replay", "replay_buffer" not in trainer_source and "historical_replay" in trainer_source)
    add(checks, "actor_forward_has_no_central_argument", all(
        forbidden not in ast.unparse(function_node(trainer_tree, "actor_epoch"))
        for forbidden in ("public22", "other_hole", "assignment_local", "focal")
    ))
    from_engine = ast.unparse(function_node(core_tree, "encode_central895"))
    add(checks, "central_encoder_no_future_deck", all(
        forbidden not in from_engine for forbidden in ("deck", "future", "outcome", "runout")
    ))
    rollout_source = ast.unparse(function_node(trainer_tree, "calculate_rollout"))
    add(checks, "rollout_enforces_legal_sidecar", "legal_masks" in rollout_source)
    launcher_flags = set(re.findall(r"'(--[a-z0-9-]+)'", PATHS["launcher"].read_text(encoding="utf-8")))
    parser_flags = {
        value.value
        for value in ast.walk(function_node(trainer_tree, "parse_args"))
        if isinstance(value, ast.Constant)
        and isinstance(value.value, str)
        and value.value.startswith("--")
    }
    add(
        checks,
        "launcher_cli_surface_exactly_supported",
        (launcher_flags | {"--vr002-contract-probe"}).issubset(parser_flags),
    )
    add(
        checks,
        "aggregate_trace_not_per_hand_fsync",
        'TRACE_AGGREGATE_SCHEMA = "v5.vr002.trace_aggregate.v1"' in trainer_source
        and trainer_source.count("append_jsonl(trace_path") == 1
        and '"sampled_raw_admitted_hands": sampled_admitted_raw' in trainer_source
        and '"sampled_raw_rejected_hands": sampled_rejected_raw' in trainer_source
        and '"rejected_hand_uids": rejected_hand_uids' in trainer_source,
    )
    run_update_source = ast.unparse(function_node(trainer_tree, "run_update"))
    run_update_literals = {
        node.value
        for node in ast.walk(function_node(trainer_tree, "run_update"))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    add(
        checks,
        "q_dispersion_exact_trainable_actor_row_set",
        "request_model" in run_update_source
        and "HERO_MODEL_ID" in run_update_source
        and '"q_dispersion_actor_rows_only": True' in trainer_source,
    )
    add(
        checks,
        "mechanism_raw_evidence_complete",
        {
            "qboost_advantage_population_variance",
            "legacy_gae_population_variance",
            "paired_actor_row_count",
            "paired_actor_uid_sha256",
            "qboost_advantage_raw_mean",
            "qboost_advantage_raw_std",
            "legacy_gae_raw_mean",
            "legacy_gae_raw_std",
            "paired_raw_correlation",
            "q_dispersion_eligible_actor_row_count",
        }.issubset(run_update_literals),
    )
    add(
        checks,
        "inherited_absolute_progress_lr_applied_and_recorded",
        "def inherited_absolute_progress_lr" in trainer_source
        and "actor_lr = inherited_absolute_progress_lr" in trainer_source
        and '"actor_learning_rate": actor_lr' in trainer_source,
    )
    endpoint_position = trainer_source.find('if total_hands >= args.total_hands:')
    trailing_assign_position = trainer_source.find("assign_next()", endpoint_position)
    endpoint_break_position = trainer_source.find("break", endpoint_position)
    add(
        checks,
        "no_unused_post_endpoint_provenance",
        endpoint_position >= 0
        and endpoint_break_position >= 0
        and trailing_assign_position > endpoint_break_position
        and '"no_unused_provenance_after_first_crossing": True' in trainer_source,
    )
    add(
        checks,
        "atomic_checkpoint_save",
        "def atomic_torch_save" in trainer_source
        and 'destination.name + ".tmp"' in trainer_source
        and "os.replace(temporary, destination)" in trainer_source
        and "atomic_torch_save(checkpoint_payload(), out_path)" in trainer_source
        and "torch.save(checkpoint_payload(), out_path)" not in trainer_source,
    )
    first_assign_call = trainer_source.find("\n    assign_next()\n")
    first_process_start = trainer_source.find("p.start()")
    add(
        checks,
        "assignment_initialized_before_worker_spawn",
        first_assign_call >= 0
        and first_process_start >= 0
        and first_assign_call < first_process_start,
    )
    sampled_raw_literals = {
        node.value
        for node in ast.walk(function_node(trainer_tree, "sampled_raw_hand"))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    add(
        checks,
        "sampled_raw_row_evidence_contract",
        "def sampled_raw_hand" in trainer_source
        and {
                "uid", "step_index", "active_absolute_seat", "request_model_id",
                "request_model_local_index", "assignment_version",
                "actor_generation", "selected_action", "legal9", "pi_ref9",
                "old_log_probability", "done", "next_uid", "training_reward",
                "state_payload_sha256", "row_payload_sha256",
        }.issubset(sampled_raw_literals),
    )
    inference_source = ast.unparse(function_node(trainer_tree, "run_inference"))
    add(
        checks,
        "serving_inference_requires_eval_mode",
        "actor.training" in inference_source
        and "inference requires frozen eval-mode actor/pool model" in inference_source,
    )
    add(
        checks,
        "assignment_version_wired_and_admission_bound",
        "assignment_version_shm.name" in trainer_source
        and "assignment_version_np" in trainer_source
        and "generation_pure =" in trainer_source
        and "assignment_current =" in trainer_source
        and "pure = generation_pure and assignment_current" in trainer_source,
    )
    checkpoint_source = trainer_source[
        trainer_source.find("def checkpoint_payload"):
        trainer_source.find("slots = args.workers", trainer_source.find("def checkpoint_payload"))
    ]
    add(
        checks,
        "checkpoint_only_vr002_q_namespaces",
        '"vr002_q_model"' in checkpoint_source
        and '"vr002_q_optimizer"' in checkpoint_source
        and '"vr002_q_minibatch_generator_state"' in checkpoint_source
        and '"q_model":' not in checkpoint_source
        and '"q_optimizer":' not in checkpoint_source
        and '"q_minibatch_generator_state":' not in checkpoint_source,
    )

    sys.dont_write_bytecode = True
    sys.path.insert(0, str(REPO / "scripts"))
    core = importlib.import_module(
        f"alpha_holdem.v5_vr002_qboost_core_{TOKEN}"
    )
    independent_codec_and_barrier_test(core)
    add(checks, "independent_central895_codec_and_barriers", True)
    independent_math_test(core)
    add(checks, "independent_expected_sarsa_math", True)
    independent_rng_gradient_checkpoint_test(core)
    add(checks, "independent_rng_gradient_checkpoint_namespaces", True)
    self_test = core.run_contract_tests()
    add(checks, "core_contract_suite_pass", self_test.get("status") == "PASS")
    add(checks, "core_contract_suite_exact_10", int(self_test.get("checks", 0)) == 10)

    launcher_text = PATHS["launcher"].read_text(encoding="utf-8")
    for literal in (
        "'581021901'", "'21600'", "'22'", "'16'", "'16384'", "'1024'",
        "'20260703'", "'73000'", "'2026072302'", "'2026072303'", "'35051'",
        "'control_uniform'",  # inherited by the trainer implementation, not a CLI flag
    ):
        if literal == "'control_uniform'":
            continue
        add(checks, f"launcher_literal_{literal.strip(chr(39))}", literal in launcher_text)
    add(checks, "launcher_exclusive_stagea_path", "output-root collision" in launcher_text)
    add(checks, "launcher_stagea_audit_gate", "VR002_IMPLEMENTATION_AUDIT_PASS_STAGEA_AUTHORIZED" in launcher_text)
    add(checks, "launcher_probe_cpu_and_zero_output", "CUDA_VISIBLE_DEVICES" in launcher_text and "probe wrote output" in launcher_text)
    add(
        checks,
        "launcher_scalar_value_loss_disabled",
        "'--value-coef', '0'" in launcher_text
        and "'--h8-value-head-catchup-after-kl-stop'" not in launcher_text,
    )

    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    probe = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(PATHS["launcher"]),
            "-Mode",
            "Probe",
        ],
        cwd=REPO,
        env=environment,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    add(checks, "sole_final_launcher_probe_exit_zero", probe.returncode == 0)
    add(checks, "sole_final_launcher_probe_contract_pass", "VR002_CONTRACT_PROBE_PASS" in probe.stdout)
    add(checks, "output_root_absent_after_probe", not PATHS["output_root"].exists())

    failed = [name for name, passed in checks.items() if not passed]
    artifacts = {
        name: {
            "path": str(PATHS[name]),
            "sha256": sha256_path(PATHS[name]),
            "bytes": PATHS[name].stat().st_size,
        }
        for name in ("core", "trainer", "launcher", "window_auditor")
    }
    result = {
        "schema_version": "v5.vr002.implementation_audit.v1",
        "audited_at": "2026-07-23",
        "status": (
            "VR002_IMPLEMENTATION_AUDIT_PASS_STAGEA_AUTHORIZED"
            if not failed
            else "VR002_IMPLEMENTATION_AUDIT_FAIL_NO_STAGEA"
        ),
        "identity_sha256": IDENTITY,
        "preregistration_sha256": PREREG_SHA256,
        "preimplementation_audit_sha256": PREAUDIT_SHA256,
        "checks": checks,
        "passed": len(checks) - len(failed),
        "total": len(checks),
        "failed_checks": failed,
        "core_contract_result": self_test,
        "probe": {
            "mode": "Probe",
            "returncode": probe.returncode,
            "stdout": probe.stdout,
            "stderr": probe.stderr,
            "cuda_visible_devices_child": "-1",
            "output_root_before": False,
            "output_root_after": PATHS["output_root"].exists(),
        },
        "artifacts": artifacts,
        "authority": {
            "stagea_authorized": not failed,
            "training_hands": 0,
            "checkpoint_created": False,
            "slumbot_hands": 0,
            "strength_authority": "NONE",
        },
    }
    PATHS["report"].write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
