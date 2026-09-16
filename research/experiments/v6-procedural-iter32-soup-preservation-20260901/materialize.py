"""Materialize the preregistered 75% iter32 actor-update soups."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path

import torch


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
PARENT = ROOT / "research/experiments/v6-actor-ema-terminal-smoke-20260831/frozen/raw.pt"
CONTROL = ROOT / (
    "research/experiments/v6-procedural-opponent-domain-randomization-pilot-20260901/"
    "control/checkpoints/checkpoint_iter000032_hands000000132038.pt"
)
TREATMENT = ROOT / (
    "research/experiments/v6-procedural-opponent-domain-randomization-pilot-20260901/"
    "treatment/checkpoints/checkpoint_iter000032_hands000000131971.pt"
)
EXPECTED_SHA256 = {
    "parent": "9fd38ad30ba25f46a80d2a103b55bb5a64affb7979a2fa47504cc187d38a2bf4",
    "control": "fe232a82842861738e4b89e35fce9cb8fe5119b3a722911e48f137c05a18b93d",
    "treatment": "fc30b57a63e852740937165b62de2c8a8343cd515870eff566019be2bb27ef11",
}
ALPHA = 0.75
ACTOR_NAMES = (
    "policy_head.weight",
    "policy_head.bias",
    "preflop_policy_head.weight",
    "preflop_policy_head.bias",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def interpolate(
    parent: dict[str, torch.Tensor],
    source: dict[str, torch.Tensor],
    alpha: float = ALPHA,
    actor_names: tuple[str, ...] = ACTOR_NAMES,
) -> dict[str, torch.Tensor]:
    if not 0.0 <= alpha <= 1.0:
        raise ValueError("alpha must be in [0, 1]")
    if set(parent) != set(source):
        raise ValueError("checkpoint model-state keys differ")
    result = {name: tensor.detach().cpu().clone() for name, tensor in parent.items()}
    for name in actor_names:
        parent_tensor = parent[name].detach().cpu()
        source_tensor = source[name].detach().cpu()
        result[name] = torch.lerp(parent_tensor, source_tensor, alpha).to(parent_tensor.dtype)
    return result


def materialize(
    parent_checkpoint: dict,
    source_checkpoint: dict,
    source_label: str,
) -> dict:
    candidate = copy.deepcopy(parent_checkpoint)
    candidate["model"] = interpolate(parent_checkpoint["model"], source_checkpoint["model"])
    candidate["run_id"] = f"v6_procedural_iter32_{source_label}_actor_soup_a075_20260901"
    candidate["deployed_actor_variant"] = "procedural_iter32_actor_update_soup"
    candidate["actor_weight_soup"] = {
        "schema": "cardpilot.actor_update_weight_soup.v1",
        "parent_sha256": EXPECTED_SHA256["parent"],
        "source_sha256": EXPECTED_SHA256[source_label],
        "parent_weight": 1.0 - ALPHA,
        "source_weight": ALPHA,
        "actor_tensors": list(ACTOR_NAMES),
        "source_label": source_label,
    }
    candidate.setdefault("config", {})["deployed_actor_variant"] = candidate[
        "deployed_actor_variant"
    ]
    return candidate


def save_atomic(value: dict, path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    torch.save(value, temporary)
    os.replace(temporary, path)


def main() -> None:
    output_dir = BASE / "frozen"
    manifest_path = BASE / "materialization.json"
    if output_dir.exists() or manifest_path.exists():
        raise FileExistsError("fixed one-shot materialization already exists")
    inputs = {"parent": PARENT, "control": CONTROL, "treatment": TREATMENT}
    actual_inputs = {name: sha256(path) for name, path in inputs.items()}
    if actual_inputs != EXPECTED_SHA256:
        raise ValueError(f"frozen input hash mismatch: {actual_inputs}")
    checkpoints = {
        name: torch.load(path, map_location="cpu", weights_only=False)
        for name, path in inputs.items()
    }
    output_dir.mkdir()
    outputs: dict[str, dict[str, str]] = {}
    parent_model = checkpoints["parent"]["model"]
    for arm in ("control", "treatment"):
        candidate = materialize(checkpoints["parent"], checkpoints[arm], arm)
        for name, tensor in candidate["model"].items():
            if name not in ACTOR_NAMES and not torch.equal(tensor, parent_model[name]):
                raise AssertionError(f"non-actor tensor changed: {arm}:{name}")
        path = output_dir / f"{arm}.pt"
        save_atomic(candidate, path)
        loaded = torch.load(path, map_location="cpu", weights_only=False)
        if loaded["actor_weight_soup"] != candidate["actor_weight_soup"]:
            raise AssertionError(f"metadata round-trip mismatch: {arm}")
        outputs[arm] = {"path": path.relative_to(ROOT).as_posix(), "sha256": sha256(path)}
    manifest = {
        "schema": "cardpilot.actor_update_soup_materialization.v1",
        "alpha": ALPHA,
        "actor_tensors": list(ACTOR_NAMES),
        "inputs": {
            name: {"path": path.relative_to(ROOT).as_posix(), "sha256": actual_inputs[name]}
            for name, path in inputs.items()
        },
        "outputs": outputs,
        "non_actor_tensors_parent_identical": True,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, sort_keys=True))


if __name__ == "__main__":
    main()
