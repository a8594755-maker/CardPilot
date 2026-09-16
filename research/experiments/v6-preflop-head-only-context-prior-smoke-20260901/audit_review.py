from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import torch


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
ENGINE = (
    ROOT
    / "research/experiments/v6-contextual-preflop-prior-mechanism-smoke-20260901/audit_review.py"
)
PARENT = (
    ROOT
    / "research/experiments/v6-procedural-iter32-soup-preservation-20260901/frozen/treatment.pt"
)


def model_state(checkpoint):
    for key in ("model_state_dict", "model"):
        if isinstance(checkpoint.get(key), dict):
            return checkpoint[key]
    raise ValueError("checkpoint has no model state")


def main() -> None:
    spec = importlib.util.spec_from_file_location("base_mechanism_review", ENGINE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    module.BASE = BASE
    module.PARENT = PARENT
    module.main()

    result_path = BASE / "terminal_review.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    checkpoints = {
        "parent": torch.load(PARENT, map_location="cpu", weights_only=False),
        "control": torch.load(BASE / "control/latest.pt", map_location="cpu", weights_only=False),
        "treatment": torch.load(BASE / "treatment/latest.pt", map_location="cpu", weights_only=False),
    }
    parent = model_state(checkpoints["parent"])
    strict_changes = {}
    strict_scope = True
    for arm in ("control", "treatment"):
        endpoint = model_state(checkpoints[arm])
        names = [name for name in parent if not torch.equal(parent[name], endpoint[name])]
        strict_changes[arm] = names
        strict_scope &= bool(names) and all(
            name.startswith(("preflop_policy_head.", "value_head."))
            for name in names
        )
        strict_scope &= all(
            torch.equal(parent[name], endpoint[name])
            for name in parent
            if name.startswith("policy_head.")
        )
        config = checkpoints[arm].get("config") or {}
        strict_scope &= bool(config.get("preflop_head_only_training"))
        strict_scope &= not bool(config.get("all_policy_heads_only_training"))
    summary = json.loads((BASE / "mechanism/summary.json").read_text(encoding="utf-8"))
    postflop = summary["contexts"]["postflop"]
    postflop_exact = all(
        postflop[label][metric] == 0.0
        for label in ("control_vs_parent", "treatment_vs_parent", "treatment_vs_control")
        for metric in ("mean_total_variation", "greedy_disagreement")
    )
    result["checks"]["strict_preflop_value_tensor_scope"] = bool(strict_scope)
    result["checks"]["postflop_policy_exactly_preserved"] = bool(postflop_exact)
    result["changed_tensors"] = strict_changes
    result["status"] = "PASS" if all(result["checks"].values()) else "FAIL"
    result_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, sort_keys=True))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
