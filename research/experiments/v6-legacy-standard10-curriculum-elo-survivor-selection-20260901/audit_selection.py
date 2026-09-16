from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import torch


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def state_sha256(state: dict[str, torch.Tensor]) -> str:
    digest = hashlib.sha256()
    for key in sorted(state):
        value = state[key].detach().cpu().contiguous()
        digest.update(key.encode('utf-8'))
        digest.update(str(value.dtype).encode('ascii'))
        digest.update(json.dumps(list(value.shape)).encode('ascii'))
        digest.update(value.numpy().tobytes())
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-final', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()

    source = torch.load(args.source_final, map_location='cpu', weights_only=False)
    archive = torch.load(args.archive, map_location='cpu', weights_only=False)
    ranked = sorted(
        source['pool_snapshots'],
        key=lambda item: (-float(item['selection_score']), int(item['id'])),
    )
    selected = ranked[0]
    assert int(selected['id']) == 2
    assert int(selected['iteration']) == 2
    assert int(selected['hands']) == 8256
    assert int(archive['iteration']) == 2
    assert int(archive['total_hands']) == 8256
    assert archive['model'].keys() == selected['state_dict'].keys()
    assert all(
        torch.equal(archive['model'][key], selected['state_dict'][key])
        for key in archive['model']
    )
    assert all(torch.isfinite(value).all() for value in archive['model'].values())
    archive_state_hash = state_sha256(archive['model'])
    selected_state_hash = state_sha256(selected['state_dict'])
    assert archive_state_hash == selected_state_hash

    output = {
        'schema': 'cardpilot.elo_survivor_selection_audit.v1',
        'status': 'PASS',
        'selection_rule': 'max_terminal_elo_then_min_snapshot_id',
        'terminal_ranking': [
            {
                'rank': rank,
                'snapshot_id': int(item['id']),
                'iteration': int(item['iteration']),
                'hands': int(item['hands']),
                'elo': float(item['selection_score']),
            }
            for rank, item in enumerate(ranked, start=1)
        ],
        'selected_snapshot_id': int(selected['id']),
        'selected_iteration': int(selected['iteration']),
        'selected_hands': int(selected['hands']),
        'selected_elo': float(selected['selection_score']),
        'source_final_sha256': file_sha256(args.source_final),
        'archive_sha256': file_sha256(args.archive),
        'archive_model_state_sha256': archive_state_hash,
        'terminal_snapshot_state_sha256': selected_state_hash,
        'bit_identical': True,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2, sort_keys=True) + '\n')
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
