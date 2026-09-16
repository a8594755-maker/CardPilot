from pathlib import Path
import sys

import torch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
from alpha_holdem.network_hybrid_h1 import AlphaHoldemNet
from alpha_holdem import v5_mirror_eval

SOURCE = ROOT / "models/baseline/standard10/latest.pt"
PREFIXES = (
    "causal_sequence_token.", "causal_sequence_convs.",
    "causal_sequence_trunk_norm.", "causal_sequence_policy_adapters.",
)


def build(hidden):
    model = AlphaHoldemNet(
        norm_layer="gn", critic_contract="critic_v2",
        separate_preflop_head=True,
        causal_sequence_policy_adapter_hidden=hidden,
    )
    with torch.no_grad():
        model(torch.zeros(2, 6, 4, 13), torch.zeros(2, 25, 4, 5), torch.zeros(2, 3))
    return model


def test_behavior_neutral_migration_has_exact_eighteen_tensor_scope():
    checkpoint = torch.load(SOURCE, map_location="cpu", weights_only=False)
    source = build(0).eval(); source.load_state_dict(checkpoint["model"])
    treatment = build(128).eval(); result = treatment.load_state_dict(checkpoint["model"], strict=False)
    assert not result.unexpected_keys and len(result.missing_keys) == 18
    assert all(key.startswith(PREFIXES) for key in result.missing_keys)
    generator = torch.Generator().manual_seed(20261037)
    card = torch.randn(32, 6, 4, 13, generator=generator)
    action = torch.randn(32, 25, 4, 5, generator=generator)
    extra = torch.cat((torch.randn(32, 2, generator=generator), torch.arange(32).remainder(2).float()[:, None]), 1)
    with torch.no_grad():
        assert torch.equal(source(card, action, extra)[0], treatment(card, action, extra)[0])


def test_checkpoint_loader_and_scope():
    checkpoint = torch.load(SOURCE, map_location="cpu", weights_only=False)
    treatment = build(128); treatment.load_state_dict(checkpoint["model"], strict=False)
    state = treatment.state_dict()
    loaded = v5_mirror_eval.init_actor({**checkpoint, "model": state}, state, "cpu")
    assert loaded.causal_sequence_policy_adapter_hidden == 128
    assert len([key for key in state if key.startswith(PREFIXES)]) == 18


def test_preregistered_gate_requires_both_lcbs_and_three_anchors():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from run_pilot import gate
    estimate = lambda lower: {"ci95": [lower, lower + 1]}
    assert gate(estimate(0.1), estimate(0.2), [1, -1, 2, -2, 3])
    assert not gate(estimate(-0.1), estimate(0.2), [1, 1, 1, 1, 1])
    assert not gate(estimate(0.1), estimate(0.2), [1, -1, 2, -2, -3])
