"""Parse and audit immutable train_v5 mirrored-self-play log evidence."""

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
    if config.get('mirror_self_play_deals') is not True:
        raise RuntimeError('checkpoint does not enable self-play deal mirroring')
    if config.get('allin_runout_ev') is not False:
        raise RuntimeError('unregistered all-in EV intervention was active')

    rows = [
        {
            key: int(value.replace(',', ''))
            for key, value in match.groupdict().items()
        }
        for match in ROW_RE.finditer(paths['train_log'].read_text(encoding='utf-8'))
    ]
    expected_iterations = list(range(1, args.expected_final_iteration + 1))
    if [row['iteration'] for row in rows] != expected_iterations:
        raise RuntimeError('mirror log iterations are not exactly contiguous')
    if len(metrics) != len(rows):
        raise RuntimeError('mirror log row count differs from training metrics')
    pending = 0
    max_pending = int(config.get('workers', 0))
    if max_pending <= 0:
        raise RuntimeError('invalid worker count for pending-mirror audit')
    for row, metric in zip(rows, metrics):
        if row['iteration'] != int(metric['iteration']):
            raise RuntimeError('mirror log/metric iteration mismatch')
        if row['hands'] != int(metric['hands']):
            raise RuntimeError('mirror log/metric hand mismatch')
        if row['mirror_source_hands'] <= 0:
            raise RuntimeError('mirror intervention did not activate in an update')
        pending += row['mirror_source_hands'] - row['mirror_replays']
        row['pending_after_iteration'] = pending
        if not 0 <= pending <= max_pending:
            raise RuntimeError(
                'pending mirror count escapes one-per-worker boundary'
            )
        if any(row[key] for key in (
            'replacements', 'runouts', 'skipped_hands', 'skipped_runouts'
        )):
            raise RuntimeError('unregistered all-in EV evidence is nonzero')

    if int(checkpoint.get('iteration', -1)) != args.expected_final_iteration:
        raise RuntimeError('checkpoint final iteration mismatch')
    if int(manifest.get('iteration', -1)) != args.expected_final_iteration:
        raise RuntimeError('manifest final iteration mismatch')
    if manifest.get('status') != 'finished':
        raise RuntimeError('manifest is not terminal finished')

    mirror_replays = sum(row['mirror_replays'] for row in rows)
    mirror_sources = sum(row['mirror_source_hands'] for row in rows)
    if mirror_sources <= 0 or mirror_replays <= 0:
        raise RuntimeError('mirror intervention never activated')
    if mirror_sources - mirror_replays != pending:
        raise RuntimeError('terminal pending-mirror accounting mismatch')
    result = {
        'schema': 'cardpilot.train_v5.mirrored_selfplay_log_audit.v1',
        'status': 'PASS',
        'run_id': checkpoint.get('run_id'),
        'final_iteration': args.expected_final_iteration,
        'actual_environment_hands': int(checkpoint['total_hands']),
        'iterations_with_mirrors': len(rows),
        'mirror_source_hands': mirror_sources,
        'mirror_replay_hands': mirror_replays,
        'terminal_pending_mirrors': pending,
        'maximum_allowed_pending_mirrors': max_pending,
        'paired_mirror_hands': mirror_sources + mirror_replays,
        'paired_fraction_of_environment_hands': (
            (mirror_sources + mirror_replays) / int(checkpoint['total_hands'])
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
