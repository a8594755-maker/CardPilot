#!/usr/bin/env python3
"""Run paired greedy/callguard Slumbot diagnostics from one frozen checkpoint.

This is diagnostic-only. It exists to measure whether the same checkpoint is
still relying on a preflop selector guard to avoid the greedy fold/raise leak.
It must not be used for L5/L6 claims.
"""

from __future__ import annotations

import argparse
import glob
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from v5_slumbot_benchmark_plan import evaluate as evaluate_plan
from v5_slumbot_benchmark_plan import write_markdown as write_plan_markdown
from v5_slumbot_benchmark_watch import freeze_checkpoint, run_artifact_audit, run_benchmark, run_hand_review


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        obj = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def policy_tag(policy: str) -> str:
    return {
        "greedy": "greedy",
        "preflop-callguard": "callguard",
    }.get(policy, policy.replace("-", "_"))


def make_plan_args(args: argparse.Namespace, *, policy_mode: str, tag: str) -> argparse.Namespace:
    return argparse.Namespace(
        run_dir=args.run_dir,
        checkpoint=args.checkpoint,
        stage="quick5k",
        tag=tag,
        output_dir=args.output_dir,
        sessions=args.sessions,
        hands_per_session=args.hands_per_session,
        min_training_hands=args.min_training_hands,
        allow_early=False,
        allow_existing_output=True,
        promotion_gate_json="",
        no_require_promotion20k=True,
        no_require_quality_gate=True,
        max_health_age_seconds=args.max_health_age_seconds,
        no_health_age_check=False,
        policy_mode=policy_mode,
        temperature=args.temperature,
        guarded_allin_max_spr=args.guarded_allin_max_spr,
        guarded_allin_min_prob=args.guarded_allin_min_prob,
        callguard_min_prob=args.callguard_min_prob,
        callguard_ratio=args.callguard_ratio,
        callguard_include_open=False,
    )


def make_run_args(plan_args: argparse.Namespace) -> argparse.Namespace:
    return argparse.Namespace(
        policy_mode=plan_args.policy_mode,
        temperature=plan_args.temperature,
        guarded_allin_max_spr=plan_args.guarded_allin_max_spr,
        guarded_allin_min_prob=plan_args.guarded_allin_min_prob,
        callguard_min_prob=plan_args.callguard_min_prob,
        callguard_ratio=plan_args.callguard_ratio,
        callguard_include_open=plan_args.callguard_include_open,
    )


