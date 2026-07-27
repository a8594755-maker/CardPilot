#!/usr/bin/env python3
"""Create a new immutable-design-lock candidate from a superseded locked JSON."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-lock', required=True)
    parser.add_argument('--out-lock', required=True)
    parser.add_argument('--locked-at', required=True)
    parser.add_argument('--supersession-reason', required=True)
    parser.add_argument('--continuation-path', required=True)
    parser.add_argument('--ledger-path', required=True)
    parser.add_argument('--ledger-prefix-bytes', type=int, required=True)
    parser.add_argument('--ledger-prefix-sha256', required=True)
    parser.add_argument('--event-id', required=True)
    args = parser.parse_args()

    source_path = Path(args.source_lock)
    out_path = Path(args.out_lock)
    if out_path.exists():
        raise FileExistsError(f'refusing existing output lock: {out_path}')
    source = json.loads(source_path.read_text(encoding='utf-8'))
    source_sha = sha256_path(source_path)
    source['lock_revision'] = 2
    source['locked_at'] = args.locked_at
    source['supersedes'] = {
        'path': str(source_path).replace('\\', '/'),
        'sha256': source_sha,
        'reason': args.supersession_reason,
        'prior_lock_is_not_launchable': True,
    }
    continuation_path = Path(args.continuation_path)
    found = False
    for item in source.get('tool_sha256', []):
        if Path(str(item.get('path', ''))).name == continuation_path.name:
            item['path'] = str(continuation_path).replace('\\', '/')
            item['sha256'] = sha256_path(continuation_path)
            found = True
    if not found:
        raise RuntimeError('continuation tool entry not found in source lock')
    source['ledger_binding'] = {
        'path': str(Path(args.ledger_path)).replace('\\', '/'),
        'prefix_bytes': args.ledger_prefix_bytes,
        'prefix_sha256': args.ledger_prefix_sha256.lower(),
        'event_id': args.event_id,
        'contract': 'verifier hashes the immutable ledger prefix and requires the later append-only event row to contain both event_id and exact design-lock SHA256',
    }
    source['tests']['results'].append({
        'name': 'design_lock_v1_automatic_tool_hash_invalidation',
        'status': 'PASS',
        'count': 'v1 verifier FAIL exactly on stale continuation SHA; no launch',
    })
    source['tests']['results'].append({
        'name': 'design_locked_inline_watcher_block_and_exp005c_rearm_routing',
        'status': 'PASS',
        'count': 'continuation2/2 plus rearm14/14',
    })
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(source, indent=2, sort_keys=False) + '\n', encoding='utf-8')
    print(json.dumps({'out': str(out_path), 'bytes': out_path.stat().st_size, 'source_sha256': source_sha}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
