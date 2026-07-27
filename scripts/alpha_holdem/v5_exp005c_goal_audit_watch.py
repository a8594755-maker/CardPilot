#!/usr/bin/env python3
"""Continuously refresh the persistent-goal audit; never advances experiments."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from v5_exp005c_goal_audit import audit, markdown


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', default=r'C:\Users\a8594\CardPilot')
    parser.add_argument('--out-json', required=True)
    parser.add_argument('--out-md', required=True)
    parser.add_argument('--status-json', required=True)
    parser.add_argument('--poll-seconds', type=int, default=30)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    repo = Path(args.repo).resolve(); out_json = Path(args.out_json); out_md = Path(args.out_md); status = Path(args.status_json)
    while True:
        payload = audit(repo)
        write(out_json, json.dumps(payload, indent=2, sort_keys=True) + '\n')
        write(out_md, markdown(payload))
        watcher = {
            'checked_at': datetime.now(timezone.utc).isoformat(),
            'overall': 'PASS' if payload['goal_complete'] is True else ('FAIL' if payload['failed_count'] else 'PENDING'),
            'state': payload['overall'], 'pending_count': payload['pending_count'],
            'failed_count': payload['failed_count'], 'goal_complete': payload['goal_complete'],
            'authority': 'REPORTING_ONLY_NO_EXPERIMENT_ADVANCE',
        }
        write(status, json.dumps(watcher, indent=2, sort_keys=True) + '\n')
        if args.once or watcher['overall'] in {'PASS', 'FAIL'}:
            return 0 if watcher['overall'] != 'FAIL' else 1
        time.sleep(max(1, args.poll_seconds))


if __name__ == '__main__':
    raise SystemExit(main())
