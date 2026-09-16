"""Standalone frozen-policy exact physical-v6 greedy mirrored evaluation."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_holdem.v5_mirror_eval import init_model, read_checkpoint
from alpha_holdem.v6_elo_eval import summarize_models


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--anchor', type=Path, required=True)
    parser.add_argument('--pairs', type=int, required=True)
    parser.add_argument('--seed', type=int, required=True)
    parser.add_argument('--observation-style', choices=('v6', 'legacy_v4'))
    parser.add_argument(
        '--candidate-observation-style', choices=('v6', 'legacy_v4')
    )
    parser.add_argument(
        '--anchor-observation-style', choices=('v6', 'legacy_v4')
    )
    parser.add_argument('--device', choices=('cpu', 'cuda'), default='cpu')
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args()
    if args.pairs < 2:
        parser.error('--pairs must be at least two')
    if args.observation_style is not None:
        if (
            args.candidate_observation_style is not None
            or args.anchor_observation_style is not None
        ):
            parser.error(
                '--observation-style cannot be combined with per-policy styles'
            )
        candidate_observation_style = args.observation_style
        anchor_observation_style = args.observation_style
    else:
        if (
            args.candidate_observation_style is None
            or args.anchor_observation_style is None
        ):
            parser.error(
                'provide --observation-style or both per-policy observation styles'
            )
        candidate_observation_style = args.candidate_observation_style
        anchor_observation_style = args.anchor_observation_style
    if args.out_dir.exists():
        raise FileExistsError(args.out_dir)
    args.out_dir.mkdir(parents=True)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)

    candidate_path = args.candidate.resolve()
    anchor_path = args.anchor.resolve()
    candidate_sha = sha256_path(candidate_path)
    anchor_sha = sha256_path(anchor_path)
    candidate_checkpoint = read_checkpoint(candidate_path)
    anchor_checkpoint = read_checkpoint(anchor_path)
    candidate = init_model(candidate_checkpoint, args.device)
    anchor = init_model(anchor_checkpoint, args.device)
    candidate.eval()
    anchor.eval()
    started = time.time()
    result = summarize_models(
        candidate=candidate,
        anchor=anchor,
        pairs=args.pairs,
        seed=args.seed,
        starting_stack=200.0,
        candidate_observation_style=candidate_observation_style,
        anchor_observation_style=anchor_observation_style,
        device=args.device,
        include_pair_outcomes=True,
    )
    pair_records = result.pop('paired_outcomes')
    pairs_path = args.out_dir / 'pairs.jsonl'
    with pairs_path.open('x', encoding='utf-8', newline='\n') as handle:
        for record in pair_records:
            handle.write(json.dumps(record, sort_keys=True) + '\n')
    if sha256_path(candidate_path) != candidate_sha:
        raise RuntimeError('candidate checkpoint changed during evaluation')
    if sha256_path(anchor_path) != anchor_sha:
        raise RuntimeError('anchor checkpoint changed during evaluation')
    summary = {
        'schema': 'cardpilot.physical_v6_contract_mirror_eval.v1',
        'status': 'COMPLETED',
        'candidate': str(candidate_path),
        'candidate_sha256': candidate_sha,
        'anchor': str(anchor_path),
        'anchor_sha256': anchor_sha,
        'pairs': int(args.pairs),
        'evaluation_hands': int(args.pairs) * 2,
        'seed': int(args.seed),
        'policy_mode': 'greedy',
        'candidate_observation_style': candidate_observation_style,
        'anchor_observation_style': anchor_observation_style,
        **result,
        'pairs_sha256': sha256_path(pairs_path),
        'wall_time_seconds': float(time.time() - started),
        'completed_at': datetime.now(timezone.utc).isoformat(),
        'command': [sys.executable, *sys.argv],
    }
    (args.out_dir / 'summary.json').write_text(
        json.dumps(summary, indent=2, sort_keys=True) + '\n',
        encoding='utf-8',
    )
    print(json.dumps(summary, sort_keys=True))


if __name__ == '__main__':
    main()
