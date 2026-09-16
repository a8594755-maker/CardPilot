"""Independent terminal-only deployment evidence review; no new model queries."""
import json
import math
from pathlib import Path
import random
import subprocess
import sys

import numpy as np
import psutil
import run_readiness as run


def main():
    if sys.argv[1:] or (run.BASE/'reviewed_analysis.json').exists():
        raise ValueError('No repeated review')
    execution=run.read(run.BASE/'execution.json')
    assert execution['status']=='COMPLETED_PENDING_REVIEW'
    try:
        assert abs(psutil.Process(execution['pid']).create_time()-execution['create_time'])>.001
    except psutil.NoSuchProcess:
        pass
    inputs=run.read(run.BASE/'input_manifest.json')
    run.verify(run.read(run.BASE/'execution_code/copy_manifest.json'),inputs)
    record=run.read(run.BASE/'experiment.json')
    assert record['status']=='RUNNING'
    def recorded(path):
        entry=next(v for p,v in record['artifact_integrity'].items() if Path(p).resolve()==path.resolve())
        assert run.sha(path)==entry['sha256']
    for name in ('execution.json','parity.jsonl','parity_analysis.json','completed_analysis.json'):
        recorded(run.BASE/name)
    parity=run.read(run.BASE/'parity_analysis.json')
    assert parity['status']=='PASS' and parity['model_sha256']==run.MODEL_SHA
    assert parity['states_checked']==4202 and parity['model_queries']==8404
    assert parity['replayed_validation_trajectories']==512
    assert parity['new_unique_hands']==parity['network_connection_attempts']==0
    assert run.sha(run.BASE/'parity.jsonl')==parity['parity_sha256']
    assert set(parity['strata'])=={f'street{s}_seat{p}' for s in range(4) for p in range(2)}
    assert sum(parity['strata'].values())==4202 and all(v>0 for v in parity['strata'].values())
    for path,digest in parity['runtime_sha256'].items():
        assert run.sha(path)==digest
    sys.path.insert(0,str(run.RUNTIME))
    from alpha_holdem.policy_contract_v6 import from_external,observation
    states=[json.loads(line) for line in (run.CORPUS/'states.jsonl').read_text().splitlines()]
    rng=random.Random(2026102101)
    count=0
    with (run.BASE/'parity.jsonl').open() as handle:
        for index,line in enumerate(handle):
            assert line.endswith('\n')
            row=json.loads(line)
            corpus=states[index]
            assert row['state_index']==corpus['state_index']==index
            assert row['hand_index']==corpus['hand_index'] and row['decision_index']==corpus['decision_index']
            assert row['uniform']==rng.random()
            assert row['observation_equal'] and row['action_table_equal'] and row['decision_equal']
            state=from_external(corpus['action'],corpus['hole_cards'],corpus['board'],corpus['seat'])
            obs,table=observation(state)
            info=row['decision']
            probs=np.asarray(info['behavior_probs'],dtype=np.float64)
            assert probs.shape==(9,) and np.isfinite(probs).all() and (probs>=0).all()
            assert math.isclose(math.fsum(probs.tolist()),1.,abs_tol=1e-12,rel_tol=0)
            assert np.all(probs[np.asarray(obs['legal_mask'])==0]==0)
            selected=info['selected_action_slot']
            assert type(selected) is int and selected in range(9) and table[selected] is not None
            assert info['direct_increment']==table[selected]
            assert info['behavior_action_probability']==probs[selected] and probs[selected]>0
            assert info['policy_mode']=='sample' and info['temperature']==1.
            count+=1
    assert count==4202
    completed=run.read(run.BASE/'completed_analysis.json')
    assert completed['decision']=='ADMIT_SEPARATE_FRESH20K' and completed['candidate_sha256']==run.MODEL_SHA
    assert completed['new_training_hands']==completed['evaluation_hands']==completed['slumbot_hands']==0
    run.verify(run.read(run.BASE/'execution_code/copy_manifest.json'),inputs)
    report=dict(status='PASS',decision='ADMIT_SEPARATE_FRESH20K',candidate_sha256=run.MODEL_SHA,
        fixed_epoch=8,states_checked=4202,parity_model_queries=8404,additional_review_model_queries=0,
        replayed_validation_trajectories=512,network_connection_attempts=0,
        new_training_hands=0,evaluation_hands=0,slumbot_hands=0,qualification_hands=0,goal_achieved=False,
        internal_return_used_for_admission=False,parity_analysis_sha256=run.sha(run.BASE/'parity_analysis.json'),
        wall_time_seconds=execution['wall_time_seconds'])
    run.write(run.BASE/'reviewed_analysis.json',report)
    (run.BASE/'result_summary.md').write_text(
        '# Fixed phase2 average deployment parity\n\n4202preserved states/8404model queries passed native/public parity. '
        'Zero new hands, network requests or strength measurements.\n\nOnly fixed epoch08 '+run.MODEL_SHA+
        ' is admitted to a separately preregistered fresh20k Slumbot pilot. No100k qualification or winning claim.\n')
    run.log('--command',f'python research/experiments/{run.BASE.name}/review_finish.py',
        '--artifact',run.BASE/'reviewed_analysis.json','--artifact',run.BASE/'result_summary.md')
    subprocess.run([sys.executable,str(run.ROOT/'research/experiment_log.py'),'finish',run.BASE.name,
        '--status','COMPLETED','--summary','Fixed phase2 average epoch08 passed4202state deployment parity; zero new hands/network.',
        '--conclusion','Technical deployment equivalence, not poker strength or external transfer. Exact epoch08 only.',
        '--decision','ADMIT_SEPARATE_FRESH20K','--next-step','Run separately preregistered8fresh2500hand Slumbot sessions of this exact hash.',
        '--count','new_training_hands=0','--count','evaluation_hands=0','--count','slumbot_hands=0',
        '--count','parity_model_queries=8404'],cwd=run.ROOT,check=True)
    print(json.dumps(report))


if __name__=='__main__': main()
