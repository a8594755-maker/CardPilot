"""Read and review completed frozen evidence, then close its existing record."""
import json
from pathlib import Path
import subprocess
import sys

from run_confirmation import (BASE, ROOT, ID, CANDIDATES, analyze, assert_contrasts_match,
    ensure_idle, sha, validate_cell, verify_inputs, verify_sources)


def gate(primary, source):
    return (len(primary) == len(source) == 3 and all(r['ood_valid'] for r in [*primary, *source])
        and min(r['delta_bb100'] for r in primary) > 0
        and max(r['bonferroni_lower'] for r in primary) > 0
        and min(r['delta_bb100'] for r in source) >= 0)


def main():
    ensure_idle()
    result_path, report_path = BASE/'reviewed_analysis.json', BASE/'result_summary.md'
    if result_path.exists() or report_path.exists():
        raise ValueError('Do not overwrite completed review')
    record = json.loads((BASE/'experiment.json').read_text())
    if (record['status'] != 'RUNNING' or record['metrics'].get('replication_complete') != 1
            or record['accounting']['evaluation_hands'] != 147456
            or record['accounting']['new_training_hands'] != 0):
        raise ValueError('Complete RUNNING evaluation required')
    verify_inputs()
    copies = json.loads((BASE/'execution_code/copy_manifest.json').read_text())
    verify_sources(copies)
    stored = json.loads((BASE/'replication_analysis.json').read_text())
    documents, hands = {}, 0
    for label, _, digest in CANDIDATES:
        path = BASE/'matrix'/f'{label}.json'
        if sha(path) != stored['cell_hashes'][label] or stored['candidate_hashes'][label] != digest:
            raise ValueError('Frozen result identity changed')
        doc = json.loads(path.read_text())
        hands += validate_cell(doc, json.loads((BASE/'matrix'/f'{label}_execution.json').read_text()), digest)
        documents[label] = doc
    if hands != 147456: raise ValueError('Wrong actual evidence count')
    result = analyze(documents)
    for key, rows in result['comparisons'].items():
        assert_contrasts_match(rows, stored['comparisons'][key])
    passed = gate(result['comparisons']['weak_vs_control'], result['comparisons']['weak_vs_source'])
    if passed != stored['replication_passed'] or result['decision'] != stored['decision']:
        raise ValueError('Independent decision mismatch')
    result['cell_hashes'] = stored['cell_hashes']
    result['candidate_hashes'] = stored['candidate_hashes']
    result['review_script_sha256'] = sha(__file__)
    result['original_analysis_sha256'] = sha(BASE/'replication_analysis.json')
    verify_inputs()
    verify_sources(copies)
    lines = ['# Weak-source-KL independent confirmation', '', f"Decision: `{result['decision']}`.", '',
        '147,456 new internal hands; zero new training or Slumbot hands. Discovery hands excluded.', '',
        '| Anchor | Weak minus control bb/100 | 95% CI | Bonferroni 98.333% CI |',
        '|---|---:|---|---|']
    for r in result['comparisons']['weak_vs_control']:
        lines.append(f"| {r['anchor']} | {r['delta_bb100']:+.4f} | [{r['ci95_lower']:+.4f}, {r['ci95_upper']:+.4f}] | [{r['bonferroni_lower']:+.4f}, {r['bonferroni_upper']:+.4f}] |")
    lines += ['', 'All raw pair/seat statistics, OOD count checks, frozen input/source hashes and paired contrasts passed post-exit review.', '',
        *['- '+text for text in result['limitations']], '',
        'Next: preregister one fixed20k strict native-sampled Slumbot pilot of exactly this weak checkpoint.' if passed else
        'Next: do not extend, pool or reselect; reassess the general learned-weight mechanism.', '',
        'The100k fresh Slumbot positive-bb/100 and positive95%lower-bound goal remains unachieved.']
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
    report_path.write_text('\n'.join(lines)+'\n', encoding='utf-8')
    subprocess.run([sys.executable, 'research/experiment_log.py', 'update', ID,
        '--command', f'python {Path(__file__).relative_to(ROOT).as_posix()}',
        '--artifact', str(result_path), '--artifact', str(report_path),
        '--metric', 'post_exit_review_pass=1'], cwd=ROOT, check=True)
    contrasts = '; '.join(f"{r['anchor']}:{r['delta_bb100']:+.4f} adjustedCI[{r['bonferroni_lower']:+.4f},{r['bonferroni_upper']:+.4f}]"
                          for r in result['comparisons']['weak_vs_control'])
    subprocess.run([sys.executable, 'research/experiment_log.py', 'finish', ID, '--status', 'COMPLETED',
        '--count', 'new_training_hands=0', '--count', 'evaluation_hands=147456',
        '--summary', f"Independent frozen weak-KL confirmation completed147456internal hands with intact evidence; {result['decision']}.",
        '--conclusion', contrasts+'. No discovery pooling or Slumbot success claim.',
        '--decision', result['decision'], '--next-step',
        'Preregister fixed20k strict sampled Slumbot pilot of this exact weak checkpoint.' if passed else
        'No extension or checkpoint reselection; choose the next general learned-weight mechanism.'], cwd=ROOT, check=True)
    print(json.dumps(dict(decision=result['decision'], evaluation_hands=hands)))


if __name__ == '__main__':
    main()
