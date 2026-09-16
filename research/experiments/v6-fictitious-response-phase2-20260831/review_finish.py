"""Terminal-only independent raw arithmetic and frozen response evidence review."""
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import random
import statistics
import subprocess
import sys

import psutil
import torch
import run_pilot as run

BASE = run.BASE


def alive(row):
    try: return abs(psutil.Process(row['pid']).create_time()-row['create_time']) < .001
    except psutil.NoSuchProcess: return False


def interval(values):
    if len(values) < 2 or not all(math.isfinite(v) for v in values):
        raise ValueError('Finite pairs required')
    n = len(values)
    mean = math.fsum(values)/n
    se = math.sqrt(math.fsum((v-mean)**2 for v in values)/(n-1)/n)
    z = statistics.NormalDist().inv_cdf(1-.05/50)
    return dict(bb_per_100=mean, standard_error=se, ci95=[mean-1.96*se, mean+1.96*se],
                family25_ci95=[mean-z*se, mean+z*se])


def close(left, right):
    if isinstance(left, dict):
        assert set(left) == set(right)
        for k in left: close(left[k], right[k])
    elif isinstance(left, list):
        assert len(left) == len(right)
        for a, b in zip(left, right): close(a, b)
    else: assert math.isclose(left, right, rel_tol=1e-10, abs_tol=1e-7)


def raw_values(rows, decks):
    if len(rows) != len(decks): raise ValueError('Incomplete paired cell')
    result = []
    for index, row in enumerate(rows):
        assert row['pair_index'] == index and row['deck'] == decks[index]
        assert sorted(row['deck']) == list(range(52))
        rewards = row['rewards_bb']
        assert len(rewards) == 2 and all(math.isfinite(v) and abs(v) <= 200 for v in rewards)
        assert len(row['decisions']) == 2 and all(type(v) is int and v > 0 for v in row['decisions'])
        result.append(math.fsum(rewards)*50)
    return result


