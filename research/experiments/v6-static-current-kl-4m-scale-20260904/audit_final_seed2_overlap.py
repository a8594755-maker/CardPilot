"""Reconstruct final stage overlap from frozen per-attempt checkpoint counters."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.alpha_holdem.fixed_deal_resume_integrity import summarize_overlap


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    import torch
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="append", required=True, help="LABEL=CHECKPOINT")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    attempts, inputs = [], []
    for value in args.source:
        label, raw = value.split("=", 1)
        path = Path(raw)
        before = sha(path)
        checkpoint = torch.load(path, map_location="cpu", weights_only=False)
        if before != sha(path):
            raise RuntimeError("source checkpoint changed during read")
        config = checkpoint["config"]
        if config["worker_seed_base"] != 2026300200 or config["fixed_training_deal_start_index"] != 38300000:
            raise RuntimeError("unexpected Seed2 attempt contract")
        attempts.append({"label": label, "config": config,
                         "accounting": checkpoint["environment_hand_accounting"]})
        inputs.append({"path": str(path.resolve()), "sha256": before,
                       "iteration": int(checkpoint["iteration"]),
                       "transition_hands": int(checkpoint["total_hands"]),
                       "physical_hands": int(checkpoint["environment_hand_accounting"]["completed_hands"]),
                       "session_physical_hands": int(checkpoint["environment_hand_accounting"]["session_completed_hands"])})
    if len(attempts) != 3:
        raise ValueError("this registered incident has exactly three attempt prefixes")
    result = summarize_overlap(attempts)
    result["inputs"] = inputs
    result["schema"] = "cardpilot.static_4m_seed2_final_deal_overlap.v1"
    result["physical_stage_increment_matches_attempt_sum"] = (
        result["executed_hands"] == inputs[-1]["physical_hands"] - 2099786)
    if not result["physical_stage_increment_matches_attempt_sum"]:
        raise RuntimeError("physical attempt accounting does not reconcile")
    if args.out.exists():
        if json.loads(args.out.read_text()) != result:
            raise RuntimeError("existing immutable result differs on replay")
        print("Immutable final overlap report replay: PASS")
    else:
        with args.out.open("x", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2, sort_keys=True)
            handle.write("\n")
    print(json.dumps({key: result[key] for key in (
        "executed_hands", "unique_evidenced_deal_identities", "repeated_deal_exposures",
        "physical_stage_increment_matches_attempt_sum")}))


if __name__ == "__main__":
    main()
