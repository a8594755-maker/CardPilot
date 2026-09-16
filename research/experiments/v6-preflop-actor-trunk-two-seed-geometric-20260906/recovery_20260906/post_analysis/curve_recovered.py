"""Terminal-only recovered learning curves using the unchanged qualified math."""
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys

import recovery_chain as chain

BASE, HERE = chain.BASE, chain.HERE
read, require, sha = chain.read, chain.require, chain.sha
SOURCE = BASE / 'post_analysis/curve_comparison.py'
sys.path.insert(0, str(BASE / 'post_analysis'))
spec = importlib.util.spec_from_file_location('qualified_actor_curve', SOURCE)
qualified_curve = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qualified_curve)
summarize = qualified_curve.summarize


def main(base=BASE):
    guard = chain.terminal_guard(base)
    require(guard['stage_count'] == 2, 'two completed stages required; no curve after stage1 safety stop')
    recovery = base / 'recovery_20260906'
    output = recovery / 'post_analysis/curve_comparison.json'
    require(not output.exists(), 'preserve prior curve')
    qualification = read(recovery / 'post_analysis/qualification.json')
    require(qualification['passed'], 'curve qualification incomplete')
    path = recovery / 'post_terminal_review.json'
    digest, report = sha(path), read(path)
    require(report['statistical_not_bitwise_worker_continuation'] is True and
            report['unknown_additional_worker_tail_hands'] is None and
            report['interrupted_prefix']['checkpoint_sha256'] == chain.PARTIAL_SHA,
            'missing recovered-chain interpretation')
    results = summarize(report)
    hashes = chain.merge_hashes(qualification['input_sha256'],
        {str(path): digest, str(recovery / 'post_analysis/qualification.json'): sha(recovery / 'post_analysis/qualification.json')})
    for name, expected in report['input_sha256'].items():
        if name.endswith(('common_deck_pairs.jsonl.gz', 'summary.json', 'stage1_analysis.json', 'stage2_analysis.json')):
            hashes = chain.merge_hashes(hashes, {name: expected})
    require(all(sha(p) == h for p, h in hashes.items()), 'review/source/evaluation changed')
    result = {'passed': True, 'created_at': datetime.now(timezone.utc).isoformat(), 'command': sys.orig_argv,
        'seeds': results, 'input_sha256': hashes, 'new_training_or_evaluation_hands': 0,
        'scope': 'Exploratory nominal conditional stage2-minus-stage1 differences on disjoint internal decks. '
                 'The connected Seed1 stage1 is a verified two-attempt statistical continuation; its unknown '
                 'in-flight tail and interrupted runtime are not erased. Not training-seed population inference, '
                 'causal attribution, Slumbot strength, multiplicity-adjusted confirmation or linear forecasting.',
        'statistical_not_bitwise_worker_continuation': True, 'unknown_additional_worker_tail_hands': None,
        'automatic_promotion_or_qualification': False}
    with output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
    print(json.dumps({'passed': True, 'seeds': results}, indent=2))


if __name__ == '__main__':
    main()
