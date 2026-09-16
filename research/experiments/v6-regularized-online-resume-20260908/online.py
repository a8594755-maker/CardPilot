"""Synchronous complete-hand PPO engine. Separate schema; NOT a train_v5 resume.

Old replay and league remain in immutable parent, inactive in this new regimen.
Only clean update boundaries are resumable. Production crash journaling remains
required before long runs; this module qualifies exact next-update restoration.
"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import torch

BASE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('target_adapter', BASE.parent / 'v6-regularized-ppo-target-qualification-20260908/qualify.py')
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)
c = adapter.capture


def key(namespace, cursor):
    return int.from_bytes(hashlib.sha256(f'{namespace}:{cursor}'.encode()).digest()[:16], 'big')


class Engine:
    def __init__(self, parent_path, reference_path, namespace, eta):
        self.parent_path = Path(parent_path).resolve()
        self.reference_path = Path(reference_path).resolve()
        self.parent_sha = c.sha(self.parent_path)
        self.reference_sha = c.sha(self.reference_path)
        self.parent = c.read_checkpoint(self.parent_path)
        self.model = c.init_model(self.parent, 'cpu').eval().requires_grad_(True)
        self.reference = c.init_model(c.read_checkpoint(self.reference_path), 'cpu').eval()
        self.optimizer = torch.optim.Adam(self.model.parameters(), lr=1e-4)
        self.optimizer.load_state_dict(copy.deepcopy(self.parent['optimizer']))
        assert adapter.equal(self.optimizer.state_dict(), self.parent['optimizer'])
        self.contract = dict(schema='regularized-online-boundary-v1', namespace=namespace,
            eta_bb=eta, gamma=1, gae_lambda=1, epochs=1, local_reference_kl=0,
            replay='inactive_preserved_in_hash_bound_parent', opponent='standard10',
            mode='sampled_temperature1', observation='legacy_v4', physical_stack_bb=200,
            critic_bounds='terminal_commitment_plus_exact_future_shaping_shift')
        assert isinstance(namespace, str) and namespace and 0 <= eta < float('inf')
        self.cursor = 0
        self.updates = 0
        self.transition_hands = 0
        self.transition_rows = 0
        self.rng = torch.Generator().manual_seed(key(namespace, 0) % (2**63)).get_state()

    def update(self, hands):
        assert isinstance(hands, int) and hands > 0
        rows, traces = [], []
        for _ in range(hands):
            cursor = self.cursor
            deal_key = key(self.contract['namespace'], cursor)
            deck = list(range(52)); random.Random(deal_key).shuffle(deck)
            hero = cursor % 2
            pair = [self.reference, self.reference]; pair[hero] = self.model
            bindings = dict(parent_sha256=self.parent_sha, update=self.updates,
                reference_sha256=self.reference_sha, hero=hero)
            trace = c.capture(pair, self.reference, deck, deal_key, bindings)
            data = adapter.transitions(trace, hero, self.model, self.contract['eta_bb'])
            # Actual terminal commitments bound poker return. Shift each bound by
            # that decision's known future shaping so value clipping does not erase it.
            state = c.ev.ChipState.new(deck)
            for r in trace['rows']:
                _, table = c.ev._observation(self.model, state, 'legacy_v4')
                state = c.ev.apply_incr(state, table[r['slot']])
            committed = [(state.initial[p] - state.stacks[p]) / 100 for p in (0, 1)]
            targets = c.transformed_returns([r['actor'] for r in trace['rows']],
                [r['log_policy'] for r in trace['rows']], [r['log_reference'] for r in trace['rows']],
                trace['terminal_bb'], self.contract['eta_bb'])['returns_bb']
            indices = [i for i, r in enumerate(trace['rows']) if r['actor'] == hero]
            for row, i in zip(data, indices):
                shift = targets[i][hero] - trace['terminal_bb'][hero]
                # Updater uses [-delta2,+delta3]; signed deltas are intentional.
                bounds = (committed[hero] - shift, committed[1-hero] + shift)
                assert -bounds[0] - 1e-8 <= targets[i][hero] <= bounds[1] + 1e-8
                rows.append(row[:9] + bounds)
            trace['terminal_commitments_bb'] = committed
            traces.append(trace)
            self.cursor += 1
            self.transition_hands += bool(data)
        assert rows
        torch.set_rng_state(self.rng)
        stats = adapter.trinal_clip_ppo_update(self.model, self.optimizer, rows, 'cpu',
            epochs=1, mini_batch_size=16384, gamma=1, gae_lambda=1,
            critic_contract='critic_v2', effective_stack_divisor=200,
            entropy_coef=.005, entropy_floor=.05, value_coef=1)
        self.rng = torch.get_rng_state()
        self.updates += 1
        self.transition_rows += len(rows)
        assert all(torch.isfinite(x).all() for x in self.model.state_dict().values())
        return traces, stats

    def save(self, path):
        with Path(path).open('xb') as handle:
            torch.save(dict(contract=self.contract, parent_path=str(self.parent_path),
                reference_path=str(self.reference_path), parent_sha=self.parent_sha,
                reference_sha=self.reference_sha, cursor=self.cursor, updates=self.updates,
                transition_hands=self.transition_hands, transition_rows=self.transition_rows,
                model=self.model.state_dict(), optimizer=self.optimizer.state_dict(), rng=self.rng), handle)

    @classmethod
    def restore(cls, path, expected_contract):
        saved = torch.load(path, map_location='cpu', weights_only=False)
        assert saved['contract'] == expected_contract
        assert c.sha(Path(saved['parent_path'])) == saved['parent_sha']
        assert c.sha(Path(saved['reference_path'])) == saved['reference_sha']
        obj = cls(saved['parent_path'], saved['reference_path'], expected_contract['namespace'], expected_contract['eta_bb'])
        assert obj.contract == expected_contract
        obj.model.load_state_dict(saved['model'])
        obj.optimizer.load_state_dict(saved['optimizer'])
        for field in ('cursor', 'updates', 'transition_hands', 'transition_rows', 'rng'):
            setattr(obj, field, saved[field])
        return obj


def main():
    torch.set_num_threads(1)
    inputs = json.loads((BASE.parent / 'v6-independent-critic-two-seed-geometric-20260908/input_contract.json').read_text())
    reports = []
    with (BASE / 'hands.jsonl').open('x') as evidence:
        for seed in ('1', '3'):
            for eta in (0.0, 0.1):
                name = f'seed{seed}_eta{eta}'
                e = Engine(inputs['parents'][seed]['path'], inputs['anchors']['standard10']['path'],
                    f'regularized-online-20260908-qualification-{name}', eta)
                assert e.parent_sha == inputs['parents'][seed]['sha256']
                trace1, _ = e.update(16)
                boundary = BASE / f'{name}_boundary.pt'; e.save(boundary)
                trace2, stats2 = e.update(16)
                restored = Engine.restore(boundary, e.contract)
                trace3, stats3 = restored.update(16)
                assert trace2 == trace3 and stats2 == stats3
                assert adapter.equal(e.model.state_dict(), restored.model.state_dict())
                assert adapter.equal(e.optimizer.state_dict(), restored.optimizer.state_dict())
                assert torch.equal(e.rng, restored.rng)
                assert e.cursor == restored.cursor == 32 and e.updates == restored.updates == 2
                assert e.transition_hands == restored.transition_hands
                assert e.transition_rows == restored.transition_rows
                assert c.sha(e.parent_path) == e.parent_sha
                wrong = dict(e.contract, eta_bb=eta+1)
                try: Engine.restore(boundary, wrong)
                except AssertionError: pass
                else: raise AssertionError('contract mutation accepted')
                for branch, traces in [('prefix',trace1),('continuous',trace2),('restored',trace3)]:
                    for trace in traces:
                        evidence.write(json.dumps(dict(arm=name,branch=branch,trace=trace))+'\n')
                evidence.flush()
                reports.append(dict(arm=name, completed_live_hands=48, unique_decks=32,
                    boundary_sha=c.sha(boundary), exact_next_update=True,
                    lineage_hands=e.cursor, transition_hands=e.transition_hands, transition_rows=e.transition_rows))
    with (BASE / 'result.json').open('x') as handle:
        json.dump(dict(passed=True,reports=reports,physical_executions=192,unique_decks=128,
            limitations='Synchronous CPU exact clean-boundary proof only; no crash-tail recovery or production throughput claim. Standard10-only fixture opponent is not generalization evidence.'), handle, indent=2)
    print(json.dumps(reports))


if __name__ == '__main__': main()
