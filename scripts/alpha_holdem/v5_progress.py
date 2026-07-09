#!/usr/bin/env python3
"""Progress and ETA report for an AlphaHoldem V5 from-zero run."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import torch

from v5_monitor import parse_log


DEFAULT_MILESTONES = [
    250_000_000,
    500_000_000,
    1_000_000_000,
    2_700_000_000,
]


def fmt_duration(seconds: float | None) -> str:
    if seconds is None:
        return 'unknown'
    if seconds < 0:
        seconds = 0
    delta = timedelta(seconds=int(seconds))
    days = delta.days
    hours, rem = divmod(delta.seconds, 3600)
    minutes, _ = divmod(rem, 60)
    if days:
        return f'{days}d {hours}h {minutes}m'
    if hours:
        return f'{hours}h {minutes}m'
    return f'{minutes}m'


def load_checkpoint(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return torch.load(path, map_location='cpu', weights_only=False)
    except Exception as exc:
        return {'_load_error': str(exc)}


def estimate_seconds_per_iteration(rows: list[dict]) -> float | None:
    durations: list[float] = []
    for prev, cur in zip(rows, rows[1:]):
        delta_hands = int(cur['hands']) - int(prev['hands'])
        hps = float(cur.get('hands_per_second') or 0.0)
        if delta_hands > 0 and hps > 0:
            durations.append(delta_hands / hps)
    return sum(durations) / len(durations) if durations else None


def next_multiple_after(value: int, interval: int | None) -> int | None:
    if not interval or interval <= 0:
        return None
    return ((value // interval) + 1) * interval


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', required=True)
    parser.add_argument('--tail', type=int, default=50)
    parser.add_argument(
        '--milestones',
        default=','.join(str(x) for x in DEFAULT_MILESTONES),
        help='Comma-separated actual-hand milestones.',
    )
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    log_path = run_dir / 'latest_train.log'
    manifest_path = run_dir / 'run_manifest.json'
    checkpoint_path = run_dir / 'latest.pt'

    manifest = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    rows = parse_log(log_path)
    latest = rows[-1] if rows else None
    recent = rows[-args.tail:] if rows else []
    checkpoint = load_checkpoint(checkpoint_path)

    recent_hps_values = [float(r['hands_per_second']) for r in recent if r.get('hands_per_second')]
    recent_hps = sum(recent_hps_values) / len(recent_hps_values) if recent_hps_values else None
    recent_seconds_per_iteration = estimate_seconds_per_iteration(recent)
    current_hands = int(latest['hands']) if latest else int(manifest.get('total_hands') or 0)
    now = datetime.now(timezone.utc)

    milestones = [int(x.strip()) for x in args.milestones.split(',') if x.strip()]
    milestone_rows = []
    for target in milestones:
        remaining = max(target - current_hands, 0)
        eta_seconds = remaining / recent_hps if recent_hps and recent_hps > 0 else None
        eta_at = (now + timedelta(seconds=eta_seconds)).isoformat() if eta_seconds is not None else None
        milestone_rows.append({
            'hands': target,
            'remaining_hands': remaining,
            'complete': current_hands >= target,
            'eta_seconds': eta_seconds,
            'eta_duration': fmt_duration(eta_seconds),
            'eta_at': eta_at,
        })

    config = manifest.get('config', {}) if isinstance(manifest.get('config'), dict) else {}
    current_iteration = int(latest['iteration']) if latest else int(manifest.get('iteration') or 0)
    try:
        k_best = int(config.get('k_best') or 0)
    except Exception:
        k_best = 0
    gate_rows = []
    for name, interval_key, expected_pool in [
        ('checkpoint_save', 'save_interval', None),
        ('opponent_pool_snapshot', 'snapshot_every', None),
    ]:
        interval = int(config.get(interval_key) or 0)
        target_iteration = next_multiple_after(current_iteration, interval)
        if target_iteration is None:
            continue
        remaining_iterations = max(target_iteration - current_iteration, 0)
        eta_seconds = (
            remaining_iterations * recent_seconds_per_iteration
            if recent_seconds_per_iteration is not None
            else None
        )
        if name == 'opponent_pool_snapshot':
            expected_pool = target_iteration // interval if interval > 0 else None
            if expected_pool is not None and k_best > 0:
                expected_pool = min(expected_pool, k_best)
        gate_rows.append({
            'name': name,
            'target_iteration': target_iteration,
            'remaining_iterations': remaining_iterations,
            'eta_seconds': eta_seconds,
            'eta_duration': fmt_duration(eta_seconds),
            'eta_at': (now + timedelta(seconds=eta_seconds)).isoformat() if eta_seconds is not None else None,
            'expected_pool_snapshots': expected_pool,
        })

    ckpt_error = checkpoint.get('_load_error') if isinstance(checkpoint, dict) else None
    summary = {
        'run_dir': str(run_dir),
        'run_id': manifest.get('run_id') or (checkpoint.get('run_id') if isinstance(checkpoint, dict) else None),
        'checked_at': now.isoformat(),
        'latest': latest,
        'recent_hands_per_second': recent_hps,
        'recent_seconds_per_iteration': recent_seconds_per_iteration,
        'upcoming_gates': gate_rows,
        'milestones': milestone_rows,
        'checkpoint': {
            'path': str(checkpoint_path),
            'exists': checkpoint_path.exists(),
            'load_error': ckpt_error,
            'iteration': checkpoint.get('iteration') if isinstance(checkpoint, dict) else None,
            'total_hands': checkpoint.get('total_hands') if isinstance(checkpoint, dict) else None,
            'env_version': checkpoint.get('env_version') if isinstance(checkpoint, dict) else None,
            'obs_version': checkpoint.get('obs_version') if isinstance(checkpoint, dict) else None,
            'pool_snapshots': len(checkpoint.get('pool_snapshots', [])) if isinstance(checkpoint, dict) else None,
        },
    }

    (run_dir / 'progress_status.json').write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding='utf-8',
    )

    lines = [
        '# V5 Progress Status',
        '',
        f"- Run id: `{summary['run_id']}`",
        f"- Checked at: `{summary['checked_at']}`",
        f"- Current hands: `{current_hands:,}`",
        f"- Recent hands/sec: `{recent_hps:.1f}`" if recent_hps is not None else '- Recent hands/sec: `unknown`',
    ]
    if latest:
        lines += [
            f"- Iteration: `{latest['iteration']}`",
            f"- Pool size: `{latest['pool_size']}`",
            f"- Entropy: `{latest['entropy']:.4f}`",
            f"- Value loss: `{latest['value_loss']:.1f}`",
        ]
    lines += [
        f"- Checkpoint iteration: `{summary['checkpoint']['iteration']}`",
        f"- Checkpoint hands: `{summary['checkpoint']['total_hands']}`",
        f"- Checkpoint pool snapshots: `{summary['checkpoint']['pool_snapshots']}`",
        '',
        'Upcoming gates:',
        '',
    ]
    for row in gate_rows:
        detail = (
            f"- `{row['name']}` at iteration `{row['target_iteration']}`; "
            f"remaining `{row['remaining_iterations']}` iterations; ETA `{row['eta_duration']}`"
        )
        if row.get('expected_pool_snapshots') is not None:
            detail += f"; expected pool snapshots `{row['expected_pool_snapshots']}`"
        lines.append(detail)
    lines += [
        '',
        'Milestones:',
        '',
    ]
    for row in milestone_rows:
        state = 'done' if row['complete'] else 'pending'
        lines.append(
            f"- {state}: `{row['hands']:,}` hands; remaining `{row['remaining_hands']:,}`; "
            f"ETA `{row['eta_duration']}`"
        )
    lines.append('')
    (run_dir / 'progress_status.md').write_text('\n'.join(lines), encoding='utf-8')

    print(f"hands={current_hands:,}")
    print(f"recent_hps={recent_hps:.1f}" if recent_hps is not None else 'recent_hps=unknown')
    for row in gate_rows:
        print(f"gate {row['name']} iter {row['target_iteration']}: {row['eta_duration']}")
    for row in milestone_rows:
        print(f"milestone {row['hands']:,}: {row['eta_duration']}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
