from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts/alpha_holdem"))
from alpha_holdem.network_hybrid_h1 import AlphaHoldemNet
from alpha_holdem.train_mp3_hybrid_h1 import trinal_clip_ppo_update
from alpha_holdem.train_v5 import encode_opponent_private_cards
from alpha_holdem import v5_mirror_eval

SOURCE = ROOT / "models/baseline/standard10/latest.pt"


def build(hidden):
    model = AlphaHoldemNet(
        norm_layer="gn", critic_contract="critic_v2",
        separate_preflop_head=True, centralized_critic_hidden=hidden,
    )
    with torch.no_grad():
        model(torch.zeros(2, 6, 4, 13), torch.zeros(2, 25, 4, 5), torch.zeros(2, 3))
    return model


def test_private_card_encoder_is_opponent_only():
    state = SimpleNamespace(hole_cards=[(0, 51), (7, 19)])
    p0 = encode_opponent_private_cards(state, player=0)
    p1 = encode_opponent_private_cards(state, player=1)
    assert np.flatnonzero(p0).tolist() == [7, 19]
    assert np.flatnonzero(p1).tolist() == [0, 51]


def test_centralized_head_preserves_actor_and_loader_reconstructs():
    checkpoint = torch.load(SOURCE, map_location="cpu", weights_only=False)
    source = build(0).eval(); source.load_state_dict(checkpoint["model"])
    treatment = build(256).eval(); result = treatment.load_state_dict(checkpoint["model"], strict=False)
    assert not result.unexpected_keys and len(result.missing_keys) == 6
    assert all(key.startswith("centralized_value_head.") for key in result.missing_keys)
    generator = torch.Generator().manual_seed(20261039)
    card = torch.randn(16, 6, 4, 13, generator=generator)
    action = torch.randn(16, 25, 4, 5, generator=generator)
    extra = torch.cat((torch.randn(16, 2, generator=generator), torch.arange(16).remainder(2).float()[:, None]), 1)
    private = torch.zeros(16, 52); private[:, 3] = 1; private[:, 17] = 1
    with torch.no_grad():
        source_logits = source(card, action, extra)[0]
        public_logits, public_value = treatment(card, action, extra)
        private_logits, private_value = treatment(card, action, extra, critic_private_info=private)
    assert torch.equal(source_logits, public_logits) and torch.equal(public_logits, private_logits)
    assert public_value.shape == private_value.shape == (16, 1)
    state = treatment.state_dict()
    loaded = v5_mirror_eval.init_actor({**checkpoint, "model": state}, state, "cpu")
    assert loaded.centralized_critic_hidden == 256


def test_centralized_ppo_recomputes_baselines_and_updates_only_registered_scope():
    model = build(32)
    for name, parameter in model.named_parameters():
        parameter.requires_grad = name.startswith(("policy_head.", "preflop_policy_head.", "centralized_value_head."))
    optimizer = torch.optim.Adam([p for p in model.parameters() if p.requires_grad], lr=1e-4)
    transitions = []
    for index in range(16):
        cards = np.zeros((6, 4, 13), np.float32); cards[0, index % 4, index % 13] = 1
        actions = np.zeros((25, 4, 5), np.float32)
        extra = np.array([1.0, 1.0, float(index % 2)], np.float32)
        mask = np.ones(9, np.float32)
        with torch.no_grad():
            logits, _ = model(torch.tensor(cards[None]), torch.tensor(actions[None]), torch.tensor(extra[None]), torch.tensor(mask[None]))
            lp = float(torch.log_softmax(logits, 1)[0, 1])
        private = np.zeros(52, np.float32); private[(index + 9) % 52] = 1; private[(index + 23) % 52] = 1
        transitions.append((cards.flatten(), actions.flatten(), extra, mask, 1, lp, (-1.0) ** index, 0.0, 1.0, 1.0, 1.0, 1.0, float("nan"), float(index % 2), float("nan"), private))
    frozen = {name: value.detach().clone() for name, value in model.state_dict().items() if not name.startswith(("policy_head.", "preflop_policy_head.", "centralized_value_head."))}
    stats = trinal_clip_ppo_update(model, optimizer, transitions, "cpu", epochs=1, mini_batch_size=8, critic_contract="critic_v2", effective_stack_divisor=200, centralized_critic=True)
    assert stats["centralized_critic"] and np.isfinite(stats["preupdate_critic_mse"])
    assert len(optimizer.state) == 10
    assert all(torch.equal(model.state_dict()[name], value) for name, value in frozen.items())


def test_cli_flags_are_registered():
    result = subprocess.run([sys.executable, str(ROOT / "scripts/alpha_holdem/train_v5.py"), "--help"], cwd=ROOT, check=True, capture_output=True, text=True)
    assert "--centralized-critic-hidden" in result.stdout and "--centralized-critic" in result.stdout
