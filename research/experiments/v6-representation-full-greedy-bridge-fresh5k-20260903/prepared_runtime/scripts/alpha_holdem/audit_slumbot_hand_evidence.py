"""Strict frozen native-policy evidence audit; never plays or repairs poker hands.

Paths in a manifest are relative to its directory unless absolute. This strict
new-run contract intentionally rejects historical rows without clean-execution
telemetry. It does not retroactively invalidate those historical experiments.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics

try:
    from .audit_slumbot_session_independence import audit_paths, initial_deal_fingerprint
    from .slumbot_ci_from_hands import summarize, DEFAULT_BASELINE_BB100
except ImportError:
    from audit_slumbot_session_independence import audit_paths, initial_deal_fingerprint
    from slumbot_ci_from_hands import summarize, DEFAULT_BASELINE_BB100


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def integer(value, label: str) -> int:
    if type(value) is not int:
        raise ValueError(f'{label} must be an integer, not coerced numeric data')
    return value


def close(actual, expected, label):
    if (isinstance(actual, bool) or not isinstance(actual, (int, float))
            or not math.isfinite(actual) or not math.isclose(actual, expected, abs_tol=1e-8, rel_tol=0)):
        raise ValueError(f'{label} disagrees with raw evidence')


def jsonl(path: Path) -> list[dict]:
    data = path.read_text(encoding='utf-8-sig')
    if not data or not data.endswith('\n'):
        raise ValueError(f'Empty or unterminated final JSONL: {path}')
    return [json.loads(line) for line in data.splitlines() if line.strip()]


def validate_session(raw, dump, result, spec, policy, execution=None):
    n = integer(spec['requested_hands'], 'requested_hands')
    if n < 1 or len(raw) != n:
        raise ValueError('Raw hand count does not match preregistered session size')
    if (integer(result['requested_hands'], 'result requested_hands') != n
            or integer(result['successful_hands'], 'successful_hands') != n
            or result.get('dry_run', False)):
        raise ValueError('Incomplete or dry-run result')
    for key, expected in [('model_sha256', policy['sha256']), ('strategy', 'model'),
                          ('obs_version', policy['obs_version']), ('policy_mode_raw', policy['policy_mode']),
                          ('policy_seed', spec['policy_seed'])]:
        if result.get(key) != expected:
            raise ValueError(f'Result policy identity mismatch: {key}')
    close(result['temperature'], policy['temperature'], 'temperature')
    close(result['starting_stack_bb'], 200., 'starting stack')
    if execution is not None:
        validate_execution_metadata(result, execution)
    cumulative, rewards, chips_by_hand = 0, [], {}
    for index, row in enumerate(raw, 1):
        if execution is not None:
            validate_execution_metadata(row, execution)
        if (row.get('policy_seed') != spec['policy_seed'] or row.get('model_sha256') != policy['sha256']
                or row.get('policy_mode') != policy['policy_mode']):
            raise ValueError('Raw row policy/session identity mismatch')
        close(row.get('policy_temperature'), policy['temperature'], 'raw policy temperature')
        if (integer(row['successful_hand'], 'successful_hand') != index
                or integer(row['attempted_hand'], 'attempted_hand') != index):
            raise ValueError('Duplicate, missing or failed hand attempt')
        chips = integer(row['winnings_chips'], 'winnings_chips')
        if abs(chips) > 20000:
            raise ValueError('Reward outside 200bb stack')
        cumulative += chips
        close(row['winnings_bb'], chips/100, 'chip/bb reward')
        if integer(row['cumulative_chips'], 'cumulative_chips') != cumulative:
            raise ValueError('Cumulative chip count mismatch')
        close(row['cumulative_bb'], cumulative/100, 'cumulative bb')
        rewards.append(chips/100)
        chips_by_hand[index-1] = chips
    if integer(result['total_chips'], 'total_chips') != cumulative:
        raise ValueError('Result total differs from raw total')
    close(result['bb_per_100'], statistics.mean(rewards)*100, 'result bb/100')
    mean = statistics.mean(rewards)
    std = statistics.stdev(rewards) if n > 1 else 0.
    half_width = 1.96*std/math.sqrt(n)
    for key, expected in [('avg_bb_per_hand', mean), ('std_bb_per_hand', std),
                          ('ci95_bb_per_hand', half_width), ('ci95_bb_per_100', half_width*100),
                          ('lower_bound_bb_per_100', (mean-half_width)*100),
                          ('upper_bound_bb_per_100', (mean+half_width)*100)]:
        close(result.get(key), expected, f'result {key}')
    by_hand, previous, hero_decisions = {}, (-1, -1), 0
    for row in dump:
        hand = integer(row['hand_idx'], 'hand_idx')
        move = integer(row['move_idx'], 'move_idx')
        if (hand, move) <= previous:
            raise ValueError('Duplicated or unordered decision row')
        previous = (hand, move)
        records = by_hand.setdefault(hand, [])
        if move != len(records) or hand not in chips_by_hand:
            raise ValueError('Missing decision or out-of-range hand')
        if integer(row['winnings_hero'], 'dump winnings') != chips_by_hand[hand]:
            raise ValueError('Dump reward differs from raw reward')
        if row.get('hand_policy_execution_clean') is not True or row.get('hand_policy_execution_issues') != []:
            raise ValueError('Fallback or unknown policy execution')
        if row.get('who') not in ('hero', 'opp'):
            raise ValueError('Unknown decision role')
        if row['who'] == 'hero':
            hero_decisions += 1
            if row.get('policy_mode') != policy['policy_mode']:
                raise ValueError('Hero policy mode mismatch')
            close(row.get('policy_temperature'), policy['temperature'], 'hero temperature')
            slot = integer(row['policy_action_slot'], 'policy_action_slot')
            mask, probs = row['policy_legal_mask'], row['policy_behavior_probs']
            if (len(mask) != 9 or len(probs) != 9 or not 0 <= slot < 9
                    or any(v not in (0, 1, False, True) for v in mask) or not mask[slot]
                    or any(isinstance(p, bool) or not isinstance(p, (int, float))
                           or not math.isfinite(p) or p < 0 or p > 1 for p in probs)
                    or any(p > 1e-8 for p, valid in zip(probs, mask) if not valid)):
                raise ValueError('Invalid legal categorical policy evidence')
            if abs(sum(probs)-1) > 2e-5 or probs[slot] <= 0:
                raise ValueError('Invalid selected action probability')
            close(row['policy_behavior_action_probability'], probs[slot], 'selected probability')
        records.append(row)
    if set(by_hand) != set(range(n)):
        raise ValueError('Dump omits one or more completed raw hands')
    for rows in by_hand.values():
        initial_deal_fingerprint(rows)
    return dict(hands=n, total_chips=cumulative, rewards_bb=rewards, hero_decisions=hero_decisions)


def validate_execution_metadata(row, execution):
    if (row.get('strict_policy_execution') is not True
            or row.get('http_transport') != execution['http_transport']):
        raise ValueError('Missing or mismatched strict transport execution metadata')


def audit_manifest(manifest_path: Path) -> dict:
    manifest_path = manifest_path.resolve()
    manifest = json.loads(manifest_path.read_text())
    if manifest['schema'] != 'cardpilot.slumbot_frozen_evidence_manifest.v1':
        raise ValueError('Unknown evidence manifest schema')
    policy, specs = manifest['policy'], manifest['sessions']
    execution = manifest.get('execution')
    # Optional v1 extension: historical v1 manifests remain auditable unchanged;
    # a newly declared strict transport contract may never silently downgrade.
    if 'execution' in manifest and (not isinstance(execution, dict)
            or execution.get('strict_policy_execution') is not True
            or execution.get('http_transport') != 'persistent_session_no_retries_v1'):
        raise ValueError('Unsupported strict execution contract')
    if (policy['strategy'] != 'model' or policy['policy_mode'] not in ('sample', 'greedy')
            or policy['temperature'] != 1 or policy['starting_stack_bb'] != 200
            or len(specs) < 2 or len({row['id'] for row in specs}) != len(specs)
            or len({integer(row['policy_seed'], 'policy_seed') for row in specs}) != len(specs)):
        raise ValueError('Unsupported frozen policy or duplicate session identity/seed')
    def resolve(value):
        path = Path(value)
        return path.resolve() if path.is_absolute() else (manifest_path.parent / path).resolve()
    checkpoint = resolve(policy['checkpoint'])
    if sha(checkpoint) != policy['sha256']:
        raise ValueError('Frozen checkpoint hash mismatch')
    paths = [resolve(row[key]) for row in specs for key in ['raw_hands', 'dump', 'result']]
    if len(paths) != len(set(paths)):
        raise ValueError('Repeated evidence path would double-count a session')
    inputs = [manifest_path, checkpoint, *paths]
    digests = {str(path): sha(path) for path in inputs}
    sessions, all_rewards = [], []
    for spec in specs:
        result = json.loads(resolve(spec['result']).read_text())
        session = validate_session(jsonl(resolve(spec['raw_hands'])), jsonl(resolve(spec['dump'])), result, spec, policy, execution)
        all_rewards.extend(session.pop('rewards_bb'))
        sessions.append(dict(id=spec['id'], **session))
    independence = audit_paths([resolve(row['dump']) for row in specs])
    if independence['status'] != 'PASS':
        raise ValueError('Observable session independence audit failed')
    summary = summarize(all_rewards, 11.1, 2., DEFAULT_BASELINE_BB100, 20000)
    # The historical baseline is greedy: never label this as a matched relative treatment gain.
    summary['baseline_comparison_scope'] = 'historical_greedy_reference_not_matched_sampled_treatment'
    for path in inputs:
        if sha(path) != digests[str(path)]:
            raise ValueError('Evidence changed while the final audit was reading it')
    return dict(schema='cardpilot.slumbot_frozen_hand_evidence_audit.v1', status='PASS',
                sessions=sessions, summary=summary, input_sha256=digests, independence=independence,
                execution_contract=execution,
                claim_scope='strict_observable_evidence_and_raw_iid_normal_ci_not_proof_of_hidden_deck_independence')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--out-json', required=True, type=Path)
    args = parser.parse_args()
    if args.out_json.exists():
        raise ValueError('Refusing to overwrite an evidence audit')
    result = audit_manifest(args.manifest)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
    print(json.dumps({'status': result['status'], 'hands': result['summary']['hands']}))


if __name__ == '__main__':
    main()
