"""Bounded read-only source/result synthesis; writes only this review's output."""
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
IDS = (
    'v6-independent-critic-two-seed-geometric-20260908',
    'sampled-policy-frozen-diagnostic-20260830',
    'v6-greedy-advantage-margin-smoke-20260901',
    'v6-source-kl-temperature-65k-greedy-fresh5k-slumbot-20260901',
    'v6-opponent-execution-mixture-two-seed-geometric-20260907',
)


def main():
    evidence = {}
    for name in IDS:
        path = ROOT / 'research/experiments' / name / 'experiment.json'
        raw = path.read_bytes()
        value = json.loads(raw)
        assert value['status'] == 'COMPLETED', name
        evidence[name] = dict(path=str(path), sha256=hashlib.sha256(raw).hexdigest(),
                              result=value['result'])
    sources = {}
    for name in ('scripts/alpha_holdem/v6_elo_eval.py',
                 'scripts/alpha_holdem/v6_public_opponent_matched_eval.py',
                 'scripts/alpha_holdem/v5_mirror_eval.py'):
        raw = (ROOT / name).read_bytes()
        sources[name] = hashlib.sha256(raw).hexdigest()
    result = dict(evidence=evidence, sources=sources, training_hands=0,
                  evaluation_hands=0, slumbot_hands=0,
                  decision='QUALIFY_CURRENT_LINEAGE_SAMPLED_ENDPOINT_COMPARISON',
                  interpretation='Execution mismatch exists but is not an established cause of plateau; earlier sampled evaluation did not confirm general gains. Do not revive prior margin/temperature methods as new discoveries.')
    with (BASE / 'evidence.json').open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps(dict(records=len(evidence), new_hands=0, decision=result['decision'])))


if __name__ == '__main__':
    main()
