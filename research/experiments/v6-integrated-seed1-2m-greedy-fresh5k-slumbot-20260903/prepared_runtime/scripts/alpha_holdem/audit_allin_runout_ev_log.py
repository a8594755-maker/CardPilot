"""Parse and audit immutable train_v5 all-in runout-EV log evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import torch


ROW_RE = re.compile(
    r'^\[\s*(?P<iteration>\d+)\]\s+hands=(?P<hands>[\d,]+).*?'
    r'\bmirror=(?P<mirror_replays>\d+)/(?P<mirror_source_hands>\d+)\s+'
    r'aiev=(?P<replacements>\d+):(?P<runouts>\d+)\s+'
    r'aiev_skip=(?P<skipped_hands>\d+):(?P<skipped_runouts>\d+)\b',
    re.MULTILINE,
)


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding='utf-8').splitlines()
        if line.strip()
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--expected-final-iteration', type=int, required=True)
    parser.add_argument('--expected-max-runouts', type=int, default=200)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()

    run_dir = args.run_dir.resolve()
    paths = {
        'checkpoint': run_dir / 'latest.pt',
        'manifest': run_dir / 'run_manifest.json',
        'metrics': run_dir / 'h1_training_metrics.jsonl',
        'train_log': run_dir / 'latest_train.log',
    }
    for path in paths.values():
        if not path.is_file():
            raise FileNotFoundError(path)

    checkpoint = torch.load(
        paths['checkpoint'], map_location='cpu', weights_only=False
    )
    manifest = json.loads(paths['manifest'].read_text(encoding='utf-8'))
    metrics = load_jsonl(paths['metrics'])
    config = checkpoint.get('config') or {}
    if config.get('allin_runout_ev') is not True:
        raise RuntimeError('checkpoint does not enable all-in runout EV')
    if int(config.get('allin_runout_ev_max_runouts', -1)) != args.expected_max_runouts:
        raise RuntimeError('all-in runout cap differs from preregistration')

    matches = list(ROW_RE.finditer(paths['train_log'].read_text(encoding='utf-8')))
    rows = [
        {
            key: int(value.replace(',', ''))
            for key, value in match.groupdict().items()
        }
        for match in matches
    ]
    expected_iterations = list(range(1, args.expected_final_iteration + 1))
    if [row['iteration'] for row in rows] != expected_iterations:
        raise RuntimeError('EV log iterations are not exactly contiguous')
    if len(metrics) != len(rows):
        raise RuntimeError('EV log row count differs from training metrics')
    for row, metric in zip(rows, metrics):
        if row['iteration'] != int(metric['iteration']):
            raise RuntimeError('EV log/metric iteration mismatch')
        if row['hands'] != int(metric['hands']):
            raise RuntimeError('EV log/metric hand mismatch')
    if int(checkpoint.get('iteration', -1)) != args.expected_final_iteration:
        raise RuntimeError('checkpoint final iteration mismatch')
    if int(manifest.get('iteration', -1)) != args.expected_final_iteration:
        raise RuntimeError('manifest final iteration mismatch')
    if manifest.get('status') != 'finished':
        raise RuntimeError('manifest is not terminal finished')

    totals = {
        key: sum(row[key] for row in rows)
        for key in (
            'mirror_replays',
            'mirror_source_hands',
            'replacements',
            'runouts',
            'skipped_hands',
            'skipped_runouts',
        )
    }
    if totals['replacements'] <= 0 or totals['runouts'] <= 0:
        raise RuntimeError('EV intervention never activated')
    if any(
        row['replacements'] > 0 and row['runouts'] < row['replacements']
        for row in rows
    ):
        raise RuntimeError('EV runout accounting is impossible')
    if totals['mirror_replays'] or totals['mirror_source_hands']:
        raise RuntimeError('unregistered mirror-deal intervention was active')

    result = {
        'schema': 'cardpilot.train_v5.allin_runout_ev_log_audit.v1',
        'status': 'PASS',
        'run_id': checkpoint.get('run_id'),
        'final_iteration': args.expected_final_iteration,
        'actual_environment_hands': int(checkpoint['total_hands']),
        'allin_runout_ev_max_runouts': args.expected_max_runouts,
        'iterations_with_replacements': sum(
            row['replacements'] > 0 for row in rows
        ),
        'totals': totals,
        'mean_runouts_per_replacement': (
            totals['runouts'] / totals['replacements']
        ),
        'rows': rows,
        'artifact_integrity': {
            name: {'bytes': path.stat().st_size, 'sha256': sha256_path(path)}
            for name, path in paths.items()
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8'
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
