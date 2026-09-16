"""Fixed matched8epoch supervised fit on original states and new own-reach targets."""
import json
import os
import shutil
import numpy as np
import torch
from fit_metrics import hero_tv,cross_entropy,paired_gate

def fit(run,manifest,reservoir,targets,validation,control_probabilities):
    from alpha_holdem.execution_v6 import load_policy
    from alpha_holdem.policy_contract_v6 import METADATA
    from temporal_average import soft_ce
    torch.manual_seed(2026102004);torch.cuda.manual_seed_all(2026102004)
    student,source,_=load_policy(manifest['initializer']['path'],'cuda')
    initial={k:v.detach().cpu().clone() for k,v in student.state_dict().items()}
    names=[]
    for name,parameter in student.named_parameters():
        trainable=not name.startswith('value_head.')
        parameter.requires_grad_(trainable)
        if trainable:names.append(name)
    assert len(names)==80
    optimizer=torch.optim.Adam([p for p in student.parameters() if p.requires_grad],lr=1e-4)
    generator=np.random.default_rng(2026102004)
    control_hands,hero_counts=hero_tv(control_probabilities,validation['targets'],validation['hands'],validation['actors'])
    np.save(run.BASE/'control_hero_tv.npy',control_hands)
    np.save(run.BASE/'validation_hero_counts.npy',hero_counts)
    history=[]
    def evaluate(epoch):
        student.eval()
        probabilities=run.infer(student,validation['arrays'],'cuda','student_validation')
        hands,counts=hero_tv(probabilities,validation['targets'],validation['hands'],validation['actors'])
        assert np.array_equal(counts,hero_counts)
        ce=cross_entropy(probabilities,validation['targets'])
        np.save(run.BASE/f'validation_epoch{epoch:02d}_probabilities.npy',probabilities)
        np.save(run.BASE/f'validation_epoch{epoch:02d}_hero_tv.npy',hands)
        np.save(run.BASE/f'validation_epoch{epoch:02d}_ce.npy',ce)
        return probabilities,hands,dict(epoch=epoch,validation_ce=float(ce.mean()),validation_hero_tv=float(np.nanmean(hands)))
    evaluate(0)
    (run.BASE/'checkpoints').mkdir()
    steps=0
    with (run.BASE/'training_metrics.jsonl').open('x') as handle:
        for epoch in range(1,9):
            student.train()
            order=generator.permutation(len(targets))
            order_digest=run.array_digest(order)
            loss_sum=0.
            for begin in range(0,len(order),1024):
                idx=order[begin:begin+1024]
                tensors=[torch.as_tensor(reservoir['arrays'][k][idx],device='cuda') for k in run.KEYS]
                target=torch.as_tensor(targets[idx],dtype=torch.float32,device='cuda')
                optimizer.zero_grad(set_to_none=True)
                loss=soft_ce(student(*tensors)[0],target,tensors[-1]).mean()
                assert torch.isfinite(loss)
                loss.backward()
                norm=torch.nn.utils.clip_grad_norm_([p for p in student.parameters() if p.requires_grad],1.)
                assert torch.isfinite(norm)
                optimizer.step();steps+=1
                value=float(loss.detach());loss_sum+=value*len(idx)
                handle.write(json.dumps(dict(epoch=epoch,step=steps,rows=len(idx),loss=value,gradient_norm=float(norm),
                    epoch_order_sha256=order_digest,new_training_hands=0))+'\n')
            handle.flush();os.fsync(handle.fileno())
            if epoch in (1,4,8):
                probabilities,hands,metrics=evaluate(epoch)
                metrics.update(step=steps,training_ce=loss_sum/len(targets))
                history.append(metrics)
                print(json.dumps(metrics),flush=True)
            assert all(torch.isfinite(v).all() for v in student.state_dict().values())
            checkpoint=dict(**METADATA,model={k:v.detach().cpu().clone() for k,v in student.state_dict().items()},
                optimizer=optimizer.state_dict(),config={**source.get('config',{}),'training_algorithm':'reach_posterior_distillation_v1','lr':1e-4,'seed':2026102004},
                critic_contract=source.get('critic_contract','critic_v2'),norm_layer='gn',separate_preflop_head=True,
                epoch=epoch,iteration=epoch,total_hands=0,optimizer_steps=steps,run_id=run.BASE.name,
                training_algorithm='reach_posterior_distillation_v1',source_weights_sha256=run.INITIALIZER_SHA,
                input_manifest_sha256=run.sha(run.BASE/'input_manifest.json'),source_dataset_sha256=run.RESERVOIR_SHA,
                reach_targets_sha256=run.sha(run.BASE/'training_relabel/reach_targets.npy'),
                offline_source_hands=262144,offline_training_rows=262144,numpy_generator_state=generator.bit_generator.state,
                torch_rng_state=torch.get_rng_state(),cuda_rng_state=torch.cuda.get_rng_state_all(),
                environment_hand_accounting=dict(completed_hands=0,prefix_complete=True,unknown_prefix_training_marker_hands=0,
                    origin_run_id=run.BASE.name,semantics='No new trainingenvironmenthands;262144preservednative collectionhands reused forSL'),
                resume_contract='Not a train_v5 PPO continuation; explicit supervised-only resume required')
            torch.save(checkpoint,run.BASE/'latest.tmp.pt');os.replace(run.BASE/'latest.tmp.pt',run.BASE/'latest.pt')
            if epoch in (1,4,8):shutil.copy2(run.BASE/'latest.pt',run.BASE/'checkpoints'/f'epoch{epoch:02d}.pt')
            run.write('fit_progress.json',dict(epoch=epoch,optimizer_steps=steps,optimizer_rows_processed=steps*1024,new_training_hands=0))
        changed=[k for k,v in student.state_dict().items() if not torch.equal(v.detach().cpu(),initial[k])]
    assert set(changed)==set(names) and len(optimizer.state)==80 and steps==2048
    assert all(float(v['step'])==2048 and all(torch.isfinite(t).all() for t in v.values() if torch.is_tensor(t)) for v in optimizer.state.values())
    result=paired_gate(control_hands,hands)
    result.update(status='PASS',epochs=8,optimizer_steps=steps,optimizer_rows_processed=steps*1024,
        changed_policy_parameters=changed,frozen_value_parameters=[k for k in initial if k.startswith('value_head.')],
        history=history,new_training_hands=0,supervised_validation_hands=8192,model_sha256=run.sha(run.BASE/'latest.pt'))
    run.write('fit_analysis.json',result)
    return result

