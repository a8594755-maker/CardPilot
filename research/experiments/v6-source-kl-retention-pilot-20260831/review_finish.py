"""Independent raw arithmetic and evidence review after the whole pilot exits."""
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'scripts'))
from research.experiment_log import sha256_file


def interval(values):
    if len(values) < 2 or not all(math.isfinite(x) for x in values): raise ValueError('Invalid pairs')
    mean = math.fsum(values)/len(values)
    se = math.sqrt(math.fsum((x-mean)**2 for x in values)/(len(values)-1)/len(values))
    z = statistics.NormalDist().inv_cdf((1+(1-.05/6))/2)
    return dict(bb_per_100=mean, standard_error=se, ci95=[mean-1.96*se, mean+1.96*se],
                ci_adjusted=[mean-z*se, mean+z*se])


def raw_values(rows):
    if len(rows) != 8192 or [r['pair_index'] for r in rows] != list(range(8192)):
        raise ValueError('Wrong raw pair prefix')
    for row in rows:
        assert len(row['deck']) == 52 and set(row['deck']) == set(range(52))
        assert len(row['rewards_bb']) == 2 and all(math.isfinite(v) and abs(v) <= 200 for v in row['rewards_bb'])
        assert len(row['decisions']) == 2 and all(type(v) is int and v > 0 for v in row['decisions'])
    return [math.fsum(row['rewards_bb'])/2*100 for row in rows]


