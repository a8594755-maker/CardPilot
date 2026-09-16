from __future__ import annotations

import hashlib
import json
import math
import random
import sys
from pathlib import Path

import torch


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts' / 'alpha_holdem'))

from scripts.alpha_holdem.train_v5 import (  # noqa: E402
    PROCEDURAL_OPPONENT_PROFILES,
    procedural_opponent_hand_seed,
    sample_procedural_opponent_style,
    validate_procedural_opponent_accounting,
)

EXP = Path(__file__).resolve().parent
RUN = EXP / 'production' / 'train_r2'
PARENT = (
    ROOT
    / 'research'
    / 'experiments'
    / 'v6-actor-ema-terminal-smoke-20260831'
    / 'frozen'
    / 'raw.pt'
)
EXPECTED_PARENT_SHA256 = (
    '9fd38ad30ba25f46a80d2a103b55bb5a64affb7979a2fa47504cc187d38a2bf4'
)
START_ENVIRONMENT_HANDS = 132553
START_TRAINING_HANDS = 111390
START_ITERATION = 27
DEAL_START_INDEX = 132553
WORKER_SEED_BASE = 2026110600
TARGET_ENVIRONMENT_HANDS = 136649


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def load_rows(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding='utf-8-sig').splitlines()
        if line.strip()
    ]


def main() -> None:
    metrics_path = RUN / 'h1_training_metrics.jsonl'
    manifest_path = RUN / 'run_manifest.json'
    checkpoint_path = RUN / 'latest.pt'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    rows = load_rows(metrics_path)
    parent = torch.load(PARENT, map_location='cpu', weights_only=False)
    candidate = torch.load(checkpoint_path, map_location='cpu', weights_only=False)
    accounting = manifest['procedural_opponent_accounting']
    validate_procedural_opponent_accounting(accounting)

    checks = {
        'parent_sha256': sha256(PARENT) == EXPECTED_PARENT_SHA256,
        'manifest_finished': manifest['status'] == 'finished',
        'iterations_contiguous': [row['iteration'] for row in rows] == [28, 29],
        'checkpoint_iteration': int(candidate['iteration']) == 29,
        'checkpoint_training_hands_match_manifest': (
            int(candidate['total_hands']) == int(manifest['total_hands'])
        ),
        'environment_target_reached': (
            int(manifest['environment_hand_accounting']['completed_hands'])
            >= TARGET_ENVIRONMENT_HANDS
        ),
        'environment_prefix_preserved': (
            int(manifest['environment_hand_accounting']['completed_hands'])
            - int(manifest['environment_hand_accounting']['session_completed_hands'])
            == START_ENVIRONMENT_HANDS
        ),
        'training_prefix_preserved': (
            int(manifest['total_hands']) - START_TRAINING_HANDS > 0
            and int(candidate['iteration']) > START_ITERATION
        ),
        'all_session_hands_are_procedural': (
            int(accounting['session_hands'])
            == int(manifest['environment_hand_accounting']['session_completed_hands'])
        ),
        'all_profiles_covered': all(
            int(value) > 0 for value in accounting['session_style_counts']
        ),
        'fold_call_raise_and_allin_covered': (
            int(accounting['session_action_counts'][0]) > 0
            and int(accounting['session_action_counts'][1]) > 0
            and sum(accounting['session_action_counts'][2:8]) > 0
            and int(accounting['session_action_counts'][8]) > 0
        ),
        'bypass_equals_decisions': (
            int(accounting['session_inference_bypasses'])
            == int(accounting['session_decisions'])
        ),
        'checkpoint_accounting_matches_manifest': (
            candidate['procedural_opponent_accounting'] == accounting
        ),
        'jsonl_final_accounting_matches_manifest': (
            rows[-1]['procedural_opponent_accounting'] == accounting
        ),
        'finite_optimizer_metrics': all(
            math.isfinite(float(row[key]))
            for row in rows
            for key in ('entropy', 'approx_kl', 'preupdate_critic_mse')
        ) and all(
            math.isfinite(float(manifest['latest_metrics'][key]))
            for key in ('policy_loss', 'value_loss')
        ),
        'optimizer_lr_preserved': (
            [group['lr'] for group in parent['optimizer']['param_groups']]
            == [group['lr'] for group in candidate['optimizer']['param_groups']]
        ),
    }

    replay_style_counts = [0 for _ in PROCEDURAL_OPPONENT_PROFILES]
    worker_hand_counts_match = True
    environment_workers = {
        int(row['worker_id']): int(row['completed_hands'])
        for row in manifest['environment_hand_accounting']['session_worker_counts']
    }
    for worker in accounting['session_worker_counts']:
        worker_id = int(worker['worker_id'])
        hand_count = int(worker['hands'])
        worker_hand_counts_match &= hand_count == environment_workers[worker_id]
        for local_index in range(hand_count):
            rng = random.Random(
                procedural_opponent_hand_seed(
                    WORKER_SEED_BASE + worker_id,
                    DEAL_START_INDEX + local_index,
                )
            )
            assert rng.random() < 1.0
            style = sample_procedural_opponent_style(rng)
            replay_style_counts[int(style['profile_id'])] += 1
    checks['worker_hand_counts_match_environment'] = worker_hand_counts_match
    checks['style_assignment_replay_exact'] = (
        replay_style_counts == accounting['session_style_counts']
    )

    allowed_prefixes = ('policy_head.', 'preflop_policy_head.', 'value_head.')
    changed = [
        name
        for name, value in parent['model'].items()
        if not torch.equal(value, candidate['model'][name])
    ]
    checks['learned_weights_changed'] = bool(changed)
    checks['nontrainable_tensors_bitwise_preserved'] = all(
        name.startswith(allowed_prefixes) for name in changed
    )

    report = {
        'schema': 'cardpilot.procedural_opponent_contract_audit.v1',
        'passed': all(checks.values()),
        'checks': checks,
        'parent_sha256': sha256(PARENT),
        'candidate_sha256': sha256(checkpoint_path),
        'new_environment_hands': (
            int(manifest['environment_hand_accounting']['completed_hands'])
            - START_ENVIRONMENT_HANDS
        ),
        'new_transition_bearing_hands': int(manifest['total_hands']) - START_TRAINING_HANDS,
        'procedural_opponent_hands': int(accounting['session_hands']),
        'procedural_opponent_decisions': int(accounting['session_decisions']),
        'style_counts': accounting['session_style_counts'],
        'replayed_style_counts': replay_style_counts,
        'action_counts': accounting['session_action_counts'],
        'changed_model_tensors': changed,
        'iterations': [row['iteration'] for row in rows],
        'approx_kl': [row['approx_kl'] for row in rows],
        'hands_per_second': [row['hands_per_second'] for row in rows],
        'artifacts': {
            str(path.relative_to(ROOT)): sha256(path)
            for path in (metrics_path, manifest_path, checkpoint_path)
        },
    }
    output = EXP / 'audit.json'
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding='utf-8')
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
