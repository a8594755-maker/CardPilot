"""Reuse the pinned archive-health verifier without changing live-run code."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
REFERENCE = ROOT/'research/experiments/v6-full-network-learning-curve-20260831/inspect_archive.py'
REFERENCE_SHA = '6142e830d47d738bc1917757d89febd7280290bb96900d510407f71d00bd50ac'
sys.path.insert(0, str(ROOT))
from research.experiment_log import capture_code_provenance, sha256_file


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--iteration', type=int, required=True)
    args = parser.parse_args()
    if args.iteration <= 0 or args.iteration % 4: raise ValueError('Scheduled archives only')
    output = BASE/f'archive_iter{args.iteration:06d}_review.json'
    if output.exists(): raise ValueError('Preserve earlier review')
    assert sha256_file(REFERENCE) == REFERENCE_SHA
    paths = list((BASE/'production/checkpoints').glob(f'checkpoint_iter{args.iteration:06d}_hands*.pt'))
    assert len(paths) == 1
    import torch
    torch.set_num_threads(1)
    checkpoint = torch.load(paths[0], map_location='cpu', weights_only=False)
    assert checkpoint['config']['source_policy_kl_coef'] == .1
    assert checkpoint['environment_hand_accounting']['origin_run_id'] == 'v6_kl010_retention_20260831'
    directory = BASE/'archive_review_code'
    if not directory.exists():
        directory.mkdir()
        relatives = [Path(__file__).resolve().relative_to(ROOT).as_posix(), REFERENCE.relative_to(ROOT).as_posix()]
        capture_code_provenance(ROOT, directory, relatives)
        copies = []
        for relative in relatives:
            target = directory/'source_files'/relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT/relative, target)
            copies.append(dict(original=relative, copy=target.relative_to(ROOT).as_posix(), sha256=sha256_file(target)))
        (directory/'copy_manifest.json').write_text(json.dumps(copies, indent=2)+'\n')
    copies = json.loads((directory/'copy_manifest.json').read_text())
    assert all(sha256_file(ROOT/item[key]) == item['sha256'] for item in copies for key in ['original', 'copy'])
    spec = importlib.util.spec_from_file_location('pinned_archive_health_reference', REFERENCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.BASE = BASE  # isolated module binding only; no source/checkpoint changes
    module.main()
    artifacts = [output, paths[0], directory/'source_manifest.json', directory/'code.patch', directory/'copy_manifest.json']
    subprocess.run([sys.executable, str(ROOT/'research/experiment_log.py'), 'update', BASE.name,
                    '--command', f'python research/experiments/v6-source-kl-retention-pilot-20260831/inspect_archive.py --iteration {args.iteration}',
                    *[v for p in artifacts for v in ['--artifact', str(p)]],
                    '--note', f'Outcome-blind scheduled archive{args.iteration}health review passed using pinned verifier:source-KL0.1 and new-run identity checked,86finite changed tensors/Adam states,physical prefix and pool/source integrity. No extra hands or performance evaluation.'], cwd=ROOT, check=True)


if __name__ == '__main__': main()
