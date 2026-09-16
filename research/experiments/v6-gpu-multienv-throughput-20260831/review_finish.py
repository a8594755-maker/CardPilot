"""Independent terminal counter/timing/provenance review; executes no poker hands."""
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'scripts'))
from research.experiment_log import capture_code_provenance, sha256_file


def sha(path): return sha256_file(Path(path))


def read(path): return json.loads(Path(path).read_text())


def near(a, b):
    assert math.isfinite(a) and math.isfinite(b) and math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12), (a, b)


def main():
    import psutil
    import torch
    from alpha_holdem.policy_contract_v6 import validate_metadata
    torch.set_num_threads(1)
    if sys.argv[1:] or (BASE/'reviewed_analysis.json').exists(): raise ValueError('Preserve previous review')
    execution = read(BASE/'execution.json')
    assert execution['status'] == 'COMPLETED_PENDING_REVIEW' and not psutil.pid_exists(execution['pid'])
    arms = [('single1', 'single', 1), ('multi4', 'multi', 4), ('multi8', 'multi', 8)]
    assert [r['arm'] for r in execution['children']] == [a[0] for a in arms]
    assert all(r['exit_code'] == 0 and not psutil.pid_exists(r['pid']) for r in execution['children'])
    report = read(BASE/'completed_analysis.json')
    assert report['status'] == 'COMPLETED_PENDING_REVIEW'
    assert not report['resume_qualified'] and not report['strength_qualified']
    assert report['evaluation_hands'] == report['slumbot_hands'] == 0
    copies = read(BASE/'execution_code/copy_manifest.json')
    for row in copies: assert all(sha(ROOT/row[key]) == row['sha256'] for key in ['original', 'copy'])
    source_path = ROOT/'models/baseline/standard10/latest.pt'
    assert sha(source_path) == '91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428'
    source = torch.load(source_path, map_location='cpu', weights_only=False)
    anchors = read(BASE/'anchor_manifest.json')
    assert [a['index'] for a in anchors] == [0, 1, 2]
    for row in anchors: assert sha(row['path']) == row['sha256'] == sha(row['source'])
    reviewed = []
    for (label, mode, slots), child, result in zip(arms, execution['children'], report['results']):
        run = BASE/'arms'/label
        assert result == read(run/'analysis.json') and result['health'] == 'PASS'
        checkpoint = torch.load(run/'latest.pt', map_location='cpu', weights_only=False)
        validate_metadata(checkpoint)
        manifest, audit = read(run/'run_manifest.json'), read(run/'session_audit.json')
        assert manifest['status'] == 'finished' and audit['status'] == 'PASS'
        config = checkpoint['config']
        for key, expected in dict(rollout_mode=mode, rollout_envs_per_worker=slots, workers=12,
                                  seed=20260925, worker_seed_base=2026092500, validate_stream=True,
                                  fixed_training_deal_stream=True, fixed_training_deal_start_index=0,
                                  source_policy_kl_coef=.01, total_environment_hands=32768,
                                  reset_hand_counter=True, reset_optimizer=True,
                                  inference_min_batch_slots=0, inference_batch_deadline_us=700).items():
            assert config[key] == expected, (label, key)
        assert checkpoint['run_id'] == f'v6_gpu_{label}_20260831'
        count = checkpoint['environment_hand_accounting']['completed_hands']
        account = checkpoint['environment_hand_accounting']
        assert account['prefix_complete'] and account['unknown_prefix_training_marker_hands'] == 0
        assert sum(w['completed_hands'] for w in account['session_worker_counts']) == count
        assert len(account['session_worker_counts']) == 12
        assert count == manifest['environment_hand_accounting']['completed_hands'] == audit['actual_environment_hands'] == result['new_training_hands']
        assert checkpoint['total_hands'] == manifest['total_hands']
        assert [r['score_components']['checkpoint_sha256'] for r in checkpoint['pool_snapshots']] == [r['sha256'] for r in anchors]
        assert len(checkpoint['model']) == 86 and all(torch.isfinite(v).all() for v in checkpoint['model'].values())
        assert sum(not torch.equal(v, source['model'][k]) for k, v in checkpoint['model'].items()) == 86
        optimizer = checkpoint['optimizer']['state']
        assert len(optimizer) == 86 and len({float(s['step']) for s in optimizer.values()}) == 1
        for state in optimizer.values():
            assert float(state['step']) > 0 and all(torch.isfinite(v).all() for v in state.values() if isinstance(v, torch.Tensor))
        metrics = [json.loads(line) for line in (run/'h1_training_metrics.jsonl').read_text().splitlines()]
        assert [r['iteration'] for r in metrics] == list(range(1, checkpoint['iteration']+1))
        physical = [r['environment_hand_accounting']['completed_hands'] for r in metrics]
        assert all(a < b for a, b in zip([0]+physical[:-1], physical))
        assert all(h < 32768 for h in physical[:-1]) and physical[-1] >= 32768 and count >= physical[-1]
        lines = [line for line in (run/'latest_train.log').read_text().splitlines() if re.match(r'^\[\s*\d+\]', line)]
        assert len(lines) == len(metrics) >= 2
        times, batches = [], []
        for i, (line, metric) in enumerate(zip(lines, metrics), 1):
            index = int(re.match(r'^\[\s*(\d+)\]', line)[1])
            fields = dict(re.findall(r'([a-z_]+)=([^\s]+)', line))
            assert index == metric['iteration'] == i
            assert int(fields['hands'].replace(',', '')) == metric['hands']
            assert int(fields['envhands'].replace(',', '')) == physical[i-1]
            times.append((float(fields['collect'].removesuffix('s')), float(fields['ppo'].removesuffix('s'))))
            batches.append(float(fields['inf_bs']))
            assert all(math.isfinite(metric[k]) for k in ['approx_kl', 'reference_policy_kl'])
            assert metric['ppo_replay_rows'] == 0
        for start, key in [(0, 'all_updates'), (1, 'excluding_update1')]:
            elapsed = sum(sum(t) for t in times[start:])
            actual = physical[-1] - (physical[start-1] if start else 0)
            near(result[key]['physical_hands_per_logged_second'], actual/elapsed)
            near(result[key]['median_inference_batch_mean'], statistics.median(batches[start:]))
        near(result['physical_hands_per_trainer_wall_second'], count/child['wall_seconds'])
        assert result['overshoot'] == count-32768 and result['shutdown_counter_tail'] == count-physical[-1]
        assert result['checkpoint_sha256'] == sha(run/'latest.pt')
        for key, name in dict(checkpoint='latest.pt', manifest='run_manifest.json', metrics='h1_training_metrics.jsonl',
                              assignments='opponent_assignments.jsonl', train_log='latest_train.log').items():
            assert sha(run/name) == audit['artifact_integrity'][key]['sha256']
        reviewed.append(dict(arm=label, slots=slots, actual_hands=count,
                             wall_rate=count/child['wall_seconds'], warm_rate=result['excluding_update1']['physical_hands_per_logged_second'],
                             median_batch=result['all_updates']['median_inference_batch_mean'],
                             checkpoint_sha256=sha(run/'latest.pt')))
    assert sum(r['actual_hands'] for r in reviewed) == report['new_training_hands']
    eligible = [r for r in reviewed[1:] if r['wall_rate'] >= 1.25*reviewed[0]['wall_rate'] and r['warm_rate'] >= 1.25*reviewed[0]['warm_rate']]
    selected = max(eligible, key=lambda r:(r['wall_rate'], -r['slots']))['arm'] if eligible else 'single1'
    assert selected == report['selected_fresh_start_configuration']
    directory = BASE/'review_code'
    directory.mkdir(exist_ok=False)
    relative = Path(__file__).resolve().relative_to(ROOT).as_posix()
    capture_code_provenance(ROOT, directory, [relative])
    target = directory/'source_files'/relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT/relative, target)
    (directory/'copy_manifest.json').write_text(json.dumps([dict(original=relative, copy=target.relative_to(ROOT).as_posix(), sha256=sha(target))], indent=2)+'\n')
    decision = 'MULTIENV_FRESH_START_THROUGHPUT_QUALIFIED' if selected != 'single1' else 'MULTIENV_SPEED_GATE_NOT_PASSED'
    final = dict(status='PASS', reviewed_at=datetime.now(timezone.utc).isoformat(), decision=decision,
                 selected_fresh_start_configuration=selected, new_training_hands=report['new_training_hands'],
                 evaluation_hands=0, slumbot_hands=0, strength_qualified=False, resume_qualified=False,
                 code_copy_pairs_verified=len(copies), reviewed_arms=reviewed)
    (BASE/'reviewed_analysis.json').write_text(json.dumps(final, indent=2, allow_nan=False)+'\n')
    text = '# Real-GPU multi-environment throughput result\n\n'
    text += f'Decision: {decision}. Selected fresh-start configuration: {selected}.\n\n'
    text += '| Arm | Actual physical hands | Trainer wall hands/s | Excluding update1 logged hands/s | Median batch |\n|---|---:|---:|---:|---:|\n'
    for r in reviewed:
        text += f'| {r["arm"]} | {r["actual_hands"]} | {r["wall_rate"]:.3f} | {r["warm_rate"]:.3f} | {r["median_batch"]:.2f} |\n'
    text += '\nAll three trainer/session/numerical/counter/provenance audits passed. This ordered single-run comparison measures implementation throughput, not causal or multi-seed performance. Logged times are rounded and omit non-collection/PPO overhead; trainer wall rate includes it. Completed unconsumed worker tails are included in physical counts, not optimizer consumption. Worker normal shutdown and per-slot interrupted resume are not qualified. Zero evaluation or Slumbot hands; no short-arm checkpoint may be promoted.\n'
    (BASE/'result_summary.md').write_text(text)
    update = [sys.executable, str(ROOT/'research/experiment_log.py'), 'update', BASE.name,
              '--count', f'new_training_hands={report["new_training_hands"]}', '--count', 'evaluation_hands=0', '--count', 'slumbot_hands=0',
              '--metric', f'selected_fresh_start_configuration={selected}']
    for path in [BASE/'reviewed_analysis.json', BASE/'result_summary.md', directory/'source_manifest.json', directory/'code.patch', directory/'copy_manifest.json']:
        update += ['--artifact', str(path)]
    subprocess.run(update, cwd=ROOT, check=True)
    subprocess.run([sys.executable, str(ROOT/'research/experiment_log.py'), 'finish', BASE.name, '--status', 'COMPLETED',
                    '--summary', f'Three fresh GPU arms completed {report["new_training_hands"]} physical hands; health/evidence PASS; {decision}.',
                    '--conclusion', f'Selected {selected} by fixed wall/warm throughput thresholds; no strength or resume qualification.',
                    '--decision', decision,
                    '--next-step', 'Use the qualified fresh-start configuration in a newly preregistered broader learned-weight training experiment; keep untouched evaluation and external admission separate.'], cwd=ROOT, check=True)
    print(json.dumps(final))


if __name__ == '__main__': main()
