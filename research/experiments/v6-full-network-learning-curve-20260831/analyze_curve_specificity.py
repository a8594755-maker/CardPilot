"""Post-hoc paired curve diagnosis, never a replacement admission gate."""
import json
from pathlib import Path
import shutil
import statistics
import subprocess
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(BASE))
from research.experiment_log import capture_code_provenance, sha256_file
from review_completed_curve import interval, verify_rows


def main():
    if sys.argv[1:] or (BASE/'curve_specificity_analysis.json').exists():
        raise ValueError('Preserve fixed completed diagnosis')
    review = json.loads((BASE/'reviewed_analysis.json').read_text())
    assert review['status'] == 'PASS' and review['decision'] == 'FINAL_BREADTH_GATE_NOT_PASSED'
    data = {}
    decks = None
    for label in ['mid65', 'final']:
        for anchor in range(5):
            directory = BASE/'matrix'/f'{label}_anchor{anchor}'
            summary = json.loads((directory/'summary.json').read_text())
            assert summary['pairs_sha256'] == sha256_file(directory/'pairs.jsonl')
            rows = [json.loads(line) for line in (directory/'pairs.jsonl').read_text().splitlines()]
            data[label, anchor] = verify_rows(rows, 2048)
            current_decks = [row['deck'] for row in rows]
            if decks is None: decks = current_decks
            assert decks == current_decks
    differences = {anchor: [b-a for a, b in zip(data['mid65', anchor], data['final', anchor])]
                   for anchor in range(5)}
    training = [statistics.mean(differences[a][i] for a in range(3)) for i in range(2048)]
    heldout = [statistics.mean(differences[a][i] for a in [3, 4]) for i in range(2048)]
    interaction = [a-b for a, b in zip(training, heldout)]
    report = dict(posthoc_descriptive=True, admission_gate_unchanged=True,
                  original_decision=review['decision'], additional_training_hands=0,
                  additional_evaluation_hands=0, reviewed_analysis_sha256=sha256_file(BASE/'reviewed_analysis.json'),
                  comparison='final minus first scheduled archive above65536actual hands (81634)',
                  pair_count=2048, per_anchor=[dict(anchor=a, **interval(differences[a])) for a in range(5)],
                  training_anchor_mean_change=interval(training), heldout_anchor_mean_change=interval(heldout),
                  training_minus_heldout_change=interval(interaction),
                  limitations='Post-hoc normal95%intervals without multiplicity correction; anchors and midpoint were already observed. '
                  'Aggregate uncertainty uses each common-deal pair as one unit,not independent anchor cells. '
                  'Suggests a mechanism to test,does not prove causal overfitting or admit any checkpoint.')
    (BASE/'curve_specificity_analysis.json').write_text(json.dumps(report, indent=2)+'\n')
    lines = ['# Post-hoc curve specificity diagnosis', '', report['limitations'], '',
             '| Final minus81,634-hand archive |bb/100 change|Descriptive95%CI|', '|---|---:|---|']
    for name, key in [('Training-anchor average', 'training_anchor_mean_change'),
                      ('Heldout-anchor average', 'heldout_anchor_mean_change'),
                      ('Training minus heldout interaction', 'training_minus_heldout_change')]:
        row = report[key]
        lines.append(f'|{name}|{row["bb_per_100"]:+.4f}|[{row["ci"][0]:+.4f},{row["ci"][1]:+.4f}]|')
    lines += ['', 'The original final gate remains failed. No midpoint promotion,extra testing of a selected old checkpoint, '
              'or budget extension is authorized by this descriptive analysis. Test any proposed learning change in a separate registered experiment.']
    (BASE/'curve_specificity.md').write_text('\n'.join(lines)+'\n')
    directory = BASE/'specificity_code'
    directory.mkdir(exist_ok=False)
    paths = [(BASE/name).relative_to(ROOT).as_posix() for name in ['analyze_curve_specificity.py', 'review_completed_curve.py']]
    capture_code_provenance(ROOT, directory, paths)
    copies = []
    for path in paths:
        target = directory/'source_files'/path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT/path, target)
        copies.append(dict(original=path, copy=target.relative_to(ROOT).as_posix(), sha256=sha256_file(target)))
    (directory/'copy_manifest.json').write_text(json.dumps(copies, indent=2)+'\n')
    artifacts = [BASE/'curve_specificity_analysis.json', BASE/'curve_specificity.md',
                 directory/'source_manifest.json', directory/'code.patch', directory/'copy_manifest.json']
    subprocess.run([sys.executable, str(ROOT/'research/experiment_log.py'), 'update', BASE.name,
                    '--command', 'python research/experiments/v6-full-network-learning-curve-20260831/analyze_curve_specificity.py',
                    *[v for p in artifacts for v in ['--artifact', str(p)]],
                    '--note', 'Post-hoc paired late-versus-early curve specificity diagnosis added with0new hands; common-deal units preserve cross-anchor covariance. Descriptive only; original final gate failure and no-midpoint-rescue decision unchanged.'], cwd=ROOT, check=True)
    print(json.dumps(report))


if __name__ == '__main__': main()
