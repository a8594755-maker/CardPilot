"""Independent fixed-horizon raw review; never consumes partial outcomes."""
import hashlib
import json
import math
from pathlib import Path
import random
import statistics
import time

BASE = Path(__file__).resolve().parents[1]
ANCHORS = ('standard10', 'cfr4', 'legacy_iter16', 'legacy_mixed65k',
           'mixture_s1', 'mixture_s3', 'heads_s1', 'heads_s3')
CONTRASTS = {'aggregate_minus_final': ('aggregate', 'final'),
             'aggregate_minus_root': ('aggregate', 'root'),
             'final_minus_root': ('final', 'root')}


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def stats(values):
    if len(values) < 2 or not all(math.isfinite(v) for v in values):
        raise ValueError('invalid sample')
    mean = statistics.mean(values) * 100
    se = statistics.stdev(values) * 100 / math.sqrt(len(values))
    return dict(bb100=mean, se_bb100=se, ci95=[mean-1.96*se, mean+1.96*se], paired_decks=len(values))


def validate_row(row, seed, anchor, index, expected_deck):
    if (row['seed'], row['anchor'], row['pair_index']) != (seed, anchor, index):
        raise ValueError('identity mismatch')
    if row['deck'] != expected_deck or len(set(row['deck'])) != 52:
        raise ValueError('deck mismatch')
    if set(row['rewards_bb']) != {'root', 'final', 'aggregate'}:
        raise ValueError('policy set mismatch')
    for rewards in row['rewards_bb'].values():
        if len(rewards) != 2 or not all(type(v) in (int, float) and math.isfinite(v) and abs(v) <= 200 for v in rewards):
            raise ValueError('invalid physical rewards')


def main():
    started = time.monotonic()
    terminal = json.loads((BASE/'terminal.json').read_text())
    assert terminal['status'] == 'FIXED_HORIZON_COMPLETE_REVIEW_REQUIRED'
    assert terminal['evaluation_hands'] == 98304
    contract = json.loads((BASE/'input_contract.json').read_text())
    hashes = dict(contract['source_sha256'])
    for name in ('input_contract.json', 'terminal.json', 'post_analysis/review.py'):
        hashes[str(BASE/name)] = sha(BASE/name)
    for path, digest in hashes.items():
        assert sha(Path(path)) == digest
    seen, results = set(), {}
    for seed in (1, 3):
        contrasts = {label: {} for label in CONTRASTS}
        absolutes = {label: {} for label in ('root', 'final', 'aggregate')}
        for ai, anchor in enumerate(ANCHORS):
            path = BASE/f'seed{seed}_{anchor}.jsonl'
            hashes[str(path)] = sha(path)
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            assert len(rows) == 1024
            rng = random.Random(202609081000 + 100*seed + 1000003*ai)
            for index, row in enumerate(rows):
                deck = list(range(52)); rng.shuffle(deck)
                validate_row(row, seed, anchor, index, deck)
                assert tuple(deck) not in seen
                seen.add(tuple(deck))
            for name, (first, second) in CONTRASTS.items():
                contrasts[name][anchor] = [[row['rewards_bb'][first][seat]-row['rewards_bb'][second][seat] for seat in (0, 1)] for row in rows]
            for name in absolutes:
                absolutes[name][anchor] = [row['rewards_bb'][name] for row in rows]
        def summarize(anchor_values):
            all_pairs = [pair for name in ANCHORS for pair in anchor_values[name]]
            return dict(pooled=stats([statistics.mean(pair) for pair in all_pairs]),
                        by_anchor={name: stats([statistics.mean(pair) for pair in pairs]) for name, pairs in anchor_values.items()},
                        by_panel={name: stats([statistics.mean(pair) for anchor in panel for pair in anchor_values[anchor]]) for name, panel in [('preservation', ANCHORS[:4]), ('transfer', ANCHORS[4:])]},
                        by_seat={str(seat): stats([pair[seat] for pair in all_pairs]) for seat in (0, 1)})
        results[str(seed)] = dict(contrasts={name: summarize(values) for name, values in contrasts.items()}, absolute={name: summarize(values) for name, values in absolutes.items()})
    assert len(seen) == 16384
    # Re-read historical raw evidence independently, not just its preflight flag.
    import gzip
    prior_rows = 0
    for path, digest in contract['prior_corpus'].items():
        assert sha(Path(path)) == digest
        with gzip.open(path, 'rt', encoding='utf-8') as stream:
            for line in stream:
                assert tuple(json.loads(line)['deck']) not in seen
                prior_rows += 1
        assert sha(Path(path)) == digest
    assert prior_rows == contract['prior_rows']
    eligible = True
    for seed in results.values():
        for label in ('aggregate_minus_final', 'aggregate_minus_root'):
            result = seed['contrasts'][label]
            eligible &= result['pooled']['ci95'][0] > 0
            eligible &= all(s['bb100'] > 0 for s in result['by_panel'].values())
            eligible &= all(s['bb100'] > 0 for s in result['by_seat'].values())
            eligible &= all(s['ci95'][1] >= -25 for s in result['by_anchor'].values())
    for path, digest in hashes.items():
        assert sha(Path(path)) == digest
    output = dict(passed=True, evaluation_hands=98304, final_qualification_hands=0,
                  unique_decks=len(seen), prior_rows=prior_rows, overlap=0,
                  external_calibration_eligible=bool(eligible), results=results,
                  costs=terminal['costs'], input_sha256=hashes,
                  evaluation_wall_seconds=terminal['wall_seconds'], review_wall_seconds=time.monotonic()-started,
                  scope='Conditional unadjusted mirrored-deck normal CIs. Internal shared-ancestry panels, not population-seed inference or final Slumbot qualification.')
    with (BASE/'post_terminal_review.json').open('x', encoding='utf-8') as stream:
        json.dump(output, stream, indent=2)
    print(json.dumps(dict(passed=True, external_calibration_eligible=bool(eligible), evaluation_hands=98304)))


if __name__ == '__main__':
    main()
