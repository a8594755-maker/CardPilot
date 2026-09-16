"""Report only complete, immutable confirmation evidence; never finish the record."""
import importlib.util
import json
from pathlib import Path

import psutil

BASE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('confirmation', BASE / 'run_confirmation.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def main():
    own_pid = psutil.Process().pid
    if any(runner.is_other_evaluation_process(p.info, own_pid)
           for p in psutil.process_iter(['pid', 'name', 'cmdline'])):
        raise RuntimeError('Wait for original confirmation writer to terminate')
    record = json.loads((BASE / 'experiment.json').read_text())
    result = json.loads((BASE / 'replication_analysis.json').read_text())
    if (record['metrics'].get('replication_complete') != 1 or result['status'] != 'PASS'
            or record['accounting']['evaluation_hands'] != 98304
            or result['evaluation_hands'] != 98304 or result['new_training_hands'] != 0):
        raise ValueError('Incomplete or inconsistent confirmation')
    output = BASE / 'result_summary.md'
    if output.exists():
        raise RuntimeError('Refusing to overwrite an existing completed report')
    for label, checkpoint, digest in runner.CANDIDATES:
        path = BASE / f'{label}.json'
        doc = json.loads(path.read_text())
        runner.validate_cell(doc, json.loads((BASE / f'{label}_execution.json').read_text()), digest)
        if runner.sha(path) != result['cell_hashes'][label] or runner.sha(checkpoint) != digest:
            raise ValueError('Frozen model or raw evidence changed after completion')
    if runner.classify(result['anchors']) != result['gates']:
        raise ValueError('Stored decision does not match predeclared gate')
    discovery = json.loads((runner.PARENT / 'completed_analysis.json').read_text())
    before = {row['anchor']: row for row in discovery['matrix']['sampled_final']['anchors']}
    passed = result['gates']['nominal_replication_gate']
    decision = 'INDEPENDENT_INTERNAL_REPLICATION_PASSED' if passed else 'INDEPENDENT_INTERNAL_REPLICATION_FAILED'
    lines = ['# Frozen final sampled independent confirmation', '', f'Decision: `{decision}`.', '',
             'New evaluation: **98,304 internal hands**, seed20260894,8192 mirrored pairs per anchor for control and final. '
             '**Zero new training/Slumbot hands.** Parent147456 discovery hands are excluded.', '',
             '| Anchor | Discovery delta (95% CI) | Independent delta (95% CI) | Independent Bonferroni98.333% CI |',
             '|---|---:|---:|---:|']
    for row in result['anchors']:
        d = before[row['anchor']]
        lines.append(f"| {row['anchor']} | {d['delta_bb100']:+.3f} [{d['ci95_lower']:+.3f}, {d['ci95_upper']:+.3f}] "
                     f"| {row['delta_bb100']:+.3f} [{row['ci95_lower']:+.3f}, {row['ci95_upper']:+.3f}] "
                     f"| [{row['bonferroni98p333_lower']:+.3f}, {row['bonferroni98p333_upper']:+.3f}] |")
    lines += ['', 'All numbers are treatment-minus-original-Standard10-control bb/100; CIs use mirrored pairs, not individual seats. '
              'Discovery and independent intervals are shown separately, never pooled.', '',
              f"Nominal registered gate: **{passed}**. Multiplicity-adjusted secondary gate: "
              f"**{result['gates']['multiplicity_adjusted_secondary_gate']}**.",
              'The nominal one-of-three positive-lower-bound gate is not familywise significance. The current result is internal evidence only, not a Slumbot benchmark, exploitability estimate, or proof of general superiority.', '',
              f"Fixed policy SHA256: `{result['candidate_sha256']}`. No checkpoint/mode was changed after discovery admission.",
              'Validation: complete raw arrays, seeds/physical action streams, paired-seat arithmetic, source/model hashes and independently recomputed paired statistics passed. The original evaluation process ended before this report was written.', '',
              '## Next action', '']
    if passed:
        lines += ['Before external sampled-policy assessment, strengthen and test action-independent session-deal replay detection identified in external_readiness_review.md. '
                  'Then separately preregister external validation with immutable files, exact model/mode identity, unique raw-hand accounting and no benchmark-specific rules. '
                  'Do not scale training solely because of this internal gate.']
    else:
        lines += ['Do not promote this checkpoint to a Slumbot test or scale the unchanged training configuration. '
                  'Follow the registered branch: a separately logged fixed-weight, whole-hand-group actor-gradient-noise diagnostic, '
                  'distinguishing PPO noise from regularizer effects before selecting an optimizer-batch treatment. '
                  'Do not retest an alternative discovery checkpoint or merge data to rescue this result.']
    lines += ['', 'The long-term goal remains unachieved: one frozen policy still needs at least100000 fresh Slumbot hands '
              'above0bb/100 with positive95% CI lower bound.']
    output.write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(json.dumps({'decision': decision, 'gates': result['gates']}))


if __name__ == '__main__':
    main()
