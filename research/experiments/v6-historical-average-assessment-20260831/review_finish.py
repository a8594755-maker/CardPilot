"""Terminal-only independent frozen-assessment arithmetic and identity review."""
import json
import math
from pathlib import Path
import random
import statistics
import subprocess
import sys

import psutil
import run_assessment as run

BASE = run.BASE


def alive(row):
    try:
        return abs(psutil.Process(row['pid']).create_time()-row['create_time']) < .001
    except psutil.NoSuchProcess:
        return False


def estimate(values):
    n = len(values)
    assert n == 4096 and all(math.isfinite(v) for v in values)
    mean = math.fsum(values)/n
    se = math.sqrt(math.fsum((v-mean)**2 for v in values)/(n-1)/n)
    z = statistics.NormalDist().inv_cdf(.995)
    return dict(bb_per_100=mean, standard_error=se, ci95=[mean-1.96*se, mean+1.96*se],
                family5_ci95=[mean-z*se, mean+z*se])


def compare(left, right):
    if isinstance(left, dict):
        assert set(left) == set(right)
        for key in left: compare(left[key], right[key])
    elif isinstance(left, list):
        assert len(left) == len(right)
        for a, b in zip(left, right): compare(a, b)
    else:
        assert math.isclose(left, right, rel_tol=1e-10, abs_tol=1e-7)


