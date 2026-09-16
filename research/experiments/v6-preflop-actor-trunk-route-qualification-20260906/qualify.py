"""Actual-parent forward/gradient/Adam and unstepped metadata-transfer qualification."""
import copy
from datetime import datetime, timezone
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback
import xml.etree.ElementTree as ET

import numpy as np
import torch

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path.insert(0,str(BASE))
sys.path.insert(0,str(BASE / 'candidate/scripts'))
import route_transfer as transfer
from alpha_holdem.network_hybrid_h1 import AlphaHoldemNet
from alpha_holdem.preflop_gradient_contract import FLAG, ORIGIN, validate_resume
from prepare_candidate import sha

PARENT_DIR = ROOT / 'research/experiments/v6-full-step-size-1m-continuation-20260905'
PARENTS = {
    1: ('8904f3b2e25baec5bc0bcb6556502c19b3fb213efdc9a32b16d55eee1284a3ef',10498234,2215),
    3: ('f2249b0d19937ddadfc29fe5ba10cd7f07909d638dc0edeca89fae05b6f498e2',10492141,2218),
}


def write_new(path, value):
    with Path(path).open('x',encoding='utf-8') as handle:
        json.dump(value,handle,indent=2,allow_nan=False)


def model_for(parent, connected, cls=AlphaHoldemNet):
    args = dict(norm_layer='gn',critic_contract='critic_v2',separate_preflop_head=True)
    if cls is AlphaHoldemNet:
        args[FLAG] = connected
    model = cls(**args).eval()
    with torch.no_grad():
        model(torch.zeros(1,6,4,13),torch.zeros(1,25,4,5),torch.zeros(1,3))
    model.load_state_dict(parent['model'],strict=True)
    assert len(list(model.parameters()))==86 and all(p.requires_grad for p in model.parameters())
    return model


def replay_inputs(parent):
    selected = {street:[] for street in (0,3,4,5)}
    identities = {street:[] for street in selected}
    for entry in parent['ppo_replay_entries']:
        for bi,block in enumerate(entry['blocks']):
            for ri,row in enumerate(block):
                cards = row[0].reshape(6,4,13)
                board = int(cards[4].sum())
                assert board in selected
                if len(selected[board])<16:
                    selected[board].append(row)
                    identities[board].append([entry['iteration'],bi,ri])
    assert all(len(rows)==16 for rows in selected.values())
    inputs = {}
    for street,rows in selected.items():
        inputs[street] = (
            torch.from_numpy(np.stack([r[0] for r in rows]).reshape(-1,6,4,13)),
            torch.from_numpy(np.stack([r[1] for r in rows]).reshape(-1,25,4,5)),
            torch.from_numpy(np.stack([r[2] for r in rows])),
            torch.from_numpy(np.stack([r[3] for r in rows])),
            torch.tensor([r[4] for r in rows],dtype=torch.long),
        )
        assert all(torch.isfinite(v).all() for v in inputs[street])
        assert torch.all(inputs[street][3].gather(1,inputs[street][4][:,None]) > 0)
    return inputs, identities


def group(name):
    for prefix in ('preflop_policy_head','policy_head','value_head'):
        if name.startswith(prefix+'.'):
            return prefix
    return 'body'


def gradient_groups(model, inputs, objective):
    logits,value = model(*inputs[:4])
    loss = torch.nn.functional.cross_entropy(logits,inputs[4]) if objective=='actor' else value.square().mean()
    named = list(model.named_parameters())
    grads = torch.autograd.grad(loss,[p for _,p in named],allow_unused=True)
    sums = {key:0. for key in ('body','policy_head','preflop_policy_head','value_head')}
    for (name,_),gradient in zip(named,grads):
        if gradient is not None:
            assert torch.isfinite(gradient).all()
            sums[group(name)] += float(gradient.double().square().sum())
    return {key:value**.5 for key,value in sums.items()}


