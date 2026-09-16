"""Freeze parents, evaluation opponents and outcome-independent deck inventory."""
import gzip
import hashlib
import json
from pathlib import Path
import random

BASE = Path(__file__).resolve().parent
PARENT = BASE.parent/'v6-fixed-regimen-two-seed-2m-20260908'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def main():
    assert read(BASE/'eval_bridge_checks.json')['passed']
    old = read(PARENT/'evaluation_contract.json')
    assert list(old['anchors']) == ['standard10','cfr4','legacy_iter16','legacy_mixed65k',
                                   'mixture_s1','mixture_s3','heads_s1','heads_s3']
    sources = {name:digest for name,digest in old['input_sha256'].items() if name.endswith('.py')}
    qual = BASE.parent/'v6-independent-observable-critic-qualification-20260908'
    sources.update(read(qual/'runtime_sources.json'))
    for p in (qual/'derive_capture_check_v2.py', BASE/'eval_candidate.py', BASE/'train_job.py'):
        sources[str(p)] = sha(p)
    for name,digest in sources.items():
        assert sha(Path(name)) == digest, name
    parents = {str(seed): {'path':str(PARENT/f'seed{seed}_control_stage1/latest.pt'), 'sha256':digest}
               for seed,digest in [(1,'52501761b214aafc00caea3cba14e6d51c8f176d33c612914d6916fd939bbcf2'),
                                   (3,'c23b7db58802e67c1bcb94f7418ff980db7ec981cab9ca171bb37cc574514d94')]}
    for item in parents.values(): assert sha(Path(item['path'])) == item['sha256']
    anchors = {name:{'path':path,'sha256':sha(Path(path))} for name,path in old['anchors'].items()}
    seeds = {'1_1':202609084101,'3_1':202609084301,'1_2':202609085101,'3_2':202609085301}
    planned = set()
    for seed in seeds.values():
        for index in range(8):
            rng = random.Random(seed+1000003*index)
            for _ in range(1024):
                deck = list(range(52)); rng.shuffle(deck)
                assert tuple(deck) not in planned
                planned.add(tuple(deck))
    assert len(planned) == 32768
    corpus = dict(old['prior_gzip'])
    corpus.update({str(path):sha(path) for path in PARENT.glob('eval_*/common_deck_pairs.jsonl.gz')})
    count = 0
    for inventory, opener in ((corpus,gzip.open),(old['prior_plain'],open)):
        for name,digest in inventory.items():
            assert sha(Path(name)) == digest
            with opener(name,'rt',encoding='utf-8') as handle:
                for line in handle:
                    row = json.loads(line)
                    assert tuple(row['deck']) not in planned
                    count += 1
    output = {'passed':True,'parents':parents,'anchors':anchors,'sources':sources,
        'eval_seeds':seeds,'planned_unique_decks':len(planned),'prior_rows_checked':count,
        'prior_gzip':corpus,'prior_plain':old['prior_plain'],'overlap':0,
        'protocol_sha256':sha(BASE/'protocol.md'),'evaluation_hands':262144}
    with (BASE/'input_contract.json').open('x',encoding='utf-8') as handle:
        json.dump(output,handle,indent=2)
    print(json.dumps({'passed':True,'planned_decks':len(planned),'prior_rows':count,'overlap':0}))


if __name__ == '__main__':
    main()
