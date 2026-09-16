"""Durable, token-redacted protocol evidence; contains no poker strategy."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path

JOURNAL_VERSION = 'slumbot_v6_request_journal_v1'
PUBLIC_KEYS = ('action', 'old_action', 'client_pos', 'hole_cards', 'board',
               'bot_hole_cards', 'winnings', 'session_num_hands', 'session_total')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False).encode('utf-8')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def token_hash(token):
    if token is None: return None
    if not isinstance(token, str) or not token:
        raise ValueError('Invalid session token')
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def public_response(response, secrets=()):
    """Preserve selected game fields; omit unknown fields and exception text.

    Invalid nonfinite JSON numbers get an explicit typed marker, never coercion
    into a usable reward. Known token strings are redacted even inside game fields.
    """
    def safe(value):
        if isinstance(value, str):
            for secret in secrets:
                if isinstance(secret, str) and secret: value = value.replace(secret, '[REDACTED_TOKEN]')
            return value
        if isinstance(value, float) and not math.isfinite(value):
            return {'invalid_nonfinite':str(value)}
        if value is None or type(value) in (bool, int, float): return value
        if isinstance(value, (list, tuple)): return [safe(v) for v in value]
        if isinstance(value, dict): return {safe(str(k)):safe(v) for k, v in value.items()}
        return {'invalid_type':type(value).__name__}
    if not isinstance(response, dict): return {'invalid_response_type':type(response).__name__}
    result = {k:safe(response[k]) for k in PUBLIC_KEYS if k in response}
    if 'error_msg' in response: result['error_msg'] = '[SERVER_ERROR_REDACTED]'
    return result


def append_line(handle, value):
    data = canonical(value)+b'\n'
    if handle.write(data) != len(data): raise OSError('Partial evidence write')
    handle.flush()
    os.fsync(handle.fileno())


class Journal:
    def __init__(self, path):
        self.handle = Path(path).open('xb', buffering=0)
        self.sequence, self.last_hash = 0, '0'*64

    def append(self, event, **fields):
        if set(fields) & {'event', 'sequence', 'previous_sha256', 'event_sha256', 'timestamp'}:
            raise ValueError('Reserved journal fields')
        row = dict(event=event, sequence=self.sequence+1, previous_sha256=self.last_hash,
                   timestamp=datetime.now(timezone.utc).isoformat(), **fields)
        row['event_sha256'] = digest(row)
        append_line(self.handle, row)
        self.sequence, self.last_hash = row['sequence'], row['event_sha256']
        return row

    def close(self): self.handle.close()
