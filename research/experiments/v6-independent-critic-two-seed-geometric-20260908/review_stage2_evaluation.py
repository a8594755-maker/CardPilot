"""Recompute stage2 paired strength and preregistered collapse from raw hands."""
import gzip
import importlib.util
import json
from pathlib import Path
import random
import sys

BASE = Path(__file__).resolve().parent
sys.path.insert(0,str(BASE))
from preflight import read, sha
from paired_contrast import join

HELPER = BASE.parent/'v6-arbitrary-anchor-reporting-20260907/paired_summary.py'
spec = importlib.util.spec_from_file_location('fixed_panel_summaries',HELPER)
paired = importlib.util.module_from_spec(spec)
spec.loader.exec_module(paired)


def summarize(rows, anchors):
    all_rows = paired.summarize(rows,anchors=anchors,pairs_per_anchor=1024)
    return {**all_rows, 'preservation':paired.summarize([r for r in rows if r['anchor'] in anchors[:4]],
                anchors=anchors[:4],pairs_per_anchor=1024),
            'transfer':paired.summarize([r for r in rows if r['anchor'] in anchors[4:]],
                anchors=anchors[4:],pairs_per_anchor=1024)}


def prescribed_decks(rows, anchors, base_seed, pairs=1024):
    groups = {a:{} for a in anchors}
    for row in rows:
        a,i = row['anchor'],row['pair_index']
        if a not in groups or i in groups[a]: raise ValueError('unexpected/duplicate identity')
        groups[a][i] = row
    for index,a in enumerate(anchors):
        rng = random.Random(base_seed+1000003*index)
        if set(groups[a]) != set(range(pairs)): raise ValueError('incomplete deck set')
        for i in range(pairs):
            deck = list(range(52)); rng.shuffle(deck)
            row = groups[a][i]
            if row['deck'] != deck or row['anchor_seed'] != base_seed+1000003*index:
                raise ValueError('wrong predeclared deck/seed')


def main():
    execution = read(BASE/'stage2_evaluation_execution.json')
    assert read(BASE/'stage2_evaluation_terminal.json')['completed_hands'] == 131072
    contract = read(BASE/'input_contract.json')
    assert sha(BASE/'protocol.md') == contract['protocol_sha256']
    for name,digest in execution['input_sha256'].items(): assert sha(Path(name)) == digest
    anchors = list(contract['anchors'])
    results, hashes = {},{}
    unique = set()
    previous = read(BASE/'stage1_raw_review.json')
    assert previous['passed_evidence_checks']
    prior_decks = set()
    for name, digest in previous['raw_hashes'].items():
        assert sha(Path(name)) == digest
        with gzip.open(name, 'rt', encoding='utf-8') as handle:
            prior_decks.update(tuple(json.loads(line)['deck']) for line in handle)
    assert len(prior_decks) == 16384
    for seed in (1,3):
        raw = {}
        own = {}
        for arm in ('control','independent'):
            out = BASE/f'eval_seed{seed}_{arm}_stage2'
            summary = read(out/'summary.json')
            path = out/'common_deck_pairs.jsonl.gz'
            digest = sha(path)
            assert summary['status']=='COMPLETED' and summary['evaluation_hands']==32768
            assert summary['policy_mode']=='greedy' and summary['starting_stack_bb']==200
            assert summary['observation_style']=='legacy_v4'
            assert summary['raw_pairs_sha256']==digest
            endpoint = BASE/f'seed{seed}_{arm}_stage2/latest.pt'
            expected = {'control':contract['parents'][str(seed)]['sha256'],'treatment':sha(endpoint),
                        **{f'anchor:{a}':v['sha256'] for a,v in contract['anchors'].items()}}
            assert summary['input_sha256']==expected
            with gzip.open(path,'rt',encoding='utf-8') as handle:
                rows = [json.loads(line) for line in handle]
            prescribed_decks(rows,anchors,contract['eval_seeds'][f'{seed}_2'])
            own[arm] = summarize(rows,anchors)
            raw[arm] = rows
            hashes[str(path)] = digest
            if arm == 'control':
                for row in rows:
                    deck = tuple(row['deck'])
                    assert deck not in unique and deck not in prior_decks
                    unique.add(deck)
        contrast = summarize(join(raw['control'],raw['independent']),anchors)
        results[str(seed)] = {'own_parent':own,'independent_minus_control':contrast}
    assert len(unique)==16384
    collapse = {arm:all(paired.severe(results[str(seed)]['own_parent'][arm],minimum_bad_anchors=3)
                        for seed in (1,3)) for arm in ('control','independent')}
    output = {'passed_evidence_checks':True,'stage':2,'evaluation_hands':131072,
        'unique_decks':len(unique),'raw_hashes':hashes,'by_seed':results,
        'replicated_broad_collapse_by_arm':collapse,
        'decision':'STOP_FOR_COLLAPSE_REVIEW' if any(collapse.values()) else 'FIXED_DOSE_COMPLETE_RESEARCH_DECISION_REQUIRED',
        'ci_scope':'Conditional unadjusted normal paired-deck95CI, not final blind qualification.',
        'generalization_scope':'Known heterogeneous learned anchors; shared ancestry, not unseen-family proof.'}
    with (BASE/'stage2_raw_review.json').open('x',encoding='utf-8') as handle:
        json.dump(output,handle,indent=2,allow_nan=False)
    print(json.dumps({'decision':output['decision'],'contrasts':{
        seed:data['independent_minus_control']['pooled'] for seed,data in results.items()}}))


if __name__ == '__main__': main()
