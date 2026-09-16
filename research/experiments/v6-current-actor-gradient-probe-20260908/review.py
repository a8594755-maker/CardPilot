"""Recheck saved state/metric suffixes and summarize weighted pre-Adam probes."""
import hashlib
import json
import math
from pathlib import Path
import statistics
import time
import torch
import run_probe as runner

BASE = Path(__file__).resolve().parent
old = runner.old


def summarize(values):
    assert values and all(math.isfinite(x) for x in values)
    return dict(min=min(values),median=statistics.median(values),max=max(values),negative=sum(x<0 for x in values),n=len(values))


def main():
    start = time.monotonic()
    terminal = old.read(BASE/'terminal.json')
    assert terminal['status']=='COMPLETE_REVIEW_REQUIRED'
    hashes = dict(old.read(BASE/'input_contract.json')['input_sha256'])
    hashes[str(BASE/'review.py')] = old.sha(BASE/'review.py')
    old.ctl.execution.check_hashes(hashes)
    results, namespaces = [], set()
    for seed in (1,3):
        folder = BASE/f'seed{seed}_control_stage1'
        evidence = old.read(folder/'parent_contract.json')
        parent = torch.load(evidence['path'],map_location='cpu',weights_only=False)
        initial = torch.load(folder/'initial_resumed_state.pt',map_location='cpu',weights_only=False)
        final = torch.load(folder/'latest.pt',map_location='cpu',weights_only=False)
        gate = old.read(folder/'initial_resume_gate.json')
        assert old.sha(Path(evidence['path']))==evidence['sha256']==gate['parent_sha256']
        assert old.sha(folder/'initial_resumed_state.pt')==gate['initial_sha256']
        normalized = old.normalized_pool(parent,200)
        for key in gate['exact_keys']:
            assert old.state_equal(normalized[key], initial[key]), key
        optimizer = old.ctl.prior.optimizer_step_audit(parent,final,True)
        assert not optimizer['new_state_ids']
        assert [g['lr'] for g in parent['optimizer']['param_groups']] == [g['lr'] for g in final['optimizer']['param_groups']]
        namespace = final['fixed_deal_attempt']['receipt']['namespace']
        assert namespace==gate['namespace'] and namespace not in namespaces
        assert namespace != parent['fixed_deal_attempt']['receipt']['namespace']
        namespaces.add(namespace)
        assert old.ctl.HELPER.helpers.load_attempt(Path(final['fixed_deal_attempt']['path']), final['fixed_deal_attempt']['sha256']) == final['fixed_deal_attempt']['receipt']
        for name, prefix in old.read(folder/'prefixes.json').items():
            with (folder/name).open('rb') as stream:
                assert hashlib.sha256(stream.read(prefix['bytes'])).hexdigest()==prefix['sha256']
        rows = [r for r in old.ctl.execution.complete_jsonl(folder/'h1_training_metrics.jsonl') if r['iteration']>parent['iteration']]
        assert [r['iteration'] for r in rows]==list(range(parent['iteration']+1,final['iteration']+1))
        physical = final['environment_hand_accounting']['completed_hands']-parent['environment_hand_accounting']['completed_hands']
        transition = final['total_hands']-parent['total_hands']
        replay = final['ppo_replay_cumulative_rows']-parent['ppo_replay_cumulative_rows']
        assert physical>=16384 and transition>0 and replay==sum(r['ppo_replay_rows'] for r in rows)>0
        assert all(r['ppo_replay_ratio']==.5 and r['ppo_replay_buffer_iterations']==2 for r in rows)
        diagnostics = [d for r in rows for d in r['gradient_diagnostics']]
        assert diagnostics and all(d['schema']=='cardpilot.ppo_component_gradients.v1' and d['minibatch']==1 for d in diagnostics)
        groups = {}
        for name in diagnostics[0]['groups']:
            values = [d['groups'][name] for d in diagnostics]
            if all(v['norms']['ppo']>0 for v in values):
                groups[name] = dict(kl_to_ppo_norm=summarize([v['norms']['source_kl']/v['norms']['ppo'] for v in values]),ppo_actor_cosine=summarize([v['cosines']['ppo_vs_actor'] for v in values]),ppo_kl_cosine=summarize([v['cosines']['ppo_vs_source_kl'] for v in values]),clip_scale=summarize([v['hypothetical_clip_scale'] for v in values]))
        assert all(d['groups']['trunk']['norms']['critic']==0 for d in diagnostics)
        results.append(dict(seed=seed,physical_hands=physical,transition_hands=transition,replay_rows=replay,iterations=len(rows),diagnostics=len(diagnostics),groups=groups,optimizer=optimizer,namespace=namespace))
        for name in ('latest.pt','initial_resumed_state.pt','h1_training_metrics.jsonl','opponent_assignments.jsonl','verification.json','gradient_probe.json','command.json','initial_resume_gate.json','mixture_observation.json'):
            hashes[str(folder/name)] = old.sha(folder/name)
        del parent, initial, final
    old.ctl.execution.check_hashes(hashes)
    old.write_new(BASE/'post_review.json',dict(passed=True,runs=results,training_hands=sum(r['physical_hands'] for r in results),transition_hands=sum(r['transition_hands'] for r in results),replay_rows=sum(r['replay_rows'] for r in results),evaluation_hands=0,final_qualification_hands=0,input_sha256=hashes,wall_seconds=terminal['wall_seconds'],review_wall_seconds=time.monotonic()-start,scope='First minibatch of each PPO epoch; weighted pre-clipping/pre-Adam geometry, not effective Adam direction, gradient SNR, causal strength or final benchmark. Statistical managed continuation, not bitwise worker equivalence.'))
    print(json.dumps(dict(passed=True,training_hands=sum(r['physical_hands'] for r in results))))


if __name__=='__main__':
    main()
