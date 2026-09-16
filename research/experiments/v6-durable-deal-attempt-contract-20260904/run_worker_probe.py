"""Isolated CPU real-worker probe; production trainer source is not changed."""
from functools import partial
import hashlib
import json
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
FIXTURE = ROOT / "research/experiments/v6-multi-rollout-contract-audit-20260831"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(FIXTURE))
import run_audit as fixture
from scripts.alpha_holdem.fixed_deal_attempt import allocate_attempt, attempt_deck

ORIGINAL_RUNTIME = fixture.runtime
ORIGINAL_WORKER = fixture.worker_entry


def namespaced_runtime(namespace):
    np, trainer, environment = ORIGINAL_RUNTIME()
    trainer.fixed_training_deck = partial(attempt_deck, namespace=namespace)
    return np, trainer, environment


def namespaced_worker(mode, slots, kwargs, events, *, namespace):
    # This replacement exists only in the newly spawned diagnostic interpreter.
    fixture.runtime = partial(namespaced_runtime, namespace)
    ORIGINAL_WORKER(mode, slots, kwargs, events)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    out = BASE / "worker_probe"
    out.mkdir(exist_ok=False)
    production = ROOT / "scripts/alpha_holdem/train_v5.py"
    before = sha(production)
    fixture.TARGET = 8
    reports, blocks = [], []
    for mode, slots in (("single", 1), ("multi", 2)):
        claim = allocate_attempt(out / "attempt_receipts", run_id=f"validation_{mode}",
                                 training_seed=19, worker_seed_base=fixture.SEED,
                                 workers=1, envs_per_worker=slots,
                                 parent_checkpoint_sha256=None)
        namespace = claim["receipt"]["namespace"]
        fixture.runtime = partial(namespaced_runtime, namespace)
        fixture.worker_entry = partial(namespaced_worker, namespace=namespace)
        summary, hand_blocks = fixture.run_case(mode, slots, "passive_self", out / mode)
        summary["attempt_receipt"] = claim
        reports.append(summary)
        blocks.append(hand_blocks)
    assert before == sha(production), "production trainer changed during isolated probe"
    # The same worker seed/env0/index0 must generate distinct decks across attempts.
    first = [next(row for row in rows if row["slot"] == 0 and row["deal_index"] == 0)
             for rows in blocks]
    assert first[0]["deck_sha256"] != first[1]["deck_sha256"]
    result = {"schema": "cardpilot.durable_attempt_real_worker_probe.v1", "passed": True,
              "production_source_unchanged": True, "production_source_sha256": before,
              "worker_validation_hands": sum(r["worker_validation_hands"] for r in reports),
              "reference_replay_hands": sum(r["reference_replay_hands"] for r in reports),
              "cases": reports, "learned_training_hands": 0, "slumbot_hands": 0,
              "integration_scope": "isolated worker dependency injection, not production CLI integration"}
    (out / "summary.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "cases"}))


if __name__ == "__main__":
    main()
