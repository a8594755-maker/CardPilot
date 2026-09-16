"""One outcome-blind audit of the first seven completed cells; no gameplay."""
from datetime import datetime, timezone
import json
import random
import shutil
import sys
import psutil
import run_curve as run

BASE,ROOT=run.BASE,run.ROOT


def main():
    if sys.argv[1:] or (BASE/'completed_prefix_review.json').exists(): raise ValueError('No repeat/alternate prefix')
    execution=run.read(BASE/'execution.json')
    assert execution['status']=='RUNNING' and psutil.pid_exists(execution['pid'])
    roles=[(label,a) for label,indices in [('source',range(5)),('mid262',range(2))] for a in indices]
    children={r['role']:r for r in execution['children']}
    for label,a in roles:
        child=children[f'{label}_anchor{a}']
        assert child['exit_code']==0 and not psutil.pid_exists(child['pid'])
    copies=run.read(BASE/'execution_code/copy_manifest.json')
    anchors=run.read(BASE/'anchor_manifest.json')
    selection=run.read(BASE/'checkpoint_selection.json')
    run.verify(copies,anchors)
    for row in selection.values(): assert run.sha(row['path'])==row['sha256']
    directory=BASE/'prefix_review_code'
    directory.mkdir(exist_ok=False)
    relative=run.Path(__file__).resolve().relative_to(ROOT).as_posix()
    run.capture_code_provenance(ROOT,directory,[relative])
    target=directory/'source_files'/relative
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(ROOT/relative,target)
    run.write(directory/'copy_manifest.json',[dict(original=relative,copy=target.relative_to(ROOT).as_posix(),sha256=run.sha(target))])
    expected,rng=[],random.Random(20261001)
    for _ in range(8192):
        deck=list(range(52))
        rng.shuffle(deck)
        expected.append(deck)
    inspected=[]
    for label,a in roles:
        cell=BASE/'matrix'/f'{label}_anchor{a}'
        summary=run.read(cell/'summary.json')
        raw_sha=run.sha(cell/'pairs.jsonl')
        assert summary['status']=='COMPLETED' and summary['seed']==20261001 and summary['evaluation_hands']==16384
        assert summary['candidate_sha256']==selection[label]['sha256'] and summary['anchor_sha256']==anchors[a]['sha256']
        assert summary['pairs_sha256']==raw_sha
        raw=(cell/'pairs.jsonl').read_bytes()
        assert raw.endswith(b'\n')
        rows=[json.loads(line) for line in raw.splitlines()]
        assert [r['pair_index'] for r in rows]==list(range(8192))
        assert [r['deck'] for r in rows]==expected
        assert run.sha(cell/'pairs.jsonl')==raw_sha
        inspected.append(dict(cell=cell.name,existing_hands=16384,pairs_sha256=raw_sha,summary_sha256=run.sha(cell/'summary.json')))
    run.verify(copies,anchors)
    report=dict(status='PASS',reviewed_at=datetime.now(timezone.utc).isoformat(),cells=inspected,
                reviewed_existing_hands=114688,regenerated_unique_decks=8192,source_pairs_verified=len(copies),
                new_training_hands=0,new_evaluation_hands=0,new_model_queries=0,outcome_statistics_computed=False,
                limitation='Closed-prefix identity and deal-sequence check only; full final review still mandatory.')
    run.write(BASE/'completed_prefix_review.json',report)
    run.log('--command',f'python research/experiments/{BASE.name}/inspect_completed_prefix.py',
            '--artifact',BASE/'completed_prefix_review.json',
            *[v for name in ['source_manifest.json','code.patch','copy_manifest.json'] for v in ['--artifact',directory/name]],
            '--note','Outcome-blind first7closed-cell prefix audit PASS:114688existing internal hands have exact regenerated decks/indices and immutable checkpoint/raw hashes;76source pairs unchanged. No extra hands/model queries or score calculation. Full final review remains required.')
    print(json.dumps(report))


if __name__=='__main__': main()
