"""Disposable hardware-only qualification. Never steps or saves a poker policy."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
SCOPE = ROOT / 'research/experiments/v6-current-kl-scope-transfer-20260905'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--batch', type=int, choices=(16384, 8192, 4096), required=True)
    args = parser.parse_args()
    output = BASE / f'memory_{args.batch}.json'
    assert not output.exists(), 'preserve prior probe'
    assert json.loads((BASE / 'experiment.json').read_text())['status'] == 'RUNNING'
    spec = importlib.util.spec_from_file_location('scope_parent_memory', SCOPE / 'inspect_parents.py')
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    import torch
    torch.set_num_threads(1)
    torch.manual_seed(20263805)
    path = SCOPE / 'derived/seed1_full.pt'
    assert helper.sha(path) == '44d332a0e234b7806933680417095d6d2bcc0daf2779119d5b72bb36ca8c589f'
    started = time.monotonic()
    result = {'batch': args.batch, 'new_training_hands': 0, 'evaluation_hands': 0,
              'optimizer_steps': 0, 'auxiliary_reserved_bytes': 512 * 1024**2,
              'command': [sys.executable, *sys.argv], 'checkpoint_sha256': helper.sha(path),
              'source_sha256': helper.sha(__file__)}
    try:
        checkpoint = torch.load(path, map_location='cpu', weights_only=False)
        model = helper.make_model(checkpoint).cuda().train()
        reference = copy.deepcopy(model).eval().requires_grad_(False)
        optimizer = torch.optim.Adam(model.parameters(), lr=.0003)
        optimizer.load_state_dict(checkpoint['optimizer'])
        reserve = torch.empty(512 * 1024**2, dtype=torch.uint8, device='cuda')
        cards = torch.rand(args.batch, 6, 4, 13, device='cuda')
        actions = torch.rand(args.batch, 25, 4, 5, device='cuda')
        extra = torch.rand(args.batch, 3, device='cuda')
        torch.cuda.reset_peak_memory_stats()
        with torch.no_grad():
            ref_logits, _ = reference(cards, actions, extra)
        logits, values = model(cards, actions, extra)
        log_probs = logits.log_softmax(-1)
        loss = (log_probs.exp() * (log_probs - ref_logits.log_softmax(-1))).sum(-1).mean()
        loss = loss - log_probs[:, 0].mean() + values.square().mean()
        loss.backward()
        torch.cuda.synchronize()
        assert torch.isfinite(loss).item()
        grads = [p.grad for p in model.parameters() if p.grad is not None]
        assert grads and all(torch.isfinite(g).all().item() for g in grads)
        result.update(passed=True, status='PASS', gradient_tensors=len(grads),
                      peak_allocated_bytes=torch.cuda.max_memory_allocated(),
                      peak_reserved_bytes=torch.cuda.max_memory_reserved(),
                      free_bytes_after_probe=torch.cuda.mem_get_info()[0])
    except torch.cuda.OutOfMemoryError as exc:
        result.update(passed=False, status='CUDA_OOM', error=str(exc))
    result['wall_seconds'] = time.monotonic() - started
    with output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
    print(json.dumps(result), flush=True)
    return 0 if result['passed'] else 42


if __name__ == '__main__':
    raise SystemExit(main())
