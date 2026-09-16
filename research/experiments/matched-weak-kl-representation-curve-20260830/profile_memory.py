"""Zero-hand scratch full-network memory/gradient feasibility, never a policy."""
import copy
import json
from pathlib import Path
import sys
import time

import psutil
import torch

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
from run_pilot import ROOT, SOURCE, DIGESTS, sha
from scripts.alpha_holdem.network_hybrid_h1 import AlphaHoldemNet


def main():
    out = BASE/'memory_profile.json'
    if out.exists():
        raise RuntimeError('Refuse to overwrite previous profile')
    for process in psutil.process_iter(['name', 'cmdline']):
        if (process.info['name'] or '').lower().startswith('python') and any(
                Path(arg).name in ['train_v5.py', 'v5_mirror_eval.py', 'play_slumbot.py']
                for arg in process.info['cmdline'] or []):
            raise RuntimeError('A poker training/evaluation process is live')
    if sha(SOURCE) != DIGESTS[0] or not torch.cuda.is_available():
        raise ValueError('Original frozen source and CUDA required')
    torch.set_num_threads(1)
    torch.manual_seed(2026091100)
    checkpoint = torch.load(SOURCE, map_location='cpu', weights_only=False)
    device = 'cuda'
    capacity = torch.cuda.get_device_properties(0).total_memory
    result = dict(status='RUNNING', source_sha256=DIGESTS[0], new_environment_hands=0,
        saved_policy_checkpoints=0, device=torch.cuda.get_device_name(0),
        total_memory_bytes=capacity, scope='full', batch_size=1024, retained_input_rows=32768,
        scratch_only=True, note='Synthetic non-poker inputs; scratch optimizer and weights discarded.')
    try:
        model = AlphaHoldemNet(num_actions=9, norm_layer='gn', separate_preflop_head=True,
                              critic_contract='critic_v2').to(device)
        model(torch.zeros(2,6,4,13,device=device),torch.zeros(2,25,4,5,device=device),torch.zeros(2,2,device=device))
        model.load_state_dict(checkpoint['model'], strict=True)
        for parameter in model.parameters():
            parameter.requires_grad_(True)
        reference = copy.deepcopy(model).eval()
        for parameter in reference.parameters():
            parameter.requires_grad_(False)
        optimizer = torch.optim.Adam(model.parameters(), lr=.00003)
        cards = torch.rand(32768,6,4,13,device=device)
        cards[::2,4] = 0  # Exercise both native preflop and postflop branches.
        actions = torch.rand(32768,25,4,5,device=device)
        extras = torch.rand(32768,2,device=device)
        masks = torch.ones(32768,9,device=device)
        torch.cuda.reset_peak_memory_stats()
        started = time.perf_counter()
        logits, values = model(cards[:1024],actions[:1024],extras[:1024],masks[:1024])
        p = logits.softmax(-1)
        with torch.no_grad():
            q_logits, _ = reference(cards[:1024],actions[:1024],extras[:1024],masks[:1024])
            q = q_logits.softmax(-1)
        kl = (q*(q.clamp_min(1e-8).log()-p.clamp_min(1e-8).log())).sum(-1).mean()
        loss = -p[:,1].clamp_min(1e-8).log().mean()+.01*kl+values.square().mean()
        if not torch.isfinite(loss):
            raise ValueError('Nonfinite scratch loss')
        optimizer.zero_grad()
        loss.backward()
        if any(v.grad is None or not torch.isfinite(v.grad).all() for v in model.parameters()):
            raise ValueError('Missing or nonfinite scratch gradients')
        torch.nn.utils.clip_grad_norm_(model.parameters(),.5)
        optimizer.step()
        torch.cuda.synchronize()
        changed = [name for name,value in model.state_dict().items()
                   if not torch.equal(value.cpu(),checkpoint['model'][name])]
        representation = [name for name in changed if not name.startswith(
            ('policy_head.','preflop_policy_head.','value_head.'))]
        peak = torch.cuda.max_memory_allocated()
        result.update(peak_allocated_bytes=peak,peak_reserved_bytes=torch.cuda.max_memory_reserved(),
            allocated_fraction=peak/capacity,seconds=time.perf_counter()-started,
            changed_tensors=changed,changed_representation_tensors=len(representation),
            trainable_parameter_tensors=sum(1 for v in model.parameters() if v.requires_grad),
            trainable_parameters=sum(v.numel() for v in model.parameters() if v.requires_grad),
            finite_parameters=all(bool(torch.isfinite(v).all()) for v in model.parameters()),
            finite_optimizer=all(not isinstance(v,torch.Tensor) or bool(torch.isfinite(v).all())
                for state in optimizer.state.values() for v in state.values()))
        if peak >= .8*capacity or len(representation)!=76 or len(changed)!=86 or not result['finite_parameters'] or not result['finite_optimizer']:
            raise ValueError('Prespecified full-scope/memory/numerical gate failed')
        result['status']='PASS'
    except Exception as exc:
        result.update(status='FAIL',error=type(exc).__name__+': '+str(exc))
    if sha(SOURCE)!=DIGESTS[0]:
        raise ValueError('Source changed during scratch profile')
    out.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps(result))
    if result['status']!='PASS':
        raise SystemExit(1)


if __name__=='__main__':
    main()
