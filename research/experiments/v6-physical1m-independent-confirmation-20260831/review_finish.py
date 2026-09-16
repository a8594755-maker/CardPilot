"""Independent raw arithmetic and session/identity review, after wrapper exits."""
from datetime import datetime, timezone
import json
import math
import random
import statistics
import subprocess
import sys
import run_confirmation as run

BASE, ROOT = run.BASE, run.ROOT


def interval(values):
    n = len(values)
    assert n == 8192 and all(math.isfinite(v) for v in values)
    mean = math.fsum(values)/n
    se = math.sqrt(math.fsum((v-mean)**2 for v in values)/(n-1)/n)
    z = statistics.NormalDist().inv_cdf((1+(1-.05/6))/2)
    return dict(bb_per_100=mean, standard_error=se, ci95=[mean-1.96*se, mean+1.96*se],
                ci_adjusted=[mean-z*se, mean+z*se])


def close(a, b):
    assert math.isfinite(a) and math.isfinite(b) and math.isclose(a, b, rel_tol=1e-11, abs_tol=1e-7), (a, b)


def main():
    import psutil
    if sys.argv[1:] or (BASE/'reviewed_analysis.json').exists(): raise ValueError('No repeated/alternate review')
    execution = run.read(BASE/'execution.json')
    assert execution['status'] == 'COMPLETED_PENDING_REVIEW'
    def original_process_alive(row):
        try: return abs(psutil.Process(row['pid']).create_time()-row['create_time']) < .001
        except psutil.NoSuchProcess: return False
    assert not original_process_alive(execution)
    roles = {f'{label}_anchor{a}' for label in ['source', 'final'] for a in range(5)} | {'mid262_anchor3', 'mid262_anchor4'}
    assert len(execution['children']) == 12 and {r['role'] for r in execution['children']} == roles
    assert all(r['exit_code'] == 0 and not original_process_alive(r) for r in execution['children'])
    copies = run.read(BASE/'execution_code/copy_manifest.json')
    models, anchors = run.read(BASE/'model_manifest.json'), run.read(BASE/'anchor_manifest.json')
    run.verify(copies, models.values(), anchors)
    assert set(models) == {'source', 'mid262', 'final'} and [r['index'] for r in anchors] == list(range(5))
    for label, expected_sha in run.MODEL_SHAS.items(): assert models[label]['sha256'] == expected_sha
    expected, previous = [], []
    for seed, output in [(20261002, expected), (20261001, previous)]:
        rng = random.Random(seed)
        for _ in range(8192):
            deck = list(range(52))
            rng.shuffle(deck)
            output.append(deck)
    assert len({tuple(d) for d in expected}) == 8192
    assert not ({tuple(d) for d in expected} & {tuple(d) for d in previous})
    prior_raw = run.PARENT/'matrix/source_anchor0/pairs.jsonl'
    assert [json.loads(line)['deck'] for line in prior_raw.read_text().splitlines()] == previous
    freshness = run.read(BASE/'deal_freshness.json')
    assert freshness['status'] == 'PASS' and freshness['full_deck_overlap'] == 0
    assert freshness['excluded_raw_sha256'] == run.sha(prior_raw)
    cells, values, raw_manifest = [], {}, []
    for label, aa in [('source', range(5)), ('final', range(5)), ('mid262', [3, 4])]:
        for a in aa:
            directory = BASE/'matrix'/f'{label}_anchor{a}'
            raw, summary = directory/'pairs.jsonl', run.read(directory/'summary.json')
            assert summary['status'] == 'COMPLETED' and summary['seed'] == 20261002
            assert summary['pairs'] == 8192 and summary['evaluation_hands'] == 16384
            assert summary['candidate_sha256'] == models[label]['sha256'] and summary['anchor_sha256'] == anchors[a]['sha256']
            assert summary['pairs_sha256'] == run.sha(raw)
            rows = [json.loads(line) for line in raw.read_text().splitlines()]
            assert [r['pair_index'] for r in rows] == list(range(8192)) and [r['deck'] for r in rows] == expected
            for row in rows:
                assert len(row['rewards_bb']) == 2 and all(math.isfinite(v) and abs(v) <= 200 for v in row['rewards_bb'])
                assert len(row['decisions']) == 2 and all(type(v) is int and v > 0 for v in row['decisions'])
            vals = [math.fsum(r['rewards_bb'])/2*100 for r in rows]
            values[label, a] = vals
            result = interval(vals)
            close(result['bb_per_100'], summary['bb_per_100'])
            for x, y in zip(result['ci95'], summary['ci95']): close(x, y)
            cells.append(dict(candidate=label, anchor=a, **result))
            raw_manifest.append(dict(path=str(raw), sha256=run.sha(raw), pairs=8192))
    assert all(v == 0 for v in values['source', 0])
    contrasts = [dict(anchor=a, **interval([f-s for f, s in zip(values['final', a], values['source', a])])) for a in range(5)]
    growth = interval([math.fsum(values['final', a][i]-values['mid262', a][i] for a in (3, 4))/2 for i in range(8192)])
    significant = {r['anchor'] for r in contrasts if r['ci_adjusted'][0] > 0}
    passed = (all(r['bb_per_100'] > 0 for r in contrasts) and len(significant) >= 3 and 0 in significant
              and bool(significant & {3, 4}) and growth['ci_adjusted'][0] > 0)
    decision = 'ADMIT_SEPARATE_SLUMBOT_PILOT' if passed else 'INDEPENDENT_CONFIRMATION_NOT_PASSED'
    writer = run.read(BASE/'completed_analysis.json')
    assert writer['confirmation_gate_pass'] == passed and writer['decision'] == decision
    assert writer['new_training_hands'] == writer['slumbot_hands'] == 0 and writer['evaluation_hands'] == 196608
    for actual, original in zip([*contrasts, growth], [*writer['primary_contrasts'], writer['heldout_growth']]):
        close(actual['bb_per_100'], original['bb_per_100'])
        for key in ['ci95', 'ci_adjusted']:
            for x, y in zip(actual[key], original[key]): close(x, y)
    report = dict(status='PASS', reviewed_at=datetime.now(timezone.utc).isoformat(), decision=decision,
                  confirmation_gate_pass=passed, qualification_admitted=False, new_training_hands=0,
                  evaluation_hands=196608, slumbot_hands=0, source_pairs_verified=len(copies), clean_child_exits=12,
                  parent_review_sha256=run.REVIEW_SHA, frozen_final_sha256=run.MODEL_SHAS['final'],
                  seed=20261002, full_deck_overlap_with_parent=0, primary_contrasts=contrasts,
                  heldout_growth=growth, cells=cells, raw_manifest=raw_manifest)
    run.write(BASE/'reviewed_analysis.json', report)
    lines = ['# Frozen physical1m independent confirmation', '', f'Decision: {decision}.', '',
             '196608 new internal hands; zero training/Slumbot hands. Twelve normal child exits.',
             'All frozen identities, source copies, full-deck freshness and independent raw arithmetic PASS.', '',
             '| Contrast | bb/100 | 95% CI | Family6 adjusted CI |', '|---|---:|---|---|']
    for name, row in [(f'final-source anchor{r["anchor"]}', r) for r in contrasts]+[('heldout final-mid262 mean', growth)]:
        lines.append(f'| {name} | {row["bb_per_100"]:+.4f} | {row["ci95"]} | {row["ci_adjusted"]} |')
    lines += ['', 'No parent sample pooling, training-seed replication, checkpoint rescue or external qualification claim.']
    (BASE/'result_summary.md').write_text('\n'.join(lines)+'\n')
    run.log('--command', f'python research/experiments/{BASE.name}/review_finish.py',
            '--artifact', BASE/'reviewed_analysis.json', '--artifact', BASE/'result_summary.md',
            '--note', 'Independent twelve-cell raw/session/deck/identity and family-six CI verification passed; no parent samples pooled.')
    subprocess.run([sys.executable, str(ROOT/'research/experiment_log.py'), 'finish', BASE.name, '--status', 'COMPLETED',
                    '--summary', f'Frozen physical1m independent confirmation completed196608internal hands;{decision}.',
                    '--conclusion', 'Fixed independent-deal breadth and held-out growth test, all evidence valid; no Slumbot claim.',
                    '--decision', decision, '--next-step',
                    'Candidate-specific offline deployment checks, then separately preregistered fresh Slumbot20k pilot of this exact final.' if passed else
                    'Analyze failure and choose the next learned-weight mechanism; no checkpoint rescue or automatic scale-up.',
                    '--count', 'new_training_hands=0', '--count', 'evaluation_hands=196608', '--count', 'slumbot_hands=0'], cwd=ROOT, check=True)
    print(json.dumps(report))


if __name__ == '__main__': main()
