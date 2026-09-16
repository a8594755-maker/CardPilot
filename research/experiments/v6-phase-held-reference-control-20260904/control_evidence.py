"""Read-only checks for this preregistered two-arm control, not a new trainer."""
from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(ROOT / 'scripts/alpha_holdem'))
from aggregate_v6_static_current_kl_262k import ANCHORS, read_rows, summarize_rows


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def module_at(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def reference_state(checkpoint, activation=882):
    state = checkpoint['moving_source_policy_reference']
    iteration = int(checkpoint['iteration'])
    completed = iteration - activation
    expected = {'schema_version': 'alpha_holdem.moving_source_policy_reference.v1',
                'direction': 'current_to_reference', 'refresh_interval_updates': 256,
                'completed_updates': completed, 'last_refresh_update': completed // 256 * 256,
                'reference_round': completed // 256, 'activation_iteration': activation,
                'trainer_iteration': iteration}
    require(completed >= 0 and all(state.get(k) == v for k, v in expected.items()),
            'wrong reference activation/cadence/counters')
    require(bool(state.get('reference_model')) and isinstance(state.get('rng_state'), dict),
            'missing serialized reference model/RNG')
    return state


def initial_reference(arm, parent, initial, equal):
    if arm == 'static':
        require(initial.get('moving_source_policy_reference') is None, 'static became moving')
        require(initial['config']['source_policy_reference_refresh_updates'] == 0, 'static cadence')
        require(Path(initial['config']['source_policy_reference_checkpoint']).resolve() ==
                (ROOT / 'models/baseline/standard10/latest.pt').resolve(), 'static source changed')
        return
    state = reference_state(initial)
    prior = parent.get('moving_source_policy_reference')
    if prior is None:
        require(initial['iteration'] == 882, 'only original4M may activate moving reference')
        require(equal(state['reference_model'], parent['model']), 'initial reference not original actor')
    else:
        for key in ('reference_model', 'activation_iteration', 'completed_updates',
                    'last_refresh_update', 'reference_round', 'trainer_iteration'):
            require(equal(state[key], prior[key]), f'moving resume changed {key}')


def verify_reference_windows(arm, parent, initial, checkpoints, metrics, equal):
    initial_reference(arm, parent, initial, equal)
    start = int(parent['iteration'])
    end = int(checkpoints[-1]['iteration'])
    rows = [row for row in metrics if int(row['iteration']) > start]
    require([row['iteration'] for row in rows] == list(range(start + 1, end + 1)), 'reference metric gap')
    if arm == 'static':
        require(all(c.get('moving_source_policy_reference') is None for c in checkpoints), 'static reference changed')
        require(all(row['moving_reference_refresh_updates'] == 0 and not row['moving_reference_refreshed']
                    for row in rows), 'static refreshed')
        return {'passed': True, 'arm': arm, 'verified_updates': len(rows), 'phase_boundaries': []}
    phases = {reference_state(initial)['reference_round']: reference_state(initial)['reference_model']}
    boundaries = []
    for ckpt in checkpoints:
        state = reference_state(ckpt)
        if state['completed_updates'] % 256 == 0 and ckpt['iteration'] > start:
            require(equal(state['reference_model'], ckpt['model']), 'refresh not exact completed actor')
            phases[state['reference_round']] = state['reference_model']
            boundaries.append({'iteration': ckpt['iteration'], 'physical_hands':
                               ckpt['environment_hand_accounting']['completed_hands'],
                               'round': state['reference_round']})
        require(state['reference_round'] in phases, 'missing actual phase-boundary checkpoint')
        require(equal(state['reference_model'], phases[state['reference_round']]), 'reference changed inside phase')
    expected = [i for i in range(start + 1, end + 1) if (i - 882) % 256 == 0]
    require(sorted(set(row['iteration'] for row in boundaries)) == expected, 'missing refresh evidence')
    for row in rows:
        count = int(row['iteration']) - 882
        expected_row = {'moving_reference_refresh_updates': 256,
                        'moving_reference_completed_updates': count,
                        'moving_reference_last_refresh_update': count // 256 * 256,
                        'moving_reference_round': count // 256,
                        'moving_reference_refreshed': count % 256 == 0}
        require(all(row.get(k) == v for k, v in expected_row.items()), 'per-update reference cadence mismatch')
    return {'passed': True, 'arm': arm, 'verified_updates': len(rows),
            'phase_boundaries': boundaries, 'last_reference_round': reference_state(checkpoints[-1])['reference_round']}


def derived_row(row, control, treatment):
    delta = [treatment[s] - control[s] for s in (0, 1)]
    return {**row, 'control_rewards_bb': control, 'treatment_rewards_bb': treatment,
            'treatment_minus_control_rewards_bb': delta,
            'control_pair_mean_bb': sum(control) / 2, 'treatment_pair_mean_bb': sum(treatment) / 2,
            'treatment_minus_control_pair_mean_bb': sum(delta) / 2}


def validated_map(rows):
    result, decks = {}, set()
    for row in rows:
        deck = tuple(row['deck'])
        require(sorted(deck) == list(range(52)), 'invalid physical deck')
        require(deck not in decks, 'repeated deck inside evaluation')
        decks.add(deck)
        control, treatment = row['control_rewards_bb'], row['treatment_rewards_bb']
        require(len(control) == len(treatment) == 2 and
                all(math.isfinite(v) and abs(v) <= 200 for v in control + treatment), 'invalid both-seat reward')
        expected = derived_row(row, control, treatment)
        for key in ('control_pair_mean_bb', 'treatment_pair_mean_bb', 'treatment_minus_control_pair_mean_bb'):
            require(math.isclose(expected[key], row[key], abs_tol=1e-9), 'incorrect paired arithmetic')
        require(all(math.isclose(a, b, abs_tol=1e-9) for a, b in zip(
            expected['treatment_minus_control_rewards_bb'], row['treatment_minus_control_rewards_bb']))
            and len(row['treatment_minus_control_rewards_bb']) == 2, 'incorrect seat delta')
        key = (row['anchor'], row['anchor_seed'], row['pair_index'])
        require(key not in result, 'duplicate pair identity')
        result[key] = row
    return result


def join_arms(static_rows, moving_rows):
    left, right = validated_map(static_rows), validated_map(moving_rows)
    require(left.keys() == right.keys(), 'unmatched arm identities')
    joined = []
    for key, a in left.items():
        b = right[key]
        require(a['deck'] == b['deck'], 'matched identifier but different deck')
        require(a['control_rewards_bb'] == b['control_rewards_bb'], 'repeated original parent outcome mismatch')
        joined.append(derived_row(a, a['treatment_rewards_bb'], b['treatment_rewards_bb']))
    return joined


def broad_collapse(summary):
    return (sum(v['ci95_high_bb100'] < -25 for v in summary['by_anchor'].values()) >= 3
            and all(summary['by_seat'][str(s)]['ci95_high_bb100'] < 0 for s in (0, 1)))


def check_prior_decks(rows, corpus):
    new_decks = {tuple(row['deck']) for row in rows}
    checked = 0
    for path, digest in corpus.items():
        require(sha(path) == digest, f'prior evaluation evidence changed: {path}')
        with gzip.open(path, 'rt', encoding='utf-8') as handle:
            for line in handle:
                if line.strip():
                    old = json.loads(line)
                    require(tuple(old['deck']) not in new_decks, 'fresh cohort overlaps earlier evidence')
                    checked += 1
        require(sha(path) == digest, 'prior evidence changed during comparison')
    return {'passed': True, 'prior_files': len(corpus), 'prior_rows_checked': checked,
            'new_unique_decks': len(new_decks), 'overlap': 0,
            'scope': 'all inventoried common_deck_pairs.jsonl.gz; not every historical poker corpus'}


def aggregate_stage(stage, base, parent_sha, endpoint_hashes, anchors, prior_corpus):
    by_arm, absolute, drift, inputs = {}, {}, {}, {}
    for arm in ('static', 'moving256'):
        directory = base / f'eval_{arm}_stage{stage}'
        summary_path, raw_path = directory / 'summary.json', directory / 'common_deck_pairs.jsonl.gz'
        summary, rows = read_json(summary_path), read_rows(raw_path)
        inputs.update({str(summary_path): sha(summary_path), str(raw_path): sha(raw_path)})
        require(summary['status'] == 'COMPLETED' and summary['evaluation_hands'] == 32768,
                'incomplete evaluation')
        require(len(rows) == len(validated_map(rows)) == 8192, 'wrong pair count')
        require(summary['raw_pairs_sha256'] == sha(raw_path), 'raw hash mismatch')
        require(summary['policy_mode'] == 'greedy' and summary['starting_stack_bb'] == 200, 'wrong eval contract')
        require(summary['command'][summary['command'].index('--seed') + 1] == str(20263410 + stage), 'wrong seed')
        require(summary['input_sha256'] == {'control': parent_sha, 'treatment': endpoint_hashes[arm],
                **{f'anchor:{k}': v['sha256'] for k, v in anchors.items()}}, 'evaluation model hashes mismatch')
        for name in ANCHORS:
            selected = [r for r in rows if r['anchor'] == name]
            require(len(selected) == 2048 and sorted(r['pair_index'] for r in selected) == list(range(2048)),
                    'missing anchor pairs')
        by_arm[arm] = rows
        absolute[arm] = summarize_rows([derived_row(r, [0., 0.], r['treatment_rewards_bb']) for r in rows])
        dpath = base / f'drift_{arm}_stage{stage}' / 'drift_analysis.json'
        d = read_json(dpath)
        dr = dpath.parent / 'drift_raw.jsonl.gz'
        inputs.update({str(dpath): sha(dpath), str(dr): sha(dr)})
        require(d['status'] == 'PASS' and d['design']['states'] == 20000 and
                d['design']['seed'] == 20263420 + stage and d['overall']['states'] == 20000,
                'drift state/contract mismatch')
        require(d['raw_sha256'] == sha(dr) and len(read_rows(dr)) == 20000, 'drift raw evidence mismatch')
        require(d['parent']['sha256'] == anchors['standard10']['sha256'] and
                d['treatment']['sha256'] == endpoint_hashes[arm], 'drift checkpoint mismatch')
        require(d['tensor_scope']['status'] == 'PASS' and not d['checkpoint_metadata_mismatches'], 'wrong learned scope')
        drift[arm] = {'overall': d['overall'], 'by_street': d['by_street'],
                      'scope': 'Standard10-to-endpoint on fixed generic rollout states; not original4M drift or strength'}
    contrast_rows = join_arms(by_arm['static'], by_arm['moving256'])
    contrast = summarize_rows(contrast_rows)
    independence = check_prior_decks(by_arm['static'], prior_corpus)
    return {'schema': 'cardpilot.phase_held_reference.stage.v1', 'passed': True, 'stage': stage,
            'evaluation_hands': 65536, 'offline_states': 40000, 'input_sha256': inputs,
            'endpoint_minus_original4M': {arm: summarize_rows(rows) for arm, rows in by_arm.items()},
            'absolute_endpoint_vs_anchors': absolute, 'moving_minus_static': contrast, 'drift': drift,
            'parent_rewards_exact_across_arms': True, 'intentional_repeated_parent_evaluation_hands': 32768,
            'independence': independence, 'broad_collapse': broad_collapse(contrast),
            'ci_scope': 'paired deck means conditional on fixed Seed1 endpoints/anchors, not training-seed uncertainty',
            'final_goal_qualified': False}
