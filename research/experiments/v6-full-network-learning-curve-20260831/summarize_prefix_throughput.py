"""Retain and analyze the fixed first12update timing/counter prefix; no gameplay."""
import json
from pathlib import Path
import re
import statistics
import sys

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
sys.path.insert(0,str(ROOT))
from research.experiment_log import sha256_file


def summarize(log_lines,metrics):
    if len(log_lines)!=12 or len(metrics)!=12: raise ValueError('Require the fixed first12updates')
    rows=[]
    pattern=re.compile(r'^\[\s*(\d+)\].*?hands=([\d,]+) envhands=([\d,]+).*?inf_bs=([\d.]+) collect=([\d.]+)s ppo=([\d.]+)s$')
    for index,(line,metric) in enumerate(zip(log_lines,metrics),1):
        match=pattern.fullmatch(line)
        if not match or int(match[1])!=index or metric['iteration']!=index:
            raise ValueError('Non-contiguous or malformed update prefix')
        hands=int(match[3].replace(',',''))
        if hands!=metric['environment_hand_accounting']['completed_hands']:
            raise ValueError('Console physical count differs from exact metric')
        rows.append(dict(iteration=index,physical_hands=hands,
            legacy_markers=int(match[2].replace(',','')),inference_batch_mean=float(match[4]),
            collection_seconds_rounded=float(match[5]),ppo_seconds_rounded=float(match[6])))
    collection=sum(r['collection_seconds_rounded'] for r in rows)
    ppo=sum(r['ppo_seconds_rounded'] for r in rows)
    if collection<=0 or ppo<0: raise ValueError('Invalid timing')
    physical=rows[-1]['physical_hands']
    rate=physical/(collection+ppo)
    return dict(through_iteration=12,physical_hands=physical,legacy_markers=rows[-1]['legacy_markers'],
        logged_collection_seconds=collection,logged_ppo_seconds=ppo,
        collection_fraction_of_logged_collect_plus_ppo=collection/(collection+ppo),
        physical_hands_per_logged_collect_plus_ppo_second=rate,
        median_logged_inference_batch_mean=statistics.median(r['inference_batch_mean'] for r in rows),
        hypothetical_days_for_2p7b_excluding_other_overhead=2.7e9/rate/86400,
        qualification_or_extension_admitted=False,additional_training_hands=0,additional_evaluation_hands=0,
        limitations='Rounded timings; excludes startup,checkpoint IO and other overhead; early12updates only; not causal bottleneck attribution or future throughput guarantee',rows=rows)


def main():
    if sys.argv[1:]: raise ValueError('Fixed12update prefix; no alternative window selection')
    output=BASE/'prefix12_throughput.json'
    if output.exists(): raise ValueError('Preserve previous prefix analysis')
    lines=[]
    for line in (BASE/'production/latest_train.log').read_text().splitlines():
        if re.match(r'^\[\s*\d+\]',line): lines.append(line)
        if len(lines)==12: break
    metrics=[]
    with (BASE/'production/h1_training_metrics.jsonl').open() as handle:
        for line in handle:
            metrics.append(json.loads(line))
            if len(metrics)==12: break
    summary=summarize(lines,metrics)
    log_copy=BASE/'prefix12_train_log.txt'
    metrics_copy=BASE/'prefix12_metrics.jsonl'
    log_copy.write_text('\n'.join(lines)+'\n')
    metrics_copy.write_text(''.join(json.dumps(row,sort_keys=True)+'\n' for row in metrics))
    summary.update(log_prefix_sha256=sha256_file(log_copy),metric_prefix_sha256=sha256_file(metrics_copy))
    output.write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k!='rows'}))


if __name__=='__main__': main()
