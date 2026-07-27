#!/usr/bin/env python
"""Complete derived artifacts (loss, audit, hand_review, dump_analysis) for a benchmark status.
Updates the status.json with artifact_status and summaries.
Exits non-zero if not PASS.
"""
import argparse
import glob
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).parent

def read_json_bom(path: Path):
    try:
        data = path.read_bytes()
        if data.startswith(b'\xef\xbb\xbf'):
            data = data[3:]
        return json.loads(data.decode('utf-8'))
    except Exception as e:
        print("read error", e)
        return None

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--from-status", required=True)
    p.add_argument("--tag", default=None, help="override tag")
    args = p.parse_args()

    status_path = Path(args.from_status)
    status = read_json_bom(status_path)
    if status is None:
        print("failed to read status")
        sys.exit(2)
    plan = status.get("plan", {}) or {}
    tag = args.tag or plan.get("tag")
    if not tag:
        print("no tag")
        sys.exit(2)
    output_dir = Path(plan.get("output_dir") or "models")
    output_dir.mkdir(parents=True, exist_ok=True)

    dump_glob = str(output_dir / f"bench_v55_{tag}_part*_dump.jsonl")
    dump_files = sorted(glob.glob(dump_glob))
    if not dump_files:
        print("no dump files for", tag)
        sys.exit(2)

    artifacts = plan.get("artifacts", {}) or {}
    dump_analysis = Path(str(artifacts.get("dump_analysis") or output_dir / f"bench_v55_{tag}_dump_analysis.txt"))
    loss_json = Path(str(artifacts.get("loss_report_json") or output_dir / f"bench_v55_{tag}_loss_report.json"))
    loss_md = Path(str(artifacts.get("loss_report_md") or output_dir / f"bench_v55_{tag}_loss_report.md"))
    audit_json = Path(str(artifacts.get("artifact_audit_json") or output_dir / f"bench_v55_{tag}_artifact_audit.json"))
    audit_md = Path(str(artifacts.get("artifact_audit_md") or output_dir / f"bench_v55_{tag}_artifact_audit.md"))
    hr_json = Path(str(artifacts.get("hand_review_json") or output_dir / f"bench_v55_{tag}_hand_review.json"))
    hr_md = Path(str(artifacts.get("hand_review_md") or output_dir / f"bench_v55_{tag}_hand_review.md"))

    # run analyze_dump (real)
    cmd = [sys.executable, str(SCRIPT_DIR / "analyze_dump.py"), "--label", tag, "--dumps"] + dump_files
    print("RUN", " ".join(map(str, cmd)))
    rc = subprocess.call(cmd)
    if rc != 0 or not dump_analysis.exists():
        print("dump_analysis failed")

    # loss
    cmd = [sys.executable, str(SCRIPT_DIR / "v5_slumbot_loss_report.py"), "--label", tag, "--dumps"] + dump_files + ["--out-json", str(loss_json), "--out-md", str(loss_md)]
    print("RUN", " ".join(map(str, cmd)))
    subprocess.call(cmd)

    # audit
    cmd = [sys.executable, str(SCRIPT_DIR / "v5_slumbot_artifact_audit.py"), "--tag", tag, "--output-dir", str(output_dir), "--out-json", str(audit_json), "--out-md", str(audit_md)]
    print("RUN", " ".join(map(str, cmd)))
    subprocess.call(cmd)

    # hand review
    cmd = [sys.executable, str(SCRIPT_DIR / "v5_slumbot_hand_review.py"), "--tag", tag, "--output-dir", str(output_dir), "--out-json", str(hr_json), "--out-md", str(hr_md)]
    if plan.get("run_dir"):
        cmd += ["--run-dir", str(plan["run_dir"])]
    print("RUN", " ".join(map(str, cmd)))
    subprocess.call(cmd)

    # update status
    br = status.setdefault("benchmark_result", {})
    br["artifact_status"] = {
        "loss_report_json": loss_json.exists(),
        "hand_review_json": hr_json.exists(),
        "artifact_audit_json": audit_json.exists(),
        "dump_analysis": dump_analysis.exists(),
    }
    if audit_json.exists():
        br["artifact_audit"] = read_json_bom(audit_json) or {}
    if hr_json.exists():
        br["hand_review"] = read_json_bom(hr_json) or {}
    if loss_json.exists():
        br["loss_report_summary"] = read_json_bom(loss_json) or {}

    audit_ok = (audit_json.exists() and br.get("artifact_audit", {}).get("overall") == "PASS")
    hr_ok = hr_json.exists() and br.get("hand_review", {}).get("overall") not in ("INCOMPLETE", "MISSING_CI")
    br["status"] = "PASS" if audit_ok and hr_ok else "FAIL"

    with open(status_path, 'w', encoding='utf-8') as f:
        json.dump(status, f, indent=2)
    print(json.dumps({"status": br["status"], "tag": tag, "artifact_status": br["artifact_status"]}, indent=2))
    if br["status"] != "PASS":
        sys.exit(1)

if __name__ == "__main__":
    main()
