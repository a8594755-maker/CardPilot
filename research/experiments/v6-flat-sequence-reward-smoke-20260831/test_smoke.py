from pathlib import Path
import subprocess
import sys

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
from alpha_holdem.network_hybrid_h1 import AlphaHoldemNet
from alpha_holdem import v5_mirror_eval


SOURCE = ROOT / "models/baseline/standard10/latest.pt"


def build(hidden):
    model = AlphaHoldemNet(
        norm_layer="gn", critic_contract="critic_v2",
        separate_preflop_head=True,
        flat_sequence_policy_adapter_hidden=hidden,
    )
    with torch.no_grad():
        model(torch.zeros(2, 6, 4, 13), torch.zeros(2, 25, 4, 5), torch.zeros(2, 3))
    return model


def test_zero_output_migration_is_exact_and_scope_is_fourteen_tensors():
    checkpoint = torch.load(SOURCE, map_location="cpu", weights_only=False)
    source = build(0)
    source.load_state_dict(checkpoint["model"])
    treatment = build(128)
    result = treatment.load_state_dict(checkpoint["model"], strict=False)
    assert not result.unexpected_keys
    assert len(result.missing_keys) == 14
    assert all(key.startswith(("flat_sequence_encoder.", "flat_sequence_trunk_norm.", "flat_sequence_policy_adapters.")) for key in result.missing_keys)
    generator = torch.Generator().manual_seed(20261031)
    card = torch.randn(64, 6, 4, 13, generator=generator)
    action = torch.randn(64, 25, 4, 5, generator=generator)
    extra = torch.cat([torch.randn(64, 2, generator=generator), torch.arange(64).remainder(2).float()[:, None]], dim=1)
    mask = torch.ones(64, 9)
    source.eval(); treatment.eval()
    with torch.no_grad():
        source_logits = source(card, action, extra, mask)[0]
        treatment_logits = treatment(card, action, extra, mask)[0]
    assert torch.equal(source_logits, treatment_logits)
    assert treatment.requires_position_feature


def test_checkpoint_loader_reconstructs_flat_sequence_architecture():
    source_checkpoint = torch.load(SOURCE, map_location="cpu", weights_only=False)
    treatment = build(128)
    treatment.load_state_dict(source_checkpoint["model"], strict=False)
    state = treatment.state_dict()
    checkpoint = {**source_checkpoint, "model": state, "flat_sequence_policy_adapter_hidden": 128}
    loaded = v5_mirror_eval.init_actor(checkpoint, state, "cpu")
    assert loaded.flat_sequence_policy_adapter_hidden == 128
    assert len([key for key in state if key.startswith(("flat_sequence_encoder.", "flat_sequence_trunk_norm.", "flat_sequence_policy_adapters."))]) == 14


def test_new_trainer_flags_are_parseable():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/alpha_holdem/train_v5.py"), "--help"],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    assert "--flat-sequence-policy-adapter-hidden" in result.stdout
    assert "--flat-sequence-adapter-only-training" in result.stdout


def test_zero_output_cpu_gpu_parity():
    if not torch.cuda.is_available():
        return
    cpu = build(128).eval()
    gpu = build(128).cuda().eval()
    gpu.load_state_dict(cpu.state_dict())
    generator = torch.Generator().manual_seed(20261032)
    card = torch.randn(64, 6, 4, 13, generator=generator)
    action = torch.randn(64, 25, 4, 5, generator=generator)
    extra = torch.cat([torch.randn(64, 2, generator=generator), torch.arange(64).remainder(2).float()[:, None]], dim=1)
    mask = torch.ones(64, 9)
    with torch.no_grad():
        left = torch.softmax(cpu(card, action, extra, mask)[0], 1).numpy()
        right = torch.softmax(gpu(card.cuda(), action.cuda(), extra.cuda(), mask.cuda())[0], 1).cpu().numpy()
    assert float(np.abs(left - right).max()) <= 2e-5
