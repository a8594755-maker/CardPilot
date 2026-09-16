"""Outcome-independent temporal probability aggregation; no weight updates."""
import hashlib
import json
from pathlib import Path
import random
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
import torch
from alpha_holdem.v5_mirror_eval import init_model, read_checkpoint
from alpha_holdem.v6_elo_eval import _observation, greedy_action
from alpha_holdem.rules_v6 import ChipState
from alpha_holdem.policy_contract_v6 import apply_incr


class ProbabilityAggregate(torch.nn.Module):
    def __init__(self, models):
        super().__init__()
        if not models:
            raise ValueError('empty ensemble')
        self.models = torch.nn.ModuleList(models)
        signatures = [tuple(getattr(m, k, False if k == 'requires_position_feature' else 0)
                            for k in ('requires_position_feature', 'position_adapter_hidden',
                                      'position_value_adapter_hidden')) for m in models]
        if any(s != signatures[0] for s in signatures):
            raise ValueError('incompatible position contracts')
        self.requires_position_feature, self.position_adapter_hidden, self.position_value_adapter_hidden = signatures[0]

    def forward(self, cards, actions, extras, mask):
        legal = mask > 0
        if not legal.any(dim=-1).all():
            raise ValueError('empty legal support')
        distributions = []
        for model in self.models:
            logits, _ = model(cards, actions, extras, mask)
            if logits.shape != mask.shape or not torch.isfinite(logits[legal]).all():
                raise ValueError('invalid constituent logits')
            distributions.append(torch.softmax(logits.double().masked_fill(~legal, -torch.inf), -1))
        probability = torch.stack(distributions).mean(0)
        # Probability output represented as logits for the existing greedy runtime.
        return probability.clamp_min(torch.finfo(torch.float64).tiny).log().masked_fill(~legal, -torch.inf), torch.zeros((mask.shape[0], 1), device=mask.device)


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    start = time.monotonic()
    torch.set_num_threads(2)
    base = ROOT / 'research/experiments'
    rows = []
    sources = {}
    for seed in (1, 3):
        paths = [base / 'v6-family-allocation-two-seed-geometric-20260907' / f'seed{seed}_control_stage2/latest.pt']
        paths += [base / 'v6-fresh-only-two-seed-geometric-20260907' / f'seed{seed}_control_stage{stage}/latest.pt' for stage in (1, 2)]
        models, metadata = [], []
        keys = ('env_version', 'obs_version', 'observation_bridge_contract', 'action_space_version', 'raise_action_mapping', 'starting_stack_bb')
        for path in paths:
            sources[str(path)] = sha(path)
            checkpoint = read_checkpoint(path)
            metadata.append({key: checkpoint.get(key) for key in keys})
            models.append(init_model(checkpoint, 'cpu').eval())
            del checkpoint
        assert all(m == metadata[0] for m in metadata)
        assert metadata[0]['env_version'] == 'v6legacyv4obs'
        aggregate = ProbabilityAggregate(models).eval()
        coverage, queries, disagreements = set(), 0, 0
        rng = random.Random(20260908071)
        with torch.no_grad():
            # Eight deterministic passive fixture hands, not strength evaluation.
            for _ in range(8):
                deck = list(range(52))
                rng.shuffle(deck)
                state = ChipState.new(deck)
                while not state.terminal:
                    obs, table = _observation(aggregate, state, 'legacy_v4')
                    tensors = [torch.as_tensor(obs[k], dtype=torch.float32).unsqueeze(0) for k in ('card_info', 'action_info', 'extra_info', 'legal_mask')]
                    legal = tensors[-1] > 0
                    logits, _ = aggregate(*tensors)
                    probabilities = logits.exp()
                    expected = torch.stack([torch.softmax(m(*tensors)[0].double().masked_fill(~legal, -torch.inf), -1) for m in models]).mean(0)
                    torch.testing.assert_close(probabilities, expected, atol=1e-14, rtol=1e-12)
                    torch.testing.assert_close(probabilities.sum(-1), torch.ones(1, dtype=torch.float64))
                    assert (probabilities[~legal] == 0).all()
                    slot = int(expected.argmax(-1).item())
                    assert greedy_action(aggregate, state, observation_style='legacy_v4', device='cpu') == table[slot]
                    single, _ = ProbabilityAggregate([models[-1]])(*tensors)
                    original = models[-1](*tensors)[0].masked_fill(~legal, -torch.inf)
                    assert int(single.argmax(-1)) == int(original.argmax(-1))
                    disagreements += int(slot != int(original.argmax(-1)))
                    coverage.add((state.street, state.actor))
                    queries += 1
                    assert table[1] is not None
                    state = apply_incr(state, table[1])
        assert coverage == {(street, seat) for street in range(4) for seat in range(2)}
        rows.append(dict(seed=seed, paths=[str(p) for p in paths], metadata=metadata[0], fixture_decisions=queries, coverage=sorted(coverage), final_iterate_disagreements=disagreements))
    assert all(sha(Path(path)) == digest for path, digest in sources.items())
    result = dict(passed=True, contract='equal_probability_T1_then_greedy_legacy_v4_physical200_v1', seeds=rows, source_sha256=sources, wall_seconds=time.monotonic()-start, fixture_hand_executions=16, training_hands=0, strength_evaluation_hands=0, final_qualification_hands=0, limitation='Passive reachable fixtures only; no strength or cycle claim. No optimizer averaging. Requires broader edge and invalid-input tests before promotion.')
    output = Path(__file__).with_name('qualification.json')
    with output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps({k: v for k, v in result.items() if k not in ('source_sha256', 'seeds')}))


if __name__ == '__main__':
    main()
