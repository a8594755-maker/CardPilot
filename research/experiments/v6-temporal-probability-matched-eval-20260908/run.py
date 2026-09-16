import gzip
import importlib.util
import json
from pathlib import Path
import random
import subprocess
import sys
import time

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
EXPS = ROOT / 'research/experiments'
QUAL = EXPS / 'v6-temporal-probability-qualification-20260908'
sys.path.insert(0, str(QUAL))
from qualify import ProbabilityAggregate, sha, init_model, read_checkpoint
from alpha_holdem.v6_elo_eval import _play_hand
import torch


def write(name, value):
    with (BASE / name).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)


def main():
    start = time.monotonic()
    torch.set_num_threads(2)
    assert torch.cuda.is_available()
    q = json.loads((QUAL / 'qualification.json').read_text())
    assert q['passed']
    sources = dict(q['source_sha256'])
    for path, digest in sources.items():
        assert sha(Path(path)) == digest
    anchor_paths = [
        ('standard10', ROOT / 'models/baseline/standard10/latest.pt'),
        ('cfr4', EXPS / 'v6-cfr4-full-e2-greedy-fresh20k-confirmation-20260901/frozen/final.pt'),
        ('legacy_iter16', EXPS / 'v6-legacy-iter16-greedy-fresh20k-20260901/frozen/final.pt'),
        ('legacy_mixed65k', EXPS / 'v6-legacy-contract-mixed-league-65k-pilot-20260901/training/latest.pt'),
    ]
    anchor_paths += [(f'mixture_s{s}', EXPS / f'v6-opponent-execution-mixture-two-seed-geometric-20260907/seed{s}_mixture_stage2/latest.pt') for s in (1, 3)]
    anchor_paths += [(f'heads_s{s}', EXPS / f'v6-current-kl-representation-pilot-20260905/seed{s}_heads_stage2/latest.pt') for s in (1, 3)]
    anchors = []
    for name, path in anchor_paths:
        sources[str(path)] = sha(path)
        anchors.append((name, init_model(read_checkpoint(path), 'cuda').eval()))
    all_decks, planned = set(), {}
    for seed in (1, 3):
        for ai, (name, _) in enumerate(anchors):
            rng = random.Random(202609081000 + 100*seed + 1000003*ai)
            decks = []
            for _ in range(1024):
                deck = list(range(52)); rng.shuffle(deck)
                assert tuple(deck) not in all_decks
                all_decks.add(tuple(deck)); decks.append(deck)
            planned[(seed, name)] = decks
    prior_base = EXPS / 'v6-fresh-only-two-seed-geometric-20260907'
    prior = json.loads((prior_base / 'qualification.json').read_text())['prior_corpus']
    prior.update({str(p): sha(p) for p in prior_base.glob('eval_*/common_deck_pairs.jsonl.gz')})
    prior_rows = 0
    for name, digest in prior.items():
        assert sha(Path(name)) == digest
        with gzip.open(name, 'rt', encoding='utf-8') as stream:
            for line in stream:
                assert tuple(json.loads(line)['deck']) not in all_decks
                prior_rows += 1
    sources.update({str(BASE / 'run.py'): sha(BASE / 'run.py'), str(BASE / 'preregistration.md'): sha(BASE / 'preregistration.md'), str(QUAL / 'qualify.py'): sha(QUAL / 'qualify.py')})
    for module in tuple(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if filename and Path(filename).suffix == '.py' and any(part in Path(filename).parts for part in ('alpha_holdem', 'deep_cfr')):
            sources[filename] = sha(Path(filename))
    write('input_contract.json', dict(source_sha256=sources, prior_corpus=prior, prior_rows=prior_rows, unique_decks=len(all_decks), overlap=0, target_execution_hands=98304, command=sys.orig_argv))
    hands, summaries = 0, []
    for row in q['seeds']:
        seed = row['seed']
        members = [init_model(read_checkpoint(Path(p)), 'cuda').eval() for p in row['paths']]
        policies = [('root', members[0]), ('final', members[-1]), ('aggregate', ProbabilityAggregate(members).eval())]
        for name, anchor in anchors:
            costs = {label: dict(seconds=0., decisions=0) for label, _ in policies}
            with (BASE / f'seed{seed}_{name}.jsonl').open('x', encoding='utf-8') as stream, torch.no_grad():
                for index, deck in enumerate(planned[(seed, name)]):
                    rewards = {}
                    for offset in range(3):
                        label, model = policies[(index+offset) % 3]
                        tick = time.monotonic()
                        outcomes = [_play_hand(model, anchor, deck, candidate_seat=seat, candidate_observation_style='legacy_v4', anchor_observation_style='legacy_v4', device='cuda') for seat in (0, 1)]
                        costs[label]['seconds'] += time.monotonic()-tick
                        costs[label]['decisions'] += sum(item[1] for item in outcomes)
                        rewards[label] = [item[0] for item in outcomes]
                        hands += 2
                    stream.write(json.dumps(dict(seed=seed, anchor=name, pair_index=index, deck=deck, rewards_bb=rewards))+'\n')
                    stream.flush()
            summaries.append(dict(seed=seed, anchor=name, costs=costs))
            write(f'seed{seed}_{name}_cost.json', summaries[-1])
            subprocess.run([sys.executable, str(ROOT/'research/experiment_log.py'), 'update', BASE.name, '--count', f'evaluation_hands={hands}', '--note', f'Completed seed{seed} {name}; fixed horizon continues.'], check=True, stdout=subprocess.DEVNULL)
            print(json.dumps(dict(seed=seed, anchor=name, execution_hands=hands)), flush=True)
    assert hands == 98304
    assert all(sha(Path(path)) == digest for path, digest in sources.items())
    write('terminal.json', dict(status='FIXED_HORIZON_COMPLETE_REVIEW_REQUIRED', evaluation_hands=hands, training_hands=0, final_qualification_hands=0, source_hashes_unchanged=True, wall_seconds=time.monotonic()-start, costs=summaries))


if __name__ == '__main__':
    main()