def write_pair_markdown(path: Path, status: dict[str, Any]) -> None:
    results = status.get("results") or {}
    greedy_result = results.get("greedy") or {}
    callguard_result = results.get("preflop-callguard") or {}
    greedy = (greedy_result.get("ci_summary") or {})
    callguard = (callguard_result.get("ci_summary") or {})
    delta = status.get("delta_callguard_vs_greedy_bb_per_100")
    lines = [
        "# V5 Selector Pair Diagnostic",
        "",
        f"- Checked at: `{status.get('checked_at')}`",
        f"- State: **{status.get('state')}**",
        f"- Run dir: `{status.get('run_dir')}`",
        f"- Frozen checkpoint: `{status.get('frozen_checkpoint')}`",
        f"- Frozen iteration / hands: `{(status.get('frozen_summary') or {}).get('iteration')}` / `{(status.get('frozen_summary') or {}).get('total_hands')}`",
        f"- Planned hands per policy: `{status.get('planned_hands_per_policy')}`",
        "",
        "Results:",
        "",
        f"- Greedy bb/100: `{greedy.get('bb_per_100')}` over `{greedy.get('hands')}` hands; CI lower `{greedy.get('lower_bound_bb_per_100')}`",
        f"- Callguard bb/100: `{callguard.get('bb_per_100')}` over `{callguard.get('hands')}` hands; CI lower `{callguard.get('lower_bound_bb_per_100')}`",
        f"- Callguard - greedy delta bb/100: `{delta}`",
        f"- Greedy SB open fold/call/raise/all-in: `{loss_rates_line(greedy_result)}`",
        f"- Greedy BB vs open call/raise: `{bb_rates_line(greedy_result)}`",
        f"- Greedy artifact audit: `{artifact_audit_line(greedy_result)}`",
        f"- Greedy hand review: `{hand_review_line(greedy_result)}`",
        f"- Callguard SB open fold/call/raise/all-in: `{loss_rates_line(callguard_result)}`",
        f"- Callguard BB vs open call/raise: `{bb_rates_line(callguard_result)}`",
        f"- Callguard artifact audit: `{artifact_audit_line(callguard_result)}`",
        f"- Callguard hand review: `{hand_review_line(callguard_result)}`",
        "",
        "Scope:",
        "",
        "- Diagnostic only. This is not promotion evidence and cannot support L5/L6 claims.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def fmt_rate(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, (int, float)):
        return f"{float(value):.3f}"
    return str(value)


def loss_rates_line(result: dict[str, Any]) -> str:
    loss_report = result.get("loss_report_summary") if isinstance(result.get("loss_report_summary"), dict) else {}
    rates = loss_report.get("rates") if isinstance(loss_report.get("rates"), dict) else {}
    return " / ".join(
        [
            fmt_rate(rates.get("sb_open_fold_rate")),
            fmt_rate(rates.get("sb_open_call_rate")),
            fmt_rate(rates.get("sb_open_raise_rate")),
            fmt_rate(rates.get("sb_open_allin_rate")),
        ]
    )


def bb_rates_line(result: dict[str, Any]) -> str:
    loss_report = result.get("loss_report_summary") if isinstance(result.get("loss_report_summary"), dict) else {}
    rates = loss_report.get("rates") if isinstance(loss_report.get("rates"), dict) else {}
    return " / ".join(
        [
            fmt_rate(rates.get("bb_vs_open_call_rate")),
            fmt_rate(rates.get("bb_vs_open_raise_rate")),
        ]
    )


def artifact_audit_line(result: dict[str, Any]) -> str:
    audit = result.get("artifact_audit") if isinstance(result.get("artifact_audit"), dict) else {}
    if not audit:
        return "n/a"
    detail = audit.get("out_md") or audit.get("out_json") or ""
    if detail:
        return f"{audit.get('overall')} ({detail})"
    return str(audit.get("overall"))


def hand_review_line(result: dict[str, Any]) -> str:
    review = result.get("hand_review") if isinstance(result.get("hand_review"), dict) else {}
    if not review:
        return "n/a"
    detail = review.get("out_md") or review.get("out_json") or ""
    base = f"{review.get('overall')} / {review.get('training_adjustment')}"
    if detail:
        return f"{base} ({detail})"
    return base


def glob_status(pattern: str) -> dict[str, Any]:
    matches = sorted(glob.glob(pattern))
    return {"pattern": pattern, "match_count": len(matches), "matches_tail": matches[-5:]}


def existing_result(plan: dict[str, Any], run_args: argparse.Namespace) -> dict[str, Any] | None:
    artifacts = plan.get("artifacts") if isinstance(plan.get("artifacts"), dict) else {}
    ci_json = Path(str(artifacts.get("ci_json") or ""))
    if not ci_json.exists():
        return None
    promotion_json = Path(str(artifacts.get("promotion_json") or ""))
    if not promotion_json.exists():
        return None
    loss_report_json = Path(str(artifacts.get("loss_report_json") or ""))
    loss_report_md = Path(str(artifacts.get("loss_report_md") or ""))
    if not loss_report_json.exists() or not loss_report_md.exists():
        return None
    hands_status = glob_status(str(artifacts.get("hands_glob") or ""))
    dump_status = glob_status(str(artifacts.get("dump_glob") or ""))
    if int(hands_status.get("match_count") or 0) <= 0 or int(dump_status.get("match_count") or 0) <= 0:
        return None
    loss_report = load_json(loss_report_json)
    rates = loss_report.get("rates") if isinstance(loss_report, dict) and isinstance(loss_report.get("rates"), dict) else {}
    if rates.get("sb_open_call_rate") is None or rates.get("sb_open_raise_rate") is None:
        return None
    artifact_audit = run_artifact_audit(plan)
    if artifact_audit.get("overall") != "PASS":
        return None
    hand_review = run_hand_review(plan)
    if hand_review.get("overall") in {"MISSING_CI", "INCOMPLETE"}:
        return None
    return {
        "status": "PASS",
        "returncode": 0,
        "elapsed_seconds": 0.0,
        "command": "reused existing diagnostic artifact",
        "policy": {
            "policy_mode": run_args.policy_mode,
            "temperature": float(run_args.temperature),
            "guarded_allin_max_spr": float(run_args.guarded_allin_max_spr),
            "guarded_allin_min_prob": float(run_args.guarded_allin_min_prob),
            "callguard_min_prob": float(run_args.callguard_min_prob),
            "callguard_ratio": float(run_args.callguard_ratio),
            "callguard_include_open": bool(run_args.callguard_include_open),
        },
        "orchestrator_log": None,
        "orchestrator_err": None,
        "artifact_status": {
            "ci_json": True,
            "promotion_json": True,
            "loss_report_json": True,
            "loss_report_md": True,
            "hands_glob": hands_status,
            "dump_glob": dump_status,
        },
        "artifact_audit": artifact_audit,
        "hand_review": hand_review,
        "ci_summary": load_json(ci_json),
        "loss_report_summary": loss_report,
        "promotion_summary": load_json(promotion_json),
        "checked_at": now_iso(),
        "reused_existing": True,
    }


def run_refresh_reports(run_dir: Path, output_dir: str) -> None:
    commands = [
        [
            sys.executable,
            str(SCRIPT_DIR / "v5_scorecard.py"),
            "--run-dir",
            str(run_dir),
            "--output-dir",
            output_dir,
            "--out-json",
            str(run_dir / "v5_scorecard.json"),
            "--out-md",
            str(run_dir / "v5_scorecard.md"),
        ],
        [
            sys.executable,
            str(SCRIPT_DIR / "v5_l6_status_brief.py"),
            "--run-dir",
            str(run_dir),
            "--out-json",
            str(run_dir / "v5_l6_status_brief.json"),
            "--out-md",
            str(run_dir / "v5_l6_status_brief.md"),
        ],
    ]
    for cmd in commands:
        subprocess.run(cmd, cwd=str(REPO_ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run paired greedy/callguard Slumbot diagnostics sequentially.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--checkpoint", default="")
    parser.add_argument("--output-dir", default="models")
    parser.add_argument("--base-tag", required=True)
    parser.add_argument("--min-training-hands", type=int, required=True)
    parser.add_argument("--sessions", type=int, default=4)
    parser.add_argument("--hands-per-session", type=int, default=500)
    parser.add_argument("--sleep-seconds", type=float, default=180.0)
    parser.add_argument("--max-health-age-seconds", type=int, default=600)
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--guarded-allin-max-spr", type=float, default=2.0)
    parser.add_argument("--guarded-allin-min-prob", type=float, default=0.65)
    parser.add_argument("--callguard-min-prob", type=float, default=0.20)
    parser.add_argument("--callguard-ratio", type=float, default=0.65)
    parser.add_argument("--status-json", default="")
    parser.add_argument("--status-md", default="")
    parser.add_argument("--log", default="")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    status_json = Path(args.status_json) if args.status_json else run_dir / "slumbot_selector_pair_75M_status.json"
    status_md = Path(args.status_md) if args.status_md else run_dir / "slumbot_selector_pair_75M_status.md"
    log_path = Path(args.log) if args.log else run_dir / "slumbot_selector_pair_75M_watch.log"
    previous_status = load_json(status_json)
    if previous_status and previous_status.get("state") == "PASS":
        print(f"{now_iso()} selector pair already PASS status_json={status_json}", flush=True)
        return 0

    def log(message: str) -> None:
        line = f"{now_iso()} {message}"
        print(line, flush=True)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.open("a", encoding="utf-8").write(line + "\n")

    policies = ["greedy", "preflop-callguard"]
    log(f"selector pair watcher started run_dir={run_dir} base_tag={args.base_tag}")
    while True:
        plans: dict[str, Any] = {}
        for policy in policies:
            tag = f"{args.base_tag}_{policy_tag(policy)}"
            plan_ns = make_plan_args(args, policy_mode=policy, tag=tag)
            plan = evaluate_plan(plan_ns)
            plans[policy] = plan
            plan_md = run_dir / f"slumbot_selector_pair_{policy_tag(policy)}_plan.md"
            write_plan_markdown(plan_md, plan)
        readiness_by_policy = {policy: plans[policy].get("overall") for policy in policies}
        checkpoint = plans["greedy"].get("checkpoint") or {}
        state = (
            "READY"
            if all(status in {"READY", "READY_WITH_WARNINGS"} for status in readiness_by_policy.values())
            else "WAITING"
        )
        status = {
            "checked_at": now_iso(),
            "state": state,
            "run_dir": str(run_dir),
            "base_tag": args.base_tag,
            "planned_hands_per_policy": args.sessions * args.hands_per_session,
            "readiness_by_policy": readiness_by_policy,
            "plans": plans,
        }
        write_json(status_json, status)
        write_pair_markdown(status_md, status)
        log(
            f"state={state} readiness={readiness_by_policy} "
            f"ckpt_iter={checkpoint.get('iteration')} ckpt_hands={checkpoint.get('total_hands')}"
        )
        if state != "READY":
            time.sleep(args.sleep_seconds)
            continue

        frozen_path = Path(args.output_dir) / f"bench_v55_{args.base_tag}_pair_checkpoint.pt"
        frozen_summary = freeze_checkpoint(Path(plans["greedy"]["checkpoint_path"]), frozen_path, checkpoint)
        status.update(
            {
                "checked_at": now_iso(),
                "state": "RUNNING",
                "frozen_checkpoint": str(frozen_path),
                "frozen_summary": frozen_summary,
                "results": {},
            }
        )
        write_json(status_json, status)
        write_pair_markdown(status_md, status)
        log(f"frozen checkpoint={frozen_path} iter={frozen_summary.get('iteration')} hands={frozen_summary.get('total_hands')}")

        results: dict[str, Any] = {}
        for policy in policies:
            plan = plans[policy]
            run_args = make_run_args(make_plan_args(args, policy_mode=policy, tag=plan["tag"]))
            reused = existing_result(plan, run_args)
            if reused:
                results[policy] = reused
                status.update({"checked_at": now_iso(), "state": "RUNNING", "results": results})
                write_json(status_json, status)
                write_pair_markdown(status_md, status)
                log(f"policy={policy} reused existing ci_json")
                continue
            log(f"running policy={policy} tag={plan['tag']}")
            result = run_benchmark(run_args, plan, frozen_path)
            results[policy] = result
            status.update({"checked_at": now_iso(), "state": "RUNNING", "results": results})
            write_json(status_json, status)
            write_pair_markdown(status_md, status)
            log(f"policy={policy} status={result.get('status')} elapsed={result.get('elapsed_seconds'):.1f}s")
            if result.get("status") != "PASS":
                status.update({"checked_at": now_iso(), "state": "FAIL", "results": results})
                write_json(status_json, status)
                write_pair_markdown(status_md, status)
                return 1

        greedy_ci = (results["greedy"].get("ci_summary") or {})
        callguard_ci = (results["preflop-callguard"].get("ci_summary") or {})
        delta = None
        if greedy_ci.get("bb_per_100") is not None and callguard_ci.get("bb_per_100") is not None:
            delta = round(float(callguard_ci["bb_per_100"]) - float(greedy_ci["bb_per_100"]), 3)
        status.update(
            {
                "checked_at": now_iso(),
                "state": "PASS",
                "results": results,
                "delta_callguard_vs_greedy_bb_per_100": delta,
            }
        )
        write_json(status_json, status)
        write_pair_markdown(status_md, status)
        run_refresh_reports(run_dir, args.output_dir)
        log(f"selector pair finished delta_callguard_vs_greedy_bb100={delta}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
