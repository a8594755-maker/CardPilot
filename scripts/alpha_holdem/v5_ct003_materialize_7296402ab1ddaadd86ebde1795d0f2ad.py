#!/usr/bin/env python3
"""Materialize the registered CT003 trainer from the frozen LG003C1 control parent."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PARENT = ROOT / "scripts/alpha_holdem/v5_lg003c1_train_8bf8cedf78b6e8c8fe153802908ed893.py"
OUTPUT = ROOT / "scripts/alpha_holdem/v5_ct003_train_7296402ab1ddaadd86ebde1795d0f2ad.py"
PARENT_SHA256 = "f841144c883d51e66a1d2de889e15303e7339695c8664f81e60208ff77770452"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, observed {count}")
    return text.replace(old, new, 1)


def materialize_text() -> str:
    raw = PARENT.read_bytes()
    if sha256_bytes(raw) != PARENT_SHA256:
        raise RuntimeError("CT003 frozen parent hash mismatch")
    text = raw.decode("utf-8")

    constants_marker = """LG003_CHECKPOINT_ORDER = (109, 115, 120, 129, 103)
LG003_WEIGHTS = {"""
    constants_replacement = """LG003_CHECKPOINT_ORDER = (109, 115, 120, 129, 103)
CT003_TOKEN = '7296402ab1ddaadd86ebde1795d0f2ad'
CT003_IDENTITY_SHA256 = '7296402ab1ddaadd86ebde1795d0f2ade6f8c609f8f13aa1c41035c6470761a0'
CT003_PREREG_SHA256 = '7702ff2d7323bcb053443a7b1e540e4624f43e3d932bfd2c3ecbb7afb0bb11fe'
CT003_TARGET_MODE = 'full_trajectory_discounted_mc_gamma_0.999'
LG003_WEIGHTS = {"""
    text = replace_once(text, constants_marker, constants_replacement, "constants")

    helper_marker = """

def lg003_assignment_u64(absolute_iteration: int) -> int:
"""
    helper_replacement = """

def ct003_attach_mc_critic_targets(transitions, gamma: float):
    \"\"\"Append an all-row critic-only Monte-Carlo target without changing fields0..11.\"\"\"
    gamma = float(gamma)
    if not (0.0 < gamma <= 1.0):
        raise ValueError('CT003 gamma must be in (0,1]')
    rows = [tuple(row) for row in transitions]
    if not rows:
        raise ValueError('CT003 requires at least one complete trajectory')
    if any(len(row) != 12 for row in rows):
        raise ValueError('CT003 requires exact 12-field source transitions')
    if float(rows[-1][8]) != 1.0:
        raise ValueError('CT003 final transition must close a trajectory')
    attached = [None] * len(rows)
    running = 0.0
    for index in range(len(rows) - 1, -1, -1):
        row = rows[index]
        done = float(row[8])
        if done not in (0.0, 1.0):
            raise ValueError('CT003 done marker must be exactly0 or1')
        reward = float(row[6])
        if not math.isfinite(reward):
            raise ValueError('CT003 reward must be finite')
        running = reward + gamma * (1.0 - done) * running
        if not math.isfinite(running):
            raise ValueError('CT003 Monte-Carlo target must be finite')
        attached[index] = row + (float(running),)
    return attached


def lg003_assignment_u64(absolute_iteration: int) -> int:
"""
    text = replace_once(text, helper_marker, helper_replacement, "helper")

    old_root = """            / 'v5_lg003c1_8bf8cedf78b6e8c8fe153802908ed893_20260723'
"""
    new_root = """            / 'v5_ct003_7296402ab1ddaadd86ebde1795d0f2ad_20260723'
"""
    text = replace_once(text, old_root, new_root, "output_root")

    validation_marker = """    if lg003_active:
        workspace = Path(__file__).resolve().parents[2]
        expected_prereg = (
"""
    validation_replacement = """    if lg003_active:
        workspace = Path(__file__).resolve().parents[2]
        ct003_prereg = (
            workspace / 'reports'
            / 'v5_ct003_mc_critic_target_preregistration_7296402ab1ddaadd86ebde1795d0f2ad_20260723.json'
        ).resolve()
        if (
            not ct003_prereg.is_file()
            or sha256_path(ct003_prereg) != CT003_PREREG_SHA256
            or args.lg003_arm != 'control_uniform'
        ):
            parser.error('CT003 preregistration or uniform-control contract mismatch')
        expected_prereg = (
"""
    text = replace_once(text, validation_marker, validation_replacement, "validation")

    contract_marker = """            'pool_mutation_disabled': True,
        }
        if args.lg003_contract_probe:
"""
    contract_replacement = """            'pool_mutation_disabled': True,
            'ct003_registration_token': CT003_TOKEN,
            'ct003_identity_sha256': CT003_IDENTITY_SHA256,
            'ct003_preregistration_sha256': CT003_PREREG_SHA256,
            'ct003_behavior_variable': 'critic_target_estimator_only',
            'ct003_target_mode': CT003_TARGET_MODE,
            'ct003_actor_gae': 'gamma0.999_lambda0.95_unchanged',
        }
        if args.lg003_contract_probe:
"""
    text = replace_once(text, contract_marker, contract_replacement, "contract")

    probe_marker = """            probe = {
                'schema_version': 'v5.lg003.contract_probe.v1',
                'status': 'PASS',
"""
    probe_replacement = """            synthetic = [
                (None, None, None, None, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0),
                (None, None, None, None, 0, 0.0, 2.0, 0.0, 1.0, 0.0, 0.0, 1),
                (None, None, None, None, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0),
                (None, None, None, None, 0, 0.0, -3.0, 0.0, 1.0, 0.0, 0.0, 1),
            ]
            attached = ct003_attach_mc_critic_targets(synthetic, 0.999)
            expected_targets = (1.998, 2.0, -2.997, -3.0)
            if any(
                attached[index][:12] != synthetic[index]
                or abs(attached[index][12] - expected_targets[index]) > 1e-12
                for index in range(4)
            ):
                parser.error('CT003 synthetic target recursion or tuple preservation failed')
            if torch.cuda.is_initialized():
                parser.error('CT003 contract probe initialized CUDA')
            probe = {
                'schema_version': 'v5.ct003.contract_probe.v1',
                'status': 'PASS',
                'ct003_target_contract': {
                    'synthetic_trajectories': 2,
                    'synthetic_rows': 4,
                    'expected_targets': list(expected_targets),
                    'first12_fields_unchanged': True,
                    'actor_gae_unchanged': True,
                },
"""
    text = replace_once(text, probe_marker, probe_replacement, "probe")

    text = replace_once(
        text,
        "'gpu_initialized': False,",
        "'gpu_initialized': bool(torch.cuda.is_initialized()),",
        "probe_gpu_state",
    )

    call_marker = """                mix = action_mix(iter_transitions)
                phase_mix = action_mix_by_phase(iter_transitions)
                stats = trinal_clip_ppo_update(
"""
    call_replacement = """                iter_transitions = ct003_attach_mc_critic_targets(
                    iter_transitions, gamma=args.gamma,
                )
                mix = action_mix(iter_transitions)
                phase_mix = action_mix_by_phase(iter_transitions)
                stats = trinal_clip_ppo_update(
"""
    text = replace_once(text, call_marker, call_replacement, "callsite")

    post_update_marker = """                )
                ppo_time = time.time() - t1
                # Keep loss-kbest in raw-BB-equivalent units.
"""
    post_update_replacement = """                )
                ct003_rows = int(stats.get('h2_critic_target_override_rows', -1))
                ct003_fraction = float(stats.get('h2_critic_target_override_fraction', -1.0))
                if ct003_rows != len(iter_transitions) or ct003_fraction != 1.0:
                    raise RuntimeError(
                        f'CT003 target coverage mismatch rows={ct003_rows}/'
                        f'{len(iter_transitions)} fraction={ct003_fraction}'
                    )
                stats['ct003_mc_target_rows'] = ct003_rows
                stats['ct003_mc_target_fraction'] = ct003_fraction
                stats['ct003_target_mode'] = CT003_TARGET_MODE
                ppo_time = time.time() - t1
                # Keep loss-kbest in raw-BB-equivalent units.
"""
    text = replace_once(text, post_update_marker, post_update_replacement, "post_update_gate")

    metrics_marker = """                        'critic_contract': args.critic_contract, 'value_coef': args.value_coef,
                        'approx_kl': float(stats.get('approx_kl', 0.0)),
"""
    metrics_replacement = """                        'critic_contract': args.critic_contract, 'value_coef': args.value_coef,
                        'ct003_target_mode': stats['ct003_target_mode'],
                        'ct003_mc_target_rows': int(stats['ct003_mc_target_rows']),
                        'ct003_mc_target_fraction': float(stats['ct003_mc_target_fraction']),
                        'approx_kl': float(stats.get('approx_kl', 0.0)),
"""
    text = replace_once(text, metrics_marker, metrics_replacement, "metrics")

    ast.parse(text)
    return text


def main() -> int:
    text = materialize_text()
    if OUTPUT.exists():
        raise RuntimeError(f"CT003 output already exists: {OUTPUT}")
    OUTPUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"materialized={OUTPUT}")
    print(f"sha256={sha256_bytes(OUTPUT.read_bytes())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
