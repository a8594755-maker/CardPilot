"""Explicit, fixed-dose local research: random-init 10M -> test -> cumulative 20M.

Default invocation is a read-only plan. No automatic retries or algorithm search.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
STAGES = {'train10m':10_000_000, 'train20m':20_000_000}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    with Path(path).open('x',encoding='utf-8') as f:
        json.dump(value,f,indent=2,allow_nan=False)
        f.flush()
        os.fsync(f.fileno())


def training_command(base, stage, seed=2026090807, workers=12):
    require(stage in STAGES, 'Unknown training stage')
    argv = [sys.executable,'-B','-u',str(base/'runtime/alpha_holdem/train_v5.py'),
        '--device','cuda','--workers',str(workers),'--torch-threads','1',
        '--hands-per-iter','16384','--mini-batch-size','16384',
        '--total-hands','20000000','--total-environment-hands',str(STAGES[stage]),
        '--starting-stack','200','--env-version','v6','--norm-layer','gn',
        '--lr','0.0001','--ppo-epochs','2','--ppo-target-kl','0.01',
        '--gamma','1','--gae-lambda','1','--epsilon','0',
        '--entropy-coef','0.005','--entropy-floor','0.05',
        '--critic-contract','critic_v1','--value-coef','0.5',
        '--ppo-replay-buffer-iterations','0','--ppo-replay-ratio','0',
        '--k-best','8','--pool-strategy','latest','--self-play-fraction','0.25',
        '--opponent-assignment','per-worker','--hero-policy-mode','sample',
        '--hero-policy-temperature','1','--rollout-mode','multi','--rollout-envs-per-worker','8',
        '--inference-batch-deadline-us','700','--worker-seed-base',str((seed*100) % (2**32-1024)),
        '--fixed-training-deal-stream','--managed-deal-attempts',
        '--deal-attempt-registry',str(base/'deal_attempt_registry'),
        '--opponent-assignment-provenance-file',str(base/'training/opponent_assignments.jsonl'),
        '--snapshot-every','32','--save-interval','20','--archive-checkpoint-every','200',
        '--run-id',base.name,'--run-dir',str(base/'training'),'--out',str(base/'training/latest.pt'),
        '--seed',str(seed),'--validate-stream']
    if stage == 'train20m':
        argv += ['--resume',str(base/'training/latest.pt'),'--allow-resume','--no-reset-optimizer',
                 '--resume-assignment-state-from-provenance','--preserve-resumed-optimizer-lr']
    return argv


def log(action, eid, *args):
    subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),action,eid,*args],cwd=ROOT,check=True)


def run_command(argv, folder, env, progress=None):
    folder.mkdir(parents=True,exist_ok=False)
    write(folder/'command.json',dict(argv=argv,exact_command=subprocess.list2cmdline(argv)))
    with (folder/'stdout.log').open('xb') as out, (folder/'stderr.log').open('xb') as err:
        proc = subprocess.Popen(argv,cwd=ROOT,env=env,stdout=out,stderr=err,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        import psutil
        write(folder/'process.json',dict(pid=proc.pid,create_time=psutil.Process(proc.pid).create_time()))
        while True:
            try:
                code = proc.wait(timeout=60)
                break
            except subprocess.TimeoutExpired:
                if progress is not None:
                    progress()
    write(folder/'terminal.json',dict(exit_code=code))
    require(code==0, f'Process failed; preserve evidence and inspect {folder}')


def checkpoint_hands(path):
    import torch
    ckpt = torch.load(path,map_location='cpu',weights_only=False)
    accounting = ckpt['environment_hand_accounting']
    require(accounting['prefix_complete'], 'Unknown physical hand prefix')
    require(ckpt.get('optimizer') and ckpt.get('main_process_rng_state') and ckpt.get('fixed_deal_attempt'),
            'Missing optimizer/RNG/managed-deal checkpoint state')
    return int(accounting['completed_hands']), int(ckpt['total_hands'])


def prepare(base, args):
    base.mkdir(parents=True,exist_ok=False)
    runtime = base/'runtime'
    for package in ('alpha_holdem','deep_cfr'):
        for source in (ROOT/'scripts'/package).rglob('*.py'):
            if '__pycache__' in source.parts:
                continue
            dest = runtime/source.relative_to(ROOT/'scripts')
            dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(source,dest)
    from importlib.metadata import version
    write(base/'contract.json',dict(initialization='random, no pretrained model',seed=args.seed,workers=args.workers,
        physical_targets=STAGES,eval_hands=100000,eval_sessions=40,eval_hands_per_session=2500,
        execution='native v6 200bb, CPU sampled temperature1; no observation bridge',
        stopping='Fixed sample. No efficacy peeking, failed-session replacement or automatic retry.',
        continuation='Cumulative20M only after completed10M evaluation, preserving optimizer and counters. '
                     'New managed deal namespace prevents prefix reuse; not bitwise in-flight worker continuation.',
        python=sys.version,packages={n:version(n) for n in ('torch','numpy','scipy','requests')},
        hashes={str(p):sha(p) for p in runtime.rglob('*.py')}))


def check_contract(base,args):
    contract=read(base/'contract.json')
    require(contract['seed']==args.seed and contract['workers']==args.workers,'Configuration changed')
    require(contract['python']==sys.version,'Python changed')
    from importlib.metadata import version
    require(all(version(n)==v for n,v in contract['packages'].items()),'Packages changed')
    require(all(sha(path)==digest for path,digest in contract['hashes'].items()),'Frozen source changed')
    return contract


def train(base,args,env):
    stage=args.stage
    require(not (base/stage).exists(),'Stage already attempted; inspect evidence, never blindly restart')
    if stage=='train10m':
        require(not (base/'training').exists(),'Fresh training requires an unused training directory')
    else:
        evaluation=read(base/'test10m/result.json')
        require(evaluation['evidence_passed'] and evaluation['hands']==100000,'Complete10M test first')
        end=read(base/'train10m/result.json')
        require(sha(base/'training/latest.pt')==end['checkpoint_sha256']==evaluation['model_sha256'],
                '10M resume checkpoint changed')
        physical,_=checkpoint_hands(base/'training/latest.pt')
        require(10_000_000<=physical<20_000_000,'Invalid continuation hand counter')
    prior_hands = 0 if stage=='train10m' else physical
    def progress():
        path=base/'training/h1_training_metrics.jsonl'
        if not path.exists():
            return
        with path.open('rb') as f:
            f.seek(max(0,path.stat().st_size-1048576))
            lines=f.read().splitlines(keepends=True)
        for line in reversed(lines):
            if not line.endswith(b'\n'):
                continue
            try:
                row=json.loads(line)
                hands=int(row['environment_hand_accounting']['completed_hands'])
            except (ValueError,KeyError):
                continue
            log('update',base.name+'-'+stage,'--count',f'new_training_hands={max(0,hands-prior_hands)}',
                '--count',f'lineage_training_hands={hands}')
            print(f'{stage}: {hands:,} actual environment hands',flush=True)
            break
    run_command(training_command(base,stage,args.seed,args.workers),base/stage,env,progress)
    physical,transition=checkpoint_hands(base/'training/latest.pt')
    require(physical>=STAGES[stage],'Target not reached; do not claim completed stage')
    frozen=base/stage/'frozen.pt'
    shutil.copy2(base/'training/latest.pt',frozen)
    # Preserve the first boundary's metadata before same-lineage continuation
    # updates latest/manifest or appends more training metrics and assignments.
    evidence=base/stage/'training_evidence'
    evidence.mkdir(exist_ok=False)
    for source in (base/'training').iterdir():
        if source.is_file() and source.suffix in ('.json','.jsonl','.log'):
            shutil.copy2(source,evidence/source.name)
    write(base/stage/'result.json',dict(physical_hands=physical,transition_hands=transition,
        checkpoint_sha256=sha(frozen),target=STAGES[stage],
        overshoot_hands=physical-STAGES[stage],new_training_origin=0,
        evidence_hashes={str(f):sha(f) for f in evidence.iterdir()}))
    log('update',base.name+'-'+stage,'--count',f'new_training_hands={physical-prior_hands}',
        '--count',f'lineage_training_hands={physical}')
    print(f'{stage} complete: {physical:,} actual hands. Frozen checkpoint: {frozen}')


def evaluate(base,args,env):
    from scipy.stats import t
    endpoint=read(base/'train10m/result.json')
    model=base/'train10m/frozen.pt'
    model_hash=sha(model)
    require(endpoint['physical_hands']>=10_000_000 and model_hash==endpoint['checkpoint_sha256'], 'Invalid10M endpoint')
    out=base/'test10m'
    out.mkdir(exist_ok=False)
    write(out/'preregistration.json',dict(model_sha256=sha(model),hands=100000,sessions=40,
        mode='sample',temperature=1,seed_base=args.seed*10000+5000,
        statistic='Raw mean/normal95% and session mean/t39. Success requires both lower bounds positive.',
        stopping='Exactly40x2500; technical failure stops new waves and preserves all launched sessions.'))
    session_dirs=[]
    for wave in range(5):
        jobs=[]
        with ThreadPoolExecutor(max_workers=8) as pool:
            for index in range(wave*8,(wave+1)*8):
                directory=out/'sessions'/f's{index:02d}'
                argv=[sys.executable,'-B',str(base/'runtime/alpha_holdem/play_slumbot_v6_journaled.py'),
                    '--model',str(model),'--hands','2500','--seed',str(args.seed*10000+5000+index),
                    '--session-id',f'{base.name}_10m_s{index:02d}','--out-dir',str(directory),
                    '--device','cpu','--policy-mode','sample']
                jobs.append(pool.submit(run_command,argv,out/'jobs'/f's{index:02d}',env))
                session_dirs.append(directory)
            for job in jobs:
                job.result()
        count=sum(read(d/'summary.json')['successful_hands'] for d in session_dirs)
        log('update',base.name+'-test10m','--count',f'evaluation_hands={count}')
    argv=[sys.executable,'-B',str(base/'runtime/alpha_holdem/audit_slumbot_v6_session.py'),
          '--model',str(model)]
    for directory in session_dirs:
        argv+=['--session-dir',str(directory)]
    run_command(argv,out/'replay_audit',env)
    audit=read(out/'replay_audit/stdout.log')
    require(audit['status']=='PASS' and audit['successful_hands']==100000 and audit['sessions']==40,
            'Incomplete full replay')
    argv=[sys.executable,'-B',str(base/'runtime/alpha_holdem/audit_journaled_slumbot_independence.py'),
          '--out-json',str(out/'independence.json')]
    for directory in session_dirs:
        argv+=['--session-dir',str(directory)]
    run_command(argv,out/'independence_audit',env)
    require(read(out/'independence.json')['status']=='PASS','Session independence check failed')
    rewards=[]
    means=[]
    for directory in session_dirs:
        rows=[json.loads(line) for line in (directory/'hands.jsonl').read_text().splitlines()]
        require(len(rows)==2500 and all(r['model_sha256']==model_hash for r in rows),'Raw coverage/model mismatch')
        values=[r['winnings_chips'] for r in rows]
        means.append(statistics.mean(values))
        rewards.extend(values)
    # 100 chips/bb divided by100 hands cancels: mean chips is bb/100.
    mean=statistics.mean(rewards)
    half=1.96*statistics.stdev(rewards)/(len(rewards)**.5)
    session_half=float(t.ppf(.975,39))*statistics.stdev(means)/(40**.5)
    write(out/'result.json',dict(evidence_passed=True,hands=100000,model_sha256=sha(model),
        bb_per_100=mean,raw_ci95=[mean-half,mean+half],session_ci95=[mean-session_half,mean+session_half],
        positive_under_both_intervals=mean>max(half,session_half),
        scope='First fixed endpoint test; not proof of general optimality. Goal completion needs independent review.'))
    print(json.dumps(read(out/'result.json'),indent=2))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=['plan','train10m','test10m','train20m'],nargs='?',default='plan')
    parser.add_argument('--run-name',default='v6-fromzero-10m-20260908')
    parser.add_argument('--seed',type=int,default=2026090807)
    parser.add_argument('--workers',type=int,default=12)
    args=parser.parse_args()
    import re
    require(re.fullmatch(r'[A-Za-z0-9_-]{1,70}',args.run_name) is not None,'Invalid run name')
    require(args.workers>0 and args.seed>=0,'Invalid workers/seed')
    base=ROOT/'research/experiments'/args.run_name
    if args.stage=='plan':
        print('RANDOM initialization; 0 -> actual10M -> frozen100k sampled test -> cumulative20M. No jobs launched.')
        print(subprocess.list2cmdline(training_command(base,'train10m',args.seed,args.workers)))
        return
    if not base.exists():
        require(args.stage=='train10m','Start with train10m')
        prepare(base,args)
    check_contract(base,args)
    eid=base.name+'-'+args.stage
    command=subprocess.list2cmdline([sys.executable,str(Path(__file__).resolve()),*sys.argv[1:]])
    subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'start','--id',eid,
        '--title',f'Fixed-dose from-zero {args.stage}','--hypothesis','Test long-horizon general self-play learning.',
        '--change','User-directed fixed10M then100k test then cumulative20M; no small benchmark gates.',
        '--command',command,'--code-path',str(base/'runtime'),'--artifact',str(base/'contract.json')],cwd=ROOT,check=True)
    started=time.monotonic()
    env=dict(os.environ,PYTHONPATH=str(base/'runtime'),PYTHONDONTWRITEBYTECODE='1',
             OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
    try:
        (evaluate if args.stage=='test10m' else train)(base,args,env)
    except BaseException:
        log('update',eid,'--note','Interrupted or failed: preserve processes/checkpoints/raw evidence. No automatic retry.')
        raise
    log('finish',eid,'--status','COMPLETED','--summary','Fixed stage completed; see retained result.',
        '--conclusion','Stage completion is not a claim of general poker superiority.',
        '--decision','Stop at the requested stage boundary.', '--next-step','Inspect result then explicitly invoke the next stage.',
        '--artifact',str(base/args.stage/'result.json'),'--metric',f'wall_time_seconds={time.monotonic()-started}')


if __name__=='__main__':
    main()
