"""Whole-episode historical mixture collection and serializable row reservoir."""
import hashlib
import json
import math
import random
from pathlib import Path

import numpy as np
import torch

KEYS = ('card_info', 'action_info', 'extra_info', 'legal_mask')
SHAPES = ((6, 4, 13), (25, 4, 5), (2,), (9,))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def seed_for(seed, hand, purpose):
    return int.from_bytes(hashlib.sha256(f'{seed}:{hand}:{purpose}'.encode()).digest()[:16], 'little')


def hand_spec(seed, index, count):
    if type(index) is not int or index < 0 or type(count) is not int or count < 1:
        raise ValueError('Invalid hand index or teacher count')
    deck = list(range(52))
    random.Random(seed_for(seed, index, 'deck')).shuffle(deck)
    teachers = [random.Random(seed_for(seed, index, f'teacher:{p}')).randrange(count) for p in (0, 1)]
    return deck, teachers


def uniform_for(seed, hand, seat, decision):
    return random.Random(seed_for(seed, hand, f'action:{seat}:{decision}')).random()


def observation_digest(obs):
    return hashlib.sha256(b''.join(np.asarray(obs[k], dtype='<f4').tobytes() for k in KEYS)).hexdigest()


def softmax_legal(logits, masks):
    x = np.asarray(logits, dtype=np.float64)
    legal = np.asarray(masks) == 1
    if x.ndim != 2 or x.shape[1] != 9 or legal.shape != x.shape or not legal.any(1).all():
        raise ValueError('Invalid policy batch')
    if not np.isfinite(x[legal]).all() or not np.isin(masks, [0, 1]).all():
        raise ValueError('Invalid logits or masks')
    x = np.where(legal, x, -np.inf)
    w = np.exp(x - x.max(1, keepdims=True))
    return w / w.sum(1, keepdims=True)


def select(probs, uniform):
    p = np.asarray(probs, dtype=np.float64)
    if p.shape != (9,) or not np.isfinite(p).all() or np.any(p < 0) or not np.isclose(p.sum(), 1, atol=1e-12) or not 0 <= uniform < 1:
        raise ValueError('Invalid probabilities or draw')
    legal = np.flatnonzero(p > 0)
    return int(legal[min(np.searchsorted(np.cumsum(p[legal]), uniform, side='right'), len(legal)-1)])


@torch.no_grad()
def batch_probs(model, observations, device):
    tensors = [torch.as_tensor(np.stack([o[k] for o in observations]), dtype=torch.float32, device=device) for k in KEYS]
    logits, _ = model(*tensors)
    return softmax_legal(logits.detach().cpu().numpy(), np.stack([o['legal_mask'] for o in observations]))


class Reservoir:
    def __init__(self, capacity, seed):
        if type(capacity) is not int or capacity <= 0:
            raise ValueError('Positive capacity required')
        self.capacity, self.seen = capacity, 0
        self.rng = random.Random(seed)
        self.arrays = {k: np.empty((capacity, *shape), dtype=np.float32) for k, shape in zip(KEYS, SHAPES)}
        self.targets = np.empty((capacity, 9), dtype=np.float64)
        self.ids = np.empty((capacity, 2), dtype=np.int64)

    def add(self, obs, target, identity):
        p = np.asarray(target, dtype=np.float64)
        if p.shape != (9,) or not np.isfinite(p).all() or np.any(p < 0) or not np.isclose(p.sum(), 1, atol=1e-10) or np.any(p[np.asarray(obs['legal_mask']) == 0] != 0):
            raise ValueError('Invalid teacher target')
        for key, shape in zip(KEYS, SHAPES):
            if np.shape(obs[key]) != shape or not np.isfinite(obs[key]).all():
                raise ValueError('Invalid observation')
        self.seen += 1
        j = self.seen-1 if self.seen <= self.capacity else self.rng.randrange(self.seen)
        if j < self.capacity:
            for key in KEYS:
                self.arrays[key][j] = obs[key]
            self.targets[j], self.ids[j] = p, identity

    def __len__(self):
        return min(self.seen, self.capacity)

    def state_dict(self):
        n = len(self)
        return dict(capacity=self.capacity, seen=self.seen, rng=self.rng.getstate(),
                    arrays={k: v[:n].copy() for k, v in self.arrays.items()},
                    targets=self.targets[:n].copy(), ids=self.ids[:n].copy())

    @classmethod
    def restore(cls, state):
        result = cls(state['capacity'], 0)
        result.seen = state['seen']
        result.rng.setstate(state['rng'])
        n = len(result)
        for k in KEYS:
            result.arrays[k][:n] = state['arrays'][k]
        result.targets[:n], result.ids[:n] = state['targets'], state['ids']
        return result


