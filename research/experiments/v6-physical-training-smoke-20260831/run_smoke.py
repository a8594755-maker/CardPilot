"""Bounded v6 trainer and frozen-evaluation smoke; no automatic restarts."""
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import psutil
import torch

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'scripts'))
from research.experiment_log import capture_code_provenance, sha256_file
from alpha_holdem.policy_contract_v6 import METADATA, validate_metadata

SOURCE = ROOT/'models/baseline/standard10/latest.pt'
ANCHORS = [SOURCE,
    Path('C:/Users/a8594/CardPilot_legacy_20260829/selected_assets/opponents/slumbot_free_anchor_position10m.pt'),
    Path('C:/Users/a8594/CardPilot_legacy_20260829/selected_assets/opponents/corrected_cfr96_anchor10.pt')]
DIGESTS = ['91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428',
           '457d3babb82cb8014a2b7c378b2b5f916962565e63a44d192d5d7acd8393d6e7',
           '902a7049ca66c0552246d11fe482eed4df47ac5c675ddf051c34ed86dcf213a6']


def log(*args):
    subprocess.run([sys.executable, str(ROOT/'research/experiment_log.py'), 'update', BASE.name, *map(str, args)], cwd=ROOT, check=True)


def record(command):
    log('--command', subprocess.list2cmdline(['python', *map(str, command)]))


def command():
    run = BASE/'production'
    return ['-u', 'scripts/alpha_holdem/train_v5.py', '--device', 'cuda', '--workers', '12',
        '--hands-per-iter', '4096', '--total-hands', '99999999', '--total-environment-hands', '8192',
        '--starting-stack', '200', '--env-version', 'v6', '--v6-rebind-legacy-weights', '--norm-layer', 'gn',
        '--lr', '.00003', '--ppo-epochs', '2', '--ppo-target-kl', '.01', '--policy-advantage-clip', '3',
        '--source-policy-kl-coef', '.01', '--source-policy-reference-checkpoint', str(BASE/'frozen/anchor0.pt'),
        '--separate-preflop-head', '--mini-batch-size', '1024', '--entropy-coef', '.005', '--entropy-floor', '.05',
        '--pool-strategy', 'latest', '--fixed-opponent-checkpoints', *[str(BASE/f'frozen/anchor{i}.pt') for i in range(3)],
        '--hero-policy-mode', 'sample', '--self-play-fraction', '.25', '--opponent-assignment', 'per-group',
        '--opponent-groups', '8', '--adaptive-opponent-league', '--adaptive-league-ema', '.9',
        '--adaptive-league-temperature-bb', '2', '--adaptive-league-min-probability', '.05',
        '--opponent-assignment-provenance-file', str(run/'opponent_assignments.jsonl'),
        '--rollout-mode', 'single', '--worker-seed-base', '2026091600', '--fixed-training-deal-stream',
        '--critic-contract', 'critic_v2', '--h1-effective-stack-divisor', '200', '--h1-critic-init-seed', '2026071102',
        '--value-coef', '1', '--autonomous-critic-v2-continue', '--snapshot-every', '999999',
        '--save-interval', '1', '--archive-checkpoint-every', '1', '--run-id', 'v6_physical_smoke_20260831',
        '--run-dir', str(run), '--out', str(run/'latest.pt'), '--seed', '20260916', '--max-runtime-seconds', '600',
        '--resume', str(SOURCE), '--allow-resume', '--reset-hand-counter', '--reset-optimizer']


def verify(copies):
    for item in copies:
        assert all(sha256_file(ROOT/item[key]) == item['sha256'] for key in ['original', 'copy'])
    for path, digest in zip(ANCHORS, DIGESTS):
        assert sha256_file(path) == digest


