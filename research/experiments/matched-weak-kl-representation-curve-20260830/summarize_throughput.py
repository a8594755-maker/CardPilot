"""Arithmetic on an already-frozen prefix review; zero new poker hands."""
import datetime as dt
import json
from pathlib import Path
import sys

BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE))
from run_pilot import sha


def estimate(rows):
    if len(rows)<2 or [row['iteration'] for row in rows]!=list(range(1,len(rows)+1)):
        raise ValueError('Expected a complete ordered prefix')
    times=[dt.datetime.fromisoformat(row['recorded_at']) for row in rows]
    counts=[row['environment_hand_accounting']['completed_hands'] for row in rows]
    if any(b<=a for a,b in zip(times,times[1:])) or any(b<=a for a,b in zip(counts,counts[1:])):
        raise ValueError('Nonmonotonic saved time or physical counters')
    elapsed=(times[-1]-times[0]).total_seconds()
    physical=counts[-1]-counts[0]
    rate=physical/elapsed
    return dict(first_update=1,last_update=len(rows),excluded_first_update_hands=counts[0],
        measured_physical_hands_between_saved_updates=physical,
        elapsed_seconds_between_saved_updates=elapsed,physical_hands_per_second=rate,
        hours_per_million_at_unchanged_rate=1e6/rate/3600,
        days_for_2_7b_at_unchanged_rate=2.7e9/rate/86400)


def main():
    path=BASE/'heads_iter000012_prefix_review.json'
    output=BASE/'heads_prefix_throughput.json'
    if output.exists():
        raise RuntimeError('Do not overwrite a saved throughput interpretation')
    doc=json.loads(path.read_text())
    if doc['status']!='PASS' or doc['arm']!='heads' or doc['iteration']!=12:
        raise ValueError('Expected already-reviewed heads prefix')
    if doc['review_script_sha256']!=sha(BASE/'review_archived_prefix.py'):
        raise ValueError('Archived-prefix reviewer changed')
    result=dict(status='PASS',new_training_hands=0,evaluation_hands=0,
        input_path=str(path),input_sha256=sha(path),script_sha256=sha(Path(__file__)),
        **estimate(doc['prefix_metric_rows']))
    result['limitations']=[
        'Read-only early heads-arm throughput, not final throughput or full-network-arm measurement.',
        'Uses physical counter increments and recorded UTC times; does not substitute the legacy marker hands/s metric.',
        'Excludes startup and first update; includes observed between-update runtime and saving overhead.',
        '2.7B extrapolation assumes nonstop unchanged throughput and excludes future evaluation, interruptions and hardware changes.',
        'Feasibility does not imply a useful learning curve or policy strength. Do not change this live preregistered run.']
    result['interpretation']='Current bounded million-hand matched study is feasible, but paper-scale work would require substantial wall time at this measured rate. If general learning signals justify scale, separately profile and validate throughput improvements before a paper-scale commitment.'
    output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps(result))


if __name__=='__main__':
    main()
