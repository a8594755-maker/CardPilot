"""Independent raw-pair arithmetic, archive selection and final identity review."""
from datetime import datetime, timezone
import json
import math
import random
import statistics
import subprocess
import sys
import run_curve as run

BASE, ROOT = run.BASE, run.ROOT


def independent_interval(values):
    if len(values) < 2 or not all(math.isfinite(v) for v in values): raise ValueError('Invalid pairs')
    mean = math.fsum(values)/len(values)
    se = math.sqrt(math.fsum((v-mean)**2 for v in values)/(len(values)-1)/len(values))
    z = statistics.NormalDist().inv_cdf((1+(1-.05/6))/2)
    return dict(bb_per_100=mean, standard_error=se, ci95=[mean-1.96*se, mean+1.96*se],
                ci_adjusted=[mean-z*se, mean+z*se])


def close(a, b):
    assert math.isfinite(a) and math.isfinite(b) and math.isclose(a, b, rel_tol=1e-11, abs_tol=1e-7), (a, b)


def main():
    import psutil
    import torch
    from alpha_holdem.policy_contract_v6 import validate_metadata
    torch.set_num_threads(1)
    if sys.argv[1:] or (BASE/'reviewed_analysis.json').exists(): raise ValueError('No alternate/repeated review')
    execution = run.read(BASE/'execution.json')
    assert execution['status'] == 'COMPLETED_PENDING_REVIEW' and not psutil.pid_exists(execution['pid'])
    roles = {'trainer'} | {f'{label}_anchor{a}' for label in ['source', 'mid262', 'mid524', 'final'] for a in range(5)}
    assert len(execution['children']) == 21 and {r['role'] for r in execution['children']} == roles
    assert all(r['exit_code'] == 0 and not psutil.pid_exists(r['pid']) for r in execution['children'])
    copies, anchors = run.read(BASE/'execution_code/copy_manifest.json'), run.read(BASE/'anchor_manifest.json')
    run.verify(copies, anchors)
    selection = run.read(BASE/'checkpoint_selection.json')
    assert list(selection) == ['source', 'mid262', 'mid524', 'final']
    production = BASE/'production'
    checkpoint = torch.load(production/'latest.pt', map_location='cpu', weights_only=False)
    validate_metadata(checkpoint)
    config = checkpoint['config']
    for key, value in dict(rollout_mode='multi', rollout_envs_per_worker=8, workers=12, seed=20260930,
                           worker_seed_base=2026093000, validate_stream=True, reset_hand_counter=True,
                           reset_optimizer=True, source_policy_kl_coef=.01, total_environment_hands=1048576,
                           fixed_training_deal_start_index=0).items(): assert config[key] == value
    metrics = [json.loads(line) for line in (production/'h1_training_metrics.jsonl').read_text().splitlines()]
    assert [r['iteration'] for r in metrics] == list(range(1, checkpoint['iteration']+1))
    counts = [r['environment_hand_accounting']['completed_hands'] for r in metrics]
    assert all(a < b for a, b in zip([0]+counts[:-1], counts))
    assert all(v < 1048576 for v in counts[:-1]) and counts[-1] >= 1048576
    archive_paths = run.archives_for(production)
    scheduled = [r for r in metrics if r['iteration'] % 4 == 0]
    assert set(archive_paths) == {r['iteration'] for r in scheduled}
    for label, threshold in [('mid262', 262144), ('mid524', 524288)]:
        chosen = next(r for r in scheduled if r['environment_hand_accounting']['completed_hands'] >= threshold)
        assert selection[label]['iteration'] == chosen['iteration']
        assert selection[label]['physical_hands'] == chosen['environment_hand_accounting']['completed_hands']
        assert run.sha(archive_paths[chosen['iteration']]) == selection[label]['sha256']
    source = torch.load(run.SOURCE, map_location='cpu', weights_only=False)
    assert selection['source']['sha256'] == anchors[0]['sha256'] and selection['source']['physical_hands'] == 0
    adam_ranges = {}
    for label, item in selection.items():
        assert run.sha(item['path']) == item['sha256']
        payload = torch.load(item['path'], map_location='cpu', weights_only=False)
        validate_metadata(payload)
        if label == 'source': continue
        assert run.sha(item['source']) == item['sha256']
        account = payload['environment_hand_accounting']
        assert account['prefix_complete'] and account['unknown_prefix_training_marker_hands'] == 0
        assert account['completed_hands'] == item['physical_hands']
        assert account['origin_run_id'] == payload['run_id'] == run.RUN_ID
        assert sum(w['completed_hands'] for w in account['session_worker_counts']) == account['completed_hands']
        assert len(payload['model']) == 86 and all(torch.isfinite(v).all() for v in payload['model'].values())
        assert sum(not torch.equal(v, source['model'][k]) for k, v in payload['model'].items()) == 86
        assert len(payload['optimizer']['state']) == 86
        steps = []
        for state in payload['optimizer']['state'].values():
            assert float(state['step']) > 0 and all(torch.isfinite(v).all() for v in state.values() if isinstance(v, torch.Tensor))
            steps.append(float(state['step']))
        adam_ranges[label] = [min(steps), max(steps)]
        assert [r['score_components']['checkpoint_sha256'] for r in payload['pool_snapshots']] == [r['sha256'] for r in anchors[:3]]
    assert adam_ranges['mid262'][0] < adam_ranges['mid524'][0] < adam_ranges['final'][0]
    count = checkpoint['environment_hand_accounting']['completed_hands']
    assert selection['final']['physical_hands'] == count and run.sha(production/'latest.pt') == selection['final']['sha256']
    manifest, audit = run.read(production/'run_manifest.json'), run.read(production/'session_audit.json')
    assert manifest['status'] == 'finished' and audit['status'] == 'PASS'
    assert count == manifest['environment_hand_accounting']['completed_hands'] == audit['actual_environment_hands']
    assert checkpoint['total_hands'] == manifest['total_hands'] == metrics[-1]['hands'] and count >= counts[-1]
    for row in metrics:
        assert row['run_id'] == run.RUN_ID and row['ppo_replay_rows'] == 0
        assert all(math.isfinite(row[k]) for k in ['approx_kl', 'reference_policy_kl'])
    for key, name in dict(checkpoint='latest.pt', manifest='run_manifest.json', metrics='h1_training_metrics.jsonl',
                           assignments='opponent_assignments.jsonl', train_log='latest_train.log').items():
        assert run.sha(production/name) == audit['artifact_integrity'][key]['sha256']
    expected, rng = [], random.Random(20261001)
    for _ in range(8192):
        deck = list(range(52))
        rng.shuffle(deck)
        expected.append(deck)
    assert len({tuple(d) for d in expected}) == 8192
    values, cells = {}, []
    for label, candidate in selection.items():
        for a in range(5):
            directory = BASE/'matrix'/f'{label}_anchor{a}'
            summary = run.read(directory/'summary.json')
            assert summary['status'] == 'COMPLETED' and summary['seed'] == 20261001 and summary['evaluation_hands'] == 16384
            assert summary['candidate_sha256'] == candidate['sha256'] and summary['anchor_sha256'] == anchors[a]['sha256']
            assert summary['pairs_sha256'] == run.sha(directory/'pairs.jsonl')
            rows = [json.loads(line) for line in (directory/'pairs.jsonl').read_text().splitlines()]
            assert [r['pair_index'] for r in rows] == list(range(8192)) and [r['deck'] for r in rows] == expected
            for row in rows:
                assert len(row['rewards_bb']) == 2 and all(math.isfinite(v) and abs(v) <= 200 for v in row['rewards_bb'])
                assert len(row['decisions']) == 2 and all(type(v) is int and v > 0 for v in row['decisions'])
            values[label, a] = [math.fsum(r['rewards_bb'])/2*100 for r in rows]
            result = independent_interval(values[label, a])
            close(result['bb_per_100'], summary['bb_per_100'])
            for x, y in zip(result['ci95'], summary['ci95']): close(x, y)
            cells.append(dict(candidate=label, anchor=a, **result))
    assert all(v == 0 for v in values['source', 0])
    contrasts = [dict(anchor=a, **independent_interval([f-s for f, s in zip(values['final', a], values['source', a])])) for a in range(5)]
    growth = independent_interval([math.fsum(values['final', a][i]-values['mid262', a][i] for a in [3, 4])/2 for i in range(8192)])
    significant = {r['anchor'] for r in contrasts if r['ci_adjusted'][0] > 0}
    passed = all(r['bb_per_100'] > 0 for r in contrasts) and len(significant) >= 3 and 0 in significant and bool(significant & {3, 4}) and growth['ci_adjusted'][0] > 0
    writer = run.read(BASE/'completed_analysis.json')
    assert writer['new_training_hands'] == count and writer['evaluation_hands'] == 327680 and writer['slumbot_hands'] == 0
    assert writer['confirmation_gate_pass'] == passed
    for row, original in zip([*contrasts, growth], [*writer['primary_contrasts'], writer['heldout_growth']]):
        close(row['bb_per_100'], original['bb_per_100'])
        for a, b in zip(row['ci_adjusted'], original['ci_adjusted']): close(a, b)
    descriptive = []
    for left, right in [('mid262', 'source'), ('mid524', 'mid262'), ('final', 'mid524'), ('final', 'mid262')]:
        for name, indices in [('training', [0, 1, 2]), ('heldout', [3, 4])]:
            vals = [math.fsum(values[left, a][i]-values[right, a][i] for a in indices)/len(indices) for i in range(8192)]
            descriptive.append(dict(contrast=f'{left}-{right}', group=name, **independent_interval(vals)))
    decision = 'ADMIT_INDEPENDENT_CONFIRMATION' if passed else 'PHYSICAL_SCALE_GATE_NOT_PASSED'
    assert writer['decision'] == decision
    report = dict(status='PASS', reviewed_at=datetime.now(timezone.utc).isoformat(), decision=decision,
                  confirmation_gate_pass=passed, qualification_admitted=False, new_training_hands=count,
                  evaluation_hands=327680, slumbot_hands=0, source_pairs_verified=len(copies), clean_child_exits=21,
                  training=dict(iteration=checkpoint['iteration'], overshoot=count-1048576, shutdown_counter_tail=count-counts[-1]),
                  selection=selection, optimizer_step_ranges=adam_ranges, primary_contrasts=contrasts,
                  heldout_growth=growth, cells=cells, descriptive_curve=descriptive)
    run.write(BASE/'reviewed_analysis.json', report)
    lines = ['# Corrected-v6 physical1m curve result', '', f'Decision: {decision}.', '',
             f'{count} new physical training hands;327680internal hands;0Slumbot hands.21normal child exits;full independent evidence PASS.', '',
             '| Contrast | bb/100 | 95%CI | Family6 adjusted CI |', '|---|---:|---|---|']
    for name, row in [(f'final-source anchor{r["anchor"]}', r) for r in contrasts]+[('heldout final-mid262 mean', growth)]:
        lines.append(f'| {name} | {row["bb_per_100"]:+.4f} | {row["ci95"]} | {row["ci_adjusted"]} |')
    lines += ['', 'Only this new final was eligible. No midpoint or old-control rescue, external qualification, or unseen-family/general equilibrium claim.']
    (BASE/'result_summary.md').write_text('\n'.join(lines)+'\n')
    run.log('--command', f'python research/experiments/{BASE.name}/review_finish.py',
            '--artifact', BASE/'reviewed_analysis.json', '--artifact', BASE/'result_summary.md',
            '--note', 'Independent counter-only selection, optimizer continuation, raw regenerated deals, six-contrast gate and all session/source identities verified.')
    subprocess.run([sys.executable, str(ROOT/'research/experiment_log.py'), 'finish', BASE.name, '--status', 'COMPLETED',
                    '--summary', f'Fresh physical1m curve completed{count}training and327680internal hands;{decision}.',
                    '--conclusion', 'Fixed within-run held-out growth and source breadth gate; all evidence valid, no external claim.',
                    '--decision', decision, '--next-step',
                    'Preregister independent confirmation of this exact new final.' if passed else
                    'Analyze complete curve for saturation/specialization and choose the next learned-weight mechanism; no automatic scale-up or checkpoint rescue.',
                    '--count', f'new_training_hands={count}', '--count', 'evaluation_hands=327680', '--count', 'slumbot_hands=0'],
                   cwd=ROOT, check=True)
    print(json.dumps(report))


if __name__ == '__main__': main()
