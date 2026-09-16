"""Post-exit independent review and same-record closure, never launches games."""
import json
from pathlib import Path
import subprocess
import sys

from report_completed_pilot import ensure_writer_finished
from run_pilot import BASE, ROOT, sha, capture_code_provenance, log


def main():
    ensure_writer_finished()
    record = json.loads((BASE/'experiment.json').read_text())
    if record['status'] != 'RUNNING':
        raise RuntimeError('Do not reopen or refinish terminal experiment')
    if (BASE/'completed_analysis.json').exists() or (BASE/'postprocessing_code').exists():
        raise RuntimeError('Existing review/snapshot requires inspection; never overwrite or automatically retry')
    command = ['python', (BASE/'report_completed_pilot.py').relative_to(ROOT).as_posix()]
    files = [(BASE/name).relative_to(ROOT).as_posix() for name in [
        'report_completed_pilot.py','test_completed_report.py','finish_review.py']]
    snapshot = BASE/'postprocessing_code'
    capture_code_provenance(ROOT,snapshot,files)
    log('--command',subprocess.list2cmdline(command),
        '--command',f'python {Path(__file__).relative_to(ROOT).as_posix()}',
        *[item for path in [*map(lambda relative:ROOT/relative,files),
            snapshot/'source_manifest.json',snapshot/'code.patch'] for item in ['--artifact',str(path)]],
        '--note','Original training/evaluation wrapper is terminal. Capture independent postprocessing source, then review without changing raw evidence; no additional poker hands.')
    subprocess.run([sys.executable,*command[1:]],cwd=ROOT,check=True)
    result = json.loads((BASE/'completed_analysis.json').read_text())
    if (result['status']!='PASS' or result['evaluation_hands']!=163840 or result['slumbot_hands']!=0
            or result['review_script_sha256']!=sha(BASE/'report_completed_pilot.py')):
        raise ValueError('Incomplete or changed independent review')
    fields=['--metric','independent_review_pass=1']
    for arm,row in result['arms'].items():
        for key,value in dict(adam_steps=row['batch_accounting']['total_steps'],
            unchanged_representation_tensors=row['unchanged_representation_tensors'],
            optimizer_state_tensors=row['optimizer_state_tensors'],
            max_reference_kl=row['max_reference_kl'],max_clip_fraction=row['max_clip_fraction']).items():
            fields+=['--metric',f'{arm}_{key}={value}']
    log(*fields,'--artifact',str(BASE/'completed_analysis.json'),'--artifact',str(BASE/'result_summary.md'))
    primary=result['comparisons']['full_final_vs_heads_final']
    contrasts='; '.join(f'{r["anchor"]}:{r["delta_bb100"]:+.4f}bb/100 adjustedCI[{r["bonferroni_lower"]:+.4f},{r["bonferroni_upper"]:+.4f}]' for r in primary)
    admitted=result['admits_independent_confirmation']
    subprocess.run([sys.executable,'research/experiment_log.py','finish',BASE.name,
        '--status','COMPLETED','--count',f'new_training_hands={result["new_training_hands"]}',
        '--count','evaluation_hands=163840','--count','slumbot_hands=0',
        '--summary',f'Matched weak-KL heads/full scopes completed{result["new_training_hands"]}physical training hands and163840frozen internal hands. Independent raw,curve,source,session,scope and Adam reviews passed; {result["decision"]}.',
        '--conclusion',contrasts+'. Only final endpoints determine admission; fixed midpoints descriptive. Fourth opponent excluded from this training run but historically related; no claim of unseen-family or Slumbot strength.',
        '--decision',result['decision'],'--next-step',
        ('Preregister separate independent confirmation of the exact final endpoints; do not pool discovery data or promote directly to Slumbot.' if admitted else
         'Do not extend or select archives to rescue this experiment. Choose the next general learned-weight mechanism from the complete curve and training health.')],cwd=ROOT,check=True)
    print(json.dumps(dict(decision=result['decision'],new_training_hands=result['new_training_hands'],evaluation_hands=163840)))


if __name__=='__main__':
    main()