def main():
    if sys.argv[1:] or (BASE/'reviewed_analysis.json').exists(): raise ValueError('No alternate review or overwrite')
    import psutil
    import torch
    from alpha_holdem.policy_contract_v6 import validate_metadata
    torch.set_num_threads(1)
    execution = json.loads((BASE/'execution.json').read_text())
    assert execution['status'] == 'COMPLETED_PENDING_REVIEW' and not psutil.pid_exists(execution['pid'])
    children = execution['children']
    assert len(children) == 16 and all(row['exit_code'] == 0 and not psutil.pid_exists(row['pid']) for row in children)
    expected_roles = {'trainer'} | {f'{label}_anchor{a}' for label in ['source', 'weak_control', 'treatment'] for a in range(5)}
    assert {row['role'] for row in children} == expected_roles
    writer = json.loads((BASE/'completed_analysis.json').read_text())
    ckpt = torch.load(BASE/'production/latest.pt', map_location='cpu', weights_only=False)
    validate_metadata(ckpt)
    account = ckpt['environment_hand_accounting']
    count = account['completed_hands']
    assert count >= 262144 and account['prefix_complete'] and account['unknown_prefix_training_marker_hands'] == 0
    assert account['origin_run_id'] == 'v6_kl010_retention_20260831'
    assert sum(row['completed_hands'] for row in account['session_worker_counts']) == count
    assert ckpt['config']['source_policy_kl_coef'] == .1 and not ckpt.get('ppo_replay_entries')
    manifest = json.loads((BASE/'production/run_manifest.json').read_text())
    assert manifest['status'] == 'finished' and manifest['environment_hand_accounting']['completed_hands'] == count
    metrics = [json.loads(line) for line in (BASE/'production/h1_training_metrics.jsonl').read_text().splitlines()]
    assert [r['iteration'] for r in metrics] == list(range(1, ckpt['iteration']+1))
    counts = [r['environment_hand_accounting']['completed_hands'] for r in metrics]
    assert all(a < b for a, b in zip([0]+counts[:-1], counts))
    assert all(v < 262144 for v in counts[:-1]) and counts[-1] >= 262144 and count >= counts[-1]
    source_path = ROOT/'models/baseline/standard10/latest.pt'
    assert sha256_file(source_path) == '91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428'
    source = torch.load(source_path, map_location='cpu', weights_only=False)
    assert len(ckpt['model']) == 86 and all(torch.isfinite(v).all() for v in ckpt['model'].values())
    changed = sum(not torch.equal(v, source['model'][k]) for k, v in ckpt['model'].items())
    assert changed == 86 and len(ckpt['optimizer']['state']) == 86
    for state in ckpt['optimizer']['state'].values():
        assert float(state['step']) > 0 and all(torch.isfinite(v).all() for v in state.values() if isinstance(v, torch.Tensor))
    anchors = json.loads((BASE/'anchor_manifest.json').read_text())
    assert [r['score_components']['checkpoint_sha256'] for r in ckpt['pool_snapshots']] == [r['sha256'] for r in anchors[:3]]
    for item in anchors:
        assert sha256_file(Path(item['path'])) == item['sha256'] == sha256_file(Path(item['source']))
    candidates = json.loads((BASE/'candidate_manifest.json').read_text())
    assert list(candidates) == ['source', 'weak_control', 'treatment']
    assert candidates['weak_control']['sha256'] == '0d2f660b3225664c5ed2bc85467649d3f3d17930cba8ab86c70b3d2082ee8606'
    assert candidates['treatment']['sha256'] == sha256_file(BASE/'production/latest.pt')
    for item in candidates.values():
        assert sha256_file(Path(item['path'])) == item['sha256']
        validate_metadata(torch.load(item['path'], map_location='cpu', weights_only=False))
    copies = json.loads((BASE/'execution_code/copy_manifest.json').read_text())
    for item in copies:
        assert all(sha256_file(ROOT/item[key]) == item['sha256'] for key in ['original', 'copy'])
    audit = json.loads((BASE/'session_audit.json').read_text())
    assert audit['status'] == 'PASS' and audit['actual_environment_hands'] == count
    for key, name in {'checkpoint':'latest.pt', 'manifest':'run_manifest.json', 'metrics':'h1_training_metrics.jsonl',
                      'assignments':'opponent_assignments.jsonl', 'train_log':'latest_train.log'}.items():
        assert sha256_file(BASE/'production'/name) == audit['artifact_integrity'][key]['sha256']
    values, cells, decks = {}, [], None
    for label, candidate in candidates.items():
        for anchor in range(5):
            directory = BASE/'matrix'/f'{label}_anchor{anchor}'
            summary = json.loads((directory/'summary.json').read_text())
            assert summary['status'] == 'COMPLETED' and summary['seed'] == 20260921 and summary['evaluation_hands'] == 16384
            assert summary['candidate_sha256'] == candidate['sha256'] and summary['anchor_sha256'] == anchors[anchor]['sha256']
            assert summary['pairs_sha256'] == sha256_file(directory/'pairs.jsonl')
            rows = [json.loads(line) for line in (directory/'pairs.jsonl').read_text().splitlines()]
            current_decks = [row['deck'] for row in rows]
            if decks is None: decks = current_decks
            assert decks == current_decks and len({tuple(deck) for deck in decks}) == 8192
            values[label, anchor] = raw_values(rows)
            result = interval(values[label, anchor])
            assert abs(result['bb_per_100']-summary['bb_per_100']) < 1e-8
            assert max(abs(a-b) for a, b in zip(result['ci95'], summary['ci95'])) < 1e-7
            cells.append(dict(candidate=label, anchor=anchor, **result))
    assert all(v == 0 for v in values['source', 0])
    contrasts = [dict(anchor=a, **interval([new-old for old, new in zip(values['source', a], values['treatment', a])])) for a in range(5)]
    retention = interval([math.fsum(values['treatment', a][i]-values['weak_control', a][i] for a in [3, 4])/2 for i in range(8192)])
    significant = {r['anchor'] for r in contrasts if r['ci_adjusted'][0] > 0}
    passed = (all(r['bb_per_100'] > 0 for r in contrasts) and len(significant) >= 3 and 0 in significant
              and bool(significant & {3, 4}) and retention['ci_adjusted'][0] > 0)
    for a, b in zip([*contrasts, retention], [*writer['primary_contrasts'], writer['retention_contrast']]):
        assert abs(a['bb_per_100']-b['bb_per_100']) < 1e-7
        assert max(abs(x-y) for x, y in zip(a['ci_adjusted'], b['ci_adjusted'])) < 1e-7
    assert passed == writer['confirmation_gate_pass'] and writer['new_training_hands'] == count
    report = dict(status='PASS', decision='ADMIT_INDEPENDENT_CONFIRMATION' if passed else 'RETENTION_GATE_NOT_PASSED',
                  confirmation_gate_pass=passed, qualification_admitted=False, old_control_eligible=False,
                  new_training_hands=count, physical_overshoot=count-262144, evaluation_hands=245760, slumbot_hands=0,
                  iterations=ckpt['iteration'], finite_changed_tensors=changed, source_pairs_verified=len(copies),
                  clean_child_exits=len(children), primary_contrasts=contrasts, retention_contrast=retention,
                  cells=cells, reviewed_at=datetime.now(timezone.utc).isoformat())
    (BASE/'reviewed_analysis.json').write_text(json.dumps(report, indent=2)+'\n')
    lines = ['# v6 source-KL retention result', '', f'Decision: {report["decision"]}.', '',
             f'{count}new physical training hands;245760new internal evaluation hands;16clean child exits. '
             'Full raw/counter/finite-weight/frozen/source review passed. No old control promotion or Slumbot qualification.', '',
             '| Contrast |bb/100|95%CI|Six-contrast adjusted CI|', '|---|---:|---|---|']
    for name, row in [(f'treatment-source anchor{r["anchor"]}', r) for r in contrasts]+[('heldout treatment-control mean', retention)]:
        lines.append(f'|{name}|{row["bb_per_100"]:+.4f}|{row["ci95"]}|{row["ci_adjusted"]}|')
    lines += ['', 'Training seeds match the old control,not necessarily its asynchronous trajectories. '
              'These heldout anchors are not wholly unseen families; one training-seed intervention is not a multi-seed causal proof.']
    (BASE/'result_summary.md').write_text('\n'.join(lines)+'\n')
    subprocess.run([sys.executable, str(ROOT/'research/experiment_log.py'), 'update', BASE.name,
                    '--command', 'python research/experiments/v6-source-kl-retention-pilot-20260831/review_finish.py',
                    '--artifact', str(BASE/'reviewed_analysis.json'), '--artifact', str(BASE/'result_summary.md'),
                    '--note', 'Independent raw arithmetic,six-contrast joint gate and full evidence review passed. Only the new treatment could be admitted to separate confirmation; old control remains ineligible.'], cwd=ROOT, check=True)
    subprocess.run([sys.executable, str(ROOT/'research/experiment_log.py'), 'finish', BASE.name,
                    '--status', 'COMPLETED', '--summary', f'Fixed source-KL0.1 intervention completed{count}physical training and245760internal hands;{report["decision"]}.',
                    '--conclusion', 'The preregistered retention/breadth test completed with valid evidence; internal comparisons do not establish external or Nash strength.',
                    '--decision', report['decision'], '--next-step',
                    ('Preregister independent confirmation of the new treatment,with external evidence hardening before any live qualification.' if passed else
                     'Analyze learning/retention tradeoffs and choose a different registered mechanism; do not promote old control or search earlier checkpoints.'),
                    '--count', f'new_training_hands={count}', '--count', 'evaluation_hands=245760', '--count', 'slumbot_hands=0'], cwd=ROOT, check=True)
    print(json.dumps(report))


if __name__ == '__main__': main()
