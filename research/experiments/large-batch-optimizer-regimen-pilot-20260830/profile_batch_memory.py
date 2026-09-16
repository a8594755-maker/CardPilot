"""Synthetic shape/memory check only; never save or promote scratch weights."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import time

import psutil
import torch

ROOT = Path(__file__).resolve().parents[3]
BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from scripts.alpha_holdem.network_hybrid_h1 import AlphaHoldemNet

SOURCE = ROOT / 'models/baseline/standard10/latest.pt'
EXPECTED_SHA = '91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428'


def source_sha():
    h = hashlib.sha256()
    with SOURCE.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    out = BASE / 'memory_profile.json'
    if out.exists():
        raise RuntimeError('Refusing to overwrite an existing memory-profile result')
    for p in psutil.process_iter(['name', 'cmdline']):
        if (p.info['name'] or '').lower().startswith('python') and any(
            name in ' '.join(p.info['cmdline'] or []) for name in ['train_v5.py', 'v5_mirror_eval.py']
        ):
            raise RuntimeError('Wait for training/evaluation before GPU memory profiling')
    if source_sha() != EXPECTED_SHA or not torch.cuda.is_available():
        raise RuntimeError('Exact source and CUDA device required')
    torch.set_num_threads(1)
    torch.manual_seed(20260900)
    device = 'cuda'
    checkpoint = torch.load(SOURCE, map_location='cpu', weights_only=False)
    model = AlphaHoldemNet(num_actions=9, norm_layer='gn', separate_preflop_head=True,
                          critic_contract='critic_v2').to(device)
    model(torch.zeros(2, 6, 4, 13, device=device), torch.zeros(2, 25, 4, 5, device=device),
          torch.zeros(2, 2, device=device))
    model.load_state_dict(checkpoint['model'], strict=True)
    for name, p in model.named_parameters():
        p.requires_grad_(name.startswith(('policy_head.', 'preflop_policy_head.', 'value_head.')))
    reference = copy.deepcopy(model).eval()
    for p in reference.parameters(): p.requires_grad_(False)
    optimizer = torch.optim.Adam([p for p in model.parameters() if p.requires_grad], lr=.0003)
    capacity = torch.cuda.get_device_properties(0).total_memory
    result = dict(status='RUNNING', device=torch.cuda.get_device_name(0), total_memory_bytes=capacity,
                  source_sha256=EXPECTED_SHA, new_environment_hands=0, saved_policy_checkpoints=0,
                  note='Synthetic tensors and scratch optimizer only; all scratch weight changes discarded.', batches=[])
    try:
        # Hold a 32768-row rollout's inputs while exercising each optimizer batch.
        cards = torch.zeros(32768, 6, 4, 13, device=device)
        cards[:, 0, 0, 0] = 1
        cards[:, 1, 1, 1] = 1
        cards[::2, 4, 0, 2:5] = 1
        actions = torch.zeros(32768, 25, 4, 5, device=device)
        extras = torch.ones(32768, 2, device=device)*.5
        masks = torch.ones(32768, 9, device=device)
        for size in [1024, 16384]:
            torch.cuda.reset_peak_memory_stats()
            started = time.perf_counter()
            idx = torch.arange(size, device=device)
            logits, values = model(cards[idx], actions[idx], extras[idx], masks[idx])
            probs = logits.softmax(-1)
            with torch.no_grad():
                q_logits, _ = reference(cards[idx], actions[idx], extras[idx], masks[idx])
                q = q_logits.softmax(-1)
            kl = (q*(q.clamp_min(1e-8).log()-probs.clamp_min(1e-8).log())).sum(-1).mean()
            loss = -probs[:, 1].clamp_min(1e-8).log().mean()+kl+values.square().mean()
            if not torch.isfinite(loss): raise ValueError('Non-finite scratch loss')
            optimizer.zero_grad()
            loss.backward()
            if not all(p.grad is None or torch.isfinite(p.grad).all() for p in model.parameters()):
                raise ValueError('Non-finite scratch gradient')
            torch.nn.utils.clip_grad_norm_(model.parameters(), .5)
            optimizer.step()
            torch.cuda.synchronize()
            peak = torch.cuda.max_memory_allocated()
            row = dict(batch_size=size, peak_allocated_bytes=peak,
                       peak_reserved_bytes=torch.cuda.max_memory_reserved(),
                       allocated_fraction=peak/capacity, seconds=time.perf_counter()-started,
                       finite_parameters=all(bool(torch.isfinite(p).all()) for p in model.parameters()))
            result['batches'].append(row)
            if peak >= .8*capacity or not row['finite_parameters']:
                raise RuntimeError('Predeclared large-batch memory/numerical gate failed')
        result['status'] = 'PASS'
    except Exception as exc:
        result.update(status='FAIL', error=type(exc).__name__+': '+str(exc))
    if source_sha() != EXPECTED_SHA:
        raise RuntimeError('Original source checkpoint changed')
    out.write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
    print(json.dumps(result))
    if result['status'] != 'PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
