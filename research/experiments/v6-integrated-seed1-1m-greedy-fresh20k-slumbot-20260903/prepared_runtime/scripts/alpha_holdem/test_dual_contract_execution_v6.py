from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import torch

from scripts.alpha_holdem.dual_contract_residual_v6 import DualContractResidualPolicy
from scripts.alpha_holdem.execution_v6 import sha256_file
from scripts.alpha_holdem import dual_contract_execution_v6 as execution
from scripts.alpha_holdem.play_slumbot_v6_journaled import run_session


class DummyBase(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.bias = torch.nn.Parameter(torch.zeros(9))

    def forward(self, cards, actions, extras, mask):
        batch = cards.shape[0]
        return self.bias.expand(batch, -1), torch.zeros((batch, 1))


def test_bundle_recovers_hash_bound_architecture_and_rejects_wrong_base(tmp_path):
    base = tmp_path / "base.bin"
    base.write_bytes(b"base")
    parent = tmp_path / "parent.pt"
    torch.save({"hidden": 16, "policy_delta_cap": 0.25}, parent)
    residual_model = DualContractResidualPolicy(DummyBase(), hidden=16, policy_delta_cap=0.25)
    residual_state = {
        key: value.detach().clone()
        for key, value in residual_model.state_dict().items()
        if not key.startswith("base.")
    }
    source = tmp_path / "source.pt"
    torch.save(
        {
            "schema": "cardpilot.dual_contract_residual.v1",
            "base_sha256": sha256_file(base),
            "start_checkpoint": str(parent),
            "start_checkpoint_sha256": sha256_file(parent),
            "dose_hands": 12,
            "residual_state_dict": residual_state,
        },
        source,
    )
    bundle = tmp_path / "bundle.pt"
    metadata = execution.build_deployment_bundle(source, base, bundle)
    assert metadata["hidden"] == 16
    assert metadata["policy_delta_cap"] == 0.25
    assert metadata["source_residual_sha256"] == sha256_file(source)

    fake_base = SimpleNamespace(model=DummyBase(), path=base, sha256=sha256_file(base), device="cpu")
    with patch.object(execution, "load_base_policy", return_value=fake_base):
        loaded = execution.load_policy(bundle, base)
    assert loaded.sha256 == sha256_file(bundle)
    assert loaded.base_sha256 == sha256_file(base)
    assert not any(parameter.requires_grad for parameter in loaded.model.parameters())

    wrong = tmp_path / "wrong.bin"
    wrong.write_bytes(b"wrong")
    with pytest.raises(ValueError, match="base checkpoint identity"):
        execution.load_policy(bundle, wrong)


def test_bundle_rejects_unbound_missing_architecture(tmp_path):
    base = tmp_path / "base.bin"
    base.write_bytes(b"base")
    source = tmp_path / "source.pt"
    torch.save(
        {
            "schema": "cardpilot.dual_contract_residual.v1",
            "base_sha256": sha256_file(base),
            "residual_state_dict": {"x": torch.zeros(1)},
        },
        source,
    )
    with pytest.raises(ValueError, match="omits architecture"):
        execution.build_deployment_bundle(source, base, tmp_path / "bundle.pt")


def test_journal_runner_rejects_either_frozen_artifact_before_session(tmp_path):
    model_path = tmp_path / "model.bin"
    base_path = tmp_path / "base.bin"
    model_path.write_bytes(b"model")
    base_path.write_bytes(b"base")
    with pytest.raises(ValueError, match="Model identity"):
        run_session(
            object(), model_path, "0" * 64, hands=1, seed=1,
            session_id="bad_model", out_dir=tmp_path / "bad_model",
        )
    with pytest.raises(ValueError, match="Additional frozen artifact"):
        run_session(
            object(), model_path, sha256_file(model_path), hands=1, seed=1,
            session_id="bad_base", out_dir=tmp_path / "bad_base",
            frozen_artifacts={str(base_path): "0" * 64},
        )
