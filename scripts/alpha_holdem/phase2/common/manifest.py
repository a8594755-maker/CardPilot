"""Phase 2 manifest + report utilities.

Every Phase 2 artifact (data, model, bench) gets a manifest JSON capturing:
  - git SHA at time of creation
  - config YAML or args
  - seed
  - input dataset hashes / paths
  - output file paths
  - timestamp
  - script name + version

Reports come in two formats: machine-readable JSON + human-readable Markdown.
"""
from __future__ import annotations
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any


def get_git_sha() -> str:
    """Return current git SHA or 'unknown' if not in a git repo."""
    try:
        out = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return 'unknown'


def write_manifest(out_path: str | Path, *, script: str, version: str,
                    args: dict, seed: int | None = None,
                    inputs: list[str | Path] | None = None,
                    outputs: list[str | Path] | None = None,
                    extra: dict[str, Any] | None = None) -> Path:
    """Write a manifest.json next to the primary output.

    args:  the CLI args / config used (will be JSON-serialized; non-serializable
           values are converted to repr)
    inputs:  paths consumed (datasets, ckpts)
    outputs: paths produced
    extra: any script-specific metadata
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'script': script,
        'version': version,
        'git_sha': get_git_sha(),
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'seed': seed,
        'args': _coerce_json(args),
        'inputs': [str(p) for p in (inputs or [])],
        'outputs': [str(p) for p in (outputs or [])],
    }
    if extra:
        payload['extra'] = _coerce_json(extra)
    with out_path.open('w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2)
    return out_path


def _coerce_json(obj):
    """Make any object JSON-serializable by repr-ing non-serializable parts."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (list, tuple)):
        return [_coerce_json(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): _coerce_json(v) for k, v in obj.items()}
    try:
        json.dumps(obj)
        return obj
    except Exception:
        return repr(obj)


def write_md_report(out_path: str | Path, *, title: str, sections: list[tuple[str, str]]) -> Path:
    """Write a human-readable Markdown report.

    sections: list of (heading, body_markdown) tuples.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f'# {title}', '', f'_Generated {time.strftime("%Y-%m-%d %H:%M:%S")}_', '']
    for heading, body in sections:
        lines.extend([f'## {heading}', '', body, ''])
    with out_path.open('w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    return out_path
