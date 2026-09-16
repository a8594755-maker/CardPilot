"""Descriptive family mass audit of completed, hash-bound assignment suffixes."""
from pathlib import Path
import hashlib
import json
import statistics as st

BASE = Path(__file__).resolve().parent
TRIAL = BASE.parent / 'v6-expanded-family-two-seed-geometric-20260907'
EXPOSURE = BASE.parent / 'v6-expanded-exposure-audit-20260907/report.json'

def read(p):
    return json.loads(p.read_text(encoding='utf-8'))

def sha(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def main():
    review = read(TRIAL / 'post_terminal_review.json')
    exposure = read(EXPOSURE)
    assert review['passed'] and exposure['passed']
    inputs = {str(EXPOSURE): sha(EXPOSURE), str(TRIAL / 'post_terminal_review.json'): sha(TRIAL / 'post_terminal_review.json')}
    results = {}
    for seed in (1, 3):
        for arm in ('control', 'expanded'):
            name = f'seed{seed}_{arm}_stage2'
            folder = TRIAL / name
            p = folder / 'opponent_assignments.jsonl'
            inputs[str(p)] = sha(p)
            assert inputs[str(p)] == review['input_sha256'][str(p)]
            prefix = read(folder / 'prefixes.json')['opponent_assignments.jsonl']
            with p.open('rb') as f:
                assert hashlib.sha256(f.read(prefix['bytes'])).hexdigest() == prefix['sha256']
                rows = [json.loads(line) for line in f if line.strip()]
            p = folder / 'h1_training_metrics.jsonl'
            inputs[str(p)] = sha(p)
            assert inputs[str(p)] == review['input_sha256'][str(p)]
            prefix = read(folder / 'prefixes.json')['h1_training_metrics.jsonl']
            with p.open('rb') as f:
                assert hashlib.sha256(f.read(prefix['bytes'])).hexdigest() == prefix['sha256']
                iterations = {json.loads(line)['iteration'] for line in f if line.strip()}
            rows = [r for r in rows if r['applies_to_iteration'] in iterations]
            assert {r['applies_to_iteration'] for r in rows} == iterations and len(rows) == len(iterations)
            fixed = set(exposure['branches'][name]['fixed_family_transition_exposure'])
            def family(sid):
                sid = str(sid)
                return 'original' if sid in {'0', '1', '2'} else ('added' if sid in fixed else 'recent')
            mass = {k: [] for k in ('original', 'added', 'recent')}
            assigned = {k: 0 for k in (*mass, 'self_play')}
            for r in rows:
                refs = {x['local_index']: x['snapshot_id'] for x in r['pool_snapshot_refs']}
                weights = r['pool_sampling_weights']
                assert len(weights) == len(refs) and abs(sum(weights) - 1) < 1e-8
                for k in mass:
                    mass[k].append(sum(w for i, w in enumerate(weights) if family(refs[i]) == k))
                for worker in r['workers']:
                    opp = worker['opponent']
                    assigned['self_play' if opp['kind'] == 'self_play' else family(opp['snapshot_id'])] += 1
            trans = {k: 0 for k in mass}
            for sid, n in exposure['branches'][name]['snapshot_transition_observations'].items():
                trans[family(sid)] += n
            results[name] = {'completed_iterations': len(rows), 'mean_conditional_pool_mass': {k: st.mean(v) for k, v in mass.items()},
                             'assigned_worker_iterations': assigned, 'pool_transition_observations': trans}
    assert all(sha(Path(p)) == h for p, h in inputs.items())
    report = {'passed': True, 'branches': results, 'input_sha256': inputs, 'new_training_hands': 0, 'evaluation_hands': 0,
              'limitations': ['Descriptive, not causal; pool mass excludes self-play.', 'Worker assignments are not physical hands, transitions, or gradient mass.', 'Compare the completed suffix only; no tail assignment counted.']}
    with (BASE / 'report.json').open('x', encoding='utf-8') as f:
        json.dump(report, f, indent=2, allow_nan=False)
    print(json.dumps({'passed': True, 'branches': results}))

if __name__ == '__main__':
    main()