def update_fixture(parent, detached, connected, inputs):
    optimizers = []
    for model in (detached,connected):
        optimizer = torch.optim.Adam(model.parameters(),lr=.0003)
        optimizer.load_state_dict(copy.deepcopy(parent['optimizer']))
        assert transfer.equal_tree(optimizer.state_dict(),parent['optimizer'])
        assert abs(optimizer.param_groups[0]['lr']-1e-4)<1e-18
        optimizer.zero_grad(set_to_none=True)
        logits,value = model(*inputs[:4])
        loss = torch.nn.functional.cross_entropy(logits,inputs[4]) + .5*value.square().mean()
        loss.backward()
        assert all(p.grad is not None and torch.isfinite(p.grad).all() for p in model.parameters())
        optimizer.step()
        for index,state in optimizer.state_dict()['state'].items():
            assert float(state['step']) == float(parent['optimizer']['state'][index]['step'])+1
            assert all(torch.isfinite(v).all() for v in state.values())
        optimizers.append(optimizer)
    differences = {key:0. for key in ('body','policy_head','preflop_policy_head','value_head')}
    for (name,a),(other,b) in zip(detached.named_parameters(),connected.named_parameters()):
        assert name==other and torch.isfinite(a).all() and torch.isfinite(b).all()
        differences[group(name)] += float((a.detach().double()-b.detach().double()).square().sum())
    assert differences['body']>0 and all(differences[k]==0 for k in differences if k!='body')
    return {'loaded_Adam_states':86,'advanced_Adam_clocks_per_arm':86,
            'actual_lr':optimizers[0].param_groups[0]['lr'],
            'control_treatment_parameter_difference_l2':{k:v**.5 for k,v in differences.items()},
            'updated_models_saved':False,
            'scope':'Diagnostic preflop action cross-entropy plus zero-target value loss on retained internal replay inputs; not a production PPO update or poker improvement.'}


