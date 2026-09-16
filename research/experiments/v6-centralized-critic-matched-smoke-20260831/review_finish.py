"""Independent terminal review of privileged centralized-critic smoke."""
import json, math, statistics, subprocess, sys, time
import psutil, torch
import run_smoke as run


def gone(execution):
    try: return abs(psutil.Process(execution["pid"]).create_time() - execution["create_time"]) > .001
    except psutil.NoSuchProcess: return True


def main():
    if sys.argv[1:] or (run.BASE / "reviewed_analysis.json").exists(): raise ValueError("No repeat")
    started = time.monotonic(); execution = run.read(run.BASE / "execution.json"); assert execution["status"] == "COMPLETED_PENDING_REVIEW" and gone(execution)
    record = run.read(run.BASE / "experiment.json"); assert record["status"] == "RUNNING"
    for path, expected in record["artifact_integrity"].items(): assert run.sha(path) == expected["sha256"]
    manifest = run.read(run.BASE / "input_manifest.json")
    for item in manifest["inputs"]: assert run.sha(item["source"]) == run.sha(item["path"]) == item["sha256"]
    for item in manifest["source_copies"]: assert run.sha(run.ROOT / item["copy"]) == item["sha256"]
    candidates = run.read(run.BASE / "candidate_manifest.json")
    for item in candidates.values(): assert run.sha(item["path"]) == item["sha256"]
    medians = {}
    for arm in run.ARMS:
        checkpoint = torch.load(run.BASE / f"frozen/{arm}.pt", map_location="cpu", weights_only=False); assert checkpoint["environment_hand_accounting"]["completed_hands"] == execution["arm_training_hands"][arm] >= run.TARGET
        assert run.read(run.BASE / f"production/{arm}/session_audit.json")["status"] == "PASS"
        rows = [json.loads(line) for line in (run.BASE / f"production/{arm}/h1_training_metrics.jsonl").read_text().splitlines()]; tail = rows[len(rows)//2:]
        medians[arm] = statistics.median(float(row["preupdate_critic_mse"]) for row in tail); assert all(bool(row["centralized_critic"]) == (arm == "treatment") for row in rows)
    values = {}; decks = None
    for name in ("source", "control", "treatment"):
        for index in range(5):
            rows = [json.loads(line) for line in (run.BASE / f"matrix/{name}_anchor{index}/pairs.jsonl").read_text().splitlines()]; assert len(rows) == run.PAIRS and [r["pair_index"] for r in rows] == list(range(run.PAIRS)); current = [r["deck"] for r in rows]
            if decks is None: decks = current
            assert current == decks; values[name,index] = [math.fsum(r["rewards_bb"]) * 50 for r in rows]
    per_anchor = [run.estimate([t-c for t,c in zip(values["treatment",i], values["control",i])]) for i in range(5)]
    tc = run.estimate([math.fsum(values["treatment",i][r]-values["control",i][r] for i in range(5))/5 for r in range(run.PAIRS)]); ts = run.estimate([math.fsum(values["treatment",i][r]-values["source",i][r] for i in range(5))/5 for r in range(run.PAIRS)]); points = [x["mean"] for x in per_anchor]
    decision = "ADMIT_MATCHED_CTDE_PILOT" if run.gate(tc, ts, points, medians["control"], medians["treatment"]) else "CENTRALIZED_CRITIC_SMOKE_NOT_PROMISING"
    analysis = run.read(run.BASE / "analysis.json"); assert analysis["decision"] == decision and analysis["positive_treatment_control_anchors"] == sum(x > 0 for x in points)
    report = {"status":"PASS","decision":decision,"arm_training_hands":execution["arm_training_hands"],"new_training_hands":execution["new_training_hands"],"evaluation_hands":execution["evaluation_hands"],"treatment_control":tc,"treatment_source":ts,"treatment_control_by_anchor":per_anchor,"positive_treatment_control_anchors":sum(x > 0 for x in points),"final_half_preupdate_critic_mse_median":medians,"candidate_sha256":{n:x["sha256"] for n,x in candidates.items()},"slumbot_hands":0,"goal_achieved":False,"wall_time_seconds":execution["wall_time_seconds"],"review_wall_time_seconds":time.monotonic()-started,"interpretation":"Fixed known-anchor CTDE smoke is internal mechanism evidence, not external strength."}
    run.write(run.BASE / "reviewed_analysis.json", report); (run.BASE / "result_summary.md").write_text(f"# Privileged centralized-critic matched smoke\n\n{decision}\n\nTreatment-control {tc['mean']:.4f} CI95 {tc['ci95']}; treatment-source {ts['mean']:.4f} CI95 {ts['ci95']}; positive anchors {report['positive_treatment_control_anchors']}/5; final-half critic MSE medians {medians}. Training {execution['new_training_hands']} hands; evaluation {execution['evaluation_hands']} hands;0 Slumbot.\n")
    run.log("--command", f"python research/experiments/{run.BASE.name}/review_finish.py", "--artifact", run.BASE / "reviewed_analysis.json", "--artifact", run.BASE / "result_summary.md", "--metric", f"review_wall_time_seconds={report['review_wall_time_seconds']}")
    next_step = "Run a preregistered262144-hand matched CTDE pilot." if decision.startswith("ADMIT") else "Reject this privileged critic and implement a matched EMA actor-target smoke."
    subprocess.run([sys.executable, str(run.ROOT/"research/experiment_log.py"), "finish", run.BASE.name, "--status", "COMPLETED", "--summary", f"Privileged centralized-critic smoke completed: {decision}.", "--conclusion", report["interpretation"], "--decision", decision, "--next-step", next_step, "--count", f"new_training_hands={execution['new_training_hands']}", "--count", f"evaluation_hands={execution['evaluation_hands']}", "--count", "slumbot_hands=0"], cwd=run.ROOT, check=True); print(json.dumps(report), flush=True)


if __name__ == "__main__": main()
