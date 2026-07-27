"""Collect diverse postflop source-policy states for CFR distillation anchoring.

The artifact stores frozen trunk features and source logits, not actions or a
runtime rule.  A CFR residual adapter can then learn equilibrium targets while
being explicitly regularized to preserve the source policy on ordinary rollout
states outside the solved single-raised-pot topology.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import torch

THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parents[1]
PHASE2_DIR = THIS_DIR / "phase2"
for path in (REPO_ROOT / "scripts", THIS_DIR, PHASE2_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from alpha_holdem.distill_cfr_v55_compact import base_hidden_logits, init_model
from train_population_ppo import parse_mix, real_rollout


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--hands", type=int, default=100_000)
    parser.add_argument("--num-envs", type=int, default=512)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--batch-size", type=int, default=4096)
    parser.add_argument("--seed", type=int, default=20260726)
    parser.add_argument(
        "--opponent-mix",
        default=(
            "self=0.30,heuristic_v3=0.20,scripted_aggro=0.15,"
            "scripted_station=0.15,scripted_jammer=0.10,random=0.10"
        ),
    )
    args = parser.parse_args()
    if not args.source.is_file():
        raise SystemExit(f"missing source checkpoint: {args.source}")
    if args.hands <= 0 or args.num_envs <= 0:
        raise SystemExit("--hands and --num-envs must be positive")

    started = time.time()
    checkpoint = torch.load(args.source, map_location="cpu", weights_only=False)
    state = checkpoint["model"]
    inherited_adapter_hidden = (
        int(state["postflop_policy_adapter.0.weight"].shape[0])
        if "postflop_policy_adapter.0.weight" in state
        else 0
    )
    model = init_model(checkpoint, inherited_adapter_hidden, args.device)
    model.eval()
    opponent_mix = parse_mix(args.opponent_mix)
    print(
        f"Collecting {args.hands:,} source-policy hands with "
        f"{args.num_envs} environments; mix={opponent_mix}",
        flush=True,
    )
    rollout = real_rollout(
        model,
        opponent_mix,
        args.num_envs,
        args.hands,
        args.device,
        seed=args.seed,
    )
    if rollout is None:
        raise SystemExit("rollout produced no source-policy transitions")

    cards = rollout["cards"]
    actions = rollout["actions_obs"]
    extras = rollout["extras"]
    masks = rollout["masks"]
    board_counts = cards[:, 4].sum(dim=(1, 2))
    postflop_indices = torch.where(board_counts >= 2.5)[0]
    if not len(postflop_indices):
        raise SystemExit("rollout produced no postflop source-policy transitions")

    hidden_parts: list[torch.Tensor] = []
    logit_parts: list[torch.Tensor] = []
    mask_parts: list[torch.Tensor] = []
    street_parts: list[torch.Tensor] = []
    with torch.no_grad():
        for start in range(0, len(postflop_indices), args.batch_size):
            idx = postflop_indices[start : start + args.batch_size]
            card = cards[idx]
            action = actions[idx]
            extra = extras[idx]
            mask = masks[idx]
            hidden, _ = base_hidden_logits(model, card, action, extra)
            source_logits, _ = model(card, action, extra)
            hidden_parts.append(hidden.cpu().to(torch.float16))
            logit_parts.append(source_logits.cpu().to(torch.float16))
            mask_parts.append(mask.cpu().to(torch.float16))
            street_parts.append(
                board_counts[idx].round().cpu().to(torch.int8)
            )

    artifact = {
        "schema": "cardpilot.postflop_source_anchor.v1",
        "source_checkpoint": str(args.source),
        "source_checkpoint_sha256": sha256(args.source),
        "obs_version": str(checkpoint.get("obs_version") or "v4"),
        "opponent_mix": opponent_mix,
        "seed": int(args.seed),
        "rollout_hands": int(rollout["n_hero_hands"]),
        "rollout_decisions": int(rollout["n_transitions"]),
        "postflop_decisions": int(len(postflop_indices)),
        "hidden": torch.cat(hidden_parts),
        "source_logits": torch.cat(logit_parts),
        "legal_mask": torch.cat(mask_parts),
        "board_count": torch.cat(street_parts),
        "runtime_seconds": float(time.time() - started),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    torch.save(artifact, args.out)
    print(
        json.dumps(
            {
                "status": "COMPLETE",
                "output": str(args.out),
                "rollout_hands": artifact["rollout_hands"],
                "rollout_decisions": artifact["rollout_decisions"],
                "postflop_decisions": artifact["postflop_decisions"],
                "runtime_seconds": artifact["runtime_seconds"],
            },
            sort_keys=True,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