def main():
    torch.set_num_threads(1)
    if sys.argv[1:] or (BASE/'reviewed_analysis.json').exists(): raise ValueError('Preserve prior review')
    execution = run.read(BASE/'execution.json')
    assert execution['status'] == 'COMPLETED_PENDING_REVIEW' and not alive(execution)
    expected = [('trainer', None, None)]+[(f'{label}_{opponent}', label, opponent) for label in run.LABELS for opponent in run.OPPONENTS]
    assert len(execution['children']) == 33
    for child, (role, label, opponent) in zip(execution['children'], expected):
        assert child['role'] == role and child['exit_code'] == 0 and not alive(child)
        cmd = run.training_command() if role == 'trainer' else run.eval_command(label, opponent)
        assert child['command'] == [sys.executable, *cmd]
    record = run.read(BASE/'experiment.json')
    assert record['status'] == 'RUNNING'
    def recorded(path):
        row = next(v for p, v in record['artifact_integrity'].items() if Path(p).resolve() == path.resolve())
        assert run.sha(path) == row['sha256']
    copies, inputs = run.read(BASE/'execution_code/copy_manifest.json'), run.read(BASE/'input_manifest.json')
    run.verify(copies, inputs)
    candidates = run.read(BASE/'candidate_manifest.json')
    assert list(candidates) == list(run.LABELS) or set(candidates) == set(run.LABELS)
    for row in candidates.values():
        assert run.sha(row['path']) == row['sha256']
        recorded(Path(row['path']))
    assert candidates['initial']['sha256'] == run.MODEL_SHA and candidates['initial']['actual_hands'] == 0
    selection = run.read(BASE/'archive_selection.json')
    recorded(BASE/'archive_selection.json')
    ordered = sorted(selection['archives'], key=lambda r:r['iteration'])
    assert {Path(r['path']).resolve() for r in ordered} == {p.resolve() for p in (BASE/'production/checkpoints').glob('checkpoint_iter*_hands*.pt')}
    for row in ordered:
        archived = torch.load(row['path'], map_location='cpu', weights_only=False)
        assert run.sha(row['path']) == row['sha256']
        assert archived['iteration'] == row['iteration'] and archived['environment_hand_accounting']['completed_hands'] == row['actual_hands']
    assert all(a['actual_hands'] < b['actual_hands'] for a,b in zip(ordered, ordered[1:]))
    for label, threshold in [('quarter', run.TARGET//4), ('half', run.TARGET//2)]:
        chosen = next(r for r in ordered if r['actual_hands'] >= threshold)
        assert chosen == selection['selected'][label]
        assert candidates[label]['sha256'] == chosen['sha256'] and candidates[label]['actual_hands'] == chosen['actual_hands']
        ck = torch.load(chosen['path'], map_location='cpu', weights_only=False)
        assert run.sha(chosen['path']) == chosen['sha256']
        assert ck['iteration'] == chosen['iteration'] and ck['environment_hand_accounting']['completed_hands'] == chosen['actual_hands']
    checkpoint = torch.load(BASE/'production/latest.pt', map_location='cpu', weights_only=False)
    source = torch.load(BASE/'frozen/average.pt', map_location='cpu', weights_only=False)
    account, health = checkpoint['environment_hand_accounting'], run.read(BASE/'production/training_health.json')
    assert account['completed_hands'] == health['actual_hands'] == execution['new_training_hands'] >= run.TARGET
    assert account['prefix_complete'] and account['unknown_prefix_training_marker_hands'] == 0
    assert account['origin_run_id'] == 'v6_fictitious_response_phase2_20260831'
    assert sum(w['completed_hands'] for w in account['session_worker_counts']) == account['completed_hands']
    assert run.sha(BASE/'production/latest.pt') == health['checkpoint_sha256'] == candidates['final']['sha256']
    assert len(checkpoint['model']) == 86 and sum(not torch.equal(v, source['model'][k]) for k,v in checkpoint['model'].items()) == 86
    assert all(torch.isfinite(v).all() for v in checkpoint['model'].values())
    assert len(checkpoint['optimizer']['state']) == 86 and len(source['optimizer']['state']) == 80
    for state in checkpoint['optimizer']['state'].values():
        assert float(state['step']) > 0 and all(torch.isfinite(v).all() for v in state.values() if isinstance(v, torch.Tensor))
    assert run.read(BASE/'initialization_audit.json')['operation'] == 'NEW_PPO_WEIGHTS_INITIALIZATION_NOT_SL_RESUME'
    assert run.read(BASE/'production/session_audit.json')['status'] == 'PASS'
    for name in ('latest.pt', 'run_manifest.json', 'h1_training_metrics.jsonl', 'opponent_assignments.jsonl', 'training_health.json', 'session_audit.json'):
        recorded(BASE/'production'/name)
    metrics = [json.loads(line) for line in (BASE/'production/h1_training_metrics.jsonl').read_text().splitlines()]
    assert [r['iteration'] for r in metrics] == list(range(1, checkpoint['iteration']+1))
    counts = [r['environment_hand_accounting']['completed_hands'] for r in metrics]
    assert all(a < b for a,b in zip([0]+counts[:-1], counts)) and all(n < run.TARGET for n in counts[:-1]) and counts[-1] >= run.TARGET
    assert health['shutdown_counter_tail'] == account['completed_hands']-counts[-1]
    assignments = [json.loads(line) for line in (BASE/'production/opponent_assignments.jsonl').read_text().splitlines()]
    assert len(assignments) == checkpoint['iteration']
    for i, row in enumerate(assignments, 1):
        assert row['applies_to_iteration'] == i and len(row['group_metadata']) == 8
        assert all(g['opponent_id'] == 0 for g in row['group_metadata'])
        assert all(w['opponent']['kind'] == 'pool_snapshot' for w in row['workers'])
    rng, decks = random.Random(run.EVAL_SEED), []
    for _ in range(run.PAIRS):
        deck = list(range(52))
        rng.shuffle(deck)
        decks.append(deck)
    assert len({tuple(d) for d in decks}) == run.PAIRS
    values, absolute = {}, {}
    input_map = {r['label']:r for r in inputs}
    for label in run.LABELS:
        for opponent in run.OPPONENTS:
            directory = BASE/'evaluation'/f'{label}_{opponent}'
            recorded(directory/'pairs.jsonl')
            recorded(directory/'summary.json')
            summary = run.read(directory/'summary.json')
            assert summary['status'] == 'COMPLETED' and summary['evaluation_hands'] == 2*run.PAIRS
            assert summary['seed'] == run.EVAL_SEED and summary['pairs'] == run.PAIRS
            assert summary['candidate_sha256'] == candidates[label]['sha256'] and summary['anchor_sha256'] == input_map[opponent]['sha256']
            assert summary['pairs_sha256'] == run.sha(directory/'pairs.jsonl')
            assert summary['command'] == [sys.executable, *run.eval_command(label, opponent)]
            rows = []
            with (directory/'pairs.jsonl').open() as handle:
                for line in handle:
                    assert line.endswith('\n')
                    rows.append(json.loads(line))
            cell = raw_values(rows, decks)
            assert len(cell) == run.PAIRS
            values[label, opponent] = cell
            absolute[f'{label}_{opponent}'] = {k:v for k,v in interval(cell).items() if k != 'family25_ci95'}
            close(absolute[f'{label}_{opponent}']['bb_per_100'], summary['bb_per_100'])
            close(absolute[f'{label}_{opponent}']['ci95'], summary['ci95'])
    assert all(v == 0 for v in values['initial', 'average'])
    effects = {f'{label}_{opponent}':interval([x-y for x,y in zip(values[label,opponent], values['initial',opponent])])
        for label in run.LABELS[1:] for opponent in run.OPPONENTS}
    budget_gain = interval([x-y for x,y in zip(values['final','average'],values['half','average'])])
    decision = 'ADMIT_SEPARATE_AVERAGE_UPDATE' if effects['final_average']['ci95'][0] > 0 else 'RESPONSE_LEARNING_GATE_NOT_PASSED'
    completed = run.read(BASE/'completed_analysis.json')
    recorded(BASE/'completed_analysis.json')
    close(effects, completed['paired_response_minus_initial'])
    close(budget_gain, completed['paired_final_minus_half_average'])
    close(absolute, completed['absolute'])
    assert completed['decision'] == decision and completed['evaluation_hands'] == execution['evaluation_hands'] == run.EVAL_HANDS
    assert completed['new_training_hands'] == health['actual_hands']
    run.verify(copies, inputs)
    report = dict(status='PASS', decision=decision, reviewed_at=datetime.now(timezone.utc).isoformat(),
        new_training_hands=health['actual_hands'], evaluation_hands=run.EVAL_HANDS, slumbot_hands=0,
        qualification_hands=0, goal_achieved=False, primary=effects['final_average'],
        absolute=absolute, paired_response_minus_initial=effects, paired_final_minus_half_average=budget_gain, training_health=health,
        independently_regenerated_decks=run.PAIRS, normal_child_exits=33, code_source_copy_pairs=len(copies),
        wall_time_seconds=execution['wall_time_seconds'], exact_best_response_proven=False,
        full_nfsp_implemented=False, equilibrium_proven=False)
    run.write(BASE/'reviewed_analysis.json', report)
    lines = ['# Frozen-average response oracle', '', decision, '',
        f'New physical PPO hands: {health["actual_hands"]}. Internal hands: {run.EVAL_HANDS}. No Slumbot hands.', '',
        f'Primary final-minus-initial versus average: {effects["final_average"]}', '',
        '| Checkpoint / opponent | Response-initial bb/100 | Paired95%CI | Family25CI |', '|---|---:|---|---|']
    for name, row in effects.items():
        lines.append(f'| {name} | {row["bb_per_100"]:+.5f} | {row["ci95"]} | {row["family25_ci95"]} |')
    lines += ['', f'Prespecified final-minus-half against average: {budget_gain}', '', 'One approximate-response component, not full NFSP, an exact best response, equilibrium, or external qualification. Known anchor families are not novel adversaries. Initial SL optimizer and all prior evidence preserved.']
    (BASE/'result_summary.md').write_text('\n'.join(lines)+'\n')
    run.log('--command', f'python research/experiments/{BASE.name}/review_finish.py', '--artifact', BASE/'reviewed_analysis.json', '--artifact', BASE/'result_summary.md')
    subprocess.run([sys.executable, str(run.ROOT/'research/experiment_log.py'), 'finish', BASE.name, '--status', 'COMPLETED',
        '--summary', f'Frozen-average response completed{health["actual_hands"]}actual PPO hands and{run.EVAL_HANDS}internal hands;{decision}.',
        '--conclusion', 'One learned response oracle tested against an immutable average; no exact best-response, equilibrium, Slumbot transfer or100k claim.',
        '--decision', decision, '--next-step', 'Preregister a separate reach-weighted average update / next response phase.' if decision == 'ADMIT_SEPARATE_AVERAGE_UPDATE' else 'Diagnose response learning before expanding training.',
        '--count', f'new_training_hands={health["actual_hands"]}', '--count', f'evaluation_hands={run.EVAL_HANDS}', '--count', 'slumbot_hands=0'], cwd=run.ROOT, check=True)
    print(json.dumps(report))


if __name__ == '__main__': main()
