"""Outcome-blind integrity review of terminal cells; no aggregate win scores."""
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import random
import shutil
import subprocess
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'scripts'))
from research.experiment_log import capture_code_provenance, sha256_file
from alpha_holdem.policy_contract_v6 import METADATA


def main():
    if sys.argv[1:]: raise ValueError('No alternate selection or seed')
    import psutil
    execution = json.loads((BASE/'execution.json').read_text())
    children = [r for r in execution['children'] if r['role'] != 'trainer' and r['exit_code'] == 0]
    if not children: raise ValueError('No completed evaluation cells')
    output = BASE/f'completed_cell_review_{len(children):03d}.json'
    if output.exists(): raise ValueError('Preserve prior completed-cell review')
    code = BASE/'completed_cell_review_code'
    relative = Path(__file__).resolve().relative_to(ROOT).as_posix()
    if not code.exists():
        code.mkdir()
        capture_code_provenance(ROOT, code, [relative])
        target = code/'source_files'/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT/relative, target)
        (code/'copy_manifest.json').write_text(json.dumps([dict(original=relative,
            copy=target.relative_to(ROOT).as_posix(), sha256=sha256_file(target))], indent=2)+'\n')
    helper_copies = json.loads((code/'copy_manifest.json').read_text())
    copies = json.loads((BASE/'execution_code/copy_manifest.json').read_text())
    for item in helper_copies+copies:
        assert all(sha256_file(ROOT/item[k]) == item['sha256'] for k in ['original', 'copy'])
    candidates = json.loads((BASE/'candidate_manifest.json').read_text())
    anchors = json.loads((BASE/'anchor_manifest.json').read_text())
    for item in list(candidates.values())+anchors: assert sha256_file(Path(item['path'])) == item['sha256']
    rng, decks = random.Random(20260921), []
    for index in range(8192):
        deck = list(range(52))
        rng.shuffle(deck)
        decks.append(deck)
    assert len({tuple(d) for d in decks}) == 8192
    cells = []
    for child in children:
        assert not psutil.pid_exists(child['pid']), 'Original completed evaluator must be terminal'
        label, anchor_text = child['role'].rsplit('_anchor', 1)
        anchor = int(anchor_text)
        directory = BASE/'matrix'/child['role']
        summary = json.loads((directory/'summary.json').read_text())
        assert summary['status'] == 'COMPLETED' and summary['seed'] == 20260921
        assert summary['pairs'] == 8192 and summary['evaluation_hands'] == 16384
        assert all(summary[k] == v for k, v in METADATA.items())
        assert summary['candidate_sha256'] == candidates[label]['sha256']
        assert summary['anchor_sha256'] == anchors[anchor]['sha256']
        path = directory/'pairs.jsonl'
        digest = sha256_file(path)
        assert digest == summary['pairs_sha256']
        data = path.read_bytes()
        assert data.endswith(b'\n')
        rows = [json.loads(line) for line in data.splitlines()]
        assert len(rows) == 8192
        for index, row in enumerate(rows):
            assert set(row) == {'pair_index', 'deck', 'rewards_bb', 'decisions'}
            assert type(row['pair_index']) is int and row['pair_index'] == index and row['deck'] == decks[index]
            assert len(row['rewards_bb']) == 2 and all(type(v) in (int, float) and math.isfinite(v) and abs(v) <= 200 and
                   abs(v*100-round(v*100)) < 1e-8 for v in row['rewards_bb'])
            assert len(row['decisions']) == 2 and all(type(v) is int and v > 0 for v in row['decisions'])
        assert sha256_file(path) == digest
        cells.append(dict(role=child['role'], original_pid=child['pid'], exit_code=0, pairs=8192,
                          raw_sha256=digest, summary_sha256=sha256_file(directory/'summary.json')))
    report = dict(status='PASS', completed_cells=len(cells), verified_physical_evaluation_hands=len(cells)*16384,
                  unique_common_decks=8192, deck_seed=20260921, source_pairs_verified=len(copies),
                  aggregate_scores_read=False, gate_assessed=False, additional_training_hands=0,
                  additional_evaluation_hands=0, cells=cells, reviewed_at=datetime.now(timezone.utc).isoformat())
    output.write_text(json.dumps(report, indent=2)+'\n')
    subprocess.run([sys.executable, str(ROOT/'research/experiment_log.py'), 'update', BASE.name,
        '--command', 'python research/experiments/v6-source-kl-retention-pilot-20260831/inspect_completed_cells.py',
        *[v for p in [output, code/'source_manifest.json', code/'code.patch', code/'copy_manifest.json'] for v in ['--artifact', str(p)]],
        '--note', f'Outcome-blind raw integrity review passed for{len(cells)}terminal cells:exact8192-pair seeded deck prefix,complete rows,chip bounds,identities and clean original child exits. No score/gate assessment,extra hands or retry.'], cwd=ROOT, check=True)
    print(json.dumps({k:v for k, v in report.items() if k != 'cells'}))


if __name__ == '__main__': main()
