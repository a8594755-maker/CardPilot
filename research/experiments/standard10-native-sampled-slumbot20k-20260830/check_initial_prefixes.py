"""Outcome-blind provisional replay check of the first100 already-completed hands."""
import hashlib
import json
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(ROOT))
from scripts.alpha_holdem.audit_slumbot_session_independence import (
    consecutive_windows, initial_deal_fingerprint, longest_run)


def compare_initial(left, right):
    common = sorted(set(left) & set(right))
    matched = [i for i in common if left[i] == right[i]]
    run = longest_run(matched)
    windows = len(consecutive_windows(left) & consecutive_windows(right))
    return dict(common_indices=len(common), same_index_matches=len(matched),
                longest_same_index_run=run, shared_five_hand_windows=windows,
                gross_replay_detected=run >= 3 or windows > 0)


def main():
    output = BASE/'initial100_deal_prefix_check.json'
    if output.exists():
        raise ValueError('Do not overwrite a fixed-prefix observation')
    manifest = json.loads((BASE/'evidence_manifest.json').read_text())
    sessions, identities = {}, {}
    for spec in manifest['sessions']:
        with Path(spec['raw_hands']).open() as stream:
            for index in range(1, 101):
                row = json.loads(stream.readline())
                if row['successful_hand'] != index or row['attempted_hand'] != index:
                    raise ValueError('First100 successful raw rows are not complete consecutive attempts')
        # A raw reward is written only after its entire decision dump is flushed.
        # Later appends cannot change these first100 complete hand records.
        grouped = {}
        with Path(spec['dump']).open() as stream:
            for line in stream:
                row = json.loads(line)
                if row['hand_idx'] >= 100:
                    break
                grouped.setdefault(row['hand_idx'], []).append(row)
        if set(grouped) != set(range(100)):
            raise ValueError('First100 complete dump hands are unavailable')
        observations = [dict(hand_idx=index, client_pos=grouped[index][0]['client_pos'],
                             hero_hole=sorted(grouped[index][0]['hero_hole'])) for index in range(100)]
        fingerprint = {index: initial_deal_fingerprint(grouped[index]) for index in range(100)}
        identities[spec['id']] = fingerprint
        sessions[spec['id']] = dict(existing_hands=100, dump=spec['dump'],
            canonical_initial_observations=observations,
            canonical_prefix_sha256=hashlib.sha256(json.dumps(observations, sort_keys=True).encode()).hexdigest())
    pairs = []
    names = list(identities)
    for i, left in enumerate(names):
        for right in names[i+1:]:
            pairs.append(dict(left=left, right=right, **compare_initial(identities[left], identities[right])))
    flagged = any(row['gross_replay_detected'] for row in pairs)
    result = dict(status='POSSIBLE_PREFIX_REPLAY' if flagged else 'NO_GROSS_REPLAY_IN_FIRST100',
        sessions=sessions, pairwise=pairs, additional_hands=0, existing_hands_observed=800,
        outcome_statistics_read=False, final_audit=False,
        limitations='Provisional800-hand prefix only; full final strict audit remains mandatory. Not statistical independence proof or strength evidence.')
    output.write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
    print(json.dumps({key: value for key, value in result.items() if key not in ['sessions', 'pairwise']}))


if __name__ == '__main__':
    main()
