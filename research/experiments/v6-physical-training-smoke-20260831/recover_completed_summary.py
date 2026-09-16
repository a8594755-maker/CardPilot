"""Recover summary only after wrapper postprocessing failed; never play/train."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import torch

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
sys.path.insert(0,str(ROOT))
from research.experiment_log import sha256_file


def main():
    if sys.argv[1:] or (BASE/'completed_analysis.json').exists():
        raise ValueError('No overwrite or alternate run')
    checkpoint=torch.load(BASE/'production/latest.pt',map_location='cpu',weights_only=False)
    manifest=json.loads((BASE/'production/run_manifest.json').read_text())
    audit=json.loads((BASE/'session_audit.json').read_text())
    assert manifest['status']=='finished' and audit['status']=='PASS'
    count=checkpoint['environment_hand_accounting']['completed_hands']
    assert count==11261 and checkpoint['iteration']==2
    for item in json.loads((BASE/'rebound_manifest.json').read_text()):
        assert sha256_file(Path(item['path']))==item['sha256']
    cells=[]
    for label in ['source','final']:
        for index in range(3):
            directory=BASE/'matrix'/f'{label}_anchor{index}'
            result=json.loads((directory/'summary.json').read_text())
            assert result['status']=='COMPLETED' and result['evaluation_hands']==128
            assert sha256_file(directory/'pairs.jsonl')==result['pairs_sha256']
            cells.append(dict(candidate=label,anchor=index,**result))
    for item in json.loads((BASE/'execution_code/copy_manifest.json').read_text()):
        for key in ['original','copy']: assert sha256_file(ROOT/item[key])==item['sha256']
    summary=dict(status='COMPLETED_PENDING_REVIEW',new_training_hands=count,physical_overshoot=count-8192,
        evaluation_hands=768,slumbot_hands=0,iteration=checkpoint['iteration'],changed_tensors=86,
        finite_optimizer_states=len(checkpoint['optimizer']['state']),final_sha256=sha256_file(BASE/'frozen/final.pt'),
        cells=cells,completed_at=datetime.now(timezone.utc).isoformat(),
        scope='Pipeline smoke, not a strength admission gate',postprocessing_recovery=dict(
            original_wrapper_exit_code=1,failed_operation='sha256_file received str from rebound manifest instead of Path',
            training_exit_code=0,all_six_evaluation_cells_completed=True,
            additional_training_hands=0,additional_evaluation_hands=0,
            original_wrapper_source_preserved=True))
    (BASE/'completed_analysis.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary['postprocessing_recovery']))


if __name__=='__main__': main()
