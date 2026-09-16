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


def estimate(values, family=1):
    n = len(values)
    assert n == 4096 and all(math.isfinite(v) for v in values)
    mean = math.fsum(values)/n
    se = math.sqrt(math.fsum((v-mean)**2 for v in values)/(n-1)/n)
    z = statistics.NormalDist().inv_cdf(1-.05/(2*family))
    return dict(bb_per_100=mean, standard_error=se, ci95=[mean-1.96*se, mean+1.96*se],
                **{f'family{family}_ci95': [mean-z*se, mean+z*se]})


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
    assert len(execution['children']) == 21 and all(c['exit_code'] == 0 and not alive(c) for c in execution['children'])
    inputs = run.read(BASE/'input_manifest.json')
    copies = run.read(BASE/'execution_code/copy_manifest.json')
    run.validate_parent()
    run.verify(copies, inputs)
    registered = [(label, a) for label in run.CANDIDATES for a in run.OPPONENTS]
    assert [(c['label'], c['anchor']) for c in execution['children']] == registered
    for child, (label, anchor) in zip(execution['children'], registered):
        assert child['command'] == [sys.executable, *run.eval_command(label, anchor)]
    record = run.read(BASE/'experiment.json')
    assert record['status'] == 'RUNNING'
    def recorded(path):
        row = next(v for p, v in record['artifact_integrity'].items() if Path(p).resolve() == path.resolve())
        assert run.sha(path) == row['sha256']
    recorded(BASE/'execution.json')
    recorded(BASE/'evaluation_commands.json')
    commands = run.read(BASE/'evaluation_commands.json')
    assert [(c['label'], c['anchor'], c['command']) for c in commands] == [
        (c['label'], c['anchor'], c['command']) for c in execution['children']]
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
        directory = BASE/'evaluation'/f'{label}_vs_{anchor}'
        recorded(directory/'pairs.jsonl')
        recorded(directory/'summary.json')
        summary = run.read(directory/'summary.json')
        assert summary['status'] == 'COMPLETED' and summary['evaluation_hands'] == 8192
        assert summary['candidate_sha256'] == inputs['models'][label]['sha256']
        assert summary['anchor_sha256'] == inputs['models'][anchor]['sha256']
        assert summary['seed'] == run.SEED and summary['pairs'] == run.PAIRS
        assert summary['pairs_sha256'] == run.sha(directory/'pairs.jsonl')
        assert summary['command'] == [sys.executable, *run.eval_command(label, anchor)]
        cell = []
        with (directory/'pairs.jsonl').open() as handle:
            for index, line in enumerate(handle):
                assert line.endswith('\n')
                row = json.loads(line)
                assert row['pair_index'] == index and row['deck'] == decks[index]
                assert len(row['rewards_bb']) == 2 and all(math.isfinite(v) and abs(v) <= 200 for v in row['rewards_bb'])
                assert len(row['decisions']) == 2 and all(type(v) is int and v > 0 for v in row['decisions'])
                cell.append(math.fsum(row['rewards_bb'])*50)
        assert len(cell) == 4096
        values[label, anchor] = cell
        absolute[f'{label}_vs_{anchor}'] = estimate(cell)
        compare(absolute[f'{label}_vs_{anchor}']['bb_per_100'], summary['bb_per_100'])
        compare(absolute[f'{label}_vs_{anchor}']['ci95'], summary['ci95'])
    assert all(v == 0 for label in ('prior','response') for v in values[label,label])
    assert all(abs(a+b) < 1e-9 for a,b in zip(values['prior','response'],values['response','prior']))
    hedge = [x-y for x,y in zip(values['student','response'],values['prior','response'])]
    retention = [(s1-r1+s2-r2)/2 for s1,r1,s2,r2 in zip(
        values['student','anchor1'],values['response','anchor1'],values['student','anchor2'],values['response','anchor2'])]
    primary = dict(hedge_against_response=estimate(hedge,2), retain_anchor1_2_vs_response=estimate(retention,2))
    calibration = {a: estimate([s-(p+r)/2 for s,p,r in zip(values['student',a],values['prior',a],values['response',a])],7) for a in run.OPPONENTS}
    decision = ('ADMIT_NEXT_RESPONSE_PHASE' if min(r['family2_ci95'][0] for r in primary.values()) > 0
                else 'AVERAGE_STRATEGIC_GATE_NOT_PASSED')
    completed = run.read(BASE/'completed_analysis.json')
    recorded(BASE/'completed_analysis.json')
    compare(absolute, completed['internal']['absolute_internal_results'])
    compare(primary, completed['internal']['primary_contrasts'])
    compare(calibration, completed['internal']['student_minus_episode_mixture'])
    assert completed['decision'] == decision and completed['evaluation_hands'] == execution['evaluation_hands'] == run.TOTAL_HANDS
    assert completed['candidate_sha256'] == inputs['models']['student']['sha256']
    run.verify(copies, inputs)
    report = dict(status='PASS', decision=decision, new_training_hands=0,
        evaluation_hands=run.TOTAL_HANDS, slumbot_hands=0, candidate_sha256=inputs['models']['student']['sha256'],
        absolute_internal_results=absolute, primary_contrasts=primary, student_minus_episode_mixture=calibration,
        paired_decks_independently_regenerated=4096, self_matches_exact_zero=True, reciprocal_match_zero=True,
        normal_evaluation_child_exits=21, parity_states=4202, parity_model_queries=8404,
        internal_return_used_for_next_response_allocation=True, external_admission=False,
        qualification_hands=0, goal_achieved=False, wall_time_seconds=execution['wall_time_seconds'])
    run.write(BASE/'reviewed_analysis.json', report)
    lines = ['# Phase1 average strategic assessment', '', decision,
             '', '172032 new internal hands; zero training, Slumbot or qualification hands. All21children normal exits.',
             '4202preserved-state native/public parity checks;8404model calls add zero new hands.', '',
             '| Primary contrast | bb/100 | Paired95%CI | Family2 95%CI |', '|---|---:|---|---|']
    for label, row in primary.items():
        lines.append(f'| {label} | {row["bb_per_100"]:+.5f} | {row["ci95"]} | {row["family2_ci95"]} |')
    lines += ['', 'Calibration compares the student with the expected whole-episode half/half teacher mixture. '
              'A CI crossing zero does not establish equivalence. Known opponents and targeted retention anchors are not novel heldouts. '
              'This gate allocates only a separately registered response phase, never external qualification.']
    (BASE/'result_summary.md').write_text('\n'.join(lines)+'\n')
    run.log('--command', f'python research/experiments/{BASE.name}/review_finish.py',
            '--artifact', BASE/'reviewed_analysis.json', '--artifact', BASE/'result_summary.md')
    subprocess.run([sys.executable, str(run.ROOT/'research/experiment_log.py'), 'finish', BASE.name,
        '--status', 'COMPLETED', '--summary', f'Fixed phase1 average strategic assessment completed172032internal hands: {decision}.',
        '--conclusion', 'Paired hedge and retention diagnostics determine response-phase allocation, not general strength or external transfer.',
        '--decision', decision, '--next-step',
        'Preregister next response-to-average phase; preserve all teachers.' if decision == 'ADMIT_NEXT_RESPONSE_PHASE' else 'Analyze average strategic failure before increasing training scale.',
        '--count', 'new_training_hands=0', '--count', 'evaluation_hands=172032', '--count', 'slumbot_hands=0'], cwd=run.ROOT, check=True)
    print(json.dumps(report))


if __name__ == '__main__': main()
