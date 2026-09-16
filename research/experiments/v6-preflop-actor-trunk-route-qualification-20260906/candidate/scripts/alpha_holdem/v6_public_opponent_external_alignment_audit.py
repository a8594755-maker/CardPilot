"""Independently audit recovered public-opponent alignment evidence."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path

import numpy as np


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def close(left, right) -> bool:
    return math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=1e-12)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    with gzip.open(args.raw, "rt", encoding="utf-8") as handle:
        raw = [json.loads(line) for line in handle]
    names = [spec["name"] for spec in manifest["candidates"]]
    grouped = defaultdict(list)
    for row in raw:
        grouped[row["candidate"]].append(row)
    counts = Counter(row["candidate"] for row in raw)
    summary_rows = {row["name"]: row for row in summary["candidates"]}
    canonical = None
    recomputed = {}
    deck_identity = True
    pair_indices = True
    statistics = True
    for name in names:
        rows = sorted(grouped[name], key=lambda row: row["pair_index"])
        pair_indices &= [row["pair_index"] for row in rows] == list(range(4096))
        decks = [row["deck"] for row in rows]
        if canonical is None:
            canonical = decks
        else:
            deck_identity &= decks == canonical
        proxy = float(np.mean([row["candidate_pair_mean_bb"] for row in rows]) * 100.0)
        seat = [
            float(np.mean([row["candidate_rewards_bb"][index] for row in rows]) * 100.0)
            for index in (0, 1)
        ]
        recomputed[name] = {"proxy_bb100": proxy, "seat_bb100": seat}
        statistics &= close(proxy, summary_rows[name]["proxy"]["bb100"])
        statistics &= close(seat[0], summary_rows[name]["seat0"]["bb100"])
        statistics &= close(seat[1], summary_rows[name]["seat1"]["bb100"])
    gates = {
        "raw_sha_matches_summary": sha256_path(args.raw) == summary["raw_sha256"],
        "manifest_sha_matches_summary": (
            sha256_path(args.manifest) == summary["manifest_sha256"]
        ),
        "exact_24576_raw_rows": len(raw) == 24_576,
        "six_candidates_4096_pairs_each": (
            set(counts) == set(names) and set(counts.values()) == {4096}
        ),
        "pair_indices_complete": bool(pair_indices),
        "common_deck_identity_exact": bool(deck_identity),
        "decks_are_permutations": all(
            len(row["deck"]) == 52 and len(set(row["deck"])) == 52 for row in raw
        ),
        "candidate_statistics_recompute": bool(statistics),
        "evaluation_hands_exact": summary["evaluation_hands"] == 49_152,
        "recovery_disclosed": summary["recovered_from_completed_raw"] is True,
        "proxy_rejected": (
            summary["proxy_admitted"] is False
            and summary["decision"] == "REJECT_PUBLIC_OPPONENT_AS_EXTERNAL_ALIGNMENT_PROXY"
        ),
        "all_frozen_input_hashes_match": all(
            sha256_path(Path(spec["checkpoint"])) == spec["checkpoint_sha256"]
            and (
                spec["contract"] != "dual_contract"
                or sha256_path(Path(spec["base_checkpoint"])) == spec["base_sha256"]
            )
            for spec in manifest["candidates"]
        ),
        "public_opponent_hash_matches": (
            sha256_path(Path(manifest["public_opponent_checkpoint"]))
            == manifest["public_opponent_sha256"]
        ),
    }
    output = {
        "schema": "cardpilot.public_opponent_external_alignment_audit.v1",
        "raw_sha256": sha256_path(args.raw),
        "summary_sha256": sha256_path(args.summary),
        "manifest_sha256": sha256_path(args.manifest),
        "candidate_counts": dict(counts),
        "recomputed": recomputed,
        "gates": gates,
        "passed": all(gates.values()),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps(output, sort_keys=True))
    if not output["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