def main():
    output = BASE / 'qualification.json'
    failure = BASE / 'qualification_failure.json'
    assert not output.exists() and not failure.exists(), 'preserve previous attempt'
    assert json.loads((BASE / 'experiment.json').read_text())['status']=='RUNNING'
    assert json.loads((PARENT_DIR/'experiment.json').read_text())['status']=='COMPLETED'
    torch.set_num_threads(1)
    torch.manual_seed(2026410602)
    started = time.monotonic()
    results, commands = {}, []
    paths = list(BASE.glob('*.py')) + [BASE/'protocol.md',BASE/'focused_tests.xml',BASE/'regression_report_v2.json',BASE/'regression_tests_v2.xml',BASE/'preparation.json',BASE/'dependency_preparation.json']
    paths += list((BASE/'candidate').rglob('*.py')) + list((BASE/'original').rglob('*.py'))
    hashes = {str(p):sha(p) for p in paths}
    try:
        regression = json.loads((BASE/'regression_report_v2.json').read_text())
        assert regression['passed'] and regression['counts']['tests']==375 and not regression['binding_errors']
        assert sha(BASE/'regression_tests_v2.xml')==regression['xml_sha256']
        assert all(sha(v['path'])==v['sha256'] for v in regression['candidate_module_bindings'].values())
        suites = list(ET.parse(BASE/'focused_tests.xml').getroot().iter('testsuite'))
        assert sum(int(s.get('tests','0')) for s in suites)==43
        assert all(all(int(s.get(k,'0'))==0 for k in ('failures','errors','skipped')) for s in suites)
        changed = []
        diffs = []
        for before in sorted((BASE/'original/scripts').rglob('*.py')):
            relative = before.relative_to(BASE/'original/scripts')
            after = BASE/'candidate/scripts'/relative
            assert sha(ROOT/'scripts'/relative)==sha(before), 'production changed'
            if sha(before)!=sha(after):
                changed.append(str(relative).replace('\\','/'))
                diffs.extend(difflib.unified_diff(before.read_text().splitlines(True),after.read_text().splitlines(True),fromfile='original/'+relative.as_posix(),tofile='candidate/'+relative.as_posix()))
        assert set(changed)=={'alpha_holdem/train_v5.py','alpha_holdem/network_hybrid_h1.py'}
        assert len(list((BASE/'candidate/scripts').rglob('*.py')))==287
        with (BASE/'candidate_delta.patch').open('x',encoding='utf-8') as handle:
            handle.writelines(diffs)
        trainer = BASE/'candidate/scripts/alpha_holdem/train_v5.py'
        for flags,expected,text in [(['--help'],0,'--preflop-trunk-gradient'),
                (['--preflop-trunk-gradient'],2,'requires a separate preflop head'),
                (['--preflop-trunk-gradient','--separate-preflop-head','--preflop-teacher-coef','1'],2,'not admitted with teacher loss')]:
            argv = [sys.executable,'-B',str(trainer),*flags]
            process = subprocess.run(argv,cwd=BASE/'candidate',capture_output=True,text=True,timeout=45)
            commands.append({'argv':argv,'cwd':str(BASE/'candidate'),'exit_code':process.returncode,
                             'required_message':text,'matched':text in process.stdout+process.stderr})
            assert process.returncode==expected and text in process.stdout+process.stderr, commands[-1]
        spec = importlib.util.spec_from_file_location('original_route_actual',BASE/'original/scripts/alpha_holdem/network_hybrid_h1.py')
        old = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(old)
        for seed,(digest,physical,iteration) in PARENTS.items():
            source = PARENT_DIR/f'seed{seed}_full_stage2/latest.pt'
            assert sha(source)==digest
            hashes[str(source)] = digest
            parent = torch.load(source,map_location='cpu',weights_only=False)
            assert parent['iteration']==iteration and parent['environment_hand_accounting']['completed_hands']==physical
            assert len(parent['optimizer']['state'])==86 and len(parent['ppo_replay_entries'])==2
            assert parent['main_process_rng_state'] is not None and parent['fixed_deal_attempt'] is not None
            binding = {'path':str(source),'sha256':digest}
            derived = transfer.derive(parent,binding)
            destination = BASE/f'seed{seed}_connected_unstepped.pt'
            with destination.open('xb') as handle:
                torch.save(derived,handle)
            restored = torch.load(destination,map_location='cpu',weights_only=False)
            assert transfer.equal_tree(derived,restored)
            transfer.validate_derived(parent,restored,binding)
            validate_resume(restored['config'],restored)
            original = model_for(parent,False,old.AlphaHoldemNet)
            detached,connected = model_for(parent,False),model_for(restored,True)
            inputs,identities = replay_inputs(parent)
            routes = {}
            for street,values in inputs.items():
                with torch.no_grad():
                    expected = original(*values[:4])
                    assert all(torch.equal(a,b) for a,b in zip(expected,detached(*values[:4])))
                    assert all(torch.equal(a,b) for a,b in zip(expected,connected(*values[:4])))
                for mode,model in [('detached',detached),('connected',connected)]:
                    for objective in ('actor','critic'):
                        groups = gradient_groups(model,values,objective)
                        observed = {k for k,v in groups.items() if v>0}
                        expected_groups = {'value_head'} if objective=='critic' else (
                            {'policy_head','body'} if street else
                            ({'preflop_policy_head','body'} if mode=='connected' else {'preflop_policy_head'}))
                        assert observed==expected_groups,(seed,street,mode,objective,groups)
                        routes[f'{street}/{mode}/{objective}']=groups
            assert transfer.equal_tree(detached.state_dict(),parent['model']) and transfer.equal_tree(connected.state_dict(),parent['model'])
            proof = update_fixture(parent,detached,connected,inputs[0])
            transfer.validate_derived(parent,restored,binding)
            results[str(seed)] = {'source':binding,'derived':str(destination),'derived_sha256':sha(destination),
                'physical_hands':physical,'iteration':iteration,'all_checkpoint_state_preserved':True,
                'forward_exact_rows_per_arm':64,'replay_row_identities':identities,'gradient_routes':routes,
                'diagnostic_update':proof,'unstepped_serialization_exact':True}
            print(json.dumps({'seed':seed,'passed':True,'new_hands':0}),flush=True)
            del parent,derived,restored,original,detached,connected
        assert all(sha(path)==digest for path,digest in hashes.items()), 'qualification input changed'
        write_new(output,{'schema':'cardpilot.preflop_actor_route_qualification.v1','passed':True,
            'created_at':datetime.now(timezone.utc).isoformat(),'command':sys.orig_argv,'actual_cli_checks':commands,
            'wall_seconds':time.monotonic()-started,'input_sha256':hashes,'parents':results,
            'focused_tests':43,'candidate_regressions':375,'production_changed':False,
            'new_training_hands':0,'evaluation_hands':0,'slumbot_hands':0,'final_qualification_hands':0,
            'goal_achieved':False,'actual_worker_initial_state_audit_still_required':True})
    except BaseException as exc:
        write_new(failure,{'error':repr(exc),'traceback':traceback.format_exc(),'parents':results,
                          'actual_cli_checks':commands,'new_hands':0,'preserve_partial_outputs':True})
        raise
    print(json.dumps({'passed':True,'parents':len(results),'wall_seconds':time.monotonic()-started,'new_hands':0}))


if __name__ == '__main__':
    main()
