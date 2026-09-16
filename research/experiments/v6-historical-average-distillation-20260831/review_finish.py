"""Terminal-only independent accounting, parameter and CE arithmetic review."""
import json
import math
from pathlib import Path
import subprocess
import sys

import numpy as np
import psutil
import torch
import run_distillation as run

BASE = run.BASE


def not_alive(execution):
    try:
        return abs(psutil.Process(execution['pid']).create_time()-execution['create_time']) > .001
    except psutil.NoSuchProcess:
        return True


def main():
    if sys.argv[1:] or (BASE/'reviewed_analysis.json').exists():
        raise ValueError('No repeated review')
    torch.set_num_threads(1)
    execution = run.read(BASE/'execution.json')
    assert execution['status'] == 'COMPLETED_PENDING_REVIEW' and not_alive(execution)
    inputs = run.read(BASE/'input_manifest.json')
    copies = run.read(BASE/'execution_code/copy_manifest.json')
    run.verify(copies, inputs)
    record = run.read(BASE/'experiment.json')
    assert record['status'] == 'RUNNING'
    def recorded(path):
        entry = next(row for label, row in record['artifact_integrity'].items() if Path(label).resolve() == path.resolve())
        assert run.sha(path) == entry['sha256']
    for name in ('training_hands.jsonl', 'validation_hands.jsonl', 'reservoir.pt', 'latest.pt', 'collection_audit.json', 'fit_analysis.json', 'completed_analysis.json', 'training_metrics.jsonl'):
        recorded(BASE/name)
    audit, fit = run.read(BASE/'collection_audit.json'), run.read(BASE/'fit_analysis.json')
    assert audit['status'] == audit['training']['status'] == audit['validation']['status'] == fit['status'] == 'PASS'
    assert execution['new_training_hands'] == audit['training']['hands'] == run.TRAIN_HANDS
    assert execution['supervised_validation_hands'] == audit['validation']['hands'] == run.VALID_HANDS
    assert audit['training']['retained_rows_verified'] == audit['reservoir_rows'] == 262144
    assert audit['training']['scalar_model_replays'] > 0
    teacher_counts = np.zeros((17, 17), dtype=np.int64)
    validation_counts = []
    unique_decks = set()
    for split, expected in [('training', run.TRAIN_HANDS), ('validation', run.VALID_HANDS)]:
        hands, decisions = 0, 0
        with (BASE/f'{split}_hands.jsonl').open() as handle:
            for index, line in enumerate(handle):
                row = json.loads(line)
                assert row['index'] == index
                digest = __import__('hashlib').sha256(bytes(row['deck'])).digest()
                assert digest not in unique_decks
                unique_decks.add(digest)
                hands += 1
                decisions += len(row['events'])
                if split == 'training':
                    teacher_counts[tuple(row['teachers'])] += 1
                else:
                    validation_counts.append(len(row['events']))
        assert hands == expected and decisions == audit[split]['decisions']
    assert len(unique_decks) == run.TRAIN_HANDS+run.VALID_HANDS
    reservoir = torch.load(BASE/'reservoir.pt', map_location='cpu', weights_only=False)
    assert reservoir['seen'] == audit['training']['decisions'] and len(reservoir['ids']) == 262144
    assert reservoir['ids'].min() >= 0 and reservoir['ids'][:, 0].max() < run.TRAIN_HANDS
    metrics = [json.loads(line) for line in (BASE/'training_metrics.jsonl').read_text().splitlines()]
    assert len(metrics) == 12*256 and [r['step'] for r in metrics] == list(range(1, 3073))
    for epoch in range(1, 13):
        rows = [r for r in metrics if r['epoch'] == epoch]
        assert len(rows) == 256 and sum(r['rows'] for r in rows) == 262144
        assert all(math.isfinite(r['loss']) and math.isfinite(r['gradient_norm']) for r in rows)
    source = torch.load(inputs['teachers'][0]['path'], map_location='cpu', weights_only=False)
    final = torch.load(BASE/'latest.pt', map_location='cpu', weights_only=False)
    assert final['epoch'] == 12 and final['optimizer_steps'] == 3072
    assert final['source_weights_sha256'] == run.SOURCE_SHA
    assert final['dataset_sha256'] == run.sha(BASE/'reservoir.pt')
    assert final['input_manifest_sha256'] == run.sha(BASE/'input_manifest.json')
    changed = []
    assert set(final['model']) == set(source['model']) and len(final['model']) == 86
    for name, tensor in final['model'].items():
        assert torch.isfinite(tensor).all()
        if not torch.equal(tensor, source['model'][name]):
            changed.append(name)
    assert set(changed) == set(fit['trainable_changed_parameters'])
    assert not any(k.startswith('value_head.') for k in changed)
    assert len(final['optimizer']['state']) == len(changed)
    assert all(float(s['step']) == 3072 for s in final['optimizer']['state'].values())
    baseline, endpoint = [np.load(BASE/name) for name in ('validation_source_ce.npy', 'validation_epoch12_ce.npy')]
    assert len(baseline) == len(endpoint) == sum(validation_counts)
    assert np.isfinite(baseline).all() and np.isfinite(endpoint).all()
    blocks, offset = [], 0
    for count in validation_counts:
        assert count > 0
        blocks.append(math.fsum((baseline[offset:offset+count]-endpoint[offset:offset+count]).tolist())/count)
        offset += count
    mean = math.fsum(blocks)/len(blocks)
    se = math.sqrt(math.fsum((x-mean)**2 for x in blocks)/(len(blocks)-1)/len(blocks))
    ci = [mean-1.96*se, mean+1.96*se]
    assert np.allclose(blocks, np.load(BASE/'validation_hand_ce_improvement.npy'), rtol=1e-10, atol=1e-10)
    assert np.allclose(ci, fit['hand_ci95'], rtol=1e-10, atol=1e-10)
    decision = 'ADMIT_SEPARATE_STRENGTH_DIAGNOSTIC' if ci[0] > 0 else 'HISTORICAL_FIT_GATE_NOT_PASSED'
    assert decision == fit['decision']
    sys.path.insert(0, str(BASE/'execution_code/source_files/scripts'))
    from alpha_holdem.execution_v6 import load_policy
    _, _, digest = load_policy(BASE/'latest.pt', 'cpu')
    assert digest == fit['model_sha256']
    run.verify(copies, inputs)
    report = dict(status='PASS', decision=decision, new_training_hands=run.TRAIN_HANDS,
        supervised_validation_hands=run.VALID_HANDS, strength_evaluation_hands=0, slumbot_hands=0,
        unique_training_and_validation_decks=len(unique_decks), qualification_hands=0, goal_achieved=False,
        teacher_pair_hand_counts=teacher_counts.tolist(), epochs=12, optimizer_steps=3072,
        changed_policy_parameter_tensors=len(changed), model_sha256=digest,
        hand_mean_ce_improvement=mean, hand_ci95=ci, source_ce=float(baseline.mean()), final_ce=float(endpoint.mean()),
        interpretation='Historical behavior fit only. No new best-response learning, equilibrium guarantee or measured strength gain.',
        wall_time_seconds=execution['wall_time_seconds'])
    run.write('reviewed_analysis.json', report)
    (BASE/'result_summary.md').write_text(f'# Historical behavior distillation\n\n{decision}\n\n'
        f'262144new native200bb training-data hands;8192separate supervised-validation hands;0Slumbot/strength hands. '
        f'17whole-hand teachers,262144reservoir decisions,12epochs/3072Adam steps.\n\n'
        f'Hand-weighted heldout CE improvement {mean:.6f},95%CI{ci}. This is behavior fit, not poker strength.\n\n'
        f'Final model SHA256: {digest}. No prior hands recounted; full raw-action/deck/target trace and independent arithmetic checks PASS.\n')
    run.log('--command', f'python research/experiments/{BASE.name}/review_finish.py', '--artifact', BASE/'reviewed_analysis.json', '--artifact', BASE/'result_summary.md')
    subprocess.run([sys.executable, str(run.ROOT/'research/experiment_log.py'), 'finish', BASE.name,
        '--status', 'COMPLETED', '--summary', f'Historical average learned-policy fit completed262144training-data hands and8192supervised validation hands: {decision}.',
        '--conclusion', report['interpretation'], '--decision', decision,
        '--next-step', 'Freeze epoch12 for separate internal diagnostic/deployment parity and20k external pilot; no100k yet.' if ci[0] > 0 else 'Analyze failed historical behavior fit before choosing next learned-weight mechanism.',
        '--count', 'new_training_hands=262144', '--count', 'evaluation_hands=8192', '--count', 'supervised_validation_hands=8192', '--count', 'slumbot_hands=0'], cwd=run.ROOT, check=True)
    print(json.dumps(report))


if __name__ == '__main__':
    main()
