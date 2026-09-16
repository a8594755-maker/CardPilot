"""Offline ordinal validation of a learned-policy holdout panel."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json, math, shutil, subprocess, sys, time
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
PAIRS = 512
SEED = 20261104
CANDIDATES = {
    "parent": ROOT / "research/experiments/v6-actor-ema-terminal-smoke-20260831/frozen/raw.pt",
    "parent_kl": ROOT / "research/experiments/v6-parent-kl-conservative-tail-recovery-20260901/frozen/tail_raw.pt",
    "weak_tail": ROOT / "research/experiments/v6-actor-low-lr-tail-20260901/frozen/tail_raw.pt",
}
OPPONENTS = {
    "entropy": ROOT / "research/experiments/v6-entropy-penalty-actor-smoke-20260901/frozen/treatment.pt",
    "causal_tcn": ROOT / "research/experiments/v6-causal-tcn-matched-reward-pilot-20260831/frozen/treatment.pt",
    "centralized": ROOT / "research/experiments/v6-centralized-critic-corrected-smoke-20260831/frozen/treatment.pt",
    "full265": ROOT / "research/experiments/v6-full-network-learning-curve-20260831/frozen/final.pt",
    "physical1m": ROOT / "research/experiments/v6-physical1m-fresh20k-slumbot-20260831/frozen/final.pt",
}
sys.path.insert(0, str(ROOT))
from research.experiment_log import atomic_json, sha256_file

def write(path, value): atomic_json(Path(path), value)
def update(*args): subprocess.run([sys.executable, str(ROOT / "research/experiment_log.py"), "update", BASE.name, *map(str,args)], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
def estimate(values):
    mean=math.fsum(values)/len(values); se=math.sqrt(math.fsum((x-mean)**2 for x in values)/(len(values)*(len(values)-1)))
    return {"n":len(values),"mean":mean,"ci95":[mean-1.96*se,mean+1.96*se]}

def main():
    if sys.argv[1:] or (BASE/"execution.json").exists(): raise ValueError("No restart")
    started=time.monotonic(); execution={"status":"RUNNING","started_at":datetime.now(timezone.utc).isoformat(),"evaluation_hands":0,"new_training_hands":0,"slumbot_hands":0}
    write(BASE/"execution.json",execution)
    frozen=BASE/"frozen"; frozen.mkdir()
    manifest={"candidates":{},"opponents":{}}
    for group,paths in (("candidates",CANDIDATES),("opponents",OPPONENTS)):
        for name,path in paths.items():
            target=frozen/f"{group}_{name}.pt"; shutil.copy2(path,target)
            manifest[group][name]={"source":str(path),"path":str(target),"sha256":sha256_file(target)}
    write(BASE/"input_manifest.json",manifest); update("--artifact",BASE/"input_manifest.json")
    evaluator=ROOT/"scripts/alpha_holdem/v6_mirror_eval.py"; jobs=[]
    for candidate in CANDIDATES:
        for opponent in OPPONENTS:
            out=BASE/"matrix"/f"{candidate}_{opponent}"
            command=[str(evaluator),"--candidate",manifest["candidates"][candidate]["path"],"--anchor",manifest["opponents"][opponent]["path"],"--pairs",str(PAIRS),"--seed",str(SEED),"--device","cpu","--policy-mode","greedy","--out-dir",str(out)]
            update("--command",subprocess.list2cmdline(["python",*command])); jobs.append((candidate,opponent,out,command))
    def run(job):
        c,o,_,cmd=job
        with (BASE/f"{c}_{o}.log").open("x") as stream: return subprocess.run([sys.executable,*cmd],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT).returncode
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures=[pool.submit(run,j) for j in jobs]
        while not all(f.done() for f in futures):
            execution["evaluation_hands"]=sum((out/"pairs.jsonl").read_bytes().count(b"\n")*2 if (out/"pairs.jsonl").exists() else 0 for _,_,out,_ in jobs); write(BASE/"execution.json",execution); time.sleep(5)
        assert all(f.result()==0 for f in futures)
    values={}; decks=None
    for c,o,out,_ in jobs:
        rows=[json.loads(x) for x in (out/"pairs.jsonl").read_text().splitlines() if x.strip()]; assert len(rows)==PAIRS
        current=[r["deck"] for r in rows]; decks=current if decks is None else decks; assert current==decks
        values[c,o]=[math.fsum(r["rewards_bb"])*50 for r in rows]
    def contrast(other): return estimate([math.fsum(values["parent",o][i]-values[other,o][i] for o in OPPONENTS)/len(OPPONENTS) for i in range(PAIRS)])
    parent_kl=contrast("parent_kl"); weak=contrast("weak_tail")
    wins_kl=sum(math.fsum(values["parent",o])/PAIRS > math.fsum(values["parent_kl",o])/PAIRS for o in OPPONENTS)
    wins_weak=sum(math.fsum(values["parent",o])/PAIRS > math.fsum(values["weak_tail",o])/PAIRS for o in OPPONENTS)
    passed=parent_kl["ci95"][0]>0 and weak["ci95"][0]>0 and wins_kl>=3 and wins_weak>=3
    decision="HELDOUT_PROXY_PANEL_VALIDATED" if passed else "HELDOUT_PROXY_PANEL_REJECTED"
    analysis={"status":"COMPLETED_PENDING_REVIEW","decision":decision,"parent_minus_parent_kl":parent_kl,"parent_minus_weak_tail":weak,"parent_wins_vs_parent_kl":wins_kl,"parent_wins_vs_weak_tail":wins_weak,"evaluation_hands":len(jobs)*PAIRS*2,"new_training_hands":0,"slumbot_hands":0,"goal_achieved":False}
    write(BASE/"analysis.json",analysis); execution.update({"status":"COMPLETED_PENDING_REVIEW","evaluation_hands":analysis["evaluation_hands"],"finished_at":datetime.now(timezone.utc).isoformat(),"wall_time_seconds":time.monotonic()-started}); write(BASE/"execution.json",execution)
    update("--artifact",BASE/"analysis.json","--count","evaluation_hands=15360","--count","new_training_hands=0","--count","slumbot_hands=0","--metric",f"wall_time_seconds={execution['wall_time_seconds']}")
    print(json.dumps(analysis,indent=2))

if __name__=="__main__": main()

