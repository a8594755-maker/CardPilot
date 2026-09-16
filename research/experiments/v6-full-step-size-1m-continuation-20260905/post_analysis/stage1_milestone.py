"""Independent review of closed stage1 while later fixed-dose work may run.

No GPU workload, new poker hands, live logger write or allocation change. This
does not replace the terminal optimizer/replay/initial-state tensor review.
"""
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import random
import sys
import time

import review as r

ANCHORS = ('standard10', 'cfr4', 'legacy_iter16', 'legacy_mixed65k')


def main():
    base = r.BASE
    output = base / 'post_analysis/stage1_independent_review.json'
    r.require(not output.exists(), 'preserve prior stage1 review')
    report = r.read(base / 'stage1_analysis.json')
    r.require(report['passed'] and report['evaluation_hands'] == 131072, 'stage1 incomplete')
    started = time.monotonic()
    contract_path = base / 'input_contract.json'
    contract = r.read(contract_path)
    hashes = dict(contract['input_sha256'])
    hashes.update({str(path): r.sha(path) for path in
                   (Path(__file__), Path(r.__file__), r.SOURCE, contract_path)})
    decks = set()
    seeds = r.review_stage(base, 1, hashes, decks)
    r.require(len(decks) == 16384, 'wrong unique stage1 deck count')

    # Independently regenerate the registered deck stream, in addition to matching
    # the arms and checking duplicate permutations in review_stage/raw_map.
    rebuilt = 0
    for seed in (1, 3):
        rows = r.raw_map(base / f'eval_seed{seed}_full_stage1/common_deck_pairs.jsonl.gz')
        for index, anchor in enumerate(ANCHORS):
            anchor_seed = 20263900 + seed * 10 + 1 + 1000003 * index
            rng = random.Random(anchor_seed)
            for pair in range(2048):
                deck = list(range(52))
                rng.shuffle(deck)
                r.require(rows[(anchor, anchor_seed, pair)]['deck'] == deck, 'registered deck stream mismatch')
                rebuilt += 1
    r.require(rebuilt == len(decks), 'deck reconstruction incomplete')

    previous_rows = 0
    for name, expected in contract['prior_common_deck_corpus'].items():
        r.require(r.sha(name) == expected, 'prior evidence changed')
        with gzip.open(name, 'rt', encoding='utf-8') as handle:
            for line in handle:
                r.require(tuple(json.loads(line)['deck']) not in decks, 'inventoried prior deck reused')
                previous_rows += 1
        hashes[name] = expected

    training_wall, evaluation_wall, worker_identities = 0., 0., 0
    counts = {key: 0 for key in ('new_physical_hands', 'new_transition_hands',
                                'new_no_decision_hands', 'residual_worker_tail_hands', 'new_replay_rows')}
    for seed, arm in r.ORDERS[1]:
        run = base / f'seed{seed}_{arm}_stage1'
        verification = r.read(run / 'verification.json')
        r.require(verification['passed'] and verification['checkpoint_sha256'] == r.sha(run / 'latest.pt'),
                  'closed training verification changed')
        hashes[str(run / 'latest.pt')] = verification['checkpoint_sha256']
        for key in counts:
            counts[key] += verification[key]
        hashes[str(run / 'verification.json')] = r.sha(run / 'verification.json')
        for kind, job in (('training', run), ('evaluation', base / f'job_eval_seed{seed}_{arm}_stage1')):
            process, terminal = r.read(job / 'process.json'), r.read(job / 'termination.json')
            r.require(terminal['exit_code'] == 0 and not terminal['observer_errors']
                      and not terminal['remaining_observed_child_pids']
                      and not r.live(process['pid'], process['create_time']), 'stage1 job not cleanly terminal')
            for pid, created in terminal['observed_children'].items():
                r.require(not r.live(pid, created), 'recorded stage1 child still live')
                worker_identities += 1
            if kind == 'training':
                training_wall += terminal['wall_seconds']
            else:
                evaluation_wall += terminal['wall_seconds']
            for name in ('process.json', 'termination.json', 'command.json'):
                hashes[str(job / name)] = r.sha(job / name)
    r.require(counts['new_physical_hands'] == counts['new_transition_hands']
              + counts['new_no_decision_hands'] + counts['residual_worker_tail_hands'], 'counter partition mismatch')
    r.require(all(r.sha(name) == expected for name, expected in hashes.items()), 'evidence changed while reviewing')
    result = {
        'passed': True, 'created_at': datetime.now(timezone.utc).isoformat(), 'command': sys.orig_argv,
        'evaluation_hands_in_reviewed_stage': 131072, 'unique_decks_rebuilt': rebuilt,
        'inventoried_prior_raw_rows_checked': previous_rows, 'seeds': seeds,
        'broad_collapse': any(seed['broad_collapse'] for seed in seeds.values()),
        'all_eight_stage1_jobs_terminal': True, 'recorded_child_identities_checked': worker_identities,
        'controller_verified_training_counts': counts,
        'training_subprocess_wall_seconds': training_wall, 'evaluation_subprocess_wall_seconds': evaluation_wall,
        'input_sha256': hashes, 'review_wall_seconds': time.monotonic() - started,
        'new_training_or_evaluation_hands_generated_by_this_review': 0, 'allocation_changed': False,
        'scope': 'Independent closed-stage raw rewards, registered deck reconstruction, inventoried-corpus '
                 'disjointness and process/cost checks. Conditional nominal paired-deck CIs, not seed-population '
                 'or Slumbot evidence. Training counts match controller verification; full optimizer/replay '
                 'and initial-state tensor reinspection remains deferred to terminal review.',
    }
    with output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
    print(json.dumps({key: result[key] for key in ('passed', 'broad_collapse', 'unique_decks_rebuilt',
                     'inventoried_prior_raw_rows_checked', 'controller_verified_training_counts',
                     'training_subprocess_wall_seconds', 'evaluation_subprocess_wall_seconds', 'review_wall_seconds')}))
    print(json.dumps({'paired_seed_results': seeds}))


if __name__ == '__main__':
    main()
