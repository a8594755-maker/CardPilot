"""Single offline preflight for unchanged four-parent continuation; no environment hands."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import run_scale as run

BASE, ROOT = run.BASE, run.ROOT
read, sha, require = run.read, run.sha, run.require


def main():
    import torch
    torch.set_num_threads(1)
    begun = time.perf_counter()
    output = BASE/'qualification.json'
    require(not output.exists() and not (BASE/'qualification_failure.json').exists(), 'preserve qualification attempt')
    run.reject_live_poker()
    require(read(BASE/'experiment.json')['status'] == 'RUNNING', 'register before meaningful work')
    require(read(run.OLD/'experiment.json')['status'] == 'COMPLETED' and
            read(run.EXTERNAL/'experiment.json')['status'] == 'COMPLETED', 'parents not closed')
    require(sha(run.OLD/'run_actor_control.py') == run.OLD_CONTROLLER_SHA, 'inherited execution source changed')
    argv = [sys.executable,'-B','-m','pytest','-q','-p','no:cacheprovider',
            str(BASE/'test_scale.py'),'--junitxml='+str(BASE/'tests.xml')]
    result = subprocess.run(argv,cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
    suite = {'command':argv,'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr}
    run.write_new(BASE/'test_result.json',suite)
    require(result.returncode == 0,result.stdout+result.stderr)
    suites = list(ET.parse(BASE/'tests.xml').getroot().iter('testsuite'))
    require(suites and all(int(s.get(k,'0')) == 0 for s in suites for k in ('failures','errors','skipped')), 'incomplete tests')
    old_report_path = run.OLD/'recovery_20260906/post_terminal_review.json'
    ext_report_path = run.EXTERNAL/'post_terminal_review.json'
    require(sha(old_report_path) == '4a244d2f06991c2bab1657f295d1b2fa218758f46827f888555ff35cb770bced', 'prior training review changed')
    require(sha(ext_report_path) == 'e847cc5d8c7e73f535733c16b14ded69605bfc0f8873506ecfeb38e1d4424d46', 'external review changed')
    old = read(old_report_path)
    known = set(old['new_attempt_namespaces'])
    sources = {p:h for p,h in read(run.OLD/'input_contract.json')['input_sha256'].items() if p.endswith('.py')}
    sources.update({str(p):sha(p) for p in BASE.iterdir() if p.is_file() and p.suffix in ('.py','.md','.ps1')})
    sources.update({str(p):sha(p) for p in (old_report_path,ext_report_path,BASE/'tests.xml',
                    BASE/'test_result.json',run.OLD/'run_actor_control.py',run.ctl.WRAPPER)})
    parents, commands = {}, {}
    for seed,arm in run.ORDER:
        key = f'seed{seed}_{arm}'
        path = run.parent_path(seed,arm,3)
        digest,physical,iteration = run.CURRENT[(seed,arm)]
        require(sha(path) == digest,'current endpoint changed: '+key)
        checkpoint = torch.load(path,map_location='cpu',weights_only=False)
        require(checkpoint['environment_hand_accounting']['completed_hands'] == physical and
                checkpoint['iteration'] == iteration,'retained counters mismatch')
        run.ctl.route_audit(checkpoint,arm == 'connected',checkpoint)
        require(len(checkpoint['optimizer']['state']) == 86 and
                checkpoint['optimizer']['param_groups'][0]['lr'] == run.EXPECTED_LR,'optimizer scope/LR')
        require(len(checkpoint['ppo_replay_entries']) == 2 and
                checkpoint['ppo_replay_cumulative_rows'] > 0,'serialized replay missing')
        require(all(name in checkpoint for name in run.ctl.prior.INITIAL_KEYS),'resume evidence missing')
        require(checkpoint['main_process_rng_state']['torch_cuda'],'missing CUDA RNG')
        attempt = checkpoint['fixed_deal_attempt']
        require(run.ctl.HELPER.helpers.load_attempt(Path(attempt['path']),attempt['sha256']) == attempt['receipt'],
                'parent attempt receipt invalid')
        known.add(attempt['receipt']['namespace'])
        sources[attempt['path']] = attempt['sha256']
        sources[str(path)] = digest
        for name in ('h1_training_metrics.jsonl','opponent_assignments.jsonl','run_manifest.json',
                     'verification.json','termination.json','command.json'):
            source = path.parent/name
            sources[str(source)] = sha(source)
        manifest, verification = read(path.parent/'run_manifest.json'),read(path.parent/'verification.json')
        require(manifest['status'] == 'finished' and
                manifest['environment_hand_accounting']['completed_hands'] == physical and
                verification['passed'] and verification['checkpoint_sha256'] == digest,'terminal endpoint unverified')
        require(read(path.parent/'termination.json')['exit_code'] == 0,'parent exit missing')
        command = run.training_command(seed,arm,3,path,physical)
        previous = read(path.parent/'command.json')
        require(run.normalized_training_command(command) == run.normalized_training_command(previous),
                'unregistered training-regimen change')
        target = run.INITIAL_PHYSICAL[seed]+run.DOSES[3]
        require(int(command[command.index('--total-environment-hands')+1]) == target > physical,'target or resume wrong')
        commands[key] = {'training':command,'evaluation':run.evaluate_command(seed,arm,3)}
        parents[key] = {'path':str(path),'sha256':digest,'physical_hands':physical,'iteration':iteration,
                       'transition_hands':checkpoint['total_hands'],'target':target,'remaining_hands':target-physical,
                       'optimizer_states':86,'actual_lr':run.EXPECTED_LR,'serialized_replay_entries':2,
                       'namespace':attempt['receipt']['namespace'],'new_route_migration':False}
        del checkpoint
    for seed,path in run.PARENTS.items():
        require(sha(path) == run.PARENT_SHA[seed],'original common parent changed')
        sources[str(path)] = run.PARENT_SHA[seed]
    for name,path in run.execution.ANCHORS.items():
        require(sha(path) == run.execution.ANCHOR_SHA256[name],'anchor changed')
        sources[str(path)] = run.execution.ANCHOR_SHA256[name]
    corpus = {str(p):sha(p) for p in (ROOT/'research/experiments').rglob('common_deck_pairs.jsonl.gz')
              if not p.is_relative_to(BASE)}
    run.execution.check_hashes(sources)
    require(sum(p['remaining_hands'] for p in parents.values()) == 4185219,'wrong aggregate new dose')
    run.write_new(BASE/'commands.json',commands)
    sources[str(BASE/'commands.json')] = sha(BASE/'commands.json')
    report = {'passed':True,'created_at':datetime.now(timezone.utc).isoformat(),'command':sys.orig_argv,
              'pytest_command':argv,'parents':parents,'input_sha256':sources,'prior_common_deck_corpus':corpus,
              'known_attempt_namespaces':sorted(known),'new_training_hands':0,'new_evaluation_hands':0,
              'minimum_new_physical_target':4185219,'internal_evaluation_hands':32768,
              'unchanged_argv_except_bound_continuation_fields':True,
              'actual_initial_state_audit_required_during_each_real_resume':True,
              'statistical_not_bitwise_worker_continuation':True,
              'earlier_unknown_lineage_tail_hands':None,'wall_seconds':time.perf_counter()-begun}
    run.write_new(output,report)
    run.logger('--command',subprocess.list2cmdline(sys.orig_argv),'--command',subprocess.list2cmdline(argv),
               '--artifact',str(output),'--artifact',str(BASE/'commands.json'),'--artifact',str(BASE/'tests.xml'),
               '--artifact',str(BASE/'test_result.json'),'--metric','resume_preflight_passed=true',
               '--metric','minimum_new_physical_target=4185219')
    print(json.dumps({'passed':True,'tests':sum(int(s.get('tests','0')) for s in suites),
                      'parents':parents,'new_training_hands':0,'frozen_inputs':len(sources)}))


if __name__ == '__main__':
    try:
        main()
    except BaseException as exc:
        failure = BASE/'qualification_failure.json'
        if not failure.exists():
            run.write_new(failure,{'error':repr(exc),'command':sys.orig_argv,
                                  'created_at':datetime.now(timezone.utc).isoformat(),'new_training_hands':0})
        raise

