"""Independent outcome-blind review of the completed KL0.1 training handoff."""
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'scripts'))
from research.experiment_log import capture_code_provenance, sha256_file as _sha256_file


def sha256_file(path):
    return _sha256_file(Path(path))


def main():
    if sys.argv[1:] or (BASE/'training_handoff_review.json').exists():
        raise ValueError('Preserve the fixed prior handoff review')
    import psutil
    import torch
    from alpha_holdem.policy_contract_v6 import validate_metadata
    torch.set_num_threads(1)
    execution = json.loads((BASE/'execution.json').read_text())
    trainer = [r for r in execution['children'] if r['role'] == 'trainer']
    assert len(trainer) == 1 and trainer[0]['exit_code'] == 0 and not psutil.pid_exists(trainer[0]['pid'])
    manifest = json.loads((BASE/'production/run_manifest.json').read_text())
    audit = json.loads((BASE/'session_audit.json').read_text())
    assert manifest['status'] == 'finished' and audit['status'] == 'PASS'
    candidates = json.loads((BASE/'candidate_manifest.json').read_text())
    assert list(candidates) == ['source', 'weak_control', 'treatment']
    assert candidates['weak_control']['sha256'] == '0d2f660b3225664c5ed2bc85467649d3f3d17930cba8ab86c70b3d2082ee8606'
    assert candidates['source']['sha256'] == '944f5f6625e29c2d2562cc457206aafcf840ef0c7edd6accbd372e1362dd57b2'
    for item in candidates.values(): assert sha256_file(item['path']) == item['sha256']
    final_path = Path(candidates['treatment']['path'])
    checkpoint = torch.load(final_path, map_location='cpu', weights_only=False)
    validate_metadata(checkpoint)
    account = checkpoint['environment_hand_accounting']
    count = account['completed_hands']
    assert count >= 262144 and account['prefix_complete'] and account['unknown_prefix_training_marker_hands'] == 0
    assert account['origin_run_id'] == 'v6_kl010_retention_20260831'
    assert checkpoint['config']['source_policy_kl_coef'] == .1 and not checkpoint.get('ppo_replay_entries')
    assert sum(r['completed_hands'] for r in account['session_worker_counts']) == count
    assert count == manifest['environment_hand_accounting']['completed_hands'] == audit['actual_environment_hands']
    rows = [json.loads(line) for line in (BASE/'production/h1_training_metrics.jsonl').read_text().splitlines()]
    assert [r['iteration'] for r in rows] == list(range(1, checkpoint['iteration']+1))
    counts = [r['environment_hand_accounting']['completed_hands'] for r in rows]
    assert all(a < b for a, b in zip([0]+counts[:-1], counts))
    assert all(v < 262144 for v in counts[:-1]) and counts[-1] >= 262144 and count >= counts[-1]
    source_path = ROOT/'models/baseline/standard10/latest.pt'
    assert sha256_file(source_path) == '91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428'
    source = torch.load(source_path, map_location='cpu', weights_only=False)
    assert len(checkpoint['model']) == 86 and all(torch.isfinite(v).all() for v in checkpoint['model'].values())
    changed = sum(not torch.equal(v, source['model'][k]) for k, v in checkpoint['model'].items())
    assert changed == 86
    optimizer = checkpoint['optimizer']['state']
    assert len(optimizer) == 86
    for state in optimizer.values():
        assert float(state['step']) > 0 and all(torch.isfinite(v).all() for v in state.values() if isinstance(v, torch.Tensor))
    anchors = json.loads((BASE/'anchor_manifest.json').read_text())
    assert [r['score_components']['checkpoint_sha256'] for r in checkpoint['pool_snapshots']] == [r['sha256'] for r in anchors[:3]]
    for item in anchors: assert sha256_file(item['path']) == item['sha256'] == sha256_file(item['source'])
    copies = json.loads((BASE/'execution_code/copy_manifest.json').read_text())
    for item in copies: assert all(sha256_file(ROOT/item[key]) == item['sha256'] for key in ['original', 'copy'])
    for key, name in {'checkpoint':'latest.pt', 'manifest':'run_manifest.json', 'metrics':'h1_training_metrics.jsonl',
                      'assignments':'opponent_assignments.jsonl', 'train_log':'latest_train.log'}.items():
        assert sha256_file(BASE/'production'/name) == audit['artifact_integrity'][key]['sha256']
    assert sha256_file(BASE/'production/latest.pt') == sha256_file(final_path) == candidates['treatment']['sha256']
    directory = BASE/'handoff_code'
    directory.mkdir(exist_ok=False)
    relative = Path(__file__).resolve().relative_to(ROOT).as_posix()
    capture_code_provenance(ROOT, directory, [relative])
    target = directory/'source_files'/relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT/relative, target)
    (directory/'copy_manifest.json').write_text(json.dumps([dict(original=relative,
        copy=target.relative_to(ROOT).as_posix(), sha256=sha256_file(target))], indent=2)+'\n')
    report = dict(status='PASS', reviewed_at=datetime.now(timezone.utc).isoformat(),
        new_training_hands=count, physical_overshoot=count-262144, last_update_physical_hands=counts[-1],
        shutdown_tail_physical_hands=count-counts[-1], legacy_training_markers=checkpoint['total_hands'],
        iteration=checkpoint['iteration'], finite_changed_tensors=changed, finite_optimizer_states=len(optimizer),
        optimizer_steps=sorted(set(float(s['step']) for s in optimizer.values())),
        final_reference_policy_kl=rows[-1]['reference_policy_kl'], final_approx_kl=rows[-1]['approx_kl'],
        source_pairs_verified=len(copies), treatment_sha256=candidates['treatment']['sha256'],
        additional_training_hands=0, additional_evaluation_hands=0, strength_assessed=False,
        external_qualification_admitted=False)
    (BASE/'training_handoff_review.json').write_text(json.dumps(report, indent=2)+'\n')
    artifacts = [BASE/'training_handoff_review.json', directory/'source_manifest.json', directory/'code.patch', directory/'copy_manifest.json']
    subprocess.run([sys.executable, str(ROOT/'research/experiment_log.py'), 'update', BASE.name,
        '--command', 'python research/experiments/v6-source-kl-retention-pilot-20260831/inspect_training_handoff.py',
        *[v for p in artifacts for v in ['--artifact', str(p)]],
        '--note', 'Outcome-blind completed-training handoff independently verified:original trainer exited0,first physical budget crossing,full counters/finite86changed tensors/Adam states,pool/checkpoint/source identities. No evaluation score consumed,additional hands or admission.'], cwd=ROOT, check=True)
    print(json.dumps(report))


if __name__ == '__main__': main()
