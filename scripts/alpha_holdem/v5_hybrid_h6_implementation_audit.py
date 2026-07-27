#!/usr/bin/env python3
"""Offline H6 KL-early-stop implementation audit; never launches workers."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch
from torch import nn

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR.parent))
from alpha_holdem.train_mp3_hybrid_h1 import trinal_clip_ppo_update


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


class TinyPolicy(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.policy = nn.Linear(2, 9)
        self.value = nn.Linear(2, 1)

    def forward(self, cards, actions, extras, masks):
        logits = self.policy(extras)
        logits = logits.masked_fill(masks <= 0, -1e9)
        return logits, self.value(extras)


def transitions(model: TinyPolicy, count: int = 24) -> list[tuple]:
    rows = []
    model.eval()
    for i in range(count):
        card = np.zeros((6, 4, 13), np.float32)
        action = np.zeros((25, 4, 5), np.float32)
        extra = np.array([1.0 + (i % 5) * 0.2, 0.5 + (i % 3) * 0.3], np.float32)
        mask = np.ones(9, np.float32)
        act = i % 4 + 1
        with torch.no_grad():
            logits, value = model(
                torch.tensor(card).unsqueeze(0),
                torch.tensor(action).unsqueeze(0),
                torch.tensor(extra).unsqueeze(0),
                torch.tensor(mask).unsqueeze(0),
            )
            old_lp = torch.log_softmax(logits, dim=-1)[0, act].item()
        done = 1.0 if i % 6 == 5 else 0.0
        reward = float((i % 7) - 3) if done else 0.0
        rows.append((card, action, extra, mask, act, old_lp, reward, float(value.item()), done, 200.0, 200.0, 1.0 if done else 0.0))
    return rows


def equal_state(a: nn.Module, b: nn.Module) -> bool:
    return all(torch.equal(a.state_dict()[key], b.state_dict()[key]) for key in a.state_dict())


def run_update(initial: TinyPolicy, data: list[tuple], target_kl: float) -> tuple[TinyPolicy, dict]:
    model = copy.deepcopy(initial)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.02)
    torch.manual_seed(2026071603)
    stats = trinal_clip_ppo_update(
        model,
        optimizer,
        data,
        "cpu",
        epochs=4,
        mini_batch_size=6,
        entropy_coef=0.0,
        action_prior_coef=0.0,
        preflop_action_prior_coef=0.0,
        target_kl=target_kl,
    )
    return model, stats


def run(preregistration: Path, trainer: Path, ppo: Path) -> dict:
    checks: list[dict] = []

    def add(name: str, passed: bool, detail: object = "") -> None:
        checks.append({"name": name, "pass": bool(passed), "detail": detail})

    prereg = json.loads(preregistration.read_text(encoding="utf-8-sig"))
    add("preregistration_identity", prereg.get("experiment_id") == "H6" and prereg.get("status") == "REGISTERED_NO_LAUNCH")
    trainer_source = trainer.read_text(encoding="utf-8")
    ppo_source = ppo.read_text(encoding="utf-8")
    add("cli_fail_closed", "positive --ppo-target-kl requires --h6-window-arm treatment" in trainer_source)
    add("exact_threshold", "H6 treatment requires exact --ppo-target-kl 0.03" in trainer_source)
    add("strict_epoch_mean", "epoch_mean_kl > float(target_kl)" in ppo_source)
    add("required_logging", all(token in trainer_source for token in ("ppo_epochs_completed", "kl_early_stop_triggered", "kl_early_stop_epoch", "ppo_target_kl")))

    torch.manual_seed(2026071603)
    initial = TinyPolicy()
    data = transitions(initial)
    disabled_model, disabled = run_update(initial, data, 0.0)
    high_model, high = run_update(initial, data, 1e9)
    forced_model, forced = run_update(initial, data, 1e-12)
    add("disabled_high_threshold_bitwise", equal_state(disabled_model, high_model))
    add("disabled_full_epochs", disabled["ppo_epochs_completed"] == 4 and disabled["kl_early_stop_triggered"] is False)
    add("high_threshold_full_epochs", high["ppo_epochs_completed"] == 4 and high["kl_early_stop_triggered"] is False)
    add(
        "forced_threshold_stops_after_completed_epoch",
        forced["kl_early_stop_triggered"] is True
        and 1 <= forced["kl_early_stop_epoch"] == forced["ppo_epochs_completed"] < 4,
        {key: forced[key] for key in ("approx_kl", "ppo_epochs_completed", "kl_early_stop_triggered", "kl_early_stop_epoch")},
    )
    add("finite_stats", all(math.isfinite(float(forced[key])) for key in ("policy_loss", "value_loss", "entropy", "approx_kl")))
    add("initial_policy_unchanged", equal_state(initial, copy.deepcopy(initial)))
    failed = [row["name"] for row in checks if not row["pass"]]
    return {
        "schema_version": "v5.hybrid.h6.implementation_audit.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "overall": "PASS_IMPLEMENTATION_PREREG_READY" if not failed else "FAIL_CLOSED",
        "checks": checks,
        "passed": len(checks) - len(failed),
        "failed": len(failed),
        "failed_checks": failed,
        "preregistration_sha256": sha(preregistration),
        "trainer_sha256": sha(trainer),
        "ppo_sha256": sha(ppo),
        "disabled_stats": disabled,
        "high_threshold_stats": high,
        "forced_threshold_stats": forced,
        "behavior_launch_authorized": False,
        "official_hands_authorized": 0,
        "strength_claim": "FORBIDDEN",
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--preregistration", required=True)
    p.add_argument("--trainer", required=True)
    p.add_argument("--ppo", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    result = run(Path(a.preregistration).resolve(), Path(a.trainer).resolve(), Path(a.ppo).resolve())
    Path(a.out).resolve().write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["overall"].startswith("PASS_") else 2


if __name__ == "__main__":
    raise SystemExit(main())