def main():
    if sys.argv[1:]: raise ValueError('Fixed smoke protocol; no automatic rerun')
    for p in psutil.process_iter(['pid','name','cmdline']):
        if p.pid != psutil.Process().pid and (p.info['name'] or '').lower().startswith('python') and any(
            Path(arg).name in ['train_v5.py','v5_mirror_eval.py','v6_mirror_eval.py','play_slumbot.py','play_slumbot_v6.py']
            for arg in p.info['cmdline'] or []):
            raise ValueError('Another poker process is active')
    if any((BASE/name).exists() for name in ['production','frozen','execution_code','completed_analysis.json']):
        raise ValueError('Existing experiment output must be preserved')
    repair = json.loads((ROOT/'research/experiments/native-rules-contract-repair-20260831/reviewed_analysis.json').read_text())
    assert repair['decision'] == 'V6_CONTRACT_REPAIR_VALIDATED'
    source = BASE/'execution_code'
    source.mkdir()
    paths = [p.relative_to(ROOT).as_posix() for p in sorted((ROOT/'scripts/alpha_holdem').glob('*.py'))]
    paths += [f'scripts/deep_cfr/{n}.py' for n in ['__init__','game_state','hand_eval']]
    paths += ['research/experiment_log.py']
    paths += [p.relative_to(ROOT).as_posix() for p in sorted(BASE.glob('*.py'))]
    paths += [(BASE/'preregistration.md').relative_to(ROOT).as_posix()]
    capture_code_provenance(ROOT, source, paths)
    copies = []
    for relative in paths:
        target = source/'source_files'/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT/relative, target)
        copies.append(dict(original=relative, copy=target.relative_to(ROOT).as_posix(), sha256=sha256_file(target)))
    (source/'copy_manifest.json').write_text(json.dumps(copies, indent=2)+'\n')
    verify(copies)
    log(*[v for name in ['source_manifest.json','code.patch','copy_manifest.json'] for v in ['--artifact',str(source/name)]])
    test_cmd = ['-m','pytest',str(BASE/'test_smoke.py'),'-q',f'--junitxml={BASE/"prerun_tests.xml"}']
    record(test_cmd)
    subprocess.run([sys.executable,*test_cmd],cwd=ROOT,check=True)
    log('--artifact',str(BASE/'prerun_tests.xml'))
    frozen = BASE/'frozen'
    frozen.mkdir()
    rebound_manifest = []
    for index, (path, digest) in enumerate(zip(ANCHORS,DIGESTS)):
        old = torch.load(path,map_location='cpu',weights_only=False)
        new = {key:value for key,value in old.items() if key not in ['optimizer'] and not key.startswith(('pool_','ppo_replay_','adaptive_opponent_'))}
        new.update(METADATA)
        new.update(artifact_kind='explicit_weight_rebinding_no_training', source_path=str(path), source_sha256=digest,
                   source_total_hands=old.get('total_hands'),source_iteration=old.get('iteration'),
                   total_hands=0,iteration=0,environment_hand_accounting=None,
                   run_id=f'v6_rebound_anchor{index}_20260831')
        validate_metadata(new)
        assert all(torch.equal(old['model'][k],new['model'][k]) for k in old['model'])
        target = frozen/f'anchor{index}.pt'
        torch.save(new,target)
        rebound_manifest.append(dict(source=str(path),source_sha256=digest,path=str(target),sha256=sha256_file(target), tensors=len(old['model'])))
        log('--artifact',str(target))
    (BASE/'rebound_manifest.json').write_text(json.dumps(rebound_manifest,indent=2)+'\n')
    log('--artifact',str(BASE/'rebound_manifest.json'))
    train_cmd = command()
    record(train_cmd)
    with (BASE/'trainer_stdout.log').open('x') as output:
        process = subprocess.Popen([sys.executable,*train_cmd],cwd=ROOT,stdout=output,stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
        log('--metric',f'trainer_pid={process.pid}')
        seen = -1
        while process.poll() is None:
            manifest_path = BASE/'production/run_manifest.json'
            if manifest_path.exists():
                try: manifest = json.loads(manifest_path.read_text())
                except (OSError,json.JSONDecodeError): manifest = {}
                count = int((manifest.get('environment_hand_accounting') or {}).get('completed_hands',0))
                if count > seen:
                    log('--count',f'new_training_hands={count}','--metric',f'latest_iteration={manifest.get("iteration",0)}')
                    seen = count
            time.sleep(3)
        code = process.wait()
    log('--metric',f'trainer_exit_code={code}','--artifact',str(BASE/'trainer_stdout.log'))
    if code: raise RuntimeError('Terminal trainer failure; do not restart')
    run = BASE/'production'
    manifest = json.loads((run/'run_manifest.json').read_text())
    checkpoint = torch.load(run/'latest.pt',map_location='cpu',weights_only=False)
    validate_metadata(checkpoint)
    count = checkpoint['environment_hand_accounting']['completed_hands']
    assert count >=8192 and checkpoint['environment_hand_accounting']['prefix_complete']
    assert count == manifest['environment_hand_accounting']['completed_hands']
    old = torch.load(SOURCE,map_location='cpu',weights_only=False)
    changed = [k for k in old['model'] if not torch.equal(old['model'][k],checkpoint['model'][k])]
    assert len(changed)==86 and all(torch.isfinite(v).all() for v in checkpoint['model'].values())
    states=checkpoint['optimizer']['state']
    assert len(states)==86 and all(torch.isfinite(v).all() for st in states.values() for v in st.values() if isinstance(v,torch.Tensor))
    audit_cmd=['scripts/alpha_holdem/audit_train_v5_fixed_pool_session.py','--run-dir',str(run),
        '--expected-target-hands','99999999','--expected-target-environment-hands','8192',
        '--expected-final-iteration',str(checkpoint['iteration']),'--expected-pool-size','3',
        '--expected-archive-every','1','--expected-normalization','global','--out',str(BASE/'session_audit.json')]
    record(audit_cmd)
    subprocess.run([sys.executable,*audit_cmd],cwd=ROOT,check=True)
    shutil.copy2(run/'latest.pt',frozen/'final.pt')
    assert sha256_file(run/'latest.pt') == sha256_file(frozen/'final.pt')
    verify(copies)
    log('--count',f'new_training_hands={count}', '--artifact',str(frozen/'final.pt'), '--artifact',str(BASE/'session_audit.json'),
        *[v for name in ['latest.pt','run_manifest.json','h1_training_metrics.jsonl','opponent_assignments.jsonl'] for v in ['--artifact',str(run/name)]])
    cells=[]
    for label,candidate in [('source',frozen/'anchor0.pt'),('final',frozen/'final.pt')]:
        for anchor_index in range(3):
            out=BASE/'matrix'/f'{label}_anchor{anchor_index}'
            eval_cmd=['scripts/alpha_holdem/v6_mirror_eval.py','--candidate',str(candidate),
                '--anchor',str(frozen/f'anchor{anchor_index}.pt'),'--pairs','64','--seed','20260917',
                '--device','cpu','--out-dir',str(out)]
            record(eval_cmd)
            subprocess.run([sys.executable,*eval_cmd],cwd=ROOT,check=True)
            result=json.loads((out/'summary.json').read_text())
            assert result['evaluation_hands']==128
            if label=='source' and anchor_index==0:
                assert all(sum(json.loads(line)['rewards_bb'])==0 for line in (out/'pairs.jsonl').read_text().splitlines())
            cells.append(dict(candidate=label,anchor=anchor_index,**result))
            log('--count',f'evaluation_hands={128*len(cells)}','--artifact',str(out/'summary.json'),'--artifact',str(out/'pairs.jsonl'))
    verify(copies)
    for item in rebound_manifest: assert sha256_file(item['path'])==item['sha256']
    summary=dict(status='COMPLETED_PENDING_REVIEW',new_training_hands=count,physical_overshoot=count-8192,
        evaluation_hands=768,slumbot_hands=0,iteration=checkpoint['iteration'],changed_tensors=len(changed),
        finite_optimizer_states=len(states),final_sha256=sha256_file(frozen/'final.pt'),cells=cells,
        completed_at=datetime.now(timezone.utc).isoformat(),scope='Pipeline smoke, not a strength admission gate')
    (BASE/'completed_analysis.json').write_text(json.dumps(summary,indent=2)+'\n')
    log('--artifact',str(BASE/'completed_analysis.json'),'--note','Production and six frozen diagnostic cells complete; independently review raw counters/CI/source evidence before finish.')
    print(json.dumps(summary),flush=True)


if __name__=='__main__': main()
