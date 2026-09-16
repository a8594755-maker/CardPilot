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
PREFIXES = (
    "causal_sequence_token.",
    "causal_sequence_convs.",
    "causal_sequence_trunk_norm.",
    "causal_sequence_policy_adapters.",
)


def build(hidden):
    model = AlphaHoldemNet(
        norm_layer="gn",
        critic_contract="critic_v2",
        separate_preflop_head=True,
        causal_sequence_policy_adapter_hidden=hidden,
    )
    with torch.no_grad():
        model(
            torch.zeros(2, 6, 4, 13),
            torch.zeros(2, 25, 4, 5),
            torch.zeros(2, 3),
        )
    return model


def observations(seed=20261035, count=64):
    generator = torch.Generator().manual_seed(seed)
    card = torch.randn(count, 6, 4, 13, generator=generator)
    action = torch.randn(count, 25, 4, 5, generator=generator)
    extra = torch.cat(
        [
            torch.randn(count, 2, generator=generator),
            torch.arange(count).remainder(2).float()[:, None],
        ],
        dim=1,
    )
    return card, action, extra, torch.ones(count, 9)


def test_zero_output_migration_is_exact_and_scope_is_eighteen_tensors():
    checkpoint = torch.load(SOURCE, map_location="cpu", weights_only=False)
    source = build(0)
    source.load_state_dict(checkpoint["model"])
    treatment = build(128)
    result = treatment.load_state_dict(checkpoint["model"], strict=False)
    assert not result.unexpected_keys
    assert len(result.missing_keys) == 18
    assert all(key.startswith(PREFIXES) for key in result.missing_keys)
    source.eval()
    treatment.eval()
    with torch.no_grad():
        source_logits = source(*observations())[0]
        treatment_logits = treatment(*observations())[0]
    assert torch.equal(source_logits, treatment_logits)
    assert treatment.requires_position_feature


def test_checkpoint_loader_reconstructs_causal_sequence_architecture():
    source_checkpoint = torch.load(SOURCE, map_location="cpu", weights_only=False)
    treatment = build(128)
    treatment.load_state_dict(source_checkpoint["model"], strict=False)
    state = treatment.state_dict()
    checkpoint = {
        **source_checkpoint,
        "model": state,
        "causal_sequence_policy_adapter_hidden": 128,
    }
    loaded = v5_mirror_eval.init_actor(checkpoint, state, "cpu")
    assert loaded.causal_sequence_policy_adapter_hidden == 128
    assert len([key for key in state if key.startswith(PREFIXES)]) == 18


def test_new_trainer_flags_are_parseable():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/alpha_holdem/train_v5.py"), "--help"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "--causal-sequence-policy-adapter-hidden" in result.stdout
    assert "--causal-sequence-adapter-only-training" in result.stdout


def test_learned_output_cpu_gpu_parity():
    if not torch.cuda.is_available():
        return
    cpu = build(128).eval()
    generator = torch.Generator().manual_seed(20261036)
    with torch.no_grad():
        for name, parameter in cpu.named_parameters():
            if name.startswith("causal_sequence_policy_adapters.") and name.endswith(
                ("2.weight", "2.bias")
            ):
                parameter.copy_(torch.randn(parameter.shape, generator=generator) * 0.01)
    gpu = build(128).cuda().eval()
    gpu.load_state_dict(cpu.state_dict())
    card, action, extra, mask = observations(20261036)
    with torch.no_grad():
        left = torch.softmax(cpu(card, action, extra, mask)[0], 1).numpy()
        right = torch.softmax(
            gpu(card.cuda(), action.cuda(), extra.cuda(), mask.cuda())[0], 1
        ).cpu().numpy()
    assert float(np.abs(left - right).max()) <= 2e-5