def collect(models, *, seed, hands, out, reservoir=None, slots=256, progress=None):
    from alpha_holdem.rules_v6 import ChipState
    from alpha_holdem.policy_contract_v6 import observation, apply_incr
    if hands <= 0 or slots <= 0:
        raise ValueError('Positive hand/slot budget required')
    out = Path(out)
    if out.exists():
        raise ValueError('No collector overwrite/resume')
    device = next(models[0].parameters()).device
    previous, completed, decisions = '0'*64, 0, 0
    with out.open('x') as handle:
        for begin in range(0, hands, 1024):
            end = min(begin+1024, hands)
            pending, active, completed_rows = begin, [], {}

            def start(index):
                deck, teachers = hand_spec(seed, index, len(models))
                return dict(state=ChipState.new(deck), deck=deck, teachers=teachers, index=index, counts=[0, 0], events=[], rows=[])

            while pending < end and len(active) < slots:
                active.append(start(pending))
                pending += 1
            while active:
                groups = {}
                for entry in active:
                    obs, table = observation(entry['state'])
                    p = entry['state'].actor
                    groups.setdefault(entry['teachers'][p], []).append((entry, obs, table))
                finished = []
                for teacher, entries in groups.items():
                    probs = batch_probs(models[teacher], [e[1] for e in entries], device)
                    for (entry, obs, table), pvec in zip(entries, probs):
                        p = entry['state'].actor
                        u = uniform_for(seed, entry['index'], p, entry['counts'][p])
                        action = select(pvec, u)
                        if table[action] is None:
                            raise ValueError('Illegal teacher action')
                        entry['events'].append(dict(seat=p, teacher=teacher, action=action, increment=table[action],
                            uniform=u, probabilities=pvec.tolist(), observation_sha256=observation_digest(obs)))
                        entry['rows'].append((obs, pvec.copy()))
                        entry['counts'][p] += 1
                        entry['state'] = apply_incr(entry['state'], table[action])
                        if entry['state'].terminal:
                            finished.append(entry)
                for entry in finished:
                    active = [item for item in active if item is not entry]
                    completed_rows[entry['index']] = entry
                    if pending < end:
                        active.append(start(pending))
                        pending += 1
            # Deterministic reservoir order and durable evidence only at full-hand barriers.
            for index in range(begin, end):
                entry = completed_rows[index]
                payoffs = entry['state'].payoffs()
                if sum(payoffs) != 0 or any(abs(v) > 20000 for v in payoffs):
                    raise ValueError('Invalid terminal payoff')
                row = dict(index=index, seed=seed, deck=entry['deck'], teachers=entry['teachers'],
                           events=entry['events'], payoffs=list(payoffs), previous_sha256=previous)
                row['sha256'] = hashlib.sha256(canonical(row).encode()).hexdigest()
                previous = row['sha256']
                handle.write(canonical(row)+'\n')
                if reservoir is not None:
                    for action_index, (obs, target) in enumerate(entry['rows']):
                        reservoir.add(obs, target, (index, action_index))
                completed += 1
                decisions += len(entry['events'])
            handle.flush()
            import os
            os.fsync(handle.fileno())
            if progress:
                progress(completed, decisions)
    return dict(hands=completed, decisions=decisions, trace_tail_sha256=previous, seed=seed)


def audit_trace(path, *, seed, hands, teacher_count, reservoir=None, models=None, model_replay_hands=0):
    from alpha_holdem.rules_v6 import ChipState
    from alpha_holdem.policy_contract_v6 import observation, apply_incr
    from alpha_holdem.execution_v6 import decide
    retained = {} if reservoir is None else {tuple(pair): i for i, pair in enumerate(reservoir.ids[:len(reservoir)])}
    if reservoir is not None and len(retained) != len(reservoir):
        raise ValueError('Duplicate reservoir identity')
    previous, decisions, checked, replayed = '0'*64, 0, 0, 0
    hand_count = 0
    with Path(path).open() as handle:
        for index, line in enumerate(handle):
            assert line.endswith('\n')
            row = json.loads(line)
            digest = row.pop('sha256')
            assert row['previous_sha256'] == previous
            assert hashlib.sha256(canonical(row).encode()).hexdigest() == digest
            previous = digest
            deck, teachers = hand_spec(seed, index, teacher_count)
            assert row['index'] == index and row['seed'] == seed and row['deck'] == deck and row['teachers'] == teachers
            state, counts = ChipState.new(deck), [0, 0]
            for action_index, event in enumerate(row['events']):
                obs, table = observation(state)
                p = state.actor
                assert event['seat'] == p and event['teacher'] == teachers[p]
                assert observation_digest(obs) == event['observation_sha256']
                u = uniform_for(seed, index, p, counts[p])
                assert u == event['uniform']
                probs = np.asarray(event['probabilities'])
                assert np.all(probs[obs['legal_mask'] == 0] == 0)
                action = select(probs, u)
                assert action == event['action'] and table[action] == event['increment'] and table[action] is not None
                if models is not None and index < model_replay_hands:
                    _, direct = decide(models[teachers[p]], state, uniform=u, device=next(models[0].parameters()).device)
                    assert np.allclose(probs, direct['behavior_probs'], rtol=0, atol=2e-5)
                    # Exact actions are reconstructed from stored batch probabilities;
                    # scalar-versus-batch float32 rounding may straddle a draw.
                    replayed += 1
                identity = (index, action_index)
                if identity in retained:
                    j = retained[identity]
                    assert np.array_equal(probs, reservoir.targets[j])
                    for key in KEYS:
                        assert np.array_equal(obs[key], reservoir.arrays[key][j])
                    checked += 1
                state = apply_incr(state, table[action])
                counts[p] += 1
                decisions += 1
            assert state.terminal and list(state.payoffs()) == row['payoffs']
            hand_count += 1
    assert hand_count == hands
    if reservoir is not None:
        assert reservoir.seen == decisions and checked == len(reservoir)
    return dict(status='PASS', hands=hand_count, decisions=decisions, retained_rows_verified=checked,
                scalar_model_replays=replayed, trace_tail_sha256=previous)


def soft_ce(logits, targets, masks):
    if logits.shape != targets.shape or masks.shape != logits.shape or not torch.isfinite(targets).all() or (targets < 0).any() or not torch.allclose(targets.sum(1), torch.ones(len(targets), device=targets.device), atol=1e-5):
        raise ValueError('Invalid supervised target')
    if (targets[masks == 0] != 0).any() or not (masks > 0).any(1).all():
        raise ValueError('Illegal supervised target')
    logp = torch.log_softmax(logits.masked_fill(masks == 0, -1e9), dim=1)
    return -(targets*logp).sum(1)
