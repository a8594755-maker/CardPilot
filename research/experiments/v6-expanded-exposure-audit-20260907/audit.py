"""Zero-new-hand, hash-bound descriptive exposure and learning-health audit."""
from pathlib import Path
from collections import Counter
import hashlib
import json
import math
import statistics

BASE = Path(__file__).resolve().parent
TRIAL = BASE.parent / 'v6-expanded-family-two-seed-geometric-20260907'

def read(p):
    return json.loads(p.read_text(encoding='utf-8'))

def sha(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def main():
    assert not (BASE / 'report.json').exists(), 'preserve output'
    review = read(TRIAL / 'post_terminal_review.json')
    assert review['passed'] and read(TRIAL / 'experiment.json')['status'] == 'COMPLETED'
    hashes = {str(TRIAL / 'post_terminal_review.json'): sha(TRIAL / 'post_terminal_review.json')}
    branches = {}
    for stage in (1, 2):
        for seed in (1, 3):
            for arm in ('control', 'expanded'):
                name = f'seed{seed}_{arm}_stage{stage}'
                folder = TRIAL / name
                prefixes = read(folder / 'prefixes.json')
                data = {}
                for filename in ('h1_training_metrics.jsonl', 'opponent_assignments.jsonl'):
                    p = folder / filename
                    hashes[str(p)] = sha(p)
                    assert review['input_sha256'][str(p)] == hashes[str(p)]
                    with p.open('rb') as f:
                        assert hashlib.sha256(f.read(prefixes[filename]['bytes'])).hexdigest() == prefixes[filename]['sha256']
                        data[filename] = [json.loads(x) for x in f if x.strip()]
                rows = data['h1_training_metrics.jsonl']
                assignments = {r['applies_to_iteration']: r for r in data['opponent_assignments.jsonl']}
                assert len(rows) == review['health'][name]['completed_training_iterations']
                assert [r['iteration'] for r in rows] == list(range(rows[0]['iteration'], rows[-1]['iteration'] + 1))
                exposure = Counter()
                for r in rows:
                    refs = {x['local_index']: x['snapshot_id'] for x in assignments[r['iteration']]['pool_snapshot_refs']}
                    for g in r['adaptive_opponent_league']:
                        if g['iteration_hands']:
                            exposure[str(refs[g['opponent_id']])] += g['iteration_hands']
                fixed = review['health'][name]['fixed_family_transition_exposure']
                metrics = {}
                for key in ('entropy', 'approx_kl', 'reference_policy_kl', 'clip_frac', 'preupdate_critic_mse', 'reward_per_hand'):
                    values = [r.get(key) for r in rows]
                    if all(isinstance(v, (float, int)) and math.isfinite(v) for v in values):
                        n = max(1, len(values) // 4)
                        metrics[key] = {'mean': statistics.mean(values), 'first_quarter': statistics.mean(values[:n]), 'last_quarter': statistics.mean(values[-n:])}
                branches[name] = {'iterations': len(rows), 'snapshot_transition_observations': dict(exposure),
                    'fixed_family_transition_exposure': fixed, 'metrics': metrics,
                    'kl_early_stops': sum(bool(r['kl_early_stop_triggered']) for r in rows),
                    'fresh_policy_rows': sum(r['fresh_policy_rows'] for r in rows),
                    'replay_rows': sum(r['ppo_replay_rows'] for r in rows)}
    assert all(sha(Path(p)) == h for p, h in hashes.items())
    report = {'passed': True, 'branches': branches, 'input_sha256': hashes, 'new_training_hands': 0, 'evaluation_hands': 0,
        'limitations': ['Descriptive serially dependent metrics, not causal effects or strength.',
            'Transition observations and replay rows are not unique physical deals.',
            'Snapshot identity is not strategic diversity; joint opponent-seat gradient mass is not reconstructed.']}
    with (BASE / 'report.json').open('x', encoding='utf-8') as f:
        json.dump(report, f, indent=2, allow_nan=False)
    print(json.dumps({'passed': True, 'branches': len(branches), 'new_hands': 0}))

if __name__ == '__main__':
    main()
