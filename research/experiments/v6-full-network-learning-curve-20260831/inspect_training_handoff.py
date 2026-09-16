"""Review immutable training handoff while fixed evaluation runs, no scores."""
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
from research.experiment_log import capture_code_provenance, sha256_file


def main():
    if sys.argv[1:] or (BASE/'training_handoff_review.json').exists():
        raise ValueError('Fixed handoff review; preserve earlier evidence')
    import psutil
    import torch
    from alpha_holdem.policy_contract_v6 import validate_metadata
    torch.set_num_threads(1)
    execution = json.loads((BASE/'execution.json').read_text())
    trainer = [row for row in execution['children'] if row['role'] == 'trainer']
    assert len(trainer) == 1 and trainer[0]['exit_code'] == 0
    assert not psutil.pid_exists(trainer[0]['pid']), 'Original trainer must be terminal'
    manifest = json.loads((BASE/'production/run_manifest.json').read_text())
    assert manifest['status'] == 'finished'
    selection = json.loads((BASE/'checkpoint_selection.json').read_text())
    audit = json.loads((BASE/'session_audit.json').read_text())
    assert audit['status'] == 'PASS'
    for item in selection.values():
        assert sha256_file(Path(item['path'])) == item['sha256']
    final_path = Path(selection['final']['path'])
    checkpoint = torch.load(final_path, map_location='cpu', weights_only=False)
    validate_metadata(checkpoint)
    account = checkpoint['environment_hand_accounting']
    count = account['completed_hands']
    assert count >= 262144 and account['prefix_complete']
    assert account['unknown_prefix_training_marker_hands'] == 0
    assert account['origin_run_id'] == 'v6_full_curve_20260831'
    assert sum(row['completed_hands'] for row in account['session_worker_counts']) == count
    assert count == manifest['environment_hand_accounting']['completed_hands'] == audit['actual_environment_hands']
    rows = [json.loads(line) for line in (BASE/'production/h1_training_metrics.jsonl').read_text().splitlines()]
    assert [row['iteration'] for row in rows] == list(range(1, checkpoint['iteration']+1))
    counts = [row['environment_hand_accounting']['completed_hands'] for row in rows]
    assert all(a < b for a, b in zip([0]+counts[:-1], counts))
    assert all(value < 262144 for value in counts[:-1]) and counts[-1] >= 262144
    assert count >= counts[-1]
    for label, threshold in [('mid65', 65536), ('mid131', 131072)]:
        first = next(row for row in rows if row['iteration'] % 4 == 0
                     and row['environment_hand_accounting']['completed_hands'] >= threshold)
        assert selection[label]['iteration'] == first['iteration']
        assert selection[label]['physical_hands'] == first['environment_hand_accounting']['completed_hands']
    source_path = ROOT/'models/baseline/standard10/latest.pt'
    assert sha256_file(source_path) == '91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428'
    source = torch.load(source_path, map_location='cpu', weights_only=False)
    assert len(checkpoint['model']) == 86
    assert all(torch.isfinite(value).all() for value in checkpoint['model'].values())
    changed = sum(not torch.equal(value, source['model'][key]) for key, value in checkpoint['model'].items())
    assert changed == 86
    optimizer = checkpoint['optimizer']['state']
    assert len(optimizer) == 86
    for state in optimizer.values():
        assert float(state['step']) > 0
        assert all(torch.isfinite(value).all() for value in state.values() if isinstance(value, torch.Tensor))
    anchors = json.loads((BASE/'anchor_manifest.json').read_text())
    assert [row['score_components']['checkpoint_sha256'] for row in checkpoint['pool_snapshots']] == [row['sha256'] for row in anchors[:3]]
    for item in anchors:
        assert sha256_file(Path(item['path'])) == item['sha256']
    copies = json.loads((BASE/'execution_code/copy_manifest.json').read_text())
    for item in copies:
        assert all(sha256_file(ROOT/item[key]) == item['sha256'] for key in ['original', 'copy'])
    assert sha256_file(BASE/'production/latest.pt') == sha256_file(final_path) == selection['final']['sha256']
    directory = BASE/'handoff_code'
    directory.mkdir(exist_ok=False)
    relative = Path(__file__).resolve().relative_to(ROOT).as_posix()
    capture_code_provenance(ROOT, directory, [relative])
    target = directory/'source_files'/relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT/relative, target)
    helper_copy = dict(original=relative, copy=target.relative_to(ROOT).as_posix(), sha256=sha256_file(target))
    (directory/'copy_manifest.json').write_text(json.dumps([helper_copy], indent=2)+'\n')
    report = dict(status='PASS', reviewed_at=datetime.now(timezone.utc).isoformat(),
                  new_training_hands=count, physical_overshoot=count-262144,
                  last_update_physical_hands=counts[-1], shutdown_tail_physical_hands=count-counts[-1],
                  legacy_training_markers=checkpoint['total_hands'], iteration=checkpoint['iteration'],
                  finite_changed_tensors=changed, finite_optimizer_states=len(optimizer),
                  optimizer_steps=sorted(set(float(state['step']) for state in optimizer.values())),
                  source_pairs_verified=len(copies), selection=selection,
                  additional_training_hands=0, additional_evaluation_hands=0,
                  strength_assessed=False, external_qualification_admitted=False)
    (BASE/'training_handoff_review.json').write_text(json.dumps(report, indent=2)+'\n')
    artifacts = [BASE/'training_handoff_review.json', directory/'source_manifest.json',
                 directory/'code.patch', directory/'copy_manifest.json', ROOT/relative]
    subprocess.run([sys.executable, str(ROOT/'research/experiment_log.py'), 'update', BASE.name,
                    '--command', 'python research/experiments/v6-full-network-learning-curve-20260831/inspect_training_handoff.py',
                    *[v for path in artifacts for v in ['--artifact', str(path)]],
                    '--note', 'Outcome-blind training handoff independently verified: terminal trainer,first physical-budget crossing and shutdown tail,finite86changed tensors/Adam states,counter-only midpoints,frozen/source identities. No performance cells consumed,extra hands,or admission claim.'], cwd=ROOT, check=True)
    print(json.dumps(report))


if __name__ == '__main__': main()
