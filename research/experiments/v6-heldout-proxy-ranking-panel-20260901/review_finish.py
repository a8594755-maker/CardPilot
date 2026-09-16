"""Independent paired-ranking review for the holdout proxy panel."""
import json, math
from pathlib import Path

BASE=Path(__file__).resolve().parent
PAIRS=512
OPPONENTS=("entropy","causal_tcn","centralized","full265","physical1m")

def load(path): return json.loads(Path(path).read_text(encoding="utf-8"))
def estimate(values):
    m=math.fsum(values)/len(values); se=math.sqrt(math.fsum((x-m)**2 for x in values)/(len(values)*(len(values)-1)))
    return {"n":len(values),"mean":m,"ci95":[m-1.96*se,m+1.96*se]}

def review():
    analysis=load(BASE/"analysis.json"); execution=load(BASE/"execution.json")
    assert execution["status"]=="COMPLETED_PENDING_REVIEW" and execution["evaluation_hands"]==15360
    values={}; decks=None
    for candidate in ("parent","parent_kl","weak_tail"):
        for opponent in OPPONENTS:
            directory=BASE/"matrix"/f"{candidate}_{opponent}"
            assert load(directory/"summary.json")["policy_mode"]=="greedy"
            rows=[json.loads(x) for x in (directory/"pairs.jsonl").read_text().splitlines() if x.strip()]
            assert len(rows)==PAIRS
            current=[r["deck"] for r in rows]; decks=current if decks is None else decks; assert current==decks
            values[candidate,opponent]=[math.fsum(r["rewards_bb"])*50 for r in rows]
    def contrast(other): return estimate([math.fsum(values["parent",o][i]-values[other,o][i] for o in OPPONENTS)/5 for i in range(PAIRS)])
    pkl,weak=contrast("parent_kl"),contrast("weak_tail")
    wins_kl=sum(math.fsum(values["parent",o])>math.fsum(values["parent_kl",o]) for o in OPPONENTS)
    wins_weak=sum(math.fsum(values["parent",o])>math.fsum(values["weak_tail",o]) for o in OPPONENTS)
    assert math.isclose(pkl["mean"],analysis["parent_minus_parent_kl"]["mean"],abs_tol=1e-12)
    assert math.isclose(weak["mean"],analysis["parent_minus_weak_tail"]["mean"],abs_tol=1e-12)
    assert wins_kl==wins_weak==0 and analysis["decision"]=="HELDOUT_PROXY_PANEL_REJECTED"
    return {"status":"PASS","decision":analysis["decision"],"parent_minus_parent_kl":pkl,"parent_minus_weak_tail":weak,"parent_wins_vs_parent_kl":wins_kl,"parent_wins_vs_weak_tail":wins_weak,"evaluation_hands":15360,"slumbot_hands":0,"goal_achieved":False}

def main():
    result=review(); (BASE/"reviewed_analysis.json").write_text(json.dumps(result,indent=2)+"\n")
    (BASE/"result_summary.md").write_text(f"# Held-out learned-policy proxy ranking result\n\nDecision: `{result['decision']}`. Across five frozen policies excluded from the raw actor's training league, parent minus parent-KL was {result['parent_minus_parent_kl']['mean']:+.4f} bb/100 with 95% CI [{result['parent_minus_parent_kl']['ci95'][0]:+.4f}, {result['parent_minus_parent_kl']['ci95'][1]:+.4f}], and parent minus weak tail was {result['parent_minus_weak_tail']['mean']:+.4f} with CI [{result['parent_minus_weak_tail']['ci95'][0]:+.4f}, {result['parent_minus_weak_tail']['ci95'][1]:+.4f}]. Parent won on 0/5 opponents in both comparisons, the reverse of the independent greedy Slumbot point ordering. Independent paired recomputation passed. The panel is discarded; zero network/Slumbot/training hands. Goal not achieved.\n",encoding="utf-8")
    print(json.dumps(result,sort_keys=True))

if __name__=="__main__": main()
