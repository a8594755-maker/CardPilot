"""Compare position-teacher candidates on one common unseen decision set."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import torch
from torch.utils.data import DataLoader

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))

from compare_policy_on_slumbot_dumps import load_model
from distill_position_teachers import (
    collect_rows,
    dump_files,
    evaluate,
    stack_rows,
)
from offline_slumbot_awr import sha256_path


def labeled_path(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("candidate must be LABEL=PATH")
    label, raw_path = value.split("=", 1)
    if not label:
        raise argparse.ArgumentTypeError("candidate label is empty")
    path = Path(raw_path).resolve()
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"candidate does not exist: {path}")
    return label, path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", action="append", required=True)
    parser.add_argument("--sb-teacher", required=True)
    parser.add_argument("--bb-teacher", required=True)
    parser.add_argument("--dump-dir", action="append", required=True)
    parser.add_argument("--obs-version", choices=("v4", "v55"), default="v4")
    parser.add_argument(
        "--raise-action-mapping",
        choices=(
            "legacy_total_over_pot",
            "preflop_pot_fraction_v2",
            "pot_fraction_v2",
        ),
        default="legacy_total_over_pot",
    )
    parser.add_argument("--max-rows-per-actor", type=int, default=300_000)
    parser.add_argument("--batch-size", type=int, default=4096)
    parser.add_argument("--teacher-temperature", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=20260883)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--out-json", required=True)
    args = parser.parse_args()

    candidates = [labeled_path(value) for value in args.candidate]
    labels = [label for label, _ in candidates]
    if len(set(labels)) != len(labels):
        raise ValueError("candidate labels must be unique")

    rows, ingest = collect_rows(
        files=dump_files(args.dump_dir),
        max_rows_per_actor=args.max_rows_per_actor,
        seed=args.seed,
        obs_version=args.obs_version,
        raise_action_mapping=args.raise_action_mapping,
    )
    if len(rows) < 10_000:
        raise RuntimeError(f"insufficient held-out rows: {len(rows)}")
    loader = DataLoader(
        stack_rows(rows),
        batch_size=args.batch_size,
        shuffle=False,
        pin_memory=True,
    )

    sb_path = Path(args.sb_teacher).resolve()
    bb_path = Path(args.bb_teacher).resolve()
    sb_teacher, _ = load_model(sb_path, args.device)
    bb_teacher, _ = load_model(bb_path, args.device)
    for teacher in (sb_teacher, bb_teacher):
        teacher.eval()
        for parameter in teacher.parameters():
            parameter.requires_grad_(False)

    results: dict[str, Any] = {}
    for label, path in candidates:
        candidate, checkpoint = load_model(path, args.device)
        candidate.eval()
        results[label] = {
            "path": str(path),
            "sha256": sha256_path(path),
            "position_adapter_hidden": int(
                checkpoint.get(
                    "position_adapter_hidden",
                    getattr(candidate, "position_adapter_hidden", 0),
                )
            ),
            "metrics": evaluate(
                candidate,
                sb_teacher,
                bb_teacher,
                loader,
                args.device,
                args.teacher_temperature,
            ),
        }
        del candidate

    payload = {
        "schema": "cardpilot.position_teacher_common_holdout.v1",
        "note": (
            "Common unseen states compare neural-teacher fidelity only; "
            "this is not an external EV estimate."
        ),
        "sb_teacher": str(sb_path),
        "sb_teacher_sha256": sha256_path(sb_path),
        "bb_teacher": str(bb_path),
        "bb_teacher_sha256": sha256_path(bb_path),
        "dump_files": [str(path) for path in dump_files(args.dump_dir)],
        "ingest": ingest,
        "config": {
            "obs_version": args.obs_version,
            "raise_action_mapping": args.raise_action_mapping,
            "max_rows_per_actor": args.max_rows_per_actor,
            "batch_size": args.batch_size,
            "teacher_temperature": args.teacher_temperature,
            "seed": args.seed,
            "device": args.device,
        },
        "candidates": results,
    }
    out = Path(args.out_json).resolve()
    if out.exists():
        raise FileExistsError(f"refusing to overwrite: {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