def main():
    if sys.argv[1:] or (BASE/'reviewed_analysis.json').exists():
        raise ValueError('No repeated independent review')
    execution = run.read(BASE/'execution.json')
    assert execution['status'] == 'COMPLETED_PENDING_REVIEW' and not alive(execution)
    assert len(execution['children']) == 10 and all(c['exit_code'] == 0 and not alive(c) for c in execution['children'])
    inputs = run.read(BASE/'input_manifest.json')
    copies = run.read(BASE/'execution_code/copy_manifest.json')
    run.validate_parent()
    run.verify(copies, inputs)
    registered = [(label, a) for label in ('source', 'student') for a in range(5)]
    assert [(c['label'], c['anchor']) for c in execution['children']] == registered
    for child, (label, anchor) in zip(execution['children'], registered):
        assert child['command'] == [sys.executable, *run.eval_command(label, anchor)]
    record = run.read(BASE/'experiment.json')
    assert record['status'] == 'RUNNING'
    def recorded(path):
        row = next(v for p, v in record['artifact_integrity'].items() if Path(p).resolve() == path.resolve())
        assert run.sha(path) == row['sha256']
    parity = run.read(BASE/'parity_analysis.json')
    assert parity['status'] == 'PASS' and parity['model_sha256'] == inputs['models']['student']['sha256']
    assert parity['states_checked'] == 4202 and parity['model_queries'] == 8404 and parity['replayed_validation_trajectories'] == 512
    assert parity['new_unique_hands'] == parity['network_connection_attempts'] == 0
    assert parity['parity_sha256'] == run.sha(BASE/'parity.jsonl')
    recorded(BASE/'parity.jsonl')
    with (BASE/'parity.jsonl').open() as handle:
        rows = [json.loads(line) for line in handle]
    assert len(rows) == 4202 and [r['state_index'] for r in rows] == list(range(4202))
    assert all(r['observation_equal'] and r['action_table_equal'] and r['decision_equal'] for r in rows)
    assert set(parity['strata']) == {f'street{s}_seat{p}' for s in range(4) for p in range(2)}
    assert sum(parity['strata'].values()) == 4202 and all(v > 0 for v in parity['strata'].values())
    for path, expected in parity['runtime_sha256'].items(): assert run.sha(path) == expected
    generator, decks = random.Random(run.SEED), []
    for _ in range(run.PAIRS):
        deck = list(range(52))
        generator.shuffle(deck)
        decks.append(deck)
    assert len({tuple(d) for d in decks}) == run.PAIRS
    values, absolute = {}, {}
    for label, anchor in registered:
        directory = BASE/'evaluation'/f'{label}_a{anchor}'
        recorded(directory/'pairs.jsonl')
        recorded(directory/'summary.json')
        summary = run.read(directory/'summary.json')
        assert summary['status'] == 'COMPLETED' and summary['evaluation_hands'] == 8192
        assert summary['candidate_sha256'] == inputs['models'][label]['sha256']
        assert summary['anchor_sha256'] == inputs['models'][f'anchor{anchor}']['sha256']
        assert summary['seed'] == run.SEED and summary['pairs'] == run.PAIRS
        assert summary['pairs_sha256'] == run.sha(directory/'pairs.jsonl')
        cell = []
        with (directory/'pairs.jsonl').open() as handle:
            for index, line in enumerate(handle):
                assert line.endswith('\n')
                row = json.loads(line)
                assert row['pair_index'] == index and row['deck'] == decks[index]
                assert len(row['rewards_bb']) == 2 and all(math.isfinite(v) and abs(v) <= 200 for v in row['rewards_bb'])
                cell.append(math.fsum(row['rewards_bb'])*50)
        assert len(cell) == 4096
        values[label, anchor] = cell
        absolute[f'{label}_a{anchor}'] = estimate(cell)
        compare(absolute[f'{label}_a{anchor}']['bb_per_100'], summary['bb_per_100'])
        compare(absolute[f'{label}_a{anchor}']['ci95'], summary['ci95'])
    assert all(v == 0 for v in values['source', 0])
    effects = {f'anchor{a}': estimate([x-y for x, y in zip(values['student', a], values['source', a])]) for a in range(5)}
    completed = run.read(BASE/'completed_analysis.json')
    recorded(BASE/'completed_analysis.json')
    compare(absolute, completed['internal']['absolute_internal_results'])
    compare(effects, completed['internal']['paired_student_minus_source'])
    assert completed['decision'] == 'ADMIT_SEPARATE_FRESH20K' and completed['evaluation_hands'] == execution['evaluation_hands'] == 81920
    assert completed['candidate_sha256'] == inputs['models']['student']['sha256']
    run.verify(copies, inputs)
    report = dict(status='PASS', decision='ADMIT_SEPARATE_FRESH20K', new_training_hands=0,
        evaluation_hands=81920, slumbot_hands=0, candidate_sha256=inputs['models']['student']['sha256'],
        absolute_internal_results=absolute, paired_student_minus_source=effects,
        paired_decks_independently_regenerated=4096, source_self_match_exact_zero=True,
        normal_evaluation_child_exits=10, parity_states=4202, parity_model_queries=8404,
        internal_return_used_for_admission=False, qualification_hands=0, goal_achieved=False,
        wall_time_seconds=execution['wall_time_seconds'])
    run.write(BASE/'reviewed_analysis.json', report)
    lines = ['# Fixed historical-average internal assessment', '', 'ADMIT_SEPARATE_FRESH20K. No live hands or100k qualification in this record.',
             '', 'Deployment parity4202preserved states/8404queries PASS;81920new internal diagnostic hands, all10clients exited0.',
             '', '| Anchor | Student-source bb/100 | Paired95%CI | Family5 95%CI |', '|---|---:|---|---|']
    for anchor, row in effects.items():
        lines.append(f'| {anchor} | {row["bb_per_100"]:+.5f} | {row["ci95"]} | {row["family5_ci95"]} |')
    lines += ['', 'Known opponent families are not novel adversaries. Internal return was not used for admission or checkpoint selection. '
              'Only exact epoch12 can enter a separately registered fresh20k strict-sampled external pilot.']
    (BASE/'result_summary.md').write_text('\n'.join(lines)+'\n')
    run.log('--command', f'python research/experiments/{BASE.name}/review_finish.py',
            '--artifact', BASE/'reviewed_analysis.json', '--artifact', BASE/'result_summary.md')
    subprocess.run([sys.executable, str(run.ROOT/'research/experiment_log.py'), 'finish', BASE.name,
        '--status', 'COMPLETED', '--summary', 'Fixed epoch12 parity and81920internal diagnostic hands completed with valid evidence;ADMIT_SEPARATE_FRESH20K.',
        '--conclusion', 'Internal strength diagnostics are not external transfer evidence. No checkpoint selection or100k admission.',
        '--decision', 'ADMIT_SEPARATE_FRESH20K', '--next-step', 'Preregister8fresh2500-hand Slumbot sessions of this exact frozen epoch12 hash with full journal/model replay.',
        '--count', 'new_training_hands=0', '--count', 'evaluation_hands=81920', '--count', 'slumbot_hands=0'], cwd=run.ROOT, check=True)
    print(json.dumps(report))


if __name__ == '__main__': main()
