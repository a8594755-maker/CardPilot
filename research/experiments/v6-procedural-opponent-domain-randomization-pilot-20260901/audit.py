from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import torch


ROOT = Path(__file__).resolve().parents[3]
BASE = Path(__file__).resolve().parent
PARENT = (
    ROOT
    / 'research'
    / 'experiments'
    / 'v6-actor-ema-terminal-smoke-20260831'
    / 'frozen'
    / 'raw.pt'
)
PARENT_SHA = '9fd38ad30ba25f46a80d2a103b55bb5a64affb7979a2fa47504cc187d38a2bf4'
START_PHYSICAL = 132553
START_TRANSITION_HANDS = 111390


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def rows(path: Path):
    return [
        json.loads(line)
        for line in path.read_text(encoding='utf-8-sig').splitlines()
        if line.strip()
    ]


def normalized_assignment(row):
    return {
        'applies_to_iteration': row['applies_to_iteration'],
        'assignment_mode': row['assignment_mode'],
        'group_metadata': row['group_metadata'],
        'pool_size': row['pool_size'],
        'pool_snapshot_refs': row['pool_snapshot_refs'],
        'worker_count': row['worker_count'],
        'worker_seed_base': row['worker_seed_base'],
        'workers': row['workers'],
    }


def main() -> None:
    parent = torch.load(PARENT, map_location='cpu', weights_only=False)
    manifests = {}
    checkpoints = {}
    metric_rows = {}
    assignment_rows = {}
    checks = {'parent_sha256': sha(PARENT) == PARENT_SHA}
    allowed = ('policy_head.', 'preflop_policy_head.', 'value_head.')
    changed = {}
    for arm in ('control', 'treatment'):
        run = BASE / arm
        manifests[arm] = json.loads(
            (run / 'run_manifest.json').read_text(encoding='utf-8-sig')
        )
        checkpoints[arm] = torch.load(
            run / 'latest.pt', map_location='cpu', weights_only=False
        )
        metric_rows[arm] = rows(run / 'h1_training_metrics.jsonl')
        assignment_rows[arm] = rows(run / 'opponent_assignments.jsonl')
        manifest = manifests[arm]
        checkpoint = checkpoints[arm]
        checks[f'{arm}_finished'] = manifest['status'] == 'finished'
        checks[f'{arm}_iterations_contiguous'] = (
            [row['iteration'] for row in metric_rows[arm]]
            == list(range(28, 44))
        )
        checks[f'{arm}_checkpoint_matches_manifest'] = (
            int(checkpoint['iteration']) == int(manifest['iteration']) == 43
            and int(checkpoint['total_hands']) == int(manifest['total_hands'])
            and checkpoint['environment_hand_accounting']
            == manifest['environment_hand_accounting']
            and checkpoint['procedural_opponent_accounting']
            == manifest['procedural_opponent_accounting']
        )
        checks[f'{arm}_physical_target_reached'] = (
            int(manifest['environment_hand_accounting']['completed_hands'])
            >= 198089
        )
        checks[f'{arm}_physical_prefix_preserved'] = (
            int(manifest['environment_hand_accounting']['completed_hands'])
            - int(manifest['environment_hand_accounting']['session_completed_hands'])
            == START_PHYSICAL
        )
        checks[f'{arm}_optimizer_lr_preserved'] = (
            [group['lr'] for group in parent['optimizer']['param_groups']]
            == [group['lr'] for group in checkpoint['optimizer']['param_groups']]
        )
        checks[f'{arm}_finite_metrics'] = all(
            math.isfinite(float(row[key]))
            for row in metric_rows[arm]
            for key in (
                'entropy',
                'approx_kl',
                'reference_policy_kl',
                'preupdate_critic_mse',
            )
        )
        changed[arm] = [
            name
            for name, value in parent['model'].items()
            if not torch.equal(value, checkpoint['model'][name])
        ]
        checks[f'{arm}_learned_weights_changed'] = bool(changed[arm])
        checks[f'{arm}_nontrainable_tensors_preserved'] = all(
            name.startswith(allowed) for name in changed[arm]
        )
        checks[f'{arm}_assignment_chain_length'] = (
            len(assignment_rows[arm]) == 16
            and assignment_rows[arm][0]['applies_to_iteration'] == 28
            and assignment_rows[arm][-1]['applies_to_iteration'] == 43
            and [row['applies_to_iteration'] for row in assignment_rows[arm]]
            == list(range(28, 44))
        )

    checks['matched_assignment_schedule'] = [
        normalized_assignment(row) for row in assignment_rows['control']
    ] == [
        normalized_assignment(row) for row in assignment_rows['treatment']
    ]
    checks['control_has_zero_procedural_hands'] = (
        manifests['control']['procedural_opponent_accounting']['session_hands']
        == 0
    )
    treatment_accounting = manifests['treatment'][
        'procedural_opponent_accounting'
    ]
    checks['treatment_procedural_accounting_consistent'] = (
        sum(treatment_accounting['session_style_counts'])
        == treatment_accounting['session_hands']
        and sum(treatment_accounting['session_action_counts'])
        == treatment_accounting['session_decisions']
        == treatment_accounting['session_inference_bypasses']
        and all(value > 0 for value in treatment_accounting['session_style_counts'])
        and all(value > 0 for value in treatment_accounting['session_action_counts'])
    )

    heldout_dir = BASE / 'heldout_greedy_32k'
    heldout = json.loads(
        (heldout_dir / 'summary.json').read_text(encoding='utf-8-sig')
    )
    pair_rows = rows(heldout_dir / 'pairs.jsonl')
    deltas = np.asarray([
        row['treatment_minus_control_bb_per_100'] for row in pair_rows
    ], dtype=np.float64)
    delta_mean = float(deltas.mean())
    delta_half = float(1.96 * deltas.std(ddof=1) / math.sqrt(len(deltas)))
    block_means = [
        float(np.mean([
            row['treatment_minus_control_bb_per_100']
            for row in pair_rows
            if row['block_index'] == block
        ]))
        for block in range(8)
    ]
    checks['heldout_pair_count_and_hash'] = (
        len(pair_rows) == heldout['pairs'] == 32768
        and sha(heldout_dir / 'pairs.jsonl') == heldout['pairs_sha256']
    )
    checks['heldout_raw_recompute_exact'] = (
        abs(delta_mean - heldout['treatment_minus_control_bb_per_100']) < 1e-12
        and abs(delta_mean - delta_half - heldout['paired_delta_ci95'][0]) < 1e-12
        and abs(delta_mean + delta_half - heldout['paired_delta_ci95'][1]) < 1e-12
        and all(
            abs(value - heldout['blocks'][index]['treatment_minus_control_bb_per_100']) < 1e-12
            for index, value in enumerate(block_means)
        )
    )
    checks['heldout_primary_gate_passed'] = (
        heldout['gate']['passed']
        and heldout['positive_blocks'] == 7
        and heldout['paired_delta_ci95'][0] > 0
    )

    preservation_dir = BASE / 'preservation'
    preservation = json.loads(
        (preservation_dir / 'summary.json').read_text(encoding='utf-8-sig')
    )
    state_rows = rows(preservation_dir / 'state_metrics.jsonl')
    treatment_tv = np.asarray([
        row['treatment_total_variation'] for row in state_rows
    ])
    treatment_disagreement = np.asarray([
        row['treatment_greedy_disagreement'] for row in state_rows
    ])
    checks['preservation_state_count_and_hash'] = (
        len(state_rows) == preservation['states'] == 14963
        and sha(preservation_dir / 'state_metrics.jsonl')
        == preservation['state_metrics_sha256']
    )
    checks['preservation_raw_recompute_exact'] = (
        abs(float(treatment_tv.mean()) - preservation['treatment_mean_total_variation']) < 1e-12
        and abs(float(treatment_disagreement.mean()) - preservation['treatment_greedy_disagreement_rate']) < 1e-12
    )
    checks['preservation_gate_failed_as_reported'] = (
        not preservation['gate']['passed']
        and preservation['treatment_mean_total_variation'] > 0.02
        and preservation['treatment_greedy_disagreement_rate'] > 0.02
    )

    report = {
        'schema': 'cardpilot.procedural_domain_pilot_audit.v1',
        'passed': all(checks.values()),
        'checks': checks,
        'parent_sha256': sha(PARENT),
        'control_sha256': sha(BASE / 'control' / 'latest.pt'),
        'treatment_sha256': sha(BASE / 'treatment' / 'latest.pt'),
        'new_environment_hands': {
            arm: int(manifests[arm]['environment_hand_accounting']['completed_hands']) - START_PHYSICAL
            for arm in ('control', 'treatment')
        },
        'new_transition_hands': {
            arm: int(manifests[arm]['total_hands']) - START_TRANSITION_HANDS
            for arm in ('control', 'treatment')
        },
        'changed_model_tensors': changed,
        'heldout': {
            'pairs': len(pair_rows),
            'evaluation_hands': heldout['evaluation_hands'],
            'paired_delta_bb_per_100': delta_mean,
            'paired_delta_ci95': [delta_mean - delta_half, delta_mean + delta_half],
            'block_means': block_means,
            'positive_blocks': sum(value > 0 for value in block_means),
        },
        'preservation': {
            'states': len(state_rows),
            'treatment_mean_total_variation': float(treatment_tv.mean()),
            'treatment_greedy_disagreement_rate': float(treatment_disagreement.mean()),
            'gate_passed': preservation['gate']['passed'],
        },
        'decision': 'FINAL_TREATMENT_JOINT_GATE_NOT_PASSED',
        'artifact_hashes': {
            str(path.relative_to(ROOT)): sha(path)
            for path in (
                BASE / 'control' / 'latest.pt',
                BASE / 'treatment' / 'latest.pt',
                heldout_dir / 'summary.json',
                heldout_dir / 'pairs.jsonl',
                preservation_dir / 'summary.json',
                preservation_dir / 'state_metrics.jsonl',
            )
        },
    }
    output = BASE / 'audit.json'
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding='utf-8')
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
